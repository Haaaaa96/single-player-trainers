"""Catalogue filtering and add input cannot route an unavailable or hidden row."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from acquisition_ui import AcquisitionPanel, add_quantity, filtered_rows, item_detail
from write_guard import Refused, Target, UncertainWrite


def stone_row(**changes):
    return dict(dict(id=50000, name="灵石", type_name="货币", stack_limit=999_999_999,
                     max_quantity=100_000_000, balance_maximum=999_999_999,
                     can_add=True, large_currency=True), **changes)


def currency_state(balance):
    return dict(currencies={"currency:1": dict(item_id=50000,
        target=Target("currency:1", 0x1000, balance, ("player",), 0, 999_999_999,
                      max_change=100_000_000))}, diagnostics=[])


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            dict(id=10,name="回春散",type_name="丹药",stack_limit=999,max_quantity=999,can_add=True),
            dict(id=20,name="青瓷素盏",type_name="文玩",stack_limit=99,max_quantity=999,can_add=True),
            dict(id=30,name="剧情标记",type_name="虚拟",stack_limit=1,max_quantity=0,can_add=False,reason="不能添加剧情标记"),
        ]

    def test_name_id_type_search_and_category_combine(self):
        self.assertEqual(filtered_rows(self.rows,"回春 丹药","全部分类",True),self.rows[:1])
        self.assertEqual(filtered_rows(self.rows,"20","文玩",True),self.rows[1:2])
        self.assertEqual(filtered_rows(self.rows,"20","丹药",True),[])

    def test_unavailable_rows_can_be_inspected_but_not_added(self):
        self.assertEqual(len(filtered_rows(self.rows,"","全部分类",False)),3)
        self.assertEqual(len(filtered_rows(self.rows,"","全部分类",True)),2)
        with self.assertRaisesRegex(Refused,"剧情"):
            add_quantity(self.rows[2],"1")

    def test_positive_integer_quantity_is_added_not_treated_as_target(self):
        self.assertEqual(add_quantity(self.rows[0],"999"),999)
        # Native creation may split 999 into several stacks of 99.
        self.assertEqual(add_quantity(self.rows[1],"999"),999)
        for value in ("0","1000","1.2","-1","1e2",""):
            with self.subTest(value=value),self.assertRaises(Refused):
                add_quantity(self.rows[0],value)

    def test_currency_description_distinguishes_cached_balance_delta_and_total(self):
        text = item_detail(stone_row(), currency_state(950_000_000))
        self.assertIn("单次最多添加 100,000,000", text)
        self.assertIn("总余额上限 999,999,999", text)
        self.assertIn("上次读取余额 950,000,000", text)
        self.assertIn("本次最多可加 49,999,999", text)
        self.assertIn("重新核验", text)

    def test_unknown_invalid_or_split_balance_is_never_displayed_as_zero(self):
        split = currency_state(17_100)
        split["currencies"]["currency:2"] = split["currencies"]["currency:1"]
        unsupported = currency_state(17_100)
        unsupported["diagnostics"] = [dict(item_id=50000, reason="unsupported")]
        for state in (None, {}, dict(currencies={}), split, unsupported,
                      currency_state(-1), currency_state(1_000_000_000)):
            with self.subTest(state=state):
                text = item_detail(stone_row(), state)
                self.assertIn("当前余额尚未核验", text)
                self.assertNotIn("上次读取余额", text)

    def test_currency_detail_honors_lower_config_and_full_balance(self):
        row = stone_row(stack_limit=50_000_000, max_quantity=50_000_000,
                        balance_maximum=50_000_000)
        text = item_detail(row, currency_state(50_000_000))
        self.assertIn("总余额上限 50,000,000", text)
        self.assertIn("本次最多可加 0", text)
        self.assertNotIn("999,999,999", text)

    def test_currency_input_accepts_one_hundred_million_but_not_one_more(self):
        self.assertEqual(add_quantity(stone_row(), "100000000"), 100_000_000)
        with self.assertRaisesRegex(Refused, "100,000,000"):
            add_quantity(stone_row(), "100000001")


class AcquisitionFlowTests(unittest.TestCase):
    def panel(self):
        panel = AcquisitionPanel.__new__(AcquisitionPanel)
        panel.app = Mock()
        panel.app.busy = False
        panel.app.state = {}
        panel.backend = Mock()
        panel.quantity = Mock()
        panel.detail = Mock()
        panel.quantity.get.return_value = '10'
        panel.selected = Mock(return_value=dict(id=180000, name='回元散', can_add=True,
                                               stack_limit=999, max_quantity=999))
        return panel

    def job(self, panel):
        panel.add()
        panel.app.work.assert_called_once()
        return panel.app.work.call_args.args

    def test_battle_refusal_preserves_connection_catalogue_and_selection(self):
        from acquisition_context import AcquisitionContextRefused
        panel = self.panel()
        panel.backend.add.side_effect = AcquisitionContextRefused('战斗中暂不添加物品。')
        job, success = self.job(panel)
        result = job()
        panel.app.adapter.snapshot.assert_not_called()
        with patch('acquisition_ui.messagebox.showwarning') as warning:
            success(result)
        warning.assert_called_once()
        panel.app.render.assert_not_called()
        panel.app.shutdown_adapter.assert_not_called()
        panel.app.status.set.assert_called_with('战斗中暂不添加物品。')

    def test_exact_pre_dispatch_limit_refusal_preserves_connection_and_input(self):
        from acquisition_adapter import AcquisitionLimitRefused
        panel = self.panel()
        panel.selected.return_value = stone_row()
        reason = "当前余额 950,000,000，总余额上限 999,999,999，本次最多可加 49,999,999。"
        panel.backend.add.side_effect = AcquisitionLimitRefused(reason)
        job, success = self.job(panel)
        with patch('acquisition_ui.messagebox.showwarning'):
            success(job())
        panel.app.adapter.snapshot.assert_not_called()
        panel.app.shutdown_adapter.assert_not_called()
        panel.app.render.assert_not_called()
        panel.detail.set.assert_called_with(reason)
        panel.quantity.set.assert_not_called()

    def test_generic_refusal_is_not_misclassified_as_safe_limit_refusal(self):
        panel = self.panel()
        panel.backend.add.side_effect = Refused("unverified state")
        job, _ = self.job(panel)
        with self.assertRaisesRegex(Refused, "unverified state"):
            job()
        panel.app.adapter.snapshot.assert_not_called()

    def test_unknown_write_is_never_treated_as_harmless_refusal(self):
        panel = self.panel()
        panel.backend.add.side_effect = UncertainWrite('uncertain')
        job, _ = self.job(panel)
        with self.assertRaises(UncertainWrite):
            job()
        panel.app.adapter.snapshot.assert_not_called()

    def test_existing_stack_success_is_distinguished(self):
        panel = self.panel()
        panel.backend.add.return_value = {'native_injection': False, 'verified': True}
        job, success = self.job(panel)
        success(job())
        self.assertIn('已有堆叠已补充', panel.app.render.call_args.args[1])

    def test_refresh_failure_after_success_cannot_invite_retry(self):
        from ui_errors import RefreshAfterWriteError
        panel = self.panel()
        panel.backend.add.return_value = {'verified': True}
        panel.app.adapter.snapshot.side_effect = OSError('read failed')
        job, _ = self.job(panel)
        with self.assertRaises(RefreshAfterWriteError):
            job()
        panel.backend.add.assert_called_once_with(180000, 10)

    def test_late_result_cannot_change_a_replaced_connection(self):
        panel = self.panel()
        panel.backend.add.return_value = {'verified': True}
        job, success = self.job(panel)
        result = job()
        panel.app.adapter = Mock()
        success(result)
        panel.app.render.assert_not_called()
        panel.detail.set.assert_not_called()


class AcquisitionCurrencyTkTests(unittest.TestCase):
    """Construct the real panel and reuse it; selection only reads cached state."""
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        self.root = tk.Tk()
        self.root.geometry("860x730+30000+30000")
        self.addCleanup(self.root.destroy)
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill="both", expand=True)
        self.app = SimpleNamespace(root=self.root, tabs=tabs, busy=False, state=currency_state(17_100),
            adapter=Mock(), block_busy_selection=Mock(), status=tk.StringVar(), work=Mock())
        self.panel = AcquisitionPanel(self.app)
        self.panel.backend = Mock()

    def test_construct_first_selection_and_repeated_refresh_use_new_snapshot(self):
        self.panel.render([stone_row()])
        self.root.update()
        self.assertIn("上次读取余额 17,100", self.panel.detail.get())
        self.assertIn("本次最多可加 100,000,000", self.panel.detail.get())
        self.app.state = currency_state(950_000_000)
        self.panel.render([stone_row()])
        self.root.update()
        self.assertIn("上次读取余额 950,000,000", self.panel.detail.get())
        self.assertIn("本次最多可加 49,999,999", self.panel.detail.get())
        self.app.adapter.snapshot.assert_not_called()
        self.panel.backend.add.assert_not_called()
        self.app.work.assert_not_called()

    def test_changed_or_missing_balance_drops_old_display_without_querying_game(self):
        self.panel.render([stone_row()])
        self.root.update()
        self.app.state = dict(currencies={}, diagnostics=[dict(item_id=50000)])
        self.panel.select()
        self.assertIn("当前余额尚未核验", self.panel.detail.get())
        self.assertNotIn("17,100", self.panel.detail.get())
        self.app.adapter.snapshot.assert_not_called()
        self.app.work.assert_not_called()

    def test_full_balance_help_and_add_controls_are_visible_at_minimum_page_size(self):
        self.app.state = currency_state(999_999_999)
        self.panel.render([stone_row()])
        self.root.update()
        self.assertIn("本次最多可加 0", self.panel.detail.get())
        for widget in (self.panel.quantity_entry, self.panel.add_button):
            self.assertTrue(widget.winfo_viewable())
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                 self.root.winfo_rooty() + self.root.winfo_height())


class AppCurrencyLimitLayoutTests(unittest.TestCase):
    def test_currency_hints_and_bottom_actions_fit_real_sidebar_pages(self):
        import tkinter as tk
        from app import App
        root = tk.Tk()
        root.withdraw()
        try:
            with patch("app.native_calls_pending", return_value=False):
                app = App(root)
                app.adapter = SimpleNamespace(write_enabled=True, blocked=False, close=Mock())
                state = currency_state(950_000_000)
                state["currencies"]["currency:1"].update(name="灵石", category="currency",
                    type_name="货币", limit_source="游戏配置与工具限制取较低值")
                state["diagnostics"] = [dict(reason="currency_balance_unverified",
                    message="背包含无法识别的条目，不能核对灵石总余额；暂不支持灵石余额修改。")]
                app.render(state, "离线界面测试")
                app.inventory_mode.set("货币余额")
                app.filter_items()
                acquisition = next(panel for panel in app.extensions if isinstance(panel, AcquisitionPanel))
                acquisition.render([stone_row()])
                root.geometry("860x730+30000+30000")
                root.deiconify()
                for width, height in ((860, 730), (940, 800)):
                    root.geometry(f"{width}x{height}+30000+30000")
                    for title, button in (("背包数量", app.item_button),
                                          ("添加物品与秘籍", acquisition.add_button)):
                        tab = next(tab for tab in app.tabs.tabs() if app.tabs.tab(tab, "text") == title)
                        app.tabs.select(tab)
                        root.update()
                        page = root.nametowidget(tab)
                        page.canvas.yview_moveto(1)
                        root.update()
                        with self.subTest(size=(width, height), page=title):
                            self.assertTrue(button.winfo_viewable())
                            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                                 page.canvas.winfo_rootx() + page.canvas.winfo_width())
                            self.assertIs(root.winfo_containing(
                                button.winfo_rootx() + button.winfo_width() // 2,
                                button.winfo_rooty() + button.winfo_height() // 2), button)
        finally:
            for timer in root.tk.call("after", "info"):
                root.after_cancel(timer)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
