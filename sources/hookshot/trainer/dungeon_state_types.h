#pragma once
#include <stdint.h>
#include "dungeon_state_limits.generated.h"

enum HkDungeonValueType {
    HK_DUNGEON_BOOL = 1, HK_DUNGEON_INT = 2,
    HK_DUNGEON_ENUM = 3, HK_DUNGEON_BOOL64 = 4
};
enum HkDungeonComparison {
    HK_DUNGEON_EQ = 0, HK_DUNGEON_NE = 1,
    HK_DUNGEON_GE = 2, HK_DUNGEON_LE = 3
};
enum HkDungeonConditionState {
    HK_DUNGEON_UNKNOWN = 0, HK_DUNGEON_UNMET = 1, HK_DUNGEON_MET = 2
};
typedef struct {
    uint64_t hash;
    uint32_t expected;
    uint8_t type, op;
    uint16_t reserved;
} HkDungeonCondition;
typedef struct {
    int map, first, count;
} HkDungeonStateSlice;
/* No guest pointers cross the host/renderer ABI. The navigation publisher owns
 * generation, scene and age validation; first indexes the generated catalog.
 * room is -1 when unavailable; the navigation publisher maps the verified
 * WorldInfo raw room ID into the scene's MapParam room-list index. */
typedef struct {
    uint64_t stamp;
    int map, room, first, count;
    uint8_t states[HK_DUNGEON_MAX_CONDITIONS];
    uint32_t values[HK_DUNGEON_MAX_CONDITIONS];
} HkDungeonState;

static inline int hk_dungeon_condition_state(const HkDungeonState *state, int index) {
    if (!state || !state->stamp || state->count < 0 ||
        state->count > HK_DUNGEON_MAX_CONDITIONS || index < state->first ||
        index - state->first >= state->count) return HK_DUNGEON_UNKNOWN;
    return state->states[index - state->first];
}
