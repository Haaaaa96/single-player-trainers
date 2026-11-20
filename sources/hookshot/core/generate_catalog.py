"""Generate the local trainer catalog from installed game tables and checked stock references."""
import argparse
import json
from pathlib import Path
import re
import struct

from catalog import RomFS, POUCH, UI_POUCH, GAME_DATA, cstring, u32


ACTOR_INFO = "RSDB/ActorInfo.Product.111.rstbl.byml.zs"

AMMO = {
    "Item_DekuStick": 0x457616b0, "Item_DekuNut": 0x735b00f7,
    "Item_DekuSeed": 0xae8cc742, "Item_Bomb": 0xe753508b,
    "Item_Bombchu": 0xe753508b, "Item_Arrow_Normal": 0x418db791,
}


def sarc(data):
    if data[:4] != b"SARC" or data[20:24] != b"SFAT":
        raise ValueError("Expected little endian SARC")
    size = struct.unpack_from("<H", data, 26)[0]
    start = u32(data, 12)
    names = 40+16*size
    for i in range(size):
        _, attr, lo, hi = struct.unpack_from("<IIII", data, 32+16*i)
        name = cstring(data, names+4*(attr & 0xffffff))
        yield name, data[start+lo:start+hi]


def plain_message(raw, encoding):
    """Keep literal text from a name, ignoring only known formatting tags."""
    width = 1 if encoding == "utf-8" else 2
    text = bytearray()
    pos = 0
    while pos + width <= len(raw):
        unit = int.from_bytes(raw[pos:pos+width], "little")
        pos += width
        if unit == 0:
            break
        if unit == 0xE:
            if pos + 6 > len(raw):
                return ""
            group, tag, size = struct.unpack_from("<HHH", raw, pos)
            if pos + 6 + size > len(raw) or (group, tag, size) not in {
                (201, 0, 4), (201, 13, 0), (201, 15, 0), (0, 3, 2),
            }:
                return ""
            pos += 6 + size
        elif unit < 32:
            return ""
        else:
            text.extend(raw[pos-width:pos])
    return text.decode(encoding, errors="strict").strip()


def msbt(data):
    if data[:10] != b"MsgStdBn\xff\xfe" or data[12] not in (0, 1):
        raise ValueError("Expected little endian MSBT")
    encoding = "utf-8" if data[12] == 0 else "utf-16le"
    sections = {}
    pos = 32
    while pos+16 <= len(data):
        length = u32(data, pos+4)
        sections[data[pos:pos+4]] = data[pos+16:pos+16+length]
        pos = (pos+16+length+15) & ~15
    labels, texts = sections[b"LBL1"], sections[b"TXT2"]
    result = {}
    for i in range(u32(labels, 0)):
        count, at = struct.unpack_from("<II", labels, 4+8*i)
        for _ in range(count):
            n = labels[at]
            name = labels[at+1:at+1+n].decode("utf-8")
            idx = u32(labels, at+1+n)
            begin = u32(texts, 4+idx*4)
            end = u32(texts, 8+idx*4) if idx+1 < u32(texts, 0) else len(texts)
            value = plain_message(texts[begin:end], encoding)
            if value:
                result[name] = value
            at += 5+n
    return result


def localized(rom, language):
    path = f"Mals/{language}.Product.110.sarc.zs"
    data = dict(sarc(rom.read(path)))["ActorMsg/PouchContent.msbt"]
    return msbt(data)


def quoted(string):
    return json.dumps(string, ensure_ascii=False)


def localized_name(messages, actor, alias):
    for source in dict.fromkeys((actor, alias)):
        for key in (source + "_Name", "Name_" + source, source):
            value = messages.get(key, "")
            if any(c.isalpha() for c in value) and value not in (actor, alias):
                return value
    return ""


def catalog_name(row, aliases, zh, en, record):
    actor = row["__RowId"]
    alias = aliases.get(actor, actor)
    translated = localized_name(zh, actor, alias)
    english = localized_name(en, actor, alias)
    if not english and record:
        name = record[4].strip()
        if name not in (actor, alias) and any(c.isalpha() for c in name):
            english = name
    if translated or english:
        return f"{translated} / {english}" if translated and english and translated != english else translated or english

    bundle = row.get("BundleActor", "")
    if bundle.startswith("Work/Actor/"):
        member = bundle.removeprefix("Work/Actor/").split(".", 1)[0]
        member_alias = aliases.get(member, member)
        member_name = localized_name(zh, member, member_alias) or localized_name(en, member, member_alias)
        if member_name:
            return f"道具组合：{member_name} ×{row.get('BundleActorNum', 1)}"

    # Keep internal records searchable, without presenting their identifiers as item names.
    kind = next((label for prefix, label in (
        ("Shop_", "商店条目"), ("TBox_", "宝箱条目"), ("Obj_", "场景道具"),
        ("Pouch_", "背包对象"), ("Weapon_", "武器对象"), ("Armor_", "装备对象"),
        ("Shootable_", "投射物"),
    ) if actor.startswith(prefix)), "条目")
    return f"未命名{kind}（{actor}）"


def make_catalog(reference, output, rom, *, hookshot_bottle=False):
    rows = rom.byml(POUCH)
    aliases = {row["__RowId"]: row["ActorName"] for row in rom.byml(ACTOR_INFO) if row.get("ActorName")}
    table = rom.byml(UI_POUCH)
    typed = rom.byml(GAME_DATA)["Data"]
    ints = {entry["Hash"] for entry in typed["Int"]}
    bottle_types = {}
    if hookshot_bottle:
        content_names = ("Empty", "RedPotion", "GreenPotion", "BluePotion", "BlueFire", "Fish",
                         "Letter", "BigPoe", "Poe", "Bug", "Fairy", "MaxMilk", "HalfMilk")
        slot_a, = (entry for entry in typed["Enum"] if entry["Hash"] == 0x7d48df76)
        if tuple(slot_a["RawValues"]) != content_names or len(slot_a["Values"]) != len(content_names):
            raise ValueError("Unexpected bottle contents in the game data")
        bottle_types = {name: (i - 1, value) for i, (name, value) in enumerate(zip(content_names, slot_a["Values"]))}
    bottle_rows = []
    html = reference.read_text(encoding="utf-8")
    ref = json.loads(re.search(r'<script id="catalog" type="application/json">(.*?)</script>', html, re.S)[1])
    inventory = {entry[1]: entry for entry in ref["inventory"]}
    zh = localized(rom, "CNzh")
    en = localized(rom, "USen")

    cells = {}
    for v in table.values():
        if not isinstance(v, list):
            continue
        for row in v:
            if not isinstance(row, dict) or "Actor" not in row or not row.get("BtnName"):
                continue
            for actor in row["Actor"]:
                cells.setdefault(actor.get("ActorShort"), set()).add(row["BtnName"])

    categories = {
        "Material": "材料", "KeyItem": "关键道具", "HeadArmor": "头部装备",
        "Arrow": "弹药", "Bow": "远程武器", "CureItem": "回复道具",
        "Weapon": "武器", "Rupee": "卢比", "Shield": "盾牌",
        "Armor": "服装", "Boot": "靴子", "Other": "其他",
    }
    output_rows = []
    for row in rows:
        actor = row["__RowId"]
        kind = row.get("PouchCategory", "Other")
        category = categories.get(kind, kind)
        lookup = actor
        if actor.startswith("Item_Mask_"):
            lookup = "Armor_Child_Mask_" + actor.removeprefix("Item_Mask_")
        record = inventory.get(lookup)
        stock = record[0] if record and record[0] in ints else 0
        maximum = row.get("FixedMaxNum") or (1 if not row.get("PouchStockable") else 0)
        capacity = AMMO.get(actor, 0)
        name = catalog_name(row, aliases, zh, en, record)
        restriction = ""
        if not stock:
            restriction = "此条目没有经过验证的背包库存字段"
        elif row.get("PouchSpecialDeal") not in ("None", "Ocarina", "Melody", "GlassTruth", "AgonyStone", "Gauntlet", "GoronGauntlet"):
            restriction = "需要通过专门的获取流程"
        elif actor.startswith("Armor_Child_Mask_") and ("Item_Mask_" + actor.removeprefix("Armor_Child_Mask_")) in {r["__RowId"] for r in rows}:
            restriction = "请使用对应的商店面具条目"
        elif row.get("BundleActorNum", 1) != 1 or row.get("BundleActor"):
            restriction = "此条目是道具组合"
        elif not capacity and not maximum:
            restriction = "此物品的库存容量尚未核实"
        price = row.get("SellingPrice", -1)
        # Multiple UI positions can be alternatives (for example, different bottles).
        slots = 1 if len(cells.get(actor, ())) == 1 else -1
        if hookshot_bottle and row.get("AssignableItem") == "BottleA":
            category = "瓶子"
            if actor == "Item_Bottle" and row.get("PouchSpecialDeal") == "Bottle" and not row.get("BottleItem"):
                restriction, slots = "", 1
            elif row.get("BottleItem") == "Letter":
                restriction = "剧情信瓶需按任务流程获取。"
            elif actor.startswith("Item_Bottle_") and row.get("PouchSpecialDeal") == "Bottle" and row.get("BottleItem") in bottle_types:
                restriction, slots = "", 1
                native_type, content_hash = bottle_types[row["BottleItem"]]
                bottle_rows.append((actor, native_type, content_hash))
            elif row.get("BottleItem"):
                restriction = "请选择同名的「可装瓶」条目。"
            elif actor in ("Pouch_Bottle", "Weapon_Bottle"):
                restriction = "请选内部代号为 Item_Bottle 的空瓶子。"
        output_rows.append((actor,name,category,restriction,stock,capacity,price,slots,maximum))
    if len({row[0] for row in output_rows}) != len(rows):
        raise ValueError("The pouch registry contains duplicate actor names")
    h = ["const TrainerItem trainer_items[] = {"]
    for row in output_rows:
        parts = [quoted(s) for s in row[:4]] + [str(n) for n in row[4:]]
        h.append("    {" + ", ".join(parts) + "},")
    h += ["};", "const int trainer_item_count = sizeof trainer_items / sizeof trainer_items[0];", ""]
    output.write_text("\n".join(h), encoding="utf-8")
    if hookshot_bottle:
        if len(bottle_rows) != len(bottle_types) - 2 or len({native_type for _, native_type, _ in bottle_rows}) != len(bottle_rows):
            raise ValueError("Incomplete bottle actor mapping")
        allowed = ", ".join(f"0x{value:08x}u" for _, value in bottle_types.values())
        rows_c = "\n".join(f"    {{{quoted(actor)}, {native_type}, 0x{value:08x}u}},"
                           for actor, native_type, value in bottle_rows)
        output.with_name("bottles.generated.h").write_text(
            f"#define HK_BOTTLE_EMPTY 0x{bottle_types['Empty'][1]:08x}u\n"
            f"static const uint32_t hk_bottle_values[] = {{{allowed}}};\n"
            "static const struct { const char *actor; int type; uint32_t value; } hk_bottle_contents[] = {\n"
            f"{rows_c}\n}};\n", encoding="utf-8")
    print(f"Catalog {len(rows)} actors; {sum(not r[3] for r in output_rows)} with stock/capacity prerequisites; "
          f"{sum(' / ' in r[1] for r in output_rows)} bilingual; "
          f"{sum(r[1].startswith('未命名') for r in output_rows)} without a resolved name.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("romfs", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    make_catalog(args.reference, args.output, RomFS(args.romfs), hookshot_bottle=True)
