"""Manual values and one completion request for the current learning round."""
import tkinter as tk
from tkinter import ttk, messagebox

from write_guard import Refused, UncertainWrite


class LearningPanel:
    def __init__(self, app):
        self.app, self.resolver, self.state = app, None, None
        self.completion = None
        frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(frame, text="功法学习小游戏")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="功法学习", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="检测 / 刷新当前局", command=self.detect)
        self.detect_button.pack(side="right")
        self.complete_button = ttk.Button(heading, text="一键完成当前学习局", command=self.complete)
        self.complete_button.pack(side="right", padx=(0, 8))
        ttk.Label(frame, text="先开始学习，再检测当前局。一键填满本局领悟进度，由游戏正常结算；不需要先触发顿悟。",
                  wraplength=810).pack(fill="x", pady=(10, 0))
        self.note = tk.StringVar(value="尚未检测。")
        ttk.Label(frame, textvariable=self.note, wraplength=810).pack(fill="x", pady=16)
        self.inputs, self.currents, self.entries, self.buttons = {}, {}, {}, {}
        for key, label in (("learning_value", "功法领悟进度"),
                           ("learning_epiphany", "星星 / 顿悟蓄能（局内 %）")):
            box = ttk.LabelFrame(frame, text=label, padding=14)
            box.pack(fill="x", pady=(0, 12))
            box.columnconfigure(1, weight=1)
            self.currents[key] = tk.StringVar(value="—")
            ttk.Label(box, textvariable=self.currents[key], font=("Segoe UI", 20, "bold")).grid(row=0,column=0,columnspan=3,sticky="w")
            ttk.Label(box, text="目标值").grid(row=1, column=0, sticky="w", pady=(10, 0))
            self.inputs[key] = tk.StringVar()
            self.entries[key] = ttk.Entry(box, textvariable=self.inputs[key])
            self.entries[key].grid(row=1,column=1,sticky="ew",padx=14,pady=(10,0))
            self.buttons[key] = ttk.Button(box,text="设置",command=lambda selected=key:self.change(selected))
            self.buttons[key].grid(row=1,column=2,pady=(10,0))
        ttk.Label(frame, text="手动设置每次最多变化 1000；一键完成只填本局目标，不改顿悟蓄能。学习仍按游戏规则消耗秘籍和时间。\n"
                  "顿悟是局内辅助，不提高学成后的功法效果。出现“结果未确认”时先核对游戏，不重复执行。",
                  wraplength=810).pack(fill="x", pady=(4,0))

    def update_enabled(self, enabled):
        self.detect_button.configure(state="normal" if enabled else "disabled")
        active = enabled and self.state and self.state.get("active")
        if hasattr(self, "complete_button"):
            ready = enabled and self.state and self.state.get("can_complete")
            self.complete_button.configure(state="normal" if ready else "disabled")
        for key in self.entries:
            state = "normal" if active else "disabled"
            self.entries[key].configure(state=state)
            self.buttons[key].configure(state=state)

    def disconnect(self):
        self.resolver, self.state, self.completion = None, None, None
        self.note.set("尚未检测。")
        for key in self.inputs:
            self.inputs[key].set("")
            self.currents[key].set("—")

    def detect(self):
        if self.app.busy or not self.app.adapter:
            return
        adapter = self.app.adapter
        def job():
            from learning_adapter import LearningResolver
            if self.resolver is None:
                self.resolver = LearningResolver(adapter.resolver.reader, metadata_base=adapter.resolver.meta)
            return self.resolver.completion_snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        if state["active"]:
            note = f"已识别当前学习局；剩余约 {state['remaining_seconds']:.0f} 秒。领悟目标 {state['maximum']}，顿悟蓄能上限 100%。"
            if state.get("reason"):
                note += " " + state["reason"]
            self.note.set(note)
            for key in self.inputs:
                target = state["targets"][key]
                self.inputs[key].set(f"{target.value:.2f}".rstrip("0").rstrip("."))
                self.currents[key].set(f"{target.value:g} / {target.maximum:g}")
        else:
            self.note.set(state["reason"])
            for key in self.inputs:
                self.inputs[key].set("")
                self.currents[key].set("—")
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def complete(self):
        if (self.app.busy or not self.app.adapter or not self.resolver
                or not self.state or not self.state.get("can_complete")):
            return
        adapter, resolver, shown = self.app.adapter, self.resolver, self.state
        def job():
            from learning_completion import LearningCompletion
            try:
                if self.completion is None:
                    self.completion = LearningCompletion(adapter, resolver)
                return self.completion.complete(shown)
            except UncertainWrite:
                raise
            except Refused as error:
                return {"status": "not_written", "message": str(error)}
        def success(result):
            self.state = None
            for key in self.inputs:
                self.inputs[key].set("")
                self.currents[key].set("—")
            self.note.set(result["message"])
            self.app.status.set(result["message"])
            self.update_enabled(not self.app.busy and self.app.adapter is not None)
        self.app.work(job, success)

    def change(self, key):
        if self.app.busy or not self.app.adapter or not self.state or not self.state["active"]:
            return
        from learning_write import parse_float_value, validate_float, FloatWriteOnce, set_float_value
        shown = self.state["targets"][key]
        try:
            value = parse_float_value(self.inputs[key].get())
            validate_float(shown, value)
        except Refused as error:
            messagebox.showwarning("检查小游戏数值", str(error), parent=self.app.root)
            return
        adapter, resolver = self.app.adapter, self.resolver
        def job():
            try:
                memory = FloatWriteOnce(adapter.resolver.reader, adapter.stamp, shown, new_value=value)
                set_float_value(memory, resolver.resolve, shown, value, adapter.record)
            except UncertainWrite:
                raise
            except Refused as error:
                # This float-write module reserves Refused for proven no-write
                # outcomes; all uncertain post-write results use UncertainWrite.
                return {"not_written": str(error)}
            try:
                return resolver.snapshot()
            except Exception as error:
                from ui_errors import RefreshAfterWriteError
                raise RefreshAfterWriteError("小游戏数值已写入并复读，但当前局正在切换，请核对游戏。") from error
        def success(state):
            if "not_written" in state:
                self.disconnect()
                self.note.set(state["not_written"] + " 请检测当前局后再设置。")
                self.app.status.set("小游戏数值未修改；连接仍然可用。")
                return
            self.render(state)
            self.app.status.set("小游戏数值已写入并复读确认。最终学习结果由游戏结算。")
        self.app.work(job, success)
