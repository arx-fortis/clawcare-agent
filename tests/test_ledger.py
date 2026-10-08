import hashlib
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from clawcare_ledger import Actor, Claim, Conflict, Evidence, Ledger, Lookup, Scope

SCOPE = Scope('tenant1', 'account1', 'acl1', 'revision1')
ACTOR = Actor('agent1', 'cloud1', 'order1')
LOOKUP = Lookup('provider', 'search', 'v1', {'query': 'Example', 'options': {'a': 1, 'b': 2}})


def process_claim(path):
    return Ledger(path).claim(SCOPE, LOOKUP, ACTOR).execution_token is not None


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.now = 1000.0
        self.ledger = Ledger(self.path, clock=lambda: self.now)
        self.evidence = Evidence.from_source('evidence:1', 'https://example.com/path?token=SECRET#fragment', 'a' * 64, 990)

    def tearDown(self): self.tmp.cleanup()

    def claim(self, **kwargs): return self.ledger.claim(SCOPE, LOOKUP, ACTOR, **kwargs)

    def complete(self, claim, **kwargs):
        data = dict(result_ref='artifact:1', evidence=[self.evidence], ttl_seconds=60)
        data.update(kwargs)
        return self.ledger.complete(SCOPE, claim.action_id, claim.execution_token, ACTOR, **data)

    def test_canonical_key_order_only(self):
        other = replace(LOOKUP, parameters={'options': {'b': 2, 'a': 1}, 'query': 'Example'})
        self.assertEqual(LOOKUP.key(SCOPE), other.key(SCOPE))
        for p in ({'query': 'example'}, {'query': 'Example '}, {'query': ['a', 'b']}, {'query': ['b', 'a']}):
            self.assertNotEqual(LOOKUP.key(SCOPE), replace(LOOKUP, parameters=p).key(SCOPE))

    def test_permission_account_and_adapter_boundaries(self):
        self.complete(self.claim())
        for field in ('tenant', 'account', 'access_context', 'permission_revision'):
            scope = replace(SCOPE, **{field: 'different'})
            self.assertEqual(self.ledger.inspect(scope, LOOKUP).state, 'missing')
            self.assertEqual(self.ledger.dashboard(scope)['actions'], [])
        self.assertEqual(self.ledger.inspect(SCOPE, replace(LOOKUP, adapter_version='v2')).state, 'missing')

    def test_threads_atomic_claim(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            claims = list(pool.map(lambda _: self.claim(), range(48)))
        self.assertEqual(sum(c.execution_token is not None for c in claims), 1)
        self.assertEqual(len({c.action_id for c in claims}), 1)
        self.assertEqual(len(self.ledger.dashboard(SCOPE)['events']), 48)

    def test_processes_atomic_claim(self):
        with multiprocessing.get_context('spawn').Pool(4) as pool:
            values = pool.map(process_claim, [str(self.path)] * 12)
        self.assertEqual(sum(values), 1)

    def test_restart_and_fresh_hit(self):
        self.complete(self.claim(), credits=2)
        new = Ledger(self.path, clock=lambda: self.now)
        hit = new.claim(SCOPE, LOOKUP, Actor('agent2', 'device2', 'work2'))
        self.assertEqual(hit.state, 'cached_fresh')
        self.assertIsNone(hit.execution_token)
        dash = new.dashboard(SCOPE)
        self.assertEqual(dash['billing']['by_provider']['provider']['reported_credits'], 2)
        self.assertEqual(dash['billing']['unknown_action_count'], 0)
        self.assertEqual(dash['events'][-1]['actor']['agent'], 'agent2')

    def test_stale_and_explicit_refresh(self):
        self.complete(self.claim())
        self.now += 60
        self.assertEqual(self.ledger.inspect(SCOPE, LOOKUP).state, 'cached_stale')
        next_claim = self.claim()
        self.assertIsNotNone(next_claim.execution_token)
        self.assertFalse(next_claim.result['fresh'])
        self.evidence = replace(self.evidence, observed_at=self.now)
        self.complete(next_claim)
        refreshed = self.claim(refresh=True)
        self.assertIsNotNone(refreshed.execution_token)
        self.assertTrue(refreshed.result['fresh'])
        self.assertIsNone(self.claim(refresh=True).execution_token)

    def test_failed_result_is_not_cache(self):
        claim = self.claim()
        self.ledger.fail(SCOPE, claim.action_id, claim.execution_token, ACTOR, code='provider_timeout')
        self.assertEqual(self.claim().state, 'failed')
        self.assertIsNone(self.claim().result)
        retry = self.claim(retry_failed=True)
        self.assertIsNotNone(retry.execution_token)
        self.complete(retry)
        self.assertEqual(self.claim().state, 'cached_fresh')

    def test_failed_refresh_remains_visible_with_old_evidence(self):
        self.complete(self.claim())
        claim = self.claim(refresh=True)
        self.ledger.fail(SCOPE, claim.action_id, claim.execution_token, ACTOR, code='failure', credits=1)
        view = self.ledger.inspect(SCOPE, LOOKUP)
        self.assertEqual(view.state, 'failed')
        self.assertTrue(view.result['fresh'])
        self.assertIsNone(self.claim().execution_token)

    def test_expiry_does_not_automatically_duplicate_spend(self):
        claim = self.claim(lease_seconds=5)
        self.now += 5
        restarted = Ledger(self.path, clock=lambda: self.now)
        view = restarted.claim(SCOPE, LOOKUP, ACTOR, refresh=True, retry_failed=True)
        self.assertTrue(view.lease_expired)
        self.assertIsNone(view.execution_token)
        restarted.abandon_expired(SCOPE, LOOKUP, ACTOR)
        self.assertEqual(self.claim().state, 'failed')
        with self.assertRaises(Conflict): self.complete(claim)
        retry = self.claim(retry_failed=True)
        self.assertNotEqual(retry.action_id, claim.action_id)
        self.assertEqual(restarted.dashboard(SCOPE)['actions'][0]['billing'], 'unknown')

    def test_renewal(self):
        claim = self.claim(lease_seconds=5)
        self.now += 4
        self.ledger.renew(SCOPE, claim.action_id, claim.execution_token, ACTOR, lease_seconds=10)
        self.now += 5
        self.assertFalse(self.ledger.inspect(SCOPE, LOOKUP).lease_expired)
        with self.assertRaises(Conflict): self.ledger.abandon_expired(SCOPE, LOOKUP, ACTOR)

    def test_completion_replay_idempotent_and_conflict_rejected(self):
        claim = self.claim()
        rid = self.complete(claim, credits=3)
        self.assertEqual(self.complete(claim, credits=3), rid)
        with self.assertRaises(Conflict): self.complete(claim, credits=4)
        with self.assertRaises(Conflict): self.complete(claim, result_ref='artifact:2')
        dash = self.ledger.dashboard(SCOPE)
        self.assertEqual(dash['billing']['by_provider']['provider']['reported_credits'], 3)
        self.assertEqual(len(dash['actions']), 1)

    def test_failure_replay_and_conflict(self):
        c = self.claim()
        for _ in range(2): self.ledger.fail(SCOPE, c.action_id, c.execution_token, ACTOR, code='timeout')
        with self.assertRaises(Conflict): self.ledger.fail(SCOPE, c.action_id, c.execution_token, ACTOR, code='other')
        with self.assertRaises(Conflict): self.complete(c)

    def test_wrong_scope_or_token_cannot_complete(self):
        c = self.claim()
        with self.assertRaises(Conflict): self.complete(replace(c, execution_token='wrong'))
        with self.assertRaises(Conflict):
            self.ledger.complete(replace(SCOPE, account='other'), c.action_id, c.execution_token, ACTOR, result_ref='ref:1', evidence=[self.evidence], ttl_seconds=5)

    def test_secret_urls_and_parameters_not_persisted(self):
        lookup = replace(LOOKUP, parameters={'api_key': 'VERY_SECRET', 'url': 'https://a.test/private?token=XXX'})
        c = self.ledger.claim(SCOPE, lookup, ACTOR)
        self.complete(c)
        raw = self.path.read_bytes()
        for secret in (b'VERY_SECRET', b'XXX', b'SECRET', b'/path', b'fragment'):
            self.assertNotIn(secret, raw)
        self.assertEqual(self.evidence.origin, 'https://example.com')
        self.assertNotIn(c.execution_token, json.dumps(self.ledger.dashboard(SCOPE)))

    def test_reject_raw_urls_and_invalid_numbers(self):
        c = self.claim()
        for bad in ('https://example.com?key=SECRET', '../file', 'raw secret text'):
            with self.assertRaises(ValueError): self.complete(c, result_ref=bad)
        for bad in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError): self.complete(c, credits=bad)
            with self.assertRaises(ValueError): self.complete(c, ttl_seconds=bad)
        with self.assertRaises(ValueError): self.complete(c, evidence=[])
        with self.assertRaises(ValueError): self.complete(c, evidence=[replace(self.evidence, origin='https://a.test/private')])
        self.assertEqual(self.ledger.inspect(SCOPE, LOOKUP).state, 'pending')

    def test_unknown_billing_not_zero(self):
        self.complete(self.claim())
        dash = self.ledger.dashboard(SCOPE)
        self.assertEqual(dash['actions'][0]['billing'], 'unknown')
        self.assertIsNone(dash['actions'][0]['credits'])
        self.assertEqual(dash['billing']['unknown_action_count'], 1)
        self.assertIsNone(dash['billing']['estimated_savings'])

    def test_zero_ttl_and_zero_reported_credits(self):
        self.complete(self.claim(), ttl_seconds=0, credits=0)
        self.assertEqual(self.ledger.inspect(SCOPE, LOOKUP).state, 'cached_stale')
        self.assertEqual(self.ledger.dashboard(SCOPE)['billing']['unknown_action_count'], 0)

    def test_atomic_rollback_on_event_validation(self):
        c = self.claim()
        with self.assertRaises(ValueError):
            self.ledger.complete(SCOPE, c.action_id, c.execution_token, Actor('bad actor', 'd', 'w'), result_ref='ref:1', evidence=[self.evidence], ttl_seconds=5)
        self.assertEqual(self.ledger.inspect(SCOPE, LOOKUP).state, 'pending')
        self.complete(c)


    def test_old_observations_not_promoted_to_fresh(self):
        self.complete(self.claim(), evidence=[replace(self.evidence, observed_at=100)])
        self.assertEqual(self.ledger.inspect(SCOPE, LOOKUP).state, 'cached_stale')

    def test_future_observations_rejected(self):
        with self.assertRaises(ValueError):
            self.complete(self.claim(), evidence=[replace(self.evidence, observed_at=1001)])

    def test_ipv6_and_invalid_port(self):
        evidence = Evidence.from_source('ref:1', 'https://[2001:db8::1]:8443/private', 'a' * 64, 900)
        self.assertEqual(evidence.origin, 'https://[2001:db8::1]:8443')
        evidence.data()
        with self.assertRaises(ValueError): replace(evidence, origin='https://example.com:99999').data()

    def test_clock_sampled_after_lock(self):
        import threading
        import time
        self.complete(self.claim(), evidence=[replace(self.evidence, observed_at=1000)], ttl_seconds=10)
        lock = sqlite3.connect(self.path, isolation_level=None)
        lock.execute('BEGIN IMMEDIATE')
        started = threading.Event()
        def run():
            started.set()
            return self.claim(lease_seconds=5)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            started.wait()
            time.sleep(0.05)
            self.now = 1020
            lock.execute('COMMIT')
            claim = future.result()
        lock.close()
        self.assertIsNotNone(claim.execution_token)
        self.assertEqual(claim.lease_expires_at, 1025)


    def test_output_and_extraction_options_are_distinct(self):
        keys = set()
        for params in (
            {'url': 'https://example.com', 'format': 'markdown'},
            {'url': 'https://example.com', 'format': 'json'},
            {'url': 'https://example.com', 'format': 'json', 'extraction': {'query': 'price'}},
            {'url': 'https://example.com', 'format': 'json', 'extraction': {'query': 'owner'}},
            {'url': 'https://example.com', 'format': 'markdown', 'maxAge': 0},
        ):
            keys.add(replace(LOOKUP, parameters=params).key(SCOPE))
        self.assertEqual(len(keys), 5)

    def test_result_kind_and_derivation_provenance(self):
        self.complete(self.claim(), result_kind='derived_answer', derived_from=['artifact:full-page'])
        result = self.ledger.inspect(SCOPE, LOOKUP).result
        self.assertEqual(result['result_kind'], 'derived_answer')
        self.assertEqual(result['derived_from'], ['artifact:full-page'])

    def test_database_created_private(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)


    def test_unknown_billing_reconciles_without_resurrecting_failure(self):
        c = self.claim(lease_seconds=1)
        self.now += 1
        self.ledger.abandon_expired(SCOPE, LOOKUP, ACTOR)
        for _ in range(2):
            self.ledger.reconcile_billing(SCOPE, c.action_id, ACTOR, receipt_id='receipt:1', credits=5, expected_revision=0)
        dash = self.ledger.dashboard(SCOPE)
        self.assertEqual(dash['billing']['by_provider']['provider']['reported_credits'], 5)
        self.assertEqual(dash['billing']['unknown_action_count'], 0)
        self.assertEqual(dash['actions'][0]['state'], 'failed')
        with self.assertRaises(Conflict):
            self.ledger.reconcile_billing(SCOPE, c.action_id, ACTOR, receipt_id='receipt:2', credits=9, expected_revision=0)
        self.ledger.reconcile_billing(SCOPE, c.action_id, ACTOR, receipt_id='receipt:2', credits=4, expected_revision=1)
        self.assertEqual(self.ledger.dashboard(SCOPE)['billing']['by_provider']['provider']['reported_credits'], 4)

    def test_billing_separated_by_provider(self):
        self.complete(self.claim(), credits=3)
        c = self.ledger.claim(SCOPE, replace(LOOKUP, provider='other'), ACTOR)
        self.complete(c, credits=2)
        self.assertEqual(set(self.ledger.dashboard(SCOPE)['billing']['by_provider']), {'provider', 'other'})

    def test_empty_database_path_rejected(self):
        with self.assertRaises(ValueError): Ledger('')


    def test_inspect_clock_sampled_after_read_lock(self):
        import threading
        import time
        self.complete(self.claim(), evidence=[replace(self.evidence, observed_at=1000)], ttl_seconds=10)
        lock = sqlite3.connect(self.path, isolation_level=None)
        lock.execute('BEGIN EXCLUSIVE')
        started = threading.Event()
        def run():
            started.set()
            return self.ledger.inspect(SCOPE, LOOKUP)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            started.wait()
            time.sleep(0.05)
            self.now = 1020
            lock.execute('COMMIT')
            view = future.result()
        lock.close()
        self.assertEqual(view.state, 'cached_stale')

if __name__ == '__main__': unittest.main()
