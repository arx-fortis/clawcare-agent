import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from control import Control,Denied
from supervisor import Supervisor
from process_lock import process_lock,Busy


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/'ledger.sqlite3'
        self.supervisor=Supervisor(self.db)
        self.processes=[]

    def tearDown(self):
        self.supervisor.request_stop()
        for process in self.processes:
            if process.poll() is None:
                try: process.wait(timeout=12)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        self.wait(lambda:self.lock_free(str(self.db)+'.worker.lock'))
        self.tmp.cleanup()

    def wait(self,predicate,seconds=15):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            value=predicate()
            if value:return value
            time.sleep(.05)
        self.fail('Timed out waiting for supervised fixture')

    @staticmethod
    def lock_free(path):
        try:
            with process_lock(path):return True
        except Busy:return False

    def start(self,command='run'):
        p=subprocess.Popen([sys.executable,str(ROOT/'supervisor.py'),'--db',str(self.db),command],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.processes.append(p)
        return p

    def test_worker_crash_restarts_and_stop_survives_new_supervisor(self):
        p=self.start()
        pid=self.wait(lambda:self.supervisor.status()['worker_pid'])
        # Only the child PID recorded by this isolated fixture is terminated.
        os.kill(pid,getattr(signal,'SIGKILL',signal.SIGTERM))
        self.wait(lambda:(s:=self.supervisor.status())['status']=='RUNNING' and s['worker_pid']!=pid)
        self.assertEqual(self.supervisor.status()['failures'],1)
        self.supervisor.request_stop(); p.wait(timeout=15)
        self.assertEqual(self.supervisor.status()['status'],'STOPPED')
        self.assertTrue(self.supervisor.status()['control_paused'])
        restarted=self.start(); restarted.wait(timeout=10)
        self.assertEqual(self.supervisor.status()['status'],'STOPPED')
        self.assertIsNone(self.supervisor.status()['worker_pid'])

    def test_supervisor_crash_releases_child_and_preserves_cases_and_revocation(self):
        import clawcare
        old=clawcare.DB; clawcare.DB=str(self.db)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self): self.send_response(503); self.end_headers()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with clawcare.conn() as c:
                c.execute('INSERT INTO targets VALUES(?,1)',(f'http://127.0.0.1:{server.server_port}/health',))
            def incident():
                with clawcare.conn() as c:
                    row=c.execute('SELECT id FROM incidents').fetchone()
                    return row[0] if row else None
            root=Path(self.tmp.name)/'managed';root.mkdir()
            (root/'fixture.json').write_text('{"enabled":false}')
            core=Control(self.db); core.initialize(root)
            order=core.propose('fixture.json','enabled',True)
            core.approve(order['id'],order['scope']);core.pause()
            p=self.start();ident=self.wait(incident)
            self.wait(lambda:not self.lock_free(str(self.db)+'.worker.lock'))
            p.kill();p.wait(timeout=10)
            self.wait(lambda:self.lock_free(str(self.db)+'.worker.lock'))
            new=self.start()
            self.wait(lambda:not self.lock_free(str(self.db)+'.worker.lock'))
            self.assertEqual(incident(),ident)
            self.assertTrue(self.supervisor.status()['control_paused'])
            core.resume()
            with self.assertRaises(Denied):core.execute(order['id'])
            self.assertEqual(core.handoff(order['id'])['status'],'AWAITING_APPROVAL')
            self.supervisor.request_stop();new.wait(timeout=15)
            with clawcare.conn() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0],1)
        finally:
            clawcare.DB=old
            server.shutdown();server.server_close();thread.join(timeout=5)

    def test_restart_budget_is_durable_and_backoff_is_recorded(self):
        s=Supervisor(self.db,max_failures=3,base_delay=.02,max_delay=.04,poll=.01,
                     worker_command=[sys.executable,'-c','raise SystemExit(2)'])
        self.assertEqual(s.run(),0)
        self.assertEqual(s.status()['status'],'EXHAUSTED')
        self.assertEqual(s.status()['failures'],3)
        with s.core.tx() as c:
            before=c.execute("SELECT COUNT(*) FROM events WHERE type='CONTROL_RUNNING'").fetchone()[0]
        s.run()
        with s.core.tx() as c:
            after=c.execute("SELECT COUNT(*) FROM events WHERE type='CONTROL_RUNNING'").fetchone()[0]
        self.assertEqual(before,after)
        s.request_start();self.assertEqual(s.status()['failures'],0)

    def test_second_supervisor_and_direct_worker_are_excluded(self):
        first=self.start();self.wait(lambda:not self.lock_free(str(self.db)+'.worker.lock'))
        second=self.start();self.assertEqual(second.wait(timeout=10),75)
        env=dict(os.environ,CLAWCARE_DB=str(self.db))
        direct=subprocess.run([sys.executable,str(ROOT/'clawcare.py'),'worker'],env=env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        self.assertEqual(direct.returncode,75)
        self.assertIsNone(first.poll())

    def test_spawn_failure_consumes_budget(self):
        s=Supervisor(self.db,max_failures=2,base_delay=.01,max_delay=.01,poll=.01,
                     worker_command=[str(Path(self.tmp.name)/'nonexistent-worker')])
        s.run()
        self.assertEqual(s.status()['status'],'EXHAUSTED')
        self.assertEqual(s.status()['failures'],2)

    @unittest.skipUnless(os.name=='nt','Windows windowless startup path')
    def test_windowless_supervisor_crash_still_stops_child(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        pythonw=str(Path(sys.executable).with_name('pythonw.exe'))
        p=subprocess.Popen([pythonw,str(ROOT/'supervisor.py'),'--db',str(self.db),'run'])
        self.processes.append(p)
        self.wait(lambda:not self.lock_free(str(self.db)+'.worker.lock'))
        child_pid=self.wait(lambda:self.supervisor.status()['worker_pid'])
        # A released file lock can precede final Windows process/SQLite handle
        # teardown. Hold the actual child handle and wait for process completion
        # before reopening its WAL, rather than inferring exit from that lock.
        handle=kernel.OpenProcess(0x00100000, False, child_pid)
        self.assertTrue(handle, 'Could not observe fixture child process')
        try:
            p.kill();p.wait(timeout=10)
            self.assertEqual(kernel.WaitForSingleObject(handle, 15000), 0,
                             'Fixture child did not exit after supervisor crash')
        finally:
            kernel.CloseHandle(handle)
        self.wait(lambda:self.lock_free(str(self.db)+'.worker.lock'))
        self.supervisor.request_stop()
        self.assertTrue(self.supervisor.status()['control_paused'])

if __name__=='__main__':unittest.main()
