"""Real persuasion resolver + concurrent NPC reader over offline byte memory.

Only OS setup and the lowest-level class inspector are replaced. In particular,
the constructor, membership route, shared container decoder, field guards and
PhotostoneResolver.info all execute their production implementations.
"""
from copy import deepcopy
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import learning_adapter
import persuasion_adapter as pa
from extension_runtime import reviewed
from test_runtime_metadata import metadata
from runtime_metadata import RuntimeMetadataError
from write_guard import Refused


class OfflineMemory:
    meta = 0x10000000
    module = 0x40000000
    h = 1
    path = Path("offline/WorldApart.exe")
    stamp = (123, 456)
    dictionary, tables = 0x10000, 0x11000
    buckets, locks, counts = 0x12000, 0x13000, 0x14000
    node, uuid_pointer, npc, world = 0x16000, 0x17000, 0x18000, 0x19000
    uuid = "45ed0f07-d7ba-446b-a759-9b342798d593"

    def __init__(self):
        self.memory, self.classes, self.class_addresses = {}, {}, {}
        layouts = {
            "Game.Model.GameWorldModel": {"<NpcModels>k__BackingField": (0x15, 0x38)},
            "System.Collections.Concurrent.ConcurrentDictionary`2": {"_tables": (0x15, 16)},
            ".Tables": {"_buckets": (0x1D, 16), "_locks": (0x1D, 24), "_countPerLock": (0x1D, 32)},
            ".Node": {"_key": (0x11, 16), "_value": (0x12, 24), "_next": (0x15, 32), "_hashcode": (8, 40)},
            "System.String": {"_stringLength": (8, 16), "_firstChar": (3, 20)},
            "System.Int32": {}, ".Node[]": {}, "System.Object[]": {}, "System.Int32[]": {},
        }
        for index, (fullname, offsets) in enumerate(layouts.items()):
            klass = 0x100000 + index * 0x1000
            self.class_addresses[fullname] = klass
            namespace, name = fullname.rsplit(".", 1)
            spec = pa.SPECS.get(fullname)
            fields = []
            for declared in spec["fields"] if spec else []:
                kind, offset = offsets.get(declared["name"], (8, 16))
                type_pointer = (self.meta + pa.SPECS["SimpleSave.EntityID"]["type_definition_offset"]
                                if fullname == ".Node" and declared["name"] == "_key" else 0)
                data = struct.pack("<Q", type_pointer) + bytes((0, 0, kind, 0)) + bytes(4)
                fields.append(dict(name=declared["name"], token=hex(declared["token"]),
                                   offset=offset, parent=hex(klass), type_data=data.hex()))
            self.classes[klass] = dict(klass=hex(klass), namespace=namespace, name=name,
                                      parent="0x0", instance_size=48 if fullname == ".Node" else 1024,
                                      fields=fields)
            if spec:
                self.put_int(klass + 0x11C, spec["token"])
                if fullname in ("System.Collections.Concurrent.ConcurrentDictionary`2", ".Tables", ".Node"):
                    generic, definition = klass + 0x400, klass + 0x500
                    self.put_pointer(klass + 0x68, 0)
                    self.put_pointer(klass + 0x60, generic)
                    self.put_pointer(generic, definition)
                    self.put_pointer(generic + 24, klass)
                    self.put(definition, struct.pack("<Q", self.meta + spec["type_definition_offset"])
                             + bytes((0, 0, 0x12, 0)) + bytes(4))
                else:
                    self.put_pointer(klass + 0x68, self.meta + spec["type_definition_offset"])

        for obj, full in ((self.world, "Game.Model.GameWorldModel"),
                          (self.dictionary, "System.Collections.Concurrent.ConcurrentDictionary`2"),
                          (self.tables, ".Tables"), (self.buckets, ".Node[]"),
                          (self.locks, "System.Object[]"), (self.counts, "System.Int32[]"),
                          (self.node, ".Node"), (self.uuid_pointer, "System.String")):
            self.put_pointer(obj, self.class_addresses[full])
        self.put_pointer(self.world + 0x38, self.dictionary)
        self.put_pointer(self.dictionary + 16, self.tables)
        self.put(self.tables + 16, struct.pack("<QQQ", self.buckets, self.locks, self.counts))
        self.put_pointer(self.class_addresses[".Node[]"] + 0x40, self.class_addresses[".Node"])
        self.put_pointer(self.class_addresses["System.Int32[]"] + 0x40, self.class_addresses["System.Int32"])
        self.put_pointer(self.buckets + 24, 3)
        self.put_pointer(self.locks + 24, 2)
        self.put_pointer(self.counts + 24, 2)
        self.put(self.buckets + 32, struct.pack("<QQQ", 0, self.node, 0))
        self.put(self.locks + 32, struct.pack("<QQ", 0x20000, 0x21000))
        self.put(self.counts + 32, struct.pack("<ii", 0, 1))
        self.put(self.node + 16, struct.pack("<QQQi", self.uuid_pointer, self.npc, 0, 1))
        self.put_int(self.uuid_pointer + 16, len(self.uuid))
        self.put(self.uuid_pointer + 20, self.uuid.encode("utf-16-le"))
        self.put(self.module + 0x15F0E43, bytes.fromhex("488b0d1e6ab606"))

    def put(self, address, raw):
        self.memory.update((address + i, value) for i, value in enumerate(raw))

    def put_pointer(self, address, value):
        self.put(address, struct.pack("<Q", value))

    def put_int(self, address, value):
        self.put(address, struct.pack("<i", value))

    def read(self, address, size):
        return bytes(self.memory[address + i] for i in range(size))

    def inspect_class(self, reader, klass, **kwargs):
        assert reader is self
        return deepcopy(self.classes[klass])

    def install_metadata(self, specifications):
        """Give the real runtime lookup independent current table bytes.

        Runtime class/field identities are relocated to this compact metadata;
        the original reviewed offsets and tokens remain deliberately different.
        """
        declarations = {name: reviewed(name, spec) for name, spec in specifications.items()}
        for row in list(declarations.values()):
            owner = row.get('declaring_type')
            if owner and owner not in declarations:
                declarations[owner] = reviewed(owner)
        rows = sorted(declarations.items(), key=lambda item: (item[1]['image_name'], item[0]))
        blob, current = metadata([(name, row['image_name'], [f['name'] for f in row['fields']])
                                  for name, row in rows], gap=3, token_shift=1000, index_shift=400)
        for name, row in rows:
            spec = current[name]
            owner = row.get('declaring_type')
            struct.pack_into('<i', blob, spec['typeDefinitionFileOffset'] + 12,
                             current[owner]['byval'] if owner else -1)
        self.put(self.meta, blob)
        self.metadata_specs = current
        self.metadata_images = {}
        relocation = {self.meta + old['type_definition_offset']:
                      self.meta + current[name]['typeDefinitionFileOffset']
                      for name, old in specifications.items()}
        for full, klass in self.class_addresses.items():
            if full not in current:
                continue
            spec = current[full]
            self.put_int(klass + 0x11C, int(spec['token'], 16))
            handle = struct.unpack('<Q', self.read(klass + 0x68, 8))[0]
            self.put_pointer(klass + 0x68 if handle else klass + 0x500,
                             self.meta + spec['typeDefinitionFileOffset'])
            fields = {f['name']: f for f in spec['fields']}
            for field in self.classes[klass]['fields']:
                field['token'] = fields[field['name']]['token']
                raw = bytearray.fromhex(field['type_data'])
                pointer = struct.unpack_from('<Q', raw)[0]
                if raw[10] == 0x11 and pointer in relocation:
                    struct.pack_into('<Q', raw, 0, relocation[pointer])
                    field['type_data'] = raw.hex()
            image = 0x600000 + len(self.metadata_images) * 0x100
            label = image + 0x80
            self.metadata_images[label] = declarations[full]['image_name']
            self.put_pointer(klass, image)
            self.put_pointer(image, label)

    def string(self, address):
        return self.metadata_images[address]


class PersuasionResolverIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.memory = mem = OfflineMemory()
        mem.install_metadata(pa.SPECS)
        self.enterContext(patch.object(learning_adapter, "process_identity", return_value=mem.stamp))
        self.enterContext(patch.object(pa, "process_identity", return_value=mem.stamp))
        self.enterContext(patch.object(learning_adapter, "validate_installation", return_value=SimpleNamespace(
            executable_path=mem.path, install_directory=mem.path.parent)))
        self.enterContext(patch.object(learning_adapter.probe, "verified_mappings", return_value={
            "metadata": [{"base": mem.meta}], "game_assembly": [{"base": mem.module}]}))
        self.inspector = self.enterContext(patch.object(learning_adapter.probe, "inspect_class", side_effect=mem.inspect_class))
        self.resolver = pa.PersuasionResolver(mem, metadata_base=mem.meta)

    def membership(self):
        m = self.memory
        return self.resolver.npc_membership(m.world, m.npc, 1001)

    def refresh_without_active_panel(self):
        adapter = pa.PersuasionAdapter.__new__(pa.PersuasionAdapter)
        adapter.blocked = False
        adapter.resolver = self.resolver
        adapter.game = SimpleNamespace(blocked=False, resolver=SimpleNamespace(reader=self.memory), stamp=self.memory.stamp)
        # No native object, journal, broker or process is needed to exercise the
        # real snapshot reset path. The panel registry is unrelated to this bug.
        with patch.object(self.resolver, "registered_panels", return_value=(0x22000, [])):
            self.assertFalse(adapter.snapshot()["active"])

    def test_first_membership_traverses_real_shared_resolver_and_proves_metadata(self):
        result = self.membership()
        self.assertEqual(result["uuid"], self.memory.uuid)
        self.assertEqual(result["node"], hex(self.memory.node))
        self.assertEqual(result["npc"], hex(self.memory.npc))
        self.assertEqual(result["dictionary_descriptor"]["count"], 1)
        proof = self.resolver.proof()
        addresses = {int(a["address"], 16) for a in proof}
        for name in ("System.Collections.Concurrent.ConcurrentDictionary`2", ".Tables", ".Node"):
            klass = self.memory.class_addresses[name]
            self.assertIn(klass, self.resolver._class_cache)
            self.assertIn(klass + 0x500, addresses)

    def test_next_snapshot_discards_cache_and_rebuilds_complete_metadata_proof(self):
        self.membership()
        original_proof = self.resolver.proof()
        first_inspection_count = self.inspector.call_count
        self.refresh_without_active_panel()
        self.assertEqual(self.resolver._class_cache, {})
        self.assertEqual(self.resolver.anchors, [])
        self.membership()
        self.assertGreater(self.inspector.call_count, first_inspection_count)
        self.assertEqual(self.resolver.proof(), original_proof)

    def test_current_metadata_relocation_is_used_and_changes_latch_rejection(self):
        m = self.memory
        current = m.metadata_specs['.Node']
        self.assertNotEqual(current['typeDefinitionFileOffset'],
                            pa.SPECS['.Node']['type_definition_offset'])
        self.assertNotEqual(int(current['token'], 16), pa.SPECS['.Node']['token'])
        self.membership()
        address = m.meta + current['typeDefinitionFileOffset'] + 84
        previous = m.read(address, 4)
        m.put_int(address, int(current['token'], 16) + 1)
        self.refresh_without_active_panel()
        with self.assertRaises(RuntimeMetadataError):
            self.membership()
        m.put(address, previous)
        self.refresh_without_active_panel()
        with self.assertRaises(RuntimeMetadataError):
            self.membership()

    def test_next_snapshot_rejects_changed_generic_definition(self):
        self.membership()
        klass = self.memory.class_addresses[".Node"]
        self.memory.put_pointer(klass + 0x500, self.memory.meta + 1)
        self.refresh_without_active_panel()
        with self.assertRaisesRegex(Refused, "元数据"):
            self.membership()

    def test_next_snapshot_rejects_changed_field_token_or_layout(self):
        self.membership()
        node = self.memory.classes[self.memory.class_addresses[".Node"]]
        key = next(field for field in node["fields"] if field["name"] == "_key")
        original = deepcopy(key)
        for change in ({"token": "0x4000000"}, {"offset": 20}):
            with self.subTest(change=change):
                key.clear()
                key.update(original, **change)
                self.refresh_without_active_panel()
                with self.assertRaises(Refused):
                    self.membership()


if __name__ == "__main__":
    unittest.main()
