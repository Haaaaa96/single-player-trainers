"""Read-only puzzle hints and bounded, native-paused MedGame controls."""
import tkinter as tk
from tkinter import ttk, messagebox

from write_guard import Refused, UncertainWrite
from meridian_logic import build_hint, build_restore_plan, SHAPE_NAMES
from acquisition_adapter import native_connection_block_reason


FIELDS = (("meridian_time", "剩余时间（秒）"),
          ("meridian_needles_used", "已用针数"),
          ("meridian_transform", "剩余变换次数"),
          ("meridian_reveal", "剩余揭示次数"))
DIRECTIONS = ("右", "右下", "左下", "左", "左上", "右上")


def pipe_label(cell, target=False):
    prefix = "target_" if target else ""
    shape = cell.get(prefix + "shape")
    if type(shape) is not int or not 0 <= shape < len(SHAPE_NAMES):
        return "—"
    directions = cell.get("target_ports" if target else "ports", ())
    return SHAPE_NAMES[shape] + "（" + " / ".join(DIRECTIONS[d] for d in directions) + "）"


class MeridianPanel:
    def __init__(self, app):
        self.app, self.resolver, self.state = app, None, None
        self.oneclick = None
        frame = ttk.Frame(app.tabs, padding=12)
        app.tabs.add(frame, text="疏经导脉辅助")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="疏经导脉 · 棋盘提示", font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="检测 / 刷新棋盘", command=self.detect)
        self.detect_button.pack(side="right")
        self.solve_button = ttk.Button(heading, text="一键疏通当前局", command=self.solve)
        self.solve_button.pack(side="right", padx=(0, 8))
        ttk.Label(frame, text="一键疏通：保持棋盘运行、取消退出确认；恢复本局原解，不扣针或技能次数，由游戏正常结算。",
                  wraplength=810).pack(fill="x", pady=(8, 0))
        ttk.Label(frame, text="手动设置数值：在游戏内点关闭/退出，停在确认框，不要确认退出，再刷新。",
                  wraplength=810).pack(fill="x", pady=(8, 5))
        self.note = tk.StringVar(value="尚未检测；先连接游戏并进入疏经导脉。")
        ttk.Label(frame, textvariable=self.note, wraplength=810).pack(fill="x", pady=(0, 6))

        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        self.inputs, self.currents, self.entries, self.buttons = {}, {}, {}, {}
        for column, (key, label) in enumerate(FIELDS):
            controls.columnconfigure(column, weight=1, uniform="meridian")
            box = ttk.LabelFrame(controls, text=label, padding=6)
            box.grid(row=0, column=column, sticky="nsew", padx=(0, 6) if column < 3 else 0)
            box.columnconfigure(0, weight=1)
            self.currents[key] = tk.StringVar(value="当前 —")
            ttk.Label(box, textvariable=self.currents[key], wraplength=185).grid(row=0, column=0, columnspan=2, sticky="w")
            self.inputs[key] = tk.StringVar()
            self.entries[key] = ttk.Entry(box, textvariable=self.inputs[key], width=9)
            self.entries[key].grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))
            self.buttons[key] = ttk.Button(box, text="设置", width=4, command=lambda selected=key: self.change(selected))
            self.buttons[key].grid(row=1, column=1, pady=(6, 0))
        ttk.Label(frame, text="已用针数越小，可用针数越多。恢复游戏后由游戏刷新显示；时间最多恢复到本局初始时限。",
                  wraplength=810).pack(fill="x", pady=(6, 7))

        self.summary = tk.StringVar(value="按棋盘自上而下数行、从左往右数列；提示不会自动操作游戏。")
        ttk.Label(frame, textvariable=self.summary, wraplength=810).pack(fill="x", pady=(0, 5))
        board = ttk.Frame(frame)
        board.pack(fill="both", expand=True)
        self.cells = ttk.Treeview(board, columns=("where", "current", "target", "state"), show="headings", height=4)
        for key, label, width in (("where", "棋盘位置", 100), ("current", "当前管道开口", 220),
                                  ("target", "参考路线目标", 220), ("state", "状态", 245)):
            self.cells.heading(key, text=label)
            self.cells.column(key, width=width, minwidth=60, stretch=True)
        scroll = ttk.Scrollbar(board, orient="vertical", command=self.cells.yview)
        self.cells.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.cells.pack(side="left", fill="both", expand=True)
        self.cells.tag_configure("route", background="#e4f2e8")
        steps_box = ttk.Frame(frame)
        steps_box.pack(fill="x", pady=(8, 0))
        self.steps = tk.Listbox(steps_box, height=3, font=("Microsoft YaHei UI", 10), activestyle="none")
        steps_vertical = ttk.Scrollbar(steps_box, orient="vertical", command=self.steps.yview)
        self.steps.configure(yscrollcommand=steps_vertical.set)
        steps_vertical.pack(side="right", fill="y")
        self.steps.pack(side="left", fill="x", expand=True)
        steps_scroll = ttk.Scrollbar(frame, orient="horizontal", command=self.steps.xview)
        self.steps.configure(xscrollcommand=steps_scroll.set)
        steps_scroll.pack(fill="x")
        self.warning = tk.StringVar(value="每次操作后刷新提示；浅绿行为已核验连通的参考路线。")
        ttk.Label(frame, textvariable=self.warning, wraplength=810).pack(fill="x", pady=(5, 0))

    def update_enabled(self, enabled):
        self.detect_button.configure(state="normal" if enabled else "disabled")
        if hasattr(self, "solve_button"):
            ready = enabled and self.state and self.state.get("can_solve") and build_restore_plan(self.state)["can_restore"]
            self.solve_button.configure(state="normal" if ready else "disabled")
        targets = (self.state or {}).get("targets", {})
        editable = enabled and self.state and self.state.get("active") and self.state.get("can_edit")
        for key in self.entries:
            state = "normal" if editable and key in targets else "disabled"
            self.entries[key].configure(state=state)
            self.buttons[key].configure(state=state)

    def disconnect(self):
        if getattr(self, "oneclick", None) is not None:
            self.oneclick.close()
            self.oneclick = None
        self.resolver = None
        self.render({"active": False, "reason": "尚未检测；先连接游戏并进入疏经导脉。"})
        self.state = None

    def detect(self):
        if self.app.busy or not self.app.adapter:
            return
        adapter = self.app.adapter
        def job():
            from meridian_adapter import MeridianResolver
            if self.resolver is None:
                self.resolver = MeridianResolver(adapter.resolver.reader, metadata_base=adapter.resolver.meta)
            try:
                state = self.resolver.snapshot()
                if state.get("active"):
                    reason = native_connection_block_reason(adapter)
                    if reason:
                        state = dict(state, can_solve=False, native_block_reason=reason)
                return state
            except Refused as error:
                return {"active": False, "reason": str(error)}
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        note = state.get("message") or state.get("reason") or "已读取当前棋盘。"
        if state.get("native_block_reason"):
            note = "一键疏通暂不可用：" + state["native_block_reason"]
        elif state.get("active") and "can_solve" in state:
            note = ("已暂停，可手动设置资源；一键疏通需先在游戏里取消退出确认。" if state.get("can_edit") else
                    "已读取运行中的棋盘，可一键疏通；手动设置资源需先停在退出确认框。" if state.get("can_solve") else
                    "当前局暂不可一键疏通，请取消退出确认、等待游戏动画结束后刷新。")
        self.note.set(note)
        values, targets = state.get("values", {}), state.get("targets", {})
        for key in self.inputs:
            value = values.get(key)
            target = targets.get(key)
            display = (f"{value:.2f}".rstrip("0").rstrip(".") if key == "meridian_time" else str(value)) if value is not None else ""
            self.inputs[key].set(display)
            current = f"当前 {display}" if value is not None else "当前 —"
            if target is not None:
                current += f"\n范围 {target.minimum:g}–{target.maximum:g}"
            self.currents[key].set(current)
        hint = build_hint(state)
        self.summary.set(hint["summary"])
        children = self.cells.get_children()
        if children:
            self.cells.delete(*children)
        for cell in sorted(hint["cells"], key=lambda c: (c["row"], c["col"])):
            tags = []
            if cell.get("on_route"):
                tags.append("参考路线")
            if cell["role"]:
                tags.append("起点" if cell["role"] == 1 else "终点")
            if cell["hidden"]:
                tags.append("未揭开")
            if cell.get("issue"):
                tags.append(cell["issue"])
            elif cell["kind"]:
                tags.append(("", "轻阻塞", "已锁定", "阻断")[cell["kind"]])
            self.cells.insert("", "end", values=(f"{cell['row'] + 1} 行 {cell['col'] + 1} 列",
                              pipe_label(cell), pipe_label(cell, True) if cell.get("on_route") else "—",
                              " / ".join(tags) or "普通"), tags=("route",) if cell.get("on_route") else ())
        self.steps.delete(0, tk.END)
        for index, step in enumerate(hint["steps"], 1):
            self.steps.insert(tk.END, f"{index}. {step['text']}")
        if not hint["steps"]:
            self.steps.insert(tk.END, "当前没有可列出的操作步骤。")
        self.warning.set(" ".join(hint["warnings"]) or "按棋盘从上到下数行、从左到右数列。")
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def solve(self):
        if (self.app.busy or not self.app.adapter or not self.resolver or not self.state
                or not self.state.get("can_solve")):
            return
        plan = build_restore_plan(self.state)
        if not plan["can_restore"]:
            messagebox.showwarning("检查一键疏通", plan["reason"], parent=self.app.root)
            return
        adapter, resolver, shown = self.app.adapter, self.resolver, self.state
        def job():
            from meridian_oneclick import MeridianOneClick
            try:
                if getattr(self, "oneclick", None) is None:
                    self.oneclick = MeridianOneClick(adapter, resolver)
                return self.oneclick.solve(shown)
            except UncertainWrite:
                raise  # App closes the connection; never classify as no change.
            except Refused as error:
                # Diagnostic events are separate from the once-only ledger:
                # never overwrite an earlier dispatched/uncertain round.
                try:
                    adapter.record(dict(operation="meridian_solve", status="not_called",
                                        called=False, reason=str(error)))
                except Exception:
                    pass  # A log failure must not obscure the original reason.
                return dict(not_called=str(error))
        def success(result):
            if "not_called" in result:
                self.render(dict(active=False, reason=result["not_called"]))
                self.app.status.set("一键疏通未调用：" + result["not_called"])
                return
            self.render(dict(active=False, reason=result["message"]))
            self.app.status.set(result["message"])
        self.app.status.set("正在校验当前局并请求一键疏通；请等待游戏结算，不要重复点击。")
        self.app.work(job, success)

    def change(self, key):
        if self.app.busy or not self.app.adapter or not self.state or not self.state.get("active") or not self.state.get("can_edit"):
            return
        shown = self.state.get("targets", {}).get(key)
        if shown is None:
            return
        from meridian_write import parse_value, validate, MeridianWriteOnce, set_meridian_value
        try:
            value = parse_value(key, self.inputs[key].get())
            validate(shown, value)
        except Refused as error:
            messagebox.showwarning("检查疏经导脉数值", str(error), parent=self.app.root)
            return
        adapter, resolver = self.app.adapter, self.resolver
        def job():
            try:
                memory = MeridianWriteOnce(adapter.resolver.reader, adapter.stamp, shown, new_value=value)
                set_meridian_value(memory, resolver.resolve, shown, value, adapter.record)
            except UncertainWrite:
                raise
            except Refused as error:
                return {"not_written": str(error)}
            try:
                return resolver.snapshot()
            except Exception as error:
                from ui_errors import RefreshAfterWriteError
                raise RefreshAfterWriteError("疏经导脉数值已写入并复读，但棋盘刷新失败；请核对游戏，勿重复设置。") from error
        def success(state):
            if "not_written" in state:
                self.disconnect()
                self.note.set(state["not_written"] + " 请暂停当前局并重新检测。")
                self.app.status.set("疏经导脉数值未修改；连接仍然可用。")
                return
            self.render(state)
            self.app.status.set("疏经导脉数值已写入并复读。取消游戏退出确认，恢复当前局后检查显示。")
        self.app.work(job, success)
