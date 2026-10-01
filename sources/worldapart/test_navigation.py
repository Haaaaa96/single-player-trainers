"""Sidebar routing and offline Tk layout tests; never connect to a game."""
import tkinter as tk
import unittest
from unittest.mock import Mock

from navigation import SidebarNavigation, route_for, connection_label
from test_app import FakeVar


class NavTree:
    def __init__(self):
        self.rows, self.children, self.selected = {}, {"":[]}, ()
        self.seen = None
    def insert(self,parent,index,iid,**options):
        self.rows[iid] = dict(options,parent=parent)
        self.children.setdefault(parent,[]).append(iid)
        self.children[iid] = []
    def move(self,key,parent,index):
        previous = self.rows[key]["parent"]
        self.children[previous].remove(key)
        self.children[parent].insert(index,key)
        self.rows[key]["parent"] = parent
    def get_children(self,parent=""):return tuple(self.children[parent])
    def selection(self):return self.selected
    def selection_set(self,key):self.selected = (key,)
    def see(self,key):self.seen = key


class NavNotebook:
    def __init__(self):self.current = ""
    def select(self,page=None):
        if page is not None:self.current = page
        return self.current


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.nav = SidebarNavigation.__new__(SidebarNavigation)
        self.nav._titles,self.nav._groups,self.nav._syncing = {},{},False
        self.nav.tree,self.nav.notebook = NavTree(),NavNotebook()
        self.nav.description,self.nav.on_change = FakeVar(),Mock()

    def test_all_existing_pages_and_split_inventory_are_registered_in_groups(self):
        titles = ["角色点数","背包数量","人物属性","资质与技艺","修行储备","增加寿元","当前资源",
                  "添加物品与秘籍","功法学习小游戏","疏经导脉辅助","游戏速度"]
        for index,title in enumerate(titles):self.nav.register(str(index),title)
        self.assertEqual(len(self.nav._titles),11)
        self.assertEqual(self.nav.tree.get_children(),("group:角色","group:背包与资源","group:游戏辅助"))
        self.assertEqual([self.nav._titles[k] for k in self.nav.tree.get_children("group:角色")],
                         ["角色点数","人物属性","资质与技艺","修行储备","增加寿元"])
        self.assertEqual([self.nav._titles[k] for k in self.nav.tree.get_children("group:背包与资源")],
                         ["背包数量","添加物品与秘籍","当前资源"])
        self.assertEqual([self.nav._titles[k] for k in self.nav.tree.get_children("group:游戏辅助")],
                         ["功法学习小游戏","疏经导脉辅助","游戏速度"])

    def test_unknown_future_panel_is_still_accessible(self):
        self.nav.register("future","新功能")
        self.assertEqual(self.nav.tree.rows["future"]["text"],"新功能")
        self.assertEqual(self.nav.tree.rows["future"]["parent"],"group:其他功能")
        self.nav.tree.selection_set("future")
        self.nav._chosen()
        self.assertEqual(self.nav.current_title(),"新功能")

    def test_page_selection_updates_notebook_and_editing_meaning(self):
        self.nav.register("growth","人物属性")
        self.nav.tree.selection_set("growth")
        self.nav._chosen()
        self.nav._page_changed()
        self.assertEqual(self.nav.notebook.current,"growth")
        self.assertIn("永久成长",self.nav.description.get())
        self.assertIn("最终值",self.nav.description.get())
        self.nav.on_change.assert_called_once_with("人物属性")

    def test_clicking_group_selects_first_page_even_when_already_active(self):
        self.nav.register("points","角色点数")
        self.nav.notebook.select("points")
        self.nav.tree.selection_set("group:角色")
        self.nav._chosen()
        self.assertEqual(self.nav.tree.selection(),("points",))
        self.assertEqual(self.nav.tree.seen,"points")

    def test_external_notebook_selection_syncs_sidebar_without_recursive_selection(self):
        self.nav.register("bag","背包数量")
        self.nav.notebook.select("bag")
        self.nav._page_changed()
        self.assertEqual(self.nav.tree.selection(),("bag",))
        self.assertIn("目标数量",self.nav.description.get())
        self.nav._syncing = True
        self.nav.tree.selection_set("group:背包与资源")
        self.nav._chosen()
        self.assertEqual(self.nav.notebook.select(),"bag")

    def test_resources_alias_keeps_old_panel_compatible(self):
        self.assertEqual(route_for("当前精力").group,route_for("当前资源").group)
        self.assertEqual(route_for("当前精力").label,"当前资源")

    def test_connection_status_separates_readonly_pending_and_disconnected(self):
        self.assertEqual(connection_label(False,False,False,False),"尚未连接")
        self.assertEqual(connection_label(False,False,True,False),"正在连接")
        self.assertEqual(connection_label(True,True,False,False),"只读 · 兼容信息")
        self.assertEqual(connection_label(True,False,False,True),"已连接 · 等待原生结果")
        self.assertEqual(connection_label(True,False,True,False),"操作进行中")


class LiveTkLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import App
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display unavailable: {exc}")
        cls.root.withdraw()
        cls.root.overrideredirect(True)
        cls.app = App(cls.root)
        cls.root.geometry("940x800+30000+30000")
        cls.root.deiconify()
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def settle(self, tab, width=940, height=800):
        self.root.geometry(f"{width}x{height}+30000+30000")
        self.app.tabs.select(tab)
        self.root.update()
        page = self.root.nametowidget(tab)
        page.canvas.yview_moveto(0)
        self.root.update()
        return page

    def hit(self, widget):
        return self.root.winfo_containing(widget.winfo_rootx()+widget.winfo_width()//2,
                                         widget.winfo_rooty()+widget.winfo_height()//2)

    def test_selected_content_is_not_covered_after_repeated_page_switches(self):
        from standalone_selftest import iter_page_buttons
        tabs = self.app.tabs.tabs()
        for tab in (*tabs, *reversed(tabs), tabs[0]):
            page = self.settle(tab)
            with self.subTest(page=self.app.tabs.tab(tab, "text")):
                self.assertTrue(page.content.winfo_ismapped())
                for other in tabs:
                    if other != tab:
                        self.assertFalse(self.root.nametowidget(other).content.winfo_ismapped())
                # Some pages' last-created actions are below the viewport.
                # Verify the topmost action, whose whole bounds are visible.
                button = min(iter_page_buttons(page), key=lambda b:b.winfo_rooty())
                self.assertIs(self.hit(button), button)

    def test_all_pages_keep_actions_inside_content_at_both_sizes(self):
        from standalone_selftest import iter_page_buttons, validate_button_geometry
        for width,height in ((940,800),(860,730)):
            for tab in self.app.tabs.tabs():
                page = self.settle(tab,width,height)
                content = page.content
                for button in iter_page_buttons(page):
                    with self.subTest(size=(width,height),page=self.app.tabs.tab(tab,"text"),button=button.cget("text")):
                        self.assertTrue(validate_button_geometry([
                            button.winfo_rootx()-content.winfo_rootx(),
                            button.winfo_rooty()-content.winfo_rooty(),
                            button.winfo_width(),button.winfo_height()],
                            [content.winfo_width(),content.winfo_height()],str(button.cget("text"))))
                self.assertIsNone(self.app.adapter)

    def test_scrolling_never_covers_footer_and_bottom_actions_remain_reachable(self):
        from standalone_selftest import iter_page_buttons
        for tab in self.app.tabs.tabs():
            page = self.settle(tab,860,730)
            for fraction in (0,1,0):
                page.canvas.yview_moveto(fraction)
                self.root.update()
                with self.subTest(page=self.app.tabs.tab(tab,"text"),scroll=fraction):
                    self.assertIs(self.hit(self.app.refresh_button),self.app.refresh_button)
                    self.assertIs(self.hit(self.app.connect_button),self.app.connect_button)
                    if fraction == 1:
                        bottom = max(iter_page_buttons(page),key=lambda b:b.winfo_rooty())
                        self.assertIs(self.hit(bottom),bottom)


if __name__ == "__main__":unittest.main()
