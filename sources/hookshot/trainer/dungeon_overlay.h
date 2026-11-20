#pragma once

static std::wstring hk_dungeon_floor_label(int map, int floor) {
    const int number = floor + hkMapScenes[map].min_floor;
    return number < 0 ? L"地下" + std::to_wstring(-number) + L"层" : std::to_wstring(number+1) + L"层";
}

static bool hk_paint_dungeon_map(HkPaint& dc, const HkNavigation& position, float scale) {
    const auto plan = hk_dungeon_plan(position);
    if (!plan.supported) return false;
    const auto& scene = hkMapScenes[position.map];
    constexpr auto player_color=RGB(118,202,255), goal_color=RGB(247,203,118);
    dc.draw->AddRectFilled(dc.at(0,0),dc.at(346,453),IM_COL32(18,26,34,236),8*scale);
    hk_draw_text(dc,12,5,322,26,scene.label);
    dc.points=14;
    hk_draw_text(dc,12,32,120,23,plan.floor >= 0 ? hk_dungeon_floor_label(position.map,plan.floor) : L"楼层定位中",hkDim);
    const auto progress = L"完成 " + std::to_wstring(plan.completed) + L"/" + std::to_wstring(plan.total) +
        (plan.superseded ? L"　越过 " + std::to_wstring(plan.superseded) : L"");
    hk_draw_text(dc,133,32,200,23,progress,hkDim,DT_RIGHT);
    hk_fill(dc,10,59,326,196,RGB(25,39,49));
    const float left=std::min(scene.left,position.x-2),right=std::max(scene.right,position.x+2);
    const float top=std::min(scene.top,position.z-2),bottom=std::max(scene.bottom,position.z+2);
    const float unit=std::min(301/(right-left),171/(bottom-top));
    const auto map=[&](float x,float z) { return dc.at(173+(x-(left+right)*.5f)*unit,157+(z-(top+bottom)*.5f)*unit); };
    const auto dot=[&](const HkDungeonNode& node) { return map(node.x,node.z); };
    for (const auto& edge : hkDungeonEdges) {
        const auto& a=hkDungeonNodes[edge.from];
        const auto& b=hkDungeonNodes[edge.to];
        if (a.scene != position.map || a.floor != plan.floor || b.floor != plan.floor) continue;
        dc.draw->AddLine(dot(a),dot(b),hk_color(RGB(65,86,102)),1.4f*scale);
    }
    for (const auto& anchor : hkDungeonAnchors)
        if (anchor.scene == position.map && anchor.floor == plan.floor)
            dc.draw->AddCircleFilled(map(anchor.x,anchor.z),2.2f*scale,hk_color(RGB(194,161,244)));
    const HkDungeonStep* step=plan.step >= 0 ? &hkDungeonSteps[plan.step] : nullptr;
    const auto* approach=plan.approach >= 0 ? &hkDungeonNodes[plan.approach] : nullptr;
    // Only the next verified portal is highlighted. Graph chords are schematic,
    // never a claim that a straight line through a room has no collision.
    if (plan.route && plan.next >= 0) {
        const auto& target=hkDungeonNodes[plan.next];
        if (target.floor == plan.floor) {
            if (!plan.room_obstacles) {
                hk_map_arrow(dc,map(position.x,position.z),dot(target),scale);
                dc.draw->AddCircleFilled(dot(target),5.2f*scale,hk_color(goal_color));
            } else dc.draw->AddCircle(dot(target),5.2f*scale,hk_color(goal_color),0,2*scale);
        }
    } else if (step && (approach ? approach->floor : step->floor) == plan.floor) {
        dc.draw->AddCircle(map(approach ? approach->x : step->x,approach ? approach->z : step->z),5.2f*scale,hk_color(goal_color),0,2*scale);
        // A hollow target has no asserted path; do not draw a through-wall arrow.
    }
    dc.draw->AddCircleFilled(map(position.x,position.z),4.4f*scale,hk_color(player_color));
    hk_draw_text(dc,18,63,200,18,L"本层路线示意",hkDim);
    hk_draw_text(dc,16,231,314,18,L"蓝点：你    金点：下一处    紫点：机关",hkDim);
    if (!plan.fresh) {
        hk_draw_text(dc,12,264,322,24,L"正在读取迷宫进度",hkMint);
        hk_draw_paragraph(dc,12,296,322,70,L"进入可操作场景后自动更新。换地图或读档时会清除上一处的指引。",hkDim);
    } else if (plan.finished || (plan.total && plan.completed + plan.superseded == plan.total)) {
        hk_draw_text(dc,12,264,322,24,plan.finished ? L"本迷宫主要目标已完成" : L"当前年龄的阶段已完成",hkMint);
        hk_draw_paragraph(dc,12,296,322,90,
            !plan.finished && position.map==kMapSpiritTemple && position.child==1 ?
            L"离开魂之神殿，回时之神殿变成年，再回来继续右侧路线。后续目标也可在「主线」页查看。" :
            L"可在「主线」页查看后续目标，或继续探索遗漏宝箱；要离开时，在迷宫下拉菜单选择「出口」。",hkDim);
    } else if (!step) {
        hk_draw_text(dc,12,264,322,24,L"当前阶段的前置条件尚未满足",hkMint);
        hk_draw_paragraph(dc,12,296,322,100,L"检查年龄、装备和主线进度。可在「主线」页查看下一步准备；进入适用阶段后自动继续。",hkDim);
    } else {
        hk_draw_text(dc,12,264,322,25,step->title,hkMint);
        std::wstring action=step->action, detail=step->detail;
        if (plan.edge >= 0 && !plan.reached) {
            const auto& edge=hkDungeonEdges[plan.edge];
            const auto& a=hkDungeonNodes[edge.from];
            const auto& b=hkDungeonNodes[edge.to];
            action=edge.action;
            const int gate_state=hk_dungeon_gate_state(position,plan.edge);
            if (gate_state==HK_DUNGEON_MET && edge.kind==kDgDoor)
                action=L"门已打开，从金色标记处通过";
            if (gate_state==HK_DUNGEON_MET && edge.kind==kDgDrop)
                action=L"从已打开的落口向下落到目标层";
            if (edge.condition==kDgSmallKey && plan.gate && hk_dungeon_inventory(position,0)==0)
                action=gate_state==HK_DUNGEON_UNMET ? L"这扇门尚未打开；先取得一把小钥匙" :
                    L"门状态未确认；若仍锁住，需要小钥匙";
            if (edge.condition==kDgBossKey && plan.gate && hk_dungeon_inventory(position,1)==0)
                action=gate_state==HK_DUNGEON_UNMET ? L"这扇门尚未打开；先取得首领钥匙" :
                    L"门状态未确认；若仍锁住，需要首领钥匙";
            if (a.floor != b.floor) action += L" → " + hk_dungeon_floor_label(position.map,b.floor);
            detail=L"到达后：" + std::wstring(step->action);
            if (plan.gate) detail += L"。通道是否打开仍按现场机关状态确认。";
        } else if (!plan.route && !plan.reached) {
            action=L"目标在" + hk_dungeon_floor_label(position.map,approach ? approach->floor : step->floor) + L"：" + step->action;
            if (*step->transition) detail=std::wstring(step->transition)+L"。"+detail;
        }
        hk_draw_paragraph(dc,12,296,322,55,action,goal_color);
        hk_draw_paragraph(dc,12,353,322,70,detail,hkInk);
        const wchar_t* state=plan.blocked ? L"先准备所需装备或机关条件；保留本步" :
            plan.uncertain_position ? L"通道定位暂未确认；仅标出目标位置" :
            plan.completion == HK_DUNGEON_UNKNOWN ? L"完成状态暂未确认；不会自动跳过" :
            plan.reached ? L"已到目标附近；完成操作后自动推进" :
            plan.room_obstacles ? L"房内有隔断或机关；金圈标记入口" :
            plan.route ? L"按当前位置更新；完成后自动推进" : L"仅标出目标；此段通路尚未完整确认";
        hk_draw_text(dc,12,428,322,18,state,hkDim);
    }
    return true;
}
