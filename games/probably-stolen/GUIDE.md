English | [简体中文](GUIDE_ZH.md)

# V1.9.4 installation and use

[Project overview](README.md) · [Development notes](DEVLOG.md)

## Install or upgrade

1. Save normally and **fully exit the game**. Back up the save beforehand.
2. Extract the ZIP and merge its `Mods` folder into the game installation directory. Replace matching files when upgrading; **V1.3 can be upgraded in place without uninstalling**.
3. Check this path:

   ```text
   <game directory>/Mods/ProbablyStolenTrainer/ProbablyStolenTrainer.dll
   <game directory>/Mods/ProbablyStolenTrainer/manifest.xml
   ```

4. Enable the trainer in the game's native MOD menu and restart when prompted.
5. Load a shop save and press **F4**. F4 toggles the menu; Esc also closes it. The hotkey can be changed and is saved between sessions.

No extra loader or framework is needed. Avoid `Mods/Mods` nesting and duplicate old trainer folders inside `Mods`; keep any backup outside that folder. The release ZIP contains the DLL, `manifest.xml` and `README-v1.9.4.txt`.

To uninstall, fully exit the game and delete **only** `<game directory>/Mods/ProbablyStolenTrainer`. Do not delete the entire `Mods` folder or game saves. Reinstall by extracting the package again. Uninstalling does not undo cash, items or other changes already saved.

## Common controls and quantities

Choose the target and parameters, then press the relevant action button to execute. Internal checks run automatically; target selection, filtering and typing do not execute changes. Goods must still be selected, manually or with automatic selection; the final trade remains manual.

Hotkeys pause during text entry. With a Chinese input method, confirm the candidate text first, then press Enter to search. Enter in a search field only searches. Save normally by sleeping after operations; the trainer does not save automatically.

- Catalogue entries follow the current loaded registry and the game's native hidden-item rules. An unavailable entry shows a reason. Being addable does not imply it can also be maintained or deleted.
- Reference unit value excludes event and retail markups. Actual trade prices are set by the game. Size means occupied cells in the real item shape; unknown values sort last.
- Addition counts default packages, which may contain multiple inventory units. A restock shortage smaller than one package is filled with one package. Insufficient capacity stops the operation and reports the result.
- Favourite presets are shared across saves; current stock is counted in the active save.
- Deletion removes all units of the selected instance, gives no refund and has no undo within the trainer. Maintenance applies to owned shop items; charging observes power outages and native battery restrictions.

## Water

Six water qualities are available in 250, 450, 750, 2000 and 6000 ml containers. Each generated unit is one full container. Restocking counts actual water quality and full-container size; half-full bottles do not count, and labels do not change the real quality.

Existing-bottle operations keep the container. Filling mixes with its contents; replacement empties it before adding the selected quality and final volume. Emptying and disposal lose the corresponding liquid. Transfer stops at a full destination or empty source. Purification to basic water retains volume and does not downgrade water already at that quality or above. Water tanks, storage tanks, filtering containers, alcohol and medicinal liquids are outside these existing-bottle operations.

## Machine assembly

**Basic completion** supplies missing batteries and the three general module types, preserving existing parts and positions without replacing or charging existing power sources.

The **recommended strongest setup** supports 12 machine types. It balances quality, output and power by machine, then fills remaining space with eligible non-negative ordinary modules. Standard compartments expand through the game's two upgrade levels; non-standard compartments do not receive that expansion. Replaced general modules and power sources return to the main inventory, so leave room. Special modules, chips, ingredients, containers and recipes are retained. Neural cores are opt-in.

These setups do not claim a global optimum, the largest part count or every cell filled. Native space, adjacency, air, container capacity, ingredients and attribute caps still apply. Neither mode starts machines or advances production. If safe values or effects cannot be established, the operation stops with a reason; basic completion remains available. If the result is marked uncertain, inspect the native parts compartment before taking another action.

## Customer orders and alerts

Use order preparation after a buying or trading customer reaches the counter and their dialogue ends. Automatic selection considers all matching stock, irrespective of current filters or pages, and selects at most 100 items. Adjust the selection manually if needed. Items move as whole items/stacks without splitting or merging; existing counter goods remain. Lack of space or a dialogue trigger stops movement.

Native inspection still occurs when goods reach the counter and may reveal traits or affect reputation. Reference value is neither the final price nor the customer's budget. Quoting, bargaining and completing the trade stay in the game.

Unusual-person alerts display supported markers only. They continue with the trainer window closed, wait for native notices to finish, and report the same category once per visit. They do not change scan/wanted states, report or arrest anyone, or advance dialogue. An absence of supported markers is not a statement about every possible story event.
