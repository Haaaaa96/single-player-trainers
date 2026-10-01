"""Experience/level semantics and guarded integer edits without any game access."""
from dataclasses import replace
import struct
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from character_attributes_interact import InteractResolver, InteractAttributesAdapter, DATA, limits_for
from acquisition_context import AcquisitionContextRefused
from character_attributes_interact_write import (InteractTarget, InteractWriteOnce, pack,
    parse_attribute_value, validate_attribute_value, set_existing_attribute)
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(InteractTarget("interact:1001", 10, ("player",), ((0x2000, "01000000"),),
                                 1001, address=0x1000, maximum=600), **changes)


class ValueTests(unittest.TestCase):
    def test_integer_input_not_float_or_level(self):
        self.assertEqual(parse_attribute_value(" 600 "), 600)
        self.assertEqual(pack(600), b"X\x02\0\0")
        for value in ("-1", "+1", "1.0", "1e3", "nan", "Infinity", "", "1,000", 1, True):
            with self.subTest(value=value), self.assertRaises(Refused):
                parse_attribute_value(value)

    def test_realm_upper_limit_and_delta(self):
        self.assertEqual(validate_attribute_value(target(), 600), 600)
        self.assertEqual(validate_attribute_value(target(value=500, maximum=1500), 1500), 1500)
        for shown, new in ((target(), 601), (target(), 10.0), (target(), True),
                           (target(maximum=1500), 1011), (target(), -1),
                           (target(value=601), 590), (target(maximum=6000), 11)):
            with self.subTest(shown=shown, new=new), self.assertRaises(Refused):
                validate_attribute_value(shown, new)

    def test_identity_whitelist_noop_and_anchors(self):
        for shown in (target(key="growth:1001"), target(attr_id=2), target(can_edit=False),
                      target(address=0, value=1), target(anchors=()),
                      target(anchors=((0x1000, "00000000"),)), target(address=0x1001)):
            with self.assertRaises(Refused):
                validate_attribute_value(shown, 12)
        with self.assertRaises(Refused):
            validate_attribute_value(target(), 10)
        self.assertEqual(validate_attribute_value(target(address=0, value=0), 1), 1)

    def test_missing_entry_cannot_use_scalar_writer(self):
        with self.assertRaises(Refused):
            InteractWriteOnce(Mock(), ("p", 1), target(address=0, value=0), new_value=1)

    def test_native_pending_blocks_scalar_write(self):
        memory = InteractWriteOnce(Mock(pid=1), ("p", 1), target(), new_value=11)
        with patch("acquisition_adapter.native_calls_pending", return_value=True), self.assertRaises(Refused):
            memory.write_exact(0x1000, pack(11))
        self.assertFalse(memory.used)

    def test_native_becomes_pending_at_final_write_boundary(self):
        memory = InteractWriteOnce(Mock(pid=1), ("p", 1), target(), new_value=11)
        kernel = Mock()
        kernel.OpenProcess.return_value = 123
        def query(handle, address, region, size):
            region._obj.State, region._obj.Type, region._obj.Protect = 0x1000, 0x20000, 4
            region._obj.BaseAddress, region._obj.RegionSize = 0x1000, 0x1000
            return size
        kernel.VirtualQueryEx.side_effect = query
        with patch("character_attributes_write.K", kernel), \
             patch("character_attributes_write.process_identity", return_value=("p", 1)), \
             patch("character_attributes_write.read_exact_handle", side_effect=[bytes.fromhex("01000000"), pack(10)]), \
             patch("acquisition_adapter.native_calls_pending", side_effect=[False, True]), \
             self.assertRaises(Refused):
            memory.write_exact(0x1000, pack(11))
        kernel.WriteProcessMemory.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)


class LevelTests(unittest.TestCase):
    def setUp(self):
        self.levels = DATA["attributes"]["1001"]["levels"]

    def test_level_threshold_is_inclusive(self):
        self.assertEqual(limits_for(self.levels, 2, 99), (1, 12, 1500))
        self.assertEqual(limits_for(self.levels, 2, 100), (2, 12, 1500))
        self.assertEqual(limits_for(self.levels, 2, 569), (6, 12, 1500))

    def test_sequential_realm_gate_does_not_skip_locked_level(self):
        # Level 15 has realmId=2 in real config, after two realmId=3 entries.
        # Native code stops at the first locked entry instead of filtering all.
        self.assertEqual(limits_for(self.levels, 2, 2100), (12, 12, 1500))
        self.assertEqual(limits_for(self.levels, 1, 600), (6, 6, 600))
        self.assertEqual(limits_for(self.levels, 3, 2700), (18, 18, 2700))

    def test_terminal_zero_threshold_does_not_mean_zero_maximum(self):
        self.assertEqual(self.levels[-1]["maxExp"], 0)
        self.assertEqual(limits_for(self.levels, 4, 5700), (25, 25, 5700))
        self.assertEqual(limits_for(self.levels, 5, 0), (1, 25, 5700))

    def test_unknown_realm_does_not_unlock_everything(self):
        for realm in (0, -1, None, True):
            with self.assertRaises(Refused):
                limits_for(self.levels, realm, 0)

    def test_all_five_configs_have_reviewed_ids_and_thresholds(self):
        self.assertEqual(set(DATA["attributes"]), {"1001", "1002", "1003", "1004", "1005"})
        self.assertEqual([DATA["attributes"][str(i)]["name"] for i in range(1001, 1006)],
                         ["灵机", "体魄", "神识", "辩道", "医术"])
        for row in DATA["attributes"].values():
            self.assertEqual(row["levels"], self.levels)


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.r = InteractResolver.__new__(InteractResolver)
        self.r.anchors = []
        self.data = bytearray(0x10000)
        self.r.reader = Mock(read=lambda address, size: bytes(self.data[address:address + size]))
        self.dictionary, self.array = 0x1000, 0x2000
        self.dc, self.ac, self.ec = {}, {"klass": "0x3000"}, {"instance_size": 32}
        self.r.obj = lambda address, fullname: self.dc if address == self.dictionary else self.ac
        self.r.info = lambda *args: self.ec
        offsets = {"_entries": 24, "_count": 32, "_freeCount": 40, "_version": 44,
                   "hashCode": 16, "next": 20, "key": 24, "value": 28}
        self.r.reviewed_field = lambda c, name, kind: offsets[name]
        self.put(self.dictionary + 24, "Q", self.array)
        self.put(self.dictionary + 32, "i", 2)
        self.put(self.dictionary + 44, "i", 12)
        self.put(self.array + 24, "Q", 3)
        self.data[self.array + 32:self.array + 64] = struct.pack("<iiiiiiii", 1001, -1, 1001, 569, 1002, -1, 1002, 13)

    def put(self, address, fmt, value):
        raw = struct.pack("<" + fmt, value)
        self.data[address:address + len(raw)] = raw

    def test_exact_integer_values_and_value_bytes_separate_from_identity(self):
        values, anchors, identity = self.r.dictionary(self.dictionary)
        self.assertEqual(values[1001], dict(value=569, address=self.array + 44))
        self.assertEqual(anchors[0][1], pack(569).hex())
        self.assertEqual(identity[-1], 12)
        self.assertNotIn(anchors[0], self.r.anchors)

    def test_null_or_unallocated_dictionary_has_no_direct_target(self):
        self.assertEqual(self.r.dictionary(0), ({}, [], (0, 0, 0, 0, 0)))
        self.put(self.dictionary + 24, "Q", 0)
        self.put(self.dictionary + 32, "i", 0)
        self.assertEqual(self.r.dictionary(self.dictionary)[0], {})

    def test_unknown_id_negative_value_duplicate_and_counter_mismatch(self):
        for offset, value in ((self.array + 56, 1001), (self.array + 56, 9999),
                              (self.array + 44, -1), (self.dictionary + 40, 1),
                              (self.array + 36, 2)):
            before = bytes(self.data)
            self.put(offset, "i", value)
            with self.subTest(offset=offset), self.assertRaises(Refused):
                self.r.dictionary(self.dictionary)
            self.data[:] = before

    def test_free_slot_is_not_mistaken_for_an_attribute(self):
        self.put(self.array + 48, "i", -1)
        self.put(self.dictionary + 40, "i", 1)
        values, _, _ = self.r.dictionary(self.dictionary)
        self.assertEqual(set(values), {1001})


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.r = InteractResolver.__new__(InteractResolver)
        self.r.tables = Mock(return_value=(0x1000, {}))
        self.r.table_rows = Mock(side_effect=lambda _t, _tc, suffix, maximum: self.rows[suffix])
        self.rows = {"CultivateLayer": {7: (0x2000, {})}, "CultivatePhase": {2: (0x3000, {})},
                     "CultivateRealm": {2: (0x4000, {})}, "InteractAttribute": {}}
        self.ints, self.pointers, self.lists = {0x2000: 2, 0x3000: 2}, {}, {}
        for attr_id in range(1001, 1006):
            pointer = 0x10000 + attr_id * 0x1000
            self.rows["InteractAttribute"][attr_id] = pointer, {}
            self.pointers[pointer] = pointer + 0x100
            self.lists[pointer + 0x100] = []
            for index, level in enumerate(DATA["attributes"][str(attr_id)]["levels"]):
                config = pointer + 0x200 + index * 32
                self.lists[pointer + 0x100].append(config)
                self.ints[config] = level["maxExp"]
                self.ints[config + 4] = level["realmId"]
        self.r.reviewed_field = lambda c, name, kind: 4 if name == "<realmId>k__BackingField" else 0
        self.r.list_objects = lambda pointer, maximum: self.lists[pointer]
        self.r.q = lambda pointer, **kwargs: self.pointers[pointer]
        self.r.i = lambda pointer, **kwargs: self.ints[pointer]
        self.r.obj = lambda *args: {}

    def test_current_layer_to_phase_to_realm_and_all_five_configs(self):
        tables, realm, levels = self.r.configuration(7)
        self.assertEqual((tables, realm), (0x1000, 2))
        self.assertEqual(len(levels), 5)
        self.assertEqual(limits_for(levels[1003], realm, 258), (3, 12, 1500))

    def test_missing_current_realm_or_level_table_rejected(self):
        with self.assertRaises(Refused):
            self.r.configuration(8)
        self.rows["CultivateRealm"].clear()
        with self.assertRaises(Refused):
            self.r.configuration(7)

    def test_changed_config_threshold_and_extra_attribute_rejected(self):
        pointer = next(iter(self.lists.values()))[0]
        self.ints[pointer] = 101
        with self.assertRaises(Refused):
            self.r.configuration(7)
        self.ints[pointer] = 100
        self.rows["InteractAttribute"][1006] = 0xDEAD, {}
        with self.assertRaises(Refused):
            self.r.configuration(7)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.stamp = ("worldapart.exe", 1)
        self.adapter = InteractAttributesAdapter.__new__(InteractAttributesAdapter)
        self.adapter.blocked, self.adapter._lock = False, threading.Lock()
        raw = dict(anchor_verified=True, manager=0x3000, store=0x4000, world=0x5000,
                   player=0x1000, anchors=[dict(address=0x9000, expected_hex="00")])
        self.adapter.game = SimpleNamespace(blocked=False, stamp=self.stamp,
            resolver=SimpleNamespace(resolve=Mock(return_value=raw), reader=Mock(h=123)))
        self.adapter._native = Mock()
        self.r = Mock(anchors=[], reader=Mock(h=123))
        self.adapter.resolver = self.r
        self.r.obj.return_value = {"klass": "0x8000"}
        fields = {"combat": 0x48, "<CurrentLayerId>k__BackingField": 0x60,
                  "<PendingRealmBreakthrough>k__BackingField": 0x70,
                  "_cultivateInjectBatchDepth": 0x78, "interactAttributes": 0x1A8}
        self.r.reviewed_field.side_effect = lambda c, name, kind: fields[name]
        self.pointers = {0x1048: 0x2000, 0x2010: 0x1000, 0x2070: 0, 0x11A8: 0x6000}
        self.ints = {0x2060: 7, 0x2078: 0}
        self.r.q.side_effect = lambda address, **kw: self.pointers[address]
        self.r.i.side_effect = lambda address, **kw: self.ints[address]
        self.r.dictionary.return_value = ({1001: dict(value=569, address=0x7000)},
                [(0x7000, pack(569).hex())], (0x6000, 0x6800, 1, 0, 3))
        self.r.configuration.return_value = (0xA000, 2,
            {int(k): v["levels"] for k, v in DATA["attributes"].items()})
        self.r.exact.side_effect = lambda address, size: pack(569) if address == 0x7000 else b"\0" * size
        stamp_patch = patch("character_attributes_interact.process_identity", return_value=self.stamp)
        stamp_patch.start()
        self.addCleanup(stamp_patch.stop)
        context_patch = patch("character_attributes_interact.require_safe_acquisition_context", return_value={"anchors": []})
        self.context = context_patch.start()
        self.addCleanup(context_patch.stop)

    def test_snapshot_pins_owner_layer_and_excludes_only_edited_value(self):
        state = self.adapter.snapshot()
        target = state["rows"]["interact:1001"]["target"]
        other = state["rows"]["interact:1002"]["target"]
        self.assertEqual((target.value, target.maximum), (569, 1500))
        self.assertEqual(state["rows"][target.key]["display_value"], 6)
        self.assertEqual(target.identity[7], 7)
        self.assertNotIn((0x7000, pack(569).hex()), target.anchors)
        self.assertIn((0x7000, pack(569).hex()), other.anchors)
        self.assertEqual((other.value, other.address), (0, 0))

    def test_unsafe_scene_and_breakthrough_keep_all_targets_read_only(self):
        self.context.side_effect = AcquisitionContextRefused("battle")
        self.assertFalse(self.adapter.snapshot()["can_edit"])
        self.context.side_effect = None
        self.pointers[0x2070] = 0xB000
        state = self.adapter.snapshot()
        self.assertFalse(state["can_edit"])
        self.assertTrue(all(not row["target"].can_edit for row in state["rows"].values()))

    def test_wrong_owner_and_changed_read_are_refused(self):
        self.pointers[0x2010] = 0xB000
        with self.assertRaises(Refused):
            self.adapter.snapshot()
        self.pointers[0x2010] = 0x1000
        self.r.exact.return_value = b"\x01"
        self.r.exact.side_effect = None
        with self.assertRaises(Refused):
            self.adapter.snapshot()

    def test_unknown_write_stops_adapter_and_native_pending_blocks_entry(self):
        shown = target()
        with patch("acquisition_adapter.native_calls_pending", return_value=True), self.assertRaises(Refused):
            self.adapter.set_value(shown, 11)
        self.adapter._native.require_ready.assert_not_called()
        with patch("acquisition_adapter.native_calls_pending", return_value=False), \
             patch("character_attributes_interact.InteractWriteOnce"), \
             patch("character_attributes_interact.set_existing_attribute", side_effect=UncertainWrite("partial")), \
             self.assertRaises(UncertainWrite):
            self.adapter.set_value(shown, 11)
        self.assertTrue(self.adapter.blocked)


class WriteFlowTests(unittest.TestCase):
    def setUp(self):
        self.shown = target()
        self.current, self.value = self.shown, pack(self.shown.value)
        self.memory, self.record = Mock(), Mock()
        self.memory.read_exact.side_effect = lambda *args: self.value
        def write(address, raw):
            self.value = raw
            self.current = replace(self.shown, value=struct.unpack("<i", raw)[0])
        self.memory.write_exact.side_effect = write
        self.resolve = Mock(side_effect=lambda key: self.current)

    def edit(self):
        return set_existing_attribute(self.memory, self.resolve, self.shown, 11, self.record)

    def test_one_integer_write_with_readback(self):
        self.assertEqual(self.edit().value, 11)
        self.memory.write_exact.assert_called_once_with(0x1000, b"\x0b\0\0\0")
        self.assertEqual([c.args[0]["status"] for c in self.record.call_args_list], ["attempt", "verified"])

    def test_changed_realm_or_identity_after_journal_has_no_write(self):
        self.record.side_effect = lambda event: setattr(self, "current", replace(self.shown, maximum=1500))
        with self.assertRaises(Refused):
            self.edit()
        self.memory.write_exact.assert_not_called()

    def test_attempt_log_must_be_durable_before_write(self):
        self.record.side_effect = OSError("disk full")
        with self.assertRaises(OSError):
            self.edit()
        self.memory.write_exact.assert_not_called()

    def test_unknown_and_failed_unknown_journal_never_become_refused(self):
        for error in (UncertainWrite("partial"), OSError("failed write")):
            self.memory.write_exact.side_effect = error
            self.record.side_effect = [None, Refused("journal corrupt")]
            with self.assertRaises(UncertainWrite):
                self.edit()

    def test_readback_or_postwrite_log_failure_is_uncertain(self):
        self.memory.write_exact.side_effect = lambda *args: None
        with self.assertRaises(UncertainWrite):
            self.edit()
        self.setUp()
        self.record.side_effect = [None, Refused("journal corrupt"), OSError("disk full")]
        with self.assertRaises(UncertainWrite):
            self.edit()
        self.assertEqual(self.value, pack(11))


if __name__ == "__main__":
    unittest.main()
