"""Loopback-only team API prototype. Offline provisioning; no public deployment."""
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time

from handoffs import Handoffs, Denied, summary


class APIError(Exception):
    def __init__(self,status,message):
        self.status=status; self.message=message


class Credentials:
    """Operator-managed token identities. Plaintext tokens are never stored here."""
    def __init__(self,root):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'identities.sqlite3'
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS credentials(
                  digest TEXT PRIMARY KEY, workspace TEXT NOT NULL, player TEXT NOT NULL,
                  agent TEXT NOT NULL, role TEXT NOT NULL, expires REAL NOT NULL,
                  revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS memberships(
                  workspace TEXT NOT NULL, player TEXT NOT NULL, role TEXT NOT NULL,
                  active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(workspace,player));
                CREATE TABLE IF NOT EXISTS projects(
                  workspace TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL,
                  PRIMARY KEY(workspace,id));
                CREATE TABLE IF NOT EXISTS administration_events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, workspace TEXT NOT NULL,
                  player TEXT NOT NULL, agent TEXT NOT NULL, at REAL NOT NULL,
                  action TEXT NOT NULL, payload TEXT NOT NULL);
            ''')
            # Preserve existing credentials as legacy memberships. Ambiguous
            # historical roles are reduced to viewer pending operator review.
            c.execute('''INSERT OR IGNORE INTO memberships(workspace,player,role,active)
                         SELECT workspace,player,CASE WHEN count(DISTINCT role)=1
                         THEN min(role) ELSE 'viewer' END,1 FROM credentials
                         GROUP BY workspace,player''')
            c.execute("INSERT OR IGNORE INTO projects SELECT id,'default','Default project' FROM workspaces")

    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()

    @staticmethod
    def workspace(value):
        if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',value):
            raise ValueError('Workspace must be a lowercase slug of at most 63 characters')
        return value

    def provision(self,workspace,player,agent,role,ttl=3600):
        workspace=self.workspace(workspace)
        player=summary(player,120);agent=summary(agent,120)
        if role not in ('viewer','worker','reviewer','admin','owner'):raise ValueError('Invalid role')
        if type(ttl) is not int or not 1<=ttl<=86400:raise ValueError('TTL must be 1..86400 seconds')
        token=secrets.token_urlsafe(32)
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO workspaces VALUES(?)',(workspace,))
            existing=c.execute('SELECT role,active FROM memberships WHERE workspace=? AND player=?',(workspace,player)).fetchone()
            if existing and (existing['role']!=role or not existing['active']):
                raise ValueError('Change membership explicitly before issuing this credential')
            c.execute('INSERT OR IGNORE INTO memberships VALUES(?,?,?,1)',(workspace,player,role))
            c.execute("INSERT OR IGNORE INTO projects VALUES(?,'default','Default project')",(workspace,))
            c.execute('INSERT INTO credentials VALUES(?,?,?,?,?,?,0)',
                      (digest,workspace,player,agent,role,time.time()+ttl))
            c.execute('INSERT INTO administration_events(workspace,player,agent,at,action,payload) VALUES(?,?,?,?,?,?)',
                      (workspace,'local-operator','offline-provisioner',time.time(),'CREDENTIAL_ISSUED',json.dumps({'player':player,'agent':agent,'role':role})))
        return token

    def revoke_player(self,workspace,player):
        with self.connect() as c:
            c.execute('UPDATE credentials SET revoked=1 WHERE workspace=? AND player=?',(workspace,player))

    def authenticate(self,token,workspace):
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.connect() as c:
            row=c.execute('SELECT * FROM credentials WHERE digest=?',(digest,)).fetchone()
        if not row or row['revoked'] or row['expires']<=time.time():
            raise APIError(401,'Invalid or expired credential')
        if row['workspace']!=workspace:raise APIError(403,'Workspace access denied')
        identity=dict(row)
        with self.connect() as c:
            member=c.execute('SELECT role,active FROM memberships WHERE workspace=? AND player=?',(workspace,row['player'])).fetchone()
        if not member or not member['active']:raise APIError(403,'Inactive membership')
        identity['role']=member['role']
        return identity

    def ledger(self,workspace,project='default'):
        # Never use client-provided paths as storage locations.
        key_input=self.workspace(workspace)
        if project!='default':key_input+=':'+self.workspace(project)
        key=hashlib.sha256(key_input.encode()).hexdigest()
        return self.root/('workspace-'+key+'.sqlite3')

    def administer(self,identity,body):
        operation=body['operation'];workspace=identity['workspace']
        schemas={'workspace_info':set(),'project_create':{'project_id','name'},
                 'member_update':{'player_id','role','active'}}
        if set(body)!=schemas[operation]|{'operation'}:raise APIError(400,'Unexpected or missing fields')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            member=c.execute('SELECT role,active FROM memberships WHERE workspace=? AND player=?',
                             (workspace,identity['player'])).fetchone()
            if not member or not member['active']:raise APIError(403,'Inactive membership')
            if operation=='workspace_info':
                return {'workspace_id':workspace,'player_id':identity['player'],'role':member['role'],
                        'projects':[dict(r) for r in c.execute('SELECT id,name FROM projects WHERE workspace=? ORDER BY id',(workspace,))],
                        'members':[dict(r) for r in c.execute('SELECT player,role,active FROM memberships WHERE workspace=? ORDER BY player',(workspace,))]}
            if member['role'] not in ('admin','owner'):raise APIError(403,'Workspace administrator required')
            if operation=='project_create':
                project=self.workspace(body['project_id']);name=summary(body['name'],120)
                if c.execute('SELECT 1 FROM projects WHERE workspace=? AND id=?',(workspace,project)).fetchone():
                    raise APIError(409,'Project already exists')
                c.execute('INSERT INTO projects VALUES(?,?,?)',(workspace,project,name))
            else:
                player=summary(body['player_id'],120);role=body['role'];active=body['active']
                if role not in ('viewer','worker','reviewer','admin','owner') or type(active) is not bool:
                    raise APIError(400,'Invalid membership')
                old=c.execute('SELECT role,active FROM memberships WHERE workspace=? AND player=?',(workspace,player)).fetchone()
                if member['role']=='admin' and (role in ('admin','owner') or (old and old['role'] in ('admin','owner'))):
                    raise APIError(403,'Only an owner may manage administrators or owners')
                if old and old['role']=='owner' and old['active'] and (role!='owner' or not active):
                    count=c.execute("SELECT count(*) FROM memberships WHERE workspace=? AND role='owner' AND active=1",(workspace,)).fetchone()[0]
                    if count<=1:raise APIError(409,'Cannot remove the last active owner')
                c.execute('INSERT INTO memberships VALUES(?,?,?,?) ON CONFLICT(workspace,player) DO UPDATE SET role=excluded.role,active=excluded.active',
                          (workspace,player,role,int(active)))
                if not active:c.execute('UPDATE credentials SET revoked=1 WHERE workspace=? AND player=?',(workspace,player))
            c.execute('INSERT INTO administration_events(workspace,player,agent,at,action,payload) VALUES(?,?,?,?,?,?)',
                      (workspace,identity['player'],identity['agent'],time.time(),operation,json.dumps(body,sort_keys=True)))
        return {'updated':True,'operation':operation}


class TeamService:
    def __init__(self,root):
        self.credentials=Credentials(root)

    def dispatch(self,identity,body):
        if not isinstance(body,dict):raise APIError(400,'JSON object required')
        operation=body.get('operation')
        if isinstance(operation,str) and operation in ('workspace_info','project_create','member_update'):
            return self.credentials.administer(identity,body)
        project=body.get('project_id','default')
        try:self.credentials.workspace(project)
        except ValueError:raise APIError(400,'Invalid project identifier')
        body={k:v for k,v in body.items() if k!='project_id'}
        fields={
            'create':{'resource','objective','acceptance'},
            'inspect':{'id'},
            'claim':{'id','revision','ttl'},
            'renew':{'id','revision','session','ttl'},
            'progress':{'id','revision','session','request_id','report'},
            'handoff':{'id','revision','session','request_id','report'},
            'review':{'id','revision','accept','evidence'},
            'recover':{'id','revision','evidence','prior_session_stopped'},
        }
        if not isinstance(operation,str) or operation not in fields:
            raise APIError(400,'Unknown operation')
        if set(body)!=fields[operation]|{'operation'}:
            raise APIError(400,'Unexpected or missing fields')
        role=identity['role']
        if role=='viewer' and operation!='inspect':raise APIError(403,'Read-only membership')
        if operation in ('review','recover') and role not in ('reviewer','admin','owner'):raise APIError(403,'Reviewer membership required')
        for key in ('revision','ttl'):
            if key in body and (type(body[key]) is not int or body[key]<0):
                raise APIError(400,'Invalid integer field')
        for key in ('id','session'):
            if key in body and (not isinstance(body[key],str) or len(body[key])>100):
                raise APIError(400,'Invalid identifier')
        for key in ('accept','prior_session_stopped'):
            if key in body and type(body[key]) is not bool:raise APIError(400,'Boolean required')
        with self.credentials.connect() as c:
            if not c.execute('SELECT 1 FROM projects WHERE workspace=? AND id=?',(identity['workspace'],project)).fetchone():
                raise APIError(404,'Unknown project')
        h=Handoffs(self.credentials.ledger(identity['workspace'],project),identity['player'],identity['agent'])
        # Identity is derived only from the credential registry, never request text.
        h.actor={'player_id':identity['player'],'agent_id':identity['agent'],
                 'workspace_id':identity['workspace'],'identity_source':'server_token',
                 'authenticated':True}
        if project!='default':h.actor['project_id']=project
        b=body
        if operation=='create':return {'id':h.create(b['resource'],b['objective'],b['acceptance'])}
        if operation=='inspect':return h.inspect(b['id'])
        if operation=='claim':return h.claim(b['id'],identity['player'],b['revision'],b['ttl'])
        if operation=='renew':return {'revision':h.renew(b['id'],b['session'],b['revision'],b['ttl'])}
        if operation in ('progress','handoff'):
            return h.write(b['id'],b['session'],b['revision'],b['request_id'],b['report'],operation.upper())
        if operation=='review':return h.review(b['id'],identity['player'],b['revision'],b['accept'],b['evidence'])
        return {'revision':h.recover(b['id'],identity['player'],b['revision'],b['evidence'],b['prior_session_stopped'])}


def strict_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate JSON key')
        result[key]=value
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass  # Never log authorization headers or report bodies.

    def setup(self):
        super().setup();self.connection.settimeout(10)

    def reply(self,status,payload):
        data=json.dumps(payload,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers();self.wfile.write(data)

    def do_POST(self):
        try:
            if self.headers.get('Origin'):raise APIError(403,'Browser origins are not enabled')
            expected=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=expected:raise APIError(403,'Invalid host')
            match=re.fullmatch(r'/v1/workspaces/([a-z0-9][a-z0-9-]{0,62})/commands',self.path)
            if not match:raise APIError(404,'Unknown endpoint')
            headers=self.headers.get_all('Authorization',[])
            if len(headers)!=1 or not re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}',headers[0]):
                raise APIError(401,'Bearer credential required')
            identity=self.server.service.credentials.authenticate(headers[0][7:],match[1])
            lengths=self.headers.get_all('Content-Length',[])
            if self.headers.get('Transfer-Encoding') or len(lengths)!=1:
                raise APIError(400,'A single content length is required')
            size=int(lengths[0])
            if not 0<size<=65536:raise APIError(413,'Request exceeds bounds')
            if self.headers.get_content_type()!='application/json':raise APIError(415,'JSON required')
            raw=self.rfile.read(size)
            if len(raw)!=size:raise APIError(400,'Incomplete request')
            body=json.loads(raw,object_pairs_hook=strict_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            result=self.server.service.dispatch(identity,body)
            self.reply(200,result)
        except APIError as e:self.reply(e.status,{'error':e.message})
        except Denied as e:self.reply(409,{'error':str(e)})
        except (ValueError,TypeError,UnicodeError):self.reply(400,{'error':'Invalid request'})
        except sqlite3.OperationalError:self.reply(503,{'error':'Storage busy or unavailable; inspect state before retrying'})
        except (ConnectionError,TimeoutError):self.close_connection=True
        except Exception:self.reply(500,{'error':'Internal failure; inspect state before retrying'})


class Server(ThreadingHTTPServer):
    daemon_threads=True
    request_queue_size=256

    def __init__(self,service,port=0):
        self.service=service
        self.slots=threading.BoundedSemaphore(128)
        super().__init__(('127.0.0.1',port),Handler)

    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request);return
        try:super().process_request(request,client_address)
        except Exception:
            self.slots.release();raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,help='Private service data directory')
    sub=p.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765)
    issue=sub.add_parser('issue')
    for field in ('workspace','player','agent','role','token-file'):issue.add_argument('--'+field,required=True)
    issue.add_argument('--ttl',type=int,default=3600)
    revoke=sub.add_parser('revoke');revoke.add_argument('--workspace',required=True);revoke.add_argument('--player',required=True)
    args=p.parse_args();service=TeamService(args.root)
    if args.command=='issue':
        # Exclusive creation prevents overwriting a credential or arbitrary file.
        with Path(args.token_file).open('x',encoding='utf-8') as f:
            token=service.credentials.provision(args.workspace,args.player,args.agent,args.role,args.ttl)
            f.write(token)
        print('Credential written to the specified private file. No token printed.')
    elif args.command=='revoke':
        service.credentials.revoke_player(args.workspace,args.player);print('Player credentials revoked.')
    else:
        server=Server(service,args.port)
        print(f'Local prototype listening on 127.0.0.1:{server.server_port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()


if __name__=='__main__':main()
