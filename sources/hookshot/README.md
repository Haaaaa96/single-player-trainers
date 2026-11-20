# HookshotTrainer 0.2.25-dev

[简体中文](README_ZH.md)

HookshotTrainer adds a Chinese-language panel to the Windows x64 build of Hookshot v2.3.1 for *The Legend of Zelda: Ocarina of Time*. It runs inside the game. The host EXE and Vulkan renderer DLL are built together. This research snapshot includes the 0.2.25 empty-bottle change and the earlier Vulkan fix for large compute shaders.

## In the game

Press the **backquote/grave key** (usually below Esc) to open or close the panel. In **道具** (Items), select **空瓶** (`Item_Bottle`), then **删除空瓶** to remove one empty bottle. A filled bottle, the letter bottle and a bottle assigned to a child or adult item slot are protected. If every empty bottle is assigned, change the assignment in the game first. The panel reports success after both the stock and ownership flags clear. A timed-out request is never resent automatically.

The panel also includes health, rupees, ammo, magic, inventory search, bottle filling, teleportation, flight, main-quest hints, a live map and guidance for the base game's dungeons. **F6** toggles flight. On one connected controller, hold **ZL + ZR + right-stick click** (Xbox **LT + RT + RS**) for half a second, then release all three before repeating. Master Quest dungeon guidance is outside this version's coverage.

## Build a local copy

Use **Windows x64**, **PowerShell 7+** and the **v2.3.1 Windows Builder toolkit**. Its bundled Python 3.14 includes `compression.zstd`. The build uses its LLVM-MinGW, CPM dependencies and the CPU-native profile-guided build settings. A source checkout alone does not contain those packages. The target upstream revision is [Hookshot 5d3de41](https://git.notrexed.dev/Hookshot/Hookshot/src/commit/5d3de413df5587a1896b2b7df6a3a385ae24195a). [Upstream releases](https://git.notrexed.dev/Hookshot/Hookshot/releases/tag/v2.3.1)

Supply your own extracted game files. The game directory must contain `romfs/` and `.hookshot_exefs/`, including the original `main` whose SHA-256 is `2591fb99008d0814f8056c3f36b36790048ed857ff0ae2bb3a4c1e37b960a4de`. It must include the Chinese and English message tables. The build generates all inventory, quest and map headers locally. Supply the exact HTML catalog separately. Its SHA-256 is `42d7777267e7959b958c8e6f8d1c247794bf0931ba2c3614628bbdc678e0de37`. [Traiver's pinned editor.html](https://raw.githubusercontent.com/Traiver/OOT-SW2SE/de26f03d0a299e39e5536bf68eeef9b251fadba1/editor.html)

Run the following from this source folder. The paths below are examples of sibling directories. Set them to the locations of your toolkit, game dump and catalog. Keep the toolkit copy separate from the Builder that manages your normal installation.

```powershell
$workspace = (Resolve-Path '..').Path
$builder = Join-Path $workspace 'HookshotBuilder'
$game = Join-Path $workspace 'GameDump'
$reference = Join-Path $workspace 'editor.html'
$stage = Join-Path $workspace 'HookshotBaseBuild'
$out = Join-Path $workspace 'HookshotTrainerBuild'
$tools = Join-Path $builder 'versions/v2.3.1/HookshotBuilder/tools'
$python = Join-Path $tools 'python/python.exe'
```

1. **Prepare a fresh retained build.** Place the complete upstream toolkit under `$tools`. Start with a dedicated Builder root with no `work-v2.3.1` and an unused stage directory. The command patches the Vulkan source in this toolkit, backs up the edits in the stage, and performs the full upstream native build with `HOOKSHOT_KEEP_BUILD_FILES=1`. This retains game and renderer objects, response files, generated code, both PGO profiles, original executable and renderer. Preparing shaders during this build is disabled. A complete build needs disk space for the game, stage and compiler intermediates. If you already have a matching, shader-patched retained build with those inputs, skip to step 2.

    ```powershell
    .\Prepare-Builder.ps1 -BuilderRoot $builder -Game $game -Stage $stage
    ```

2. **Build the trainer.** Choose an unused output directory outside the source, Builder and game trees. Keep the retained builder's optional libraries available. A builder compiled for DLSS needs the matching local NGX SDK under `$tools/ngx-sdk` or `HOOKSHOT_NGX_SDK`. If dav1d was enabled, keep the matching headers and static library in its CPM cache. A stock or incomplete Vulkan object set is rejected.

    ```powershell
    & $python -B -X utf8 .\trainer\build_candidate.py --builder-root $builder --game $game --reference $reference --out $out
    ```

3. **Use the pair locally.** After the build prints both SHA-256 hashes, close the game and back up the existing `bin/hookshot.exe`, `bin/hookshot_vk.dll` and saves. Install **both** new files under those same names in the matching Hookshot game's `bin` directory. Keep the other runtime files from the matching upstream build. Restore the previous pair together to roll back. An upstream Update can replace both files. A locally rebuilt pair has its own build identifier and may depend on the build machine's CPU.

## Verification and rights

The November 17 reference installation used build `6d5c41081406`, trainer ABI 14 and renderer API 23. This portable source snapshot was rebuilt against retained v2.3.1 inputs. All twelve generated headers, including the trainer core, matched the reference candidate byte for byte. Offline fixtures covered the empty-bottle state machine and the Vulkan shader size boundaries. The packaging check did not run the game. In-game inventory refresh, save/reload, restart and other systems or mod combinations have no compatibility guarantee.

Hookshot's upstream source uses GPLv3. Third-party components retain their own notices, licenses and trademarks. The inventory reference is from Traiver's OOT-SW2SE (MIT). The original trainer research also consulted the public player and pouch work in Hookshot-AllowGames. The source archive contains integration code, tests and build scripts. Game assets, the catalog HTML, SDKs, compilers, generated tables, local saves and linked binaries are supplied or generated locally. This is a personal research archive with no support commitment and no additional blanket license for independent original trainer code. [Hookshot GPLv3](notices/Hookshot-COPYING.txt) · [OOT-SW2SE license](notices/OOT-SW2SE-LICENSE.txt) · [Hookshot-AllowGames reference](https://github.com/AllGamersRD17/Hookshot-AllowGames/blob/95b9c20cffc4a92485bf9a84e0649c3cec027a8c/host/hos_main.c)
