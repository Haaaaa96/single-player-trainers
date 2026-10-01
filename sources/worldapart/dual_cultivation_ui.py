"""One-shot minigame panels; terminal results never trigger automatic retry."""
import tkinter as tk
from tkinter import ttk
from acquisition_adapter import native_calls_pending
from write_guard import Refused, UncertainWrite


class MiniGamePanel:
    title = "小游戏"
    button_text = "完成当前局"
    explanation = ""

    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(frame, text=self.title)
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text=self.title, font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新当前局", command=self.detect)
        self.detect_button.pack(side="right")
        self.summary = tk.StringVar(value="尚未读取当前局。")
        ttk.Label(frame, textvariable=self.summary, wraplength=560, font=("Microsoft YaHei UI", 11)).pack(fill="x", pady=(18, 14))
        self.button = ttk.Button(frame, text=self.button_text, command=self.solve)
        self.button.pack(anchor="w")
        self.note = tk.StringVar(value="先连接游戏，再读取当前局。")
        ttk.Label(frame, textvariable=self.note, wraplength=560).pack(fill="x", pady=16)
        ttk.Label(frame, text=self.explanation, wraplength=560).pack(fill="x")
        self.update_enabled(False)

    def update_enabled(self, enabled):
        available = bool(enabled and self.available())
        self.detect_button.configure(state="normal" if available else "disabled")
        self.button.configure(state="normal" if available and self.state and self.state.get("can_solve") else "disabled")

    def available(self):
        game = self.app.adapter
        return bool(game is not None and getattr(game, "write_enabled", True) is True
                    and not self.app.busy and not native_calls_pending()
                    and not getattr(game, "blocked", False)
                    and not (self.adapter and self.adapter.blocked))

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter, self.state = None, None
        self.summary.set("尚未读取当前局。")
        self.note.set("先连接游戏，再读取当前局。")
        self.update_enabled(False)

    def detect(self):
        if not self.available():
            return
        game = self.app.adapter
        self.state = None
        self.update_enabled(False)
        def job():
            if self.adapter is None:
                self.adapter = self.create_adapter(game)
            return self.adapter.snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        self.summary.set(self.describe(state) if state.get("active") else "当前没有可操作的活动局。")
        self.note.set(state.get("reason") or "当前局已确认，可以执行一次。")
        self.update_enabled(self.app.adapter is not None and not self.app.busy)

    def solve(self):
        if (not self.available() or self.adapter is None or not self.state
                or not self.state.get("can_solve")):
            return
        shown, adapter = self.state, self.adapter
        self.state = None
        self.update_enabled(False)
        def job():
            try:
                return adapter.solve(shown)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_called=str(error))
        def success(result):
            self.state = None
            text = result.get("not_called") or result["message"]
            self.note.set(text)
            self.app.status.set(text)
            self.update_enabled(self.app.adapter is not None and not self.app.busy)
        self.app.work(job, success)


class DualCultivationPanel(MiniGamePanel):
    title = "双修"
    button_text = "一键完成本局双修"
    explanation = ("先正常进入双修，按游戏界面提示开始本局，再点击“读取 / 刷新当前局”。\n"
                   "开始前、暂停中和结算中不能执行；恢复游戏后请重新读取。每局只派发一次原有成功结算。\n"
                   "正常条件、消耗、游戏时间和道侣关系影响仍由游戏处理；后续奖励界面需要在游戏内继续。\n"
                   "不会增加额外奖励，不自动开始下一局或保存。结果未确认时不自动重试。")

    def create_adapter(self, game):
        from dual_cultivation_adapter import DualCultivationAdapter
        return DualCultivationAdapter(game)

    def describe(self, state):
        phase = {0: "尚未开始", 1: "进行中", 2: "成功结算", 3: "失败结算"}.get(state.get("phase"), "状态待确认")
        return (f"对象编号 {state['npc_id']} · 双修配置 {state['config_id']} · {phase}\n"
                f"当前共鸣 {state['resonance']:.1f} / {state['required']} · 剩余 {state['remaining']:.1f} 秒")
