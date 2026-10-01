# WorldApart Trainer v1.3

**English** | [简体中文](README_ZH.md)

A standalone trainer research archive for **不问凡尘 (WorldApart)**. Results apply only to the recorded environment; compatibility and effects are not guaranteed. No user support or commitment to future updates is offered. See [terms](../../TERMS.md).

Recorded: **2026-10-01** · Steam Build **25617557** · Windows x64 · The tool UI remains in Chinese.

[Binary archive](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new) · [Guide](GUIDE.md) · [Development notes](DEVLOG.md) · [Source](../../sources/worldapart) · [Build](../../sources/worldapart/BUILD.md) · [Checksums](SHA256SUMS.txt)

## Scope

The archived version contains 54 modification functions across 18 modules, plus a memory-stone checklist, character locations and meridian-route hints.

| Area | Implemented scope |
| --- | --- |
| Character | Spiritual-root and path points; 16 growth attributes; five aptitude/skill experience values; stored spiritual energy; added lifespan |
| Inventory and resources | Item quantities, currency, adding unowned items and manuals, current health, spiritual energy and stamina |
| Activities | Technique learning, meridian assistance, 0.5–2× speed, memory-stone activation/replay, persuasion |
| Crafting and other activities | Alchemy quality and seven talents, recipe exploration, forging quality/affixes and talent points, dual cultivation, jade scraping |

## Archived revision

The “new v1.3” archive keeps the v1.3 UI version and improves the initial reads for aptitude/skills, technique learning and memory stones. The preceding v1.3 work adapted character, resource and activity handling to the reference game build, addressed a connection scan limit, and updated the alchemy spiritual-energy step and memory-stone replay flow.

Use the release tag and checksum to distinguish this package from earlier v1.3 binaries. The public source is a sanitized research snapshot, not a claim of byte-for-byte equivalence with an archived executable; this documentation/source preparation did not run the snapshot or repeat game tests.

The snapshot excludes alchemy_specs.json and photostone_catalog.json, which contain game configuration text; engine_game_types.json was already unavailable. It cannot currently be rebuilt in one step, and affected imports and the full test suite cannot run completely. See the [build notes](../../sources/worldapart/BUILD.md).

## Basic use

Back up the save, start the game and load it, then run WorldApartTrainer.exe and choose “连接游戏” (Connect). The game may be detected automatically or selected through WorldApart.exe. Read or refresh a function page before applying a change.

Use ordinary value/item operations in a stable normal scene. Enter each minigame normally before using its controls. Replay can clear completion records and may grant rewards again; the [guide](GUIDE.md) records those effects and input limits.

## Licensing

Keep the third-party notices included in the executable and the applicable source licenses. The archive does not change rights granted by third-party projects.
