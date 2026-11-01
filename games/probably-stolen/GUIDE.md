English | [简体中文](GUIDE_ZH.md)

# V1.9.8 installation and use

[Project overview](README.md) · [Development notes](DEVLOG.md)

## Install or upgrade

1. Save normally and **fully exit the game**. Back up the save beforehand.
2. Extract the ZIP and merge its `Mods` folder into the game installation directory. Replace matching files when upgrading; **local V1.3 or later versions can be upgraded in place without uninstalling**.
3. Check this path:

   ```text
   <game directory>/Mods/ProbablyStolenTrainer/ProbablyStolenTrainer.dll
   <game directory>/Mods/ProbablyStolenTrainer/manifest.xml
   ```

4. Enable the trainer in the game's native MOD menu and restart when prompted.
5. Load a shop save and press **F4**. F4 toggles the menu; Esc also closes it. The hotkey can be changed and is saved between sessions.

No extra loader or framework is needed. Avoid `Mods/Mods` nesting and duplicate old trainer folders inside `Mods`; keep any backup outside that folder. The release ZIP contains the DLL, `manifest.xml` and `README-v1.9.8.txt`.

To uninstall, fully exit the game and delete **only** `<game directory>/Mods/ProbablyStolenTrainer`. Do not delete the entire `Mods` folder or game saves. Reinstall by extracting the package again. Uninstalling does not undo cash, items or other changes already saved.

## Local package and Workshop

Use one distribution at a time. Unsubscribe from this trainer's Workshop item when using the local package. To switch to Workshop, save and fully exit the game, move the entire local `Mods/ProbablyStolenTrainer` folder outside `Mods`, then subscribe. A local copy with the same MOD ID can shadow the Workshop copy; disabling it alone is insufficient. Preserve `ModData/ProbablyStolenTrainer` under the save location to keep hotkeys, favourites and alert settings. Enable the MOD again if the game requests it.

## Common controls and quantities

Choose the target and parameters, then press the relevant action button to execute. Internal checks run automatically; target selection, filtering and typing do not execute changes. Goods must still be selected, manually or with automatic selection; the final trade remains manual.

Hotkeys pause during text entry. With a Chinese input method, confirm the candidate text first, then press Enter to search. Enter in a search field only searches. Save normally by sleeping after operations; the trainer does not save automatically.

- Catalogue entries follow the current loaded registry and the game's native hidden-item rules. An unavailable entry shows a reason. Being addable does not imply it can also be maintained or deleted.
- Reference unit value excludes event and retail markups. Actual trade prices are set by the game. Size means occupied cells in the real item shape; unknown values sort last.
- Addition counts default packages, which may contain multiple inventory units. A restock shortage smaller than one package is filled with one package. Insufficient capacity stops the operation and reports the result.
- Favourite presets are shared across saves; current stock is counted in the active save.
- Deletion removes all units of the selected instance, gives no refund and has no undo within the trainer. Maintenance applies to owned shop items; charging observes power outages and native battery restrictions.

## Item attributes and maintenance

In inventory management, select an owned item, choose durability, armour or charge, enter the final current value and limit, and apply. The list identifies real supported attributes and offers an attribute-only filter. One-click repair and recharge remain available. Supported storage and unlocked installed accessories use the same ownership checks.

The current value must be between zero and its limit; the limit is 1–21,474,836, with further restrictions from armour efficiency and native battery valuation. Raising ordinary durability above its base limit also raises that base and displayed durability. Armour keeps its base value, and depleted 0/0 armour can receive a new limit. Battery capacity does not change output bandwidth or automatic charging speed. Custom charge editing does not require shop power; one-click recharge still checks power.

Only attributes actually present on the item are editable. UV filters have no ordinary durability; one-use power sources, converters and hypertech batteries use different mechanisms. Locked, working or trade-area items are rejected. Native item callbacks may later recalculate values; this feature does not freeze them.

## Water

Six water qualities are available in 250, 450, 750, 2000 and 6000 ml containers. Each generated unit is one full container. Restocking counts actual water quality and full-container size; half-full bottles do not count, and labels do not change the real quality.

Existing-bottle operations keep the container. Filling mixes with its contents; replacement empties it before adding the selected quality and final volume. Emptying and disposal lose the corresponding liquid. Transfer stops at a full destination or empty source. Purification to basic water retains volume and does not downgrade water already at that quality or above. Water tanks, storage tanks, filtering containers, alcohol and medicinal liquids are outside these existing-bottle operations.

## Machine assembly

Both modes support 24 registered machine/device profiles with their actual slots. **Basic completion** supplies missing eligible parts while preserving existing parts. **Recommended strongest setup** chooses a machine-specific configuration, adds eligible ordinary modules and expands supported standard compartments. Batteries, tanks, filters and cores are handled only where the native device exposes those slots. Neural cores remain opt-in.

Replaced parts and their contents return to inventory; leave enough free space. The advanced booster, hypertech booster and Aug scanner now accept battery completion through both modes. Water-device assembly accepts omitted zero-valued liquid components in existing containers; capacity, invalid values, locking, ownership and space checks remain.

These setups do not claim a global optimum, the largest part count or every cell filled. Native space, adjacency, air, container capacity, ingredients and attribute caps still apply. Neither mode starts machines or advances production. If safe values or effects cannot be established, the operation stops with a reason. If the result is marked uncertain, inspect the native parts compartment before another action; do not repeatedly click.

## Customer orders and alerts

Use order preparation after a buying or trading customer reaches the counter and their dialogue ends. Automatic selection considers all matching stock, irrespective of current filters or pages, and selects at most 100 items. Adjust the selection manually if needed. Items move as whole items/stacks without splitting or merging; existing counter goods remain. Lack of space or a dialogue trigger stops movement.

Native inspection still occurs when goods reach the counter and may reveal traits or affect reputation. Reference value is neither the final price nor the customer's budget. Quoting, bargaining and completing the trade stay in the game.

Unusual-person alerts display supported markers only. They continue with the trainer window closed, wait for native notices to finish, and report the same category once per visit. They do not change scan/wanted states, report or arrest anyone, or advance dialogue. An absence of supported markers is not a statement about every possible story event.
