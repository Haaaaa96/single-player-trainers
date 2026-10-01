import copy
from dataclasses import replace
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import meridian_logic as ml
import meridian_write as mw
from write_guard import Refused, UncertainWrite


def board():
    return dict(active=True, config=dict(rows=1, cols=3, start_col=0, start_row=0, end_col=2, end_row=0),
                cells=[dict(col=c, row=0, role=(1, 0, 2)[c], kind=0, shape=0,
                            variant=(0, 1, 0)[c], hidden=False, is_generated_path=True,
                            solution_shape=0, solution_variant=0, rotate_count=0) for c in range(3)])


class HintTests(unittest.TestCase):
    def test_restore_plan_unlocks_hidden_generated_route_without_mutation(self):
        state = board()
        state["cells"][1].update(kind=3, hidden=True, rotate_count=10)
        original = copy.deepcopy(state)
        self.assertFalse(ml.build_hint(state)["verified_path"])
        restored = ml.build_restore_plan(state)
        self.assertTrue(restored["can_restore"])
        self.assertEqual(restored["changed_cells"], 1)
        self.assertEqual(state, original)

    def test_restore_plan_never_rewrites_nonpath_or_fakes_a_broken_solution(self):
        state = board()
        state["cells"][1]["is_generated_path"] = False
        self.assertFalse(ml.build_restore_plan(state)["can_restore"])
        state = board()
        state["cells"][1]["solution_variant"] = 1
        state["cells"][1]["hidden"] = True
        self.assertFalse(ml.build_restore_plan(state)["can_restore"])

    def test_restore_plan_declines_noop_and_invalid_board(self):
        state = board()
        state["cells"][1]["variant"] = 0
        self.assertFalse(ml.build_restore_plan(state)["can_restore"])
        for value in (None, {}, dict(active=True), dict(active=False)):
            self.assertFalse(ml.build_restore_plan(value)["can_restore"])

    def test_exact_native_shape_catalog(self):
        expected = (((0, 3), (1, 4), (2, 5)),
                    ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)),
                    ((0, 2), (1, 3), (2, 4), (3, 5), (0, 4), (1, 5)),
                    ((0, 2, 4), (1, 3, 5)),
                    ((0, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 5), (0, 4, 5), (0, 1, 5)),
                    ((0, 1, 2, 3, 4, 5),))
        for shape, variants in enumerate(expected):
            self.assertEqual(ml.VARIANT_COUNTS[shape], len(variants))
            for variant, value in enumerate(variants):
                self.assertEqual(ml.ports(shape, variant), frozenset(value))

    def test_neighbor_inverse_for_both_parities_and_negative_coordinates(self):
        for col in range(-2, 3):
            for row in range(-2, 3):
                for direction in range(6):
                    adjacent = ml.neighbor(col, row, direction)
                    self.assertEqual(ml.neighbor(*adjacent, (direction + 3) % 6), (col, row))
        self.assertEqual(ml.neighbor(2, 0, 1), (2, 1))
        self.assertEqual(ml.neighbor(2, 1, 1), (3, 2))

    def test_rotations_use_native_left_and_right_minimum_clicks(self):
        for shape, count in enumerate(ml.VARIANT_COUNTS):
            for current in range(count):
                for desired in range(count):
                    clicks, direction = ml.rotation_steps(shape, current, desired)
                    self.assertEqual((current + clicks * direction) % count, desired)
                    self.assertLessEqual(clicks, count // 2)
        self.assertEqual(ml.rotation_steps(1, 0, 5), (1, -1))

    def test_hint_is_read_only_and_maps_one_based_instruction(self):
        state = board()
        before = copy.deepcopy(state)
        result = ml.build_hint(state)
        self.assertEqual(state, before)
        self.assertTrue(result["verified_path"])
        self.assertEqual(result["route"], [(0, 0), (1, 0), (2, 0)])
        self.assertEqual(result["steps"][0]["direction"], -1)
        self.assertIn("第 1 行第 2 列", result["steps"][0]["text"])
        self.assertEqual(result["estimated_needles"], 1)

    def test_hidden_requires_reveal_then_rotation_and_extra_needle(self):
        state = board()
        state["cells"][1]["hidden"] = True
        state["needle_remaining"] = 1
        result = ml.build_hint(state)
        self.assertEqual(result["steps"][0]["action"], "reveal_rotate")
        self.assertEqual(result["estimated_needles"], 2)
        self.assertTrue(any("补足" in warning for warning in result["warnings"]))

    def test_weak_stuck_allows_only_one_rotation(self):
        state = board()
        state["cells"][1]["kind"] = 1
        self.assertTrue(ml.build_hint(state)["verified_path"])
        state["cells"][1]["rotate_count"] = 1
        result = ml.build_hint(state)
        self.assertFalse(result["verified_path"])
        self.assertEqual(result["steps"], [])
        self.assertTrue(any("锁定" in warning for warning in result["warnings"]))

    def test_strong_stuck_wrong_orientation_never_suggests_rotate(self):
        state = board()
        state["cells"][1]["kind"] = 2
        self.assertFalse(ml.build_hint(state)["verified_path"])
        state["cells"][1]["variant"] = 0
        result = ml.build_hint(state)
        self.assertTrue(result["verified_path"])
        self.assertEqual(result["steps"], [])

    def test_blocker_never_connects_even_with_solution_ports(self):
        state = board()
        state["cells"][1].update(kind=3, variant=0)
        self.assertFalse(ml.build_hint(state)["verified_path"])

    def test_transformed_full_connect_preserved_instead_of_replacing_with_original(self):
        state = board()
        state["cells"][1].update(shape=5, variant=0)
        result = ml.build_hint(state)
        self.assertTrue(result["verified_path"])
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["cells"][1]["target_shape"], 5)

    def test_fixed_endpoint_direction_not_overwritten_with_solution(self):
        state = board()
        state["cells"][0]["variant"] = 1
        self.assertFalse(ml.build_hint(state)["verified_path"])

    def test_only_generated_path_cells_used(self):
        state = board()
        state["cells"][1]["is_generated_path"] = False
        result = ml.build_hint(state)
        self.assertFalse(result["verified_path"])
        self.assertEqual(result["steps"], [])

    def test_inactive_missing_duplicate_and_malformed_board_never_produce_steps(self):
        invalid = [None, {}, dict(active=False), dict(active=True), board(), board(), board(), board()]
        invalid[-4]["cells"].pop()
        invalid[-3]["cells"][1]["col"] = 0
        invalid[-2]["cells"][1]["shape"] = 6
        invalid[-1]["config"]["start_col"] = 2
        for state in invalid:
            with self.subTest(state=state):
                self.assertFalse(ml.build_hint(state)["verified_path"])
                self.assertEqual(ml.build_hint(state)["steps"], [])

    def test_unknown_geometry_values_rejected(self):
        for shape, variant in ((True, 0), (1, 6), (-1, 0), (0, True)):
            with self.assertRaises(ValueError):
                ml.ports(shape, variant)


STAMP = ("WorldApart.exe", 17)


class Memory:
    h, pid = 1, 17

    def __init__(self):
        self.data = {0x1000: struct.pack("<i", 12), 0x2000: b"\1"}
        self.writes = []

    def read_exact(self, address, size):
        return self.data[address][:size]

    def write_exact(self, address, raw):
        self.writes.append((address, raw))
        self.data[address] = raw


class WriteTests(unittest.TestCase):
    def setUp(self):
        self.mem = Memory()
        self.target = mw.MeridianTarget("meridian_needles_used", 0x1000, 12, (STAMP, 3), 0, 100,
                                        ((0x2000, "01"),))
        self.events = []

    def resolve(self, key):
        return replace(self.target, value=struct.unpack("<f" if self.target.kind == "f32" else "<i",
                                                       self.mem.data[0x1000])[0])

    def write(self, value, resolver=None, record=None):
        return mw.set_meridian_value(self.mem, resolver or self.resolve, self.target, value,
                                     record or self.events.append)

    def test_successful_single_scalar_write_with_log_and_fresh_readback(self):
        result = self.write(0)
        self.assertEqual(result.value, 0)
        self.assertEqual(self.mem.writes, [(0x1000, struct.pack("<i", 0))])
        self.assertEqual([e["status"] for e in self.events], ["attempt", "verified_memory"])

    def test_float32_time_write(self):
        self.target = replace(self.target, key="meridian_time", value=12.5, minimum=1.0,
                              maximum=100.0, kind="f32")
        self.mem.data[0x1000] = struct.pack("<f", 12.5)
        result = self.write(99.25)
        self.assertEqual(result.value, 99.25)
        self.assertEqual(self.mem.writes, [(0x1000, struct.pack("<f", 99.25))])

    def test_float32_minimum_rounding_is_usable_and_does_not_allow_subminimum_input(self):
        target = replace(self.target, key="meridian_time", kind="f32", value=12.5,
                         minimum=0.01, maximum=100.0)
        normalized = mw.validate(target, 0.01)
        self.assertEqual(normalized, struct.unpack("<f", struct.pack("<f", 0.01))[0])
        self.assertEqual(mw.validate(replace(target, value=normalized), 12.5), 12.5)
        with self.assertRaises(Refused):
            mw.validate(target, 0.0099)

    def test_input_types_bounds_and_unchanged_never_write(self):
        for value in (-1, 101, True, 1.5, "12", float("inf"), float("nan"), 12):
            with self.subTest(value=value), self.assertRaises(Refused):
                self.write(value)
        self.assertEqual(self.mem.writes, [])

    def test_parser_only_plain_ascii_numbers(self):
        self.assertEqual(mw.parse_value("meridian_time", " 99.25 "), 99.25)
        self.assertEqual(mw.parse_value("meridian_transform", "999"), 999)
        for key, text in (("meridian_time", "1e2"), ("meridian_time", "1.234"),
                          ("meridian_transform", "2.0"), ("meridian_reveal", "９９"),
                          ("item:1", "1"), ("meridian_time", True), ("meridian_time", "-1")):
            with self.subTest(key=key, text=text), self.assertRaises(Refused):
                mw.parse_value(key, text)

    def test_forged_kind_unknown_key_bad_address_and_anchors_never_write(self):
        for target in (replace(self.target, key="item:1"), replace(self.target, kind="f32"),
                       replace(self.target, address=0x1001), replace(self.target, anchors=()),
                       replace(self.target, identity=()), replace(self.target, anchors=((0x1000, "00"),)),
                       replace(self.target, anchors=((0x2000, "zz"),))):
            with self.subTest(target=target), self.assertRaises(Refused):
                mw.validate(target, 0)

    def test_caps_and_single_delta_are_tool_limits(self):
        with self.assertRaises(Refused):
            mw.validate(replace(self.target, key="meridian_reveal", maximum=1000), 13)
        with self.assertRaises(Refused):
            mw.validate(replace(self.target, maximum=3000), 2012)

    def test_changed_round_and_pause_anchor_refused_before_write(self):
        with self.assertRaises(Refused):
            self.write(0, lambda _: replace(self.target, identity=(STAMP, 4)))
        self.assertEqual(self.mem.writes, [])

    def test_race_after_attempt_log_does_not_write(self):
        count = 0

        def resolver(key):
            nonlocal count
            count += 1
            return self.target if count < 3 else replace(self.target, value=13)

        with self.assertRaises(Refused):
            self.write(0, resolver)
        self.assertEqual(self.mem.writes, [])
        self.assertEqual(self.events[-1]["status"], "refused_changed")

    def test_log_failure_before_write_prevents_mutation(self):
        def broken(event):
            raise OSError("disk full")
        with self.assertRaises(OSError):
            self.write(0, record=broken)
        self.assertEqual(self.mem.writes, [])

    def test_partial_write_or_exception_is_uncertain_not_retried(self):
        def failed(address, raw):
            self.mem.writes.append((address, raw))
            raise OSError("partial")
        self.mem.write_exact = failed
        with self.assertRaises(UncertainWrite):
            self.write(0)
        self.assertEqual(len(self.mem.writes), 1)
        self.assertEqual(self.events[-1]["status"], "uncertain")

    def test_post_write_round_change_is_uncertain(self):
        def resolver(key):
            result = self.resolve(key)
            return replace(result, identity=(STAMP, 4)) if self.mem.writes else result
        with self.assertRaises(UncertainWrite):
            self.write(0, resolver)
        self.assertEqual(len(self.mem.writes), 1)

    def test_consumed_value_is_uncertain_without_second_write(self):
        def overwritten(address, raw):
            self.mem.writes.append((address, raw))
            self.mem.data[address] = struct.pack("<i", 1)
        self.mem.write_exact = overwritten
        with self.assertRaises(UncertainWrite):
            self.write(0)
        self.assertEqual(len(self.mem.writes), 1)

    def kernel(self, calls, *, protection=4):
        def region(handle, address, output, size):
            target = output._obj
            target.BaseAddress, target.RegionSize = 0x1000, 0x1000
            target.State, target.Type, target.Protect = 0x1000, 0x20000, protection
            return 1
        def write(handle, address, buffer, size, count):
            calls.append((address, bytes(buffer.raw[:size]), size))
            count._obj.value = size
            return 1
        return SimpleNamespace(OpenProcess=lambda *a: 22, CloseHandle=lambda h: None,
                               VirtualQueryEx=region, WriteProcessMemory=write)

    def test_native_revalidates_pause_anchors_before_write(self):
        calls = []
        once = mw.MeridianWriteOnce(self.mem, STAMP, self.target, new_value=0)
        self.mem.data[0x2000] = b"\0"
        with patch.object(mw, "K", self.kernel(calls)), patch.object(mw, "process_identity", return_value=STAMP), \
             patch.object(mw, "read_exact_handle", side_effect=lambda h, a, s: self.mem.read_exact(a, s)):
            with self.assertRaises(Refused):
                once.write_exact(0x1000, struct.pack("<i", 0))
        self.assertEqual(calls, [])

    def test_native_refuses_executable_memory_and_process_replacement(self):
        for protection, identity in ((0x40, STAMP), (4, ("Other.exe", 18))):
            calls = []
            once = mw.MeridianWriteOnce(self.mem, STAMP, self.target, new_value=0)
            with patch.object(mw, "K", self.kernel(calls, protection=protection)), \
                 patch.object(mw, "process_identity", return_value=identity):
                with self.assertRaises(Refused):
                    once.write_exact(0x1000, struct.pack("<i", 0))
            self.assertEqual(calls, [])

    def test_native_exact_four_bytes_one_time_only(self):
        calls = []
        once = mw.MeridianWriteOnce(self.mem, STAMP, self.target, new_value=0)
        with patch.object(mw, "K", self.kernel(calls)), patch.object(mw, "process_identity", return_value=STAMP), \
             patch.object(mw, "read_exact_handle", side_effect=lambda h, a, s: self.mem.read_exact(a, s)):
            once.write_exact(0x1000, struct.pack("<i", 0))
            with self.assertRaises(Refused):
                once.write_exact(0x1000, struct.pack("<i", 0))
        self.assertEqual(calls, [(0x1000, struct.pack("<i", 0), 4)])


if __name__ == "__main__":
    unittest.main()
