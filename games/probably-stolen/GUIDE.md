English | [简体中文](GUIDE_ZH.md)

# V1.10.3 installation and use

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

No extra loader or framework is needed. Avoid `Mods/Mods` nesting and duplicate old trainer folders inside `Mods`; keep any backup outside that folder. The release ZIP contains the DLL, `manifest.xml` and `README-v1.10.3.txt`.

To uninstall, fully exit the game and delete **only** `<game directory>/Mods/ProbablyStolenTrainer`. Do not delete the entire `Mods` folder or game saves. Reinstall by extracting the package again. Uninstalling does not undo cash, items or other changes already saved.

## Local package and Workshop

Use one distribution at a time. Unsubscribe from this trainer's Workshop item when using the local package. To switch to Workshop, save and fully exit the game, move the entire local `Mods/ProbablyStolenTrainer` folder outside `Mods`, then subscribe. A local copy with the same MOD ID can shadow the Workshop copy; disabling it alone is insufficient. Preserve `ModData/ProbablyStolenTrainer` under the save location to keep hotkeys, favourites and alert settings. Enable the MOD again if the game requests it.

## Common controls and quantities

Choose the target and parameters, then press the relevant action button to execute. Internal checks run automatically; target selection, filtering and typing do not execute changes. Goods must still be selected, manually or with automatic selection; the final trade remains manual.

Default F4 and saved custom hotkeys share the same input handling. Hotkeys pause while an active text field, IME composition, console input or native key capture needs the keyboard. Closing the trainer clears only its own selected field; existing hotkey settings remain unchanged after upgrading to V1.10.3. With a Chinese input method, confirm the candidate text first, then press Enter to search. Enter in a search field only searches. Save normally by sleeping after operations; the trainer does not save automatically.

- Catalogue entries follow the current loaded registry and the game's native hidden-item rules. An unavailable entry shows a reason. Being addable does not imply it can also be maintained or deleted.
- Reference unit value excludes event and retail markups. Actual trade prices are set by the game. Size means occupied cells in the real item shape; unknown values sort last.
- Addition counts default packages, which may contain multiple inventory units. A restock shortage smaller than one package is filled with one package. Insufficient capacity stops the operation and reports the result.
- Favourite presets are shared across saves; current stock is counted in the active save.
- Deletion removes all units of the selected instance, gives no refund and has no undo within the trainer. Maintenance applies to owned shop items; charging observes power outages and native battery restrictions.

## Automatic assembly of newly added items

Ordinary addition, target restocking and favourite presets automatically assemble supported new items. Choose the item and quantity, then execute once; no separate assembly page or second confirmation is required. Each new instance is placed and assembled before the next is created. Existing inventory is not upgraded by restocking, and attachment counts do not inflate the requested root-item quantity.

There are 34 conditional plans: 24 machine/tool profiles, six moddable gun types, one water pitcher and three modular backpacks. The item and its attachments must exist in the currently loaded addable catalogue, and their actual slot layout and compatibility must pass inspection. Unrecognised items retain normal factory addition rather than receiving invented attachments.

Supported equipment uses a suitable position in the main inventory. For guns, space for the complete recommended attachment shape is checked before placement. Leave enough room for the finished item and any parts that must return to inventory. If a capacity, compatibility or state check fails, the result reports what was added or assembled and why the batch stopped. Already placed items remain; an uncertain result stops the batch and is not automatically retried.

Machine plans reuse the recommended setup and supported batteries, modules and internal parts. Water vending machines fill the corresponding tanks for the chosen basic, quality or pure-water option. Forbidden neural cores remain off by default. Production ingredients, recipes, faction choices and gun ammunition remain manual; no machine is automatically started and no trade is completed.

Water pitchers receive an advanced self-repairing filter without adding water. Addable small modular backpacks receive one large general-purpose pouch; medium and large variants receive two. Only verified expansion slots are filled; main storage stays empty. Ordinary storage, ingredient areas and recipe slots are not attachment slots. Other ordinary-item and water-addition behaviour remains unchanged.

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

## Customer service gun assembly

The gun-loadout page has **Customer service guns** above **Owned guns**. The service section is independent of the owned-gun search.

1. Wait until the customer's dialogue ends and the actual service gun appears on the front or back trade counter. Open the gun-loadout page and review its name, ID and required/bonus conditions.
2. Leave room around the gun for its assembled shape, then press the order-assembly action once. Missing compatible parts are generated and installed; all existing parts remain in place.
3. Read the actual result and complete delivery manually in the original game interface. The trainer does not complete the order, settle cash or add ammunition.

Only the current customer's modification service gun is eligible. Ordinary incoming guns, purchase orders and past customers are excluded. If the customer, order, gun or counter position changes, old actions expire; reopen the page to refresh.

Planning prioritizes all required conditions, then bonuses and legal slot filling, using the game's strict attribute comparisons and calibre equality. Existing attachments and ownership remain unchanged. Incompatible, locked or condition-breaking slots may remain empty; if existing parts prevent a valid plan, handle those parts in the game first. Search is bounded and does not claim a global optimum or every slot filled. Base quality is not changed.

The complete expanded shape and native slot acceptance are checked before execution. State changes stop the operation, and an uncertain result is not retried automatically. Inspect the actual gun before issuing another action.

## Owned-gun loadout

1. Leave room for the gun to expand at its current position and for returned parts in the main inventory. The gun remains in place; moving it to ordinary grid inventory is no longer required.
2. Open the gun-loadout page. Reachable owned guns appear automatically; search by name or ID and press Enter to show results only.
3. Select a gun and apply the recommended loadout. Compatible parts are generated and installed directly; read the actual result at the top of the page.

The reader covers 16 verified inventory entry points and their owned nested contents, including main, storage/display/trade areas, hidden and night-time inventory, pockets/backpacks, employee inventory and compatible mounted positions. An available entry point does not imply that every gun can fit there or that every temporary location persists independently. The owned-gun action rejects customer/service-order guns, unreachable roots, duplicate identities, true locks and insufficient space. Use the separate service section only for an eligible current service order.

A gun in the purchase area can be assembled in place when no customer trade is active. Finish an active customer's trade first: native attachment callbacks can otherwise affect the transaction or its dialogue. A customer at the counter does not by itself block assembly in unrelated owned locations.

The catalogue covers six moddable gun types and 31 compatible attachments. Recommendations combine firepower, style, reliability, recoil control, ergonomics and accuracy, including fixed and percentage modifiers. Individual attributes can involve tradeoffs. Existing parts with an equal or better combined score stay installed; replaced parts and their contents return intact to the main inventory.

Grid locations reserve a conservative envelope for the original and recommended shapes before removing anything; compatible non-grid slots use native state, ownership and parent-container checks. All returned parts still need space in the main inventory. If a result is uncertain, inspect the actual inventory before another action; do not repeatedly click.

Pistols have no compatible stock and shotguns have no compatible magazine, so those positions stay empty. Revolvers, electric weapons and unfinished frames show why this attachment system is unavailable. Magazines are attachments; ammunition must be supplied separately. This action does not add ammunition, fire the gun or complete a trade. Machine basic completion remains available on the machine page.

## Customer orders and alerts

Use order preparation after a buying or trading customer reaches the counter and their dialogue ends. Automatic selection considers all matching stock, irrespective of current filters or pages, and selects at most 100 items. Adjust the selection manually if needed. Items move as whole items/stacks without splitting or merging; existing counter goods remain. Lack of space or a dialogue trigger stops movement.

Native inspection still occurs when goods reach the counter and may reveal traits or affect reputation. Reference value is neither the final price nor the customer's budget. Quoting, bargaining and completing the trade stay in the game.

Unusual-person alerts display supported markers only. They continue with the trainer window closed, wait for native notices to finish, and report the same category once per visit. They do not change scan/wanted states, report or arrest anyone, or advance dialogue. An absence of supported markers is not a statement about every possible story event.

## Counter-item counterfeit and quality alerts

Enabled by default. Open **F4/custom key → Identification assistance** for the detailed list and the independent item-alert toggle, which is saved automatically. Person alerts retain their separate control on the person-identification page.

The monitor reads both trade-counter sides every 0.5 seconds, including items inside counter containers and attached parts. It does not scan warehouse, main or display inventory outside those counter roots. Alerts identify customer goods, owned counter goods or counter goods without an active customer. The detail list shows up to 32 items and reports any remainder.

Supported problems include native counterfeit cigarettes, vouchers, injectors, replicas and food; expiration, spoilage, failure, rust, dents, stuck modules and explicit low quality; damaged hands and plasma-battery casing defects. Water uses actual versus labelled quality: rust/ditch water is reported, while correctly labelled ghost water is not flagged merely for its type. Empty bottles, ordinary second-hand goods and opened packages are not automatically treated as counterfeit.

The top banner stays active with the menu closed, combines item and person alerts without intercepting mouse input, and clears when affected goods leave the counter. Normal polling can take up to the next half-second interval. The monitor reads real unrevealed traits but does not reveal/discover them or change item values, prices, transactions or final trading. Only the independent alert preference is saved. Malformed, oversized or unknown data is reported as partial/uncertain; an absence of supported markers is not a guarantee that all goods are genuine. Real Unity display/input and restart acceptance remain pending for this build.
