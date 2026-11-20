#pragma once

typedef struct {
    uint32_t value;
    const wchar_t *where, *who, *action;
    int map_region;
} HkQuestStep;

typedef struct {
    uint32_t hash;
    const wchar_t *title;
    const HkQuestStep *steps;
    int count;
} HkQuestDefinition;

#include "quests.generated.h"
#include "dungeon_guidance.h"

enum { HK_QUEST_COUNT = sizeof hk_quests / sizeof *hk_quests };

static int hk_quest_stage(const HkQuestDefinition *quest, uint32_t value) {
    for (int i = 0; i < quest->count; ++i)
        if (quest->steps[i].value == value) return i;
    return -1;
}

static int hk_quest_pick(const uint32_t *values, HkQuestStatus *out) {
    int stages[HK_QUEST_COUNT];
    for (int i = 0; i < HK_QUEST_COUNT; ++i) {
        stages[i] = hk_quest_stage(&hk_quests[i], values[i]);
        if (stages[i] < 0) return 0;
    }
    // Impa's lesson is part of DoorOfTime but precedes the fire and water stones.
    static const int order[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    for (int n = 0; n < HK_QUEST_COUNT; ++n) {
        int i = order[n];
        if (i == 2 && stages[4] == 2) i = 4;
        if (stages[i] == hk_quests[i].count - 1) continue;
        out->quest = i;
        out->step = stages[i];
        return 1;
    }
    out->quest = HK_QUEST_COUNT;
    out->step = 0;
    return 1;
}
