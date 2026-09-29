import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from connect import initialize, operator_command
from team_api import TeamService, Server
from team_mcp import Bridge


class ConnectTests(unittest.TestCase):
    def test_setup_never_reads_or_copies_provider_credentials_and_never_calls_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'private'
            with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'FAKE_PROVIDER_SECRET',
                                       'OPENAI_API_KEY': 'FAKE_OTHER_SECRET'}), \
                 patch('http.client.HTTPConnection', side_effect=AssertionError('Unexpected network')):
                initialize(root, 'demo', 'alice')
            for file in root.iterdir():
                if file.is_file():
                    self.assertNotIn(b'FAKE_PROVIDER_SECRET', file.read_bytes())
                    self.assertNotIn(b'FAKE_OTHER_SECRET', file.read_bytes())
            snippet = json.loads((root / 'openclaw-mcp.json').read_text())
            self.assertEqual(set(snippet), {'mcp'})
            self.assertNotIn('operator.token', json.dumps(snippet))
            self.assertIn('agent.token', json.dumps(snippet))
            service = TeamService(root)
            worker = service.credentials.authenticate((root / 'agent.token').read_text(), 'demo')
            owner = service.credentials.authenticate((root / 'operator.token').read_text(), 'demo')
            self.assertEqual(worker['role'], 'worker')
            self.assertEqual(owner['role'], 'owner')
            self.assertNotEqual(worker['player'], owner['player'])
            original = (root / 'operator.token').read_bytes()
            with self.assertRaises(FileExistsError):
                initialize(root, 'demo', 'alice')
            self.assertEqual(original, (root / 'operator.token').read_bytes())
            if os.name != 'nt':
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)

    def test_manual_mode_needs_no_ai_or_openclaw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = initialize(Path(tmp) / 'private', 'demo', 'alice', mode='manual')
            self.assertFalse((root / 'openclaw-mcp.json').exists())
            self.assertFalse(json.loads((root / 'connection.json').read_text())['provider_requests_by_control_plane'])

    def test_worker_handoff_then_separate_operator_review_without_ai(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = initialize(Path(tmp) / 'private', 'demo', 'alice')
            server = Server(TeamService(root))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                profile = json.loads((root / 'operator.json').read_text())
                profile['port'] = server.server_port
                (root / 'operator.json').write_text(json.dumps(profile))
                worker = Bridge(server.server_port, 'demo', 'default', root / 'agent.token')
                def call(op, **args):
                    value = worker.call('clawcare_' + op, args)
                    self.assertFalse(value['isError'], value)
                    return json.loads(value['content'][0]['text'])
                ident = call('create', resource='synthetic-fixture', objective='Inspect fixture', acceptance='Evidence logged')['id']
                claim = call('claim', id=ident, revision=0, ttl=600)
                report = dict(completed=['Test fixture inspected'], remaining=[], blockers=[],
                              verification=['Synthetic assertion passed'], checkpoint_refs=[],
                              recovery_notes=['No external effects'], next_work_order=None)
                call('handoff', id=ident, session=claim['session'], revision=1, request_id='fixture-1', report=report)
                request = root / 'review.json'
                request.write_text(json.dumps(dict(operation='review', id=ident, revision=2,
                                                   accept=True, evidence='Synthetic fixture independently checked')))
                operator_command(root / 'operator.json', request)
                state = call('inspect', id=ident)
                self.assertEqual(state['records'][0]['actor']['player_id'], 'alice:agent')
                self.assertEqual(state['audit_events'][-1]['actor']['player_id'], 'alice')
                request.write_text(json.dumps({'operation': 'workspace_info'}))
                self.assertIsInstance(operator_command(root / 'operator.json', request), dict)
                request.write_text(json.dumps({'operation': 'project_create', 'project_id': 'second', 'name': 'Second project'}))
                self.assertTrue(operator_command(root / 'operator.json', request)['updated'])
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
