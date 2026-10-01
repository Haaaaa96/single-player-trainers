"""Current-metadata fixtures only: no OS process access or game execution."""
import copy
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'game_runtime'))
from runtime_metadata import (MetadataError, RuntimeSpecs, resolve_runtime_specs,
                              HEADER_SIZE, TYPE_SIZE, FIELD_SIZE, IMAGE_SIZE,
                              MAX_FIELD_COUNT, MAX_READ_BYTES)


BASE = 0x10000000
PLAYER = 'Game.Model.PlayerModel'
OPTIONAL = 'Game.Model.GameStore'


class MemoryReader:
    def __init__(self, data):
        self.data = bytearray(data)
        self.calls = []
        self.on_read = None

    def read(self, address, size):
        offset = address - BASE
        self.calls.append((offset, size))
        if self.on_read:
            self.on_read(offset, size)
        if offset < 0:
            return b''
        return bytes(self.data[offset:offset + size])


def metadata(types=None, *, gap=0, token_shift=0, index_shift=0):
    """Build format-31 records, including explicit image ownership ranges."""
    if types is None:
        types = [(PLAYER, 'Game.dll', ['bag', 'extra'])]
    strings = bytearray(b'\0' + b'padding\0' * gap)
    string_indices = {'': 0}

    def string(value):
        if value not in string_indices:
            string_indices[value] = len(strings)
            strings.extend(value.encode('utf8') + b'\0')
        return string_indices[value]

    records, fields, images, locations = [], [], [], {}
    for ordinal, (full, image, names) in enumerate(types):
        namespace, _, name = full.rpartition('.')
        if not images or images[-1][0] != image:
            images.append([image, ordinal, 0])
        images[-1][2] += 1
        values = [0] * 26
        values[0], values[1] = string(name), string(namespace)
        values[2], values[4] = 100 + index_shift + ordinal, 200 + index_shift + ordinal
        values[8], values[18] = len(fields) if names else -1, len(names)
        values[25] = 0x02000001 + token_shift + ordinal
        row_fields = []
        for field_ordinal, field_name in enumerate(names):
            field_index = len(fields)
            values_field = (string(field_name), 300 + index_shift + field_index,
                            0x04000001 + token_shift + field_index)
            fields.append(struct.pack('<iiI', *values_field))
            row_fields.append(dict(name=field_name, nameIndex=values_field[0],
                                   fieldIndex=field_index, typeIndex=values_field[1],
                                   token=hex(values_field[2])))
        records.append(struct.pack('<16i8H2I', *values))
        locations[full] = dict(values=values, fields=row_fields, image=image)
    for image, _start, _count in images:
        string(image)
    string_offset = HEADER_SIZE + gap * 7
    field_offset = string_offset + len(strings) + gap * 3
    type_offset = field_offset + len(fields) * FIELD_SIZE + gap * 5
    image_offset = type_offset + len(records) * TYPE_SIZE + gap * 11
    data = bytearray(image_offset + len(images) * IMAGE_SIZE)
    struct.pack_into('<II', data, 0, 0xFAB11BAF, 31)
    for pos, offset, size in ((0x18, string_offset, len(strings)),
                              (0x60, field_offset, len(fields) * FIELD_SIZE),
                              (0xA0, type_offset, len(records) * TYPE_SIZE),
                              (0xA8, image_offset, len(images) * IMAGE_SIZE)):
        struct.pack_into('<II', data, pos, offset, size)
    data[string_offset:string_offset + len(strings)] = strings
    data[field_offset:field_offset + len(fields) * FIELD_SIZE] = b''.join(fields)
    data[type_offset:type_offset + len(records) * TYPE_SIZE] = b''.join(records)
    for i, (image, start, count) in enumerate(images):
        struct.pack_into('<iiiI6i', data, image_offset + i * IMAGE_SIZE,
                         string_indices[image], i, start, count, -1, 0, -1, 1, 0, 0)
    specs = {}
    for full, row in locations.items():
        values = row['values']
        index = (values[25] - 0x02000001 - token_shift)
        specs[full] = dict(name=full, typeDef=index, nameIndex=values[0],
                           nameFileOffset=string_offset + values[0],
                           namespaceFileOffset=string_offset + values[1],
                           typeDefinitionFileOffset=type_offset + index * TYPE_SIZE,
                           byval=values[2], parentType=values[4], fieldStart=values[8],
                           fieldCount=values[18], token=hex(values[25]),
                           fields=[{k: v for k, v in field.items() if k != 'nameIndex'} |
                                   {'nameFileOffset': string_offset + field['nameIndex']}
                                   for field in row['fields']])
    return data, specs


class RuntimeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.data, self.specs = metadata()
        self.reviewed = copy.deepcopy(self.specs)
        # Only bag is reviewed. Extra/changed nonessential fields must not be
        # promoted to permissions or turn unrelated additions into rejection.
        self.reviewed[PLAYER]['fields'] = [self.reviewed[PLAYER]['fields'][0]]
        self.reader = MemoryReader(self.data)

    def lookup(self, reader=None, reviewed=None):
        reader = reader or self.reader
        return RuntimeSpecs(reader, BASE, reviewed or self.reviewed,
                            metadata_size=len(reader.data))

    def test_real_initialization_first_lookup_and_repeat_share_tables(self):
        lookup = self.lookup()
        self.assertEqual(self.reader.calls, [])
        current = lookup[PLAYER]
        self.assertEqual(current['image_name'], 'Game.dll')
        self.assertEqual(current['fields'][0], self.reviewed[PLAYER]['fields'][0])
        self.assertEqual(lookup[PLAYER], current)
        for header_pos in (0x18, 0xA0, 0xA8):
            section = struct.unpack_from('<II', self.data, header_pos)
            # An evidence read can equal the full table for a one-record image
            # or type table, so strings demonstrate the index isn't reloaded.
            if header_pos == 0x18:
                self.assertEqual(self.reader.calls.count(section), 1)
        self.assertTrue(all(size <= MAX_READ_BYTES for _, size in self.reader.calls))

    def test_positions_tokens_indices_and_unneeded_fields_can_change(self):
        shifted_data, shifted_specs = metadata([
            ('Other.Prefix', 'Game.dll', ['dummy']),
            (PLAYER, 'Game.dll', ['new_before', 'bag', 'new_after']),
        ], gap=17, token_shift=91, index_shift=771)
        before = copy.deepcopy(self.reviewed)
        current = self.lookup(MemoryReader(shifted_data))[PLAYER]
        expected = shifted_specs[PLAYER]
        for name in ('typeDef', 'nameIndex', 'nameFileOffset', 'namespaceFileOffset',
                     'typeDefinitionFileOffset', 'byval', 'parentType',
                     'fieldStart', 'fieldCount', 'token'):
            self.assertEqual(current[name], expected[name], name)
        self.assertEqual(current['fields'], [expected['fields'][1]])
        self.assertEqual(current['fieldCount'], 3)
        self.assertEqual(self.reviewed, before)

    def test_explicit_reviewed_image_allows_new_reviewed_name_without_guessing(self):
        data, specs = metadata([('Example.Type', 'Example.dll', ['value'])])
        specs['Example.Type']['image'] = 'Example.dll'
        current = self.lookup(MemoryReader(data), specs)['Example.Type']
        self.assertEqual(current['image_name'], 'Example.dll')
        del specs['Example.Type']['image']
        with self.assertRaisesRegex(MetadataError, 'reviewed image'):
            self.lookup(MemoryReader(data), specs)['Example.Type']

    def test_duplicate_full_name_in_other_image_does_not_override_owner(self):
        data, _ = metadata([(PLAYER, 'OtherMod.dll', ['bag']),
                            (PLAYER, 'Game.dll', ['bag'])])
        current = self.lookup(MemoryReader(data))[PLAYER]
        self.assertEqual(current['typeDef'], 1)
        self.assertEqual(current['image_name'], 'Game.dll')

    def test_duplicate_type_in_reviewed_image_is_rejected(self):
        data, _ = metadata([(PLAYER, 'Game.dll', ['bag']),
                            (PLAYER, 'Game.dll', ['bag'])])
        with self.assertRaisesRegex(MetadataError, 'ambiguous current type'):
            self.lookup(MemoryReader(data))[PLAYER]

    def test_wrong_image_or_namespace_cannot_supply_reviewed_type(self):
        for full, image in ((PLAYER, 'OtherMod.dll'), ('Other.Model.PlayerModel', 'Game.dll')):
            with self.subTest(full=full, image=image):
                data, _ = metadata([(full, image, ['bag'])])
                with self.assertRaisesRegex(MetadataError, 'Missing or ambiguous current type'):
                    self.lookup(MemoryReader(data))[PLAYER]

    def test_missing_optional_type_is_local_to_its_lookup(self):
        reviewed = {**self.reviewed, OPTIONAL: dict(name=OPTIONAL, fields=[])}
        lookup = self.lookup(reviewed=reviewed)
        self.assertEqual(lookup[PLAYER]['name'], PLAYER)
        with self.assertRaisesRegex(MetadataError, 'Missing or ambiguous current type'):
            lookup[OPTIONAL]
        self.assertEqual(lookup[PLAYER]['name'], PLAYER)
        self.assertIsNone(lookup.get('Unreviewed.Type'))
        selected = resolve_runtime_specs(self.reader, BASE, reviewed, [PLAYER])
        self.assertEqual(list(selected), [PLAYER])

    def test_missing_or_duplicate_required_field_rejected(self):
        for names in (['different'], ['bag', 'bag']):
            with self.subTest(names=names):
                data, _ = metadata([(PLAYER, 'Game.dll', names)])
                with self.assertRaises(MetadataError):
                    self.lookup(MemoryReader(data))[PLAYER]

    def test_preserves_reviewed_semantic_requirements_without_using_old_type_index(self):
        self.reviewed[PLAYER]['fields'][0].update(kind=0x12, static=False)
        data, specs = metadata(index_shift=500)
        current = self.lookup(MemoryReader(data))[PLAYER]['fields'][0]
        self.assertEqual((current['kind'], current['static']), (0x12, False))
        self.assertEqual(current['typeIndex'], specs[PLAYER]['fields'][0]['typeIndex'])

    def test_unknown_format_and_bad_magic_rejected_before_indexing(self):
        for pos, value in ((0, 0xDEADBEEF), (4, 32)):
            with self.subTest(pos=pos):
                reader = MemoryReader(self.data)
                struct.pack_into('<I', reader.data, pos, value)
                with self.assertRaisesRegex(MetadataError, 'Unsupported current metadata format'):
                    self.lookup(reader)[PLAYER]
                self.assertEqual(reader.calls, [(0, HEADER_SIZE)])

    def test_truncated_metadata_and_partial_table_read_rejected(self):
        reader = MemoryReader(self.data[:-1])
        with self.assertRaises(MetadataError):
            RuntimeSpecs(reader, BASE, self.reviewed)[PLAYER]
        field_offset, _ = struct.unpack_from('<II', self.data, 0x60)
        original_read = self.reader.read
        self.reader.read = lambda address, size: (
            original_read(address, size)[:-1] if address == BASE + field_offset
            else original_read(address, size))
        with self.assertRaisesRegex(MetadataError, 'Truncated or unreadable'):
            self.lookup()[PLAYER]

    def test_invalid_bounded_field_range_and_record_type_are_rejected(self):
        td = self.specs[PLAYER]['typeDefinitionFileOffset']
        field_offset, _ = struct.unpack_from('<II', self.data, 0x60)
        cases = [(td + 68, '<H', MAX_FIELD_COUNT + 1),
                 (td + 32, '<i', 1000000),
                 (td + 84, '<I', 0x04000001),
                 (field_offset + 4, '<i', -1),
                 (field_offset + 8, '<I', 0x02000001)]
        for offset, fmt, value in cases:
            with self.subTest(offset=offset):
                reader = MemoryReader(self.data)
                struct.pack_into(fmt, reader.data, offset, value)
                with self.assertRaises(MetadataError):
                    self.lookup(reader)[PLAYER]

    def test_malformed_string_and_overlapping_section_rejected(self):
        td = self.specs[PLAYER]['typeDefinitionFileOffset']
        reader = MemoryReader(self.data)
        struct.pack_into('<i', reader.data, td, 0x7FFFFFFF)
        with self.assertRaisesRegex(MetadataError, 'string index'):
            self.lookup(reader)[PLAYER]
        reader = MemoryReader(self.data)
        struct.pack_into('<I', reader.data, 0xA0, HEADER_SIZE)
        with self.assertRaisesRegex(MetadataError, 'Overlapping metadata sections'):
            self.lookup(reader)[PLAYER]
        reader = MemoryReader(self.data)
        start, count = struct.unpack_from('<II', self.data, 0x18)
        reader.data[start:start + count] = b'x' * count
        with self.assertRaisesRegex(MetadataError, 'Unterminated or oversized'):
            self.lookup(reader)[PLAYER]

    def test_header_or_selected_record_change_rejected_on_repeat(self):
        for offset, fmt, value in ((4, '<I', 32),
                                  (self.specs[PLAYER]['typeDefinitionFileOffset'] + 84, '<I', 0x02009999),
                                  (self.specs[PLAYER]['nameFileOffset'], '<B', ord('X'))):
            with self.subTest(offset=offset):
                reader = MemoryReader(self.data)
                lookup = self.lookup(reader)
                lookup[PLAYER]
                struct.pack_into(fmt, reader.data, offset, value)
                with self.assertRaisesRegex(MetadataError, 'changed'):
                    lookup[PLAYER]
                reader.data[:] = self.data
                with self.assertRaisesRegex(MetadataError, 'invalidated'):
                    lookup[PLAYER]
                self.assertFalse(lookup._cache)
                self.assertFalse(lookup._evidence)

    def test_repeat_budget_is_per_lookup_and_single_lookup_is_still_bounded(self):
        initial = self.lookup()
        initial[PLAYER]
        initial_bytes = sum(size for _, size in self.reader.calls)
        reader = MemoryReader(self.data)
        lookup = self.lookup(reader)
        with patch('runtime_metadata.MAX_TOTAL_READ_BYTES', initial_bytes + 1):
            for _ in range(20):
                self.assertEqual(lookup[PLAYER]['name'], PLAYER)
        reader = MemoryReader(self.data)
        with patch('runtime_metadata.MAX_TOTAL_READ_BYTES', HEADER_SIZE + 2):
            with self.assertRaisesRegex(MetadataError, 'read budget exhausted'):
                self.lookup(reader)[PLAYER]
        self.assertLessEqual(sum(size for _, size in reader.calls), HEADER_SIZE + 2)

    def test_selected_field_change_during_snapshot_is_rejected(self):
        field_offset, field_size = struct.unpack_from('<II', self.data, 0x60)
        reads = 0

        def mutate(offset, size):
            nonlocal reads
            if offset == field_offset and size == field_size:
                reads += 1
                if reads == 2:
                    struct.pack_into('<I', self.reader.data, field_offset + 8, 0x04007777)
        self.reader.on_read = mutate
        with self.assertRaisesRegex(MetadataError, 'Selected metadata changed'):
            self.lookup()[PLAYER]

    def test_empty_class_is_supported_without_reading_negative_field_start(self):
        full = 'Game.Model.Components.BagItem'
        data, specs = metadata([(full, 'Game.dll', [])])
        current = self.lookup(MemoryReader(data), specs)[full]
        self.assertEqual((current['fieldStart'], current['fieldCount'], current['fields']), (-1, 0, []))


if __name__ == '__main__':
    unittest.main()
