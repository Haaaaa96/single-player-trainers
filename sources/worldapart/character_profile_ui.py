"""Explicit target editing for reviewed cultivation and alignment scalars."""
import tkinter as tk
from tkinter import ttk, messagebox
from types import SimpleNamespace

from acquisition_adapter import native_calls_pending
from character_profile import FIELDS, parse_profile_value, validate_profile_value
from ui_errors import RefreshAfterWriteError
from write_guard import Refused, UncertainWrite


class CharacterProfilePanel:
    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=14)
        app.tabs.add(frame, text="修行储备")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="修行储备", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新", command=self.detect)
        self.detect_button.pack(side="right")
        ttk.Label(frame, text="输入修改后的目标整数，每项分别设置。丹田灵气仅修改储备，后续修行由游戏处理。",
                  wraplength=560).pack(fill="x", pady=(12, 10))
        self.controls = {}
        for key, spec in FIELDS.items():
            box = ttk.LabelFrame(frame, text=spec["name"], padding=12)
            box.pack(fill="x", pady=6)
            widgets = SimpleNamespace(current=tk.StringVar(value="—"), input=tk.StringVar(),
                                      note=tk.StringVar(value="请先读取。"))
            ttk.Label(box, text="当前值").grid(row=0, column=0, sticky="w")
            ttk.Label(box, textvariable=widgets.current, font=("Segoe UI", 19, "bold")).grid(
                row=0, column=1, sticky="w", padx=12, columnspan=2)
            ttk.Label(box, text="目标值").grid(row=1, column=0, sticky="w", pady=8)
            widgets.entry = ttk.Entry(box, textvariable=widgets.input, width=16)
            widgets.entry.grid(row=1, column=1, sticky="w", padx=12)
            widgets.button = ttk.Button(box, text="设置", command=lambda k=key:self.change(k))
            widgets.button.grid(row=1, column=2, sticky="w")
            ttk.Label(box, textvariable=widgets.note, wraplength=520).grid(
                row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))
            self.controls[key] = widgets
        self.note = tk.StringVar(value="先连接游戏，再读取修行储备数据。")
        ttk.Label(frame, textvariable=self.note, wraplength=560).pack(fill="x", pady=(12, 8))
        ttk.Label(frame, text="仅限整数，单次变化最多 1000。范围以各项说明为准。\n"
                  "在稳定普通场景使用；修改后请回游戏核对，需要保留时手动存档。",
                  wraplength=560).pack(fill="x")

    def available(self):
        return (not self.app.busy and self.app.adapter is not None
                and getattr(self.app.adapter, "write_enabled", True) is not False
                and not native_calls_pending())

    def update_enabled(self, enabled):
        available = bool(enabled and self.available())
        self.detect_button.configure(state="normal" if available else "disabled")
        for key, widgets in self.controls.items():
            target = (self.state or {}).get("rows", {}).get(key, {}).get("target")
            editable = bool(available and self.state and self.state.get("can_edit")
                            and target and target.key == key and target.can_edit)
            for widget in (widgets.entry, widgets.button):
                widget.configure(state="normal" if editable else "disabled")

    def _clear(self):
        self.state = None
        for widgets in self.controls.values():
            widgets.current.set("—")
            widgets.input.set("")
            widgets.note.set("请先读取。")

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter = None
        self._clear()
        self.note.set("先连接游戏，再读取修行储备数据。")
        self.update_enabled(False)

    def detect(self):
        if not self.available():
            return
        game = self.app.adapter
        self._clear()
        self.note.set("正在核对当前角色与场景……")
        def job():
            from character_profile import CharacterProfileAdapter
            if self.adapter is None:
                self.adapter = CharacterProfileAdapter(game)
            try:
                return self.adapter.snapshot()
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(read_error=str(error))
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self._clear()
        if "read_error" in state:
            self.note.set(state["read_error"] + " 请重新读取。")
        else:
            self.state = state
            for key, widgets in self.controls.items():
                row = state.get("rows", {}).get(key, {})
                target = row.get("target")
                if target is not None and target.key == key:
                    widgets.current.set(str(target.value))
                    widgets.input.set(str(target.value) if target.can_edit else "")
                    source = row.get("limit_source") or "工具限制"
                    widgets.note.set(f"允许 {target.minimum}～{target.maximum}（{source}）。 " + row.get("note", ""))
                else:
                    widgets.note.set(row.get("note") or "当前没有可核验的数据。")
            self.note.set(state.get("reason") or "已读取当前主角；设置后会重新核对数据。")
        self.update_enabled(True)

    def change(self, key):
        if key not in self.controls or not self.available() or self.adapter is None or not self.state or not self.state.get("can_edit"):
            return
        row = self.state.get("rows", {}).get(key, {})
        shown = row.get("target")
        if shown is None or shown.key != key or not shown.can_edit:
            return
        try:
            value = parse_profile_value(self.controls[key].input.get())
            validate_profile_value(shown, value)
        except Refused as error:
            messagebox.showwarning("检查目标数值", str(error), parent=self.app.root)
            return
        adapter, name = self.adapter, row["name"]
        def job():
            try:
                adapter.set_value(shown, value)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
            try:
                return adapter.snapshot()
            except Exception as error:
                raise RefreshAfterWriteError(f"{name}已修改并复读，但刷新失败；请核对游戏，勿重复设置。") from error
        def success(state):
            if "not_written" in state:
                self._clear()
                self.note.set(state["not_written"] + " 请刷新后再操作。")
                self.update_enabled(True)
                self.app.status.set(f"{name}未修改。")
                return
            self.render(state)
            self.app.status.set(f"{name}：{shown.value} → {value}。已复读确认；请回游戏核对。")
        self.app.work(job, success)
