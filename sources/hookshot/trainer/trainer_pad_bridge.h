#pragma once
#include "trainer_pad_chord.h"

/* Included in display.c; window, renderer and input threads share this lock. */
static SRWLOCK hk_pad_lock = SRWLOCK_INIT;
static HkPadChord hk_pad_chord;
static uint64_t hk_pad_generation, hk_pad_context_ms, hk_pad_event_ms;
static int hk_pad_allowed, hk_pad_event;

static void hk_pad_cancel(void) {
    AcquireSRWLockExclusive(&hk_pad_lock);
    hk_pad_allowed = hk_pad_event = 0;
    hk_pad_chord_cancel(&hk_pad_chord);
    ReleaseSRWLockExclusive(&hk_pad_lock);
}

void hk_pad_flight_context(uint64_t generation, int allowed) {
    AcquireSRWLockExclusive(&hk_pad_lock);
    if (hk_pad_generation != generation || hk_pad_allowed != !!allowed) {
        hk_pad_event = 0;
        hk_pad_chord_cancel(&hk_pad_chord);
    }
    hk_pad_generation = generation;
    hk_pad_allowed = !!allowed;
    hk_pad_context_ms = GetTickCount64();
    ReleaseSRWLockExclusive(&hk_pad_lock);
}

/* Called after a NEW native SDL/XInput poll, before pad_bind transforms it. */
uint32_t hk_pad_filter(uint32_t raw, int controllers, int player_ready) {
    const uint64_t now = GetTickCount64();
    AcquireSRWLockExclusive(&hk_pad_lock);
    const int allowed = hk_pad_allowed && now-hk_pad_context_ms <= 150 &&
        controllers == 1 && player_ready && GetForegroundWindow() == hwnd &&
        !InterlockedCompareExchange(&hk_input_wanted, 0, 0) &&
        !InterlockedCompareExchange(&hk_ime_composing, 0, 0);
    int toggle;
    raw = hk_pad_chord_sample(&hk_pad_chord, raw, now, allowed, &toggle);
    if (!allowed) hk_pad_event = 0;
    if (toggle) { hk_pad_event = 1; hk_pad_event_ms = now; }
    ReleaseSRWLockExclusive(&hk_pad_lock);
    return raw;
}

static int hk_take_pad_hotkey(void) {
    const uint64_t now = GetTickCount64();
    AcquireSRWLockExclusive(&hk_pad_lock);
    const int event = hk_pad_event && hk_pad_allowed && now-hk_pad_context_ms <= 150 &&
        now-hk_pad_event_ms <= 150 && GetForegroundWindow() == hwnd &&
        !InterlockedCompareExchange(&hk_input_wanted, 0, 0) &&
        !InterlockedCompareExchange(&hk_ime_composing, 0, 0);
    hk_pad_event = 0;
    ReleaseSRWLockExclusive(&hk_pad_lock);
    return event ? HK_HOTKEY_FLIGHT : 0;
}
