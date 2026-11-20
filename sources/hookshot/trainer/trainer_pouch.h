#include "bottles.generated.h"

enum { HK_BOTTLE_ADD = 1, HK_BOTTLE_ADD_THEN_FILL, HK_BOTTLE_FILL, HK_BOTTLE_REMOVE };
typedef struct { unsigned owned; uint32_t content[5]; } HkBottleSnapshot;

static struct {
    uint64_t deadline;
    int item, before, delta, capacity;
    char actor[96];
    int bottle_phase, bottle_slot, new_bottle;
    HkBottleSnapshot bottles;
} awaiting;

/* The five BottleA–E structs each link an Int stock field and a content Enum. */
static const uint32_t hk_bottle_slots[] = {0xd53ce3a7u, 0xfca29a04u, 0x893216a1u, 0x5324f9d3u, 0xc92b16beu};
static const uint32_t hk_bottle_enums[] = {0x7d48df76u, 0x1edd164au, 0xb80c70a8u, 0xe4c1b1fcu, 0x365e1953u};
/* IsGet belongs to the content struct, not the separate Stock struct. Native
 * add selects the first false IsGet; removal must free it as well as Stock. */
static const uint32_t hk_bottle_ownership_keys[] = {0xf39ce410u, 0x000ff6eau, 0xf63b1194u, 0xb7f052ceu, 0xe27b136du};

static int hk_bottle_ownership(uint64_t mgr, unsigned *owned) {
    unsigned mask = 0;
    for (unsigned i = 0; i < ARRAYSIZE(hk_bottle_ownership_keys); ++i) {
        const uint64_t entry = indexed_entry(mgr, hk_bottle_ownership_keys[i], 0x10, 24);
        /* The verified Bool table's live/save bytes are +22/+23. */
        if (!entry || LD8(entry+0x16) > 1 || LD8(entry+0x16) != LD8(entry+0x17)) return 0;
        mask |= (unsigned)LD8(entry+0x16) << i;
    }
    *owned = mask;
    return 1;
}

static int hk_bottle_sample(uint64_t mgr, HkBottleSnapshot *out) {
    HkBottleSnapshot bottles = {0};
    for (unsigned i = 0; i < ARRAYSIZE(hk_bottle_slots); ++i) {
        const int stock = integer(mgr, hk_bottle_slots[i]);
        const uint64_t entry = indexed_entry(mgr, hk_bottle_enums[i], 0x250, 56);
        if (stock < 0 || stock > 1 || !entry || LD64(entry) != 0x84c40898ull) return 0;
        const uint32_t content = LD32(entry + 0x1c);
        unsigned type = 0;
        while (type < ARRAYSIZE(hk_bottle_values) && hk_bottle_values[type] != content) ++type;
        if (type == ARRAYSIZE(hk_bottle_values)) return 0;
        bottles.owned |= (unsigned)stock << i;
        bottles.content[i] = content;
    }
    *out = bottles;
    return 1;
}

static int hk_bottle_first_empty(const HkBottleSnapshot *bottles) {
    for (unsigned i = 0; i < ARRAYSIZE(bottles->content); ++i)
        if ((bottles->owned & (1u << i)) && bottles->content[i] == HK_BOTTLE_EMPTY) return i;
    return -1;
}

/* Native current-item lookup f_8019b6e0 selects these saved Adult/Child enums.
 * Keep both age assignments intact; an assigned bottle must be unequipped first. */
static const uint32_t hk_bottle_assignment_keys[] = {0xbc32ce24u, 0xa0029837u};
static const uint32_t hk_bottle_assignment_values[] = {
    0x22c7238cu, 0xac889fd5u, 0xa7d94611u, 0xb55ee4e3u, 0xd8cc3008u
};

static int hk_bottle_stable(uint64_t mgr, const HkBottleSnapshot *bottles) {
    for (unsigned i = 0; i < ARRAYSIZE(hk_bottle_slots); ++i) {
        const uint64_t stock = integer_field(mgr, hk_bottle_slots[i]);
        const uint64_t content = indexed_entry(mgr, hk_bottle_enums[i], 0x250, 56);
        const unsigned owned = (bottles->owned >> i) & 1u;
        if (!stock || !access_guest(stock, 8, 1) || !content ||
            LD64(content) != 0x84c40898ull || LD32(stock) != owned || LD32(stock+4) != owned ||
            LD32(content+0x1c) != bottles->content[i] || LD32(content+0x20) != bottles->content[i]) return 0;
    }
    return 1;
}

static int hk_bottle_assigned(uint64_t mgr, unsigned *assigned) {
    unsigned mask = 0;
    for (unsigned k = 0; k < ARRAYSIZE(hk_bottle_assignment_keys); ++k) {
        const uint64_t entry = indexed_entry(mgr, hk_bottle_assignment_keys[k], 0x250, 56);
        if (!entry || LD64(entry) != 0x84c40898ull || LD32(entry+0x1c) != LD32(entry+0x20)) return 0;
        for (unsigned i = 0; i < ARRAYSIZE(hk_bottle_assignment_values); ++i)
            if (LD32(entry+0x1c) == hk_bottle_assignment_values[i]) mask |= 1u << i;
    }
    *assigned = mask;
    return 1;
}

static int hk_bottle_remove(Ctx *c, uint64_t sp, int index, uint64_t mgr,
                            const HkBottleSnapshot *bottles, char *result, size_t size) {
    unsigned assigned = 0, owned = 0;
    if (!hk_bottle_stable(mgr, bottles) || !hk_bottle_assigned(mgr, &assigned) ||
        !hk_bottle_ownership(mgr, &owned) || owned != bottles->owned) {
        snprintf(result, size, "瓶槽或道具栏正在同步，请稍后重试。");
        return 0;
    }
    int slot = -1, empty_count = 0;
    for (int i = 4; i >= 0; --i) {
        if (!(bottles->owned & (1u << i)) || bottles->content[i] != HK_BOTTLE_EMPTY) continue;
        ++empty_count;
        if (slot < 0 && !(assigned & (1u << i))) slot = i;
    }
    if (slot < 0) {
        snprintf(result, size, "%s", empty_count ?
            "空瓶已分配到童年或成年道具栏，请先切换为其他道具。" : "没有可删除的空瓶；装有内容的瓶子会保留。");
        return 0;
    }
    if (!hk_remove_empty_bottle(c, sp, mgr, hk_bottle_slots[slot], hk_bottle_ownership_keys[slot])) return 0;
    awaiting = (typeof(awaiting)){.deadline = GetTickCount64()+2500, .item = index,
        .bottle_phase = HK_BOTTLE_REMOVE, .bottle_slot = slot, .bottles = *bottles};
    hos_log("trainer: dispatched empty bottle removal slot=%d before=%x", slot, bottles->owned);
    return 1;
}

static int hk_bottle_content_index(const char *actor) {
    for (unsigned i = 0; i < ARRAYSIZE(hk_bottle_contents); ++i)
        if (!strcmp(actor, hk_bottle_contents[i].actor)) return i;
    return -1;
}

static int hk_bottle_dispatch_fill(Ctx *c, uint64_t sp, int slot, const HkBottleSnapshot *bottles) {
    const int content = hk_bottle_content_index(trainer_items[awaiting.item].actor);
    if (content < 0 || !pouch_ready() || hk_bottle_first_empty(bottles) != slot ||
        !hk_push_to_empty_bottle(c, sp, hk_bottle_contents[content].type)) return 0;
    awaiting.bottle_phase = HK_BOTTLE_FILL;
    awaiting.bottle_slot = slot;
    awaiting.bottles = *bottles;
    awaiting.deadline = GetTickCount64()+2500;
    hos_log("trainer: dispatched bottle fill %s slot=%d", trainer_items[awaiting.item].actor, slot);
    return 1;
}

static int hk_bottle_start(Ctx *c, uint64_t sp, int index, int delta, uint64_t mgr, char *result, size_t size) {
    const TrainerItem *item = &trainer_items[index];
    const int empty = hk_is_empty_bottle(item);
    if (awaiting.deadline) {
        snprintf(result, size, "上一项道具操作尚未完成。");
        return 0;
    }
    if (delta != 1 && !(empty && delta == -1)) {
        snprintf(result, size, "每次可增删 1 个空瓶；有内容的瓶子不能直接删除。");
        return 0;
    }
    HkBottleSnapshot bottles;
    if ((!empty && hk_bottle_content_index(item->actor) < 0) || !pouch_ready() ||
        !hk_bottle_sample(mgr, &bottles) || sp < 0x3000 ||
        !access_guest((sp - 0x1000) & ~15ull, 0x1000, 3)) return 0;

    if (delta == -1) return hk_bottle_remove(c, sp, index, mgr, &bottles, result, size);

    const int slot = hk_bottle_first_empty(&bottles);
    if (!empty && slot >= 0) {
        awaiting = (typeof(awaiting)){.item = index};
        return hk_bottle_dispatch_fill(c, sp, slot, &bottles);
    }
    if (__builtin_popcount(bottles.owned) == ARRAYSIZE(hk_bottle_slots)) {
        snprintf(result, size, "%s", empty ? "瓶槽已满。" : "没有空瓶，瓶槽也已满。");
        return 0;
    }
    const int event_code = oot_pouch_change(c, "Item_Bottle", 1);
    if (event_code < 0) return 0;
    awaiting = (typeof(awaiting)){.deadline = GetTickCount64()+2500, .item = index, .bottles = bottles,
                                  .bottle_phase = empty ? HK_BOTTLE_ADD : HK_BOTTLE_ADD_THEN_FILL};
    hos_log("trainer: dispatched empty bottle before=%x event=%d", bottles.owned, event_code);
    return 1;
}

static int hk_pouch_change(Ctx *c, uint64_t sp, int index, int delta, uint64_t mgr,
                           char *result, size_t size) {
    const TrainerItem *item = &trainer_items[index];
    if (!item->restriction[0] && (hk_is_empty_bottle(item) || hk_is_bottle_content(item)))
        return hk_bottle_start(c, sp, index, delta, mgr, result, size);
    if (!item->stock || item->restriction[0] || !delta || delta < -1000 || delta > 1000 || !pouch_ready())
        return 0;
    const int have = integer(mgr, item->stock);
    const int cap = item->capacity ? integer(mgr, item->capacity) : item->maximum;
    if (have < 0 || cap <= 0 || have > cap || cap > 1000 || delta > cap-have) return 0;

    const char *actor = item->actor;
    int held = pouch_count(c, sp, actor);
    char mask_alias[sizeof awaiting.actor];
    if (delta < 0 && held == 0 && have > 0 && !strncmp(actor, "Item_Mask_", 10)) {
        const int length = snprintf(mask_alias, sizeof mask_alias, "Armor_Child_Mask_%s", actor+10);
        if (length < 0 || (size_t)length >= sizeof mask_alias) return 0;
        actor = mask_alias;
        held = pouch_count(c, sp, actor);
    }
    if (held != have) return 0;
    if (delta < -have) {
        snprintf(result, size, "持有数量不足，当前有 %d 个。", have);
        return 0;
    }
    if (sp < 0x3000 || !access_guest((sp - 0xe0) & ~15ull, 0xe0, 3)) return 0;
    const int event_code = oot_pouch_change(c, actor, delta);
    if (event_code < 0) return 0;

    awaiting = (typeof(awaiting)){.deadline = GetTickCount64()+2500, .item = index,
                                  .before = have, .delta = delta, .capacity = cap};
    snprintf(awaiting.actor, sizeof awaiting.actor, "%s", actor);
    hos_log("trainer: dispatched %s request=%+d before=%d event=%d", actor, delta, have, event_code);
    return 1;
}

static int hk_bottle_poll(Ctx *c, uint64_t sp, uint64_t mgr, uint64_t now, char *result, size_t size) {
    HkBottleSnapshot bottles;
    const HkBottleSnapshot *before = &awaiting.bottles;
    const int phase = awaiting.bottle_phase;
    if (hk_bottle_sample(mgr, &bottles)) {
        if (phase == HK_BOTTLE_REMOVE) {
            const unsigned expected = before->owned & ~(1u << awaiting.bottle_slot);
            unsigned owned = 0, assigned = 0;
            if (bottles.owned == expected && !memcmp(bottles.content, before->content, sizeof bottles.content) &&
                hk_bottle_stable(mgr, &bottles) && hk_bottle_ownership(mgr, &owned) && owned == expected &&
                hk_bottle_assigned(mgr, &assigned) && !(assigned & (1u << awaiting.bottle_slot))) {
                snprintf(result, size, "已删除 1 个空瓶（剩余 %d 个瓶子）。", __builtin_popcount(bottles.owned));
                awaiting.deadline = 0;
                return 1;
            }
        } else if (phase == HK_BOTTLE_FILL) {
            const int content = hk_bottle_content_index(trainer_items[awaiting.item].actor);
            HkBottleSnapshot expected = *before;
            expected.content[awaiting.bottle_slot] = hk_bottle_contents[content].value;
            if (bottles.owned == expected.owned && !memcmp(bottles.content, expected.content, sizeof bottles.content)) {
                snprintf(result, size, "%s", awaiting.new_bottle ? "已添加新瓶并装入所选材料。" : "已装入原有空瓶。");
                awaiting.deadline = 0;
                return 1;
            }
        } else {
            const unsigned added = bottles.owned & ~before->owned;
            if ((bottles.owned & before->owned) == before->owned && __builtin_popcount(added) == 1) {
                const int slot = __builtin_ctz(added);
                HkBottleSnapshot expected = *before;
                expected.content[slot] = HK_BOTTLE_EMPTY;
                if (!memcmp(bottles.content, expected.content, sizeof bottles.content)) {
                    if (phase == HK_BOTTLE_ADD) {
                        snprintf(result, size, "已添加 1 个空瓶（已使用 %d 个瓶槽）。", __builtin_popcount(bottles.owned));
                        awaiting.deadline = 0;
                        return 1;
                    }
                    awaiting.new_bottle = 1;
                    if (now < awaiting.deadline && hk_bottle_dispatch_fill(c, sp, slot, &bottles)) return 0;
                    snprintf(result, size, "已添加空瓶，当前无法装瓶。");
                    awaiting.deadline = 0;
                    return -1;
                }
            }
        }
    }
    if (now < awaiting.deadline) return 0;
    snprintf(result, size, "%s", phase == HK_BOTTLE_REMOVE ? "空瓶删除结果未确认，请先查看背包，勿重复操作。" :
        phase == HK_BOTTLE_FILL ? (awaiting.new_bottle ?
        "已添加空瓶，装瓶结果未确认，请查看背包。" : "装瓶结果未确认，请查看背包。") :
        "空瓶添加结果未确认，请查看背包。");
    awaiting.deadline = 0;
    return -1;
}

static int hk_pouch_poll(Ctx *c, uint64_t sp, uint64_t mgr, uint64_t now, char *result, size_t size) {
    if (awaiting.bottle_phase) return hk_bottle_poll(c, sp, mgr, now, result, size);
    const TrainerItem *item = &trainer_items[awaiting.item];
    const int count = integer(mgr, item->stock);
    const int expected = awaiting.before + awaiting.delta;
    const int removed = awaiting.delta < 0;
    int confirmed = 1;
    if (count >= 0 && count <= awaiting.capacity && (removed ? count == expected : count >= expected) &&
        pouch_ready() && pouch_count(c, sp, awaiting.actor) == count) {
        if (removed)
            snprintf(result, size, "已删除 %d 个（剩余 %d 个）。", awaiting.before-count, count);
        else
            snprintf(result, size, "已增加 %d 个（当前 %d / %d）。", count-awaiting.before, count, awaiting.capacity);
    } else if (now >= awaiting.deadline) {
        snprintf(result, size, "结果未确认，请先查看背包。");
        confirmed = -1;
    } else {
        return 0;
    }
    awaiting.deadline = 0;
    return confirmed;
}
