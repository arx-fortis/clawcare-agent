"""Source-checkpoint smoke tests; no installation or external service calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UpgradeEntrypointTests(unittest.TestCase):
    def test_fixture_entrypoint_help(self):
        for name in ('fixture_service.py', 'fixture_service_supervisor.py',
                     'fixture_service_mcp.py'):
            with self.subTest(name=name):
                result = subprocess.run([sys.executable, str(ROOT / name), '--help'],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--root', result.stdout)

    def test_fixture_cli_round_trip_and_persisted_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = str(Path(temporary) / 'new-fixture')
            def invoke(*arguments):
                result = subprocess.run(
                    [sys.executable, str(ROOT / 'fixture_service.py'), '--root', root, *arguments],
                    capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            self.assertEqual(invoke('init-fixture')['status'], 'PAUSED_FIXTURE_CREATED')
            self.assertTrue(invoke('authorize-fixture', '--ttl', '60', '--max-actions', '1')['synthetic'])
            receipt = invoke('once')
            self.assertEqual(receipt['outcome'], 'VERIFIED')
            self.assertTrue(receipt['synthetic'])
            self.assertFalse(receipt['real_gateway_repaired'])
            self.assertEqual(invoke('status')['status'], 'VERIFIED')
            self.assertEqual(invoke('revoke')['status'], 'PAUSED')

    def test_packaging_remains_bounded_review_templates(self):
        windows = json.loads((ROOT / 'packaging/windows-task-review.json').read_text())
        self.assertFalse(windows['install_automatically'])
        self.assertFalse(windows['overwrite_existing_task'])
        self.assertEqual(windows['execution_time_limit_seconds'], 900)
        linux = (ROOT / 'packaging/clawcare-fixture.service.in').read_text()
        self.assertIn('REVIEW TEMPLATE ONLY', linux)
        self.assertIn('RuntimeMaxSec=900', linux)
        self.assertIn('UMask=0077', linux)
