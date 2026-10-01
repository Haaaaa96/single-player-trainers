# House of Legacy v0.3.0 — Guide

**English** | [简体中文](GUIDE_ZH.md)

[Overview](README.md) · [Development notes](DEVLOG.md) · [Terms](../../TERMS.md)

Historical reference: 2026-10-01, game V0.9.03 / Steam Build 22970665, Windows x64, Unity Mono and BepInEx 5.4.23.5. The ZIP contains HouseOfLegacyTrainer.dll (internal version 0.3.0.0) and README-v0.3.0.txt. It contains no game, save, loader, personal configuration or logs; .NET SDK and Python are not required to use it.

## Install or update

1. Save and exit the game normally. Back up the whole save directory, commonly %USERPROFILE%/AppData/LocalLow/S3Studio/House of Legacy; do not back up only GameData.es3.
2. In Steam, use Manage → Browse local files to locate House of Legacy.exe.
3. If needed, extract [BepInEx_win_x64_5.4.23.5.zip](https://github.com/BepInEx/BepInEx/releases/tag/v5.4.23.5) beside the game EXE, with BepInEx, winhttp.dll and doorstop_config.ini at that level. Do not choose x86, IL2CPP or BepInEx 6. Check any existing MOD loader before replacing files; preserve its files and licenses.
4. Place HouseOfLegacyTrainer.dll in BepInEx/plugins/HouseOfLegacyTrainer. For an update, back up the previous DLL and configuration outside the game directory, then replace that DLL. Do not leave duplicate versions under plugins.
5. Start the game, load a save and press Tab during normal play or on the original character page.

A protected installation directory may require Windows authorization to copy files. Check the actual destination; do not change broad directory permissions or force routine game sessions to run as administrator.

## Use

Opening the plugin pauses the game. Choose a page, refresh, and check the selected character's name, ID, current value and input meaning before applying. The original character page refreshes if it still shows the same character and identity checks pass; otherwise reopen that page to confirm.

Press Tab or “关闭” (Close), then release the keyboard and mouse. Closing restores the prior run/pause state and speed. Save through the game to keep a change. Closing or disabling the plugin does not undo changes, and it does not save automatically.

The default left-side layout was checked at 1280×720 and 1920×1080; overflow can be scrolled. Title-bar dragging did not move the window in the recorded automated check, and manual dragging remains unconfirmed. Tab also closes the window inside text fields; select fields with the mouse. While open, the plugin isolates game clicks, scrolling and shortcuts. Switching away closes it and restores the earlier state; release held keys before reopening after switching back.

## Inputs: 14 one-time operations

| Operation | Input |
| --- | --- |
| Money | Nonzero integer change, −1,000,000 to 1,000,000; resulting balance cannot be negative |
| Family reputation | Amount to add, from 1 to the displayed remaining reputation for this level; at most one level per operation, with game funding and upgrade conditions retained |
| Literary, martial, business and artistic talent; renown | Target 0–100; decimals allowed |
| Mood | Integer target −100–100 |
| Health | Integer target 1–100; not a cure, lifespan extension or immortality |
| Charm and scheming | Integer target 0–100 |
| Stamina | One-time restore button; target depends on age and current state |
| Remaining creation trait points | Integer target 0–1000, only on the trait-selection page; choose traits and confirm the character through the game |
| Already-owned vegetables | Add 1–1000, within remaining storage capacity; quantity and available capacity change together |

Attributes apply to the selected member of the player's family. Creation points do not edit existing characters' traits; vegetables cannot create an unowned item. A target replaces the value; a money input is a change. Some game attribute displays round down. The top money/reputation display may update only after closing and resuming; check readback before submitting again.

Refresh after applying, changing saves/characters/scenes, data changes or a long wait. Wait for loading, saving, scene changes and transactions to finish. If a result is uncertain, inspect it rather than repeating the operation. These controls do not lock values; growth, consumption and events continue.

## Keys, disabling and rollback

After exiting, edit ToggleKey in BepInEx/config/local.houseoflegacy.trainer.cfg; it applies on the next launch. Old default F8 configurations migrate to Tab, other custom keys remain, and HotkeySchema needs no manual change. The game also uses Tab for construction/edit mode; rebind that game action or the plugin as needed.

To disable, exit normally and move the whole BepInEx/plugins/HouseOfLegacyTrainer folder outside the game directory. Renaming it inside plugins is insufficient. Move it back to restore the plugin. To roll back, restore the earlier DLL and matching configuration after exit; v0.2.0 used Esc followed by F8. Rolling back a plugin does not undo saved progress. Never replace a DLL while the game is running or remove other MODs/the entire loader.

If no window appears, check loader version, DLL location, scene and configured key. BepInEx/LogOutput.log records loading and rejection reasons; look for HouseOfLegacyTrainer 0.3.0. If the loader generated no configuration/log, check the loader before copying the plugin again. Do not install duplicate copies from different packages.

The [development notes](DEVLOG.md) separate historical checks from unverified fields, state boundaries and MOD combinations. Version/file differences alone are reminders; incompatible structures or failed input protection stop relevant operations.

## Licensing

The independently written plugin references game/BepInEx components at runtime and embeds no third-party DLLs. Preserve each dependency's original license.
