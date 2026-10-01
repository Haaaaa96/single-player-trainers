"""Read-only complete item catalogue. No writes, injections, or game calls.

This intentionally does not resolve the player inventory: Tables.Current is an
independent configuration root, so an unsupported inventory subtype should not
prevent research of the available item definitions. It still validates static
metadata identity and all collection anchors before emitting the catalogue.
"""
from pathlib import Path
import collections
import json
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(HERE / 'game_runtime'))
import config_probe as cp
import resolver

LARGE_CURRENCY_IDS = frozenset((50000, 50001, 50002))
CURRENCY_ADD_MAXIMUM = 1_000_000
SPIRIT_STONE_ADD_MAXIMUM = 100_000_000
CURRENCY_BALANCE_MAXIMUM = 999_999_999


def _currency_field(rr, klass, name, kind, offset, *, static=False):
    """Match current metadata FieldInfo before using a bridge-visible offset."""
    actual = rr.field(klass, name, kind, static=static)
    full = klass['namespace'] + '.' + klass['name']
    spec = rr.specs.get(full)
    reviewed = [] if spec is None else [field for field in spec['fields'] if field['name'] == name]
    fields = [field for field in klass['fields'] if field['name'] == name]
    if (len(fields) != 1 or len(reviewed) != 1
            or int(fields[0]['token'], 16) != int(reviewed[0]['token'], 16)
            or actual != offset):
        raise resolver.ResolutionError('Currency configuration field differs: ' + name)
    return actual


def _currency_class(rr, address, full):
    klass = rr.verify_class(address, full)
    rr.anchor(address + 0x68, 8, full + '.metadata')
    rr.anchor(address + 0x11c, 4, full + '.token')
    return klass


def _currency_proofs(rr, tables_class, tables, rows, items):
    """Pin only the three reviewed currency rows and their canonical table chain.

    This is a read-only proof, not permission to add an arbitrary amount. The
    adapter adds the balance and requested maximum; the bridge checks all bytes
    again on the game thread before entering AddItem.
    """
    wanted = [(index, item) for index, item in enumerate(items)
              if item['id'] in LARGE_CURRENCY_IDS and item['item_type_id'] == 5]
    if not wanted:
        return {}
    start = len(rr.anchors)
    tc = _currency_class(rr, tables_class, 'LubanDatas.Tables')
    sf = rr.pointer(tables_class + 0xb8, 'currency.Tables.static_fields')
    current = rr.pointer(sf + _currency_field(rr, tc, 'Current', 0x12,
                         0, static=True), 'currency.Tables.Current')
    if current != tables or rr.pointer(tables, 'currency.Tables.klass') != tables_class:
        raise resolver.ResolutionError('Currency configuration root changed')
    table = rr.pointer(tables + _currency_field(rr, tc, '<TbItem>k__BackingField',
                       0x12, 0x248), 'currency.TbItem')
    table_class = rr.pointer(table, 'currency.TbItem.klass')
    tbc = _currency_class(rr, table_class, 'LubanDatas.TbItem')
    override_address = table + _currency_field(rr, tbc, '_overrides', 0x15,
                                               0x20)
    overrides = struct.unpack('<Q', rr.anchor(override_address, 8,
                                            'currency.TbItem.overrides'))[0]
    if overrides:
        if overrides % 8:
            raise resolver.ResolutionError('Currency overrides pointer is unaligned')
        dc = rr.info(rr.pointer(overrides, 'currency.overrides.klass'),
                     'Dictionary`2', 'System.Collections.Generic')
        count = struct.unpack('<i', rr.anchor(overrides + rr.field(dc, '_count', 8),
                                             4, 'currency.overrides.count'))[0]
        free = struct.unpack('<i', rr.anchor(overrides + rr.field(dc, '_freeCount', 8),
                                            4, 'currency.overrides.freeCount'))[0]
        rr.anchor(overrides + rr.field(dc, '_version', 8), 4, 'currency.overrides.version')
        if not 0 <= free == count <= 10000:
            raise resolver.ResolutionError('Currency runtime overrides are not empty')
    data = rr.pointer(table + _currency_field(rr, tbc, '_dataList', 0x15,
                      0x18), 'currency.TbItem.dataList')
    list_class = rr.pointer(data, 'currency.dataList.klass')
    lc = rr.info(list_class, 'NotifiableList`1', 'Emei')
    parent = rr.pointer(list_class + 0x58, 'currency.dataList.parent')
    if parent != int(lc['parent'], 16):
        raise resolver.ResolutionError('Currency list parent changed')
    base = rr.info(parent, 'List`1', 'System.Collections.Generic')
    for name, kind, offset in (('_items', 0x1d, 0x10), ('_size', 8, 0x18),
                               ('_version', 8, 0x1c)):
        if rr.field(base, name, kind) != offset:
            raise resolver.ResolutionError('Currency list layout differs')
    size = struct.unpack('<i', rr.anchor(data + 0x18, 4, 'currency.dataList.size'))[0]
    rr.anchor(data + 0x1c, 4, 'currency.dataList.version')
    array = rr.pointer(data + 0x10, 'currency.dataList.items')
    array_class = rr.pointer(array, 'currency.dataList.array.klass')
    rr.info(array_class, 'Item[]', 'LubanDatas.data')
    capacity = struct.unpack('<Q', rr.anchor(array + 0x18, 8,
                                           'currency.dataList.capacity'))[0]
    if size != len(rows) or not 0 <= size <= capacity <= 20000:
        raise resolver.ResolutionError('Currency configuration collection changed')
    common = list(rr.anchors[start:])
    proofs = {}
    for index, item in wanted:
        row_start = len(rr.anchors)
        obj = rr.pointer(array + 0x20 + index * 8, 'currency.row.slot')
        if obj != rows[index] or hex(obj) != item['config_object']:
            raise resolver.ResolutionError('Currency row changed')
        klass = rr.pointer(obj, 'currency.row.klass')
        ic = _currency_class(rr, klass, 'LubanDatas.data.Item')
        for name, kind, offset, expected in (
                ('<id>k__BackingField', 0x11, 0x10, item['id']),
                ('<itemType>k__BackingField', 0x11, 0x48, 5),
                ('<maxCntPerGrid>k__BackingField', 8, 0x64,
                 item['max_count_per_grid'])):
            address = obj + _currency_field(rr, ic, name, kind, offset)
            if struct.unpack('<i', rr.anchor(address, 4, 'currency.row.' + name))[0] != expected:
                raise resolver.ResolutionError('Currency configuration value changed')
        auto = obj + _currency_field(rr, ic, '<autoUse>k__BackingField', 0x15,
                                     0x54)
        field = next(f for f in ic['fields'] if f['name'] == '<autoUse>k__BackingField')
        generic = int.from_bytes(bytes.fromhex(field['type_data'])[:8], 'little')
        nullable = rr.info(rr.pointer(generic + 24, 'currency.autoUse.cachedClass'),
                           'Nullable`1', 'System')
        if (rr.field(nullable, 'hasValue', 2) != 16
                or rr.field(nullable, 'value', 2) != 17):
            raise resolver.ResolutionError('Currency nullable Boolean layout differs')
        has_value, value = rr.anchor(auto, 2, 'currency.row.autoUse')
        if has_value not in (0, 1) or value not in (0, 1):
            raise resolver.ResolutionError('Currency auto-use flag is invalid')
        actual_auto = bool(value) if has_value else None
        if actual_auto is not item['auto_use']:
            raise resolver.ResolutionError('Currency auto-use value changed')
        proofs[item['id']] = dict(tables=hex(tables), tables_class=hex(tables_class),
                                 config_object=hex(obj), row_index=index,
                                 anchors=common + list(rr.anchors[row_start:]))
    return proofs


def read_catalogue(pid):
    with resolver.Resolver(pid) as rr:
        try:
            cached = json.loads((cp.CACHE_ROOT / 'config_classes.json').read_text(encoding='utf8'))
            for name in cp.CONFIG_NAMES:
                rr.verify_class(int(cached[name]['klass'], 16), name)
        except (OSError, KeyError, ValueError, resolver.ResolutionError):
            cached, _ = cp.discover_config(rr)
        k = int(cached['LubanDatas.Tables']['klass'], 16)
        tc = rr.verify_class(k, 'LubanDatas.Tables')
        sf = rr.pointer(k + 0xb8, 'Tables.static_fields')
        tables = rr.pointer(sf + rr.field(tc, 'Current', 0x12, static=True), 'Tables.Current')
        if rr.q(tables) != k:
            raise resolver.ResolutionError('Tables.Current class changed')
        rows, _ = cp.table_rows(rr, tables, tc, '<TbItem>k__BackingField', 'LubanDatas.TbItem')
        ic = rr.verify_class(int(cached['LubanDatas.data.Item']['klass'], 16), 'LubanDatas.data.Item')
        l10nc = rr.verify_class(int(cached['LubanDatas.L10nText']['klass'], 16), 'LubanDatas.L10nText')
        items = []
        for obj in rows:
            if rr.q(obj) != int(ic['klass'], 16):
                raise resolver.ResolutionError('Unexpected item row class')
            items.append(dict(
                id=rr.i(obj + rr.field(ic, '<id>k__BackingField', 0x11)),
                config_object=hex(obj),
                names=cp.localized(rr, obj, ic, '<itemName>k__BackingField', l10nc),
                item_type_id=rr.i(obj + rr.field(ic, '<itemType>k__BackingField', 0x11)),
                max_count_per_grid=rr.i(obj + rr.field(ic, '<maxCntPerGrid>k__BackingField', 8)),
                can_use=bool(rr.exact(obj + rr.field(ic, '<canUse>k__BackingField', 2), 1)[0]),
                can_discard=bool(rr.exact(obj + rr.field(ic, '<canDiscard>k__BackingField', 2), 1)[0]),
                auto_use=cp.nullable_bool(rr, obj, ic, '<autoUse>k__BackingField'),
            ))
        if len({i['id'] for i in items}) != len(items):
            raise resolver.ResolutionError('Duplicate item ID')
        currency_proofs = _currency_proofs(rr, k, tables, rows, items)
        itc = rr.verify_class(int(cached['LubanDatas.data.ItemType']['klass'], 16), 'LubanDatas.data.ItemType')
        type_rows, _ = cp.table_rows(rr, tables, tc, '<TbItemType>k__BackingField', 'LubanDatas.TbItemType')
        types = {}
        for obj in type_rows:
            if rr.q(obj) != int(itc['klass'], 16):
                raise resolver.ResolutionError('Unexpected item-type class')
            typeid = rr.i(obj + rr.field(itc, '<id>k__BackingField', 0x11))
            if typeid in types:
                raise resolver.ResolutionError('Duplicate item-type ID')
            types[typeid] = dict(
                type_names=cp.localized(rr, obj, itc, '<typeName>k__BackingField', l10nc),
                bag_type_id=rr.i(obj + rr.field(itc, '<bagType>k__BackingField', 0x11)),
                hide_in_bag=bool(rr.exact(obj + rr.field(itc, '<hideInBag>k__BackingField', 2), 1)[0]),
            )
        for item in items:
            item.update(types[item['item_type_id']])
        for anchor in rr.anchors:
            if rr.exact(anchor['address'], anchor['size']).hex() != anchor['expected_hex']:
                raise resolver.ResolutionError('Configuration changed during read')
        return dict(pid=pid, process_creation_filetime=rr.start_time,
                    captured_unix=time.time(), tables_current=hex(tables),
                    source='Read-only validated Tables.Current -> TbItem / TbItemType; no overrides; collection anchors rechecked',
                    types=types, items=items, currency_proofs=currency_proofs)
