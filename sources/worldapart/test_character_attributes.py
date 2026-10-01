"""Synthetic-memory checks for bounded growth edits and structural guards."""
from dataclasses import replace
import struct
import unittest
from unittest.mock import Mock, patch

from character_attributes import AttributeResolver, SPECS
from character_attributes_write import (AttributeTarget, AttributeWriteOnce, pack,
    parse_attribute_value, validate_attribute_value, set_existing_attribute,
    ATTRIBUTE_NAMES, PERCENTAGE_IDS, attribute_maximum, to_display_value, from_display_value)
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(AttributeTarget("growth:2", 10.0, ("player",), ((0x2000, "01000000"),),
                                   2, address=0x1000), **changes)


class ValueTests(unittest.TestCase):
    def percent_target(self, attr_id=111, value=0.):
        return target(key=f"growth:{attr_id}", attr_id=attr_id, value=value,
                      maximum=attribute_maximum(attr_id))

    def test_reviewed_extended_whitelist_does_not_include_current_or_lifespan(self):
        self.assertEqual(set(ATTRIBUTE_NAMES), {2, 3, 4, 5, 6, 7, 21, 22, 24, 201,
                                               111, 112, 113, 114, 115, 116})
        for excluded in (1, 8, 23, 25, 200, 999):
            with self.subTest(attr_id=excluded), self.assertRaises(Refused):
                validate_attribute_value(target(key=f"growth:{excluded}", attr_id=excluded), 11)

    def test_percentage_uses_percentage_points_and_float32_storage(self):
        for attr_id in PERCENTAGE_IDS:
            shown = self.percent_target(attr_id)
            value = from_display_value(shown, parse_attribute_value("1.25"))
            self.assertEqual(value, .0125)
            self.assertEqual(pack(validate_attribute_value(shown, value)), pack(.0125))
            self.assertEqual(to_display_value(shown, .0125), 1.25)

    def test_percentage_policy_cannot_be_widened_by_forged_target(self):
        for attr_id in PERCENTAGE_IDS:
            shown = self.percent_target(attr_id)
            with self.subTest(attr_id=attr_id), self.assertRaises(Refused):
                validate_attribute_value(replace(shown, maximum=1_000_000), .01)

    def test_percentage_step_and_endpoint_rounding(self):
        shown = self.percent_target(value=struct.unpack('<f', pack(.7))[0])
        self.assertEqual(pack(validate_attribute_value(shown, .8)), pack(.8))
        self.assertEqual(pack(validate_attribute_value(shown, .6)), pack(.6))
        with self.assertRaises(Refused):
            validate_attribute_value(shown, .8001)
        with self.assertRaises(Refused):
            validate_attribute_value(self.percent_target(value=.95), 1.01)
        self.assertEqual(pack(validate_attribute_value(self.percent_target(112, 2.9), 3.0)), pack(3.0))

    def test_move_speed_range_step_and_units(self):
        shown = target(key="growth:7", attr_id=7, value=9, maximum=10)
        self.assertEqual(validate_attribute_value(shown, 10), 10)
        self.assertEqual(to_display_value(shown, 10), 10)
        self.assertEqual(from_display_value(shown, 10), 10)
        for value in (10.01, 7.99):
            with self.assertRaises(Refused):
                validate_attribute_value(shown, value)

    def test_nonfinite_percentage_input_refused_before_conversion(self):
        for value in (True, float('nan'), float('inf')):
            with self.assertRaises(Refused):
                from_display_value(self.percent_target(), value)

    def test_decimal_input(self):
        self.assertEqual(parse_attribute_value(" 123.45 "), 123.45)

    def test_unsupported_text(self):
        for value in ("-1", "+1", "1e3", "1.001", "nan", "Infinity", "", "1,000", 1, True):
            with self.subTest(value=value), self.assertRaises(Refused):
                parse_attribute_value(value)

    def test_absolute_value_and_float32(self):
        self.assertEqual(validate_attribute_value(target(), 10.25), 10.25)
        self.assertEqual(pack(validate_attribute_value(target(), 10.01)), pack(10.01))

    def test_limits_and_single_change(self):
        for new in (-1, 1010.01, 1_000_001, float("nan"), float("inf"), True):
            with self.subTest(value=new), self.assertRaises(Refused):
                validate_attribute_value(target(), new)
        self.assertEqual(validate_attribute_value(target(), 1010), 1010)
        self.assertEqual(validate_attribute_value(target(value=999_999), 1_000_000), 1_000_000)

    def test_nonwhitelisted_id_and_key(self):
        for shown in (target(attr_id=1), target(key="base:2"), target(can_edit=False)):
            with self.assertRaises(Refused):
                validate_attribute_value(shown, 11)

    def test_missing_entry_only_zero_before(self):
        self.assertEqual(validate_attribute_value(target(address=0, value=0), 1000), 1000)
        with self.assertRaises(Refused):
            validate_attribute_value(target(address=0, value=10), 11)

    def test_existing_writer_cannot_create_entry(self):
        with self.assertRaises(Refused):
            AttributeWriteOnce(Mock(), ("p", 1), target(address=0, value=0), new_value=1)

    def test_noop_and_float32_rounding_noop(self):
        for shown, new in ((target(), 10), (target(value=999_999), 999_999.01)):
            with self.assertRaises(Refused):
                validate_attribute_value(shown, new)

    def test_anchors_must_not_overlap_edit(self):
        for anchors in ((), ((0x1000, "00000000"),), ((0xFFF, "000000"),), ((0, "00"),)):
            with self.assertRaises(Refused):
                validate_attribute_value(target(anchors=anchors), 11)


class WriteFlowTests(unittest.TestCase):
    def setUp(self):
        self.shown = target()
        self.current = self.shown
        self.memory = Mock()
        self.value = pack(10)
        self.memory.read_exact.side_effect = lambda address, size: self.value
        def write(address, raw):
            self.value = raw
            self.current = replace(self.shown, value=struct.unpack("<f", raw)[0])
        self.memory.write_exact.side_effect = write
        self.resolve = Mock(side_effect=lambda key: self.current)
        self.record = Mock()

    def run_edit(self):
        return set_existing_attribute(self.memory, self.resolve, self.shown, 11, self.record)

    def test_one_exact_write_with_readback(self):
        result = self.run_edit()
        self.assertEqual(result.value, 11)
        self.memory.write_exact.assert_called_once_with(0x1000, pack(11))
        self.assertEqual([x.args[0]["status"] for x in self.record.call_args_list], ["attempt", "verified"])

    def test_identity_change_before_write(self):
        self.current = replace(self.shown, identity=("other_player",))
        with self.assertRaises(Refused):
            self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_context_change_after_journal(self):
        self.record.side_effect = lambda event: setattr(self, "current", replace(self.shown, can_edit=False))
        with self.assertRaises(Refused):
            self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_uncertain_write_is_never_logged_rejected(self):
        self.memory.write_exact.side_effect = UncertainWrite("partial")
        with self.assertRaises(UncertainWrite):
            self.run_edit()
        self.assertEqual(self.record.call_args.args[0]["status"], "unknown")

    def test_readback_failure_is_uncertain(self):
        self.memory.write_exact.side_effect = lambda *args: None
        with self.assertRaises(UncertainWrite):
            self.run_edit()
        self.assertEqual(self.memory.write_exact.call_count, 1)

    def test_journal_failure_before_write_has_no_mutation(self):
        self.record.side_effect = OSError("disk full")
        with self.assertRaises(OSError):
            self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_failed_unknown_log_preserves_uncertain_write(self):
        self.memory.write_exact.side_effect = UncertainWrite("partial")
        self.record.side_effect = [None, Refused("corrupt journal")]
        with self.assertRaises(UncertainWrite):
            self.run_edit()

    def test_failed_unknown_log_after_unexpected_writer_error_is_uncertain(self):
        self.memory.write_exact.side_effect = OSError("transport lost")
        self.record.side_effect = [None, Refused("corrupt journal")]
        with self.assertRaises(UncertainWrite):
            self.run_edit()

    def test_verified_and_unknown_logs_both_fail_after_write(self):
        self.record.side_effect = [None, Refused("corrupt journal"), OSError("disk full")]
        with self.assertRaises(UncertainWrite):
            self.run_edit()
        self.assertEqual(self.value, pack(11))


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.r = AttributeResolver.__new__(AttributeResolver)
        self.r.anchors = []
        self.data = bytearray(0x10000)
        class Reader:
            def read(inner, address, size):
                return bytes(self.data[address:address + size])
        self.r.reader = Reader()
        self.dictionary, self.array = 0x1000, 0x2000
        self.dc = {"name": "Dictionary`2"}
        self.ac = {"klass": "0x3000"}
        self.ec = {"name": "Entry", "instance_size": 32}
        self.r.obj = lambda address, fullname: self.dc if address == self.dictionary else self.ac
        self.r.info = lambda *args: self.ec
        offsets = {"_entries": 24, "_count": 32, "_freeCount": 40, "_version": 44,
                   "hashCode": 16, "next": 20, "key": 24, "value": 28}
        self.r.reviewed_field = lambda c, name, kind: offsets[name]
        self.put(self.dictionary + 24, "Q", self.array)
        self.put(self.dictionary + 32, "i", 2)
        self.put(self.dictionary + 44, "i", 12)
        self.put(self.array + 24, "Q", 3)
        self.data[self.array + 32:self.array + 64] = struct.pack("<iiifiiif", 2, -1, 2, 10.5, 3, -1, 3, 1.0)

    def put(self, address, fmt, value):
        raw = struct.pack("<" + fmt, value)
        self.data[address:address + len(raw)] = raw

    def test_exact_float32_dictionary_entries(self):
        values, anchors, identity = self.r.dictionary(self.dictionary)
        self.assertEqual(values[2], dict(value=10.5, address=self.array + 44))
        self.assertEqual(len(anchors), 2)
        self.assertEqual(identity[-1], 12)

    def test_empty_dictionary_without_allocation(self):
        self.put(self.dictionary + 24, "Q", 0)
        self.put(self.dictionary + 32, "i", 0)
        self.assertEqual(self.r.dictionary(self.dictionary)[0], {})

    def test_duplicate_keys_refused(self):
        self.put(self.array + 56, "i", 2)
        with self.assertRaises(Refused):
            self.r.dictionary(self.dictionary)

    def test_nan_refused(self):
        self.put(self.array + 44, "f", float("nan"))
        with self.assertRaises(Refused):
            self.r.dictionary(self.dictionary)

    def test_free_counter_mismatch_refused(self):
        self.put(self.dictionary + 40, "i", 1)
        with self.assertRaises(Refused):
            self.r.dictionary(self.dictionary)

    def test_too_large_capacity_refused(self):
        self.put(self.array + 24, "Q", 10000)
        with self.assertRaises(Refused):
            self.r.dictionary(self.dictionary)


if __name__ == "__main__":
    unittest.main()
