[English](DEVLOG.md) · [简体中文](DEVLOG_ZH.md)

# NX2naviTrainer v0.1.1 development record

The examined v0.6.1 runtime contained a cheat panel implementation that was unreachable from its stock pause menu. The local build adapter adds a menu entry and connects the trainer to the identified player update. The trainer checks the active player and scene, then reads back writes or the result of the inventory request. Maintaining health restores it to the current maximum on eligible updates and clears that setting when the player or scene identity changes.

The local catalog was generated from 395 registered game actors. Of those, 96 had the stock and capacity metadata required by the add-item path. Eligibility can change with inventory state and progression. The catalog and filters include records that cannot be added and explain the restriction. The observed catalog had 184 bilingual labels. Unknown values and slot counts sort after known values.

On an isolated test profile, local builds demonstrated healing from 2.75 to 3 hearts, the maintain-health toggle, rupees from 7 to 76, Deku Sticks from 2 to 10, and a Hylian Shield from 0 to 1. A save and restart confirmed representative persisted values. The Chinese build additionally verified readable menu text, Chinese Enter-to-search, and both success and full-stock feedback. Normal exit was exercised. Test environment was Windows 11 Pro x64 build 26200, Intel Core i7-13700K and GeForce RTX 4070 Ti.

The publication source recipe was built separately against the same local NX2navi 0.6.1 kit and game input with Python 3.14.7 and the kit's UCRT64 Clang 23.1.5. The resulting publication-check executable was not run. Runtime observations above refer to the local trainer builds. Individual add-item results for all 96 candidates, other game versions and other host builds remain unverified.
