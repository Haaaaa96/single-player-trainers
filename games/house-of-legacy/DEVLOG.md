# House of Legacy — Development notes

**English** | [简体中文](DEVLOG_ZH.md)

[Overview](README.md) · [Source](../../sources/house-of-legacy) · [Build](../../sources/house-of-legacy/BUILD.md) · [Terms](../../TERMS.md)

Summary of the v0.3.0 record dated 2026-10-01. The sanitized public snapshot needs local game/framework assemblies. It was not built or run in this preparation and is not claimed to reproduce the historical DLL exactly.

## Revision focus

v0.3.0 made the window available directly from normal play and the character page through Tab, retained the original page alongside the left-side plugin window, and refreshed it after checking character identity. Opening/closing preserves the earlier pause and speed state. Input changes covered Tab in text boxes, repeated toggling, focus loss and migration from the old default F8 key.

## Historical checks

- Normal-play/character-page Tab, text-field Tab, repeated toggles, click/scroll/Esc isolation and input restoration; default layout at 1280×720 and 1920×1080.
- Pausing and speed restoration at 1× and 3×; rejection during loading.
- Literary talent, money, family reputation without crossing a level, and charm: representative changes persisted after normal save, exit, restart and load. Character-page synchronization was checked where applicable.
- Creation-page point editing and subsequent trait-point deduction; final creation of a new character was not confirmed.
- Game startup with the plugin disabled, then installation from a freshly extracted package and loading again.

## Unverified or limited

Other attribute writes/persistence, rapid character switching, reputation level changes, vegetable quantity/capacity changes, saving a newly created character and long-term growth settlement were not fully checked. Held-key behavior, returning while holding keys, 5×/10× speed, single-day advancement, save-in-progress and transaction-page rejection, and other MOD combinations remain unverified. Automated title-bar dragging showed no movement; the cause was not established.

These are historical checks of an in-game plugin, not evidence for an external native-host reuse path. No new lifecycle or game tests were added in this source/documentation preparation.
