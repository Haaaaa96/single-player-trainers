"""Learning-round lifecycle, stale target, numeric and float32 write tests."""
from dataclasses import replace
import math
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import learning_adapter as la
import learning_write as lw
from write_guard import Refused, UncertainWrite


STAMP = ("worldapart.exe", 123)


class Memory:
    def __init__(self):
        self.data = {}
        self.h = 1
        self.pid = 99
        self.writes = []

    def put(self,address,raw):
        self.data.update({address+i:b for i,b in enumerate(raw)})

    def read(self,address,size):
        try:
            return bytes(self.data[address+i] for i in range(size))
        except KeyError:
            return b""

    def read_exact(self,address,size):
        raw = self.read(address,size)
        if len(raw) != size:
            raise Refused("short read")
        return raw

    def write_exact(self,address,raw):
        self.writes.append((address,raw))
        self.put(address,raw)

    def number(self,address,value,fmt="i"):
        self.put(address,struct.pack("<"+fmt,value))


class PanelFixture:
    """Synthetic memory at the same reviewed offsets, independent of a live game."""
    def __init__(self):
        self.mem = Memory()
        self.lr = la.LearningResolver.__new__(la.LearningResolver)
        self.lr.reader,self.lr.stamp = self.mem,STAMP
        self.lr.meta,self.lr.module,self.lr.anchors = 0x100000,0x200000,[]
        self.panel,self.runtime,self.config = 0x8000,0x9000,0xA000
        self.classes = {}
        self.add_class(0x3000,la.NS+"LearnGongfaPanel",472,0x4000,[
            ("_runtime",232,0x12,0x4008637),("_config",240,0x12,0x4008638),
            ("_itemUid",248,0x0A,0x4008639),("_resultShown",264,2,0x400863B),
            ("_resultSuccess",265,2,0x400863C),("_learnEffectFailed",266,2,0x400863D),
            ("_callbackInvoked",267,2,0x400863E),("_shouldCompleteLearningOnExit",268,2,0x400863F),
            ("_learnEffectExecuted",269,2,0x4008640),("_roundInitialValue",272,8,0x4008642),
            ("_resultExitHandled",270,2,0x4008641),("_targetType",276,0x11,0x4008643),
            ("_targetId",280,8,0x4008644),("_targetLevel",284,8,0x4008645),
            ("_gameStartedNotified",288,2,0x4008646)])
        self.add_class(0x4000,"Game.BaseUI",200,0,[
            ("isShowing",66,2,0x4003FEB),("isInitialized",67,2,0x4003FEC),
            ("<IsInVisualHide>k__BackingField",88,2,0x4003FEF),
            ("<IsInteractable>k__BackingField",146,2,0x4003FF8),
            ("<IsPaused>k__BackingField",147,2,0x4003FF9),
            ("<HandleToken>k__BackingField",168,8,0x4003FFC)])
        self.add_class(0x5000,la.NS+"LearnGongfaRuntime",216,0,[
            ("_config",16,0x12,0x40086CD),("_gameDurationSeconds",88,0x0C,0x40086D7),
            ("_elapsedSeconds",140,0x0C,0x40086E4),("_epiphanyValue",152,0x0C,0x40086E7),
            ("_hasConsumedTime",156,2,0x40086E8),("_boundsInitialized",157,2,0x40086E9),
            ("<Phase>k__BackingField",160,0x11,0x40086EA),
            ("<EndReason>k__BackingField",164,0x11,0x40086EB),
            ("<CurrentValue>k__BackingField",168,0x0C,0x40086EC),
            ("<DemonValue>k__BackingField",172,0x0C,0x40086ED)])
        self.add_class(0x6000,"LubanDatas.data.MiniGameLearnGongfa",72,0,[
            ("<comprehend_value_limit>k__BackingField",24,8,0x400165C)])
        m=self.mem
        for address,size in ((self.panel,472),(self.runtime,216),(self.config,72)):
            m.put(address,b"\0"*size)
        m.number(self.panel,0x3000,"Q");m.number(self.runtime,0x5000,"Q");m.number(self.config,0x6000,"Q")
        m.number(self.panel+16,0xDEAD0000,"Q")
        for offset in (66,67,146,288):m.put(self.panel+offset,b"\1")
        m.number(self.panel+232,self.runtime,"Q");m.number(self.panel+240,self.config,"Q")
        m.number(self.panel+248,8,"Q");m.number(self.panel+168,27)
        m.number(self.panel+276,2);m.number(self.panel+280,104);m.number(self.panel+284,1)
        m.number(self.runtime+16,self.config,"Q");m.number(self.runtime+88,60.0,"f")
        m.number(self.runtime+140,5.0,"f");m.number(self.runtime+152,20.0,"f")
        m.number(self.runtime+160,1);m.number(self.runtime+164,0);m.number(self.runtime+168,10.5,"f")
        m.put(self.runtime+157,b"\1")
        m.number(self.config+24,300)

    def add_class(self,address,fullname,size,parent,fields):
        namespace,_,name=fullname.rpartition(".")
        fs=[]
        for n,offset,kind,token in fields:
            td=bytearray(16);td[8]=1;td[10]=kind
            fs.append(dict(name=n,offset=offset,token=hex(token),parent=hex(address),type_data=td.hex()))
        md,token,count=la.SPECS[fullname]
        for i in range(count-len(fs)):
            fs.append(dict(name="unused"+str(i),offset=16,token="0x1",parent=hex(address),type_data="00"*16))
        self.classes[address]=dict(klass=hex(address),namespace=namespace,name=name,instance_size=size,
                                   parent=hex(parent),fields=fs)
        self.mem.number(address+0x68,self.lr.meta+md,"Q")
        self.mem.number(address+0x11C,token)

    def invoke(self,method,*args,panels=None,**kwargs):
        with patch.object(la.probe,"inspect_class",side_effect=lambda reader,k:self.classes.get(k)), \
             patch.object(la,"process_identity",return_value=STAMP), \
             patch.object(self.lr,"_registered_panels",return_value=(0x7000,[self.panel] if panels is None else panels)):
            return getattr(self.lr,method)(*args,**kwargs)

    def state(self,panels=None,**kwargs):
        return self.invoke("snapshot",panels=panels,**kwargs)


class ResolverTests(unittest.TestCase):
    def setUp(self):self.fx=PanelFixture()

    def test_active_round_returns_true_float_targets_and_real_limit(self):
        state=self.fx.state()
        self.assertTrue(state["active"])
        self.assertEqual((state["current_value"],state["epiphany_percent"],state["maximum"]),(10.5,20.0,300))
        self.assertEqual(state["remaining_seconds"],55.0)
        self.assertEqual(state["targets"]["learning_value"].address,self.fx.runtime+168)

    def test_leftover_finished_object_not_selected_when_not_registered(self):
        self.assertFalse(self.fx.state([])["active"])

    def test_finished_or_aborted_round_not_editable(self):
        for phase,end in ((4,2),(4,1),(1,3),(1,4)):
            self.fx.mem.number(self.fx.runtime+160,phase)
            self.fx.mem.number(self.fx.runtime+164,end)
            self.assertFalse(self.fx.state()["active"])

    def test_phase_zero_before_start_is_inactive_without_write_targets(self):
        self.fx.mem.number(self.fx.runtime+160,0)
        self.fx.mem.put(self.fx.panel+288,b"\0")
        for method in ("snapshot","completion_snapshot"):
            with self.subTest(method=method):
                state = self.fx.invoke(method)
                self.assertFalse(state["active"])
                self.assertFalse(state["can_complete"])
                self.assertEqual(state["targets"],{})

    def test_phase_zero_after_start_is_rejected_as_inconsistent(self):
        self.fx.mem.number(self.fx.runtime+160,0)
        with self.assertRaisesRegex(Refused,"阶段或结束原因异常"):
            self.fx.state()
        with self.assertRaisesRegex(Refused,"阶段或结束原因异常"):
            self.fx.invoke("prepare_completion")

    def test_hidden_destroyed_unstarted_or_settled_panel_not_editable(self):
        for offset,value in ((16,0),(66,0),(67,0),(88,1),(264,1),(270,1),(288,0)):
            with self.subTest(offset=offset):
                fx=PanelFixture();fx.mem.number(fx.panel+offset,value,"Q" if offset==16 else "B")
                self.assertFalse(fx.state()["active"])

    def test_config_swap_refused(self):
        self.fx.mem.number(self.fx.panel+240,self.fx.config+8,"Q")
        with self.assertRaises(Refused):self.fx.state()

    def test_runtime_nan_infinity_and_invalid_range_refused(self):
        for value in (float("nan"),float("inf"),-1.0,301.0):
            self.fx.mem.number(self.fx.runtime+168,value,"f")
            with self.assertRaises(Refused):self.fx.state()

    def test_epiphany_has_actual_100_percent_ceiling(self):
        self.fx.mem.number(self.fx.runtime+152,100.01,"f")
        with self.assertRaises(Refused):self.fx.state()

    def test_metadata_token_mismatch_refused(self):
        self.fx.mem.number(0x5000+0x11C,0x0200FFFF)
        with self.assertRaises(Refused):self.fx.state()

    def test_field_type_mismatch_refused(self):
        f=next(f for f in self.fx.classes[0x5000]["fields"] if f["name"]=="<CurrentValue>k__BackingField")
        data=bytearray.fromhex(f["type_data"]);data[10]=8;f["type_data"]=data.hex()
        with self.assertRaises(Refused):self.fx.state()

    def test_item_uid_or_panel_handle_changes_identity(self):
        before=self.fx.state()["targets"]["learning_value"]
        self.fx.mem.number(self.fx.panel+248,9,"Q")
        after=self.fx.state()["targets"]["learning_value"]
        self.assertNotEqual(before.identity,after.identity)

    def test_duplicate_active_panels_refused(self):
        with self.assertRaises(Refused):self.fx.state([self.fx.panel,self.fx.panel])


class CompletionSnapshotTests(unittest.TestCase):
    def setUp(self): self.fx = PanelFixture()

    def prepare(self,shown=None):
        return self.fx.invoke("prepare_completion",shown)

    def finish(self,end=2):
        m = self.fx.mem
        m.number(self.fx.runtime+160,4)
        m.number(self.fx.runtime+164,end)
        m.number(self.fx.runtime+168,300.0,"f")
        m.put(self.fx.panel+264,b"\1")
        m.put(self.fx.panel+265,b"\1" if end==2 else b"\0")
        m.put(self.fx.runtime+156,b"\1")

    def test_prepare_has_single_progress_target_and_dynamic_threshold(self):
        state = self.prepare()
        self.assertTrue(state["can_complete"])
        self.assertEqual(state["target"].key,"learning_value")
        self.assertEqual(state["target"].maximum,300)
        self.assertEqual(state["round_key"],state["identity"])
        guards = state["completion_guards"]
        self.assertEqual(guards,{"elapsed_address":self.fx.runtime+140,
            "duration_address":self.fx.runtime+88,"demon_address":self.fx.runtime+172,
            "paused_address":self.fx.panel+147})
        anchors = dict(state["target"].anchors)
        self.assertIn(guards["demon_address"],anchors)
        self.assertIn(guards["duration_address"],anchors)
        self.assertIn(guards["paused_address"],anchors)
        self.assertNotIn(guards["elapsed_address"],anchors)

    def test_fresh_progress_and_normal_phase_transition_keep_same_round(self):
        shown = self.prepare()
        self.fx.mem.number(self.fx.runtime+168,20.5,"f")
        self.fx.mem.number(self.fx.runtime+160,3)
        self.fx.mem.number(self.fx.runtime+152,99.0,"f")
        fresh = self.prepare(shown)
        self.assertEqual(fresh["round_key"],shown["round_key"])
        self.assertNotEqual(fresh["target"].identity,shown["target"].identity)
        self.assertEqual(fresh["target"].value,20.5)

    def test_same_round_at_threshold_can_be_observed_without_another_write(self):
        shown = self.prepare()
        self.fx.mem.number(self.fx.runtime+168,300.0,"f")
        fresh = self.prepare(shown)
        self.assertTrue(fresh["can_complete"])
        self.assertEqual(fresh["target"].value,fresh["maximum"])

    def test_pause_cover_uninitialized_and_settlement_refuse_prepare(self):
        for address,value in ((self.fx.panel+147,1),(self.fx.panel+146,0),
                              (self.fx.runtime+157,0),(self.fx.runtime+156,1),
                              (self.fx.panel+265,1),(self.fx.panel+266,1),
                              (self.fx.panel+267,1),(self.fx.panel+268,1),(self.fx.panel+269,1)):
            with self.subTest(address=address):
                before = self.fx.mem.read_exact(address,1)
                self.fx.mem.put(address,bytes([value]))
                with self.assertRaises(Refused): self.prepare()
                self.fx.mem.put(address,before)

    def test_full_demon_or_expired_time_cannot_prepare(self):
        for address,value in ((self.fx.runtime+172,100.0),(self.fx.runtime+140,60.0)):
            with self.subTest(address=address):
                before = self.fx.mem.read_exact(address,4)
                self.fx.mem.number(address,value,"f")
                with self.assertRaises(Refused): self.prepare()
                self.fx.mem.put(address,before)

    def test_invalid_demon_duration_elapsed_or_flags_refused(self):
        cases = [(self.fx.runtime+172,v,"f") for v in (float("nan"),-1.0,100.1)]
        cases += [(self.fx.runtime+88,v,"f") for v in (float("inf"),0.0,-1.0)]
        cases += [(self.fx.runtime+140,-1.0,"f"),(self.fx.panel+147,2,"B"),
                  (self.fx.runtime+157,2,"B")]
        for address,value,fmt in cases:
            with self.subTest(address=address,value=value):
                before = self.fx.mem.read_exact(address,struct.calcsize(fmt))
                self.fx.mem.number(address,value,fmt)
                with self.assertRaises(Refused): self.prepare()
                self.fx.mem.put(address,before)

    def test_changed_book_handle_target_or_round_initial_rejected(self):
        shown = self.prepare()
        for offset,fmt in ((248,"Q"),(168,"i"),(276,"i"),(280,"i"),(284,"i"),(272,"i")):
            with self.subTest(offset=offset):
                address = self.fx.panel+offset
                before = self.fx.mem.read_exact(address,struct.calcsize(fmt))
                old = struct.unpack("<"+fmt,before)[0]
                self.fx.mem.number(address,old+1,fmt)
                with self.assertRaisesRegex(Refused,"已更换"): self.prepare(shown)
                self.fx.mem.put(address,before)

    def test_completion_observation_returns_terminal_without_write_targets(self):
        shown = self.prepare()
        self.finish()
        state = self.fx.invoke("observe_completion",shown)
        self.assertFalse(state["active"])
        self.assertFalse(state["can_complete"])
        self.assertEqual(state["status"],"round_success")
        self.assertEqual(state["round_key"],shown["round_key"])
        self.assertEqual(state["targets"],{})
        self.assertIsNone(state["target"])
        self.assertFalse(self.fx.state()["active"])

    def test_hidden_terminal_still_registered_is_readable_for_original_round_only(self):
        shown = self.prepare()
        self.finish()
        self.fx.mem.put(self.fx.panel+66,b"\0")
        self.fx.mem.put(self.fx.panel+88,b"\1")
        self.fx.mem.put(self.fx.panel+288,b"\0")
        self.fx.mem.put(self.fx.panel+269,b"\1")
        self.fx.mem.put(self.fx.panel+270,b"\1")
        state = self.fx.invoke("observe_completion",shown)
        self.assertFalse(state["visible"])
        self.assertTrue(state["learn_effect_executed"])
        self.assertTrue(state["result_exit_handled"])
        self.assertFalse(self.fx.invoke("completion_snapshot")["active"])
        with self.assertRaises(Refused): self.prepare(shown)

    def test_hidden_active_round_never_exposes_targets(self):
        shown = self.prepare()
        self.fx.mem.put(self.fx.panel+66,b"\0")
        with self.assertRaises(Refused): self.fx.invoke("observe_completion",shown)

    def test_destroyed_unregistered_or_replaced_round_is_unknown(self):
        shown = self.prepare()
        self.finish()
        with self.assertRaises(Refused): self.fx.invoke("observe_completion",shown,panels=[])
        self.fx.mem.number(self.fx.panel+16,0,"Q")
        with self.assertRaises(Refused): self.fx.invoke("observe_completion",shown)
        self.fx.mem.number(self.fx.panel+16,0xDEAD0000,"Q")
        self.fx.mem.number(self.fx.panel+248,99,"Q")
        with self.assertRaises(Refused): self.fx.invoke("observe_completion",shown)

    def test_each_non_success_end_and_effect_failure_are_distinct_from_success(self):
        shown = self.prepare()
        for end in (1,3,4):
            with self.subTest(end=end):
                self.finish(end)
                self.assertEqual(self.fx.invoke("observe_completion",shown)["status"],"failed")
        self.finish()
        self.fx.mem.put(self.fx.panel+266,b"\1")
        self.assertEqual(self.fx.invoke("observe_completion",shown)["status"],"failed")

    def test_execution_flag_alone_does_not_claim_learning_applied(self):
        shown = self.prepare()
        self.finish()
        self.fx.mem.put(self.fx.panel+269,b"\1")
        self.fx.mem.put(self.fx.panel+268,b"\1")
        result = self.fx.invoke("observe_completion",shown)
        self.assertEqual(result["status"],"round_success")
        self.assertTrue(result["should_complete_on_exit"])

    def test_malformed_round_identity_and_ambiguous_panels_refused(self):
        for shown in ({},False,{"round_key":("bad",)}):
            with self.subTest(shown=shown),self.assertRaises(Refused): self.prepare(shown)
        with self.assertRaises(Refused): self.fx.invoke("observe_completion",{})
        shown = self.prepare()
        with self.assertRaises(Refused):
            self.fx.invoke("prepare_completion",shown,panels=[self.fx.panel,self.fx.panel])


class FloatWriteTests(unittest.TestCase):
    def setUp(self):
        self.m=Memory();self.m.number(0x1000,10.5,"f");self.m.put(0x2000,b"\1")
        self.t=lw.FloatTarget("learning_value",0x1000,10.5,(STAMP,1),0.0,300.0,((0x2000,"01"),))
        self.log=[]

    def set(self,value,resolve=None):
        return lw.set_float_value(self.m,resolve or (lambda key:self.t),self.t,value,self.log.append)

    def test_writes_float32_once_and_records_readback(self):
        result=self.set(20.25)
        self.assertEqual(self.m.writes,[(0x1000,struct.pack("<f",20.25))])
        self.assertEqual(result.value,20.25)
        self.assertEqual([e["status"] for e in self.log],["attempt","verified_memory"])

    def test_decimal_rounding_is_reported_as_float32(self):
        result=self.set(20.23)
        self.assertEqual(result.value,struct.unpack("<f",struct.pack("<f",20.23))[0])

    def test_nan_inf_bool_and_out_of_range_never_write(self):
        for value in (float("nan"),float("inf"),True,-1,301,"20",10.5):
            with self.subTest(value=value),self.assertRaises(Refused):self.set(value)
        self.assertEqual(self.m.writes,[])

    def test_stale_round_and_stale_value_never_write(self):
        for changed in (replace(self.t,identity=(STAMP,2)),replace(self.t,value=11.5)):
            with self.assertRaises(Refused):self.set(20,lambda key:changed)
        self.assertEqual(self.m.writes,[])

    def test_race_before_write_refused(self):
        count=0
        def resolve(key):
            nonlocal count
            count+=1
            return self.t if count<3 else replace(self.t,identity=(STAMP,2))
        with self.assertRaises(Refused):self.set(20,resolve)
        self.assertEqual(self.m.writes,[])

    def test_log_failure_before_write_prevents_mutation(self):
        with self.assertRaises(OSError):
            lw.set_float_value(self.m,lambda k:self.t,self.t,20,lambda event:(_ for _ in ()).throw(OSError()))
        self.assertEqual(self.m.writes,[])

    def test_game_consuming_meter_is_uncertain_and_never_retried(self):
        original=self.m.write_exact
        def write(address,data):original(address,data);self.m.number(address,19.9,"f")
        self.m.write_exact=write
        with self.assertRaises(UncertainWrite):self.set(20)
        self.assertEqual(len(self.m.writes),1)
        self.assertEqual(self.log[-1]["status"],"consumed_or_changed")

    def test_parser_accepts_only_plain_nonnegative_numbers(self):
        self.assertEqual(lw.parse_float_value(" 99.25 "),99.25)
        for text in ("1e2","NaN","inf","-1","1,000","１","1.234","",True):
            with self.subTest(text=text),self.assertRaises(Refused):lw.parse_float_value(text)

    def test_single_change_limit(self):
        target=replace(self.t,maximum=10000)
        with self.assertRaises(Refused):lw.validate_float(target,2000)

    def test_native_revalidates_round_anchors_before_requesting_write(self):
        calls=[]
        def region(handle,address,pointer,size):
            obj=pointer._obj;obj.BaseAddress=0x1000;obj.RegionSize=0x1000
            obj.State=0x1000;obj.Type=0x20000;obj.Protect=4
            return 1
        kernel=SimpleNamespace(OpenProcess=lambda *args:22,CloseHandle=lambda h:calls.append("closed"),
                               VirtualQueryEx=region,WriteProcessMemory=lambda *a:calls.append("write"))
        once=lw.FloatWriteOnce(self.m,STAMP,self.t,new_value=20)
        self.m.put(0x2000,b"\0")
        with patch.object(lw,"K",kernel),patch.object(lw,"process_identity",return_value=STAMP), \
             patch.object(lw,"read_exact_handle",side_effect=lambda h,a,n:self.m.read_exact(a,n)):
            with self.assertRaises(Refused):once.write_exact(0x1000,struct.pack("<f",20))
        self.assertEqual(calls,["closed"])

    def test_native_writes_exact_float_bytes_once_only(self):
        calls=[]
        def region(handle,address,pointer,size):
            obj=pointer._obj;obj.BaseAddress=0x1000;obj.RegionSize=0x1000
            obj.State=0x1000;obj.Type=0x20000;obj.Protect=4
            return 1
        def write(handle,address,buffer,size,count):
            calls.append((address,bytes(buffer.raw[:size]),size));count._obj.value=size;return 1
        kernel=SimpleNamespace(OpenProcess=lambda *args:22,CloseHandle=lambda h:None,
                               VirtualQueryEx=region,WriteProcessMemory=write)
        once=lw.FloatWriteOnce(self.m,STAMP,self.t,new_value=20.25)
        with patch.object(lw,"K",kernel),patch.object(lw,"process_identity",return_value=STAMP), \
             patch.object(lw,"read_exact_handle",side_effect=lambda h,a,n:self.m.read_exact(a,n)):
            once.write_exact(0x1000,struct.pack("<f",20.25))
            with self.assertRaises(Refused):once.write_exact(0x1000,struct.pack("<f",20.25))
        self.assertEqual(calls,[(0x1000,struct.pack("<f",20.25),4)])

    def test_native_rejects_wrong_bytes_and_changed_process_before_writes(self):
        for wrong in (struct.pack("<i",20),b"",b"\0"*8):
            once=lw.FloatWriteOnce(self.m,STAMP,self.t,new_value=20)
            with self.assertRaises(Refused):once.write_exact(0x1000,wrong)
        kernel=SimpleNamespace(OpenProcess=lambda *args:22,CloseHandle=lambda h:None)
        once=lw.FloatWriteOnce(self.m,STAMP,self.t,new_value=20)
        with patch.object(lw,"K",kernel),patch.object(lw,"process_identity",return_value=("other.exe",123)):
            with self.assertRaises(Refused):once.write_exact(0x1000,struct.pack("<f",20))

    def test_malformed_and_unknown_target_rejected(self):
        for changed in (replace(self.t,key="item:1"),replace(self.t,address=0x1001),
                        replace(self.t,anchors=()),replace(self.t,anchors=((0x2000,"zz"),)),
                        replace(self.t,anchors=("bad",))):
            with self.assertRaises(Refused):lw.validate_float(changed,20)


if __name__ == "__main__":unittest.main()
