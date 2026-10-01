"""Persuasion semantic fixtures; no process reader or native backend is opened."""
from copy import deepcopy
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import persuasion_adapter as pa
from write_guard import Refused, UncertainWrite


class Fields:
    def __init__(self):
        self.values = {}
        self.anchors = []
        self.reader = SimpleNamespace(h=1)
        self.panels = [0x1000]
        self.actionable = True
        self.hidden = False
        self._native_registry = dict(registry_links=[dict(address="0x100", expected="0x200")], registry=dict(count=1))
        self.flow_state = dict(closure="0x7000", command="0x7100", context="0x7200", activation_id=3,
                              sub_id=7, notified=False, ended=False, cancelled=False,
                              callbacks={k: dict(address=hex(0x8000 + i*0x100)) for i, k in enumerate(("alive", "win", "lose", "close"))})
        self.config = dict(threshold=30, max_rounds=6, exit_delay_ms=10000)
        self.absorbed = []
        self.membership_error = None
    def registered_panels(self): return 0x500, self.panels
    def visible_panel(self, p): return None if self.hidden else (self.obj(p), self.actionable)
    def obj(self, p, _=None):
        if not p: raise Refused("missing object")
        return dict(klass=hex(p+0x100000), pointer=p)
    def value(self, p, n): return self.values[p, n]
    def pointer_field(self, p, c, n, *_, **kw): return self.value(p, n)
    def number(self, p, c, n, *_, **kw): return self.value(p, n)
    def flag(self, p, c, n, *_): return self.value(p, n)
    def q(self, p, **_): return 123
    def flow(self, *args): return deepcopy(self.flow_state)
    def configuration(self, *args): return deepcopy(self.config)
    def absorb(self, anchors): self.absorbed.extend(anchors)
    def npc_membership(self, *args):
        if self.membership_error: raise self.membership_error
        return dict(npc="0x2000")
    def event_subscription(self, *args): return [dict(target="0x1000")]
    def proof(self): return [dict(address="0x1234", size=4, expected_hex="01000000")]
    def method(self, *args): return "0x9000"


def fixture():
    rr = Fields()
    values = {
        0x1000: {"_subscribedNpc":0x2000, "_npcId":1001, "_topicId":2001,
                 "_persuadeEnded":False, "_persuadeResultNotified":False, "_userInitiatedClose":False,
                 "_settlementDelayCts":0, "_peekLoadingCo":0, "_settlementIsWin":False,
                 "_peekRequestToken":7, "DialogueInput":0x3000},
        0x2000: {"<NpcCfgId>k__BackingField":1001, "<PersuadeSessionId>k__BackingField":4,
                 "<IsProcessingChatMessage>k__BackingField":False,"<IsSummarizingChatHistory>k__BackingField":False,
                 "IsProcessingPersuadeMessage":False, "<LastPersuadeEndReason>k__BackingField":0,
                 "<CurrentPersuadeTopicId>k__BackingField":2001, "<PersuadeRound>k__BackingField":1,
                 "<PersuadeEmotionValue>k__BackingField":10, "_persuadeProcessingToken":6,
                 "<GameWorld>k__BackingField":0x4000, "OnPersuadeEnded":0x6000,
                 "<PersuadeChatMessages>k__BackingField":0x6100, "_persuadeLedger":0x6200},
        0x3000: {"m_CanSubmit":True, "m_SubmitAvailable":False},
    }
    rr.values = {(p, n): v for p, fields in values.items() for n, v in fields.items()}
    raw = dict(anchor_verified=True, process_creation_filetime=123, world=0x4000, player=0x5000,
               anchors=[dict(address=0x900+8*i, size=8, expected_hex="0010000000000000",label=label)
                        for i,label in enumerate(pa.ROOT_LABELS)])
    game = SimpleNamespace(stamp=("game", 123), blocked=False, resolver=SimpleNamespace(resolve=Mock(return_value=raw)))
    adapter = pa.PersuasionAdapter.__new__(pa.PersuasionAdapter)
    adapter.game, adapter.resolver, adapter.blocked, adapter.native = game, rr, False, Mock()
    return adapter, rr


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(pa, "process_identity", return_value=("game", 123)),
                  patch.object(pa, "require_safe_persuasion_context", return_value=dict(identity={"space_handler": 0x8800}, anchors=[dict(address=0x910,size=1,expected_hex="00")]))):
            p.start(); self.addCleanup(p.stop)

    def test_idle_empty_input_has_valid_config_and_current_scope(self):
        a, rr = fixture(); state = a.snapshot()
        self.assertTrue(state["can_solve"])
        self.assertEqual((state["npc_id"], state["topic_id"], state["threshold"], state["max_rounds"]), (1001,2001,30,6))
        self.assertEqual(len(rr.absorbed), 13)
        self.assertEqual(len(state["native"]["post_stable_anchors"]),12)
        self.assertEqual(a.prepare_solve(state)["native"]["method_info"], "0x9000")

    def test_busy_processing_peek_and_input_are_independently_disabled(self):
        for p, field, value in ((0x2000,"IsProcessingPersuadeMessage",True),
                                (0x2000,"<IsProcessingChatMessage>k__BackingField",True),
                                (0x2000,"<IsSummarizingChatHistory>k__BackingField",True),
                                (0x1000,"_peekLoadingCo",0x8888), (0x3000,"m_CanSubmit",False)):
            a, rr = fixture(); rr.values[p,field]=value
            state=a.snapshot(); self.assertFalse(state["can_solve"]); self.assertIn("等待",state["reason"])
            with self.assertRaises(Refused): a.prepare_solve(state)
            a.native.solve.assert_not_called()

    def test_ended_notified_user_close_and_countdown_block(self):
        for field, value in (("_persuadeEnded",True),("_persuadeResultNotified",True),("_userInitiatedClose",True),("_settlementDelayCts",0x100)):
            a, rr=fixture(); rr.values[0x1000,field]=value
            self.assertFalse(a.snapshot()["can_solve"])

    def test_paused_cancelled_notified_and_finished_flow_block(self):
        a, rr=fixture(); rr.actionable=False; self.assertFalse(a.snapshot()["can_solve"])
        for key in ("notified","ended","cancelled"):
            a, rr=fixture(); rr.flow_state[key]=True; self.assertFalse(a.snapshot()["can_solve"])

    def test_hidden_uninitialized_and_multiple_panels(self):
        a, rr=fixture(); rr.hidden=True; self.assertFalse(a.snapshot()["active"])
        rr.hidden=False; rr.panels=[]; self.assertFalse(a.snapshot()["active"])
        rr.panels=[0x1000,0x1000]
        with self.assertRaises(Refused): a.snapshot()
        a,rr=fixture();rr.values[0x1000,"_subscribedNpc"]=0
        self.assertFalse(a.snapshot()["can_solve"])

    def test_wrong_npc_owner_and_missing_canonical_member_refuse(self):
        for key, value in (("<NpcCfgId>k__BackingField",1002),("<GameWorld>k__BackingField",0x4001)):
            a,rr=fixture();rr.values[0x2000,key]=value
            with self.assertRaises(Refused):a.snapshot()
        a,rr=fixture();rr.membership_error=Refused("not member")
        with self.assertRaises(Refused):a.snapshot()

    def test_scene_and_process_changes_never_create_target(self):
        a,rr=fixture()
        with patch.object(pa,"require_safe_persuasion_context",side_effect=pa.AcquisitionContextRefused("battle")):
            self.assertFalse(a.snapshot()["can_solve"])
        with patch.object(pa,"process_identity",return_value=("game",124)),self.assertRaises(Refused):a.snapshot()

    def test_changed_safe_scene_rejects_previously_shown_target(self):
        a, rr = fixture()
        old = a.snapshot()
        with patch.object(pa, "require_safe_persuasion_context", return_value=dict(
                identity={"space_handler": 0x9900}, anchors=[])):
            with self.assertRaises(Refused):
                a.prepare_solve(old)
        a.native.solve.assert_not_called()

    def test_stale_session_flow_npc_and_topic_refuse(self):
        for mode in ("session", "flow", "topic"):
            a,rr=fixture();old=a.snapshot()
            if mode=="session":rr.values[0x2000,"<PersuadeSessionId>k__BackingField"]=5
            elif mode=="flow":rr.flow_state["activation_id"]=4
            else:
                rr.values[0x1000,"_topicId"]=2002;rr.values[0x2000,"<CurrentPersuadeTopicId>k__BackingField"]=2002
            with self.assertRaises(Refused):a.prepare_solve(old)

    def test_normal_progress_can_refresh_without_changing_session_claim(self):
        a,rr=fixture();old=a.snapshot()
        rr.values[0x2000,"<PersuadeEmotionValue>k__BackingField"]=20
        rr.values[0x2000,"<PersuadeRound>k__BackingField"]=2
        rr.values[0x2000,"_persuadeProcessingToken"]=8
        new=a.prepare_solve(old)
        self.assertEqual(old["native"]["round_key"],new["native"]["round_key"])
        self.assertEqual(new["progress"],20)

    def test_invalid_round_refused_and_topic_end_not_actionable(self):
        a,rr=fixture();rr.values[0x2000,"<PersuadeRound>k__BackingField"]=7
        with self.assertRaises(Refused):a.snapshot()
        for field, value in (("<LastPersuadeEndReason>k__BackingField",1),("<CurrentPersuadeTopicId>k__BackingField",0)):
            a,rr=fixture();rr.values[0x2000,field]=value;self.assertFalse(a.snapshot()["can_solve"])

    def test_result_is_countdown_only_and_unknown_blocks_adapter(self):
        a,rr=fixture();state=a.snapshot()
        result=dict(npc_id=1001,topic_id=2001,session_id=4,end_reason=1,current_topic_id=0,
                    native_won=True,normal_countdown=True,panel_ended=True,settlement_is_win=True)
        self.assertFalse(a.verify_native(result,state)["settlement_verified"])
        for key,value in (("session_id",5),("end_reason",True),("panel_ended",False),("normal_countdown",False)):
            with self.assertRaises(UncertainWrite):a.verify_native(dict(result,**{key:value}),state)
        a.native.solve.side_effect=UncertainWrite("lost")
        with self.assertRaises(UncertainWrite):a.solve(state)
        self.assertTrue(a.blocked)


class ActualSceneIntegrationTests(unittest.TestCase):
    def test_active_snapshot_uses_real_npc_scene_guard_and_keeps_proof(self):
        import acquisition_context as ac
        from test_persuasion_context import PersuasionFixture
        fx = PersuasionFixture()
        fx.memory.number(fx.handler + 0x38, 0x2000)
        a, rr = fixture()
        fx.resolver.resolve = a.game.resolver.resolve
        a.game.resolver = fx.resolver
        with patch.object(pa, "process_identity", return_value=a.game.stamp), patch.object(
                ac.probe, "inspect_class", side_effect=lambda reader, klass: fx.classes.get(klass)):
            first = a.snapshot()
            self.assertTrue(first["can_solve"])
            self.assertEqual(first["reason"], "")
            self.assertTrue(any(x["address"] == fx.handler + 0x38 for x in rr.absorbed))
            self.assertEqual(a.prepare_solve(first)["identity"], first["identity"])
            fx.memory.number(fx.handler + 0x38, 0x3000)
            self.assertFalse(a.snapshot()["can_solve"])
            with self.assertRaises(Refused):
                a.prepare_solve(first)
        a.native.solve.assert_not_called()


class ResolverGuardTests(unittest.TestCase):
    def test_real_constructor_supports_shared_concurrent_class_inspector(self):
        from learning_adapter import LearningResolver
        name = "System.Collections.Concurrent.ConcurrentDictionary`2"
        spec = pa.SPECS[name]
        klass = 0x2000
        c = dict(klass=hex(klass), namespace=name.rsplit(".", 1)[0], name=name.rsplit(".", 1)[1],
                 fields=[dict(name=f["name"], token=hex(f["token"])) for f in spec["fields"]])
        # Stub only process setup and the raw class inspector. The actual
        # Persuasion constructor, shared delegation and metadata guard all run.
        def setup(rr, reader, **kwargs):
            rr.reader, rr.meta, rr.anchors = reader, 0x100000, []
        with patch.object(LearningResolver, "__init__", setup), \
                patch.object(LearningResolver, "info", return_value=c) as inspect:
            rr = pa.PersuasionResolver(object())
            rr.q = Mock(return_value=rr.meta + spec["type_definition_offset"])
            rr.i = Mock(return_value=spec["token"])
            self.assertIs(rr.info(klass, name), c)
            self.assertIs(rr.info(klass, name), c)
            self.assertEqual(inspect.call_count, 1)
            with self.assertRaises(Refused):
                rr.info(klass, ".Node")

    def test_refresh_discards_cached_classes_with_previous_proof(self):
        a, rr = fixture()
        rr.panels = []
        rr._class_cache = {0x2000: {"name": "stale"}}
        rr.anchors = [(0x2080, "00")]
        with patch.object(pa, "process_identity", return_value=a.game.stamp):
            a.snapshot()
            self.assertEqual(rr._class_cache, {})
            self.assertEqual(rr.anchors, [])

    def test_large_arrays_keep_full_proof_in_bounded_chunks(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
        raw=bytes(range(256))*35;rr.exact=Mock(return_value=raw);rr.anchors=[]
        self.assertEqual(rr.anchor(0x1000,len(raw)),raw)
        self.assertEqual([len(h)//2 for _,h in rr.anchors],[4096,4096,768])
        self.assertEqual([a for a,_ in rr.anchors],[0x1000,0x2000,0x3000])
        self.assertEqual(b"".join(bytes.fromhex(h) for _,h in rr.anchors),raw)

    def test_post_root_proof_excludes_mutable_inventory_but_requires_every_owner_link(self):
        a,_=fixture();raw=a.game.resolver.resolve()
        raw["anchors"].append(dict(address=0xFFF,size=4,expected_hex="01000000",label="Items._size"))
        proof=pa.stable_roots(raw)
        self.assertEqual(len(proof),12)
        self.assertTrue(all(x["address"].startswith("0x") for x in proof))
        self.assertNotIn("Items._size",[x["label"] for x in proof])
        raw["anchors"].pop(0)
        with self.assertRaises(Refused):pa.stable_roots(raw)

    def test_offsets_and_boolean_bytes_checked_before_use(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
        rr.reviewed_field=Mock(return_value=0x21);rr.anchor=Mock(return_value=b"\0")
        with self.assertRaises(Refused):rr.flag(0x100,{},"busy",0x20)
        rr.anchor.assert_not_called()
        rr.reviewed_field.return_value=0x20;rr.anchor.return_value=b"\x02"
        with self.assertRaises(Refused):rr.flag(0x100,{},"busy",0x20)

    def test_absorbed_owner_proofs_are_rechecked_not_trusted(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver);rr.anchor=Mock(return_value=b"\1")
        with self.assertRaises(Refused):rr.absorb([dict(address="0x100",size=1,expected_hex="00")])
        rr.anchor.assert_called_once_with(0x100,1)

    def test_offline_spec_exact_callback_and_native_success_signature(self):
        self.assertEqual(pa.METHOD["params"],[2,0x11])
        self.assertEqual(pa.METHOD["rva"],0xE1BEF0)
        self.assertEqual(pa.METHODS["alive"]["rva"],0x19C91E0)
        self.assertFalse(pa.DATA["fast_settlement"])
        self.assertEqual(pa.SPECS["Game.Model.NpcModel"]["field_count"],104)

    def test_canonical_concurrent_membership_matches_object_not_config_id_key(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
        rr.obj=Mock(return_value={});rr.pointer_field=Mock(return_value=0x400)
        descriptor=dict(kind="concurrent",items=[dict(key="uuid-1",node="0x500",value="0x2000")])
        with patch.object(pa,"read_concurrent",return_value=({"uuid-1":0x2000},descriptor)) as read:
            result=rr.npc_membership(0x100,0x2000,1001)
        self.assertEqual(result["uuid"],"uuid-1");self.assertEqual(result["node"],"0x500")
        read.assert_called_once_with(rr,0x400,"npc")
        for mapping in ({"uuid-1":0x2001},{"uuid-1":0x2000,"uuid-2":0x2000}):
            with patch.object(pa,"read_concurrent",return_value=(mapping,descriptor)),self.assertRaises(Refused):
                rr.npc_membership(0x100,0x2000,1001)

    def test_flow_delegate_requires_exact_method_target_and_single_callback(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
        rr.obj=Mock(return_value=dict(parent="0x500"))
        rr.info=Mock(side_effect=[dict(parent="0x600"),{}]*8)
        rr.reviewed_field=lambda _,n,k:dict(method_ptr=0x10,method=0x28,method_code=0x40,delegates=0x78)[n]
        memory={0x110:0xABC,0x128:0x900,0x140:0x700,0x178:0,0x900:0xABC}
        rr.q=lambda p,**_:memory[p]
        self.assertEqual(rr.delegate(0x100,expected_method="0x900",expected_target=0x700)["target"],"0x700")
        for address,value in ((0x128,0x901),(0x140,0x701),(0x178,0x800),(0x110,0xABD)):
            original=memory[address];memory[address]=value
            with self.assertRaises(Refused):rr.delegate(0x100,expected_method="0x900",expected_target=0x700)
            memory[address]=original


def flow_fixture():
    rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
    refs={"alive":0x8000,"win":0x8100,"lose":0x8200,"close":0x8300}
    values={
        (0x1000,"_isFlowAlive"):refs["alive"],(0x1000,"_actionOnWin"):refs["win"],
        (0x1000,"_actionOnLose"):refs["lose"],(0x1000,"_actionOnClose"):refs["close"],
        (0x7000,"notified"):False,(0x7000,"win"):False,(0x7000,"<>4__this"):0x7100,(0x7000,"ctx"):0x7200,
        (0x7100,"_npcId"):1001,(0x7100,"_topicId"):2001,
        (0x7200,"<ActivationId>k__BackingField"):3,(0x7200,"_endedNotified"):False,
        (0x7300,"_state"):1,(0x7300,"_disposed"):False,
    }
    raw={(0x7100,"_subId"):b"\1\0\0\0"+struct.pack("<i",7),
         (0x7200,"<Ct>k__BackingField"):struct.pack("<Q",0x7300)}
    rr.obj=lambda p,n:dict(klass=hex(p+0x100000))
    rr.pointer_field=lambda p,c,n,*a,**k:values[p,n]
    rr.number=lambda p,c,n,*a:values[p,n]
    rr.flag=lambda p,c,n,*a:values[p,n]
    rr.fixed=lambda p,c,n,*a:raw[p,n]
    rr.method=lambda k,s:hex(s["token"])
    rr.delegate=Mock(side_effect=lambda address,**k:dict(target="0x7000",address=hex(address)))
    return rr,values,raw


class FlowAndConfigurationTests(unittest.TestCase):
    def test_flow_uses_normal_callbacks_and_exact_cancelled_state(self):
        rr,values,raw=flow_fixture();flow=rr.flow(0x1000,{},1001,2001)
        self.assertEqual(flow["sub_id"],7);self.assertFalse(flow["cancelled"])
        self.assertEqual(rr.delegate.call_count,5)
        self.assertTrue(all(call.kwargs.get("expected_target")==0x7000 for call in rr.delegate.call_args_list[1:]))
        for state in (2,3):
            values[0x7300,"_state"]=state;self.assertTrue(rr.flow(0x1000,{},1001,2001)["cancelled"])
        values[0x7300,"_state"]=1;values[0x7300,"_disposed"]=True
        self.assertTrue(rr.flow(0x1000,{},1001,2001)["cancelled"])

    def test_null_cancellation_source_is_live_but_missing_command_subid_is_unsupported(self):
        rr,values,raw=flow_fixture();raw[0x7200,"<Ct>k__BackingField"]=bytes(8)
        self.assertFalse(rr.flow(0x1000,{},1001,2001)["cancelled"])
        raw[0x7100,"_subId"]=bytes(8)
        with self.assertRaises(Refused):rr.flow(0x1000,{},1001,2001)

    def test_foreign_command_and_missing_callback_refused(self):
        for p,n,v in ((0x7100,"_npcId",1002),(0x7100,"_topicId",2002),(0x1000,"_isFlowAlive",0),
                       (0x1000,"_actionOnWin",0),(0x7300,"_state",4)):
            rr,values,raw=flow_fixture();values[p,n]=v
            with self.assertRaises(Refused):rr.flow(0x1000,{},1001,2001)

    def config_fixture(self):
        rr=pa.PersuasionResolver.__new__(pa.PersuasionResolver)
        rr.obj=lambda p,n:dict(pointer=p)
        rr.tables=lambda:(0x100,{})
        rr.table_rows=lambda *a:{2001:(0x200,{})}
        rr.list_objects=lambda *a:[0x300]
        rr.no_overrides=Mock()
        values={(0x200,"<npcId>k__BackingField"):1001,(0x200,"<maxRounds>k__BackingField"):6,
                (0x300,"<npcId>k__BackingField"):1001,(0x300,"<subId>k__BackingField"):7,
                (0x300,"<interactGameType>k__BackingField"):2,(0x300,"<interactGameParam>k__BackingField"):2001,
                (0x400,"<AINPC_PERSUADE_SUCCESS_THRESHOLD>k__BackingField"):30}
        pointers={(0x100,"<TbNpcInteractGameEntry>k__BackingField"):0x110,(0x110,"_dataList"):0x120,
                  (0x100,"<TbConstants>k__BackingField"):0x130,(0x130,"_data"):0x400}
        rr.pointer_field=lambda p,c,n,*a,**k:pointers[p,n]
        rr.integer=lambda p,c,n,*a:values[p,n]
        rr.number=lambda p,c,n,*a:values[p,n]
        rr.fixed=lambda *a:b"\1\0\0\0"+struct.pack("<i",10000)
        return rr,values

    def test_configuration_reads_threshold_and_native_nonpositive_fallback(self):
        rr,values=self.config_fixture()
        self.assertEqual(rr.configuration(1001,2001,7)["threshold"],30)
        values[0x400,"<AINPC_PERSUADE_SUCCESS_THRESHOLD>k__BackingField"]=0
        self.assertEqual(rr.configuration(1001,2001,7)["threshold"],100)
        rr.no_overrides.assert_any_call(0x110,{"pointer":0x110})
        rr.no_overrides.assert_any_call(0x130,{"pointer":0x130})

    def test_configuration_requires_exact_topic_npc_subid_and_type2(self):
        for p,n,value in ((0x200,"<npcId>k__BackingField",1002),(0x300,"<subId>k__BackingField",8),
                          (0x300,"<interactGameType>k__BackingField",1),(0x300,"<interactGameParam>k__BackingField",2002)):
            rr,values=self.config_fixture();values[p,n]=value
            with self.assertRaises(Refused):rr.configuration(1001,2001,7)
        rr,values=self.config_fixture();rr.list_objects=lambda *a:[0x300,0x300]
        with self.assertRaises(Refused):rr.configuration(1001,2001,7)


if __name__ == "__main__":
    unittest.main()
