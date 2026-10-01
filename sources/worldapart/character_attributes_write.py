"""Bounded edits to reviewed, permanent GrowthAttrs values, never final stats."""
from native_scalar_guard import coordinated_scalar_write

import ctypes as C
from dataclasses import dataclass, replace
import math
import re
import struct

from native_write import K, MBI, process_identity, read_exact_handle
from write_guard import Refused, UncertainWrite

# These are trainer policy limits, not native game limits. Percentages are
# stored as ratios; the UI converts them to percentage points. Current values,
# lifespan and cultivation transitions require their own native lifecycle.
ATTRIBUTE_NAMES = {2: "攻击", 3: "防御", 4: "生命上限", 5: "幸运", 6: "魅力",
                   21: "速度", 22: "灵力上限", 24: "韧性上限", 201: "精力上限",
                   7: "移速", 111: "暴击率", 112: "暴击伤害", 113: "抗暴",
                   114: "暴伤减免", 115: "命中", 116: "闪避"}
MAXIMUM = 1_000_000
MAX_CHANGE = 1000
PERCENTAGE_IDS = frozenset(range(111, 117))


def attribute_maximum(attr_id):
    return 3.0 if attr_id == 112 else (1.0 if attr_id in PERCENTAGE_IDS else
                                      (10.0 if attr_id == 7 else float(MAXIMUM)))


def attribute_max_change(attr_id):
    return 0.1 if attr_id in PERCENTAGE_IDS else (1.0 if attr_id == 7 else MAX_CHANGE)


def to_display_value(target, value):
    return value * 100 if target.attr_id in PERCENTAGE_IDS else value


def from_display_value(target, value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise Refused("请输入有限的属性数值。")
    return value / 100 if target.attr_id in PERCENTAGE_IDS else value


@dataclass(frozen=True)
class AttributeTarget:
    key: str
    value: float
    identity: tuple
    anchors: tuple
    attr_id: int
    address: int = 0
    minimum: float = 0.0
    maximum: float = float(MAXIMUM)
    can_edit: bool = True

    @property
    def exists(self):
        return self.address > 0


def parse_attribute_value(text):
    if (type(text) is not str or len(text) > 32 or
            not re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", text.strip())):
        raise Refused("请输入非负数字，最多两位小数。")
    return float(text.strip())


def pack(value):
    return struct.pack("<f", value)


def validate_attribute_value(target, value):
    if (not isinstance(target, AttributeTarget) or target.attr_id not in ATTRIBUTE_NAMES
            or target.key != f"growth:{target.attr_id}" or not target.can_edit):
        raise Refused("该人物属性当前不能修改。请返回普通场景后刷新。")
    values = (value, target.value, target.minimum, target.maximum)
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in values)
    except (ValueError, OverflowError):
        valid = False
    if (not valid or not 0 <= target.minimum <= target.maximum <= attribute_maximum(target.attr_id)
            or not target.minimum <= value <= target.maximum
            or not target.minimum <= target.value <= target.maximum):
        raise Refused("成长属性超出该项工具允许范围，请查看选中属性说明。")
    maximum_change = attribute_max_change(target.attr_id)
    # Current values have already been rounded to float32. Comparing two
    # decimal UI endpoints must allow at most one float32 rounding unit.
    tolerance = (max(abs(target.value), abs(value), maximum_change) * 2 ** -23
                 if target.attr_id in PERCENTAGE_IDS else 0.0)
    if abs(value - target.value) > maximum_change + tolerance:
        raise Refused("百分比成长单次最多变化 10 个百分点，移速最多 1，其他属性最多 1000。")
    if (type(target.address) is not int or target.address < 0 or target.address % 4
            or not target.exists and target.value != 0
            or type(target.identity) is not tuple or not target.identity
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096):
        raise Refused("人物属性目标或身份锚无效。")
    for anchor in target.anchors:
        if type(anchor) is not tuple or len(anchor) != 2:
            raise Refused("人物属性身份锚格式无效。")
        address, raw = anchor
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused("人物属性身份锚格式无效。")
        try:
            data = bytes.fromhex(raw)
        except ValueError as exc:
            raise Refused("人物属性身份锚格式无效。") from exc
        if not 1 <= len(data) <= 4096 or (target.exists and
                address < target.address + 4 and address + len(data) > target.address):
            raise Refused("人物属性身份锚范围无效。")
    normalized = struct.unpack("<f", pack(value))[0]
    if not target.minimum <= normalized <= target.maximum or abs(normalized - target.value) > maximum_change + tolerance:
        raise Refused("数值按游戏精度取整后超出允许范围。")
    if pack(normalized) == pack(target.value):
        raise Refused("目标值与当前成长加成相同。")
    return normalized


class AttributeWriteOnce:
    """One existing float value only; never mutate dictionary structure."""
    def __init__(self, reader, stamp, target, *, new_value):
        normalized = validate_attribute_value(target, new_value)
        if not target.exists:
            raise Refused("尚无该成长属性条目，需要由游戏原生方法创建。")
        self.reader, self.stamp, self.target = reader, stamp, target
        self.before, self.after, self.used = pack(target.value), pack(normalized), False

    def read_exact(self, address, size):
        if address != self.target.address or size != 4 or process_identity(self.reader.h) != self.stamp:
            raise Refused("人物属性目标或游戏进程已变化。")
        return read_exact_handle(self.reader.h, address, size)

    @coordinated_scalar_write
    def write_exact(self, address, raw):
        if self.used or address != self.target.address or type(raw) is not bytes or raw != self.after:
            raise Refused("人物属性写入与已核对目标不一致。")
        self.used = True
        handle = K.OpenProcess(0x438, False, self.reader.pid)
        if not handle:
            raise Refused("当前权限不能写入游戏。")
        try:
            if process_identity(handle) != self.stamp:
                raise Refused("游戏进程已经更换，未修改人物属性。")
            region = MBI()
            if (not K.VirtualQueryEx(handle, address, C.byref(region), C.sizeof(region))
                    or region.State != 0x1000 or region.Type != 0x20000 or region.Protect != 4
                    or not region.BaseAddress or address < region.BaseAddress
                    or address + 4 > region.BaseAddress + region.RegionSize):
                raise Refused("人物属性目标不是普通可写对象内存。")
            for pointer, expected in self.target.anchors:
                data = bytes.fromhex(expected)
                if read_exact_handle(handle, pointer, len(data)) != data:
                    raise Refused("角色、属性集合或场景已变化，未修改人物属性。")
            if read_exact_handle(handle, address, 4) != self.before:
                raise Refused("人物属性刚刚变化，请刷新后重试。")
            # Recheck at the final mutation boundary, including subclasses that
            # use this single-scalar transport for saved integer experience.
            from acquisition_adapter import native_calls_pending
            if native_calls_pending():
                raise Refused("游戏原生操作尚未完成，未修改人物属性。")
            count = C.c_size_t()
            buffer = C.create_string_buffer(raw)
            if not K.WriteProcessMemory(handle, address, buffer, 4, C.byref(count)) or count.value != 4:
                raise UncertainWrite("人物属性写入结果不确定，请核对游戏，勿重复操作。")
        finally:
            K.CloseHandle(handle)


def set_existing_attribute(memory, resolve, shown, value, record):
    normalized = validate_attribute_value(shown, value)
    if not shown.exists:
        raise Refused("当前成长属性条目尚不存在。")
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        raise Refused("人物属性或场景已变化，请刷新后再设置。")
    event = dict(operation="character_growth_set", route="existing_value", attr_id=shown.attr_id,
                 before=shown.value, after=normalized)
    def record_unknown():
        # A disk failure must never disguise an attempted mutation as a safe
        # refusal. The already durable attempt remains a retry-blocking state.
        try:
            record(dict(event, status="unknown"))
        except Exception:
            pass
    record(dict(event, status="attempt"))
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        record(dict(event, status="rejected"))
        raise Refused("写入前人物属性或场景已变化，未写入。")
    try:
        memory.write_exact(shown.address, pack(normalized))
    except UncertainWrite:
        record_unknown()
        raise
    except Refused:
        record(dict(event, status="rejected"))
        raise
    except Exception as exc:
        record_unknown()
        raise UncertainWrite("人物属性写入未确认，请核对游戏，勿重复操作。") from exc
    try:
        current = resolve(shown.key)
        if (current != replace(shown, value=normalized)
                or memory.read_exact(shown.address, 4) != pack(normalized)):
            raise UncertainWrite("人物属性写入后回读不符，请核对游戏，勿重复操作。")
        record(dict(event, status="verified"))
    except Exception as exc:
        record_unknown()
        raise UncertainWrite("人物属性写入后验证未完成，请核对游戏。") from exc
    return current
