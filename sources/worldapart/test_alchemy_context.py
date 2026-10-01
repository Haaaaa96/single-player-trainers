"""Specialized pill-scene whitelist with unchanged lifecycle/battle guards."""
import struct
import unittest
from unittest.mock import patch

import acquisition_context as ac
import alchemy_context as al
from test_acquisition_context import Fixture


class PillFixture(Fixture):
    def __init__(self, pill=True):
        super().__init__()
        self.sub_k = 0x170000
        if pill:
            self.add_pill_class(self.sub_k, al.SUB_HANDLER, self.base_k)
            self.add_pill_class(self.handler_k, al.PILL_HANDLER, self.sub_k)

    def add_pill_class(self, address, fullname, parent):
        spec = self.specs[fullname]
        namespace, _, name = fullname.rpartition(".")
        fields = [dict(name=f["name"], token=hex(f["token"]), offset=56, parent=hex(address),
                       type_data=(b"\0" * 10 + b"\x08" + b"\0" * 5).hex()) for f in spec["fields"]]
        self.classes[address] = dict(klass=hex(address), name=name, namespace=namespace, fields=fields,
                                     instance_size=64, parent=hex(parent))
        self.memory.number(address + 0x68, self.meta + spec["type_definition_offset"])
        self.memory.number(address + 0x11C, spec["token"], "i")
        self.memory.number(address + 0x58, parent)

    def state(self):
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r, k: self.classes.get(k)):
            return al.require_safe_alchemy_context(self.resolver)


class AlchemyContextTests(unittest.TestCase):
    def test_only_reviewed_pill_scene_and_main_scene_allowed(self):
        for pill in (True, False):
            fx = PillFixture(pill)
            state = fx.state()
            self.assertEqual(state["status"], "safe_alchemy_nonbattle")
            self.assertEqual(state["identity"]["space_class"], al.PILL_HANDLER if pill else "Game.SpaceHandlers.MainSpaceHandler")

    def test_generic_subspace_battle_or_unknown_not_whitelisted(self):
        for name in ("SubSpaceHandler", "BattleSpaceHandler", "AlchemySpaceHandler", "FakeRefiningPillsSpaceHandler"):
            fx = PillFixture(); fx.classes[fx.handler_k]["name"] = name
            with self.subTest(name=name), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_reviewed_parent_chain_is_required_and_anchored(self):
        fx = PillFixture()
        result = fx.state()
        for address in (fx.handler_k + 0x58, fx.sub_k + 0x58, fx.sub_k + 0x68, fx.handler_k + 0x68):
            self.assertTrue(any(a["address"] == address for a in result["anchors"]))
        fx.memory.number(fx.handler_k + 0x58, fx.base_k)
        with self.assertRaises(ac.AcquisitionContextRefused):
            fx.state()

    def test_local_handler_metadata_cannot_be_spoofed(self):
        for kind in ("token", "definition", "field"):
            fx = PillFixture()
            if kind == "token": fx.memory.number(fx.handler_k + 0x11C, 0, "i")
            elif kind == "definition": fx.memory.number(fx.sub_k + 0x68, 0)
            else: fx.classes[fx.handler_k]["fields"][0]["token"] = "0x400ffff"
            with self.subTest(kind=kind), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_lifecycle_and_transition_guards_remain(self):
        for base, offsets in (("main", [33, 68, 69, 70, 71]), ("space", [96, 112]), ("life", [56, 57])):
            for offset in offsets:
                fx = PillFixture(); fx.memory.number(getattr(fx, base) + offset, 1, "B")
                with self.subTest(base=base, offset=offset), self.assertRaises(ac.AcquisitionContextRefused):
                    fx.state()
        for offset in (80, 104):
            fx = PillFixture(); fx.memory.number(fx.space + offset, 0xDEAD00)
            with self.subTest(offset=offset), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_wave_instance_and_ambiguous_wave_refused(self):
        fx = PillFixture(); fx.resolved_wave(0xBAD000)
        with self.assertRaises(ac.AcquisitionContextRefused):
            fx.state()
        fx.resolved_wave()
        self.assertEqual(fx.state()["identity"]["wave_state"], "no_instance")
        for value in (0, 1, ac.WAVE_COLD_USAGE + 2):
            fx.memory.number(fx.module + ac.WAVE_CLASS_RVA, value)
            with self.subTest(value=value), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_scene_change_during_read_refused(self):
        fx = PillFixture(); original = fx.memory.read; count = 0
        def read(address, size):
            nonlocal count
            if address == fx.space + 64:
                count += 1
                if count > 1:
                    return struct.pack("<Q", 0)
            return original(address, size)
        fx.memory.read = read
        with self.assertRaises(ac.AcquisitionContextRefused):
            fx.state()

    def test_item_acquisition_whitelist_is_unchanged(self):
        fx = PillFixture()
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r, k: fx.classes.get(k)):
            with self.assertRaises(ac.AcquisitionContextRefused):
                ac.require_safe_acquisition_context(fx.resolver)


if __name__ == "__main__":
    unittest.main()
