"""One bounded float32 write to a freshly resolved live learning-game target.

Separate from Int32 item/point writes. No freeze loop, injection, thread creation,
function calls, page-protection changes, or attempts to resume finished rounds.
"""
from native_scalar_guard import coordinated_scalar_write

import ctypes as C
from dataclasses import dataclass, replace
import math
import re
import struct

from native_write import K, MBI, process_identity, read_exact_handle
from write_guard import Refused, UncertainWrite

MAX_FLOAT_CHANGE = 1000.0
KEYS = {"learning_value", "learning_epiphany"}


@dataclass(frozen=True)
class FloatTarget:
    key: str
    address: int
    value: float
    identity: tuple
    minimum: float
    maximum: float
    # (address, expected bytes as hex) from the active panel/round route.
    anchors: tuple


def parse_float_value(text):
    if type(text) is not str or len(text) > 32 or not re.fullmatch(r"[0-9]{1,7}(?:\.[0-9]{1,2})?", text.strip()):
        raise Refused("请输入非负数字，最多两位小数；不接受科学计数法。")
    return float(text.strip())


def validate_float(target, value):
    if not isinstance(target, FloatTarget) or target.key not in KEYS:
        raise Refused("未知小游戏修改目标。")
    numbers = (target.value, target.minimum, target.maximum, value)
    try:
        valid_numbers = all(type(x) in (int,float) and math.isfinite(x) for x in numbers)
    except (OverflowError, ValueError):
        valid_numbers = False
    if not valid_numbers:
        raise Refused("小游戏目标必须是有限数字。")
    if (type(target.address) is not int or target.address <= 0 or target.address % 4
            or not 0 <= target.minimum <= target.value <= target.maximum <= 1_000_000
            or not target.minimum <= value <= target.maximum
            or target.key == "learning_epiphany" and target.maximum != 100
            or not target.anchors or not isinstance(target.identity,tuple)):
        raise Refused("小游戏目标或允许范围不正确。")
    if abs(value - target.value) > MAX_FLOAT_CHANGE:
        raise Refused("小游戏单次变化最多 1000。")
    after = struct.pack("<f", value)
    if after == struct.pack("<f",target.value):
        raise Refused("目标值与当前值相同。")
    if type(target.anchors) is not tuple or len(target.anchors) > 4096:
        raise Refused("小游戏对象锚无效。")
    for anchor in target.anchors:
        if type(anchor) is not tuple or len(anchor) != 2:
            raise Refused("小游戏对象锚无效。")
        address, expected = anchor
        if type(address) is not int or address <= 0 or type(expected) is not str:
            raise Refused("小游戏对象锚无效。")
        try:
            data = bytes.fromhex(expected)
        except ValueError as exc:
            raise Refused("小游戏对象锚无效。") from exc
        if not 1 <= len(data) <= 64:
            raise Refused("小游戏对象锚范围无效。")
    return struct.unpack("<f",after)[0]


class FloatWriteOnce:
    def __init__(self, reader, process_stamp, target, *, new_value):
        validate_float(target,new_value)
        self.reader, self.stamp, self.target = reader, process_stamp, target
        self.before, self.after = struct.pack("<f",target.value), struct.pack("<f",new_value)
        self.used = False

    def read_exact(self,address,size):
        if address != self.target.address or size != 4 or process_identity(self.reader.h) != self.stamp:
            raise Refused("小游戏读取目标或游戏进程已变化。")
        return read_exact_handle(self.reader.h,address,size)

    @coordinated_scalar_write
    def write_exact(self,address,value):
        if self.used or address != self.target.address or type(value) is not bytes or value != self.after:
            raise Refused("小游戏写入与已核对目标不一致。")
        self.used = True
        handle = K.OpenProcess(0x438,False,self.reader.pid)
        if not handle:
            raise Refused("当前权限不能写入游戏。")
        try:
            if process_identity(handle) != self.stamp:
                raise Refused("游戏进程已更换，未写入。")
            region = MBI()
            if not K.VirtualQueryEx(handle,address,C.byref(region),C.sizeof(region)):
                raise Refused("小游戏目标内存不可查询。")
            if (region.State != 0x1000 or region.Type != 0x20000 or region.Protect != 4
                    or not region.BaseAddress or address < region.BaseAddress
                    or address + 4 > region.BaseAddress + region.RegionSize):
                raise Refused("小游戏目标不是普通可写对象内存。")
            for anchor, expected_hex in self.target.anchors:
                expected = bytes.fromhex(expected_hex)
                if read_exact_handle(handle,anchor,len(expected)) != expected:
                    raise Refused("学习局次或界面已改变，未写入。")
            if read_exact_handle(handle,address,4) != self.before:
                raise Refused("小游戏数值刚刚变化，未写入。")
            count = C.c_size_t()
            buffer = C.create_string_buffer(value)
            if not K.WriteProcessMemory(handle,address,buffer,4,C.byref(count)) or count.value != 4:
                raise UncertainWrite("小游戏写入结果不确定；请核对画面，勿连续重试。")
        finally:
            K.CloseHandle(handle)


def set_float_value(memory, resolve, shown, new_value, record):
    """Guarded unit-testable operation. Caller marks its session blocked on uncertainty.

The game continues ticking: a changed value/round before writing is refused;
changes between write and readback are reported as uncertain, never overwritten
again. Setting the star meter to 100 can be consumed by the next game tick.
"""
    packed_value = validate_float(shown,new_value)
    current = resolve(shown.key)
    if current != shown:
        raise Refused("小游戏数值或局次已变化，请刷新后再设置。")
    before, after = struct.pack("<f",current.value), struct.pack("<f",new_value)
    if memory.read_exact(current.address,4) != before or resolve(shown.key) != current:
        raise Refused("小游戏刚刚变化，未写入。")
    event = dict(target=current.key,before=current.value,after=packed_value,storage="float32")
    record({**event,"status":"attempt"})
    if memory.read_exact(current.address,4) != before or resolve(shown.key) != current:
        record({**event,"status":"refused_changed"})
        raise Refused("写入前小游戏刚刚变化，未写入。")
    try:
        memory.write_exact(current.address,after)
    except UncertainWrite as exc:
        try:
            record({**event,"status":"uncertain"})
        finally:
            raise exc
    except Refused:
        record({**event,"status":"refused_changed"})
        raise
    except Exception as exc:
        try:
            record({**event,"status":"uncertain"})
        finally:
            raise UncertainWrite("小游戏写入未确认，请核对游戏，勿连续重试。") from exc
    try:
        actual = memory.read_exact(current.address,4)
        if actual != after:
            record({**event,"status":"consumed_or_changed"})
            raise UncertainWrite("写入后数值已被游戏更新，结果需核对；不会自动重复写入。")
        record({**event,"status":"verified_memory"})
    except UncertainWrite:
        raise
    except Exception as exc:
        raise UncertainWrite("写入后读回或日志未完成，请核对游戏。") from exc
    return replace(current,value=packed_value)
