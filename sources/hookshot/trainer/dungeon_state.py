"""Typed, read-only dungeon condition catalog from the matching RomFS.

Names are accepted only after Murmur3 and exact type-table validation. Actor
keys are separate 64-bit keys; their existence alone proves no gameplay meaning.
"""
import struct

from catalog import GAME_DATA


def murmur3(text):
    """GameData name hash (MurmurHash3 x86_32, seed 0)."""
    data = text.encode("utf-8")
    h = 0
    rotate = lambda x, n: ((x << n) | (x >> (32 - n))) & 0xffffffff
    def mix(k):
        return (rotate((k * 0xcc9e2d51) & 0xffffffff, 15) * 0x1b873593) & 0xffffffff
    for offset in range(0, len(data) & ~3, 4):
        h ^= mix(struct.unpack_from("<I", data, offset)[0])
        h = (rotate(h, 13) * 5 + 0xe6546b64) & 0xffffffff
    tail = data[len(data) & ~3:]
    if tail:
        h ^= mix(int.from_bytes(tail, "little"))
    h ^= len(data)
    h ^= h >> 16
    h = h * 0x85ebca6b & 0xffffffff
    h ^= h >> 13
    h = h * 0xc2b2ae35 & 0xffffffff
    return h ^ (h >> 16)


TYPES = {"Bool": "HK_DUNGEON_BOOL", "Int": "HK_DUNGEON_INT",
         "Enum": "HK_DUNGEON_ENUM", "Bool64bitKey": "HK_DUNGEON_BOOL64"}
OPS = {"eq": "HK_DUNGEON_EQ", "ne": "HK_DUNGEON_NE",
       "ge": "HK_DUNGEON_GE", "le": "HK_DUNGEON_LE"}


class GameDataIndex:
    def __init__(self, rom):
        data = rom.byml(GAME_DATA)["Data"]
        self.tables = {kind: {row["Hash"]: row for row in data[kind]} for kind in TYPES}
        self.structs = {row["Hash"]: row for row in data["Struct"]}
        if any(len(self.tables[kind]) != len(data[kind]) for kind in TYPES):
            raise ValueError("GameData contains duplicate typed keys")

    def condition(self, name, expected=1, op="eq", kind=None):
        if not isinstance(name, str) or not name or "?" in name or "/" in name:
            raise ValueError("Use the exact GameData name, not its resource path")
        key = murmur3(name)
        if kind is None:
            matches = [t for t in ("Bool", "Int", "Enum") if key in self.tables[t]]
            if len(matches) != 1:
                raise ValueError(f"{name}: expected exactly one supported GameData type; found {matches}")
            kind = matches[0]
        if kind not in TYPES or kind == "Bool64bitKey" or key not in self.tables[kind]:
            raise ValueError(f"{name}: absent from GameData {kind}")
        row = self.tables[kind][key]
        if kind == "Enum" and isinstance(expected, str):
            if expected not in row["RawValues"]:
                raise ValueError(f"{name}: unknown enum literal {expected}")
            expected = row["Values"][row["RawValues"].index(expected)]
        result = {"hash": key, "type": kind, "expected": expected, "op": op, "name": name}
        self.validate(result)
        return result

    def condition64(self, key, expected=1, op="eq"):
        result = {"hash": key, "type": "Bool64bitKey", "expected": expected,
                  "op": op, "name": f"Bool64bitKey:{key:016x}"}
        self.validate(result)
        return result

    def struct_condition(self, path, expected=1, op="eq", kind=None):
        """Verify every struct link as well as the flattened leaf name hash."""
        parts = path.split(".")
        if len(parts) < 2:
            raise ValueError("A struct condition requires a member path")
        key = murmur3(parts[0])
        for part in parts[1:]:
            row = self.structs.get(key)
            if row is None:
                raise ValueError(f"{path}: missing intermediate Struct")
            members = {member["Hash"]: member["Value"] for member in row["DefaultValue"]}
            key = members.get(murmur3(part))
            if key is None:
                raise ValueError(f"{path}: missing Struct member {part}")
        result = self.condition(path, expected, op, kind)
        if result["hash"] != key:
            raise ValueError(f"{path}: flattened and structured keys disagree")
        return result

    def chest_open(self, actor_hash):
        """TreasureBox.module: IsTreasureBoxOpen, actor instance ID as %llu.

        This is a named Bool, not either of the actor's Bool64 presence keys.
        The caller must bind actor_hash to the actual treasure box actor.
        """
        return self.struct_condition(f"IsTreasureBoxOpen.{actor_hash}", kind="Bool")

    def chain_open(self, gate_hash):
        """DoorChainLock.root uses its *controller* gate ID, not the lock ID.

        f_82a04fb0 -> f_82a05030 resolves the Reference controller and formats
        its instance ID with %llu. MapParam Door.InstanceID supplies that gate.
        """
        return self.struct_condition(f"IsChainLockDoorOpen.{gate_hash}", kind="Bool")

    def dungeon_inventory(self, scene, member, expected=1, op="eq"):
        if member not in ("IsGetBossKey", "SmallKeyNum", "IsGetMap", "IsGetCompass"):
            raise ValueError("Dungeon inventory member has not been verified")
        return self.struct_condition(f"DungeonInfo.{scene}.{member}", expected, op)

    def validate(self, condition):
        kind, key = condition["type"], condition["hash"]
        expected, op = condition["expected"], condition["op"]
        if kind not in TYPES or key not in self.tables[kind]:
            raise ValueError(f"Missing typed condition key: {kind} {key:#x}")
        if op not in OPS or not isinstance(expected, int):
            raise ValueError("Invalid condition comparison")
        if op in ("ge", "le") and kind != "Int":
            raise ValueError("Ordered comparisons require an Int field")
        if kind in ("Bool", "Bool64bitKey") and expected not in (0, 1):
            raise ValueError("Bool comparison value is not a bool")
        if kind == "Int" and not -(1 << 31) <= expected < (1 << 31):
            raise ValueError("Int comparison overflows")
        if kind == "Enum" and expected not in self.tables[kind][key]["Values"]:
            raise ValueError("Enum comparison value is not a member")
        return condition


def generate_dungeon_state(rom, out, scene_conditions):
    """Write ordered per-map slices; return {map_id: first_global_index}.

    Conditions retain caller order (and duplicates), so steps and geometry can
    safely refer to first + their local index. No implicit cross-map reuse.
    """
    index = GameDataIndex(rom)
    conditions, slices, offsets = [], [], {}
    for map_id, items in sorted(scene_conditions.items()):
        if not isinstance(map_id, int) or map_id < 1:
            raise ValueError("A state slice requires an actual map ID")
        offsets[map_id] = len(conditions)
        slices.append((map_id, len(conditions), len(items)))
        conditions.extend(index.validate(item) for item in items)
    maximum = max((row[2] for row in slices), default=1)
    if maximum > 1024:
        raise ValueError("Dungeon condition slice exceeds the bounded read budget")
    (out / "dungeon_state_limits.generated.h").write_text(
        "#pragma once\n" + f"#define HK_DUNGEON_MAX_CONDITIONS {max(1, maximum)}\n", encoding="utf-8")
    lines = ["/* Typed conditions checked against the installed GameData catalog. */",
             f"enum {{ HK_DUNGEON_CONDITION_COUNT = {len(conditions)}, HK_DUNGEON_STATE_SLICE_COUNT = {len(slices)} }};",
             "static const HkDungeonCondition hk_dungeon_conditions[] = {"]
    for item in conditions:
        lines.append(f"    {{0x{item['hash']:016x}ull, 0x{item['expected'] & 0xffffffff:08x}u, "
                     f"{TYPES[item['type']]}, {OPS[item['op']]}, 0}}, /* {item.get('name', '')} */")
    if not conditions:
        lines.append("    {0,0,0,0,0},")
    lines += ["};", "static const HkDungeonStateSlice hk_dungeon_state_slices[] = {"]
    lines.extend("    {%d, %d, %d}," % row for row in slices)
    if not slices:
        lines.append("    {0,0,0},")
    lines.append("};")
    (out / "dungeon_state.generated.h").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return offsets
