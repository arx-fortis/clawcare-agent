import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from control import Denied
from cooperative_worker import CooperativeWorker, create_worker
from process_lock import process_lock, Busy
from workload_protection import Limits


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now
    def advance(self, n=1): self.now += n


class SimulatedPressure:
    def __init__(self, clock): self.clock=clock; self.available=10_000_000
    def __call__(self):
        return {'synthetic': True, 'source': 'deterministic_pressure_fixture',
                'observed_at': self.clock(), 'status': 'unknown' if self.available is None else 'observed',
                'available_bytes': self.available, 'total_bytes': 20_000_000}


class Interrupted(Exception): pass


class CooperativeWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'worker'
        self.clock=Clock(); self.pressure=SimulatedPressure(self.clock)
        self.limits=Limits(reserve_bytes=100,recovery_margin_bytes=50,cooldown_seconds=10)
        self.worker=create_worker(self.root,clock=self.clock,collector=self.pressure,limits=self.limits)

    def restart(self, hook=None):
        self.worker=CooperativeWorker(self.root,clock=self.clock,collector=self.pressure,fault_hook=hook)
        return self.worker

    def resume(self): self.worker.set_mode('RUNNING')

    def files(self): return sorted((self.root/'outputs').iterdir())

    def action_count(self):
        with self.worker.service.core.tx() as c:
            return c.execute('SELECT COUNT(*) FROM workload_actions').fetchone()[0]

    def stable(self):
        self.pressure.available=10_000_000
        self.clock.advance(); self.worker._sample()
        self.clock.advance(10); self.worker._sample()

    def fail_at(self, phase):
        def hook(actual):
            if phase==actual: raise Interrupted(phase)
        self.worker.fault_hook=hook

    def test_initial_pause_and_tiny_real_output_healthy_path(self):
        self.assertEqual('PAUSED',self.worker.step()['status'])
        self.assertEqual([],self.files())
        self.resume()
        for i in range(3):
            self.clock.advance()
            result=self.worker.step()
            self.assertEqual('VERIFIED',result['status'])
            self.assertTrue(result['actual_output_verified'])
            self.assertEqual(hashlib.sha256(bytes([i+1])*4096).hexdigest(),result['output_sha256'])
        self.assertTrue(self.worker.status()['complete'])
        self.assertEqual('COMPLETE',self.worker.step()['status'])
        self.assertEqual(3,self.action_count())
        self.assertEqual(3,len(list((self.root/'checkpoints').iterdir())))

    def test_memory_unknown_pressure_pause_resume_cooldown(self):
        self.resume();self.pressure.available=None
        self.assertEqual('MISSING_OR_STALE_MEMORY',self.worker.step()['status'])
        self.assertEqual([],self.files());self.assertEqual(0,self.action_count())
        self.pressure.available=10
        self.clock.advance()
        self.assertEqual('MEMORY_PRESSURE',self.worker.step()['status'])
        self.stable();self.clock.advance()
        self.assertEqual('VERIFIED',self.worker.step()['status'])
        self.assertEqual(1,len(self.files()))

    def test_pressure_change_before_effect_blocks_actual_write(self):
        self.resume()
        def hook(phase):
            if phase=='after_claim':
                self.clock.advance();self.pressure.available=10
        self.worker.fault_hook=hook
        self.assertEqual('EFFECT_BLOCKED',self.worker.step()['status'])
        self.assertEqual([],self.files())
        self.restart()
        self.assertEqual('RECONCILED_NO_OUTPUT',self.worker.reconcile()['status'])
        self.stable();self.clock.advance()
        self.assertEqual('VERIFIED',self.worker.step()['status'])
        self.assertEqual(2,self.action_count())

    def test_stale_observation_at_effect_boundary_writes_nothing(self):
        self.resume()
        self.worker.fault_hook=lambda phase:self.clock.advance(31) if phase=='before_effect' else None
        self.assertEqual('EFFECT_BLOCKED',self.worker.step()['status'])
        self.assertEqual([],self.files())

    def test_cancelled_reconciliation_only_checkpoints_existing_output(self):
        self.resume();self.fail_at('after_output')
        with self.assertRaises(Interrupted):self.worker.step()
        original={p.name:p.read_bytes() for p in self.files()}
        self.restart();self.worker.set_mode('CANCELLED')
        result=self.worker.reconcile()
        self.assertEqual('RECONCILED_VERIFIED_OUTPUT',result['status'])
        self.assertEqual(original,{p.name:p.read_bytes() for p in self.files()})
        self.assertEqual('CANCELLED',self.worker.step()['status'])
        self.assertEqual(1,len(list((self.root/'checkpoints').iterdir())))

    def test_reconciliation_requires_fresh_exact_independent_evidence(self):
        self.resume();self.fail_at('after_claim')
        with self.assertRaises(Interrupted):self.worker.step()
        action=self.worker.status()['units'][0]['action_id']
        args={'observed_at':self.clock(),'output_sha256':'a'*64,
              'checkpoint_sha256':hashlib.sha256((self.root/'workload.json').read_bytes()).hexdigest(),
              'output_verified':True,'worker_quiescent':True,'no_untracked_effects':True}
        for bad in ({'observed_at':999},{'checkpoint_sha256':'b'*64},{'output_verified':False},
                    {'worker_quiescent':False},{'no_untracked_effects':False}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                self.worker.guard.reconcile_verified_action(action,**dict(args,**bad))
        self.assertEqual('RECONCILED_NO_OUTPUT',self.worker.reconcile()['status'])
        with self.assertRaises(ValueError):self.worker.guard.reconcile_verified_action(action,**args)

    def test_pause_before_effect_and_terminal_cancel(self):
        self.resume()
        def hook(phase):
            if phase=='before_effect': self.worker.set_mode('PAUSED')
        self.worker.fault_hook=hook
        self.assertEqual('EFFECT_BLOCKED',self.worker.step()['status'])
        self.assertEqual([],self.files())
        self.worker.set_mode('CANCELLED')
        self.assertEqual('CANCELLED',self.worker.step()['status'])
        self.assertEqual('RECONCILED_NO_OUTPUT',self.worker.reconcile()['status'])
        with self.assertRaises(Denied):self.resume()
        self.assertEqual([],self.files())

    def test_pause_between_units_preserves_checkpoint_and_output(self):
        self.resume();self.worker.step()
        before={p.name:p.read_bytes() for p in self.files()}
        checkpoint=(self.root/'checkpoints/unit-0.json').read_bytes()
        self.worker.set_mode('PAUSED');self.clock.advance()
        self.assertEqual('PAUSED',self.worker.step()['status'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.files()})
        self.resume();self.clock.advance();self.worker.step()
        self.assertEqual(checkpoint,(self.root/'checkpoints/unit-0.json').read_bytes())

    def test_crash_after_intent_without_claim_reconciles_without_replay(self):
        self.resume();self.fail_at('after_intent')
        with self.assertRaises(Interrupted):self.worker.step()
        self.assertEqual(0,self.action_count());self.assertEqual([],self.files())
        self.restart()
        self.assertEqual('RECONCILED_NO_OUTPUT',self.worker.reconcile()['status'])
        self.assertEqual([],self.files());self.clock.advance()
        self.assertEqual('VERIFIED',self.worker.step()['status'])

    def test_crash_after_claim_no_output_bounded_retry(self):
        self.resume()
        for attempt in range(3):
            self.fail_at('after_claim')
            with self.assertRaises(Interrupted):self.worker.step()
            self.restart()
            self.assertEqual('RECONCILED_NO_OUTPUT',self.worker.reconcile()['status'])
            self.clock.advance(10*2**attempt);self.stable();self.clock.advance()
        self.assertEqual('RETRY_BUDGET_EXHAUSTED',self.worker.step()['status'])
        self.assertEqual([],self.files());self.assertEqual(3,self.action_count())

    def test_crash_after_actual_output_reconciles_existing_bytes_once(self):
        self.resume();self.fail_at('after_output')
        with self.assertRaises(Interrupted):self.worker.step()
        path=self.files()[0];before=path.read_bytes();stat_before=path.stat()
        self.restart()
        result=self.worker.reconcile()
        self.assertEqual('RECONCILED_VERIFIED_OUTPUT',result['status']);self.assertFalse(result['replayed'])
        self.assertEqual(before,path.read_bytes());self.assertEqual(stat_before.st_mtime_ns,path.stat().st_mtime_ns)
        self.assertEqual('NOTHING_TO_RECONCILE',self.worker.reconcile()['status'])
        self.clock.advance();result=self.worker.step()
        self.assertEqual('VERIFIED',result['status']);self.assertEqual(1,result['unit'])
        self.assertEqual(2,self.action_count())

    def test_crash_after_checkpoint_or_before_outcome_does_not_duplicate(self):
        for phase in ('after_checkpoint','before_outcome'):
            with self.subTest(phase=phase):
                root=Path(self.temp.name)/phase
                worker=create_worker(root,clock=self.clock,collector=self.pressure,limits=self.limits)
                worker.set_mode('RUNNING')
                worker.fault_hook=lambda actual: (_ for _ in ()).throw(Interrupted(phase)) if actual==phase else None
                with self.assertRaises(Interrupted):worker.step()
                before=(root/'outputs/unit-0.bin').read_bytes()
                worker=CooperativeWorker(root,clock=self.clock,collector=self.pressure)
                self.assertEqual('RECONCILED_VERIFIED_OUTPUT',worker.reconcile()['status'])
                self.assertEqual(before,(root/'outputs/unit-0.bin').read_bytes())
                self.clock.advance();self.assertEqual(1,worker.step()['unit'])

    def test_corrupted_crash_output_is_preserved_for_review(self):
        self.resume();self.fail_at('after_output')
        with self.assertRaises(Interrupted):self.worker.step()
        path=self.files()[0];path.write_bytes(b'partial')
        self.restart()
        with self.assertRaises(Denied):self.worker.reconcile()
        self.assertEqual(b'partial',path.read_bytes())
        self.assertEqual(1,self.action_count())

    def test_checkpoint_drift_before_outcome_cannot_claim_verified_success(self):
        self.resume()
        def hook(phase):
            if phase=='before_outcome':(self.root/'checkpoints/unit-0.json').write_text('{}')
        self.worker.fault_hook=hook
        with self.assertRaises(Denied):self.worker.step()
        with self.worker.service.core.tx() as c:
            action=json.loads(c.execute('SELECT body FROM workload_actions').fetchone()[0])
        self.assertEqual('CLAIMED',action['status'])
        self.assertFalse(self.worker.status()['checkpoint_inventory_intact'])

    def test_checkpointed_output_missing_before_outcome_is_not_replayed(self):
        self.resume();self.fail_at('before_outcome')
        with self.assertRaises(Interrupted):self.worker.step()
        self.files()[0].unlink();self.restart()
        with self.assertRaises(Denied):self.worker.reconcile()
        self.assertEqual([],self.files());self.assertEqual(1,self.action_count())

    def test_output_disappearing_before_verification_is_never_marked_verified(self):
        self.resume()
        def hook(phase):
            if phase=='after_output':self.files()[0].unlink()
        self.worker.fault_hook=hook
        with self.assertRaises(Denied):self.worker.step()
        self.assertEqual('INTENT',self.worker.status()['units'][0]['state'])
        self.assertEqual([],list((self.root/'checkpoints').iterdir()))

    def test_checkpoint_corruption_blocks_subsequent_units(self):
        self.resume();self.worker.step()
        path=self.root/'checkpoints/unit-0.json';path.write_text('{}')
        self.clock.advance()
        with self.assertRaises(Denied):self.worker.step()
        self.assertEqual(1,len(self.files()))

    def test_verified_output_loss_is_not_replayed(self):
        self.resume();self.worker.step()
        self.files()[0].unlink();self.clock.advance()
        with self.assertRaises(Denied):self.worker.step()
        self.assertEqual([],self.files());self.assertEqual(1,self.action_count())

    def test_identity_drift_and_root_adoption_are_rejected(self):
        with self.assertRaises(FileExistsError):create_worker(self.root)
        manifest=self.root/'workload.json';value=json.loads(manifest.read_text());value['worker_id']='other'
        manifest.write_text(json.dumps(value))
        with self.assertRaises(Denied):self.restart()
        self.assertEqual([],self.files())

    @unittest.skipIf(os.name=='nt','POSIX symlink fixture; Windows reparse review separate')
    def test_root_symlink_drift_cannot_create_lock_in_foreign_directory(self):
        moved=Path(self.temp.name)/'moved';foreign=Path(self.temp.name)/'foreign'
        foreign.mkdir();self.root.rename(moved);self.root.symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(Denied):self.worker.step()
        with self.assertRaises(Denied):self.worker.set_mode('RUNNING')
        with self.assertRaises(Denied):self.worker.status()
        self.assertEqual([],list(foreign.iterdir()))

    @unittest.skipIf(os.name=='nt','POSIX link fixture; Windows reparse review separate')
    def test_database_link_drift_is_rejected_before_foreign_file_open(self):
        self.resume()
        original=self.root/'service.sqlite3';original.rename(self.root/'original.sqlite3')
        foreign=Path(self.temp.name)/'foreign.sqlite3';foreign.write_bytes(b'not a database')
        original.symlink_to(foreign)
        before=foreign.read_bytes()
        for operation in (self.worker.step,self.worker.status,lambda:self.worker.set_mode('PAUSED'),
                          lambda:self.worker.guard.assess(self.worker.worker_id)):
            with self.assertRaises(Denied):operation()
        self.assertEqual(before,foreign.read_bytes())
        self.assertFalse(Path(str(foreign)+'-wal').exists())

    def test_fixture_identity_drift_after_construction_blocks_effect(self):
        self.resume()
        path=self.root/'fixture.json';value=json.loads(path.read_text());value['fixture_id']='fixture-'+'0'*32
        path.write_text(json.dumps(value))
        with self.assertRaises(Denied):self.worker.step()
        self.assertEqual([],self.files())

    @unittest.skipIf(os.name=='nt','POSIX mode check; Windows ACL review remains separate')
    def test_root_permission_drift_after_construction_blocks_effect(self):
        self.resume();self.root.chmod(0o777)
        try:
            with self.assertRaises(Denied):self.worker.step()
            self.assertEqual([],self.files())
        finally:self.root.chmod(0o700)

    def test_owned_lock_prevents_second_writer(self):
        self.resume()
        with process_lock(self.worker.lock):
            with self.assertRaises(Busy):self.worker.step()
        self.assertEqual([],self.files())

    def test_stalled_heartbeat_requires_cooldown_then_owned_quiescence(self):
        self.resume();self.worker.guard.heartbeat(self.worker.worker_id,0)
        self.clock.advance(60);self.worker.guard.heartbeat(self.worker.worker_id,0)
        self.worker._sample()
        self.assertEqual('STALLED',self.worker.guard.assess(self.worker.worker_id)['worker'])
        self.assertEqual('RECOVERY_COOLDOWN',self.worker.step()['status'])
        self.stable();self.clock.advance()
        self.assertEqual('VERIFIED',self.worker.step()['status'])

    def test_unknown_real_host_capacity_blocks_governed_worker(self):
        from workload_observer import LinuxMemoryObserver
        if not sys.platform.startswith('linux'):self.skipTest('Linux collector')
        real=LinuxMemoryObserver().collect()
        root=Path(self.temp.name)/'real-resource'
        worker=create_worker(root,collector=lambda:real)
        worker.set_mode('RUNNING')
        result=worker.step()
        if real['status']=='unknown':
            self.assertEqual('MISSING_OR_STALE_MEMORY',result['status'])
            self.assertEqual([],list((root/'outputs').iterdir()))
        else:
            self.assertIn(result['status'],('VERIFIED','MEMORY_PRESSURE'))
        self.assertFalse(real['synthetic'])

    def test_reconciliation_never_marks_recovered_without_new_work(self):
        self.resume();self.fail_at('after_output')
        with self.assertRaises(Interrupted):self.worker.step()
        self.restart();self.worker.reconcile()
        self.assertEqual('PAUSED',self.worker.guard.assess(self.worker.worker_id)['status'])

    def test_final_output_is_not_complete_before_outcome_reconciliation(self):
        root=Path(self.temp.name)/'single'
        worker=create_worker(root,items=1,clock=self.clock,collector=self.pressure,limits=self.limits)
        worker.set_mode('RUNNING')
        worker.fault_hook=lambda phase: (_ for _ in ()).throw(Interrupted()) if phase=='before_outcome' else None
        with self.assertRaises(Interrupted):worker.step()
        status=worker.status()
        self.assertTrue(status['artifacts_recorded_verified'])
        self.assertTrue(status['reconciliation_pending'])
        self.assertFalse(status['complete'])
        worker=CooperativeWorker(root,clock=self.clock,collector=self.pressure)
        worker.reconcile();self.assertTrue(worker.status()['complete'])
        (root/'outputs/unit-0.bin').unlink()
        self.assertFalse(worker.status()['complete'])
        self.assertFalse(worker.status()['checkpoint_inventory_intact'])

    def test_untracked_files_prevent_false_quiescence_claim(self):
        self.resume();(self.root/'outputs/untracked.bin').write_bytes(b'not ours')
        with self.assertRaises(Denied):self.worker.step()
        self.assertEqual(b'not ours',(self.root/'outputs/untracked.bin').read_bytes())

    def test_deterministic_pressure_and_actual_output_provenance_are_separate(self):
        self.resume();result=self.worker.step()
        self.assertTrue(result['actual_output_verified'])
        with self.worker.service.core.tx() as c:
            records=[(r['event'],json.loads(r['body'])) for r in c.execute('SELECT * FROM cooperative_receipts')]
        self.assertTrue(all(body['synthetic'] is True for event,body in records if event=='MEMORY_OBSERVATION'))
        self.assertTrue(any(event=='OUTPUT_INDEPENDENTLY_VERIFIED' for event,body in records))


if __name__=='__main__':unittest.main()
