"""Semantic state tests with a reviewed-field fake reader; no live process."""
from copy import deepcopy
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import dual_cultivation_adapter as dual
import jade_adapter as jade
import dual_cultivation_ui as ui
from jade_ui import JadePanel
from test_app import FakeVar, FakeWidget
from write_guard import Refused, UncertainWrite


class Fields:
    def __init__(self):
        self.values={};self.offsets={};self.anchors=[];self.panels=[10];self.actionable=True;self.hidden=False
        self.reader=SimpleNamespace(h=1);self._native_registry=dict(registry_links=[1],registry=dict(count=1))
        self.methods=[];self.lists={}
    def registered_panels(self):return 7,self.panels
    def visible_panel(self,p):return None if self.hidden else (self.obj(p),self.actionable)
    def obj(self,p,_=None):return dict(klass=hex(p+0x10000),pointer=p)
    def get(self,p,n):return self.values[(p,n)]
    def pointer_field(self,p,c,n,*_,**kwargs):return self.get(p,n)
    def integer(self,p,c,n,*_,**kwargs):return self.get(p,n)
    def boolean(self,p,c,n):return self.get(p,n)
    def float_field(self,p,c,n,**kwargs):return self.get(p,n)
    def object_list(self,p,*_,**kwargs):return self.lists[p]
    def proof(self):return [dict(address='0x1',size=1,expected_hex='00')]
    def method(self,*args):self.methods.append(args);return '0x999'
    def _field(self,c,n,*_):return self.offsets[(c['pointer'],n)]
    def anchor(self,p,n):return self.memory.get(p,bytes(n))


def fixture(kind):
    rr=Fields();game=SimpleNamespace(blocked=False,stamp=('game',123),resolver=SimpleNamespace(resolve=Mock()))
    a=(dual.DualCultivationAdapter if kind=='dual' else jade.JadeAdapter).__new__(dual.DualCultivationAdapter if kind=='dual' else jade.JadeAdapter)
    a.game,a.resolver,a.blocked=game,rr,False;a.native=Mock()
    def put(p,**kw):rr.values.update({(p,k):v for k,v in kw.items()})
    if kind=='dual':
        put(10,m_Game=20,m_NpcId=100,m_DualCultivateId=200,m_SettlementStarted=False,m_ResultCallbackInvoked=False,m_PendingResultIsWin=False,m_ActionOnGameEnd=51)
        put(20,m_Config=30,m_NpcId=100,m_DualCultivateId=200,m_Phase=1,m_IsPresentationReady=True,m_Completed=50,m_TimeRemaining=20.,m_Resonance=50.)
        rr.values[20,'<Slots>k__BackingField']=40;put(30,RequiredResonance=100,TimeLimitSec=30)
        rr.lists[40]=(41,42,43)
        for s in (41,42,43):put(s,m_Owner=20)
    else:
        put(10,m_ViewModel=20,m_ViewBound=True);put(20,m_SelectedStone=30,m_StoneSelectionVersion=1,m_CanExchange=False)
        put(30,SourceItem=40,SaveRecord=50,ItemId=101,Seed=42,DetailsRestored=True,Exchanged=False,RevealRatio=.25,CurrentValue=70,Template=60,Flesh=61,Blooms=70,Cracks=80)
        rr.values.update({(50,n):v for n,v in {'<SourceItemId>k__BackingField':101,'<Seed>k__BackingField':42,'<GenerationPending>k__BackingField':False,
            '<Exchanged>k__BackingField':False,'<RevealRatio>k__BackingField':.25,'<CurrentValue>k__BackingField':70}.items()})
        rr.offsets.update({(40,'<StoneInstanceId>k__BackingField'):0x38,(50,'<InstanceId>k__BackingField'):0x10,
            (50,'<RevealRatio>k__BackingField'):0x80,(50,'<CurrentValue>k__BackingField'):0x88})
        rr.memory={40+0x38:struct.pack('<q',99),50+0x10:struct.pack('<q',99)}
        for name,o,want in [('m_CanScratch',0x110,True),('m_ExchangeChoiceVisible',0x112,False),('m_ExchangeResultVisible',0x113,False),('m_ScratchSessionActive',0x139,False),('m_ScratchDirty',0x13b,False),('m_HasPendingScratchSettlement',0x13c,False)]:
            put(20,**{name:want});rr.offsets[20,name]=o
        rr.lists[70]=(71,);rr.lists[80]=(81,)
        for p,o in [(71,0x1c),(81,0x2c)]:
            rr.values[p,'<Config>k__BackingField']=p+500;rr.values[p,'<Seen>k__BackingField']=False;rr.offsets[p,'<Seen>k__BackingField']=o
        game.resolver.resolve.return_value=dict(anchor_verified=True,anchors=[],items=[dict(object=40,class_name='Game.Model.Components.GambleStoneBagItem',count=1,count_address=400,item_id=101,uid=1234)])
    return a,rr


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        for m in (dual,jade):
            p=patch.object(m,'process_identity',return_value=('game',123));p.start();self.addCleanup(p.stop)

    def test_dual_active_normal_round(self):
        a,r=fixture('dual');s=a.snapshot();self.assertTrue(s['can_solve']);self.assertEqual(s['npc_id'],100)
        prepared=a.prepare_solve(s);self.assertEqual(prepared['native']['method_info'],'0x999')

    def test_progress_not_part_of_round_key(self):
        a,r=fixture('dual');before=a.snapshot();r.values[20,'m_Resonance']=90.;r.values[20,'m_TimeRemaining']=10.
        after=a.snapshot();self.assertEqual(before['identity'],after['identity']);self.assertEqual(before['native']['round_key'],after['native']['round_key'])

    def test_reused_panel_new_game_has_new_key(self):
        a,r=fixture('dual');before=a.snapshot();r.values[10,'m_Game']=21
        for (p,n),v in list(r.values.items()):
            if p==20:r.values[21,n]=v
        for s in (41,42,43):r.values[s,'m_Owner']=21
        after=a.snapshot();self.assertNotEqual(before['native']['round_key'],after['native']['round_key'])
        with self.assertRaises(Refused):a.prepare_solve(before)

    def test_dual_paused_or_settling_not_actionable(self):
        for p,n,v in [(20,'m_Phase',2),(20,'m_TimeRemaining',0.),(20,'m_IsPresentationReady',False),(20,'m_Completed',0),(10,'m_SettlementStarted',True),(10,'m_ResultCallbackInvoked',True)]:
            a,r=fixture('dual');r.values[p,n]=v;self.assertFalse(a.snapshot()['can_solve'])
        a,r=fixture('dual');r.actionable=False;self.assertFalse(a.snapshot()['can_solve'])

    def test_dual_wrong_slot_owner_or_count_refuses(self):
        a,r=fixture('dual');r.values[41,'m_Owner']=99
        with self.assertRaises(Refused):a.snapshot()
        a,r=fixture('dual');r.lists[40]=(41,42)
        with self.assertRaises(Refused):a.snapshot()

    def test_hidden_and_absent_panels_are_inactive(self):
        for kind in ('dual','jade'):
            a,r=fixture(kind);r.hidden=True;self.assertFalse(a.snapshot()['active'])
            r.hidden=False;r.panels=[];self.assertFalse(a.snapshot()['active'])

    def test_multiple_panels_refused(self):
        for kind in ('dual','jade'):
            a,r=fixture(kind);r.panels=[10,10]
            with self.assertRaises(Refused):a.snapshot()

    def test_process_change_rejected(self):
        a,r=fixture('dual')
        with patch.object(dual,'process_identity',return_value=('game',124)),self.assertRaises(Refused):a.snapshot()

    def test_jade_owned_stone_ready(self):
        a,r=fixture('jade');s=a.snapshot();self.assertTrue(s['can_solve']);self.assertEqual(s['cracks'],1)
        self.assertEqual(a.prepare_solve(s)['native']['method_info'],'0x999')

    def test_jade_same_stone_key_stable_but_stale_progress_refuses(self):
        a,r=fixture('jade');before=a.snapshot();r.values[30,'RevealRatio']=.5;r.values[30,'CurrentValue']=40
        after=a.snapshot();self.assertEqual(before['native']['round_key'],after['native']['round_key'])
        with self.assertRaises(Refused):a.prepare_solve(before)
        r.values[20,'m_StoneSelectionVersion']=2;self.assertEqual(before['native']['round_key'],a.snapshot()['native']['round_key'])

    def test_jade_ownership_and_saved_identity_required(self):
        a,r=fixture('jade');a.game.resolver.resolve.return_value['items']=[]
        with self.assertRaises(Refused):a.snapshot()
        a,r=fixture('jade');r.memory[50+0x10]=struct.pack('<q',101)
        with self.assertRaises(Refused):a.snapshot()

    def test_jade_busy_unready_exchanged_and_complete(self):
        for p,n,v in [(20,'m_ScratchSessionActive',True),(20,'m_ScratchDirty',True),(20,'m_HasPendingScratchSettlement',True),(20,'m_ExchangeChoiceVisible',True),(30,'RevealRatio',1.),(30,'Exchanged',True)]:
            a,r=fixture('jade');r.values[p,n]=v;self.assertFalse(a.snapshot()['can_solve'])
        a,r=fixture('jade');r.values[30,'DetailsRestored']=False
        with self.assertRaises(Refused):a.snapshot()

    def test_native_result_truthful_and_mismatch_is_unknown(self):
        a,r=fixture('dual');s=a.snapshot();ok=dict(native_won=True,settlement_started=True,npc_id=100,config_id=200)
        self.assertFalse(a.verify_native(ok,s)['settlement_verified'])
        for k,v in [('native_won',False),('npc_id',101)]:
            with self.assertRaises(UncertainWrite):a.verify_native(dict(ok,**{k:v}),s)
        a,r=fixture('jade');s=a.snapshot();ok=dict(fully_revealed=True,record_verified=True,instance_id='99',current_value=10)
        self.assertIn('天然裂纹',a.verify_native(ok,s)['message'])
        with self.assertRaises(UncertainWrite):a.verify_native(dict(ok,current_value=True),s)


class MiniUiTests(unittest.TestCase):
    def setUp(self):
        self.p=ui.DualCultivationPanel.__new__(ui.DualCultivationPanel)
        self.p.app=SimpleNamespace(busy=False,adapter=SimpleNamespace(write_enabled=True,blocked=False),work=Mock(),status=FakeVar())
        self.p.adapter=Mock(blocked=False);self.p.state=dict(can_solve=True,active=True,npc_id=1,config_id=2,resonance=3,required=100,remaining=20)
        for n in ('summary','note'):setattr(self.p,n,FakeVar())
        for n in ('button','detect_button'):setattr(self.p,n,FakeWidget())
        p=patch.object(ui,'native_calls_pending',return_value=False);self.pending=p.start();self.addCleanup(p.stop)

    def test_unknown_reaches_global_stop(self):
        self.p.solve();job,_=self.p.app.work.call_args.args;self.p.adapter.solve.side_effect=UncertainWrite('unknown')
        with self.assertRaises(UncertainWrite):job()

    def test_success_clears_one_shot_target(self):
        self.p.solve();job,done=self.p.app.work.call_args.args;self.p.adapter.solve.return_value=dict(message='settling')
        done(job());self.assertIsNone(self.p.state);self.assertEqual(self.p.button.options['state'],'disabled')

    def test_refused_never_claims_completed(self):
        self.p.solve();job,done=self.p.app.work.call_args.args;self.p.adapter.solve.side_effect=Refused('paused')
        done(job());self.assertEqual(self.p.note.get(),'paused');self.assertIsNone(self.p.state)

    def test_busy_pending_inactive_disable(self):
        self.pending.return_value=True;self.p.solve();self.p.update_enabled(True)
        self.assertEqual(self.p.button.options['state'],'disabled');self.p.app.work.assert_not_called()

    def test_descriptions_do_not_claim_pristine_jade(self):
        self.assertIn('天然裂纹',JadePanel.explanation);self.assertIn('不会',JadePanel.explanation)

    def test_readonly_and_disconnected_never_enable_or_dispatch(self):
        self.p.app.adapter.write_enabled=False;self.p.update_enabled(True);self.p.detect();self.p.solve()
        self.assertEqual(self.p.button.options['state'],'disabled');self.p.app.work.assert_not_called()
        self.p.app.adapter=None;self.p.update_enabled(True);self.p.solve();self.p.app.work.assert_not_called()

    def test_failed_refresh_cannot_keep_stale_target(self):
        self.p.detect();self.assertIsNone(self.p.state);self.assertEqual(self.p.button.options['state'],'disabled')
        self.p.solve();self.assertEqual(self.p.app.work.call_count,1)


if __name__=='__main__':unittest.main()
