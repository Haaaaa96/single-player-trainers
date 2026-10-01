# WorldApartTrainer source and build notes

English | [简体中文](BUILD_ZH.md)

This is a privacy-edited research source snapshot dated 2026-10-02, based on the
v1.3 `read-performance-1` working tree. It includes the trainer implementation,
technical interface specifications, build scripts and offline regression sources.
The application UI remains in Chinese. This snapshot was **not built or run
against the game during this publication work**.

## Missing inputs and reproducibility

The snapshot intentionally omits these original resource files:

| Input | Why omitted | Effect |
| --- | --- | --- |
| `alchemy_specs.json` | Contains copied game talent configuration and localized descriptions as well as technical metadata. | Alchemy adapters/context and dependent tests cannot import it; application feature initialization can fail. |
| `photostone_catalog.json` | Contains extracted NPC, reward and interaction configuration. | Photostone adapter imports and dependent tests fail without it. |
| `engine_game_types.json` | Historical extracted type inventory is not part of this selected source set. | The legacy `game_runtime/probe.py` `classes` command is not self-contained. |

No empty substitute, fabricated data, generator or fallback has been added. The
PyInstaller spec still requires the real alchemy and photostone inputs and will
fail when they are absent. Full test discovery also reaches modules that require
those inputs. This checkout is therefore reviewable source, **not a complete,
one-command rebuild of the archived executable**. A complete build would require
the matching omitted inputs, obtained and used under appropriate rights, and
fresh validation. No game binaries, metadata dumps, asset bundles, saves, runtime
caches or private evidence logs are included.

The remaining JSON files record interface/type names, offsets, method signatures,
short instruction prefixes and authored validation rules. Their inclusion is
technical research evidence; it does not grant rights to the game's assets or
claim that game-derived identifiers belong to this project. Game-specific safety
checks and source hashes were retained, rather than replaced with placeholders.

## Historical artifact identity

The archived v1.3 `read-performance-1` executable has SHA256
`bed5bd18a201998c3c84811e7efa7eb412868b636ef04b8cc38d65b569d41f05`.
The source baseline was `db1d4009b38e55647dda6abc7894bf837a30e3a2` **plus uncommitted
working-tree changes**. That commit alone is not the final build source.
Before this export, all 85 product modules and 20 packaged resources matched the
per-file hashes in the local delivery record, and the archived EXE hash matched.

This public copy removes an old author label and local machine identifier,
generalizes the related privacy-test fixture, changes the default build interpreter
to `python` on PATH, and replaces the bundled prose with research archive notes.
Its source marker identifies a public snapshot. It does not match the archived
EXE byte for byte, and no rebuilt binary is provided by this source export.

## Environment and build entry points

- Windows x64. The historical build used Python 3.14.7 with Tkinter/Tcl/Tk.
- Python build packages are pinned in `requirements-build.txt`, including Frida
  17.7.3 and PyInstaller 6.22.3. `requirements-acquisition.txt` documents the same
  Frida version for a source-runtime installation.
- PowerShell 7 for the supplied scripts. `build_standalone.ps1 -Python <path>`
  accepts an explicit interpreter; its default resolves `python` from PATH.
- Node.js is needed only for the JavaScript contract tests; those tests use Node
  built-ins and have no npm dependency set. No exact Node version is pinned here.
- `build_tcl_resources.py` stages an installed Python distribution's Tcl/Tk zip
  resources when its virtual zipfs paths cannot be copied by the PyInstaller hook.

The original build entry point is `build_standalone.ps1`. It creates `.build-venv`,
installs the pinned requirements, invokes `WorldApartTrainer.spec`, and checks the
bundle with `verify_bundle.py`. It cannot finish from this incomplete snapshot.
`verify_standalone.ps1` starts a supplied EXE in an isolated offline self-test;
`verify_release_archive.py` inspects a supplied ZIP without running its EXE.

For independent offline checks that do not need the omitted resources, the source
contains these existing test modules. They were not rerun as functional tests in
this publication pass:

```powershell
python -m unittest test_write_guard test_runtime_paths test_build_tcl_resources test_verify_release_archive
```

These use synthetic fixtures or temporary files. They do not establish live game
behavior. The broader test sources are retained for review, including tests whose
imports depend on omitted resources; do not report full discovery as passing.

## Runtime and licensing boundaries

The reader uses Windows process APIs. Native actions use a shared Frida broker;
ordinary reads and availability checks must not silently inject a broker. Runtime
state belongs to the user's local application-data directory, and development
caches/logs are generated locally. Never publish these generated files.

The supplied third-party license texts and [component notice](THIRD_PARTY_NOTICES.md)
are preserved. Their required copyright attributions are not personal project
credits. The old `Launcher.cs` and development launcher EXE are omitted; they are
not part of the standalone PyInstaller build.

This archive records personal research. There is no promise of adaptation,
maintenance, troubleshooting or compatibility with other games, builds or mods.
