English | [简体中文](README_ZH.md)

# Probably Stolen Multi-function Trainer V1.9.4

A personal development and research archive for the native MOD for **Probably Stolen** (深空当铺：可能是偷的). This release contains the trainer binary and documentation; implementation source is not included.

[Release and ZIP](https://github.com/Haaaaa96/single-player-trainers/releases/tag/probably-stolen-v1.9.4) · [Installation and use](GUIDE.md) · [Development notes](DEVLOG.md)

- Version: **V1.9.4**, build `1.9.4-20261030a`, dated 2026-10-30.
- Reference game: Steam build `26284217` (2026-10-29).
- Uses the game's native MOD interface. No additional loader or framework is required.
- Default menu key: **F4**, configurable and saved between sessions; **Esc** also closes the menu.

## Features

1. **Cash:** add 1–10,000,000 credits per operation.
2. **Item catalogue:** display the loaded catalogue immediately, with categories, keyword/Enter search and paging. Show reference unit value and occupied grid cells; sort either value or size in both directions. Add 1–100 default packages at a time.
3. **Target restocking:** fill the shortage up to a chosen package count; do not add more when the target is already met.
4. **Favourite presets:** save up to 12 items and target quantities, with individual or batch restocking.
5. **Identification assistance:** inspect real traits, stolen status and contraband information on hover without directly changing their revealed state.
6. **Item maintenance:** restore durability and armour on owned items, and charge eligible rechargeable batteries while retaining their current limits.
7. **Trade assistance:** estimate bargaining risk, restore a current appraisal customer's remaining patience before it is exhausted, and inspect or selectively reveal eligible counter-item traits.
8. **Inventory deletion:** remove an entire selected stack of ordinary owned items in the main or rear inventory. Containers, special callbacks and hazardous waste are excluded.
9. **Water management:** six water qualities and five container sizes; generation, restocking and favourites, plus inspection, filling, replacement, emptying, measured disposal, purification, transfer and label correction.
10. **Machine assembly:** generate and install missing parts. Basic completion preserves existing parts; the recommended strongest setup selects machine-specific enhancements, adds eligible non-negative ordinary modules, expands standard compartments and returns replaced parts to inventory. Neural cores are optional and off by default.
11. **Customer order preparation:** find matching owned stock, including goods in ordinary storage slots. Select manually or by high/low reference value, then move whole items or stacks to the purchase area. **Final trading remains manual.**
12. **Unusual-person alerts:** show supported wanted, concealed-wanted and Aug markers, including disguises. Ordinary merchant identities are not alerts. Automatic notifications can be disabled.
13. **Custom hotkey:** choose a key or Ctrl/Alt/Shift combination, save it, or restore F4.

## Cumulative changes since V1.3

Compared with V1.3, V1.9.4 adds: the expanded catalogue and value/size sorting; water management; machine assembly with basic completion and recommended setups; customer order preparation; unusual-person alerts; and inventory deletion.

Operations now run from their action button after the target and parameters are chosen. There is no mandatory preview/second-confirmation step. Internal identity, ownership, capacity and duplicate-operation checks remain. V1.9.4 also refreshes trade-reveal checks at the moment of execution.

## Installation and boundaries

Save normally and fully exit the game, then merge the ZIP's `Mods` folder into the game directory. Existing V1.3 installations can be overwritten directly without uninstalling first. Enable the MOD in the native MOD menu and restart as prompted. See the [guide](GUIDE.md) for exact paths, removal and operation limits.

The final build passed the recorded static and offline checks and was installed while the game was closed. Actual UI behaviour, gameplay effects, normal restart and save/reload for this build remain for the author to check in game. See the [development notes](DEVLOG.md) for the distinction between these results.

This archive records personal experiments and versioned results. It does not promise compatibility with other computers, game versions, saves or MOD combinations, or ongoing support, fixes or updates. Use is at your own discretion and risk. The package contains no game assemblies or assets; game names and associated marks belong to their respective rights holders.
