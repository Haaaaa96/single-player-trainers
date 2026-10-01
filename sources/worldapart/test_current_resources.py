"""Offline stamina targets, readonly resolver, and guarded dispatch contracts."""
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import current_resources as cr
import current_resources_native as cn
from write_guard import Refused, UncertainWrite


def target(**changes):
    version = changes.pop("version", 1)
    identity = tuple(range(9)) + ((0x6000, 0x6020, 2, 0, version),)
    return replace(cr.ResourceTarget(50.0, 0x604C, identity, ((0x5000, "01000000"),)), **changes)


class ValueTests(unittest.TestCase):
    def test_resource_input_roundtrips_real_single_without_rounding_above_max(self):
        for value in (737.4599609375, 0.000012345678, 1., 1000000.):
            original = struct.unpack('<f', cr.pack(value))[0]
            parsed = cr.parse_attribute_value(cr.resource_input(original))
            self.assertEqual(cr.pack(parsed), cr.pack(original))
        for value in ('NaN','Infinity','-1','1e99','1000001','1,000', True, 1):
            with self.subTest(value=value), self.assertRaises(Refused):
                cr.parse_attribute_value(value)

    def test_current_resource_is_not_growth_or_maximum(self):
        shown = target()
        self.assertEqual(shown.key, "current_stamina")
        self.assertEqual(cr.validate_stamina_value(shown, 49.25), 49.25)
        with self.assertRaises(Refused):
            cr.validate_stamina_value(replace(shown, key="growth:201"), 51)

    def test_float32_normalization_and_boundaries(self):
        self.assertEqual(cr.pack(cr.validate_stamina_value(target(), 50.01)), cr.pack(50.01))
        self.assertEqual(cr.validate_stamina_value(target(), 1050), 1050)
        self.assertEqual(cr.validate_stamina_value(target(), 0), 0)
        for value in (-1, 1050.01, 1000001, True, float("nan"), float("inf"), 50):
            with self.subTest(value=value), self.assertRaises(Refused):
                cr.validate_stamina_value(target(), value)

    def test_missing_or_untrusted_current_entry_rejected(self):
        for shown in (target(address=0), target(address=0x604D), target(can_edit=False),
                      target(identity=()), target(anchors=()), target(value=float("nan")),
                      target(anchors=((0x604A, "00000000"),)), target(anchors=((1,"zz"),))):
            with self.subTest(shown=shown), self.assertRaises(Refused):
                cr.validate_stamina_value(shown, 51)

    def test_static_method_whitelist(self):
        self.assertEqual((cr.METHODS["current"]["token"], cr.METHODS["current"]["rva"]), (0x06014B07, 0xE5FEA0))
        self.assertEqual((cr.METHODS["max"]["token"], cr.METHODS["max"]["rva"]), (0x06014B08, 0xE60A90))
        self.assertEqual((cr.METHODS["modify"]["token"], cr.METHODS["modify"]["rva"]), (0x06014B00, 0xE653A0))

    def test_health_never_sets_zero_or_resurrects(self):
        shown = target(key="current_health")
        self.assertEqual(cr.validate_resource_value(shown, 1), 1)
        for current, value in ((50, 0), (0, 50), (50, 0.99)):
            with self.assertRaises(Refused):
                cr.validate_resource_value(replace(shown, value=current), value)

    def test_mana_and_stamina_can_be_zero_but_noop_is_rejected(self):
        for key in ("current_mana", "current_stamina"):
            self.assertEqual(cr.validate_resource_value(target(key=key), 0), 0)
            with self.assertRaises(Refused):
                cr.validate_resource_value(target(key=key, value=0), 0)

    def test_only_exact_dictionary_version_increment_is_accepted(self):
        before = target().identity
        self.assertTrue(cr.resource_identity_after_modify(before, target(version=2).identity))
        for after in (target(version=1).identity, target(version=3).identity, ("other",),
                      before[:9]+((0x6000,0x6020,3,0,2),), before[:9]+((0x6000,0x6030,2,0,2),)):
            self.assertFalse(cr.resource_identity_after_modify(before, after))

    def test_dictionary_version_wrap_matches_native_int32(self):
        self.assertTrue(cr.resource_identity_after_modify(target(version=2147483647).identity,
                                                         target(version=-2147483648).identity))


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.adapter = cr.CurrentResourcesAdapter.__new__(cr.CurrentResourcesAdapter)
        self.raw = dict(anchor_verified=True, anchors=[dict(address=0x100, expected_hex="00")],
                        player=0x2000, manager=1, store=2, world=3)
        self.game = types.SimpleNamespace(resolver=types.SimpleNamespace(resolve=Mock(return_value=self.raw)),
                                          blocked=False, stamp=("game", 1))
        self.adapter.game, self.adapter.blocked = self.game, False
        self.rr = self.adapter.resolver = Mock()
        self.rr.reader.h = 10
        self.rr.obj.return_value = {"klass": "0x3000"}
        offsets = {"combat": 0x20, "<CurrentLayerId>k__BackingField": 0x60,
                   "<PendingRealmBreakthrough>k__BackingField": 0xA0, "_cultivateInjectBatchDepth": 0x100,
                   "<BaseAttrs>k__BackingField": 0x20}
        self.rr.reviewed_field.side_effect = lambda c, n, k: offsets[n]
        self.rr.q.side_effect = lambda a, **kw: {0x2020:0x4000, 0x4010:0x2000, 0x40A0:0, 0x4020:0x6000}[a]
        self.rr.i.side_effect = lambda a, **kw: 1 if a == 0x4060 else 0
        self.rr.dictionary.return_value = ({200:{"value":50.0,"address":0x604C},
                                           201:{"value":10.0,"address":0x605C}},
                                          [(0x604C,cr.pack(50).hex()),(0x605C,cr.pack(10).hex())],
                                          (0x6000,0x6020,2,0,1))
        expected = {0x100:b"\0", 0x604C:cr.pack(50), 0x605C:cr.pack(10)}
        self.expected = expected
        self.rr.exact.side_effect = lambda a, n: expected[a]
        self.context = patch.object(cr,"require_safe_acquisition_context",return_value={"anchors":[]}).start()
        self.addCleanup(patch.stopall)
        patch.object(cr,"process_identity",return_value=self.game.stamp).start()

    def test_base_current_is_read_but_base_201_is_not_claimed_as_true_max(self):
        state = self.adapter.snapshot()
        self.assertEqual(state["current"],50)
        self.assertIsNone(state["maximum"])
        self.assertEqual(state["target"].address,0x604C)
        self.assertNotIn((0x604C,cr.pack(50).hex()),state["target"].anchors)
        self.assertIn((0x605C,cr.pack(10).hex()),state["target"].anchors)

    def add_vitals(self):
        values, anchors, identity = self.rr.dictionary.return_value
        for attr,address,value in ((1,0x606C,80.),(25,0x607C,20.)):
            values[attr] = dict(value=value,address=address)
            anchors.append((address,cr.pack(value).hex()))
            self.expected[address] = cr.pack(value)
        self.rr.dictionary.return_value = values, anchors, identity[:2]+(4,)+identity[3:]

    def test_three_resources_map_only_reviewed_current_keys(self):
        self.add_vitals()
        state = self.adapter.snapshot()
        self.assertEqual(set(state["rows"]), set(cr.RESOURCE_SPECS))
        for key,value,address in (("current_health",80,0x606C),("current_mana",20,0x607C),("current_stamina",50,0x604C)):
            row = state["rows"][key]
            self.assertEqual(row["current"],value)
            self.assertEqual(row["target"].address,address)
            self.assertEqual(row["target"].key,key)
            self.assertIsNone(row["maximum"])
            self.assertNotIn((address,cr.pack(value).hex()),row["target"].anchors)

    def test_health_zero_is_readable_but_not_editable_or_resurrectable(self):
        self.add_vitals()
        self.rr.dictionary.return_value[0][1]["value"] = 0.
        anchors = self.rr.dictionary.return_value[1]
        anchors[:] = [(a,cr.pack(0).hex() if a == 0x606C else raw) for a,raw in anchors]
        self.expected[0x606C] = cr.pack(0)
        state = self.adapter.snapshot()
        self.assertEqual(state["rows"]["current_health"]["current"],0)
        self.assertFalse(state["rows"]["current_health"]["can_edit"])
        self.assertTrue(state["rows"]["current_mana"]["can_edit"])

    def test_prepare_uses_selected_resource_methods_and_complete_value_anchors(self):
        self.add_vitals()
        shown = self.adapter.resolve("current_health")
        methods = dict(current="0x1000",max="0x2000",modify="0x3000")
        selected = cr.RESOURCE_SPECS["current_health"]["methods"]
        self.rr.resource_methods.return_value = (methods, selected)
        descriptor = self.adapter.prepare_native(shown,81.)
        self.assertEqual(descriptor["resource_key"],"current_health")
        self.assertEqual(descriptor["address"],"0x606c")
        self.rr.resource_methods.assert_called_once_with(0x3000,"current_health",include_specs=True)
        self.assertEqual(descriptor["method_specs"],selected)
        anchors = {int(a["address"],16):a["expected_hex"] for a in descriptor["anchors"]}
        self.assertEqual(anchors[0x606C],cr.pack(80).hex())
        self.assertEqual(anchors[0x607C],cr.pack(20).hex())

    def test_missing_base200_is_readonly_not_structurally_created(self):
        values, anchors, identity = self.rr.dictionary.return_value
        del values[200]
        state = self.adapter.snapshot()
        self.assertIsNone(state["target"])
        self.assertFalse(state["can_edit"])
        self.assertIn("初始化", state["reason"])

    def test_wrong_owner_and_process_refused(self):
        self.rr.q.side_effect = [0x4000, 0x9999]
        with self.assertRaises(Refused):
            self.adapter.snapshot()
        with patch.object(cr,"process_identity",return_value=("other",2)), self.assertRaises(Refused):
            self.adapter.snapshot()

    def test_combat_or_transition_is_readonly(self):
        self.context.side_effect = cr.AcquisitionContextRefused("combat")
        state = self.adapter.snapshot()
        self.assertFalse(state["target"].can_edit)
        self.assertFalse(state["can_edit"])

    def test_unstable_current_value_is_refused(self):
        self.rr.exact.side_effect = lambda a,n: cr.pack(49) if a == 0x604C else b"\0"
        with self.assertRaises(Refused):
            self.adapter.snapshot()

    def test_native_pending_blocks_before_dispatch(self):
        self.adapter._lock, self.adapter._native = threading.Lock(), Mock()
        with patch("acquisition_adapter.native_calls_pending",return_value=True), self.assertRaises(Refused):
            self.adapter.set_value(target(),51)
        self.adapter._native.set_value.assert_not_called()

    def test_uncertain_native_result_stops_adapter(self):
        self.adapter._lock, self.adapter._native = threading.Lock(), Mock()
        self.adapter._native.set_value.side_effect = UncertainWrite("unknown")
        with patch("acquisition_adapter.native_calls_pending",return_value=False), self.assertRaises(UncertainWrite):
            self.adapter.set_value(target(),51)
        self.assertTrue(self.adapter.blocked)


class MethodTests(unittest.TestCase):
    resource_key = "current_stamina"
    def setUp(self):
        self.rr = cr.StaminaResolver.__new__(cr.StaminaResolver)
        self.rr.module, self.klass, self.table = 0x10000000, 0x1000, 0x2000
        self.rr.anchors, self.memory, self.names = [], {}, {}
        self.put(self.klass+0x98,"Q",self.table)
        self.put(self.klass+0x120,"H",3)
        self.methods = {}
        self.specs = cr.RESOURCE_SPECS[self.resource_key]["methods"]
        for i,(key,spec) in enumerate(self.specs.items()):
            mi, name, ret = 0x3000+i*0x100, 0x5000+i*0x100, 0x7000+i*0x100
            self.methods[key] = mi
            self.put(self.table+i*8,"Q",mi)
            self.put(mi,"Q",self.rr.module+spec["rva"])
            self.put(mi+0x18,"Q",name)
            self.put(mi+0x20,"Q",self.klass)
            self.put(mi+0x28,"Q",ret)
            self.put(mi+0x48,"i",spec["token"])
            self.put(mi+0x4C,"H",0x86)
            self.put(mi+0x52,"B",spec["parameters"])
            self.put(ret+10,"B",spec["return_kind"])
            self.store(self.rr.module+spec["rva"],bytes.fromhex(spec["prefix"]))
            self.names[name] = spec["name"]
        self.rr.reader = SimpleReader(self.memory,self.names)

    def resolve(self):
        return self.rr.resource_methods(self.klass, self.resource_key)

    def store(self,address,data):
        for i,value in enumerate(data):self.memory[address+i] = value

    def put(self,address,fmt,value):
        self.store(address,struct.pack("<"+fmt,value))

    def test_all_three_reviewed_methods_resolve_with_code_anchors(self):
        self.assertEqual(self.resolve(),{k:hex(v) for k,v in self.methods.items()})
        addresses = {a for a,_ in self.rr.anchors}
        self.assertTrue(all(self.rr.module+s["rva"] in addresses for s in self.specs.values()))

    def test_wrong_maximum_getter_signature_fails_closed(self):
        self.put(self.methods["max"]+0x52,"B",1)
        with self.assertRaises(Refused):self.resolve()

    def test_static_or_wrong_class_method_is_rejected(self):
        self.put(self.methods["modify"]+0x4C,"H",0x96)
        with self.assertRaises(Refused):self.resolve()
        self.put(self.methods["modify"]+0x4C,"H",0x86)
        self.put(self.methods["modify"]+0x20,"Q",0x9000)
        with self.assertRaises(Refused):self.resolve()

    def test_getter_code_or_return_type_change_is_rejected(self):
        self.put(0x7000+10,"B",8)
        with self.assertRaises(Refused):self.resolve()
        self.put(0x7000+10,"B",12)
        self.put(self.rr.module+self.specs["current"]["rva"],"B",0)
        with self.assertRaises(Refused):self.resolve()


class HealthMethodTests(MethodTests):
    resource_key = "current_health"


class ManaMethodTests(MethodTests):
    resource_key = "current_mana"


class SimpleReader:
    def __init__(self,memory,names):self.memory,self.names = memory,names
    def read(self,address,size):return bytes(self.memory.get(address+i,0) for i in range(size))
    def string(self,address):return self.names.get(address,"")


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = types.SimpleNamespace(resolver=types.SimpleNamespace(reader=types.SimpleNamespace(pid=98765)),
                                          stamp=("worldapart.exe",12345),record=Mock())
        self.shown, self.after = target(), target(value=51.25,version=2)
        self.descriptor = dict(combat="0x1000",combat_class="0x2000",player="0x3000",dictionary="0x4000",
            address="0x604c",before=50.0,value=51.25,identity_key="a"*64,method_info="0x7000",resource_key="current_stamina",
            methods={"current":"0x7100","max":"0x7200","modify":"0x7000"},
            anchors=[dict(address="0x5000",size=4,expected_hex="00000000")])
        self.adapter = types.SimpleNamespace(prepare_native=Mock(return_value=self.descriptor),resolve=Mock(return_value=self.after))
        patch.object(cn,"initialize_runtime",return_value=Path(self.temp.name)).start()
        patch.dict("sys.modules",frida=types.SimpleNamespace(__version__="17.7.3")).start()
        self.addCleanup(patch.stopall)
        self.bridge = cn.CurrentResourcesNative(self.game,self.adapter)
        self.addCleanup(lambda:cn._LIVE_BRIDGES.discard(self.bridge))
        self.addCleanup(lambda:cn._RETAINED_BRIDGES.discard(self.bridge))
        self.connection = Mock()
        self.connection.script = types.SimpleNamespace(exports_sync=types.SimpleNamespace(submit=Mock()))
        self.behavior = "success"
        self.acquire = patch.object(cn,"acquire_connection",side_effect=self.acquire_connection).start()

    def acquire_connection(self, identity, frida, source, epoch, owner, message, detached, before, check):
        before()
        def submit(request):
            if self.behavior == "rpc_error": raise OSError("transport")
            payload = dict(status="completed",token=request["token"],called=True,result=True,
                           value=51.25,maximum=100.0,before=50.0,identity_key="a"*64,resource_key=request["resource"]["resource_key"])
            if self.behavior == "wrong_value": payload["value"] = 51.5
            elif self.behavior == "getter_reject": payload.update(status="rejected",called=False,reason="real max exceeded")
            elif self.behavior == "setter_false": payload["result"] = False
            elif self.behavior == "bad_max": payload["maximum"] = 50
            elif self.behavior == "exception": payload["status"] = "exception"
            message(dict(type="send",payload=payload),None)
        self.connection.script.exports_sync.submit.side_effect = submit
        return self.connection

    def test_shared_connection_and_true_max_result(self):
        result = self.bridge.set_value(self.shown,51.25)
        self.assertEqual(result["current"],51.25)
        self.assertEqual(result["maximum"],100)
        self.assertTrue(result["verified"])
        self.assertEqual(self.acquire.call_args.args[0],(98765,12345))
        self.assertEqual(self.acquire.call_args.args[3].name,"acquisition-native-epochs.json")
        request = self.connection.script.exports_sync.submit.call_args.args[0]
        self.assertEqual(request["operation"],"current_stamina_set")
        self.assertEqual(request["resource"]["methods"],self.descriptor["methods"])
        self.assertEqual(request["method_token"],0x06014B00)
        self.assertEqual(self.bridge._ledger()["processes"][self.bridge.process_key]["status"],"verified")
        self.connection.release.assert_called_once_with(self.bridge)

    def test_state_change_before_dispatch_never_submits(self):
        self.adapter.prepare_native.side_effect = [self.descriptor,Refused("changed")]
        with self.assertRaises(Refused): self.bridge.set_value(self.shown,51.25)
        self.connection.script.exports_sync.submit.assert_not_called()

    def test_getter_rejection_before_setter_is_proven_not_written(self):
        self.behavior = "getter_reject"
        with self.assertRaises(Refused) as caught: self.bridge.set_value(self.shown,51.25)
        self.assertNotIsInstance(caught.exception,UncertainWrite)
        self.bridge.require_ready()

    def test_setter_false_value_mismatch_or_bad_max_all_block_repeat(self):
        for behavior in ("setter_false","wrong_value","bad_max","exception"):
            with self.subTest(behavior=behavior):
                self.behavior = behavior
                self.bridge.record(dict(status="verified"))
                with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)
                with self.assertRaises(Refused): self.bridge.require_ready()

    def test_rpc_unknown_keeps_connection_and_durable_guard(self):
        self.behavior = "rpc_error"
        with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)
        self.assertTrue(self.bridge._native_inflight)
        self.assertIn(self.bridge,cn._RETAINED_BRIDGES)
        self.connection.release.assert_not_called()
        other = cn.CurrentResourcesNative(self.game,self.adapter)
        self.addCleanup(lambda:cn._LIVE_BRIDGES.discard(other))
        with self.assertRaises(Refused): other.require_ready()

    def test_postwrite_read_failure_is_uncertain(self):
        self.adapter.resolve.side_effect = Refused("read failed")
        with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)

    def test_wrong_player_after_write_is_uncertain(self):
        self.adapter.resolve.return_value = target(value=51.25,identity=("other",))
        with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)

    def test_real_dictionary_version_increment_is_required(self):
        self.adapter.resolve.return_value = target(value=51.25, version=1)
        with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)

    def test_health_and_mana_route_to_distinct_reviewed_native_methods(self):
        for key in ("current_health", "current_mana"):
            with self.subTest(key=key):
                self.bridge.record(dict(status="verified"))
                shown, after = target(key=key), target(key=key, value=51.25, version=2)
                self.descriptor["resource_key"] = key
                self.adapter.resolve.return_value = after
                result = self.bridge.set_value(shown, 51.25)
                request = self.connection.script.exports_sync.submit.call_args.args[0]
                spec = cr.RESOURCE_SPECS[key]
                self.assertEqual(request["operation"], spec["operation"])
                self.assertEqual(request["method_token"], spec["methods"]["modify"]["token"])
                self.assertEqual(request["method_rva"], spec["methods"]["modify"]["rva"])
                self.assertEqual(result["resource_key"], key)

    def test_cross_resource_descriptor_is_refused_before_attach(self):
        self.descriptor["resource_key"] = "current_health"
        with self.assertRaises(Refused): self.bridge.set_value(self.shown, 51.25)
        self.acquire.assert_not_called()

    def test_pending_or_corrupt_journal_prevents_attach(self):
        self.bridge.record(dict(status="pending"))
        with self.assertRaises(Refused): self.bridge.set_value(self.shown,51.25)
        self.bridge.journal.write_text("bad",encoding="utf8")
        with self.assertRaises(Refused): self.bridge.set_value(self.shown,51.25)
        self.acquire.assert_not_called()

    def test_journal_failure_before_dispatch_does_not_submit(self):
        self.bridge.record = Mock(side_effect=OSError("disk full"))
        with self.assertRaises(OSError): self.bridge.set_value(self.shown,51.25)
        self.connection.script.exports_sync.submit.assert_not_called()

    def test_journal_failure_after_write_is_uncertain(self):
        original = self.bridge.record
        def record(event):
            if event["status"] in ("verified","unknown"): raise Refused("disk full")
            original(event)
        self.bridge.record = record
        with self.assertRaises(UncertainWrite): self.bridge.set_value(self.shown,51.25)
        self.assertEqual(self.bridge._ledger()["processes"][self.bridge.process_key]["status"],"pending")


if __name__ == "__main__":
    unittest.main()
