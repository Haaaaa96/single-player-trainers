[English](BUILD.md) · [简体中文](BUILD_ZH.md)

# Build NX2naviTrainer v0.1.1

## Requirements

- [NX2navi v0.6.1 for Windows](https://github.com/tangerineturtle1/NX2navi/releases/tag/v0.6.1). Upstream specifies Windows 10/11 x64 with SSE4.2, 16 GB RAM, and Vulkan 1.3 with `VK_EXT_external_memory_host` and `VK_EXT_mesh_shader`. Upstream estimates about 30 GB for the game plus 1.5 GB for the launcher. Allow additional room for the retained cache and this build.
- Your own game dump of **The Legend of Zelda: Ocarina of Time for Nintendo Switch 2, v1.1.1**, Title ID `0400486024DEC000`, main NSO Build ID prefix `E0F3CCFAF50065AE`. The adapter checks the main NSO SHA-256 and the recorded guest layout.
- A completed game build from that launcher with the matching `app/0.6.1` build kit, UCRT64 toolchain and `game/build-cache` still present, including the lifted and generated sources, objects and `link.rsp`. The original ExeFS and RomFS extracted by the launcher must be available.
- Python 3.14 with `compression.zstd`. Verified with Python 3.14.7 and NX2navi's bundled UCRT64 Clang 23.1.5 for `x86_64-w64-windows-gnu`. Cheat Engine, REA and a separate emulator are not runtime dependencies.

## Build and install

Open PowerShell in this source directory. Obtain the pinned MIT-licensed catalog reference and build into a new or empty directory.

```powershell
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Traiver/OOT-SW2SE/de26f03d0a299e39e5536bf68eeef9b251fadba1/editor.html' -OutFile .\oot-sw2se-reference.html
py -3.14 .\build_candidate.py --catalog-reference .\oot-sw2se-reference.html --out .\trainer-build
```

The default install path is `%LOCALAPPDATA%\Programs\NX2navi` and the default game directory is `game` under it. Supply `--install-root` and `--game-dir` for custom paths. The script writes `trainer-build/ocarina.exe` and intermediates without modifying the installation.

1. Exit the game normally. Back up the original `ocarina.exe` and `game/profile` to a separate location.
2. Copy the locally built `ocarina.exe` into the existing NX2navi game directory. It uses that directory's runtime DLLs and game data.
3. Launch normally, load a save, and open **Esc → 金手指**. Select a feature and click its button to apply it. Press Enter in item search to filter without writing to inventory.
4. To restore the original build, exit the game and put back the backed-up `ocarina.exe`. A launcher rebuild can also replace the custom executable.

See the [upstream and third-party notices](THIRD_PARTY_NOTICES.md). The release supplies the patch recipe and trainer source. Prepare the game and upstream inputs locally and follow their applicable terms.
