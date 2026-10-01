"""One unified page for current player health, mana and stamina."""
import tkinter as tk
from tkinter import ttk, messagebox
from types import SimpleNamespace

from acquisition_adapter import native_calls_pending
from character_ui import number
from current_resources import RESOURCE_SPECS, parse_attribute_value, validate_resource_value, resource_input
from write_guard import Refused, UncertainWrite


class StaminaPanel:
    """Keep the existing app extension name while expanding its resource scope."""
    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(frame, text="当前资源")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="当前资源", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新资源", command=self.detect)
        self.detect_button.pack(side="right")
        ttk.Label(frame, text="设置主角当前生命、灵力或精力。永久上限加成位于“人物属性”页。",
                  wraplength=560).pack(fill="x", pady=(10, 8))
        self.controls = {}
        for key, spec in RESOURCE_SPECS.items():
            box = ttk.LabelFrame(frame, text=spec["name"], padding=(12, 8))
            box.pack(fill="x", pady=5)
            row = SimpleNamespace(current=tk.StringVar(value="—"), maximum=tk.StringVar(value="设置时由游戏实时核对"),
                                  input=tk.StringVar(), note=tk.StringVar(value="请先读取。"))
            ttk.Label(box, text="当前值").grid(row=0, column=0, sticky="w", padx=(0, 12))
            ttk.Label(box, textvariable=row.current, font=("Segoe UI", 19, "bold"), width=8).grid(row=0, column=1, sticky="w")
            ttk.Label(box, text="目标值").grid(row=0, column=2, sticky="w", padx=(12, 8))
            row.entry = ttk.Entry(box, textvariable=row.input, width=12)
            row.entry.grid(row=0, column=3, sticky="w")
            row.button = ttk.Button(box, text="设置", command=lambda k=key: self.change(k), width=7)
            row.button.grid(row=0, column=4, padx=(10, 0))
            ttk.Label(box, text="实际上限").grid(row=1, column=0, sticky="w", pady=(4, 0))
            ttk.Label(box, textvariable=row.maximum).grid(row=1, column=1, columnspan=4, sticky="w", pady=(4, 0))
            ttk.Label(box, textvariable=row.note, wraplength=530).grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))
            self.controls[key] = row
        self.note = tk.StringVar(value="先连接游戏，再读取当前资源。")
        ttk.Label(frame, textvariable=self.note, wraplength=560).pack(fill="x", pady=(8, 8))
        ttk.Label(frame, text="支持小数，单次变化最多 1000。灵力与精力范围 0–1,000,000；生命至少为 1，不提供复活。\n"
                  "目标还须不超过游戏实时上限，超出时整次拒绝。仅在稳定普通场景设置。\n"
                  "每次仅修改选中资源；完成后请刷新再修改其他资源。需要保留时请在游戏内保存。",
                  wraplength=560).pack(fill="x")

    def update_enabled(self, enabled):
        available = bool(enabled and not native_calls_pending())
        self.detect_button.configure(state="normal" if available else "disabled")
        rows = self.state.get("rows", {}) if self.state else {}
        for key, widgets in self.controls.items():
            row = rows.get(key, {})
            target = row.get("target")
            editable = bool(available and row.get("can_edit") and target and target.key == key)
            for control in (widgets.entry, widgets.button):
                control.configure(state="normal" if editable else "disabled")

    def _clear(self):
        self.state = None
        for widgets in self.controls.values():
            widgets.current.set("—")
            widgets.maximum.set("设置时由游戏实时核对")
            widgets.input.set("")
            widgets.note.set("请先读取。")

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter = None
        self._clear()
        self.note.set("先连接游戏，再读取当前资源。")

    def detect(self):
        if self.app.busy or self.app.adapter is None or native_calls_pending():
            return
        game = self.app.adapter
        def job():
            from current_resources import CurrentResourcesAdapter
            if self.adapter is None:
                self.adapter = CurrentResourcesAdapter(game)
            return self.adapter.snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        for key, widgets in self.controls.items():
            row = state.get("rows", {}).get(key, {})
            widgets.current.set(number(row.get("current")))
            widgets.maximum.set("设置时由游戏实时核对" if row.get("maximum") is None
                                else number(row["maximum"]) + "（本次操作时）")
            widgets.input.set(resource_input(row["target"].value) if row.get("target") else "")
            widgets.note.set(row.get("reason") or "请输入目标值，设置时核对游戏实际上限。")
        self.note.set(state.get("message") or "已读取当前资源；各项独立设置，不会自动持续恢复。")
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def change(self, key="current_stamina"):
        if (key not in RESOURCE_SPECS or self.app.busy or self.adapter is None or native_calls_pending() or not self.state):
            return
        row = self.state.get("rows", {}).get(key, {})
        shown = row.get("target")
        if not row.get("can_edit") or shown is None or shown.key != key:
            return
        adapter, name = self.adapter, RESOURCE_SPECS[key]["name"]
        try:
            value = parse_attribute_value(self.controls[key].input.get())
            validate_resource_value(shown, value)
        except Refused as error:
            messagebox.showwarning(f"检查{name}数值", str(error), parent=self.app.root)
            return
        def job():
            try:
                result = adapter.set_value(shown, value)
                return dict(result, can_edit=True, reason=f"当前{name}已修改并复读确认；请回游戏核对。")
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        def success(result):
            if "not_written" in result:
                self._clear()
                self.note.set(result["not_written"] + " 请刷新资源后重试。")
                self.update_enabled(self.app.adapter is not None and not self.app.busy)
                self.app.status.set(f"当前{name}未修改。")
                return
            # Any set_Item changes the shared dictionary version. Discard the
            # other two old targets instead of offering them as fresh inputs.
            rows = {other: dict(target=None, can_edit=False, current=None, maximum=None, reason="请刷新后再修改。")
                    for other in RESOURCE_SPECS}
            rows[key] = result
            self.render(dict(rows=rows, message=f"当前{name}已修改。其他资源请刷新后再操作。"))
            self.app.status.set(f"当前{name}：{number(shown.value)} → {number(result['current'])}。游戏已执行并复读确认。")
        self.app.work(job, success)


CurrentResourcesPanel = StaminaPanel
