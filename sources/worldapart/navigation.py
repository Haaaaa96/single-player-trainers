"""Expandable sidebar navigation around the existing Notebook panel API."""
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass(frozen=True)
class PageRoute:
    group: str
    label: str
    description: str


GROUPS = ("角色", "背包与资源", "游戏辅助", "生活技艺", "其他功能")
PAGE_ORDER = ("角色点数", "人物属性", "资质与技艺", "修行储备", "增加寿元", "背包数量", "添加物品与秘籍",
              "当前资源", "当前精力", "功法学习小游戏", "疏经导脉辅助", "游戏速度", "留影石", "秒说服",
              "炼丹辅助", "丹方探索", "炼器辅助", "双修", "刮玉")
ROUTES = {
    "角色点数": PageRoute("角色", "角色点数", "修改剩余可分配灵根点和道途点；不会直接解锁节点。"),
    "人物属性": PageRoute("角色", "人物属性", "输入永久成长加成；人物面板最终值还包含基础、装备与其他效果。"),
    "资质与技艺": PageRoute("角色", "资质与技艺", "输入累计经验，由游戏换算等级；允许范围随当前境界变化。"),
    "修行储备": PageRoute("角色", "修行储备", "分别设置当前角色数值；丹田灵气是储备，不直接提升修为或突破境界。"),
    "增加寿元": PageRoute("角色", "增加寿元", "输入本次增加年数；不会改变年龄，不提供减寿或复活。"),
    "背包数量": PageRoute("背包与资源", "背包数量", "输入已有堆叠的目标数量；切换货币或分类后重新选择物品。"),
    "添加物品与秘籍": PageRoute("背包与资源", "物品获取", "输入本次新增数量；可获取角色当前没有的物品。"),
    "当前资源": PageRoute("背包与资源", "当前资源", "修改当前可用资源；资源上限的永久成长加成在“人物属性”页。"),
    "当前精力": PageRoute("背包与资源", "当前资源", "修改当前可用精力；精力上限的永久成长加成在“人物属性”页。"),
    "功法学习小游戏": PageRoute("游戏辅助", "功法学习", "作用于当前学习局；达到领悟目标后仍由游戏判定与结算。"),
    "疏经导脉辅助": PageRoute("游戏辅助", "疏经导脉", "一键疏通保持本局运行；手动设置资源须停在退出确认暂停中。"),
    "游戏速度": PageRoute("游戏辅助", "游戏速度", "设置0.5～2倍基础速度；游戏暂停和慢动作优先，需要恢复时选择1.0。"),
    "留影石": PageRoute("游戏辅助", "留影石", "查看各角色留影完成记录、激活下一段，或预览后强制重玩指定阶段。"),
    "秒说服": PageRoute("游戏辅助", "秒说服", "立即判定当前说服成功，保留游戏原有的倒计时与奖励结算。"),
    "炼丹辅助": PageRoute("生活技艺", "炼丹辅助", "完成当前火候小游戏至最高品质，或修改炼丹天赋等级。"),
    "丹方探索": PageRoute("生活技艺", "丹方探索", "从当前地图已显示的候选中自动取得本局第一张丹方。"),
    "炼器辅助": PageRoute("生活技艺", "炼器辅助", "完成当前炼器至最高品质和词条能量门槛，或修改炼器天赋点。"),
    "双修": PageRoute("生活技艺", "双修", "完成当前双修小游戏；正常消耗和结算由游戏处理。"),
    "刮玉": PageRoute("生活技艺", "刮玉", "完整揭示当前原石，保留天然玉花与裂纹，不自动兑换。"),
}


def route_for(title):
    return ROUTES.get(title, PageRoute("其他功能", title, "先读取当前数据，再按页面说明操作。"))


def connection_label(connected, readonly, busy, pending):
    if busy:
        return "操作进行中" if connected else "正在连接"
    if not connected:
        return "尚未连接"
    if readonly:
        return "只读 · 兼容信息"
    return "已连接 · 等待原生结果" if pending else "已连接"


class ScrollPage(ttk.Frame):
    """Keep whole pages reachable at the minimum window size and larger fonts."""
    def __init__(self, notebook, content):
        super().__init__(notebook)
        self.content = content
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                background=ttk.Style().lookup("TFrame", "background") or "#f0f0f0")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.vertical.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self._scroll_state)
        # Tk allows a canvas window whose parent is an ancestor of the canvas;
        # existing panels remain children of app.tabs without being rewritten.
        self.window = self.canvas.create_window(0, 0, window=content, anchor="nw")
        self._layout_pending = False
        self._wrap_limits = {}
        self.canvas.bind("<Configure>", self._schedule)
        self.bind("<Map>", self._mapped, add="+")
        content.bind("<Configure>", self._schedule, add="+")
        self.canvas.bind("<MouseWheel>", self._wheel)
        content.bind("<MouseWheel>", self._wheel, add="+")

    def _mapped(self, _event=None):
        # The window item's parent is the Notebook, so it is a sibling of
        # this page. Notebook selection raises the page above that sibling.
        # Raise the content only after the selected page has been mapped.
        self.content.lift()
        self._schedule()

    def _scroll_state(self, first, last):
        self.vertical.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.vertical.grid_remove()
        else:
            self.vertical.grid()

    def _schedule(self, _event=None):
        if not self._layout_pending:
            self._layout_pending = True
            self.after_idle(self._layout)

    def _layout(self):
        self._layout_pending = False
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        self.canvas.itemconfigure(self.window, width=width)
        self._fit_labels(self.content, width)
        desired = max(height, self.content.winfo_reqheight())
        self.canvas.itemconfigure(self.window, height=desired)
        self.canvas.configure(scrollregion=(0, 0, width, desired))

    def _fit_labels(self, parent, page_width):
        for child in parent.winfo_children():
            if isinstance(child, ttk.Label):
                original = self._wrap_limits.setdefault(str(child), int(float(child.cget("wraplength") or 0)))
                if original > 0:
                    parent_width = parent.winfo_width()
                    limit = min(original, max(80, min(page_width, parent_width if parent_width > 1 else page_width)-24))
                    if int(float(child.cget("wraplength") or 0)) != limit:
                        child.configure(wraplength=limit)
                # Background labels should scroll their page, while tables and
                # input controls keep their native wheel behavior.
                if not getattr(child, "_page_wheel_bound", False):
                    child.bind("<MouseWheel>", self._wheel, add="+")
                    child._page_wheel_bound = True
            self._fit_labels(child, page_width)

    def _wheel(self, event):
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
        return None


class PageNotebook(ttk.Notebook):
    """Notebook-compatible registration with hidden headers and scroll pages."""
    def __init__(self, parent, on_add):
        style = ttk.Style(parent)
        style.layout("Sidebar.TNotebook.Tab", [])
        style.configure("Sidebar.TNotebook", borderwidth=0)
        super().__init__(parent, style="Sidebar.TNotebook")
        self._pages = {}
        self._on_add = on_add
        self.bind("<<NotebookTabChanged>>", self._raise_selected, add="+")

    def _raise_selected(self, _event=None):
        selected = super().select()
        if selected:
            page = self.nametowidget(selected)
            page.content.lift()
            page._schedule()

    def add(self, child, **kwargs):
        if str(child) not in self._pages:
            page = ScrollPage(self, child)
            self._pages[str(child)] = page
            super().add(page, **kwargs)
            self._on_add(str(page), kwargs.get("text", "功能"))
        else:
            super().add(self._pages[str(child)], **kwargs)

    def select(self, tab_id=None):
        result = super().select(self._pages.get(str(tab_id), tab_id) if tab_id is not None else None)
        if tab_id is not None:
            self._raise_selected()
        return result

    def tab(self, tab_id, option=None, **kwargs):
        return super().tab(self._pages.get(str(tab_id), tab_id), option, **kwargs)


class SidebarNavigation(ttk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        self._titles = {}
        self._groups = {}
        self._syncing = False
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(self, padding=(0, 8, 8, 0), width=152)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(1, weight=1)
        ttk.Label(sidebar, text="功能导航", font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=0, sticky="w", padx=9, pady=(0, 10))
        self.tree = ttk.Treeview(sidebar, show="tree", selectmode="browse", height=13)
        self.tree.column("#0", width=126, minwidth=108, stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.tree.tag_configure("group", foreground="#6a727d")
        content = ttk.Frame(self, padding=(8, 0, 0, 0))
        content.grid(row=0, column=1, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self.description = tk.StringVar()
        hint = ttk.Label(content, textvariable=self.description, wraplength=620, foreground="#566170")
        hint.grid(row=0, column=0, sticky="ew", padx=12, pady=(3, 9))
        hint.bind("<Configure>", lambda event:hint.configure(wraplength=max(100,event.width)))
        self.notebook = PageNotebook(content, self.register)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._chosen)
        self.notebook.bind("<<NotebookTabChanged>>", self._page_changed, add="+")

    def register(self, page, title):
        route = route_for(title)
        self._titles[page] = title
        if route.group not in self._groups:
            group = "group:"+route.group
            self._groups[route.group] = group
            self.tree.insert("", "end", iid=group, text=route.group, open=True, tags=("group",))
            for index, name in enumerate(group for group in GROUPS if group in self._groups):
                self.tree.move(self._groups[name], "", index)
        self.tree.insert(self._groups[route.group], "end", iid=page, text=route.label)
        parent = self._groups[route.group]
        children = self.tree.get_children(parent)
        ranked = sorted(children, key=lambda key: PAGE_ORDER.index(self._titles[key])
                        if self._titles[key] in PAGE_ORDER else len(PAGE_ORDER))
        for index, key in enumerate(ranked):
            self.tree.move(key, parent, index)

    def current_title(self):
        return self._titles.get(self.notebook.select(), "")

    def _chosen(self, _event=None):
        if self._syncing:
            return
        selected = self.tree.selection()
        if selected and selected[0] in self._titles:
            self.notebook.select(selected[0])
        elif selected:
            children = self.tree.get_children(selected[0])
            if children:
                self.notebook.select(children[0])
            self._page_changed()

    def _page_changed(self, _event=None):
        page = self.notebook.select()
        if page not in self._titles:
            return
        self._syncing = True
        try:
            self.tree.selection_set(page)
            self.tree.see(page)
            self.description.set(route_for(self._titles[page]).description)
        finally:
            self._syncing = False
        if self.on_change is not None:
            self.on_change(self._titles[page])
