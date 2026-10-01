"""Bounded one-shot base speed setting; never installs a repeating timer."""
import tkinter as tk
from tkinter import ttk, messagebox

from acquisition_adapter import native_calls_pending
from character_ui import number
from game_speed import parse_attribute_value, validate_speed_value
from write_guard import Refused, UncertainWrite


class GameSpeedPanel:
    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(frame, text="游戏速度")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="游戏速度", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新速度", command=self.detect)
        self.detect_button.pack(side="right")
        self.base, self.effective, self.input = tk.StringVar(value="—"), tk.StringVar(value="—"), tk.StringVar()
        values = ttk.LabelFrame(frame, text="当前状态", padding=12)
        values.pack(fill="x", pady=(16, 12))
        ttk.Label(values, text="基础速度").grid(row=0, column=0, sticky="w", padx=(0, 20))
        ttk.Label(values, textvariable=self.base, font=("Segoe UI", 21, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(values, text="当前生效（控制器）").grid(row=1, column=0, sticky="w", padx=(0, 20), pady=8)
        ttk.Label(values, textvariable=self.effective, font=("Segoe UI", 21, "bold")).grid(row=1, column=1, sticky="w")
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Label(row, text="目标基础速度").pack(side="left", padx=(0, 10))
        self.entry = ttk.Entry(row, textvariable=self.input, width=10)
        self.entry.pack(side="left")
        self.button = ttk.Button(row, text="设置速度", command=self.change)
        self.button.pack(side="left", padx=10)
        self.restore_button = ttk.Button(row, text="恢复 1.0", command=lambda: self.change(1.0))
        self.restore_button.pack(side="left")
        self.note = tk.StringVar(value="先连接游戏，再读取速度。")
        ttk.Label(frame, textvariable=self.note, wraplength=560).pack(fill="x", pady=16)
        ttk.Label(frame, text="基础速度范围 0.5–2.0 倍，每次只设置一次。仅支持普通稳定场景。\n"
                  "游戏的暂停、剧情和慢动作覆盖继续优先；存在覆盖时，基础值与生效值可能不同。\n"
                  "“恢复 1.0”只恢复基础速度，不会解除游戏暂停或清除覆盖。\n"
                  "读取显示刷新时刻的值；游戏仍可自行调整速度。退出修改器不会自动恢复，请需要时先按恢复按钮。",
                  wraplength=560).pack(fill="x")

    def update_enabled(self, enabled):
        available = bool(enabled and not native_calls_pending())
        self.detect_button.configure(state="normal" if available else "disabled")
        editable = bool(available and self.state and self.state.get("can_edit") and self.state.get("target"))
        for control in (self.entry, self.button, self.restore_button):
            control.configure(state="normal" if editable else "disabled")

    def clear(self):
        self.state = None
        self.base.set("—")
        self.effective.set("—")
        self.input.set("")

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter = None
        self.clear()
        self.note.set("先连接游戏，再读取速度。")

    def detect(self):
        if self.app.busy or self.app.adapter is None or native_calls_pending():
            return
        game = self.app.adapter
        def job():
            from game_speed import GameSpeedAdapter
            if self.adapter is None:
                self.adapter = GameSpeedAdapter(game)
            return self.adapter.snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        self.base.set(number(state["base"]) + " ×")
        self.effective.set(number(state["effective"]) + " ×")
        self.input.set(number(state["base"]))
        message = (f"游戏有 {state['override_count']} 项速度覆盖，当前生效 {number(state['effective'])} 倍。基础设置保留。"
                   if state["override_count"] else "当前没有游戏速度覆盖；基础速度生效。")
        self.note.set(state.get("reason") or message)
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def change(self, preset=None):
        if (self.app.busy or self.adapter is None or native_calls_pending() or not self.state
                or not self.state.get("can_edit") or not self.state.get("target")):
            return
        shown, adapter = self.state["target"], self.adapter
        try:
            value = parse_attribute_value(self.input.get()) if preset is None else preset
            validate_speed_value(shown, value)
        except Refused as error:
            messagebox.showwarning("检查速度设置", str(error), parent=self.app.root)
            return
        def job():
            try:
                return adapter.set_value(shown, value)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        def success(result):
            if "not_written" in result:
                self.clear()
                self.note.set(result["not_written"] + " 请刷新后重试。")
                self.update_enabled(self.app.adapter is not None and not self.app.busy)
                self.app.status.set("速度未修改。")
                return
            self.render(result)
            self.app.status.set(f"基础速度已设置 {number(result['base'])} 倍，当前生效 {number(result['effective'])} 倍；已复读确认。")
        self.app.work(job, success)
