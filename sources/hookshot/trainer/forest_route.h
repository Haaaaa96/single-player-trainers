#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

struct HkForestPoint { float x, z; };
enum HkForestNode {
    kKokiriGate, kEntryRoom, kTargetRoom, kGoronRoom, kZoraRoom, kForkRoom,
    kBoulderRoom, kLastRoom, kMeadowGate, kGoronGate, kZoraBank, kZoraGate,
    kStageApproach, kStageDoor, kSkullRoom, kBridgeBend, kBridgeRoom, kForestNodeCount
};

// Child and Adult Banc/LostWood: entrances, scene triggers, tunnel actors and
// the groups on both sides of each traversable tunnel. Dead-end reset gates
// are intentionally absent; going back to Kokiri uses the normal exit.
constexpr HkForestPoint hkForestNodes[] = {
    {0, 7}, {0, 0}, {24, 0}, {24, -24}, {47.9f, -24}, {47.9f, -48.1f},
    {47.9f, -72}, {24, -72}, {24, -83.7f}, {24, -35.7f}, {55.7f, -25.6f}, {68.5f, -25.6f},
    {14.9f, -47.8f}, {3.8f, -47.5f}, {-35.5f, 0}, {-36.3f, 9}, {-36.3f, 29},
};
struct HkForestEdge { int a, b; };
constexpr HkForestEdge hkForestEdges[] = {
    {kKokiriGate, kEntryRoom}, {kEntryRoom, kTargetRoom}, {kTargetRoom, kGoronRoom},
    {kGoronRoom, kZoraRoom}, {kZoraRoom, kForkRoom}, {kForkRoom, kBoulderRoom},
    {kBoulderRoom, kLastRoom}, {kLastRoom, kMeadowGate},
    {kGoronRoom, kGoronGate}, {kZoraRoom, kZoraBank}, {kZoraBank, kZoraGate},
    {kForkRoom, kStageApproach}, {kStageApproach, kStageDoor},
    {kEntryRoom, kSkullRoom}, {kSkullRoom, kBridgeBend}, {kBridgeBend, kBridgeRoom},
};
constexpr const wchar_t *hkForestDestinations[] = {
    L"圣林草地", L"鼓隆城", L"卓拉河", L"科奇里森林", L"林中舞台洞口",
};
constexpr const wchar_t *hkForestNotes[] = {
    nullptr, L"须先开启通道", L"需潜水", nullptr, L"到洞口为止",
};
constexpr int hkForestGoals[] = {kMeadowGate, kGoronGate, kZoraGate, kKokiriGate, kStageDoor};
constexpr int hkForestGoalCount = sizeof hkForestGoals / sizeof *hkForestGoals;
static_assert(sizeof hkForestNodes / sizeof *hkForestNodes == kForestNodeCount);
static_assert(sizeof hkForestDestinations / sizeof *hkForestDestinations == hkForestGoalCount);
static_assert(sizeof hkForestNotes / sizeof *hkForestNotes == hkForestGoalCount);

// All supported connections form a tree. Compute directions toward each
// destination once; rerouting only needs a position projection and path walk.
static constexpr auto hk_forest_routes() {
    std::array<std::array<int, kForestNodeCount>, hkForestGoalCount> routes{};
    for (int d = 0; d < hkForestGoalCount; ++d) {
        auto& next = routes[d];
        next.fill(-1);
        int queue[kForestNodeCount]{hkForestGoals[d]}, head = 0, tail = 1;
        next[hkForestGoals[d]] = hkForestGoals[d];
        while (head < tail) {
            const int here = queue[head++];
            for (auto [a,b] : hkForestEdges) {
                const int there = here == a ? b : here == b ? a : -1;
                if (there < 0 || next[there] >= 0) continue;
                next[there] = here;
                queue[tail++] = there;
            }
        }
    }
    return routes;
}
constexpr auto hkForestRoutes = hk_forest_routes();

struct HkForestPlan {
    HkForestPoint start{};
    std::array<int, kForestNodeCount> stops{};
    int count = 0;
    bool arrived = false;
};

static float hk_forest_dist2(HkForestPoint a, HkForestPoint b) {
    const float x = b.x-a.x, z = b.z-a.z;
    return x*x+z*z;
}

static bool hk_forest_surface(float x, float y, float z) {
    // The Zora River tunnel descends to y≈92.2; grottos are near y≈83.
    const bool river = x >= 54.0f && x <= 71.5f && std::abs(z+25.6f) <= 6.0f;
    return y >= (river ? 88.0f : 96.0f) && y <= 111.0f;
}

static HkForestPlan hk_forest_plan(float x, float y, float z, int destination) {
    HkForestPlan plan{};
    if (destination < 0 || destination >= hkForestGoalCount || !hk_forest_surface(x, y, z)) return plan;
    const auto& next = hkForestRoutes[destination];
    const int goal = hkForestGoals[destination];
    const HkForestPoint pos{x,z};
    if (hk_forest_dist2(pos, hkForestNodes[goal]) <= 2.2f*2.2f) {
        plan.arrived = true;
        return plan;
    }

    int node = -1;
    for (int i = kEntryRoom; i <= kLastRoom; ++i) {
        if (hk_forest_dist2(pos, hkForestNodes[i]) <= 4.0f*4.0f) {
            plan.start = hkForestNodes[i];
            node = next[i];
            break;
        }
    }
    if (node < 0) {
        float best = std::numeric_limits<float>::infinity();
        for (auto [i,j] : hkForestEdges) {
            const auto a = hkForestNodes[i], b = hkForestNodes[j];
            const float dx = b.x-a.x, dz = b.z-a.z;
            const float t = std::clamp(((x-a.x)*dx+(z-a.z)*dz)/(dx*dx+dz*dz), 0.0f, 1.0f);
            const HkForestPoint projection{a.x+t*dx, a.z+t*dz};
            const float d2 = hk_forest_dist2(pos, projection);
            if (d2 >= best) continue;
            best = d2;
            plan.start = projection;
            node = next[i] == j ? j : i;
        }
        if (best > 8.5f*8.5f) return {};
    }
    while (node >= 0 && plan.count < kForestNodeCount) {
        plan.stops[plan.count++] = node;
        if (node == goal) return plan;
        node = next[node];
    }
    return {};  // no verified connection
}

static const wchar_t *hk_forest_direction(const HkForestPlan& plan) {
    if (plan.count <= 0) return L"";
    const auto target = hkForestNodes[plan.stops[0]];
    const float dx = target.x-plan.start.x, dz = target.z-plan.start.z;
    if (std::abs(dx) > std::abs(dz)) return dx > 0 ? L"图上向右 →" : L"图上向左 ←";
    return dz > 0 ? L"图上向下 ↓" : L"图上向上 ↑";
}
