"""Read-only collection view and explicit, single-stage photostone actions."""
import tkinter as tk
from tkinter import ttk

from acquisition_adapter import native_calls_pending
from write_guard import Refused, UncertainWrite


class PhotostonePanel:
    title = "留影石"

    def __init__(self, app):
        self.app, self.adapter, self.state = app, None, None
        self.rows, self.preview = {}, None
        self._epoch = 0
        self._force_dialog = None
        self._force_dialog_confirm = self._force_dialog_button = None
        frame = ttk.Frame(app.tabs, padding=16)
        app.tabs.add(frame, text=self.title)
        heading = ttk.Frame(frame)
        heading.pack(fill="x")
        ttk.Label(heading, text="留影完成清单", font=("Microsoft YaHei UI", 15, "bold")).pack(side="left")
        self.detect_button = ttk.Button(heading, text="读取 / 刷新清单", command=self.detect)
        self.detect_button.pack(side="right")
        self.summary = tk.StringVar(value="连接游戏后读取各角色的留影阶段。")
        ttk.Label(frame, textvariable=self.summary, wraplength=570).pack(fill="x", pady=(12, 8))
        filters = ttk.Frame(frame)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="角色名称 / 编号").pack(side="left")
        self.query = tk.StringVar()
        self.search = ttk.Entry(filters, textvariable=self.query, width=19)
        self.search.pack(side="left", padx=8)
        self.mode = tk.StringVar(value="全部阶段")
        self.filter = ttk.Combobox(filters, textvariable=self.mode, state="readonly", width=16,
                                  values=("全部阶段", "仅未完成", "当前可激活", "已完成"))
        self.filter.pack(side="right")
        self.query.trace_add("write", self.filter_rows)
        self.filter.bind("<<ComboboxSelected>>", self.filter_rows)
        # Keep actions above the expanding list so they remain reachable at
        # normal window sizes. All destructive confirmation lives in a dialog.
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 8))
        self.activate_button = ttk.Button(actions, text="激活下一段未完成留影", command=self.activate)
        self.activate_button.pack(side="left")
        self.preview_button = ttk.Button(actions, text="强制开启 / 重玩…", command=self.preview_force)
        self.preview_button.pack(side="right")
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("name", "stage", "completion", "location", "status"),
                                 show="headings", selectmode="browse", height=8)
        for name, label, width in (("name", "角色", 95), ("stage", "阶段", 60),
                                    ("completion", "成功次数", 70), ("location", "当前场景", 130),
                                    ("status", "当前状态", 170)):
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, minwidth=60, stretch=name in ("name", "status"))
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.tree.bind("<Button-1>", self.block_busy)
        self.tree.bind("<KeyPress>", self.block_busy)
        self.detail = tk.StringVar(value="请选择一个角色的具体阶段。")
        ttk.Label(frame, textvariable=self.detail, wraplength=570).pack(fill="x", pady=(10, 6))
        self.force_note = tk.StringVar(value="强制重玩会清除所选阶段的完成记录；普通激活会保留记录。")
        ttk.Label(frame, textvariable=self.force_note, wraplength=570, foreground="#81530e").pack(fill="x", pady=(10, 5))
        self.confirmed = tk.BooleanVar(value=False)
        self.note = tk.StringVar(value="读取清单不会激活互动。任务专用、废弃或无法核实的阶段会单独提示。")
        ttk.Label(frame, textvariable=self.note, wraplength=570).pack(fill="x", pady=(10, 0))
        ttk.Label(frame, text="清单可在人物互动时读取；激活或强制重玩前，请先退出人物互动，回到稳定普通场景。\n"
                  "激活后再与对应角色互动；正常精力消耗和结算保持。\n"
                  "强制重玩后失败或退出，原完成记录不会自动恢复；再次成功可能再得奖励。",
                  wraplength=570).pack(fill="x", pady=(8, 0))
        self.update_enabled(False)

    def available(self):
        game = self.app.adapter
        return bool(game is not None and getattr(game, "write_enabled", True) is True
                    and not self.app.busy and not native_calls_pending()
                    and not getattr(game, "blocked", False)
                    and not (self.adapter and self.adapter.blocked))

    def block_busy(self, _event=None):
        return "break" if self.app.busy else None

    def selected_row(self):
        keys = self.tree.selection()
        return self.rows.get(keys[0]) if self.state and keys else None

    def selected_target(self):
        row = self.selected_row()
        return (row.get("npc_id"), row.get("sub_id")) if row else None

    def current_request(self, epoch, game, adapter):
        return self._epoch == epoch and self.app.adapter is game and self.adapter is adapter

    def clear_preview(self):
        self.close_force_dialog()
        self.preview = None
        self.confirmed.set(False)
        self.force_note.set("强制重玩会清除所选阶段的完成记录；普通激活会保留记录。")

    def close_force_dialog(self):
        window, self._force_dialog = self._force_dialog, None
        self._force_dialog_confirm = self._force_dialog_button = None
        if window is not None:
            window.destroy()

    def show_force_preview(self, preview):
        from tkinter.scrolledtext import ScrolledText
        self.close_force_dialog()
        self.confirmed.set(False)
        window = self._force_dialog = tk.Toplevel(self.app.root)
        window.title("留影石 · 强制重玩影响")
        window.transient(self.app.root)
        window.geometry(f"680x440+{max(0, self.app.root.winfo_rootx() + 40)}+{max(0, self.app.root.winfo_rooty() + 40)}")
        window.minsize(550, 360)
        ttk.Label(window, text="请核对角色、阶段及记录重置影响",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=18, pady=(16, 10))
        content = ScrolledText(window, wrap="word", font=("Microsoft YaHei UI", 10),
                              padx=10, pady=10, height=10)
        content.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        content.insert("1.0", preview["message"])
        content.configure(state="disabled")
        self._force_dialog_confirm = ttk.Checkbutton(window,
            text="我已查看以上影响，允许重置这一阶段", variable=self.confirmed,
            command=lambda: self.update_enabled(True))
        self._force_dialog_confirm.pack(anchor="w", padx=18, pady=(0, 12))
        actions = ttk.Frame(window)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        def cancel():
            self.close_force_dialog()
            self.confirmed.set(False)
            self.update_enabled(True)
        ttk.Button(actions, text="取消", command=cancel).pack(side="left")
        self._force_dialog_button = ttk.Button(actions, text="强制开启所选阶段", command=self.force)
        self._force_dialog_button.pack(side="right")
        window.protocol("WM_DELETE_WINDOW", cancel)
        self.update_enabled(True)
        window.grab_set()
        window.lift()
        window.focus_set()

    def preview_matches(self, row):
        target = self.preview.get("row") if isinstance(self.preview, dict) else None
        return bool(row and isinstance(target, dict) and row.get("identity")
                    and all(row.get(key) == target.get(key) for key in ("identity", "npc_id", "sub_id")))

    def update_enabled(self, enabled):
        available = bool(enabled and self.available())
        row = self.selected_row()
        self.detect_button.configure(state="normal" if available else "disabled")
        self.search.configure(state="normal" if available else "disabled")
        self.filter.configure(state="readonly" if available else "disabled")
        self.tree.state(["!disabled"] if available else ["disabled"])
        self.activate_button.configure(state="normal" if available and row and row.get("can_activate") else "disabled")
        # A blocked row can still explain its reason. The actual action remains
        # independently guarded here, by force(), and by the fresh backend read.
        self.preview_button.configure(state="normal" if available and row else "disabled")
        ready = bool(available and row and self.preview_matches(row) and row.get("can_force"))
        if self._force_dialog is not None:
            self._force_dialog_confirm.configure(state="normal" if ready else "disabled")
            self._force_dialog_button.configure(state="normal" if ready and self.confirmed.get() else "disabled")

    def disconnect(self):
        self._epoch += 1
        if self.adapter is not None:
            self.adapter.close()
        self.adapter, self.state, self.rows = None, None, {}
        self.clear_preview()
        self.tree.delete(*self.tree.get_children())
        self.summary.set("连接游戏后读取各角色的留影阶段。")
        self.detail.set("请选择一个角色的具体阶段。")
        self.note.set("先连接游戏，再读取清单。")
        self.update_enabled(False)

    def detect(self):
        if not self.available():
            return
        game = self.app.adapter
        target, original_adapter = self.selected_target(), self.adapter
        self._epoch += 1
        epoch = self._epoch
        self.state = None
        self.clear_preview()
        self.update_enabled(False)
        def job():
            if not self.current_request(epoch, game, original_adapter):
                return None
            if self.adapter is None:
                from photostone_adapter import PhotostoneAdapter
                adapter = PhotostoneAdapter(game)
                if not self.current_request(epoch, game, original_adapter):
                    adapter.close()
                    return None
                self.adapter = adapter
            adapter = self.adapter
            return adapter, adapter.snapshot()
        def success(result):
            if result is not None:
                adapter, state = result
                if self.current_request(epoch, game, adapter):
                    self.render(state, selected_target=target)
        self.app.work(job, success, readonly=True)

    def render(self, state, selected_target=None):
        self.state = state
        self.summary.set(state.get("summary") or "已读取留影阶段；完成状态和当前可用状态分别显示。")
        self.note.set("激活或强制开启成功后自动刷新；换存档或在游戏内完成一段后，请手动刷新。")
        self.filter_rows(selected_target=selected_target)

    def filter_rows(self, *_args, selected_target=None):
        if self.app.busy:
            return
        target = selected_target if selected_target is not None else self.selected_target()
        self.clear_preview()
        self.rows = {}
        self.tree.delete(*self.tree.get_children())
        query, mode = self.query.get().strip().casefold(), self.mode.get()
        for index, row in enumerate((self.state or {}).get("rows", [])):
            name = row.get("name") or str(row.get("npc_id", ""))
            if query and query not in (str(name) + " " + str(row.get("npc_id", ""))).casefold():
                continue
            count = row.get("success_count")
            maximum = row.get("max_success", 1)
            complete = isinstance(count, int) and count >= maximum
            if mode == "仅未完成" and (count is None or complete):
                continue
            if mode == "已完成" and not complete:
                continue
            if mode == "当前可激活" and not row.get("can_activate"):
                continue
            key = str(index)
            self.rows[key] = row
            stage = row.get("stage", row.get("sub_id", ""))
            stage_label = {1: "普通", 2: "精品", 3: "珍贵"}.get(stage, str(stage))
            self.tree.insert("", "end", iid=key, values=(name, stage_label,
                f"{count} / {maximum}" if count is not None else "无法判定",
                row.get("location_label", "位置未知"), row.get("status", "")))
            if target == (row.get("npc_id"), row.get("sub_id")):
                self.tree.selection_set(key)
                self.tree.focus(key)
                self.tree.see(key)
        self.selected()

    def selected(self, _event=None):
        self.clear_preview()
        row = self.selected_row()
        detail = row.get("reason") or "当前阶段可以按下方按钮操作。" if row else "请选择一个角色的具体阶段。"
        if row:
            if not row.get("can_force") and row.get("force_reason"):
                detail += "\n强制开启不可用：" + row["force_reason"]
            detail += "\n所在场景：" + row.get("location_label", "位置未知")
            if row.get("location_reason"):
                detail += "；" + row["location_reason"]
        self.detail.set(detail)
        self.update_enabled(True)

    def preview_force(self):
        row = self.selected_row()
        if not self.available() or not self.adapter or not row:
            return
        self.clear_preview()
        if not row.get("can_force"):
            reason = row.get("force_reason") or "当前阶段未通过操作条件核验，请刷新清单。"
            self.show_force_preview(dict(row=row, message=(
                f"{row.get('name', row.get('npc_id'))} · 第 {row.get('stage')} 段\n\n"
                f"当前无法强制开启：{reason}\n\n"
                "处理上述条件后，请关闭此窗口并刷新清单。未修改任何记录。")))
            return
        adapter = self.adapter
        game, epoch = self.app.adapter, self._epoch
        def success(preview):
            if not self.current_request(epoch, game, adapter) or self.selected_row() is not row:
                return
            self.preview = preview
            self.show_force_preview(preview)
            self.update_enabled(True)
        self.app.work(lambda: adapter.preview_force(row), success, readonly=True)

    def activate(self):
        row = self.selected_row()
        if self.available() and self.adapter and row and row.get("can_activate"):
            adapter = self.adapter
            self.execute(lambda: adapter.activate_next(row))

    def force(self):
        row = self.selected_row()
        if (self.available() and self.adapter and row and row.get("can_force")
                and self.preview_matches(row) and self.confirmed.get()):
            adapter, preview = self.adapter, self.preview
            self.execute(lambda: adapter.force(preview, confirmed=True))

    def execute(self, operation):
        target = self.selected_target()
        game, adapter = self.app.adapter, self.adapter
        self._epoch += 1
        epoch = self._epoch
        self.state, self.rows = None, {}
        self.tree.delete(*self.tree.get_children())
        self.summary.set("正在执行并核对留影状态…")
        self.detail.set("等待本次操作完成。")
        self.clear_preview()
        self.update_enabled(False)
        def job():
            if not self.current_request(epoch, game, adapter):
                return None
            try:
                result = operation()
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(message=str(error), not_called=True)
            # Native verification and its durable record have already finished.
            # A later display read must never turn that success into a retry.
            if result.get("verified") is True and not result.get("not_called"):
                if not self.current_request(epoch, game, adapter):
                    return result
                try:
                    return dict(result, refreshed_state=adapter.snapshot())
                except Exception as error:
                    return dict(result, refresh_error=str(error))
            return result
        def success(result):
            if result is None or not self.current_request(epoch, game, adapter):
                return
            if "refreshed_state" in result:
                self.render(result["refreshed_state"], selected_target=target)
                suffix = " 清单已自动刷新。"
                if target is not None and self.selected_row() is None:
                    suffix += " 原选择不在当前筛选结果中；已保留筛选，请按需调整。"
            elif "refresh_error" in result:
                self.state, self.rows = None, {}
                self.tree.delete(*self.tree.get_children())
                self.detail.set("请手动刷新清单后再选择阶段。")
                self.summary.set("操作已完成；清单待刷新。")
                suffix = " 自动刷新失败：" + result["refresh_error"] + "。请手动刷新清单，不要重复激活。"
            else:
                self.summary.set("本次未调用游戏；请刷新清单。" if result.get("not_called")
                                 else "请刷新清单确认当前状态。")
                self.detail.set("请手动刷新清单后再选择阶段。")
                suffix = " 请刷新清单后再操作。"
            self.note.set(result["message"] + suffix)
            self.app.status.set(result["message"])
            self.update_enabled(True)
        self.app.work(job, success)
