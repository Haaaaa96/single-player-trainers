English | [简体中文](THIRD_PARTY_NOTICES_ZH.md)

# Third-party notices

The archive terms do not replace third-party licenses. Required copyright, author and license records are preserved without adding an acknowledgements or contact section.

## World Apart

The historical artifact uses Python 3.14.7, Frida 17.7.3, PyInstaller 6.22.3 and their dependencies.

- [Component records](third_party/THIRD_PARTY_NOTICES.md)
- [License notices](third_party/notices/) and [direct component licenses](third_party/licenses/)
- [Dependency rebuilding and replacement notes](third_party/REBUILD.md)
- [Pinned sources and hashes](third_party/sources-lock.json)
- [Corresponding dependency source archive](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new)

Dependency sources and the trainer implementation are separate materials; publishing them does not grant redistribution rights over game assets.

## House of Legacy

The plugin artifact contains the DLL and operating notes, not game code or the BepInEx loader. The public implementation needs local reference assemblies. [BepInEx](https://github.com/BepInEx/BepInEx) and its components retain their upstream licenses.

## WulinToyBox

HaxxToyBox is derived from Haxx / neeetman's [WuLinToyBoxMod](https://github.com/neeetman/WuLinToyBoxMod), under Apache-2.0. [License](games/wulin-toybox/LICENSE.txt) · [Notice](games/wulin-toybox/NOTICE.txt).

The earlier integration referenced masterZP.'s package and the EnhanceGameplay module attributed to 630444540 / gmhaxx. Those dependencies are not made part of the HaxxToyBox license. The public plugin package does not redistribute the loader, EnhanceGameplay, UniverseLib or Unity game libraries. Exact prerequisites remain in the [project notes](games/wulin-toybox/GUIDE.md).

The helper tools under `third_party/` retain their [existing MIT license](third_party/TOOL_LICENSE.txt); this is not a blanket license for all trainer source.
