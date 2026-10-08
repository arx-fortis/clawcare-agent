"""Dependency-free, SYNTHETIC workload decisions; never starts or kills a worker.

Trusted-local fixture callers supply observations and independent verification.
SQLite transactions durably reserve actions before an adapter could act. A claim
is not permission to run a real operation and is never automatically replayed.
"""
from dataclasses import asdict, dataclass
import json
import math
import re
import time


@dataclass(frozen=True)
class Limits:
    sample_max_age: int = 30
    reserve_bytes: int = 256 * 1024 * 1024
    recovery_margin_bytes: int = 128 * 1024 * 1024
    cooldown_seconds: int = 10
    stall_seconds: int = 60
    heartbeat_max_age: int = 30
    verification_max_age: int = 30
    max_attempts: int = 3

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in asdict(self).values()):
            raise ValueError('Limits must be positive integers')
        if self.max_attempts > 3:
            raise ValueError('At most three lifetime attempts per task')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', value):
        raise ValueError('Invalid bounded identifier')
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('Expected SHA-256')
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def encode(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))


class WorkloadProtection:
    """Use the candidate's existing FULL-synchronous SQLite transaction provider.

    Limits persist and cannot silently change on restart. All timestamps use an
    injected wall clock; backwards/nonfinite time fails closed, not recovered.
    """
    def __init__(self, core, clock=time.time, limits=None):
        self.core, self.clock = core, clock
        with core.tx() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS workload_state(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workload_tasks(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workload_actions(id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                    item_id TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workload_observations(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workload_alerts(task_id TEXT NOT NULL, code TEXT NOT NULL,
                    first_seen REAL NOT NULL, last_seen REAL NOT NULL, observations INTEGER NOT NULL,
                    PRIMARY KEY(task_id, code));
            ''')
            row = c.execute('SELECT body FROM workload_state WHERE singleton=1').fetchone()
            if row:
                state = json.loads(row[0])
                self.limits = Limits(**state['limits'])
                if limits is not None and limits != self.limits:
                    raise ValueError('Persisted limits cannot change implicitly')
            else:
                self.limits = limits or Limits()
                c.execute('INSERT INTO workload_state VALUES(1,?)', (encode({
                    'limits': asdict(self.limits), 'last_clock': 0, 'sample': None, 'sample_seq': 0, 'sample_watermark': None}),))

    def _now(self, c):
        now = self.clock()
        state = json.loads(c.execute('SELECT body FROM workload_state WHERE singleton=1').fetchone()[0])
        if not number(now) or now < state['last_clock']:
            raise ValueError('Clock invalid or regressed; review required')
        state['last_clock'] = now
        self._state(c, state)
        return now, state

    @staticmethod
    def _state(c, state):
        c.execute('UPDATE workload_state SET body=? WHERE singleton=1', (encode(state),))

    @staticmethod
    def _task(c, task_id):
        identifier(task_id)
        row = c.execute('SELECT body FROM workload_tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown task')
        return json.loads(row[0])

    @staticmethod
    def _save(c, task):
        c.execute('UPDATE workload_tasks SET body=? WHERE id=?', (encode(task), task['id']))

    @staticmethod
    def _alert(c, task_id, code, now):
        c.execute('''INSERT INTO workload_alerts VALUES(?,?,?,?,1)
            ON CONFLICT(task_id,code) DO UPDATE SET last_seen=excluded.last_seen,
            observations=workload_alerts.observations+1''', (task_id, code, now, now))

    def register(self, task_id, required_bytes, checkpoint_ref, checkpoint_sha256, completed=None, preserved=None):
        """Store immutable checkpoint references, not checkpoint bytes or paths to open.

        completed is the fixture's already independently verified item/digest map.
        Re-registering never overwrites checkpoints, progress, actions or budgets.
        """
        identifier(task_id); identifier(checkpoint_ref); sha(checkpoint_sha256)
        if type(required_bytes) is not int or required_bytes <= 0:
            raise ValueError('Positive workload estimate required')
        completed = dict(completed or {})
        preserved = dict(preserved or {})
        if len(preserved) > 10000:
            raise ValueError('Preserved inventory too large')
        for item, status in preserved.items():
            identifier(item)
            if status not in ('saved_unverified', 'draft') or item in completed:
                raise ValueError('Invalid preserved item state')
        if len(completed) > 10000:
            raise ValueError('Checkpoint inventory too large')
        for item, digest in completed.items():
            identifier(item); sha(digest)
        with self.core.tx() as c:
            now, _ = self._now(c)
            old = c.execute('SELECT body FROM workload_tasks WHERE id=?', (task_id,)).fetchone()
            if old:
                task = json.loads(old[0])
                if (required_bytes, checkpoint_ref, checkpoint_sha256) != (
                        task['required_bytes'], task['checkpoint_ref'], task['checkpoint_sha256']):
                    raise ValueError('Task/checkpoint identity is immutable')
                return task
            task = {'id': task_id, 'required_bytes': required_bytes,
                    'checkpoint_ref': checkpoint_ref, 'checkpoint_sha256': checkpoint_sha256,
                    'completed': completed, 'preserved': preserved, 'fault_revision': 0, 'fault_at': 0, 'progress_fault_revision': 0, 'progress_seq': 0, 'progress_at': now,
                    'heartbeat_at': None, 'attempts': 0, 'status': 'READY',
                    'recovering': False, 'uncertain': False, 'retry_after': 0,
                    'good_samples': 0, 'last_good_sample': None, 'good_since': None,
                    'checkpoint_verification': None, 'worker_quiescent_at': None}
            c.execute('INSERT INTO workload_tasks VALUES(?,?)', (task_id, encode(task)))
            return task

    def observe_memory(self, observed_at, available_bytes, total_bytes):
        """Invalid/missing/future samples replace usable evidence with UNKNOWN.

        Older or repeated timestamp samples cannot refresh evidence or count as
        a second recovery sample. Host data is never collected by this module.
        """
        with self.core.tx() as c:
            now, state = self._now(c)
            previous = state.get('sample_watermark')
            valid = (number(observed_at) and observed_at <= now and
                     type(available_bytes) is int and type(total_bytes) is int and
                     0 <= available_bytes <= total_bytes and total_bytes > 0)
            timestamp = observed_at if number(observed_at) and observed_at <= now else now
            if previous is not None and number(observed_at) and observed_at <= now:
                if timestamp < previous:
                    return False
                if timestamp == previous:
                    if valid and state['sample'] == {'observed_at': observed_at,
                            'available_bytes': available_bytes, 'total_bytes': total_bytes}:
                        return False
                    valid = False  # Conflicting same-time evidence invalidates admission.
            state['sample_watermark'] = max(timestamp, previous or 0)
            state['sample_seq'] += 1
            state['sample'] = ({'observed_at': observed_at, 'available_bytes': available_bytes,
                                'total_bytes': total_bytes} if valid else None)
            self._state(c, state)
            # Consume every sample so pressure cannot disappear between assessments.
            for row in c.execute('SELECT body FROM workload_tasks').fetchall():
                self._assessment(c, json.loads(row[0]), state, now)
            return valid

    def heartbeat(self, task_id, progress_seq):
        """A heartbeat refreshes liveness only; strictly increasing durable units
        refresh progress. Adapters must never use heartbeat count as progress.
        """
        if type(progress_seq) is not int or progress_seq < 0:
            raise ValueError('Expected a monotonic progress sequence')
        with self.core.tx() as c:
            now, _ = self._now(c)
            task = self._task(c, task_id)
            if progress_seq < task['progress_seq']:
                raise ValueError('Progress regression')
            if progress_seq > task['progress_seq']:
                task['progress_at'], task['progress_seq'] = now, progress_seq
                task['progress_fault_revision'] = task['fault_revision']
            task['heartbeat_at'] = now
            task['worker_quiescent_at'] = None
            self._save(c, task)

    def _fault(self, c, task, code, now, uncertain=False):
        if not task['recovering']:
            task['retry_after'] = now + self.limits.cooldown_seconds
            task['good_samples'], task['good_since'], task['last_good_sample'] = 0, None, None
        task['fault_revision'] += 1
        task['fault_at'] = now
        task['recovering'] = True
        task['uncertain'] = task['uncertain'] or uncertain
        task['status'] = 'NEEDS_RECONCILIATION' if task['uncertain'] else 'PAUSED'
        self._alert(c, task['id'], code, now)

    def observe_cause(self, event_id, domain, code, observed_at, task_id):
        """Independent observed events; temporal precedence NEVER implies cause."""
        identifier(event_id); identifier(code)
        if domain not in ('host', 'gateway', 'task'):
            raise ValueError('Separate host/gateway/task domain required')
        with self.core.tx() as c:
            now, _ = self._now(c)
            if not number(observed_at) or observed_at > now:
                raise ValueError('Invalid event time')
            task = self._task(c, task_id)
            event = {'id': event_id, 'domain': domain, 'code': code,
                     'observed_at': observed_at, 'task_id': task_id, 'causal_link': 'unknown'}
            old = c.execute('SELECT body FROM workload_observations WHERE id=?', (event_id,)).fetchone()
            if old:
                if json.loads(old[0]) != event:
                    raise ValueError('Event ID conflict')
                return False
            c.execute('INSERT INTO workload_observations VALUES(?,?)', (event_id, encode(event)))
            self._fault(c, task, code, now, uncertain=(code == 'DISCONNECTED'))
            self._save(c, task)
            return True

    def verify_checkpoint(self, task_id, checkpoint_sha256, outputs_verified, observed_at):
        """Record a fresh independent adapter report for the immutable checkpoint
        and its verified output inventory. Preserved drafts stay blocked.
        Does not itself resume work.
        """
        sha(checkpoint_sha256)
        if type(outputs_verified) is not bool:
            raise ValueError('Explicit verification required')
        with self.core.tx() as c:
            now, _ = self._now(c)
            task = self._task(c, task_id)
            passed = (outputs_verified and checkpoint_sha256 == task['checkpoint_sha256'] and
                      number(observed_at) and task['fault_at'] <= observed_at <= now and now - observed_at <= self.limits.verification_max_age)
            report = {'passed': bool(passed), 'observed_at': observed_at if number(observed_at) and observed_at <= now else now,
                      'fault_revision': task['fault_revision'], 'checkpoint_sha256': checkpoint_sha256}
            previous = task['checkpoint_verification']
            if previous and report['observed_at'] < previous['observed_at']:
                return False
            if previous and report['observed_at'] == previous['observed_at']:
                if previous == report:
                    return previous['passed']
                previous['passed'] = False
                task['checkpoint_verification'] = previous
                self._save(c, task)
                return False
            task['checkpoint_verification'] = report
            self._save(c, task)
            return bool(passed)

    def _assessment(self, c, task, state, now):
        sample = state['sample']
        reserved, reserved_tasks = 0, set()
        for row in c.execute('SELECT a.body,t.body FROM workload_tasks t LEFT JOIN workload_actions a ON t.id=a.task_id WHERE t.id != ?', (task['id'],)):
            action, other = json.loads(row[0]) if row[0] else None, json.loads(row[1])
            holding = other['uncertain'] or (action is not None and (
                action['status'] in ('CLAIMED', 'UNKNOWN') or not sample or
                sample['observed_at'] <= action.get('last_report_at', action['at'])))
            if holding and other['id'] not in reserved_tasks:
                reserved += other['required_bytes']
                reserved_tasks.add(other['id'])
        live = ('QUIESCENT' if task['worker_quiescent_at'] is not None else 'UNKNOWN' if task['heartbeat_at'] is None or
                now - task['heartbeat_at'] > self.limits.heartbeat_max_age else
                'STALLED' if now - task['progress_at'] >= self.limits.stall_seconds else 'PROGRESSING')
        if live == 'STALLED':
            self._fault(c, task, 'LIVE_BUT_STALLED', now)
        if not sample or not 0 <= now - sample['observed_at'] <= self.limits.sample_max_age:
            memory, reason = 'unknown', 'MISSING_OR_STALE_MEMORY'
        elif sample['available_bytes'] < task['required_bytes'] + reserved + self.limits.reserve_bytes + (
                self.limits.recovery_margin_bytes if task['recovering'] else 0):
            memory, reason = 'pause', 'MEMORY_PRESSURE'
        else:
            memory, reason = 'allow', 'HEADROOM_VALID'
        if memory != 'allow':
            self._fault(c, task, reason, now)
            task['good_samples'], task['good_since'], task['last_good_sample'] = 0, None, None
        elif task['recovering']:
            if task['last_good_sample'] != state['sample_seq']:
                task['good_samples'] += 1
                task['last_good_sample'] = state['sample_seq']
                if task['good_since'] is None:
                    task['good_since'] = now
            if (task['good_samples'] < 2 or now < task['retry_after'] or
                    now - task['good_since'] < self.limits.cooldown_seconds):
                memory, reason = 'pause', 'RECOVERY_COOLDOWN'
        self._save(c, task)
        return {'synthetic': True, 'memory': memory, 'reason': reason, 'worker': live,
                'status': task['status'], 'uncertain': task['uncertain'],
                'attempts': task['attempts'], 'other_reserved_bytes': reserved, 'checkpoint_ref': task['checkpoint_ref']}

    def assess(self, task_id):
        with self.core.tx() as c:
            now, state = self._now(c)
            return self._assessment(c, self._task(c, task_id), state, now)

    def reconcile_disconnect(self, task_id, worker_quiescent, no_untracked_effects):
        """Explicit trusted fixture evidence, never inferred from lack of heartbeat.
        Pending claims must be reconciled individually before uncertainty clears.
        """
        if worker_quiescent is not True or no_untracked_effects is not True:
            return False
        with self.core.tx() as c:
            now, _ = self._now(c)
            task = self._task(c, task_id)
            if self._pending(c, task_id):
                return False
            task['uncertain'] = False
            task['worker_quiescent_at'] = now
            task['status'] = 'PAUSED'
            self._save(c, task)
            return True

    @staticmethod
    def _pending(c, task_id):
        return any(json.loads(row[0])['status'] in ('CLAIMED', 'UNKNOWN') for row in c.execute(
            'SELECT body FROM workload_actions WHERE task_id=?', (task_id,)))

    def claim(self, task_id, item_id, action_id):
        """Reserve a synthetic plan once. No execution, permission, or auto replay.
        A committed claim with an uncertain return remains pending after restart.
        """
        identifier(item_id); identifier(action_id)
        with self.core.tx() as c:
            now, state = self._now(c)
            task = self._task(c, task_id)
            old = c.execute('SELECT task_id,item_id FROM workload_actions WHERE id=?', (action_id,)).fetchone()
            if old:
                if tuple(old) != (task_id, item_id):
                    raise ValueError('Action identity conflict')
                return {'decision': 'EXISTING_ACTION', 'execute': False}
            assessment = self._assessment(c, task, state, now)
            if item_id in task['completed']:
                reason = 'ALREADY_VERIFIED'
            elif item_id in task['preserved']:
                reason = 'PRESERVED_OUTPUT_REQUIRES_REVIEW'
            elif task['uncertain'] or self._pending(c, task_id):
                reason = 'NEEDS_RECONCILIATION'
            elif task['attempts'] >= self.limits.max_attempts:
                reason = 'RETRY_BUDGET_EXHAUSTED'
            elif assessment['memory'] != 'allow':
                reason = assessment['reason']
            elif task['recovering'] and (task['worker_quiescent_at'] is None or
                    now - task['worker_quiescent_at'] > self.limits.verification_max_age):
                reason = 'WORKER_NOT_QUIESCENT'
            elif now < task['retry_after']:
                reason = 'RETRY_COOLDOWN'
            else:
                verification = task['checkpoint_verification']
                reason = None if verification and verification['passed'] and verification['fault_revision'] == task['fault_revision'] and 0 <= now - verification[
                    'observed_at'] <= self.limits.verification_max_age else 'CHECKPOINT_UNVERIFIED'
            if reason:
                self._alert(c, task_id, reason, now)
                return {'decision': reason, 'execute': False}
            task['attempts'] += 1
            task['status'] = 'AWAITING_VERIFICATION'
            action = {'id': action_id, 'task_id': task_id, 'item_id': item_id, 'status': 'CLAIMED',
                      'at': now, 'progress_seq': task['progress_seq'], 'attempt': task['attempts']}
            c.execute('INSERT INTO workload_actions VALUES(?,?,?,?)', (action_id, task_id, item_id, encode(action)))
            self._save(c, task)
            return {'decision': 'CLAIMED_SYNTHETIC_PLAN', 'execute': False, 'action': action}

    def reconcile_verified_action(self, action_id, *, observed_at, output_sha256,
                                  checkpoint_sha256, output_verified, worker_quiescent,
                                  no_untracked_effects):
        """Record independently re-read output without replay or recovery claims.

        Only a trusted owned-workload adapter can establish these assertions.
        This resolves an ambiguous effect, never grants a new execution or marks
        a running worker healthy. New work still needs fresh admission/checkpoint
        verification and the original finite budget.
        """
        identifier(action_id); sha(output_sha256); sha(checkpoint_sha256)
        if output_verified is not True or worker_quiescent is not True or no_untracked_effects is not True:
            raise ValueError('Explicit independent reconciliation evidence required')
        with self.core.tx() as c:
            now, _ = self._now(c)
            row = c.execute('SELECT body FROM workload_actions WHERE id=?', (action_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown action')
            action = json.loads(row[0])
            task = self._task(c, action['task_id'])
            if (not number(observed_at) or not max(action['at'], task['fault_at']) <= observed_at <= now or
                    now - observed_at > self.limits.verification_max_age or
                    checkpoint_sha256 != task['checkpoint_sha256'] or
                    action['status'] == 'NO_EFFECT'):
                raise ValueError('Reconciliation evidence is stale or conflicting')
            old = task['completed'].get(action['item_id'])
            if old is not None and old != output_sha256:
                raise ValueError('Verified output identity conflict')
            action.update(status='VERIFIED', last_report_at=now, last_report_observed_at=observed_at,
                          reconciled_without_replay=True)
            c.execute('UPDATE workload_actions SET body=? WHERE id=?', (encode(action), action_id))
            task['completed'][action['item_id']] = output_sha256
            task['uncertain'] = self._pending(c, task['id'])
            task['status'] = 'NEEDS_RECONCILIATION' if task['uncertain'] else 'PAUSED'
            task['worker_quiescent_at'] = observed_at
            self._save(c, task)
            return {'status': 'VERIFIED', 'recovered': False, 'replayed': False}

    def outcome(self, action_id, outcome, *, observed_at, output_sha256=None,
                output_verified=False, independent_healthy=False, original_symptom_healthy=False, worker_quiescent=False):
        """Independent output + symptom + subsequent progress are all required.
        Known no-effect failures need positive quiescence evidence before retry.
        Unknown results retain their action and cannot be replayed automatically.
        """
        identifier(action_id)
        if outcome not in ('verified', 'no_effect', 'unknown'):
            raise ValueError('Invalid outcome')
        with self.core.tx() as c:
            now, state = self._now(c)
            row = c.execute('SELECT body FROM workload_actions WHERE id=?', (action_id,)).fetchone()
            if row is None:
                raise ValueError('Unknown action')
            action = json.loads(row[0])
            if action['status'] in ('VERIFIED', 'NO_EFFECT'):
                return {'status': action['status'], 'duplicate': True}
            task = self._task(c, action['task_id'])
            if 'last_report_observed_at' in action and number(observed_at) and observed_at < action['last_report_observed_at']:
                return {'status': action['status'], 'duplicate': True, 'report_rejected': True}
            fresh = number(observed_at) and max(action['at'], task['fault_at']) <= observed_at <= now and now - observed_at <= self.limits.verification_max_age
            assessment = self._assessment(c, task, state, now)
            if (outcome == 'verified' and fresh and output_verified is True and independent_healthy is True and original_symptom_healthy is True and
                    task['progress_seq'] > action['progress_seq'] and task['progress_at'] <= observed_at and
                    task['progress_fault_revision'] == task['fault_revision'] and
                    assessment['memory'] == 'allow' and assessment['worker'] == 'PROGRESSING'):
                sha(output_sha256)
                action['status'] = 'VERIFIED'
                task['completed'][action['item_id']] = output_sha256
                if task['uncertain']:
                    task['status'] = 'NEEDS_RECONCILIATION'
                else:
                    task['status'] = 'VERIFIED_RECOVERY' if task['recovering'] else 'VERIFIED_OUTPUT'
                    task['recovering'] = False
            elif (outcome == 'no_effect' and fresh and worker_quiescent is True and
                  (task['heartbeat_at'] is None or observed_at >= task['heartbeat_at']) and
                  task['progress_seq'] == action['progress_seq']):
                action['status'] = 'NO_EFFECT'
                self._fault(c, task, 'KNOWN_NO_EFFECT', now)
                task['worker_quiescent_at'] = observed_at
                task['retry_after'] = now + self.limits.cooldown_seconds * 2 ** (task['attempts'] - 1)
            else:
                action['status'] = 'UNKNOWN'
                self._fault(c, task, 'OUTPUT_UNVERIFIED', now, uncertain=True)
            action['last_report_at'] = now
            if number(observed_at) and observed_at <= now:
                action['last_report_observed_at'] = max(observed_at, action.get('last_report_observed_at', action['at']))
            c.execute('UPDATE workload_actions SET body=? WHERE id=?', (encode(action), action_id))
            self._save(c, task)
            return {'status': action['status'], 'task_status': task['status'], 'duplicate': False}


def task_summary(body):
    task = json.loads(body)
    completed = task.pop('completed')
    preserved = task.pop('preserved')
    task['completed_count'] = len(completed)
    task['preserved_counts'] = {kind: sum(value == kind for value in preserved.values())
                                for kind in ('saved_unverified', 'draft')}
    return task


def read_workloads(connection):
    """Bounded read-only projection; works against an older candidate ledger."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workload_tasks'").fetchone():
        return {'synthetic': True, 'tasks': [], 'alerts': [], 'observations': [], 'actions': [],
                'note': 'Workload policy not initialized; no live resource collector.'}
    return {'synthetic': True,
            'tasks': [task_summary(r[0]) for r in connection.execute('SELECT body FROM workload_tasks ORDER BY id LIMIT 100')],
            'actions': [json.loads(r[0]) for r in connection.execute('SELECT body FROM workload_actions ORDER BY id LIMIT 100')],
            'observations': [json.loads(r[0]) for r in connection.execute('SELECT body FROM workload_observations ORDER BY id LIMIT 100')],
            'alerts': [dict(r) for r in connection.execute('SELECT * FROM workload_alerts ORDER BY last_seen DESC LIMIT 100')],
            'note': 'Last recorded SYNTHETIC evidence; no live collection, execution, causal proof, or real recovery claim.'}
