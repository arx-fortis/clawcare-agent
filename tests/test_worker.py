import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cc',ROOT/'clawcare.py')
cc=importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)

class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        cc.DB=str(Path(self.tmp.name)/'test.sqlite3')
        self.old_health=cc.health
        cc.health=lambda url:(False,'fixture down')
        self.url='http://127.0.0.1:18789/health'
    def tearDown(self):
        cc.health=self.old_health
        self.tmp.cleanup()
    def command(self,command,**kw):
        with contextlib.redirect_stdout(io.StringIO()):
            cc.cmd(SimpleNamespace(command=command,**kw))
    def incident(self):
        with cc.conn() as c:
            cc.detect(c,self.url)
            return c.execute('SELECT id FROM incidents').fetchone()[0]
    def test_dedup_persistence_and_recovery(self):
        ident=self.incident()
        with cc.conn() as c:
            before=c.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            cc.detect(c,self.url)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],before)
        with self.assertRaises(SystemExit): self.command('repair',id=ident)
        self.command('approve',id=ident,actor='test-owner')
        self.command('repair',id=ident)
        with self.assertRaises(SystemExit): self.command('repair',id=ident)
        cc.health=lambda url:(True,'HTTP 200')
        with cc.conn() as c:
            cc.detect(c,self.url)
            self.assertEqual(c.execute('SELECT status FROM incidents').fetchone()[0],'COMPLETED')
            self.assertIn('External recovery',c.execute("SELECT data FROM events WHERE type='HANDOFF' ORDER BY id DESC").fetchone()[0])
        cc.health=lambda url:(False,'fixture down')
        with cc.conn() as c:
            cc.detect(c,self.url)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],2)
    def test_checkpoint_is_readable_snapshot(self):
        ident=self.incident()
        snapshot=cc.checkpoint()
        with contextlib.closing(sqlite3.connect(snapshot)) as c:
            self.assertEqual(c.execute('SELECT id FROM incidents').fetchone()[0],ident)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_retry_requires_new_approval(self):
        ident=self.incident()
        self.command('approve',id=ident,actor='test-owner')
        self.command('repair',id=ident)
        self.command('retry',id=ident)
        with self.assertRaises(SystemExit): self.command('repair',id=ident)
    def test_url_and_interval_validation(self):
        for value in ['file:///tmp/key','http://user:pass@host/','https://host/?key=secret']:
            with self.assertRaises(Exception): cc.target_url(value)
        for value in ['0','-1','86401']:
            with self.assertRaises(Exception): cc.positive_interval(value)
    def test_real_http_worker_restart_and_recovery(self):
        state={'healthy':False}
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if state['healthy'] else 503); self.end_headers()
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        self.url=f'http://127.0.0.1:{server.server_port}/health'
        self.command('add',url=self.url,interval=1)
        env=os.environ.copy(); env['CLAWCARE_DB']=cc.DB
        processes=[]
        def start():
            p=subprocess.Popen([sys.executable,str(ROOT/'clawcare.py'),'worker'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(p); return p
        def wait_status(expected):
            end=time.monotonic()+20
            while time.monotonic()<end:
                with cc.conn() as c:
                    row=c.execute('SELECT id,status FROM incidents').fetchone()
                    if row and row['status']==expected:return row['id']
                time.sleep(.1)
            self.fail('worker did not reach '+expected)
        try:
            p=start(); ident=wait_status('AWAITING_APPROVAL')
            p.terminate(); p.wait(timeout=10)
            p=start(); time.sleep(1.5)
            self.assertEqual(wait_status('AWAITING_APPROVAL'),ident)
            state['healthy']=True
            self.assertEqual(wait_status('COMPLETED'),ident)
            with cc.conn() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],1)
        finally:
            for p in processes:
                if p.poll() is None:p.terminate();p.wait(timeout=10)
            server.shutdown();server.server_close();thread.join(timeout=5)

if __name__=='__main__': unittest.main(verbosity=2)
