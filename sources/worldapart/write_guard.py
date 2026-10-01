"""Bounded absolute changes; target resolution is supplied by the game adapter.

No address can be entered by the user. A fresh, validated model snapshot is
required before each change. A failed/uncertain write is never retried.
"""
from dataclasses import dataclass
import re
import struct
from typing import Callable, Protocol


class Refused(RuntimeError):
    pass


class UncertainWrite(Refused):
    write_attempted = True


class PreconditionChanged(Refused):
    """A checked read failed before the operating-system write was called."""
    write_attempted = False


# These are this tool's limits, not a claim about the game's official limits.
INT32_MAX = 2_147_483_647
MAX_CHANGE = 1000
SPIRIT_STONE_MAX_CHANGE = 100_000_000


@dataclass(frozen=True)
class Target:
    key: str
    address: int
    value: int
    # Includes process lifetime, active-player identity, object and item UID.
    identity: tuple
    minimum: int
    maximum: int = INT32_MAX
    # Larger deltas are supplied only by the adapter's verified currency policy.
    # This participates in equality, so refreshing must reproduce the policy.
    max_change: int = MAX_CHANGE


class Memory(Protocol):
    def read_exact(self, address: int, size: int) -> bytes: ...
    def write_exact(self, address: int, value: bytes) -> None: ...


def parse_value(text: str) -> int:
    """Parse a short ASCII decimal target without signs or coercion."""
    if type(text) is not str or len(text) > 64:
        raise Refused("请输入不超过 10 位的非负十进制整数。")
    stripped = text.strip()
    if not re.fullmatch(r"[0-9]{1,10}", stripped):
        raise Refused("请输入非负整数；不接受小数、符号、千分位或科学计数法。")
    value = int(stripped, 10)
    if value > INT32_MAX:
        raise Refused("输入超过 Int32 整数范围。")
    return value


def validate_value(target: Target, new_value: int) -> None:
    """Validate independently at both the policy and native write boundaries."""
    if (not isinstance(target, Target) or type(target.value) is not int or
            type(target.address) is not int or target.address <= 0 or
            target.address % 4 or type(target.minimum) is not int or
            type(target.maximum) is not int or
            type(target.max_change) is not int or
            not 1 <= target.max_change <= SPIRIT_STONE_MAX_CHANGE or
            (target.max_change > MAX_CHANGE and
             (type(target.key) is not str or not target.key.startswith("currency:"))) or
            not 0 <= target.minimum <= target.maximum <= INT32_MAX or
            not target.minimum <= target.value <= INT32_MAX):
        raise Refused("目标数据无效，请重新连接。")
    if type(new_value) is not int:
        raise Refused("目标值必须是整数。")
    if not target.minimum <= new_value <= target.maximum:
        raise Refused(f"允许的目标范围为 {target.minimum}～{target.maximum}。")
    if new_value == target.value:
        raise Refused("目标值与当前值相同，无需修改。")
    if abs(new_value - target.value) > target.max_change:
        raise Refused(f"工具限制：单次变化量最多 {target.max_change}，本次未修改。")


def set_value(memory: Memory, resolve: Callable[[str], Target], shown: Target,
              new_value: int, record: Callable[[dict], None]) -> Target:
    """Resolve repeatedly, compare, write one Int32, and verify once.

    These checks are not an atomic compare-and-swap with the game. The caller
    should operate with the relevant menu open and no concurrent game action.
    Items cannot be reduced to zero: that needs the game's removal workflow.
    """
    validate_value(shown, new_value)
    current = resolve(shown.key)
    if current != shown:
        raise Refused("游戏数据或当前角色已变化；请刷新后再试。")
    validate_value(current, new_value)
    before = struct.pack("<i", current.value)
    after = struct.pack("<i", new_value)
    if memory.read_exact(current.address, 4) != before:
        raise Refused("数值已变化，未写入。")
    if resolve(shown.key) != current:
        raise Refused("对象关系已变化，未写入。")
    event = {"target": current.key, "before": current.value, "after": new_value}
    # A local audit event must be persisted before requesting the write.
    record({**event, "status": "attempt"})
    if memory.read_exact(current.address, 4) != before:
        record({**event, "status": "refused_changed"})
        raise Refused("写入前数值已变化，未写入。")
    if resolve(shown.key) != current:
        record({**event, "status": "refused_changed"})
        raise Refused("写入前对象关系已变化，未写入。")

    def after_write_record(status):
        try:
            record({**event, "status": status})
        except Exception as exc:
            raise UncertainWrite(
                "操作已请求写入，但日志保存失败；请核对游戏当前值，勿重复点击。"
            ) from exc

    try:
        memory.write_exact(current.address, after)
        actual = memory.read_exact(current.address, 4)
    except PreconditionChanged:
        record({**event, "status": "refused_precondition"})
        raise
    except Exception as exc:
        after_write_record("uncertain")
        raise UncertainWrite("写入结果未能确认；已停止，请检查游戏，勿重复点击。") from exc
    if actual != after:
        after_write_record("readback_mismatch")
        raise UncertainWrite("游戏未保留目标值；已停止，不自动重试。")
    after_write_record("verified")
    return Target(current.key, current.address, new_value, current.identity,
                  current.minimum, current.maximum, current.max_change)


def step(memory: Memory, resolve: Callable[[str], Target], shown: Target,
         delta: int, record: Callable[[dict], None]) -> Target:
    """Compatibility helper for existing callers requesting exactly ±1."""
    if type(delta) is not int or delta not in (-1, 1):
        raise Refused("兼容接口每次只能加 1 或减 1。")
    if not isinstance(shown, Target) or type(shown.value) is not int:
        raise Refused("目标数据无效，请重新连接。")
    return set_value(memory, resolve, shown, shown.value + delta, record)
