/* Uses the same destination table and player callback as Hookshot's Debug menu. */
static struct {
    const char *banc;
    uint64_t deadline, next_check;
    int same_map;
} hk_teleport;

static void hk_teleport_start(Ctx *c, uint64_t actor, int index, uint64_t now,
                              char *result, size_t size) {
    if ((unsigned)index >= sizeof oot_destinations / sizeof oot_destinations[0]) {
        snprintf(result, size, "请选择有效的传送地点。");
        return;
    }
    const uint64_t sp = c->x[31], stack_needed = OOT_EVENT_ARG_SIZE + 0x100;
    if (sp < stack_needed + 16 || !access_guest((sp-stack_needed) & ~15ull, stack_needed, 3)) {
        snprintf(result, size, "当前角色无法安全发起传送。");
        return;
    }
    int child;
    if (!oot_gamedata_bool(c, 0xcea220d3u, &child)) {   /* Sequence_IsChildhood */
        snprintf(result, size, "无法确认林克年龄，请稍后再试。");
        return;
    }
    const OotDestination *destination = &oot_destinations[index];
    const char *banc = child ? destination->child_banc : destination->adult_banc;
    if (!banc) {
        snprintf(result, size, "当前年龄无法传送到此处。");
        return;
    }
    char current[80];
    if (!oot_gamedata_string(c, 0x1d6189dau, current, sizeof current) || !current[0]) {
        snprintf(result, size, "无法确认当前地图，请稍后再试。");
        return;
    }
    if (!oot_teleport(c, actor, (unsigned)index)) {
        snprintf(result, size, "游戏暂未接受传送，请等待剧情或加载结束。");
        return;
    }
    hk_teleport.banc = banc;
    hk_teleport.same_map = !strcmp(current, banc);
    hk_teleport.deadline = now + 8000;
    hk_teleport.next_check = now + 250;
}

static int hk_teleport_poll(Ctx *c, uint64_t now, int ready, char *result, size_t size) {
    if (!hk_teleport.deadline || now < hk_teleport.next_check) return 0;
    hk_teleport.next_check = now + 250;
    if (ready && !hk_teleport.same_map) {
        char current[80];
        if (oot_gamedata_string(c, 0x1d6189dau, current, sizeof current) &&
            !strcmp(current, hk_teleport.banc)) {
            snprintf(result, size, "已进入目标地图。");
            hk_teleport.deadline = 0;
            return 1;
        }
    }
    if (now < hk_teleport.deadline) return 0;
    snprintf(result, size, "%s", hk_teleport.same_map ?
             "已发出同地图传送，请在游戏中确认落点。" :
             "传送结果未确认，请查看当前地图。");
    hk_teleport.deadline = 0;
    return 1;
}
