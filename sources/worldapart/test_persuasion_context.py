"""Real readonly context paths over memory fixtures, without a game or broker."""
import struct
import unittest
from unittest.mock import patch

import acquisition_context as ac
import persuasion_context as pc
from test_acquisition_context import Fixture


class PersuasionFixture(Fixture):
    def __init__(self, single=True):
        super().__init__()
        self.npc = 0xA0000
        if single:
            namespace, _, name = pc.SINGLE_HANDLER.rpartition(".")
            fields = []
            for field in pc.HANDLER_SPEC["fields"]:
                is_npc = field["name"] == "CurNpc"
                is_static = field["name"] == "<SuppressAutoNpcDialogueOnce>k__BackingField"
                td = bytearray(16)
                td[8] = 0x11 if is_static else 1
                td[10] = 0x12 if is_npc else 2
                fields.append(dict(name=field["name"], token=hex(field["token"]),
                                   offset=0x38 if is_npc else (0 if is_static else 0x40),
                                   parent=hex(self.handler_k), type_data=td.hex()))
            self.classes[self.handler_k] = dict(klass=hex(self.handler_k), name=name, namespace=namespace,
                                                fields=fields, instance_size=72, parent=hex(self.base_k))
            self.memory.number(self.handler_k + 0x68, self.meta + self.specs[pc.SINGLE_HANDLER]["type_definition_offset"])
            self.memory.number(self.handler_k + 0x11C, pc.HANDLER_SPEC["token"], "i")
            self.memory.number(self.handler + 0x38, self.npc)

    def state(self, npc=None):
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r, k: self.classes.get(k)):
            return pc.require_safe_persuasion_context(self.resolver, self.npc if npc is None else npc)


class PersuasionContextTests(unittest.TestCase):
    def test_single_scene_binds_current_npc_and_main_scene_still_supported(self):
        for single in (True, False):
            fx = PersuasionFixture(single)
            state = fx.state()
            self.assertEqual(state["status"], "safe_persuasion_nonbattle")
            self.assertEqual(state["identity"]["space_class"], pc.SINGLE_HANDLER if single else pc.MAIN_HANDLER)
            self.assertEqual(state["identity"]["scene_npc"], fx.npc if single else None)
            if single:
                proof = next(a for a in state["anchors"] if a["address"] == fx.handler + 0x38)
                self.assertEqual(proof["expected_hex"], struct.pack("<Q", fx.npc).hex())

    def test_wrong_or_missing_scene_npc_never_authorizes_current_panel(self):
        for value in (0, 1, 0xB0000):
            fx = PersuasionFixture(); fx.memory.number(fx.handler + 0x38, value)
            with self.subTest(value=value), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_invalid_expected_npc_rejected_even_in_main_scene(self):
        for value in (0, 1, -8, True, "0xA0000"):
            fx = PersuasionFixture(single=False)
            with self.subTest(value=value), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state(npc=value)

    def test_unknown_battle_subspace_or_other_minigame_not_whitelisted(self):
        for name in ("SubSpaceHandler", "BattleSpaceHandler", "RefiningPillsSpaceHandler", "FakeSingleSpaceHandler"):
            fx = PersuasionFixture(); fx.classes[fx.handler_k]["name"] = name
            with self.subTest(name=name), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_metadata_identity_field_layout_and_parent_chain_must_match(self):
        for kind in ("token", "definition", "field_token", "field_count", "field_type", "field_offset", "parent"):
            fx = PersuasionFixture()
            fields = fx.classes[fx.handler_k]["fields"]
            field = next(f for f in fields if f["name"] == "CurNpc")
            if kind == "token": fx.memory.number(fx.handler_k + 0x11C, 0, "i")
            elif kind == "definition": fx.memory.number(fx.handler_k + 0x68, 0)
            elif kind == "field_token": field["token"] = "0x400ffff"
            elif kind == "field_count": fields.pop()
            elif kind == "field_type":
                td = bytearray.fromhex(field["type_data"]); td[10] = 8; field["type_data"] = td.hex()
            elif kind == "field_offset": field["offset"] = 0x30
            else: fx.memory.number(fx.handler_k + 0x58, fx.main_k)
            with self.subTest(kind=kind), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()

    def test_handler_identity_and_parent_are_in_request_proof(self):
        fx = PersuasionFixture(); state = fx.state()
        for address in (fx.space + 64, fx.handler_k + 0x58, fx.handler_k + 0x68,
                        fx.handler_k + 0x11C, fx.base_k + 0x68, fx.handler + 0x38):
            self.assertTrue(any(a["address"] == address for a in state["anchors"]))

    def test_lifecycle_and_pending_transition_guards_remain(self):
        for base, offsets in (("main", (33, 68, 69, 70, 71)), ("space", (96, 112)), ("life", (56, 57))):
            for offset in offsets:
                fx = PersuasionFixture(); fx.memory.number(getattr(fx, base) + offset, 1, "B")
                with self.subTest(base=base, offset=offset), self.assertRaises(ac.AcquisitionContextRefused):
                    fx.state()
        for offset in (80, 104):
            fx = PersuasionFixture(); fx.memory.number(fx.space + offset, 0xDEAD00)
            with self.subTest(offset=offset), self.assertRaises(ac.AcquisitionContextRefused):
                fx.state()
        fx = PersuasionFixture(); fx.memory.number(fx.main + 32, 0, "B")
        with self.assertRaises(ac.AcquisitionContextRefused): fx.state()

    def test_wave_presence_and_ambiguous_wave_refused(self):
        fx = PersuasionFixture(); fx.resolved_wave(0xBAD000)
        with self.assertRaises(ac.AcquisitionContextRefused): fx.state()
        fx.resolved_wave()
        self.assertEqual(fx.state()["identity"]["wave_state"], "no_instance")
        for value in (0, 1, ac.WAVE_COLD_USAGE + 2):
            fx.memory.number(fx.module + ac.WAVE_CLASS_RVA, value)
            with self.subTest(value=value), self.assertRaises(ac.AcquisitionContextRefused): fx.state()

    def test_scene_or_npc_change_during_read_refused(self):
        for field in ("scene", "npc"):
            fx = PersuasionFixture(); original = fx.memory.read; count = 0
            target = fx.space + 64 if field == "scene" else fx.handler + 0x38
            def read(address, size):
                nonlocal count
                if address == target:
                    count += 1
                    if count > 1: return struct.pack("<Q", 0xDEAD00)
                return original(address, size)
            fx.memory.read = read
            with self.subTest(field=field), self.assertRaisesRegex(ac.AcquisitionContextRefused, "读取期间"):
                fx.state()

    def test_repeated_real_context_reads_do_not_reuse_old_scene_npc(self):
        fx = PersuasionFixture()
        first = fx.state(); second = fx.state()
        self.assertEqual(first, second)
        fx.memory.number(fx.handler + 0x38, fx.npc + 8)
        with self.assertRaises(ac.AcquisitionContextRefused): fx.state()

    def test_item_acquisition_permissions_are_unchanged(self):
        fx = PersuasionFixture()
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r, k: fx.classes.get(k)):
            with self.assertRaises(ac.AcquisitionContextRefused):
                ac.require_safe_acquisition_context(fx.resolver)
        main = PersuasionFixture(single=False)
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r, k: main.classes.get(k)):
            self.assertEqual(ac.require_safe_acquisition_context(main.resolver)["status"], "safe_nonbattle")

    def test_shared_errors_use_persuasion_wording_and_read_failure_refuses(self):
        fx = PersuasionFixture(); fx.memory.number(fx.space + 96, 1, "B")
        with self.assertRaises(ac.AcquisitionContextRefused) as caught: fx.state()
        self.assertIn("执行说服", str(caught.exception))
        self.assertNotIn("添加", str(caught.exception))
        fx = PersuasionFixture()
        fx.memory.read = lambda *_: (_ for _ in ()).throw(OSError("process exited"))
        with self.assertRaisesRegex(ac.AcquisitionContextRefused, "无法核对当前说服场景"):
            fx.state()


if __name__ == "__main__":
    unittest.main()
