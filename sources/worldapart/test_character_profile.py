"""Synthetic scalar safety tests; no game process is opened."""
from contextlib import nullcontext
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import character_profile as cp
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(cp.ProfileTarget("reserve_exp", 100, 0x4074, ("player",),
                                    ((0x100, "00"),), 0, 1_000_000), **changes)


class ProfileValueTests(unittest.TestCase):
    def test_integer_parser_rejects_decimal_exponent_bool_and_unbounded_text(self):
        self.assertEqual(cp.parse_profile_value(" 123 "), 123)
        for text in ("", "1.0", "1e3", True, 1, "+1", "1,000", "12345678", "1" * 21):
            with self.subTest(text=text), self.assertRaises(Refused):
                cp.parse_profile_value(text)

    def test_reserve_has_nonnegative_range_and_thousand_change_limit(self):
        self.assertEqual(cp.validate_profile_value(target(), 1100), 1100)
        self.assertEqual(cp.validate_profile_value(target(value=999_999), 1_000_000), 1_000_000)
        for value in (-1, 1101, 100, 1_000_001, True, 101.0):
            with self.subTest(value=value), self.assertRaises(Refused):
                cp.validate_profile_value(target(), value)

    def test_forged_policy_identity_and_overlapping_anchor_are_rejected(self):
        for changes in (dict(key="unknown"), dict(minimum=-1), dict(maximum=2_000_000),
                        dict(can_edit=False), dict(address=0), dict(address=0x4075),
                        dict(identity=()), dict(anchors=()), dict(anchors=((0x4073,"0000"),)),
                        dict(anchors=((0x100,"nothex"),)), dict(anchors=((0,"00"),))):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                cp.validate_profile_value(target(**changes), 101)

    def test_old_alignment_field_is_not_an_editable_profile_scalar(self):
        self.assertEqual(set(cp.FIELDS), {"reserve_exp"})
        with self.assertRaises(Refused):
            cp.validate_profile_value(target(key="prop_evil"), 101)

    def test_dynamic_realm_limit_is_enforced_below_tool_limit(self):
        shown = target(value=5900,maximum=6000)
        self.assertEqual(cp.validate_profile_value(shown,6000),6000)
        with self.assertRaises(Refused):cp.validate_profile_value(shown,6001)
        for maximum in (0,-1,1_000_001,True):
            with self.subTest(maximum=maximum),self.assertRaises(Refused):
                cp.validate_profile_value(target(maximum=maximum),101)

    def test_writer_uses_exact_int32_and_inherited_cross_host_guard(self):
        writer = cp.ProfileWriteOnce(Mock(), ("path", 1), target(), new_value=101)
        self.assertEqual(writer.before, struct.pack("<i", 100))
        self.assertEqual(writer.after, struct.pack("<i", 101))
        self.assertIs(cp.ProfileWriteOnce.write_exact, cp.AttributeWriteOnce.write_exact)
        self.assertTrue(writer.write_exact._scalar_coordinated)


class ProfileWriteTests(unittest.TestCase):
    def setUp(self):
        self.shown, self.current = target(), target()
        self.data = cp.pack(self.shown.value)
        self.memory, self.record = Mock(), Mock()
        self.memory.read_exact.side_effect = lambda a,n:self.data
        def write(a,data):
            self.data = data
            self.current = replace(self.shown, value=struct.unpack("<i",data)[0])
        self.memory.write_exact.side_effect = write
        self.resolve = Mock(side_effect=lambda key:self.current)

    def run_edit(self):
        return cp.set_profile_scalar(self.memory,self.resolve,self.shown,101,self.record)

    def test_exact_four_byte_write_and_verified_readback(self):
        self.assertEqual(self.run_edit().value, 101)
        self.memory.write_exact.assert_called_once_with(self.shown.address, cp.pack(101))
        self.assertEqual([c.args[0]["status"] for c in self.record.call_args_list], ["attempt","verified"])

    def test_stale_identity_or_value_never_writes(self):
        self.current = replace(self.shown, identity=("other",))
        with self.assertRaises(Refused):self.run_edit()
        self.current = self.shown
        self.data = cp.pack(102)
        with self.assertRaises(Refused):self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_context_changed_after_durable_attempt_is_rejected(self):
        self.record.side_effect = lambda e:setattr(self,"current",replace(self.shown,can_edit=False))
        with self.assertRaises(Refused):self.run_edit()
        self.memory.write_exact.assert_not_called()
        self.assertEqual(self.record.call_args.args[0]["status"],"rejected")

    def test_attempt_journal_failure_prevents_write(self):
        self.record.side_effect = OSError("disk")
        with self.assertRaises(OSError):self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_unknown_log_failure_never_masks_original_uncertain(self):
        error = UncertainWrite("partial")
        self.memory.write_exact.side_effect = error
        self.record.side_effect = [None,OSError("disk")]
        with self.assertRaises(UncertainWrite) as caught:self.run_edit()
        self.assertIs(caught.exception,error)
        self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_unexpected_writer_exception_is_unknown(self):
        self.memory.write_exact.side_effect = OSError("possibly partial")
        with self.assertRaises(UncertainWrite):self.run_edit()
        self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_proven_no_write_is_rejected(self):
        self.memory.write_exact.side_effect = Refused("changed")
        with self.assertRaises(Refused) as caught:self.run_edit()
        self.assertNotIsInstance(caught.exception,UncertainWrite)
        self.assertEqual(self.record.call_args.args[0]["status"],"rejected")

    def test_postwrite_identity_change_or_read_failure_is_unknown(self):
        for result in (replace(self.shown,value=101,identity=("other",)), OSError("read")):
            with self.subTest(result=result):
                self.setUp()
                self.resolve.side_effect = [self.shown,self.shown,result]
                with self.assertRaises(UncertainWrite):self.run_edit()
                self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_verified_and_unknown_journal_failures_remain_uncertain(self):
        self.record.side_effect = [None,OSError("disk"),OSError("disk")]
        with self.assertRaises(UncertainWrite):self.run_edit()
        self.memory.write_exact.assert_called_once()


class ProfileJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = cp.CharacterProfileAdapter.__new__(cp.CharacterProfileAdapter)
        self.adapter.journal = Path(self.tmp.name)/"profile.json"
        self.adapter.game = SimpleNamespace(resolver=SimpleNamespace(reader=SimpleNamespace(pid=123)),stamp=("game",456),record=Mock())
        self.adapter.blocked,self.adapter._lock = False,threading.Lock()

    def test_atomic_journal_contains_identity_and_pending_blocks_new_adapter(self):
        self.adapter.require_ready()
        self.adapter.record(dict(status="attempt"))
        data = json.loads(self.adapter.journal.read_text(encoding="utf8"))
        self.assertEqual(data["process_key"],[123,456])
        self.assertEqual(data["version"],1)
        with self.assertRaises(Refused):self.adapter.require_ready()
        for status in ("verified","rejected"):
            self.adapter.record(dict(status=status))
            self.adapter.require_ready()

    def test_corrupt_wrong_identity_and_unknown_journal_fail_closed(self):
        for data in ("bad",json.dumps(dict(version=1,process_key=[123,999],status="verified")),
                     json.dumps(dict(version=1,process_key=[123,456],status="unknown"))):
            self.adapter.journal.write_text(data,encoding="utf8")
            with self.assertRaises(Refused):self.adapter.require_ready()

    def test_native_pending_stops_before_writer_or_journal(self):
        with patch("native_broker.startup_lock",return_value=nullcontext()), \
             patch("acquisition_adapter.native_calls_pending",return_value=True), \
             patch.object(cp,"ProfileWriteOnce") as writer, self.assertRaises(Refused):
            self.adapter.set_value(target(),101)
        writer.assert_not_called()
        self.assertFalse(self.adapter.journal.exists())
        self.assertTrue(self.adapter._lock.acquire(blocking=False))
        self.adapter._lock.release()


    def test_uncertain_flow_permanently_blocks_adapter_and_releases_local_lock(self):
        with patch("native_broker.startup_lock",return_value=nullcontext()), \
             patch("acquisition_adapter.native_calls_pending",return_value=False), \
             patch.object(cp,"ProfileWriteOnce"), \
             patch.object(cp,"set_profile_scalar",side_effect=UncertainWrite("unknown")), self.assertRaises(UncertainWrite):
            self.adapter.set_value(target(),101)
        self.assertTrue(self.adapter.blocked)
        self.assertTrue(self.adapter._lock.acquire(blocking=False))
        self.adapter._lock.release()


class ProfileLimitTests(unittest.TestCase):
    def setUp(self):
        self.resolver = cp.ProfileResolver.__new__(cp.ProfileResolver)
        rr = self.resolver
        rr.module,rr.anchors = 0x100000,[]
        rr.exact = Mock(return_value=bytes.fromhex("40534883ec20803d1375080700488bd9"))
        rr.tables = Mock(return_value=(0x5000,{"table":"root"}))
        self.rows = {"CultivateLayer":{1:(0x6000,{"kind":"layer"})},
                     "CultivatePhase":{2:(0x7000,{"kind":"phase"})},
                     "CultivateRealm":{3:(0x8000,{"kind":"realm"})}}
        rr.table_rows = Mock(side_effect=lambda tables,tc,suffix,limit:self.rows[suffix])
        self.offsets = {"<phase>k__BackingField":0x20,"<realm>k__BackingField":0x24,
                        "<cultivate_reserve_exp_limit>k__BackingField":0xC0}
        rr.reviewed_field = Mock(side_effect=lambda klass,name,kind:self.offsets[name])
        self.values = {0x6020:2,0x7024:3,0x80C0:6000}
        def integer(address,anchored=False):
            value = self.values[address]
            if anchored:rr.anchors.append((address,cp.pack(value).hex()))
            return value
        rr.i = Mock(side_effect=integer)

    def test_realm_mapping_and_limit_are_all_anchored(self):
        self.assertEqual(self.resolver.reserve_limit(1),(0x5000,3,6000))
        self.assertEqual(self.resolver.anchors,[(0x100000+0x14C4D00,"40534883ec20803d1375080700488bd9"),(0x6020,cp.pack(2).hex()),
                         (0x7024,cp.pack(3).hex()),(0x80C0,cp.pack(6000).hex())])

    def test_changed_getter_code_and_unreviewed_layout_refuse(self):
        self.resolver.exact.return_value = b"\0"*16
        with self.assertRaises(Refused):self.resolver.reserve_limit(1)
        self.resolver.tables.assert_not_called()
        self.resolver.exact.return_value = bytes.fromhex("40534883ec20803d1375080700488bd9")
        self.offsets["<cultivate_reserve_exp_limit>k__BackingField"] = 0xC4
        with self.assertRaises(Refused):self.resolver.reserve_limit(1)

    def test_missing_layer_phase_realm_and_invalid_limit_refuse(self):
        for address,value in ((0x6020,99),(0x7024,99),(0x7024,0),(0x80C0,0),(0x80C0,-1)):
            with self.subTest(address=address,value=value):
                old = self.values[address]
                self.values[address] = value
                with self.assertRaises(Refused):self.resolver.reserve_limit(1)
                self.values[address] = old
        with self.assertRaises(Refused):self.resolver.reserve_limit(99)


class ProfileSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.adapter = cp.CharacterProfileAdapter.__new__(cp.CharacterProfileAdapter)
        self.raw = dict(anchor_verified=True,anchors=[dict(address=0x100,expected_hex="00")],
                        player=0x2000,manager=1,store=2,world=3)
        self.game = SimpleNamespace(resolver=SimpleNamespace(resolve=Mock(return_value=self.raw)),blocked=False,stamp=("game",1))
        self.adapter.game,self.adapter.blocked = self.game,False
        rr = self.adapter.resolver = Mock()
        self.rr = rr
        rr.reader.h = 10
        self.pc = {"namespace":"Game","name":"PlayerModel","fields":[]}
        self.cc = {"namespace":"Game","name":"CombatModel","fields":[dict(name="<CultivateReserveExp>k__BackingField",token="0x0400AD3B")]}
        rr.runtime_spec.return_value = {"fields":[dict(name="<CultivateReserveExp>k__BackingField",token=0x0400AD3B)]}
        rr.obj.side_effect = lambda pointer,name:self.pc if pointer==0x2000 else self.cc
        self.offsets = {"combat":0x20,"<CurrentLayerId>k__BackingField":0x60,
                        "<PendingRealmBreakthrough>k__BackingField":0xA0,"_cultivateInjectBatchDepth":0x100,
                        "<CultivateReserveExp>k__BackingField":0x74}
        rr.reviewed_field.side_effect = lambda c,name,kind:self.offsets[name]
        self.values = {0x2020:(0x4000,"Q"),0x4010:(0x2000,"Q"),0x4060:(1,"i"),
                       0x40A0:(0,"Q"),0x4100:(0,"i"),0x4074:(100,"i"),0x80C0:(6000,"i")}
        def read(address,anchored=False):
            value,fmt = self.values[address]
            if anchored:rr.anchors.append((address,struct.pack("<"+fmt,value).hex()))
            return value
        rr.q.side_effect = rr.i.side_effect = read
        def limit(layer):
            native = read(0x80C0,True)
            return 0x5000,3,native
        rr.reserve_limit.side_effect = limit
        def exact(address,size):
            if address==0x100:return b"\0"
            value,fmt = self.values[address]
            return struct.pack("<"+fmt,value)
        rr.exact.side_effect = exact
        self.context = patch.object(cp,"require_safe_acquisition_context",return_value=dict(anchors=[])).start()
        self.stamp = patch.object(cp,"process_identity",return_value=self.game.stamp).start()
        self.addCleanup(patch.stopall)

    def test_only_reserve_is_exposed_with_current_realm_limit_and_anchors(self):
        state = self.adapter.snapshot()
        self.assertEqual(set(state["rows"]),{"reserve_exp"})
        row = state["rows"]["reserve_exp"]
        shown = row["target"]
        self.assertEqual((shown.value,shown.maximum,shown.address),(100,6000,0x4074))
        self.assertEqual(shown.identity[-3:],(0x5000,3,6000))
        self.assertIn((0x80C0,cp.pack(6000).hex()),shown.anchors)
        self.assertFalse(any(a<=shown.address<a+len(bytes.fromhex(raw)) for a,raw in shown.anchors))
        self.assertIn("6000",row["limit_source"])

    def test_tool_cap_and_out_of_current_realm_range_are_readonly(self):
        self.values[0x80C0] = 2_000_000,"i"
        self.assertEqual(self.adapter.resolve("reserve_exp").maximum,1_000_000)
        self.values[0x80C0] = 99,"i"
        self.assertFalse(self.adapter.resolve("reserve_exp").can_edit)

    def test_scene_pending_breakthrough_and_injection_block_edit(self):
        self.context.side_effect = cp.AcquisitionContextRefused("combat")
        self.assertFalse(self.adapter.resolve("reserve_exp").can_edit)
        self.context.side_effect = None
        for address,fmt in ((0x40A0,"Q"),(0x4100,"i")):
            self.values[address] = 1,fmt
            self.assertFalse(self.adapter.resolve("reserve_exp").can_edit)
            self.values[address] = 0,fmt

    def test_wrong_owner_metadata_offset_and_token_fail_closed(self):
        self.values[0x4010] = 0x9000,"Q"
        with self.assertRaises(Refused):self.adapter.snapshot()
        self.values[0x4010] = 0x2000,"Q"
        self.offsets["<CultivateReserveExp>k__BackingField"] = 0x78
        with self.assertRaises(Refused):self.adapter.snapshot()
        self.offsets["<CultivateReserveExp>k__BackingField"] = 0x74
        self.cc["fields"][0]["token"] = "0x04000001"
        with self.assertRaises(Refused):self.adapter.snapshot()

    def test_changed_value_or_process_during_snapshot_is_refused(self):
        self.rr.exact.side_effect = lambda address,size:b"\0"*size
        with self.assertRaises(Refused):self.adapter.snapshot()
        self.stamp.return_value = ("game",2)
        with self.assertRaises(Refused):self.adapter.snapshot()

if __name__ == "__main__":unittest.main()
