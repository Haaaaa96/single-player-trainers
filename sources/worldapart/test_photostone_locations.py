"""Live-location routes over byte memory; no game, broker or native calls.

The real constructor, class verifier, SpaceUuid concurrent collection reader,
NPC/world ownership, field guards, refresh cache reset and proof reread run here.
Only OS setup, class inspection and the shared Dictionary decoder are
substituted; the full localized read is additionally checked against the game.
"""
from copy import deepcopy
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import Mock, patch

import learning_adapter
import photostone_adapter as pa
from test_persuasion_resolver_integration import OfflineMemory
from write_guard import Refused


class LocationMemory(OfflineMemory):
    space, config, config_tables, space_table = 0x23000, 0x24000, 0x25000, 0x26000
    listing, array, city, room, languages_city, languages_room = (0x27000, 0x28000, 0x29000, 0x2A000, 0x2B000, 0x2C000)

    def __init__(self):
        super().__init__()
        self.add_class("Game.Model.NpcModel", {
            "<NpcCfgId>k__BackingField": (0x11, 0x150), "<CurrentSpaceUuid>k__BackingField": (0x11, 0x158),
            "<WorldStatus>k__BackingField": (0x11, 0x160), "<GameWorld>k__BackingField": (0x12, 0x168)})
        self.add_class("Game.Model.SpaceModel", {"<SpaceId>k__BackingField": (0x11, 0x24),
            "<WorldStatus>k__BackingField": (0x11, 0x30), "<GameWorld>k__BackingField": (0x12, 0x68)})
        self.add_class("Game.ConfigManager", {"<Tables>k__BackingField": (0x12, 0x18)})
        self.add_class("LubanDatas.Tables", {"Current": (0x12, 0), "<TbSpace>k__BackingField": (0x12, 0xA8)})
        self.add_class("LubanDatas.TbSpace", {"_overrides": (0x15, 0x20), "_dataList": (0x15, 0x18)})
        self.add_class("LubanDatas.data.Space", {"<id>k__BackingField": (0x11, 0x18),
            "<spaceName>k__BackingField": (0x11, 0x30), "<fatherSpace>k__BackingField": (0x15, 0x28)})
        self.add_class("System.Collections.Generic.List`1", {"_items": (0x1D, 0x10), "_size": (8, 0x18), "_version": (8, 0x1C)})
        self.add_class("Emei.NotifiableList`1", {})
        self.set_field("Game.Model.GameWorldModel", "<Spaces>k__BackingField", kind=0x15, offset=0x30)
        self.set_field(".Node", "_key", value_type="Game.Model.SpaceUuid")
        self.set_field("Game.Model.NpcModel", "<CurrentSpaceUuid>k__BackingField", value_type="Game.Model.SpaceUuid")
        self.set_field("Game.Model.SpaceModel", "<SpaceId>k__BackingField", value_type="LubanDatas.TbSpaceId")
        self.set_field("LubanDatas.data.Space", "<id>k__BackingField", value_type="LubanDatas.TbSpaceId")
        self.set_field("LubanDatas.data.Space", "<spaceName>k__BackingField", value_type="LubanDatas.L10nText")
        for obj, full in ((self.npc, "Game.Model.NpcModel"), (self.space, "Game.Model.SpaceModel"),
                          (self.config, "Game.ConfigManager"), (self.config_tables, "LubanDatas.Tables"),
                          (self.space_table, "LubanDatas.TbSpace"), (self.listing, "Emei.NotifiableList`1"),
                          (self.city, "LubanDatas.data.Space"), (self.room, "LubanDatas.data.Space")):
            self.put_pointer(obj, self.class_addresses[full])
        self.put_pointer(self.world + 0x30, self.dictionary)
        self.put_pointer(self.node + 24, self.space)
        self.put_int(self.npc + 0x150, 1001)
        self.put_pointer(self.npc + 0x158, self.uuid_pointer)
        self.put_int(self.npc + 0x160, 0)
        self.put_pointer(self.npc + 0x168, self.world)
        self.put_int(self.space + 0x24, 2002)
        self.put_int(self.space + 0x30, 0)
        self.put_pointer(self.space + 0x68, self.world)
        self.put_pointer(self.config + 0x18, self.config_tables)
        self.put_pointer(self.class_addresses["LubanDatas.Tables"] + 0xB8, 0x2D000)
        self.put_pointer(0x2D000, self.config_tables)
        self.put_pointer(self.config_tables + 0xA8, self.space_table)
        self.put_pointer(self.space_table + 0x20, 0)
        self.put_pointer(self.space_table + 0x18, self.listing)
        self.put_pointer(self.class_addresses["Emei.NotifiableList`1"] + 0x58, self.class_addresses["System.Collections.Generic.List`1"])
        self.put_pointer(self.listing + 0x10, self.array)
        self.put_int(self.listing + 0x18, 2)
        self.put_int(self.listing + 0x1C, 7)
        self.put_pointer(self.array + 24, 2)
        self.put(self.array + 32, struct.pack("<QQ", self.city, self.room))
        self.put_int(self.city + 0x18, 2001)
        self.put_int(self.room + 0x18, 2002)
        self.put(self.city + 0x28, bytes(8))
        self.put(self.room + 0x28, struct.pack("<ii", 1, 2001))
        self.put_pointer(self.city + 0x30, self.languages_city)
        self.put_pointer(self.room + 0x30, self.languages_room)
        self.translations = {self.languages_city: {"zh-Hans": "河望镇"}, self.languages_room: {"zh-Hans": "客栈大堂"}}

    def add_class(self, fullname, offsets):
        klass = 0x200000 + len(self.classes) * 0x1000
        self.class_addresses[fullname] = klass
        namespace, name = fullname.rsplit(".", 1)
        spec = pa.SPECS["metadata"][fullname]
        fields = []
        for declared in spec["fields"]:
            kind, offset = offsets.get(declared["name"], (8, 16))
            # Tables.Current is the only static field read by this fixture.
            attrs = 0x10 if fullname == "LubanDatas.Tables" and declared["name"] == "Current" else 0
            raw = struct.pack("<Q", 0) + bytes((attrs, 0, kind, 0)) + bytes(4)
            fields.append(dict(name=declared["name"], token=hex(declared["token"]),
                               offset=offset, parent=hex(klass), type_data=raw.hex()))
        self.classes[klass] = dict(klass=hex(klass), namespace=namespace, name=name,
                                  parent="0x0", instance_size=1024, fields=fields)
        self.put_int(klass + 0x11C, spec["token"])
        self.put_pointer(klass + 0x68, self.meta + spec["type_definition_offset"])

    def set_field(self, fullname, name, *, kind=None, offset=None, value_type=None):
        field = next(f for f in self.classes[self.class_addresses[fullname]]["fields"] if f["name"] == name)
        raw = bytearray.fromhex(field["type_data"])
        if kind is not None: raw[10] = kind
        if offset is not None: field["offset"] = offset
        if value_type: struct.pack_into("<Q", raw, 0, self.meta + pa.SPECS["metadata"][value_type]["type_definition_offset"])
        field["type_data"] = raw.hex()
        return field


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.memory = m = LocationMemory()
        m.install_metadata(pa.SPECS['metadata'])
        self.enterContext(patch.object(learning_adapter, "process_identity", return_value=m.stamp))
        self.enterContext(patch.object(learning_adapter, "validate_installation", return_value=SimpleNamespace(
            executable_path=m.path, install_directory=m.path.parent)))
        self.enterContext(patch.object(learning_adapter.probe, "verified_mappings", return_value={
            "metadata": [{"base": m.meta}], "game_assembly": [{"base": m.module}]}))
        self.inspector = self.enterContext(patch.object(learning_adapter.probe, "inspect_class", side_effect=m.inspect_class))
        self.game = SimpleNamespace(resolver=SimpleNamespace(reader=m, meta=m.meta), stamp=m.stamp)
        self.resolver = pa.PhotostoneLocationResolver(self.game)
        self.translations = self.enterContext(patch.object(self.resolver, "dictionary",
            side_effect=lambda p, *args, **kwargs: (deepcopy(m.translations[p]), {})))
        self.raw = dict(world=m.world, anchors=[])
        self.npcs = {1001: dict(pointer=m.npc)}

    def locations(self):
        return self.resolver.locations(self.raw, self.npcs, self.memory.config)

    def test_real_constructor_resolves_current_uuid_to_world_scene_and_parent_name(self):
        row = self.locations()[1001]
        self.assertEqual(row["location_label"], "河望镇 / 客栈大堂")
        self.assertEqual(row["location_space_id"], 2002)
        self.assertIn("当前场景记录", row["location_reason"])
        self.assertNotIn("native", row)
        self.assertNotIn("identity", row)
        self.assertEqual(self.translations.call_count, 2)

    def test_second_refresh_rechecks_metadata_and_observes_movement_and_names(self):
        self.locations()
        inspections = self.inspector.call_count
        self.memory.put_int(self.memory.space + 0x24, 2001)
        self.memory.translations[self.memory.languages_city]["zh-Hans"] = "新城名"
        self.assertEqual(self.locations()[1001]["location_label"], "新城名")
        self.assertGreater(self.inspector.call_count, inspections)

    def test_second_refresh_rejects_changed_collection_type_metadata(self):
        self.locations()
        klass = self.memory.class_addresses[".Node"]
        self.memory.put_pointer(klass + 0x500, self.memory.meta + 1)
        with self.assertRaisesRegex(Refused, "元数据"):
            self.locations()

    def test_second_refresh_rejects_changed_npc_location_field_layout(self):
        self.locations()
        self.memory.set_field("Game.Model.NpcModel", "<CurrentSpaceUuid>k__BackingField", offset=0x150)
        with self.assertRaisesRegex(Refused, "偏移"):
            self.locations()

    def test_space_uuid_wrapper_is_not_mistaken_for_entity_id(self):
        self.memory.set_field(".Node", "_key", value_type="SimpleSave.EntityID")
        with self.assertRaisesRegex(Refused, "包装"):
            self.locations()

    def test_space_id_wrapper_is_verified_before_name_mapping(self):
        self.memory.set_field("Game.Model.SpaceModel", "<SpaceId>k__BackingField", value_type="Game.Model.SpaceUuid")
        with self.assertRaisesRegex(Refused, "包装"):
            self.locations()

    def test_missing_empty_or_unknown_space_does_not_invent_initial_location(self):
        for pointer, length in ((0, None), (self.memory.uuid_pointer, 0)):
            with self.subTest(pointer=pointer, length=length):
                self.memory.put_pointer(self.memory.npc + 0x158, pointer)
                if length is not None:
                    # Separate the NPC string from the dictionary's key string.
                    self.memory.put_pointer(self.memory.npc + 0x158, 0x2E000)
                    self.memory.put_pointer(0x2E000, self.memory.class_addresses["System.String"])
                    self.memory.put_int(0x2E010, length)
                row = self.locations()[1001]
                self.assertIsNone(row["location_space_id"])
                self.assertNotIn("河望镇", row["location_label"])

    def test_inactive_npc_or_scene_does_not_claim_old_place_is_visitable(self):
        for offset, status, label in ((self.memory.npc + 0x160, 1, "角色未登场"),
                                     (self.memory.npc + 0x160, 2, "角色已离场"),
                                     (self.memory.space + 0x30, 1, "场景尚未开放")):
            with self.subTest(status=status, offset=offset):
                self.memory.put_int(offset, status)
                self.assertEqual(self.locations()[1001]["location_label"], label)
                self.memory.put_int(offset, 0)

    def test_wrong_world_and_npc_identity_refuse_display_target(self):
        for address, value in ((self.memory.npc + 0x150, 9999), (self.memory.npc + 0x168, 0),
                               (self.memory.space + 0x68, 0)):
            old = self.memory.read(address, 4)
            self.memory.put_int(address, value)
            with self.subTest(address=address), self.assertRaises(Refused): self.locations()
            self.memory.put(address, old)

    def test_changed_mid_read_rejected_by_display_proof(self):
        original = self.resolver.space_names
        def names(*args):
            result = original(*args)
            self.memory.put_int(self.memory.space + 0x24, 2001)
            return result
        with patch.object(self.resolver, "space_names", side_effect=names):
            with self.assertRaisesRegex(Refused, "读取期间"):
                self.locations()

    def test_bad_name_schema_falls_back_to_verified_scene_id(self):
        self.memory.set_field("LubanDatas.data.Space", "<spaceName>k__BackingField", value_type="Game.Model.SpaceUuid")
        row = self.locations()[1001]
        self.assertEqual((row["location_label"], row["location_space_id"]), ("场景 2002", 2002))
        self.assertIn("场景名称未能核实", row["location_reason"])

    def test_parent_loop_falls_back_without_infinite_read(self):
        self.memory.put(self.memory.city + 0x28, struct.pack("<ii", 1, 2002))
        row = self.locations()[1001]
        self.assertEqual(row["location_label"], "场景 2002")
        self.assertIn("循环", row["location_reason"])

    def test_adjacent_duplicate_labels_are_collapsed(self):
        self.memory.translations[self.memory.languages_room]["zh-Hans"] = "河望镇"
        self.assertEqual(self.locations()[1001]["location_label"], "河望镇")

    def test_names_are_shared_across_npcs_not_scanned_per_stage(self):
        self.npcs[1002] = dict(pointer=0x30000)
        self.memory.put_pointer(0x30000, self.memory.class_addresses["Game.Model.NpcModel"])
        self.memory.put_int(0x30150, 1002)
        self.memory.put_pointer(0x30158, self.memory.uuid_pointer)
        self.memory.put_int(0x30160, 0)
        self.memory.put_pointer(0x30168, self.memory.world)
        rows = self.locations()
        self.assertEqual(rows[1001], rows[1002])
        self.assertEqual(self.translations.call_count, 2)

    def test_location_failure_is_display_only_and_does_not_change_native_proof(self):
        resolver = pa.PhotostoneResolver(self.game)
        resolver.anchors = [(self.memory.world, self.memory.read(self.memory.world, 8).hex())]
        resolver.links = [dict(address="0x20", expected="0x30")]
        old_anchors, old_links = deepcopy(resolver.anchors), deepcopy(resolver.links)
        result = dict(rows=[dict(npc_id=1001, identity="same", can_activate=True,
            native=dict(anchors=[dict(address="0x40", expected_hex="01")]))])
        old_row = deepcopy(result["rows"][0])
        with patch.object(pa.PhotostoneLocationResolver, "locations", side_effect=Refused("位置变化")):
            resolver.append_locations(result, self.raw, self.npcs, self.memory.config)
        self.assertEqual(result["rows"][0]["location_label"], "位置暂不可读")
        self.assertEqual(old_row, {k: v for k, v in result["rows"][0].items() if not k.startswith("location_")})
        self.assertEqual((resolver.anchors, resolver.links), (old_anchors, old_links))

    def test_missing_npc_has_explicit_unknown_location(self):
        resolver = pa.PhotostoneResolver(self.game)
        result = dict(rows=[dict(npc_id=9999)])
        with patch.object(pa.PhotostoneLocationResolver, "locations", return_value={}):
            resolver.append_locations(result, self.raw, {}, self.memory.config)
        self.assertEqual(result["rows"][0]["location_label"], "角色未生成")
        self.assertIsNone(result["rows"][0]["location_space_id"])


class DisplayIsolationTests(unittest.TestCase):
    def test_replay_preview_excludes_location_only_changes(self):
        from test_photostone import npc, catalog
        from photostone_logic import build_rows
        row = build_rows(catalog(), {100: npc()})["rows"][0]
        row.update(location_label="河望镇", location_space_id=2001, location_reason="读取时位置")
        adapter = pa.PhotostoneAdapter.__new__(pa.PhotostoneAdapter)
        adapter.current_row = Mock(return_value=row)
        first = adapter.preview_force(row)
        row["location_label"], row["location_space_id"] = "临州", 3001
        self.assertEqual(adapter.preview_force(row), first)
        self.assertFalse(any(key.startswith("location_") for key in first["row"]))


if __name__ == "__main__":
    unittest.main()
