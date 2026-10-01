"""Synthetic-memory round lifecycle and strict MedGame layout tests."""
import struct
import unittest
from unittest.mock import patch

import meridian_adapter as ma
import meridian_write as mw
from write_guard import Refused

STAMP = ("worldapart.exe", 234)


class Memory:
    h, pid = 1, 999

    def __init__(self):
        self.data = {}

    def put(self, address, raw):
        self.data.update({address + i: b for i, b in enumerate(raw)})

    def number(self, address, value, fmt="i"):
        self.put(address, struct.pack("<" + fmt, value))

    def read(self, address, size):
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError:
            return b""

    def read_exact(self, address, size):
        value = self.read(address, size)
        if len(value) != size:
            raise Refused("synthetic short read")
        return value

    def write_exact(self, address, raw):
        self.put(address, raw)


class Fixture:
    def __init__(self):
        self.mem = Memory()
        self.resolver = ma.MeridianResolver.__new__(ma.MeridianResolver)
        r = self.resolver
        r.reader, r.stamp, r.meta, r.module, r.anchors = self.mem, STAMP, 0x100000, 0x200000, []
        self.panel, self.runtime, self.config = 0x10000, 0x11000, 0x12000
        self.collection, self.items, self.array = 0x13000, 0x14000, 0x15000
        self.cells = (0x16000, 0x17000)
        self.classes = {}
        self.offsets = {}
        self.add_class(0x3000, ma.NS + "MedGamePanel", 280, 0x4000, {
            "_game": (208, 0x12), "_settlementStarted": (248, 2),
            "_settlementCompletionDelegated": (249, 2), "_boardLoading": (250, 2),
            "_boardLoaded": (251, 2), "_exitConfirmOpen": (252, 2)})
        self.add_class(0x4000, "Game.BaseUI", 200, 0, {
            "isShowing": (66, 2), "isInitialized": (67, 2),
            "<IsInVisualHide>k__BackingField": (88, 2), "<HandleToken>k__BackingField": (168, 8)})
        self.add_class(0x5000, ma.NS + "MedGameViewModel", 312, 0, {
            "_config": (64, 0x12), "_seed": (72, 8), "_needleUsed": (80, 8),
            "_bonusNeedleGained": (84, 8), "_passiveNeedleBonus": (88, 8),
            "_timeRemaining": (100, 0x0C), "_transformLeft": (104, 8), "_revealLeft": (108, 8),
            "_pendingTransform": (113, 2), "_finished": (114, 2), "_hasWon": (115, 2),
            "_timerEnabled": (116, 2), "_paused": (117, 2), "_revealAnimating": (119, 2),
            "_boardLayoutReady": (137, 2), "_timerCts": (200, 0x12),
            "_completed": (192, 0x15), "_revealAnimationCts": (208, 0x12),
            "_bonusFlashCts": (216, 0x12), "_boardShakeCts": (224, 0x12), "_winPathAnimationCts": (232, 0x12),
            "<Cells>k__BackingField": (248, 0x15), "<FailureReason>k__BackingField": (264, 0x11)})
        self.add_class(0x6000, ma.NS + "MedGameConfig", 152, 0, {
            "Cols": (32, 8), "Rows": (36, 8), "StartCol": (40, 8), "StartRow": (44, 8),
            "EndCol": (48, 8), "EndRow": (52, 8), "TimeLimit": (64, 8), "RotationLimit": (68, 8)})
        self.add_class(0x7000, "Loxodon.Framework.Observables.ObservableList`1", 72, 0,
                       {"items": (56, 0x15)})
        self.add_class(0x8000, "System.Collections.Generic.List`1", 40, 0,
                       {"_items": (16, 0x1D), "_size": (24, 8), "_version": (28, 8)})
        self.add_class(0x9000, ma.NS + "MedCellViewModel", 152, 0, {
            "_owner": (40, 0x12), "_col": (48, 8), "_row": (52, 8),
            "_kind": (56, 0x11), "_shape": (60, 0x11), "_variant": (64, 8),
            "_hidden": (72, 2), "_rotateCount": (108, 8), "_isGeneratedPath": (116, 2),
            "_solutionShape": (120, 0x11), "_solutionVariant": (124, 8),
            "<Role>k__BackingField": (144, 0x11)})
        self.classes[0xA000] = dict(klass="0xa000", namespace=ma.NS[:-1], name="MedCellViewModel[]",
                                    instance_size=32, parent="0x0", fields=[])
        self.mem.number(0xA000 + 0x40, 0x9000, "Q")
        for address, size, klass in ((self.panel, 280, 0x3000), (self.runtime, 312, 0x5000),
                (self.config, 152, 0x6000), (self.collection, 72, 0x7000), (self.items, 40, 0x8000),
                (self.array, 48, 0xA000), *( (x, 152, 0x9000) for x in self.cells)):
            self.mem.put(address, b"\0" * size)
            self.mem.number(address, klass, "Q")
        self.mem.number(self.panel + 16, 0xDEAD0000, "Q")
        for offset in (66, 67, 251, 252):
            self.mem.put(self.panel + offset, b"\1")
        self.mem.number(self.panel + 168, 6)
        self.mem.number(self.panel + 208, self.runtime, "Q")
        self.mem.number(self.runtime + 64, self.config, "Q")
        self.mem.number(self.runtime + 72, 12345)
        self.mem.number(self.runtime + 80, 3)
        self.mem.number(self.runtime + 84, 2)
        self.mem.number(self.runtime + 88, 1)
        self.mem.number(self.runtime + 100, 40.5, "f")
        self.mem.number(self.runtime + 104, 1)
        self.mem.number(self.runtime + 108, 2)
        self.mem.put(self.runtime + 116, b"\1\1")
        self.mem.put(self.runtime + 137, b"\1")
        self.mem.number(self.runtime + 248, self.collection, "Q")
        self.mem.number(self.runtime + 192, 0xB0000, "Q")
        for offset, value in ((32, 2), (36, 1), (48, 1), (64, 60), (68, 10)):
            self.mem.number(self.config + offset, value)
        self.mem.number(self.collection + 56, self.items, "Q")
        self.mem.number(self.items + 16, self.array, "Q")
        self.mem.number(self.items + 24, 2)
        self.mem.number(self.array + 24, 2, "Q")
        for index, address in enumerate(self.cells):
            self.mem.number(self.array + 32 + 8 * index, address, "Q")
            self.mem.number(address + 40, self.runtime, "Q")
            self.mem.number(address + 48, index)
            self.mem.put(address + 116, b"\1")
            self.mem.number(address + 144, index + 1)

    def add_class(self, address, fullname, size, parent, selected):
        spec = ma.SPECS[fullname]
        fields = []
        for f in spec["fields"]:
            offset, kind = selected.get(f["name"], (16, 8))
            raw = bytearray(16)
            raw[8], raw[10] = 1, kind
            fields.append(dict(name=f["name"], token=hex(f["token"]), offset=offset,
                               parent=hex(address), type_data=raw.hex()))
        ns, _, name = fullname.rpartition(".")
        self.classes[address] = dict(klass=hex(address), namespace=ns, name=name,
                                     instance_size=size, parent=hex(parent), fields=fields)
        self.mem.number(address + 0x68, self.resolver.meta + spec["type_definition_offset"], "Q")
        self.mem.number(address + 0x11C, spec["token"])

    def state(self, panels=None):
        with patch("learning_adapter.probe.inspect_class", side_effect=lambda reader, k: self.classes.get(k)), \
                patch.object(ma, "process_identity", return_value=STAMP), \
                patch.object(self.resolver, "_registered_panels", return_value=(0x20000,
                        [self.panel] if panels is None else panels)):
            return self.resolver.snapshot()


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()

    def test_paused_round_has_reviewed_targets_and_actual_board(self):
        s = self.fx.state()
        self.assertTrue(s["active"] and s["paused"] and s["can_edit"])
        self.assertEqual(set(s["targets"]), {"meridian_time", "meridian_needles_used",
                                              "meridian_transform", "meridian_reveal"})
        self.assertEqual((s["needle_total"], s["needle_remaining"]), (13, 10))
        self.assertEqual(s["targets"]["meridian_time"].maximum, 60)
        self.assertEqual(len(s["cells"]), 2)
        self.assertEqual(s["values"]["meridian_time"], 40.5)

    def test_running_round_is_readonly(self):
        self.fx.mem.put(self.fx.runtime + 117, b"\0")
        self.fx.mem.put(self.fx.panel + 252, b"\0")
        self.fx.mem.number(self.fx.runtime + 200, 0xBEEF0000, "Q")
        s = self.fx.state()
        self.assertTrue(s["active"])
        self.assertFalse(s["can_edit"])
        self.assertEqual(s["targets"], {})
        self.assertTrue(s["can_solve"])
        self.assertEqual(s["native"]["cells"][0]["address"], hex(self.fx.cells[0]))
        self.assertTrue(s["native"]["anchors"])
        self.assertEqual(len(s["native"]["round_key"]), 64)

    def test_oneclick_refuses_paused_animation_or_missing_completion(self):
        self.assertFalse(self.fx.state()["can_solve"])
        self.fx.mem.put(self.fx.runtime + 117, b"\0")
        self.fx.mem.put(self.fx.panel + 252, b"\0")
        for offset in (208, 216, 224, 232):
            self.fx.mem.number(self.fx.runtime + offset, 0xDEAD, "Q")
            self.assertFalse(self.fx.state()["can_solve"])
            self.fx.mem.number(self.fx.runtime + offset, 0, "Q")
        self.fx.mem.number(self.fx.runtime + 192, 0, "Q")
        self.assertFalse(self.fx.state()["can_solve"])

    def test_new_cell_objects_change_round_identity_even_with_same_seed(self):
        before = self.fx.state()
        replacement = 0x18000
        self.fx.mem.put(replacement, self.fx.mem.read(self.fx.cells[0], 152))
        self.fx.mem.number(self.fx.array + 32, replacement, "Q")
        after = self.fx.state()
        self.assertNotEqual(before["identity"], after["identity"])
        self.assertNotEqual(before["native"]["round_key"], after["native"]["round_key"])

    def test_native_method_requires_exact_receiver_return_signature_and_entry(self):
        f = self.fx
        f.mem.put(f.runtime + 117, b"\0")
        f.mem.put(f.panel + 252, b"\0")
        f.mem.put(f.cells[0] + 72, b"\1")
        shown = f.state()
        klass, table, method, name, return_type = 0x5000, 0x31000, 0x32000, 0x33000, 0x34000
        f.mem.number(klass + 0x120, 1, "H")
        f.mem.number(klass + 0x98, table, "Q")
        f.mem.number(table, method, "Q")
        f.mem.put(method, b"\0" * 88)
        f.mem.number(method, f.resolver.module + 0x1DAC830, "Q")
        f.mem.number(method + 0x18, name, "Q")
        f.mem.number(method + 0x20, klass, "Q")
        f.mem.number(method + 0x28, return_type, "Q")
        f.mem.number(method + 0x48, 0x06010174)
        f.mem.number(method + 0x4C, 0x83, "H")
        f.mem.put(return_type + 10, b"\x02\0")
        f.mem.put(f.resolver.module + ma.METHOD_SPEC['rva'], bytes.fromhex(ma.METHOD_SPEC['prefix']))
        f.mem.string = lambda address: "RevealSolutionPathForEditor" if address == name else "unknown"
        with patch("learning_adapter.probe.inspect_class", side_effect=lambda reader, k: f.classes.get(k)), \
                patch.object(ma, "process_identity", return_value=STAMP), \
                patch.object(f.resolver, "snapshot", return_value=shown):
            self.assertEqual(f.resolver.prepare_solve(shown)["native"]["method_info"], hex(method))
            for address, bad in ((method, struct.pack("<Q", 123)),
                                 (method + 0x20, struct.pack("<Q", 0x9000)),
                                 (method + 0x52, b"\1"), (method + 0x4C, b"\x93\0"),
                                 (return_type + 10, b"\x08")):
                old = f.mem.read(address, len(bad)); f.mem.put(address, bad)
                with self.subTest(address=address), self.assertRaises(Refused):
                    f.resolver.prepare_solve(shown)
                f.mem.put(address, old)
            with self.assertRaises(Refused):
                f.resolver.prepare_solve({"identity": ("different round",)})
    def test_pause_without_confirmation_or_live_timer_is_readonly(self):
        for address, raw in ((self.fx.panel + 252, b"\0"),
                             (self.fx.runtime + 200, struct.pack("<Q", 0x77770)),
                             (self.fx.runtime + 113, b"\1"), (self.fx.runtime + 119, b"\1")):
            with self.subTest(address=address):
                old = self.fx.mem.read(address, len(raw)); self.fx.mem.put(address, raw)
                self.assertFalse(self.fx.state()["can_edit"])
                self.fx.mem.put(address, old)

    def test_finished_hidden_unloaded_settling_round_is_inactive(self):
        for address, raw in ((self.fx.panel + 16, b"\0" * 8), (self.fx.panel + 66, b"\0"),
                    (self.fx.panel + 67, b"\0"), (self.fx.panel + 88, b"\1"),
                    (self.fx.panel + 248, b"\1"), (self.fx.panel + 249, b"\1"),
                    (self.fx.panel + 250, b"\1"), (self.fx.panel + 251, b"\0"),
                    (self.fx.runtime + 114, b"\1"), (self.fx.runtime + 115, b"\1"),
                    (self.fx.runtime + 137, b"\0"),
                    (self.fx.runtime + 264, struct.pack("<i", 1))):
            with self.subTest(address=address):
                old = self.fx.mem.read(address, len(raw)); self.fx.mem.put(address, raw)
                self.assertFalse(self.fx.state()["active"])
                self.fx.mem.put(address, old)

    def test_unregistered_lingering_objects_are_ignored(self):
        self.assertFalse(self.fx.state([])["active"])

    def test_multiple_active_panels_refused(self):
        with self.assertRaises(Refused):
            self.fx.state([self.fx.panel, self.fx.panel])

    def test_unlimited_round_has_no_time_or_used_needles_target(self):
        self.fx.mem.number(self.fx.config + 64, -1)
        self.fx.mem.number(self.fx.config + 68, -1)
        s = self.fx.state()
        self.assertEqual(set(s["targets"]), {"meridian_transform", "meridian_reveal"})
        self.assertIsNone(s["needle_total"])
        self.assertIsNone(s["needle_remaining"])

    def test_pause_with_subsecond_time_can_be_replenished(self):
        self.fx.mem.number(self.fx.runtime + 100, 0.5, "f")
        self.assertEqual(self.fx.state()["targets"]["meridian_time"].value, 0.5)

    def test_inflated_generic_list_definition_verified(self):
        klass, generic, definition = 0x7000, 0xB000, 0xB100
        spec = ma.SPECS["Loxodon.Framework.Observables.ObservableList`1"]
        self.fx.mem.number(klass + 0x68, 0, "Q")
        self.fx.mem.number(klass + 0x60, generic, "Q")
        self.fx.mem.number(generic, definition, "Q")
        self.fx.mem.number(generic + 24, klass, "Q")
        raw = bytearray(16)
        struct.pack_into("<Q", raw, 0, self.fx.resolver.meta + spec["type_definition_offset"])
        raw[10] = 0x12
        self.fx.mem.put(definition, raw)
        self.assertTrue(self.fx.state()["active"])
        self.fx.mem.number(generic + 24, 0xC000, "Q")
        with self.assertRaises(Refused): self.fx.state()

    def test_fresh_snapshot_rejects_changed_cell_anchor(self):
        original = self.fx.resolver.exact
        address = self.fx.cells[0] + 40
        reads = 0

        def changing_read(a, size):
            nonlocal reads
            if a == address and size == 64:
                reads += 1
                if reads == 2:
                    self.fx.mem.number(self.fx.cells[0] + 64, 1)
            return original(a, size)

        with patch.object(self.fx.resolver, "exact", side_effect=changing_read):
            with self.assertRaises(Refused): self.fx.state()

    def test_game_pauses_with_over_cap_resource_remains_readable(self):
        self.fx.mem.number(self.fx.runtime + 104, 1000)
        s = self.fx.state()
        self.assertEqual(s["values"]["meridian_transform"], 1000)
        self.assertNotIn("meridian_transform", s["targets"])

    def test_malformed_board_fails_closed(self):
        for address, value, fmt in ((self.fx.items + 24, 3, "i"),
                    (self.fx.cells[1] + 48, 0, "i"), (self.fx.cells[0] + 40, 0x77770, "Q"),
                    (self.fx.cells[0] + 60, 6, "i"), (self.fx.cells[0] + 64, 3, "i"),
                    (self.fx.cells[1] + 144, 0, "i"), (self.fx.cells[0] + 72, 2, "B")):
            with self.subTest(address=address):
                old = self.fx.mem.read(address, struct.calcsize("<" + fmt))
                self.fx.mem.number(address, value, fmt)
                with self.assertRaises(Refused): self.fx.state()
                self.fx.mem.put(address, old)

    def test_wrong_metadata_field_token_refused(self):
        self.fx.classes[0x5000]["fields"][0]["token"] = "0x123"
        with self.assertRaises(Refused): self.fx.state()

    def test_nonfinite_timer_refused(self):
        self.fx.mem.number(self.fx.runtime + 100, float("nan"), "f")
        with self.assertRaises(Refused): self.fx.state()

    def test_new_value_does_not_change_identity_or_enter_anchors(self):
        before = self.fx.state()["targets"]["meridian_time"]
        self.fx.mem.number(self.fx.runtime + 100, 55.0, "f")
        after = self.fx.state()["targets"]["meridian_time"]
        self.assertEqual(before.identity, after.identity)
        self.assertEqual(before.anchors, after.anchors)
        self.assertNotEqual(before.value, after.value)

    def test_each_resolved_scalar_can_make_one_synthetic_bounded_edit(self):
        # Integration: the real resolver's anchors/identity must survive each
        # write path's final re-resolution; no real process handle is used.
        for key, value in (("meridian_time", 41.5), ("meridian_needles_used", 2),
                           ("meridian_transform", 2), ("meridian_reveal", 3)):
            with self.subTest(key=key):
                fx = Fixture()
                shown = fx.state()["targets"][key]
                events = []
                result = mw.set_meridian_value(fx.mem, lambda k: fx.state()["targets"][k],
                                               shown, value, events.append)
                self.assertEqual(result.value, value)
                self.assertEqual(fx.state()["values"][key], value)
                self.assertEqual([e["status"] for e in events], ["attempt", "verified_memory"])

    def test_minimum_time_float32_roundtrip_keeps_fresh_target(self):
        shown = self.fx.state()["targets"]["meridian_time"]
        result = mw.set_meridian_value(self.fx.mem, lambda k: self.fx.state()["targets"][k],
                                       shown, 0.01, lambda event: None)
        self.assertAlmostEqual(result.value, 0.01)
        fresh = self.fx.state()["targets"]["meridian_time"]
        self.assertEqual(fresh.value, result.value)
        self.assertEqual(fresh.minimum, 0.01)


if __name__ == "__main__":
    unittest.main()
