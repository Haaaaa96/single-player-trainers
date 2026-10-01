"""Exact Int32 cumulative experience edits for the five interaction attributes."""
from dataclasses import dataclass, replace
import re
import struct

from character_attributes_write import AttributeTarget, AttributeWriteOnce
from write_guard import Refused, UncertainWrite

ATTRIBUTE_NAMES = {1001: "灵机", 1002: "体魄", 1003: "神识", 1004: "辩道", 1005: "医术"}
MAXIMUM, MAX_CHANGE = 5700, 1000


@dataclass(frozen=True)
class InteractTarget(AttributeTarget):
    minimum: int = 0
    maximum: int = MAXIMUM


def pack(value):
    return struct.pack("<i", value)


def parse_attribute_value(text):
    if type(text) is not str or len(text) > 20 or not re.fullmatch(r"[0-9]{1,4}", text.strip()):
        raise Refused("累计经验请输入非负整数，不支持小数。")
    return int(text.strip())


def validate_attribute_value(target, value):
    if (not isinstance(target, InteractTarget) or target.attr_id not in ATTRIBUTE_NAMES
            or target.key != f"interact:{target.attr_id}" or not target.can_edit):
        raise Refused("该资质或技艺当前不能修改，请返回普通场景后刷新。")
    if (any(type(v) is not int for v in (value, target.value, target.minimum, target.maximum))
            or target.minimum != 0 or not 0 < target.maximum <= MAXIMUM
            or not 0 <= target.value <= target.maximum or not 0 <= value <= target.maximum):
        raise Refused("累计经验超出当前境界允许范围。")
    if abs(value - target.value) > MAX_CHANGE:
        raise Refused("累计经验单次变化最多 1000。")
    if value == target.value:
        raise Refused("目标经验与当前值相同。")
    if (type(target.address) is not int or target.address < 0 or target.address % 4
            or not target.exists and target.value != 0
            or type(target.identity) is not tuple or not target.identity
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096):
        raise Refused("资质与技艺目标或身份锚无效。")
    for anchor in target.anchors:
        if type(anchor) is not tuple or len(anchor) != 2:
            raise Refused("资质与技艺身份锚格式无效。")
        address, raw = anchor
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused("资质与技艺身份锚格式无效。")
        try:
            data = bytes.fromhex(raw)
        except ValueError as exc:
            raise Refused("资质与技艺身份锚格式无效。") from exc
        if not 1 <= len(data) <= 4096 or (target.exists and
                address < target.address + 4 and address + len(data) > target.address):
            raise Refused("资质与技艺身份锚范围无效。")
    return value


class InteractWriteOnce(AttributeWriteOnce):
    """Inherit the guarded four-byte write, but encode experience as Int32."""
    def __init__(self, reader, stamp, target, *, new_value):
        normalized = validate_attribute_value(target, new_value)
        if not target.exists:
            raise Refused("该经验条目尚不存在，需要由游戏方法创建。")
        self.reader, self.stamp, self.target = reader, stamp, target
        self.before, self.after, self.used = pack(target.value), pack(normalized), False

    def write_exact(self, address, raw):
        from acquisition_adapter import native_calls_pending
        if native_calls_pending():
            raise Refused("游戏原生操作尚未完成，未修改经验。")
        return super().write_exact(address, raw)


def set_existing_attribute(memory, resolve, shown, value, record):
    normalized = validate_attribute_value(shown, value)
    if not shown.exists:
        raise Refused("经验条目尚不存在。")
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        raise Refused("经验、境界或场景已变化，请刷新后再设置。")
    event = dict(operation="character_interact_set", route="existing_value", attr_id=shown.attr_id,
                 before=shown.value, after=normalized)
    def unknown():
        try:
            record(dict(event, status="unknown"))
        except Exception:
            pass
    record(dict(event, status="attempt"))
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        record(dict(event, status="rejected"))
        raise Refused("写入前经验、境界或场景已变化，未写入。")
    try:
        memory.write_exact(shown.address, pack(normalized))
    except UncertainWrite:
        unknown()
        raise
    except Refused:
        record(dict(event, status="rejected"))
        raise
    except Exception as exc:
        unknown()
        raise UncertainWrite("经验写入未确认，请核对游戏，勿重复操作。") from exc
    try:
        current = resolve(shown.key)
        if current != replace(shown, value=normalized) or memory.read_exact(shown.address, 4) != pack(normalized):
            raise UncertainWrite("经验写入后回读不符。")
        record(dict(event, status="verified"))
    except Exception as exc:
        unknown()
        raise UncertainWrite("经验写入后验证未完成，请核对游戏，勿重复操作。") from exc
    return current
