#pragma once
#include <stdint.h>

/* Physical SDL/XInput positions, before the user's Switch-button remapping. */
#define HK_PAD_RS (1u << 8)
#define HK_PAD_TRIGGERS ((1u << 15) | (1u << 16))
#define HK_PAD_CHORD (HK_PAD_TRIGGERS | HK_PAD_RS)

typedef struct {
    uint64_t last_ms, began_ms;
    int sampled, armed, capturing, fired;
} HkPadChord;

static void hk_pad_chord_cancel(HkPadChord *s) {
    s->armed = s->fired = 0;
    s->began_ms = 0;
    /* Keep eating a captured press until its components are all released. */
}

/* Only fresh hardware polls call this. A complete chord is held for 500ms. */
static uint32_t hk_pad_chord_sample(HkPadChord *s, uint32_t raw, uint64_t now,
                                    int allowed, int *toggle) {
    *toggle = 0;
    if (!s->sampled || now < s->last_ms || now-s->last_ms > 100) {
        hk_pad_chord_cancel(s);
        s->sampled = 1;
    }
    s->last_ms = now;
    if (!allowed) hk_pad_chord_cancel(s);
    if (!(raw & HK_PAD_CHORD)) {
        s->capturing = 0;
        s->fired = 0;
        s->began_ms = 0;
        s->armed = allowed && !raw;
        return raw;
    }
    if (raw != HK_PAD_CHORD && ((raw & HK_PAD_RS) || s->capturing || (raw & ~HK_PAD_CHORD)))
        hk_pad_chord_cancel(s);
    if (allowed && s->armed && raw == HK_PAD_CHORD) {
        if (!s->capturing) { s->capturing = 1; s->began_ms = now; }
        if (!s->fired && now-s->began_ms >= 500) {
            *toggle = 1;
            s->fired = 1;
            s->armed = 0;
        }
    }
    return s->capturing ? raw & ~HK_PAD_CHORD : raw;
}
