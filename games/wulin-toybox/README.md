# Wulin ToyBox v1.1.0

**English** | [简体中文](README_ZH.md)

A modification research archive for **大侠立志传**, based on HaxxToyBox. Results apply only to the recorded environment; compatibility and effects are not guaranteed. No user support or commitment to future updates is offered. See [terms](../../TERMS.md).

Recorded: **2026-09-30** · Game **V1.2.0818 75 / Steam Build 24794582** · Windows 11 x64 · The tool UI remains in Chinese.

[Binary archive](https://github.com/Haaaaa96/single-player-trainers/releases/tag/wulin-toybox-v1.1.0) · [Guide](GUIDE.md) · [Development notes](DEVLOG.md) · [Source](../../sources/wulin-toybox) · [Build](../../sources/wulin-toybox/BUILD.md) · [Checksums](SHA256SUMS.txt)

## Revision and scope

v1.1.0 repaired character-name/portrait/attribute reading, item search across categories, talent search/add/remove, and martial-art list scrolling and button layout. It also adjusted Chinese fonts and prompts and corrected short-press key capture and Esc cancellation.

The plugin includes current-party character editing, items, talents, money, time pause, post-battle recovery, random-encounter suppression, movement/game speed, gifting assistance, ability-experience multipliers and achievement options. Martial-art limit extensions still require the original EnhanceGameplay module. The character page displays 31 information fields; historical checks included 11 ordinary martial arts and normal upgrades.

## Package boundary

WulinToyBox-v1.1.0-plugin.zip is a plugin update for an existing compatible installation. It does not include BepInEx, .NET, UniverseLib, EnhanceGameplay or Unity libraries. Back up the save and original HaxxToyBox.dll, obtain prerequisites from their original sources, and follow the [guide](GUIDE.md). Tab opens the plugin; the lower-left version should read HaxxToyBox v1.1.0.

Slow startup remains unresolved. Historical checks focused on protagonist attributes, search, talents, martial-art UI and selected assistance controls. Previous use of teammates, gifting and ability-experience multipliers is recorded separately from that revision's tests. Permanent achievement unlocking was not executed.

The public source is a sanitized snapshot requiring local game/prerequisite assemblies. It was not built or run during this preparation and is not claimed to match historical binaries exactly.

## Licensing

- **HaxxToyBox:** original author Haxx; source [neeetman/WuLinToyBoxMod](https://github.com/neeetman/WuLinToyBoxMod), Apache-2.0. See [LICENSE](LICENSE.txt) and [NOTICE](NOTICE.txt).
- **EnhanceGameplay:** the original page lists author 630444540 and submitter gmhaxx. [Original project page](https://mod.3dmgame.com/mod/195081).
- **Referenced integration package:** published by masterZP. on 2024-02-25. The integrator is distinct from the component authors. [Original integration post and prerequisite source](https://bbs.3dmgame.com/thread-6489560-1-1.html).

Preserve each component's attribution and license. This archive does not redistribute unverified third-party dependencies.
