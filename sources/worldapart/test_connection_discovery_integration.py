"""Real discovery/resolver construction over bounded offline metadata and memory.

Only the process reader, verified OS mapping identities and GetProcessTimes are
replaced. Metadata lookup, class scanning, cache publication, class verification
and field semantics execute their production paths. No game is opened.
"""
from contextlib import ExitStack
import copy
import ctypes
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_class_discovery import Memory
from test_runtime_metadata import metadata
import discovery
import probe
import resolver
from connection_diagnostics import ConnectionDiagnosticError
from runtime_metadata import MetadataError, RuntimeSpecs


PID = 77
CREATION_TIME = (9 << 32) | 8765
PLAYER = 'Game.Model.PlayerModel'


class RuntimeMemory(Memory):
    """Share byte storage across distinct reader lifetimes without OS handles."""

    def __init__(self, current_data, current_specs):
        super().__init__(protect=2)
        self.path = 'X:/A1/WorldApart.exe'
        self.install_directory = Path(self.path).parent
        self.installation = SimpleNamespace(executable_path=Path(self.path))
        self.readers = []
        self.install_layout(current_data, current_specs)

    def put(self, address, data):
        # The parent fixture's sparse store covers standalone objects. Writes
        # within an existing metadata block must update that block in place.
        for start, existing in self.extra.items():
            if start <= address and address + len(data) <= start + len(existing):
                updated = bytearray(existing)
                updated[address - start:address - start + len(data)] = data
                self.extra[start] = updated
                return
        super().put(address, data)

    def install_layout(self, current_data, current_specs, *, class_shift=0):
        self.data[:] = bytes(len(self.data))
        self.extra.clear()
        self.extra[self.meta] = bytearray(current_data)
        self.current_specs = current_specs
        self.klasses = {}
        self.type_pointers = {}
        image, image_name = 0x600000, 0x601000
        self.put(image, struct.pack('<Q', image_name))
        self.put(image_name, b'Game.dll' + bytes(256))
        for ordinal, full in enumerate(discovery.REQUIRED):
            spec = current_specs[full]
            klass = 0x11000 + ordinal * 0x1000 + class_shift
            field_table, type_pointer = klass + 0x400, 0x610000 + ordinal * 0x100
            self.klasses[full], self.type_pointers[full] = klass, type_pointer
            header = bytearray(320)
            for offset, value in (
                    (0, image), (16, self.meta + spec['nameFileOffset']),
                    (24, self.meta + spec['namespaceFileOffset']),
                    (0x68, self.meta + spec['typeDefinitionFileOffset']),
                    (0x78, klass), (0x80, field_table)):
                struct.pack_into('<Q', header, offset, value)
            struct.pack_into('<I', header, 0xF8, 32)
            struct.pack_into('<I', header, 0x11C, int(spec['token'], 16))
            struct.pack_into('<H', header, 0x124, spec['fieldCount'])
            self.put(klass, header)
            self.put(type_pointer, bytes(10) + b'\x08' + bytes(5))
            for field_ordinal, field in enumerate(spec['fields']):
                self.put(field_table + field_ordinal * 32,
                         struct.pack('<QQQiI', self.meta + field['nameFileOffset'],
                                     type_pointer, klass, 16 + field_ordinal * 4,
                                     int(field['token'], 16)))

    def new_reader(self, pid, *, expected_path=None):
        if pid != PID or expected_path is not None and Path(expected_path) != Path(self.path):
            raise AssertionError('The test requested an unexpected process identity')
        reader = copy.copy(self)
        reader.pid, reader.h, reader.closed = pid, 200 + len(self.readers), False
        self.readers.append(reader)
        return reader

    def mappings(self, reader):
        return dict(pid=reader.pid, image=reader.path,
                    metadata=[dict(base=self.meta, allocation=self.meta,
                                   size=len(self.extra[self.meta]), type=0x40000, protect=2,
                                   mapped_file=str(self.install_directory / 'WorldApart_Data' /
                                                   'il2cpp_data/Metadata/global-metadata.dat'),
                                   installation_matches=True)],
                    game_assembly=[dict(base=0x20000000, allocation=0x20000000,
                                        size=0x100000, type=0x1000000, protect=0x20,
                                        mapped_file=str(self.install_directory / 'GameAssembly.dll'))])


def process_times(_handle, creation, _exit, _kernel, _user):
    value = ctypes.cast(creation, ctypes.POINTER(probe.W.FILETIME)).contents
    value.dwHighDateTime, value.dwLowDateTime = CREATION_TIME >> 32, CREATION_TIME & 0xFFFFFFFF
    return True


class ConnectionDiscoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = Path(self.stack.enter_context(TemporaryDirectory()))
        self.resources, self.cache = directory / 'resources', directory / 'cache'
        self.resources.mkdir()
        rows = [(name, 'Game.dll', ['Count']) for name in discovery.REQUIRED]
        _old_data, self.reviewed = metadata(rows)
        current_data, current_specs = metadata(list(reversed(rows)), gap=17,
                                               token_shift=91, index_shift=771)
        self.memory = RuntimeMemory(current_data, current_specs)
        (self.resources / 'engine_runtime_handoff.json').write_text(
            json.dumps(list(self.reviewed.values())), encoding='utf8')
        for module in (discovery, resolver):
            self.stack.enter_context(patch.object(module, 'RESOURCE_ROOT', self.resources))
            self.stack.enter_context(patch.object(module, 'CACHE_ROOT', self.cache))
        self.stack.enter_context(patch.object(probe, 'Reader', side_effect=self.memory.new_reader))
        self.stack.enter_context(patch.object(probe, 'verified_mappings', side_effect=self.memory.mappings))
        self.stack.enter_context(patch.object(probe.K, 'GetProcessTimes', side_effect=process_times))

    def discover(self):
        return discovery.connect_discover(PID, max_resident_mib=1, max_seconds=5,
                                           expected_path=self.memory.path)

    def open_resolver(self):
        return resolver.Resolver(PID, expected_path=self.memory.path)

    def verify_all(self, instance):
        self.assertIsInstance(instance.specs, RuntimeSpecs)
        self.assertEqual(instance.start_time, CREATION_TIME)
        for name in discovery.REQUIRED:
            current = instance.verify_class(instance.known[name], name)
            self.assertEqual(current['klass'], hex(self.memory.klasses[name]))
            self.assertEqual(instance.field(current, 'Count', 8), 16)
            spec, expected = instance.specs[name], self.memory.current_specs[name]
            for key in ('nameFileOffset', 'typeDefinitionFileOffset', 'typeDef', 'token',
                        'byval', 'parentType', 'fieldStart'):
                self.assertEqual(spec[key], expected[key], (name, key))
            self.assertEqual(spec['fields'], expected['fields'])

    def test_migrated_metadata_discovers_and_constructs_first_and_repeat_resolver(self):
        for _ in range(2):
            result = self.discover()
            self.assertEqual(result['diagnostic']['outcome'], 'verified')
            self.assertEqual(set(result['diagnostic']['relocated_types']), set(discovery.REQUIRED))
            self.assertEqual(len(result['classes']), 6)
            self.assertTrue(self.memory.readers[-1].closed)
            with self.open_resolver() as instance:
                self.verify_all(instance)
                self.verify_all(instance)
            self.assertTrue(self.memory.readers[-1].closed)
        self.assertEqual(len(self.memory.readers), 4)
        self.assertEqual({p.name for p in self.cache.iterdir()}, {'classes.json', 'objects.json'})

    def test_expired_class_cache_is_replaced_using_current_metadata_and_live_classes(self):
        initial = self.discover()
        old_addresses = {c['klass'] for c in initial['classes']}
        rows = [(name, 'Game.dll', ['Count']) for name in discovery.REQUIRED]
        data, specs = metadata(rows, gap=31, token_shift=701, index_shift=900)
        self.memory.install_layout(data, specs, class_shift=0x800)
        with self.open_resolver() as stale:
            with self.assertRaises(resolver.ResolutionError):
                stale.verify_class(stale.known[PLAYER], PLAYER)
        result = self.discover()
        new_addresses = {c['klass'] for c in result['classes']}
        self.assertTrue(old_addresses.isdisjoint(new_addresses))
        published = json.loads((self.cache / 'classes.json').read_text(encoding='utf8'))
        self.assertEqual({c['klass'] for c in published['classes']}, new_addresses)
        with self.open_resolver() as current:
            self.verify_all(current)

    def test_incompatible_schema_or_field_owner_refuses_without_publishing_cache(self):
        original_data = bytes(self.memory.extra[self.memory.meta])
        original_specs = copy.deepcopy(self.memory.current_specs)
        for reason in ('missing_field', 'wrong_owner'):
            with self.subTest(reason=reason):
                self.memory.install_layout(original_data, original_specs)
                if reason == 'missing_field':
                    rows = [(name, 'Game.dll', ['Removed' if name == PLAYER else 'Count'])
                            for name in discovery.REQUIRED]
                    data, specs = metadata(rows, gap=17, token_shift=91, index_shift=771)
                    self.memory.install_layout(data, specs)
                else:
                    self.memory.put(self.memory.klasses[PLAYER] + 0x400 + 16,
                                    struct.pack('<Q', 0))
                with self.assertRaises(ConnectionDiagnosticError) as raised:
                    self.discover()
                diagnostic = raised.exception.diagnostic
                if reason == 'missing_field':
                    self.assertEqual(diagnostic['stage'], 'metadata_resolution')
                    self.assertIn('required field', diagnostic['reason'])
                else:
                    self.assertEqual(diagnostic['stage'], 'class_discovery')
                    self.assertEqual(diagnostic['types'][PLAYER]['rejections'],
                                     {'field_identity_mismatch': 1})
                self.assertFalse(self.cache.exists())
                self.assertTrue(self.memory.readers[-1].closed)

    def test_metadata_change_invalidates_existing_resolver_even_if_bytes_are_restored(self):
        self.discover()
        with self.open_resolver() as instance:
            instance.verify_class(instance.known[PLAYER], PLAYER)
            field = self.memory.current_specs[PLAYER]['fields'][0]
            address = self.memory.meta + field['nameFileOffset']
            self.memory.put(address, b'Xount\0')
            with self.assertRaisesRegex(MetadataError, 'Selected metadata changed'):
                instance.verify_class(instance.known[PLAYER], PLAYER)
            self.memory.put(address, b'Count\0')
            with self.assertRaisesRegex(MetadataError, 'invalidated'):
                instance.verify_class(instance.known[PLAYER], PLAYER)
        with self.open_resolver() as refreshed:
            self.verify_all(refreshed)

    def test_current_metadata_identity_does_not_bypass_runtime_field_semantics(self):
        self.discover()
        for kind, attributes, reason in ((0x0A, 0, 'Unexpected field type'),
                                        (0x08, 0x10, 'Unexpected static/literal field')):
            with self.subTest(kind=kind, attributes=attributes):
                raw_type = bytearray(16)
                struct.pack_into('<H', raw_type, 8, attributes)
                raw_type[10] = kind
                self.memory.put(self.memory.type_pointers[PLAYER], raw_type)
                with self.open_resolver() as instance:
                    current = instance.verify_class(instance.known[PLAYER], PLAYER)
                    with self.assertRaisesRegex(resolver.ResolutionError, reason):
                        instance.field(current, 'Count', 8)


if __name__ == '__main__':
    unittest.main()
