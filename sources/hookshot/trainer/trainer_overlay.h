#include "trainer_api.h"
#include "destinations.generated.h"
#include "forest_route.h"
#include "jabu_route.h"
#include "world_map.h"
#include "trainer_quest.h"
#include "dungeon_route.h"

constexpr int kTrainerPage = 6, hkW = 860, hkH = 620;
constexpr int hkTableX = 20, hkTableW = hkW - 40;
constexpr int hkHeaderY = 245, hkListY = 275, hkRowH = 26, hkLines = 9;
constexpr int hkAmountY = 572, hkCloseX = 778, hkCloseW = 62;
constexpr int hkNavX = 20, hkNavY = 207, hkNavW = 180;
constexpr int hkFlightX = 20, hkFlightY = 253, hkFlightW = 180;
constexpr int hkAmmoKeepX = 378, hkAmmoKeepW = 210;
constexpr int hkMagicY = 158, hkMagicRefillX = 20, hkMagicRefillW = 112;
constexpr int hkMagicKeepX = 142, hkMagicKeepW = 156;
constexpr int hkSaveX = 680, hkSaveY = 318, hkSaveW = 160;
constexpr int hkTabX = 365, hkTabStep = 130, hkTabWidth = 120, hkItemShift = 77;
enum HkSection { hkMainQuest, hkCommon, hkItems };
static constexpr const wchar_t *hkTabNames[] = {L"主线", L"常用", L"道具"};
constexpr int hkAddX = 247, hkRemoveX = 395, hkItemActionW = 138;
constexpr int hkPriceX = 595, hkPriceW = 126, hkSlotsX = 727, hkSlotsW = 109;
constexpr int hkDropdownRowH = 26;
constexpr int hkTeleportY = 80, hkTeleportX = 760, hkTeleportW = 80;
static_assert(std::size(hkDestinations) == kTeleports + 1 &&
              std::size(hkDestinationNotes) == std::size(hkDestinations));
constexpr COLORREF hkInk = RGB(232, 239, 246), hkDim = RGB(166, 184, 201);
constexpr COLORREF hkBlue = RGB(49, 82, 113), hkCard = RGB(34, 47, 61);
constexpr COLORREF hkMint = RGB(139, 225, 180);
static const HkTrainerApi *hk_api() {
    static const HkTrainerApi *api = []() -> const HkTrainerApi * {
        using GetApi = const HkTrainerApi *(*)();
        const auto get = reinterpret_cast<GetApi>(GetProcAddress(GetModuleHandleW(nullptr), "hookshot_trainer_api"));
        const auto p = get ? get() : nullptr;
        return p && p->abi == HK_TRAINER_ABI && p->size == sizeof *p && p->count > 0 && p->count <= 512 ? p : nullptr;
    }();
    return api;
}

struct HkDropdown;
struct HkMenu {
    TrainerStatus state{};
    HkMagicStatus magic{-1, -1};
    std::vector<int> rows;
    std::vector<std::string> categories;
    std::wstring draft, query, money, quantity = L"1";
    int field = 0, category = 0, order = 0, selected = -1, offset = 0, ammo = 0, destination = 0;
    int forest_destination = 0, map_destination = 0, dungeon_destination = 0;
    unsigned pref_flags = 0;
    int prefs_save_result = 0;
    HkSection section = hkMainQuest;
    const HkDropdown *dropdown = nullptr;
    int dropdown_cursor = 0, dropdown_offset = 0;
    bool replace_text = false, composing = false, built = false;
};
static HkMenu hk;
static std::atomic<bool> hk_nav_overlay{false};
static std::atomic<int> hk_nav_destination{0};
static std::atomic<int> hk_world_destination{0}, hk_dungeon_destination{0};
static constexpr const wchar_t *hkDungeonDestinations[] = {L"逐步攻略", L"关键道具", L"首领", L"出口"};
static const wchar_t *const hkAmmo[] = {
    L"德库木棒", L"德库坚果", L"德库种子", L"炸弹", L"炸弹鼠", L"箭"
};
static const wchar_t *const hkAmmoWeapons[] = {
    nullptr, nullptr, L"妖精弹弓", nullptr, nullptr, L"妖精之弓"
};
static_assert(std::size(hkAmmo) == std::size(hkAmmoIds) && std::size(hkAmmo) == std::size(hkAmmoWeapons));
static const wchar_t *const hkOrders[] = {L"默认", L"售价升序", L"售价降序", L"格数升序", L"格数降序"};

static std::wstring hk_wide(const char *value) {
    wchar_t out[320]{};
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, value, -1, out, std::size(out))) return L"";
    return out;
}

struct HkDropdown {
    HkSection section;
    int x, y, width;
    const wchar_t *title;
    int& selected;
    const wchar_t *const *labels = nullptr;
    int label_count = 0;
    const wchar_t *const *details = nullptr;
    int popup_width = 0;

    int count() const { return labels ? label_count : (int)hk.categories.size() + 1; }
    int list_y() const { return y + 34; }
    int list_width() const { return popup_width ? popup_width : width + (details ? 32 : 0); }
    int lines() const { return std::min(count(), (hkH-list_y()-8)/hkDropdownRowH); }

    std::wstring name(int index) const {
        if (labels) return labels[index];
        return index ? hk_wide(hk.categories[index-1].c_str()) : L"全部";
    }

    std::wstring option_name(int index) const {
        auto text = name(index);
        if (details && details[index]) {
            text += L'（';
            text += details[index];
            text += L'）';
        }
        return text;
    }
};

static const HkDropdown hkDropdowns[] = {
    {hkCommon, 20, 119, 217, L"弹药：", hk.ammo, hkAmmo, std::size(hkAmmo), hkAmmoWeapons},
    {hkItems, 20, 207, 226, L"分类：", hk.category},
    {hkItems, 256, 207, 209, L"排序：", hk.order, hkOrders, std::size(hkOrders)},
    {hkCommon, 580, hkTeleportY, 170, L"", hk.destination, hkDestinations, std::size(hkDestinations),
     hkDestinationNotes, 260},
    {hkCommon, 210, hkNavY, 195, L"", hk.map_destination, hkMapRegionNames, std::size(hkMapRegionNames)},
    {hkCommon, 415, hkNavY, 183, L"迷宫：", hk.dungeon_destination, hkDungeonDestinations, std::size(hkDungeonDestinations)},
    {hkCommon, 610, hkNavY, 230, L"森林：", hk.forest_destination, hkForestDestinations, hkForestGoalCount, hkForestNotes, 230},
};

static bool hk_match(const char *value) {
    if (hk.query.empty()) return true;
    auto text = hk_wide(value);
    for (const wchar_t *p = text.c_str(); *p; ++p)
        if (!_wcsnicmp(p, hk.query.c_str(), hk.query.size())) return true;
    return false;
}

static void hk_filter() {
    const auto api = hk_api();
    hk.rows.clear();
    for (int i = 0; i < api->count; ++i) {
        const auto& item = api->items[i];
        if (hk.category && hk.categories[hk.category - 1] != item.category) continue;
        if (hk_match(item.name) || hk_match(item.actor)) hk.rows.push_back(i);
    }
    if (hk.order) std::stable_sort(hk.rows.begin(), hk.rows.end(), [&](int a, int b) {
        const auto &x = api->items[a], &y = api->items[b];
        const int av = hk.order <= 2 ? x.price : x.cells, bv = hk.order <= 2 ? y.price : y.cells;
        if ((av < 0) != (bv < 0)) return av >= 0;
        if (av < 0 || av == bv) return false;
        return hk.order % 2 ? av < bv : av > bv;
    });
    hk.offset = 0;
    hk.selected = -1;
    hk.quantity = L"1";
}

static void hk_focus(int field) {
    if (field == hk.field) return;
    hk.field = field;
    hk.replace_text = field >= 2;
    hk_api()->text_focus(field == 1 ? 1 : field ? 2 : 0);
}

struct HkBounds {
    float scale, left, top;
};

static HkBounds hk_bounds(float w, float h) {
    const float scale = std::min({std::max(1.0f, h/720.0f), (w-24)/hkW, (h-24)/hkH});
    return {scale, (w-hkW*scale)/2, (h-hkH*scale)/2};
}

struct HkPaint {
    ImDrawList *draw;
    HkBounds bounds;
    ImFont *font;
    int points;

    ImVec2 at(float x, float y) const {
        return {bounds.left + x*bounds.scale, bounds.top + y*bounds.scale};
    }
};

static std::string hk_utf8(const std::wstring& text) {
    if (text.empty()) return {};
    const int count = WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), nullptr, 0, nullptr, nullptr);
    std::string result(count, '\0');
    if (count) WideCharToMultiByte(CP_UTF8, 0, text.data(), (int)text.size(), result.data(), count, nullptr, nullptr);
    return result;
}

static ImFont *hk_font(const char *label, const wchar_t *filename, ImFont *fallback) {
    auto *atlas = ImGui::GetIO().Fonts;
    for (auto *font : atlas->Fonts)
        if (strcmp(font->GetDebugName(), label) == 0) return font;
    if (atlas->Locked) return fallback;
    wchar_t folder[MAX_PATH]{};
    const UINT count = GetWindowsDirectoryW(folder, std::size(folder));
    if (!count || count >= std::size(folder)) return fallback;
    const std::wstring path = std::wstring(folder) + L"\\Fonts\\" + filename;
    if (GetFileAttributesW(path.c_str()) == INVALID_FILE_ATTRIBUTES) return fallback;
    ImFontConfig config;
    snprintf(config.Name, sizeof config.Name, "%s", label);
    const auto utf8 = hk_utf8(path);
    auto *font = atlas->AddFontFromFileTTF(utf8.c_str(), 19.0f, &config);
    return font ? font : fallback;
}

static ImU32 hk_color(COLORREF color) {
    return IM_COL32(GetRValue(color), GetGValue(color), GetBValue(color), 255);
}

static void hk_fill(HkPaint& dc, int x, int y, int w, int h, COLORREF color) {
    dc.draw->AddRectFilled(dc.at(x, y), dc.at(x+w, y+h), hk_color(color));
}

static void hk_draw_text(HkPaint& dc, int x, int y, int w, int h, const std::wstring& text, COLORREF color = hkInk,
                         UINT format = DT_LEFT) {
    std::string value = hk_utf8(text);
    if (value.empty()) return;
    const float px = dc.points*dc.bounds.scale, room = w*dc.bounds.scale;
    ImVec2 size = ui::size_of(dc.font, px, value.c_str());
    if (size.x > room) {
        const float dots = ui::size_of(dc.font, px, "…").x;
        const char *end = value.c_str();
        dc.font->CalcTextSizeA(px, std::max(0.0f, room-dots), 0, value.c_str(), nullptr, &end);
        value.resize(end-value.c_str());
        value += "…";
        size = ui::size_of(dc.font, px, value.c_str());
    }
    const auto corner = dc.at(x, y);
    const float remaining = std::max(0.0f, room-size.x);
    const float dx = format == DT_CENTER ? remaining/2 : format == DT_RIGHT ? remaining : 0.0f;
    const float dy = (h*dc.bounds.scale-px)/2;
    const auto end = dc.at(x+w, y+h);
    const ImVec4 clip(corner.x, corner.y, end.x, end.y);
    dc.draw->AddText(dc.font, px, {corner.x+dx, corner.y+dy}, hk_color(color), value.c_str(), nullptr, 0, &clip);
}
// Map instructions must wrap: a clipped single line can hide the required action.
static void hk_draw_paragraph(HkPaint& dc, int x, int y, int w, int h,
                              const std::wstring& text, COLORREF color = hkInk) {
    const auto value = hk_utf8(text);
    if (value.empty()) return;
    const auto corner = dc.at(x, y), end = dc.at(x+w, y+h);
    const ImVec4 clip(corner.x, corner.y, end.x, end.y);
    dc.draw->AddText(dc.font, dc.points*dc.bounds.scale, corner, hk_color(color),
                     value.c_str(), nullptr, w*dc.bounds.scale, &clip);
}
static void hk_button(HkPaint& dc, int x, int y, int w, const std::wstring& text, bool enabled = true) {
    hk_fill(dc, x, y, w, 31, enabled ? hkBlue : hkCard);
    hk_draw_text(dc, x+5, y, w-10, 31, text, enabled ? hkInk : hkDim, DT_CENTER);
}
static void hk_edit(HkPaint& dc, int x, int y, int w, int field, const std::wstring& value, const wchar_t *placeholder) {
    hk_fill(dc, x, y, w, 31, hk.field == field ? RGB(51, 98, 124) : hkCard);
    if (hk.field == field) hk_fill(dc, x, y+29, w, 2, hkMint);
    const auto text = (hk.field == field && !hk.replace_text && !hk.composing) ? value + L"|" : value;
    hk_draw_text(dc, x+8, y, w-16, 31, text.empty() ? placeholder : text, text.empty() ? hkDim : hkInk);
}
static const TrainerItem *hk_item() {
    return hk.selected >= 0 && hk.selected < (int)hk.rows.size() ? &hk_api()->items[hk.rows[hk.selected]] : nullptr;
}

static void hk_paint_dropdown_button(HkPaint& dc, const HkDropdown& menu) {
    hk_fill(dc, menu.x, menu.y, menu.width, 31, hkBlue);
    hk_draw_text(dc, menu.x+9, menu.y, menu.width-37, 31, menu.title + menu.name(menu.selected));
    const int arrow = menu.x + menu.width - 17;
    const int direction = hk.dropdown == &menu ? -1 : 1;
    dc.draw->AddTriangleFilled(dc.at(arrow-5, menu.y+15-3*direction),
                               dc.at(arrow+5, menu.y+15-3*direction),
                               dc.at(arrow, menu.y+15+3*direction), hk_color(hkInk));
}

static void hk_paint_dropdown(HkPaint& dc, const HkDropdown& menu) {
    const int count = menu.count(), lines = menu.lines();
    const int height = lines * hkDropdownRowH;
    const int top = menu.list_y(), width = menu.list_width();
    hk_fill(dc, menu.x-1, top-1, width+2, height+2, hkBlue);
    for (int row = 0; row < lines; ++row) {
        const int index = hk.dropdown_offset + row;
        const int y = top + row*hkDropdownRowH;
        hk_fill(dc, menu.x, y, width, hkDropdownRowH, index == hk.dropdown_cursor ? hkBlue : hkCard);
        if (index == menu.selected) hk_fill(dc, menu.x+3, y+6, 3, hkDropdownRowH-12, hkMint);
        hk_draw_text(dc, menu.x+14, y, width-28, hkDropdownRowH, menu.option_name(index),
                     index == menu.selected ? hkMint : hkInk);
    }
    if (count > lines) {
        const int thumb = std::max(12, height*lines/count);
        const int y = top + (height-thumb)*hk.dropdown_offset/(count-lines);
        hk_fill(dc, menu.x+width-4, y, 3, thumb, hkDim);
    }
}

static bool hk_visible_navigation(bool allow, HkNavigation& position) {
    return allow && hk_nav_overlay.load(std::memory_order_relaxed) && hk_api()->navigation_sample(&position);
}

static void hk_set_navigation(bool enabled) {
    hk_api()->navigation_set(enabled);
    hk_nav_overlay.store(enabled);
}

static void hk_apply_prefs(HkTrainerPrefs prefs) {
    hk.pref_flags = prefs.flags;
    hk.forest_destination = prefs.forest_destination;
    hk_nav_destination.store(prefs.forest_destination);
    hk_set_navigation(!!(prefs.flags & HK_PREF_NAVIGATION));
}

static void hk_save_preference(unsigned mask, unsigned flags, int destination = -1) {
    const auto api = hk_api();
    hk.prefs_save_result = api->prefs_set(mask, flags, destination) ? 1 : -1;
    hk_apply_prefs(api->prefs_get());
}

static void hk_sync_flight() {
    int expected = player_flight.load();
    if (!(hk.pref_flags & HK_PREF_FLIGHT) || hk_flight_effective(expected, cheats_on()) >= 0 ||
        GetTickCount64() < hk_flight_arm_due.load()) return;
    const auto status = hk_api()->status(nullptr);
    if (!status.ready || status.pending) return;
    player_flight.compare_exchange_strong(expected, 2);
}

static void hk_map_arrow(HkPaint& dc, ImVec2 start, ImVec2 end, float scale) {
    dc.draw->AddLine(start, end, hk_color(hkMint), 3.4f*scale);
    const float dx = end.x-start.x, dy = end.y-start.y, length = std::sqrt(dx*dx+dy*dy);
    if (length > 8*scale) {
        const float ux = dx/length, uy = dy/length;
        const ImVec2 tip = {start.x+dx*0.78f, start.y+dy*0.78f};
        const ImVec2 tail = {tip.x-6*scale*ux, tip.y-6*scale*uy};
        dc.draw->AddTriangleFilled(tip, {tail.x-4*scale*uy, tail.y+4*scale*ux},
                                  {tail.x+4*scale*uy, tail.y-4*scale*ux}, hk_color(hkMint));
    }
}

static void hk_paint_jabu_map(HkPaint& dc, const HkNavigation& position, float scale) {
    constexpr auto player_color = RGB(118, 202, 255), goal_color = RGB(247, 203, 118);
    const int floor = hk_jabu_floor(position.x, position.y, position.z);
    const auto plan = hk_jabu_plan(position.x, position.y, position.z, position.guide_step);
    constexpr const wchar_t *floors[] = {L"地下区域", L"入口层", L"上层区域"};
    dc.draw->AddRectFilled(dc.at(0, 0), dc.at(244, 264), IM_COL32(18, 26, 34, 229), 8*scale);
    hk_draw_text(dc, 12, 5, 220, 27, L"加卜加卜大人腹中");
    hk_fill(dc, 10, 36, 224, 175, RGB(25, 39, 49));
    if (floor >= 0) {
        auto map = [&](float x, float z) { return dc.at(122+1.85f*x, 197+0.69f*z); };
        auto point = [&](int node) { return map(hkJabuPoints[node].x, hkJabuPoints[node].z); };
        for (const auto [from, to] : hkJabuEntryPath) {
            if (hkJabuPoints[from].floor == floor)
                dc.draw->AddLine(point(from), point(to), hk_color(hkDim), 2*scale);
        }
        for (int node = 0; node < kJabuNodeCount; ++node)
            if (hkJabuPoints[node].floor == floor)
                dc.draw->AddCircleFilled(point(node), 2.4f*scale, hk_color(hkDim));
        const auto player = map(position.x, position.z);
        if (plan.target >= 0) {
            const auto goal = point(plan.target);
            hk_map_arrow(dc, player, goal, scale);
            dc.draw->AddCircleFilled(goal, 5.5f*scale, hk_color(goal_color));
        }
        dc.draw->AddCircleFilled(player, 4.2f*scale, hk_color(player_color));
    }
    dc.points = 14;
    hk_draw_text(dc, 16, 40, 69, 20, floor >= 0 ? floors[floor] : L"定位中", hkDim);
    hk_draw_text(dc, 12, 215, 220, 22, floor >= 0 ? plan.instruction : L"等待楼层定位",
                 plan.target >= 0 ? hkMint : hkDim);
    hk_draw_text(dc, 12, 239, 73, 18, L"蓝点：你", player_color);
    if (plan.target >= 0) hk_draw_text(dc, 101, 239, 129, 18, L"金点：下一步", goal_color);
}

static void hk_paint_world_map(HkPaint& dc, HkNavigation position, float scale) {
    constexpr auto player_color = RGB(118, 202, 255), goal_color = RGB(247, 203, 118);
    const int start_map = position.map;
    const int selected_destination = hk_world_destination.load();
    if (selected_destination) position.goal_region = selected_destination;
    position.map = hk_map_zone(start_map, position.x, position.z);
    const auto& scene = hkMapScenes[position.map];
    const int floor = hk_map_floor(scene, position.y);
    int route = hk_map_exit(position, position.goal_region);
    if (route < 0 && position.map != start_map && scene.region != position.goal_region) {
        HkNavigation field_position = position;
        field_position.map = start_map;
        route = hk_map_exit(field_position, position.goal_region);
    }
    const auto* exit = route >= 0 ? &hkMapPoints[route] : nullptr;
    const bool here = position.goal_region > 0 && scene.region == position.goal_region;
    const auto* local_quest = !scene.floors && here && !selected_destination && position.quest < HK_QUEST_COUNT ?
        hk_map_quest_target(position, scene, hk_quests[position.quest].steps[position.step].who) : nullptr;
    const auto* target = exit ? exit : scene.floors && (!position.goal_region || here) ?
        hk_dungeon_target(position, scene, std::max(0,hk_dungeon_destination.load()-1)) : local_quest;
    const auto* door = target && floor >= 0 ? hk_map_door(scene, floor, position, *target) : nullptr;
    dc.draw->AddRectFilled(dc.at(0, 0), dc.at(282, 310), IM_COL32(18, 26, 34, 229), 8*scale);
    hk_draw_text(dc, 12, 6, 258, 26, scene.label ? scene.label : L"当前区域");
    dc.points = 14;
    std::wstring floor_label;
    if (floor >= 0) {
        const int display_floor = floor + scene.min_floor;
        floor_label = display_floor < 0 ? L"地下" + std::to_wstring(-display_floor) + L"层" :
                                        std::to_wstring(display_floor+1) + L"层";
    } else {
        floor_label = scene.label ? L"地面" : L"位置坐标";
    }
    wchar_t coordinates[80]{};
    swprintf(coordinates, std::size(coordinates), L"X %.0f   Y %.0f   Z %.0f", position.x, position.y, position.z);
    hk_draw_text(dc, 12, 32, 63, 23, floor_label, hkDim);
    hk_draw_text(dc, 78, 32, 190, 23, coordinates, hkDim, DT_RIGHT);
    hk_fill(dc, 10, 58, 262, 188, RGB(25, 39, 49));
    const float left = scene.label ? std::min(scene.left, position.x-2) : position.x-20;
    const float right = scene.label ? std::max(scene.right, position.x+2) : position.x+20;
    const float top = scene.label ? std::min(scene.top, position.z-2) : position.z-20;
    const float bottom = scene.label ? std::max(scene.bottom, position.z+2) : position.z+20;
    const float unit = std::min(239/(right-left), 165/(bottom-top));
    const auto map = [&](float x, float z) {
        return dc.at(141 + (x-(left+right)*.5f)*unit, 152 + (z-(top+bottom)*.5f)*unit);
    };
    const auto player = map(position.x, position.z);
    for (int i = scene.first_segment; i < scene.first_segment+scene.segments; ++i) {
        const auto& segment = hkMapSegments[i];
        if (segment.floor == floor)
            dc.draw->AddLine(map(segment.x, segment.z), map(segment.door_x, segment.door_z),
                             hk_color(RGB(69, 90, 106)), 1.8f*scale);
    }
    const HkMapPoint* nearest = nullptr;
    float nearest_dist = std::numeric_limits<float>::infinity();
    for (int i = scene.first; i < scene.first+scene.count; ++i) {
        const auto& p = hkMapPoints[i];
        if (p.floor != floor || (p.age >= 0 && p.age != position.child)) continue;
        const auto dot = map(p.x, p.z);
        const auto color = p.kind == kMapExit ? hkMint : p.kind == kMapDoor || p.kind == kMapPassage ? hkDim :
            p.kind == kMapBoss || p.kind == kMapMiddleBoss ? RGB(253, 135, 126) :
            p.kind == kMapChest || p.kind == kMapLoot || p.kind == kMapGoal ? goal_color :
            p.kind == kMapMechanism || p.kind == kMapFacility ? RGB(194, 161, 244) : RGB(87, 111, 127);
        dc.draw->AddCircleFilled(dot, (p.kind == kMapRoom ? 3.5f : 2.8f)*scale, hk_color(color));
        if (!*p.label) continue;
        const float dist = hk_map_distance(p, position);
        if (dist < nearest_dist) {
            nearest = &p;
            nearest_dist = dist;
        }
    }
    const auto goal = target ? map(target->x, target->z) : player;
    // In indoor scenes a different floor may require a lift or a drop.
    if (target && target->floor == floor && goal.x >= dc.at(10, 58).x && goal.x <= dc.at(272, 246).x &&
        goal.y >= dc.at(10, 58).y && goal.y <= dc.at(272, 246).y) {
        dc.draw->AddCircleFilled(goal, 5.0f*scale, hk_color(goal_color));
        if (!scene.floors) hk_map_arrow(dc, player, goal, scale);
    }
    if (door) {
        const auto doorway = map(door->door_x, door->door_z);
        hk_map_arrow(dc, player, doorway, scale);
        dc.draw->AddCircleFilled(doorway, 4.2f*scale, hk_color(hkMint));
    }
    dc.draw->AddCircleFilled(player, 4.5f*scale, hk_color(player_color));
    if (position.goal_region)
        hk_draw_text(dc, 12, 249, 258, 23, std::wstring(selected_destination ? L"目的地：" : L"主线：") +
            hkMapRegionNames[position.goal_region], hkMint);
    if (exit)
        hk_draw_text(dc, 12, 274, 258, 22, std::wstring(L"出口往：") + exit->label, goal_color);
    else if (target)
        hk_draw_text(dc, 12, 274, 258, 22, std::wstring(L"目标：") + target->label +
            (target->floor < floor ? L" · 下层" : target->floor > floor ? L" · 上层" : L""), goal_color);
    else if (selected_destination && !here)
        hk_draw_text(dc, 12, 274, 258, 22, L"此处未找到可标注的出口", hkDim);
    else if (nearest)
        hk_draw_text(dc, 12, 274, 258, 22, std::wstring(L"附近：") + nearest->label, hkDim);
    else if (here)
        hk_draw_text(dc, 12, 274, 258, 22, L"打开面板查看主线步骤", hkDim);
}

#include "dungeon_overlay.h"

static void hk_paint_navigation(ui::Ctx& c, const HkNavigation& position) {
    const float scale = std::clamp(c.h/720.0f, 0.6f, 2.0f);
    HkPaint dc{c.d, {scale, 14*scale, 90*scale}, hk_font("HookshotTrainer YaHei", L"msyh.ttc", c.f.body), 16};
    const int selected_region=hk_world_destination.load();
    if (!hk_dungeon_destination.load() && position.map > 0 && position.map < HK_MAP_COUNT &&
        (!selected_region || selected_region == hkMapScenes[position.map].region) &&
        hk_paint_dungeon_map(dc,position,scale)) return;
    if (!hk_world_destination.load() && !hk_dungeon_destination.load() && position.map == kMapInsideJabuJabuBelly &&
        hk_jabu_plan(position.x, position.y, position.z, position.guide_step).target >= 0) {
        hk_paint_jabu_map(dc, position, scale);
        return;
    }
    if (position.map != kMapLostWood_Child && position.map != kMapLostWood_Adult) {
        hk_paint_world_map(dc, position, scale);
        return;
    }
    constexpr auto player_color = RGB(118, 202, 255);
    int destination = hk_nav_destination.load();
    if (const int selected = hk_world_destination.load()) {
        const int route = hk_map_exit(position, selected);
        if (route < 0) {
            hk_paint_world_map(dc, position, scale);
            return;
        }
        const int destination_map = hkMapPoints[route].target;
        switch (destination_map) {
        case kMapSacredForestMeadow_Adult:
        case kMapSacredForestMeadow_Child: destination = 0; break;
        case kMapGoronCity_Adult:
        case kMapGoronCity_Child: destination = 1; break;
        case kMapZoraRiver_Adult:
        case kMapZoraRiver_Child: destination = 2; break;
        case kMapKokiriForest_Adult:
        case kMapKokiriForest_Child: destination = 3; break;
        default: hk_paint_world_map(dc, position, scale); return;
        }
    }
    const auto plan = hk_forest_plan(position.x, position.y, position.z, destination);
    constexpr auto goal_color = RGB(247, 203, 118);
    dc.draw->AddRectFilled(dc.at(0, 0), dc.at(232, 248), IM_COL32(18, 26, 34, 229), 8*scale);
    hk_draw_text(dc, 12, 5, 208, 29, std::wstring(L"前往：") + hkForestDestinations[destination]);
    hk_fill(dc, 10, 36, 212, 169, RGB(25, 39, 49));
    auto map = [&](HkForestPoint p) { return dc.at(88 + 1.80f*p.x, 155 + 1.28f*p.z); };
    hk_draw_text(dc, 16, 40, 55, 20, L"路线图", hkDim);
    for (auto [a,b] : hkForestEdges)
        dc.draw->AddLine(map(hkForestNodes[a]), map(hkForestNodes[b]), hk_color(hkDim), 2*scale);
    for (auto room : hkForestNodes) dc.draw->AddCircleFilled(map(room), 2.4f*scale, hk_color(hkDim));
    if (plan.count > 0) {
        for (int i = 1; i < plan.count; ++i)
            dc.draw->AddLine(map(hkForestNodes[plan.stops[i-1]]), map(hkForestNodes[plan.stops[i]]),
                             hk_color(RGB(74, 152, 116)), 2.8f*scale);
        const auto a = map(plan.start), b = map(hkForestNodes[plan.stops[0]]);
        dc.draw->AddLine(a, b, hk_color(hkMint), 4.0f*scale);
        const float dx = b.x-a.x, dy = b.y-a.y, length = std::sqrt(dx*dx+dy*dy);
        if (length > 1.0f) {
            const float ux = dx/length, uy = dy/length;
            const ImVec2 tip = {a.x+dx*0.78f, a.y+dy*0.78f};
            const ImVec2 tail = {tip.x-6*scale*ux, tip.y-6*scale*uy};
            dc.draw->AddTriangleFilled(tip, {tail.x-4*scale*uy, tail.y+4*scale*ux},
                                      {tail.x+4*scale*uy, tail.y-4*scale*ux}, hk_color(hkMint));
        }
    }
    dc.draw->AddCircleFilled(map(hkForestNodes[hkForestGoals[destination]]), 5.6f*scale, hk_color(goal_color));
    if (hk_forest_surface(position.x, position.y, position.z) &&
        position.x > -40 && position.x < 72 && position.z > -90 && position.z < 35)
        dc.draw->AddCircleFilled(map({position.x, position.z}), 4.5f*scale, hk_color(player_color));

    const auto direction = plan.arrived ? (destination == hkForestGoalCount-1 ? L"已到洞口" : L"已到出口，继续通过")
                         : plan.count > 0 ? hk_forest_direction(plan) : L"当前不在已知通路上";
    hk_draw_text(dc, 12, 207, 208, 22, direction, plan.arrived || plan.count ? hkMint : hkDim);
    dc.points = 14;
    hk_draw_text(dc, 12, 228, 60, 17, L"蓝点：你", player_color);
    hk_draw_text(dc, 80, 228, 140, 17, hkForestNotes[destination] ? hkForestNotes[destination] : L"金点：目的地", goal_color);
}

static void hk_paint_quest(HkPaint& dc, const HkQuestStatus& status, bool fresh) {
    if (!fresh) {
        hk_draw_text(dc, 24, 82, 812, 44,
                     hk.state.ready ? L"正在读取当前任务进度…" : L"请先载入存档并进入游戏。", hkDim);
        return;
    }
    if (status.quest == HK_QUEST_COUNT) {
        hk_draw_text(dc, 24, 82, 812, 44, L"主线已完成", hkMint);
        return;
    }
    const auto& quest = hk_quests[status.quest];
    const auto& step = quest.steps[status.step];
    hk_fill(dc, 20, 80, 820, 214, hkCard);
    dc.points = 23;
    hk_draw_text(dc, 36, 86, 785, 40, quest.title, hkMint);
    dc.points = 19;
    hk_draw_text(dc, 36, 135, 90, 28, L"去哪", hkDim);
    hk_draw_text(dc, 135, 135, 680, 28, step.where);
    if (*step.who) {
        hk_draw_text(dc, 36, 171, 90, 28, L"找谁", hkDim);
        hk_draw_text(dc, 135, 171, 680, 28, step.who);
    }
    const int y = *step.who ? 207 : 177;
    hk_draw_text(dc, 36, y, 90, 28, L"做什么", hkDim);
    const std::wstring action(step.action);
    hk_draw_text(dc, 135, y, 680, 28, action.substr(0, 34));
    if (action.size() > 34) hk_draw_text(dc, 135, y+29, 680, 28, action.substr(34));
}

static void hk_paint_dungeon_guide(HkPaint& dc, const HkQuestStatus& status) {
    const auto& guide = hk_dungeon_guides[status.guide-1];
    hk_fill(dc, 20, 306, 820, 289, hkCard);
    dc.points = 22;
    hk_draw_text(dc, 36, 313, 785, 36, std::wstring(L"当前地点攻略 · ") + guide.name, hkMint);
    dc.points = 17;
    for (int i = 0; i < (int)std::size(guide.steps) && guide.steps[i]; ++i) {
        const int y = 351+i*29;
        const bool current = i+1 == status.guide_step;
        if (current) hk_fill(dc, 28, y, 804, 28, hkBlue);
        hk_draw_text(dc, 36, y, 39, 28, std::to_wstring(i+1), current ? hkMint : hkDim);
        hk_draw_text(dc, 76, y, 750, 28, guide.steps[i], current ? hkMint : hkInk);
    }
}

static void hk_paint(ui::Ctx& c) {
    const auto bounds = hk_bounds(c.w, c.h);
    if (bounds.scale <= 0) return;
    HkPaint dc{c.d, bounds, hk_font("HookshotTrainer YaHei Bold", L"msyhbd.ttc", c.f.strong), 26};
    HkQuestStatus quest{};
    const bool quest_fresh = hk.section == hkMainQuest && hk_api()->quest_sample(&quest);
    const bool show_guide = quest_fresh && quest.guide > 0 && quest.guide <= HK_DUNGEON_COUNT;
    const int panel_height = hk.section == hkItems ? 570 : hk.section == hkMainQuest ? (show_guide ? 610 : 318) : 362;
    hk_fill(dc, 0, 0, hkW, panel_height, RGB(21, 29, 39));
    hk_fill(dc, 0, 0, hkW, 3, hkMint);
    hk_draw_text(dc, 20, 9, 337, 33, L"时之笛 · 中文修改器");
    dc.font = hk_font("HookshotTrainer YaHei", L"msyh.ttc", c.f.body);
    dc.points = 19;
    for (int i = 0; i < (int)std::size(hkTabNames); ++i) {
        const int x = hkTabX + i*hkTabStep;
        hk_fill(dc, x, 11, hkTabWidth, 31, i == hk.section ? hkBlue : hkCard);
        hk_draw_text(dc, x, 11, hkTabWidth, 31, hkTabNames[i], i == hk.section ? hkMint : hkInk, DT_CENTER);
    }
    hk_button(dc, hkCloseX, 11, hkCloseW, L"关闭");
    wchar_t summary[110]{};
    if (hk.state.ready)
        swprintf(summary, std::size(summary), L"生命 %.2f / %.2f 心       卢比 %d / %d",
                 hk.state.health/4.0, hk.state.max_health/4.0, hk.state.rupees, hk.state.wallet);
    hk_draw_text(dc, 20, 46, 600, 26, hk.state.ready ? summary : L"请先读档并进入可操作场景。", hkMint);
    hk_draw_text(dc, 630, 46, 210, 26, L"面板快捷键：`", hkDim, DT_RIGHT);
    if (hk.section == hkMainQuest) {
        hk_paint_quest(dc, quest, quest_fresh);
        if (show_guide) hk_paint_dungeon_guide(dc, quest);
        return;
    }
    const bool enabled = hk.state.ready && !hk.state.pending;
    if (hk.section == hkCommon) {
        hk_button(dc, 20, 80, 112, L"回满生命", enabled);
        hk_button(dc, 142, 80, 156, hk.pref_flags & HK_PREF_HEALTH ? L"保持满血：开" : L"保持满血：关");
        hk_draw_text(dc, 324, 80, 49, 31, L"卢比");
        hk_edit(dc, 373, 80, 80, 2, hk.money, L"数量");
        hk_button(dc, 462, 80, 107, L"设置卢比", enabled);
        hk_button(dc, hkTeleportX, hkTeleportY, hkTeleportW, L"传送", enabled && hk.destination);
        hk_button(dc, 247, 119, 113, L"补满弹药", enabled);
        hk_button(dc, hkAmmoKeepX, 119, hkAmmoKeepW,
                  hk.pref_flags & HK_PREF_AMMO ? L"弹药不减少：开" : L"弹药不减少：关");
        hk_button(dc, hkMagicRefillX, hkMagicY, hkMagicRefillW, L"补满魔力", enabled && hk.magic.maximum > 0);
        hk_button(dc, hkMagicKeepX, hkMagicY, hkMagicKeepW,
                  hk.pref_flags & HK_PREF_MAGIC ? L"魔力不减少：开" : L"魔力不减少：关");
        wchar_t magic[70]{};
        if (hk.magic.maximum > 0)
            swprintf(magic, std::size(magic), L"魔力 %.1f / %.0f", hk.magic.current / 10.0, hk.magic.maximum / 10.0);
        hk_draw_text(dc, 324, hkMagicY, 480, 31,
                     hk.magic.maximum > 0 ? magic : hk.magic.maximum == 0 ? L"尚未解锁魔力槽" : L"等待魔力数据",
                     hk.magic.maximum > 0 ? hkMint : hkDim);
        hk_button(dc, hkNavX, hkNavY, hkNavW, hk_nav_overlay.load() ? L"地图指引：开" : L"地图指引：关");
        const int flight = menu_player_flight();
        hk_button(dc, hkFlightX, hkFlightY, hkFlightW,
                  flight > 0 ? L"飞行：飞行中" : flight == 0 ? L"飞行：待起飞" :
                  hk.pref_flags & HK_PREF_FLIGHT ? L"飞行：等待场景" : L"飞行：关");
        hk_draw_text(dc, 212, hkFlightY, 620, 30, L"起降：F6；ZL+ZR+右摇杆按下，保持半秒。", hkDim);
        hk_draw_text(dc, 212, hkFlightY+33, 620, 28, L"Xbox：LT+RT+RS。松开再用；B/R 上升，L 下降。", hkDim);
        hk_draw_text(dc, 20, hkSaveY, 641, 30,
                     hk.prefs_save_result > 0 ? L"开关设置已保存" :
                     hk.prefs_save_result < 0 ? L"设置已应用，但保存失败；可点击「保存设置」重试。" :
                     hk_wide(hk.state.message), hk.prefs_save_result < 0 ? hkDim : hkMint);
        hk_button(dc, hkSaveX, hkSaveY, hkSaveW, L"保存设置");
        for (const auto& menu : hkDropdowns) if (menu.section == hkCommon) hk_paint_dropdown_button(dc, menu);
        if (hk.dropdown) hk_paint_dropdown(dc, *hk.dropdown);
        return;
    }
    dc.bounds.top -= hkItemShift*dc.bounds.scale;
    hk_fill(dc, hkTableX, 159, hkTableW, 1, RGB(61, 81, 100));
    hk_edit(dc, 20, 169, 420, 1, hk.draft, L"道具名或代号 · 输入后按回车");
    hk_button(dc, 450, 169, 88, L"搜索");
    hk_button(dc, 548, 169, 88, L"清除");
    for (const auto& menu : hkDropdowns) if (menu.section == hkItems) hk_paint_dropdown_button(dc, menu);
    hk_draw_text(dc, 485, 207, 355, 31, L"显示 " + std::to_wstring(hk.rows.size()) + L" / " + std::to_wstring(hk_api()->count) +
                  L" 条", hkDim, DT_RIGHT);
    hk_fill(dc, hkTableX, hkHeaderY, hkTableW, hkListY-hkHeaderY-1, hkBlue);
    hk_draw_text(dc, 26, hkHeaderY, 72, 29, L"状态");
    hk_draw_text(dc, 105, hkHeaderY, 399, 29, L"道具名称");
    hk_draw_text(dc, 510, hkHeaderY, 80, 29, L"分类");
    hk_draw_text(dc, hkPriceX, hkHeaderY, hkPriceW, 29, L"售价（卢比）", hkInk, DT_CENTER);
    hk_draw_text(dc, hkSlotsX, hkHeaderY, hkSlotsW, 29, L"占用格数", hkInk, DT_CENTER);
    if (hk.rows.empty()) hk_draw_text(dc, 25, hkListY, hkTableW-10, 30, L"没有符合当前筛选的道具。", hkDim);
    for (int j = 0; j < hkLines && hk.offset+j < (int)hk.rows.size(); ++j) {
        const int r = hk.offset+j, y = hkListY + j*hkRowH;
        const auto& item = hk_api()->items[hk.rows[r]];
        hk_fill(dc, hkTableX, y, hkTableW, hkRowH-1, r == hk.selected ? hkBlue : j%2 ? RGB(27, 38, 50) : hkCard);
        hk_draw_text(dc, 26, y, 72, hkRowH,
                     item.restriction[0] ? L"仅查看" : hk_is_bottle_content(&item) ? L"可装瓶" : L"可增删",
                     item.restriction[0] ? hkDim : hkMint);
        hk_draw_text(dc, 105, y, 399, hkRowH, hk_wide(item.name));
        hk_draw_text(dc, 510, y, 80, hkRowH, hk_wide(item.category), hkDim);
        hk_draw_text(dc, hkPriceX, y, hkPriceW, hkRowH, item.price < 0 ? L"—" : std::to_wstring(item.price),
                     item.price < 0 ? hkDim : hkInk, DT_CENTER);
        hk_draw_text(dc, hkSlotsX, y, hkSlotsW, hkRowH, item.cells < 0 ? L"—" : std::to_wstring(item.cells),
                     item.cells < 0 ? hkDim : hkInk, DT_CENTER);
    }
    const auto item = hk_item();
    const bool empty_bottle = item && hk_is_empty_bottle(item) && !item->restriction[0];
    const bool bottle_content = item && hk_is_bottle_content(item);
    hk_draw_text(dc, 20, 513, hkTableW, 24, item ? item->restriction[0] ? hk_wide(item->restriction)
        : bottle_content ? L"优先装入已有空瓶。没有空瓶时，尝试新添 1 个再装入。"
        : empty_bottle ? L"每次增删 1 个空瓶；有内容或已分配到道具栏的瓶子会保留。"
        : L"可添加或删除，数量受背包库存和容量限制。" : L"选中道具查看增删条件 · 滚轮或上下键浏览", hkDim);
    if (item) hk_draw_text(dc, 20, 538, hkTableW, 24, L"内部代号：" + hk_wide(item->actor), hkDim);
    hk_draw_text(dc, 20, hkAmountY, 52, 31, L"数量");
    if (empty_bottle || bottle_content) {
        hk_draw_text(dc, 115, hkAmountY, 75, 31, L"1", hkInk, DT_CENTER);
    } else {
        hk_button(dc, 72, hkAmountY, 37, L"−");
        hk_edit(dc, 115, hkAmountY, 75, 3, hk.quantity, L"1");
        hk_button(dc, 196, hkAmountY, 37, L"+");
    }
    const bool can_edit = enabled && item && !item->restriction[0];
    hk_button(dc, hkAddX, hkAmountY, hkItemActionW, bottle_content ? L"装瓶" : L"添加所选道具", can_edit);
    hk_button(dc, hkRemoveX, hkAmountY, hkItemActionW, empty_bottle ? L"删除空瓶" : L"删除所选道具", can_edit && !bottle_content);
    hk_draw_text(dc, 545, hkAmountY, 155, 31, L"—  表示暂无数据", hkDim);
    hk_draw_text(dc, 20, 610, hkTableW, 28, hk_wide(hk.state.message), hkMint);
    if (!hk.rows.empty()) hk_draw_text(dc, 710, hkAmountY, 130, 31, L"当前 " + std::to_wstring(hk.offset+1) + L"–" +
        std::to_wstring(std::min(hk.offset+hkLines, (int)hk.rows.size())), hkDim, DT_RIGHT);
    if (hk.dropdown) hk_paint_dropdown(dc, *hk.dropdown);
}

static int hk_value(const std::wstring& text, int max) {
    if (text.empty() || text.size() > 4) return -1;
    int value = 0;
    for (wchar_t ch : text) {
        if (ch < L'0' || ch > L'9') return -1;
        value = value*10 + ch-L'0';
    }
    return value <= max ? value : -1;
}
static bool hk_send(int action, int item = 0, int amount = 0) {
    const auto api = hk_api();
    const auto now = api->status(nullptr);
    return now.ready && !now.pending && hk.state.ready && hk.state.generation == now.generation &&
           api->request(now.generation, action, item, amount);
}
static void hk_set_open(bool open) {
    hk_api()->pad_flight_context(0, 0);
    // A native text field can own the keyboard when grave switches pages.
    // Cancel its draft and retire its host queue before giving our page focus.
    if (editing) edit_end(false);
    if (host && host->take_text) host->take_text(HOS_TEXT_OFF, nullptr, 0);
    hk.dropdown = nullptr;
    hk_focus(0);
    hk_api()->quest_set(open && hk.section == hkMainQuest);
    page = open ? kTrainerPage : 0;
    open_now.store(open);
    if (open) {
        if (!hk.built) {
            const auto api = hk_api();
            for (int i = 0; i < api->count; ++i) {
                std::string name = api->items[i].category;
                if (std::find(hk.categories.begin(), hk.categories.end(), name) == hk.categories.end())
                    hk.categories.push_back(name);
            }
            hk_filter();
            hk.built = true;
        }
        hk.money = std::to_wstring(hk_api()->status(nullptr).rupees);
    }
}

// Runs inside the stock menu tick; uses its mouse/input ownership and the same bitmap slot.
static bool hk_overlay_frame(bool mine, bool stock_key, bool escape, bool up, bool down, bool confirm,
                             bool pgup, bool pgdn, const MkwVkPointer& ptr, bool mouse, int mx, int my) {
    static bool prefs_loaded = false;
    if (!prefs_loaded && hk_api()) {
        hk_apply_prefs(hk_api()->prefs_get());
        prefs_loaded = true;
    }
    const bool active = open_now.load() && page == kTrainerPage;
    const auto api = hk_api();
    if (api) {
        const auto state = api->status(nullptr);
        api->pad_flight_context(state.generation, mine && !stock_key && !open_now.load() &&
            !listening && !startup_on.load() && !hk.field && state.ready && !state.pending &&
            !menu_free_camera() && GetTickCount64() >= hk_flight_arm_due.load());
    }
    const int hotkeys = api ? api->take_hotkey() : 0;
    if (mine && (hotkeys & HK_HOTKEY_PANEL) &&
        (active || (!listening && !startup_on.load() &&
                    (!open_now.load() || (page != 5 && !restart_ask()))))) {
        hk_set_open(!active);
        return true;
    }
    if (mine && (hotkeys & HK_HOTKEY_FLIGHT) && !stock_key && !open_now.load() && !listening && !startup_on.load()) {
        const auto status = api->status(nullptr);
        const bool ready = status.ready && !status.pending && !menu_free_camera() &&
                           GetTickCount64() >= hk_flight_arm_due.load();
        hk_flight_toggle(player_flight, cheats_on(), hk.pref_flags & HK_PREF_FLIGHT, ready);
    }
    if (prefs_loaded) hk_sync_flight();
    if (!active) return false;
    if (!mine) {
        if (hk.field) hk_focus(0);
        hk.dropdown = nullptr;
    }
    const bool typing_ime = hk.field == 1 && hk_api()->composing();
    if (mine && (stock_key || (escape && !hk.field && !hk.dropdown) ||
                 (mouse && (ptr.pressed & HOS_MOUSE_RIGHT)))) {
        hk_set_open(false);
        return true;
    }
    hk.composing = typing_ime;
    if (escape && hk.field && !typing_ime) hk_focus(0);
    const auto latest = hk_api()->status(&hk.magic);
    const bool state_changed = latest.generation != hk.state.generation || latest.ready != hk.state.ready;
    if (state_changed) {
        hk.money = std::to_wstring(latest.rupees);
        hk.selected = -1;
        hk.quantity = L"1";
        hk.destination = 0;
        hk_focus(0);
    }
    hk.state = latest;
    const auto bounds = hk_bounds((float)dev.swap_extent.width, (float)dev.swap_extent.height);
    const float x = bounds.scale > 0 ? (mx-bounds.left)/bounds.scale : -1;
    float y = bounds.scale > 0 ? (my-bounds.top)/bounds.scale : -1;
    auto hit = [&](int left, int top, int width, int height = 31) {
        return x >= left && x < left+width && y >= top && y < top+height;
    };
    const bool click = mouse && (ptr.pressed & HOS_MOUSE_LEFT);
    if (mine && click) {
        if (hit(hkCloseX, 11, hkCloseW)) { hk_set_open(false); return true; }
        for (int i = 0; i < (int)std::size(hkTabNames); ++i) {
            if (!hit(hkTabX+i*hkTabStep, 11, hkTabWidth)) continue;
            hk.dropdown = nullptr;
            hk_focus(0);
            hk.section = static_cast<HkSection>(i);
            hk_api()->quest_set(hk.section == hkMainQuest);
            return true;
        }
    }
    if (hk.section == hkMainQuest) return true;
    const bool items = hk.section == hkItems;
    if (items) y += hkItemShift;
    if (mine && hk.dropdown) {
        const auto& menu = *hk.dropdown;
        const int count = menu.count(), lines = menu.lines();
        const bool in_list = mouse && hit(menu.x, menu.list_y(), menu.list_width(), lines*hkDropdownRowH);
        if (escape || state_changed || (click && !in_list)) hk.dropdown = nullptr;
        else if (click || confirm) {
            const int index = click ? hk.dropdown_offset + (int)(y-menu.list_y())/hkDropdownRowH : hk.dropdown_cursor;
            hk.dropdown = nullptr;
            if (&menu.selected == &hk.forest_destination) {
                hk.map_destination = 0;
                hk_world_destination.store(0);
                hk_save_preference(HK_PREF_NAVIGATION, HK_PREF_NAVIGATION, index);
            } else if (&menu.selected == &hk.map_destination || &menu.selected == &hk.dungeon_destination) {
                menu.selected = index;
                hk_world_destination.store(hk.map_destination);
                hk_dungeon_destination.store(hk.dungeon_destination);
                if (!hk_nav_overlay.load()) hk_save_preference(HK_PREF_NAVIGATION, HK_PREF_NAVIGATION);
            } else if (index != menu.selected) {
                menu.selected = index;
                if (&menu.selected == &hk.category || &menu.selected == &hk.order) hk_filter();
            }
        } else if (up || down || pgup || pgdn) {
            const int delta = pgup ? -lines : pgdn ? lines : up ? -1 : 1;
            hk.dropdown_cursor = std::clamp(hk.dropdown_cursor+delta, 0, count-1);
            hk.dropdown_offset = std::clamp(hk.dropdown_offset,
                                            std::max(0, hk.dropdown_cursor-lines+1), hk.dropdown_cursor);
        } else if (in_list && ptr.wheel) {
            hk.dropdown_offset = std::clamp(hk.dropdown_offset-3*ptr.wheel, 0, count-lines);
            hk.dropdown_cursor = std::clamp(hk.dropdown_cursor, hk.dropdown_offset, hk.dropdown_offset+lines-1);
        }
        return true;
    }
    auto search = [&] { hk.query = hk.draft; hk_focus(0); hk_filter(); };
    if (mine && click) {
        hk.prefs_save_result = 0;
        for (const auto& menu : hkDropdowns) {
            if (menu.section != hk.section || !hit(menu.x, menu.y, menu.width)) continue;
            hk_focus(0);
            hk.dropdown = &menu;
            hk.dropdown_cursor = menu.selected;
            hk.dropdown_offset = std::max(0, menu.selected-menu.lines()+1);
            return true;
        }
        if (!items && hit(hkNavX, hkNavY, hkNavW)) {
            hk_focus(0);
            hk_save_preference(HK_PREF_NAVIGATION, hk.pref_flags ^ HK_PREF_NAVIGATION);
            return true;
        }
        if (!items && hit(hkFlightX, hkFlightY, hkFlightW)) {
            hk_focus(0);
            const bool off = (hk.pref_flags & HK_PREF_FLIGHT) || menu_player_flight() >= 0;
            if (off) player_flight.store(-1);
            hk_save_preference(HK_PREF_FLIGHT, off ? 0 : HK_PREF_FLIGHT);
            hk_sync_flight();
            return true;
        }
        if (!items && hit(hkAmmoKeepX, 119, hkAmmoKeepW)) {
            hk_focus(0);
            hk_save_preference(HK_PREF_AMMO, hk.pref_flags ^ HK_PREF_AMMO);
            return true;
        }
        if (!items && hit(hkSaveX, hkSaveY, hkSaveW)) {
            hk_focus(0);
            hk_save_preference(0, 0);
            return true;
        }
        const auto selected_item = items ? hk_item() : nullptr;
        const bool bottle = selected_item && !selected_item->restriction[0] &&
            (hk_is_empty_bottle(selected_item) || hk_is_bottle_content(selected_item));
        if (items && hit(20, 169, 420)) hk_focus(1);
        else if (!items && hit(373, 80, 80)) hk_focus(2);
        else if (items && !bottle && hit(115, hkAmountY, 75)) hk_focus(3);
        else {
            hk_focus(0);
            if (!items && hit(20, 80, 112)) hk_send(TRAINER_HEAL);
            else if (!items && hit(142, 80, 156)) hk_save_preference(HK_PREF_HEALTH, hk.pref_flags ^ HK_PREF_HEALTH);
            else if (!items && hit(hkMagicRefillX, hkMagicY, hkMagicRefillW)) {
                if (hk.magic.maximum > 0) hk_send(HK_TRAINER_REFILL_MAGIC);
            } else if (!items && hit(hkMagicKeepX, hkMagicY, hkMagicKeepW))
                hk_save_preference(HK_PREF_MAGIC, hk.pref_flags ^ HK_PREF_MAGIC);
            else if (!items && hit(462, 80, 107)) {
                const int amount = hk_value(hk.money, hk.state.wallet);
                if (amount >= 0) hk_send(TRAINER_RUPEES, 0, amount);
            } else if (!items && hit(hkTeleportX, hkTeleportY, hkTeleportW)) {
                if (hk.destination && hk_send(HK_TRAINER_TELEPORT, hk.destination - 1)) {
                    hk_set_open(false);
                    return true;
                }
            } else if (!items && hit(247, 119, 113)) {
                for (int i = 0; i < hk_api()->count; ++i)
                    if (!strcmp(hk_api()->items[i].actor, hkAmmoIds[hk.ammo])) { hk_send(TRAINER_AMMO, i); break; }
            } else if (items && hit(450, 169, 88)) search();
            else if (items && hit(548, 169, 88)) { hk.query.clear(); hk.draft.clear(); hk.category = 0; hk_filter(); }
            else if (items && hit(hkTableX, hkListY, hkTableW, hkLines*hkRowH)) {
                const int r = hk.offset+(y-hkListY)/hkRowH;
                if (r < (int)hk.rows.size()) { hk.selected = r; hk.quantity = L"1"; }
            } else if (items && !bottle && (hit(72, hkAmountY, 37) || hit(196, hkAmountY, 37))) {
                hk.quantity = std::to_wstring(std::clamp(hk_value(hk.quantity, 1000) + (x < 115 ? -1 : 1), 1, 1000));
            } else if (items && (hit(hkAddX, hkAmountY, hkItemActionW) || hit(hkRemoveX, hkAmountY, hkItemActionW))) {
                const int amount = bottle ? 1 : hk_value(hk.quantity, 1000);
                const bool removing = x >= hkRemoveX;
                if (selected_item && !selected_item->restriction[0] && amount > 0 &&
                    (!removing || !hk_is_bottle_content(selected_item))) {
                    const int action = removing ? (int)HK_TRAINER_REMOVE_ITEM : (int)TRAINER_ITEM;
                    hk_send(action, hk.rows[hk.selected], amount);
                }
            }
        }
    }
    if (mine && hk.field) {
        uint16_t chars[256];
        const int n = hk_api()->take_text(chars, std::size(chars));
        auto& edit = hk.field == 1 ? hk.draft : hk.field == 2 ? hk.money : hk.quantity;
        for (int i = 0; i < n; ++i) {
            const uint16_t ch = chars[i];
            if (ch == L'\r') {
                if (hk.field == 1 && !hk.composing) search();
                else if (hk.field != 1) hk_focus(0);   // Enter never applies a numeric modification.
                break;
            }
            if (ch == 1) { hk.replace_text = true; continue; }
            if (ch != 8 && (ch < 32 || (hk.field != 1 && (ch < L'0' || ch > L'9')))) continue;
            if (hk.replace_text) { edit.clear(); hk.replace_text = false; if (ch == 8) continue; }
            if (ch == 8 && !edit.empty()) {
                const wchar_t last = edit.back();
                edit.pop_back();
                if (last >= 0xDC00 && last <= 0xDFFF && !edit.empty() && edit.back() >= 0xD800 && edit.back() <= 0xDBFF)
                    edit.pop_back();
            } else if (ch >= 32 && edit.size() < (hk.field == 1 ? 120 : 4)) edit += (wchar_t)ch;
        }
    } else if (mine && items && !hk.rows.empty() && (up || down || pgup || pgdn)) {
        const int delta = pgup ? -hkLines : pgdn ? hkLines : up ? -1 : 1;
        hk.selected = std::clamp(hk.selected < 0 ? hk.offset : hk.selected + delta, 0, (int)hk.rows.size()-1);
        hk.offset = std::clamp(hk.offset, std::max(0, hk.selected-hkLines+1), hk.selected);
        hk.quantity = L"1";
    }
    if (mine && items && mouse && ptr.wheel && hit(hkTableX, hkListY, hkTableW, hkLines*hkRowH)) {
        hk.offset = std::clamp(hk.offset-3*ptr.wheel, 0, std::max(0, (int)hk.rows.size()-hkLines));
    }
    return true;
}
