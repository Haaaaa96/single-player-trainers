#pragma once

// Authored instructions bind to resource actors and typed runtime conditions.
// A location can be reached without completing its puzzle.
struct HkDungeonStep {
    int map, age, floor, room;
    float x, y, z;
    uint64_t actor;
    const wchar_t *title, *action, *detail, *transition;
    int first_prerequisite, prerequisites, first_completion, completions;
    bool any_completion, final;
};

struct HkDungeonGateRule {
    int first, count;
    bool any;
};
// Later native completion may supersede an instruction without opening its gate.
struct HkDungeonAdvanceRule { int first, count; };
struct HkDungeonRestrictedRoom { int map, room; };
struct HkDungeonInventory { int map, small_key, boss_key, water_level; };
