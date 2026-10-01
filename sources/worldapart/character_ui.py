"""Character growth editing with explicit layer labels and pinned targets."""
import tkinter as tk
from tkinter import ttk, messagebox

from write_guard import Refused, UncertainWrite
from ui_errors import RefreshAfterWriteError


def number(value):
    return "—" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def display_number(target, value):
    # Interact targets retain integer experience units. Growth targets retain
    # raw float32 storage in the backend, while percentages use player units.
    from character_attributes_write import PERCENTAGE_IDS
    if getattr(target, "attr_id", None) in PERCENTAGE_IDS:
        from character_attributes_write import to_display_value
        return number(to_display_value(target, value))
    return number(value)


def unit_suffix(target):
    from character_attributes_write import PERCENTAGE_IDS
    return " 个百分点" if getattr(target, "attr_id", None) in PERCENTAGE_IDS else ""


class CharacterPanel:
    def __init__(self, app, kind="growth"):
        self.kind = kind
        interact = kind == "interact"
        self.app, self.adapter, self.state = app, None, None
        frame = ttk.Frame(app.tabs, padding=14)
        app.tabs.add(frame, text="资质与技艺" if interact else "人物属性")
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="资质与技艺 · 累计经验" if interact else "人物属性 · 永久成长加成",
                  font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新属性", command=self.detect)
        self.detect_button.pack(side="right")
        ttk.Label(frame, text=("灵机、体魄、神识、辩道、医术：修改累计经验，由游戏配置换算等级。"
                  if interact else "修改主角的成长加成，游戏据此计算属性。这里的目标值不是人物面板的最终总值。"),
                  wraplength=800).pack(fill="x", pady=(10, 5))
        ttk.Label(frame, text=("经验上限随当前境界变化；此处显示累计经验，不是人物面板的本级经验进度。"
                  if interact else "人物面板还会计入境界、装备、丹药和技能效果；修改后重新打开人物面板核对。"),
                  wraplength=800).pack(fill="x", pady=(0, 10))
        self.note = tk.StringVar(value="先连接游戏，再读取人物属性。")
        ttk.Label(frame, textvariable=self.note, wraplength=800).pack(fill="x", pady=(0, 8))
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("name", "growth", "total", "range"),
                                 displaycolumns=(("name", "growth", "total", "range") if interact else ("name", "growth", "range")),
                                 show="headings", selectmode="browse", height=7)
        for key, label, width in (("name", "属性", 190), ("growth", "累计经验" if interact else "成长加成", 160),
                                  ("total", "当前等级" if interact else "基础合计参考", 150),
                                  ("range", "经验范围（当前境界）" if interact else "允许范围（工具限制）", 205)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=90, stretch=True,
                             anchor="w" if key == "name" else "center")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Button-1>", self.block_busy_selection)
        self.tree.bind("<KeyPress>", self.block_busy_selection)
        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(14, 6))
        ttk.Label(controls, text="累计经验目标值" if interact else "成长加成目标值").pack(side="left")
        self.input = tk.StringVar()
        self.entry = ttk.Entry(controls, textvariable=self.input, width=16)
        self.entry.pack(side="left", padx=10)
        self.set_button = ttk.Button(controls, text="设置选中属性", command=self.change)
        self.set_button.pack(side="right")
        self.detail = tk.StringVar(value="请先选择一个属性。")
        ttk.Label(frame, textvariable=self.detail, wraplength=800).pack(fill="x", pady=(2, 7))
        ttk.Label(frame, text=("仅输入整数，单次经验变化最多 1000；范围按游戏当前境界配置限制。\n"
                  "修改后重新打开人物面板核对。保留修改时，请在游戏内手动存档。" if interact else
                  "最多两位小数。百分比按百分点输入，单次最多 10；移速最多 1；其他属性最多 1000。\n"
                  "提高上限不会补满当前资源，降低上限也不同时裁剪当前值；后续显示与消耗由游戏处理。"),
                  wraplength=800).pack(fill="x", pady=(4, 0))
        self.interact_panel = CharacterPanel(app, "interact") if not interact else None

    def selected(self):
        keys = self.tree.selection()
        return (self.state or {}).get("rows", {}).get(keys[0]) if keys else None

    def block_busy_selection(self, _event):
        return "break" if self.app.busy else None

    def update_enabled(self, enabled):
        if getattr(self, "interact_panel", None) is not None:
            self.interact_panel.update_enabled(enabled)
        self.detect_button.configure(state="normal" if enabled else "disabled")
        selected = self.selected()
        can_edit = bool(enabled and self.state and self.state.get("can_edit") and selected
                        and getattr(selected["target"], "can_edit", True))
        self.tree.state(["!disabled"] if enabled else ["disabled"])
        self.entry.configure(state="normal" if can_edit else "disabled")
        self.set_button.configure(state="normal" if can_edit else "disabled")

    def disconnect(self):
        if getattr(self, "interact_panel", None) is not None:
            self.interact_panel.disconnect()
        if self.adapter is not None:
            self.adapter.close()
        self.adapter, self.state = None, None
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.input.set("")
        self.detail.set("请先选择一个属性。")
        self.note.set("先连接游戏，再读取人物属性。")

    def detect(self):
        if self.app.busy or not self.app.adapter:
            return
        game = self.app.adapter
        def job():
            if getattr(self, "kind", "growth") == "interact":
                from character_attributes_interact import InteractAttributesAdapter as Adapter
            else:
                from character_attributes import CharacterAttributesAdapter as Adapter
            if self.adapter is None:
                self.adapter = Adapter(game)
            return self.adapter.snapshot()
        self.app.work(job, self.render, readonly=True)

    def render(self, state):
        selected = self.tree.selection()
        self.state = state
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        for key, row in state.get("rows", {}).items():
            target = row["target"]
            self.tree.insert("", "end", iid=key,
                             values=(row["name"], display_number(target, target.value) + unit_suffix(target),
                                     number(row.get("display_value")),
                                     f"{display_number(target, target.minimum)}–{display_number(target, target.maximum)}{unit_suffix(target)}"))
        if selected and selected[0] in state.get("rows", {}):
            self.tree.selection_set(selected[0])
        self.note.set(state.get("reason") or ("已读取当前主角；选择资质或技艺后输入累计经验目标值。"
                      if getattr(self, "kind", "growth") == "interact" else "已读取当前主角；选择属性后输入成长加成目标值。"))
        self.select()

    def select(self, _event=None):
        row = self.selected()
        if row is None:
            self.input.set("")
            self.detail.set("请先选择一个属性。")
        else:
            target = row["target"]
            self.input.set(display_number(target, target.value))
            self.detail.set(f"{row['name']} · {row.get('layer', '永久成长加成')}："
                            f"允许 {display_number(target, target.minimum)}–{display_number(target, target.maximum)}{unit_suffix(target)}。 " + row.get("note", ""))
        self.update_enabled(not self.app.busy and self.app.adapter is not None)

    def change(self):
        row = self.selected()
        if self.app.busy or self.adapter is None or not self.state or not self.state.get("can_edit") or row is None:
            return
        if getattr(self, "kind", "growth") == "interact":
            from character_attributes_interact import parse_attribute_value, validate_attribute_value
        else:
            from character_attributes import parse_attribute_value, validate_attribute_value
        shown, label = row["target"], row["name"]
        try:
            value = parse_attribute_value(self.input.get())
            if getattr(self, "kind", "growth") != "interact":
                from character_attributes_write import from_display_value
                value = from_display_value(shown, value)
            validate_attribute_value(shown, value)
        except Refused as error:
            messagebox.showwarning("检查属性数值", str(error), parent=self.app.root)
            return
        adapter = self.adapter
        def job():
            try:
                adapter.set_value(shown, value)
            except UncertainWrite:
                raise
            except Refused as error:
                return {"not_written": str(error)}
            try:
                return adapter.snapshot()
            except Exception as error:
                raise RefreshAfterWriteError("人物属性已修改并复读，但刷新失败；请核对游戏后再操作。") from error
        def success(state):
            if "not_written" in state:
                self.state = None
                self.input.set("")
                self.note.set(state["not_written"] + " 请刷新属性后再操作。")
                self.update_enabled(self.app.adapter is not None)
                self.app.status.set("人物属性未修改。")
                return
            self.render(state)
            layer = "累计经验" if getattr(self, "kind", "growth") == "interact" else "成长加成"
            self.app.status.set(f"{label}{layer}：{display_number(shown, shown.value)} → {display_number(shown, value)}{unit_suffix(shown)}。已复读确认；重新打开人物面板核对。")
        self.app.work(job, success)
