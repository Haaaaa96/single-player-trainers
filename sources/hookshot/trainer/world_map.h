#pragma once
#include <array>
#include <cmath>
#include <cwchar>
#include <limits>

enum HkMapKind : unsigned char {
    kMapRoom, kMapPassage, kMapDoor, kMapExit, kMapChest, kMapLoot, kMapFacility, kMapMechanism,
    kMapBoss, kMapGoal, kMapMiddleBoss, kMapQuest
};
struct HkMapPoint { float x, y, z; int floor; HkMapKind kind; const wchar_t *label; int target, age; };
struct HkMapScene {
    const wchar_t *label;
    int region, first, count, first_floor, floors, min_floor;
    float left, top, right, bottom;
    int first_segment, segments, rooms;
};
struct HkMapSegment { float x, z, door_x, door_z; int floor, room, other; };
#include "map_data.generated.h"
static_assert(std::size(hkMapScenes) == HK_MAP_COUNT);

static int hk_map_floor(const HkMapScene& map, float y) {
    if (!map.floors) return -1;
    const float* thresholds = hkMapFloors + map.first_floor;
    int floor = 0;
    while (floor+1 < map.floors && y >= thresholds[floor+1]) ++floor;
    return floor;
}

static int hk_map_zone(int id, float x, float z) {
    int lake = 0, ranch = 0;
    switch (id) {
    case kMapHyruleField_Adult: lake = kMapLakeHylia_Adult; ranch = kMapLonLonRanch_Adult; break;
    case kMapHyruleField_Child: lake = kMapLakeHylia_Child; ranch = kMapLonLonRanch_Child; break;
    default: return id;
    }
    for (const int zone : {lake, ranch}) {
        const auto& box = hkMapScenes[zone];
        if (x >= box.left && x <= box.right && z >= box.top && z <= box.bottom) return zone;
    }
    return id;
}

static float hk_map_distance(const HkMapPoint& point, const HkNavigation& pos) {
    const float x = point.x-pos.x, y = point.y-pos.y, z = point.z-pos.z;
    return x*x + y*y + z*z;
}

static const HkMapPoint *hk_dungeon_target(const HkNavigation& pos, const HkMapScene& scene, int choice) {
    const HkMapKind choices[] = {kMapGoal, kMapBoss, kMapExit};
    const HkMapPoint* target = nullptr;
    float nearest = std::numeric_limits<float>::infinity();
    for (int i = scene.first; i < scene.first+scene.count; ++i) {
        const auto& p = hkMapPoints[i];
        if (p.kind != choices[choice] || (p.age >= 0 && p.age != pos.child)) continue;
        const float d = hk_map_distance(p, pos);
        if (d < nearest) {
            target = &p;
            nearest = d;
        }
    }
    return target;
}

static const HkMapPoint *hk_map_quest_target(const HkNavigation& pos, const HkMapScene& scene, const wchar_t *who) {
    float nearest = std::numeric_limits<float>::infinity();
    const HkMapPoint* target = nullptr;
    if (!*who) return nullptr;
    for (int i = scene.first; i < scene.first+scene.count; ++i) {
        const auto& point = hkMapPoints[i];
        if (point.kind != kMapQuest || wcscmp(who, point.label)) continue;
        const float d = hk_map_distance(point, pos);
        if (d < nearest) {
            nearest = d;
            target = &point;
        }
    }
    return target;
}

static int hk_map_room(const HkMapScene& scene, int floor, float x, float z) {
    float best = 24.0f*24.0f;
    int room = -1;
    for (int i = scene.first_segment; i < scene.first_segment+scene.segments; ++i) {
        const auto& s = hkMapSegments[i];
        if (s.floor != floor) continue;
        const float dx = x-s.x, dz = z-s.z;
        const float d = dx*dx+dz*dz;
        if (d >= best) continue;
        best = d;
        room = s.room;
    }
    return room;
}

static const HkMapSegment *hk_map_door(const HkMapScene& scene, int floor,
                                       const HkNavigation& pos, const HkMapPoint& target) {
    if (target.floor != floor || !scene.rooms) return nullptr;
    const int from = hk_map_room(scene, floor, pos.x, pos.z);
    const int to = hk_map_room(scene, floor, target.x, target.z);
    if (from < 0 || to < 0 || from == to) return nullptr;
    std::array<int, HK_MAX_MAP_ROOMS> queue{}, first{};
    first.fill(-1);
    first[from] = -2;
    queue[0] = from;
    int tail = 1;
    for (int head = 0; head < tail; ++head) {
        const int room = queue[head];
        for (int i = scene.first_segment; i < scene.first_segment+scene.segments; ++i) {
            const auto& door = hkMapSegments[i];
            if (door.floor != floor || door.room != room || door.other < 0 || first[door.other] != -1) continue;
            first[door.other] = room == from ? i : first[room];
            if (door.other == to) return &hkMapSegments[first[to]];
            queue[tail++] = door.other;
        }
    }
    return nullptr;
}

static int hk_map_exit(const HkNavigation& pos, int goal) {
    if (pos.map <= 0 || pos.map >= HK_MAP_COUNT || goal <= 0 ||
        goal >= (int)std::size(hkMapRegionNames) || hkMapScenes[pos.map].region == goal) return -1;
    std::array<int, HK_MAP_COUNT> queue{}, distance{}, first_exit{};
    distance.fill(-1);
    queue[0] = pos.map;
    distance[pos.map] = 0;
    int tail = 1, best = -1, depth = HK_MAP_COUNT;
    float best_distance = std::numeric_limits<float>::infinity();
    for (int head = 0; head < tail; ++head) {
        const int id = queue[head];
        if (distance[id] > depth) break;
        if (hkMapScenes[id].region == goal) {
            const int via = first_exit[id];
            const float d = hk_map_distance(hkMapPoints[via], pos);
            if (d < best_distance) {
                best_distance = d;
                best = via;
                depth = distance[id];
            }
            continue;
        }
        const auto& scene = hkMapScenes[id];
        for (int index = scene.first; index < scene.first+scene.count; ++index) {
            const auto& mark = hkMapPoints[index];
            if (!mark.target) continue;
            if (mark.age >= 0 && mark.age != pos.child) continue;
            const int via = id == pos.map ? index : first_exit[id];
            const int next_depth = distance[id]+1;
            if (distance[mark.target] == next_depth && hk_map_distance(hkMapPoints[via], pos) <
                hk_map_distance(hkMapPoints[first_exit[mark.target]], pos)) first_exit[mark.target] = via;
            if (distance[mark.target] >= 0) continue;
            distance[mark.target] = next_depth;
            first_exit[mark.target] = via;
            queue[tail++] = mark.target;
        }
    }
    return best;
}
