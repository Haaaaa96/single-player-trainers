"""Five saved interaction attributes; cumulative Int32 experience, not stats.

Reviewed native source: PlayerModel.GetInteractAttributeLevel(0xDC1270),
GetInteractAttributeLevelCapByRealm(0xDC1060), GetInteractAttributeMaxValue
(0xDC15B0), SetInteractAttributeValue(0xDC5EE0). Runtime configuration is
rechecked against the shipped build's tbinteractattribute JSON on every read.
"""
import hashlib
import json
import struct
import threading

from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from character_attributes import AttributeResolver, _deduplicate, NS
from character_attributes_interact_write import (ATTRIBUTE_NAMES, InteractTarget,
    InteractWriteOnce, MAXIMUM, pack, parse_attribute_value, validate_attribute_value,
    set_existing_attribute)
from native_method_profiles import resolve_reviewed_method
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

DATA = json.loads((RESOURCE_ROOT / "character_attributes_interact_specs.json").read_text(encoding="utf8"))
SPECS = DATA["metadata"]
TABLES_CLASS_RVA = 0x8211570  # CultivateLayer.get_phase_Ref, mov at 0x100B089.
CONFIG_CLASS_RVA = 0x81D2CC8  # Singleton<ConfigManager>, get_T mov at 0x14B3DDC.
METHOD_TOKEN, METHOD_RVA = 0x06013E63, 0xDC5EE0
METHOD_PREFIX = "48895c2418554883ec20803d832f780700"
METHOD_SPEC = dict(name="SetInteractAttributeValue", token=METHOD_TOKEN, rva=METHOD_RVA,
                   prefix=METHOD_PREFIX, parameters=2, return_kind=1, static=False)


def limits_for(levels, realm, experience):
    """Mirror the native sequential realm stop and final positive threshold."""
    if (type(realm) is not int or realm <= 0 or type(experience) is not int
            or not 0 <= experience <= 2147483647 or not levels):
        raise Refused("当前境界或经验无法核对。")
    cap = 1
    for index, level in enumerate(levels):
        if level["realmId"] > realm:
            break
        cap = index + 1
    maximum = next((x["maxExp"] for x in reversed(levels[:cap]) if x["maxExp"] > 0), 0)
    actual = 1
    for item in levels:
        if experience < item["maxExp"] or actual >= len(levels):
            break
        actual += 1
    return min(actual, cap), cap, maximum


class InteractResolver(AttributeResolver):
    def info(self, klass, fullname=None):
        c = super().info(klass, fullname)
        name = c["namespace"] + "." + c["name"]
        if name in SPECS and name not in ("System.Collections.Generic.Dictionary`2", ".Entry"):
            spec = self.runtime_spec(name, SPECS[name])
            if (self.q(klass + 0x68, anchored=True) != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or {f["name"]: int(f["token"], 16) for f in c["fields"]}
                    != {f["name"]: f["token"] for f in spec["fields"]}
                    or len(c["fields"]) != spec["field_count"]):
                raise Refused("资质与技艺元数据与已验证版本不同。")
        return c

    def reviewed_field(self, c, name, kind, *, static=False):
        fullname = c["namespace"] + "." + c["name"]
        spec = SPECS.get(fullname)
        if spec is None:
            raise Refused("资质与技艺类型未经审核。")
        token = next((f["token"] for f in spec["fields"] if f["name"] == name), None)
        if token is None:
            raise Refused("资质与技艺字段未经审核。")
        return self.field(c, name, kind, token, static=static)

    def dictionary(self, address):
        if not address:
            return {}, [], (0, 0, 0, 0, 0)
        dc = self.obj(address, "System.Collections.Generic.Dictionary`2")
        offsets = {n: self.reviewed_field(dc, n, k) for n, k in
                   (("_entries", 0x1D), ("_count", 8), ("_freeCount", 8), ("_version", 8))}
        if offsets != {"_entries": 24, "_count": 32, "_freeCount": 40, "_version": 44}:
            raise Refused("经验字典布局与静态代码不同。")
        count = self.i(address + 32, anchored=True)
        free = self.i(address + 40, anchored=True)
        version = self.i(address + 44, anchored=True)
        array = self.q(address + 24, anchored=True)
        if not 0 <= free <= count <= 64 or not array and count:
            raise Refused("经验字典长度异常。")
        result, values = {}, []
        if not array:
            return result, values, (address, array, count, free, version)
        ac = self.obj(array, ".Entry[]")
        ec = self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), ".Entry")
        offsets = [self.reviewed_field(ec, n, k) - 16 for n, k in
                   (("hashCode", 8), ("next", 8), ("key", 0x11), ("value", 8))]
        if ec["instance_size"] != 32 or offsets != [0, 4, 8, 12]:
            raise Refused("经验字典并非已确认的枚举与整数布局。")
        if not count <= self.q(array + 24, anchored=True) <= 128:
            raise Refused("经验字典容量异常。")
        live = 0
        for index in range(count):
            entry = array + 32 + index * 16
            h, nxt, key = struct.unpack("<iii", self.anchor(entry, 12))
            if not -1 <= nxt < max(1, count):
                raise Refused("经验字典条目链异常。")
            if h < 0:
                continue
            live += 1
            value = self.i(entry + 12)
            if key not in ATTRIBUTE_NAMES or key in result or value < 0:
                raise Refused("经验编号、重复条目或经验值异常。")
            result[key] = dict(value=value, address=entry + 12)
            values.append((entry + 12, pack(value).hex()))
        if live != count - free:
            raise Refused("经验字典有效条目数不符。")
        return result, values, (address, array, count, free, version)

    def list_objects(self, pointer, maximum):
        c = self.obj(pointer, "Emei.NotifiableList`1")
        parent = self.q(int(c["klass"], 16) + 0x58, anchored=True)
        lc = self.info(parent, "System.Collections.Generic.List`1")
        size = self.i(pointer + self.field(lc, "_size", 8), anchored=True)
        self.i(pointer + self.field(lc, "_version", 8), anchored=True)
        array = self.q(pointer + self.field(lc, "_items", 0x1D), anchored=True)
        if not 0 <= size <= maximum or not array:
            raise Refused("资质配置列表长度异常。")
        if not size <= self.q(array + 24, anchored=True) <= maximum * 2:
            raise Refused("资质配置列表容量异常。")
        raw = self.anchor(array + 32, size * 8) if size else b""
        return list(struct.unpack("<" + "Q" * size, raw))

    def tables(self):
        klass = self.owned_class_address('LubanDatas.Tables')
        tc = self.info(klass, "LubanDatas.Tables")
        sf = self.q(klass + 0xB8, anchored=True)
        tables = self.q(sf + self.reviewed_field(tc, "Current", 0x12, static=True), anchored=True)
        if self.q(tables, anchored=True) != klass:
            raise Refused("当前配置表身份不匹配。")
        # Native Get_T and realm reference properties must read the same Tables.
        config_class = self.owned_class_address('Game.ConfigManager')
        self.info(config_class, 'Game.ConfigManager')
        singleton = self.q(config_class + 0x58, anchored=True)
        sc = self.info(singleton, "Game.Singleton`1")
        static = self.q(singleton + 0xB8, anchored=True)
        lazy = self.q(static + self.field(sc, "lazyInstance", 0x15, 0x04000022, static=True), anchored=True)
        lc = self.obj(lazy, "System.Lazy`1")
        manager = self.q(lazy + self.field(lc, "_value", 0x12, 0x0400042D), anchored=True)
        cc = self.obj(manager, "Game.ConfigManager")
        if self.q(manager + self.reviewed_field(cc, "<Tables>k__BackingField", 0x12), anchored=True) != tables:
            raise Refused("配置表正在切换或存在替代配置，请稍后刷新。")
        return tables, tc

    def table_rows(self, tables, tc, suffix, maximum):
        table = self.q(tables + self.reviewed_field(tc, f"<Tb{suffix}>k__BackingField", 0x12), anchored=True)
        klass = self.obj(table, "LubanDatas.Tb" + suffix)
        overrides = self.q(table + self.reviewed_field(klass, "_overrides", 0x15), anchored=True)
        if overrides:
            dc = self.obj(overrides, "System.Collections.Generic.Dictionary`2")
            count = self.i(overrides + self.reviewed_field(dc, "_count", 8), anchored=True)
            free = self.i(overrides + self.reviewed_field(dc, "_freeCount", 8), anchored=True)
            self.i(overrides + self.reviewed_field(dc, "_version", 8), anchored=True)
            if count != free or not 0 <= count <= 1024:
                raise Refused("资质或境界配置存在覆盖项，暂不支持修改。")
        items = self.q(table + self.reviewed_field(klass, "_dataList", 0x15), anchored=True)
        result = {}
        for pointer in self.list_objects(items, maximum):
            c = self.obj(pointer, "LubanDatas.data." + suffix)
            row_id = self.i(pointer + self.reviewed_field(c, "<id>k__BackingField", 0x11), anchored=True)
            if row_id in result:
                raise Refused("资质或境界配置编号重复。")
            result[row_id] = pointer, c
        return result

    def configuration(self, layer):
        tables, tc = self.tables()
        layers = self.table_rows(tables, tc, "CultivateLayer", 128)
        phases = self.table_rows(tables, tc, "CultivatePhase", 64)
        realms = self.table_rows(tables, tc, "CultivateRealm", 32)
        if layer not in layers:
            raise Refused("当前修为层级没有配置，不提供经验修改。")
        pointer, c = layers[layer]
        phase = self.i(pointer + self.reviewed_field(c, "<phase>k__BackingField", 0x11), anchored=True)
        if phase not in phases:
            raise Refused("当前修为阶段没有配置。")
        pointer, c = phases[phase]
        realm = self.i(pointer + self.reviewed_field(c, "<realm>k__BackingField", 0x11), anchored=True)
        if realm not in realms or realm <= 0:
            raise Refused("当前境界没有配置。")
        rows = self.table_rows(tables, tc, "InteractAttribute", 16)
        if set(rows) != set(ATTRIBUTE_NAMES):
            raise Refused("资质配置不是已确认的五项。")
        levels = {}
        for attr_id, (pointer, c) in rows.items():
            configs = self.q(pointer + self.reviewed_field(c, "<levelConfigs>k__BackingField", 0x15), anchored=True)
            values = []
            for config in self.list_objects(configs, 32):
                lc = self.obj(config, "LubanDatas.InteractAttributeLevelConfig")
                values.append(dict(maxExp=self.i(config + self.reviewed_field(lc, "<maxExp>k__BackingField", 8), anchored=True),
                    realmId=self.i(config + self.reviewed_field(lc, "<realmId>k__BackingField", 0x11), anchored=True)))
            if values != DATA["attributes"][str(attr_id)]["levels"]:
                raise Refused("资质等级阈值与已验证配置不同。")
            levels[attr_id] = values
        return tables, realm, levels

    def method(self, klass, *, include_spec=False):
        count = struct.unpack("<H", self.anchor(klass + 0x120, 2))[0]
        if not 1 <= count <= 512:
            raise Refused("人物属性方法表数量异常。")
        method, selected = resolve_reviewed_method(self, klass, METHOD_SPEC)
        return (method, selected) if include_spec else method


class InteractAttributesAdapter:
    def __init__(self, game_adapter):
        self.game = game_adapter
        self.resolver = InteractResolver(game_adapter.resolver.reader, metadata_base=game_adapter.resolver.meta)
        self._lock, self.blocked = threading.Lock(), False
        from character_attributes_interact_native import InteractAttributesNative
        self._native = InteractAttributesNative(game_adapter, self)

    def snapshot(self):
        if self.blocked or not self.game.resolver or self.game.blocked:
            raise Refused("资质与技艺连接已停止，请先核对游戏。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("无法确认当前角色。")
        rr.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        player = raw["player"]
        pc = rr.obj(player, "Game.Model.PlayerModel")
        combat = rr.q(player + rr.reviewed_field(pc, "combat", 0x12), anchored=True)
        cc = rr.obj(combat, NS + "CombatModel")
        if rr.q(combat + 0x10, anchored=True) != player:
            raise Refused("修为组件不属于当前角色。")
        layer = rr.i(combat + rr.reviewed_field(cc, "<CurrentLayerId>k__BackingField", 0x11), anchored=True)
        pending = rr.q(combat + rr.reviewed_field(cc, "<PendingRealmBreakthrough>k__BackingField", 0x12), anchored=True)
        depth = rr.i(combat + rr.reviewed_field(cc, "_cultivateInjectBatchDepth", 8), anchored=True)
        offset = rr.reviewed_field(pc, "interactAttributes", 0x15)
        if offset != 0x1A8:
            raise Refused("资质保存字段与原生代码不同。")
        dictionary = rr.q(player + offset, anchored=True)
        values, value_anchors, dictionary_identity = rr.dictionary(dictionary)
        tables, realm, levels = rr.configuration(layer)
        can_edit, reason = True, ""
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        except AcquisitionContextRefused:
            can_edit, reason = False, "资质与技艺只能在普通场景且战斗结算结束后修改。"
        if pending or depth:
            can_edit, reason = False, "正在注入修为或进行境界突破，请完成后刷新。"
        anchors = _deduplicate(rr.anchors)
        for address, expected in anchors + tuple(value_anchors):
            if rr.exact(address, len(expected) // 2).hex() != expected:
                raise Refused("读取期间资质、境界或场景变化，请刷新。")
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        owner = (self.game.stamp, raw["manager"], raw["store"], raw["world"], player,
                 combat, int(pc["klass"], 16), layer, tables)
        identity = owner + (dictionary_identity, realm)
        rows = {}
        for attr_id, name in ATTRIBUTE_NAMES.items():
            entry = values.get(attr_id, dict(value=0, address=0))
            level, cap, maximum = limits_for(levels[attr_id], realm, entry["value"])
            supported = 0 <= entry["value"] <= maximum <= MAXIMUM
            target = InteractTarget(key=f"interact:{attr_id}", value=entry["value"], identity=identity,
                anchors=_deduplicate(anchors + tuple(a for a in value_anchors if a[0] != entry["address"])),
                attr_id=attr_id, address=entry["address"], maximum=maximum, can_edit=can_edit and supported)
            rows[target.key] = dict(name=name, layer="累计经验", target=target, display_value=level,
                level_cap=cap, note=f"当前等级 {level}，当前境界等级上限 {cap}。输入累计经验，不是等级或本级进度；"
                "仅整数，单次最多变化 1000。修改后重新打开人物面板核对；保存游戏后保留。"
                + (" 当前经验已超出本境界上限，仅供读取。" if not supported else ""))
        return dict(rows=rows, can_edit=can_edit, reason=reason, owner_identity=owner,
            native=dict(player=hex(player), player_class=pc["klass"], dictionary=hex(dictionary),
                        identity_key=hashlib.sha256(repr(owner).encode()).hexdigest()))

    def resolve(self, key):
        state = self.snapshot()
        if key not in state["rows"]:
            raise Refused("未知资质或技艺。")
        return state["rows"][key]["target"]

    def prepare_native(self, shown, value):
        normalized = validate_attribute_value(shown, value)
        state = self.snapshot()
        if state["rows"][shown.key]["target"] != shown or shown.exists:
            raise Refused("资质条目或境界已变化，请刷新。")
        descriptor = dict(state["native"], attr_id=shown.attr_id, value=normalized, maximum=shown.maximum)
        method, selected = self.resolver.method(int(descriptor["player_class"], 16), include_spec=True)
        descriptor.update(method_info=hex(method), method_spec=selected)
        method_anchors = _deduplicate(tuple(self.resolver.anchors) + shown.anchors)
        descriptor["anchors"] = [dict(address=hex(a), size=len(raw)//2, expected_hex=raw,
            label="interact_context") for a, raw in method_anchors]
        dictionary = int(descriptor["dictionary"], 16)
        if dictionary:
            array, count = self.resolver.q(dictionary + 24), self.resolver.i(dictionary + 32)
            if not 0 <= count <= 64:
                raise Refused("资质条目长度已变化。")
            descriptor["anchors"].extend(dict(address=hex(array + 32 + i * 16), size=16,
                expected_hex=self.resolver.exact(array + 32 + i * 16, 16).hex(),
                label="interact_complete_entry") for i in range(count))
        if any(self.resolver.exact(a, len(raw)//2).hex() != raw for a, raw in method_anchors):
            raise Refused("准备创建经验条目时游戏状态已变化。")
        return descriptor

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused("资质与技艺请求正在处理中。")
        try:
            validate_attribute_value(shown, value)
            from acquisition_adapter import native_calls_pending
            if native_calls_pending():
                raise Refused("游戏原生操作尚未完成，请等待后再修改经验。")
            self._native.require_ready()
            if shown.exists:
                memory = InteractWriteOnce(self.game.resolver.reader, self.game.stamp, shown, new_value=value)
                return set_existing_attribute(memory, self.resolve, shown, value, self._native.record)
            return self._native.set_value(shown, value)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        self._native.close()
