#pragma once

enum { HK_AMMO_TYPES = sizeof hkAmmoIds / sizeof *hkAmmoIds };
static struct {
    uint64_t generation, deadline;
    unsigned epoch;
    int baseline[HK_AMMO_TYPES], blocked[HK_AMMO_TYPES];
    int item[HK_AMMO_TYPES], built;
    int pending_type, target;
} hk_ammo;

static int hk_ammo_tick(Ctx *c, uint64_t sp, uint64_t mgr, uint64_t now,
                        uint64_t generation, int ready, int manual_item, int manual_result, int manual_request,
                        HkTrainerPrefs prefs) {
    if (hk_ammo.generation != generation) {
        hk_ammo.generation = generation;
        hk_ammo.deadline = 0;
        for (int i = 0; i < HK_AMMO_TYPES; ++i) hk_ammo.baseline[i] = -1, hk_ammo.blocked[i] = 0;
    }
    if (hk_ammo.epoch != prefs.ammo_epoch) {
        hk_ammo.epoch = prefs.ammo_epoch;
        for (int i = 0; i < HK_AMMO_TYPES; ++i) hk_ammo.baseline[i] = -1, hk_ammo.blocked[i] = 0;
    }
    const int enabled = !!(prefs.flags & HK_PREF_AMMO);
    if (!ready || (!enabled && !hk_ammo.deadline)) return 0;
    if (!hk_ammo.built) {
        for (int k = 0; k < HK_AMMO_TYPES; ++k) {
            hk_ammo.item[k] = -1;
            for (int i = 0; i < trainer_item_count; ++i)
                if (!strcmp(trainer_items[i].actor, hkAmmoIds[k])) {
                    hk_ammo.item[k] = i;
                    break;
                }
        }
        hk_ammo.built = 1;
    }

    if (hk_ammo.deadline) {
        const int k = hk_ammo.pending_type;
        const TrainerItem *item = &trainer_items[hk_ammo.item[k]];
        const int have = integer(mgr, item->stock);
        if (have >= hk_ammo.target && pouch_ready() && pouch_count(c, sp, item->actor) == have) {
            hk_ammo.deadline = 0;
            hk_ammo.baseline[k] = have;
        } else if (now >= hk_ammo.deadline) {
            hk_ammo.deadline = 0;
            hk_ammo.blocked[k] = 1;
            hos_log("trainer: ammo refill not confirmed for %s; stopped until re-enabled or scene changes", item->actor);
        } else {
            return 1;
        }
    }
    if (!enabled) return 0;

    for (int k = 0; k < HK_AMMO_TYPES; ++k) {
        const int index = hk_ammo.item[k];
        if (index < 0 || hk_ammo.blocked[k]) continue;
        if (index == manual_item && manual_result < 0) {
            hk_ammo.blocked[k] = 1;
            continue;
        }
        const TrainerItem *item = &trainer_items[index];
        if (!item->stock || !item->capacity || item->restriction[0]) continue;
        const int have = integer(mgr, item->stock), capacity = integer(mgr, item->capacity);
        if (capacity <= 0 || capacity > 1000 || have < 0 || have > capacity) continue;
        int *baseline = &hk_ammo.baseline[k];
        if (manual_item == index || *baseline > capacity || have >= *baseline) {
            *baseline = have;
            continue;
        }
        if (manual_request || manual_item >= 0 || !pouch_ready() || sp < 0x3000 ||
            !access_guest((sp-0xe0) & ~15ull, 0xe0, 3) || pouch_count(c, sp, item->actor) != have)
            continue;
        if (oot_pouch_change(c, item->actor, *baseline-have) < 0) {
            hk_ammo.blocked[k] = 1;
            continue;
        }
        hk_ammo.pending_type = k;
        hk_ammo.target = *baseline;
        hk_ammo.deadline = GetTickCount64() + 750;
        return 1;
    }
    return 0;
}
