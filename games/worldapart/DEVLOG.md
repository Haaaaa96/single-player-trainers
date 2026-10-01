# WorldApart — Development notes

**English** | [简体中文](DEVLOG_ZH.md)

[Overview](README.md) · [Source](../../sources/worldapart) · [Build](../../sources/worldapart/BUILD.md) · [Terms](../../TERMS.md)

Selected historical findings through 2026-10-01. The public source is a sanitized research snapshot; it was not executed or tested during this documentation preparation and is not represented as an exact source match for earlier binaries.

## Read performance in the “new v1.3” archive

The focused change concerned initial reads for aptitude/skills, technique learning and memory stones. Aptitude and learning had searched large readable memory ranges to find managers. The revised path follows a reviewed manager chain, checks owner uniqueness and runtime identity, and retains a validated fallback for unknown entry code.

Memory-stone reads repeatedly checked the same metadata. The revision reuses metadata within one list read, revalidates used definitions before returning, and clears the cache after success, failure and before the next refresh. Character, location and action state are still read again.

Historical measurements in the same reference game session, with profiling enabled:

| Page | Earlier first / repeated read | Revised first / repeated read |
| --- | --- | --- |
| Aptitude and skills | 31.62 / 0.25 s | 0.75 / 0.45 s |
| Technique learning | 15.87 / 0.02 s | 0.15 / 0.11 s |
| Memory stones | 9.65 / 9.30 s | 2.52 / 2.08 s |

These measurements exclude connection and approximately 0.12 seconds of parser construction, depend on session load, and are not a performance promise. An additional unprofiled memory-stone comparison, including construction, measured 5.53 → 1.27 seconds with equal complete returned dictionaries.

Historical validation covered real construction, first and repeated reads, metadata/owner rejection cases and relevant offline checks. Technique learning had no active round, so its result demonstrates object lookup and inactive-state reading, not active-round effects or settlement.

## Earlier findings retained in the design

- A reused parser method depended on an uninitialized class cache. Tests need the real constructor and both first and repeated reads; replacing the whole read path can hide initialization defects.
- Activity controls can fail when an ordinary-scene rule is reused in an active minigame, or an optional notification is treated as mandatory. Required identity and settlement checks remain separate from those assumptions.
- Connection limits must be checked without a warm cache. Scan-byte exhaustion and elapsed-time limits are distinct failure stages.
- Version numbers and whole-file differences are reference information. Operation availability depends on the required runtime structures, with unrelated functions kept separate where possible.
- Native component reuse is a shared lifecycle concern. One successful button press or a restart does not establish that reuse and upgrade behavior are correct.
- Alchemy gained a spiritual-energy step; memory-stone replay required a missing date-field mapping. A readable list alone did not prove the action and settlement path.
- Final executable identity and a downloaded archive's contents matter independently of the displayed version. Source snapshots and binary checksums should be recorded separately.

## Connection reuse and limits

During the historical read optimization check, the existing native host stayed connected and idle before and after the reads. No injection, native game-method dispatch, host upgrade or unloading occurred; the native client, host and script were unchanged from the preceding v1.3 package.

That session did not cover a new host's cold start, native calls after reopening the trainer, alternating live activity writes, active learning settlement, or save/reload. Earlier game-effect confirmations remain earlier evidence. This source/documentation preparation added no game validation.
