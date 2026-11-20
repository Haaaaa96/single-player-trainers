#include "trainer.h"
#include "items.generated.h"
#include "trainer_api.h"
#include "trainer_prefs.h"

static int hk_in_range(uint64_t address, uint64_t size, uint64_t base, uint64_t length) {
    return address >= base && size <= length && address - base <= length - size;
}

static int access_guest(uint64_t address, uint64_t size, unsigned permission) {
    if (!address || !size || address >= HOS_SPACE_END || size > HOS_SPACE_END - address) return 0;
    if (hk_in_range(address, size, HOS_HEAP_BASE, hos_heap_size)) return 1;
    if (!(permission & 2) && hk_in_range(address, size, hos_image_base, hos_image_end - hos_image_base)) return 1;
    uint64_t stack = 0, stack_size = 0;
    hos_thread_stack(hos_self(), &stack, &stack_size);
    return hk_in_range(address, size, stack, stack_size);
}

static uint64_t hk_load64(uint64_t a) {
    uint64_t result;
    memcpy(&result, GP(a), sizeof result);
    return result;
}

static uint32_t hk_load32(uint64_t a) {
    uint32_t result;
    memcpy(&result, GP(a), sizeof result);
    return result;
}

#define LD64 hk_load64
#define LD32 hk_load32
#define LD8(a) (*(const uint8_t *)GP(a))

/* OneShotPushToEmptyBottle. The game's event selects the first owned empty slot. */
static int hk_push_to_empty_bottle(Ctx *c, uint64_t sp, int type) {
    const A64Fn push = a64_lookup(0x829364c0ull);
    const uint64_t frame = (sp - 0x80) & ~15ull;
    if (!push || sp < 0x1000 || !access_guest((sp - 0x1000) & ~15ull, 0x1000, 3)) return 0;
    const Ctx saved = *c;
    memset(GP(frame), 0, 0x80);
    recomp_store64_sp(c, frame+32, frame+0x60);
    recomp_store64_sp(c, frame+40, frame+0x64);
    recomp_store64_sp(c, frame+48, frame+0x68);
    recomp_store32_sp(c, frame+0x60, (uint32_t)type);
    recomp_store32_sp(c, frame+0x68, UINT32_MAX); /* No Poe minigame parameter. */
    c->x[31] = c->x[0] = frame;
    push(c);
    *c = saved;
    return 1;
}

/* Native scalar Int queue used by bottle addition, plus its Bool ownership
 * setter. IsGet gates reuse of BottleA-E; Stock alone is insufficient. The
 * scalar queue avoids f_83768270's unrelated IntArray-priority lookup. */
static int hk_remove_empty_bottle(Ctx *c, uint64_t sp, uint64_t mgr, uint32_t hash, uint32_t owned_hash) {
    const A64Fn change = a64_lookup(0x8378a620ull);
    const A64Fn clear = a64_lookup(0x806a2b20ull);
    if (!change || !clear || !hash || !owned_hash || !access_guest(mgr+200, 64, 1) ||
        !access_guest(mgr+16, 56, 1) || sp < 0x1000 ||
        !access_guest((sp-0x1000) & ~15ull, 0x1000, 3)) return 0;
    const uint32_t capacity = LD32(mgr+240), count = LD32(mgr+256) & 0xfffffu;
    const uint64_t queue = LD64(mgr+248);
    const uint32_t bool_capacity = LD32(mgr+48), bool_count = LD32(mgr+64) & 0xfffffu;
    const uint64_t bool_queue = LD64(mgr+56);
    if (!capacity || capacity > 0xfffffu || count >= capacity ||
        !access_guest(queue, (uint64_t)capacity*12, 3) || !bool_capacity || bool_capacity > 0xfffffu ||
        bool_count >= bool_capacity || !access_guest(bool_queue, (uint64_t)bool_capacity*8, 3)) return 0;
    const Ctx saved = *c;
    const uint64_t frame = (sp-0x20) & ~15ull;
    recomp_store32_sp(c, frame, UINT32_MAX); /* signed delta -1 */
    recomp_store32_sp(c, frame+4, hash);
    c->x[31] = frame;
    c->x[0] = mgr+200;
    c->x[1] = hash;
    c->x[2] = frame;
    change(c);
    *c = saved;
    c->x[31] = frame;
    c->x[0] = mgr;
    c->x[1] = 0;
    c->x[2] = owned_hash;
    clear(c);
    *c = saved;
    return 1; /* The asynchronous readback, not this return, confirms removal. */
}

#include "trainer_teleport.h"
#include "core.generated.h"
#undef LD8
#undef LD32
#undef LD64
#include "trainer_navigation.h"
#include "trainer_quest_host.h"
#include "trainer_flight_host.h"

extern void hk_text_focus(int);
extern int hk_take_text(uint16_t *, int);
extern int hk_composing(void);
extern int hk_take_hotkey(void);
extern void hk_pad_flight_context(uint64_t generation, int allowed);

__declspec(dllexport) const HkTrainerApi *hookshot_trainer_api(void) {
    static const HkTrainerApi api = { HK_TRAINER_ABI, sizeof(HkTrainerApi), trainer_items,
        sizeof trainer_items / sizeof trainer_items[0], hk_trainer_status, hk_trainer_request,
        hk_text_focus, hk_take_text, hk_composing, hk_navigation_set, hk_navigation_sample,
        hk_quest_set, hk_quest_sample, hk_prefs_get, hk_prefs_set, hk_take_hotkey, hk_pad_flight_context };
    return &api;
}
