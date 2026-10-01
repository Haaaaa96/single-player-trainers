"""Searchable game catalogue and explicit add-quantity workflow."""
import tkinter as tk
from tkinter import ttk, messagebox

from write_guard import Refused, parse_value


def filtered_rows(rows, query, category, only_addable):
    words = query.strip().casefold().split()
    return [row for row in rows
            if (not only_addable or row["can_add"])
            and (category == "全部分类" or row["type_name"] == category)
            and all(word in f"{row['id']} {row['name']} {row['type_name']}".casefold()
                    for word in words)]


def add_quantity(row, text):
    if not row or not row["can_add"]:
        raise Refused((row or {}).get("reason") or "请先选择可添加的物品。")
    quantity = parse_value(text)
    if not 1 <= quantity <= row["max_quantity"]:
        raise Refused(f"本物品每次允许添加 1–{row['max_quantity']:,} 个。")
    return quantity


def item_detail(row, state):
    """Explain limits from cached display data; never query or inject on selection."""
    if not row or not row["can_add"]:
        return (row or {}).get("reason") or "选择物品后查看添加范围。"
    if not row.get("large_currency"):
        note = "这类物品可能由游戏按独立实例分格。" if row.get("may_split_single") else ""
        return (f"{row['name']}：配置堆叠上限 {row['stack_limit']:,}，"
                f"每次可添加 1–{row['max_quantity']:,} 个。{note}")
    maximum = row["balance_maximum"]
    summary = (f"{row['name']}：单次最多添加 {row['max_quantity']:,}；"
               f"总余额上限 {maximum:,}（游戏配置与工具限制取较低值），禁止超过。")
    # Missing targets can mean an absent item or an unsupported/invalid balance.
    # Never treat them as zero, or add together split targets whose total has not
    # been validated. The adapter always reads and verifies the real total again.
    balance = None
    if isinstance(state, dict):
        currencies = state.get("currencies", {})
        matches = [item for item in currencies.values() if item.get("item_id") == row["id"]]
        invalid = any(item.get("item_id") == row["id"] for item in state.get("diagnostics", []))
        if len(matches) == 1 and not invalid:
            value = matches[0]["target"].value
            if type(value) is int and 0 <= value <= maximum:
                balance = value
    if balance is None:
        return summary + "\n当前余额尚未核验；添加前会重新读取余额，超限时显示本次可添加数量。"
    remaining = min(row["max_quantity"], maximum - balance)
    return (summary + f"\n上次读取余额 {balance:,}；按该余额本次最多可加 {remaining:,}。"
            "点击添加前会重新核验，不会自动缩减或重复添加。")


class AcquisitionPanel:
    def __init__(self, app):
        self.app = app
        self.backend = None
        self.rows = []
        self.by_id = {}
        frame = ttk.Frame(app.tabs, padding=12)
        app.tabs.add(frame, text="添加物品与秘籍")
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text="从游戏完整物品清单中选择，可添加当前没有的物品。",
                  font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")
        self.load_button = ttk.Button(top, text="读取物品清单", command=self.load)
        self.load_button.pack(side="right")
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=12)
        ttk.Label(bar, text="搜索名称或编号").pack(side="left")
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.search, width=28)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(8, 12))
        self.category = tk.StringVar(value="全部分类")
        self.category_box = ttk.Combobox(bar, textvariable=self.category,
                                         values=("全部分类",), state="readonly", width=15)
        self.category_box.pack(side="left")
        self.only_addable = tk.BooleanVar(value=True)
        self.only_check = ttk.Checkbutton(bar, text="仅可添加", variable=self.only_addable,
                                          command=self.filter)
        self.only_check.pack(side="left", padx=(12, 0))
        self.search.trace_add("write", lambda *_: self.filter())
        self.category_box.bind("<<ComboboxSelected>>", self.filter)
        self.summary = tk.StringVar(value="连接游戏后，读取清单即可搜索。")
        ttk.Label(frame, textvariable=self.summary).pack(fill="x", pady=(0, 8))
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("name", "type", "limit", "id", "status"),
                                show="headings", selectmode="browse", height=8)
        for name, label, width in (("name", "名称", 270), ("type", "分类", 140),
                                   ("limit", "配置上限", 85), ("id", "编号", 100),
                                   ("status", "可用状态", 105)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, stretch=name == "name",
                             anchor="w" if name in ("name", "type") else "center")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("unavailable", foreground="#777777")
        self.tree.bind("<<TreeviewSelect>>", self.select)
        self.tree.bind("<Button-1>", app.block_busy_selection)
        self.tree.bind("<KeyPress>", app.block_busy_selection)
        self.detail = tk.StringVar(value="选择物品后查看添加范围。")
        detail_label = ttk.Label(frame, textvariable=self.detail, wraplength=810)
        detail_label.pack(fill="x", pady=(12, 8))
        detail_label.bind('<Configure>', lambda event: detail_label.configure(wraplength=max(100, event.width)))
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="新增数量").pack(side="left")
        self.quantity = tk.StringVar(value="1")
        self.quantity_entry = ttk.Entry(controls, textvariable=self.quantity, width=12)
        self.quantity_entry.pack(side="left", padx=12)
        self.add_button = ttk.Button(controls, text="添加选中物品", command=self.add)
        self.add_button.pack(side="right")
        ttk.Label(frame, text="请回到已验证的普通城镇／地图场景添加；人物互动、独立小游戏、战斗或转场时不开放添加。\n已有可用堆叠优先补数量；这里填写增加量。添加后请在游戏内手动存档。",
                  wraplength=810).pack(fill="x", pady=(12, 0))

    def selected(self):
        selection = self.tree.selection()
        return self.by_id.get(selection[0]) if selection else None

    def update_enabled(self, enabled):
        self.load_button.configure(state="normal" if enabled else "disabled")
        loaded = enabled and bool(self.rows)
        self.search_entry.configure(state="normal" if loaded else "disabled")
        self.category_box.configure(state="readonly" if loaded else "disabled")
        self.only_check.configure(state="normal" if loaded else "disabled")
        self.tree.state(["!disabled"] if loaded else ["disabled"])
        can_add = loaded and self.selected() and self.selected()["can_add"]
        self.quantity_entry.configure(state="normal" if can_add else "disabled")
        self.add_button.configure(state="normal" if can_add else "disabled")

    def disconnect(self):
        if self.backend:
            self.backend.close()
        self.backend = None
        self.rows, self.by_id = [], {}
        self.filter()
        self.summary.set("连接游戏后，读取清单即可搜索。")

    def load(self):
        if self.app.busy or not self.app.adapter:
            return
        self.app.status.set("正在读取当前游戏版本的完整物品清单……")
        adapter = self.app.adapter
        def job():
            from acquisition_adapter import AcquisitionAdapter
            if self.backend:
                self.backend.close()
            self.backend = AcquisitionAdapter(adapter)
            return self.backend.catalog()
        self.app.work(job, self.render, readonly=True)

    def render(self, rows):
        self.rows = rows
        self.by_id = {str(row["id"]): row for row in rows}
        categories = ["全部分类", *sorted({row["type_name"] for row in rows})]
        self.category_box.configure(values=categories)
        if self.category.get() not in categories:
            self.category.set("全部分类")
        self.filter()
        self.app.status.set("物品清单已读取。搜索并选择物品，输入新增数量后添加。")

    def filter(self, _event=None):
        previous = self.tree.selection()
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        rows = filtered_rows(self.rows, self.search.get(), self.category.get(), self.only_addable.get())
        visible = set()
        for row in rows:
            key = str(row["id"])
            visible.add(key)
            self.tree.insert("", "end", iid=key,
                             values=(row["name"], row["type_name"], row["stack_limit"],
                                     row["id"], "可添加" if row["can_add"] else "暂不开放"),
                             tags=() if row["can_add"] else ("unavailable",))
        if previous and previous[0] in visible:
            self.tree.selection_set(previous[0])
        elif len(rows) == 1:
            self.tree.selection_set(str(rows[0]["id"]))
        self.summary.set(f"完整清单 {len(self.rows)} 项 · 当前显示 {len(rows)} 项")
        self.select()

    def select(self, _event=None):
        self.quantity.set("1")
        self.update_detail()
        self.update_enabled(not self.app.busy and self.app.state is not None and self.app.adapter is not None)

    def update_detail(self):
        self.detail.set(item_detail(self.selected(), self.app.state))

    def add(self):
        if self.app.busy or not self.backend or not self.app.adapter:
            return
        row = self.selected()
        try:
            quantity = add_quantity(row, self.quantity.get())
        except Refused as error:
            messagebox.showwarning("检查新增数量", str(error), parent=self.app.root)
            return
        item_id, name = row["id"], row["name"]
        adapter, backend = self.app.adapter, self.backend
        self.app.status.set(f"正在添加 {name} × {quantity}，请保持游戏当前界面……")
        def job():
            from acquisition_context import AcquisitionContextRefused
            from acquisition_adapter import AcquisitionLimitRefused
            try:
                result = backend.add(item_id, quantity)
            except (AcquisitionContextRefused, AcquisitionLimitRefused) as error:
                # These precise gates have not written or dispatched an item call.
                # Preserve the catalogue and selection so a refused battle-time
                # action is not presented as a broken game connection.
                return None, None, str(error)
            try:
                state = adapter.snapshot()
            except Exception as error:
                from ui_errors import RefreshAfterWriteError
                raise RefreshAfterWriteError(f"{name} × {quantity} 已添加并核验，但列表刷新失败；请检查游戏，勿重复添加。\n{error}") from error
            return result, state, None
        def success(result):
            if self.app.adapter is not adapter or self.backend is not backend:
                return
            event, state, refusal = result
            if refusal:
                self.app.status.set(refusal)
                self.detail.set(refusal)
                messagebox.showwarning("当前不能添加", refusal, parent=self.app.root)
                return
            route = "已有堆叠已补充" if event.get('native_injection') is False else "已添加"
            self.app.render(state, f"{route} {name} × {quantity}，背包数量已核验。需要保留时请在游戏内手动存档。")
            self.update_detail()
        self.app.work(job, success)
