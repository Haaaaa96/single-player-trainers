English | [简体中文](DEVLOG_ZH.md)

# Development notes — V1.9.4

2026-10-30 · Build `1.9.4-20261030a`

[Project overview](README.md) · [Installation and use](GUIDE.md)

## Scope and implementation

This release archives the binary and bilingual project documentation, without implementation source. The cumulative additions since V1.3 cover the expanded catalogue, water, machine assembly, order preparation, person alerts and deletion.

V1.9.4 checks the complete menu flow for direct execution. It removes a stale “preview again” message and changes trade-trait revelation to recheck the target at click time, match its UID and ID, consume the request token, then execute within the same callback. Window/session tokens, mutual exclusion, ownership and capacity checks remain; uncertain results are not automatically dispatched again. Item selection and final manual trading remain part of the workflow.

The existing native `IMod` and main-thread architecture is retained. No extra loader, injection path or external background component was introduced.

## Evidence and remaining checks

- **Static/offline:** the build against the real game references passed. Related trade, menu and catalogue checks passed; final-DLL inspection covered all 12 menu pages and the affected execution paths. Native reference signatures and visibility were checked, with targeted IL inspection of the final reveal callback.
- **Lifecycle checks, offline:** window closure, page changes/recreation, repeated entry, state changes during callbacks and uncertain-result rejection were covered. These are not a claim of an in-game restart test.
- **Installation:** the build was installed while the game was closed, after backing up the prior version and saves. The later release-package revision changed only its README; the DLL and manifest stayed unchanged. It was not a new gameplay test or a reinstall of the revised ZIP.
- **In-game acceptance:** actual UI behaviour, gameplay effects, normal restart and save/reload for this build remain for the author to check. They are not marked as passed here.

## Artifact identity

| Item | Recorded identity |
| --- | --- |
| Reference game | Steam build `26284217` (2026-10-29) |
| Release tag | `probably-stolen-v1.9.4` |
| ZIP | `ProbablyStolenTrainer-v1.9.4.zip` |
| ZIP size | 111,985 bytes |
| ZIP SHA256 | `78D1D22C5D97F85013921DDA499F988F8487C42073BC9EFA49E2FE12B11AB86B` |
| DLL SHA256 | `570BB2EC784FF8CCA872FE099113AC4EB418FA2929ACAE416044DFC79D6F0130` |

The reference build identifies the development environment; it is not evidence of compatibility with every other version or MOD combination.
