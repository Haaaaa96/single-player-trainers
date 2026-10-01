"""Explicit positive-only lifespan additions with native age/max inspection."""
import tkinter as tk
from tkinter import ttk, messagebox

from acquisition_adapter import native_calls_pending
from character_lifespan import LifespanAdapter, parse_increase, validate_increase
from write_guard import Refused, UncertainWrite


class LifespanPanel:
    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=18)
        app.tabs.add(frame, text="增加寿元")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="增加寿元", font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新寿元", command=self.detect)
        self.detect_button.pack(side="right")
        ttk.Label(frame, text="读取游戏计算的当前年龄和寿元上限，再增加额外寿元。不会改变角色年龄。",
                  wraplength=560).pack(fill="x", pady=(14, 16))
        self.summary = tk.StringVar(value="年龄 —  /  寿元上限 —")
        ttk.Label(frame, textvariable=self.summary, font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        self.note = tk.StringVar(value="先连接游戏，再读取寿元。读取会使用游戏原生连接。")
        ttk.Label(frame, textvariable=self.note, wraplength=560).pack(fill="x", pady=(10, 20))
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="本次增加年数").pack(side="left")
        self.input = tk.StringVar(value="1")
        self.entry = ttk.Entry(controls, textvariable=self.input, width=12)
        self.entry.pack(side="left", padx=10)
        self.add_button = ttk.Button(controls, text="增加寿元", command=self.change)
        self.add_button.pack(side="right")
        ttk.Label(frame, text="每次增加 1～1000 年额外寿元，仅接受正整数。实际寿元上限仍受游戏效果影响。\n"
                  "只在稳定普通场景操作；正在突破、死亡或寿尽处理时不执行。\n"
                  "此操作不提供减寿或无风险回退。需要保留时，请在游戏内手动存档。",
                  wraplength=560).pack(fill="x", pady=(20, 0))

    def update_enabled(self, enabled):
        available = bool(enabled and not native_calls_pending())
        self.detect_button.configure(state="normal" if available else "disabled")
        editable = bool(available and self.state and self.state.get("can_edit") and self.state.get("target"))
        for widget in (self.entry, self.add_button):
            widget.configure(state="normal" if editable else "disabled")

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter = self.state = None
        self.summary.set("年龄 —  /  寿元上限 —")
        self.note.set("先连接游戏，再读取寿元。")
        self.input.set("1")

    def detect(self):
        if self.app.busy or self.app.adapter is None or native_calls_pending():
            return
        game = self.app.adapter
        def job():
            if self.adapter is None:
                self.adapter = LifespanAdapter(game)
            try:
                return self.adapter.snapshot()
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        self.app.work(job, self.render)

    def render(self, state):
        if "not_written" in state:
            self.state = None
            self.summary.set("年龄 —  /  寿元上限 —")
            self.note.set(state["not_written"] + " 请核对后重新读取。")
        else:
            self.state = state
            self.summary.set(f"年龄 {state['current_age']}  /  寿元上限 {state['maximum']}")
            self.note.set("已由游戏原生方法核对年龄、上限和寿尽状态；请输入本次增加年数。")
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def change(self):
        if (self.app.busy or self.adapter is None or native_calls_pending() or not self.state
                or not self.state.get("can_edit") or not self.state.get("target")):
            return
        shown, adapter = self.state["target"], self.adapter
        try:
            amount = parse_increase(self.input.get())
            validate_increase(shown, amount)
        except Refused as error:
            messagebox.showwarning("检查增加年数", str(error), parent=self.app.root)
            return
        def job():
            try:
                return adapter.increase(shown, amount)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        def success(result):
            self.render(result)
            if "not_written" in result:
                self.app.status.set("尚未增加寿元。")
            else:
                self.note.set(f"额外寿元已增加 {amount} 年；游戏寿元上限 {shown.maximum} → {result['maximum']}。")
                self.app.status.set("寿元增加已由游戏执行并复读确认；不提供回退，请按需存档。")
        self.app.work(job, success)
