English | [简体中文](DEVLOG_ZH.md)

# Development notes — V1.10.3

2026-11-03 · Build `1.10.3-20261103a`

[Project overview](README.md) · [Installation and use](GUIDE.md)

## Changes and decisions

V1.10.3 separates the current customer's service gun from owned guns and adds order-based attachment generation. The plan first satisfies all required conditions, then seeks bonuses and legal slot filling. It preserves the original gun's ownership and every existing attachment, and leaves delivery and settlement to the player. Static and offline checks passed; actual gameplay and save/reload remain unverified for this build.

Native metadata and targeted code inspection establish strict greater-than/less-than attribute conditions, calibre equality and the six current service-order attributes. The calculation includes condition, descendant percentage modifiers and fixed additions, with integer truncation toward zero. All 31 candidate factories initialize the required twelve attribute tags; missing keys stop planning rather than invoking a helper that would lazily create tags.

The service path binds the save, visit, customer blueprint, order and actual placed service gun. It accepts only that gun directly on the front or back counter, not an ordinary incoming gun or purchase order. The six supported native gun layouts reuse the existing slot reader. Existing attachments remain fixed; empty-slot candidates must pass native compatibility.

Planning orders its goals by required conditions, bonuses, filled slots and the six-attribute total. Search is capped at one million nodes; a cap permits only a valid plan already found, not a claim of global optimality. Incompatible, locked or condition-breaking slots may stay empty. Base quality and ammunition are unchanged. The complete expanded shape is preflighted; each insertion uses the native slot path once, followed by attribute and object readback. The final acceptance check does not invoke order completion or cash settlement.

Whole-gun counter insertion/removal locks are distinct from attachment-slot permission. The service path captures and monitors the former instead of rejecting every locked counter gun; native slot and occupancy checks remain. It returns no existing parts to main inventory, so it does not block solely because main-inventory insertion is locked. The owned-gun replacement path retains its return-space and locking checks. Unrecognized extra customer callbacks are rejected; this is not evidence of compatibility with every MOD.

## Lifecycle and verification

The existing native `IMod`, single trainer host, main thread, shared machine/assembly exclusion and session generations remain the execution path. No new loader, injection, bridge, background process or second write channel is introduced. Page tokens and order tickets are consumed once; refresh, close, page/save/customer changes or changed targets and requirements reject stale callbacks. Unknown results are blocked from automatic redispatch. The common hotkey/input implementation is unchanged; affected menu lifecycle checks reference its prior evidence.

- **Offline checks:** 295 relevant assertions passed: 53 planner, 25 service, 20 assembly-control, 53 menu and 144 retained-channel/order-routing checks. Production logic is exercised with controlled external game objects, rendering and native leaves; these are not in-game results.
- **Final artifact:** build against real game references, 349 native-reference checks, direct-action inspection, native manifest/metadata scanning and three-file package checks passed. Independent extraction matched all payload hashes.
- **Retained scope:** owned-gun loadouts, automatic new-item assembly and machine basic completion remain. Unchanged features reuse existing evidence; this release does not claim a fresh full gameplay regression.
- **Still pending:** actual Unity display, native callbacks, front/back-counter assembly, manual delivery, Workshop upgrade, normal restart and save/reload remain for the author to check. Publication reuses the original ZIP without rebuilding or operating the game.

## Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.10.3` |
| ZIP | `ProbablyStolenTrainer-v1.10.3.zip` |
| ZIP size | 152245 bytes |
| ZIP SHA256 | `DDB11BDD4C03ADCD08FCA5E5CF1AC6B92F14B52B947EE42EB465A35ED6A3AB5B` |
| DLL SHA256 | `5C18A1E0137371B16591A6604E517E60024923F7FB9F2E84A03F4DDE3DC25DC7` |

Implementation source is not included. Reference identities do not establish compatibility with other versions or MOD combinations.

## Historical V1.10.2 record

The following preserves the prior version's decisions and evidence; it does not claim fresh gameplay verification of V1.10.3.

### Changes and decisions

V1.10.2 adds continuous counterfeit/quality warnings for the front and back trade-counter roots and their contained items or attached parts. Native metadata and targeted code evidence distinguish real traits from displayed traits, so names, superficial replica labels and negative values alone are not treated as proof of counterfeiting. Ordinary second-hand and opened goods remain outside those assumptions.

The classifier uses 20 exact feature-category/actual-condition pairs, plus native water quality buckets and mislabelling, the Ribwich counterfeit predicate, hand damage and plasma-battery casing defects. Rust/ditch water is reported; correctly labelled ghost water is not flagged solely for its type, and empty bottles do not trigger water warnings. Unknown third-party features are not universally classified.

Reads avoid the game's tag helper that can lazily create missing tags. Traversal uses bounded forward paths and reference deduplication rather than an unbounded parent walk. Duplicate IDs, malformed graphs and limits are reported as partial/unknown. Scope is bounded to 4096 graph nodes, 1024 items, depth 64 and 128 features per item; absence of a supported marker is not an authenticity guarantee.

### Lifecycle and verification

The existing half-second refresh drives the read-only classifier and the single noninteractive item/person banner. The monitor continues with the menu closed. Context and the first displayed item's path are checked between polls; reset, scene/load changes and disable clear both monitors. The item-alert preference has its own persistent toggle in identification assistance. The existing native `IMod`, single main-thread host, hotkey priority and execution ownership remain. There is no new loader, injection, bridge, background process or game-state write channel, and no automatic reveal, pricing or trading.

- **Offline service:** 24 production-service groups passed, including exact condition matrices, counterexamples, nested graphs, limits and lifecycle. Native leaves are controlled, and no lazy-tag/write interface was called.
- **Offline UI/host:** 33 assertions passed, plus one timing observation; 73 retained hotkey cases passed. These are production-method checks with controlled leaves, not real Unity rendering or input timing tests.
- **Final artifact:** real-reference build, 330 native-reference checks, direct-action inspection, native MOD scanner and three-file package/extraction checks passed. Unchanged gun/machine functionality references V1.10.1 evidence rather than a new full matrix run.
- **Still pending:** actual goods appearing/leaving, simultaneous item/person rendering, native gameplay, restart preference persistence, save/reload and other MOD combinations remain for the author to check. Publication reuses the original ZIP without rebuilding, installing or operating the game.

### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.10.2` |
| ZIP | `ProbablyStolenTrainer-v1.10.2.zip` |
| ZIP size | 142684 bytes |
| ZIP SHA256 | `26977CCECC0B78FEFFEA25517A9ED24B25DB2849B13A7CBD50B5F6D2675ABB33` |
| DLL SHA256 | `F5F6DD79E69AB37CB4AE7E4A57E794BEC37BE03F25F8E75FE21E6B9DEFBDF592` |

Implementation source is not included. Reference identities do not establish compatibility with other versions or MOD combinations.

### Historical V1.10.1 record

The following preserves the prior version's decisions and evidence; it does not claim fresh gameplay verification of V1.10.2.

#### Changes and decisions

V1.10.0 rejected normal guns with the changed-eight-slot-structure message. The reference game assembly was unchanged: this was a trainer defect, not evidence of a game update or damaged save. The reader treated an outer one-cell grid as the attachment slot and missed the native intake wrapper. V1.10.1 unwraps that structure, then checks direct parent links, nearest owning item, all eight unique slots and existing contents. Unknown wrappers and inconsistent identities remain rejected.

The original offline tests replaced the gun-reading path and flattened the slot structure, so they missed a failure affecting all six normal gun types. The new regression enters the production reader with native-shaped controlled leaves, including initial and repeated reads. This corrects the earlier evidence boundary; static API presence and coordinator tests alone did not establish a working gun read.

Manual gun assembly now keeps the gun in its reachable owned location. Sixteen verified inventory roots and owned nested contents are checked before, after and between steps. Grid positions reserve the conservative union of the current and recommended shapes; compatible non-grid mounts use native state, ownership and parent-container checks. True container locks remain distinct from a parent inventory's interface-only pickup lock.

Purchase-area guns are rejected before writing while a customer trade is active, because native attachment callbacks can trigger transaction, dialogue and procurement behaviour. After the trade ends, the same position can be used. Unrelated owned positions are not rejected merely because a customer is present.

#### Automatic assembly during addition

The shared addition path now applies recommended attachments to new supported instances during ordinary addition, target restocking and favourite presets. It completes one instance before making the next and does not upgrade existing stock. Supported equipment uses a suitable main-inventory location; the complete gun attachment shape is reserved before placement. Placed items remain when a later step fails, and uncertain results stop the batch without automatic redispatch.

There are 34 conditional plans: 24 existing machine/tool profiles, six moddable guns, a water pitcher and three modular backpacks. The pitcher receives the advanced filter for its native self-repair benefit. Addable small modular backpacks receive one 12-cell general-purpose pouch; medium and large variants receive two. Their main storage stays empty. Current catalogue registration, actual slot structure, parent chains and native compatibility are checked instead of inferring availability from an old factory method.

Ordinary storage and ingredient/recipe areas are not treated as attachment slots. A separate RAS tank or vending core has no child attachment slots of its own. The old technician-backpack module factories do not establish a currently registered module catalogue. Unknown plans preserve normal factory addition rather than claiming complete assembly. Existing machine basic completion remains, neural cores stay off by default, and no ammunition loading, firing, automatic production or final transaction is added.

#### Verification and lifecycle

- **Related offline regression:** 382 checks passed: 32 addition/simple-equipment cases, 59 production gun-reader/location cases, 60 gun coordinator/scoring cases, 11 combined-shape preflights, seven new-gun placement cases, 32 menu callbacks and 181 retained machine cases. Actual production methods run with controlled native leaves; these are not 382 gameplay tests.
- **Final artifact:** the real-reference build, 329 native-reference checks, native MOD scanner, direct-action CIL inspection and three-file release checks passed. The recorded checks bind to the final source and DLL.
- **Package:** publication reuses the final original ZIP. It does not rebuild, install or operate the game.

The native `IMod`, single main-thread host, shared execution ownership and session generations remain. The affected paths retain stale-window invalidation, ownership, native locks, space reservation, single dispatch and uncertain-result protection. No extra loader, bridge, injected backend or external process was introduced.

Static wrapper/callback evidence, controlled-leaf production-code regressions, final-DLL reference checks and native gameplay are distinct. Actual UI rendering, Unity/native effects, normal restart, save/reload and other MOD combinations remain for the author to check in game. This publication uses the final package identity recorded below and does not imply local installation or game acceptance.

#### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.10.1` |
| ZIP | `ProbablyStolenTrainer-v1.10.1.zip` |
| ZIP size | 136890 |
| ZIP SHA256 | `5AE35404B4A71166C3B276F45F865A9189276D7D8CA4378C4E2563F8D588FC4E` |
| DLL SHA256 | `58DEDCDAF669C4AC138F2DCC75AD130E143D122FA6548FC4AAF18088AA9474C0` |

Implementation source is not included. Reference identities do not establish compatibility with other versions or MOD combinations.

#### Historical V1.10.0 record

The following preserves the earlier record. Its offline checks missed the real gun-reading failure described above. Its restriction to grid inventory is superseded by V1.10.1 and is not current usage guidance.

##### Changes and decisions

V1.10.0 adds one recommended gun-loadout action. Native metadata and targeted code inspection establish six moddable gun types, 31 compatible attachments and eight attachment positions. The recommendation compares combined gains in firepower, style, reliability, recoil control, ergonomics and accuracy, including fixed and percentage modifiers. Existing parts with an equal or better score remain. This is a practical recommendation, not a proof of a global optimum or maximum values for every attribute.

Pistols have no compatible stock and shotguns have no compatible magazine. Unsupported revolvers, electric weapons and unfinished frames retain an explanation. No slots or ammunition are invented. The existing machine basic-completion workflow remains.

Gun attachments can expand the occupied shape. The coordinator checks the complete conservative shape envelope and room for all returned-part trees before removing old parts. Guns in non-grid mounting slots are rejected until moved to owned grid inventory. Replaced parts and their contents return intact to the main inventory. Native acceptance is dispatched once per step and read back; uncertainty blocks repeat assembly in that session.

##### Verification and lifecycle

- **Static/offline:** the real-reference build, 60 coordinator/scoring checks, 32 production-menu callback checks and 27 retained hotkey/host checks passed. Inventory and Unity leaves are controlled in these checks; they are not native gameplay assembly tests.
- **Final artifact:** 315 native-reference checks, native manifest/scanner checks, direct-execution UI inspection and independent three-file ZIP extraction passed.
- **Lifecycle:** the native `IMod` and single shared main-thread host remain. The new page reuses the existing execution lock, session generations, ownership checks and uncertain-result record. Closing, navigation, changed search/selection and save changes invalidate stale callbacks. No new loader, bridge, injected backend or external process was introduced.
- **Targeted review:** construction callbacks are rechecked for session/object changes; non-grid mounts are rejected where whole-shape reservation cannot be established; temporary-part cleanup failure overrides apparent success and prevents retry. Offline fault injection covers these branches.
- **Pending in game:** actual loading, disable/enable, Unity input ordering, attachment effects, normal restart, save/reload and other MOD combinations remain for the author to check. Unchanged behaviour may reuse identified prior evidence; the historical 73-key matrix is not presented as a new V1.10.0 run. Publication reuses the original package without rebuilding or installing it.

##### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.10.0` |
| ZIP | `ProbablyStolenTrainer-v1.10.0.zip` |
| ZIP size | 130,224 bytes |
| ZIP SHA256 | `BB1DC01C9C668C27CF25B3FC69E1E8A61D8E8FF26F348FB4D3063F01FFB00E67` |
| DLL SHA256 | `18C4B65982447AE421B1119BB904D961237F64E620EE8FBBEFE7F75884250E3F` |

Implementation source is not included. Reference identities do not establish compatibility with other versions or MOD combinations.

##### Historical V1.9.9 record

The following is prior evidence, retained as history rather than new V1.10.0 testing.

##### Changes and decisions

Native code inspection identified a persistent typing flag that can survive a game editor closing. The old hotkey path trusted that flag and could keep rejecting the menu key. V1.9.9 checks actual active and enabled input focus, IME composition, console focus and native key capture instead. It does not reset the game's typing flag or change another window's focus. This fixes reproducible conditions, without claiming to explain every unrecorded gameplay report.

The trainer's close callback invalidates its window and operation generation, clears queued searches and releases only focus owned by that closing window. Stale callbacks cannot invalidate a newer window. After checking the current save identity, the host handles the menu toggle before automatic refresh. Single-frame dispatch, held-key suppression, exact modifiers, save-frame suppression and native key-conflict checks remain. All V1.9.8 features are retained.

##### Verification and lifecycle

- **Offline comparison:** the same initial suite passed 17/27 on V1.9.8 and 27/27 after the fix. It compiles the production host and hotkey code plus the affected menu methods, covering stale typing state, hidden/disabled fields, IME, close/page changes, focus ownership and refresh failures.
- **Expanded key matrix:** 73/73 total checks passed, including the original 27 and 46 additional checks for F4, custom F3/F5/BackQuote, seven Ctrl/Alt/Shift combinations on F3, left/right modifier keys, extra-modifier rejection, repeated toggles, input/page recovery, key conflicts and settings readback failures. No further production change was needed.
- **Final artifact:** build against real game references, 308 native-reference checks, final-DLL operation inspection, the native manifest/scanner and independent three-file extraction passed.
- **Lifecycle:** the existing native `IMod` main-thread host remains. Affected reset, destruction, repeated enable and menu lifecycle paths have offline coverage, including 2,000 toggles, 50 scene changes and 30 disable/enable cycles in the initial suite. No new loader, injected backend or external process was added.
- **Not claimed:** these are not gameplay tests. Actual Unity event ordering, in-game loading and hotkeys, normal restart, gameplay effects and save/reload remain for the author to check. The follow-up did not retest real search submission, system focus switching or overlay key interception. Publication reuses the original package without rebuilding or installing it.

Earlier tests fixed the typing result to false and replaced some hotkey/open paths, missing the persistent flag and actual dispatch order. Future input changes retain the affected production paths and failure cases.

##### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.9.9` |
| ZIP | `ProbablyStolenTrainer-v1.9.9.zip` |
| ZIP size | 124,514 bytes |
| ZIP SHA256 | `EB4683726973F5165E03128BDC53D80767A36FEAD269201A1F41B152D53C739F` |
| DLL SHA256 | `28A1204BDDFA268C40D262EF73364108D1D9C7B4D159825306B8BD40C97795B3` |

Implementation source is not included. Reference identities do not establish compatibility with other versions or MOD combinations.

##### Historical V1.9.8 record

The following is prior evidence, retained as history rather than new V1.9.9 testing.

##### Changes and decisions

This binary-and-documentation archive adds editable current values and limits for native durability, armour and ordinary battery charge. It preserves repair/recharge actions, the shared ownership resolver and single-dispatch menu execution. Only actual instance attributes are exposed; special battery mechanisms are not treated as ordinary rechargeable batteries. Native recalculation and valuation limits remain relevant.

Water-machine assembly previously required every liquid component to exist explicitly. The game reads an omitted component as zero, so the trainer now accepts that specific case while still requiring capacity and rejecting invalid or conflicting values. Both basic and recommended assembly paths were checked. This identifies a reproducible defect, not proof that it was the sole cause of an unrecorded gameplay failure.

Three devices with ordinary battery slots were added: advanced booster, hypertech booster and Aug scanner. The bounded native catalogue review brings the supported profile count to 24 without inventing slots for devices that have none. This release also includes V1.9.7's new-save recognition fix and intervening device, accessory and order-preparation changes.

##### Verification and lifecycle

- **Static/offline:** 28 service cases, 18 menu callbacks, 14 host lifecycle cases and 181 related machine cases passed. The real-reference final build, 309 native-reference checks, final-DLL operation checks and native manifest/scanner checks passed. These are offline results, not 241 gameplay tests.
- **Lifecycle:** the existing native `IMod` and shared Unity main-thread host remain. Session/window tokens, ownership, mutual exclusion and uncertain-result rejection are retained. No new loader, injected backend or external process was added. Unchanged person-alert files reuse matching prior evidence.
- **Package:** the original three-file ZIP was inspected and independently extracted; the DLL, manifest and versioned README match the delivery hashes. Publication does not rebuild or install it.
- **Still unverified in game for this build:** actual loading, UI/input behaviour, item and machine effects, normal restart and save/reload remain for the author to check. Static save-path evidence is not a completed persistence test.

##### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.9.8` |
| ZIP | `ProbablyStolenTrainer-v1.9.8.zip` |
| ZIP size | 123,850 bytes |
| ZIP SHA256 | `C15FE660ADCAFEB4F2BF0811961BE31FF39B5D5712E97E4C6C4944727D23D813` |
| DLL SHA256 | `63E967D66BB7A181C80AFD6867B387E9AB4C473EE7F4328BD259D1F8F65B0A2B` |

Implementation source is not included. Reference-build and hash identities do not establish compatibility with other versions or MOD combinations.

##### Historical V1.9.4 record

The following is the prior version's evidence, retained as history rather than a claim about V1.9.8.

##### Scope and implementation

This release archives the binary and bilingual project documentation, without implementation source. The cumulative additions since V1.3 cover the expanded catalogue, water, machine assembly, order preparation, person alerts and deletion.

V1.9.4 checks the complete menu flow for direct execution. It removes a stale “preview again” message and changes trade-trait revelation to recheck the target at click time, match its UID and ID, consume the request token, then execute within the same callback. Window/session tokens, mutual exclusion, ownership and capacity checks remain; uncertain results are not automatically dispatched again. Item selection and final manual trading remain part of the workflow.

The existing native `IMod` and main-thread architecture is retained. No extra loader, injection path or external background component was introduced.

##### Evidence and remaining checks

- **Static/offline:** the build against the real game references passed. Related trade, menu and catalogue checks passed; final-DLL inspection covered all 12 menu pages and the affected execution paths. Native reference signatures and visibility were checked, with targeted IL inspection of the final reveal callback.
- **Lifecycle checks, offline:** window closure, page changes/recreation, repeated entry, state changes during callbacks and uncertain-result rejection were covered. These are not a claim of an in-game restart test.
- **Installation:** the build was installed while the game was closed, after backing up the prior version and saves. The later release-package revision changed only its README; the DLL and manifest stayed unchanged. It was not a new gameplay test or a reinstall of the revised ZIP.
- **In-game acceptance:** actual UI behaviour, gameplay effects, normal restart and save/reload for this build remain for the author to check. They are not marked as passed here.

##### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26284217` (2026-10-29) |
| Release tag | `probably-stolen-v1.9.4` |
| ZIP | `ProbablyStolenTrainer-v1.9.4.zip` |
| ZIP size | 111,985 bytes |
| ZIP SHA256 | `78D1D22C5D97F85013921DDA499F988F8487C42073BC9EFA49E2FE12B11AB86B` |
| DLL SHA256 | `570BB2EC784FF8CCA872FE099113AC4EB418FA2929ACAE416044DFC79D6F0130` |

The reference build identifies the development environment; it is not evidence of compatibility with every other version or MOD combination.
