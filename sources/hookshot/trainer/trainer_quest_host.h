#pragma once
#include "trainer_quest.h"

static SRWLOCK hk_quest_lock = SRWLOCK_INIT;
static unsigned hk_quest_epoch;
static uint64_t hk_quest_next, hk_quest_seen, hk_quest_generation;
static HkQuestStatus hk_quest_current;

static void hk_quest_set(int enabled) {
    AcquireSRWLockExclusive(&hk_quest_lock);
    const unsigned epoch = __atomic_load_n(&hk_quest_epoch, __ATOMIC_RELAXED);
    if ((epoch & 1u) != (unsigned)!!enabled) {
        hk_quest_next = hk_quest_seen = 0;
        __atomic_store_n(&hk_quest_epoch, epoch + 1, __ATOMIC_RELAXED);
    }
    ReleaseSRWLockExclusive(&hk_quest_lock);
}

static int hk_quest_sample(HkQuestStatus *out) {
    const TrainerStatus trainer = trainer_status();
    AcquireSRWLockShared(&hk_quest_lock);
    const int fresh = trainer.ready && trainer.generation == hk_quest_generation &&
        hk_quest_seen && GetTickCount64() - hk_quest_seen <= 1100;
    if (fresh) *out = hk_quest_current;
    ReleaseSRWLockShared(&hk_quest_lock);
    return fresh;
}

static void hk_quest_tick(Ctx *c) {
    if (!(__atomic_load_n(&hk_quest_epoch, __ATOMIC_RELAXED) & 1u)) return;
    const uint64_t now = GetTickCount64();
    AcquireSRWLockExclusive(&hk_quest_lock);
    const unsigned epoch = __atomic_load_n(&hk_quest_epoch, __ATOMIC_RELAXED);
    const int due = (epoch & 1u) && now >= hk_quest_next;
    if (due) hk_quest_next = now + 300;
    ReleaseSRWLockExclusive(&hk_quest_lock);
    if (!due) return;

    const TrainerStatus trainer = trainer_status();
    const uint64_t sp = c->x[31];
    int loading = 1;
    int valid = trainer.ready && sp >= 0x1000 &&
        access_guest((sp - 0x1000) & ~15ull, 0x1000, 3) &&
        oot_gamedata_bool(c, 0xef2b60c2u, &loading) && !loading;
    HkQuestStatus status = {0};
    if (valid) {
        const uint64_t mgr = pointer_at(pointer_at(GDM_SLOT));
        valid = hk_quest_read(mgr, &status);
        if (valid) {
            char banc[80];
            if (oot_gamedata_string(c, 0x1d6189dau, banc, sizeof banc)) {
                status.guide = hk_dungeon_index(banc);
                if (!strcmp(banc, "InsideJabuJabuBelly")) status.guide_step = hk_jabu_guide_step(mgr);
            }
        }
        if (valid) valid = mgr == pointer_at(pointer_at(GDM_SLOT)) &&
            oot_gamedata_bool(c, 0xef2b60c2u, &loading) && !loading;
    }
    AcquireSRWLockExclusive(&hk_quest_lock);
    if (__atomic_load_n(&hk_quest_epoch, __ATOMIC_RELAXED) == epoch) {
        hk_quest_current = status;
        hk_quest_generation = trainer.generation;
        hk_quest_seen = valid ? now : 0;
    }
    ReleaseSRWLockExclusive(&hk_quest_lock);
}
