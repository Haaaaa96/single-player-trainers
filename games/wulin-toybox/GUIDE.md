# Wulin ToyBox v1.1.0 — Guide

**English** | [简体中文](GUIDE_ZH.md)

[Overview](README.md) · [Development notes](DEVLOG.md) · [Terms](../../TERMS.md)

These notes concern the plugin update recorded on 2026-09-30: game V1.2.0818 75 / Steam Build 24794582, Windows 11 x64. The UI remains in Chinese.

## Install the plugin update

1. Exit the game normally. Back up the save and original HaxxToyBox.dll.
2. If the original prerequisite environment is absent, obtain it from the [original integration post](https://bbs.3dmgame.com/thread-6489560-1-1.html) and follow its instructions. This archive is not a complete loader package.
3. Check for BepInEx/plugins/HaxxToyBox/UniverseLib.IL2CPP.dll, the original AssetBundle, loader and other required files. Do not mix framework generations.
4. Merge this package's BepInEx directory into the directory containing Wulin.exe, replacing only HaxxToyBox.dll at the same location. Preserve prerequisites and other MODs; do not clear folders or retain duplicate plugin copies.
5. Launch and load the game, then press Tab. Check for HaxxToyBox v1.1.0 in the lower-left corner. To roll back, exit before restoring the backed-up DLL.

WulinToyBox-v1.1.0-plugin.zip excludes BepInEx, .NET, UniverseLib, EnhanceGameplay and Unity libraries. Martial-art limit extensions still depend on the original EnhanceGameplay module, which is not supplied here.

## Controls and inputs

| Control | Use |
| --- | --- |
| Tab | Show/hide |
| F1 | Recovery |
| = / − | Increase/decrease game speed |
| Key assignment | Change on the assistance page; Esc cancels capture |
| Character attributes | Edit current-party characters' base values; press Enter to submit; equipment/talents may alter final game totals |
| Percentage fields | Decimal 0–1, such as 0.01 |
| Morality/personality fields | Integer −100–100; other fields follow displayed limits |
| Items | Search by name across categories, confirm the result and add integer quantity 1–9999; clear the query to restore categories |
| Money | Target total in 文, integer 0–999999999; Enter submits |
| Ability-experience multiplier | Integer 1–1000; Enter submits; 1 restores normal gain |

Talent controls search, add and remove talents while avoiding duplicate additions. Scroll within the original martial-art list to see more entries; list controls support front ordering and forgetting. “无限武学：由扩展模块处理” is an explanatory label, not a button. Drag the movement-speed slider handle; game speed also has shortcut controls. Set 1× to restore the trainer's normal speed.

Gifting assistance adds a “满好感” (Maximum affinity) button to the NPC gifting page after enabling “添加满好感按钮（送礼页面）”. Click that button on the gifting page; enabling the option alone does not change all NPCs.

The ability-experience multiplier affects newly earned corresponding ability experience. It is not the training resource used for martial-art upgrades and does not directly add existing experience. Max-level abilities may show no further growth.

## Effects and limitations

- Back up and use a separate save first, then verify changes before saving.
- Time pause, random-encounter suppression and protagonist post-battle recovery in one ordinary encounter were historically checked. Suppression does not imply bypassing every scripted battle.
- Teammates, gifting and experience multipliers were retained from earlier normal use; the v1.1.0 checks focused on protagonist attributes, search, talents, martial-art UI and assistance controls.
- Initial launch or a game update may require slow initialization. This remains unresolved. If startup stays stuck, preserve generated files, exit normally and try one restart; do not repeatedly delete caches.
- “解锁成就” (Unlock achievements) is permanent and cannot be undone by restoring a save. A second click within 10 seconds confirms; leaving the assistance page or timing out cancels. Permanent unlocking was not executed in the recorded checks.

## Licensing

HaxxToyBox is by Haxx under Apache-2.0; EnhanceGameplay and the reference integration package have separate attribution. See the [component sources and licensing](README.md#licensing), [LICENSE](LICENSE.txt) and [NOTICE](NOTICE.txt). Preserve original dependency licenses.
