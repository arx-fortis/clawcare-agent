import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from team_api import TeamService, Server
from team_mcp import Bridge


class MCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = TeamService(self.tmp.name)
        self.token = self.service.credentials.provision('demo', 'test-player', 'mcp-test', 'worker')
        self.file = Path(self.tmp.name) / 'credential'
        self.file.write_text(self.token)
        self.server = Server(self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.bridge = Bridge(self.server.server_port, 'demo', 'default', self.file)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def call(self, operation, **args):
        r = self.bridge.call('clawcare_' + operation, args)
        self.assertFalse(r['isError'], r)
        return json.loads(r['content'][0]['text'])

    def test_real_api_handoff_attribution_and_revocation(self):
        ident = self.call('create', resource='synthetic-fixture', objective='Inspect fixture', acceptance='Evidence logged')['id']
        claim = self.call('claim', id=ident, revision=0, ttl=600)
        report = dict(completed=['Synthetic fixture checked'], remaining=[], blockers=[],
                      verification=['Test fixture assertion passed'], checkpoint_refs=[],
                      recovery_notes=['No external changes'], next_work_order=None)
        self.call('handoff', id=ident, revision=1, session=claim['session'], request_id='test-handoff', report=report)
        state = self.call('inspect', id=ident)
        self.assertEqual(state['records'][0]['actor']['player_id'], 'test-player')
        self.assertEqual(state['records'][0]['actor']['agent_id'], 'mcp-test')
        self.assertTrue(state['records'][0]['actor']['authenticated'])
        self.service.credentials.revoke_player('demo', 'test-player')
        r = self.bridge.call('clawcare_inspect', {'id': ident})
        self.assertTrue(r['isError'])
        self.assertNotIn(self.token, json.dumps(r))

    def test_no_admin_review_execution_or_identity_override(self):
        for op in ('review', 'recover', 'member_update', 'exec', 'project_create'):
            self.assertTrue(self.bridge.call('clawcare_' + op, {})['isError'])
        for field in ('player_id', 'project_id', 'workspace', 'url', 'token'):
            self.assertTrue(self.bridge.call('clawcare_inspect', {'id': 'x', field: 'other'})['isError'])
        self.assertRaises(ValueError, Bridge, 8765, '../other', 'default', self.file)

    def test_stdio_transport_initialization_notifications_and_bounds(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18'}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'clawcare_create',
             'arguments': {'resource': 'stdio-fixture', 'objective': 'Inspect fixture', 'acceptance': 'Logged'}}},
        ]
        command = [sys.executable, str(ROOT / 'team_mcp.py'), '--port', str(self.server.server_port),
                   '--workspace', 'demo', '--token-file', str(self.file)]
        r = subprocess.run(command, input='\n'.join(map(json.dumps, requests)) + '\n',
                           text=True, capture_output=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        responses = list(map(json.loads, r.stdout.splitlines()))
        self.assertEqual([x['id'] for x in responses], [1, 2, 3])
        self.assertEqual(len(responses[1]['result']['tools']), 6)
        self.assertFalse(responses[2]['result']['isError'])
        self.assertNotIn(self.token, r.stdout + r.stderr)
        r = subprocess.run(command, input='x' * 65537, text=True, capture_output=True, timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, '')


if __name__ == '__main__':
    unittest.main()
