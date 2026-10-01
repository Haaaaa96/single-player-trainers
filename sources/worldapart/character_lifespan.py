"""Add lifespan through PlayerModel's reviewed lifecycle, never raw writes.

The maximum includes native modifiers. A main-thread inspection obtains the
actual age and maximum; an add repeats that inspection immediately before the
single positive ModifyMaxLifespan call. No age editing or reversal is exposed.
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
from native_write import process_identity
from native_method_profiles import select_method_profile, reviewed_method_profile
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

SPECS = json.loads((RESOURCE_ROOT / "character_lifespan_specs.json").read_text(encoding="utf8"))
LIMIT = 1_000_000  # Conservative Growth[8] bound, not a native lifespan cap.
MAX_NATIVE_INT = 2_147_483_647  # Actual age and maximum are native Int32 values.


def lifespan_anchors(anchors, complete_entries):
    """Expand this operation's 12-byte entry proof only after prefix equality.

    Do not relax the shared deduplicator: all other repeated addresses retain
    its exact-size/exact-byte contract.
    """
    complete = dict(complete_entries)
    kept = []
    for address, raw in anchors:
        if address in complete:
            if not complete[address].startswith(raw):
                raise Refused("寿元完整条目与已读取的身份锚不一致。")
        else:
            kept.append((address, raw))
    return _deduplicate(tuple(kept) + tuple(complete_entries))


@dataclass(frozen=True)
class LifespanTarget:
    current_age: int
    maximum: int
    growth: float
    growth_address: int
    identity: tuple
    anchors: tuple
    can_edit: bool = True
    exhausted: bool = False


def parse_increase(text):
    if type(text) is not str or not re.fullmatch(r"[0-9]{1,4}", text.strip()):
        raise Refused("请输入增加年数，范围为 1～1000 的整数。")
    value = int(text.strip())
    if not 1 <= value <= 1000:
        raise Refused("每次只能增加 1～1000 年；不提供减寿或回退。")
    return value


def validate_increase(target, amount):
    if (type(target) is not LifespanTarget or not target.can_edit or target.exhausted
            or type(amount) is not int or not 1 <= amount <= 1000
            or type(target.current_age) is not int or type(target.maximum) is not int
            or not 0 <= target.current_age <= target.maximum <= MAX_NATIVE_INT or target.maximum <= 0
            or type(target.growth) not in (int, float) or not math.isfinite(target.growth)
            or not -LIMIT <= target.growth <= LIMIT
            or type(target.growth_address) is not int or target.growth_address < 0 or target.growth_address % 4
            or not target.growth_address and target.growth != 0
            or type(target.identity) is not tuple or len(target.identity) != 10
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 20000):
        raise Refused("寿元目标、年龄或寿尽状态不允许增加，请重新读取。")
    for anchor in target.anchors:
        if type(anchor) is not tuple or len(anchor) != 2:
            raise Refused("寿元身份锚格式不正确。")
        address, raw = anchor
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused("寿元身份锚格式不正确。")
        try:
            data = bytes.fromhex(raw)
        except ValueError as exc:
            raise Refused("寿元身份锚格式不正确。") from exc
        if not 1 <= len(data) <= 4096:
            raise Refused("寿元身份锚长度不正确。")
    after = struct.unpack("<f", pack(target.growth + amount))[0]
    if not target.growth < after <= LIMIT:
        raise Refused("增加后的额外寿元超出工具范围。")
    return after


class LifespanResolver(AttributeResolver):
    def lifespan_methods(self, klass):
        # Clear the last read's choice before inspecting a fresh method table.
        self.lifespan_method_profile = None
        table = self.q(klass + 0x98, anchored=True)
        count = struct.unpack("<H", self.anchor(klass + 0x120, 2))[0]
        if not 1 <= count <= 512:
            raise Refused("寿元方法表数量异常。")
        found, observed = {}, {}
        for index in range(count):
            mi = self.q(table + index * 8)
            name = self.reader.string(self.q(mi + 0x18))
            for key, spec in SPECS["methods"].items():
                if name != spec["name"]:
                    continue
                if key in found:
                    raise Refused("寿元方法存在重复入口。")
                found[key] = hex(mi)
                observed[key] = (name, self.i(mi + 0x48, anchored=True),
                                 self.q(mi, anchored=True) - self.module)
        profile = select_method_profile(SPECS, observed)
        selected = reviewed_method_profile(SPECS, profile)
        for key, spec in selected.items():
            mi = int(found[key], 16)
            flags = struct.unpack("<H", self.anchor(mi + 0x4C, 2))[0]
            return_type = self.q(mi + 0x28, anchored=True)
            if (self.i(mi + 0x48, anchored=True) != spec["token"] or flags & 0x10
                    or self.anchor(mi + 0x52, 1) != bytes([spec["parameters"]])
                    or self.q(mi, anchored=True) != self.module + spec["rva"]
                    or self.q(mi + 0x20, anchored=True) != klass
                    or self.anchor(return_type + 10, 1) != bytes([spec["return_kind"]])
                    or self.anchor(return_type + 11, 1)[0] & 0x7F
                    or self.anchor(self.module + spec["rva"], len(spec["prefix"]) // 2).hex() != spec["prefix"]):
                raise Refused("寿元方法签名与已核验版本不同。")
        self.lifespan_method_profile = profile
        return found


class LifespanAdapter:
    def __init__(self, game):
        self.game = game
        self.resolver = LifespanResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self._lock, self.blocked = threading.Lock(), False
        from character_lifespan_native import LifespanNative
        self._native = LifespanNative(game, self)

    def read_context(self):
        if self.blocked or not self.game.resolver or self.game.blocked:
            raise Refused("寿元连接已停止，请先核对游戏。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("无法确认当前角色。")
        rr.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        player = raw["player"]
        pc = rr.obj(player, "Game.Model.PlayerModel")
        combat = rr.q(player + rr.reviewed_field(pc, "combat", 0x12), anchored=True)
        cc = rr.obj(combat, NS + "CombatModel")
        if rr.q(combat + 0x10, anchored=True) != player:
            raise Refused("寿元组件不属于当前角色。")
        layer = rr.i(combat + rr.reviewed_field(cc, "<CurrentLayerId>k__BackingField", 0x11), anchored=True)
        pending = rr.q(combat + rr.reviewed_field(cc, "<PendingRealmBreakthrough>k__BackingField", 0x12), anchored=True)
        depth = rr.i(combat + rr.reviewed_field(cc, "_cultivateInjectBatchDepth", 8), anchored=True)
        growth = rr.q(combat + rr.reviewed_field(cc, "<GrowthAttrs>k__BackingField", 0x15), anchored=True)
        base = rr.q(combat + rr.reviewed_field(cc, "<BaseAttrs>k__BackingField", 0x15), anchored=True)
        values, growth_values, dictionary_identity = rr.dictionary(growth)
        base_values, base_anchors, _ = rr.dictionary(base)
        entry = values.get(8, dict(value=0., address=0))
        health = base_values.get(1)
        if (health is None or not math.isfinite(health["value"]) or not 0 < health["value"] <= LIMIT
                or not math.isfinite(entry["value"]) or not -LIMIT <= entry["value"] <= LIMIT):
            raise Refused("生命或寿元状态不支持此操作；不提供复活。")
        lifecycle = {}
        for key, spec in SPECS["fields"].items():
            offset = rr.reviewed_field(pc, spec["name"], spec["kind"])
            if offset != spec["offset"]:
                raise Refused("寿尽状态字段布局不匹配。")
            data = rr.anchor(player + offset, 1 if key == "handling" else 8)
            if data[0] not in (0, 1):
                raise Refused("寿尽状态格式异常。")
            lifecycle[key] = bool(data[0])
        if any(lifecycle.values()):
            raise Refused("角色正在或曾进入未清除的寿尽处理状态，不通过修改器复活。")
        if pending or depth:
            raise Refused("正在注入修为或境界突破，请完成后再读取寿元。")
        try:
            context = require_safe_acquisition_context(self.game.resolver)
        except AcquisitionContextRefused as exc:
            raise Refused("寿元仅可在普通安全场景读取和增加。") from exc
        rr.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        methods = rr.lifespan_methods(int(pc["klass"], 16))
        # Include the free-slot values too: native creation may reuse those
        # slots, while an inspection must prove the entire old dictionary.
        array, count = dictionary_identity[1:3]
        complete = tuple((array + 32 + i * 16, rr.exact(array + 32 + i * 16, 16).hex())
                         for i in range(count))
        anchors = lifespan_anchors(tuple(rr.anchors) + tuple(growth_values) + tuple(base_anchors), complete)
        if any(rr.exact(a, len(h) // 2).hex() != h for a, h in anchors):
            raise Refused("寿元读取期间状态变化，请重新读取。")
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        owner = (self.game.stamp, raw["manager"], raw["store"], raw["world"], player,
                 combat, int(pc["klass"], 16), growth, layer)
        identity = owner + (dictionary_identity,)
        descriptor = dict(player=hex(player), player_class=pc["klass"], combat=hex(combat), combat_class=cc["klass"],
                          growth_dictionary=hex(growth), base_dictionary=hex(base), growth_before=entry["value"],
                          growth_address=hex(entry["address"]), health_address=hex(health["address"]),
                          methods=methods, identity_key=hashlib.sha256(repr(owner).encode()).hexdigest())
        descriptor["method_profile"] = rr.__dict__.get("lifespan_method_profile", "legacy")
        return dict(identity=identity, anchors=anchors, growth=entry["value"], growth_address=entry["address"],
                    descriptor=descriptor, lifecycle=lifecycle)

    def prepare_native(self, context, shown=None, amount=None):
        fresh = self.read_context()
        if fresh != context:
            raise Refused("寿元、角色或场景已变化，请重新读取。")
        descriptor = dict(fresh["descriptor"])
        if shown is not None:
            after = validate_increase(shown, amount)
            if (shown.identity != fresh["identity"] or shown.anchors != fresh["anchors"]
                    or pack(shown.growth) != pack(fresh["growth"]) or shown.growth_address != fresh["growth_address"]):
                raise Refused("寿元目标已变化，请重新读取。")
            descriptor.update(amount=amount, expected_age=shown.current_age, expected_maximum=shown.maximum,
                              growth_after=after)
        descriptor["anchors"] = [dict(address=hex(a), size=len(h) // 2, expected_hex=h, label="lifespan_context")
                                 for a, h in fresh["anchors"]]
        return descriptor

    def _guard_pending(self):
        from acquisition_adapter import native_calls_pending
        if native_calls_pending():
            raise Refused("另一个游戏原生操作尚未结束，请稍后再读取或增加寿元。")

    def snapshot(self):
        if not self._lock.acquire(blocking=False):
            raise Refused("寿元操作正在处理中。")
        try:
            self._guard_pending()
            context = self.read_context()
            result = self._native.execute(context)
            return dict(target=result["target"], current_age=result["current_age"], maximum=result["maximum"],
                        growth=result["growth"], exhausted=False, can_edit=True)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def increase(self, shown, amount):
        if not self._lock.acquire(blocking=False):
            raise Refused("寿元操作正在处理中。")
        try:
            validate_increase(shown, amount)
            self._guard_pending()
            context = self.read_context()
            self.prepare_native(context, shown, amount)
            return self._native.execute(context, shown, amount)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        self._native.close()
