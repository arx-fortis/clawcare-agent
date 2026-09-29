"""Local work-order ownership and session handoffs. No external execution authority."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
from datetime import datetime, timezone

from control import Control, Denied


def summary(value, limit=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise Denied('A bounded, nonempty summary is required')
    # Defense in depth, not a guarantee that arbitrary prose contains no secrets.
    patterns=[r'(?i)\bsk-[A-Za-z0-9_-]{8,}', r'(?i)\bBearer\s+\S+',
              r'(?i)\b(password|api[_ -]?key|token|secret)\s*[:=]\s*\S+',
              r'-----BEGIN .*PRIVATE KEY-----',r'https?://[^\s/]+:[^\s/]+@']
    if any(re.search(p,value) for p in patterns):
        raise Denied('Remove credentials from the summary before write-back')
    return value.strip()


class Handoffs:
    def __init__(self,database,player_id=None,agent_id='local-cli'):
        self.actor={'player_id':summary(player_id or 'local:'+getpass.getuser(),120),
                    'agent_id':summary(agent_id,120),'identity_source':'local_declared',
                    'authenticated':False}
        self.core=Control(database)
        with self.core.tx() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS build_orders(
                  id TEXT PRIMARY KEY, resource TEXT NOT NULL, objective TEXT NOT NULL,
                  acceptance TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
                  predecessor TEXT UNIQUE, owner TEXT, session TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS build_claims(resource TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS build_records(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                  session TEXT NOT NULL, request_id TEXT NOT NULL, kind TEXT NOT NULL,
                  payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                  UNIQUE(order_id,session,request_id));
                CREATE TABLE IF NOT EXISTS build_chain(
                  sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL,
                  previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL);
            ''')

    def verify_chain(self,c):
        previous='GENESIS'; count=0
        for r in c.execute('SELECT * FROM build_chain ORDER BY sequence'):
            count+=1
            expected=hashlib.sha256((previous+'\n'+r['payload']).encode('utf-8')).hexdigest()
            if r['sequence']!=count or r['previous_hash']!=previous or r['record_hash']!=expected:
                raise Denied('Audit chain mismatch; reconcile before continuing')
            previous=expected
        return {'records':count,'terminal_hash':previous}

    def log(self,c,ident,event,actor=None,**evidence):
        chain=self.verify_chain(c)
        actor=dict(self.actor if actor is None else actor)
        payload=json.dumps({'schema_version':2,'event_id':uuid.uuid4().hex,'actor':actor,
            'work_order_id':ident,'event':event,'evidence':evidence,
            'recorded_at':datetime.now(timezone.utc).isoformat()},
            sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        previous=chain['terminal_hash']
        digest=hashlib.sha256((previous+'\n'+payload).encode('utf-8')).hexdigest()
        c.execute('INSERT INTO build_chain VALUES(?,?,?,?)',
                  (chain['records']+1,payload,previous,digest))
        self.core.log(c,ident,event,actor=actor,**evidence)

    def session_actor(self,c,ident,session):
        for row in c.execute('SELECT payload FROM build_chain ORDER BY sequence'):
            event=json.loads(row[0])
            if (event['work_order_id']==ident and event['event']=='WORK_CLAIMED'
                    and event['evidence'].get('session')==session):
                actor=event.get('actor')
                if actor is None:
                    raise Denied('Legacy session has no bound player; reconcile and claim a new session')
                if actor!=self.actor:
                    raise Denied('Player or agent differs from the session author')
                return actor
        raise Denied('Unknown session author')

    def sweep(self):
        # Commit expiry independently so a rejected stale write cannot undo it.
        with self.core.tx() as c:
            self.verify_chain(c)
            self.verify_reports(c)
            self.expire(c)

    def verify_reports(self,c):
        anchors=set()
        for row in c.execute('SELECT payload FROM build_chain'):
            event=json.loads(row[0])
            if event['event'] in ('SESSION_PROGRESS','SESSION_HANDOFF'):
                anchors.add((event['work_order_id'],event['evidence']['session'],event['evidence']['record_hash']))
        for row in c.execute('SELECT * FROM build_records'):
            digest=hashlib.sha256((row['kind']+row['payload']).encode()).hexdigest()
            if digest!=row['payload_hash'] or (row['order_id'],row['session'],digest) not in anchors:
                raise Denied('Report integrity mismatch; reconcile before continuing')

    def row(self,c,ident):
        r=c.execute('SELECT * FROM build_orders WHERE id=?',(ident,)).fetchone()
        if not r: raise Denied('Unknown build work order')
        return r

    def expire(self,c):
        for r in c.execute("SELECT * FROM build_orders WHERE status='ACTIVE' AND expires<=?",(time.time(),)).fetchall():
            c.execute("UPDATE build_orders SET status='REVIEW_REQUIRED',revision=revision+1,session=NULL,expires=NULL WHERE id=?",(r['id'],))
            self.log(c,r['id'],'SESSION_EXPIRED',
                     actor={'player_id':None,'agent_id':'clawcare-lease-monitor',
                            'identity_source':'system','authenticated':False},
                     resource_lock_retained=True,previous_owner=r['owner'],session=r['session'])

    def create_in(self,c,resource,objective,acceptance,predecessor=None):
        ident='BUILD-'+uuid.uuid4().hex
        c.execute("INSERT INTO build_orders VALUES(?,?,?,?,'QUEUED',0,?,NULL,NULL,NULL)",
                  (ident,resource,objective,acceptance,predecessor))
        self.log(c,ident,'WORK_CREATED',predecessor=predecessor,resource=resource,
                 objective=objective,acceptance=acceptance,execution_authorized=False)
        return ident

    def create(self,resource,objective,acceptance):
        resource=summary(resource,120).casefold()
        objective=summary(objective); acceptance=summary(acceptance)
        with self.core.tx() as c:
            return self.create_in(c,resource,objective,acceptance)

    def claim(self,ident,owner,revision,ttl=1800):
        self.sweep()
        owner=summary(owner,80)
        if not 1<=ttl<=14400: raise Denied('Session lease must be 1..14400 seconds')
        with self.core.tx() as c:
            self.expire(c)
            r=self.row(c,ident)
            if r['status']!='QUEUED' or r['revision']!=revision:
                raise Denied('Work order changed or is not claimable')
            if c.execute('SELECT 1 FROM build_claims WHERE resource=?',(r['resource'],)).fetchone():
                raise Denied('Another session or unresolved handoff owns this resource')
            session='SESSION-'+uuid.uuid4().hex
            c.execute('INSERT INTO build_claims VALUES(?,?)',(r['resource'],ident))
            c.execute("UPDATE build_orders SET status='ACTIVE',revision=revision+1,owner=?,session=?,expires=? WHERE id=?",
                      (owner,session,time.time()+ttl,ident))
            self.log(c,ident,'WORK_CLAIMED',owner=owner,session=session,execution_authorized=False)
            return {'id':ident,'session':session,'revision':revision+1,'execution_authorized':False}

    def current(self,c,ident,session,revision):
        self.session_actor(c,ident,session)
        self.expire(c)
        r=self.row(c,ident)
        if r['status']!='ACTIVE' or r['session']!=session or r['revision']!=revision:
            raise Denied('Session expired, was replaced, or revision is stale')
        return r

    def renew(self,ident,session,revision,ttl=1800):
        self.sweep()
        if not 1<=ttl<=14400: raise Denied('Session lease must be 1..14400 seconds')
        with self.core.tx() as c:
            self.current(c,ident,session,revision)
            c.execute('UPDATE build_orders SET expires=?,revision=revision+1 WHERE id=?',(time.time()+ttl,ident))
            self.log(c,ident,'SESSION_RENEWED',session=session,ttl=ttl)
            return revision+1

    def payload(self,report,kind):
        allowed={'completed','remaining','blockers','verification','checkpoint_refs','recovery_notes'}
        if kind=='HANDOFF': allowed.add('next_work_order')
        if not isinstance(report,dict) or set(report)!=allowed:
            raise Denied('Report fields must match the write-back schema exactly')
        result={}
        for key in allowed-{'next_work_order'}:
            value=report[key]
            if not isinstance(value,list) or len(value)>20:
                raise Denied('Report fields must be bounded lists of summaries')
            result[key]=[summary(item) for item in value]
        if kind=='HANDOFF':
            if not result['verification'] or not result['recovery_notes']:
                raise Denied('Handoff requires verification evidence and recovery notes')
            n=report['next_work_order']
            if n is not None:
                if not isinstance(n,dict) or set(n)!={'objective','acceptance'}:
                    raise Denied('Provide exactly one next work order or null')
                n={k:summary(v) for k,v in n.items()}
            result['next_work_order']=n
        return json.dumps(result,sort_keys=True)

    def write(self,ident,session,revision,request_id,report,kind='PROGRESS'):
        self.sweep()
        if kind not in ('PROGRESS','HANDOFF'): raise Denied('Unsupported record kind')
        request_id=summary(request_id,100)
        payload=self.payload(report,kind)
        fingerprint=hashlib.sha256((kind+payload).encode()).hexdigest()
        with self.core.tx() as c:
            self.session_actor(c,ident,session)
            prior=c.execute('SELECT payload_hash FROM build_records WHERE order_id=? AND session=? AND request_id=?',
                            (ident,session,request_id)).fetchone()
            if prior:
                if prior[0]!=fingerprint: raise Denied('Request ID already used for different content')
                return {'duplicate':True,'revision':self.row(c,ident)['revision']}
            self.current(c,ident,session,revision)
            c.execute('INSERT INTO build_records(order_id,session,request_id,kind,payload,payload_hash) VALUES(?,?,?,?,?,?)',
                      (ident,session,request_id,kind,payload,fingerprint))
            if kind=='HANDOFF':
                # Hold the resource until the handoff is reviewed, not merely posted.
                c.execute("UPDATE build_orders SET status='HANDOFF_REVIEW',revision=revision+1,session=NULL,expires=NULL WHERE id=?",(ident,))
            else:
                c.execute('UPDATE build_orders SET revision=revision+1 WHERE id=?',(ident,))
            self.log(c,ident,'SESSION_'+kind,session=session,record_hash=fingerprint)
            return {'duplicate':False,'revision':revision+1}

    def review(self,ident,reviewer,revision,accept,evidence):
        reviewer=summary(reviewer,80); evidence=summary(evidence)
        with self.core.tx() as c:
            self.verify_chain(c)
            self.verify_reports(c)
            r=self.row(c,ident)
            if r['status']!='HANDOFF_REVIEW' or r['revision']!=revision:
                raise Denied('Handoff changed or is not awaiting review')
            record=c.execute("SELECT payload FROM build_records WHERE order_id=? AND kind='HANDOFF' ORDER BY id DESC LIMIT 1",(ident,)).fetchone()
            report=json.loads(record[0])
            if accept and (report['remaining'] or report['blockers']):
                raise Denied('Unfinished or blocked work cannot be marked completed; reject and continue this order')
            successor=None
            c.execute('DELETE FROM build_claims WHERE order_id=?',(ident,))
            state='COMPLETED' if accept else 'QUEUED'
            c.execute('UPDATE build_orders SET status=?,revision=revision+1,owner=NULL WHERE id=?',(state,ident))
            if accept and report['next_work_order']:
                n=report['next_work_order']
                successor=self.create_in(c,r['resource'],n['objective'],n['acceptance'],ident)
            self.log(c,ident,'HANDOFF_REVIEWED',reviewer=reviewer,accepted=accept,evidence=evidence,
                          verification_source='local_operator_attestation',next_work_order=successor)
            return {'status':state,'revision':revision+1,'next_work_order':successor}

    def recover(self,ident,reviewer,revision,evidence,prior_session_stopped=False):
        self.sweep()
        reviewer=summary(reviewer,80); evidence=summary(evidence)
        if not prior_session_stopped: raise Denied('Confirm the prior session stopped before releasing ownership')
        with self.core.tx() as c:
            self.expire(c)
            r=self.row(c,ident)
            if r['status']!='REVIEW_REQUIRED' or r['revision']!=revision:
                raise Denied('Inspect the current interrupted session before recovery')
            c.execute('DELETE FROM build_claims WHERE order_id=?',(ident,))
            c.execute("UPDATE build_orders SET status='QUEUED',revision=revision+1,owner=NULL WHERE id=?",(ident,))
            self.log(c,ident,'SESSION_RECOVERED',reviewer=reviewer,evidence=evidence,
                          verification_source='local_operator_attestation',old_session_fenced=True)
            return revision+1

    def inspect(self,ident):
        with self.core.tx() as c:
            self.expire(c)
            result=dict(self.row(c,ident))
            result['chain']=self.verify_chain(c)
            self.verify_reports(c)
            result['records']=[{'kind':r['kind'],'session':r['session'],'report':json.loads(r['payload'])}
                               for r in c.execute('SELECT * FROM build_records WHERE order_id=? ORDER BY id',(ident,))]
            result['events']=[dict(r) for r in c.execute('SELECT at,type,data FROM events WHERE incident=? ORDER BY id',(ident,))]
            result['audit_events']=[json.loads(r[0]) for r in c.execute('SELECT payload FROM build_chain ORDER BY sequence')
                                    if json.loads(r[0])['work_order_id']==ident]
            for record in result['records']:
                fingerprint=hashlib.sha256((record['kind']+json.dumps(record['report'],sort_keys=True)).encode()).hexdigest()
                event=next((e for e in result['audit_events'] if e['event']=='SESSION_'+record['kind']
                            and e['evidence'].get('session')==record['session']
                            and e['evidence'].get('record_hash')==fingerprint),None)
                record['actor']=event.get('actor') if event else None
                record['identity_status']='recorded' if record['actor'] else 'legacy_unattributed'
            result['execution_authorized']=False
            return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default=os.environ.get('CLAWCARE_DB','clawcare.sqlite3'))
    p.add_argument('--player-id',help='Stable local player label; not authentication')
    p.add_argument('--agent-id',default='local-cli',help='Agent producing this operation')
    sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('create');a.add_argument('resource');a.add_argument('objective');a.add_argument('acceptance')
    for name in ('inspect','claim','renew','progress','handoff','review','recover'):
        a=sub.add_parser(name);a.add_argument('id')
        if name!='inspect':a.add_argument('--revision',type=int,required=True)
        if name=='claim':a.add_argument('--owner',required=True)
        if name in ('claim','renew'):a.add_argument('--ttl',type=int,default=1800)
        if name in ('renew','progress','handoff'):a.add_argument('--session',required=True)
        if name in ('progress','handoff'):
            a.add_argument('--request-id',required=True);a.add_argument('--report',required=True)
        if name in ('review','recover'):
            a.add_argument('--reviewer',required=True);a.add_argument('--evidence',required=True)
        if name=='review':a.add_argument('--decision',choices=['accept','reject'],required=True)
        if name=='recover':a.add_argument('--prior-session-stopped',action='store_true')
    args=p.parse_args()
    try:
        h=Handoffs(args.db,args.player_id,args.agent_id)
        if args.command=='create':r=h.create(args.resource,args.objective,args.acceptance)
        elif args.command=='inspect':r=h.inspect(args.id)
        elif args.command=='claim':r=h.claim(args.id,args.owner,args.revision,args.ttl)
        elif args.command=='renew':r=h.renew(args.id,args.session,args.revision,args.ttl)
        elif args.command in ('progress','handoff'):
            path=Path(args.report)
            if path.stat().st_size>65536:raise Denied('Report exceeds 64 KiB')
            r=h.write(args.id,args.session,args.revision,args.request_id,json.loads(path.read_text(encoding='utf-8-sig')),
                      'HANDOFF' if args.command=='handoff' else 'PROGRESS')
        elif args.command=='review':r=h.review(args.id,args.reviewer,args.revision,args.decision=='accept',args.evidence)
        else:r=h.recover(args.id,args.reviewer,args.revision,args.evidence,args.prior_session_stopped)
        print(json.dumps(r,indent=2))
    except (Denied,ValueError,OSError) as e:
        p.exit(2,(str(e) if isinstance(e,Denied) else 'Invalid or inaccessible handoff input')+'\n')

if __name__=='__main__':main()
