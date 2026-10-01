"""One bounded scalar edit in a resolver-confirmed, natively paused MedGame.

No injection, code patches, pointer writes, synthetic victory, timer loops or
edits to shared game configuration. The resolver supplies the exact current
panel/round anchors; every request re-resolves before one four-byte write.
"""
from native_scalar_guard import coordinated_scalar_write

import ctypes as C
from dataclasses import dataclass, replace
import math
import re
import struct

from native_write import K, MBI, process_identity, read_exact_handle
from write_guard import Refused, UncertainWrite

KEYS = {"meridian_time", "meridian_needles_used", "meridian_transform", "meridian_reveal"}
MAX_CHANGE = 1000
# These are trainer bounds, not claims about native maxima.
CAPS = {"meridian_time": 3600, "meridian_needles_used": 1_000_000,
        "meridian_transform": 999, "meridian_reveal": 999}
MIN_TIME = struct.unpack("<f", struct.pack("<f", 0.01))[0]


@dataclass(frozen=True)
class MeridianTarget:
    key: str
    address: int
    value: int | float
    identity: tuple
    minimum: int | float
    maximum: int | float
    anchors: tuple
    kind: str = "i32"


def parse_value(key, text):
    if key not in KEYS or type(text) is not str or len(text) > 32:
        raise Refused("未知疏经导脉输入，或数字过长。")
    pattern = r"[0-9]{1,7}(?:\.[0-9]{1,2})?" if key == "meridian_time" else r"[0-9]{1,7}"
    if not re.fullmatch(pattern, text.strip()):
        raise Refused("请输入非负数字；时间最多两位小数，其余项目只接受整数。")
    return float(text.strip()) if key == "meridian_time" else int(text.strip())


def _pack(target, value):
    return struct.pack("<f" if target.kind == "f32" else "<i", value)


def validate(target, value):
    if not isinstance(target, MeridianTarget) or target.key not in KEYS:
        raise Refused("未知疏经导脉修改目标。")
    expected_kind = "f32" if target.key == "meridian_time" else "i32"
    if target.kind != expected_kind:
        raise Refused("疏经导脉字段类型不匹配。")
    numbers = (target.value, target.minimum, target.maximum, value)
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in numbers)
    except (OverflowError, ValueError):
        valid = False
    if not valid or target.kind == "i32" and any(type(v) is not int for v in numbers):
        raise Refused("疏经导脉数值类型不正确。")
    if not 0 <= target.minimum <= target.maximum <= CAPS[target.key]:
        raise Refused("疏经导脉目标超出该局允许范围。")
    lower = struct.unpack("<f", struct.pack("<f", target.minimum))[0] if target.kind == "f32" else target.minimum
    upper = struct.unpack("<f", struct.pack("<f", target.maximum))[0] if target.kind == "f32" else target.maximum
    if (type(target.address) is not int or target.address <= 0 or target.address % 4
            or type(target.identity) is not tuple or not target.identity
            or not lower <= target.value <= upper
            or not target.minimum <= value <= target.maximum
            or target.key == "meridian_time" and (target.minimum < MIN_TIME or value <= 0)):
        raise Refused("疏经导脉目标超出该局允许范围。")
    if abs(value - target.value) > MAX_CHANGE:
        raise Refused("疏经导脉单次变化最多 1000。")
    if type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096:
        raise Refused("疏经导脉局次锚无效。")
    for anchor in target.anchors:
        if type(anchor) is not tuple or len(anchor) != 2:
            raise Refused("疏经导脉局次锚无效。")
        address, raw = anchor
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused("疏经导脉局次锚无效。")
        try:
            data = bytes.fromhex(raw)
        except ValueError as exc:
            raise Refused("疏经导脉局次锚无效。") from exc
        if not 1 <= len(data) <= 64 or address < target.address + 4 and address + len(data) > target.address:
            raise Refused("疏经导脉局次锚范围无效。")
    packed = _pack(target, value)
    normalized = struct.unpack("<f" if target.kind == "f32" else "<i", packed)[0]
    if not lower <= normalized <= upper:
        raise Refused("数值按游戏精度取整后超出范围。")
    if packed == _pack(target, target.value):
        raise Refused("目标值与当前值相同。")
    return normalized


class MeridianWriteOnce:
    def __init__(self, reader, process_stamp, target, *, new_value):
        validate(target, new_value)
        self.reader, self.stamp, self.target = reader, process_stamp, target
        self.before, self.after = _pack(target, target.value), _pack(target, new_value)
        self.used = False

    def read_exact(self, address, size):
        if address != self.target.address or size != 4 or process_identity(self.reader.h) != self.stamp:
            raise Refused("疏经导脉目标或游戏进程已变化。")
        return read_exact_handle(self.reader.h, address, size)

    @coordinated_scalar_write
    def write_exact(self, address, value):
        if self.used or address != self.target.address or type(value) is not bytes or value != self.after:
            raise Refused("疏经导脉写入与已核对目标不一致。")
        self.used = True
        handle = K.OpenProcess(0x438, False, self.reader.pid)
        if not handle:
            raise Refused("当前权限不能写入游戏。")
        try:
            if process_identity(handle) != self.stamp:
                raise Refused("游戏进程已更换，未写入。")
            region = MBI()
            if not K.VirtualQueryEx(handle, address, C.byref(region), C.sizeof(region)):
                raise Refused("疏经导脉内存不可查询。")
            if (region.State != 0x1000 or region.Type != 0x20000 or region.Protect != 4
                    or not region.BaseAddress or address < region.BaseAddress
                    or address + 4 > region.BaseAddress + region.RegionSize):
                raise Refused("疏经导脉目标不是普通可写对象内存。")
            for anchor, raw in self.target.anchors:
                expected = bytes.fromhex(raw)
                if read_exact_handle(handle, anchor, len(expected)) != expected:
                    raise Refused("小游戏局次、暂停状态或界面已变化，未写入。")
            if read_exact_handle(handle, address, 4) != self.before:
                raise Refused("疏经导脉数值刚刚变化，未写入。")
            count = C.c_size_t()
            buffer = C.create_string_buffer(value)
            if not K.WriteProcessMemory(handle, address, buffer, 4, C.byref(count)) or count.value != 4:
                raise UncertainWrite("疏经导脉写入结果不确定；请核对画面，勿连续重试。")
        finally:
            K.CloseHandle(handle)


def set_meridian_value(memory, resolve, shown, new_value, record):
    normalized = validate(shown, new_value)
    current = resolve(shown.key)
    if current != shown:
        raise Refused("疏经导脉数值或局次已变化，请刷新后再设置。")
    before, after = _pack(current, current.value), _pack(current, new_value)
    if memory.read_exact(current.address, 4) != before or resolve(shown.key) != current:
        raise Refused("小游戏刚刚变化，未写入。")
    event = dict(target=current.key, before=current.value, after=normalized, storage=current.kind)
    record({**event, "status": "attempt"})
    if memory.read_exact(current.address, 4) != before or resolve(shown.key) != current:
        record({**event, "status": "refused_changed"})
        raise Refused("写入前小游戏刚刚变化，未写入。")
    try:
        memory.write_exact(current.address, after)
    except UncertainWrite as exc:
        try:
            record({**event, "status": "uncertain"})
        finally:
            raise exc
    except Refused:
        record({**event, "status": "refused_changed"})
        raise
    except Exception as exc:
        try:
            record({**event, "status": "uncertain"})
        finally:
            raise UncertainWrite("疏经导脉写入未确认，请核对游戏，勿连续重试。") from exc
    try:
        if memory.read_exact(current.address, 4) != after:
            record({**event, "status": "consumed_or_changed"})
            raise UncertainWrite("写入后数值已变化，结果需核对；不会自动重复写入。")
        after_target = resolve(current.key)
        if (after_target.identity != current.identity or after_target.address != current.address
                or after_target.kind != current.kind or _pack(after_target, after_target.value) != after):
            raise UncertainWrite("写入后局次或目标发生变化，请核对游戏。")
        record({**event, "status": "verified_memory"})
    except UncertainWrite:
        raise
    except Exception as exc:
        raise UncertainWrite("写入后读回或日志未完成，请核对游戏。") from exc
    return replace(current, value=normalized)
