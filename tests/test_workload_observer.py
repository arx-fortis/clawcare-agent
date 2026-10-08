import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from workload_observer import (LinuxMemoryObserver, _bounded_text, discover_cgroup,
                               parse_meminfo, parse_memory_value, run_bounded_demo,
                               submit_memory_observation)


class ParserTests(unittest.TestCase):
    def test_meminfo_uses_kib_and_available_not_free(self):
        result = parse_meminfo('MemTotal: 1000 kB\nMemFree: 999 kB\nMemAvailable: 250 kB\n')
        self.assertEqual({'total_bytes': 1024000, 'available_bytes': 256000}, result)

    def test_invalid_or_missing_meminfo_stays_unknown(self):
        for text in ('MemTotal: 100 kB\nMemFree: 90 kB\n',
                     'MemTotal: 100 kB\nMemAvailable: -1 kB\n',
                     'MemTotal: 100 kB\nMemAvailable: 101 kB\n',
                     'MemTotal: 0 kB\nMemAvailable: 0 kB\n',
                     'MemTotal: 100 B\nMemAvailable: 10 kB\n',
                     'MemTotal: 100 kB\nMemAvailable: 10 kB\nMemAvailable: 9 kB\n',
                     'MemTotal: 18446744073709551615 kB\nMemAvailable: 1 kB\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_meminfo(text)

    def test_cgroup_values_and_explicit_unlimited(self):
        self.assertEqual(0, parse_memory_value('0\n'))
        self.assertEqual(8192, parse_memory_value('8192\n'))
        self.assertIsNone(parse_memory_value('max\n', allow_max=True))
        for value in ('', '-1', '+1', 'NaN', '1.5', '1 kB', '12\n13', '18446744073709551616', 'max'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_memory_value(value)

    def test_cgroup_mount_resolution_and_escape(self):
        result = discover_cgroup('0::/tenant/work\n',
                                 '31 20 0:29 /tenant /my\\040cgroup rw - cgroup2 cgroup rw\n')
        self.assertEqual('/tenant', result['mount_root'])
        self.assertEqual(str(Path('/my cgroup/work')), result['leaf'])

    def test_prefers_widest_visible_ancestry(self):
        result = discover_cgroup('0::/tenant/work\n',
                                 '31 20 0:29 /tenant /narrow rw - cgroup2 cgroup rw\n'
                                 '32 20 0:29 / /wide rw - cgroup2 cgroup rw\n')
        self.assertEqual(str(Path('/wide/tenant/work')), result['leaf'])

    def test_ambiguous_missing_and_traversal_membership_rejected(self):
        mounts = '31 20 0:29 / /cgroup rw - cgroup2 cgroup rw\n'
        for text in ('', '2:memory:/x\n', '0::/a\n0::/b\n', '0::/../x\n',
                     '0::relative\n', '0::/old (deleted)\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                discover_cgroup(text, mounts)
        with self.assertRaises(ValueError):
            discover_cgroup('0::/tenant-other/work\n',
                            '31 20 0:29 /tenant /cgroup rw - cgroup2 cgroup rw\n')
        with self.assertRaises(ValueError):
            discover_cgroup('0::/\n', '')

    def test_bounded_read_rejects_oversized_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            path.write_text('x' * 129)
            with self.assertRaises(ValueError):
                _bounded_text(path, 128)
            self.assertEqual('x' * 129, _bounded_text(path, 129))

    @unittest.skipUnless(hasattr(os, 'O_NOFOLLOW'), 'requires no-follow file opens')
    def test_bounded_read_rejects_final_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_text('10')
            link = Path(directory) / 'link'
            link.symlink_to(target)
            with self.assertRaises(OSError):
                _bounded_text(link, 128)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO test')
    def test_bounded_read_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fifo'
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                _bounded_text(path, 128)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.proc = Path('/fixture-proc')
        self.mount = Path('/fixture-cgroup')
        self.files = {
            self.proc / 'meminfo': 'MemTotal: 1000 kB\nMemAvailable: 800 kB\n',
            self.proc / 'self/cgroup': '0::/parent/worker\n',
            self.proc / 'self/mountinfo': '31 20 0:29 / /fixture-cgroup rw - cgroup2 cgroup rw\n',
        }
        for relative, current, maximum in (('', '200000', 'max'),
                                            ('parent', '400000', '500000'),
                                            ('parent/worker', '100000', '900000')):
            path = self.mount / relative
            self.files[path / 'memory.current'] = current
            self.files[path / 'memory.max'] = maximum

    def read(self, path, limit):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def collect(self, clock=lambda: 100):
        with patch('workload_observer._bounded_text', side_effect=self.read):
            return LinuxMemoryObserver(self.proc, clock=clock).collect()

    def test_ancestor_limit_and_usage_constrain_leaf(self):
        result = self.collect()
        self.assertTrue(result['synthetic'])
        self.assertEqual('observed', result['status'])
        self.assertEqual('host_and_visible_cgroup_v2', result['scope'])
        self.assertEqual(100000, result['available_bytes'])
        self.assertEqual(500000, result['total_bytes'])
        self.assertEqual(819200, result['host']['available_bytes'])
        self.assertEqual(3, len(result['cgroup']['ancestors']))
        self.assertFalse(result['safety_guarantee'])
        json.dumps(result, allow_nan=False)

    def test_host_pressure_can_be_tighter_than_cgroup(self):
        self.files[self.proc / 'meminfo'] = 'MemTotal: 1000 kB\nMemAvailable: 1 kB\n'
        self.assertEqual(1024, self.collect()['available_bytes'])

    def test_over_limit_usage_is_zero_headroom(self):
        self.files[self.mount / 'parent/memory.current'] = '510000'
        result = self.collect()
        self.assertEqual('observed', result['status'])
        self.assertEqual(0, result['available_bytes'])

    def test_unlimited_is_explicit_not_a_missing_value(self):
        for path in list(self.files):
            if path.name == 'memory.max':
                self.files[path] = 'max'
        result = self.collect()
        self.assertEqual('observed', result['status'])
        self.assertEqual(819200, result['available_bytes'])
        self.assertTrue(all(row['unlimited'] for row in result['cgroup']['ancestors']))

    def test_missing_ancestor_interface_fails_closed(self):
        del self.files[self.mount / 'memory.max']
        result = self.collect()
        self.assertEqual('unknown', result['status'])
        self.assertEqual('observed', result['host']['status'])
        self.assertIsNone(result['available_bytes'])
        self.assertIsNone(result['total_bytes'])

    def test_missing_v2_mount_retains_host_without_assuming_capacity(self):
        self.files[self.proc / 'self/mountinfo'] = ''
        result = self.collect()
        self.assertEqual('unknown', result['status'])
        self.assertEqual(819200, result['host']['available_bytes'])
        self.assertIsNone(result['available_bytes'])

    def test_malformed_host_or_cgroup_data_is_unknown(self):
        for path in (self.proc / 'meminfo', self.mount / 'parent/memory.current',
                     self.mount / 'parent/memory.max'):
            with self.subTest(path=path):
                old = self.files[path]
                self.files[path] = 'not a valid value'
                self.assertEqual('unknown', self.collect()['status'])
                self.files[path] = old

    def test_zero_limit_is_unknown_not_usable_total(self):
        self.files[self.mount / 'parent/memory.max'] = '0'
        result = self.collect()
        self.assertEqual('unknown', result['status'])
        self.assertIn('ZERO_VISIBLE_CAPACITY', result['errors'])

    def test_bad_clock_is_json_safe_unknown(self):
        for value in (float('nan'), float('inf'), -1, True, 'now'):
            with self.subTest(value=value):
                result = self.collect(lambda: value)
                self.assertEqual('unknown', result['status'])
                self.assertIsNone(result['observed_at'])
                json.dumps(result, allow_nan=False)

    def test_cgroup_migration_while_collecting_invalidates_snapshot(self):
        calls = 0
        original = self.read

        def moving_read(path, limit):
            nonlocal calls
            if path == self.proc / 'self/cgroup':
                calls += 1
                if calls > 1:
                    return '0::/different\n'
            return original(path, limit)

        self.read = moving_read
        result = self.collect()
        self.assertEqual('unknown', result['status'])
        self.assertEqual('unknown', result['cgroup']['status'])

    def test_excessively_deep_cgroup_fails_before_counter_reads(self):
        self.files[self.proc / 'self/cgroup'] = '0::/' + '/'.join(['deep'] * 64) + '\n'
        result = self.collect()
        self.assertEqual('unknown', result['status'])
        self.assertEqual([], result['cgroup']['ancestors'])

    def test_unsupported_platform_returns_unknown(self):
        with patch('workload_observer.sys.platform', 'win32'):
            result = LinuxMemoryObserver().collect()
        self.assertFalse(result['synthetic'])
        self.assertEqual('unknown', result['status'])
        self.assertIn('UNSUPPORTED_PLATFORM', result['errors'])

    def test_adapter_forwards_unknown_to_clear_existing_evidence(self):
        engine = Mock()
        engine.observe_memory.return_value = False
        self.assertFalse(submit_memory_observation(engine, {
            'status': 'unknown', 'observed_at': 100, 'available_bytes': 999, 'total_bytes': 1000}))
        engine.observe_memory.assert_called_once_with(100, None, None)

    def test_adapter_forwards_observed_values(self):
        engine = Mock()
        sample = self.collect()
        submit_memory_observation(engine, sample)
        engine.observe_memory.assert_called_once_with(100, 100000, 500000)


class DemoTests(unittest.TestCase):
    def test_actual_artifact_work_progress_is_independently_verified(self):
        observer = Mock()
        observer.collect.return_value = {'synthetic': False, 'status': 'unknown'}
        result = run_bounded_demo(items=3, item_bytes=64, observer=observer)
        self.assertFalse(result['synthetic'])
        self.assertFalse(result['memory_governed'])
        self.assertFalse(result['production_safety_demonstrated'])
        self.assertTrue(result['temporary_artifacts_removed'])
        self.assertEqual(3, observer.collect.call_count)
        self.assertEqual([1, 2, 3], [event['progress_seq'] for event in result['events']])
        for index, event in enumerate(result['events']):
            self.assertEqual(hashlib.sha256(bytes([index]) * 64).hexdigest(), event['sha256'])
            self.assertEqual('artifact_verified', event['kind'])
            self.assertEqual(64, event['bytes_verified'])

    def test_demo_bounds_reject_large_or_invalid_workloads(self):
        for items in (0, 17, True, 1.5):
            with self.subTest(items=items), self.assertRaises(ValueError):
                run_bounded_demo(items=items)
        for size in (0, 65537, True, 1.5):
            with self.subTest(size=size), self.assertRaises(ValueError):
                run_bounded_demo(item_bytes=size)

    @unittest.skipUnless(sys.platform.startswith('linux') and Path('/proc/meminfo').exists(),
                         'requires real Linux procfs')
    def test_live_linux_snapshot_and_real_tiny_workload(self):
        before = LinuxMemoryObserver().collect()
        self.assertFalse(before['synthetic'])
        self.assertEqual('linux_procfs', before['source'])
        # No assertion that this environment exposes cgroups or enough capacity.
        self.assertIn(before['status'], ('observed', 'unknown'))
        self.assertEqual('observed', before['host']['status'])
        self.assertGreater(before['host']['total_bytes'], 0)
        result = run_bounded_demo(items=2, item_bytes=1024)
        self.assertEqual(2, result['items_verified'])
        for event in result['events']:
            self.assertFalse(event['synthetic'])
            self.assertFalse(event['memory']['synthetic'])
            self.assertGreaterEqual(event['memory']['observed_at'], before['observed_at'])
            json.dumps(event, allow_nan=False)


if __name__ == '__main__':
    unittest.main()
