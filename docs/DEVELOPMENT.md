English | [简体中文](DEVELOPMENT_ZH.md)

# Development method

This is a record of working practices derived from the projects, not a maintenance roadmap.

## Start with the uncertain prerequisite

Before expanding an approach, test the smallest path that could invalidate it: framework load, one read-only operation, normal exit and repeat startup. The abandoned World Apart in-game experiment showed why feature migration should wait until the loader itself works.

## Bind evidence to the actual artifact

Keep source identity, executable or DLL hash, archive hash and relevant runtime protocol together. A version label or base commit does not describe uncommitted changes. Public source copies may remove personal paths or omit restricted inputs; their manifests and build notes identify that boundary.

## Reproduce, then repair narrowly

1. Identify the failing stage and retain the first concrete error.
2. Reproduce through the real constructor and first read, not a replacement for the whole path.
3. Make the smallest relevant change; check a valid state and an invalid or changed state.
4. Reuse valid earlier evidence for unaffected code. Broaden testing when shared lifecycle or build code changes.

Object identity, field type, method signature, calling convention and input bounds remain checks on actual operations. A game version or whole-file fingerprint alone is not evidence that every feature is unusable.

## Keep different kinds of evidence separate

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Static parsing and offline tests | Code structure and specific exercised paths | Live game behavior |
| Read-only runtime check | Discovery and reads in that state | Successful writes or rewards |
| Write and immediate readback | Immediate memory result | Saved data or later calculations |
| Normal save and reload | Persistence in that tested flow | Every activity's settlement |
| Activity completion | That activity's observed outcome | All scenes, characters or future versions |

Reported manual success and direct observations are labelled separately. A missing test is not a failure, but is not a pass either.

## Shared lifecycle and performance

Native features reuse one owned broker/session. Client close, script changes and host upgrades need distinct checks; a restart restoring function does not prove stale-session reuse was fixed. Unknown dispatch results must not trigger an automatic second write.

Cold discovery and repeated reads are measured separately. Use bounded scans and per-read validated caches; invalidate stale data and recheck identities. Improving speed must not bypass those protections.

## Stop at the agreed scope

Avoid expanding a small repair into a new automation framework or all-feature retest. Preserve useful failed evidence, identify what would change the conclusion, and stop repeated attempts without new information. Archive publication does not restart the development or testing of the software.

[Project logs](../README.md#projects) · [Privacy boundaries](PRIVACY.md)
