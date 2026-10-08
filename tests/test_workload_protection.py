import json
from pathlib import Path
import tempfile
import threading
import unittest

from fixture_service import FixtureService, ReadView, initialize_fixture
from fixture_service_mcp import Bridge
from workload_protection import Limits


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now
    def advance(self, seconds=1): self.now += seconds


class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'fixture'
        self.service = initialize_fixture(self.root)
        self.clock = Clock()
        self.service.clock = self.clock
        self.limits = Limits(reserve_bytes=100, recovery_margin_bytes=50, cooldown_seconds=10)
        self.guard = self.service.workload_protection(self.limits)
        self.digest = 'a' * 64
        self.guard.register('task', 200, 'checkpoint-v1', self.digest)

    def memory(self, available=500, at=None):
        return self.guard.observe_memory(self.clock() if at is None else at, available, 1000)

    def verify(self, task='task'):
        return self.guard.verify_checkpoint(task, self.digest, True, self.clock())

    def claim(self, item='item', action='action'):
        return self.guard.claim('task', item, action)

    def ready(self):
        self.memory(); self.verify()

    def stable(self):
        self.clock.advance(); self.memory(); self.guard.assess('task')
        self.clock.advance(10); self.memory(); self.guard.assess('task')
        self.guard.reconcile_disconnect('task', True, True)
        self.verify()

    def outcome(self, action='action', **kwargs):
        return self.guard.outcome(action, 'verified', observed_at=self.clock(),
            output_sha256='b' * 64, output_verified=True, independent_healthy=True,
            original_symptom_healthy=True, **kwargs)

    def test_healthy_path_independent_output_and_progress(self):
        self.ready()
        self.assertEqual('allow', self.guard.assess('task')['memory'])
        self.assertEqual('CLAIMED_SYNTHETIC_PLAN', self.claim()['decision'])
        self.clock.advance(); self.guard.heartbeat('task', 1)
        self.assertEqual('VERIFIED', self.outcome()['status'])
        self.assertEqual('ALREADY_VERIFIED', self.claim(action='another')['decision'])
        self.assertEqual('VERIFIED_OUTPUT', ReadView(self.root).workload_status()['tasks'][0]['status'])

    def test_missing_stale_future_invalid_memory_fails_closed(self):
        self.assertEqual('unknown', self.guard.assess('task')['memory'])
        for available, total, at in [(None,1000,1000), (1001,1000,1000), (True,1000,1000),
                                      (500,1000,1001), (500,1000,float('nan'))]:
            self.assertFalse(self.guard.observe_memory(at,available,total))
            self.assertEqual('unknown', self.guard.assess('task')['memory'])
        self.memory(); self.clock.advance(31)
        self.assertEqual('unknown', self.guard.assess('task')['memory'])

    def test_memory_pressure_hysteresis_distinct_samples_cooldown(self):
        self.memory(299)
        self.assertEqual('pause', self.guard.assess('task')['memory'])
        self.clock.advance(); self.memory(340)
        self.assertEqual('MEMORY_PRESSURE', self.guard.assess('task')['reason'])
        self.clock.advance(); self.memory(500)
        self.assertEqual('RECOVERY_COOLDOWN', self.guard.assess('task')['reason'])
        self.clock.advance(10)
        self.assertEqual('pause', self.guard.assess('task')['memory'])
        self.memory()
        self.assertEqual('allow', self.guard.assess('task')['memory'])
        self.assertEqual('PAUSED', self.guard.assess('task')['status'])

    def test_old_duplicate_samples_do_not_count_or_refresh(self):
        self.memory(100); self.guard.assess('task')
        self.clock.advance(); self.memory(); self.guard.assess('task')
        self.assertFalse(self.memory(at=1001))
        self.assertFalse(self.memory(at=999))
        self.clock.advance(10)
        self.assertEqual('pause', self.guard.assess('task')['memory'])
        self.guard.observe_memory(None, None, None)
        self.assertFalse(self.memory(at=1000))
        self.assertEqual('unknown', self.guard.assess('task')['memory'])

    def test_live_but_stalled_worker_is_not_heartbeat_progress(self):
        self.ready(); self.guard.heartbeat('task', 0)
        self.clock.advance(60); self.memory(); self.guard.heartbeat('task', 0)
        result = self.guard.assess('task')
        self.assertEqual('STALLED', result['worker'])
        self.assertEqual('PAUSED', result['status'])
        self.clock.advance(10); self.memory(); self.verify()
        self.assertEqual('WORKER_NOT_QUIESCENT', self.claim()['decision'])
        self.assertEqual(0, ReadView(self.root).workload_status()['tasks'][0]['progress_seq'])

    def test_missing_heartbeat_does_not_prove_termination(self):
        self.ready(); self.guard.observe_cause('disconnect','host','DISCONNECTED',1000,'task')
        self.stable()
        self.guard.heartbeat('task',0)  # New activity invalidates quiescence evidence.
        self.assertEqual('WORKER_NOT_QUIESCENT', self.claim()['decision'])

    def test_restart_pending_claim_never_replayed(self):
        self.ready(); self.claim()
        restarted = FixtureService(self.root, self.clock).workload_protection()
        self.assertEqual('EXISTING_ACTION', restarted.claim('task','item','action')['decision'])
        self.assertEqual('NEEDS_RECONCILIATION', restarted.claim('task','other','other-action')['decision'])
        self.assertFalse(restarted.reconcile_disconnect('task',True,True))
        self.assertEqual(1, restarted.assess('task')['attempts'])

    def test_concurrent_claims_reserve_only_once(self):
        self.ready()
        results=[]
        def claim(i): results.append(self.claim(action='action-'+str(i)))
        threads=[threading.Thread(target=claim,args=(i,)) for i in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(1,sum(r['decision']=='CLAIMED_SYNTHETIC_PLAN' for r in results))
        self.assertTrue(all(r['execute'] is False for r in results))

    def test_bounded_retry_budget_persists_across_restart(self):
        self.ready()
        for i in range(3):
            action='attempt-'+str(i)
            self.assertEqual('CLAIMED_SYNTHETIC_PLAN',self.claim(action=action)['decision'])
            self.assertEqual('NO_EFFECT',self.guard.outcome(action,'no_effect',observed_at=self.clock(),worker_quiescent=True)['status'])
            if i < 2:
                self.assertIn(self.claim(action='too-soon-'+str(i))['decision'],('RECOVERY_COOLDOWN','RETRY_COOLDOWN'))
            self.clock.advance(10 * 2**i)
            self.stable()
            self.guard=FixtureService(self.root,self.clock).workload_protection()
        self.assertEqual('RETRY_BUDGET_EXHAUSTED',self.claim(action='fourth')['decision'])
        self.assertEqual(3,self.guard.assess('task')['attempts'])

    def test_false_recovered_labels_are_prevented(self):
        for missing in ('progress','output','independent','symptom','freshness','memory'):
            with self.subTest(missing=missing):
                task='test-'+missing; action='action-'+missing
                self.guard.register(task,200,'cp',self.digest)
                self.clock.advance(); self.guard.observe_memory(self.clock(),10000,20000); self.verify(task)
                self.guard.claim(task,'item',action)
                if missing != 'progress':
                    self.clock.advance(); self.guard.heartbeat(task,1)
                if missing == 'memory':
                    self.clock.advance(); self.memory(100)
                result=self.guard.outcome(action,'verified',
                    observed_at=self.clock()-40 if missing=='freshness' else self.clock(),
                    output_sha256='b'*64,output_verified=missing!='output',
                    independent_healthy=missing!='independent', original_symptom_healthy=missing!='symptom')
                self.assertEqual('UNKNOWN',result['status'])
                self.assertEqual('NEEDS_RECONCILIATION',result['task_status'])

    def test_checkpoint_verification_required_and_expires(self):
        self.memory()
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])
        self.assertFalse(self.guard.verify_checkpoint('task','b'*64,True,self.clock()))
        self.clock.advance(); self.verify(); self.clock.advance(31); self.memory()
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])

    def test_no_effect_requires_positive_quiescence(self):
        self.ready(); self.claim()
        self.assertEqual('UNKNOWN',self.guard.outcome('action','no_effect',observed_at=self.clock())['status'])
        self.assertEqual('NEEDS_RECONCILIATION',self.claim(action='new')['decision'])

    def test_verified_output_keeps_reservation_until_fresh_sample(self):
        self.ready(); self.claim(); self.clock.advance(); self.guard.heartbeat('task',1)
        self.outcome()
        self.guard.register('second',250,'cp',self.digest)
        self.assertEqual(200,self.guard.assess('second')['other_reserved_bytes'])
        self.clock.advance(); self.memory()
        self.assertEqual(0,self.guard.assess('second')['other_reserved_bytes'])

    def test_disconnect_keeps_reservation_after_output_verifies(self):
        self.ready(); self.claim()
        self.guard.observe_cause('disconnect','host','DISCONNECTED',self.clock(),'task')
        self.clock.advance(); self.memory(); self.clock.advance(10); self.memory()
        self.guard.heartbeat('task',1)
        self.assertEqual('VERIFIED',self.outcome()['status'])
        self.guard.register('second',250,'cp',self.digest)
        self.clock.advance(); self.memory()
        self.assertEqual(200,self.guard.assess('second')['other_reserved_bytes'])
        self.guard.reconcile_disconnect('task',True,True)
        self.assertEqual(0,self.guard.assess('second')['other_reserved_bytes'])

    def test_concurrent_workloads_reserve_memory_against_same_sample(self):
        self.ready(); self.claim()
        self.guard.register('second',250,'cp',self.digest)
        self.verify('second')
        result=self.guard.claim('second','item','second-action')
        self.assertEqual('MEMORY_PRESSURE',result['decision'])
        self.assertEqual(200,self.guard.assess('second')['other_reserved_bytes'])

    def test_conflicting_memory_same_timestamp_invalidates_success(self):
        self.ready()
        self.assertFalse(self.memory(100))
        self.assertEqual('unknown',self.guard.assess('task')['memory'])

    def test_conflicting_checkpoint_same_timestamp_invalidates_success(self):
        self.ready()
        self.assertFalse(self.guard.verify_checkpoint('task',self.digest,False,self.clock()))
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])
        self.assertFalse(self.verify())
        self.clock.advance(); self.assertTrue(self.verify())

    def test_delayed_prefault_checkpoint_report_cannot_authorize_recovery(self):
        self.memory(); self.clock.advance()
        self.guard.observe_cause('fault','task','OOM',self.clock(),'task')
        self.clock.advance(); self.memory()
        self.clock.advance(10); self.memory(); self.guard.reconcile_disconnect('task',True,True)
        self.assertFalse(self.guard.verify_checkpoint('task',self.digest,True,1000))
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])

    def test_invalid_payload_timestamp_also_advances_memory_watermark(self):
        self.memory(100)
        self.clock.advance(10)
        self.guard.observe_memory(self.clock(),None,None)
        self.assertFalse(self.memory(at=1005))
        self.assertEqual('unknown',self.guard.assess('task')['memory'])

    def test_old_no_effect_cannot_override_newer_worker_activity(self):
        self.ready(); self.claim()
        self.clock.advance(15); self.guard.heartbeat('task',1)
        self.clock.advance(5)
        result=self.guard.outcome('action','no_effect',observed_at=1001,worker_quiescent=True)
        self.assertEqual('UNKNOWN',result['status'])
        self.assertIsNone(ReadView(self.root).workload_status()['tasks'][0]['worker_quiescent_at'])

    def test_prefault_health_cannot_mark_gateway_recovered(self):
        self.ready(); self.claim()
        self.clock.advance(); self.guard.heartbeat('task',1)
        self.clock.advance(); self.guard.observe_cause('gateway-fault','gateway','UNHEALTHY',self.clock(),'task')
        self.memory(); self.clock.advance(10); self.memory()
        result=self.guard.outcome('action','verified',observed_at=1001,output_sha256='b'*64,
            output_verified=True,independent_healthy=True,original_symptom_healthy=True)
        self.assertEqual('UNKNOWN',result['status'])

    def test_newer_failed_checkpoint_cannot_be_overwritten_by_older_success(self):
        self.ready(); self.clock.advance()
        self.assertFalse(self.guard.verify_checkpoint('task',self.digest,False,self.clock()))
        self.clock.advance()
        self.assertFalse(self.guard.verify_checkpoint('task',self.digest,True,1000))
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])

    def test_memory_fault_between_assessments_restarts_cooldown(self):
        self.memory(100); self.clock.advance(); self.memory()
        self.clock.advance(10); self.memory(100)
        self.clock.advance(); self.memory()
        self.verify(); self.guard.reconcile_disconnect('task',True,True)
        self.assertEqual('RECOVERY_COOLDOWN',self.claim()['decision'])
        self.clock.advance(10); self.memory(); self.verify()
        self.assertEqual('CLAIMED_SYNTHETIC_PLAN',self.claim()['decision'])

    def test_new_fault_invalidates_prior_checkpoint_verification(self):
        self.ready()
        self.guard.observe_cause('oom','task','OOM',self.clock(),'task')
        self.clock.advance(); self.memory()
        self.clock.advance(10); self.memory()
        self.guard.reconcile_disconnect('task',True,True)
        self.assertEqual('CHECKPOINT_UNVERIFIED',self.claim()['decision'])
        self.verify()
        self.assertEqual('CLAIMED_SYNTHETIC_PLAN',self.claim()['decision'])

    def test_clock_regression_and_config_changes_fail_closed(self):
        self.ready(); self.clock.now=999
        with self.assertRaises(ValueError):self.claim()
        self.clock.now=1000
        with self.assertRaises(ValueError):self.service.workload_protection(Limits())
        with self.assertRaises(ValueError):self.guard.heartbeat('task',-1)

    def test_checkpoint_preserved_and_id_conflicts_rejected(self):
        self.ready(); self.claim()
        with self.assertRaises(ValueError):self.guard.register('task',200,'changed',self.digest)
        with self.assertRaises(ValueError):self.guard.claim('task','different','action')
        task=self.guard.register('task',200,'checkpoint-v1',self.digest)
        self.assertEqual(1,task['attempts'])

    def test_readonly_status_has_bounded_inventory_summary(self):
        self.guard.register('large',200,'cp',self.digest,{'item-%d'%i:self.digest for i in range(10000)})
        status=ReadView(self.root).workload_status()
        self.assertLess(len(json.dumps(status)),10000)
        self.assertEqual(10000,next(t for t in status['tasks'] if t['id']=='large')['completed_count'])

    def test_alerts_deduplicate_and_readonly_api(self):
        self.guard.assess('task'); self.guard.assess('task')
        view=ReadView(self.root).workload_status()
        self.assertEqual(1,len(view['alerts']))
        self.assertEqual(2,view['alerts'][0]['observations'])
        result=Bridge(ReadView(self.root)).call('clawcare_workload_status',{})
        self.assertFalse(result['isError'])
        self.assertTrue(json.loads(result['content'][0]['text'])['synthetic'])

    def test_unknown_action_verification_does_not_clear_disconnect(self):
        self.ready(); self.claim()
        self.guard.observe_cause('disconnect','host','DISCONNECTED',self.clock(),'task')
        self.clock.advance(); self.memory(); self.guard.assess('task')
        self.clock.advance(10); self.memory(); self.guard.heartbeat('task',1)
        result=self.outcome()
        self.assertEqual('VERIFIED',result['status'])
        self.assertEqual('NEEDS_RECONCILIATION',result['task_status'])
        self.assertEqual('NEEDS_RECONCILIATION',self.claim(item='next',action='next')['decision'])

    def test_media_regression_synthetic_inventory_preserved(self):
        # Counts represent a synthetic regression, never private media or transcripts.
        inventory={'mp3-%02d'%i:self.digest for i in range(80)}
        preserved={'mp3-%02d'%i:'saved_unverified' for i in (80,81)}
        preserved.update({'transcript-%02d'%i:'draft' for i in range(20)})
        task=self.guard.register('media-fixture',200,'saved82-verified80-drafts20',self.digest,inventory,preserved)
        self.guard.observe_cause('onnx','task','ONNX_OOM',998,'media-fixture')
        self.guard.observe_cause('ffmpeg','task','FFMPEG_OOM',999,'media-fixture')
        self.guard.observe_cause('desktop','host','DISCONNECTED',1000,'media-fixture')
        self.guard.observe_cause('gateway','gateway','HEALTH_UNKNOWN',1000,'media-fixture')
        self.assertFalse(self.guard.observe_cause('desktop','host','DISCONNECTED',1000,'media-fixture'))
        self.memory(); self.guard.assess('media-fixture')
        self.clock.advance(10); self.memory(); self.verify('media-fixture')
        self.assertEqual('NEEDS_RECONCILIATION',self.guard.claim('media-fixture','mp3-82','resume')['decision'])
        self.assertTrue(self.guard.reconcile_disconnect('media-fixture',True,True))
        self.assertEqual('ALREADY_VERIFIED',self.guard.claim('media-fixture','mp3-00','duplicate')['decision'])
        self.assertEqual('PRESERVED_OUTPUT_REQUIRES_REVIEW',self.guard.claim('media-fixture','mp3-80','saved')['decision'])
        self.assertEqual('PRESERVED_OUTPUT_REQUIRES_REVIEW',self.guard.claim('media-fixture','transcript-00','draft')['decision'])
        self.assertEqual('CLAIMED_SYNTHETIC_PLAN',self.guard.claim('media-fixture','mp3-82','resume')['decision'])
        self.clock.advance(); self.guard.heartbeat('media-fixture',1)
        result=self.guard.outcome('resume','verified',observed_at=self.clock(),output_sha256='b'*64,
            output_verified=True,independent_healthy=True,original_symptom_healthy=True)
        self.assertEqual('VERIFIED_RECOVERY',result['task_status'])
        saved=ReadView(self.root).workload_status()
        recovered=next(t for t in saved['tasks'] if t['id']=='media-fixture')
        self.assertEqual(task['checkpoint_ref'],recovered['checkpoint_ref'])
        self.assertEqual(task['checkpoint_sha256'],recovered['checkpoint_sha256'])
        with self.service.core.tx() as c:
            full=json.loads(c.execute("SELECT body FROM workload_tasks WHERE id='media-fixture'").fetchone()[0])
        self.assertTrue(all(full['completed'][k]==v for k,v in inventory.items()))
        self.assertEqual(81,recovered['completed_count'])
        self.assertEqual(preserved,full['preserved'])
        self.assertEqual({'saved_unverified':2,'draft':20},recovered['preserved_counts'])
        self.assertTrue(all(e['causal_link']=='unknown' for e in saved['observations']))
        self.assertEqual({'host','task','gateway'},{e['domain'] for e in saved['observations']})


if __name__=='__main__':unittest.main()
