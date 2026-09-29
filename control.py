"""Standalone, local-owner control plane. One bounded JSON Boolean repair adapter.

The SQLite ledger and managed directory must be writable only by the trusted
local owner. This is not a sandbox against hostile processes under that owner.
"""
import argparse
from contextlib import contextmanager
import getpass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import uuid

from clawcare import health, target_url


class Denied(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Control:
    def __init__(self, database):
        self.database = str(Path(database).absolute())
        with self.tx() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS control_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO control_settings VALUES('paused','0');
                CREATE TABLE IF NOT EXISTS control_orders(
                    id TEXT PRIMARY KEY, target TEXT NOT NULL, status TEXT NOT NULL,
                    field TEXT NOT NULL, desired INTEGER NOT NULL, probe TEXT,
                    before_bytes BLOB NOT NULL, after_bytes BLOB NOT NULL,
                    before_hash TEXT NOT NULL, after_hash TEXT NOT NULL,
                    scope TEXT NOT NULL, grant TEXT, expires REAL,
                    attempts INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS control_active_target ON control_orders(target)
                    WHERE status NOT IN ('VERIFIED','ROLLED_BACK','ABORTED');
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident TEXT, at TEXT, type TEXT, data TEXT);
            ''')

    @contextmanager
    def tx(self):
        c = sqlite3.connect(self.database, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=FULL')
        c.execute('BEGIN IMMEDIATE')
        try:
            with c:
                yield c
        finally:
            c.close()

    def log(self, c, ident, event, **evidence):
        # Callers pass fixed reason codes and hashes, never file bytes or errors.
        c.execute('INSERT INTO events(incident,at,type,data) VALUES(?,?,?,?)',
                  (ident, str(time.time()), 'CONTROL_'+event, json.dumps(evidence, sort_keys=True)))

    def initialize(self, root):
        p = Path(root).absolute()
        self.no_links(p)
        if not p.is_dir():
            raise Denied('Managed root must already be a directory')
        with self.tx() as c:
            old = c.execute("SELECT value FROM control_settings WHERE key='root'").fetchone()
            if old and old[0] != str(p):
                raise Denied('Managed root is immutable for this ledger')
            c.execute("INSERT OR IGNORE INTO control_settings VALUES('root',?)", (str(p),))

    @staticmethod
    def no_links(path):
        for part in [path, *path.parents]:
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise Denied('Symbolic links and Windows reparse points are not allowed')

    def file(self, c, relative):
        row = c.execute("SELECT value FROM control_settings WHERE key='root'").fetchone()
        if not row:
            raise Denied('Initialize a managed root first')
        rel = Path(relative)
        if rel.is_absolute() or rel.drive or '..' in rel.parts or ':' in relative:
            raise Denied('Target must be a relative managed JSON file')
        p = Path(row[0]) / rel
        self.no_links(p)
        if p.suffix.lower() != '.json' or not p.is_file() or p.stat().st_nlink != 1:
            raise Denied('Only regular, non-hardlinked JSON files are supported')
        if p.stat().st_size > 65536:
            raise Denied('Target exceeds the 64 KiB runbook limit')
        return p

    def order(self, c, ident):
        r = c.execute('SELECT * FROM control_orders WHERE id=?', (ident,)).fetchone()
        if not r:
            raise Denied('Unknown work order')
        return r

    def active(self, c):
        if c.execute("SELECT value FROM control_settings WHERE key='paused'").fetchone()[0] == '1':
            raise Denied('Control plane is paused')

    def ownership(self, c, r):
        if c.execute("SELECT 1 FROM control_orders WHERE target=? AND id!=? AND status NOT IN ('VERIFIED','ROLLED_BACK','ABORTED')",
                     (r['target'],r['id'])).fetchone():
            raise Denied('Another unfinished work order owns this target')

    def propose(self, target, field, desired, probe=None):
        if type(desired) is not bool or not field or len(field) > 80:
            raise Denied('A named Boolean field is required')
        if probe:
            target_url(probe)
        with self.tx() as c:
            self.active(c)
            p = self.file(c, target)
            before = p.read_bytes()
            data = json.loads(before)
            if not isinstance(data, dict) or type(data.get(field)) is not bool:
                raise Denied('The existing top-level field must be Boolean')
            if data[field] == desired:
                raise Denied('No change required')
            data[field] = desired
            after = (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode()
            if len(after) > 65536:
                raise Denied('Repaired target exceeds the runbook size limit')
            scope = digest(json.dumps([str(p), field, desired, probe, digest(before), digest(after)],
                                      sort_keys=True).encode())
            ident = 'WO-'+uuid.uuid4().hex
            try:
                c.execute('''INSERT INTO control_orders
                    (id,target,status,field,desired,probe,before_bytes,after_bytes,before_hash,after_hash,scope)
                    VALUES(?,?,'AWAITING_APPROVAL',?,?,?,?,?,?,?,?)''',
                          (ident, os.path.normcase(str(Path(target))), field, int(desired), probe, before, after,
                           digest(before), digest(after), scope))
            except sqlite3.IntegrityError:
                raise Denied('An unfinished work order already owns this target') from None
            self.log(c, ident, 'CHECKPOINTED', before_hash=digest(before), after_hash=digest(after), scope=scope)
            return {'id': ident, 'scope': scope, 'status': 'AWAITING_APPROVAL'}

    def approval_scope(self, r, action):
        if action == 'repair':
            return r['scope']
        return digest(('rollback:'+r['scope']).encode())

    def approve(self, ident, scope, ttl=300, action='repair'):
        if action not in ('repair', 'rollback') or not 1 <= ttl <= 900:
            raise Denied('Unsupported action or expiry; maximum 900 seconds')
        with self.tx() as c:
            self.active(c)
            r = self.order(c, ident)
            self.ownership(c,r)
            allowed = ('AWAITING_APPROVAL',) if action == 'repair' else ('VERIFIED', 'RECOVERY_REQUIRED')
            if r['status'] not in allowed or scope != self.approval_scope(r, action):
                raise Denied('Approval does not match current work order and action')
            expected = r['before_hash'] if action == 'repair' else r['after_hash']
            if digest(self.file(c, r['target']).read_bytes()) != expected:
                raise Denied('Target changed; inspect and create a new work order')
            c.execute('UPDATE control_orders SET grant=?,expires=? WHERE id=?', (action,time.time()+ttl,ident))
            self.log(c, ident, 'APPROVED', action=action, scope=scope, local_owner=getpass.getuser(), ttl=ttl)

    @staticmethod
    def atomic_write(path, payload):
        fd, temporary = tempfile.mkstemp(prefix='.clawcare-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def execute(self, ident, action='repair'):
        # Persist the claim BEFORE filesystem effects. A crash cannot replay a grant.
        with self.tx() as c:
            self.active(c)
            r = self.order(c, ident)
            self.ownership(c,r)
            allowed = ('AWAITING_APPROVAL',) if action == 'repair' else ('VERIFIED','RECOVERY_REQUIRED')
            if action not in ('repair','rollback') or r['status'] not in allowed:
                raise Denied('Action is not valid in this state')
            if r['grant'] != action or not r['expires'] or r['expires'] <= time.time():
                raise Denied('Fresh scoped approval required')
            expected = r['before_hash'] if action == 'repair' else r['after_hash']
            payload = r['after_bytes'] if action == 'repair' else r['before_bytes']
            wanted = r['after_hash'] if action == 'repair' else r['before_hash']
            if digest(payload) != wanted:
                raise Denied('Checkpoint integrity check failed')
            if digest(self.file(c,r['target']).read_bytes()) != expected:
                raise Denied('Target drift detected before execution')
            c.execute("UPDATE control_orders SET status='EXECUTING',grant=NULL,expires=NULL,attempts=attempts+1 WHERE id=?",(ident,))
            self.log(c,ident,'CLAIMED',action=action)
        try:
            with self.tx() as c:
                self.active(c)
                current = self.order(c,ident)
                if current['status'] != 'EXECUTING':
                    raise Denied('Operation was interrupted or aborted')
                if r['expires'] <= time.time():
                    raise Denied('Approval expired before filesystem effect')
                path = self.file(c,r['target'])
                if digest(path.read_bytes()) != expected:
                    raise Denied('Target drift detected after claim')
                self.atomic_write(path,payload)
                verified = digest(path.read_bytes()) == wanted
                probe_ok = health(r['probe'])[0] if action == 'repair' and r['probe'] else None
                if probe_ok is False:
                    verified = False
                state = ('VERIFIED' if action == 'repair' else 'ROLLED_BACK') if verified else 'RECOVERY_REQUIRED'
                c.execute('UPDATE control_orders SET status=? WHERE id=?',(state,ident))
                self.log(c,ident,'VERIFICATION',action=action,bytes_match=digest(path.read_bytes())==wanted,
                         probe_healthy=probe_ok,status=state)
                return state
        except Exception:
            with self.tx() as c:
                # Never erase an independent abort with a catch-all failure status.
                c.execute("UPDATE control_orders SET status='RECOVERY_REQUIRED' WHERE id=? AND status='EXECUTING'",(ident,))
                self.log(c,ident,'INTERRUPTED',reason='inspect_before_retry')
            raise Denied('Execution interrupted; inspect the work order before recovery') from None

    def pause(self):
        with self.tx() as c:
            c.execute("UPDATE control_settings SET value='1' WHERE key='paused'")
            c.execute('UPDATE control_orders SET grant=NULL,expires=NULL')
            self.log(c,'control-plane','PAUSED',approvals_revoked=True)

    def resume(self):
        with self.tx() as c:
            c.execute("UPDATE control_settings SET value='0' WHERE key='paused'")
            self.log(c,'control-plane','RESUMED',fresh_approvals_required=True)

    def abort(self, ident):
        with self.tx() as c:
            r=self.order(c,ident)
            if r['status'] in ('VERIFIED','ROLLED_BACK'):
                raise Denied('Completed actions need separately approved rollback')
            c.execute("UPDATE control_orders SET status='ABORTED',grant=NULL,expires=NULL WHERE id=?",(ident,))
            self.log(c,ident,'ABORTED',changes_undone=False)

    def reconcile(self, ident):
        with self.tx() as c:
            r=self.order(c,ident)
            if r['status'] != 'EXECUTING':
                raise Denied('Only interrupted executions need reconciliation')
            actual=digest(self.file(c,r['target']).read_bytes())
            observed='before' if actual==r['before_hash'] else 'after' if actual==r['after_hash'] else 'drift'
            c.execute("UPDATE control_orders SET status='RECOVERY_REQUIRED',grant=NULL,expires=NULL WHERE id=?",(ident,))
            self.log(c,ident,'RECONCILED',observed=observed,automatic_replay=False)

    def handoff(self, ident):
        with self.tx() as c:
            r=self.order(c,ident)
            result={k:r[k] for k in ('id','status','scope','before_hash','after_hash','attempts')}
            result['rollback_scope']=self.approval_scope(r,'rollback')
            result['next_action']='inspect_current_state_before_next_work_order'
            result['events']=[dict(e) for e in c.execute('SELECT at,type,data FROM events WHERE incident=? ORDER BY id',(ident,))]
            return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=os.environ.get('CLAWCARE_DB','clawcare.sqlite3'))
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('init'); a.add_argument('root')
    a=sub.add_parser('propose'); a.add_argument('target'); a.add_argument('field'); a.add_argument('value',choices=['true','false']); a.add_argument('--probe')
    for command in ('approve','execute','handoff','abort','reconcile'):
        a=sub.add_parser(command); a.add_argument('id')
        if command in ('approve','execute'): a.add_argument('--action',choices=['repair','rollback'],default='repair')
        if command=='approve': a.add_argument('--scope',required=True); a.add_argument('--ttl',type=int,default=300)
    sub.add_parser('pause'); sub.add_parser('resume')
    args=p.parse_args(); core=Control(args.db)
    try:
        if args.command=='init': result=core.initialize(args.root)
        elif args.command=='propose': result=core.propose(args.target,args.field,args.value=='true',args.probe)
        elif args.command=='approve': result=core.approve(args.id,args.scope,args.ttl,args.action)
        elif args.command=='execute': result=core.execute(args.id,args.action)
        elif args.command in ('pause','resume'): result=getattr(core,args.command)()
        else: result=getattr(core,args.command)(args.id)
        print(json.dumps(result if result is not None else {'result':'recorded'},indent=2))
    except (Denied,ValueError,OSError) as e:
        # Low-level exception detail may contain paths; do not echo it.
        p.exit(2, (str(e) if isinstance(e,Denied) else 'Invalid or inaccessible managed input')+'\n')

if __name__=='__main__':
    main()
