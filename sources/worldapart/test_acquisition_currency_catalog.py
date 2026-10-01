"""Synthetic catalogue proofs only; no process access, game calls or injection."""
import copy
import json
import struct
import unittest
from unittest.mock import Mock, patch

import acquisition_catalog as catalogue


class MemoryResolver:
    field = catalogue.resolver.Resolver.field
    verify_class = catalogue.resolver.Resolver.verify_class
    _inspect_info = catalogue.resolver.Resolver.info
    q = catalogue.resolver.Resolver.q
    i = catalogue.resolver.Resolver.i
    anchor = catalogue.resolver.Resolver.anchor
    pointer = catalogue.resolver.Resolver.pointer

    def __init__(self):
        self.memory, self.classes, self.specs, self.anchors = {}, {}, {}, []
        self.meta, self.start_time = 0x100000, 99
        self.reader = self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def put(self, address, data):
        self.memory.update({address + i: value for i, value in enumerate(data)})

    def p(self, address, value):
        self.put(address, struct.pack('<Q', value))

    def integer(self, address, value):
        self.put(address, struct.pack('<i', value))

    def exact(self, address, size):
        try:
            return bytes(self.memory[address + i] for i in range(size))
        except KeyError as error:
            raise catalogue.resolver.ResolutionError('Synthetic unreadable address') from error

    def info(self, address, name=None, namespace=None, *, max_fields=512):
        try:
            klass = self.classes[address]
        except KeyError as error:
            raise catalogue.resolver.ResolutionError('Synthetic missing class') from error
        if len(klass['fields']) > max_fields:
            raise catalogue.resolver.ResolutionError('Synthetic field count exceeds limit')
        with patch.object(catalogue.resolver.probe, 'inspect_class', return_value=klass):
            return self._inspect_info(address, name, namespace, max_fields=max_fields)

    def klass(self, address, full, fields=(), parent=0, size=0x100):
        ns, _, name = full.rpartition('.')
        values = []
        for field_name, offset, kind, token, static in fields:
            type_data = bytearray(16)
            struct.pack_into('<Q', type_data, 0, 0xD000 if kind == 0x15 else 0x900000)
            struct.pack_into('<H', type_data, 8, 0x10 if static else 0)
            type_data[10] = kind
            values.append(dict(name=field_name, offset=offset, token=hex(token),
                               parent=hex(address), type_data=type_data.hex()))
        obj = dict(klass=hex(address), name=name, namespace=ns, parent=hex(parent),
                   fields=values, instance_size=size)
        self.classes[address] = obj
        token = 0x02000000 + len(self.classes)
        self.specs[full] = dict(typeDefinitionFileOffset=address,
                               token=hex(token), fieldCount=len(values), fields=copy.deepcopy(values))
        self.p(address + 0x68, self.meta + address)
        self.integer(address + 0x11c, token)
        self.p(address + 0x58, parent)
        return obj


def fixture():
    r = MemoryResolver()
    r.klass(0x1000, 'LubanDatas.Tables', (
        ('Current', 0, 0x12, 0x04000800, True),
        ('<TbItem>k__BackingField', 0x248, 0x12, 0x04000848, False)), size=0x798)
    r.klass(0x2000, 'LubanDatas.TbItem', (
        ('_dataList', 0x18, 0x15, 0x04000ade, False),
        ('_overrides', 0x20, 0x15, 0x04000adf, False)))
    r.klass(0x3000, 'Emei.NotifiableList`1', parent=0x4000)
    r.klass(0x4000, 'System.Collections.Generic.List`1', (
        ('_items', 0x10, 0x1d, 1, False), ('_size', 0x18, 8, 2, False),
        ('_version', 0x1c, 8, 3, False)))
    r.klass(0x5000, 'LubanDatas.data.Item[]')
    r.klass(0x6000, 'LubanDatas.data.Item', (
        ('<id>k__BackingField', 0x10, 0x11, 0x0400158d, False),
        ('<itemType>k__BackingField', 0x48, 0x11, 0x04001594, False),
        ('<maxCntPerGrid>k__BackingField', 0x64, 8, 0x0400159d, False),
        ('<autoUse>k__BackingField', 0x54, 0x15, 0x0400159a, False),
        ('<canUse>k__BackingField', 0x52, 2, 0x04001598, False),
        ('<canDiscard>k__BackingField', 0x51, 2, 0x04001597, False)))
    r.klass(0x7000, 'System.Nullable`1', (
        ('hasValue', 16, 2, 1, False), ('value', 17, 2, 2, False)))
    r.klass(0x8000, 'System.Collections.Generic.Dictionary`2', (
        ('_count', 0x20, 8, 1, False), ('_freeCount', 0x28, 8, 2, False),
        ('_version', 0x2c, 8, 3, False)))
    r.klass(0x9000, 'LubanDatas.TbItemType')
    r.klass(0xA000, 'LubanDatas.L10nText')
    r.klass(0xB000, 'LubanDatas.data.ItemType', (
        ('<id>k__BackingField', 0x10, 0x11, 1, False),
        ('<bagType>k__BackingField', 0x20, 0x11, 2, False),
        ('<hideInBag>k__BackingField', 0x24, 2, 3, False)))
    r.p(0x1000 + 0xb8, 0x10000)
    r.p(0x10000, 0x20000)
    r.p(0x20000, 0x1000)
    r.p(0x20248, 0x30000)
    r.p(0x30000, 0x2000)
    r.p(0x30018, 0x40000)
    r.p(0x30020, 0)
    r.p(0x40000, 0x3000)
    r.p(0x40010, 0x50000)
    r.integer(0x40018, 4)
    r.integer(0x4001c, 7)
    r.p(0x50000, 0x5000)
    r.p(0x50018, 8)
    r.p(0xD018, 0x7000)
    r.p(0x90000, 0x8000)
    r.integer(0x90020, 0)
    r.integer(0x90028, 0)
    r.integer(0x9002c, 0)
    rows, items = [], []
    for index, item_id in enumerate((50000, 50001, 50002, 50005)):
        address = 0x60000 + index * 0x100
        rows.append(address)
        r.p(0x50020 + index * 8, address)
        r.p(address, 0x6000)
        r.integer(address + 0x10, item_id)
        r.integer(address + 0x48, 5)
        r.integer(address + 0x64, 999999999)
        r.put(address + 0x54, b'\0\0')
        r.put(address + 0x51, b'\0\0')
        items.append(dict(id=item_id, config_object=hex(address), item_type_id=5,
                          max_count_per_grid=999999999, auto_use=None,
                          names={'zh-Hans': '任意名字'}))
    r.p(0xA0000, 0xB000)
    r.integer(0xA0010, 5)
    r.integer(0xA0020, 5)
    r.put(0xA0024, b'\1')
    return r, rows, items


class CurrencyProofTests(unittest.TestCase):
    def setUp(self):
        self.r, self.rows, self.items = fixture()

    def proof(self):
        return catalogue._currency_proofs(self.r, 0x1000, 0x20000, self.rows, self.items)

    def migrate_currency_metadata(self):
        """Move current metadata identities without changing bridge layouts."""
        for address in (0x1000, 0x2000, 0x6000):
            klass = self.r.classes[address]
            full = klass['namespace'] + '.' + klass['name']
            spec = self.r.specs[full]
            spec['typeDefinitionFileOffset'] += 0x10000
            spec['token'] = hex(int(spec['token'], 16) + 7)
            self.r.p(address + 0x68, self.r.meta + spec['typeDefinitionFileOffset'])
            self.r.integer(address + 0x11c, int(spec['token'], 16))
            for field in klass['fields']:
                field['token'] = hex(int(field['token'], 16) + 0x100)
                next(f for f in spec['fields'] if f['name'] == field['name'])['token'] = field['token']

    def test_current_metadata_and_field_tokens_migrate_together(self):
        self.migrate_currency_metadata()
        for _ in range(2):
            self.r.anchors.clear()
            proofs = self.proof()
            self.assertEqual(set(proofs), {50000, 50001, 50002})
            for proof in proofs.values():
                for anchor in proof['anchors']:
                    self.assertEqual(self.r.exact(anchor['address'], anchor['size']).hex(),
                                     anchor['expected_hex'])
        self.assertEqual(set(self.read_catalogue()['currency_proofs']), {50000, 50001, 50002})

    def test_current_metadata_and_field_token_must_match_on_both_sides(self):
        for side in ('runtime', 'metadata'):
            with self.subTest(side=side):
                self.setUp()
                self.migrate_currency_metadata()
                klass = self.r.classes[0x6000]
                fields = (klass['fields'] if side == 'runtime' else
                          self.r.specs['LubanDatas.data.Item']['fields'])
                field = next(f for f in fields if f['name'] == '<itemType>k__BackingField')
                field['token'] = hex(int(field['token'], 16) + 1)
                with self.assertRaisesRegex(catalogue.resolver.ResolutionError,
                                            'Static/runtime field mismatch'):
                    self.proof()

    def test_migrated_metadata_cannot_change_bridge_field_offsets(self):
        for address, name in ((0x1000, 'Current'), (0x1000, '<TbItem>k__BackingField'),
                              (0x2000, '_dataList'), (0x2000, '_overrides'),
                              (0x6000, '<id>k__BackingField'),
                              (0x6000, '<itemType>k__BackingField'),
                              (0x6000, '<maxCntPerGrid>k__BackingField'),
                              (0x6000, '<autoUse>k__BackingField')):
            with self.subTest(name=name):
                self.setUp()
                self.migrate_currency_metadata()
                klass = self.r.classes[address]
                full = klass['namespace'] + '.' + klass['name']
                for fields in (klass['fields'], self.r.specs[full]['fields']):
                    next(f for f in fields if f['name'] == name)['offset'] += 8
                with self.assertRaisesRegex(catalogue.resolver.ResolutionError,
                                            'Currency configuration field differs'):
                    self.proof()

    def test_migrated_metadata_retains_field_kind_static_and_parent_guards(self):
        for mutation in ('kind', 'static', 'literal', 'parent'):
            with self.subTest(mutation=mutation):
                self.setUp()
                self.migrate_currency_metadata()
                field = next(f for f in self.r.classes[0x6000]['fields']
                             if f['name'] == '<itemType>k__BackingField')
                if mutation == 'parent':
                    field['parent'] = '0x2000'
                else:
                    data = bytearray.fromhex(field['type_data'])
                    if mutation == 'kind':
                        data[10] = 8
                    else:
                        data[8] |= 0x10 if mutation == 'static' else 0x40
                    field['type_data'] = data.hex()
                with self.assertRaises(catalogue.resolver.ResolutionError):
                    self.proof()

    def test_three_reviewed_ids_only_and_complete_independent_chains(self):
        proofs = self.proof()
        self.assertEqual(set(proofs), {50000, 50001, 50002})
        self.assertEqual(catalogue.CURRENCY_ADD_MAXIMUM, 1000000)
        self.assertEqual(catalogue.SPIRIT_STONE_ADD_MAXIMUM, 100000000)
        self.assertEqual(catalogue.CURRENCY_BALANCE_MAXIMUM, 999999999)
        for index, item_id in enumerate((50000, 50001, 50002)):
            proof = proofs[item_id]
            self.assertEqual((proof['tables'], proof['tables_class'], proof['row_index']),
                             ('0x20000', '0x1000', index))
            obj = self.rows[index]
            anchors = {a['address']: a for a in proof['anchors']}
            for address in (0x10b8, 0x10000, 0x20000, 0x20248, 0x30000,
                            0x30018, 0x30020, 0x40000, 0x3058, 0x40018,
                            0x4001c, 0x40010, 0x50018, 0x50020 + index * 8,
                            obj, obj + 0x10, obj + 0x48, obj + 0x64, obj + 0x54):
                self.assertIn(address, anchors)
            self.assertEqual(anchors[obj + 0x54]['size'], 2)
            other = self.rows[(index + 1) % 3]
            self.assertNotIn(other + 0x10, anchors)

    def test_name_and_item_id_without_currency_type_never_grant_proof(self):
        self.items[0]['item_type_id'] = 23
        proofs = self.proof()
        self.assertNotIn(50000, proofs)
        self.assertNotIn(50005, proofs)
        self.assertEqual(set(proofs), {50001, 50002})

    def test_empty_non_null_overrides_are_anchored_including_tombstones(self):
        self.r.p(0x30020, 0x90000)
        self.r.integer(0x90020, 3)
        self.r.integer(0x90028, 3)
        addresses = {a['address'] for a in self.proof()[50000]['anchors']}
        self.assertTrue({0x90000, 0x90020, 0x90028, 0x9002c} <= addresses)

    def test_live_or_malformed_overrides_fail_closed(self):
        for count, free in ((1, 0), (0, 1), (-1, -1), (10001, 10001)):
            with self.subTest(count=count, free=free):
                self.r.p(0x30020, 0x90000)
                self.r.integer(0x90020, count)
                self.r.integer(0x90028, free)
                with self.assertRaises(catalogue.resolver.ResolutionError):
                    self.proof()

    def test_replaced_root_slot_row_and_cap_are_rejected(self):
        mutations = ((0x10000, 0x21000, 8), (0x20000, 0x2000, 8),
                     (0x50020, self.rows[1], 8), (self.rows[0] + 0x10, 50001, 4),
                     (self.rows[0] + 0x48, 23, 4), (self.rows[0] + 0x64, 999, 4),
                     (0x40018, 3, 4), (0x50018, 3, 8))
        for address, value, size in mutations:
            with self.subTest(address=address):
                self.setUp()
                (self.r.p if size == 8 else self.r.integer)(address, value)
                with self.assertRaises(catalogue.resolver.ResolutionError):
                    self.proof()

    def test_reviewed_metadata_field_token_or_layout_cannot_drift(self):
        for klass, name, change in ((0x1000, 'Current', {'offset': 8}),
                (0x2000, '_dataList', {'token': '0x400ffff'}),
                (0x4000, '_items', {'offset': 0x20}),
                (0x6000, '<itemType>k__BackingField', {'offset': 0x4c}),
                (0x7000, 'value', {'offset': 18})):
            with self.subTest(name=name):
                self.setUp()
                next(f for f in self.r.classes[klass]['fields'] if f['name'] == name).update(change)
                with self.assertRaises(catalogue.resolver.ResolutionError):
                    self.proof()

    def test_invalid_or_changed_nullable_auto_use_rejected(self):
        for raw in (b'\2\0', b'\1\2', b'\1\1', b'\1\0'):
            with self.subTest(raw=raw):
                self.r.put(self.rows[0] + 0x54, raw)
                with self.assertRaises(catalogue.resolver.ResolutionError):
                    self.proof()

    def read_catalogue(self, mutate=False):
        cache = {name: {'klass': self.r.classes[address]['klass']} for name, address in (
            ('LubanDatas.Tables', 0x1000), ('LubanDatas.TbItem', 0x2000),
            ('LubanDatas.data.Item', 0x6000), ('LubanDatas.TbItemType', 0x9000),
            ('LubanDatas.L10nText', 0xA000), ('LubanDatas.data.ItemType', 0xB000))}
        cache_path = Mock(read_text=Mock(return_value=json.dumps(cache)))
        root = Mock()
        root.__truediv__ = Mock(return_value=cache_path)
        def rows(_rr, _tables, _tc, _field, full):
            if full == 'LubanDatas.TbItem':
                return self.rows, 0x30000
            if mutate:
                self.r.integer(self.rows[0] + 0x64, 123)
            return [0xA0000], 0xA1000
        with patch.object(catalogue.resolver, 'Resolver', return_value=self.r), \
                patch.object(catalogue.cp, 'CACHE_ROOT', root), \
                patch.object(catalogue.cp, 'table_rows', side_effect=rows), \
                patch.object(catalogue.cp, 'localized', return_value={'zh-Hans': '名称'}):
            return catalogue.read_catalogue(123)

    def test_read_catalogue_returns_proofs_with_integer_keys(self):
        result = self.read_catalogue()
        self.assertEqual(set(result['currency_proofs']), {50000, 50001, 50002})
        self.assertEqual(result['process_creation_filetime'], 99)
        self.assertEqual(len(result['items']), 4)

    def test_change_after_proof_before_read_completion_rejected(self):
        with self.assertRaisesRegex(catalogue.resolver.ResolutionError, 'Configuration changed'):
            self.read_catalogue(mutate=True)


if __name__ == '__main__':
    unittest.main()
