import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from handoffs import Handoffs, Denied


def report(handoff=False):
    r=dict(completed=['Synthetic fixture updated'],remaining=[],blockers=[],
           verification=['Fixture read back'],checkpoint_refs=['fixture-checkpoint'],
           recovery_notes=['Restore the synthetic fixture snapshot'])
    if handoff:r['next_work_order']={'objective':'Check second fixture','acceptance':'Readback matches expected state'}
    return r


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.sqlite3'
        self.h=Handoffs(self.db)
        self.id=self.h.create('demo-account','Update fixture','Readback succeeds')

    def tearDown(self):self.tmp.cleanup()

    def test_two_operator_handoff_and_single_successor(self):
        claim=self.h.claim(self.id,'Operator A',0)
        self.h.write(self.id,claim['session'],1,'progress-1',report())
        self.h.write(self.id,claim['session'],2,'handoff-1',report(True),'HANDOFF')
        other=self.h.create('demo-account','Other task','Verified')
        with self.assertRaises(Denied):self.h.claim(other,'Operator B',0)
        result=self.h.review(self.id,'Operator B',3,True,'Independently checked fixture')
        with self.assertRaises(Denied):self.h.review(self.id,'Operator B',3,True,'Retry')
        next_claim=self.h.claim(result['next_work_order'],'Operator B',0)
        self.assertFalse(next_claim['execution_authorized'])
        with self.assertRaises(Denied):self.h.write(self.id,claim['session'],4,'late',report())
        self.assertEqual(self.h.inspect(self.id)['status'],'COMPLETED')

    def test_idempotency_and_revision(self):
        s=self.h.claim(self.id,'Operator A',0)['session']
        self.h.write(self.id,s,1,'same',report())
        self.assertTrue(self.h.write(self.id,s,1,'same',report())['duplicate'])
        changed=report();changed['completed']=['Different']
        with self.assertRaises(Denied):self.h.write(self.id,s,2,'same',changed)
        with self.assertRaises(Denied):self.h.write(self.id,s,1,'new',report())
        self.assertEqual(len(self.h.inspect(self.id)['records']),1)

    def test_expiry_persists_and_requires_reconciliation(self):
        s=self.h.claim(self.id,'Operator A',0)['session']
        with self.h.core.tx() as c:c.execute('UPDATE build_orders SET expires=0 WHERE id=?',(self.id,))
        with self.assertRaises(Denied):self.h.write(self.id,s,1,'late',report())
        h=Handoffs(self.db)
        with h.core.tx() as c:self.assertEqual(h.row(c,self.id)['status'],'REVIEW_REQUIRED')
        with self.assertRaises(Denied):h.recover(self.id,'Operator B',2,'Inspected')
        h.recover(self.id,'Operator B',2,'Prior session stopped and fixture inspected',True)
        new=h.claim(self.id,'Operator B',3)
        self.assertNotEqual(s,new['session'])
        with self.assertRaises(Denied):h.renew(self.id,s,4)

    def test_blocked_handoff_cannot_complete(self):
        s=self.h.claim(self.id,'Operator A',0)['session']
        r=report(True);r['blockers']=['Missing fixture']
        self.h.write(self.id,s,1,'handoff',r,'HANDOFF')
        with self.assertRaises(Denied):self.h.review(self.id,'Operator B',2,True,'Checked')
        self.assertEqual(self.h.review(self.id,'Operator B',2,False,'Continue original work')['status'],'QUEUED')

    def test_schema_and_credentials_rejected(self):
        s=self.h.claim(self.id,'Operator A',0)['session']
        r=report();r['unexpected']='misaligned column'
        with self.assertRaises(Denied):self.h.write(self.id,s,1,'bad',r)
        r=report();r['completed']=['api_key=FAKE_TEST_SENTINEL']
        with self.assertRaises(Denied):self.h.write(self.id,s,1,'bad',r)
        self.assertEqual(self.h.inspect(self.id)['records'],[])

    def test_chain_tamper_blocks_mutation(self):
        with self.h.core.tx() as c:c.execute("UPDATE build_chain SET payload='{}' WHERE sequence=1")
        with self.assertRaises(Denied):self.h.claim(self.id,'Operator A',0)
        with self.assertRaises(Denied):self.h.create('other','Task','Checked')
        with self.h.core.tx() as c:self.assertEqual(c.execute('SELECT count(*) FROM build_orders').fetchone()[0],1)

    def test_concurrent_process_claims(self):
        args=[sys.executable,str(ROOT/'handoffs.py'),'--db',str(self.db),'claim',self.id,'--revision','0','--owner','Operator']
        processes=[subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
        results=[(p.communicate(timeout=30),p.returncode) for p in processes]
        self.assertEqual(sorted(r[1] for r in results),[0,2])

    def test_player_and_agent_attribution_survives_handoff(self):
        a=Handoffs(self.db,'player-a','assistant-a')
        b=Handoffs(self.db,'player-b','assistant-b')
        s=a.claim(self.id,'Display A',0)['session']
        a.write(self.id,s,1,'report',report(True),'HANDOFF')
        b.review(self.id,'Display B',2,True,'Fixture independently verified')
        result=b.inspect(self.id)
        self.assertEqual(result['records'][0]['actor']['player_id'],'player-a')
        self.assertEqual(result['records'][0]['actor']['agent_id'],'assistant-a')
        review=[e for e in result['audit_events'] if e['event']=='HANDOFF_REVIEWED'][0]
        self.assertEqual(review['actor']['player_id'],'player-b')
        self.assertFalse(review['actor']['authenticated'])
        self.assertTrue(a.write(self.id,s,1,'report',report(True),'HANDOFF')['duplicate'])
        with self.assertRaises(Denied):b.write(self.id,s,1,'report',report(True),'HANDOFF')

    def test_different_player_or_agent_cannot_write_bound_session(self):
        a=Handoffs(self.db,'player-a','assistant-a')
        s=a.claim(self.id,'A',0)['session']
        for player,agent in [('player-b','assistant-a'),('player-a','assistant-b')]:
            other=Handoffs(self.db,player,agent)
            with self.assertRaises(Denied):other.write(self.id,s,1,'attempt',report())
            with self.assertRaises(Denied):other.renew(self.id,s,1)
        self.assertEqual(a.inspect(self.id)['records'],[])

    def test_expiry_is_attributed_to_system_not_observer(self):
        a=Handoffs(self.db,'player-a','assistant-a')
        s=a.claim(self.id,'A',0)['session']
        with a.core.tx() as c:c.execute('UPDATE build_orders SET expires=0 WHERE id=?',(self.id,))
        observed=Handoffs(self.db,'player-b','assistant-b').inspect(self.id)
        event=observed['audit_events'][-1]
        self.assertEqual(event['event'],'SESSION_EXPIRED')
        self.assertIsNone(event['actor']['player_id'])
        self.assertEqual(event['actor']['identity_source'],'system')
        self.assertEqual(event['evidence']['session'],s)

if __name__=='__main__':unittest.main()
