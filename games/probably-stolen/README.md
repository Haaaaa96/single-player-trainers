English | [简体中文](README_ZH.md)

# Probably Stolen Multi-function Trainer V1.10.3

A personal development and research archive for the native MOD for **Probably Stolen** (深空当铺：可能是偷的). This release contains the trainer binary and documentation; implementation source is not included.

[Release and ZIP](https://github.com/Haaaaa96/single-player-trainers/releases/tag/probably-stolen-v1.10.3) · [Installation and use](GUIDE.md) · [Development notes](DEVLOG.md)

- Version: **V1.10.3**, build `1.10.3-20261103a`, dated 2026-11-03.
- Reference game: Steam build `26337366`.
- Uses the game's native MOD interface. No additional loader or framework is required.
- Default menu key: **F4**, configurable and saved between sessions; **Esc** also closes the menu.

## Features

1. **Cash:** add 1–10,000,000 credits per operation.
2. **Item catalogue:** display the loaded catalogue immediately, with categories, keyword/Enter search and paging. Show reference unit value and occupied grid cells; sort either value or size in both directions. Add 1–100 default packages at a time.
3. **Target restocking:** fill the shortage up to a chosen package count; do not add more when the target is already met.
4. **Favourite presets:** save up to 12 items and target quantities, with individual or batch restocking.
5. **Identification assistance:** inspect real traits, stolen status and contraband information on hover without directly changing their revealed state.
6. **Item maintenance:** edit current durability, armour or battery charge and their limits on eligible owned items, including supported installed accessories; retain one-click repair and recharge.
7. **Trade assistance:** estimate bargaining risk, restore a current appraisal customer's remaining patience before it is exhausted, and inspect or selectively reveal eligible counter-item traits.
8. **Inventory deletion:** remove an entire selected stack of ordinary owned items in the main or rear inventory. Containers, special callbacks and hazardous waste are excluded.
9. **Water management:** six water qualities and five container sizes; generation, restocking and favourites, plus inspection, filling, replacement, emptying, measured disposal, purification, transfer and label correction.
10. **Machine assembly:** 24 machine/device profiles, using their real battery, module, tank, filter and core slots. Generate and install missing parts. Basic completion preserves existing parts; the recommended strongest setup selects machine-specific enhancements, adds eligible non-negative ordinary modules, expands standard compartments and returns replaced parts to inventory. Neural cores are optional and off by default.
11. **Customer order preparation:** find matching owned stock, including goods in ordinary storage slots. Select manually or by high/low reference value, then move whole items or stacks to the purchase area. **Final trading remains manual.**
12. **Unusual-person alerts:** show supported wanted, concealed-wanted and Aug markers, including disguises. Ordinary merchant identities are not alerts. Automatic notifications can be disabled.
13. **Custom hotkey:** choose a key or Ctrl/Alt/Shift combination, save it, or restore F4.

14. **Gun loadout:** select an owned gun and generate/install recommended compatible parts in one action. Covers six moddable gun types and 31 compatible attachments, preserves existing parts with an equal or better combined score, and returns replaced parts with their contents to the main inventory.

15. **Automatic new-item assembly:** newly generated supported machines, guns, water pitchers and modular backpacks receive their recommended attachments during addition, restocking and favourite presets. Only the new instances are assembled; existing stock stays unchanged.

16. **Counter-item risk alerts:** continuously inspect both trade-counter sides, including contained items and installed parts, for supported counterfeit and quality defects. Read real traits without revealing them or changing prices or trades. A separate saved toggle is available on the identification-assistance page.

17. **Customer service guns:** a separate section on the gun-loadout page generates compatible parts for the current service order. Prioritize required conditions, then bonuses and legal empty-slot filling; preserve existing attachments and ownership. Final delivery remains manual.

## Cumulative changes since V1.3

Compared with V1.3, V1.10.3 adds: the expanded catalogue and value/size sorting; water management; machine assembly with basic completion and recommended setups; customer order preparation; unusual-person alerts; inventory deletion; recommended gun loadouts; automatic assembly of supported newly added items; continuous counter-item risk alerts; and order-based assembly of customer service guns.

Operations now run from their action button after the target and parameters are chosen. There is no mandatory preview/second-confirmation step. Internal identity, ownership, capacity and duplicate-operation checks remain. The V1.9.4 trade-reveal checks at execution time remain included.

## New in V1.10.3 (since V1.10.2)

- Separate **Customer service guns** from **Owned guns** on the gun-loadout page. The service section shows the current gun, ID and required/bonus conditions, independently of owned-gun search.
- Generate and install missing compatible attachments with one action. Required conditions take priority, followed by bonus conditions and legal slot filling. Existing parts stay installed, and the gun remains owned by the customer.
- Use the native condition comparisons and compatibility rules. Incompatible, locked or condition-breaking slots may remain empty; this is not a promise to fill every slot or find a global optimum.
- Bind the action to the current customer, order, gun and counter position; reject stale actions after those change. Report the actual result, then leave final delivery to the player. No automatic settlement, ammunition loading or base-quality change is added.

## Retained V1.10.2 changes

- Inspect the front and back trade counters every 0.5 seconds, including their containers and accessories. Warehouse, main-inventory and display storage outside these roots are excluded.
- Display the item, specific supported defect and source. Alerts continue with the trainer menu closed and clear when affected goods leave the counter; they share the existing noninteractive person-alert banner.
- Recognize 20 exact native feature/actual-condition combinations plus water mislabelling and poor-quality water, the native Ribwich counterfeit check, damaged hands and plasma-battery casing defects. Ordinary second-hand/opened goods and correctly labelled ghost water are not flagged solely for those properties.
- Keep a separate, saved item-alert toggle under identification assistance. This reads unrevealed real traits without exposing them, modifying item/price/trade state or completing a sale. Unknown or truncated data remains uncertain; no alert does not certify authenticity.

## Retained V1.10.1 changes

- Automatically apply recommended attachments to newly generated supported items during ordinary addition, target restocking and favourite presets. Complete one new item before creating the next; existing inventory is not modified by restocking.
- Include 34 conditional plans: 24 machine/tool profiles, six moddable gun types, the water pitcher with an advanced self-repairing filter, and three modular backpacks with large general-purpose pouches. Plans require current catalogue registration, verified slots and native compatibility; this is not a claim that every plan is present in every game session.
- Fix normal guns being rejected as having a changed eight-slot structure. The reader now unwraps the native grid/intake layers before checking the actual slots.
- Assemble owned guns in place across 16 verified inventory entry points and their owned nested contents, including compatible installed positions. The gun no longer has to be moved into ordinary grid inventory.
- A gun in the purchase area must wait until the active customer trade ends because attachment changes invoke native trade callbacks. The owned-gun action still rejects customer/service-order guns, true locks and insufficient space; V1.10.3 handles the current service gun in its separate order section.
- Keep one recommended gun action, existing machine basic completion and automatic internal checks. No extra confirmation, forbidden neural cores by default, ammunition loading, firing or automatic final trade is added.

## Retained V1.10.0 features

- The owned-gun workflow remains **Gun loadout → select an owned gun → apply recommended loadout**. Compare firepower, style, reliability, recoil control, ergonomics and accuracy together, without claiming every attribute is individually maximal.
- Preserve existing parts with an equal or better combined score and return replaced parts with their contents to the main inventory.
- Pistols have no compatible stock and shotguns have no compatible magazine, so those positions remain empty.

## Retained V1.9.9 changes

- Fix menu hotkeys remaining blocked after a game editor leaves a stale typing flag. Default F4 and saved custom keys use the same corrected input checks.
- Continue pausing hotkeys while an active text field, IME composition, console input or native key capture needs the keyboard.
- Clear only the trainer window’s own focus when it closes, and handle the toggle before automatic refresh so queued searches or refresh errors cannot swallow that toggle.
- Keep all V1.9.8 features and existing hotkey settings. The recorded 73 checks are offline results; in-game input and restart acceptance remain pending.

## Retained V1.9.8 changes

- Edit durability, armour, battery charge and their limits from the inventory-management page; repair and recharge buttons remain available.
- Fix assembly rejection for water collectors and related water devices when an existing container omits a zero-valued liquid component. Basic completion and recommended setup both have offline regression coverage.
- Add battery assembly for the advanced booster, hypertech booster and Aug scanner, bringing the supported profile count to 24.
- Include the V1.9.7 new-save recognition fix, plus the intervening shoplifter order-preparation and device/installed-accessory updates. Existing saves do not need to be deleted or restarted.

## Installation and boundaries

Save normally and fully exit the game, then merge the ZIP's `Mods` folder into the game directory. Existing local V1.3 or later installations can be overwritten directly without uninstalling first. Use either the local package or the Workshop version; remove the local copy from `Mods` before switching to Workshop. Enable the MOD in the native MOD menu and restart as prompted. See the [guide](GUIDE.md) for exact paths, removal and operation limits.

The final build passed the recorded static and offline checks. Package revision r2 repackages a wording-only change to the bundled README. The DLL and manifest are unchanged; version V1.10.3 and build `1.10.3-20261103a` are retained. No new gameplay testing is claimed. Actual UI behaviour, gameplay effects, normal restart and save/reload for this build remain for the author to check in game. See the [development notes](DEVLOG.md) for the distinction between these results.

This archive records personal experiments and versioned results. It does not promise compatibility with other computers, game versions, saves or MOD combinations, or ongoing support, fixes or updates. Use is at your own discretion and risk. The package contains no game assemblies or assets; game names and associated marks belong to their respective rights holders.
