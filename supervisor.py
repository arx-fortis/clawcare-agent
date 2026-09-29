"""Independent ClawCare worker supervision. No repair execution or model access."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from control import Control
from process_lock import process_lock, Busy


class Supervisor:
    def __init__(self, database, max_failures=5, base_delay=1, max_delay=30,
                 stable_seconds=60, poll=0.25, worker_command=None):
        self.db=str(Path(database).resolve())
        self.core=Control(self.db)
        self.max_failures=max_failures
        self.base_delay=base_delay
        self.max_delay=max_delay
        self.stable_seconds=stable_seconds
        self.poll=poll
        # pythonw has no reliable standard streams. The watched child requires a
        # real stdin pipe, so use python.exe without creating a console window.
        child_python=str(Path(sys.executable).with_name('python.exe')) if Path(sys.executable).name.lower()=='pythonw.exe' else sys.executable
        self.worker_command=worker_command or [child_python,str(Path(__file__).resolve()),'--db',self.db,'worker']
        self.interrupted=False
        self.child=None
        with self.core.tx() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS supervisor_state(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                desired TEXT NOT NULL, status TEXT NOT NULL,
                failures INTEGER NOT NULL, next_start REAL NOT NULL,
                supervisor_pid INTEGER, worker_pid INTEGER, heartbeat REAL)''')
            c.execute("INSERT OR IGNORE INTO supervisor_state VALUES(1,'running','IDLE',0,0,NULL,NULL,NULL)")

    def status(self):
        with self.core.tx() as c:
            result=dict(c.execute('SELECT * FROM supervisor_state WHERE singleton=1').fetchone())
            result['control_paused']=c.execute("SELECT value FROM control_settings WHERE key='paused'").fetchone()[0]=='1'
            result['heartbeat_age_seconds']=None if result['heartbeat'] is None else max(0,time.time()-result['heartbeat'])
            result['note']='PID/status are last recorded evidence; a stale heartbeat is not proof of a running process.'
            return result

    def request_stop(self):
        # Pause first: stopping supervision must not leave outstanding repair grants.
        self.core.pause()
        with self.core.tx() as c:
            c.execute("UPDATE supervisor_state SET desired='stopped' WHERE singleton=1")
            self.core.log(c,'supervisor','STOP_REQUESTED',approvals_revoked=True)

    def request_start(self):
        with self.core.tx() as c:
            c.execute("UPDATE supervisor_state SET desired='running',failures=0,next_start=0 WHERE singleton=1")
            self.core.log(c,'supervisor','START_REQUESTED',control_pause_preserved=True)

    def state(self, status, **fields):
        with self.core.tx() as c:
            fields.update(status=status,heartbeat=time.time(),supervisor_pid=os.getpid())
            c.execute('UPDATE supervisor_state SET '+','.join(k+'=?' for k in fields)+' WHERE singleton=1',tuple(fields.values()))
            self.core.log(c,'supervisor',status,**{k:v for k,v in fields.items() if k not in ('heartbeat','supervisor_pid')})

    def heartbeat(self):
        with self.core.tx() as c:
            c.execute('UPDATE supervisor_state SET heartbeat=? WHERE singleton=1',(time.time(),))

    def stop_child(self):
        if self.child is None:
            return
        if self.child.stdin:
            self.child.stdin.close()  # Managed worker exits on EOF even if supervisor dies.
        try:
            self.child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.child.terminate()
            try: self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.child.kill(); self.child.wait(timeout=3)
        self.child=None

    def run(self):
        with process_lock(self.db+'.supervisor.lock'):
            return self._run()

    def _run(self):
        try:
            self.state('STARTING',worker_pid=None)
            while not self.interrupted:
                state=self.status()
                if state['desired']=='stopped':
                    self.state('STOPPED',worker_pid=None); return 0
                if state['failures']>=self.max_failures:
                    self.state('EXHAUSTED',worker_pid=None); return 0
                if time.time()<state['next_start']:
                    self.heartbeat(); time.sleep(self.poll); continue
                env=os.environ.copy(); env['CLAWCARE_DB']=self.db
                started=time.monotonic()
                try:
                    self.child=subprocess.Popen(self.worker_command,env=env,stdin=subprocess.PIPE,
                                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                except OSError:
                    failures=state['failures']+1
                    delay=min(self.max_delay,self.base_delay*2**min(failures-1,20))
                    self.state('SPAWN_FAILED',worker_pid=None,failures=failures,next_start=time.time()+delay)
                    continue
                self.state('RUNNING',worker_pid=self.child.pid)
                reset=False
                while self.child.poll() is None and not self.interrupted:
                    current=self.status()
                    if current['desired']=='stopped':
                        self.stop_child(); self.state('STOPPED',worker_pid=None); return 0
                    if not reset and time.monotonic()-started>=self.stable_seconds:
                        with self.core.tx() as c:
                            c.execute('UPDATE supervisor_state SET failures=0,next_start=0 WHERE singleton=1')
                        reset=True
                    self.heartbeat(); time.sleep(self.poll)
                if self.interrupted:
                    break
                exit_code=self.child.returncode
                self.stop_child()
                if exit_code==75:
                    # Do not kill or take over a worker launched by another owner.
                    self.state('WORKER_CONFLICT',worker_pid=None); return 1
                failures=self.status()['failures']+1
                delay=min(self.max_delay,self.base_delay*2**min(failures-1,20))
                self.state('BACKOFF',worker_pid=None,failures=failures,next_start=time.time()+delay)
            return 0
        finally:
            self.stop_child()
            if self.interrupted:
                self.request_stop(); self.state('STOPPED',worker_pid=None)


def managed_worker(db):
    def watch_parent():
        sys.stdin.buffer.read()
        os._exit(0)
    threading.Thread(target=watch_parent,daemon=True).start()
    os.environ['CLAWCARE_DB']=db
    import clawcare
    clawcare.DB=db
    sys.argv=['clawcare.py','worker']
    clawcare.main()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=os.environ.get('CLAWCARE_DB','clawcare.sqlite3'))
    p.add_argument('command',choices=['run','start','enable','stop','status','worker'])
    args=p.parse_args()
    if args.command=='worker':
        managed_worker(str(Path(args.db).resolve())); return
    s=Supervisor(args.db)
    if args.command=='status': print(json.dumps(s.status(),indent=2)); return
    if args.command=='stop': s.request_stop(); print('Stop requested; approvals revoked. Check status for STOPPED.'); return
    if args.command=='enable': s.request_start(); print('Supervision enabled; start the scheduled task or use run. Repair pause is preserved.'); return
    if args.command=='start': s.request_start()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_: setattr(s,'interrupted',True))
    try: return s.run()
    except Busy: p.exit(75,'Another supervisor owns this ledger.\n')


if __name__=='__main__':
    sys.exit(main())
