#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include "dungeon_plan_types.h"
#include "dungeon_geometry.generated.h"
#include "dungeon_plan.generated.h"

static_assert(std::size(hkDungeonEdges) == std::size(hkDungeonGateRules));
static_assert(std::size(hkDungeonSteps) == std::size(hkDungeonAdvanceRules));

struct HkDungeonPlan {
    int step = -1, floor = -1, room = -1, from = -1, goal = -1;
    int edge = -1, next = -1, approach = -1, completion = HK_DUNGEON_UNKNOWN;
    int total = 0, completed = 0, superseded = 0;
    bool supported = false, fresh = false, reached = false, route = false, finished = false;
    bool uncertain_position = false, gate = false, blocked = false;
    bool room_obstacles = false;
    std::array<int, 64> path{};
    int path_count = 0;
};

static int hk_dungeon_group(const HkDungeonState& state, int first, int count, bool any) {
    if (count <= 0 || first < 0 || first > (int)std::size(hkDungeonConditionRefs)-count)
        return HK_DUNGEON_UNKNOWN;
    bool unknown = false;
    for (int i = first; i < first+count; ++i) {
        const int result = hk_dungeon_condition_state(&state, hkDungeonConditionRefs[i]);
        if (any && result == HK_DUNGEON_MET) return HK_DUNGEON_MET;
        if (!any && result == HK_DUNGEON_UNMET) return HK_DUNGEON_UNMET;
        unknown |= result == HK_DUNGEON_UNKNOWN;
    }
    return unknown ? HK_DUNGEON_UNKNOWN : any ? HK_DUNGEON_UNMET : HK_DUNGEON_MET;
}

static bool hk_dungeon_age(const HkDungeonStep& step, const HkNavigation& pos) {
    return !step.age || (pos.child >= 0 && step.age == (pos.child ? 1 : 2));
}

static bool hk_dungeon_superseded(const HkNavigation& pos, int step_index) {
    if (step_index < 0 || step_index >= (int)std::size(hkDungeonSteps)) return false;
    const auto& step = hkDungeonSteps[step_index];
    const auto& rule = hkDungeonAdvanceRules[step_index];
    if (rule.count <= 0 || rule.first < 0 ||
        rule.first > (int)std::size(hkDungeonAdvanceRefs)-rule.count) return false;
    for (int i=rule.first; i<rule.first+rule.count; ++i) {
        const int next = hkDungeonAdvanceRefs[i];
        if (next <= step_index || next >= (int)std::size(hkDungeonSteps)) continue;
        const auto& witness = hkDungeonSteps[next];
        if (step.map == pos.map && witness.map == pos.map && hk_dungeon_age(witness,pos) &&
            hk_dungeon_group(pos.dungeon,witness.first_completion,witness.completions,
                             witness.any_completion) == HK_DUNGEON_MET) return true;
    }
    return false;
}

static float hk_dungeon_distance(float x, float y, float z, float a, float b, float c) {
    const float dx=x-a, dy=y-b, dz=z-c;
    return dx*dx+dy*dy+dz*dz;
}

static int hk_dungeon_node_at(int scene, int floor, int room, float x, float z,
                              uint64_t actor = 0, float radius = 28) {
    int best = -1;
    float nearest = radius*radius;
    for (int i = 0; i < (int)std::size(hkDungeonNodes); ++i) {
        const auto& node = hkDungeonNodes[i];
        if (node.scene != scene || node.floor != floor || (room >= 0 && node.room != room)) continue;
        if (actor && node.actor == actor) return i;
        const float dx=node.x-x, dz=node.z-z, distance=dx*dx+dz*dz;
        if (distance < nearest) { nearest=distance; best=i; }
    }
    return best;
}

static int hk_dungeon_gate_state(const HkNavigation& position, int edge) {
    const auto& rule = hkDungeonGateRules[edge];
    return hk_dungeon_group(position.dungeon, rule.first, rule.count, rule.any);
}

static int hk_dungeon_map_room(int scene,int raw_room) {
    if (raw_room < 0) return -1;
    for (const auto& entry : hkDungeonRoomMaps)
        if (entry.scene == scene && entry.raw_room == raw_room) return entry.room;
    return -1;
}

static int hk_dungeon_inventory(const HkNavigation& position,int which) {
    for (const auto& entry : hkDungeonInventoryFields) if (entry.map == position.map) {
        const int index=which==0 ? entry.small_key : which==1 ? entry.boss_key : entry.water_level;
        if (hk_dungeon_condition_state(&position.dungeon,index)==HK_DUNGEON_UNKNOWN) return -1;
        return (int32_t)position.dungeon.values[index-position.dungeon.first];
    }
    return -1;
}

static HkDungeonPlan hk_dungeon_plan(const HkNavigation& position) {
    HkDungeonPlan plan;
    if (position.map <= 0 || position.map >= HK_MAP_COUNT ||
        !std::isfinite(position.x) || !std::isfinite(position.y) || !std::isfinite(position.z)) return plan;
    plan.floor = hk_map_floor(hkMapScenes[position.map], position.y);
    plan.fresh = position.dungeon.stamp && position.dungeon.map == position.map;
    if (plan.fresh) plan.room = hk_dungeon_map_room(position.map,position.dungeon.room);
    for (int i = 0; i < (int)std::size(hkDungeonSteps); ++i) {
        const auto& step = hkDungeonSteps[i];
        if (step.map != position.map) continue;
        plan.supported = true;
        if (!hk_dungeon_age(step, position)) continue;
        ++plan.total;
        const int done = hk_dungeon_group(position.dungeon, step.first_completion, step.completions, step.any_completion);
        if (plan.fresh && done == HK_DUNGEON_MET) {
            ++plan.completed;
            plan.finished |= step.final;
            continue;
        }
        if (plan.fresh && hk_dungeon_superseded(position,i)) {
            ++plan.superseded;
            continue;
        }
        if (plan.step >= 0) continue;
        const int pre = step.prerequisites ?
            hk_dungeon_group(position.dungeon, step.first_prerequisite, step.prerequisites, false) : HK_DUNGEON_MET;
        plan.step = i;
        plan.completion = plan.fresh ? done : HK_DUNGEON_UNKNOWN;
        plan.blocked = pre != HK_DUNGEON_MET;
    }
    if (plan.finished) plan.step = -1;
    if (!plan.fresh || plan.step < 0 || plan.floor < 0 || plan.blocked) return plan;
    const auto& step = hkDungeonSteps[plan.step];
    plan.reached = step.floor == plan.floor &&
        hk_dungeon_distance(position.x,position.y,position.z,step.x,step.y,step.z) < 3.0f*3.0f;
    if (plan.room < 0) {
        plan.uncertain_position=true;
        return plan;
    }
    plan.from = hk_dungeon_node_at(position.map,plan.floor,plan.room,position.x,position.z);
    plan.goal = hk_dungeon_node_at(position.map,step.floor,step.room,step.x,step.z,step.actor,80);
    // Breaking a floor web requires approaching from ABOVE it. Its actor origin
    // is on the lower floor and is not the place to stand before the drop.
    for (const auto& edge : hkDungeonEdges) {
        if (edge.kind != kDgDrop || edge.gate_actor != step.actor) continue;
        const auto& from=hkDungeonNodes[edge.from];
        if (from.scene != position.map || from.floor < step.floor) continue;
        if (plan.goal < 0 || from.floor > hkDungeonNodes[plan.goal].floor) {
            plan.goal=edge.from;
            plan.approach=edge.from;
            plan.reached=plan.floor == from.floor &&
                hk_dungeon_distance(position.x,position.y,position.z,from.x,from.y,from.z)<9;
        }
    }
    if (plan.from < 0 || plan.goal < 0) { plan.uncertain_position=true; return plan; }
    for (const auto& room : hkDungeonRestrictedRooms)
        if (room.map == position.map && room.room == plan.room) plan.room_obstacles=true;
    if (plan.from == plan.goal) { plan.route=true; return plan; }

    constexpr auto count = std::size(hkDungeonNodes);
    std::array<float,count> cost;
    std::array<int,count> previous;
    std::array<bool,count> visited{};
    cost.fill(std::numeric_limits<float>::infinity());
    previous.fill(-1);
    cost[plan.from] = 0;
    for (size_t iteration=0; iteration<count; ++iteration) {
        int here=-1;
        float nearest=std::numeric_limits<float>::infinity();
        for (int i=0; i<(int)count; ++i)
            if (!visited[i] && cost[i] < nearest) { nearest=cost[i]; here=i; }
        if (here < 0 || here == plan.goal) break;
        visited[here] = true;
        for (int i=0; i<(int)std::size(hkDungeonEdges); ++i) {
            const auto& edge=hkDungeonEdges[i];
            if (edge.from != here) continue;
            const auto& a=hkDungeonNodes[edge.from];
            const auto& b=hkDungeonNodes[edge.to];
            if (a.scene != position.map || b.scene != position.map) continue;
            const int gate = hk_dungeon_gate_state(position,i);
            // A blocked passage may identify the next mechanism to operate;
            // it is never presented as already traversable. Prefer open routes.
            const bool locked = edge.condition >= kDgMechanismGate && gate != HK_DUNGEON_MET;
            const float next = nearest + 1 + std::sqrt(hk_dungeon_distance(a.x,a.y,a.z,b.x,b.y,b.z)) + (locked ? 75 : 0);
            if (next < cost[edge.to]) { cost[edge.to]=next; previous[edge.to]=i; }
        }
    }
    if (previous[plan.goal] < 0) return plan;
    std::array<int,count> reversed{};
    int cursor=plan.goal, length=0;
    while (cursor != plan.from && length < (int)count) {
        const int edge=previous[cursor];
        if (edge < 0) return plan;
        reversed[length++]=edge;
        cursor=hkDungeonEdges[edge].from;
    }
    if (cursor != plan.from) return plan;
    plan.route=true;
    // Keep only the visible, first part. A new snapshot replans after movement.
    for (int i=length-1; i>=0 && plan.path_count<(int)plan.path.size(); --i)
        plan.path[plan.path_count++]=reversed[i];
    for (int i=0; i<plan.path_count; ++i) {
        const int edge_id=plan.path[i];
        const auto& edge=hkDungeonEdges[edge_id];
        const auto& a=hkDungeonNodes[edge.from];
        const auto& b=hkDungeonNodes[edge.to];
        if (edge.kind == kDgWalk && a.room == b.room && a.floor == b.floor) continue;
        plan.edge=edge_id;
        plan.next=edge.from;
        if (a.floor != plan.floor) break;
        const int state=hk_dungeon_gate_state(position,edge_id);
        plan.gate=edge.condition >= kDgMechanismGate && state != HK_DUNGEON_MET;
        return plan;
    }
    return plan;
}
