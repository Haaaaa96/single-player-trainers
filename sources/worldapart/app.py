"""Local trainer UI. All mutations use the reviewed adapters and one worker."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from game_connection import connect_game as GameAdapter
from write_guard import Refused, UncertainWrite, parse_value, validate_value
from ui_errors import ReadOnlyPageError, RefreshAfterWriteError
from connection_diagnostics import ConnectionDiagnosticError, show_connection_error
from release_info import (VERSION, UPDATED_AT, SUPPORTED_GAME, FREE_NOTICE,
                          UPDATE_NOTICE, show_feature_introduction)
from acquisition_adapter import native_calls_pending, native_connection_block_reason
from item_categories import ALL_CATEGORIES, category_name
from navigation import SidebarNavigation, connection_label


class App:
    def __init__(self, root):
        self.root = root
        self.adapter = None
        self.state = None
        self.busy = False
        self.events = queue.Queue()
        self.extensions = []
        self.selected_game_path = None
        root.title(f"WorldApartTrainer v{VERSION}")
        root.geometry("940x800")
        root.minsize(860, 730)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(10, 5))
        style.configure("Treeview", font=("Microsoft YaHei UI", 10), rowheight=30)
        box = ttk.Frame(root, padding=14)
        box.pack(fill="both", expand=True)
        top = ttk.Frame(box)
        top.pack(fill="x")
        ttk.Label(top, text="不问凡尘 · 修改器", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        ttk.Label(top, text="v" + VERSION).pack(side="left", padx=12)
        self.connection_state = tk.StringVar(value="尚未连接")
        ttk.Label(top, textvariable=self.connection_state, foreground="#426578").pack(side="left", padx=(0, 8))
        self.connect_button = ttk.Button(top, text="连接游戏", command=self.connect)
        self.connect_button.pack(side="right")
        self.about_button = ttk.Button(top, text="功能介绍", command=lambda: show_feature_introduction(root))
        self.about_button.pack(side="right", padx=(0, 8))
        release_label = ttk.Label(box,
            text=f"更新：{UPDATED_AT}    适配：{SUPPORTED_GAME}",
            foreground="#426578", wraplength=810)
        release_label.pack(fill="x", pady=(7, 0))
        release_label.bind("<Configure>", lambda event: release_label.configure(wraplength=max(100, event.width)))
        update_label = ttk.Label(box, text=f"{FREE_NOTICE}。{UPDATE_NOTICE}", foreground="#81530e", wraplength=810)
        update_label.pack(fill="x", pady=(3, 0))
        update_label.bind("<Configure>", lambda event: update_label.configure(wraplength=max(100, event.width)))
        location = ttk.Frame(box)
        location.pack(fill="x", pady=(8, 0))
        location.columnconfigure(0, weight=1)
        self.auto_path_button = ttk.Button(location, text="自动识别", command=self.use_auto_path)
        self.auto_path_button.grid(row=0, column=2)
        self.choose_path_button = ttk.Button(location, text="选择游戏…", command=self.choose_game_path)
        self.choose_path_button.grid(row=0, column=1, padx=8)
        self.game_location = tk.StringVar(value="游戏位置：自动识别正在运行的 WorldApart.exe")
        path_label = ttk.Label(location, textvariable=self.game_location, wraplength=530)
        path_label.grid(row=0, column=0, sticky="ew")
        path_label.bind("<Configure>", lambda event: path_label.configure(wraplength=max(100, event.width)))
        self.status = tk.StringVar(value="尚未连接。请先进入存档，打开天赋或背包界面。")
        status_label = ttk.Label(box, textvariable=self.status, wraplength=810)
        status_label.pack(fill="x", pady=(8, 5))
        status_label.bind("<Configure>", lambda event:status_label.configure(wraplength=max(100,event.width)))
        self.connection_notice = tk.StringVar()
        notice_label = ttk.Label(box, textvariable=self.connection_notice, wraplength=810, foreground="#81530e")
        notice_label.pack(fill="x", pady=(0, 6))
        notice_label.bind("<Configure>", lambda event:notice_label.configure(wraplength=max(100,event.width)))

        self.navigation = SidebarNavigation(box, on_change=self.page_changed)
        self.navigation.pack(fill="both", expand=True)
        self.tabs = self.navigation.notebook
        points_page = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(points_page, text="角色点数")
        ttk.Label(points_page, text="角色点数", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", pady=(0, 14))
        talents = ttk.Frame(points_page)
        talents.pack(fill="x")
        talents.columnconfigure(0, weight=1, uniform="points")
        talents.columnconfigure(1, weight=1, uniform="points")
        self.point_values = {}
        self.point_inputs = {}
        self.point_entries = {}
        self.point_buttons = {}
        for column, (kind, label) in enumerate((("spirit", "剩余灵根点"), ("path", "剩余道途点"))):
            panel = ttk.LabelFrame(talents, text=label, padding=12)
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 7) if column == 0 else (7, 0))
            panel.columnconfigure(1, weight=1)
            current, target = tk.StringVar(value="—"), tk.StringVar()
            self.point_values[kind], self.point_inputs[kind] = current, target
            ttk.Label(panel, text="当前").grid(row=0, column=0, sticky="w")
            ttk.Label(panel, textvariable=current, font=("Segoe UI", 22, "bold")).grid(row=0, column=1, columnspan=2, sticky="w", padx=10)
            ttk.Label(panel, text="目标值").grid(row=1, column=0, sticky="w", pady=(8, 4))
            entry = ttk.Entry(panel, textvariable=target, width=10, font=("Segoe UI", 11))
            entry.grid(row=1, column=1, sticky="ew", padx=10, pady=(8, 4))
            button = ttk.Button(panel, text="设置", command=lambda key=kind: self.change(key))
            button.grid(row=1, column=2, pady=(8, 4))
            self.point_entries[kind], self.point_buttons[kind] = entry, button
            ttk.Label(panel, text="允许范围：0–1000（工具限制）").grid(row=2, column=0, columnspan=3, sticky="w", pady=(5, 0))
        ttk.Label(points_page, text="填写修改后的目标值。已分配的灵根和道途节点保持原状。\n"
                  "需要保留结果时，请在游戏内手动存档。", wraplength=680).pack(fill="x", pady=(18, 0))

        inventory_page = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(inventory_page, text="背包数量")
        ttk.Label(inventory_page, text="已有物品与余额", font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w")
        ttk.Label(inventory_page, text="这里设置已有堆叠的目标数量；获取新物品请使用左侧“物品获取”。",
                  wraplength=680).pack(fill="x", pady=(7, 12))
        inventory = ttk.Frame(inventory_page)
        inventory.pack(fill="both", expand=True)
        filters = ttk.Frame(inventory)
        filters.pack(fill="x", pady=(0, 8))
        self.inventory_mode = tk.StringVar(value="背包物品")
        self.inventory_filter = ttk.Combobox(filters, textvariable=self.inventory_mode,
                                           values=("背包物品", "货币余额"), state="readonly", width=16)
        self.inventory_filter.pack(side="left")
        self.inventory_filter.bind("<<ComboboxSelected>>", self.filter_items)
        ttk.Label(filters, text="分类").pack(side="left", padx=(14, 6))
        self.inventory_category = tk.StringVar(value=ALL_CATEGORIES)
        self.inventory_category_filter = ttk.Combobox(filters, textvariable=self.inventory_category,
                                                     values=(ALL_CATEGORIES,), state="readonly", width=15)
        self.inventory_category_filter.pack(side="left")
        self.inventory_category_filter.bind("<<ComboboxSelected>>", self.filter_items)
        self._inventory_mode_shown = self.inventory_mode.get()
        self.inventory_note = tk.StringVar()
        inventory_note_label = ttk.Label(inventory, textvariable=self.inventory_note, wraplength=680)
        inventory_note_label.pack(fill="x", pady=(0, 8))
        inventory_note_label.bind("<Configure>", lambda event:
            inventory_note_label.configure(wraplength=max(100, event.width)))
        table = ttk.Frame(inventory)
        table.pack(fill="both", expand=True)
        self.items = ttk.Treeview(table, columns=("name", "type", "count", "maximum"), show="headings", selectmode="browse", height=9)
        for column, label, width in (("name", "物品名称", 260), ("type", "分类", 100),
                                     ("count", "当前数量", 85), ("maximum", "单格上限", 85)):
            self.items.heading(column, text=label)
            self.items.column(column, width=width, anchor="w" if column in ("name", "type") else "center", stretch=column == "name")
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.items.yview)
        self.items.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.items.pack(side="left", fill="both", expand=True)
        self.items.bind("<<TreeviewSelect>>", self.select_item)
        # These bindings prevent selection changes while the worker uses its target.
        self.items.bind("<Button-1>", self.block_busy_selection)
        self.items.bind("<KeyPress>", self.block_busy_selection)
        controls = ttk.Frame(inventory)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Label(controls, text="目标数量").pack(side="left")
        self.item_input = tk.StringVar()
        self.item_entry = ttk.Entry(controls, textvariable=self.item_input, width=12, font=("Segoe UI", 11))
        self.item_entry.pack(side="left", padx=10)
        self.item_button = ttk.Button(controls, text="设置选中物品", command=lambda: self.change("item"))
        self.item_button.pack(side="right")
        self.item_range = tk.StringVar(value="请先选中一种物品。")
        item_range_label = ttk.Label(inventory, textvariable=self.item_range, wraplength=680)
        item_range_label.pack(fill="x", pady=(7, 0))
        item_range_label.bind("<Configure>", lambda event:
            item_range_label.configure(wraplength=max(100, event.width)))

        from acquisition_ui import AcquisitionPanel
        from learning_ui import LearningPanel
        from meridian_ui import MeridianPanel
        from character_ui import CharacterPanel
        from current_resources_ui import StaminaPanel
        from character_profile_ui import CharacterProfilePanel
        from character_lifespan_ui import LifespanPanel
        from game_speed_ui import GameSpeedPanel
        from alchemy_ui import AlchemyPanel
        from alchemy_recipe_ui import AlchemyRecipePanel
        from crafting_ui import CraftingPanel
        from dual_cultivation_ui import DualCultivationPanel
        from jade_ui import JadePanel
        from photostone_ui import PhotostonePanel
        from persuasion_ui import PersuasionPanel
        character = CharacterPanel(self)
        profile = CharacterProfilePanel(self)
        lifespan = LifespanPanel(self)
        resources = StaminaPanel(self)
        acquisition = AcquisitionPanel(self)
        learning = LearningPanel(self)
        meridian = MeridianPanel(self)
        speed = GameSpeedPanel(self)
        photostone = PhotostonePanel(self)
        persuasion = PersuasionPanel(self)
        alchemy = AlchemyPanel(self)
        recipes = AlchemyRecipePanel(self)
        crafting = CraftingPanel(self)
        dual = DualCultivationPanel(self)
        jade = JadePanel(self)
        self.extensions = [character, profile, lifespan, resources, acquisition, learning, meridian, speed, photostone, persuasion,
                           alchemy, recipes, crafting, dual, jade]
        self._page_refreshers = {
            "人物属性": character.detect, "资质与技艺": character.interact_panel.detect,
            "修行储备": profile.detect,
            "增加寿元": lifespan.detect,
            "当前精力": resources.detect, "当前资源": resources.detect,
            "添加物品与秘籍": acquisition.load, "功法学习小游戏": learning.detect,
            "疏经导脉辅助": meridian.detect,
            "游戏速度": speed.detect,
            "留影石": photostone.detect, "秒说服": persuasion.detect,
            "炼丹辅助": alchemy.detect, "丹方探索": recipes.detect, "炼器辅助": crafting.detect,
            "双修": dual.detect, "刮玉": jade.detect,
        }

        footer = ttk.Frame(box)
        # Keep the shared actions visible when a page needs vertical scrolling.
        footer.pack(side="bottom", fill="x", pady=(10, 0), before=self.navigation)
        self.refresh_button = ttk.Button(footer, text="刷新本页", command=self.refresh_active)
        self.refresh_button.pack(side="right", padx=(12, 0))
        ttk.Label(footer, text="修改后在游戏内核对；需要保留时，请手动存档。", wraplength=570).pack(side="left")
        self.buttons()
        root.after(100, self.poll)

    def inventory_rows(self):
        if self.state is None:
            return {}
        return self.state.get("currencies" if self.inventory_mode.get() == "货币余额" else "items", {})

    def current_rows(self):
        rows = self.inventory_rows()
        category = self.inventory_category.get()
        return rows if category == ALL_CATEGORIES else {
            key: row for key, row in rows.items() if category_name(row) == category}

    def selected_item(self):
        selected = self.items.selection()
        return self.current_rows().get(selected[0]) if selected else None

    def buttons(self):
        enabled = not self.busy and self.adapter is not None and self.state is not None
        pending = native_calls_pending()
        if hasattr(self, "connection_state"):
            self.connection_state.set(connection_label(self.adapter is not None and self.state is not None,
                getattr(self.adapter, "write_enabled", True) is False, self.busy, pending))
        writable = enabled and not pending and getattr(self.adapter, "write_enabled", True) is not False
        connectable = not self.busy and not pending
        self.connect_button.configure(state="normal" if connectable else "disabled")
        self.choose_path_button.configure(state="normal" if connectable else "disabled")
        self.auto_path_button.configure(state="normal" if connectable and self.selected_game_path else "disabled")
        self.refresh_button.configure(state="normal" if enabled else "disabled")
        for kind in self.point_entries:
            point_enabled = writable and kind in self.state
            state = "normal" if point_enabled else "disabled"
            self.point_entries[kind].configure(state=state)
            self.point_buttons[kind].configure(state=state)
        self.items.state(["!disabled"] if enabled else ["disabled"])
        self.inventory_filter.configure(state="readonly" if enabled else "disabled")
        self.inventory_category_filter.configure(state="readonly" if enabled else "disabled")
        item_enabled = writable and self.selected_item() is not None
        self.item_entry.configure(state="normal" if item_enabled else "disabled")
        self.item_button.configure(state="normal" if item_enabled else "disabled")
        for extension in self.extensions:
            extension.update_enabled(writable)

    def block_busy_selection(self, _event):
        if self.busy or self.state is None:
            return "break"
        return None

    def select_item(self, _event=None):
        row = self.selected_item()
        if row is None:
            self.item_input.set("")
            self.item_range.set("当前分类没有可修改物品，请选择其他分类。"
                                if self.state is not None and self.inventory_category.get() != ALL_CATEGORIES
                                and not self.current_rows() else "请先选中一种物品。")
        else:
            target = row["target"]
            self.item_input.set(str(target.value))
            source = row.get("limit_source", "游戏单格上限")
            lower = max(target.minimum, target.value - target.max_change)
            upper = min(target.maximum, target.value + target.max_change)
            available = (f"本次可设 {lower:,}–{upper:,}；填写修改后的目标值。" if lower <= upper
                         else "当前值超过工具可编辑范围，本次没有可设置的目标。")
            total_limit = (f"总余额上限 {target.maximum:,}（{source}），禁止超过；"
                           if row.get("category") == "currency" else "")
            self.item_range.set(f"{row['name']}：目标范围 {target.minimum:,}–{target.maximum:,}（{source}）；"
                                f"单次变化量最多 {target.max_change:,}。\n{total_limit}{available}")
        self.buttons()

    def shutdown_adapter(self):
        for extension in self.extensions:
            extension.disconnect()
        if self.adapter:
            self.adapter.close()
        self.adapter = None
        if hasattr(self, "connection_notice"):
            self.connection_notice.set("")

    def work(self, fn, success, *, readonly=False):
        if self.busy:
            return
        # Opt in only for memory reads: setters, native getters and any refresh
        # chained after a write must keep the default fail-closed behavior.
        adapter = self.adapter
        self.busy = True
        self.buttons()
        def run():
            try:
                self.events.put((success, fn(), None))
            except Exception as error:
                if (readonly is True and adapter is not None and self.adapter is adapter
                        and not isinstance(error, (RefreshAfterWriteError, UncertainWrite))):
                    try:
                        if native_calls_pending():
                            raise Refused("原生操作尚未结束，不能单独恢复基础连接。")
                        state = adapter.snapshot()
                    except Exception:
                        pass  # The original failure remains a full disconnect.
                    else:
                        if self.adapter is adapter:
                            error = ReadOnlyPageError(error, adapter, state)
                self.events.put((success, None, error))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            success, result, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if error is not None:
                if isinstance(error, ReadOnlyPageError) and self.adapter is error.adapter:
                    # UI-owned targets are discarded only on the UI thread.
                    # Re-render the fresh core snapshot instead of retaining
                    # targets captured before the failed extension read.
                    for extension in self.extensions:
                        extension.disconnect()
                    self.render(error.state, "当前页读取失败：" + str(error)
                                + "；基础连接已重新核验，可继续使用其他功能。")
                else:
                    # No follow-up writes after any uncertain result or stale state.
                    self.shutdown_adapter()
                    self.state = None
                    if isinstance(error, RefreshAfterWriteError):
                        self.status.set("数值已写入并复读成功，但刷新失败；请核对游戏后重新连接，勿重复设置。")
                    else:
                        self.status.set("已停止操作。请检查游戏后重新连接。")
                if isinstance(error, ConnectionDiagnosticError):
                    show_connection_error(self.root, error)
                else:
                    messagebox.showerror("WorldApartTrainer", str(error), parent=self.root)
            else:
                success(result)
            self.buttons()
        self.root.after(100, self.poll)

    def choose_game_path(self):
        if self.busy or native_calls_pending():
            return
        options = dict(parent=self.root, title="选择游戏安装目录中的 WorldApart.exe",
                       filetypes=(("WorldApart.exe", "WorldApart.exe"), ("可执行文件", "*.exe")))
        if self.selected_game_path:
            options["initialdir"] = str(Path(self.selected_game_path).parent)
        selected = filedialog.askopenfilename(**options)
        if not selected:
            return
        if Path(selected).name.casefold() != "worldapart.exe":
            messagebox.showwarning("请选择游戏文件", "请选择游戏安装目录中的 WorldApart.exe，不要选择修改器。", parent=self.root)
            return
        self.set_game_path(selected)

    def use_auto_path(self):
        self.set_game_path(None)

    def set_game_path(self, path):
        if self.busy or native_calls_pending():
            return
        self.shutdown_adapter()
        self.state = None
        self.selected_game_path = path
        for kind in self.point_values:
            self.point_values[kind].set("—")
            self.point_inputs[kind].set("")
        self.filter_items()
        self.game_location.set("游戏位置：" + str(path) if path else "游戏位置：自动识别正在运行的 WorldApart.exe")
        self.status.set("游戏位置已选择；请先启动这份游戏并进入存档，再点击“连接游戏”。" if path
                        else "已恢复自动识别，点击“连接游戏”。")
        self.buttons()

    def connected(self, state):
        self.game_location.set("已连接：" + str(self.adapter.executable_path))
        readonly = getattr(self.adapter, "write_enabled", True) is False
        compatibility = getattr(self.adapter, "compatibility", None)
        unreviewed = getattr(compatibility, "reviewed_files_match", None) is False
        self.render(state, "当前仅有进程信息，尚未读取到角色或背包。" if readonly else
                    "已连接并读取数值。版本差异仅作提醒，可继续使用；不兼容的功能会提示失败。" if unreviewed else
                    "已连接。输入目标值后点击对应设置按钮。")
        if compatibility is not None and isinstance(compatibility.warnings, tuple) and compatibility.warnings:
            messagebox.showwarning("游戏版本兼容提醒", "\n".join(compatibility.warnings), parent=self.root)

    def connect(self):
        if self.busy or native_calls_pending():
            return
        selected_path = self.selected_game_path
        self.status.set("正在核对游戏版本并查找当前角色；首次连接可能需要片刻……")
        def job():
            if self.adapter:
                self.adapter.close()
                self.adapter = None
            self.adapter = GameAdapter(game_path=selected_path)
            if getattr(self.adapter, "write_enabled", True) is not False:
                self.adapter.native_block_reason = native_connection_block_reason(self.adapter)
            return self.adapter.snapshot()
        # Detach extension state on the UI thread before replacing the adapter.
        for extension in self.extensions:
            extension.disconnect()
        self.work(job, self.connected)

    def refresh(self):
        if self.busy or self.adapter is None or self.state is None:
            return
        self.work(self.adapter.snapshot, lambda state: self.render(state, "数值已刷新；输入框已重置为当前值。"),
                  readonly=True)

    def page_changed(self, _title):
        # Navigation only changes the view. It never reads or mutates the game.
        if hasattr(self, "refresh_button"):
            self.buttons()

    def refresh_active(self):
        if self.busy or self.adapter is None or self.state is None:
            return
        if getattr(self.adapter, "write_enabled", True) is False or not hasattr(self, "navigation"):
            self.refresh()
            return
        action = getattr(self, "_page_refreshers", {}).get(self.navigation.current_title(), self.refresh)
        action()

    def render(self, state, message):
        self.state = state
        for kind in self.point_values:
            target = state.get(kind)
            value = str(target.value) if target is not None else ""
            self.point_values[kind].set(value or "—")
            self.point_inputs[kind].set(value)
        if hasattr(self, "connection_notice"):
            compatibility = getattr(self.adapter, "compatibility", None)
            warnings = getattr(compatibility, "warnings", ())
            notices = list(warnings) if isinstance(warnings, tuple) else []
            reason = getattr(self.adapter, "native_block_reason", "")
            if isinstance(reason, str) and reason:
                notices.append("原生功能暂不可用：" + reason)
            self.connection_notice.set("\n".join(notices))
        self.filter_items()
        self.status.set(message)

    def filter_items(self, _event=None):
        selected = self.items.selection()
        mode = self.inventory_mode.get()
        if mode != self._inventory_mode_shown or self.state is None:
            self.inventory_category.set(ALL_CATEGORIES)
        self._inventory_mode_shown = mode
        all_rows = self.inventory_rows()
        categories = {category_name(row) for row in all_rows.values()}
        category = self.inventory_category.get()
        # Retain an empty selected category after refresh. Switching to another
        # category implicitly could select a different writable item instead.
        if category != ALL_CATEGORIES:
            categories.add(category)
        self.inventory_category_filter.configure(values=[ALL_CATEGORIES, *sorted(categories - {ALL_CATEGORIES})])
        rows = self.current_rows()
        children = self.items.get_children()
        if children:
            self.items.delete(*children)
        for key, row in rows.items():
            self.items.insert("", "end", iid=key,
                              values=(row["name"], category_name(row), row["target"].value, row["target"].maximum))
        if selected and selected[0] in rows:
            self.items.selection_set(selected[0])
        elif len(rows) == 1:
            self.items.selection_set(next(iter(rows)))
        diagnostics = (self.state or {}).get("diagnostics", [])
        skipped = sum(d.get("reason") != "null_entry" for d in diagnostics)
        note = f"显示 {len(rows)} / {len(all_rows)} 项" + (f"；{skipped} 项暂不开放数量修改" if skipped else "")
        if mode == "货币余额":
            messages = list(dict.fromkeys(d["message"] for d in diagnostics
                if d.get("reason") in ("currency_balance_above_limit", "currency_multiple_stacks",
                                       "currency_balance_unverified")
                and isinstance(d.get("message"), str)))
            if messages:
                note += "\n货币提示：" + "\n".join(messages[:3])
                if len(messages) > 3:
                    note += f"\n另有 {len(messages) - 3} 项货币限制提示。"
        self.inventory_note.set(note)
        self.select_item()

    def change(self, kind):
        if self.busy or self.adapter is None or self.state is None:
            return
        if getattr(self.adapter, "write_enabled", True) is False:
            self.status.set("当前为兼容信息连接，游戏字段尚未核验，不能修改数值。")
            return
        if native_calls_pending():
            self.status.set("原生操作仍未安全结束，请先核对游戏，暂不能执行其他修改。")
            self.buttons()
            return
        if kind in ("spirit", "path"):
            if kind not in self.state:
                return
            shown = self.state[kind]
            label = "剩余灵根点" if kind == "spirit" else "剩余道途点"
            text = self.point_inputs[kind].get()
        elif kind == "item":
            row = self.selected_item()
            if row is None:
                return
            shown, label = row["target"], row["name"]
            text = self.item_input.get()
        else:
            return
        try:
            new_value = parse_value(text)
            validate_value(shown, new_value)
        except Refused as error:
            # An input mistake is not a stale connection or an attempted write.
            messagebox.showwarning("检查目标数值", str(error), parent=self.root)
            return
        adapter = self.adapter
        message = f"{label}：{shown.value} → {new_value}。已写入并复读确认；重新打开游戏面板查看。"
        def job():
            adapter.set_value(shown, new_value)
            try:
                return adapter.snapshot()
            except Exception as error:
                raise RefreshAfterWriteError(
                    f"{label}：{shown.value} → {new_value}。\n"
                    "写入和复读已成功，但刷新列表失败。请核对游戏后重新连接，勿重复设置。\n"
                    f"刷新失败原因：{error}"
                ) from error
        self.work(job, lambda state: self.render(state, message))

    def close(self):
        if self.busy:
            return
        from acquisition_adapter import native_calls_pending
        if native_calls_pending():
            messagebox.showwarning("等待游戏操作结束", "游戏内的物品操作尚未返回。请保持修改器打开，先核对游戏状态。", parent=self.root)
            return
        self.shutdown_adapter()
        self.root.destroy()


if __name__ == "__main__":
    App(tk.Tk()).root.mainloop()
