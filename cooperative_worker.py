"""Experimental governor for its own tiny deterministic local artifact workload.

Actual file writes and independent verification, simulated or real observations.
No user jobs, shell/process control, gateways, providers, installations or network.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

from control import Control, Denied
from fixture_service import FixtureService, initialize_fixture, read_json, private_root, MARKER as FIXTURE_MARKER
from process_lock import process_lock
from workload_observer import LinuxMemoryObserver, submit_memory_observation
from workload_protection import encode

MARKER = 'clawcare-owned-tiny-worker-v1'


def _hash(payload):
    return hashlib.sha256(payload).hexdigest()


def _payload(index, size):
    return bytes([index + 1]) * size


def _preflight(root):
    root = private_root(root)
    for name in ('service.sqlite3', 'service.sqlite3-wal', 'service.sqlite3-shm'):
        path = root / name
        if name == 'service.sqlite3' or path.exists() or path.is_symlink():
            Control.no_links(path)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise Denied('Owned database path changed')
    return root


class ValidatedTransactions:
    """Revalidate static filesystem drift before every policy database open."""
    def __init__(self, core, root): self.core, self.root = core, root

    @contextmanager
    def tx(self):
        _preflight(self.root)
        with self.core.tx() as connection:
            yield connection


def create_worker(root, *, items=3, item_bytes=4096, clock=time.time, collector=None, limits=None):
    """Explicitly create a new private demo root, initially paused. Never adopt."""
    if type(items) is not int or not 1 <= items <= 3:
        raise ValueError('The finite policy supports 1..3 units')
    if type(item_bytes) is not int or not 1 <= item_bytes <= 65536:
        raise ValueError('Units must be 1..65536 bytes')
    service = initialize_fixture(root)
    service.clock = clock
    worker_id = 'worker-' + uuid.uuid4().hex
    manifest = {'kind': MARKER, 'worker_id': worker_id, 'fixture_id': service.fixture_id,
                'items': items, 'item_bytes': item_bytes,
                'outputs': [{'index': i, 'name': 'unit-%d.bin' % i,
                             'sha256': _hash(_payload(i, item_bytes))} for i in range(items)]}
    payload = (encode(manifest) + '\n').encode()
    Control.atomic_write(service.root / 'workload.json', payload)
    (service.root / 'outputs').mkdir(mode=0o700)
    (service.root / 'checkpoints').mkdir(mode=0o700)
    guard = service.workload_protection(limits)
    guard.register(worker_id, 1024 * 1024, 'owned-tiny-manifest-v1', _hash(payload))
    with service.core.tx() as c:
        c.executescript('''
            CREATE TABLE cooperative_meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                worker_id TEXT NOT NULL, manifest_hash TEXT NOT NULL, mode TEXT NOT NULL);
            CREATE TABLE cooperative_units(idx INTEGER PRIMARY KEY, state TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0, action_id TEXT, output_hash TEXT);
            CREATE TABLE cooperative_receipts(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                at REAL NOT NULL, unit INTEGER, event TEXT NOT NULL, body TEXT NOT NULL);
        ''')
        c.execute('INSERT INTO cooperative_meta VALUES(1,?,?,?)', (worker_id, _hash(payload), 'PAUSED'))
        c.executemany('INSERT INTO cooperative_units(idx,state) VALUES(?,?)', [(i, 'TODO') for i in range(items)])
    return CooperativeWorker(service.root, clock=clock, collector=collector)


class CooperativeWorker:
    """Cooperative single-unit steps, serialized by an owned-root process lock.

    Fault hooks are a Python-test-only injection seam, not executable user data.
    A hook raises to simulate interruption; no process is killed or launched.
    """
    def __init__(self, root, *, clock=time.time, collector=None, fault_hook=None):
        _preflight(root)
        self.service = FixtureService(root, clock)
        self.root, self.clock = self.service.root, clock
        self.guard = self.service.workload_protection()
        self.guard.core = ValidatedTransactions(self.service.core, self.root)
        self.collector = collector or LinuxMemoryObserver(clock=clock).collect
        self.fault_hook = fault_hook or (lambda phase: None)
        self.lock = self.root / 'cooperative.lock'
        self.manifest = read_json(self.root / 'workload.json')
        with self._tx() as c:
            self._identity(c)
        self.worker_id = self.manifest['worker_id']

    @contextmanager
    def _tx(self):
        # Reject static root drift before SQLite could create/open outside it.
        with self.guard.core.tx() as c:
            yield c

    def _identity(self, c):
        private_root(self.root)
        if read_json(self.root / 'fixture.json') != {'kind': FIXTURE_MARKER, 'fixture_id': self.service.fixture_id}:
            raise Denied('Fixture identity changed')
        manifest = read_json(self.root / 'workload.json')
        row = c.execute('SELECT * FROM cooperative_meta WHERE singleton=1').fetchone()
        if (not row or manifest != self.manifest or manifest.get('kind') != MARKER or
                manifest.get('fixture_id') != self.service.fixture_id or
                row['worker_id'] != manifest.get('worker_id') or
                row['manifest_hash'] != _hash((self.root / 'workload.json').read_bytes())):
            raise Denied('Owned workload identity mismatch')
        for directory in ('outputs', 'checkpoints'):
            path = self.root / directory
            Control.no_links(path)
            if not path.is_dir() or (os.name != 'nt' and path.stat().st_mode & 0o077):
                raise Denied('Owned output directory changed')
        units = list(c.execute('SELECT * FROM cooperative_units ORDER BY idx'))
        if [unit['idx'] for unit in units] != list(range(manifest['items'])):
            raise Denied('Owned unit inventory changed')
        permitted_outputs = {manifest['outputs'][unit['idx']]['name'] for unit in units
                             if unit['state'] in ('INTENT', 'VERIFIED') and unit['action_id']}
        permitted_checkpoints = {'unit-%d.json' % unit['idx'] for unit in units
                                if unit['state'] in ('INTENT', 'VERIFIED') and unit['action_id']}
        if (any(path.name not in permitted_outputs for path in (self.root / 'outputs').iterdir()) or
                any(path.name not in permitted_checkpoints for path in (self.root / 'checkpoints').iterdir())):
            raise Denied('Untracked file in the owned workload')
        return row

    @contextmanager
    def _owned(self):
        _preflight(self.root)
        if self.lock.exists() or self.lock.is_symlink():
            Control.no_links(self.lock)
            if not self.lock.is_file() or self.lock.stat().st_nlink != 1:
                raise Denied('Invalid worker lock')
        with process_lock(self.lock):
            with self._tx() as c:
                self._identity(c)
            yield

    def _receipt(self, c, index, event, **body):
        c.execute('INSERT INTO cooperative_receipts(at,unit,event,body) VALUES(?,?,?,?)',
                  (self.clock(), index, event, encode(body)))

    def set_mode(self, mode):
        if mode not in ('RUNNING', 'PAUSED', 'CANCELLED'):
            raise ValueError('Invalid mode')
        with self._tx() as c:
            meta = self._identity(c)
            if meta['mode'] == 'CANCELLED' and mode != 'CANCELLED':
                raise Denied('Cancellation is terminal for this owned workload')
            c.execute('UPDATE cooperative_meta SET mode=? WHERE singleton=1', (mode,))
            self._receipt(c, None, mode)
        return self.status()

    def status(self):
        with self._tx() as c:
            meta = self._identity(c)
            units = [dict(r) for r in c.execute('SELECT * FROM cooperative_units ORDER BY idx')]
            pending = self._pending_unit(c) is not None
            try:
                self._checkpoint_inventory(c)
                integrity = True
            except (Denied, OSError, ValueError):
                integrity = False
        return {'worker_id': meta['worker_id'], 'mode': meta['mode'], 'units': units,
                'artifacts_recorded_verified': all(unit['state'] == 'VERIFIED' for unit in units),
                'reconciliation_pending': pending, 'checkpoint_inventory_intact': integrity,
                'complete': integrity and not pending and all(unit['state'] == 'VERIFIED' for unit in units),
                'actual_local_artifacts': True, 'arbitrary_process_protection': False}

    def _sample(self):
        _preflight(self.root)
        observation = self.collector()
        if not isinstance(observation, dict) or type(observation.get('synthetic')) is not bool:
            raise ValueError('Memory observation must include explicit provenance')
        submit_memory_observation(self.guard, observation)
        with self._tx() as c:
            self._receipt(c, None, 'MEMORY_OBSERVATION', synthetic=observation['synthetic'],
                          source=observation.get('source', 'unspecified'),
                          status=observation.get('status', 'unknown'),
                          observed_at=observation.get('observed_at'))
        return observation

    def _output(self, index):
        return self.root / 'outputs' / self.manifest['outputs'][index]['name']

    def _check_output(self, index):
        """Independent bounded disk read, exact size and manifest hash required."""
        path = self._output(index)
        if not path.exists() and not path.is_symlink():
            return None
        Control.no_links(path)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != self.manifest['item_bytes']:
            raise Denied('Output is not an intact owned unit')
        with path.open('rb') as source:
            payload = source.read(self.manifest['item_bytes'] + 1)
        digest = _hash(payload)
        if len(payload) != self.manifest['item_bytes'] or digest != self.manifest['outputs'][index]['sha256']:
            raise Denied('Independent output verification failed')
        return digest

    def _checkpoint(self, c, index, action_id, digest):
        """Idempotent immutable per-unit receipt; never overwrite a checkpoint."""
        body = {'kind': MARKER, 'worker_id': self.worker_id, 'unit': index,
                'action_id': action_id, 'output_sha256': digest,
                'manifest_sha256': _hash((self.root / 'workload.json').read_bytes())}
        path = self.root / 'checkpoints' / ('unit-%d.json' % index)
        if path.exists() or path.is_symlink():
            if read_json(path) != body:
                raise Denied('Checkpoint conflict; preserve for review')
        else:
            # O_EXCL: an interrupted partial checkpoint is preserved for review.
            with path.open('xb') as target:
                target.write((encode(body) + '\n').encode())
                target.flush(); os.fsync(target.fileno())
            self._sync_directory(path.parent)
        c.execute("UPDATE cooperative_units SET state='VERIFIED',output_hash=? WHERE idx=?", (digest, index))
        self._receipt(c, index, 'OUTPUT_INDEPENDENTLY_VERIFIED', action_id=action_id, sha256=digest,
                      verification='separate bounded read and manifest SHA-256 comparison')

    @staticmethod
    def _sync_directory(path):
        if os.name != 'nt':
            fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)

    def _checkpoint_inventory(self, c):
        meta = self._identity(c)
        for row in c.execute("SELECT * FROM cooperative_units WHERE state='VERIFIED'"):
            if self._check_output(row['idx']) != row['output_hash']:
                raise Denied('A preserved output disappeared')
            path = self.root / 'checkpoints' / ('unit-%d.json' % row['idx'])
            body = read_json(path)
            expected = {'kind': MARKER, 'worker_id': self.worker_id, 'unit': row['idx'],
                'action_id': row['action_id'], 'output_sha256': row['output_hash'],
                'manifest_sha256': meta['manifest_hash']}
            if body != expected:
                raise Denied('Preserved checkpoint identity changed')
        return meta['manifest_hash']

    def _verify_checkpoint_inventory(self):
        with self._tx() as c:
            digest = self._checkpoint_inventory(c)
        return self.guard.verify_checkpoint(self.worker_id, digest, True, self.clock())

    @staticmethod
    def _pending_unit(c):
        for unit in c.execute("SELECT * FROM cooperative_units WHERE action_id IS NOT NULL ORDER BY idx"):
            action = c.execute('SELECT body FROM workload_actions WHERE id=?', (unit['action_id'],)).fetchone()
            if unit['state'] == 'INTENT' or (action and json.loads(action[0])['status'] in ('CLAIMED', 'UNKNOWN')):
                return dict(unit)
        return None

    def reconcile(self):
        """Explicit local reconciliation also remains available after cancellation."""
        with self._owned():
            with self._tx() as c:
                unit = self._pending_unit(c)
            return self._reconcile(unit) if unit else {'status': 'NOTHING_TO_RECONCILE'}

    def _reconcile(self, unit):
        """Owned lock establishes no other cooperative writer. Never replay output."""
        index, action_id = unit['idx'], unit['action_id']
        digest = self._check_output(index)
        with self._tx() as c:
            self._identity(c)
            action_row = c.execute('SELECT body FROM workload_actions WHERE id=?', (action_id,)).fetchone()
        if action_row is not None:
            action = json.loads(action_row[0])
            if action['task_id'] != self.worker_id or action['item_id'] != 'unit-%d' % index:
                raise Denied('Policy action belongs to a different owned unit')
        if digest is not None:
            if action_row is None:
                raise Denied('Output has no durable policy claim; preserve for review')
            with self._tx() as c:
                self._checkpoint(c, index, action_id, digest)
            self.guard.reconcile_verified_action(action_id, observed_at=self.clock(), output_sha256=digest,
                checkpoint_sha256=_hash((self.root / 'workload.json').read_bytes()),
                output_verified=True, worker_quiescent=True, no_untracked_effects=True)
            return {'status': 'RECONCILED_VERIFIED_OUTPUT', 'unit': index, 'replayed': False}
        checkpoint = self.root / 'checkpoints' / ('unit-%d.json' % index)
        if unit['state'] == 'VERIFIED' or unit['output_hash'] is not None or checkpoint.exists() or checkpoint.is_symlink():
            raise Denied('Checkpointed output is missing; never replay')
        if action_row is not None:
            action = json.loads(action_row[0])
            if action['status'] == 'VERIFIED':
                raise Denied('Previously verified output is missing')
            result = self.guard.outcome(action_id, 'no_effect', observed_at=self.clock(), worker_quiescent=True)
            if result['status'] != 'NO_EFFECT':
                return {'status': 'NEEDS_RECONCILIATION', 'unit': index, 'replayed': False}
        with self._tx() as c:
            c.execute("UPDATE cooperative_units SET state='TODO',action_id=NULL WHERE idx=?", (index,))
            self._receipt(c, index, 'RECONCILED_NO_OUTPUT', action_id=action_id)
        self.guard.reconcile_disconnect(self.worker_id, True, True)
        return {'status': 'RECONCILED_NO_OUTPUT', 'unit': index, 'replayed': False}

    def step(self):
        """At most one actual unit. Unknown capacity, pause and cancel write none."""
        with self._owned():
            with self._tx() as c:
                meta = self._identity(c)
                if meta['mode'] != 'RUNNING':
                    return {'status': meta['mode'], 'wrote_unit': False}
                pending = self._pending_unit(c)
            self._sample()
            if pending:
                return self._reconcile(dict(pending))
            self._verify_checkpoint_inventory()
            self.guard.assess(self.worker_id)
            # This process owns the cooperative lock and no unit is in flight.
            self.guard.reconcile_disconnect(self.worker_id, True, True)
            with self._tx() as c:
                meta = self._identity(c)
                unit = c.execute("SELECT * FROM cooperative_units WHERE state='TODO' ORDER BY idx LIMIT 1").fetchone()
                if not unit:
                    return {'status': 'COMPLETE', 'wrote_unit': False}
                index = unit['idx']
                action_id = '%s-u%d-a%d' % (self.worker_id, index, unit['attempt'] + 1)
                if self._output(index).exists() or self._output(index).is_symlink():
                    raise Denied('Unexpected existing output; never overwrite or adopt')
                c.execute("UPDATE cooperative_units SET state='INTENT',attempt=attempt+1,action_id=? WHERE idx=?", (action_id,index))
            self.fault_hook('after_intent')
            result = self.guard.claim(self.worker_id, 'unit-%d' % index, action_id)
            if result['decision'] != 'CLAIMED_SYNTHETIC_PLAN':
                with self._tx() as c:
                    c.execute("UPDATE cooperative_units SET state='TODO',action_id=NULL WHERE idx=?", (index,))
                return {'status': result['decision'], 'wrote_unit': False}
            self.fault_hook('after_claim')
            self._sample()  # Re-observe immediately before the owned effect boundary.
            self.fault_hook('before_effect')
            with self._tx() as c:
                meta = self._identity(c)
                now, state = self.guard._now(c)
                task = self.guard._task(c, self.worker_id)
                assessment = self.guard._assessment(c, task, state, now)
                action = json.loads(c.execute('SELECT body FROM workload_actions WHERE id=?', (action_id,)).fetchone()[0])
                verification = task['checkpoint_verification']
                if (meta['mode'] != 'RUNNING' or assessment['memory'] != 'allow' or task['uncertain'] or
                        action['status'] != 'CLAIMED' or not verification or not verification['passed'] or
                        verification['fault_revision'] != task['fault_revision'] or
                        now - verification['observed_at'] > self.guard.limits.verification_max_age):
                    self._receipt(c,index,'EFFECT_BLOCKED',reason=assessment['reason'],mode=meta['mode'])
                    return {'status': 'EFFECT_BLOCKED', 'wrote_unit': False}
                path = self._output(index)
                with path.open('xb') as output:
                    payload = _payload(index, self.manifest['item_bytes'])
                    output.write(payload); output.flush(); os.fsync(output.fileno())
                self._sync_directory(path.parent)
                self.fault_hook('after_output')
                digest = self._check_output(index)
                if digest is None:
                    raise Denied('New output disappeared before independent verification')
                self._checkpoint(c,index,action_id,digest)
                self.fault_hook('after_checkpoint')
            self.fault_hook('before_outcome')
            verified_digest = self._check_output(index)
            checkpoint_ok = self._verify_checkpoint_inventory()
            if verified_digest != digest or not checkpoint_ok:
                raise Denied('Output/checkpoint verification changed before outcome')
            self.guard.heartbeat(self.worker_id, index + 1)
            result = self.guard.outcome(action_id,'verified',observed_at=self.clock(),output_sha256=digest,
                output_verified=verified_digest == digest,independent_healthy=checkpoint_ok,
                original_symptom_healthy=verified_digest == self.manifest['outputs'][index]['sha256'])
            return {'status': result['status'], 'unit': index, 'wrote_unit': True,
                    'output_sha256': digest, 'actual_output_verified': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('command',choices=('init','status','resume','pause','cancel','step','reconcile'))
    args=parser.parse_args(argv)
    worker=create_worker(args.root) if args.command=='init' else CooperativeWorker(args.root)
    if args.command in ('init','status'): result=worker.status()
    elif args.command=='step': result=worker.step()
    elif args.command=='reconcile': result=worker.reconcile()
    else: result=worker.set_mode({'resume':'RUNNING','pause':'PAUSED','cancel':'CANCELLED'}[args.command])
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
