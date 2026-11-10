#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include "cpu.h"
#include "host.h"
#include "trainer.h"
#include "items.generated.h"

#define GDM_SLOT 0x7004c7e180ull
#define POUCH_SLOT 0x7004c7e0d0ull
#define POUCH_MANAGER 0x7004e78e28ull
#define STATE_SLOT 0x7004c7e2a8ull
#define ACTOR_DB 0x7004e96888ull
#define ACTOR_INFO 0x7004e6c060ull
#define POUCH_EDIT 0x70028b4a70ull
#define POUCH_COUNT 0x70005963e0ull
#define SCRIPT_NAME 0x7003eea6d8ull
#define INT_VTABLE 0x7004c20718ull
#define LIFE_HASH 0x31ab5580u
#define LIFE_MAX_HASH 0xfbe01da1u
#define RUPEE_HASH 0xa77921d7u
#define WALLET_HASH 0xe0010a50u

static SRWLOCK state_lock = SRWLOCK_INIT;
static SRWLOCK tick_lock = SRWLOCK_INIT;
static TrainerStatus status;
static uint64_t last_tick, last_publish, actor_seen, manager_seen, life_seen;
static int keep;
static struct { uint64_t at, generation; int action, item, amount; } request;
static struct { uint64_t deadline; int item, before, amount, capacity; } awaiting;

static int access_guest(uint64_t a, uint64_t n, unsigned perm) {
    RtMemoryInfo info;
    return a && n && !mem_query(a, &info) && (info.perm & perm) == perm &&
           a >= info.base && n <= info.size && a - info.base <= info.size - n;
}

static uint64_t pointer_at(uint64_t a) {
    return access_guest(a, 8, 1) ? LD64(a) : 0;
}

static uint64_t indexed_entry(uint64_t mgr, uint32_t hash, unsigned head, unsigned stride) {
    if (!access_guest(mgr + head, 32, 1)) return 0;
    uint32_t length = LD32(mgr + head), slots = LD32(mgr + head + 28);
    uint64_t data = LD64(mgr + head + 8), index = LD64(mgr + head + 16);
    if (!length || length > 20000 || slots != 2*length ||
        !access_guest(index, 8ull*slots, 1) || !access_guest(data, (uint64_t)stride*length, 1)) return 0;
    uint32_t cursor = hash % slots;
    for (unsigned i = 0; i < slots; i++, cursor = (cursor+1) % slots) {
        uint64_t entry = index + 8ull*cursor;
        uint32_t key = LD32(entry);
        if (!key) return 0;
        if (key == hash) {
            uint32_t pos = LD32(entry + 4);
            return pos < length ? data + (uint64_t)stride*pos : 0;
        }
    }
    return 0;
}

static uint64_t integer_field(uint64_t mgr, uint32_t hash) {
    uint64_t entry = indexed_entry(mgr, hash, 0xd0, 40);
    return entry && LD64(entry) == INT_VTABLE ? entry + 0x1c : 0;
}

static int integer(uint64_t mgr, uint32_t hash) {
    uint64_t a = integer_field(mgr, hash);
    return a ? (int32_t)LD32(a) : -1;
}

static int write_integer(uint64_t address, int before, int after) {
    if (before == after) return 1;
    if ((address & 3) || !access_guest(address, 4, 3)) return 0;
    mem_thaw(address, 4);
    return __atomic_compare_exchange_n((int32_t *)(uintptr_t)address, &before, after,
                                        0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

static int set_rupees(uint64_t address, int before, int after) {
    // For this Int entry +0x1c is the displayed value and +0x20 is serialized.
    if (!access_guest(address, 8, 3) || (int32_t)LD32(address+4) != before) return 0;
    if (!write_integer(address, before, after)) return 0;
    if (write_integer(address+4, before, after)) return 1;
    return write_integer(address, after, before) ? 0 : -1;
}

static uint64_t player(uint64_t actor) {
    if (pointer_at(actor) != 0x7004b25e18ull) return 0;
    uint64_t components = pointer_at(actor + 624);
    if (!components) return 0;
    uint64_t movement = pointer_at(components + 800);
    if (movement < 0x1d50 || pointer_at(movement + 24) != actor) return 0;
    uint64_t link = movement - 0x1d50;
    uint64_t res = pointer_at(link + 16);
    return pointer_at(link) == 0x7004b4c460ull && res && access_guest(res+88, 7, 1) &&
           !memcmp((const void *)(uintptr_t)(res+88), "Player", 7) ? link : 0;
}

TrainerStatus trainer_status(void) {
    AcquireSRWLockShared(&state_lock);
    TrainerStatus copy = status;
    if (GetTickCount64() - last_publish > 1200) copy.ready = copy.keep_health = 0;
    ReleaseSRWLockShared(&state_lock);
    return copy;
}

void trainer_request(uint64_t generation, int action, int item, int amount) {
    AcquireSRWLockExclusive(&state_lock);
    uint64_t now = GetTickCount64();
    if (status.ready && generation == status.generation && now - last_publish <= 1200 &&
        (!status.pending || (request.action && now - request.at > 1600))) {
        request = (typeof(request)){now, generation, action, item, amount};
        status.pending = 1;
        snprintf(status.message, sizeof status.message, "等待角色更新…");
    }
    ReleaseSRWLockExclusive(&state_lock);
}

static int pouch_ready(void) {
    uint64_t p = pointer_at(POUCH_MANAGER);
    return p && p == pointer_at(pointer_at(POUCH_SLOT)) && pointer_at(p) &&
           pointer_at(pointer_at(STATE_SLOT)) && pointer_at(ACTOR_DB) && pointer_at(ACTOR_INFO) &&
           access_guest(SCRIPT_NAME, 7, 1) && !memcmp((const void *)(uintptr_t)SCRIPT_NAME, "Script", 7);
}

static int pouch_count(Cpu *c, uint64_t sp, const char *name) {
    if (strlen(name) >= 0x60 || sp < 0x3000) return -1;
    uint64_t frame = (sp - 0x80) & ~15ull;
    if (!access_guest(frame, 0x80, 3)) return -1;
    Cpu saved = *c;
    memcpy((void *)(uintptr_t)(frame + 0x10), name, strlen(name)+1);
    ST64(frame, frame + 0x10);
    c->sp = frame;
    int count = (int32_t)rt_call(c, POUCH_COUNT, 4, pointer_at(POUCH_MANAGER), frame, 0ull, 0ull);
    *c = saved;
    rt_fpcr_sync(c);
    return count;
}

static int pouch_add(Cpu *c, uint64_t sp, int index, int amount, uint64_t mgr) {
    const TrainerItem *item = &trainer_items[index];
    if (!item->stock || item->restriction[0] || amount <= 0 || !pouch_ready()) return -1;
    int have = integer(mgr, item->stock);
    int cap = item->capacity ? integer(mgr, item->capacity) : item->maximum;
    if (have < 0 || cap <= 0 || have >= cap || cap > 1000 || amount > cap-have ||
        pouch_count(c, sp, item->actor) != have) return -1;
    size_t len = strlen(item->actor);
    uint64_t event = (sp - 0xe0) & ~15ull;
    if (len >= 0x60 || !access_guest(event, 0xe0, 3)) return -1;
    Cpu saved = *c;
    memset((void *)(uintptr_t)event, 0, 0xe0);
    memcpy((void *)(uintptr_t)(event+0x80), item->actor, len+1);
    ST64(event+0x20, event+0x60);
    ST64(event+0x30, event+0x70);
    ST64(event+0x38, event+0x68);
    ST64(event+0x48, event+0x74);
    ST64(event+0x50, event+0x74);
    ST64(event+0x60, event+0x80);
    ST64(event+0x68, SCRIPT_NAME);
    ST32(event+0x70, amount);
    c->sp = event;
    rt_call(c, POUCH_EDIT, 1, event);
    unsigned code = LD32(event+0x18) >> 30;
    *c = saved;
    rt_fpcr_sync(c);
    awaiting = (typeof(awaiting)){GetTickCount64()+2500, index, have, amount, cap};
    rt_log("trainer: dispatched %s request=%d before=%d event=%u", item->actor, amount, have, code);
    return 1;
}

void trainer_tick(Cpu *c, uint64_t actor, uint64_t sp) {
    uint64_t now = GetTickCount64();
    if (!TryAcquireSRWLockExclusive(&tick_lock)) return;
    if (now - last_tick < 90) goto done;
    uint64_t link = player(actor);
    if (!link) goto done;
    last_tick = now;
    uint64_t life = pointer_at(link + 7184);
    uint64_t mgr = pointer_at(pointer_at(GDM_SLOT));
    uint64_t loading = mgr ? indexed_entry(mgr, 0xef2b60c2u, 0x10, 24) : 0;
    uint64_t hp_address = mgr ? integer_field(mgr, LIFE_HASH) : 0;
    uint64_t rupee_address = mgr ? integer_field(mgr, RUPEE_HASH) : 0;
    int hp = life && access_guest(life+8, 4, 3) ? (int32_t)LD32(life+8) : -1;
    int max_hp = mgr ? integer(mgr, LIFE_MAX_HASH) : -1;
    int coins = rupee_address ? (int32_t)LD32(rupee_address) : -1;
    int wallet = mgr ? integer(mgr, WALLET_HASH) : -1;
    int ready = loading && !(LD8(loading+22) & 1) && hp_address && hp > 0 &&
                hp <= max_hp && max_hp >= 12 && max_hp <= 80 && !(max_hp % 4) &&
                (wallet == 200 || wallet == 500 || wallet == 1000) && coins >= 0 && coins <= wallet;
    AcquireSRWLockExclusive(&state_lock);
    int changed = actor_seen != link || manager_seen != mgr || life_seen != life ||
                  now-last_publish > 1200 || ready != status.ready;
    if (changed) {
        actor_seen = link;
        manager_seen = mgr;
        life_seen = life;
        status.generation++;
        keep = 0;
        if (awaiting.deadline) {
            awaiting.deadline = 0;
            status.pending = 0;
            snprintf(status.message, sizeof status.message, "角色已切换，未能确认道具操作结果。");
            rt_log("trainer: item result unknown after player change");
        }
    }
    if (request.action && (request.generation != status.generation || now-request.at > 1600 || !ready)) {
        request.action = 0;
        status.pending = 0;
        snprintf(status.message, sizeof status.message, "请求已过期，或当前角色已切换。");
    }
    int action = request.action, item = request.item, amount = request.amount;
    request.action = 0;
    status.ready = ready;
    last_publish = now;
    status.health = hp;
    status.max_health = max_hp;
    status.rupees = coins;
    status.wallet = wallet;
    ReleaseSRWLockExclusive(&state_lock);

    char result[160] = "";
    int settled = 0;
    if (ready && awaiting.deadline) {
        const TrainerItem *entry = &trainer_items[awaiting.item];
        int count = integer(mgr, entry->stock);
        if (count >= awaiting.before + awaiting.amount && count <= awaiting.capacity &&
            pouch_ready() && pouch_count(c, sp, entry->actor) == count) {
            snprintf(result, sizeof result, "已增加 %d 个（当前 %d / %d）。", count-awaiting.before, count, awaiting.capacity);
            settled = 1;
        } else if (now >= awaiting.deadline) {
            snprintf(result, sizeof result, "结果未确认，请查看背包后再试。");
            settled = 1;
        }
        if (settled) awaiting.deadline = 0;
    }
    if (ready) {
        if (action == TRAINER_KEEP) {
            keep = !!amount;
            snprintf(result, sizeof result, "%s", keep ? "已开启持续回血。" : "已关闭持续回血。");
        }
        if ((keep || action == TRAINER_HEAL) && hp < max_hp) {
            int applied = write_integer(life+8, hp, max_hp);
            if (applied) {
                int stored = (int32_t)LD32(hp_address);
                if (stored >= 0 && stored <= max_hp) write_integer(hp_address, stored, max_hp);
                hp = max_hp;
            }
            if (action == TRAINER_HEAL)
                snprintf(result, sizeof result, applied ? "生命已回满。" : "生命值已变化，请重试。");
        } else if (action == TRAINER_HEAL) {
            snprintf(result, sizeof result, "当前生命已满。");
        }
        if (action == TRAINER_RUPEES) {
            int applied = amount >= 0 && amount <= wallet ? set_rupees(rupee_address, coins, amount) : 0;
            coins = (int32_t)LD32(rupee_address);
            snprintf(result, sizeof result, applied > 0 ? "卢比已设为 %d。" :
                     applied < 0 ? "修改结果未确认，当前卢比 %d。" :
                     "未能修改卢比，当前为 %d。", coins);
        }
        if (action == TRAINER_ITEM && item >= 0 && item < trainer_item_count) {
            if (pouch_add(c, sp, item, amount, mgr) <= 0)
                snprintf(result, sizeof result, "无法添加，请检查持有数量、容量与解锁条件。");
        }
        if (action == TRAINER_AMMO && item >= 0 && item < trainer_item_count) {
            const TrainerItem *entry = &trainer_items[item];
            int cap = entry->capacity ? integer(mgr, entry->capacity) : entry->maximum;
            int have = integer(mgr, entry->stock);
            int sent = have >= 0 && cap > have ? pouch_add(c, sp, item, cap-have, mgr) : -1;
            if (sent <= 0) snprintf(result, sizeof result, have == cap && cap > 0 ?
                                    "弹药已满。" : "无法补充，请检查容器和容量。");
        }
    }
    AcquireSRWLockExclusive(&state_lock);
    if (action || settled) {
        status.pending = awaiting.deadline != 0;
        snprintf(status.message, sizeof status.message, "%s", awaiting.deadline ?
                 "等待背包数量更新…" : result[0] ? result : "当前无法执行此操作。");
        rt_log("trainer: request=%d %s", action, status.message);
    }
    status.keep_health = keep;
    status.health = hp;
    status.rupees = coins;
    ReleaseSRWLockExclusive(&state_lock);
done:
    ReleaseSRWLockExclusive(&tick_lock);
}
