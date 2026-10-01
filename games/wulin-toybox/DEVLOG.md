# Wulin ToyBox — Development notes

**English** | [简体中文](DEVLOG_ZH.md)

[Overview](README.md) · [Source](../../sources/wulin-toybox) · [Build](../../sources/wulin-toybox/BUILD.md) · [Terms](../../TERMS.md)

Summary of the v1.1.0 record dated 2026-09-30. This revision builds on HaxxToyBox and the referenced integration environment; original attribution remains in [Licensing](README.md#licensing). The sanitized source needs local game/prerequisite assemblies. This preparation did not build or run it and does not claim exact equivalence with the archived DLL.

## Revision focus

- Restore character names, portraits and attributes, with 31 displayed information fields and current-party selection.
- Repair item search across categories and quantity-based addition; complete talent search/add/remove with duplicate prevention.
- Make long martial-art lists scrollable and keep upgrade controls accessible, with ordering and forgetting controls.
- Adjust Chinese fonts, size and prompts; correct short key-press capture and Esc cancellation.
- Add confirmation before permanent achievement unlocking while retaining the existing achievement options.

## Historical evidence and limits

The recorded revision checks focused on protagonist attributes, search, talents, martial-art UI and assistance switches. Eleven ordinary martial arts displayed and upgraded normally. Time pause, random-encounter suppression and one ordinary encounter's protagonist post-battle recovery were checked.

Teammate handling, gifting and ability-experience multipliers had earlier normal-use reports; they were not presented as the same revision's full regression coverage. Permanent achievement unlocking was not executed. Encounter suppression does not establish that every scripted battle can be bypassed. Other game versions, operating systems and MOD combinations were not exhaustively checked.

Slow startup remained unresolved. The archive retains a plugin-only boundary; martial-art limit expansion still depends on EnhanceGameplay. The existing records concern an in-game plugin, not external native-host reuse. This source/documentation preparation added no game or lifecycle tests.
