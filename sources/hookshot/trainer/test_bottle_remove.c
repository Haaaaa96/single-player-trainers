/* Offline fixture for the production pouch state machine. The real catalog,
 * classifiers, bottle sampler, dispatcher and poller are included. Only the
 * guest-memory/native boundaries are replaced; this never opens a game process.
 * Build with -I <retained generated output> -I ../core. */
#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define ARRAYSIZE(a) (sizeof(a) / sizeof((a)[0]))
#define WM_APP 0x8000
#include "trainer_api.h"
#include "items.generated.h"

typedef struct { uint64_t x[32]; } Ctx;
enum { MGR = 256, STOCK_BASE = 4096, ENUM_BASE = 8192, STRIDE = 64,
       STACK = 61440, ORDINARY_FIELD = 12288, ASSIGN_BASE = 16384, OWNED_BASE = 20480 };
static unsigned char memory[65536];
static uint64_t clock_now;
static int ready, readable, event_result, fill_result, remove_result;
static int dispatches, fills, removals, last_delta, last_type, ordinary_live;
static uint32_t removed_hash, removed_owned_hash, missing_enum;
static char last_actor[96];

static int access_guest(uint64_t address, uint64_t size, unsigned permissions) {
    (void)permissions;
    return readable && address && address < sizeof memory && size <= sizeof memory-address;
}
static uint32_t load32(uint64_t address) {
    uint32_t value;
    assert(access_guest(address, sizeof value, 1));
    memcpy(&value, memory+address, sizeof value);
    return value;
}
static uint64_t load64(uint64_t address) {
    uint64_t value;
    assert(access_guest(address, sizeof value, 1));
    memcpy(&value, memory+address, sizeof value);
    return value;
}
static uint8_t load8(uint64_t address) {
    assert(access_guest(address, 1, 1));
    return memory[address];
}
static void put32(uint64_t address, uint32_t value) { memcpy(memory+address, &value, sizeof value); }
static void put64(uint64_t address, uint64_t value) { memcpy(memory+address, &value, sizeof value); }
#define LD32 load32
#define LD64 load64
#define LD8 load8
#define INT_VTABLE 0x84c40718ull

static uint64_t integer_field(uint64_t mgr, uint32_t hash);
static int integer(uint64_t mgr, uint32_t hash);
static uint64_t indexed_entry(uint64_t mgr, uint32_t hash, unsigned head, unsigned stride);
static int pouch_ready(void) { return ready; }
static int pouch_count(Ctx *c, uint64_t sp, const char *actor);
static int oot_pouch_change(Ctx *c, const char *actor, int delta) {
    (void)c;
    ++dispatches;
    last_delta = delta;
    snprintf(last_actor, sizeof last_actor, "%s", actor);
    return event_result;
}
static int hk_push_to_empty_bottle(Ctx *c, uint64_t sp, int type) {
    (void)c; (void)sp;
    ++fills;
    last_type = type;
    return fill_result;
}
static int hk_remove_empty_bottle(Ctx *c, uint64_t sp, uint64_t mgr, uint32_t hash, uint32_t owned_hash) {
    assert(c && sp == STACK && mgr == MGR);
    ++removals;
    removed_hash = hash;
    removed_owned_hash = owned_hash;
    /* Native dispatch is asynchronous: this boundary never changes the fixture. */
    return remove_result;
}
static uint64_t GetTickCount64(void) { return clock_now; }
static void hos_log(const char *format, ...) { (void)format; }

#include "trainer_pouch.h"

static uint64_t integer_field(uint64_t mgr, uint32_t hash) {
    if (mgr != MGR) return 0;
    for (unsigned i=0; i<ARRAYSIZE(hk_bottle_slots); ++i)
        if (hash == hk_bottle_slots[i]) {
            uint64_t entry = STOCK_BASE+i*STRIDE;
            return access_guest(entry, 40, 1) && LD64(entry) == INT_VTABLE ? entry+0x1c : 0;
        }
    for (int i=0; i<trainer_item_count; ++i)
        if (hash == trainer_items[i].stock && !strcmp(trainer_items[i].actor, "Item_DekuNut"))
            return ORDINARY_FIELD;
    for (int i=0; i<trainer_item_count; ++i)
        if (hash == trainer_items[i].capacity && !strcmp(trainer_items[i].actor, "Item_DekuNut"))
            return ORDINARY_FIELD+8;
    return 0;
}
static int integer(uint64_t mgr, uint32_t hash) {
    uint64_t field = integer_field(mgr, hash);
    return field ? (int32_t)LD32(field) : -1;
}
static uint64_t indexed_entry(uint64_t mgr, uint32_t hash, unsigned head, unsigned stride) {
    if (mgr != MGR || hash == missing_enum) return 0;
    if (head == 0x10) {
        assert(stride == 24);
        for (unsigned i=0; i<ARRAYSIZE(hk_bottle_ownership_keys); ++i)
            if (hash == hk_bottle_ownership_keys[i]) {
                uint64_t entry = OWNED_BASE+i*STRIDE;
                return access_guest(entry, 24, 1) ? entry : 0;
            }
        return 0;
    }
    assert(head == 0x250 && stride == 56);
    for (unsigned i=0; i<ARRAYSIZE(hk_bottle_enums); ++i)
        if (hash == hk_bottle_enums[i]) {
            uint64_t entry = ENUM_BASE+i*STRIDE;
            return access_guest(entry, 56, 1) ? entry : 0;
        }
    for (unsigned i=0; i<ARRAYSIZE(hk_bottle_assignment_keys); ++i)
        if (hash == hk_bottle_assignment_keys[i]) return ASSIGN_BASE+i*STRIDE;
    return 0;
}
static int pouch_count(Ctx *c, uint64_t sp, const char *actor) {
    (void)c; (void)sp;
    if (!strcmp(actor, "Item_Bottle")) {
        int count = 0;
        for (unsigned i=0; i<5; ++i)
            count += integer(MGR, hk_bottle_slots[i]) == 1 &&
                     LD32(ENUM_BASE+i*STRIDE+0x1c) == 0xbe69de49u;
        return count;
    }
    return ordinary_live;
}

static Ctx context;
static char message[256];
static int empty_item, red_item, ordinary_item;
static int item_index(const char *actor) {
    for (int i=0; i<trainer_item_count; ++i)
        if (!strcmp(trainer_items[i].actor, actor)) return i;
    assert(!"required actor missing from real catalog");
    return -1;
}
static void set_owned(unsigned index, int live, int saved) {
    assert(index < 5 && live >= 0 && live <= 255 && saved >= 0 && saved <= 255);
    memory[OWNED_BASE+index*STRIDE+22] = (uint8_t)live;
    memory[OWNED_BASE+index*STRIDE+23] = (uint8_t)saved;
}
static void slot(unsigned index, int owned, uint32_t content) {
    assert(index < 5);
    put64(STOCK_BASE+index*STRIDE, INT_VTABLE);
    put32(STOCK_BASE+index*STRIDE+0x1c, (uint32_t)owned);
    put32(STOCK_BASE+index*STRIDE+0x20, (uint32_t)owned);
    put64(ENUM_BASE+index*STRIDE, 0x84c40898ull);
    put32(ENUM_BASE+index*STRIDE+0x1c, content);
    put32(ENUM_BASE+index*STRIDE+0x20, content);
    set_owned(index, owned, owned);
}
static void assignment(unsigned age, uint32_t value) {
    assert(age < 2);
    put64(ASSIGN_BASE+age*STRIDE, 0x84c40898ull);
    put32(ASSIGN_BASE+age*STRIDE+0x1c, value);
    put32(ASSIGN_BASE+age*STRIDE+0x20, value);
}
static void apply_removal(unsigned index) {
    /* Stock and IsGet queues complete independently. Do not clear IsGet here. */
    put32(STOCK_BASE+index*STRIDE+0x1c, 0);
    put32(STOCK_BASE+index*STRIDE+0x20, 0);
}
static int native_add_slot(void) {
    /* Native bottle-add f_8112d570 selects by IsGet, never by Stock. */
    for (unsigned i=0; i<5; ++i)
        if (!LD8(OWNED_BASE+i*STRIDE+22)) return (int)i;
    return -1;
}
static int apply_native_add(void) {
    int target = native_add_slot();
    if (target >= 0) slot((unsigned)target, 1, 0xbe69de49u);
    return target;
}
static void reset(void) {
    memset(memory, 0, sizeof memory);
    memset(&context, 0, sizeof context);
    memset(&awaiting, 0, sizeof awaiting);
    memset(message, 0, sizeof message);
    memset(last_actor, 0, sizeof last_actor);
    ready = readable = fill_result = remove_result = 1;
    event_result = dispatches = fills = removals = last_delta = ordinary_live = 0;
    removed_hash = removed_owned_hash = missing_enum = 0;
    last_type = -1;
    clock_now = 100;
    context.x[31] = STACK;
    for (unsigned i=0; i<5; ++i) slot(i, 0, 0xbe69de49u);
    for (unsigned i=0; i<2; ++i) assignment(i, 0xbe69de49u); /* Verified Empty selection. */
}
static int change(int item, int delta) {
    message[0] = 0;
    return hk_pouch_change(&context, STACK, item, delta, MGR, message, sizeof message);
}
static int poll(uint64_t now) {
    clock_now = now;
    /* The generated production core only polls an active request. */
    return awaiting.deadline ? hk_pouch_poll(&context, STACK, MGR, now, message, sizeof message) : 0;
}
static void expect_stock(unsigned index, int stock, uint32_t content) {
    assert((int)LD32(STOCK_BASE+index*STRIDE+0x1c) == stock);
    assert((int)LD32(STOCK_BASE+index*STRIDE+0x20) == stock);
    assert(LD32(ENUM_BASE+index*STRIDE+0x1c) == content);
    assert(LD32(ENUM_BASE+index*STRIDE+0x20) == content);
    assert(LD8(OWNED_BASE+index*STRIDE+22) == stock);
    assert(LD8(OWNED_BASE+index*STRIDE+23) == stock);
}

static void test_add_and_fill(void) {
    reset();
    assert(change(empty_item, 1));
    assert(dispatches == 1 && fills == 0 && last_delta == 1 && !strcmp(last_actor, "Item_Bottle"));
    assert(poll(200) == 0);
    assert(apply_native_add() == 0);
    assert(poll(300) == 1 && !awaiting.deadline);
    assert(change(red_item, 1));
    assert(dispatches == 1 && fills == 1 && last_type == 0);
    slot(0, 1, 0xeaba6067u);
    assert(poll(400) == 1 && !awaiting.deadline);
    expect_stock(0, 1, 0xeaba6067u);

    /* Without an empty slot, the existing two-stage route adds then fills once. */
    assert(change(red_item, 1));
    assert(dispatches == 2 && fills == 1);
    assert(apply_native_add() == 1);
    assert(poll(500) == 0 && fills == 2);
    assert(poll(600) == 0 && fills == 2);
    slot(1, 1, 0xeaba6067u);
    assert(poll(700) == 1 && !awaiting.deadline);
    expect_stock(0, 1, 0xeaba6067u);
    expect_stock(1, 1, 0xeaba6067u);

    /* Full bottles never turn a content request into a destructive operation. */
    for (unsigned i=0; i<5; ++i) slot(i, 1, 0xeaba6067u);
    assert(!change(empty_item, 1));
    assert(!change(red_item, 1));
    assert(!change(red_item, -1));
    assert(dispatches == 2 && fills == 2);
    puts("PASS existing add, fill, add-then-fill, repeated operation and full-capacity refusal");
}

static void test_boundary_refusals(void) {
    reset();
    assert(!change(empty_item, 2));
    assert(!change(red_item, -1));
    slot(0, 1, 0xbe69de49u);
    put64(ENUM_BASE, 0);
    assert(!change(empty_item, 1));
    slot(0, 1, 0xdeadbeefu);
    assert(!change(red_item, 1));
    slot(0, 2, 0xbe69de49u);
    assert(!change(empty_item, 1));
    slot(0, 1, 0xbe69de49u);
    ready = 0;
    assert(!change(empty_item, 1));
    ready = 1; readable = 0;
    assert(!change(empty_item, 1));
    assert(dispatches == 0 && fills == 0 && !awaiting.deadline);
    puts("PASS invalid quantity, unknown enum, invalid type/stock, unavailable pouch and unreadable memory refusal");
}

static void test_timeout_no_redispatch(void) {
    reset();
    assert(change(empty_item, 1));
    assert(poll(500) == 0 && poll(1000) == 0);
    assert(poll(2600) == -1 && !awaiting.deadline);
    assert(strstr(message, "未确认"));
    assert(poll(3000) == 0 && poll(4000) == 0 && dispatches == 1 && fills == 0);

    reset();
    slot(0, 1, 0xbe69de49u);
    assert(change(red_item, 1));
    assert(poll(500) == 0 && poll(2600) == -1);
    assert(poll(3000) == 0 && dispatches == 0 && fills == 1);
    puts("PASS unconfirmed add/fill timeout clears pending without automatic re-dispatch");
}

static void test_remove_mixed_and_repeat(void) {
    reset();
    slot(0, 1, 0xbe69de49u); /* Empty A. */
    slot(1, 1, 0xeaba6067u); /* Red potion B. */
    slot(2, 1, 0x0f24e808u); /* Story letter C. */
    slot(3, 1, 0xbe69de49u); /* Empty D; the last eligible slot. */
    slot(4, 1, 0x1e834ef8u); /* Fish E. */
    unsigned char before[sizeof memory];
    memcpy(before, memory, sizeof memory);
    assert(change(empty_item, -1));
    assert(removals == 1 && removed_hash == 0x5324f9d3u && removed_owned_hash == 0xb7f052ceu &&
           dispatches == 0 && fills == 0);
    assert(awaiting.bottle_phase == HK_BOTTLE_REMOVE && awaiting.bottle_slot == 3);
    assert(!memcmp(before, memory, sizeof memory)); /* No direct guest-memory write. */
    assert(!change(empty_item, -1) && !change(empty_item, 1) && !change(red_item, 1));
    assert(removals == 1 && dispatches == 0 && fills == 0);
    assert(poll(200) == 0);
    put32(STOCK_BASE+3*STRIDE+0x1c, 0); /* Display changed; save still owns D. */
    assert(poll(300) == 0 && awaiting.deadline);
    put32(STOCK_BASE+3*STRIDE+0x20, 0);
    assert(poll(350) == 0); /* Stock complete does not mean IsGet complete. */
    set_owned(3, 0, 0);
    assert(poll(400) == 1 && !awaiting.deadline);
    expect_stock(0, 1, 0xbe69de49u);
    expect_stock(1, 1, 0xeaba6067u);
    expect_stock(2, 1, 0x0f24e808u);
    expect_stock(3, 0, 0xbe69de49u);
    expect_stock(4, 1, 0x1e834ef8u);

    assert(change(empty_item, -1) && removed_hash == 0xd53ce3a7u && removals == 2);
    apply_removal(0);
    set_owned(0, 0, 0);
    assert(poll(500) == 1);
    assert(!change(empty_item, -1) && removals == 2);
    assert(change(empty_item, 1) && dispatches == 1);
    assert(apply_native_add() == 0);
    assert(poll(600) == 1);
    assert(change(red_item, 1) && fills == 1);
    slot(0, 1, 0xeaba6067u);
    assert(poll(700) == 1);
    expect_stock(2, 1, 0x0f24e808u);
    puts("PASS mixed empty/filled/letter preservation, asynchronous save confirmation, pending refusal and remove/add/fill reuse");
}

static void test_each_slot_and_assignments(void) {
    static const uint32_t stock_hashes[] = {
        0xd53ce3a7u, 0xfca29a04u, 0x893216a1u, 0x5324f9d3u, 0xc92b16beu
    };
    static const uint32_t owned_hashes[] = {
        0xf39ce410u, 0x000ff6eau, 0xf63b1194u, 0xb7f052ceu, 0xe27b136du
    };
    for (unsigned target=0; target<5; ++target) {
        reset();
        for (unsigned i=0; i<5; ++i) slot(i, 1, 0xeaba6067u);
        slot(target, 1, 0xbe69de49u);
        assert(change(empty_item, -1) && removals == 1 && removed_hash == stock_hashes[target] &&
               removed_owned_hash == owned_hashes[target]);
        apply_removal(target);
        set_owned(target, 0, 0);
        assert(poll(200) == 1);
        for (unsigned i=0; i<5; ++i)
            expect_stock(i, i != target, i == target ? 0xbe69de49u : 0xeaba6067u);
    }
    reset();
    for (unsigned i=0; i<5; ++i) slot(i, 1, 0xbe69de49u);
    assignment(0, 0xd8cc3008u); /* Adult E. */
    assignment(1, 0xb55ee4e3u); /* Child D. */
    assert(change(empty_item, -1) && removed_hash == 0x893216a1u);
    apply_removal(2);
    set_owned(2, 0, 0);
    assert(poll(200) == 1);
    expect_stock(3, 1, 0xbe69de49u);
    expect_stock(4, 1, 0xbe69de49u);
    assert(LD32(ASSIGN_BASE+0x1c) == 0xd8cc3008u && LD32(ASSIGN_BASE+STRIDE+0x1c) == 0xb55ee4e3u);

    reset();
    slot(0, 1, 0xbe69de49u);
    slot(4, 1, 0xbe69de49u);
    assignment(0, 0x22c7238cu); /* Adult A. */
    assignment(1, 0xd8cc3008u); /* Child E. */
    assert(!change(empty_item, -1) && removals == 0 && !awaiting.deadline);
    assert(strstr(message, "道具栏"));
    puts("PASS A-E target hashes, both-age assignment exclusion and all-empty-slots-assigned refusal");
}

static void test_remove_refusals(void) {
    reset();
    assert(!change(empty_item, -1)); /* No owned bottle. */
    for (unsigned i=0; i<5; ++i) slot(i, 1, i == 2 ? 0x0f24e808u : 0xeaba6067u);
    assert(!change(empty_item, -1) && removals == 0);
    assert(!change(red_item, -1));

    reset();
    slot(0, 1, 0xbe69de49u);
    put32(STOCK_BASE+0x20, 0);
    assert(!change(empty_item, -1));
    slot(0, 1, 0xbe69de49u);
    put32(ENUM_BASE+0x20, 0xeaba6067u);
    assert(!change(empty_item, -1));
    slot(0, 1, 0xbe69de49u);
    put64(STOCK_BASE, 0);
    assert(!change(empty_item, -1));
    slot(0, 1, 0xbe69de49u);
    put64(ENUM_BASE, 0);
    assert(!change(empty_item, -1));
    slot(0, 1, 0xdeadbeefu);
    assert(!change(empty_item, -1));
    slot(0, 1, 0xbe69de49u);
    missing_enum = 0x7d48df76u;
    assert(!change(empty_item, -1));
    missing_enum = 0;
    put32(ASSIGN_BASE+0x20, 0x22c7238cu);
    assert(!change(empty_item, -1));
    assignment(0, 0xbe69de49u);
    put64(ASSIGN_BASE+STRIDE, 0);
    assert(!change(empty_item, -1));
    assignment(1, 0xbe69de49u);
    missing_enum = 0xa0029837u;
    assert(!change(empty_item, -1));
    missing_enum = 0xf39ce410u;
    assert(!change(empty_item, -1));
    missing_enum = 0;
    set_owned(0, 0, 0); /* Stock says owned, IsGet says not obtained. */
    assert(!change(empty_item, -1));
    set_owned(0, 1, 0); /* Boolean live/save divergence. */
    assert(!change(empty_item, -1));
    set_owned(0, 2, 2); /* Invalid Bool representation. */
    assert(!change(empty_item, -1));
    assert(removals == 0 && !awaiting.deadline);

    reset();
    slot(0, 1, 0xbe69de49u);
    remove_result = 0;
    assert(!change(empty_item, -1) && removals == 1 && !awaiting.deadline);
    expect_stock(0, 1, 0xbe69de49u);
    assert(poll(3000) == 0 && removals == 1);
    puts("PASS no-empty, filled-content, typed fields, Stock/IsGet/live/save divergence and native pre-dispatch refusal");
}

static void test_remove_unconfirmed(void) {
    /* Each mutation is distinct: delayed/no result, wrong slot, extra slot,
     * changed content, live/save divergence, each partial queue, extra IsGet,
     * and an assignment that changes after the request was queued. */
    for (unsigned mutation=0; mutation<9; ++mutation) {
        reset();
        slot(0, 1, 0xbe69de49u);
        slot(1, 1, 0xbe69de49u);
        slot(2, 1, 0x0f24e808u);
        assert(change(empty_item, -1) && removed_hash == 0xfca29a04u);
        if (mutation == 1) { apply_removal(0); set_owned(0, 0, 0); }
        if (mutation >= 2 && mutation <= 4) { apply_removal(1); set_owned(1, 0, 0); }
        if (mutation == 2) { apply_removal(2); set_owned(2, 0, 0); }
        if (mutation == 3) slot(1, 0, 0xeaba6067u);
        if (mutation == 4) put32(ENUM_BASE+2*STRIDE+0x20, 0xeaba6067u);
        if (mutation == 5) apply_removal(1); /* Stock-only completion. */
        if (mutation == 6) set_owned(1, 0, 0); /* IsGet-only completion. */
        if (mutation == 7) {
            apply_removal(1); set_owned(1, 0, 0);
            set_owned(2, 0, 0); /* Unrelated IsGet changed. */
        }
        if (mutation == 8) {
            apply_removal(1); set_owned(1, 0, 0);
            assignment(1, 0xac889fd5u); /* Child equips target B while queued. */
        }
        assert(poll(200) == 0 && poll(1500) == 0);
        assert(poll(2600) == -1 && !awaiting.deadline && strstr(message, "未确认"));
        assert(poll(3000) == 0 && poll(4000) == 0);
        assert(removals == 1 && dispatches == 0 && fills == 0);
    }
    puts("PASS wrong/extra slot, content/assignment mutation, partial queues and timeout stay unconfirmed without re-dispatch");
}

static void test_ownership_completion_and_reuse(void) {
    /* Completing the two native queues in either order must require both,
     * and a full inventory can reuse only the IsGet-cleared former slot. */
    for (unsigned bool_first=0; bool_first<2; ++bool_first) {
        reset();
        for (unsigned i=0; i<5; ++i) slot(i, 1, 0xeaba6067u);
        slot(4, 1, 0xbe69de49u);
        assert(native_add_slot() == -1);
        assert(change(empty_item, -1) && removed_hash == 0xc92b16beu && removed_owned_hash == 0xe27b136du);
        if (bool_first) {
            set_owned(4, 0, 0);
            assert(LD32(STOCK_BASE+4*STRIDE+0x1c) == 1);
        } else {
            apply_removal(4);
            assert(native_add_slot() == -1); /* The old Stock-only implementation leaked this slot. */
        }
        assert(poll(200) == 0 && awaiting.deadline);
        assert(!change(empty_item, 1) && dispatches == 0 && removals == 1);
        if (bool_first) apply_removal(4);
        else {
            set_owned(4, 0, 1);
            assert(poll(300) == 0); /* Even IsGet's live/save bytes must settle. */
            set_owned(4, 0, 0);
        }
        assert(poll(400) == 1 && !awaiting.deadline);
        expect_stock(4, 0, 0xbe69de49u);
        assert(native_add_slot() == 4);
        assert(change(empty_item, 1) && dispatches == 1);
        assert(apply_native_add() == 4);
        assert(poll(500) == 1);
        assert(change(red_item, 1) && fills == 1);
        slot(4, 1, 0xeaba6067u);
        assert(poll(600) == 1);
        for (unsigned i=0; i<5; ++i) expect_stock(i, 1, 0xeaba6067u);
        assert(native_add_slot() == -1 && removals == 1);
    }
    puts("PASS independent Stock/IsGet completion in both orders and real IsGet-selected delete/re-add/fill reuse");
}

static void test_ordinary_item_path(void) {
    reset();
    put32(ORDINARY_FIELD, 4);
    put32(ORDINARY_FIELD+8, 20);
    ordinary_live = 4;
    assert(change(ordinary_item, -1));
    assert(dispatches == 1 && last_delta == -1 && !strcmp(last_actor, "Item_DekuNut"));
    assert(!awaiting.bottle_phase && removals == 0 && fills == 0);
    assert(poll(200) == 0);
    ordinary_live = 3; put32(ORDINARY_FIELD, 3);
    assert(poll(300) == 1 && !awaiting.deadline);
    assert(change(ordinary_item, 2) && dispatches == 2 && last_delta == 2);
    ordinary_live = 5; put32(ORDINARY_FIELD, 5);
    assert(poll(400) == 1);
    assert(!change(ordinary_item, -6) && dispatches == 2);
    puts("PASS existing ordinary-item remove/add/readback and insufficient-stock refusal");
}

int main(void) {
    empty_item = item_index("Item_Bottle");
    red_item = item_index("Item_Bottle_RedPotion");
    ordinary_item = item_index("Item_DekuNut");
    assert(!trainer_items[empty_item].restriction[0] && !trainer_items[red_item].restriction[0]);
    assert(HK_BOTTLE_EMPTY == 0xbe69de49u);
    test_add_and_fill();
    test_boundary_refusals();
    test_timeout_no_redispatch();
    test_remove_mixed_and_repeat();
    test_each_slot_and_assignments();
    test_remove_refusals();
    test_remove_unconfirmed();
    test_ownership_completion_and_reuse();
    test_ordinary_item_path();
    puts("Offline production pouch header regression passed; no game process was opened.");
    return 0;
}
