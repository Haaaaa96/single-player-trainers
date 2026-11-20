#pragma once
#include <cmath>

enum HkJabuNode {
#define HK_JABU_POINT(name, x, z, floor) kJabu##name,
#include "jabu.generated.h"
#undef HK_JABU_POINT
    kJabuNodeCount
};
struct HkJabuPoint { float x, z; int floor; };
constexpr HkJabuPoint hkJabuPoints[] = {
#define HK_JABU_POINT(name, x, z, floor) {x, z, floor},
#include "jabu.generated.h"
#undef HK_JABU_POINT
};
static_assert(sizeof hkJabuPoints / sizeof *hkJabuPoints == kJabuNodeCount);

struct HkJabuEdge { HkJabuNode from, to; };
constexpr HkJabuEdge hkJabuEntryPath[] = {
    {kJabuEntrance, kJabuEntranceDoor}, {kJabuEntranceDoor, kJabuLiftHall},
    {kJabuLiftHall, kJabuPitDoor}, {kJabuPitDoor, kJabuRuto},
    {kJabuRuto, kJabuRutoHole}, {kJabuPitBelow, kJabuRutoBelow},
};

// Only draw a route from known approaches. During a floor change suspend
// guidance in the height gap, even if the player shares the same X/Z.
static int hk_jabu_floor(float x, float y, float z) {
    if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z) ||
        x < -47 || x > 53 || z < -211 || z > 11) return -1;
    if (y >= 72 && y <= 86.5f) return 0;
    if (y >= 88.5f && y <= 97.5f) return 1;
    if (y >= 98.5f && y <= 113) return 2;
    return -1;
}

struct HkJabuPlan { int target; const wchar_t *instruction; };

static HkJabuPlan hk_jabu_plan(float x, float y, float z, int stage) {
    const int floor = hk_jabu_floor(x, y, z);
    if (stage == 2 && floor == 0 && x >= -10 && x <= 12 && z >= -98 && z <= -72)
        return {kJabuRutoBelow, L"与露朵交谈"};
    if ((stage != 1 && stage != 2) || floor != 1 || std::abs(x) > 15 || z < -101)
        return {-1, L"查看主线攻略"};
    if (z > -28.53f)
        return {kJabuEntranceSwitch, L"弹弓打天花板机关"};
    if (z > -60.0f)
        return {kJabuPitDoor, L"穿过水母房"};
    if (stage == 1)
        return {kJabuRuto, L"去地洞房找露朵"};
    return {kJabuRutoHole, L"跟露朵跳进洞"};
}
