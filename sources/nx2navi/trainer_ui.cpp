#include "imgui.h"
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

extern "C" {
#include "trainer.h"
}

static std::string folded(const char *s) {
    std::string out(s);
    for (char &c : out) c = (char)std::tolower((unsigned char)c);
    return out;
}

extern "C" void trainer_ui(void) {
    TrainerStatus s = trainer_status();
    static uint64_t generation;
    static int rupees, amount = 1, item = -1, category, order, ammo;
    static bool open_inventory;
    static char search[128] = {}, applied[128] = {};
    if (s.generation != generation) {
        generation = s.generation;
        rupees = s.rupees;
    }
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(ImGui::GetStyle().ItemSpacing.x, 4));
    ImGui::SeparatorText("NX2naviTrainer 0.1.1");
    if (s.ready) ImGui::Text("生命 %.2f / %.2f 心　卢比 %d / %d",
                           s.health/4.0, s.max_health/4.0, s.rupees, s.wallet);
    else ImGui::TextUnformatted("请先读取存档，等待林克进入游戏。");
    ImGui::BeginDisabled(!s.ready || s.pending);
    if (ImGui::Button("回满生命")) trainer_request(generation, TRAINER_HEAL, 0, 0);
    ImGui::SameLine();
    bool keep = !!s.keep_health;
    if (ImGui::Checkbox("保持满血", &keep)) trainer_request(generation, TRAINER_KEEP, 0, keep);
    ImGui::SetNextItemWidth(135);
    ImGui::InputInt("##rupees", &rupees, 0);
    ImGui::SameLine();
    ImGui::BeginDisabled(rupees < 0 || rupees > s.wallet);
    if (ImGui::Button("设置卢比")) trainer_request(generation, TRAINER_RUPEES, 0, rupees);
    ImGui::EndDisabled();
    static const char *ammo_names[] = {"德库木棒", "德库坚果", "德库种子", "炸弹", "炸弹鼠", "箭矢"};
    static const char *ammo_ids[] = {"Item_DekuStick","Item_DekuNut","Item_DekuSeed","Item_Bomb","Item_Bombchu","Item_Arrow_Normal"};
    ImGui::SetNextItemWidth(180);
    ImGui::Combo("##ammo", &ammo, ammo_names, IM_ARRAYSIZE(ammo_names));
    ImGui::SameLine();
    if (ImGui::Button("补满弹药")) {
        for (int i = 0; i < trainer_item_count; ++i)
            if (!strcmp(trainer_items[i].actor, ammo_ids[ammo])) {
                trainer_request(generation, TRAINER_AMMO, i, 0);
                break;
            }
    }
    ImGui::EndDisabled();
    if (s.message[0]) ImGui::TextWrapped("%s", s.message);
    if (ImGui::CollapsingHeader("添加道具", ImGuiTreeNodeFlags_DefaultOpen)) {
        if (!open_inventory) {
            search[0] = applied[0] = '\0';
            category = order = 0;
            item = -1;
        }
        open_inventory = true;
        static const std::vector<const char *> categories = [] {
            std::vector<const char *> result{"全部"};
            for (int i=0; i<trainer_item_count; ++i) {
                const char *cat = trainer_items[i].category;
                if (std::none_of(result.begin(), result.end(), [cat](const char *v) {return !strcmp(cat,v);}))
                    result.push_back(cat);
            }
            return result;
        }();
        ImGui::SetNextItemWidth(200);
        bool submit = ImGui::InputTextWithHint("##item-search", "输入道具名", search, sizeof search, ImGuiInputTextFlags_EnterReturnsTrue);
        ImGui::SameLine();
        submit |= ImGui::Button("搜索");
        if (submit) snprintf(applied, sizeof applied, "%s", search);
        ImGui::SameLine();
        if (ImGui::Button("清除")) { search[0] = applied[0] = '\0'; category = 0; }
        ImGui::SetNextItemWidth(130);
        ImGui::Combo("##category", &category, categories.data(), (int)categories.size());
        ImGui::SameLine();
        ImGui::SetNextItemWidth(170);
        ImGui::Combo("##order", &order, "默认\0售价升序\0售价降序\0占格升序\0占格降序\0");
        std::vector<int> visible;
        std::string keyword = folded(applied);
        for (int i=0; i<trainer_item_count; ++i) {
            const TrainerItem &entry = trainer_items[i];
            if (category && strcmp(entry.category,categories[category])) continue;
            if (!keyword.empty() && folded(entry.name).find(keyword) == std::string::npos &&
                folded(entry.actor).find(keyword) == std::string::npos) continue;
            visible.push_back(i);
        }
        if (order) std::stable_sort(visible.begin(), visible.end(), [](int a, int b) {
            const TrainerItem &x = trainer_items[a], &y = trainer_items[b];
            int l = order < 3 ? x.price : x.cells, r = order < 3 ? y.price : y.cells;
            if (l < 0 || r < 0) return l >= 0 && r < 0;
            return order % 2 ? l < r : l > r;
        });
        if (item >= 0 && std::find(visible.begin(), visible.end(), item) == visible.end()) item = -1;
        ImGui::Text("显示 %d / %d 条", (int)visible.size(), trainer_item_count);
        if (item >= 0) {
            const TrainerItem &e = trainer_items[item];
            ImGui::TextWrapped("%s", e.name);
            if (e.restriction[0]) ImGui::TextWrapped("%s",e.restriction);
            ImGui::BeginDisabled(!s.ready || s.pending || e.restriction[0]);
            ImGui::SetNextItemWidth(120);
            ImGui::InputInt("##quantity",&amount,0);
            ImGui::SameLine();
            ImGui::BeginDisabled(amount < 1 || amount > 1000 || (e.maximum && !e.capacity && amount > e.maximum));
            if (ImGui::Button("添加所选道具")) trainer_request(generation,TRAINER_ITEM,item,amount);
            ImGui::EndDisabled();
            ImGui::EndDisabled();
        }
        if (ImGui::BeginChild("##item-list", ImVec2(0, 190), ImGuiChildFlags_Borders)) {
            ImGuiListClipper clip;
            clip.Begin((int)visible.size());
            while (clip.Step()) for (int pos = clip.DisplayStart; pos < clip.DisplayEnd; ++pos) {
                int i = visible[pos];
                const TrainerItem &e = trainer_items[i];
                char label[512], price[32], cells[32];
                if (e.price >= 0) snprintf(price,sizeof price,"%d",e.price); else strcpy(price,"未知");
                if (e.cells >= 0) snprintf(cells,sizeof cells,"%d",e.cells); else strcpy(cells,"未知");
                snprintf(label,sizeof label,"%s  |  %s  |  售价 %s  |  占格 %s##%d",
                         e.name,e.category,price,cells,i);
                if (ImGui::Selectable(label, item == i)) { item = i; amount = 1; }
            }
        }
        ImGui::EndChild();
    } else {
        open_inventory = false;
    }
    ImGui::PopStyleVar();
}
