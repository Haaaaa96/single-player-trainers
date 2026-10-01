"""Acquisition is refused before injection in battle or ambiguous contexts."""
import struct
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import acquisition_context as ac


def metadata_fixture(memory, base, *, current=False):
    """Actual metadata-31 tables: exercise RuntimeSpecs without replacing it."""
    specs = dict(ac.SPECS)
    for filename, names in (("persuasion_specs.json", ("Game.SpaceHandlers.SingleSpaceHandler",)),
                            ("alchemy_specs.json", ("Game.SpaceHandlers.RefiningPillsSpaceHandler",
                                                    "Game.SpaceHandlers.SubSpaceHandler"))):
        extra = json.loads((ac.HERE / filename).read_text(encoding="utf8"))["metadata"]
        specs.update({name: extra[name] for name in names})
    ordered = sorted(specs, key=lambda name: (name.startswith("System."), name))
    strings = bytearray(b"\0"); names = {"": 0}
    def string(name):
        if name not in names:
            names[name] = len(strings); strings.extend(name.encode() + b"\0")
        return names[name]
    type_rows, field_rows = [], []
    dynamic = {}
    for index, fullname in enumerate(ordered):
        spec = specs[fullname]
        namespace, _, name = fullname.rpartition(".")
        row = [0] * 26
        row[:5] = [string(name), string(namespace),
                   (71243 if current else 71254) if name == "WaveCombatManager" else index + 1, -1, -1]
        row[8], row[18], row[25] = len(field_rows), len(spec["fields"]), spec["token"]
        for f in spec["fields"]:
            field_rows.append((string(f["name"]), 8, f["token"]))
        type_rows.append(row)
    game_image, system_image = string("Game.dll"), string("mscorlib.dll")
    type_offset = 256 + len(strings)
    field_offset = type_offset + 88 * len(type_rows)
    image_offset = field_offset + 12 * len(field_rows)
    header = bytearray(256)
    struct.pack_into("<II", header, 0, 0xFAB11BAF, 31)
    for position, offset, size in ((0x18,256,len(strings)), (0xA0,type_offset,len(type_rows)*88),
                                  (0x60,field_offset,len(field_rows)*12),(0xA8,image_offset,80)):
        struct.pack_into("<II",header,position,offset,size)
    game_count = sum(not name.startswith("System.") for name in ordered)
    images = (struct.pack("<iiiIiIiIiI",game_image,0,0,game_count,0,0,0,0,0,0)
              +struct.pack("<iiiIiIiI",system_image,0,game_count,len(ordered)-game_count,0,0,0,0)
              + b"\0"*8)
    raw = (header + strings + b"".join(struct.pack("<16i8H2I",*row) for row in type_rows)
           + b"".join(struct.pack("<iiI",*row) for row in field_rows) + images)
    memory.put(base, raw)
    for index, fullname in enumerate(ordered):
        dynamic[fullname] = {**specs[fullname], "type_definition_offset":type_offset+index*88}
    return dynamic


class Memory:
    def __init__(self):
        self.data = {}
        self.regions = [dict(base=0x10000000, allocation=0x10000000, type=0x1000000)]

    def put(self, address, raw):
        self.data.update({address + i: b for i, b in enumerate(raw)})

    def number(self, address, value, fmt="Q"):
        self.put(address, struct.pack("<" + fmt, value))

    def read(self, address, size):
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError:
            return b""

    def mapped(self, address):
        return "C:\\game\\GameAssembly.dll"


class Fixture:
    def __init__(self):
        self.memory = m = Memory()
        self.meta, self.module = 0x20000000, 0x10000000
        self.specs = metadata_fixture(m, self.meta)
        self.classes = {}
        self.main, self.space, self.life, self.handler = 0x10000, 0x20000, 0x30000, 0x40000
        self.listing, self.array = 0x50000, 0x60000
        self.main_k, self.space_k, self.life_k = 0x100000, 0x110000, 0x120000
        self.handler_k, self.base_k, self.list_k, self.wave_k = 0x130000, 0x140000, 0x150000, 0x160000
        self.main_sf, self.wave_sf = 0x70000, 0x80000
        for rva, raw in ac.CODE_PROOFS.items():
            m.put(self.module + rva, bytes.fromhex(raw))
        self.add_class(self.main_k, "Game.A1Main", 80, [
            ("_instance", 0, 0x12, True), ("_managers", 48, 0x15),
            ("<IsInitialized>k__BackingField", 32, 2), ("_isDestroying", 33, 2),
            ("m_IsStarting", 68, 2), ("m_QuitRequested", 69, 2),
            ("m_QuitAllowed", 70, 2), ("m_ManagersDestroyed", 71, 2)])
        self.add_class(self.space_k, "Game.SpaceManager", 136, [
            ("_currentSpaceHandler", 64, 0x12), ("_pendingChangeSpaceRequest", 80, 0x12),
            ("_isTransitioning", 96, 2), ("m_TransitionPreparation", 104, 0x12),
            ("m_IsUnloadingWorld", 112, 2)])
        self.add_class(self.life_k, "Game.GameLifecycleManager", 80, [
            ("m_IsLeaving", 56, 2), ("m_ShuttingDown", 57, 2)])
        self.add_class(self.handler_k, "Game.SpaceHandlers.MainSpaceHandler", 64, [], parent=self.base_k)
        self.add_class(self.base_k, "Game.SpaceHandlers.BaseSpaceHandler", 56, [])
        self.add_class(self.list_k, "System.Collections.Generic.List`1", 40, [
            ("_items", 16, 0x1D), ("_size", 24, 8), ("_version", 28, 8)])
        self.add_class(self.wave_k, "Game.Logic.Combat.WaveCombatManager", 256, [
            ("<Instance>k__BackingField", 104, 0x12, True)])
        for obj, klass, size in ((self.main,self.main_k,80),(self.space,self.space_k,136),
                                 (self.life,self.life_k,80),(self.handler,self.handler_k,64),
                                 (self.listing,self.list_k,40)):
            m.put(obj,b"\0"*size);m.number(obj,klass)
        m.number(self.module+ac.A1_MAIN_CLASS_RVA,self.main_k)
        m.number(self.main_k+0xB8,self.main_sf);m.number(self.main_sf,self.main)
        m.number(self.main+16,0xDEAD0000);m.number(self.main+32,1,"B")
        m.number(self.main+48,self.listing);m.number(self.listing+16,self.array)
        m.number(self.listing+24,2,"i");m.number(self.array+24,4)
        m.number(self.array+32,self.space);m.number(self.array+40,self.life)
        m.number(self.space+64,self.handler)
        m.number(self.module+ac.WAVE_CLASS_RVA,ac.WAVE_COLD_USAGE)
        self.resolver=SimpleNamespace(reader=m,meta=self.meta)

    def add_class(self, address, fullname, size, layouts, parent=0):
        namespace,_,name=fullname.rpartition(".")
        layouts={f[0]:f[1:] for f in layouts}
        fields=[]
        for spec in self.specs[fullname]["fields"]:
            layout=layouts.get(spec["name"],(16,8))
            offset,kind=layout[:2];static=len(layout)>2 and layout[2]
            data=bytearray(16);data[8]=0x11 if static else 1;data[10]=kind
            fields.append(dict(name=spec["name"],token=hex(spec["token"]),offset=offset,
                               parent=hex(address),type_data=data.hex()))
        self.classes[address]=dict(klass=hex(address),name=name,namespace=namespace,
                                   fields=fields,instance_size=size,parent=hex(parent))
        self.memory.number(address+0x68,self.meta+self.specs[fullname]["type_definition_offset"])
        self.memory.number(address+0x11C,self.specs[fullname]["token"],"i")
        self.memory.number(address+0x58,parent)

    def resolved_wave(self, instance=0):
        self.memory.number(self.module+ac.WAVE_CLASS_RVA,self.wave_k)
        self.memory.number(self.wave_k+0xB8,self.wave_sf)
        self.memory.number(self.wave_sf+104,instance)

    def state(self):
        with patch.object(ac.probe,"inspect_class",side_effect=lambda r,k:self.classes.get(k)):
            return ac.require_safe_acquisition_context(self.resolver)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.fx=Fixture()

    def test_settled_main_scene_and_exact_cold_wave_are_two_signals(self):
        result=self.fx.state()
        self.assertEqual(result["status"],"safe_nonbattle")
        self.assertEqual(result["identity"]["space_handler"],self.fx.handler)
        self.assertEqual(result["identity"]["wave_state"],"never_initialized")
        required=[self.fx.space+64,self.fx.space+96,self.fx.module+ac.WAVE_CLASS_RVA]
        self.assertTrue(all(any(a["address"]==x for a in result["anchors"]) for x in required))

    def test_resolved_wave_class_with_no_instance_is_allowed(self):
        self.fx.resolved_wave()
        result=self.fx.state()
        self.assertEqual(result["identity"]["wave_state"],"no_instance")
        self.assertTrue(any(a["address"]==self.fx.wave_sf+104 for a in result["anchors"]))

    def test_inflated_generic_list_requires_reviewed_definition(self):
        m=self.fx.memory;g,t=0x90000,0xA0000
        m.number(self.fx.list_k+0x68,0);m.number(self.fx.list_k+0x60,g)
        m.number(g,t);m.number(g+24,self.fx.list_k)
        td=bytearray(16);struct.pack_into("<Q",td,0,self.fx.meta+self.fx.specs["System.Collections.Generic.List`1"]["type_definition_offset"]);td[10]=0x12;m.put(t,td)
        self.assertEqual(self.fx.state()["status"],"safe_nonbattle")
        m.number(g+24,self.fx.wave_k)
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_battle_handler_refused_even_without_wave_instance(self):
        self.fx.classes[self.fx.handler_k]["name"]="BattleSpaceHandler"
        with self.assertRaisesRegex(ac.AcquisitionContextRefused,"战斗中"):
            self.fx.state()

    def test_unknown_or_missing_handler_is_never_treated_as_safe(self):
        for name in ("TutorialHandler","FakeMainSpaceHandler","BaseSpaceHandler"):
            self.fx.classes[self.fx.handler_k]["name"]=name
            with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()
        self.fx.memory.number(self.fx.space+64,0)
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_existing_wave_instance_refused_even_if_main_handler_lingers(self):
        self.fx.resolved_wave(instance=0xE0000)
        with self.assertRaisesRegex(ac.AcquisitionContextRefused,"战斗"):
            self.fx.state()

    def test_unknown_wave_slot_or_missing_statics_refused(self):
        for value in (0,1,ac.WAVE_COLD_USAGE+2,0xF0000):
            self.fx.memory.number(self.fx.module+ac.WAVE_CLASS_RVA,value)
            with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()
        self.fx.resolved_wave();self.fx.memory.number(self.fx.wave_k+0xB8,0)
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_all_transition_and_shutdown_flags_refused(self):
        for base, offsets in (("main",[33,68,69,70,71]),("space",[96,112]),("life",[56,57])):
            for offset in offsets:
                with self.subTest(base=base,offset=offset):
                    fx=Fixture();fx.memory.number(getattr(fx,base)+offset,1,"B")
                    with self.assertRaises(ac.AcquisitionContextRefused):fx.state()
        self.fx.memory.number(self.fx.main+32,0,"B")
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_queued_transition_and_preparation_refused(self):
        for offset in (80,104):
            fx=Fixture();fx.memory.number(fx.space+offset,0xE0000)
            with self.assertRaises(ac.AcquisitionContextRefused):fx.state()

    def test_corrupt_boolean_refused(self):
        self.fx.memory.number(self.fx.space+96,2,"B")
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_duplicate_manager_and_short_array_refused(self):
        self.fx.memory.number(self.fx.array+40,self.fx.space)
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()
        self.fx=Fixture();del self.fx.memory.data[self.fx.array+35]
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_wrong_code_metadata_and_field_kind_refused(self):
        rva=next(iter(ac.CODE_PROOFS));self.fx.memory.number(self.fx.module+rva,0,"B")
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()
        self.fx=Fixture();self.fx.memory.number(self.fx.space_k+0x11C,0,"i")
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()
        self.fx=Fixture();f=next(f for f in self.fx.classes[self.fx.space_k]["fields"] if f["name"]=="_isTransitioning")
        td=bytearray.fromhex(f["type_data"]);td[10]=8;f["type_data"]=td.hex()
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_scene_change_during_read_is_refused(self):
        original=self.fx.memory.read;calls=0;target=self.fx.space+64
        def read(address,size):
            nonlocal calls
            if address==target:
                calls+=1
                if calls>1:return struct.pack("<Q",0)
            return original(address,size)
        self.fx.memory.read=read
        with self.assertRaisesRegex(ac.AcquisitionContextRefused,"检测期间"):
            self.fx.state()

    def test_unexpected_read_error_is_local_context_refusal(self):
        self.fx.memory.read=lambda *_: (_ for _ in ()).throw(OSError("process exited"))
        with self.assertRaises(ac.AcquisitionContextRefused):self.fx.state()

    def test_current_relocated_profile_uses_current_metadata_cold_usage(self):
        fx = self.fx
        fx.specs = metadata_fixture(fx.memory, fx.meta, current=True)
        fx.memory.number(fx.module + next(iter(ac.CODE_PROOFS)), 0, "B")
        profile = ac.CODE_PROFILES[1]
        for rva, raw in profile["code"].items():
            fx.memory.put(fx.module + rva, bytes.fromhex(raw))
        fx.memory.number(fx.module + profile["main_slot"], fx.main_k)
        fx.memory.number(fx.module + profile["wave_slot"], 0x20000001 | (profile["wave_byval"] << 1))
        state = fx.state()
        self.assertEqual(state["identity"]["wave_state"], "never_initialized")
        self.assertTrue(any(a["address"] == fx.module + profile["wave_slot"] for a in state["anchors"]))
        # A valid old cold token at the new slot must not mean no battle.
        fx.memory.number(fx.module + profile["wave_slot"], ac.WAVE_COLD_USAGE)
        with self.assertRaises(ac.AcquisitionContextRefused): fx.state()

    def test_tokens_are_checked_against_current_metadata_not_bundled_numbers(self):
        fx = self.fx
        offset = fx.specs["Game.A1Main"]["type_definition_offset"]
        fx.memory.number(fx.meta + offset + 84, 0x0200F001, "I")
        fx.memory.number(fx.main_k + 0x11C, 0x0200F001, "I")
        self.assertEqual(fx.state()["status"], "safe_nonbattle")
        fx.memory.number(fx.main_k + 0x11C, ac.SPECS["Game.A1Main"]["token"], "I")
        with self.assertRaises(ac.AcquisitionContextRefused): fx.state()

    def test_real_context_repeated_snapshot_rebuilds_proofs_and_rejects_metadata_change(self):
        fx = self.fx
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r,k: fx.classes.get(k)):
            obj = ac._Context(fx.resolver)
            first = obj.snapshot()
            second = obj.snapshot()
            self.assertEqual(first, second)
            self.assertIsNot(first["anchors"], second["anchors"])
            offset = fx.specs["Game.A1Main"]["type_definition_offset"]
            fx.memory.number(fx.meta + offset + 84, 0x0200F001, "I")
            with self.assertRaisesRegex(Exception, "metadata|Metadata"): obj.snapshot()

    def test_same_instance_rejects_changed_code_and_changed_scene(self):
        fx = self.fx
        with patch.object(ac.probe, "inspect_class", side_effect=lambda r,k: fx.classes.get(k)):
            obj = ac._Context(fx.resolver)
            obj.snapshot()
            fx.memory.number(fx.space + 96, 1, "B")
            with self.assertRaises(ac.AcquisitionContextRefused): obj.snapshot()
            fx.memory.number(fx.space + 96, 0, "B")
            fx.memory.number(fx.module + next(iter(ac.CODE_PROOFS)), 0, "B")
            with self.assertRaisesRegex(ac.AcquisitionContextRefused, "代码"): obj.snapshot()


if __name__=="__main__":unittest.main()
