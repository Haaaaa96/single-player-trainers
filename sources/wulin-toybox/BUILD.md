# Building WulinToyBox / HaxxToyBox 1.1.0

English | [简体中文](BUILD_ZH.md)

This is a source snapshot for a personal research archive. No build, test, game launch, or runtime verification was performed for this export. Existing release binaries were not rebuilt.

## Requirements

- Windows x64 and PowerShell 7 with `Microsoft.CodeAnalysis.dll` and `Microsoft.CodeAnalysis.CSharp.dll` under `$PSHOME`.
- A locally installed copy of 大侠立志传, using the `WulinSH` installation layout.
- The existing matching BepInEx IL2CPP environment, including populated `dotnet`, `BepInEx/core`, and `BepInEx/interop` directories, plus `BepInEx/plugins/HaxxToyBox/UniverseLib.IL2CPP.dll`.

Recorded game reference: V1.2.0818 75, Steam build 24794582. The historical environment used BepInEx 6.0.0-be.672 and .NET Runtime 6.0.7. This script consumes the installed reference assemblies; it does not download prerequisites, generate interop assemblies, or install a complete environment. Other combinations are unverified. Game/Unity DLLs, loaders, runtime libraries, generated caches, and other mods are excluded from this snapshot.

## Build

From this directory in PowerShell 7:

```powershell
./build.ps1 -GameDir 'X:/Games/WulinSH'
```

Replace the example path with the actual local installation, or set `WULIN_GAME_DIR`. Output: `build/HaxxToyBox.dll`. The script includes the upstream `src/Assets/toybox` resource, compiles the C# sources, and prints SHA-256; it does not install or start the plugin.

The game-directory default was generalized for this export. Product sources derive from source commit `f7a4f7b2d21fd8dbfcdd1b1a0ad09960c734da2d`. Modified upstream files carry an added neutral comment; see `NOTICE.txt` for the verified change list. Those public copies are no longer byte-identical to the historical sources. Executable statements remain unchanged, and no byte-identical rebuild is claimed.

## Available offline check

```powershell
pwsh -NoProfile -File ./tests/check-item-search.ps1
```

This only checks the search-text helper. It does not load the game, prove UI behavior, or validate saves. It was not executed during this export.

## Sources and rights

HaxxToyBox is derived from [neeetman/WuLinToyBoxMod](https://github.com/neeetman/WuLinToyBoxMod/tree/b2aee7a4be4c1254910ca1f13897d40853a5f20e), by Haxx. Keep `LICENSE.txt` and `NOTICE.txt`, including the upstream copyright text. `src/Assets/toybox` matches the corresponding upstream resource byte for byte; SHA-256: `746dada617bdb07933f77c79a7110156e232e4acc4af5c0ebf9e9c6ebd11eaf8`.

The Apache-2.0 license for HaxxToyBox does not license BepInEx, UniverseLib, EnhanceGameplay, Unity, the game, or other external dependencies. The complete historical environment is not redistributed here. The UI uses a locally installed Microsoft YaHei font; font files are not included.
