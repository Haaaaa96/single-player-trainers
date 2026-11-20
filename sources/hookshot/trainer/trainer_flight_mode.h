#pragma once
#include <atomic>

// Stock values are disabled (-1), armed (0), and flying (1).
// 2 and 3 represent a trainer-owned arm/fly session in the same atomic.
static int hk_flight_effective(int state, bool debug) {
    return state >= 2 ? state-2 : debug ? state : -1;
}

static void hk_flight_shortcut(std::atomic<int>& state, bool debug, bool flying) {
    int before = state.load(std::memory_order_relaxed);
    const int mode = hk_flight_effective(before, debug);
    if (mode < 0 || mode == (int)flying) return;
    const int after = before - mode + (int)flying;
    state.compare_exchange_strong(before, after, std::memory_order_relaxed);
}

static void hk_flight_toggle(std::atomic<int>& state, bool debug, bool keep_armed, bool ready) {
    int before = state.load(std::memory_order_relaxed);
    if (hk_flight_effective(before, debug) > 0) {
        const int after = keep_armed ? 2 : debug && before == 1 ? 0 : -1;
        state.compare_exchange_strong(before, after, std::memory_order_relaxed);
    } else if (ready) {
        state.compare_exchange_strong(before, 3, std::memory_order_relaxed);
    }
}

static bool hk_flight_cancel(std::atomic<int>& state) {
    int before = state.load(std::memory_order_relaxed);
    while (before >= 2)
        if (state.compare_exchange_weak(before, -1, std::memory_order_relaxed)) return true;
    return false;
}
