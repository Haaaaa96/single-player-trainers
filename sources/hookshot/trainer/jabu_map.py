"""Read the verified Jabu-Jabu room centers and guide landmarks from the local Banc."""

BANC = "Banc/InsideJabuJabuBelly/InsideJabuJabuBelly_Static.bcett.byml.zs"

# Actor hashes from the v111 scene. Levels are the walkable layers; several
# center anchors are above the actual floor. Path knots use ground-level actors.
POINTS = (
    ("Entrance", 0x4f73373db3bcf5ab, "DungeonRoomCenterAnchor", 1),
    ("EntranceSwitch", 0x22af0df7f5ebb300, "Obj_InsideJabu_Jabu_SwitchHit_A_01", 1),
    ("EntranceDoor", 0xa68cf1567b8d689b, "PushAirWall_DoorFront", 1),
    ("LiftHall", 0xd74eda6184ca9bdb, "DungeonRoomCenterAnchor", 1),
    ("PitDoor", 0xbd4c97cd961a23c5, "PushAirWall_DoorFront", 1),
    ("PitRoom", 0xc1219df2de96e250, "DungeonRoomCenterAnchor", 1),
    ("Ruto", 0xcb9b5b7cae7bb261, "Npc_Zora_Ruto_Child_001", 1),
    ("RutoHole", 0x530456ccfee25875, "DestinationAnchor", 1),
    ("PitBelow", 0xa3d2383552e8102a, "DungeonRoomCenterAnchor", 0),
    ("RutoBelow", 0x972867af099bd11b, "AnchorAction2", 0),
    ("LiftBelow", 0x39bf834be3851737, "DungeonRoomCenterAnchor", 0),
    ("SideCave", 0x9c0b60e53d06d6b2, "DungeonRoomCenterAnchor", 0),
    ("Pool", 0x20c87097e064ff06, "DungeonRoomCenterAnchor", 0),
    ("Octo", 0x39bd8b391347209d, "DungeonRoomCenterAnchor", 0),
    ("Junction", 0x1a0e0f8a8e5c2da2, "DungeonRoomCenterAnchor", 1),
    ("WestRoom", 0x106b37cac8f819f2, "DungeonRoomCenterAnchor", 1),
    ("EastRoom", 0x6c5c54973b26f2da, "DungeonRoomCenterAnchor", 1),
    ("NorthRoom", 0xc8592cc22e9b563c, "DungeonRoomCenterAnchor", 1),
    ("NorthWestRoom", 0xb71826bc78a8931a, "DungeonRoomCenterAnchor", 1),
    ("NorthEastRoom", 0x50b55e9c77b01d8a, "DungeonRoomCenterAnchor", 1),
    ("UpperLift", 0x95ae9fcfc8b48537, "DungeonRoomCenterAnchor", 2),
    ("UpperWest", 0xbdb77cec0f2f595c, "DungeonRoomCenterAnchor", 2),
    ("UpperEast", 0x550a2bb511a25dcf, "DungeonRoomCenterAnchor", 2),
    ("BossApproach", 0xfa757361a0c44e24, "DungeonRoomCenterAnchor", 2),
    ("BossRoom", 0xa1043ba493c33e7d, "DungeonRoomCenterAnchor", 2),
)


def generate_jabu_map(rom, output):
    actors = {actor["Hash"]: actor for actor in rom.byml(BANC)["Actors"]}
    lines = []
    for name, actor_hash, kind, floor in POINTS:
        actor = actors[actor_hash]
        if actor["Gyaml"] != kind or len(actor["Translate"]) != 3:
            raise ValueError(f"Jabu-Jabu map landmark changed: {name}")
        x, _, z = actor["Translate"]
        lines.append(f"HK_JABU_POINT({name}, {x:.3f}f, {z:.3f}f, {floor})")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
