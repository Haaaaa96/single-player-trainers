# House of Legacy Trainer v0.3.0

**English** | [简体中文](README_ZH.md)

An experimental in-game plugin research archive for **吾今有世家 (House of Legacy)**. Results apply only to the recorded environment; compatibility and effects are not guaranteed. No user support or commitment to future updates is offered. See [terms](../../TERMS.md).

Recorded: **2026-10-01** · Game **V0.9.03 / Steam Build 22970665** · Windows x64 · Unity Mono · BepInEx **5.4.23.5** · The tool UI remains in Chinese.

[Binary archive](https://github.com/Haaaaa96/single-player-trainers/releases/tag/house-of-legacy-v0.3.0) · [Guide](GUIDE.md) · [Development notes](DEVLOG.md) · [Source](../../sources/house-of-legacy) · [Build](../../sources/house-of-legacy/BUILD.md) · [Checksums](SHA256SUMS.txt)

## Scope

The plugin loads with the game and opens with Tab by default. There is no separate trainer executable. It contains 14 one-time operations across four groups:

- **Family:** add/subtract money and add family reputation.
- **Family members:** edit nine attributes and restore stamina once, for the selected member of the player's family.
- **Character creation:** edit remaining trait points, then choose traits through the game's own UI; existing characters' traits are unchanged.
- **Storage:** add vegetables already owned and reduce available storage capacity accordingly; arbitrary items and first-time deposits are outside this version's scope.

## v0.3.0 changes

Tab opens the window during normal play or on the character page, without first opening the Esc menu. Opening pauses the game; closing restores its prior run/pause state and speed. The default left-side layout preserves the character page and refreshes it after identity-checked changes.

The revision also handles Tab inside text fields, repeated opening/closing and input recovery after switching away from the game. An old default F8 configuration migrates to Tab; other customized keys remain unchanged.

## Setup and evidence

Install [BepInEx 5.4.23.5 x64 Mono](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.5) first, then place HouseOfLegacyTrainer.dll in BepInEx/plugins/HouseOfLegacyTrainer. The archive does not include the loader and requires no .NET SDK or Python. Back up the save and follow the [installation and input guide](GUIDE.md).

Historical checks covered window/input behavior, 1×/3× speed restoration, selected value changes and save/restart persistence, creation-page point spending, disabling and reinstalling the plugin. Several fields, reputation level changes, vegetables and completed new-character saves remain unverified; see [development notes](DEVLOG.md).

The public source is a sanitized research snapshot, not a claim of exact equivalence with the archived DLL. This preparation did not run the snapshot or repeat game tests.

## Licensing

The plugin was independently written and references components supplied by the game and BepInEx at runtime. The binary package embeds no third-party DLLs. Preserve the licenses provided by the loader and other component projects when obtaining or redistributing them.
