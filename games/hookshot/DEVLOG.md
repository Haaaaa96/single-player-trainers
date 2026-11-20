English | [简体中文](DEVLOG_ZH.md)

# HookshotTrainer development record

| Date | Change and observed result |
|---|---|
| November 2026 | The Chinese panel grew from inventory editing into three tabs with quest guidance, map and dungeon navigation, flight, and magic controls. The host and Vulkan renderer use the same in-process trainer interface. |
| November 16, 2026 | A valid terrain compute shader exceeded the translator's original 1 MiB limit. The local repair uses the validated input length and the existing 16 MiB package ceiling. The headless preparation run on 0.2.24-dev processed 38,809 shader entries with zero failures. |
| November 17, 2026 | The 0.2.25-dev executable and renderer from build `6d5c41081406` were installed as a pair. Offline tests exercised protected bottles, queued operations, timeouts and repeated requests. The test harness simulated native dispatch and game memory. |

The final installed pair used trainer ABI 14 and renderer API 23. The installation check confirmed the protected saves and settings retained their hashes. Opening the final panel, removing a bottle in live gameplay, saving, reloading and restarting were still awaiting in-game verification in the recorded build.

[Project overview](README.md) · [Source](../../sources/hookshot/)
