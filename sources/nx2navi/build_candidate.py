"""Relink a separate local candidate from the installed kit and existing objects."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from generate_catalog import make_catalog

INSTALL = Path(os.environ["LOCALAPPDATA"]) / "Programs/NX2navi"
SRC = Path(__file__).resolve().parent
MAIN_SHA256 = "ca344998b12a1b9c98444162dde46f9f6a53326e6107434bc42dfae2bc4a5eb4"
REFERENCE_SHA256 = "42d7777267e7959b958c8e6f8d1c247794bf0931ba2c3614628bbdc678e0de37"


def run(*args, env, capture=False):
    return subprocess.run([str(x) for x in args], env=env, check=True,
                          text=True, capture_output=capture)


def edit(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Expected one source anchor: {old}")
    return text.replace(old, new)


def make_menu_sources(rt, obj):
    menu = (rt/"ui/menu.cpp").read_text("utf-8")
    (obj/"fonts").mkdir(exist_ok=True)
    shutil.copy2(rt/"ui/fonts/Roboto-Medium.ttf", obj/"fonts/Roboto-Medium.ttf")
    menu = 'extern "C" {\n#include "trainer.h"\n}\n' + menu
    menu = edit(menu, "EV_FOCUS, EV_MAX = 256", "EV_FOCUS, EV_CHAR, EV_MAX = 256")
    menu = edit(menu, 'extern "C" void menu_event_focus',
                'extern "C" void menu_event_char(int c) { push({EV_CHAR, c, 0, 0, 0}); }\n'
                'extern "C" void menu_event_focus')
    menu = edit(menu, 'case EV_FOCUS: io.AddFocusEvent(e.a != 0); break;',
                'case EV_FOCUS: io.AddFocusEvent(e.a != 0); break;\n'
                '        case EV_CHAR: io.AddInputCharacterUTF16((ImWchar16)e.a); break;')
    menu = edit(menu, 'TAB_SOUND, TAB_CONTROLS, TAB_COUNT', 'TAB_SOUND, TAB_CONTROLS, TAB_CHEATS, TAB_COUNT')
    strings = "".join((obj/name).read_text("utf-8")
                      for name in ("trainer.c", "trainer_ui.cpp", "items.generated.h"))
    glyphs = "".join(sorted({char for char in strings if ord(char) >= 0x80}))
    menu = edit(menu, 'b.BuildRanges(&ranges[i]);',
                f'b.AddText({json.dumps(glyphs, ensure_ascii=False)});\n'
                '        b.AddText("金手指");\n        b.BuildRanges(&ranges[i]);')
    menu = edit(menu, 'b.BuildRanges(&title_ranges[i]);', 'b.AddText("金手指");\n            b.BuildRanges(&title_ranges[i]);')
    menu = edit(menu, 'int step = g_modal || binds_modal()', 'int step = g_modal || binds_modal() || ImGui::GetIO().WantTextInput')
    menu = edit(menu, 'snprintf(label, sizeof label, "  %s  ###tab%d", menu_text(kTabNames[k]), k);',
                'const char *title = k == TAB_CHEATS ? "金手指" : menu_text(kTabNames[k]);\n'
                '            snprintf(label, sizeof label, "  %s  ###tab%d", title, k);')
    menu = edit(menu, 'skin_tab_item(label, menu_text(kTabNames[k]),', 'skin_tab_item(label, title,')
    menu = edit(menu, 'case TAB_CONTROLS: tab_controls(scale); break;',
                'case TAB_CONTROLS: tab_controls(scale); break;\n'
                '            case TAB_CHEATS: if (tab_cheats(scale)) { restart_rebuild = true; g_confirm_quit = false; ImGui::OpenPopup("##confirm"); } break;')
    menu = edit(menu, 'if (!was_modal && (ImGui::IsKeyPressed(ImGuiKey_Escape, false)',
                'if (!was_modal && !ImGui::GetIO().WantTextInput && (ImGui::IsKeyPressed(ImGuiKey_Escape, false)')
    (obj/"menu.cpp").write_text(menu, encoding="utf-8")
    win = (rt/"ui/menu_win.cpp").read_text("utf-8")
    win = 'extern "C" void menu_event_char(int c);\n' + win
    win = edit(win, "case 'Q': return ImGuiKey_Q;", "case 'A': return ImGuiKey_A;\n    case 'C': return ImGuiKey_C;\n    case 'V': return ImGuiKey_V;\n    case 'X': return ImGuiKey_X;\n    case 'Q': return ImGuiKey_Q;")
    win = edit(win, 'static unsigned g_held;', 'static unsigned g_held;\nstatic bool composing;')
    win = edit(win, 'case WM_KEYDOWN:',
               'case WM_IME_STARTCOMPOSITION: composing = menu_is_open(); return 0;\n'
               '    case WM_IME_ENDCOMPOSITION: composing = false; return 0;\n'
               '    case WM_CHAR:\n'
               '        if (menu_is_open() && w >= 32 && w < 65536) { menu_event_char((int)w); *res = 0; return 1; }\n'
               '        return 0;\n    case WM_KEYDOWN:')
    win = edit(win, 'if (ImGuiKey k = key_of(w))',
               'if (composing && w == VK_RETURN && (m == WM_KEYDOWN || m == WM_SYSKEYDOWN)) return 0;\n'
               '        if (ImGuiKey k = key_of(w))')
    win = edit(win, 'case WM_KILLFOCUS:\n', 'case WM_KILLFOCUS:\n        if (m == WM_KILLFOCUS) composing = false;\n')
    (obj/"menu_win.cpp").write_text(win, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-root", type=Path, default=INSTALL)
    parser.add_argument("--game-dir", type=Path, help="Completed NX2navi game build (default: install-root/game)")
    parser.add_argument("--catalog-reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    install = args.install_root.resolve()
    game = (args.game_dir or install/"game").resolve()
    out = args.out.resolve()
    if out == install or out.is_relative_to(game) or out.is_relative_to(install/"app") or out.is_relative_to(install/"toolchain"):
        raise ValueError("Choose a separate output folder")
    if out.exists() and any(out.iterdir()):
        raise ValueError("Choose a new or empty output folder")
    kit = install/"app/0.6.1"
    cache = game/"build-cache"
    if (kit/"VERSION").read_text("utf-8").strip() != "0.6.1":
        raise ValueError("This patch expects the NX2navi 0.6.1 build kit")
    for path, expected in ((game/"exefs/main", MAIN_SHA256),
                           (args.catalog_reference, REFERENCE_SHA256)):
        with path.open("rb") as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != expected:
                raise ValueError(f"Input fingerprint differs: {path}")
    layouts = json.loads((cache/"lift/layout.json").read_text("utf-8"))
    if not any(entry["name"] == "main" and int(entry["base"], 0) == 0x7000000000
               and int(entry["size"], 0) == 0x4ea0000 for entry in layouts):
        raise ValueError("Guest layout differs from the recorded build")
    level = json.loads((cache/"obj/lifted-build.json").read_text("utf-8"))["level"]
    if level not in (0, 1, 2, 3, 4):
        raise ValueError("Unexpected lifted CPU level")
    obj = out/"build"
    obj.mkdir(parents=True)
    for name in ("trainer.h", "trainer.c", "trainer_ui.cpp"):
        shutil.copy2(SRC/name, obj/name)
    make_catalog(args.catalog_reference, obj/"items.generated.h", game)
    rt = kit/"runtime"
    tool = install/"toolchain/msys64/ucrt64"
    bin = tool/"bin"
    env = dict(os.environ, PATH=str(bin)+os.pathsep+os.environ["PATH"])

    lifted = cache / "lift/main/main_0373.c"
    text = lifted.read_text("utf-8")
    anchor = "    if (((x8 >> 1) & 1) != 0) { goto L_7002c21748; }"
    if text.count(anchor) != 1 or "void f_7002c215e0(Cpu *c) {" not in text:
        raise ValueError("Player movement update does not match the verified build")
    text = text.replace(anchor, "    trainer_tick(c, x19, sp_);\n"+anchor)
    (obj/"main_0373.c").write_text(
        text.replace('#include "cpu.h"', '#include "cpu.h"\nextern void trainer_tick(Cpu *, uint64_t, uint64_t);',1),
        encoding="utf-8")
    tab = (rt/"ui/cheats_tab.cpp").read_text("utf-8")
    anchor = '    opt_begin("##cheats", scale);'
    if tab.count(anchor) != 1:
        raise ValueError("Cheats tab changed")
    tab = 'extern "C" void trainer_ui(void);\n' + tab.replace(anchor,anchor+"\n    trainer_ui();")
    tab = edit(tab, '        opt_text_str(line);\n        opt_end();\n        return false;',
               '        opt_end();\n        return false;')
    (obj/"cheats_tab.cpp").write_text(tab, encoding="utf-8")
    make_menu_sources(rt, obj)
    lib = obj / "libnx2navirt.a"
    shutil.copy2(kit/"lib/libnx2navirt.a", lib)
    members = run(bin/"ar.exe","t",lib,env=env,capture=True).stdout.splitlines()
    replaced_members = {"rt_ui_cheats_tab.o", "rt_ui_menu.o", "rt_ui_menu_win.o"}
    if not replaced_members.issubset(set(members)):
        raise ValueError("Runtime archive layout differs")
    run(bin/"ar.exe","d",lib,*sorted(replaced_members),env=env)
    includes = [obj, rt, rt/"ui", cache/"gen", cache/"lift", rt/"third_party/imgui", tool/"include/vma"]
    inc = [x for directory in includes for x in ("-I", directory)]
    inputs = [("main_0373.c","main_main_0373.o"),("trainer.c","trainer.o"),
              ("trainer_ui.cpp","trainer_ui.o"),("cheats_tab.cpp","trainer_cheats_tab.o"),
              ("menu.cpp","trainer_menu.o"),("menu_win.cpp","trainer_menu_win.o")]
    for source, output in inputs:
        cpp = source.endswith(".cpp")
        guest = output.startswith("main_")
        run(bin/("clang++.exe" if cpp else "clang.exe"), "-c",
            "-std=gnu++17" if cpp else "-std=gnu11", "-O1" if guest else "-O2",
            *([f"-march=x86-64-v{level}"] if guest and level >= 2 else []), "-fno-strict-aliasing", *inc,
            "-o", obj/output, obj/source, env=env)
    rsp = obj / "trainer.rsp"
    lines = []
    for line in (cache/"link.rsp").read_text("utf-8").splitlines():
        if not (line.startswith('"') and line.endswith('"') and line.count('"') == 2):
            raise ValueError("Unexpected object path in NX2navi link.rsp")
        path = cache/"obj"/Path(line[1:-1]).name
        if path.suffix != ".o" or not path.is_file():
            raise ValueError(f"Missing cached object: {path.name}")
        lines.append(f'"{path.as_posix()}"')
    replaced = [i for i,line in enumerate(lines) if line.endswith('/main_main_0373.o"')]
    if len(replaced) != 1:
        raise ValueError("Original lifted object not found uniquely")
    lines[replaced[0]] = f'"{(obj/"main_main_0373.o").as_posix()}"'
    lines += [f'"{(obj/o).as_posix()}"' for _,o in inputs if not o.startswith("main_")]
    rsp.write_text("\n".join(lines), encoding="utf-8")
    libs = ("vulkan-1","SDL3","opus","vpx",":libdav1d.a","zstd",":libatomic.a","bcrypt",
            "imm32","uuid","ole32","user32","shell32","gdi32","advapi32","winmm")
    candidate = out/"ocarina.new.exe"
    run(bin/"clang++.exe","-Wl,--stack,16777216",
        "-Wl,--Map="+str(obj/"ocarina.map"),"-o",candidate,"@"+str(rsp),
        "-Wl,--whole-archive",lib,"-Wl,--no-whole-archive","-L",tool/"lib",
        *["-l"+x for x in libs],env=env)
    candidate.replace(out/"ocarina.exe")
    with (out/"ocarina.exe").open("rb") as f:
        print("Candidate SHA256",hashlib.file_digest(f,"sha256").hexdigest())
    print(out)


if __name__ == "__main__":
    main()
