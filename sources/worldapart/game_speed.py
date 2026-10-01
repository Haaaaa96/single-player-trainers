"""Read-only speed-controller resolution; one native SetBaseScale per request.

The game's Overrides list is never changed. It can legitimately make the
effective speed differ from the base setting, including a paused speed of zero.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import struct
import threading

from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from character_attributes import _deduplicate
from character_attributes_write import pack, parse_attribute_value
from learning_adapter import LearningResolver
from native_method_profiles import resolve_reviewed_method
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

SPECS = json.loads((RESOURCE_ROOT / "game_speed_specs.json").read_text(encoding="utf8"))
METHODS = SPECS["methods"]


@dataclass(frozen=True)
class SpeedTarget:
    value: float
    effective: float
    address: int
    identity: tuple
    anchors: tuple
    override_count: int
    can_edit: bool = True


def validate_speed_value(target, value):
    if (type(target) is not SpeedTarget or not target.can_edit or type(target.address) is not int
            or target.address <= 0 or target.address % 4 or type(target.identity) is not tuple
            or not target.identity or type(target.anchors) is not tuple or not target.anchors):
        raise Refused("速度目标尚未就绪，请刷新。")
    if (type(value) not in (int, float) or not math.isfinite(value) or not 0.5 <= value <= 2
            or not math.isfinite(target.value) or not 0 <= target.value <= 100
            or not math.isfinite(target.effective) or not 0 <= target.effective <= 100):
        raise Refused("基础速度仅支持 0.5–2.0 倍。")
    value = struct.unpack("<f", pack(value))[0]
    if pack(value) == pack(target.value):
        raise Refused("基础速度已经是该值；如显示覆盖，请等待游戏解除覆盖。")
    return value


class GameSpeedResolver(LearningResolver):
    def info(self, klass, fullname=None):
        c = super().info(klass, fullname)
        actual = c["namespace"] + "." + c["name"]
        spec = SPECS["classes"].get(actual)
        if spec:
            spec = self.runtime_spec(actual, spec)
            handle = self.q(klass + 0x68, anchored=True)
            if not handle and actual == "System.Collections.Generic.List`1":
                generic = self.q(klass + 0x60, anchored=True)
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] != 0x12 or self.q(generic + 24, anchored=True) != klass:
                    raise Refused("速度覆盖集合泛型不匹配。")
                handle = struct.unpack_from("<Q", raw)[0]
            if (handle != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or len(c["fields"]) != spec["field_count"]
                    or {f["name"]: int(f["token"], 16) for f in c["fields"]}
                    != {f["name"]: f["token"] for f in spec["fields"]}):
                raise Refused("速度控制器元数据与已验证版本不符。")
        return c

    def reviewed_field(self, c, name, kind, offset, *, static=False):
        spec = SPECS["classes"][c["namespace"] + "." + c["name"]]
        token = next(f["token"] for f in spec["fields"] if f["name"] == name)
        actual = self.field(c, name, kind, token, static=static)
        if actual != offset:
            raise Refused("速度控制器字段偏移与已验证版本不符。")
        return actual

    def controller(self):
        klass = self.class_address('Game.GameTimeScaleController')
        c = self.info(klass, "Game.GameTimeScaleController")
        if self.i(klass + 0xE0, anchored=True) != 1:
            raise Refused("速度控制器尚未初始化。")
        static = self.q(klass + 0xB8, anchored=True)
        if not static or static % 8:
            raise Refused("速度静态数据尚未就绪。")
        self.reviewed_field(c, "Overrides", 0x15, 0, static=True)
        self.reviewed_field(c, "_baseScale", 12, 8, static=True)
        address = static + 8
        base = self.f(address)
        overrides = self.q(static, anchored=True)
        lc = self.obj(overrides, "System.Collections.Generic.List`1")
        self.reviewed_field(lc, "_items", 0x1D, 0x10)
        self.reviewed_field(lc, "_size", 8, 0x18)
        self.reviewed_field(lc, "_version", 8, 0x1C)
        items = self.q(overrides + 0x10, anchored=True)
        count = self.i(overrides + 0x18, anchored=True)
        version = self.i(overrides + 0x1C, anchored=True)
        if not items or not 0 <= count <= 64:
            raise Refused("速度覆盖集合长度异常。")
        ac = self.obj(items, ".TimeScaleOverride[]")
        ec = self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), ".TimeScaleOverride")
        self.reviewed_field(ec, "Handle", 8, 16)
        self.reviewed_field(ec, "Scale", 12, 20)
        capacity = self.q(items + 0x18, anchored=True)
        if ec["instance_size"] != 24 or not count <= capacity <= 128:
            raise Refused("速度覆盖条目布局异常。")
        entries, handles = [], set()
        for index in range(count):
            raw = self.anchor(items + 32 + index * 8, 8)
            handle, scale = struct.unpack("<if", raw)
            if handle <= 0 or handle in handles or not math.isfinite(scale) or not 0 <= scale <= 100:
                raise Refused("游戏速度覆盖值无效。")
            handles.add(handle)
            entries.append((handle, scale))
        if not math.isfinite(base) or not 0 <= base <= 100:
            raise Refused("游戏基础速度超出可核对范围。")
        effective = entries[-1][1] if entries else base
        identity = (klass, static, overrides, items, count, version, tuple(entries))
        return dict(value=base, effective=effective, address=address, identity=identity,
                    klass=klass, static=static, overrides=overrides, items=items,
                    override_count=count, override_version=version, capacity=capacity)

    def methods(self, klass, *, include_specs=False):
        methods = METHODS
        count = struct.unpack("<H", self.anchor(klass + 0x120, 2))[0]
        if not 1 <= count <= 64:
            raise Refused("原生方法表数量异常。")
        resolved = {key: resolve_reviewed_method(self, klass, dict(spec, static=True))
                    for key, spec in methods.items()}
        matches = {key: hex(value[0]) for key, value in resolved.items()}
        selected = {key: value[1] for key, value in resolved.items()}
        return (matches, selected) if include_specs else matches



class GameSpeedAdapter:
    def __init__(self, game):
        self.game, self.blocked, self._lock = game, False, threading.Lock()
        self.resolver = GameSpeedResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        from game_speed_native import GameSpeedNative
        self._native = GameSpeedNative(game, self)

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("速度连接已停止，请先核对游戏。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        rr.anchors = []
        raw = rr.controller()
        reason = ""
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        except AcquisitionContextRefused:
            reason = "请在普通稳定场景设置基础速度，战斗或过场暂不支持。"
        anchors = _deduplicate(rr.anchors)
        for address, expected in anchors + ((raw["address"], pack(raw["value"]).hex()),):
            if rr.exact(address, len(expected)//2).hex() != expected:
                raise Refused("游戏速度或场景正在变化，请刷新。")
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        identity = (self.game.stamp,) + raw["identity"]
        target = SpeedTarget(raw["value"], raw["effective"], raw["address"], identity,
                             anchors, raw["override_count"], not reason)
        native = {k: hex(raw[k]) for k in ("klass", "static", "overrides", "items")}
        native.update(override_count=raw["override_count"], override_version=raw["override_version"],
                      capacity=raw["capacity"], identity_key=hashlib.sha256(repr(identity).encode()).hexdigest())
        return dict(target=target, base=target.value, effective=target.effective,
                    override_count=target.override_count, can_edit=not reason, reason=reason, native=native)

    def prepare_native(self, shown, value):
        value = validate_speed_value(shown, value)
        state = self.snapshot()
        if state["target"] != shown:
            raise Refused("速度或游戏覆盖状态已变化，请刷新后重试。")
        rr = self.resolver
        descriptor = dict(state["native"], before=shown.value, effective_before=shown.effective,
                          value=value, address=hex(shown.address))
        methods, selected = rr.methods(int(descriptor["klass"], 16), include_specs=True)
        anchors = _deduplicate(tuple(rr.anchors) + shown.anchors + ((shown.address, pack(shown.value).hex()),))
        if any(rr.exact(a, len(h)//2).hex() != h for a, h in anchors):
            raise Refused("准备设置时速度或场景已变化，未调用。")
        descriptor.update(methods=methods, method_specs=selected, method_info=methods["modify"],
            anchors=[dict(address=hex(a), size=len(h)//2, expected_hex=h, label="speed_context") for a, h in anchors])
        return descriptor

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused("速度请求正在处理中。")
        try:
            validate_speed_value(shown, value)
            from acquisition_adapter import native_calls_pending
            if native_calls_pending():
                raise Refused("原生操作尚未结束，请稍后设置速度。")
            return self._native.set_value(shown, value)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        self._native.close()
