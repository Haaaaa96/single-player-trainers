"""Pill refining: one current QTE, or saved talent rank editing."""
import tkinter as tk
from tkinter import ttk, messagebox

from acquisition_adapter import native_calls_pending
from alchemy_talents import parse_rank, validate_rank
from write_guard import Refused, UncertainWrite


class AlchemyPanel:
    def __init__(self, app):
        self.app, self.adapter, self.talents = app, None, None
        self.state, self.talent_state = None, None
        self.frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(self.frame, text="炼丹辅助")
        ttk.Label(self.frame, text="炼丹辅助", font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        qte = ttk.LabelFrame(self.frame, text="当前火候小游戏", padding=12)
        qte.pack(fill="x", pady=(12, 10))
        self.qte_note = tk.StringVar(value="正常选择丹方、投入材料后读取。若提示等待灵力，请在游戏内添加灵力开始控火，再刷新。")
        ttk.Label(qte, textvariable=self.qte_note, wraplength=610).pack(fill="x")
        row = ttk.Frame(qte)
        row.pack(fill="x", pady=(10, 0))
        self.detect_button = ttk.Button(row, text="读取当前炼丹局", command=self.detect)
        self.detect_button.pack(side="left")
        self.solve_button = ttk.Button(row, text="一键最高品阶", command=self.solve)
        self.solve_button.pack(side="left", padx=12)
        ttk.Label(qte, text="每局仅一次。先完成正常材料消耗和注入灵力；只补满火候并进入游戏原有结算。\n"
                  "丹毒、药效、数量、经验及自动存档遵循游戏；不额外修改灵珠得分。", wraplength=610).pack(fill="x", pady=(10, 0))
        talent = ttk.LabelFrame(self.frame, text="炼丹天赋等级", padding=12)
        talent.pack(fill="both", expand=True)
        self.talent_note = tk.StringVar(value="炼丹使用逐项天赋等级，不存在独立天赋点余额。")
        ttk.Label(talent, textvariable=self.talent_note, wraplength=610).pack(fill="x")
        self.tree = ttk.Treeview(talent, columns=("name", "rank", "limit"), show="headings", height=7, selectmode="browse")
        for name, label, width in (("name", "天赋", 210), ("rank", "当前等级", 95), ("limit", "当前可设范围", 150)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        controls = ttk.Frame(talent)
        controls.pack(fill="x")
        self.talent_detect = ttk.Button(controls, text="读取天赋", command=self.detect_talents)
        self.talent_detect.pack(side="left")
        ttk.Label(controls, text="目标等级").pack(side="left", padx=(16, 8))
        self.rank = tk.StringVar()
        self.entry = ttk.Entry(controls, textvariable=self.rank, width=7)
        self.entry.pack(side="left")
        self.set_button = ttk.Button(controls, text="设置选中天赋", command=self.set_talent)
        self.set_button.pack(side="left", padx=10)
        ttk.Label(talent, text="每项配置上限 5 级，保留当前炼丹等级的解锁要求。0 表示移除该项。\n"
                  "修改不扣除或返还灵石；先退出炼丹探索、火候和天赋界面，修改后重开，存档后保留。", wraplength=610).pack(fill="x", pady=(10, 0))

    def _available(self):
        game = self.app.adapter
        return bool(game is not None and not self.app.busy and not native_calls_pending()
                    and getattr(game, "write_enabled", True) is not False
                    and getattr(game, "blocked", False) is not True
                    and getattr(self.adapter, "blocked", False) is not True
                    and getattr(self.talents, "blocked", False) is not True)

    def update_enabled(self, enabled):
        available = bool(enabled and self._available())
        for button in (self.detect_button, self.talent_detect):
            button.configure(state="normal" if available else "disabled")
        self.solve_button.configure(state="normal" if available and self.state and self.state.get("can_solve") else "disabled")
        edit = available and self.talent_state and self.talent_state.get("can_edit") and self.tree.selection()
        for control in (self.entry, self.set_button):
            control.configure(state="normal" if edit else "disabled")

    def disconnect(self):
        for adapter in (self.adapter, self.talents):
            if adapter is not None:
                adapter.close()
        self.adapter = self.talents = self.state = self.talent_state = None
        self.tree.delete(*self.tree.get_children())
        self.rank.set("")
        self.qte_note.set("先连接游戏，再读取当前炼丹局。")
        self.talent_note.set("先连接游戏，再读取炼丹天赋。")
        self.update_enabled(False)

    def detect(self):
        if not self._available():
            return
        self.state = None
        self.qte_note.set("正在读取当前炼丹局……")
        self.update_enabled(False)
        def job():
            from alchemy_adapter import AlchemyAdapter
            if self.adapter is None:
                self.adapter = AlchemyAdapter(self.app.adapter)
            return self.adapter.snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        self.state = state
        prefix = f"火候 {state['values']['progress']:.1f} / {state['values']['maximum']}。" if state.get("active") else ""
        self.qte_note.set(prefix + state["reason"])
        self.update_enabled(self.app.adapter is not None and not self.app.busy)

    def solve(self):
        if not self._available() or self.adapter is None or not self.state or not self.state.get("can_solve"):
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
                return dict(not_written=str(error))
        def success(result):
            self.state = None
            self.qte_note.set(result.get("not_written") or result["message"])
            self.app.status.set("炼丹未修改，请刷新。" if "not_written" in result else result["message"])
            self.update_enabled(self.app.adapter is not None and not self.app.busy)
        self.app.work(job, success)

    def detect_talents(self):
        if not self._available():
            return
        self.talent_state = None
        self.tree.delete(*self.tree.get_children())
        self.rank.set("")
        self.talent_note.set("正在读取炼丹天赋……")
        self.update_enabled(False)
        def job():
            from alchemy_talents import AlchemyTalentAdapter
            if self.talents is None:
                self.talents = AlchemyTalentAdapter(self.app.adapter)
            return self.talents.snapshot()
        self.app.work(job, self.render_talents, readonly=True)

    def render_talents(self, state):
        self.talent_state = state
        self.tree.delete(*self.tree.get_children())
        for key, row in state["rows"].items():
            self.tree.insert("", "end", iid=key, values=(row["name"], row["value"], f"0–{row['maximum']}（配置上限 5）"))
        self.talent_note.set(state["reason"] or f"当前炼丹等级 {state['player_level']}。选择天赋后手动输入目标等级。")
        self.rank.set("")
        self.update_enabled(self.app.adapter is not None and not self.app.busy)

    def select(self, _event=None):
        selection = self.tree.selection()
        if self.talent_state and selection:
            row = self.talent_state["rows"][selection[0]]
            self.rank.set(str(row["value"]))
            self.talent_note.set(self.talent_state["reason"] or row["note"])
        self.update_enabled(self.app.adapter is not None and not self.app.busy)

    def set_talent(self):
        selection = self.tree.selection()
        if (not self._available() or self.talents is None or not self.talent_state or not self.talent_state.get("can_edit")
                or not selection):
            return
        talent_id, shown, adapter = int(selection[0]), self.talent_state, self.talents
        try:
            value = parse_rank(self.rank.get())
            validate_rank(talent_id, value, shown["player_level"])
        except Refused as error:
            messagebox.showwarning("检查炼丹天赋等级", str(error), parent=self.app.root)
            return
        self.talent_state = None
        self.tree.delete(*self.tree.get_children())
        self.rank.set("")
        self.update_enabled(False)
        def job():
            try:
                return adapter.set_value(shown, talent_id, value)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        def success(result):
            if "not_written" in result:
                self.talent_state = None
                self.talent_note.set(result["not_written"] + " 请刷新。")
                self.app.status.set("炼丹天赋未修改。")
                self.update_enabled(self.app.adapter is not None and not self.app.busy)
            else:
                self.render_talents(result["snapshot"])
                self.app.status.set(result["message"])
        self.app.work(job, success)
