English | [简体中文](DEVLOG_ZH.md)

# ZaohuaTrainer development notes

## 2026-10-28 — alpha.52 permanent attribute pill kit

The item page now has a single button for 95 native best-quality permanent attribute pills, 100 each. This covers speed, combat stats, eight roots, cultivation efficiency, dantian, mind, luck and lifespan. Blood-evil pills, temporary recovery effects and pills without a native best-quality variant are excluded. It adds inventory without consuming pills or changing tolerance. Repeated clicks add another set; partial results are reported rather than retried automatically.

Selection is checked against the complete native catalog, independently of page filters. All entries and quantities are preflighted before dispatch; each item uses the existing ItemService path with readback. Session or metadata changes stop remaining requests, while an uncertain native call retains the existing pending-result lock. The item-page actions now use two rows. No hook, worker, injector or lifecycle replacement was added.

The actual-reference build has 146 identity-checked inputs. Thirteen focused offline groups cover the independent 95-ID catalog, exact quantities, repeat batches, exclusion, preflight and interruption; nine existing breakthrough groups also passed. Native inventory calls in these tests use bounded fixtures. The plugin remains uninstalled locally for this increment; Unity layout/input, real effects, action alternation, restart and save/reload remain unverified. This publication does not operate the game or saves.

Public version `0.12.0-alpha.52`, assembly `0.12.0.51`. The complete ZIP retains 23 loader and 14 third-party files from alpha.51 byte-for-byte, replacing only the plugin and versioned README. See the [project page](README.md) for package identity. The previous release remains archived.

## 2026-10-28 — alpha.51 archive

The cumulative plugin covers items, character and profession values, NPC/map helpers, dantian layouts, combat assistance and crafting references.

Recent work simplified layout application into one action: back up relevant state, learn missing entries, align fusion traits and equip the layout/spell bars. It also addressed startup readiness, shared fusion references, new-save comparisons with no corresponding equipment, and per-preset deletion.

The latest increment adds a custom spirit-stone amount of 1–100,000,000 per operation and a fixed standard breakthrough bundle: nine 筑基丹 and one each of nine other items. Blood-path pills are excluded. The batch uses the existing item execution path, stops on a failure or uncertain result, and does not automatically retry an unknown operation.

The production binary was built before publication against the local reference environment. Its 145 build inputs were identity-checked. Related offline checks covered currency boundaries and breakthrough batch behavior; the layout fixes have their own prior offline evidence. Those checks do not establish live game behavior.

The release package contains 39 files: the plugin, versioned README, 23 original loader files and 14 third-party notice/license/source files. Independent extraction and per-file hashes matched. No game assemblies, saves, logs or personal configuration are included.

## Historical alpha.51 verification boundaries

This is an in-process BepInEx plugin using its existing main-thread execution and lifecycle protections. No new external broker or injector was introduced by packaging. The alpha.51 live menu/input behavior, feature alternation, game restart, actual effects and save/reload remain unverified here. No game operation or runtime replacement was performed for this publication.

Public version: `0.12.0-alpha.51`; assembly version: `0.12.0.50`. Identify the artifact using the public version and hashes on the [project page](README.md). BepInEx is `6.0.0-be.788+5b766a3`; Harmony is `2.10.2.0`.

This publication contains the binary and these notes, not a trainer source snapshot or a reproducible-build claim. Dependency sources are included under their upstream licenses. No new feature work or wider compatibility campaign is implied.
