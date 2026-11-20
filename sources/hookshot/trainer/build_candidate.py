"""Build a local Windows Hookshot trainer from a retained v2.3.1 build.

The official build must use HOOKSHOT_KEEP_BUILD_FILES=1 so its generated code,
object response files and unmodified binaries remain available here.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys


SOURCE = Path(__file__).resolve().parent
PREVIOUS = SOURCE.parent / "core"
UPSTREAM = "v2.3.1"
TRAINER_VERSION = "0.2.25-dev"
TOOLS: Path
WORK: Path
MAIN_SHA256 = "2591fb99008d0814f8056c3f36b36790048ed857ff0ae2bb3a4c1e37b960a4de"
REFERENCE_SHA256 = "42d7777267e7959b958c8e6f8d1c247794bf0931ba2c3614628bbdc678e0de37"
TELEPORT_NAMES = {
    "Kokiri Forest": "科奇里森林",
    "Hyrule Field": "海拉鲁平原",
    "Kakariko Village": "卡卡利科村",
    "Market": "城下町",
    "Hyrule Castle": "海拉鲁城堡",
    "Lost Woods": "迷失森林",
    "Sacred Forest Meadow": "圣林草地",
    "Lake Hylia": "海利亚湖",
    "Graveyard": "墓地",
    "Death Mountain Trail": "死亡之山山道",
    "Death Mountain Crater": "死亡之山火山口",
    "Goron City": "鼓隆城",
    "Zora's River": "卓拉河",
    "Zora's Domain": "卓拉领地",
    "Zora's Fountain": "卓拉泉",
    "Gerudo Valley": "格鲁德峡谷",
    "Gerudo Fortress": "格鲁德要塞",
    "Haunted Wasteland": "幻影沙漠",
    "Desert Colossus": "沙漠巨像",
    "Inside the Deku Tree": "德库树内部",
    "Dodongo's Cavern": "多东哥洞窟",
    "Jabu-Jabu's Belly": "加卜加卜腹中",
    "Forest Temple": "森林神殿",
    "Fire Temple": "火之神殿",
    "Water Temple": "水之神殿",
    "Shadow Temple": "暗影神殿",
    "Spirit Temple": "魂之神殿",
    "Bottom of the Well": "井底",
    "Ice Cavern": "冰之洞窟",
    "Gerudo Training Ground": "格鲁德训练场",
    "Ganon's Castle": "盖侬城堡内部",
}


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def optional_link_inputs(original):
    """Keep the optional libraries used by the retained official Windows build.

    The objects, rather than a newly changed environment, decide which libraries
    are required. Never silently discard an enabled decoder or DLSS build.
    """
    def object_names(filename):
        return {Path(row.strip('"')).name
                for row in (original / filename).read_text(encoding="utf-8").splitlines()}

    host_flags, renderer_flags, libraries = [], [], []
    if "host_dav1d_av1.o" in object_names("objs.rsp"):
        package = None
        roots = [Path(os.environ["RX_CPM"])] if os.environ.get("RX_CPM") else []
        roots.append(TOOLS / "cpm")
        for root in roots:
            folder = root / "dav1d"
            versions = sorted(folder.iterdir()) if folder.is_dir() else []
            if versions:
                package = versions[-1]  # nx2/build.py cpm_package uses the same order.
                break
        if package is None or not (package / "include/dav1d/dav1d.h").is_file() or not (package / "lib/libdav1d.a").is_file():
            raise ValueError("The retained build uses dav1d; its matching CPM headers and lib/libdav1d.a are required")
        library = package / "lib/libdav1d.a"
        host_flags.append(str(library))
        libraries.append(library)

    if "vk_ngx_msvc_rt.o" in object_names("vk_objs.rsp"):
        sdk = Path(os.environ.get("HOOKSHOT_NGX_SDK") or TOOLS / "ngx-sdk")
        library = sdk / "lib/nvsdk_ngx_s.lib"
        if not library.is_file():
            raise ValueError("The retained build uses DLSS; set HOOKSHOT_NGX_SDK to its matching SDK with lib/nvsdk_ngx_s.lib")
        renderer_flags.extend((str(library), "-ladvapi32", "-Wl,-Xlink=/nodefaultlib:libcpmt"))
        libraries.append(library)
    return host_flags, renderer_flags, libraries


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected exactly one anchor: {old[:80]}")
    return text.replace(old, new, 1)


def write_teleport_labels(host, renderer, output):
    host_table = host.split("static const OotDestination oot_destinations[] = {", 1)[1].split("\n};", 1)[0]
    menu_table = renderer.split("constexpr const char* teleport_names[] = {", 1)[1].split("};", 1)[0]
    host_names = re.findall(r"}\s*,\s*/\* ([^\n]+?) \*/", host_table)
    menu_names = re.findall(r'"([^"]+)"', menu_table)
    if host_names != menu_names or len(menu_names) != len(TELEPORT_NAMES) or set(menu_names) != TELEPORT_NAMES.keys():
        raise ValueError("The host, original menu, and Chinese teleport catalog must match")
    notes = renderer.split("constexpr const char* teleport_notes[] = {", 1)[1].split("};", 1)[0]
    notes = [value.strip() for value in notes.split(",")]
    adult_index = menu_names.index("Gerudo Fortress")
    if len(notes) != len(menu_names) or notes[adult_index] != '"adult only"' or notes.count("nullptr") != len(menu_names)-1:
        raise ValueError("The original teleport restrictions have changed")
    labels = ['L"选择传送地点"'] + [f'L"{TELEPORT_NAMES[name]}"' for name in menu_names]
    details = ["nullptr"] * len(labels)
    details[adult_index+1] = 'L"仅成人"'
    output.write_text(
        "static const wchar_t *const hkDestinations[] = {\n    " + ",\n    ".join(labels) + "\n};\n"
        "static const wchar_t *const hkDestinationNotes[] = {\n    " + ", ".join(details) + "\n};\n",
        encoding="utf-8",
    )


def core_for_hookshot():
    code = (PREVIOUS / "trainer.c").read_text(encoding="utf-8")
    code = code[code.index("#define GDM_SLOT"):]
    code, address_count = re.subn(
        r"0x700([0-9a-f]{7})ull",
        lambda match: hex(0x80020000 + int(match[1], 16)) + "ull",
        code,
    )
    if address_count != 12:
        raise ValueError("Previous trainer guest address set changed")
    for name in ("POUCH_EDIT", "POUCH_COUNT"):
        code = re.sub(rf"^#define {name} .*\n", "", code, flags=re.MULTILINE)
    start = code.index("static int access_guest(")
    end = code.index("static uint64_t pointer_at(", start)
    code = code[:start] + code[end:]
    start = code.index("static uint64_t player(")
    end = code.index("TrainerStatus trainer_status(", start)
    code = code[:start] + code[end:]
    start = code.index("static int pouch_count(")
    end = code.index("static int pouch_add(", start)
    code = code[:start] + """static int pouch_count(Ctx *c, uint64_t sp, const char *name) {
    if (sp < 0x3000 || !access_guest((sp - 0x80) & ~15ull, 0x80, 3)) return -1;
    return oot_pouch_count(c, name);
}

""" + code[end:]
    code = replace_once(code, "    mem_thaw(address, 4);\n"
                       "    return __atomic_compare_exchange_n((int32_t *)(uintptr_t)address, &before, after,\n"
                       "                                        0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);",
                       "    int32_t *dest = GP(address);\n"
                       "    if (!__atomic_compare_exchange_n(dest, &before, after, 0,\n"
                       "                                     __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) return 0;\n"
                       "    HOS_WRITTEN(dest, sizeof *dest);\n"
                       "    return 1;")
    code = replace_once(code, "static struct { uint64_t deadline; int item, before, amount, capacity; } awaiting;\n", "")
    start = code.index("static int pouch_add(")
    end = code.index("void trainer_tick(", start)
    code = code[:start] + '#include "trainer_pouch.h"\n#include "trainer_ammo.h"\n#include "trainer_magic.h"\n\n' + code[end:]
    code = code.replace("set_rupees(", "set_saved_integer(")
    code = replace_once(code, "void trainer_tick(Cpu *c, uint64_t actor, uint64_t sp) {",
                       "static void trainer_tick(Ctx *c, uint64_t link, uint64_t actor) {\n"
                       "    const uint64_t sp = c->x[31];")
    code = replace_once(code, "    uint64_t link = player(actor);\n    if (!link) goto done;\n", "")
    code = replace_once(code, "static int keep;\n", "")
    code = replace_once(code, "        keep = 0;\n", "")
    code = replace_once(code, "copy.ready = copy.keep_health = 0;", "copy.ready = 0;")
    code = replace_once(code, "static TrainerStatus status;",
                       "static TrainerStatus status;\nstatic HkMagicStatus magic_status = {-1, -1};")
    code = replace_once(code, "TrainerStatus trainer_status(void) {",
                       "static TrainerStatus hk_trainer_status(HkMagicStatus *magic) {")
    code = replace_once(code, "    ReleaseSRWLockShared(&state_lock);\n    return copy;\n}",
                       "    if (magic) *magic = copy.ready ? magic_status : (HkMagicStatus){-1, -1};\n"
                       "    ReleaseSRWLockShared(&state_lock);\n    return copy;\n}\n\n"
                       "TrainerStatus trainer_status(void) {\n    return hk_trainer_status(NULL);\n}")
    code = replace_once(code, "        if (action == TRAINER_KEEP) {\n"
                       "            keep = !!amount;\n"
                       "            snprintf(result, sizeof result, \"%s\", keep ? \"已开启持续回血。\" : \"已关闭持续回血。\");\n"
                       "        }\n", "")
    code = replace_once(code, "    status.keep_health = keep;\n", "")
    code = replace_once(code, "        status.generation++;\n",
                       "        status.generation++;\n        magic_status = (HkMagicStatus){-1, -1};\n")
    code = code.replace("Cpu *c", "Ctx *c").replace("rt_log(", "hos_log(")
    code = code.replace("(const void *)(uintptr_t)SCRIPT_NAME", "GP(SCRIPT_NAME)")
    code = replace_once(code, "    AcquireSRWLockExclusive(&state_lock);\n    int changed = actor_seen",
                       "    AcquireSRWLockExclusive(&state_lock);\n"
                       "    now = GetTickCount64();\n"
                       "    int changed = actor_seen")
    code = replace_once(code, "        request.action = 0;\n        status.pending = 0;",
                       "        hos_log(\"trainer: request=%d refused before dispatch (age %llu ms, generation %llu/%llu, ready %d)\",\n"
                       "                request.action, (unsigned long long)(now - request.at),\n"
                       "                (unsigned long long)request.generation, (unsigned long long)status.generation, ready);\n"
                       "        request.action = 0;\n        status.pending = 0;")
    code = replace_once(code, "void trainer_request(uint64_t generation, int action, int item, int amount) {",
                       "static int hk_trainer_request(uint64_t generation, int action, int item, int amount) {\n"
                       "    int accepted = 0;")
    code = replace_once(code, "        request = (typeof(request)){now, generation, action, item, amount};",
                       "        request = (typeof(request)){now, generation, action, item, amount};\n"
                       "        accepted = 1;")
    code = replace_once(code, "    ReleaseSRWLockExclusive(&state_lock);\n}\n\nstatic int pouch_ready(",
                       "    ReleaseSRWLockExclusive(&state_lock);\n    return accepted;\n}\n\nstatic int pouch_ready(")
    start = code.index("    int settled = 0;\n    if (ready && awaiting.deadline)")
    end = code.index("    if (ready) {", start)
    code = code[:start] + """    int settled = hk_teleport_poll(c, now, ready, result, sizeof result);
    const int manual_item = awaiting.deadline ? awaiting.item : -1;
    const int manual_result = ready && awaiting.deadline ? hk_pouch_poll(c, sp, mgr, now, result, sizeof result) : 0;
    settled |= manual_result != 0;
    const HkTrainerPrefs prefs = hk_prefs_get();
    const int keep = !!(prefs.flags & HK_PREF_HEALTH);
    const HkMagicStatus magic = hk_magic_tick(mgr, link, actor, now, generation, ready, action,
                                            prefs.flags, result, sizeof result, &settled);
    const int edit_pouch = action == TRAINER_ITEM || action == HK_TRAINER_REMOVE_ITEM || action == TRAINER_AMMO;
    const int ammo_busy = hk_ammo_tick(c, sp, mgr, now, generation, ready, manual_item, manual_result,
                                      edit_pouch || action == HK_TRAINER_TELEPORT || hk_teleport.deadline, prefs);
""" + code[end:]
    code = replace_once(code,
                        """        if (action == TRAINER_ITEM && item >= 0 && item < trainer_item_count) {
            if (pouch_add(c, sp, item, amount, mgr) <= 0)
                snprintf(result, sizeof result, "无法添加，请检查持有数量、容量与解锁条件。");
        }""",
                        """        if (action == HK_TRAINER_TELEPORT)
            hk_teleport_start(c, actor, item, now, result, sizeof result);
        if (edit_pouch && ammo_busy)
            snprintf(result, sizeof result, "弹药回补处理中，请稍后操作。");
        if (!ammo_busy && (action == TRAINER_ITEM || action == HK_TRAINER_REMOVE_ITEM) && item >= 0 && item < trainer_item_count) {
            const int removing = action == HK_TRAINER_REMOVE_ITEM;
            const int dispatched = amount > 0 && amount <= 1000 &&
                hk_pouch_change(c, sp, item, removing ? -amount : amount, mgr, result, sizeof result);
            if (!dispatched && !result[0])
                snprintf(result, sizeof result, "%s", removing ? "无法删除，请检查背包与持有状态。" :
                         "无法添加，请检查持有数量、容量与解锁条件。");
        }""")
    code = replace_once(code, "pouch_add(c, sp, item, cap-have, mgr) : -1;",
                       "hk_pouch_change(c, sp, item, cap-have, mgr, result, sizeof result) : 0;")
    code = replace_once(code, "        if (action == TRAINER_AMMO && item >= 0 && item < trainer_item_count) {",
                       "        if (!ammo_busy && action == TRAINER_AMMO && item >= 0 && item < trainer_item_count) {")
    code = replace_once(code, "    int action = request.action, item = request.item, amount = request.amount;",
                       "    const uint64_t generation = status.generation;\n"
                       "    int action = request.action, item = request.item, amount = request.amount;")
    code = replace_once(code, "    AcquireSRWLockExclusive(&state_lock);\n    if (action || settled) {",
                       "    AcquireSRWLockExclusive(&state_lock);\n    magic_status = magic;\n"
                       "    if (action || settled) {")
    code = replace_once(code, "        status.pending = awaiting.deadline != 0;\n"
                       "        snprintf(status.message, sizeof status.message, \"%s\", awaiting.deadline ?",
                       "        status.pending = awaiting.deadline != 0 || hk_teleport.deadline != 0 || hk_magic_pending.deadline != 0;\n"
                       "        snprintf(status.message, sizeof status.message, \"%s\", hk_teleport.deadline ?\n"
                       "                 \"传送已发出，等待地图载入…\" : hk_magic_pending.deadline ?\n"
                       "                 \"等待游戏同步魔力…\" : awaiting.deadline ?")
    return code


def linked_objects(original, out, filename, replacements):
    objects = []
    swapped = set()
    retained_dir = original / "obj"
    for row in (original / filename).read_text(encoding="utf-8").splitlines():
        path = Path(row.strip('"'))
        if tuple(p.lower() for p in path.parent.parts[-4:]) == (WORK.name.lower(), "sa", "build", "obj"):
            path = retained_dir / path.name
        path = path.resolve(strict=True)
        if path.parent != retained_dir or path.suffix != ".o":
            raise ValueError(f"Unexpected object path: {path}")
        if path.name in replacements:
            if path.name in swapped:
                raise ValueError(f"Duplicate object: {path.name}")
            swapped.add(path.name)
            path = replacements[path.name]
        objects.append(f'"{path.as_posix()}"')
    if swapped != replacements.keys():
        raise ValueError(f"The original build does not contain all requested objects: {swapped}")
    rsp = out / filename
    rsp.write_text("\n".join(objects), encoding="utf-8")
    return rsp


def build_display(out):
    source = (TOOLS / "host/display.c").read_text(encoding="utf-8")
    source = replace_once(source, "static LRESULT CALLBACK wndproc(HWND w, UINT msg, WPARAM wp, LPARAM lp) {\n",
                          '#include "trainer_input.h"\n\n'
                          "static LRESULT CALLBACK wndproc(HWND w, UINT msg, WPARAM wp, LPARAM lp) {\n"
                          "    if (hk_window_hotkey(w, msg, wp, lp)) return 0;\n"
                          "    if (hk_window_text(w, msg, wp, lp)) return 0;\n")
    source = replace_once(source, "    {   /* (nothing is typed here.", '    if (getenv("HOS_TRAINER_NO_IME")) {   /* (nothing is typed here.')
    for old, new in (("DefWindowProcA", "DefWindowProcW"), ("WNDCLASSA", "WNDCLASSW"),
                     ("wc.lpszClassName = \"Hookshot\";", "wc.lpszClassName = L\"Hookshot\";"),
                     ("RegisterClassA", "RegisterClassW"), ("CreateWindowA(\"Hookshot\", HOS_GAME_TITLE,", "CreateWindowW(L\"Hookshot\", L\"Hookshot\","),
                     ("GetMessageA", "GetMessageW"), ("DispatchMessageA", "DispatchMessageW")):
        source = source.replace(old, new)
    source = replace_once(source, '    if (!hwnd) display_start_failed("CreateWindowA");',
                          '    if (!hwnd) display_start_failed("CreateWindowW");\n'
                          '    ImmAssociateContextEx(hwnd, NULL, 0);')
    # The trainer uses a Unicode window. Let the native field validate Unicode
    # (including its full-width digits), without truncating it into an ANSI byte.
    source = replace_once(source,
                          '        static int trail;\n'
                          '        const BYTE c = (BYTE)wp;\n'
                          '        if (trail) trail = 0;\n'
                          '        else if (IsDBCSLeadByte(c)) trail = 1;\n'
                          '        else if (c >= 0x20 && c != 0x7F) hos_text_put(c);',
                          '        const uint32_t c = (uint32_t)wp;\n'
                          '        if (c >= 0x20 && c != 0x7F) hos_text_put(c);')
    patched = out / "display.c"
    patched.write_text(source, encoding="utf-8")
    return patched


def build_pad_input(out):
    source = (TOOLS / "host/nn_hid.c").read_text(encoding="utf-8")
    source = replace_once(source, "static void pads_read(uint64_t *buttons, int32_t stick[4]) {",
                          "uint32_t hk_pad_filter(uint32_t raw, int controllers, int player_ready);\n"
                          "int hk_sdl_pad_fresh(void);\n"
                          "int hos_oot_flight_shortcut_ready(void);\n\n"
                          "static void pads_read(uint64_t *buttons, int32_t stick[4]) {")
    source = replace_once(source, "    int sdl_pads = 0;", "    int sdl_pads = 0, hk_controllers = 0;")
    source = replace_once(source, "        sdl_pads = n;", "        sdl_pads = n;\n        hk_controllers += n;")
    source = replace_once(source, "            const WORD w = xs.Gamepad.wButtons;",
                          "            ++hk_controllers;\n            const WORD w = xs.Gamepad.wButtons;")
    source = replace_once(source, "    InterlockedExchange(&pad_raw_now, (LONG)raw);",
                          "    InterlockedExchange(&pad_raw_now, (LONG)raw);\n"
                          "    raw = hk_pad_filter((uint32_t)raw, hk_controllers,\n"
                          "                        (!sdl_pads || hk_sdl_pad_fresh()) &&\n"
                          "                        hos_oc_wait != 1 && !rx_option(1, 0) && hos_oot_flight_shortcut_ready());")
    patched = out / "nn_hid.c"
    patched.write_text(source, encoding="utf-8")
    return patched


def build_pad_sdl(out):
    source = (TOOLS / "host/pad_sdl.c").read_text(encoding="utf-8")
    source = replace_once(source, "static int state_count;", "static int state_count;\nstatic uint64_t hk_sdl_poll_ms;")
    source = replace_once(source, "        state_count = count;",
                          "        state_count = count;\n        hk_sdl_poll_ms = GetTickCount64();")
    source += '''
/* Freshness of the real SDL poll, not nn_hid's reads of its cached state. */
int hk_sdl_pad_fresh(void) {
    AcquireSRWLockShared(&state_lock);
    const int fresh = hk_sdl_poll_ms && GetTickCount64()-hk_sdl_poll_ms <= 100;
    ReleaseSRWLockShared(&state_lock);
    return fresh;
}
'''
    patched = out / "pad_sdl.c"
    patched.write_text(source, encoding="utf-8")
    return patched


def build_renderer(out, original, cc, target, nodefault, version, optional_libraries):
    gpu = TOOLS / "gpu"
    vk = gpu / "vk"
    source = (vk / "vk_menu.cpp").read_text(encoding="utf-8")
    source = replace_once(source, "std::atomic<int> player_flight{-1};",
                          '#include "trainer_api.h"\n#include "trainer_flight_mode.h"\n'
                          'std::atomic<int> player_flight{-1};\n'
                          'std::atomic<uint64_t> hk_flight_arm_due{0};')
    source = replace_once(source, "return cheats_on() ? player_flight.load(std::memory_order_relaxed) : -1;",
                          "return hk_flight_effective(player_flight.load(std::memory_order_relaxed), cheats_on());")
    source = replace_once(source, "    if (id == HOS_OPT_CHEAT_FLIGHT) {\n"
                          "        if (cheats_on()) {\n"
                          "            int expected = value ? 0 : 1;\n"
                          "            player_flight.compare_exchange_strong(expected, value != 0, std::memory_order_relaxed);\n"
                          "        }\n"
                          "        return;\n"
                          "    }",
                          "    if (id == HOS_OPT_CHEAT_FLIGHT) {\n"
                          "        hk_flight_shortcut(player_flight, cheats_on(), value != 0);\n"
                          "        return;\n"
                          "    }\n"
                          "    if (id == HK_OPT_CANCEL_TRAINER_FLIGHT) {\n"
                          "        hk_flight_arm_due.store(GetTickCount64() + 500);\n"
                          "        hk_flight_cancel(player_flight);\n"
                          "        return;\n"
                          "    }")
    source = replace_once(source, "void menu_tick() {",
                          '#include "trainer_overlay.h"\n\nvoid menu_tick() {')
    source = replace_once(source, "for (int c = VK_F2; c <= VK_F12; c++) k.push_back(c);",
                          "for (int c = VK_F2; c <= VK_F12; c++) if (c != VK_F6) k.push_back(c);")
    source = replace_once(source, "VK_OEM_2, VK_OEM_3, VK_OEM_4,", "VK_OEM_2, VK_OEM_4,")
    # The window notification is shared with the trainer; only native menu
    # handling may mark an opening as Escape so mouse capture is restored.
    source = replace_once(source,
                          "    const bool esc_opens = opts.menu_shortcut == 2 && press[5] && !open_now.load();",
                          "    esc_opens = opts.menu_shortcut == 2 && press[5] && !open_now.load();")
    source = replace_once(source, "    // (closing with a setting that takes a restart changed:",
                          "    bool esc_opens = false;\n"
                          "    if (!hk_overlay_frame(mine, press[0] || press[6], press[5],\n"
                          "                          press[1], press[2], press[7], press[13], press[14], ptr, mouse,\n"
                          "                          mouse ? mx + (int)menu_ox : -1, my)) {\n"
                          "    // (closing with a setting that takes a restart changed:")
    source = replace_once(source, "    {   // (hookshot) the window lets the mouse go while the menu is open,",
                          "    }\n    {   // (hookshot) the window lets the mouse go while the menu is open,")
    stock_draw = "    if (open) draw_menu(c);"
    if source.count(stock_draw) != 2:
        raise ValueError("Expected stock menu to draw on both output paths")
    source = source.replace(stock_draw,
                            "    if (open) { if (page == kTrainerPage) hk_paint(c); else draw_menu(c); }\n"
                            "    else if (navigation) hk_paint_navigation(c, position);")
    source = replace_once(source, "    if (!start && !fps && !open) {",
                          "    HkNavigation position{};\n"
                          "    const bool navigation = hk_visible_navigation(!start && !open, position);\n"
                          "    if (!start && !fps && !open && !navigation) {")
    source = replace_once(source, "    if (!open && !fps) return;",
                          "    HkNavigation position{};\n"
                          "    const bool navigation = hk_visible_navigation(!open && !startup_on.load(), position);\n"
                          "    if (!open && !fps && !navigation) return;")
    patched = out / "vk_menu.cpp"
    patched.write_text(source, encoding="utf-8")
    obj = out / "vk_vk_menu.o"

    def cpm(name):
        pkg, = (TOOLS / "cpm" / name).iterdir()
        return pkg / "include"

    spirv = cpm("spirv-headers")
    includes = [vk / "compat", gpu / "compat", vk / "eden", gpu / "third_party/suyu",
                vk / "sirit/include", vk / "sirit/src", spirv, spirv / "spirv/unified1",
                cpm("vulkanheaders"), vk, WORK / "sa/gen", cpm("vulkanmemoryallocator"),
                TOOLS / "third_party/imgui", TOOLS / "third_party/zbic",
                SOURCE, PREVIOUS, out]
    cxx = cc.with_name("clang++.exe")
    profile = WORK / "hookshot_vk.shipped.profdata"
    profile_key = hashlib.sha1(profile.read_bytes(), usedforsecurity=False).hexdigest()[:16]
    subprocess.run([str(cxx), *target, "-march=native", "-ffp-contract=off", "-std=c++20", "-O2", "-g0",
                    f"-fprofile-instr-use={profile}", f"-DHOOKSHOT_VK_PROFILE_SHA1={profile_key}",
                    "-DNDEBUG", "-DVK_NO_PROTOTYPES", "-DMKWVK_BUILDING", "-DMKWVK_INCLUDES=2", "-DHOOKSHOT_RELEASE",
                    "-DIMGUI_IMPL_VULKAN_NO_PROTOTYPES", "-DIMGUI_DISABLE_DEFAULT_SHELL_FUNCTIONS",
                    "-DIMGUI_DISABLE_WIN32_FUNCTIONS", "-DIMGUI_DISABLE_DEMO_WINDOWS", "-DIMGUI_DISABLE_DEBUG_TOOLS",
                    version, *[f"-I{x}" for x in includes],
                    *[f"-include{x}" for x in ("algorithm", "cstdio", "cstdlib", "cstring", "functional", "string", "vector")],
                    "-c", str(patched), "-o", str(obj)], check=True)
    rsp = linked_objects(original, out, "vk_objs.rsp", {obj.name: obj})
    dll = out / "hookshot_vk.dll"
    subprocess.run([str(cc), *target, "-fuse-ld=lld", "-static", *nodefault, "-shared",
                    "-o", str(dll), "@" + str(rsp), "-luser32", "-lc++", "-lunwind",
                    *optional_libraries], check=True)
    return dll


def patch_flight_pose(main_source):
    main_source = replace_once(main_source, "static _Thread_local uint64_t flight_pose_actor;",
                               "static _Thread_local uint64_t flight_pose_actor;\n"
                               "static _Thread_local float hk_flight_position[3];")
    main_source = replace_once(main_source,
                               "    flight_pose_actor = flying && !returning ? actor : 0;\n",
                               "")
    main_source = replace_once(main_source, "    change_position(c);\n    flight_transform_controller = 0;",
                               "    change_position(c);\n"
                               "    flight_transform_controller = 0;\n"
                               "    if (flying && !returning) {\n"
                               "        memcpy(hk_flight_position, target, sizeof hk_flight_position);\n"
                               "        flight_pose_actor = actor;\n"
                               "    }")
    return replace_once(main_source,
                        "    if (flight_pose_actor == actor) {\n"
                        "        flight_pose_actor = 0;\n"
                        "        oot_write_flight_rotation(c, matrix);",
                        "    if (flight_pose_actor && flight_pose_actor == actor) {\n"
                        "        flight_pose_actor = 0;\n"
                        "        oot_write_flight_rotation(c, matrix);\n"
                        "        for (unsigned row = 0; row < 3; ++row) {\n"
                        "            uint32_t bits;\n"
                        "            memcpy(&bits, &hk_flight_position[row], sizeof bits);\n"
                        "            recomp_store32(c, matrix + row * 16 + 12, bits);\n"
                        "        }")


def flight_movement_source():
    """Hot-piece numbering changes when the upstream call graph is regrouped."""
    matches = []
    for path in (WORK / "sa/gen").glob("code_hot_*.c"):
        source = path.read_text(encoding="utf-8")
        if "L_82c41778:;\n" in source:
            if source.count("L_82c41778:;\n") != 1 or source.count("L_82c41950:;\n") != 1:
                raise ValueError("Flight movement labels are no longer unique")
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(f"Expected one flight movement hot piece, found {len(matches)}")
    return matches[0]


def build_flight_movement(out, original, cc, target):
    gen = WORK / "sa/gen"
    source_path = flight_movement_source()
    source = source_path.read_text(encoding="utf-8")
    call = "    hos_oot_flight_pose(c, c->x[19], c->x[25]);\n"
    source = replace_once(source, "L_82c41778:;\n" + call, "L_82c41778:;\n")
    # Normal movement may replace the matrix after the original hook.
    # This point sees all those branches converge, before the matrix is published.
    source = replace_once(source, "L_82c41950:;\n", "L_82c41950:;\n" + call)
    patched = out / source_path.name
    patched.write_text(source, encoding="utf-8")
    obj = out / source_path.with_suffix(".o").name
    profile = WORK / "hookshot_pieces.prof"
    profile_key = hashlib.sha1(profile.read_bytes(), usedforsecurity=False).hexdigest()[:16]
    includes = [original / "rt64", gen, TOOLS / "third_party/a64-kit/rt", TOOLS / "nx2/rt"]
    subprocess.run([str(cc), *target, "-march=native", "-ffp-contract=off",
                    *[f"-I{x}" for x in includes], "-Wno-everything", "-fno-strict-aliasing", "-mcx16",
                    "-O2", "-g0", "-mllvm", "-rotation-max-header-size=0", "-ffunction-sections",
                    "-mllvm", "-capture-tracking-max-uses-to-explore=5000", "-DA64_POLLING", "-DA64_WRITE_TRACK",
                    f"-fprofile-instr-use={profile}", f"-DHOOKSHOT_PROFILE_SHA1={profile_key}",
                    "-c", str(patched), "-o", str(obj)], check=True)
    return obj


def main():
    global TOOLS, WORK
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--game", type=Path, required=True, help="Game folder containing romfs and .hookshot_exefs")
    parser.add_argument("--builder-root", type=Path, required=True, help="HookshotBuilder folder containing versions and work-v2.3.1")
    parser.add_argument("--base-exe", type=Path, help="Optional matching reference EXE. Defaults to the retained official build.")
    args = parser.parse_args()
    builder = args.builder_root.resolve(strict=True)
    TOOLS = builder / "versions" / UPSTREAM / "HookshotBuilder/tools"
    WORK = builder / f"work-{UPSTREAM}"
    out = args.out.resolve()
    game = args.game.resolve(strict=True)
    if any(out.is_relative_to(root) for root in (game, builder, SOURCE.parent)) or out.exists():
        raise ValueError("Choose a new output directory outside the source, game and Builder trees")
    if (TOOLS / "version.txt").read_text(encoding="utf-8").strip() != UPSTREAM:
        raise ValueError("The installed Hookshot toolchain has changed")
    original = (WORK / "sa/build").resolve(strict=True)
    for required in (flight_movement_source(), original / "objs.rsp", original / "vk_objs.rsp",
                     original / "hookshot.exe", original / "hookshot_vk.dll"):
        if not required.is_file():
            raise ValueError(f"Official build input missing: {required}; build with HOOKSHOT_KEEP_BUILD_FILES=1")
    from shader_size_fix import apply as check_shader_patch
    check_shader_patch(TOOLS, None, check=True)
    shader_object = original / "obj/vk_vk_shader.o"
    if b"native instruction span exceeds its validated package" not in shader_object.read_bytes():
        raise ValueError("Rebuild the retained Vulkan renderer after applying the shader patch (see README)")
    host_libraries, renderer_libraries, optional_libraries = optional_link_inputs(original)
    base_exe = args.base_exe or original / "hookshot.exe"
    if file_hash(base_exe) != file_hash(original / "hookshot.exe"):
        raise ValueError("Base EXE differs from the retained official build")
    for path, digest in (
        (game / ".hookshot_exefs/main", MAIN_SHA256),
        (args.reference, REFERENCE_SHA256),
    ):
        if file_hash(path) != digest:
            raise ValueError(f"Input differs from the verified local build: {path}")

    out.mkdir(parents=True)
    sys.path.insert(0, str(PREVIOUS))
    from catalog import RomFS
    from generate_catalog import make_catalog
    from quest_guidance import generate_quest_guidance
    from jabu_map import generate_jabu_map
    from world_map import generate_world_map
    from dungeon_geometry import generate_dungeon_geometry
    from dungeon_plan import generate_dungeon_plan

    rom = RomFS(game / "romfs")
    make_catalog(args.reference, out / "items.generated.h", rom, hookshot_bottle=True)
    regions = generate_world_map(rom, out)
    geometry = generate_dungeon_geometry(rom, out)
    generate_dungeon_plan(rom, out, geometry)
    generate_quest_guidance(rom, out / "quests.generated.h", regions)
    generate_jabu_map(rom, out / "jabu.generated.h")
    (out / "core.generated.h").write_text(core_for_hookshot(), encoding="utf-8")

    main_source = (TOOLS / "host/hos_main.c").read_text(encoding="utf-8")
    write_teleport_labels(main_source, (TOOLS / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8"),
                          out / "destinations.generated.h")
    main_source = replace_once(main_source, "static int64_t flight_player_seen;",
                               '#include "trainer_host.h"\n\nstatic int64_t flight_player_seen;')
    main_source = replace_once(main_source, "    CreateDirectoryA(hos_user_dir, NULL);",
                               "    CreateDirectoryA(hos_user_dir, NULL);\n    (void)hk_prefs_get();")
    main_source = replace_once(main_source, "    oot_update_player_cheats(c, actor, components);",
                               "    trainer_tick(c, movement - 0x1d50, actor);\n"
                               "    hk_navigation_tick(c, actor);\n"
                               "    hk_quest_tick(c);\n"
                               "    hk_flight_tick(c);\n"
                               "    oot_update_player_cheats(c, actor, components);")
    main_source = patch_flight_pose(main_source)
    patched = out / "hos_main.c"
    patched.write_text(main_source, encoding="utf-8")

    cc = TOOLS / "llvm-mingw/bin/clang.exe"
    ffmpeg, = (TOOLS / "cpm/ffmpeg").glob("*-windows-amd64")
    target = ["--target=x86_64-w64-mingw32", "-fms-extensions", "-D_CRT_SECURE_NO_WARNINGS"]
    stamp = hashlib.sha256()
    stamp.update(f"{UPSTREAM}\0{TRAINER_VERSION}\0".encode("ascii"))
    for relative in ("host/hos_main.c", "host/display.c", "host/nn_hid.c", "host/pad_sdl.c",
                     "gpu/vk/vk_menu.cpp", "gpu/vk/vk_api.h", "nx2/build.py"):
        stamp.update(relative.encode("ascii") + b"\0")
        stamp.update(file_hash(TOOLS / relative).encode("ascii"))
    for path in (original / "hookshot.exe", original / "hookshot_vk.dll", *optional_libraries):
        stamp.update(path.name.encode("utf-8") + b"\0")
        stamp.update(file_hash(path).encode("ascii"))
    for path in (SOURCE / "trainer_host.h", SOURCE / "trainer_overlay.h", SOURCE / "trainer_api.h",
                 SOURCE / "trainer_teleport.h", SOURCE / "trainer_pouch.h", out / "destinations.generated.h",
                 SOURCE / "trainer_input.h", SOURCE / "trainer_navigation.h", SOURCE / "forest_route.h", Path(__file__),
                 SOURCE / "trainer_pad_chord.h", SOURCE / "trainer_pad_bridge.h",
                 SOURCE / "trainer_quest.h", SOURCE / "trainer_quest_host.h", SOURCE / "quest_guidance.py",
                 SOURCE / "dungeon_guidance.h", SOURCE / "jabu_map.py", SOURCE / "jabu_route.h",
                 SOURCE / "world_map.py", SOURCE / "world_map.h", out / "jabu.generated.h",
                 SOURCE / "dungeon_geometry.py", SOURCE / "dungeon_plan.py", SOURCE / "dungeon_steps.py",
                 SOURCE / "dungeon_state.py", SOURCE / "dungeon_state.h", SOURCE / "dungeon_state_types.h",
                 SOURCE / "dungeon_route.h", SOURCE / "dungeon_plan_types.h", SOURCE / "dungeon_overlay.h",
                 out / "dungeon_state.generated.h", out / "dungeon_state_limits.generated.h",
                 out / "dungeon_geometry.generated.h", out / "dungeon_plan.generated.h",
                 out / "map_ids.generated.h", out / "map_data.generated.h",
                 SOURCE / "trainer_flight_mode.h", SOURCE / "trainer_flight_host.h",
                 SOURCE / "trainer_prefs.h", SOURCE / "trainer_ammo.h", SOURCE / "trainer_magic.h",
                 out / "quests.generated.h",
                 PREVIOUS / "trainer.c", PREVIOUS / "trainer.h", out / "items.generated.h",
                 out / "bottles.generated.h"):
        stamp.update(path.read_bytes())
    movement_source = flight_movement_source()
    stamp.update(movement_source.name.encode("ascii"))
    stamp.update(file_hash(movement_source).encode("ascii"))
    stamp.update(file_hash(WORK / "hookshot_vk.shipped.profdata").encode("ascii"))
    build_id = stamp.hexdigest()[:12]
    obj = out / "host_hos_main.o"
    includes = [TOOLS / "host", original / "rt64", WORK / "sa/gen", TOOLS / "third_party/opus/include",
                ffmpeg / "include", SOURCE, PREVIOUS, out]
    version = f'-DHOOKSHOT_VERSION="{UPSTREAM} (HookshotTrainer {TRAINER_VERSION} {build_id})"'
    display_obj = out / "host_display.o"
    pad_obj = out / "host_nn_hid.o"
    sdl_obj = out / "host_pad_sdl.o"
    for src, output in ((patched, obj), (build_display(out), display_obj), (build_pad_input(out), pad_obj),
                        (build_pad_sdl(out), sdl_obj)):
        subprocess.run([str(cc), *target, "-march=native", "-ffp-contract=off", "-O2", "-g0",
                        "-mcx16", "-DA64_POLLING", "-DA64_WRITE_TRACK", version,
                        *[f"-I{x}" for x in includes], "-c", str(src), "-o", str(output)], check=True)
    movement_obj = build_flight_movement(out, original, cc, target)
    rsp = linked_objects(original, out, "objs.rsp", {p.name: p for p in (obj, display_obj, pad_obj, sdl_obj, movement_obj)})
    exe = out / "hookshot.exe"
    nodefault = [f"-Wl,-Xlink=/nodefaultlib:{n}" for n in ("libcmt", "oldnames", "libvcruntime", "msvcrt")]
    subprocess.run([str(cc), *target, "-fuse-ld=lld", "-static", *nodefault,
                    "-o", str(exe), "-Wl,-Xlink=/stack:8388608", "@" + str(rsp),
                    "-Xlinker", f"-Xlink=/order:@{(WORK / 'hot_order.txt').as_posix()}", "-Wl,-Xlink=/ignore:4037",
                    "-lwinhttp", "-luser32", "-lwinmm", "-ladvapi32", "-lole32", "-lshell32",
                    "-lgdi32", "-ldbghelp", "-limm32", str(WORK / "hookshot.res"), str(original / "hookshot_manifest.res"),
                    "-Wl,-Xlink=/subsystem:windows", "-Wl,-Xlink=/entry:mainCRTStartup",
                    str(TOOLS / "wgpu-native/lib/wgpu_native.dll.lib"),
                    *[str(ffmpeg / "lib" / f"{n}.lib") for n in ("avcodec", "swscale", "swresample", "avutil")],
                    "-lbcrypt", "-lmfplat", "-lmfuuid", "-lstrmiids", "-lole32", *host_libraries,
                    "-lc++", "-lunwind"], check=True)
    dll = build_renderer(out, original, cc, target, nodefault, version, renderer_libraries)
    for binary in (exe, dll):
        print(f"Built {binary} ({build_id}) SHA256 {file_hash(binary)}")


if __name__ == "__main__":
    main()
