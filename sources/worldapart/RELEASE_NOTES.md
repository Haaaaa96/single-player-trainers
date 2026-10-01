# WorldApartTrainer v1.3 research snapshot

English | [简体中文](RELEASE_NOTES_ZH.md)

This source records the v1.3 `read-performance-1` research stage, with a reference
environment of Windows x64 and Steam build 25617557. It covers character values,
inventory and currency, runtime resources, learning and meridian interactions,
alchemy/crafting, dual cultivation, jade, persuasion and photostone workflows.

The reading optimization stage targeted first reads of character aptitude,
learning state and photostone data. Archived validation separated read-only
results, offline guards and previous user observations; it did not establish every
live write, settlement, save/reload or fresh broker startup in that stage.

This public copy omits two game-derived configuration resources and removes old
personal display labels. It is not a complete runnable distribution. See
[source and build boundaries](BUILD.md) before interpreting the code or tests.

Game build and file differences are warnings; actual object identity, field types,
method signatures and operation conditions determine whether an action is allowed.
Do not bypass guards or retry an operation whose dispatch/result is uncertain.
Back up saves before any later authorized live experiment.

Third-party component notices and complete license texts are retained. This is a
personal research archive without adaptation, maintenance or troubleshooting commitments.
