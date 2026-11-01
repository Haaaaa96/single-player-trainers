English | [简体中文](DEVLOG_ZH.md)

# Development notes — V1.9.8

2026-11-01 · Build `1.9.8-20261101a`

[Project overview](README.md) · [Installation and use](GUIDE.md)

## Changes and decisions

This binary-and-documentation archive adds editable current values and limits for native durability, armour and ordinary battery charge. It preserves repair/recharge actions, the shared ownership resolver and single-dispatch menu execution. Only actual instance attributes are exposed; special battery mechanisms are not treated as ordinary rechargeable batteries. Native recalculation and valuation limits remain relevant.

Water-machine assembly previously required every liquid component to exist explicitly. The game reads an omitted component as zero, so the trainer now accepts that specific case while still requiring capacity and rejecting invalid or conflicting values. Both basic and recommended assembly paths were checked. This identifies a reproducible defect, not proof that it was the sole cause of an unrecorded gameplay failure.

Three devices with ordinary battery slots were added: advanced booster, hypertech booster and Aug scanner. The bounded native catalogue review brings the supported profile count to 24 without inventing slots for devices that have none. This release also includes V1.9.7's new-save recognition fix and intervening device, accessory and order-preparation changes.

## Verification and lifecycle

- **Static/offline:** 28 service cases, 18 menu callbacks, 14 host lifecycle cases and 181 related machine cases passed. The real-reference final build, 309 native-reference checks, final-DLL operation checks and native manifest/scanner checks passed. These are offline results, not 241 gameplay tests.
- **Lifecycle:** the existing native `IMod` and shared Unity main-thread host remain. Session/window tokens, ownership, mutual exclusion and uncertain-result rejection are retained. No new loader, injected backend or external process was added. Unchanged person-alert files reuse matching prior evidence.
- **Package:** the original three-file ZIP was inspected and independently extracted; the DLL, manifest and versioned README match the delivery hashes. Publication does not rebuild or install it.
- **Still unverified in game for this build:** actual loading, UI/input behaviour, item and machine effects, normal restart and save/reload remain for the author to check. Static save-path evidence is not a completed persistence test.

## Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26337366` |
| Release tag | `probably-stolen-v1.9.8` |
| ZIP | `ProbablyStolenTrainer-v1.9.8.zip` |
| ZIP size | 123,850 bytes |
| ZIP SHA256 | `C15FE660ADCAFEB4F2BF0811961BE31FF39B5D5712E97E4C6C4944727D23D813` |
| DLL SHA256 | `63E967D66BB7A181C80AFD6867B387E9AB4C473EE7F4328BD259D1F8F65B0A2B` |

Implementation source is not included. Development was assisted by OpenAI Codex. Reference-build and hash identities do not establish compatibility with other versions or MOD combinations.

## Historical V1.9.4 record

The following is the prior version's evidence, retained as history rather than a claim about V1.9.8.

### Scope and implementation

This release archives the binary and bilingual project documentation, without implementation source. The cumulative additions since V1.3 cover the expanded catalogue, water, machine assembly, order preparation, person alerts and deletion.

V1.9.4 checks the complete menu flow for direct execution. It removes a stale “preview again” message and changes trade-trait revelation to recheck the target at click time, match its UID and ID, consume the request token, then execute within the same callback. Window/session tokens, mutual exclusion, ownership and capacity checks remain; uncertain results are not automatically dispatched again. Item selection and final manual trading remain part of the workflow.

The existing native `IMod` and main-thread architecture is retained. No extra loader, injection path or external background component was introduced.

### Evidence and remaining checks

- **Static/offline:** the build against the real game references passed. Related trade, menu and catalogue checks passed; final-DLL inspection covered all 12 menu pages and the affected execution paths. Native reference signatures and visibility were checked, with targeted IL inspection of the final reveal callback.
- **Lifecycle checks, offline:** window closure, page changes/recreation, repeated entry, state changes during callbacks and uncertain-result rejection were covered. These are not a claim of an in-game restart test.
- **Installation:** the build was installed while the game was closed, after backing up the prior version and saves. The later release-package revision changed only its README; the DLL and manifest stayed unchanged. It was not a new gameplay test or a reinstall of the revised ZIP.
- **In-game acceptance:** actual UI behaviour, gameplay effects, normal restart and save/reload for this build remain for the author to check. They are not marked as passed here.

### Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26284217` (2026-10-29) |
| Release tag | `probably-stolen-v1.9.4` |
| ZIP | `ProbablyStolenTrainer-v1.9.4.zip` |
| ZIP size | 111,985 bytes |
| ZIP SHA256 | `78D1D22C5D97F85013921DDA499F988F8487C42073BC9EFA49E2FE12B11AB86B` |
| DLL SHA256 | `570BB2EC784FF8CCA872FE099113AC4EB418FA2929ACAE416044DFC79D6F0130` |

The reference build identifies the development environment; it is not evidence of compatibility with every other version or MOD combination.
