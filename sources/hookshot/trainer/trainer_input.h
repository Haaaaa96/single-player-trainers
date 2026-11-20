#include <imm.h>
#include "trainer_api.h"

static SRWLOCK hk_input_lock = SRWLOCK_INIT;
static uint16_t hk_input[256];
static int hk_input_count;
static volatile LONG hk_input_wanted, hk_ime_composing;
static volatile LONG hk_hotkey_pressed;
static int hk_input_mode;

#include "trainer_pad_bridge.h"

int hk_take_hotkey(void) { return InterlockedExchange(&hk_hotkey_pressed, 0) | hk_take_pad_hotkey(); }

static int hk_window_hotkey(HWND w, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_KILLFOCUS || msg == WM_CANCELMODE || (msg == WM_ACTIVATEAPP && !wp)) {
        hk_pad_cancel();
        hk_take_hotkey();
    }
    if (msg != WM_KEYDOWN || (wp != VK_OEM_3 && wp != VK_F6) || GetForegroundWindow() != w ||
        InterlockedCompareExchange(&hk_input_wanted, 0, 0) ||
        ((GetKeyState(VK_SHIFT) | GetKeyState(VK_CONTROL) | GetKeyState(VK_MENU)) & 0x8000))
        return 0;
    if (!(lp & (1L << 30))) InterlockedOr(&hk_hotkey_pressed, wp == VK_OEM_3 ? HK_HOTKEY_PANEL : HK_HOTKEY_FLIGHT);
    return 1;
}

void hk_text_focus(int mode) {
    AcquireSRWLockExclusive(&hk_input_lock);
    InterlockedExchange(&hk_input_wanted, mode);
    hk_input_count = 0;
    ReleaseSRWLockExclusive(&hk_input_lock);
    if (hwnd) PostMessageW(hwnd, HK_TRAINER_TEXT_MESSAGE, 0, 0);
}

int hk_take_text(uint16_t *out, int capacity) {
    AcquireSRWLockExclusive(&hk_input_lock);
    int n = capacity < hk_input_count ? capacity : hk_input_count;
    memcpy(out, hk_input, n * sizeof *out);
    hk_input_count -= n;
    memmove(hk_input, hk_input+n, hk_input_count * sizeof *out);
    ReleaseSRWLockExclusive(&hk_input_lock);
    return n;
}

int hk_composing(void) { return InterlockedCompareExchange(&hk_ime_composing, 0, 0) != 0; }

static void hk_push_text(const WCHAR *text, int count) {
    AcquireSRWLockExclusive(&hk_input_lock);
    if (hk_input_mode && hk_input_mode == hk_input_wanted) {
        for (int i = 0; i < count && hk_input_count < ARRAYSIZE(hk_input); ++i)
            hk_input[hk_input_count++] = text[i];
    }
    ReleaseSRWLockExclusive(&hk_input_lock);
}

static void hk_change_text_mode(HWND w, int mode) {
    if (mode == hk_input_mode) return;
    const int old = hk_input_mode;
    hk_input_mode = 0;   /* discard any commit fired while releasing our context */
    if (old == 1) {
        HIMC ctx = ImmGetContext(w);
        if (ctx) { ImmNotifyIME(ctx, NI_COMPOSITIONSTR, CPS_CANCEL, 0); ImmReleaseContext(w, ctx); }
        ImmAssociateContextEx(w, NULL, 0);
    }
    InterlockedExchange(&hk_ime_composing, 0);
    hk_input_mode = mode;
    if (mode == 1) {
        ImmAssociateContextEx(w, NULL, IACE_DEFAULT);
        HIMC ctx = ImmGetContext(w);
        if (ctx) {
            RECT client;
            GetClientRect(w, &client);
            COMPOSITIONFORM form = {CFS_POINT, {client.right / 4, client.bottom / 3}, {0}};
            ImmSetCompositionWindow(ctx, &form);
            ImmReleaseContext(w, ctx);
        }
    }
}

static void hk_paste(HWND w) {
    if (!OpenClipboard(w)) return;
    HGLOBAL data = GetClipboardData(CF_UNICODETEXT);
    const WCHAR *str = data ? (const WCHAR *)GlobalLock(data) : NULL;
    if (str) {
        size_t size = GlobalSize(data) / sizeof *str;
        int n = 0;
        while (n < 128 && n < size && str[n] && str[n] >= 32) ++n;
        hk_push_text(str, n);
        GlobalUnlock(data);
    }
    CloseClipboard();
}

static int hk_window_text(HWND w, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == HK_TRAINER_TEXT_MESSAGE) {
        hk_change_text_mode(w, GetForegroundWindow() == w ? hk_input_wanted : 0);
        return 1;
    }
    if (msg == WM_SETFOCUS && hk_input_wanted) hk_change_text_mode(w, hk_input_wanted);
    if (msg == WM_KILLFOCUS || msg == WM_CANCELMODE) {
        hk_change_text_mode(w, 0);
        AcquireSRWLockExclusive(&hk_input_lock);
        hk_input_count = 0;
        ReleaseSRWLockExclusive(&hk_input_lock);
    }
    if (!hk_input_mode || hk_input_mode != hk_input_wanted || GetForegroundWindow() != w) return 0;
    if (msg == WM_IME_STARTCOMPOSITION) InterlockedExchange(&hk_ime_composing, 1);
    if (msg == WM_IME_ENDCOMPOSITION) InterlockedExchange(&hk_ime_composing, 0);
    if (msg == WM_IME_COMPOSITION && (lp & GCS_RESULTSTR)) {
        HIMC ctx = ImmGetContext(w);
        if (ctx) {
            WCHAR result[128];
            LONG len = ImmGetCompositionStringW(ctx, GCS_RESULTSTR, result, sizeof result);
            if (len > 0 && len <= sizeof result) hk_push_text(result, len / sizeof *result);
            ImmReleaseContext(w, ctx);
        }
        return 1;
    }
    if (msg == WM_CHAR) {
        if (wp == 22) { hk_paste(w); return 1; }
        if (!hk_composing() && (wp >= 32 || wp == 1 || wp == '\b' || wp == '\r')) {
            WCHAR ch = (WCHAR)wp;
            hk_push_text(&ch, 1);
        }
        return 1;
    }
    return 0;
}
