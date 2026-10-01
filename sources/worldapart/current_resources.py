"""Current health, mana and stamina are reviewed BaseAttrs[1,25,200].

This module only reads process memory. Mutation uses the corresponding reviewed
Modify method on the shared native session after the game computes its maximum.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import re
import struct
import threading

from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from character_attributes import AttributeResolver, _deduplicate, NS
from character_attributes_write import pack
from native_method_profiles import resolve_reviewed_method
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

RESOURCE_SPECS = json.loads((RESOURCE_ROOT / "current_resources_specs.json").read_text(encoding="utf8"))
METHODS = RESOURCE_SPECS["current_stamina"]["methods"]  # Existing callers' stamina contract.
MAXIMUM, MAX_CHANGE = 1_000_000, 1000


def parse_attribute_value(text):
    """Accept enough digits to round-trip the game's Single resource values."""
    if (type(text) is not str or len(text) > 40 or not re.fullmatch(
            r'[0-9]{1,7}(?:\.[0-9]{1,16})?(?:[eE]-?[0-9]{1,2})?', text.strip())):
        raise Refused('请输入非负资源数值，不接受逗号或非数值内容。')
    value = float(text.strip())
    if not math.isfinite(value) or not 0 <= value <= MAXIMUM:
        raise Refused('资源数值应在 0–1,000,000 内。')
    return value


def resource_input(value):
    return format(value, '.9g')


@dataclass(frozen=True)
class ResourceTarget:
    value: float
    address: int
    identity: tuple
    anchors: tuple
    can_edit: bool = True
    key: str = "current_stamina"


StaminaTarget = ResourceTarget


def validate_resource_value(target, value):
    if (type(target) is not ResourceTarget or target.key not in RESOURCE_SPECS or not target.can_edit
            or type(target.address) is not int or target.address <= 0 or target.address % 4
            or type(target.identity) is not tuple or not target.identity
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096):
        raise Refused("当前资源目标或场景不可修改，请刷新。")
    spec = RESOURCE_SPECS[target.key]
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= MAXIMUM
           for v in (value, target.value)):
        raise Refused("当前资源数值超出工具范围 0–1,000,000。")
    if value < spec["minimum"] or target.value < spec["minimum"]:
        raise Refused("生命必须至少为 1；不通过本功能将角色清零或复活。")
    normalized = struct.unpack("<f", pack(value))[0]
    if abs(value-target.value) > MAX_CHANGE or abs(normalized-target.value) > MAX_CHANGE:
        raise Refused("当前资源单次变化最多 1000。")
    if pack(normalized) == pack(target.value):
        raise Refused("目标值与当前资源相同。")
    for entry in target.anchors:
        if type(entry) is not tuple or len(entry) != 2:
            raise Refused("资源身份锚格式无效。")
        address, raw = entry
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused("资源身份锚格式无效。")
        try:
            data = bytes.fromhex(raw)
        except ValueError as exc:
            raise Refused("资源身份锚格式无效。") from exc
        if not 1 <= len(data) <= 4096 or address < target.address+4 and address+len(data) > target.address:
            raise Refused("资源身份锚范围无效。")
    return normalized


validate_stamina_value = validate_resource_value


def resource_identity_after_modify(before, after):
    """set_Item increments _version even for an already-existing dictionary key."""
    if (not isinstance(before, tuple) or not isinstance(after, tuple) or len(before) != 10
            or len(after) != 10 or before[:9] != after[:9]):
        return False
    old, new = before[9], after[9]
    if (not isinstance(old, tuple) or not isinstance(new, tuple) or len(old) != 5 or len(new) != 5
            or old[:4] != new[:4] or type(old[4]) is not int or type(new[4]) is not int):
        return False
    expected = (old[4] + 1 + 0x80000000) % 0x100000000 - 0x80000000
    return new[4] == expected


class ResourceResolver(AttributeResolver):
    def resource_methods(self, klass, resource_key, *, include_specs=False):
        if resource_key not in RESOURCE_SPECS:
            raise Refused("未知当前资源方法。")
        methods = RESOURCE_SPECS[resource_key]["methods"]
        count = struct.unpack("<H", self.anchor(klass + 0x120, 2))[0]
        if not 1 <= count <= 512:
            raise Refused("原生方法表数量异常。")
        resolved = {key: resolve_reviewed_method(self, klass, dict(spec, static=False))
                    for key, spec in methods.items()}
        matches = {key: hex(value[0]) for key, value in resolved.items()}
        selected = {key: value[1] for key, value in resolved.items()}
        return (matches, selected) if include_specs else matches

    def stamina_methods(self, klass):
        return self.resource_methods(klass, "current_stamina")


StaminaResolver = ResourceResolver


class CurrentResourcesAdapter:
    def __init__(self, game):
        self.game = game
        self.resolver = ResourceResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self._lock, self.blocked = threading.Lock(), False
        from current_resources_native import CurrentResourcesNative
        self._native = CurrentResourcesNative(game, self)

    def snapshot(self):
        if self.blocked or not self.game.resolver or self.game.blocked:
            raise Refused("当前资源连接已停止，请先核对游戏。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("无法确认当前角色。")
        rr.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        pc = rr.obj(raw["player"], "Game.Model.PlayerModel")
        combat = rr.q(raw["player"] + rr.reviewed_field(pc, "combat", 0x12), anchored=True)
        cc = rr.obj(combat, NS + "CombatModel")
        if rr.q(combat + 0x10, anchored=True) != raw["player"]:
            raise Refused("资源组件不属于当前角色。")
        layer = rr.i(combat + rr.reviewed_field(cc, "<CurrentLayerId>k__BackingField", 0x11), anchored=True)
        pending = rr.q(combat + rr.reviewed_field(cc, "<PendingRealmBreakthrough>k__BackingField", 0x12), anchored=True)
        depth = rr.i(combat + rr.reviewed_field(cc, "_cultivateInjectBatchDepth", 8), anchored=True)
        base = rr.q(combat + rr.reviewed_field(cc, "<BaseAttrs>k__BackingField", 0x15), anchored=True)
        if not base:
            raise Refused("当前角色资源集合尚未初始化，请回游戏完成初始化。")
        values, value_anchors, dictionary_identity = rr.dictionary(base)
        reason = ""
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        except AcquisitionContextRefused:
            reason = "当前资源只能在普通场景且战斗结算结束后修改。"
        if pending or depth:
            reason = "正在修为注入或境界突破，请完成后刷新。"
        anchors = _deduplicate(rr.anchors)
        for address, expected in anchors + tuple(value_anchors):
            if rr.exact(address, len(expected)//2).hex() != expected:
                raise Refused("资源或角色状态正在变化，请刷新。")
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        owner = (self.game.stamp, raw["manager"], raw["store"], raw["world"], raw["player"],
                 combat, int(cc["klass"], 16), base, layer)
        rows = {}
        for key, spec in RESOURCE_SPECS.items():
            entry, row_reason, target = values.get(spec["attr_id"]), reason, None
            if not entry:
                row_reason = f"当前{spec['name']}条目尚未初始化，请先让游戏正常初始化后再刷新。"
            elif not spec["minimum"] <= entry["value"] <= MAXIMUM:
                row_reason = f"当前{spec['name']}超出工具支持范围，仅供查看。" + ("不提供复活。" if key == "current_health" else "")
            if entry:
                target = ResourceTarget(entry["value"], entry["address"], owner+(dictionary_identity,),
                    _deduplicate(anchors+tuple(a for a in value_anchors if a[0] != entry["address"])), not row_reason, key)
            rows[key] = dict(target=target, can_edit=not row_reason, reason=row_reason, name=spec["name"], resource_key=key,
                             current=None if not entry else entry["value"], maximum=None)
        return dict(rows=rows, **rows["current_stamina"],
                    native=dict(combat=hex(combat), combat_class=cc["klass"], player=hex(raw["player"]),
                    dictionary=hex(base), identity_key=hashlib.sha256(repr(owner).encode()).hexdigest()))

    def resolve(self, key):
        if key not in RESOURCE_SPECS:
            raise Refused("未知当前资源。")
        return self.snapshot()["rows"][key]["target"]

    def prepare_native(self, shown, value):
        value = validate_resource_value(shown, value)
        state = self.snapshot()
        if state["rows"][shown.key]["target"] != shown:
            raise Refused("资源、角色或场景已变化，请刷新后重新设置。")
        rr = self.resolver
        descriptor = dict(state["native"], before=shown.value, value=value, address=hex(shown.address), resource_key=shown.key)
        methods, selected = rr.resource_methods(int(descriptor["combat_class"], 16), shown.key, include_specs=True)
        descriptor.update(methods=methods, method_specs=selected, method_info=methods["modify"])
        anchors = _deduplicate(tuple(rr.anchors) + shown.anchors + ((shown.address, pack(shown.value).hex()),))
        if any(rr.exact(a, len(h)//2).hex() != h for a, h in anchors):
            raise Refused("准备资源修改时游戏状态已变化，未调用。")
        descriptor["anchors"] = [dict(address=hex(a), size=len(h)//2, expected_hex=h, label="current_resource_context")
                                 for a, h in anchors]
        return descriptor

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused("当前资源请求正在处理中。")
        try:
            validate_resource_value(shown, value)
            from acquisition_adapter import native_calls_pending
            if native_calls_pending():
                raise Refused("游戏原生操作尚未结束，请稍后再修改当前资源。")
            return self._native.set_value(shown, value)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        self._native.close()
