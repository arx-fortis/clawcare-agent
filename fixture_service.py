"""Review-only offline service candidate for ClawCare's SYNTHETIC gateway fixture.

Reuses the verified Control repair/checkpoint and process lock implementations.
No shell commands, sockets, real Gateway adapter, provider calls, or credentials.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import sqlite3
import stat
import sys
import threading
import tempfile
import time
import uuid

from control import Control, Denied, digest
from process_lock import process_lock, Busy
from workload_protection import WorkloadProtection, read_workloads

MARKER = 'clawcare-synthetic-service-v1'
TERMINAL = ('VERIFIED', 'ROLLED_BACK', 'ABORTED')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate key')
        result[key] = value
    return result


def read_json(path):
    Control.no_links(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 65536:
        raise Denied('Invalid bounded fixture input')
    value = json.loads(path.read_bytes(), object_pairs_hook=strict_object,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(value, dict):
        raise Denied('Expected a bounded JSON object')
    return value


def private_root(root):
    root = Path(root).absolute()
    Control.no_links(root)
    if not root.is_dir() or (os.name != 'nt' and root.stat().st_mode & 0o077):
        raise Denied('Fixture directory must be private to its local owner')
    return root


def initialize_fixture(root, independent_healthy=True, provider_required=False):
    """Create a NEW synthetic fixture directory. Never accepts an existing path."""
    root = Path(root).absolute()
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    ident = 'fixture-' + uuid.uuid4().hex
    contents = {
        'fixture.json': {'kind': MARKER, 'fixture_id': ident},
        'gateway.json': {'fixture_id': ident, 'enabled': False},
        'signals.json': {'fixture_id': ident, 'responding': True,
                         'independent_healthy': independent_healthy,
                         'provider_required': provider_required},
    }
    for name, value in contents.items():
        Control.atomic_write(root / name, (json.dumps(value) + '\n').encode())
    service = FixtureService(root)
    service.core.pause()  # Initialization grants no authority.
    return service


class FixtureControl(Control):
    """Narrow base extension: cached authorization is checked at the file effect."""
    effect_guard = None
    effect_transaction = None

    def active(self, c):
        super().active(c)
        if self.effect_guard is not None:
            self.effect_guard(c)
            self.effect_transaction = c

    def atomic_write(self, path, payload):
        if self.effect_guard is None or self.effect_transaction is None:
            raise Denied('Fixture effect lacks a live policy guard')
        self.effect_guard(self.effect_transaction)
        fd, temporary = tempfile.mkstemp(prefix='.clawcare-fixture-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            # Temp-file IO can be delayed; recheck immediately before the target effect.
            self.effect_guard(self.effect_transaction)
            os.replace(temporary, path)
            if os.name != 'nt':
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory)
                finally: os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


class FixtureService:
    def __init__(self, root, clock=time.time):
        self.root = private_root(root)
        marker = read_json(self.root / 'fixture.json')
        if set(marker) != {'kind', 'fixture_id'} or marker['kind'] != MARKER:
            raise Denied('Only explicitly marked synthetic fixtures are supported')
        self.fixture_id = marker['fixture_id']
        if not isinstance(self.fixture_id, str) or not self.fixture_id.startswith('fixture-') or len(self.fixture_id) != 40:
            raise Denied('Invalid fixture identity')
        self.database = self.root / 'service.sqlite3'
        if self.database.exists():
            Control.no_links(self.database)
            if self.database.stat().st_nlink != 1:
                raise Denied('Linked database denied')
        else:
            fd = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.core = FixtureControl(self.database)
        self.core.initialize(self.root)
        self.clock = clock
        self.owner = uuid.uuid4().hex
        self.lock = str(self.database) + '.fixture-service.lock'
        self.worker_lock = str(self.database) + '.fixture-service.worker.lock'
        with self.core.tx() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS fixture_service(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    permission_revision INTEGER NOT NULL DEFAULT 1,
                    next_due REAL NOT NULL DEFAULT 0,
                    last_clock REAL NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'IDLE',
                    observation TEXT,
                    lease_owner TEXT, lease_until REAL,
                    active_order TEXT, policy_id TEXT, active_policy_revision INTEGER, active_policy_expiry REAL);
                INSERT OR IGNORE INTO fixture_service(singleton) VALUES(1);
                CREATE TABLE IF NOT EXISTS fixture_receipts(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL UNIQUE,
                    at REAL NOT NULL, outcome TEXT NOT NULL,
                    policy_id TEXT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fixture_failures(
                    code TEXT PRIMARY KEY, first_seen REAL NOT NULL,
                    last_seen REAL NOT NULL, observations INTEGER NOT NULL);
            ''')

    def workload_protection(self, limits=None):
        """Opt-in synthetic policy API; does not alter gateway repair authority."""
        return WorkloadProtection(self.core, self.clock, limits)

    def _state(self, c):
        return dict(c.execute('SELECT * FROM fixture_service WHERE singleton=1').fetchone())

    def _set(self, c, **fields):
        c.execute('UPDATE fixture_service SET ' + ','.join(k + '=?' for k in fields) +
                  ' WHERE singleton=1', tuple(fields.values()))

    def _failure(self, c, code, now):
        c.execute('''INSERT INTO fixture_failures VALUES(?,?,?,1)
            ON CONFLICT(code) DO UPDATE SET last_seen=excluded.last_seen,
            observations=fixture_failures.observations+1''', (code, now, now))

    def observe(self):
        config = read_json(self.root / 'gateway.json')
        signals = read_json(self.root / 'signals.json')
        if (set(config) != {'fixture_id', 'enabled'} or
                set(signals) != {'fixture_id', 'responding', 'independent_healthy', 'provider_required'} or
                config['fixture_id'] != self.fixture_id or signals['fixture_id'] != self.fixture_id or
                type(config['enabled']) is not bool or
                any(type(signals[k]) is not bool for k in ('responding', 'independent_healthy', 'provider_required'))):
            raise Denied('Unexpected synthetic fixture shape')
        symptom_ok = config['enabled'] and signals['responding'] and not signals['provider_required']
        return {'synthetic': True, 'original_symptom_healthy': symptom_ok,
                'independent_signal_healthy': signals['independent_healthy'],
                'healthy': symptom_ok and signals['independent_healthy'],
                'enabled': config['enabled'], 'provider_required': signals['provider_required']}

    def authorize_fixture(self, ttl=300, max_actions=1):
        """Explicit local test-only authorization bundles repair AND conditional rollback."""
        if type(ttl) is not int or not 1 <= ttl <= 900 or type(max_actions) is not int or not 1 <= max_actions <= 3:
            raise Denied('Fixture policy permits 1..900 seconds and 1..3 actions')
        with process_lock(self.lock), self.core.tx() as c:
            state = self._state(c)
            if state['active_order']:
                raise Denied('Reconcile outstanding work before authorization')
            now = self.clock()
            if not math.isfinite(now) or now < state['last_clock']:
                raise Denied('Clock regression requires review')
            policy = {'kind': MARKER, 'fixture_id': self.fixture_id,
                      'policy_id': 'policy-' + uuid.uuid4().hex,
                      'permission_revision': state['permission_revision'],
                      'valid_from': now, 'valid_until': now + ttl,
                      'target': 'gateway.json', 'field': 'enabled', 'desired': True,
                      'actions': ['repair', 'rollback'], 'offline_allowed': True,
                      'max_actions': max_actions}
            Control.atomic_write(self.root / 'policy.json', (json.dumps(policy) + '\n').encode())
            self._set(c, next_due=0, last_clock=now, status='AUTHORIZED_FIXTURE')
            c.execute("UPDATE control_settings SET value='0' WHERE key='paused'")
            self.core.log(c, 'fixture-service', 'FIXTURE_AUTHORIZED', policy_id=policy['policy_id'],
                          synthetic=True, ttl=ttl, max_actions=max_actions)
            return policy['policy_id']

    def revoke(self):
        # BEGIN IMMEDIATE serializes with Control's actual effect transaction.
        # This remains available while the background worker is running.
        with self.core.tx() as c:
            state = self._state(c)
            self._set(c, permission_revision=state['permission_revision'] + 1,
                      status='PAUSED', next_due=0)
            c.execute("UPDATE control_settings SET value='1' WHERE key='paused'")
            c.execute('UPDATE control_orders SET grant=NULL,expires=NULL')
            self.core.log(c, 'fixture-service', 'FIXTURE_REVOKED', synthetic=True)

    def _policy(self, c, now, expected_id=None, allow_consumed=False):
        Control.active(self.core, c)
        policy = read_json(self.root / 'policy.json')
        expected = {'kind', 'fixture_id', 'policy_id', 'permission_revision', 'valid_from',
                    'valid_until', 'target', 'field', 'desired', 'actions', 'offline_allowed', 'max_actions'}
        state = self._state(c)
        if set(policy) != expected:
            raise Denied('Invalid cached policy')
        if (policy['kind'] != MARKER or policy['fixture_id'] != self.fixture_id or
                policy['target'] != 'gateway.json' or policy['field'] != 'enabled' or
                policy['desired'] is not True or policy['actions'] != ['repair', 'rollback'] or
                policy['offline_allowed'] is not True or
                type(policy['permission_revision']) is not int or
                policy['permission_revision'] != state['permission_revision'] or
                type(policy['max_actions']) is not int or not 1 <= policy['max_actions'] <= 3 or
                not isinstance(policy['policy_id'], str) or
                not policy['policy_id'].startswith('policy-') or len(policy['policy_id']) != 39):
            raise Denied('Cached policy scope or revision mismatch')
        start, end = policy['valid_from'], policy['valid_until']
        if (type(start) not in (int, float) or type(end) not in (int, float) or
                not math.isfinite(start) or not math.isfinite(end) or
                not start <= now < end or not 0 < end - start <= 900 or now < state['last_clock']):
            raise Denied('Cached policy expired, future-dated, or clock regressed')
        if expected_id is not None and policy['policy_id'] != expected_id:
            raise Denied('Cached policy replaced during an action')
        count = c.execute('SELECT COUNT(*) FROM fixture_receipts WHERE policy_id=?',
                          (policy['policy_id'],)).fetchone()[0]
        if count >= policy['max_actions'] and not allow_consumed:
            raise Denied('Fixture action budget exhausted')
        return policy

    def _receipt(self, c, order, outcome, observation, now, reconciled=False):
        state = self._state(c)
        row = self.core.order(c, order)
        body = {'schema_version': 1, 'synthetic': True, 'order_id': order,
                'fixture_id': self.fixture_id, 'outcome': outcome,
                'policy_id': state['policy_id'], 'permission_revision': state['active_policy_revision'],
                'policy_valid_until': state['active_policy_expiry'],
                'current_permission_revision': state['permission_revision'],
                'before_hash': row['before_hash'], 'after_hash': row['after_hash'],
                'actual_hash': digest(self.core.file(c, row['target']).read_bytes()),
                'observation': observation,
                'observation_stage': 'restart_reconciliation' if reconciled else 'post_repair_verification',
                'post_action_observation': self.observe(),
                'reconciled_after_restart': reconciled,
                'control_status': row['status'], 'at': now,
                'real_gateway_repaired': False}
        c.execute('INSERT OR IGNORE INTO fixture_receipts(order_id,at,outcome,policy_id,body) VALUES(?,?,?,?,?)',
                  (order, now, outcome, state['policy_id'], json.dumps(body, sort_keys=True)))
        if outcome == 'ROLLED_BACK':
            self._failure(c, 'POST_REPAIR_VERIFICATION_FAILED', now)
        failures = 0 if outcome in ('VERIFIED', 'VERIFIED_RECONCILED') else state['failures'] + 1
        self._set(c, status=outcome, failures=failures, next_due=now + min(300, 5 * 2**min(failures, 6)),
                  lease_owner=None, lease_until=None, active_order=None, policy_id=None,
                  active_policy_revision=None, active_policy_expiry=None,
                  last_clock=now, observation=json.dumps(body['post_action_observation']))
        return body

    def _reconcile(self, now):
        """No expired lease is replay authority. Reconcile durable effects read-only."""
        with self.core.tx() as c:
            state = self._state(c)
            order = state['active_order']
            if not order:
                orphan = c.execute("SELECT id FROM control_orders WHERE status NOT IN ('VERIFIED','ROLLED_BACK','ABORTED') LIMIT 1").fetchone()
                if not orphan:
                    return None
                order = orphan['id']
                self._set(c, active_order=order, policy_id=None, active_policy_revision=None, active_policy_expiry=None)
            row = self.core.order(c, order)
            observed = self.observe()
            actual = digest(self.core.file(c, row['target']).read_bytes())
            if row['status'] == 'VERIFIED' and actual == row['after_hash'] and observed['healthy']:
                outcome = 'VERIFIED_RECONCILED'
            elif row['status'] == 'ROLLED_BACK' and actual == row['before_hash']:
                outcome = 'ROLLED_BACK_RECONCILED'
            elif row['status'] == 'AWAITING_APPROVAL' and actual == row['before_hash']:
                c.execute("UPDATE control_orders SET status='ABORTED',grant=NULL,expires=NULL WHERE id=?", (order,))
                outcome = 'INTERRUPTED_NO_EFFECT'
            else:
                c.execute("UPDATE control_orders SET status='RECOVERY_REQUIRED',grant=NULL,expires=NULL WHERE id=?", (order,))
                outcome = 'NEEDS_RECONCILIATION'
            self.core.log(c, order, 'FIXTURE_RECONCILED', outcome=outcome, automatic_replay=False)
            return self._receipt(c, order, outcome, observed, now, reconciled=True)

    def tick(self):
        with process_lock(self.lock):
            return self._tick()

    def _tick(self):
        now = self.clock()
        with self.core.tx() as c:
            state = self._state(c)
            if not math.isfinite(now) or now < state['last_clock']:
                self._set(c, status='CLOCK_REVIEW_REQUIRED')
                return {'status': 'CLOCK_REVIEW_REQUIRED', 'synthetic': True}
        if state['status'] == 'NEEDS_RECONCILIATION' and not state['active_order']:
            return {'status': 'NEEDS_RECONCILIATION', 'synthetic': True}
        reconciled = self._reconcile(now)
        if reconciled:
            return reconciled
        with self.core.tx() as c:
            state = self._state(c)
            if state['status'] == 'NEEDS_RECONCILIATION':
                return {'status': 'NEEDS_RECONCILIATION', 'synthetic': True}
            if now < state['next_due']:
                return {'status': 'NOT_DUE', 'next_due': state['next_due'], 'synthetic': True}
            # Lease metadata is evidence only; the same-host OS lock is the exclusion mechanism.
            self._set(c, lease_owner=self.owner, lease_until=now + 30, last_clock=now)
        try:
            observed = self.observe()
            if observed['healthy']:
                return self._record_observation('HEALTHY', observed, now)
            if observed['provider_required']:
                return self._record_observation('ONLINE_REQUIRED', observed, now, failure=True)
            if observed['enabled']:
                return self._record_observation('DIAGNOSIS_REQUIRED', observed, now, failure=True)
            with self.core.tx() as c:
                self._failure(c, 'FIXTURE_DISABLED', now)
                policy = self._policy(c, now)
            order = self.core.propose('gateway.json', 'enabled', True)
            with self.core.tx() as c:
                self._set(c, active_order=order['id'], policy_id=policy['policy_id'],
                          active_policy_revision=policy['permission_revision'],
                          active_policy_expiry=policy['valid_until'], status='CHECKPOINTED')
            return self._execute(order['id'], policy['policy_id'])
        except (Denied, ValueError, OSError):
            with self.core.tx() as c:
                if self._state(c)['active_order']:
                    # Durable pending state is deliberately left for passive reconciliation.
                    self._set(c, status='INTERRUPTED', lease_owner=None, lease_until=None)
                    return {'status': 'INTERRUPTED', 'synthetic': True}
            return self._record_observation('POLICY_OR_INPUT_BLOCKED', None, now, failure=True)

    def _record_observation(self, status, observed, now, failure=False):
        with self.core.tx() as c:
            if failure:
                self._failure(c, status, now)
            self._set(c, status=status, observation=json.dumps(observed), last_clock=now,
                      next_due=now + 5, lease_owner=None, lease_until=None)
        return {'status': status, 'observation': observed, 'synthetic': True}

    def _execute(self, order, policy_id):
        self.core.effect_guard = lambda c: self._policy(c, self.clock(), policy_id)
        try:
            return self._execute_guarded(order, policy_id)
        finally:
            self.core.effect_guard = None
            self.core.effect_transaction = None

    def _execute_guarded(self, order, policy_id):
        # Every effect rechecks the current cached policy; no model or remote grant is consulted.
        with self.core.tx() as c:
            now = self.clock()
            policy = self._policy(c, now, policy_id)
            scope = self.core.order(c, order)['scope']
        self.core.approve(order, scope, ttl=max(1, min(300, math.ceil(policy['valid_until'] - now))))
        with self.core.tx() as c:
            self._policy(c, self.clock(), policy_id)
            c.execute('UPDATE control_orders SET expires=MIN(expires,?) WHERE id=?', (policy['valid_until'], order))
        self.core.execute(order)
        # Control's byte check alone is insufficient. Verify the original symptom and
        # the independent fixture health channel without trusting repair return value.
        observed = self.observe()
        if observed['healthy']:
            outcome = 'VERIFIED'
        else:
            with self.core.tx() as c:
                now = self.clock()
                policy = self._policy(c, now, policy_id)
                scope = self.core.approval_scope(self.core.order(c, order), 'rollback')
            self.core.approve(order, scope, ttl=max(1, min(300, math.ceil(policy['valid_until'] - now))), action='rollback')
            with self.core.tx() as c:
                self._policy(c, self.clock(), policy_id)
                c.execute('UPDATE control_orders SET expires=MIN(expires,?) WHERE id=?', (policy['valid_until'], order))
            self.core.execute(order, action='rollback')
            with self.core.tx() as c:
                row = self.core.order(c, order)
                restored = digest(self.core.file(c, row['target']).read_bytes()) == row['before_hash']
            outcome = 'ROLLED_BACK' if restored else 'NEEDS_RECONCILIATION'
        with self.core.tx() as c:
            return self._receipt(c, order, outcome, observed, self.clock())

    def run(self, stop, poll=0.25):
        if not 0.01 <= poll <= 60:
            raise ValueError('Invalid poll interval')
        with process_lock(self.worker_lock):
            while not stop.is_set():
                try:
                    self.tick()
                except Busy:
                    pass  # A short owner operation holds the effect lock; try next tick.
                stop.wait(poll)


class ReadView:
    """Read-only SQLite views; construction does not initialize or mutate the ledger."""
    def __init__(self, root):
        self.root = private_root(root)
        self.db = self.root / 'service.sqlite3'
        Control.no_links(self.db)
        if not self.db.is_file() or self.db.stat().st_nlink != 1:
            raise Denied('Fixture ledger unavailable')

    @contextmanager
    def _connect(self):
        c = sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

    def health(self):
        with self._connect() as c:
            r = dict(c.execute('SELECT * FROM fixture_service WHERE singleton=1').fetchone())
        return {'synthetic': True, 'status': r['status'], 'last_observed_at': r['last_clock'],
                'next_due': r['next_due'], 'active_order': r['active_order'],
                'observation': json.loads(r['observation']) if r['observation'] else None,
                'note': 'Last recorded evidence only; not proof the service or real gateway is running.'}

    def work_order_status(self, order_id):
        if not isinstance(order_id, str) or len(order_id) > 80:
            raise ValueError('Invalid order ID')
        with self._connect() as c:
            receipt = c.execute('SELECT body FROM fixture_receipts WHERE order_id=?', (order_id,)).fetchone()
            if receipt:
                return json.loads(receipt[0])
            row = c.execute('SELECT id,status,attempts FROM control_orders WHERE id=?', (order_id,)).fetchone()
            if not row:
                return {'synthetic': True, 'status': 'NOT_FOUND'}
            return {'synthetic': True, 'id': row['id'], 'status': 'PENDING_SERVICE_VERIFICATION',
                    'control_status': row['status'], 'attempts': row['attempts'],
                    'note': 'Control byte verification alone is not service health verification.'}

    def workload_status(self):
        with self._connect() as c:
            return read_workloads(c)

    def failure_records(self):
        with self._connect() as c:
            return {'synthetic': True, 'failures': [dict(r) for r in c.execute(
                'SELECT * FROM fixture_failures ORDER BY last_seen DESC LIMIT 100')]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init-fixture')
    a = sub.add_parser('authorize-fixture')
    a.add_argument('--ttl', type=int, default=300)
    a.add_argument('--max-actions', type=int, default=1)
    sub.add_parser('revoke')
    sub.add_parser('once')
    sub.add_parser('status')
    a = sub.add_parser('run')
    a.add_argument('--managed', action='store_true')
    args = p.parse_args()
    try:
        if args.command == 'init-fixture':
            initialize_fixture(args.root)
            result = {'status': 'PAUSED_FIXTURE_CREATED', 'synthetic': True}
        elif args.command == 'status':
            result = ReadView(args.root).health()
        else:
            service = FixtureService(args.root)
            if args.command == 'authorize-fixture':
                result = {'policy_id': service.authorize_fixture(args.ttl, args.max_actions), 'synthetic': True}
            elif args.command == 'revoke':
                service.revoke(); result = {'status': 'PAUSED', 'synthetic': True}
            elif args.command == 'once':
                result = service.tick()
            else:
                stop = threading.Event()
                for sig in (signal.SIGINT, signal.SIGTERM):
                    signal.signal(sig, lambda *_: stop.set())
                if args.managed:
                    def watch_parent():
                        sys.stdin.buffer.read()
                        os._exit(0)
                    threading.Thread(target=watch_parent, daemon=True).start()
                service.run(stop)
                return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except Busy:
        return 75
    except (Denied, ValueError, OSError, sqlite3.Error):
        print('Fixture service blocked; inspect private fixture inputs and authorization.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
