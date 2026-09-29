import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from control import Control, Denied


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'managed'; self.root.mkdir()
        self.path=self.root/'service.json'
        self.original=b'{"enabled": false, "private_note": "PRIVATE_FIXTURE_SENTINEL"}\n'
        self.path.write_bytes(self.original)
        self.db=Path(self.tmp.name)/'ledger.sqlite3'
        self.core=Control(self.db); self.core.initialize(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def proposal(self,probe=None):
        return self.core.propose('service.json','enabled',True,probe)

    def test_real_repair_probe_and_exact_rollback(self):
        path=self.path
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if json.loads(path.read_bytes())['enabled'] else 503)
                self.end_headers()
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            p=self.proposal(f'http://127.0.0.1:{server.server_port}/health')
            self.core.approve(p['id'],p['scope'])
            self.assertEqual(self.core.execute(p['id']),'VERIFIED')
            handoff=self.core.handoff(p['id'])
            self.assertNotIn('PRIVATE_FIXTURE_SENTINEL',json.dumps(handoff))
            self.assertNotIn(str(self.root),json.dumps(handoff))
            with self.assertRaises(Denied): self.core.execute(p['id'],'rollback')
            self.core.approve(p['id'],handoff['rollback_scope'],action='rollback')
            self.assertEqual(self.core.execute(p['id'],'rollback'),'ROLLED_BACK')
            self.assertEqual(self.path.read_bytes(),self.original)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_approval_denies_missing_wrong_scope_expired_and_replay(self):
        p=self.proposal()
        with self.assertRaises(Denied): self.core.execute(p['id'])
        with self.assertRaises(Denied): self.core.approve(p['id'],'wrong-scope')
        self.assertEqual(self.path.read_bytes(),self.original)
        self.core.approve(p['id'],p['scope'])
        with self.core.tx() as c: c.execute('UPDATE control_orders SET expires=0')
        with self.assertRaises(Denied): self.core.execute(p['id'])
        self.core.approve(p['id'],p['scope'])
        self.core.execute(p['id'])
        with self.assertRaises(Denied): self.core.execute(p['id'])

    def test_pause_revokes_grants_and_abort_prevents_execution(self):
        p=self.proposal(); self.core.approve(p['id'],p['scope'])
        self.core.pause()
        with self.assertRaises(Denied): self.core.execute(p['id'])
        self.core.resume()
        with self.assertRaises(Denied): self.core.execute(p['id'])
        self.core.approve(p['id'],p['scope']); self.core.abort(p['id'])
        with self.assertRaises(Denied): self.core.execute(p['id'])
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_drift_dedup_and_scope_boundary(self):
        for path in ['../outside.json',str(self.path)]:
            with self.assertRaises(Denied): self.core.propose(path,'enabled',True)
        p=self.proposal()
        with self.assertRaises(Denied): self.proposal()
        self.core.approve(p['id'],p['scope'])
        changed=b'{"enabled":false,"another_change":true}'
        self.path.write_bytes(changed)
        with self.assertRaises(Denied): self.core.execute(p['id'])
        self.assertEqual(self.path.read_bytes(),changed)

    def test_checkpoint_corruption_denied(self):
        p=self.proposal(); self.core.approve(p['id'],p['scope']); self.core.execute(p['id'])
        h=self.core.handoff(p['id'])
        self.core.approve(p['id'],h['rollback_scope'],action='rollback')
        with self.core.tx() as c: c.execute('UPDATE control_orders SET before_bytes=?',(b'bad',))
        with self.assertRaises(Denied): self.core.execute(p['id'],'rollback')
        self.assertTrue(json.loads(self.path.read_bytes())['enabled'])

    def test_probe_failure_requires_recovery_not_success(self):
        p=self.proposal('http://127.0.0.1:9/health'); self.core.approve(p['id'],p['scope'])
        with patch('control.health',return_value=(False,'fixture failed')):
            self.assertEqual(self.core.execute(p['id']),'RECOVERY_REQUIRED')
        with self.assertRaises(Denied): self.core.execute(p['id'])

    def test_crash_after_file_write_survives_and_never_replays(self):
        p=self.proposal(); self.core.approve(p['id'],p['scope'])
        script='''import os,sys
from control import Control
c=Control(sys.argv[1]); original=c.atomic_write
def crash(path,payload):
 original(path,payload)
 os._exit(77)
c.atomic_write=crash
c.execute(sys.argv[2])
'''
        run=subprocess.run([sys.executable,'-c',script,str(self.db),p['id']],cwd=ROOT,capture_output=True,timeout=20)
        self.assertEqual(run.returncode,77)
        core=Control(self.db)
        self.assertEqual(core.handoff(p['id'])['status'],'EXECUTING')
        self.assertTrue(json.loads(self.path.read_bytes())['enabled'])
        with self.assertRaises(Denied): core.execute(p['id'])
        core.reconcile(p['id'])
        h=core.handoff(p['id']); self.assertEqual(h['status'],'RECOVERY_REQUIRED')
        core.approve(p['id'],h['rollback_scope'],action='rollback')
        self.assertEqual(core.execute(p['id'],'rollback'),'ROLLED_BACK')
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_competing_processes_cannot_consume_same_approval(self):
        p=self.proposal(); self.core.approve(p['id'],p['scope'])
        command=[sys.executable,str(ROOT/'control.py'),'--db',str(self.db),'execute',p['id']]
        a=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        b=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        a.communicate(timeout=20); b.communicate(timeout=20)
        self.assertEqual(sorted([a.returncode,b.returncode]),[0,2])
        self.assertEqual(self.core.handoff(p['id'])['attempts'],1)

    def test_old_rollback_cannot_take_new_work_order_target(self):
        p=self.proposal(); self.core.approve(p['id'],p['scope']); self.core.execute(p['id'])
        h=self.core.handoff(p['id'])
        new=self.core.propose('service.json','enabled',False)
        with self.assertRaises(Denied):
            self.core.approve(p['id'],h['rollback_scope'],action='rollback')
        self.assertEqual(self.core.handoff(new['id'])['status'],'AWAITING_APPROVAL')

    def test_symlink_and_oversize_are_rejected(self):
        self.path.write_bytes(b' '*65537)
        with self.assertRaises(Denied): self.proposal()
        self.path.write_bytes(self.original)
        link=self.root/'link.json'
        try: link.symlink_to(self.path)
        except OSError: return  # Windows may lack symlink privilege; Linux CI exercises it.
        with self.assertRaises(Denied): self.core.propose('link.json','enabled',True)

if __name__=='__main__': unittest.main()
