English | [简体中文](README_ZH.md)

# ZaohuaTrainer — Destiny of Immortal / 造化仙缘

**v0.12.0-alpha.52 · experimental archive · 2026-10-28**

[Full Windows x64 package](https://github.com/Haaaaa96/single-player-trainers/releases/download/zaohua-v0.12.0-alpha.52/ZaohuaTrainer-v0.12.0-alpha.52-full-win64.zip) · [Release page](https://github.com/Haaaaa96/single-player-trainers/releases/tag/zaohua-v0.12.0-alpha.52) · [Development notes](DEVLOG.md)

The package includes the plugin, BepInEx loader, Chinese usage notes and third-party license/source materials. No separate loader download is needed. The interface is Chinese.

## Included features

- **New in alpha.52:** one click adds 95 native best-quality permanent attribute pills, 100 of each (9,500 total), including speed, combat stats, eight roots, cultivation efficiency, dantian, mind, luck and lifespan. Blood-evil pills are excluded. It adds inventory only; it does not consume pills or change tolerance. Ordinary-only and temporary recovery pills are excluded. The single-item amount does not affect the batch; each click adds another full set.

- Search and add items by category and grade. Add a standard breakthrough bundle: 18 items across 10 types, excluding blood-path pills; it does not consume items or trigger a breakthrough.
- Set the amount of spirit stones to add or remove, from 1 to 100,000,000 per operation. Adjust character attributes and alchemy, talisman or crafting experience/levels.
- Find NPC locations, adjust affinity, teleport to an NPC on the same map, reveal current-map fog, and use Left Alt + left click to teleport on supported ordinary maps.
- Expand dantian space and technique slots; import/export layouts, learn missing entries, match preset fusion traits, equip the planned layout and spell bars, or delete individual presets.
- Assist combat with a configured action order and recover HP during the protagonist's idle turn. Native energy, cooldown and usage limits remain.
- Generate crafting reference recipes based on an item's role. This does not directly create customized equipment.

## Install and use

1. Save and exit the game. Back up saves and existing mods.
2. Extract the full package beside `Zaohua.exe`, so `BepInEx` sits in the same directory. If another loader or `winhttp.dll` already exists, check compatibility before replacing it.
3. Load a character, stop movement and close other game panels. Press the backquote key (U+0060, left of 1 / below Esc, without Shift) to toggle the menu. The menu key is customizable.

Save normally after changes. Save before applying a layout: layout backups cannot undo every learning, fusion or attribute change. If an action reports an uncertain result, inspect the actual state before retrying. To remove only this plugin, exit the game and remove `BepInEx/plugins/ZaohuaTrainer`; keep a loader used by other mods.

## Evidence and scope

Reference environment: Steam Windows x64 build **25847133**, BepInEx **6.0.0-be.788+5b766a3**. The alpha.52 candidate was compiled against the actual reference assemblies: 146 inputs matched. Thirteen new batch checks and nine existing breakthrough checks passed offline. Packaging reuses that exact binary without rebuilding it. Package identities were checked; actual alpha.52 game effects, Unity/menu lifecycle, normal restart and save/reload remain unverified. Other versions and mod combinations are unverified.

Personal research archive, provided as-is. No compatibility or outcome guarantee, issue intake, user support or continuing maintenance commitment.

The trainer implementation source is not included in this publication. GitHub's automatic “Source code” downloads are repository snapshots, not the installation package. The bundled dependency source archives remain separate from the trainer and retain their own licenses.

## File identity and licenses

- ZIP: `ZaohuaTrainer-v0.12.0-alpha.52-full-win64.zip` — 2,336,336 bytes
- ZIP SHA256: `9b882b2e9a22652136e1d387c677070c0e5fbdb3c6dcf75d97103a02f3d3ca71`
- Plugin SHA256: `8c9ade1d274afaf5945d40c8630c247c06afa302af986c9ff437a58b40d5dffa`

Preserve the complete `ThirdParty` directory, including notices, licenses, sources and replacement/build notes. BepInEx, UnityDoorstop and their dependencies retain their upstream rights; archive terms do not restrict those licenses or grant rights over game files. Developed with Codex assistance.

[Archive terms](../../TERMS.md) · [Third-party notices](../../THIRD_PARTY_NOTICES.md) · [Project index](../../README.md)
