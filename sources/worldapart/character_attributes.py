"""Version-locked current-player growth attributes with no live heap discovery.

GrowthAttrs is serialized by CombatModelFormatter and read on each native stat
calculation. Existing entry values are four-byte edits; absent entries are
created exclusively by the game's SetGrowthAttr on the shared native bridge.
"""
import hashlib
import json
import math
import struct
import threading

from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from learning_adapter import LearningResolver
from native_method_profiles import resolve_reviewed_method
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite
from character_attributes_write import (ATTRIBUTE_NAMES, PERCENTAGE_IDS, AttributeTarget,
    AttributeWriteOnce, parse_attribute_value, validate_attribute_value,
    set_existing_attribute, pack, attribute_maximum, to_display_value, from_display_value)

SPECS = json.loads((RESOURCE_ROOT / "character_attributes_specs.json").read_text(encoding="utf8"))
NS = "Game.Model.Player.Components."
METHOD_TOKEN, METHOD_RVA = 0x06014B6C, 0xE679F0
METHOD_PREFIX = "48895c2408574883ec30803d981c6e0700"
METHOD_SPEC = dict(name="SetGrowthAttr", token=METHOD_TOKEN, rva=METHOD_RVA,
                   prefix=METHOD_PREFIX, parameters=2, return_kind=1, static=False)


class AttributeResolver(LearningResolver):
    def info(self, klass, fullname=None):
        c = super().info(klass)
        actual = c["namespace"] + "." + c["name"]
        if fullname is not None and fullname != actual:
            raise Refused("人物属性对象类型不匹配。")
        spec = SPECS.get(actual)
        if spec:
            spec = self.runtime_spec(actual, spec)
            handle = self.q(klass + 0x68, anchored=True)
            if not handle and actual in ("System.Collections.Generic.Dictionary`2", ".Entry"):
                generic = self.q(klass + 0x60, anchored=True)
                if not generic:
                    raise Refused("人物属性泛型定义不存在。")
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] not in (0x11, 0x12) or self.q(generic + 24, anchored=True) != klass:
                    raise Refused("人物属性泛型定义不匹配。")
                handle = struct.unpack_from("<Q", raw)[0]
            fields = {f["name"]: int(f["token"], 16) for f in c["fields"]}
            if (handle != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or len(c["fields"]) != spec["field_count"]
                    or fields != {f["name"]: f["token"] for f in spec["fields"]}):
                raise Refused("人物属性元数据与已验证版本不同。")
        return c

    def reviewed_field(self, c, name, kind):
        full = c["namespace"] + "." + c["name"]
        token = next((f["token"] for f in SPECS[full]["fields"] if f["name"] == name), None)
        if token is None:
            raise Refused("人物属性字段未经审核。")
        return self.field(c, name, kind, token)

    def dictionary(self, address):
        dc = self.obj(address, "System.Collections.Generic.Dictionary`2")
        offsets = {n: self.reviewed_field(dc, n, k) for n, k in
                   (("_entries", 0x1D), ("_count", 8), ("_freeCount", 8), ("_version", 8))}
        if offsets != {"_entries": 0x18, "_count": 0x20, "_freeCount": 0x28, "_version": 0x2C}:
            raise Refused("人物属性字典布局与静态代码不同。")
        count = self.i(address + offsets["_count"], anchored=True)
        free = self.i(address + offsets["_freeCount"], anchored=True)
        version = self.i(address + offsets["_version"], anchored=True)
        array = self.q(address + offsets["_entries"], anchored=True)
        if not 0 <= free <= count <= 256 or not array and count:
            raise Refused("人物属性字典长度异常。")
        result, value_anchors = {}, []
        if not array:
            return result, value_anchors, (address, array, count, free, version)
        ac = self.obj(array, ".Entry[]")
        ec = self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), ".Entry")
        stride = ec["instance_size"] - 16
        entry_offsets = [self.reviewed_field(ec, n, k) - 16 for n, k in
                         (("hashCode", 8), ("next", 8), ("key", 0x11), ("value", 0x0C))]
        if stride != 16 or entry_offsets != [0, 4, 8, 12]:
            raise Refused("人物属性条目并非已验证的枚举与单精度数值。")
        capacity = self.q(array + 24, anchored=True)
        if not count <= capacity <= 512:
            raise Refused("人物属性数组容量异常。")
        live = 0
        for index in range(count):
            entry = array + 32 + index * stride
            h, nxt, key = struct.unpack("<iii", self.anchor(entry, 12))
            if not -1 <= nxt < max(1, count):
                raise Refused("人物属性条目链异常。")
            if h < 0:
                continue
            live += 1
            value = self.f(entry + 12)
            if key <= 0 or key in result or abs(value) > 100_000_000:
                raise Refused("人物属性编号、重复条目或数值异常。")
            result[key] = dict(value=value, address=entry + 12)
            value_anchors.append((entry + 12, pack(value).hex()))
        if live != count - free:
            raise Refused("人物属性字典有效条目数不符。")
        return result, value_anchors, (address, array, count, free, version)

    def method(self, klass, *, include_spec=False):
        count = struct.unpack("<H", self.anchor(klass + 0x120, 2))[0]
        if not 1 <= count <= 512:
            raise Refused("人物属性方法表数量异常。")
        method, selected = resolve_reviewed_method(self, klass, METHOD_SPEC)
        return (method, selected) if include_spec else method


def _deduplicate(anchors):
    unique = {}
    for address, raw in anchors:
        if address in unique and unique[address] != raw:
            raise Refused("人物属性读取期间身份锚发生变化。")
        unique[address] = raw
    return tuple(unique.items())


class CharacterAttributesAdapter:
    def __init__(self, game_adapter):
        self.game = game_adapter
        self.resolver = AttributeResolver(game_adapter.resolver.reader,
                                          metadata_base=game_adapter.resolver.meta)
        self._lock = threading.Lock()
        from character_attributes_native import CharacterAttributesNative
        self._native = CharacterAttributesNative(game_adapter, self)
        self.blocked = False

    def snapshot(self):
        if self.blocked or not self.game.resolver or self.game.blocked:
            raise Refused("人物属性连接已停止，请先核对游戏。")
        if process_identity(self.game.resolver.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("无法确认当前角色。")
        rr = self.resolver
        rr.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        pc = rr.obj(raw["player"], "Game.Model.PlayerModel")
        combat = rr.q(raw["player"] + rr.reviewed_field(pc, "combat", 0x12), anchored=True)
        cc = rr.obj(combat, NS + "CombatModel")
        if rr.q(combat + 0x10, anchored=True) != raw["player"]:
            raise Refused("属性组件所属角色与当前存档不同。")
        # A transition in cultivation must not race a permanent stat edit.
        layer = rr.i(combat + rr.reviewed_field(cc, "<CurrentLayerId>k__BackingField", 0x11), anchored=True)
        pending = rr.q(combat + rr.reviewed_field(cc, "<PendingRealmBreakthrough>k__BackingField", 0x12), anchored=True)
        depth = rr.i(combat + rr.reviewed_field(cc, "_cultivateInjectBatchDepth", 8), anchored=True)
        growth = rr.q(combat + rr.reviewed_field(cc, "<GrowthAttrs>k__BackingField", 0x15), anchored=True)
        values, value_anchors, dictionary_identity = rr.dictionary(growth)
        can_edit, reason = True, ""
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        except AcquisitionContextRefused:
            can_edit, reason = False, "人物属性只能在普通场景且战斗结算结束后修改。"
        if pending or depth:
            can_edit, reason = False, "正在注入修为或进行境界突破，请完成后刷新。"
        anchors = _deduplicate(rr.anchors)
        for address, expected in anchors + tuple(value_anchors):
            if rr.exact(address, len(expected) // 2).hex() != expected:
                raise Refused("人物属性读取期间状态变化，请刷新。")
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        owner_identity = (self.game.stamp, raw["manager"], raw["store"], raw["world"],
                          raw["player"], combat, int(cc["klass"], 16), growth)
        identity = owner_identity + (layer, dictionary_identity)
        rows = {}
        for attr_id, name in ATTRIBUTE_NAMES.items():
            entry = values.get(attr_id, dict(value=0.0, address=0))
            target_anchors = _deduplicate(anchors + tuple(a for a in value_anchors if a[0] != entry["address"]))
            maximum = attribute_maximum(attr_id)
            supported = 0 <= entry["value"] <= maximum
            target = AttributeTarget(key=f"growth:{attr_id}", value=entry["value"],
                    identity=identity, anchors=target_anchors, attr_id=attr_id,
                    address=entry["address"], maximum=maximum, can_edit=can_edit and supported)
            rows[target.key] = dict(name=name, layer="永久成长加成", target=target,
                    display_value=None,
                    note=("修改永久成长加成；最终面板值还含境界基础、装备、丹药和技能效果。"
                          + ("按百分点输入，例如 5 表示额外增加 5 个百分点；不是最终概率。"
                             "单次变化最多 10 个百分点，最多两位小数。"
                             if attr_id in PERCENTAGE_IDS else
                             ("这是地图移速加成，不是战斗速度；范围 0～10，单次变化最多 1。"
                              if attr_id == 7 else "范围为修改器限制，单次变化最多 1000，最多两位小数。"))
                          + ("提高上限不补满；降低上限不同时裁剪当前值，显示与消耗由游戏处理。"
                             if attr_id in (4, 22, 24, 201) else "")
                          + ("当前值超出工具范围，只读。" if not supported else "")))
        return dict(rows=rows, can_edit=can_edit, reason=reason,
                    native=dict(combat=hex(combat), combat_class=cc["klass"],
                                player=hex(raw["player"]), dictionary=hex(growth),
                                identity_key=hashlib.sha256(repr(owner_identity).encode()).hexdigest()),
                    owner_identity=owner_identity)

    def resolve(self, key):
        state = self.snapshot()
        if key not in state["rows"]:
            raise Refused("未知人物属性。")
        return state["rows"][key]["target"]

    def prepare_native(self, shown, value):
        normalized = validate_attribute_value(shown, value)
        state = self.snapshot()
        if state["rows"][shown.key]["target"] != shown or shown.exists:
            raise Refused("人物成长条目或场景已变化，请刷新后重新设置。")
        descriptor = dict(state["native"], attr_id=shown.attr_id, value=normalized)
        method, selected = self.resolver.method(int(descriptor["combat_class"], 16), include_spec=True)
        descriptor.update(method_info=hex(method), method_spec=selected)
        method_anchors = _deduplicate(tuple(self.resolver.anchors) + shown.anchors)
        descriptor["anchors"] = [dict(address=hex(a), size=len(raw)//2, expected_hex=raw,
                                       label="character_context") for a, raw in method_anchors]
        # The native branch performs structural creation. Pin complete entries,
        # including free slots, in addition to the scalar-path identity pieces.
        dictionary = int(descriptor["dictionary"], 16)
        array, count = self.resolver.q(dictionary + 0x18), self.resolver.i(dictionary + 0x20)
        if not 0 <= count <= 256:
            raise Refused("人物成长属性条目长度已变化。")
        descriptor["anchors"].extend(dict(address=hex(array + 32 + i * 16), size=16,
            expected_hex=self.resolver.exact(array + 32 + i * 16, 16).hex(),
            label="character_complete_entry") for i in range(count))
        if any(self.resolver.exact(a, len(raw)//2).hex() != raw for a, raw in method_anchors):
            raise Refused("准备创建成长属性时游戏状态已变化。")
        return descriptor

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused("人物属性请求正在处理中。")
        try:
            validate_attribute_value(shown, value)
            from acquisition_adapter import native_calls_pending
            if native_calls_pending():
                raise Refused("游戏原生操作尚未完成，请等待结果后再修改人物属性。")
            self._native.require_ready()
            if shown.exists:
                memory = AttributeWriteOnce(self.game.resolver.reader, self.game.stamp, shown, new_value=value)
                return set_existing_attribute(memory, self.resolve, shown, value,
                                              self._native.record)
            return self._native.set_value(shown, value)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        if self._native is not None:
            self._native.close()
