from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from team_api import TeamService, Server


def report():
    return dict(completed=['Synthetic fixture checked'],remaining=[],blockers=[],
                verification=['Readback matched fixture'],checkpoint_refs=[],
                recovery_notes=['No external changes'],next_work_order=None)


class TeamAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.service=TeamService(self.tmp.name)
        self.server=Server(self.service)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.worker=self.issue('alice')
        self.reviewer=self.issue('bob','reviewer')
        self.viewer=self.issue('viewer','viewer')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.tmp.cleanup()

    def issue(self,player,role='worker',workspace='demo'):
        return self.service.credentials.provision(workspace,player,'test-agent',role)

    def call(self,token,body,workspace='demo',headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=60)
        try:
            hs={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
            hs.update(headers or {})
            connection.request('POST',f'/v1/workspaces/{workspace}/commands',json.dumps(body),hs)
            r=connection.getresponse();return r.status,json.loads(r.read())
        finally:connection.close()

    def create(self,resource='fixture'):
        status,r=self.call(self.worker,dict(operation='create',resource=resource,objective='Inspect fixture',acceptance='Readback matches'))
        self.assertEqual(status,200,r);return r['id']

    def test_auth_roles_isolation_and_forged_actor(self):
        ident=self.create()
        inspect=dict(operation='inspect',id=ident)
        self.assertEqual(self.call('x'*43,inspect)[0],401)
        self.assertEqual(self.call(self.worker,inspect,'other')[0],403)
        other=self.issue('alice',workspace='other')
        self.assertEqual(self.call(other,inspect,'other')[0],409)
        self.assertEqual(self.call(self.viewer,inspect)[0],200)
        claim=dict(operation='claim',id=ident,revision=0,ttl=1800)
        self.assertEqual(self.call(self.viewer,claim)[0],403)
        self.assertEqual(self.call(self.worker,{**claim,'player_id':'bob'})[0],400)
        self.assertEqual(self.call(self.worker,claim,headers={'Origin':'https://example.invalid'})[0],403)
        self.assertEqual(self.call(self.worker,claim,headers={'Host':'attacker.invalid'})[0],403)
        self.assertEqual(self.call(self.worker,dict(operation='review',id=ident,revision=0,accept=True,evidence='Checked'))[0],403)

    def test_authenticated_handoff_and_persistent_revocation(self):
        ident=self.create()
        status,claim=self.call(self.worker,dict(operation='claim',id=ident,revision=0,ttl=1800))
        self.assertEqual(status,200)
        body=dict(operation='handoff',id=ident,revision=1,session=claim['session'],request_id='handoff-1',report=report())
        self.assertEqual(self.call(self.reviewer,body)[0],409)
        self.assertEqual(self.call(self.worker,body)[0],200)
        self.assertTrue(self.call(self.worker,body)[1]['duplicate'])
        self.assertEqual(self.call(self.reviewer,dict(operation='review',id=ident,revision=2,accept=True,evidence='Fixture checked'))[0],200)
        status,r=self.call(self.viewer,dict(operation='inspect',id=ident))
        self.assertEqual(status,200)
        self.assertEqual(r['records'][0]['actor']['player_id'],'alice')
        self.assertTrue(r['records'][0]['actor']['authenticated'])
        self.assertEqual(r['audit_events'][-1]['actor']['player_id'],'bob')
        self.service.credentials.revoke_player('demo','alice')
        self.server.service=TeamService(self.tmp.name)
        self.assertEqual(self.call(self.worker,dict(operation='inspect',id=ident))[0],401)
        self.assertEqual(self.call(self.viewer,dict(operation='inspect',id=ident))[0],200)

    def test_expired_token_and_strict_types(self):
        ident=self.create()
        self.assertEqual(self.call(self.worker,dict(operation='claim',id=ident,revision=False,ttl=1))[0],400)
        with self.service.credentials.connect() as c:c.execute("UPDATE credentials SET expires=0 WHERE player='alice'")
        self.assertEqual(self.call(self.worker,dict(operation='inspect',id=ident))[0],401)

    def test_membership_roles_last_owner_and_live_downgrade(self):
        owner=self.issue('owner','owner');admin=self.issue('admin','admin')
        info=self.call(owner,{'operation':'workspace_info'})
        self.assertEqual(info[0],200)
        update=dict(operation='member_update',player_id='owner',role='viewer',active=True)
        self.assertEqual(self.call(owner,update)[0],409)
        self.assertEqual(self.call(admin,update)[0],403)
        update=dict(operation='member_update',player_id='alice',role='viewer',active=True)
        self.assertEqual(self.call(self.worker,update)[0],403)
        self.assertEqual(self.call(admin,update)[0],200)
        self.assertEqual(self.call(self.worker,dict(operation='create',resource='blocked',objective='Task',acceptance='Check'))[0],403)
        update['active']=False
        self.assertEqual(self.call(admin,update)[0],200)
        self.assertEqual(self.call(self.worker,{'operation':'workspace_info'})[0],401)
        with self.service.credentials.connect() as c:
            event=c.execute("SELECT player,action FROM administration_events WHERE action='member_update' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(event['player'],'admin')

    def test_project_isolation_and_admin_creation(self):
        owner=self.issue('owner','owner')
        create=dict(operation='project_create',project_id='project-b',name='Synthetic project B')
        self.assertEqual(self.call(self.worker,create)[0],403)
        self.assertEqual(self.call(owner,create)[0],200)
        self.assertEqual(self.call(owner,create)[0],409)
        ident=self.create()
        status,r=self.call(self.worker,dict(operation='create',project_id='project-b',resource='fixture',objective='Task',acceptance='Check'))
        self.assertEqual(status,200)
        self.assertEqual(self.call(self.viewer,dict(operation='inspect',project_id='project-b',id=ident))[0],409)
        self.assertEqual(self.call(self.viewer,dict(operation='inspect',id=r['id']))[0],409)
        status,record=self.call(self.viewer,dict(operation='inspect',project_id='project-b',id=r['id']))
        self.assertEqual(status,200)
        self.assertEqual(record['audit_events'][0]['actor']['project_id'],'project-b')
        self.assertEqual(self.call(self.worker,{**create,'project_id':'../escape'})[0],403)

    def test_100_clients_different_resources_and_same_resource(self):
        tokens=[self.issue(f'player-{i:03}') for i in range(100)]
        orders=[self.create(f'fixture-{i:03}') for i in range(100)]
        barrier=threading.Barrier(100)
        def distinct(i):
            barrier.wait(timeout=30)
            start=time.monotonic()
            status,result=self.call(tokens[i],dict(operation='claim',id=orders[i],revision=0,ttl=1800))
            return status,result,time.monotonic()-start
        start=time.monotonic()
        with ThreadPoolExecutor(max_workers=100) as pool:results=list(pool.map(distinct,range(100)))
        elapsed=time.monotonic()-start
        self.assertEqual([r[0] for r in results],[200]*100)
        self.assertEqual(len({r[1]['session'] for r in results}),100)
        barrier=threading.Barrier(100)
        def write_progress(i):
            barrier.wait(timeout=30)
            payload=report();payload.pop('next_work_order')
            return self.call(tokens[i],dict(operation='progress',id=orders[i],revision=1,
                             session=results[i][1]['session'],request_id='progress-1',report=payload))[0]
        with ThreadPoolExecutor(max_workers=100) as pool:written=list(pool.map(write_progress,range(100)))
        self.assertEqual(written,[200]*100)
        # A second simultaneous wave tests a single contested resource.
        contested=self.create('shared-fixture');barrier=threading.Barrier(100)
        def compete(i):
            barrier.wait(timeout=30)
            return self.call(tokens[i],dict(operation='claim',id=contested,revision=0,ttl=1800))[0]
        with ThreadPoolExecutor(max_workers=100) as pool:statuses=list(pool.map(compete,range(100)))
        self.assertEqual(statuses.count(200),1)
        self.assertEqual(statuses.count(409),99)
        # Inspect every authored claim using a separate read-only identity.
        for i,ident in enumerate(orders):
            status,r=self.call(self.viewer,dict(operation='inspect',id=ident))
            self.assertEqual(status,200)
            self.assertEqual(r['audit_events'][-1]['actor']['player_id'],f'player-{i:03}')
            self.assertEqual(r['records'][0]['actor']['player_id'],f'player-{i:03}')
        print(json.dumps({'test':'100_clients','distinct_successes':100,'elapsed_seconds':round(elapsed,3),
                          'max_request_seconds':round(max(r[2] for r in results),3),
                          'progress_records':100,'contested_winners':1,'contested_conflicts':99}),flush=True)


if __name__=='__main__':unittest.main()
