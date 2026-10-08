import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from control import Control, Denied, digest
from fixture_service import FixtureService, ReadView, initialize_fixture
from fixture_service_mcp import Bridge
from process_lock import process_lock, Busy


class Clock:
    def __init__(self): self.now = time.time()
    def __call__(self): return self.now
    def advance(self, n=10): self.now += n


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'fixture'
        self.service = initialize_fixture(self.root)
        self.clock = Clock()
        self.service.clock = self.clock

    def tearDown(self): self.temp.cleanup()

    def edit(self, name, **values):
        path = self.root / name
        data = json.loads(path.read_text())
        data.update(values)
        Control.atomic_write(path, json.dumps(data).encode())

    def authorize(self, **kwargs): return self.service.authorize_fixture(**kwargs)

    def count(self):
        with self.service.core.tx() as c:
            return c.execute('SELECT COUNT(*) FROM fixture_receipts').fetchone()[0]

    def pending(self, execute=False):
        policy = self.authorize()
        order = self.service.core.propose('gateway.json', 'enabled', True)
        with self.service.core.tx() as c:
            self.service._set(c, active_order=order['id'], policy_id=policy,
                              lease_owner='dead-owner', lease_until=self.clock() + 99999)
        if execute:
            core = Control(self.service.database)  # Synthesize a pre-crash legacy effect.
            core.approve(order['id'], order['scope'])
            core.execute(order['id'])
        return order['id']

    def test_acceptance_repair_verify_receipt_restart(self):
        self.authorize()
        receipt = self.service.tick()
        self.assertEqual('VERIFIED', receipt['outcome'])
        self.assertTrue(receipt['observation']['original_symptom_healthy'])
        self.assertTrue(receipt['observation']['independent_signal_healthy'])
        self.assertFalse(receipt['real_gateway_repaired'])
        restarted = FixtureService(self.root, self.clock)
        self.assertEqual(receipt, ReadView(self.root).work_order_status(receipt['order_id']))
        self.clock.advance()
        self.assertEqual('HEALTHY', restarted.tick()['status'])
        self.assertEqual(1, self.count())

    def test_false_health_rolls_back_exact_bytes(self):
        self.edit('signals.json', independent_healthy=False)
        before = (self.root / 'gateway.json').read_bytes()
        self.authorize()
        receipt = self.service.tick()
        self.assertEqual('ROLLED_BACK', receipt['outcome'])
        self.assertEqual(before, (self.root / 'gateway.json').read_bytes())
        self.assertTrue(receipt['observation']['original_symptom_healthy'])
        self.assertFalse(receipt['observation']['independent_signal_healthy'])
        self.assertEqual('ROLLED_BACK', receipt['control_status'])

    def test_original_symptom_failure_rolls_back(self):
        self.edit('signals.json', responding=False)
        self.authorize()
        receipt = self.service.tick()
        self.assertEqual('ROLLED_BACK', receipt['outcome'])
        self.assertFalse(receipt['observation']['original_symptom_healthy'])

    def test_default_paused_and_missing_policy_no_repair(self):
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])
        self.assertFalse(json.loads((self.root / 'gateway.json').read_text())['enabled'])
        self.assertEqual(0, self.count())

    def test_offline_provider_failure_is_not_repaired(self):
        self.edit('signals.json', provider_required=True)
        self.authorize()
        self.assertEqual('ONLINE_REQUIRED', self.service.tick()['status'])
        self.assertEqual(0, self.count())
        self.assertFalse(json.loads((self.root / 'gateway.json').read_text())['enabled'])

    def test_expired_policy_no_repair(self):
        self.authorize(ttl=1)
        self.clock.advance(2)
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_future_policy_no_repair(self):
        self.authorize()
        self.edit('policy.json', valid_from=self.clock() + 10)
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_policy_bound_and_unknown_fields_fail_closed(self):
        self.authorize()
        self.edit('policy.json', run_shell='anything')
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_wrong_policy_identity(self):
        self.authorize()
        self.edit('policy.json', fixture_id='fixture-' + '0' * 32)
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_missing_rollback_authority_denies_repair_bundle(self):
        self.authorize()
        self.edit('policy.json', actions=['repair'])
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_policy_revision_revocation_survives_restart(self):
        self.authorize()
        self.service.revoke()
        restarted = FixtureService(self.root, self.clock)
        restarted.core.resume()  # Merely resuming cannot revive the cached old grant.
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', restarted.tick()['status'])

    def test_clock_regression_no_repair(self):
        self.authorize()
        self.clock.advance(-1)
        self.assertEqual('CLOCK_REVIEW_REQUIRED', self.service.tick()['status'])
        self.assertEqual(0, self.count())

    def test_monotonic_check_survives_process_restart(self):
        self.authorize()
        self.clock.advance(-5)
        self.assertEqual('CLOCK_REVIEW_REQUIRED', FixtureService(self.root, self.clock).tick()['status'])

    def test_budget_stops_repeated_repairs_after_rollback(self):
        self.edit('signals.json', independent_healthy=False)
        self.authorize(max_actions=1)
        self.assertEqual('ROLLED_BACK', self.service.tick()['outcome'])
        self.clock.advance(20)
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])
        self.assertEqual(1, self.count())

    def test_backoff_persists(self):
        self.edit('signals.json', independent_healthy=False)
        self.authorize(max_actions=3)
        self.service.tick()
        restarted = FixtureService(self.root, self.clock)
        self.assertEqual('NOT_DUE', restarted.tick()['status'])
        self.clock.advance(11)
        restarted.tick()
        self.assertEqual(2, self.count())
        with restarted.core.tx() as c:
            state = restarted._state(c)
        self.assertEqual(self.clock() + 20, state['next_due'])

    def test_os_lease_prevents_duplicate_actions(self):
        self.authorize()
        with process_lock(self.service.lock):
            with self.assertRaises(Busy): FixtureService(self.root, self.clock).tick()
        self.assertEqual('VERIFIED', self.service.tick()['outcome'])
        self.assertEqual(1, self.count())

    def test_concurrent_workers_one_effect(self):
        self.authorize()
        results = []
        def run():
            try: results.append(FixtureService(self.root, self.clock).tick())
            except Busy: results.append({'status': 'BUSY'})
        workers = [threading.Thread(target=run) for _ in range(4)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(1, self.count())
        self.assertEqual(1, sum(r.get('outcome') == 'VERIFIED' for r in results))

    def test_restart_before_effect_aborts_without_replay(self):
        order = self.pending()
        receipt = FixtureService(self.root, self.clock).tick()
        self.assertEqual('INTERRUPTED_NO_EFFECT', receipt['outcome'])
        self.assertTrue(receipt['reconciled_after_restart'])
        self.assertFalse(json.loads((self.root / 'gateway.json').read_text())['enabled'])
        self.assertEqual(0, ReadView(self.root).work_order_status(order)['observation']['enabled'])

    def test_restart_after_effect_verifies_without_replay(self):
        self.pending(execute=True)
        with patch.object(Control, 'execute', side_effect=AssertionError('No replay')):
            receipt = FixtureService(self.root, self.clock).tick()
        self.assertEqual('VERIFIED_RECONCILED', receipt['outcome'])
        self.assertTrue(receipt['reconciled_after_restart'])

    def test_expired_lease_never_replays_uncertain_effect(self):
        order = self.pending()
        with self.service.core.tx() as c:
            c.execute("UPDATE control_orders SET status='EXECUTING',grant=NULL WHERE id=?", (order,))
            self.service._set(c, lease_until=self.clock() - 1)
        receipt = FixtureService(self.root, self.clock).tick()
        self.assertEqual('NEEDS_RECONCILIATION', receipt['outcome'])
        self.assertFalse(json.loads((self.root / 'gateway.json').read_text())['enabled'])
        self.assertEqual(1, self.count())
        self.clock.advance(100)
        self.assertEqual('NEEDS_RECONCILIATION', FixtureService(self.root, self.clock).tick()['status'])
        self.assertEqual(1, self.count())

    def test_restart_unhealthy_after_effect_does_not_invent_rollback_permission(self):
        self.pending(execute=True)
        self.edit('signals.json', independent_healthy=False)
        receipt = FixtureService(self.root, self.clock).tick()
        self.assertEqual('NEEDS_RECONCILIATION', receipt['outcome'])
        self.assertTrue(json.loads((self.root / 'gateway.json').read_text())['enabled'])

    def test_orphan_checkpoint_is_not_replayed(self):
        self.authorize()
        self.service.core.propose('gateway.json', 'enabled', True)
        self.assertEqual('INTERRUPTED_NO_EFFECT', FixtureService(self.root, self.clock).tick()['outcome'])
        self.assertEqual(1, self.count())

    def test_exception_after_effect_is_reconciled(self):
        self.authorize()
        original = self.service.observe
        calls = [0]
        def interrupted():
            calls[0] += 1
            if calls[0] == 2: raise OSError('simulated observation interruption')
            return original()
        with patch.object(self.service, 'observe', side_effect=interrupted):
            self.assertEqual('INTERRUPTED', self.service.tick()['status'])
        self.assertEqual('VERIFIED_RECONCILED', FixtureService(self.root, self.clock).tick()['outcome'])

    def test_policy_expires_between_repair_and_rollback(self):
        self.edit('signals.json', independent_healthy=False)
        self.authorize(ttl=1)
        original = self.service.core.execute
        def execute(*args, **kwargs):
            value = original(*args, **kwargs)
            self.clock.advance(2)
            return value
        with patch.object(self.service.core, 'execute', side_effect=execute):
            self.assertEqual('INTERRUPTED', self.service.tick()['status'])
        self.assertTrue(json.loads((self.root / 'gateway.json').read_text())['enabled'])
        self.assertEqual('NEEDS_RECONCILIATION', FixtureService(self.root, self.clock).tick()['outcome'])

    def test_receipt_preserves_authorizing_revision_after_revocation(self):
        self.authorize()
        original = self.service.core.execute
        def execute_then_revoke(*args, **kwargs):
            result = original(*args, **kwargs)
            FixtureService(self.root, self.clock).revoke()
            return result
        with patch.object(self.service.core, 'execute', side_effect=execute_then_revoke):
            receipt = self.service.tick()
        self.assertEqual('VERIFIED', receipt['outcome'])
        self.assertEqual(1, receipt['permission_revision'])
        self.assertEqual(2, receipt['current_permission_revision'])

    def test_rollback_receipt_distinguishes_verification_and_restored_state(self):
        self.edit('signals.json', independent_healthy=False)
        self.authorize()
        receipt = self.service.tick()
        self.assertEqual('post_repair_verification', receipt['observation_stage'])
        self.assertTrue(receipt['observation']['enabled'])
        self.assertFalse(receipt['post_action_observation']['enabled'])
        self.assertFalse(ReadView(self.root).health()['observation']['enabled'])

    def test_policy_expiry_at_exact_effect_boundary(self):
        self.authorize(ttl=1)
        before = (self.root / 'gateway.json').read_bytes()
        original = self.service.core.atomic_write
        def delayed_write(path, payload):
            self.clock.advance(2)
            return original(path, payload)
        with patch.object(self.service.core, 'atomic_write', side_effect=delayed_write):
            self.assertEqual('INTERRUPTED', self.service.tick()['status'])
        self.assertEqual(before, (self.root / 'gateway.json').read_bytes())
        self.assertEqual('NEEDS_RECONCILIATION', FixtureService(self.root, self.clock).tick()['outcome'])

    def test_policy_expiry_during_temp_fsync_prevents_replace(self):
        self.authorize(ttl=1)
        before = (self.root / 'gateway.json').read_bytes()
        original = os.fsync
        def slow_fsync(fd):
            original(fd)
            self.clock.advance(2)
        with patch('fixture_service.os.fsync', side_effect=slow_fsync):
            self.assertEqual('INTERRUPTED', self.service.tick()['status'])
        self.assertEqual(before, (self.root / 'gateway.json').read_bytes())
        self.assertEqual([], list(self.root.glob('.clawcare-fixture-*')))

    def test_live_worker_can_revoke_and_renew(self):
        stop = threading.Event()
        worker = threading.Thread(target=lambda: self.service.run(stop, poll=.02))
        worker.start()
        try:
            time.sleep(.06)
            controller = FixtureService(self.root, self.clock)
            controller.revoke()
            deadline = time.monotonic() + 2
            while True:
                try:
                    controller.authorize_fixture()
                    break
                except Busy:
                    if time.monotonic() >= deadline: raise
                    time.sleep(.01)
            self.clock.advance()
            deadline = time.monotonic() + 2
            while self.count() == 0 and time.monotonic() < deadline: time.sleep(.01)
            self.assertEqual(1, self.count())
            controller.revoke()
            with controller.core.tx() as c:
                self.assertEqual('1', c.execute("SELECT value FROM control_settings WHERE key='paused'").fetchone()[0])
        finally:
            stop.set(); worker.join(2)
        self.assertFalse(worker.is_alive())

    def test_supervisor_stop_invalidates_cached_policy(self):
        from fixture_service_supervisor import FixtureSupervisor
        self.authorize()
        supervisor = FixtureSupervisor(self.service)
        supervisor.request_stop()
        supervisor.request_start()
        self.service.core.resume()
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])
        self.assertEqual(0, self.count())

    def test_wrong_json_types_are_bounded_failures(self):
        self.authorize()
        for value in (None, [], 'text', 5, True):
            with self.subTest(value=value):
                (self.root / 'signals.json').write_text(json.dumps(value))
                self.clock.advance()
                self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_fixture_drift_rejected(self):
        self.authorize()
        self.edit('gateway.json', unrelated=True)
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_symlink_rejected(self):
        other = Path(self.temp.name) / 'other.json'
        other.write_text('{}')
        (self.root / 'signals.json').unlink()
        (self.root / 'signals.json').symlink_to(other)
        self.authorize()
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_duplicate_json_key_rejected(self):
        (self.root / 'signals.json').write_text('{"responding":true,"responding":false}')
        self.authorize()
        self.assertEqual('POLICY_OR_INPUT_BLOCKED', self.service.tick()['status'])

    def test_authorize_does_not_accept_unbounded_ttl_or_budget(self):
        for options in ({'ttl': 901}, {'ttl': 0}, {'max_actions': 4}, {'max_actions': True}):
            with self.assertRaises(Denied): self.authorize(**options)

    def test_read_view_never_promotes_control_byte_check_to_service_success(self):
        order = self.pending(execute=True)
        view = ReadView(self.root).work_order_status(order)
        self.assertEqual('PENDING_SERVICE_VERIFICATION', view['status'])
        self.assertEqual('VERIFIED', view['control_status'])

    def test_read_view_cannot_write(self):
        view = ReadView(self.root)
        with view._connect() as c:
            with self.assertRaises(sqlite3.OperationalError): c.execute('DELETE FROM fixture_service')
        self.assertIn('not proof', view.health()['note'])

    def test_mcp_exposes_only_three_reads(self):
        bridge = Bridge(ReadView(self.root))
        self.assertIn('error', bridge.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}))
        bridge.dispatch({'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {}})
        tools = bridge.dispatch({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})['result']['tools']
        self.assertEqual(4, len(tools))
        self.assertTrue(all(tool['annotations']['readOnlyHint'] for tool in tools))
        for name in ('clawcare_execute', 'clawcare_approve', 'clawcare_revoke'):
            self.assertTrue(bridge.call(name, {})['isError'])
        self.assertTrue(bridge.call('clawcare_health', {'run': True})['isError'])

    def test_mcp_stdio_smoke(self):
        payload = '\n'.join(json.dumps(x) for x in [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'clawcare_health', 'arguments': {}}},
        ]) + '\n'
        proc = subprocess.run([sys.executable, 'fixture_service_mcp.py', '--root', str(self.root)],
                              input=payload, text=True, capture_output=True, timeout=5)
        self.assertEqual(0, proc.returncode, proc.stderr)
        replies = [json.loads(x) for x in proc.stdout.splitlines()]
        self.assertEqual(2, len(replies))
        self.assertTrue(json.loads(replies[1]['result']['content'][0]['text'])['synthetic'])

    def test_supervised_fixture_process_repairs_and_stops(self):
        from supervisor import Supervisor
        self.authorize()
        proc = subprocess.Popen([sys.executable, 'fixture_service_supervisor.py', '--root', str(self.root), 'run'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 8
            while self.count() == 0 and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(.03)
            self.assertEqual(1, self.count())
            supervisor = Supervisor(self.service.database)
            supervisor.request_stop()
            out, err = proc.communicate(timeout=8)
            self.assertEqual(0, proc.returncode, err.decode())
            self.assertTrue(supervisor.status()['control_paused'])
            self.assertEqual('STOPPED', supervisor.status()['status'])
            self.assertEqual('VERIFIED', ReadView(self.root).health()['status'])
        finally:
            if proc.poll() is None:
                proc.kill(); proc.communicate(timeout=5)

    def test_managed_worker_exits_on_parent_eof(self):
        proc = subprocess.Popen([sys.executable, 'fixture_service.py', '--root', str(self.root), 'run', '--managed'],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
            self.assertEqual(0, proc.returncode)
            with process_lock(self.service.lock): pass
        finally:
            if proc.poll() is None: proc.kill(); proc.wait(timeout=5)
            proc.stdout.close(); proc.stderr.close()

    def test_scheduled_loop_stops_and_deduplicates(self):
        self.authorize()
        stop = threading.Event()
        worker = threading.Thread(target=lambda: self.service.run(stop, poll=.02))
        worker.start()
        for _ in range(100):
            if self.count(): break
            time.sleep(.01)
        stop.set(); worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(1, self.count())


if __name__ == '__main__': unittest.main()
