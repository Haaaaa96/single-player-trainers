# Building HouseOfLegacyTrainer 0.3.0

English | [简体中文](BUILD_ZH.md)

This is a source snapshot for a personal research archive. No build, test, game launch, or runtime verification was performed for this export. Existing release binaries were not rebuilt.

## Requirements

- Windows x64 and PowerShell 7.
- A .NET SDK with the Roslyn compiler. The recorded build used .NET SDK 8.0.425.
- A locally installed copy of House of Legacy. Recorded reference: V0.9.03, Steam build 22970665, Unity 2020.1.14f1c1, Mono x64.
- An extracted official BepInEx 5.4.23.5 x64 Mono package. Its root must contain `BepInEx/core/BepInEx.dll`, `0Harmony.dll`, and `Mono.Cecil.dll`.

Game assemblies, the loader, and third-party binaries are not included. The compiler references the installed game's `House of Legacy_Data/Managed` files. Obtain prerequisites from their respective sources; an SDK is only a build dependency.

## Build

From this directory in PowerShell 7:

```powershell
./tools/Build.ps1 -GameDir 'X:/Games/HouseOfLegacy' -FrameworkDir 'X:/Tools/BepInEx-5.4.23.5' -Dotnet 'C:/Program Files/dotnet/dotnet.exe'
```

Replace example paths with actual local paths. Alternatively, set `HOUSE_OF_LEGACY_GAME_DIR` and `BEPINEX5_DIR`; `dotnet` is resolved from `PATH` unless `-Dotnet` is supplied. The selected SDK must expose `sdk/<version>/Roslyn/bincore/csc.dll` next to its `dotnet.exe` installation root.

Output: `bin/HouseOfLegacyTrainer.dll`. The script compiles locally and prints its SHA-256; it does not install or start the plugin. Path defaults were generalized for this export. The product sources remain unchanged from source commit `52932847bb241009d3b78d602c29b8078ee2bdcd`; no byte-identical rebuild is claimed.

## Available offline checks

Each command requires a fresh PowerShell 7 process:

```powershell
pwsh -NoProfile -File ./tests/Test-Guards.ps1
pwsh -NoProfile -File ./tests/Test-Inventory.ps1
```

These use bounded substitutes with the actual data-operation source. They do not load game assemblies or prove Unity UI, save persistence, or in-game behavior. They were not executed during this export.

## Scope

The plugin source was independently implemented. BepInEx, Harmony, Mono.Cecil, Unity, and the game retain their respective rights and terms. This source snapshot does not include or grant rights to their binaries. This export does not introduce a new license for the independently authored code.
