#pragma once
#include "trainer_quest.h"
#include "dungeon_state.h"

/* One snapshot from the existing, identity-checked player callback. The renderer
 * never receives guest pointers and never calls guest code. */
static SRWLOCK hk_nav_lock = SRWLOCK_INIT;
static unsigned hk_nav_epoch;  /* odd: enabled; incremented on each toggle */
static uint64_t hk_nav_next, hk_nav_seen, hk_nav_generation;
static HkNavigation hk_nav_position;
static int hk_nav_quest_goal;
static HkQuestStatus hk_nav_quest_status;
static uint64_t hk_nav_quest_next, hk_nav_quest_generation;
static int hk_nav_quest_map;
static uint64_t hk_nav_data_manager;
static HkDungeonState hk_nav_dungeon;
static unsigned hk_nav_cache_epoch;

static int hk_quest_read(uint64_t mgr, HkQuestStatus *out) {
    uint32_t values[HK_QUEST_COUNT];
    for (int i = 0; i < HK_QUEST_COUNT; ++i) {
        /* f_808073d0: Enum table at 0x250, 56-byte entries, live value at +0x1c. */
        const uint64_t entry = mgr ? indexed_entry(mgr, hk_quests[i].hash, 0x250, 56) : 0;
        if (!entry) return 0;
        values[i] = hk_load32(entry + 0x1c);
    }
    return hk_quest_pick(values, out);
}

static int hk_nav_scene(const char *banc) {
    static const char *const names[] = {"",
#define HK_MAP_ID(name) #name,
#include "map_ids.generated.h"
#undef HK_MAP_ID
    };
    int low = 1, high = HK_MAP_COUNT;
    while (low < high) {
        const int mid = low + (high-low)/2;
        const int order = strcmp(banc, names[mid]);
        if (!order) return mid;
        if (order < 0) high = mid;
        else low = mid+1;
    }
    return HK_MAP_UNKNOWN;
}

static int hk_jabu_guide_step(uint64_t mgr) {
    const uint64_t entry = mgr ? indexed_entry(mgr, 0x5bca02a6u, 0x250, 56) : 0;
    if (!entry) return 0;
    switch (hk_load32(entry + 0x1c)) {
    case 0x5daeca58u: return 1;  /* Step09: first encounter. */
    case 0x0be69809u: return 2;  /* Step10: carry Ruto. */
    case 0x02428c32u: return integer(mgr, 0xa1d76d31u) == 1 ? 4 : 3;
    case 0xc25a29d8u: return 5;  /* Step12: Big Octo. */
    case 0x2f0ed242u:
    case 0xa6447454u: return 6;
    default: return 0;
    }
}

static void hk_navigation_set(int enabled) {
    AcquireSRWLockExclusive(&hk_nav_lock);
    const unsigned epoch = __atomic_load_n(&hk_nav_epoch, __ATOMIC_RELAXED);
    if ((epoch & 1u) != (unsigned)!!enabled) {
        hk_nav_seen = 0;
        hk_nav_next = 0;
        __atomic_store_n(&hk_nav_epoch, epoch + 1, __ATOMIC_RELAXED);
    }
    ReleaseSRWLockExclusive(&hk_nav_lock);
}

static int hk_navigation_sample(HkNavigation *out) {
    const TrainerStatus trainer = trainer_status();
    AcquireSRWLockShared(&hk_nav_lock);
    const int fresh = trainer.ready && trainer.generation == hk_nav_generation &&
        hk_nav_seen && GetTickCount64() - hk_nav_seen <= 350;
    if (fresh) *out = hk_nav_position;
    ReleaseSRWLockShared(&hk_nav_lock);
    return fresh;
}

static void hk_navigation_tick(Ctx *c, uint64_t actor) {
    if (!(__atomic_load_n(&hk_nav_epoch, __ATOMIC_RELAXED) & 1u)) return;
    const uint64_t now = GetTickCount64();
    AcquireSRWLockExclusive(&hk_nav_lock);
    const unsigned epoch = __atomic_load_n(&hk_nav_epoch, __ATOMIC_RELAXED);
    const int due = (epoch & 1u) && now >= hk_nav_next;
    if (due) hk_nav_next = now + 125;
    ReleaseSRWLockExclusive(&hk_nav_lock);
    if (!due) return;
    // This cache is owned by the player callback; the menu only changes epoch.
    if (hk_nav_cache_epoch != epoch) {
        hk_nav_cache_epoch = epoch;
        hk_nav_quest_next = 0;
        hk_nav_data_manager = 0;
        hk_nav_dungeon = (HkDungeonState){0};
    }

    char banc[64];
    int loading = 1;
    const uint64_t sp = c->x[31];
    const TrainerStatus trainer = trainer_status();
    HkNavigation pos = {0};
    int room_before = -1;
    int valid = trainer.ready && access_guest(actor + 796, 12, 1) && sp >= 0x1000 &&
        access_guest((sp - 0x1000) & ~15ull, 0x1000, 3) &&
        oot_gamedata_bool(c, 0xef2b60c2u, &loading) && !loading && /* Sequence_IsLoadingBanc */
        oot_gamedata_string(c, 0x1d6189dau, banc, sizeof banc); /* Sequence_CurrentBanc */
    if (valid) {
        pos.map = hk_nav_scene(banc);
        pos.x = oot_load_float(c, actor + 796);
        pos.y = oot_load_float(c, actor + 800);
        pos.z = oot_load_float(c, actor + 804);
        valid = isfinite(pos.x) && isfinite(pos.y) && isfinite(pos.z);
        int child = 0;
        pos.child = oot_gamedata_bool(c, 0xcea220d3u, &child) ? child : -1;
        const uint64_t mgr = pointer_at(pointer_at(GDM_SLOT));
        const int room_known = hk_dungeon_actor_room(actor, &room_before);
        if (pos.map == kMapInsideJabuJabuBelly) pos.guide_step = hk_jabu_guide_step(mgr);
        if (mgr && (now >= hk_nav_quest_next || hk_nav_data_manager != mgr ||
                    hk_nav_quest_generation != trainer.generation ||
                    hk_nav_quest_map != pos.map)) {
            hk_nav_quest_status = (HkQuestStatus){0};
            hk_nav_quest_goal = hk_quest_read(mgr, &hk_nav_quest_status) && hk_nav_quest_status.quest < HK_QUEST_COUNT ?
                hk_quests[hk_nav_quest_status.quest].steps[hk_nav_quest_status.step].map_region : 0;
            hk_nav_quest_next = now + 500;
            hk_nav_quest_generation = trainer.generation;
            hk_nav_quest_map = pos.map;
            hk_nav_data_manager = mgr;
            hk_nav_dungeon = (HkDungeonState){0};
            if (hk_dungeon_state_read(c, mgr, pos.map, &hk_nav_dungeon)) hk_nav_dungeon.stamp = now;
        }
        if (mgr && mgr == pointer_at(pointer_at(GDM_SLOT))) {
            pos.goal_region = hk_nav_quest_goal;
            pos.quest = hk_nav_quest_status.quest;
            pos.step = hk_nav_quest_status.step;
            if (hk_nav_dungeon.map == pos.map && hk_nav_dungeon.stamp &&
                now - hk_nav_dungeon.stamp <= 750) pos.dungeon = hk_nav_dungeon;
            pos.dungeon.room = room_known ? room_before : -1;
        }
        char after_banc[64];
        const TrainerStatus after = trainer_status();
        int room_after = -1;
        const int same_room = !room_known || (hk_dungeon_actor_room(actor, &room_after) && room_after == room_before);
        valid = valid && after.ready && after.generation == trainer.generation &&
            same_room &&
            mgr == pointer_at(pointer_at(GDM_SLOT)) &&
            oot_gamedata_bool(c, 0xef2b60c2u, &loading) && !loading &&
            oot_gamedata_string(c, 0x1d6189dau, after_banc, sizeof after_banc) && !strcmp(banc, after_banc);
    }
    if (!valid) {
        hk_nav_quest_next = 0;
        hk_nav_data_manager = 0;
        hk_nav_dungeon = (HkDungeonState){0};
    }

    AcquireSRWLockExclusive(&hk_nav_lock);
    if (__atomic_load_n(&hk_nav_epoch, __ATOMIC_RELAXED) == epoch) {
        hk_nav_position = pos;
        hk_nav_generation = trainer.generation;
        hk_nav_seen = valid ? now : 0;
    }
    ReleaseSRWLockExclusive(&hk_nav_lock);
}
