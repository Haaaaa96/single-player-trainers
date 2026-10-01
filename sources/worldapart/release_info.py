"""Release identity and the feature introduction bundled with every EXE."""
from runtime_paths import RESOURCE_ROOT

VERSION = "1.3"
UPDATED_AT = "2026-10-01"
SUPPORTED_GAME = "Steam build 25617557"
FREE_NOTICE = "本软件完全免费"
UPDATE_NOTICE = "版本差异仅作提醒，不限制连接和使用；未来游戏更新后部分功能可能失效。"
# Static release provenance only: identical for all users, with no device data,
# network access, enforcement, or obfuscation. This is removable, not DRM.
SOURCE_WATERMARK = "WorldApartTrainer|v1.3|2026-10-01|read-performance-1|public-source-snapshot"
FEATURES_FILE = "RELEASE_NOTES.md"


def read_feature_introduction():
    text = (RESOURCE_ROOT / FEATURES_FILE).read_text(encoding="utf-8")
    if VERSION not in text.splitlines()[0]:
        raise RuntimeError("功能介绍与当前软件版本不一致。")
    return text


def show_feature_introduction(parent):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    window = tk.Toplevel(parent)
    window.title("WorldApartTrainer v" + VERSION)
    window.geometry("790x640")
    window.minsize(600, 430)
    window.transient(parent)
    ttk.Label(window, text="功能介绍 · v" + VERSION,
              font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
    ttk.Label(window, text=f"{FREE_NOTICE}    更新：{UPDATED_AT}    适配：{SUPPORTED_GAME}",
              wraplength=720).pack(anchor="w", padx=18, pady=(0, 8))
    content = ScrolledText(window, wrap="word", font=("Microsoft YaHei UI", 10),
                           padx=12, pady=10, borderwidth=1)
    content.pack(fill="both", expand=True, padx=18, pady=(0, 12))
    content.insert("1.0", read_feature_introduction())
    content.configure(state="disabled")
    actions = ttk.Frame(window)
    actions.pack(fill="x", padx=18, pady=(0, 14))
    ttk.Button(actions, text="第三方许可", command=lambda: show_third_party_notices(window)).pack(side="left")
    ttk.Button(actions, text="关闭", command=window.destroy).pack(side="right")
    return window


LICENSE_FILES = (
    "Frida-COPYING.txt", "Frida-COPYING.LIB.txt", "Python-LICENSE.txt",
    "PyInstaller-COPYING.txt", "PyInstaller-Runtime-Notices.txt",
)


def read_third_party_notices():
    blocks = [(RESOURCE_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8-sig")]
    for name in LICENSE_FILES:
        blocks.append("\n\n" + "=" * 60 + "\n" + name + "\n" + "=" * 60 + "\n\n"
                      + (RESOURCE_ROOT / "licenses" / name).read_text(encoding="utf-8-sig"))
    return "\n".join(blocks)


def show_third_party_notices(parent):
    import tkinter as tk
    from tkinter import ttk
    from tkinter.scrolledtext import ScrolledText

    window = tk.Toplevel(parent)
    window.title("WorldApartTrainer — 第三方许可")
    window.geometry("790x640")
    window.minsize(600, 430)
    window.transient(parent)
    ttk.Label(window, text="第三方组件与完整许可文本",
              font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
    content = ScrolledText(window, wrap="word", font=("Microsoft YaHei UI", 10), padx=12, pady=10)
    content.pack(fill="both", expand=True, padx=18, pady=(0, 12))
    content.insert("1.0", read_third_party_notices())
    content.configure(state="disabled")
    ttk.Button(window, text="关闭", command=window.destroy).pack(anchor="e", padx=18, pady=(0, 14))
    return window
