"""Offline controller layout, dispatch, override preservation and uncertainty."""
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import game_speed as gs
import game_speed_native as gn
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(gs.SpeedTarget(1., 1., 0x2008, ((123, 456), 0x1000, 0x2000, 0x3000, 0x4000, 0, 9, ()),
                                  ((0x100, "00"),), 0), **changes)


class ValueTests(unittest.TestCase):
    def test_boundaries_and_normalization(self):
        for value in (0.5, 0.75, 1.01, 1.25, 2.):
            self.assertEqual(gs.pack(gs.validate_speed_value(target(), value)), gs.pack(value))

    def test_invalid_and_noop_never_accepted(self):
        for value in (True, "2", 0.49, 2.001, 1., float("nan"), float("inf"), -1):
            with self.subTest(value=value), self.assertRaises(Refused):gs.validate_speed_value(target(), value)

    def test_existing_outside_tool_range_can_restore_one(self):
        self.assertEqual(gs.validate_speed_value(target(value=10.), 1.), 1.)

    def test_invalid_target_refuses(self):
        for t in (None, target(can_edit=False), target(identity=()), target(address=0), target(address=9), target(anchors=())):
            with self.subTest(target=t), self.assertRaises(Refused):gs.validate_speed_value(t, 1.5)

    def test_paused_override_does_not_block_valid_base_setting(self):
        self.assertEqual(gs.validate_speed_value(target(effective=0., override_count=1), 1.5), 1.5)


class MemoryFixture:
    def __init__(self):
        self.memory, self.names = {}, {}
    def store(self, address, raw):
        for i, v in enumerate(raw):self.memory[address+i] = v
    def put(self, address, fmt, value):self.store(address, struct.pack("<"+fmt, value))
    def read(self, address, size):return bytes(self.memory.get(address+i, 0) for i in range(size))
    def string(self, address):return self.names.get(address, "")


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.mem = MemoryFixture()
        self.rr = gs.GameSpeedResolver.__new__(gs.GameSpeedResolver)
        self.rr.reader, self.rr.module, self.rr.meta, self.rr.anchors = self.mem, 0x10000000, 0x20000000, []
        self.mem.store(self.rr.module+gs.SPECS["slot_proof_rva"], bytes.fromhex(gs.SPECS["slot_proof"]))
        for a,v in ((self.rr.module+gs.SPECS["class_slot_rva"],0x1000),(0x10B8,0x2000),(0x2000,0x3000),
                    (0x3000,0x5000),(0x3010,0x4000),(0x4000,0x6000),(0x6040,0x7000),(0x4018,4)):
            self.mem.put(a,"Q",v)
        for a,v in ((0x10E0,1),(0x3018,0),(0x301C,9)):self.mem.put(a,"i",v)
        self.mem.put(0x2008,"f",1.)
        def c(full, k, size=32):
            ns, name = full.rsplit(".",1)
            return dict(namespace=ns,name=name,klass=hex(k),instance_size=size)
        self.classes = {0x1000:c("Game.GameTimeScaleController",0x1000),
            0x5000:c("System.Collections.Generic.List`1",0x5000),
            0x6000:c(".TimeScaleOverride[]",0x6000),0x7000:c(".TimeScaleOverride",0x7000,24)}
        self.rr.info = Mock(side_effect=lambda k,full=None:self.classes[k])
        self.rr.class_address = Mock(return_value=0x1000)
        self.rr.reviewed_field = Mock(side_effect=lambda c,n,k,o,**kw:o)

    def test_no_override_reads_base_and_does_not_write(self):
        before = self.mem.memory.copy()
        result = self.rr.controller()
        self.assertEqual((result["value"],result["effective"],result["override_count"]),(1.,1.,0))
        self.assertEqual(self.mem.memory,before)
        self.assertNotIn((0x2008,gs.pack(1.).hex()),self.rr.anchors)

    def overrides(self, scales):
        self.mem.put(0x3018,"i",len(scales))
        for i,scale in enumerate(scales):
            self.mem.put(0x4020+i*8,"i",i+1)
            self.mem.put(0x4024+i*8,"f",scale)

    def test_last_override_has_priority_including_pause(self):
        for scales in ([.5],[2.,.5],[.5,0.]):
            self.overrides(scales)
            result = self.rr.controller()
            self.assertEqual(result["effective"], scales[-1])
            self.assertEqual(result["override_count"], len(scales))

    def test_unknown_uninitialized_or_large_list_refuses(self):
        for address,fmt,value in ((0x10E0,"i",0),(0x3018,"i",65),(0x4018,"Q",129),(0x2008,"f",float("nan"))):
            with self.subTest(address=address):
                old = self.mem.memory.copy();self.mem.put(address,fmt,value)
                with self.assertRaises(Refused):self.rr.controller()
                self.mem.memory = old

    def test_invalid_override_handle_or_scale_refuses(self):
        self.overrides([.5,.25])
        for address,fmt,value in ((0x4028,"i",1),(0x4020,"i",0),(0x4024,"f",float("inf")),(0x4024,"f",-1)):
            with self.subTest(address=address):
                old=self.mem.memory.copy();self.mem.put(address,fmt,value)
                with self.assertRaises(Refused):self.rr.controller()
                self.mem.memory=old

    def test_method_static_identity_return_and_prefix(self):
        self.mem.put(0x1098,"Q",0x8000);self.mem.put(0x1120,"H",3)
        methods={}
        for i,(key,spec) in enumerate(gs.METHODS.items()):
            mi,n,ret=0x9000+i*0x100,0xA000+i*0x100,0xB000+i*0x100
            self.mem.names[n]=spec["name"]; methods[key]=hex(mi)
            for a,v in ((0x8000+i*8,mi),(mi,self.rr.module+spec["rva"]),(mi+0x18,n),(mi+0x20,0x1000),(mi+0x28,ret)):
                self.mem.put(a,"Q",v)
            self.mem.put(mi+0x48,"i",spec["token"]);self.mem.put(mi+0x4C,"H",0x96)
            self.mem.put(mi+0x52,"B",spec["parameters"]);self.mem.put(ret+10,"B",spec["return_kind"])
            self.mem.put(ret+11,"B",0x80 if spec["return_kind"] == 12 else 0)
            self.mem.store(self.rr.module+spec["rva"],bytes.fromhex(spec["prefix"]))
        self.assertEqual(self.rr.methods(0x1000),methods)
        for a,fmt,v in ((0x924C,"H",0x86),(0x9020,"Q",0),(0xB00A,"B",8),(0x9252,"B",2),(0x9248,"i",0),(0xB00B,"B",0x20),(0xB00B,"B",0x40)):
            with self.subTest(address=a):
                old=self.mem.memory.copy();self.mem.put(a,fmt,v)
                with self.assertRaises(Refused):self.rr.methods(0x1000)
                self.mem.memory=old


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.a=gs.GameSpeedAdapter.__new__(gs.GameSpeedAdapter)
        self.a.game=types.SimpleNamespace(stamp=(1,2),blocked=False,resolver=Mock())
        self.a.blocked=False;self.a.resolver=Mock();self.a.resolver.anchors=[]
        self.raw=dict(value=1.,effective=0.,address=0x2008,identity=(0x1000,0x2000,0x3000,0x4000,1,9,((1,0.),)),
            klass=0x1000,static=0x2000,overrides=0x3000,items=0x4000,override_count=1,override_version=9,capacity=4)
        self.a.resolver.controller.return_value=self.raw
        self.a.resolver.exact.side_effect=lambda a,n:gs.pack(1.) if a==0x2008 else b"\0"
        patch.object(gs,"process_identity",return_value=(1,2)).start()
        self.context=patch.object(gs,"require_safe_acquisition_context",return_value={"anchors":[{"address":0x100,"expected_hex":"00"}]}).start()
        self.addCleanup(patch.stopall)

    def test_context_refused_keeps_readonly_display(self):
        self.context.side_effect=gs.AcquisitionContextRefused("combat")
        state=self.a.snapshot()
        self.assertEqual(state["effective"],0)
        self.assertFalse(state["can_edit"])

    def test_full_native_request_includes_actual_base_anchor(self):
        shown=self.a.snapshot()["target"]
        self.a.resolver.methods.return_value=(dict(base="0xA000",effective="0xB000",modify="0xC000"),gs.METHODS)
        d=self.a.prepare_native(shown,1.5)
        self.assertEqual(d["value"],1.5)
        self.assertEqual(d["effective_before"],0.)
        self.assertEqual(d["method_specs"],gs.METHODS)
        self.assertIn(dict(address="0x2008",size=4,expected_hex=gs.pack(1.).hex(),label="speed_context"),d["anchors"])

    def test_changed_override_after_display_never_prepares(self):
        shown=self.a.snapshot()["target"]
        self.raw["effective"]=.5
        with self.assertRaises(Refused):self.a.prepare_native(shown,1.5)
        self.a.resolver.methods.assert_not_called()

    def test_pending_is_refused_before_native(self):
        self.a._lock=__import__('threading').Lock();self.a._native=Mock()
        with patch('acquisition_adapter.native_calls_pending',return_value=True),self.assertRaises(Refused):
            self.a.set_value(target(),1.5)
        self.a._native.set_value.assert_not_called()


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        patch.object(gn,"initialize_runtime",return_value=Path(self.temp.name)).start()
        patch.dict("sys.modules",frida=types.SimpleNamespace(__version__="17.7.3")).start()
        self.addCleanup(patch.stopall)
        self.game=types.SimpleNamespace(resolver=types.SimpleNamespace(reader=types.SimpleNamespace(pid=123)),stamp=(123,456),record=Mock())
        self.shown=target();self.after=target(value=1.5,effective=1.5)
        self.d=dict(klass="0x1000",static="0x2000",overrides="0x3000",items="0x4000",override_count=0,override_version=9,capacity=4,
            before=1.,value=1.5,effective_before=1.,address="0x2008",identity_key="a"*64,methods=dict(base="0x5000",effective="0x6000",modify="0x7000"),
            method_info="0x7000",anchors=[dict(address="0x100",size=1,expected_hex="00")])
        self.adapter=types.SimpleNamespace(prepare_native=Mock(return_value=self.d),snapshot=Mock(return_value=dict(target=self.after,base=1.5,effective=1.5,override_count=0)))
        self.native=gn.GameSpeedNative(self.game,self.adapter)
        self.addCleanup(lambda:gn._LIVE_BRIDGES.discard(self.native));self.addCleanup(lambda:gn._RETAINED_BRIDGES.discard(self.native))
        self.connection=Mock();self.connection.script=types.SimpleNamespace(exports_sync=types.SimpleNamespace(submit=Mock()))
        self.behavior="success"
        self.acquire=patch.object(gn,"acquire_connection",side_effect=self.connect).start()

    def connect(self,identity,frida,source,epoch,owner,message,detached,before,check):
        def submit(request):
            if self.behavior=="transport":raise OSError("pipe closed")
            payload=dict(status="completed",called=True,token=request["token"],before=1.,value=1.5,effective=self.after.effective,
                         override_count=self.shown.override_count,identity_key="a"*64)
            if self.behavior=="wrong":payload["value"]=1.25
            if self.behavior=="override_lost":payload["effective"]=1.5
            if self.behavior=="rejected":payload.update(status="rejected",called=False)
            if self.behavior=="exception":payload["status"]="exception"
            message(dict(type="send",payload=payload),None)
        self.connection.script.exports_sync.submit.side_effect=submit
        return self.connection

    def test_single_shared_call_returns_verified_state(self):
        result=self.native.set_value(self.shown,1.5)
        self.assertTrue(result["verified"])
        request=self.connection.script.exports_sync.submit.call_args.args[0]
        self.assertEqual((request["operation"],request["method_token"],request["method_rva"]),("game_speed_set",0x06007F5E,0x1517B60))
        self.assertNotIn("bag",request)
        self.assertEqual(self.acquire.call_args.args[3].name,"acquisition-native-epochs.json")
        self.connection.release.assert_called_once_with(self.native)

    def paused(self):
        self.shown=target(effective=0.,override_count=1)
        self.after=replace(self.shown,value=1.5)
        self.d.update(override_count=1,effective_before=0.)
        self.adapter.snapshot.return_value.update(target=self.after,effective=0.,override_count=1)

    def test_game_pause_override_is_valid_success_with_effective_zero(self):
        self.paused()
        self.assertEqual(self.native.set_value(self.shown,1.5)["effective"],0.)

    def test_losing_existing_override_is_unknown(self):
        self.paused();self.behavior="override_lost"
        with self.assertRaises(UncertainWrite):self.native.set_value(self.shown,1.5)

    def test_scene_change_during_connection_never_submits(self):
        self.adapter.prepare_native.side_effect=[self.d,Refused("changed")]
        with self.assertRaises(Refused):self.native.set_value(self.shown,1.5)
        self.connection.script.exports_sync.submit.assert_not_called()

    def test_proven_no_call_can_retry(self):
        self.behavior="rejected"
        with self.assertRaises(Refused) as c:self.native.set_value(self.shown,1.5)
        self.assertNotIsInstance(c.exception,UncertainWrite)
        self.native.require_ready()

    def test_dispatched_unknown_is_durable_and_not_retried(self):
        for behavior in ("wrong","exception","transport"):
            with self.subTest(behavior=behavior):
                self.native.record(dict(status="verified"));self.behavior=behavior
                with self.assertRaises(UncertainWrite):self.native.set_value(self.shown,1.5)
                with self.assertRaises(Refused):self.native.require_ready()

    def test_postwrite_override_version_or_identity_changed_is_unknown(self):
        self.adapter.snapshot.return_value["target"]=replace(self.after,identity=("changed",))
        with self.assertRaises(UncertainWrite):self.native.set_value(self.shown,1.5)

    def test_postwrite_read_failed_is_unknown(self):
        self.adapter.snapshot.side_effect=Refused("read failed")
        with self.assertRaises(UncertainWrite):self.native.set_value(self.shown,1.5)

    def test_corrupt_or_pending_journal_prevents_connection(self):
        self.native.record(dict(status="pending"))
        with self.assertRaises(Refused):self.native.set_value(self.shown,1.5)
        self.native.journal.write_text("bad",encoding="utf8")
        with self.assertRaises(Refused):self.native.set_value(self.shown,1.5)
        self.acquire.assert_not_called()


if __name__ == "__main__":unittest.main()
