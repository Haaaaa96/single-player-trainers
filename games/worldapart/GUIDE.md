# WorldApart Trainer v1.3 — Guide

**English** | [简体中文](GUIDE_ZH.md)

[Overview](README.md) · [Development notes](DEVLOG.md) · [Terms](../../TERMS.md)

Operating notes for the archived release, recorded on 2026-10-01 with Steam Build 25617557 on Windows x64. The ZIP contains WorldApartTrainer.exe and README-v1.3.txt. UI labels remain Chinese.

## Start

1. Back up the save. Start the game, load a save and wait for loading to finish.
2. Run WorldApartTrainer.exe and click “连接游戏” (Connect). Use automatic detection or select WorldApart.exe manually.
3. Select a page and read/refresh it before choosing a target and applying a value. Initial connection may take tens of seconds.
4. Check the result in the game. Save through the game if you want to keep it. Read again after loading, a breakthrough or a new activity round.

The release covers 54 modification functions in 18 modules: character growth and experience, inventory/currency, current resources, learning, meridians, speed, memory stones, persuasion, alchemy, forging, recipe exploration, dual cultivation and jade scraping. The checklist, character locations and route hints are additional readouts.

## Input meanings and limits

| Input | Meaning and boundary |
| --- | --- |
| “目标值” (target value) | The resulting value, not an increment |
| “新增数量” (quantity to add) | The amount added in this operation |
| Spirit stones | At most 100,000,000 added/subtracted per operation; total at most 999,999,999, or the lower game limit |
| Town/sect contribution | At most 1,000,000 added per operation |
| Ordinary items | At most 999 added per operation; some individual items are limited to 256; stacks still follow game limits |
| Character attributes | Growth bonuses, not the final displayed totals |
| Five aptitude/skill values | Cumulative experience |
| Health, spiritual energy, stamina | Current values, without a persistent lock |
| Lifespan | Added lifespan only; age is not edited |

For example, setting a stack quantity to 20 produces 20 items; adding 20 produces 20 additional items. Other limits appear on the relevant page. Inputs above a supported limit are rejected.

## Activity notes

- **Alchemy:** add ingredients normally, then add spiritual energy when the game asks. Read and use assistance after fire control starts. Maximum heat assistance does not remove pill toxicity.
- **Memory stones:** return to a stable normal scene, refresh the list and select a stage. Activation and “强制开启 / 重玩…” (Force open / Replay) are above the list. After activation, interact with the relevant character and satisfy the remaining prerequisites and stamina requirements.
- **Forced replay:** review and confirm the dialog. It clears the selected stage's success record; failure, exit or not starting does not restore it automatically. Later content may be affected, and success may award rewards again.
- **Persuasion:** enter the round normally and wait for AI responses or other processing before reading. After success is set, wait for the game's countdown and settlement.
- **Technique learning:** filling the current round's comprehension still leaves settlement to the game. Inner demons are unchanged; a full inner-demon meter can take priority and cause failure.
- **Meridians:** wait for the board and animation to finish and close the exit confirmation before one-click completion. For manual resource editing, remain at the exit confirmation, apply the change, then cancel exiting.
- **Forging:** add ingredients normally and enter the board before reading. Affixes remain random. Close the minigame and talent pages before editing alchemy/forging talents.
- **Recipe exploration:** read when there is no recipe in the current round and the trajectory has stopped. It collects eligible recipes within the revealed area; it is not permanent unlocking.
- **Dual cultivation:** start the current round before reading.
- **Jade scraping:** release the mouse and wait for scratch processing to finish. Full reveal preserves natural quality and cracks and does not guarantee the exchange threshold.

## State changes and uncertain results

Use ordinary values/items only in a stable normal scene, away from combat, transitions and settlement. The game may autosave. Closing the trainer does not reset game speed; restore 1× first when needed.

For a disabled button, follow the page's scene requirements, wait for animations and refresh. Close and reopen a game panel if its display has not updated. If an operation reports an error or its result is unclear, inspect the game before repeating it.

If a message explicitly requires a restart, save normally and restart the game; do not delete records to bypass protection. Game-version or MOD-file differences alone do not reject a connection, but incompatible runtime structures stop affected operations. The reference build no longer shows the obsolete compatibility notice.
