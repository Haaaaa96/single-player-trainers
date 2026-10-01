"""UI flow tests using fake widgets only; no Tk window or game process is opened."""
import queue
import threading
from types import SimpleNamespace
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

import app as ui
from write_guard import Refused, Target, UncertainWrite


class FakeVar:
    def __init__(self, value=""):
        self.value = value
    def set(self, value):
        self.value = value
    def get(self):
        return self.value


class FakeWidget:
    def __init__(self):
        self.options = {}
    def configure(self, **options):
        self.options.update(options)


class FakeTree:
    def __init__(self):
        self.rows = {}
        self.selected = ()
        self.states = set()
    def state(self, states):
        for state in states:
            if state.startswith("!"):
                self.states.discard(state[1:])
            else:
                self.states.add(state)
    def selection(self):
        return self.selected
    def selection_set(self, key):
        self.selected = (key,)
    def get_children(self):
        return tuple(self.rows)
    def delete(self, *keys):
        for key in keys:
            self.rows.pop(key, None)
        self.selected = tuple(key for key in self.selected if key not in keys)
    def insert(self, parent, position, iid, values):
        self.rows[iid] = values


class AppTests(unittest.TestCase):
    def setUp(self):
        self.ui = ui.App.__new__(ui.App)
        self.ui.root = Mock()
        self.ui.adapter = Mock()
        self.ui.state = {
            "spirit": Target("spirit", 0x1000, 0, ("player",), 0, 1000),
            "path": Target("path", 0x1004, 5, ("player",), 0, 1000),
            "items": {
                "item:1": {"name": "青瓷素盏", "type_name": "杂物", "target": Target("item:1", 0x2000, 2, ("item1",), 1, 99)},
                "item:2": {"name": "测试物品", "type_name": "材料", "target": Target("item:2", 0x2004, 7, ("item2",), 1, 50)},
            },
        }
        self.ui.busy = False
        self.ui.selected_game_path = None
        self.ui.game_location = FakeVar()
        self.ui.extensions = []
        self.ui.inventory_mode = FakeVar("背包物品")
        self.ui.inventory_filter = FakeWidget()
        self.ui.inventory_category = FakeVar(ui.ALL_CATEGORIES)
        self.ui.inventory_category_filter = FakeWidget()
        self.ui._inventory_mode_shown = "背包物品"
        self.ui.inventory_note = FakeVar()
        self.ui.events = queue.Queue()
        self.ui.status = FakeVar()
        self.ui.connection_notice = FakeVar()
        self.ui.connection_state = FakeVar()
        self.ui.items = FakeTree()
        self.ui.point_values = {kind: FakeVar() for kind in ("spirit", "path")}
        self.ui.point_inputs = {kind: FakeVar() for kind in ("spirit", "path")}
        self.ui.point_entries = {kind: FakeWidget() for kind in ("spirit", "path")}
        self.ui.point_buttons = {kind: FakeWidget() for kind in ("spirit", "path")}
        self.ui.item_input = FakeVar()
        self.ui.item_range = FakeVar()
        for name in ("connect_button", "refresh_button", "item_entry", "item_button", "choose_path_button", "auto_path_button"):
            setattr(self.ui, name, FakeWidget())
        self.ui.render(self.ui.state, "initial")
        self.warning_patch = patch.object(ui.messagebox, "showwarning")
        self.error_patch = patch.object(ui.messagebox, "showerror")
        self.warning = self.warning_patch.start()
        self.error = self.error_patch.start()
        self.addCleanup(self.warning_patch.stop)
        self.addCleanup(self.error_patch.stop)

    def capture_work(self):
        self.ui.work = Mock()

    def pending_job(self):
        self.ui.work.assert_called_once()
        return self.ui.work.call_args.args

    def select(self, key):
        self.ui.items.selection_set(key)
        self.ui.select_item()

    def test_render_refills_points_and_shows_item_limits(self):
        self.ui.point_inputs["spirit"].set("999")
        self.ui.point_inputs["path"].set("999")
        self.select("item:1")
        self.ui.item_input.set("88")
        self.ui.render(self.ui.state, "refreshed")
        self.assertEqual(self.ui.point_values["spirit"].get(), "0")
        self.assertEqual(self.ui.point_inputs["spirit"].get(), "0")
        self.assertEqual(self.ui.point_values["path"].get(), "5")
        self.assertEqual(self.ui.point_inputs["path"].get(), "5")
        self.assertEqual(self.ui.items.rows["item:1"], ("青瓷素盏", "杂物", 2, 99))
        self.assertEqual(self.ui.item_input.get(), "2")
        self.assertIn("1–99", self.ui.item_range.get())
        self.assertEqual(self.ui.status.get(), "refreshed")

    def test_current_page_refresh_routes_to_panel_without_refreshing_other_targets(self):
        refresh_panel = Mock()
        self.ui.navigation = SimpleNamespace(current_title=lambda:"人物属性")
        self.ui._page_refreshers = {"人物属性":refresh_panel}
        self.capture_work()
        self.ui.refresh_active()
        refresh_panel.assert_called_once()
        self.ui.work.assert_not_called()

    def test_readonly_current_page_refresh_uses_compatibility_snapshot_only(self):
        refresh_panel = Mock()
        self.ui.adapter.write_enabled = False
        self.ui.navigation = SimpleNamespace(current_title=lambda:"人物属性")
        self.ui._page_refreshers = {"人物属性":refresh_panel}
        self.capture_work()
        self.ui.refresh_active()
        refresh_panel.assert_not_called()
        job,_ = self.pending_job()
        self.assertEqual(job,self.ui.adapter.snapshot)

    def test_busy_and_disconnected_do_not_dispatch_current_page_refresh(self):
        refresh_panel = Mock()
        self.ui.navigation = SimpleNamespace(current_title=lambda:"人物属性")
        self.ui._page_refreshers = {"人物属性":refresh_panel}
        self.ui.busy = True
        self.ui.refresh_active()
        self.ui.busy = False
        self.ui.adapter = None
        self.ui.refresh_active()
        refresh_panel.assert_not_called()

    def test_navigation_only_updates_controls_and_preserves_pinned_data(self):
        self.capture_work()
        self.select("item:1")
        self.ui.item_input.set("30")
        original = self.ui.state
        self.ui.page_changed("人物属性")
        self.assertIs(self.ui.state,original)
        self.assertEqual(self.ui.item_input.get(),"30")
        self.ui.work.assert_not_called()
        self.ui.adapter.snapshot.assert_not_called()

    def test_connection_badge_reflects_readonly_pending_and_disconnection(self):
        self.ui.adapter.write_enabled = False
        self.ui.buttons()
        self.assertEqual(self.ui.connection_state.get(),"只读 · 兼容信息")
        self.ui.adapter.write_enabled = True
        with patch.object(ui,"native_calls_pending",return_value=True):self.ui.buttons()
        self.assertIn("等待原生结果",self.ui.connection_state.get())
        self.ui.adapter = None
        self.ui.buttons()
        self.assertEqual(self.ui.connection_state.get(),"尚未连接")

    def test_information_connection_clears_old_targets_and_disables_extensions(self):
        self.ui.adapter.write_enabled = False
        extension = Mock()
        self.ui.extensions = [extension]
        state = dict(read_only=True, items={}, currencies={}, diagnostics=[])
        self.ui.render(state, "兼容信息连接")
        self.assertEqual(self.ui.point_values["spirit"].get(), "—")
        self.assertEqual(self.ui.point_inputs["path"].get(), "")
        self.assertEqual(self.ui.point_buttons["spirit"].options["state"], "disabled")
        self.assertEqual(self.ui.refresh_button.options["state"], "normal")
        extension.update_enabled.assert_called_with(False)
        self.capture_work()
        self.ui.change("spirit")
        self.ui.work.assert_not_called()

    def test_version_warning_and_native_reason_remain_visible_after_refresh(self):
        self.ui.adapter.compatibility = SimpleNamespace(warnings=("游戏版本较新，功能不一定有效",))
        self.ui.adapter.native_block_reason = "请先保存并重启游戏"
        self.ui.connected(self.ui.state)
        self.warning.assert_called_once()
        self.ui.render(self.ui.state, "数值已刷新")
        self.assertIn("版本较新", self.ui.connection_notice.get())
        self.assertIn("重启游戏", self.ui.connection_notice.get())
        self.ui.shutdown_adapter()
        self.assertEqual(self.ui.connection_notice.get(), "")

    def test_unreviewed_build_warns_without_disabling_current_targets(self):
        self.ui.adapter.write_enabled = True
        self.ui.adapter.compatibility = SimpleNamespace(
            reviewed_files_match=False, warnings=("版本差异仅作提醒",))
        self.ui.connected(self.ui.state)
        self.assertIn("可继续使用", self.ui.status.get())
        self.assertNotEqual(self.ui.point_values["spirit"].get(), "—")
        self.assertEqual(self.ui.point_buttons["spirit"].options["state"], "normal")
        self.warning.assert_called_once()

    def test_selecting_another_item_resets_target_input(self):
        self.select("item:1")
        self.ui.item_input.set("80")
        self.select("item:2")
        self.assertEqual(self.ui.item_input.get(), "7")
        self.assertIn("1–50", self.ui.item_range.get())

    def test_missing_selection_disables_item_input(self):
        self.assertEqual(self.ui.item_input.get(), "")
        self.assertEqual(self.ui.item_entry.options["state"], "disabled")
        self.assertEqual(self.ui.item_button.options["state"], "disabled")
        self.capture_work()
        self.ui.change("item")
        self.ui.work.assert_not_called()

    def test_pending_native_operation_blocks_other_writes_after_reconnect(self):
        self.select("item:1")
        self.capture_work()
        with patch.object(ui, "native_calls_pending", return_value=True):
            self.ui.buttons()
            self.assertEqual(self.ui.point_buttons["spirit"].options["state"], "disabled")
            self.assertEqual(self.ui.item_button.options["state"], "disabled")
            self.ui.change("spirit")
            self.ui.change("item")
        self.ui.work.assert_not_called()
        self.assertIn("原生操作", self.ui.status.get())

    def test_removed_item_clears_selection_and_old_target(self):
        self.select("item:1")
        self.ui.item_input.set("80")
        state = {**self.ui.state, "items": {}}
        self.ui.render(state, "empty")
        self.assertEqual(self.ui.items.selection(), ())
        self.assertEqual(self.ui.item_input.get(), "")
        self.assertEqual(self.ui.item_button.options["state"], "disabled")

    def test_single_item_is_selected_and_refilled(self):
        state = {**self.ui.state, "items": {"item:2": self.ui.state["items"]["item:2"]}}
        self.ui.render(state, "one")
        self.assertEqual(self.ui.items.selection(), ("item:2",))
        self.assertEqual(self.ui.item_input.get(), "7")
        self.assertEqual(self.ui.item_entry.options["state"], "normal")

    def test_currency_selection_uses_separate_target_and_allows_zero(self):
        target = Target("currency:1", 0x3000, 800, ("currency",), 0, 1000000)
        self.ui.state["currencies"] = {"currency:1": {"name": "灵石", "target": target}}
        self.select("item:1")
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        self.assertEqual(self.ui.items.selection(), ("currency:1",))
        self.assertEqual(self.ui.item_input.get(), "800")
        self.capture_work()
        self.ui.item_input.set("0")
        self.ui.change("item")
        job, _ = self.pending_job()
        job()
        self.ui.adapter.set_value.assert_called_once_with(target, 0)

    def test_stone_selection_states_total_and_per_change_limits(self):
        target = Target("currency:1", 0x3000, 950_000_000, ("currency",), 0,
                        999_999_999, max_change=100_000_000)
        self.ui.state["currencies"] = {target.key: dict(name="灵石", target=target,
            category="currency", limit_source="游戏配置与工具限制取较低值")}
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        detail = self.ui.item_range.get()
        self.assertIn("单次变化量最多 100,000,000", detail)
        self.assertIn("总余额上限 999,999,999", detail)
        self.assertIn("本次可设 850,000,000–999,999,999", detail)
        self.assertIn("禁止超过", detail)
        self.assertEqual(self.ui.item_input.get(), "950000000")
        self.capture_work()
        self.ui.item_input.set("1000000000")
        self.ui.change("item")
        self.ui.work.assert_not_called()
        self.ui.adapter.set_value.assert_not_called()
        self.ui.adapter.close.assert_not_called()
        self.warning.assert_called_once()

    def test_stone_selection_uses_lower_runtime_configuration_limit(self):
        target = Target("currency:1", 0x3000, 17_100, ("currency",), 0,
                        50_000_000, max_change=100_000_000)
        self.ui.state["currencies"] = {target.key: dict(name="灵石", target=target,
            category="currency", limit_source="游戏配置与工具限制取较低值")}
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        self.assertIn("总余额上限 50,000,000", self.ui.item_range.get())
        self.assertIn("本次可设 0–50,000,000", self.ui.item_range.get())
        self.assertNotIn("999,999,999", self.ui.item_range.get())

    def test_excluded_currency_reason_is_visible_deduplicated_and_not_a_disconnect(self):
        warning = "灵石存在多个堆叠，暂不支持余额修改；其它条目仍可读取。"
        self.ui.state["diagnostics"] = [dict(reason="currency_multiple_stacks", message=warning)] * 2
        self.ui.state["diagnostics"].append(dict(reason="unknown", message="not a reviewed UI message"))
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        text = self.ui.inventory_note.get()
        self.assertEqual(text.count(warning), 1)
        self.assertIn("货币提示", text)
        self.assertNotIn("not a reviewed", text)
        self.ui.adapter.close.assert_not_called()
        self.assertEqual(self.ui.item_button.options["state"], "disabled")

    def test_currency_diagnostics_are_bounded_and_absent_from_item_mode(self):
        self.ui.state["diagnostics"] = [dict(reason="currency_balance_above_limit", message=f"余额限制 {index}")
                                        for index in range(5)]
        self.ui.filter_items()
        self.assertNotIn("货币提示", self.ui.inventory_note.get())
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        text = self.ui.inventory_note.get()
        self.assertIn("余额限制 2", text)
        self.assertNotIn("余额限制 3", text)
        self.assertIn("另有 2 项货币限制提示", text)

    def test_switch_to_empty_currency_list_clears_item_target(self):
        self.select("item:1")
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        self.assertEqual(self.ui.item_input.get(), "")
        self.assertEqual(self.ui.item_button.options["state"], "disabled")

    def test_category_filter_shows_matching_items_and_refills_the_new_target(self):
        self.assertEqual(self.ui.inventory_category_filter.options["values"],
                         [ui.ALL_CATEGORIES, "杂物", "材料"])
        self.select("item:1")
        self.ui.item_input.set("80")
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.assertEqual(set(self.ui.items.rows), {"item:2"})
        self.assertEqual(self.ui.items.selection(), ("item:2",))
        self.assertEqual(self.ui.item_input.get(), "7")
        self.assertIn("显示 1 / 2 项", self.ui.inventory_note.get())

    def test_hidden_stale_selection_cannot_be_written(self):
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.ui.items.selection_set("item:1")
        self.ui.item_input.set("3")
        self.assertIsNone(self.ui.selected_item())
        self.capture_work()
        self.ui.change("item")
        self.ui.work.assert_not_called()

    def test_refresh_keeps_empty_category_and_clears_old_write_target(self):
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.ui.item_input.set("40")
        state = {**self.ui.state, "items": {"item:1": self.ui.state["items"]["item:1"]}}
        self.ui.render(state, "refreshed")
        self.assertEqual(self.ui.inventory_category.get(), "材料")
        self.assertIn("材料", self.ui.inventory_category_filter.options["values"])
        self.assertEqual(self.ui.items.rows, {})
        self.assertEqual(self.ui.items.selection(), ())
        self.assertEqual(self.ui.item_input.get(), "")
        self.assertEqual(self.ui.item_button.options["state"], "disabled")
        self.assertIn("当前分类没有", self.ui.item_range.get())

    def test_refresh_preserves_category_but_refills_fresh_quantity(self):
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.ui.item_input.set("40")
        row = self.ui.state["items"]["item:2"]
        row["target"] = replace(row["target"], value=9)
        self.ui.render(self.ui.state, "refreshed")
        self.assertEqual(self.ui.inventory_category.get(), "材料")
        self.assertEqual(self.ui.items.selection(), ("item:2",))
        self.assertEqual(self.ui.item_input.get(), "9")

    def test_switching_inventory_mode_resets_category_and_old_target(self):
        self.ui.state["currencies"] = {"currency:1": {
            "name": "灵石", "type_name": "货币", "target": Target("currency:1", 0x3000, 80, ("currency",), 0, 1000000)}}
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.ui.inventory_mode.set("货币余额")
        self.ui.filter_items()
        self.assertEqual(self.ui.inventory_category.get(), ui.ALL_CATEGORIES)
        self.assertEqual(self.ui.inventory_category_filter.options["values"], [ui.ALL_CATEGORIES, "货币"])
        self.assertEqual(self.ui.item_input.get(), "80")
        self.ui.inventory_category.set("货币")
        self.ui.filter_items()
        self.ui.inventory_mode.set("背包物品")
        self.ui.filter_items()
        self.assertEqual(self.ui.inventory_category.get(), ui.ALL_CATEGORIES)
        self.assertEqual(self.ui.items.selection(), ())
        self.assertEqual(self.ui.item_input.get(), "")

    def test_unknown_category_keeps_trusted_quantity_target_writable(self):
        row = self.ui.state["items"]["item:1"]
        del row["type_name"]
        original_target = row["target"]
        self.ui.inventory_category.set("未知分类")
        self.ui.filter_items()
        self.assertEqual(self.ui.items.rows["item:1"], ("青瓷素盏", "未知分类", 2, 99))
        self.assertIs(self.ui.selected_item()["target"], original_target)
        self.capture_work()
        self.ui.item_input.set("3")
        self.ui.change("item")
        job, _ = self.pending_job()
        job()
        self.ui.adapter.set_value.assert_called_once_with(original_target, 3)

    def test_category_filter_does_not_bypass_pending_native_write_guard(self):
        self.capture_work()
        with patch.object(ui, "native_calls_pending", return_value=True):
            self.ui.inventory_category.set("材料")
            self.ui.filter_items()
            self.assertEqual(self.ui.item_button.options["state"], "disabled")
            self.ui.item_input.set("8")
            self.ui.change("item")
        self.ui.work.assert_not_called()

    def test_path_change_clears_category_and_its_stale_rows(self):
        self.ui.inventory_category.set("材料")
        self.ui.filter_items()
        self.ui.set_game_path("D:/Games/WorldApart.exe")
        self.assertEqual(self.ui.inventory_category.get(), ui.ALL_CATEGORIES)
        self.assertEqual(self.ui.inventory_category_filter.options["values"], [ui.ALL_CATEGORIES])
        self.assertEqual(self.ui.items.rows, {})
        self.assertEqual(self.ui.item_input.get(), "")

    def test_disconnect_invalidates_extensions_before_closing_game_reader(self):
        extension = Mock()
        adapter = self.ui.adapter
        self.ui.extensions = [extension]
        self.ui.shutdown_adapter()
        extension.disconnect.assert_called_once()
        adapter.close.assert_called_once()
        self.assertIsNone(self.ui.adapter)

    def test_cancel_game_selection_preserves_connection(self):
        adapter, state = self.ui.adapter, self.ui.state
        with patch.object(ui.filedialog, "askopenfilename", return_value=""):
            self.ui.choose_game_path()
        self.assertIs(self.ui.adapter, adapter)
        self.assertIs(self.ui.state, state)
        adapter.close.assert_not_called()

    def test_selecting_wrong_executable_keeps_current_connection(self):
        adapter = self.ui.adapter
        with patch.object(ui.filedialog, "askopenfilename", return_value="D:/游戏/WorldApartTrainer.exe"):
            self.ui.choose_game_path()
        self.warning.assert_called_once()
        self.assertIs(self.ui.adapter, adapter)
        adapter.close.assert_not_called()

    def test_changing_location_invalidates_old_targets_without_launching(self):
        adapter = self.ui.adapter
        self.ui.extensions = [Mock()]
        self.select("item:1")
        path = "D:/Steam Library/中文 游戏/WorldApart.exe"
        with patch.object(ui.filedialog, "askopenfilename", return_value=path), patch.object(ui, "GameAdapter") as factory:
            self.ui.choose_game_path()
        self.assertEqual(self.ui.selected_game_path, path)
        self.assertIn(path, self.ui.game_location.get())
        self.assertIsNone(self.ui.adapter)
        self.assertIsNone(self.ui.state)
        adapter.close.assert_called_once()
        self.ui.extensions[0].disconnect.assert_called_once()
        self.assertFalse(self.ui.items.rows)
        self.assertEqual(self.ui.point_inputs["spirit"].get(), "")
        self.assertEqual(self.ui.item_entry.options["state"], "disabled")
        factory.assert_not_called()

    def test_return_to_auto_discards_manual_filter(self):
        self.ui.selected_game_path = "D:/Library/WorldApart.exe"
        self.ui.use_auto_path()
        self.assertIsNone(self.ui.selected_game_path)
        self.assertIn("自动识别", self.ui.game_location.get())
        self.assertEqual(self.ui.auto_path_button.options["state"], "disabled")

    def test_connect_pins_selected_path_before_async_worker(self):
        self.capture_work()
        chosen = "D:/Steam Library/中文/WorldApart.exe"
        self.ui.selected_game_path = chosen
        self.ui.connect()
        job, success = self.pending_job()
        self.ui.selected_game_path = "E:/Other/WorldApart.exe"
        with patch.object(ui, "GameAdapter") as factory:
            factory.return_value.executable_path = chosen
            factory.return_value.snapshot.return_value = self.ui.state
            state = job()
            factory.assert_called_once_with(game_path=chosen)
            success(state)
        self.assertIn(chosen, self.ui.game_location.get())

    def test_auto_connect_passes_no_fixed_location(self):
        self.capture_work()
        self.ui.connect()
        job, _ = self.pending_job()
        with patch.object(ui, "GameAdapter") as factory:
            job()
        factory.assert_called_once_with(game_path=None)

    def test_pending_native_call_blocks_path_changes_and_reconnect(self):
        self.capture_work()
        adapter = self.ui.adapter
        with patch.object(ui, "native_calls_pending", return_value=True), patch.object(ui.filedialog, "askopenfilename") as picker:
            self.ui.buttons()
            self.ui.choose_game_path()
            self.ui.use_auto_path()
            self.ui.connect()
        self.assertEqual(self.ui.choose_path_button.options["state"], "disabled")
        self.assertEqual(self.ui.connect_button.options["state"], "disabled")
        self.assertIs(self.ui.adapter, adapter)
        picker.assert_not_called()
        self.ui.work.assert_not_called()

    def test_invalid_point_input_keeps_connection_without_worker(self):
        self.capture_work()
        adapter, state = self.ui.adapter, self.ui.state
        for kind in ("spirit", "path"):
            for value in ("", "-1", "1.5", "1e3", "1001", str(state[kind].value)):
                with self.subTest(kind=kind, value=value):
                    self.ui.point_inputs[kind].set(value)
                    self.ui.change(kind)
                    self.assertIs(self.ui.adapter, adapter)
                    self.assertIs(self.ui.state, state)
                    self.assertFalse(self.ui.busy)
        self.assertEqual(self.warning.call_count, 12)
        self.ui.work.assert_not_called()
        adapter.set_value.assert_not_called()
        adapter.close.assert_not_called()

    def test_item_limit_is_checked_before_worker(self):
        self.capture_work()
        self.select("item:1")
        for value in ("0", "100", "2"):
            self.ui.item_input.set(value)
            self.ui.change("item")
        self.assertEqual(self.warning.call_count, 3)
        self.ui.work.assert_not_called()
        self.ui.adapter.close.assert_not_called()

    def test_single_change_limit_checked_before_worker(self):
        self.capture_work()
        row = self.ui.state["items"]["item:1"]
        row["target"] = replace(row["target"], maximum=10000)
        self.select("item:1")
        self.ui.item_input.set("1003")
        self.ui.change("item")
        self.warning.assert_called_once()
        self.ui.work.assert_not_called()

    def test_point_targets_use_one_absolute_write_and_one_refresh(self):
        for kind, value in (("spirit", 1000), ("path", 400)):
            with self.subTest(kind=kind):
                self.capture_work()
                self.ui.adapter.reset_mock()
                shown = self.ui.state[kind]
                self.ui.point_inputs[kind].set(str(value))
                self.ui.change(kind)
                job, success = self.pending_job()
                fresh = {**self.ui.state, kind: replace(shown, value=value)}
                self.ui.adapter.snapshot.return_value = fresh
                self.assertIs(job(), fresh)
                self.ui.adapter.set_value.assert_called_once_with(shown, value)
                self.ui.adapter.snapshot.assert_called_once()
                self.ui.adapter.change.assert_not_called()
                success(fresh)
                self.assertEqual(self.ui.point_inputs[kind].get(), str(value))
                self.assertIn("已写入并复读确认", self.ui.status.get())

    def test_item_target_is_pinned_before_async_work(self):
        self.capture_work()
        self.select("item:1")
        shown = self.ui.state["items"]["item:1"]["target"]
        self.ui.item_input.set("30")
        self.ui.change("item")
        job, _ = self.pending_job()
        self.select("item:2")
        self.ui.item_input.set("40")
        job()
        self.ui.adapter.set_value.assert_called_once_with(shown, 30)
        self.ui.adapter.snapshot.assert_called_once()

    def test_busy_disables_all_inputs_buttons_and_list(self):
        self.select("item:1")
        self.ui.busy = True
        self.ui.buttons()
        widgets = [self.ui.connect_button, self.ui.refresh_button, self.ui.item_entry,
                   self.ui.item_button, self.ui.inventory_filter, self.ui.inventory_category_filter,
                   *self.ui.point_entries.values(), *self.ui.point_buttons.values()]
        self.assertTrue(all(widget.options["state"] == "disabled" for widget in widgets))
        self.assertIn("disabled", self.ui.items.states)
        self.assertEqual(self.ui.block_busy_selection(None), "break")
        self.capture_work()
        self.ui.change("spirit")
        self.ui.refresh()
        self.ui.connect()
        self.ui.work.assert_not_called()

    def test_disconnected_controls_stay_disabled(self):
        self.ui.adapter = None
        self.ui.state = None
        self.ui.buttons()
        self.assertEqual(self.ui.connect_button.options["state"], "normal")
        self.assertEqual(self.ui.refresh_button.options["state"], "disabled")
        self.assertEqual(self.ui.point_entries["path"].options["state"], "disabled")
        self.assertIn("disabled", self.ui.items.states)

    def test_verified_write_followed_by_refresh_failure_is_explicit(self):
        self.capture_work()
        self.ui.point_inputs["path"].set("6")
        self.ui.adapter.snapshot.side_effect = OSError("mock refresh failure")
        self.ui.change("path")
        job, success = self.pending_job()
        with self.assertRaises(ui.RefreshAfterWriteError) as raised:
            job()
        error = raised.exception
        self.assertIn("写入和复读已成功", str(error))
        self.assertIn("剩余道途点：5 → 6", str(error))
        self.ui.adapter.set_value.assert_called_once()
        adapter = self.ui.adapter
        self.ui.events.put((success, None, error))
        self.ui.poll()
        self.assertIsNone(self.ui.adapter)
        self.assertIsNone(self.ui.state)
        adapter.close.assert_called_once()
        self.assertIn("数值已写入并复读成功", self.ui.status.get())
        self.error.assert_called_once()

    def test_failed_write_does_not_refresh_or_claim_success(self):
        self.capture_work()
        self.ui.point_inputs["path"].set("6")
        self.ui.adapter.set_value.side_effect = UncertainWrite("mock uncertain write")
        self.ui.change("path")
        job, success = self.pending_job()
        with self.assertRaises(UncertainWrite) as raised:
            job()
        self.ui.adapter.snapshot.assert_not_called()
        adapter = self.ui.adapter
        self.ui.events.put((success, None, raised.exception))
        self.ui.poll()
        self.assertIn("已停止操作", self.ui.status.get())
        self.assertNotIn("复读成功", self.ui.status.get())
        adapter.close.assert_called_once()
        adapter.set_value.assert_called_once()

    def test_worker_enqueues_one_result_and_poll_enables_controls(self):
        job, success = Mock(return_value="result"), Mock()
        with patch.object(ui.threading, "Thread") as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs["target"]()
            self.ui.work(job, success)
            thread.assert_called_once()
            self.assertTrue(thread.call_args.kwargs["daemon"])
        self.assertTrue(self.ui.busy)
        job.assert_called_once()
        success.assert_not_called()
        self.ui.poll()
        self.assertFalse(self.ui.busy)
        success.assert_called_once_with("result")
        self.assertEqual(self.ui.point_entries["spirit"].options["state"], "normal")

    def test_close_during_work_does_not_release_in_use_adapter(self):
        adapter = self.ui.adapter
        self.ui.busy = True
        self.ui.close()
        adapter.close.assert_not_called()
        self.ui.root.destroy.assert_not_called()
        self.ui.busy = False
        self.ui.close()
        adapter.close.assert_called_once()
        self.ui.root.destroy.assert_called_once()

    def run_job(self, job, success, **options):
        with patch.object(ui.threading, 'Thread') as thread:
            thread.return_value.start.side_effect = lambda: thread.call_args.kwargs['target']()
            self.ui.work(job, success, **options)

    def test_pure_read_failure_rechecks_core_on_same_worker_and_clears_extension_targets(self):
        adapter, success = self.ui.adapter, Mock()
        stale = {'target': object()}
        extension = Mock()
        extension.disconnect.side_effect = stale.clear
        self.ui.extensions = [extension]
        fresh = {**self.ui.state, 'path': replace(self.ui.state['path'], value=8)}
        seen_threads = []
        def read_page():
            seen_threads.append(threading.get_ident())
            raise Refused('测试：扩展字段尚未适配')
        def read_core():
            seen_threads.append(threading.get_ident())
            return fresh
        adapter.snapshot.side_effect = read_core
        self.ui.work(read_page, success, readonly=True)
        event = self.ui.events.get(timeout=5)
        self.ui.events.put(event)
        self.assertEqual(len(seen_threads), 2)
        self.assertEqual(seen_threads[0], seen_threads[1])
        self.assertNotEqual(seen_threads[0], threading.get_ident())
        extension.disconnect.assert_not_called()
        self.assertTrue(stale)
        self.ui.poll()
        self.assertIs(self.ui.adapter, adapter)
        self.assertIs(self.ui.state, fresh)
        self.assertEqual(self.ui.point_inputs['path'].get(), '8')
        self.assertEqual(stale, {})
        extension.disconnect.assert_called_once()
        adapter.close.assert_not_called()
        success.assert_not_called()
        self.assertIn('基础连接已重新核验', self.ui.status.get())
        self.assertIn('扩展字段尚未适配', self.ui.status.get())
        self.assertEqual(self.ui.point_buttons['path'].options['state'], 'normal')
        self.assertIn('扩展字段尚未适配', self.error.call_args.args[1])

    def test_pure_read_failure_with_failed_core_identity_check_disconnects(self):
        adapter, success = self.ui.adapter, Mock()
        adapter.snapshot.side_effect = Refused('游戏进程已变化')
        self.run_job(Mock(side_effect=Refused('页面读取失败')), success, readonly=True)
        adapter.snapshot.assert_called_once()
        self.ui.poll()
        self.assertIsNone(self.ui.adapter)
        self.assertIsNone(self.ui.state)
        adapter.close.assert_called_once()
        success.assert_not_called()

    def test_default_jobs_and_uncertain_or_post_write_errors_never_recover(self):
        cases = ((False, Refused('写入准备失败')),
                 (False, OSError('原生getter读取失败')),
                 (True, UncertainWrite('结果未知')),
                 (True, ui.RefreshAfterWriteError('已写入但随后刷新失败')))
        for readonly, error in cases:
            with self.subTest(readonly=readonly, error=type(error).__name__):
                adapter = Mock()
                self.ui.adapter, self.ui.state = adapter, {'items': {}}
                self.ui.busy = False
                success = Mock()
                self.run_job(Mock(side_effect=error), success, readonly=readonly)
                adapter.snapshot.assert_not_called()
                self.ui.poll()
                self.assertIsNone(self.ui.adapter)
                self.assertIsNone(self.ui.state)
                adapter.close.assert_called_once()
                success.assert_not_called()

    def test_pure_read_failure_with_pending_native_operation_does_not_recover(self):
        adapter = self.ui.adapter
        with patch.object(ui, 'native_calls_pending', return_value=True):
            self.run_job(Mock(side_effect=Refused('页面读取失败')), Mock(), readonly=True)
            self.ui.poll()
        adapter.snapshot.assert_not_called()
        adapter.close.assert_called_once()
        self.assertIsNone(self.ui.adapter)

    def test_recovered_read_event_never_restores_a_replaced_adapter(self):
        original = self.ui.adapter
        original.snapshot.return_value = self.ui.state
        self.run_job(Mock(side_effect=Refused('页面读取失败')), Mock(), readonly=True)
        replacement = Mock()
        self.ui.adapter = replacement
        self.ui.poll()
        self.assertIsNone(self.ui.adapter)
        self.assertIsNone(self.ui.state)
        replacement.close.assert_called_once()
        original.close.assert_not_called()

    def test_successful_pure_read_has_no_extra_core_probe_or_extension_reset(self):
        success, extension = Mock(), Mock()
        self.ui.extensions = [extension]
        self.run_job(lambda: 'page', success, readonly=True)
        self.ui.poll()
        success.assert_called_once_with('page')
        self.ui.adapter.snapshot.assert_not_called()
        extension.disconnect.assert_not_called()

    def test_core_refresh_opts_into_readonly_recovery_but_write_refresh_does_not(self):
        self.capture_work()
        self.ui.refresh()
        self.assertIs(self.ui.work.call_args.kwargs.get('readonly'), True)
        self.ui.work.reset_mock()
        self.ui.point_inputs['path'].set('6')
        self.ui.change('path')
        self.assertIsNot(self.ui.work.call_args.kwargs.get('readonly'), True)


if __name__ == "__main__":
    unittest.main()
