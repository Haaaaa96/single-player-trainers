"""Generate local map overlays from the game's map and scene tables."""

import json
from math import dist, isfinite

BANC_SUFFIX = ".game__banc__GameBancParam.bgyml"
BASE = "Banc/BancBasedResource"
LABELS = {
    "BottomOfTheWell": "井底", "DeathMountainCrater": "死亡之山火山口",
    "DeathMountainTrail": "死亡之山山道", "DesertColossus": "沙漠巨像",
    "DodongoCavern": "多东哥洞窟", "FireTemple": "火之神殿",
    "ForestTemple": "森之神殿", "GanonCastle": "加侬多夫城堡外",
    "CrumblingGanonCastle": "崩塌的加侬多夫城堡", "FinalBattleField": "加侬多夫城堡废墟",
    "GerudoFortress": "格鲁德要塞", "GerudoTrainingGround": "格鲁德训练场",
    "GerudoValley": "格鲁德之谷", "GoronCity": "鼓隆城", "Graveyard": "墓地",
    "HountedWasteland": "幻影沙漠", "HyruleCastle": "海拉鲁城堡",
    "HyruleField": "海拉鲁平原", "IceCavern": "冰之洞窟",
    "InsideGanonCastle": "加侬多夫城堡内", "InsideJabuJabuBelly": "加卜加卜大人腹中",
    "InsideTheDekuTree": "德库树体内", "KakarikoVillage": "卡卡利科村",
    "KokiriForest": "科奇里森林", "LakeHylia": "海利亚湖", "LonLonRanch": "隆隆牧场",
    "LostWood": "迷途森林", "Market": "海拉鲁城邑", "SacredForestMeadow": "圣林草地",
    "ShadowTemple": "暗之神殿", "SpiritTemple": "魂之神殿", "WaterTemple": "水之神殿",
    "ZoraDomain": "卓拉领地", "ZoraFountain": "卓拉之泉", "ZoraRiver": "卓拉河",
    "SageRoom": "贤者之间", "Demo_ShootingLocation_Tapestry_ED": "结局场景",
    "BossRushIntervalRoom": "首领连战休息室", "EnemyMuseum": "梦境战斗",
    "BarinadeStage": "巴林奈德战", "BigOctoStage": "大章鱼战", "BongoBongoStage": "邦戈邦戈战",
    "DarkLinkStage": "暗影林克战", "DeadHandStage": "死亡之手战", "DinolfosStage": "蜥蜴战士战",
    "DodongoStage": "多东哥王战", "FlareDancerStage": "火焰舞者战",
    "GanondorfStage": "加侬多夫战", "GanonStage": "魔兽加侬战", "GerudoThiefStage": "格鲁德战士战",
    "GohmaStage": "哥玛战", "IronKnuckleBlackStage": "黑色铁甲战士战",
    "IronKnuckleWhiteStage": "白色铁甲战士战", "LizalfosStage": "蜥蜴人战",
    "MegStage": "幽灵梅格战", "MorphaStage": "莫法战", "NaboruStage": "娜波露战",
    "PhantomGanonStage": "幻影加侬战", "StalfosStage": "骷髅战士战",
    "StalfosWeakStage": "骷髅战士练习", "TwinrovaStage": "双生魔女战",
    "VolvagiaStage": "瓦尔巴吉亚战", "WolfosStage": "狼战士战", "WolfosWhiteStage": "白狼战士战",
}
ITEMS = {
    "Item_Range_SlingShot": "妖精弹弓", "Item_BombBag_Small": "炸弹袋",
    "Item_Boomerang": "回旋镖", "Item_Range_Bow": "妖精弓", "Item_Hammer": "巨锤",
    "Item_Longshot": "长钩索", "Item_HoverBoot": "悬浮靴", "Item_HeavyBoot": "重铁靴",
    "Item_GlassTruth": "真实之眼", "Item_Gauntlet_Gold": "金手套", "Item_Arrow_Ice": "冰箭",
    "Item_Dungeon_BossKey": "首领钥匙", "Item_Dungeon_SmallKey": "小钥匙",
    "Item_Dungeon_Map": "迷宫地图", "Item_Dungeon_Compass": "指南针",
}
ACTORS = {
    "Npc_Kokiri_Mido_Child": "米多", "Npc_Goron_Darunia_Child": "达鲁尼亚",
    "Npc_Zora_KingZora_child": "卓拉王", "Npc_Zora_KingZora_Adult": "卓拉王",
    "Npc_Hylia_Malon_Child": "玛蓉", "Npc_Hylia_Talon_Child": "泰荣",
    "Npc_Hylia_Zelda_Child": "塞尔达", "Npc_Kokiri_Saria_Child": "莎莉亚",
    "Npc_Zora_Ruto_Child_001": "露朵",
    "Obj_TimeTemple_MasterSword_A_01": "大师之剑",
    "Obj_TimeTemple_SpiritStoneBase_A_01": "时之神殿石板",
}
STAGE_GOALS = {
    "Get_StoneOfForest": "KokiriForest InsideTheDekuTree InsideTheDekuTree InsideTheDekuTree",
    "Goto_HyruleCastle": "HyruleCastle HyruleCastle HyruleCastle HyruleCastle",
    "Get_StoneOfFire": "DeathMountainTrail GoronCity GoronCity GoronCity LostWood SacredForestMeadow GoronCity DodongoCavern DodongoCavern DodongoCavern DeathMountainTrail",
    "Get_StoneOfWater": "ZoraDomain ZoraDomain LakeHylia ZoraDomain ZoraFountain InsideJabuJabuBelly InsideJabuJabuBelly InsideJabuJabuBelly ZoraFountain",
    "DoorOfTime": "HyruleCastle Market HyruleField Market Market Market",
    "SageOfForest": "Graveyard Graveyard ForestTemple ForestTemple ForestTemple",
    "SageOfFire": "GoronCity GoronCity DeathMountainCrater FireTemple FireTemple FireTemple",
    "SageOfWater": "ZoraFountain IceCavern ZoraDomain WaterTemple WaterTemple WaterTemple",
    "SageOfShadow": "KakarikoVillage BottomOfTheWell ShadowTemple ShadowTemple",
    "SageOfSpirit": "GerudoValley GerudoFortress HountedWasteland HountedWasteland DesertColossus Market SpiritTemple Market SpiritTemple",
    "Defeat_Ganon": "Market GanonCastle InsideGanonCastle InsideGanonCastle InsideGanonCastle InsideGanonCastle CrumblingGanonCastle FinalBattleField FinalBattleField",
}
PRIORITY_ITEMS = {
    "InsideTheDekuTree": "Item_Range_SlingShot", "DodongoCavern": "Item_BombBag_Small",
    "InsideJabuJabuBelly": "Item_Boomerang", "ForestTemple": "Item_Range_Bow",
    "FireTemple": "Item_Hammer", "WaterTemple": "Item_Longshot", "ShadowTemple": "Item_HoverBoot",
    "SpiritTemple": "Item_Dungeon_BossKey", "IceCavern": "Item_HeavyBoot",
    "BottomOfTheWell": "Item_GlassTruth", "GerudoTrainingGround": "Item_Arrow_Ice",
    "InsideGanonCastle": "Item_Dungeon_BossKey",
}
SUBREGIONS = ("LakeHylia", "LonLonRanch")
FALLBACK_BOUNDS = (-24, -24, 24, 24)


def region(name):
    return name.removesuffix("_Alternative").removesuffix("_Adult").removesuffix("_Child").removesuffix("_MQ")


def position(values):
    if isinstance(values, (list, tuple)) and len(values) == 3 and all(isfinite(v) for v in values):
        return tuple(values)
    return None


def wide(value):
    return "L" + json.dumps(value, ensure_ascii=False)


def f(value):
    return f"{value:.4f}f"


def text_bounds(info):
    minimum = info.get("BoundingBoxMin", {})
    maximum = info.get("BoundingBoxMax", {})
    if all("X" in v and "Z" in v for v in (minimum, maximum)):
        return minimum["X"], minimum["Z"], maximum["X"], maximum["Z"]
    return None


def bounds(points, box=None):
    coords = [(p[0], p[2]) for p in points]
    if box:
        coords += [(box[0], box[1]), (box[2], box[3])]
    if not coords:
        return FALLBACK_BOUNDS
    xs, zs = zip(*coords)
    mid_x, mid_z = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    dx, dz = max(14.0, (max(xs) - min(xs)) * .56), max(14.0, (max(zs) - min(zs)) * .56)
    return mid_x - dx, mid_z - dz, mid_x + dx, mid_z + dz


def map_points(row, name, ids):
    out = []
    floors = row.get("Floor", [])
    layout = floors or [row]
    for index, data in enumerate(layout):
        floor = index if floors else -1
        for key, kind, label in (
            ("Door", "Door", "门"), ("TBox", "Chest", "宝箱"),
            ("EntranceAnchor", "Exit", "入口或出口"), ("Facility", "Facility", "设施"),
            ("StoneTablet", "Mechanism", "石板"),
        ):
            for item in data.get(key, []):
                p = position(item.get("Trans"))
                if not p or (kind == "Exit" and not item.get("IsVisible", True)):
                    continue
                dest = region(item.get("Location", ""))
                title = LABELS.get(dest, label) if kind == "Exit" else label
                target = ""
                if name.startswith("HyruleField_") and dest in SUBREGIONS:
                    target = dest + name.removeprefix("HyruleField")
                elif region(name) in SUBREGIONS and dest:
                    suffix = name[len(region(name)):]
                    target = dest + suffix if dest + suffix in ids else dest
                out.append((p, floor, kind, title, target, item.get("InstanceID")))
    for room in row.get("Room", []):
        if room.get("IsInvisibleMiniMap"):
            continue
        center = position(room.get("CenterTrans"))
        if not center:
            continue
        for raw_floor in room.get("Floor", []):
            index = raw_floor - row["MinFloor"]
            if 0 <= index < len(floors):
                out.append((center, index, "Room", "", "", None))
        for entry in room.get("Entrance", []):
            p = position(entry.get("Trans"))
            if p and floors:
                index = min(len(floors)-1, sum(p[1] >= layer["TransY"] for layer in floors) - 1)
                out.append((p, max(index, 0), "Passage", "", "", entry.get("InstanceID")))
    return out


def map_segments(row, thresholds):
    entries = []
    segments = []
    for room_index, room in enumerate(row.get("Room", [])):
        center = position(room.get("CenterTrans"))
        if not center or room.get("IsInvisibleMiniMap"):
            continue
        for entrance in room.get("Entrance", []):
            p = position(entrance.get("Trans"))
            if not p:
                continue
            floor = max(0, sum(p[1] >= y for y in thresholds) - 1)
            if floor + row["MinFloor"] in room.get("Floor", []):
                entries.append((room_index, center, p, floor))
    # Pair the two sides of a doorway only when each is the other's nearest
    # entrance within five units and both are marked on the same floor.
    def opposite(room, point, floor):
        return min(((dist(point, p), i) for i, (other, _, p, layer) in enumerate(entries)
                    if other != room and layer == floor), default=(float("inf"), -1))

    neighbors = [opposite(room, p, floor) for room, _, p, floor in entries]
    for index, (room, center, p, floor) in enumerate(entries):
        gap, other = neighbors[index]
        connected = gap <= 5 and neighbors[other][1] == index
        if connected:
            locked = any(
                door.get("IsChainLocked") and (anchor := position(door.get("Trans"))) and dist(p, anchor) <= 3.5
                for door in row["Floor"][floor].get("Door", [])
            )
            other_room = -1 if locked else entries[other][0]
        else:
            other_room = -1
        segments.append((center[0], center[2], p[0], p[2], floor, room, other_room))
    return segments


def generate_world_map(rom, out):
    native = rom.byml(f"{BASE}/MapParam.byml.zs")
    starts = rom.byml(f"{BASE}/StartPos.byml.zs")
    files = rom.files("Banc/GameBancParam", f"*{BANC_SUFFIX}")
    params = {p.name.removesuffix(BANC_SUFFIX): rom.byml(p.as_posix()) for p in files}
    if set(params) != set(starts):
        raise ValueError("GameBancParam and StartPos disagree about scene coverage")
    names = sorted(set(params) | set(native))
    regions = sorted({region(name) for name in names})
    if set(regions) - LABELS.keys():
        raise ValueError(f"Missing map names: {set(regions) - LABELS.keys()}")
    ids = {name: i for i, name in enumerate(names, 1)}
    region_ids = {name: i for i, name in enumerate(regions, 1)}
    scenes, points, levels, segments = [], [], [], []
    for name in names:
        param = params.get(name, {})
        row = native.get(name, {})
        first = len(points)
        floor_start = len(levels)
        levels.extend(layer["TransY"] for layer in row.get("Floor", []))
        count = len(levels) - floor_start
        marks = map_points(row, name, ids)
        first_segment = len(segments)
        segments.extend(map_segments(row, levels[floor_start:]))
        if name.startswith("HyruleField_"):
            ranch = "LonLonRanch" + name.removeprefix("HyruleField")
            entry = next((position(p["Trans"]) for p in native[ranch]["EntranceAnchor"] if p["Location"] == "HyruleField"), None)
            if entry:
                marks.append((entry, -1, "Exit", LABELS["LonLonRanch"], ranch, None))
        box = text_bounds(param.get("HeightMapParam", {}))
        scene_ref = param.get("Banc", {}).get("Main")
        if scene_ref:
            base = scene_ref.removeprefix("Work/Banc/Scene/").removesuffix(".bcett.json")
            actors = []
            for part in ("Static", "Dynamic"):
                path = f"Banc/{base}_{part}.bcett.byml.zs"
                actors.extend(rom.byml(path).get("Actors", []))
            by_hash = {x["Hash"]: x for x in actors}
            age = "Child" if "_Child" in name else "Adult" if "_Adult" in name else ""
            for actor in actors:
                p = position(actor.get("Translate"))
                if not p:
                    continue
                kind = actor["Gyaml"]
                data = actor.get("Dynamic", {})
                if kind.startswith("FieldAndDungeonEntranceEventRequestActor") and not data.get("IsNoDisplayMapIcon"):
                    a, b = (data.get("NextBancParamName" + x, "") for x in ("Child", "Adult"))
                    choices = [(a, -1)] if age == "Child" or a == b else [(b, -1)] if age == "Adult" else [(a, 1), (b, 0)]
                    for target, child in choices:
                        if target in ids and target != name:
                            # Locate the walkway anchor that is rendered instead of the high trigger.
                            linked = [by_hash.get(link.get("Dst"), {}) for link in actor.get("Links", [])]
                            near = next((position(x.get("Translate")) for x in linked
                                         if x.get("Gyaml") == "DungeonRoomArea"), None)
                            if not count and near is None:
                                candidates = [m[0] for m in marks
                                              if m[2] == "Exit" and m[3] == LABELS[region(target)] and dist(m[0], p) <= 35]
                                if candidates:
                                    near = min(candidates, key=lambda marker: dist(marker, p))
                            marks.append((near or p, -1, "Exit", LABELS[region(target)], target, actor["Hash"], child))
                elif kind.startswith("Enemy_DungeonBoss"):
                    marks.append((p, -1, "Boss", "首领", "", actor["Hash"]))
                elif kind.startswith("Enemy_MiddleBoss"):
                    marks.append((p, -1, "MiddleBoss", "中首领", "", actor["Hash"]))
                elif kind in ACTORS:
                    if not any(m[2] == "Quest" and m[3] == ACTORS[kind] and dist(m[0], p) < 2 for m in marks):
                        marks.append((p, -1, "Quest", ACTORS[kind], "", actor["Hash"]))
                elif count and any(word in kind.lower() for word in ("switchhit", "stepswitch", "waterswitch", "elevator", "movefloor")):
                    marks.append((p, -1, "Mechanism", "机关或平台", "", actor["Hash"]))
                elif "TBox" in kind and data.get("Drop__DropActor") in ITEMS:
                    label = ITEMS[data["Drop__DropActor"]]
                    official_floor = next((m[1] for m in marks if m[5] == actor["Hash"] and m[2] == "Chest"), -1)
                    marks = [m for m in marks if m[5] != actor["Hash"] or m[2] != "Chest"]
                    point_kind = "Goal" if data["Drop__DropActor"] == PRIORITY_ITEMS.get(name) else "Loot"
                    marks.append((p, official_floor, point_kind, label, "", actor["Hash"]))
            if box is None and not marks:
                box = bounds([p for actor in actors if (p := position(actor.get("Translate")))])
        all_positions = [m[0] for m in marks]
        start_points = list(dict.fromkeys(p for item in starts.get(name, {}).values()
                                         if (p := position(item.get("Trans")))))
        all_positions += start_points
        if not marks:
            marks = [(p, -1, "Facility", "场景起点", "", None) for p in start_points]
        if not marks and bbox != FALLBACK_BOUNDS:
            marks = [(((bbox[0]+bbox[2])/2, 0, (bbox[1]+bbox[3])/2), -1, "Room", "", "", None)]
        bbox = bounds(all_positions, box)
        if name not in params and region(name) in SUBREGIONS:
            # These zones have local map data but share Hyrule Field's loaded Banc.
            bbox = bounds(all_positions)
        for p, floor, kind, label, target, _, *age_rule in marks:
            if floor < 0 and count:
                floor = max(0, sum(p[1] >= y for y in levels[floor_start:]) - 1)
            if region(name) == "LostWood" and kind == "Exit" and region(target) == "LostWood":
                continue
            points.append((p, floor, kind, label, ids.get(target, 0), age_rule[0] if age_rule else -1))
        scenes.append((name, first, len(points) - first, floor_start, count, row.get("MinFloor", 0), bbox,
                       first_segment, len(segments) - first_segment, len(row.get("Room", []))))

    with (out / "map_ids.generated.h").open("w", encoding="utf-8") as stream:
        for name in names:
            stream.write(f'HK_MAP_ID({name})\n')
    with (out / "map_data.generated.h").open("w", encoding="utf-8") as stream:
        stream.write("static constexpr HkMapPoint hkMapPoints[] = {\n")
        for p, floor, kind, label, target, age in points:
            stream.write(f"    {{{', '.join(map(f,p))}, {floor}, kMap{kind}, {wide(label)}, {target}, {age}}},\n")
        stream.write("};\nstatic constexpr float hkMapFloors[] = {" + ", ".join(map(f, levels)) + "};\n")
        stream.write("static constexpr HkMapSegment hkMapSegments[] = {\n")
        for x, z, door_x, door_z, floor, room, other in segments:
            stream.write(f"    {{{f(x)}, {f(z)}, {f(door_x)}, {f(door_z)}, {floor}, {room}, {other}}},\n")
        stream.write("};\nstatic constexpr const wchar_t *hkMapRegionNames[] = {L\"跟随主线\", ")
        stream.write(", ".join(wide(LABELS[name]) for name in regions) + "};\n")
        stream.write("static constexpr HkMapScene hkMapScenes[] = {\n    {},\n")
        for name, first, count, floor_start, floors, min_floor, bbox, first_segment, segment_count, room_count in scenes:
            stream.write(f"    {{{wide(LABELS[region(name)])}, {region_ids[region(name)]}, {first}, {count}, "
                         f"{floor_start}, {floors}, {min_floor}, {', '.join(map(f, bbox))}, "
                         f"{first_segment}, {segment_count}, {room_count}}}, /* {name} */\n")
        stream.write("};\n")
        stream.write(f"enum {{ HK_MAX_MAP_ROOMS = {max(row[-1] for row in scenes)} }};\n")
    return region_ids
