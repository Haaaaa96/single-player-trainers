#pragma once

/* f_80f40f90 resolves the magic component from actor->components.
   f_801839b0 copies its live MP at +7100 to GameData, in tenths of MP. */
#define HK_MAGIC_HASH 0x76b18200u
#define HK_MAGIC_MAX_HASH 0x12d63a97u
#define HK_MAGIC_VTABLE 0x84b6dfc0ull
#define HK_MAGIC_CURRENT_OFFSET 7100

static struct { uint64_t deadline, generation, address; int maximum; } hk_magic_pending;

static uint64_t hk_magic_component(uint64_t actor) {
    const uint64_t components = pointer_at(actor + 624);
    return components ? pointer_at(components + 856) : 0;
}

static HkMagicStatus hk_magic_sample(uint64_t mgr, uint64_t link, uint64_t actor, int ready,
                                    uint64_t *address) {
    const HkMagicStatus unavailable = {-1, -1};
    if (!ready) return unavailable;
    const int maximum = integer(mgr, HK_MAGIC_MAX_HASH);
    if (maximum == 0) return (HkMagicStatus){0, 0};
    if (maximum != 240 && maximum != 480) return unavailable;

    const uint64_t component = hk_magic_component(actor);
    if (!component || pointer_at(component) != HK_MAGIC_VTABLE ||
        pointer_at(component + 24) != actor || pointer_at(link + 24) != actor ||
        !access_guest(component + 7088, 16, 1) ||
        LD32(component + 7088) != HK_MAGIC_HASH || LD32(component + 7092) != HK_MAGIC_MAX_HASH)
        return unavailable;
    const uint64_t current_address = component + HK_MAGIC_CURRENT_OFFSET;
    const int current = (int32_t)LD32(current_address);
    if (current < 0 || current > maximum) return unavailable;
    *address = current_address;
    return (HkMagicStatus){current, maximum};
}

static HkMagicStatus hk_magic_tick(uint64_t mgr, uint64_t link, uint64_t actor, uint64_t now,
                                  uint64_t generation, int ready, int action, unsigned flags,
                                  char *result, size_t size, int *settled) {
    const int refill = action == HK_TRAINER_REFILL_MAGIC;
    uint64_t address = 0;
    HkMagicStatus sample = hk_magic_sample(mgr, link, actor,
        ready && action != HK_TRAINER_TELEPORT && !hk_teleport.deadline, &address);
    if (hk_magic_pending.deadline) {
        const char *message = NULL;
        if (generation != hk_magic_pending.generation || address != hk_magic_pending.address ||
            sample.maximum != hk_magic_pending.maximum)
            message = "场景或魔力状态已变化，补充结果未确认。";
        else if (sample.current == sample.maximum && integer(mgr, HK_MAGIC_HASH) == sample.maximum)
            message = "魔力已补满。";
        else if (now >= hk_magic_pending.deadline)
            message = "游戏尚未确认魔力已补满，请查看当前魔力。";
        if (message) {
            hk_magic_pending.deadline = 0;
            *settled = 1;
            snprintf(result, size, "%s", message);
        }
        return sample;
    }

    if (sample.maximum <= 0) {
        if (refill) snprintf(result, size, "%s", sample.maximum == 0 ?
                             "当前存档尚未解锁魔力槽。" : "暂时无法读取角色魔力。");
        return sample;
    }
    if (!refill && (!(flags & HK_PREF_MAGIC) || sample.current == sample.maximum)) return sample;
    if (refill && sample.current == sample.maximum && integer(mgr, HK_MAGIC_HASH) == sample.maximum) {
        snprintf(result, size, "当前魔力已满。");
        return sample;
    }

    const uint64_t loading = indexed_entry(mgr, 0xef2b60c2u, 0x10, 24);
    if (!loading || (LD8(loading+22) & 1) || pointer_at(pointer_at(GDM_SLOT)) != mgr ||
        hk_magic_component(actor) != address - HK_MAGIC_CURRENT_OFFSET ||
        integer(mgr, HK_MAGIC_MAX_HASH) != sample.maximum) {
        if (refill) snprintf(result, size, "场景或魔力上限已变化，请稍后重试。");
        return (HkMagicStatus){-1, -1};
    }
    if (!write_integer(address, sample.current, sample.maximum)) {
        if (refill) snprintf(result, size, "角色魔力已变化，请稍后重试。");
        return sample;
    }
    if (refill)
        hk_magic_pending = (typeof(hk_magic_pending)){now + 1200, generation, address, sample.maximum};
    sample.current = sample.maximum;
    return sample;
}
