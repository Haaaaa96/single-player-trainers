English | [简体中文](README_ZH.md)

# RiseAloneTrainer V1.8.2 · 重生2我独自逆袭

An in-game plugin for the Windows x64 Steam build 26669300. V1.8.2 fixes a silent black screen during automatic story transitions with unlimited choice time enabled.

[Complete Windows package](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-win64.7z) · [Release](https://github.com/Haaaaa96/single-player-trainers/releases/tag/rise-alone-v1.8.2) · [Development notes](DEVLOG.md) · [Source and build](../../sources/rise-alone/README.md)

## Features

- Edit ten player values including money, action points and starting or current combat technique points. Fourteen characters have editable affinity. Eleven other values cover the younger sister, the potted plant and Mr. Zhao's approval.
- Seven switches control action-point spending, zero stress, maximum affinity on interaction, minigame assistance, choice recovery, unlimited choice time and map labels for undiscovered locations you can currently enter.
- Choice hints show known effects and task interruptions. The recommendation prioritizes original affinity gains and ignores action points. Enable choice recovery before making the choice. Restoring it rolls back subsequent progress.

## Installation

1. Exit the game. In Steam, open **Manage → Browse local files**. Extract the 7z there once, with `winhttp.dll` beside the game executable. BepInEx 6.0.0-be.793, its runtime and Unity reference libraries are included.
2. Launch through Steam and load a save. Press the backtick key below Esc to toggle the panel. The first launch generates local game interfaces.
3. Click **保存设置** to retain the seven switches across saves and restarts. Save character and story progress through the game.
4. With an existing compatible BepInEx IL2CPP x64 installation, update only `BepInEx/plugins/RiseAlonePlugin.dll` to keep custom loader settings. Exit the game and move that DLL out to disable the trainer.

[Player values](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-01-stats.png) · [Assistance and choice recovery](https://github.com/Haaaaa96/single-player-trainers/releases/download/rise-alone-v1.8.2/RiseAloneTrainer-v1.8.2-02-assists.png). Both previews use the V1.8.2 menu with sample values.
