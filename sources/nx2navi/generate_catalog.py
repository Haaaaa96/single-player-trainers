"""Generate the local trainer catalog from installed game tables and checked stock references."""
import argparse
import json
from pathlib import Path
import re
import struct

from catalog import GAME, RomFS, POUCH, UI_POUCH, GAME_DATA, cstring, u32


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
            value = texts[begin:end].decode(encoding, errors="replace").split("\0",1)[0]
            if value and all(ord(x) >= 32 for x in value):
                result[name] = value
            at += 5+n
    return result


def localized(rom, language):
    path = f"Mals/{language}.Product.110.sarc.zs"
    data = dict(sarc(rom.read(path)))["ActorMsg/PouchContent.msbt"]
    return msbt(data)


def quoted(string):
    return json.dumps(string, ensure_ascii=False)


def make_catalog(reference, output, game=GAME):
    rom = RomFS(game)
    rows = rom.byml(POUCH)
    table = rom.byml(UI_POUCH)
    typed = rom.byml(GAME_DATA)["Data"]
    ints = {entry["Hash"] for entry in typed["Int"]}
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
        key = next((k for k in [actor, actor+"_Name", "Name_"+actor] if k in zh or k in en), None)
        translated = zh.get(key)
        english = en.get(key) or (record[4] if record else actor)
        name = f"{translated} / {english}" if translated and translated != english else english
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
        output_rows.append((actor,name,category,restriction,stock,capacity,price,slots,maximum))
    if len({row[0] for row in output_rows}) != len(rows):
        raise ValueError("The pouch registry contains duplicate actor names")
    h = ["const TrainerItem trainer_items[] = {"]
    for row in output_rows:
        parts = [quoted(s) for s in row[:4]] + [str(n) for n in row[4:]]
        h.append("    {" + ", ".join(parts) + "},")
    h += ["};", "const int trainer_item_count = sizeof trainer_items / sizeof trainer_items[0];", ""]
    output.write_text("\n".join(h), encoding="utf-8")
    print(f"Catalog {len(rows)} actors; {sum(not r[3] for r in output_rows)} with stock/capacity prerequisites; "
          f"{sum(' / ' in r[1] for r in output_rows)} bilingual. Item labels sampled: {list(zh)[:6]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--game-dir", type=Path, default=GAME)
    args = parser.parse_args()
    make_catalog(args.reference, args.output, args.game_dir)
