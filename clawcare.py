#!/usr/bin/env python3
"""ClawCare MVP: durable monitoring, work orders, audit, approval and recovery."""
import argparse, json, os, sqlite3, time, urllib.request, urllib.error, uuid
from process_lock import process_lock, Busy
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime, timezone

DB = os.environ.get('CLAWCARE_DB', 'clawcare.sqlite3')
def now(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def conn():
    c=sqlite3.connect(DB, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, target TEXT, status TEXT, work_order TEXT, created TEXT, updated TEXT, attempts INTEGER DEFAULT 0, error TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS active_target ON incidents(target) WHERE status NOT IN ('COMPLETED','CLOSED');
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, incident TEXT, at TEXT, type TEXT, data TEXT);
    CREATE TABLE IF NOT EXISTS approvals(incident TEXT PRIMARY KEY, actor TEXT, at TEXT, scope TEXT);
    CREATE TABLE IF NOT EXISTS targets(url TEXT PRIMARY KEY, interval INTEGER DEFAULT 30);''')
    try:
        with c:
            yield c
    finally:
        c.close()
def target_url(value):
    p=urlsplit(value)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment:
        raise argparse.ArgumentTypeError('Use an HTTP(S) health URL without credentials, query or fragment')
    return value
def positive_interval(value):
    n=int(value)
    if not 1 <= n <= 86400:
        raise argparse.ArgumentTypeError('Interval must be 1..86400 seconds')
    return n
def checkpoint():
    folder=Path(DB).resolve().parent / 'checkpoints'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder / ('ledger-'+uuid.uuid4().hex+'.sqlite3')
    with conn() as source:
        dest=sqlite3.connect(path)
        try: source.backup(dest)
        finally: dest.close()
    return str(path)
def event(c,i,t,**data): c.execute('INSERT INTO events(incident,at,type,data) VALUES(?,?,?,?)',(i,now(),t,json.dumps(data,sort_keys=True)))
def health(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'ClawCare-MVP/0.1'}),timeout=5) as r:
            return 200 <= r.status < 400, 'HTTP '+str(r.status)
    except Exception as e: return False, type(e).__name__
def detect(c,url):
    ok,detail=health(url)
    current=c.execute("SELECT * FROM incidents WHERE target=? AND status NOT IN ('COMPLETED','CLOSED')",(url,)).fetchone()
    if ok:
        if current:
            event(c,current['id'],'HEALTHY_OBSERVED',detail=detail)
            if current['status'] in ('DETECTED','INSPECTING','AWAITING_APPROVAL','APPROVED','RECOVERY_REQUIRED'):
                c.execute("UPDATE incidents SET status='COMPLETED',updated=? WHERE id=?",(now(),current['id']))
                event(c,current['id'],'VERIFIED',healthy=True,detail=detail,source='monitor')
                event(c,current['id'],'HANDOFF',result='External recovery observed; no repair effect attributed',next_action='none')
        return
    if current:
        # Repeated unchanged failures do not grow the audit indefinitely.
        if current['error'] != detail:
            event(c,current['id'],'FAILURE_CHANGED',detail=detail)
            c.execute('UPDATE incidents SET error=?,updated=? WHERE id=?',(detail,now(),current['id']))
        return
    i='CC-'+uuid.uuid4().hex[:12]
    order={'id':'WO-'+i,'objective':'Restore '+url,'steps':['inspect failure','request approval for repair','execute approved adapter','verify health','record handoff'],'definition_of_done':'endpoint healthy after action','approval_gate':'required before repair'}
    c.execute('INSERT INTO incidents(id,target,status,work_order,created,updated,error) VALUES(?,?,?,?,?,?,?)',(i,url,'AWAITING_APPROVAL',json.dumps(order),now(),now(),detail))
    event(c,i,'DETECTED',detail=detail); event(c,i,'INSPECTED',target=url,observation=detail)
    event(c,i,'WORK_ORDER',**order); event(c,i,'APPROVAL_REQUIRED',scope='repair')
def run_once():
    with conn() as c:
        for row in c.execute('SELECT * FROM targets').fetchall(): detect(c,row['url'])
def cmd(args):
    if args.command=='checkpoint':
        print(checkpoint()); return
    with conn() as c:
        if args.command=='add':
            c.execute('INSERT INTO targets(url,interval) VALUES(?,?) ON CONFLICT(url) DO UPDATE SET interval=excluded.interval',(target_url(args.url),args.interval)); print('Monitoring',args.url)
        elif args.command=='list':
            for r in c.execute('SELECT id,target,status,error FROM incidents ORDER BY created DESC'): print(dict(r))
        elif args.command=='audit':
            for r in c.execute('SELECT at,type,data FROM events WHERE incident=? ORDER BY id',(args.id,)): print(dict(r))
        elif args.command=='approve':
            r=c.execute('SELECT * FROM incidents WHERE id=?',(args.id,)).fetchone()
            if not r or r['status']!='AWAITING_APPROVAL': raise SystemExit('Incident not awaiting approval')
            c.execute('INSERT OR REPLACE INTO approvals VALUES(?,?,?,?)',(args.id,args.actor,now(),'repair'))
            c.execute("UPDATE incidents SET status='APPROVED',updated=? WHERE id=?",(now(),args.id))
            event(c,args.id,'APPROVED',actor=args.actor,scope='repair'); print('Approved',args.id)
        elif args.command=='repair':
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM incidents WHERE id=?',(args.id,)).fetchone()
            if not r or r['status'] != 'APPROVED': raise SystemExit('Fresh approval required; simulation is single-use')
            if not c.execute('SELECT 1 FROM approvals WHERE incident=?',(args.id,)).fetchone(): raise SystemExit('Approval record missing')
            # MVP repair adapter is deliberately simulated. No shell or production changes.
            event(c,args.id,'BEFORE_STATE',target=r['target'],detail=r['error'])
            c.execute("UPDATE incidents SET status='VERIFYING',attempts=attempts+1,updated=? WHERE id=?",(now(),args.id))
            event(c,args.id,'EXECUTED',adapter='simulation',effect='none')
            ok,detail=health(r['target']); event(c,args.id,'VERIFIED',healthy=ok,detail=detail)
            status='COMPLETED' if ok else 'RECOVERY_REQUIRED'
            c.execute('UPDATE incidents SET status=?,updated=?,error=? WHERE id=?',(status,now(),detail,args.id))
            c.execute('DELETE FROM approvals WHERE incident=?',(args.id,))
            event(c,args.id,'HANDOFF',result=status,next_action='human repair or configure a bounded repair adapter' if not ok else 'none')
            print(args.id,status,detail)
        elif args.command=='retry':
            r=c.execute('SELECT status FROM incidents WHERE id=?',(args.id,)).fetchone()
            if not r or r['status']!='RECOVERY_REQUIRED': raise SystemExit('Case is not awaiting recovery')
            c.execute("UPDATE incidents SET status='AWAITING_APPROVAL',updated=? WHERE id=?",(now(),args.id))
            event(c,args.id,'APPROVAL_REQUIRED',scope='simulation only',reason='explicit retry request')
        elif args.command=='once': pass
    if args.command=='once': run_once()
def main():
    try:
        if 'worker' in __import__('sys').argv[1:]:
            with process_lock(str(Path(DB).resolve())+'.worker.lock'):
                return entrypoint()
        return entrypoint()
    except Busy:
        raise SystemExit(75)

def entrypoint():
    p=argparse.ArgumentParser(description='ClawCare background recovery MVP'); sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('add'); a.add_argument('url',type=target_url); a.add_argument('--interval',type=positive_interval,default=30)
    sub.add_parser('once'); sub.add_parser('list')
    a=sub.add_parser('audit'); a.add_argument('id')
    a=sub.add_parser('approve'); a.add_argument('id'); a.add_argument('--actor',required=True)
    a=sub.add_parser('repair'); a.add_argument('id')
    a=sub.add_parser('retry'); a.add_argument('id')
    sub.add_parser('checkpoint')
    a=sub.add_parser('worker'); a.add_argument('--interval',type=positive_interval,default=1)
    args=p.parse_args()
    if args.command=='worker':
        due={}
        print('ClawCare monitor running; repairs require a separate explicit command.',flush=True)
        try:
            while True:
                try:
                    with conn() as c:
                        for row in c.execute('SELECT * FROM targets').fetchall():
                            if time.monotonic() >= due.get(row['url'],0):
                                detect(c,row['url'])
                                due[row['url']]=time.monotonic()+max(1,row['interval'])
                except Exception as e: print('worker error:',type(e).__name__,flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print('Monitor stopped; committed cases remain in SQLite.',flush=True)
    else: cmd(args)
if __name__=='__main__': main()
