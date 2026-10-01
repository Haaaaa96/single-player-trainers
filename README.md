English | [简体中文](README_ZH.md)

# Single-Player Trainer Research

A personal record of experiments, implementation work and fixes for single-player game trainers.

This repository keeps selected source snapshots, development notes and versioned artifacts together. It documents what was attempted, what was observed and what remains unverified.

**Research archive, provided as-is.** Results are specific to the recorded environment. Compatibility with other computers, game versions or mod combinations, and the effects of using these tools, are not guaranteed. Use is at your own risk. No user support, issue intake, feature requests or ongoing maintenance is offered.

## Projects

| Project | Archived version | Approach | Explore |
|---|---|---|---|
| World Apart / 不问凡尘 | v1.3, read-performance revision | Standalone Python trainer with a shared native broker | [Overview](games/worldapart/README.md) · [Source](sources/worldapart) · [Development log](games/worldapart/DEVLOG.md) · [Artifacts](https://github.com/Haaaaa96/single-player-trainers/releases/tag/worldapart-v1.3-new) |
| House of Legacy / 吾今有世家 | v0.3.0, experimental | C# plugin for a Unity Mono game | [Overview](games/house-of-legacy/README.md) · [Source](sources/house-of-legacy) · [Development log](games/house-of-legacy/DEVLOG.md) · [Artifacts](https://github.com/Haaaaa96/single-player-trainers/releases/tag/house-of-legacy-v0.3.0) |
| Hero's Adventure / 大侠立志传 | WulinToyBox v1.1.0 | Revisions to an existing IL2CPP plugin | [Overview](games/wulin-toybox/README.md) · [Source](sources/wulin-toybox) · [Development log](games/wulin-toybox/DEVLOG.md) · [Artifacts](https://github.com/Haaaaa96/single-player-trainers/releases/tag/wulin-toybox-v1.1.0) |

## Background

The work began with small, local changes to game values and grew into experiments with object discovery, runtime validation, native-session reuse and in-game interfaces. The notes retain failed approaches and limited evidence as well as successful changes. The purpose is to preserve the research process, not to promise a maintained product.

## Technical approach

- **World Apart:** Python/Tk UI, IL2CPP metadata and object validation, bounded memory discovery, and a shared native broker for reviewed game calls. Feature-specific checks stay separate from version hints.
- **House of Legacy:** a BepInEx 5 plugin with guarded edits, pause ownership and input isolation while its window is open.
- **WulinToyBox:** targeted changes to the upstream plugin's data reads, search, lists, input handling and UI. Original dependencies and licenses remain separate.

## Source and development

Start with a project's `BUILD.md`. These are privacy-reviewed source snapshots, not a mirror of the private working directory or its Git history. Some build inputs belong to the game or third parties and are deliberately absent; the project notes list those gaps.

No game executable, game assembly, save, runtime log, credential or personal configuration is intentionally included in the source export. Source publication does not mean that a fresh build was tested this time or will reproduce an older executable byte for byte. The trainer interfaces themselves may still be Chinese.

- [Source scope and build entry points](sources/README.md)
- [Development method and lessons](docs/DEVELOPMENT.md)
- [Privacy and provenance boundaries](docs/PRIVACY.md)
- [Artifact checksums](releases.json)

## Repository layout

```text
README.md / README_ZH.md       English and Chinese entry points
games/<game>/                 Overview, operating notes and development log
sources/<game>/               Selected implementation, tests and build notes
docs/                         Development method and privacy boundaries
third_party/                  Required licenses and source/build materials
releases.json                 Archived artifact identities
```

Releases retain historical files. Their bundled wording may reflect an earlier publication style; it does not establish a support commitment. Automatic “Source code” downloads are repository snapshots, while named release assets identify the archived programs and separate dependency sources. A checksum identifies bytes, not safety or compatibility.

## Licensing

Original source is publicly readable; this publication does not silently apply a new open-source license to it. WulinToyBox and third-party components retain their existing licenses and required attribution. Game names and assets belong to their respective owners.

[Archive terms](TERMS.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)
