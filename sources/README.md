English | [简体中文](README_ZH.md)

# Source snapshots

| Project | Implementation and build notes | Main boundary |
|---|---|---|
| World Apart | [Source](worldapart) · [Build](worldapart/BUILD.md) | Some game-derived inputs are intentionally omitted; read the exact list before attempting a build. |
| House of Legacy | [Source](house-of-legacy) · [Build](house-of-legacy/BUILD.md) | Requires local game and BepInEx assemblies, which are not redistributed here. |
| WulinToyBox | [Source](wulin-toybox) · [Build](wulin-toybox/BUILD.md) | Requires the original loader and generated interop dependencies; upstream Apache-2.0 notices remain. |

The export includes implementation files and selected existing tests. Tests are code for inspection, not evidence that all tests or game scenarios were rerun during this publication. Personal defaults were sanitized only in these copies. File manifests identify what is present; per-project build notes describe exclusions.

Original code without an explicit license has no newly granted open-source license. Third-party code keeps its existing terms; see [archive terms](../TERMS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).
