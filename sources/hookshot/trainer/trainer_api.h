#pragma once
#include <string.h>
#include "trainer.h"
#include "dungeon_state_types.h"

#define HK_TRAINER_ABI 14u
#define HK_TRAINER_TEXT_MESSAGE (WM_APP + 31)
enum { HK_OPT_CANCEL_TRAINER_FLIGHT = 0x484b1001 };
enum { HK_HOTKEY_PANEL = 1, HK_HOTKEY_FLIGHT = 2 };

enum { HK_TRAINER_TELEPORT = TRAINER_AMMO + 1, HK_TRAINER_REMOVE_ITEM, HK_TRAINER_REFILL_MAGIC };
enum {
    HK_PREF_HEALTH = 1, HK_PREF_AMMO = 2, HK_PREF_NAVIGATION = 4, HK_PREF_FLIGHT = 8,
    HK_PREF_MAGIC = 16, HK_PREF_ALL = 31
};

enum {
    HK_MAP_UNKNOWN,
#define HK_MAP_ID(name) kMap##name,
#include "map_ids.generated.h"
#undef HK_MAP_ID
    HK_MAP_COUNT
};
typedef struct {
    float x, y, z;
    int map, guide_step, goal_region, child, quest, step;
    HkDungeonState dungeon;
} HkNavigation;
typedef struct { int quest, step, guide, guide_step; } HkQuestStatus;
typedef struct { int current, maximum; } HkMagicStatus;
typedef struct { unsigned flags, ammo_epoch; int forest_destination; } HkTrainerPrefs;

static const char *const hkAmmoIds[] = {
    "Item_DekuStick", "Item_DekuNut", "Item_DekuSeed", "Item_Bomb", "Item_Bombchu", "Item_Arrow_Normal"
};

static inline int hk_is_empty_bottle(const TrainerItem *item) {
    return strcmp(item->actor, "Item_Bottle") == 0;
}

static inline int hk_is_bottle_content(const TrainerItem *item) {
    return !item->restriction[0] && strncmp(item->actor, "Item_Bottle_", 12) == 0;
}

typedef struct {
    unsigned abi, size;
    const TrainerItem *items;
    int count;
    TrainerStatus (*status)(HkMagicStatus *);
    int (*request)(uint64_t, int, int, int);
    void (*text_focus)(int mode);   /* 0 none, 1 search (IME), 2 numbers */
    int (*take_text)(uint16_t *, int);
    int (*composing)(void);
    void (*navigation_set)(int);
    int (*navigation_sample)(HkNavigation *);
    void (*quest_set)(int);
    int (*quest_sample)(HkQuestStatus *);
    HkTrainerPrefs (*prefs_get)(void);
    int (*prefs_set)(unsigned mask, unsigned flags, int forest_destination);
    int (*take_hotkey)(void);
    void (*pad_flight_context)(uint64_t generation, int allowed);
} HkTrainerApi;
