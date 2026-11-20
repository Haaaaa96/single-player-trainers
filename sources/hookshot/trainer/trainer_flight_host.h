#pragma once

static void hk_flight_tick(Ctx *c) {
    int rx_option(int id, int otherwise);
    void rx_option_set(int id, int value);
    // This tick runs under the stock player callback lock.
    static uint64_t generation, last_poll;
    static char last_scene[64];
    if (rx_option(HOS_OPT_CHEAT_FLIGHT, -1) < 0) {
        generation = last_poll = 0;
        last_scene[0] = 0;
        return;
    }
    const TrainerStatus status = trainer_status();
    int valid = status.ready && (!generation || status.generation == generation);
    const uint64_t now = GetTickCount64();
    if (valid && (!last_poll || now-last_poll >= 125)) {
        const uint64_t sp = c->x[31];
        char scene[64];
        int loading = 1;
        valid = sp >= 0x1000 && access_guest((sp-0x1000) & ~15ull, 0x1000, 3) &&
            oot_gamedata_bool(c, 0xef2b60c2u, &loading) && !loading &&
            oot_gamedata_string(c, 0x1d6189dau, scene, sizeof scene) && scene[0] &&
            (!last_scene[0] || !strcmp(scene, last_scene));
        if (valid) {
            snprintf(last_scene, sizeof last_scene, "%s", scene);
            last_poll = now;
        }
    }
    if (valid) {
        generation = status.generation;
    } else {
        rx_option_set(HK_OPT_CANCEL_TRAINER_FLIGHT, 0);
        generation = last_poll = 0;
        last_scene[0] = 0;
    }
}
