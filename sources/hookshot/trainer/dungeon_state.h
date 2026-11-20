#pragma once
#include "dungeon_state_types.h"
#include "dungeon_state.generated.h"

/* QueryWorldInfoGetDungeonRoomID, retained f_82b23020 -> f_80853900 ->
 * f_82eecb60. Input actor identity belongs to the caller's current session.
 * This is the raw signed dungeon-room ID, not a MapParam room-list index. */
static int hk_dungeon_actor_room(uint64_t actor, int *room) {
    if (!room) return 0;
    *room = -1;
    if (!actor || !access_guest(actor + 624, 8, 1)) return 0;
    const uint64_t components = pointer_at(actor + 624);
    if (!components || !access_guest(components + 1120, 8, 1)) return 0;
    const uint64_t world_info = pointer_at(components + 1120);
    if (!world_info || !access_guest(world_info + 4468, 4, 1)) return 0;
    const int32_t value = (int32_t)hk_load32(world_info + 4468);
    if (value < 0 || components != pointer_at(actor + 624) ||
        world_info != pointer_at(components + 1120)) return 0;
    *room = value;
    return 1;
}

/* Exact retained v2.1.0 generated getter f_80858960 (and f_83781680):
 * GameDataMgr+3160 is count, +3168 is sorted data; 16-byte records contain
 * uint64 key at +0, live byte at +12. We use a bounded checked equivalent,
 * rather than calling a native getter that may probe beyond a missing key. */
static int hk_dungeon_bool64(uint64_t mgr, uint64_t hash, uint32_t *value) {
    if (!hash || !access_guest(mgr + 3160, 16, 1)) return 0;
    const uint32_t count = hk_load32(mgr + 3160);
    const uint64_t data = pointer_at(mgr + 3168);
    if (!count || count > 20000 || !access_guest(data, (uint64_t)count * 16, 1)) return 0;
    uint32_t low = 0, high = count;
    while (low < high) {
        const uint32_t mid = low + (high - low) / 2;
        const uint64_t key = pointer_at(data + (uint64_t)mid * 16);
        if (key < hash) low = mid + 1;
        else high = mid;
    }
    if (low >= count) return 0;
    const uint64_t entry = data + (uint64_t)low * 16;
    if (pointer_at(entry) != hash) return 0;
    /* A byte outside the documented Bool domain is unknown, not true. */
    const uint32_t live = *(const uint8_t *)GP(entry + 12);
    if (live > 1 || count != hk_load32(mgr + 3160) || data != pointer_at(mgr + 3168)) return 0;
    *value = live;
    return 1;
}

static int hk_dungeon_value(Ctx *c, uint64_t mgr,
                            const HkDungeonCondition *condition, uint32_t *value) {
    if (!condition || !condition->hash) return 0;
    if (condition->type == HK_DUNGEON_BOOL64)
        return hk_dungeon_bool64(mgr, condition->hash, value);
    if (condition->hash > UINT32_MAX) return 0;
    const uint32_t hash = (uint32_t)condition->hash;
    if (condition->type == HK_DUNGEON_BOOL) {
        int live = 0;
        if (!oot_gamedata_bool(c, hash, &live)) return 0;
        *value = (uint32_t)live;
        return 1;
    }
    if (condition->type == HK_DUNGEON_INT) {
        const uint64_t address = integer_field(mgr, hash);
        if (!address) return 0;
        *value = hk_load32(address);
        return 1;
    }
    if (condition->type == HK_DUNGEON_ENUM) {
        /* Retained f_808073d0: normal Enum table, stride 56, live +28. */
        const uint64_t entry = indexed_entry(mgr, hash, 0x250, 56);
        if (!entry) return 0;
        *value = hk_load32(entry + 0x1c);
        return 1;
    }
    return 0;
}

static uint8_t hk_dungeon_compare(const HkDungeonCondition *condition, uint32_t value) {
    int met;
    switch (condition->op) {
    case HK_DUNGEON_EQ: met = value == condition->expected; break;
    case HK_DUNGEON_NE: met = value != condition->expected; break;
    case HK_DUNGEON_GE:
        if (condition->type != HK_DUNGEON_INT) return HK_DUNGEON_UNKNOWN;
        met = (int32_t)value >= (int32_t)condition->expected; break;
    case HK_DUNGEON_LE:
        if (condition->type != HK_DUNGEON_INT) return HK_DUNGEON_UNKNOWN;
        met = (int32_t)value <= (int32_t)condition->expected; break;
    default: return HK_DUNGEON_UNKNOWN;
    }
    return met ? HK_DUNGEON_MET : HK_DUNGEON_UNMET;
}

static int hk_dungeon_state_read(Ctx *c, uint64_t mgr, int map, HkDungeonState *out) {
    if (!out) return 0;
    memset(out, 0, sizeof *out);
    out->room = -1;
    if (!c || !mgr || mgr != pointer_at(pointer_at(GDM_SLOT))) return 0;
    const uint64_t sp = c->x[31];
    if (sp < 0x1000 || !access_guest((sp - 0x1000) & ~15ull, 0x1000, 3)) return 0;
    const HkDungeonStateSlice *slice = NULL;
    for (int i = 0; i < HK_DUNGEON_STATE_SLICE_COUNT; ++i)
        if (hk_dungeon_state_slices[i].map == map) { slice = &hk_dungeon_state_slices[i]; break; }
    if (!slice || slice->count < 0 || slice->count > HK_DUNGEON_MAX_CONDITIONS ||
        slice->first < 0 || slice->first > HK_DUNGEON_CONDITION_COUNT - slice->count) return 0;
    out->map = map; out->first = slice->first; out->count = slice->count;
    for (int i = 0; i < slice->count; ++i) {
        const HkDungeonCondition *condition = &hk_dungeon_conditions[slice->first + i];
        uint32_t value = 0;
        if (hk_dungeon_value(c, mgr, condition, &value)) {
            out->values[i] = value;
            out->states[i] = hk_dungeon_compare(condition, value);
        }
    }
    if (mgr != pointer_at(pointer_at(GDM_SLOT))) {
        memset(out, 0, sizeof *out); out->room = -1; return 0;
    }
    out->stamp = GetTickCount64();
    return 1;
}
