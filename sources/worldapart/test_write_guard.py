"""Safety behavior against fake memory; never opens a process."""
import struct
import unittest
from dataclasses import replace
from unittest.mock import Mock
from write_guard import (INT32_MAX, MAX_CHANGE, PreconditionChanged, Refused, UncertainWrite, Target,
                         parse_value, set_value, step, validate_value)


class FakeMemory:
    def __init__(self, value=2):
        self.value = struct.pack("<i", value)
        self.writes = []
        self.fail = False
    def read_exact(self, address, size):
        return self.value
    def write_exact(self, address, value):
        self.writes.append((address, value))
        if self.fail:
            raise OSError("injected failure")
        self.value = value


class GuardTests(unittest.TestCase):
    def target(self, value=2, identity=(123, "player", "item"), minimum=1,
               maximum=INT32_MAX):
        return Target("item:1", 0x1000, value, identity, minimum, maximum)
    def test_precondition_refusal_is_not_reported_as_a_completed_or_unknown_write(self):
        memory = FakeMemory()
        memory.write_exact = Mock(side_effect=PreconditionChanged('scene changed'))
        shown, records = self.target(), []
        with self.assertRaises(PreconditionChanged):
            set_value(memory, lambda _: shown, shown, 3, records.append)
        self.assertEqual(memory.value, struct.pack('<i', 2))
        self.assertEqual([e['status'] for e in records], ['attempt', 'refused_precondition'])
    def test_absolute_large_change_then_restore(self):
        memory = FakeMemory()
        shown = self.target()
        records = []
        changed = set_value(memory, lambda _: shown, shown, 1002, records.append)
        restored = set_value(memory, lambda _: changed, changed, 2, records.append)
        self.assertEqual(restored, shown)
        self.assertEqual([struct.unpack("<i", data)[0] for _, data in memory.writes],
                         [1002, 2])
        self.assertEqual([event["status"] for event in records],
                         ["attempt", "verified", "attempt", "verified"])
    def test_change_limit_both_directions(self):
        for before, after in ((0, 1000), (1000, 0), (2, 1002), (1002, 2)):
            with self.subTest(before=before, after=after):
                shown = self.target(value=before, minimum=0)
                memory = FakeMemory(before)
                result = set_value(memory, lambda _: shown, shown, after, lambda _: None)
                self.assertEqual(result.value, after)
                self.assertEqual(len(memory.writes), 1)
        for before, after in ((0, 1001), (1001, 0), (2, 1003), (1003, 2)):
            with self.subTest(before=before, after=after):
                shown = self.target(value=before, minimum=0)
                memory, resolver, logger = FakeMemory(before), Mock(), Mock()
                with self.assertRaises(Refused):
                    set_value(memory, resolver, shown, after, logger)
                self.assertFalse(memory.writes)
                resolver.assert_not_called()
                logger.assert_not_called()
    def test_range_and_integer_boundaries(self):
        for before, after, minimum, maximum in (
                (1, 99, 1, 99), (99, 1, 1, 99), (0, 1000, 0, 1000),
                (1000, 0, 0, 1000), (INT32_MAX - 1, INT32_MAX, 0, INT32_MAX)):
            with self.subTest(after=after, maximum=maximum):
                shown = self.target(before, minimum=minimum, maximum=maximum)
                memory = FakeMemory(before)
                actual = set_value(memory, lambda _: shown, shown, after, lambda _: None)
                self.assertEqual(actual.value, after)
        for before, after, minimum, maximum in (
                (2, 0, 1, 99), (0, -1, 0, 1000), (99, 100, 1, 99),
                (999, 1001, 0, 1000), (INT32_MAX, INT32_MAX + 1, 0, INT32_MAX)):
            with self.subTest(after=after, maximum=maximum):
                memory = FakeMemory(before)
                shown = self.target(before, minimum=minimum, maximum=maximum)
                with self.assertRaises(Refused):
                    set_value(memory, lambda _: shown, shown, after, lambda _: None)
                self.assertFalse(memory.writes)
    def test_invalid_absolute_types_rejected_without_side_effects(self):
        for value in (True, False, 3.0, "3", "", None, -1, INT32_MAX + 1):
            with self.subTest(value=value):
                memory, resolver, logger = FakeMemory(), Mock(), Mock()
                with self.assertRaises(Refused):
                    set_value(memory, resolver, self.target(), value, logger)
                self.assertFalse(memory.writes)
                resolver.assert_not_called()
                logger.assert_not_called()
    def test_same_value_has_no_side_effects(self):
        memory, resolver, logger = Mock(), Mock(), Mock()
        with self.assertRaisesRegex(Refused, "无需修改"):
            set_value(memory, resolver, self.target(), 2, logger)
        memory.assert_not_called()
        self.assertEqual(memory.mock_calls, [])
        resolver.assert_not_called()
        logger.assert_not_called()
    def test_invalid_target_metadata(self):
        shown = self.target()
        for changed in (
                {"value": True}, {"value": 2.0}, {"value": -1},
                {"value": INT32_MAX + 1}, {"address": 0}, {"address": 4097},
                {"address": 4096.0}, {"address": True}, {"minimum": -1},
                {"minimum": True}, {"minimum": 100}, {"maximum": 0},
                {"maximum": 2.0}, {"maximum": INT32_MAX + 1}):
            with self.subTest(changed=changed), self.assertRaises(Refused):
                validate_value(replace(shown, **changed), 3)
    def test_second_resolution_change_refused_before_log(self):
        shown = self.target()
        memory, logger = FakeMemory(), Mock()
        resolver = Mock(side_effect=[shown, replace(shown, identity=("other",))])
        with self.assertRaises(Refused):
            set_value(memory, resolver, shown, 50, logger)
        self.assertFalse(memory.writes)
        logger.assert_not_called()
    def test_change_during_attempt_log_refused(self):
        shown = self.target()
        memory, records = FakeMemory(), []
        def logger(event):
            records.append(event)
            if event["status"] == "attempt":
                memory.value = struct.pack("<i", 5)
        with self.assertRaises(Refused):
            set_value(memory, lambda _: shown, shown, 50, logger)
        self.assertFalse(memory.writes)
        self.assertEqual([event["status"] for event in records],
                         ["attempt", "refused_changed"])
    def test_third_resolution_change_refused_after_log(self):
        shown = self.target()
        memory, records = FakeMemory(), []
        resolver = Mock(side_effect=[shown, shown, replace(shown, address=0x2000)])
        with self.assertRaises(Refused):
            set_value(memory, resolver, shown, 50, records.append)
        self.assertFalse(memory.writes)
        self.assertEqual([event["status"] for event in records],
                         ["attempt", "refused_changed"])
    def test_readback_mismatch_never_retried(self):
        class IgnoredWrite(FakeMemory):
            def write_exact(self, address, value):
                self.writes.append((address, value))
        shown = self.target()
        memory, records = IgnoredWrite(), []
        with self.assertRaises(UncertainWrite):
            set_value(memory, lambda _: shown, shown, 50, records.append)
        self.assertEqual(len(memory.writes), 1)
        self.assertEqual([event["status"] for event in records],
                         ["attempt", "readback_mismatch"])
    def test_one_step_then_restore(self):
        memory = FakeMemory()
        shown = self.target()
        records = []
        actual = step(memory, lambda _: shown, shown, 1, records.append)
        self.assertEqual(actual.value, 3)
        restored = step(memory, lambda _: actual, actual, -1, records.append)
        self.assertEqual(restored.value, 2)
        self.assertEqual(len(memory.writes), 2)
    def test_no_large_change(self):
        for invalid in (0, 2, -2, 100, True):
            memory = FakeMemory()
            shown = self.target()
            with self.assertRaises(Refused):
                step(memory, lambda _: shown, shown, invalid, lambda _: None)
            self.assertFalse(memory.writes)
    def test_changed_character_refused(self):
        memory = FakeMemory()
        shown = self.target()
        with self.assertRaises(Refused):
            step(memory, lambda _: self.target(identity=(123, "other", "item")),
                 shown, 1, lambda _: None)
        self.assertFalse(memory.writes)
    def test_changed_value_refused(self):
        memory = FakeMemory(3)
        shown = self.target()
        with self.assertRaises(Refused):
            step(memory, lambda _: shown, shown, 1, lambda _: None)
        self.assertFalse(memory.writes)
    def test_no_zero_stack_or_negative_root(self):
        for value, minimum in ((1, 1), (0, 0)):
            memory = FakeMemory(value)
            shown = self.target(value=value, minimum=minimum)
            with self.assertRaises(Refused):
                step(memory, lambda _: shown, shown, -1, lambda _: None)
            self.assertFalse(memory.writes)
    def test_failed_write_never_retried(self):
        memory = FakeMemory()
        memory.fail = True
        shown = self.target()
        with self.assertRaises(Refused):
            step(memory, lambda _: shown, shown, 1, lambda _: None)
        self.assertEqual(len(memory.writes), 1)
    def test_logging_failure_prevents_write(self):
        memory = FakeMemory()
        shown = self.target()
        def fail(_):
            raise OSError("disk unavailable")
        with self.assertRaises(OSError):
            step(memory, lambda _: shown, shown, 1, fail)
        self.assertFalse(memory.writes)
    def test_read_failure_after_write_is_uncertain(self):
        class ReadFailsAfterWrite(FakeMemory):
            def read_exact(self, address, size):
                if self.writes:
                    raise OSError("read failed")
                return super().read_exact(address, size)
        memory = ReadFailsAfterWrite()
        shown = self.target()
        with self.assertRaises(UncertainWrite):
            step(memory, lambda _: shown, shown, 1, lambda _: None)
        self.assertEqual(len(memory.writes), 1)
        self.assertEqual(struct.unpack("<i", memory.value)[0], 3)
    def test_log_failure_after_write_is_uncertain(self):
        memory = FakeMemory()
        shown = self.target()
        def logger(event):
            if event["status"] != "attempt":
                raise OSError("disk failed after attempt")
        with self.assertRaises(UncertainWrite):
            step(memory, lambda _: shown, shown, 1, logger)
        self.assertEqual(len(memory.writes), 1)
        self.assertEqual(struct.unpack("<i", memory.value)[0], 3)


class ParseTests(unittest.TestCase):
    def test_decimal_values(self):
        for text, expected in (("0", 0), (" 1000 \t", 1000), ("0099", 99),
                               (str(INT32_MAX), INT32_MAX)):
            with self.subTest(text=text):
                self.assertEqual(parse_value(text), expected)
    def test_invalid_inputs(self):
        for text in ("", " ", "+1", "-1", "1.0", "1e3", "1,000", "1_000",
                     "１２", "١٢", "1 0", "0x10", "1\n2", "\x001", True,
                     None, 1, 1.0, str(INT32_MAX + 1), "9" * 100000,
                     " " * 65 + "1", "0" * 11):
            with self.subTest(text=str(text)[:40]), self.assertRaises(Refused):
                parse_value(text)
    def test_limit_is_1000(self):
        self.assertEqual(MAX_CHANGE, 1000)


if __name__ == "__main__":
    unittest.main()
