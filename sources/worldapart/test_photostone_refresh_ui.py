"""Exercise post-action refresh through real Tk, App.work and App.poll.

Only the game adapter is a substitute: these tests do not open a game process
or acquire a native connection. The operation, queue and UI callback sequence
is retained, including the distinction between a committed action and a failed
display refresh.
"""
from copy import deepcopy
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app import App
from photostone_ui import PhotostonePanel
from write_guard import Refused, UncertainWrite


def checklist():
    return dict(summary="当前清单", rows=[
        dict(name="角色甲", npc_id=1, sub_id=11, identity="before-one", stage=1,
             success_count=1, max_success=1, status="已完成", reason="可以重玩",
             can_activate=False, can_force=True),
        dict(name="角色甲", npc_id=1, sub_id=12, identity="before-two", stage=2,
             success_count=0, max_success=1, status="未完成", reason="可以激活",
             can_activate=True, can_force=True, location_label="初始山门",
             location_reason="之前读取的位置"),
        dict(name="角色乙", npc_id=2, sub_id=21, identity="before-other", stage=1,
             success_count=0, max_success=1, status="未完成", reason="可以激活",
             can_activate=True, can_force=True)])


def activated_checklist(sub_id=12, *, reorder=False):
    state = deepcopy(checklist())
    state["summary"] = "激活后的真实清单"
    row = next(row for row in state["rows"] if row["sub_id"] == sub_id)
    row.update(identity="after-activation", active_special=sub_id, success_count=0,
               status="已激活", reason="本阶段已经激活，请回游戏选择留影石。",
               can_activate=False, can_force=False, location_label="逍遥城",
               location_reason="已读取当前角色所在场景")
    if reorder:
        state["rows"] = [state["rows"][1], state["rows"][2], state["rows"][0]]
    return state


class PhotostoneRefreshUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.cleanup_root)
        for target in ("app.native_calls_pending", "photostone_ui.native_calls_pending",
                       "dual_cultivation_ui.native_calls_pending"):
            handle = patch(target, return_value=False)
            handle.start()
            self.addCleanup(handle.stop)
        # Tests map off-screen windows only; never take keyboard focus from the
        # user's foreground game while exercising the production dialog code.
        for method in ("lift", "focus_set"):
            handle = patch.object(tk.Toplevel, method)
            handle.start()
            self.addCleanup(handle.stop)
        error_dialog = patch("app.messagebox.showerror")
        self.showerror = error_dialog.start()
        self.addCleanup(error_dialog.stop)
        self.app = App(self.root)
        self.photo = next(extension for extension in self.app.extensions
                          if isinstance(extension, PhotostonePanel))
        self.game = self.new_game()
        self.adapter = self.new_adapter(self.game)
        self.app.adapter = self.game
        self.app.state = dict(items={}, currencies={})
        self.photo.adapter = self.adapter
        self.photo.render(checklist())
        self.app.buttons()

    @staticmethod
    def new_game():
        return SimpleNamespace(write_enabled=True, blocked=False, close=Mock())

    @staticmethod
    def new_adapter(game):
        return SimpleNamespace(game=game, blocked=False, close=Mock(),
            activate_next=Mock(return_value=dict(verified=True, status="verified", message="已激活角色甲")),
            force=Mock(return_value=dict(verified=True, status="verified", message="已强制激活角色甲")),
            preview_force=Mock(), snapshot=Mock(return_value=activated_checklist()))

    def cleanup_root(self):
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.destroy()

    def select(self, sub_id=12):
        key = next(key for key, row in self.photo.rows.items() if row["sub_id"] == sub_id)
        self.photo.tree.selection_set(key)
        self.photo.selected()

    def await_event(self):
        # Wait for the real worker without entering Tk's event loop. This leaves
        # the exact completion callback pending for deliberate stale-UI tests.
        return self.app.events.get(timeout=5)

    def deliver(self, event):
        self.app.events.put(event)
        self.app.poll()

    def finish(self):
        event = self.await_event()
        self.deliver(event)
        return event

    def assert_no_write_target(self):
        self.assertIsNone(self.photo.state)
        self.assertEqual(self.photo.rows, {})
        self.assertEqual(self.photo.tree.get_children(), ())
        self.assertEqual(str(self.photo.activate_button["state"]), "disabled")
        self.assertIsNone(self.photo._force_dialog_button)

    @staticmethod
    def widgets_below(widget):
        for child in widget.winfo_children():
            yield child
            yield from PhotostoneRefreshUiTests.widgets_below(child)

    def map_photo_page(self):
        tab = next(tab for tab in self.app.tabs.tabs()
                   if self.app.tabs.tab(tab, "text") == self.photo.title)
        self.app.tabs.select(tab)
        self.root.overrideredirect(True)
        self.root.geometry("940x800+30000+30000")
        self.root.deiconify()
        self.root.update()

    def queue_force_preview(self):
        self.select(11)
        # Deliver the real selection event before the preview button action,
        # matching the order of mouse interaction in the mapped application.
        self.root.update()
        preview = dict(row=dict(self.photo.selected_row()), message=(
            "角色甲 · 第 1 段（编号 11）\n当前成功次数：1。\n"
            "将删除本阶段已有成功记录并激活该阶段；其它阶段记录保持不变。\n"
            "不直接发奖励，不推进时间。失败或退出不会恢复原完成记录。"))
        self.adapter.preview_force.return_value = preview
        self.photo.preview_force()
        return preview, self.await_event()

    def open_force_preview(self):
        self.map_photo_page()
        preview, event = self.queue_force_preview()
        self.deliver(event)
        self.root.update()
        dialog = self.photo._force_dialog
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.winfo_ismapped())
        self.assertTrue(dialog.winfo_viewable())
        self.assertGreaterEqual(dialog.winfo_rootx(), 30000)
        return dialog, preview

    def test_activate_refreshes_once_after_verified_write_in_real_queue(self):
        order = []
        self.adapter.activate_next.side_effect = lambda row: (
            order.append("activate") or dict(verified=True, message="已激活角色甲"))
        self.adapter.snapshot.side_effect = lambda: (
            order.append("snapshot") or activated_checklist())
        self.select()
        self.photo.activate()
        self.assertTrue(self.app.busy)
        self.assertIsNone(self.photo.state)
        self.photo.activate()  # A second click before the worker callback.
        event = self.finish()
        self.assertIsNone(event[2])
        self.assertEqual(order, ["activate", "snapshot"])
        self.adapter.activate_next.assert_called_once()
        self.adapter.snapshot.assert_called_once_with()
        self.assertFalse(self.app.busy)
        row = self.photo.selected_row()
        self.assertEqual((row["npc_id"], row["sub_id"]), (1, 12))
        self.assertEqual(row["status"], "已激活")
        selected = self.photo.tree.selection()[0]
        self.assertEqual(self.photo.tree.set(selected, "status"), "已激活")
        self.assertEqual(self.photo.tree.set(selected, "location"), "逍遥城")
        self.assertIn("逍遥城", self.photo.detail.get())
        self.assertIn("已读取当前角色所在场景", self.photo.detail.get())
        self.assertNotIn("初始山门", self.photo.detail.get())
        self.assertIn("已激活", self.photo.note.get())
        self.assertIn("已激活", self.app.status.get())
        self.assertEqual(str(self.photo.activate_button["state"]), "disabled")
        self.photo.activate()  # Already-active target must remain unavailable.
        self.adapter.activate_next.assert_called_once()
        self.showerror.assert_not_called()

    def test_force_success_refreshes_and_discards_old_confirmation(self):
        self.select(11)
        preview = dict(row=dict(self.photo.selected_row()), message="将重置所选阶段")
        self.photo.preview = preview
        self.photo.confirmed.set(True)
        self.adapter.snapshot.return_value = activated_checklist(11)
        self.photo.force()
        self.finish()
        self.adapter.force.assert_called_once_with(preview, confirmed=True)
        self.adapter.activate_next.assert_not_called()
        self.adapter.snapshot.assert_called_once_with()
        self.assertEqual(self.photo.selected_row()["sub_id"], 11)
        self.assertEqual(self.photo.selected_row()["status"], "已激活")
        self.assertIsNone(self.photo.preview)
        self.assertFalse(self.photo.confirmed.get())
        self.assertIsNone(self.photo._force_dialog_button)

    def test_preview_opens_visible_dialog_and_requires_checkbox_before_single_force(self):
        dialog, preview = self.open_force_preview()
        message = next(widget for widget in self.widgets_below(dialog)
                       if widget.winfo_class() == "Text")
        self.assertEqual(message.get("1.0", "end-1c"), preview["message"])
        self.assertEqual(str(message["state"]), "disabled")
        self.assertIs(self.root.grab_current(), dialog)
        self.assertFalse(self.photo.confirmed.get())
        button = self.photo._force_dialog_button
        checkbox = self.photo._force_dialog_confirm
        self.assertEqual(str(button["state"]), "disabled")
        button.invoke()
        self.adapter.force.assert_not_called()
        self.adapter.activate_next.assert_not_called()
        self.adapter.snapshot.assert_not_called()
        self.assertTrue(self.app.events.empty())
        checkbox.invoke()
        self.assertTrue(self.photo.confirmed.get())
        self.assertEqual(str(button["state"]), "normal")
        self.adapter.snapshot.return_value = activated_checklist(11)
        button.invoke()
        self.assertIsNone(self.photo._force_dialog)
        self.assertFalse(dialog.winfo_exists())
        self.finish()
        self.photo.force()
        self.adapter.force.assert_called_once_with(preview, confirmed=True)
        self.adapter.snapshot.assert_called_once_with()
        self.assertFalse(self.photo.confirmed.get())
        self.assertIsNone(self.photo.preview)
        self.assertEqual(self.photo.selected_row()["status"], "已激活")
        self.showerror.assert_not_called()

    def test_preview_cancel_closes_dialog_without_writing_and_revokes_confirmation(self):
        dialog, preview = self.open_force_preview()
        self.photo._force_dialog_confirm.invoke()
        self.assertTrue(self.photo.confirmed.get())
        cancel = next(widget for widget in self.widgets_below(dialog)
                      if widget.winfo_class() == "TButton" and widget.cget("text") == "取消")
        cancel.invoke()
        self.root.update()
        self.assertIsNone(self.photo._force_dialog)
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNone(self.root.grab_current())
        self.assertFalse(self.photo.confirmed.get())
        self.assertIs(self.photo.preview, preview)
        self.assertIsNone(self.photo._force_dialog_button)
        self.photo.force()
        self.adapter.force.assert_not_called()
        self.adapter.activate_next.assert_not_called()
        self.adapter.snapshot.assert_not_called()
        self.assertTrue(self.app.events.empty())

    def test_preview_closes_when_another_stage_is_selected(self):
        dialog, _preview = self.open_force_preview()
        self.photo._force_dialog_confirm.invoke()
        self.select(12)
        self.root.update()
        self.assertIsNone(self.photo._force_dialog)
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNone(self.photo.preview)
        self.assertFalse(self.photo.confirmed.get())
        self.adapter.force.assert_not_called()

    def test_blocked_row_explains_reason_in_dialog_without_enabling_force(self):
        self.map_photo_page()
        self.select(11)
        self.root.update()
        row = self.photo.selected_row()
        row.update(can_force=False, force_reason="角色已有其它特殊互动（编号 1），请先正常处理。")
        self.photo.selected()
        self.assertEqual(str(self.photo.preview_button['state']), 'normal')
        self.assertIn(row['force_reason'], self.photo.detail.get())
        self.photo.preview_button.invoke()
        self.root.update()
        dialog = self.photo._force_dialog
        self.assertIsNotNone(dialog)
        text = next(widget for widget in self.widgets_below(dialog) if widget.winfo_class() == 'Text')
        self.assertIn(row['force_reason'], text.get('1.0', 'end'))
        self.assertEqual(str(self.photo._force_dialog_button['state']), 'disabled')
        self.assertEqual(str(self.photo._force_dialog_confirm['state']), 'disabled')
        self.photo.confirmed.set(True)
        self.photo.force()
        self.adapter.preview_force.assert_not_called()
        self.adapter.force.assert_not_called()

    def test_actions_are_visible_without_scrolling_at_normal_window_size(self):
        self.map_photo_page()
        self.root.geometry('860x730+30000+30000')
        self.root.update()
        for button in (self.photo.activate_button, self.photo.preview_button):
            self.assertTrue(button.winfo_viewable())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 self.root.winfo_rooty() + self.root.winfo_height())
        self.assertFalse(hasattr(self.photo, 'force_button'))

    def test_preview_closes_on_refresh_without_replaying_the_operation(self):
        dialog, _preview = self.open_force_preview()
        self.photo._force_dialog_confirm.invoke()
        self.photo.detect()
        self.assertIsNone(self.photo._force_dialog)
        self.assertFalse(dialog.winfo_exists())
        self.finish()
        self.assertIsNone(self.photo.preview)
        self.assertFalse(self.photo.confirmed.get())
        self.adapter.force.assert_not_called()
        self.adapter.activate_next.assert_not_called()
        self.adapter.snapshot.assert_called_once_with()

    def test_preview_closes_on_disconnect_without_writing(self):
        dialog, _preview = self.open_force_preview()
        self.photo._force_dialog_confirm.invoke()
        self.app.shutdown_adapter()
        self.app.state = None
        self.root.update()
        self.assertIsNone(self.photo._force_dialog)
        self.assertFalse(dialog.winfo_exists())
        self.assertIsNone(self.photo.preview)
        self.assertFalse(self.photo.confirmed.get())
        self.assertIsNone(self.app.adapter)
        self.adapter.force.assert_not_called()

    def test_late_preview_after_disconnect_never_opens_dialog(self):
        self.map_photo_page()
        _preview, event = self.queue_force_preview()
        self.app.shutdown_adapter()
        self.app.state = None
        self.app.status.set("预览期间断开")
        self.deliver(event)
        self.root.update()
        self.assertIsNone(self.photo._force_dialog)
        self.assertIsNone(self.photo.preview)
        self.assertEqual(self.app.status.get(), "预览期间断开")
        self.adapter.preview_force.assert_called_once()
        self.adapter.force.assert_not_called()
        self.adapter.snapshot.assert_not_called()

    def test_late_preview_for_previous_selection_never_opens_dialog(self):
        self.map_photo_page()
        _preview, event = self.queue_force_preview()
        self.select(12)
        self.deliver(event)
        self.root.update()
        self.assertIsNone(self.photo._force_dialog)
        self.assertIsNone(self.photo.preview)
        self.assertEqual(self.photo.selected_row()["sub_id"], 12)
        self.adapter.preview_force.assert_called_once()
        self.adapter.force.assert_not_called()
        self.adapter.snapshot.assert_not_called()

    def test_location_column_and_detail_render_unknown_without_inventing_a_place(self):
        self.select(21)
        selected = self.photo.tree.selection()[0]
        self.assertEqual(self.photo.tree.set(selected, "location"), "位置未知")
        self.assertIn("所在场景：位置未知", self.photo.detail.get())
        self.assertNotIn("逍遥城", self.photo.detail.get())
        self.adapter.snapshot.assert_not_called()
        self.adapter.activate_next.assert_not_called()

    def test_populated_location_and_status_columns_fit_both_mapped_window_sizes(self):
        # Match the standalone verifier: a mapped off-screen window has real
        # geometry and stacking, unlike a withdrawn 1px tree or notebook page.
        long_location = "云川大陆 · 苍梧州 · 百药山庄 · 后山深处的炼丹长廊；" * 3
        populated = checklist()
        populated["rows"][1].update(location_label=long_location,
            location_reason="此处显示读取到的完整场景名称；长名称应在详情换行。")
        self.photo.render(populated)
        self.select()
        tab = next(tab for tab in self.app.tabs.tabs()
                   if self.app.tabs.tab(tab, "text") == self.photo.title)
        self.app.tabs.select(tab)
        page = self.root.nametowidget(tab)
        content = page.content
        self.root.overrideredirect(True)
        self.root.geometry("940x800+30000+30000")
        self.root.deiconify()
        self.root.update()
        controls = (self.photo.detect_button, self.photo.activate_button,
                    self.photo.preview_button)

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        detail_label = next(widget for widget in descendants(content)
                            if widget.winfo_class() == "TLabel"
                            and str(widget.cget("textvariable")) == str(self.photo.detail))
        for width, height in ((940, 800), (860, 730)):
            with self.subTest(width=width, height=height):
                self.root.geometry(f"{width}x{height}+30000+30000")
                page.canvas.yview_moveto(0)
                self.root.update()
                self.assertTrue(content.winfo_ismapped())
                self.assertTrue(self.photo.tree.winfo_ismapped())
                self.assertGreater(self.photo.tree.winfo_width(), 1)
                self.assertEqual(self.root.winfo_width(), width)
                self.assertEqual(self.root.winfo_height(), height)
                self.assertIn(long_location, self.photo.detail.get())
                self.assertGreaterEqual(detail_label.winfo_height(), detail_label.winfo_reqheight())
                self.assertGreaterEqual(detail_label.winfo_width(), int(detail_label.cget("wraplength")))

                tree_width = self.photo.tree.winfo_width()
                self.assertEqual(int(self.photo.tree.column("location", "width")), 130,
                                 "A long scene name must not widen the fixed location column")
                for key in self.photo.tree.get_children():
                    for column in ("location", "status"):
                        bounds = self.photo.tree.bbox(key, column)
                        self.assertTrue(bounds, f"Missing visible {column} cell for {key}")
                        x, y, cell_width, cell_height = bounds
                        self.assertGreater(cell_width, 1)
                        self.assertGreater(cell_height, 1)
                        self.assertGreaterEqual(x, 0)
                        self.assertLessEqual(x + cell_width, tree_width,
                            f"{column} cell extends outside {tree_width}px tree: {bounds}")
                self.assertLessEqual(self.photo.tree.winfo_rootx() + tree_width,
                                     content.winfo_rootx() + content.winfo_width())
                for widget in controls:
                    self.assertTrue(widget.winfo_ismapped())
                    x = widget.winfo_rootx() - content.winfo_rootx()
                    y = widget.winfo_rooty() - content.winfo_rooty()
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + widget.winfo_width(), content.winfo_width())
                    self.assertLessEqual(y + widget.winfo_height(), content.winfo_height())

                reachable = set()
                for fraction in (0, 0.25, 0.5, 0.75, 1):
                    page.canvas.yview_moveto(fraction)
                    self.root.update()
                    top = page.canvas.winfo_rooty()
                    bottom = top + page.canvas.winfo_height()
                    for widget in controls:
                        if (widget.winfo_rooty() >= top and
                                widget.winfo_rooty() + widget.winfo_height() <= bottom):
                            hit = self.root.winfo_containing(
                                widget.winfo_rootx() + widget.winfo_width() // 2,
                                widget.winfo_rooty() + widget.winfo_height() // 2)
                            self.assertIs(hit, widget, f"Covered control: {widget.cget('text')}")
                            reachable.add(widget)
                self.assertEqual(reachable, set(controls),
                                 "Every page action must be reachable through normal vertical scrolling")
        self.adapter.snapshot.assert_not_called()
        self.adapter.activate_next.assert_not_called()

    def test_reordered_refresh_restores_semantic_selection_and_keeps_filters(self):
        self.photo.query.set("角色甲")
        self.photo.mode.set("仅未完成")
        self.photo.filter_rows()
        self.select()
        old_identity = self.photo.selected_row()["identity"]
        self.adapter.snapshot.return_value = activated_checklist(reorder=True)
        self.photo.activate()
        event = self.await_event()
        with patch.object(self.photo.tree, "see", wraps=self.photo.tree.see) as see:
            self.deliver(event)
            see.assert_called_with("0")
        self.assertEqual(self.photo.query.get(), "角色甲")
        self.assertEqual(self.photo.mode.get(), "仅未完成")
        self.assertEqual(self.photo.tree.selection(), ("0",))
        self.assertEqual(self.photo.selected_row()["sub_id"], 12)
        self.assertNotEqual(self.photo.selected_row()["identity"], old_identity)
        self.assertEqual(list(self.photo.rows), ["0"])

    def test_actionable_filter_removes_activated_row_without_selecting_another(self):
        self.photo.mode.set("当前可激活")
        self.photo.filter_rows()
        self.select()
        self.photo.activate()
        self.finish()
        self.assertEqual(self.photo.mode.get(), "当前可激活")
        self.assertEqual([row["sub_id"] for row in self.photo.rows.values()], [21])
        self.assertEqual(self.photo.tree.selection(), ())
        self.assertIsNone(self.photo.selected_row())
        self.assertIn("筛选", self.photo.note.get())
        self.assertIn("已激活", self.photo.note.get())
        self.assertEqual(str(self.photo.activate_button["state"]), "disabled")

    def test_refresh_failure_preserves_success_and_invalidates_all_old_targets(self):
        self.select()
        self.adapter.snapshot.side_effect = RuntimeError("显示读取失败测试")
        self.photo.activate()
        event = self.finish()
        self.assertIsNone(event[2], "A display refresh failure must not become an action failure")
        self.assertIs(self.app.adapter, self.game)
        self.assertIs(self.photo.adapter, self.adapter)
        self.assert_no_write_target()
        self.assertIn("已激活", self.photo.note.get())
        self.assertIn("自动刷新失败", self.photo.note.get())
        self.assertIn("重复", self.photo.note.get())
        self.assertIn("待刷新", self.photo.summary.get())
        self.assertIn("已激活", self.app.status.get())
        self.photo.activate()
        self.adapter.activate_next.assert_called_once()
        self.adapter.snapshot.assert_called_once_with()
        self.showerror.assert_not_called()

    def test_refused_action_does_not_refresh_or_retry(self):
        self.select()
        self.adapter.activate_next.side_effect = Refused("当前前提发生变化，未调用")
        self.photo.activate()
        event = self.finish()
        self.assertIsNone(event[2])
        self.assertTrue(event[1]["not_called"])
        self.adapter.activate_next.assert_called_once()
        self.adapter.snapshot.assert_not_called()
        self.assert_no_write_target()
        self.assertIn("未调用", self.photo.note.get())
        self.assertIs(self.app.adapter, self.game)

    def test_manual_read_after_automatic_read_failure_recovers_without_reactivation(self):
        self.select()
        self.adapter.snapshot.side_effect = [Refused("读取期间正在转场"), activated_checklist()]
        self.photo.activate()
        self.finish()
        self.assert_no_write_target()
        self.assertEqual(str(self.photo.detect_button["state"]), "normal")
        self.photo.detect()
        self.finish()
        self.assertEqual(self.photo.state["summary"], "激活后的真实清单")
        self.assertEqual(self.adapter.snapshot.call_count, 2)
        self.adapter.activate_next.assert_called_once()
        self.showerror.assert_not_called()

    def test_unknown_action_propagates_and_real_poll_disconnects_without_refresh(self):
        self.select()
        self.adapter.activate_next.side_effect = UncertainWrite("调用结果未确认，禁止重发")
        self.photo.activate()
        self.photo.activate()
        event = self.await_event()
        self.assertIsInstance(event[2], UncertainWrite)
        self.deliver(event)
        self.adapter.activate_next.assert_called_once()
        self.adapter.snapshot.assert_not_called()
        self.assertIsNone(self.app.adapter)
        self.assertIsNone(self.photo.adapter)
        self.assert_no_write_target()
        self.showerror.assert_called_once()

    def test_only_explicit_verified_success_allows_automatic_read(self):
        for result in (dict(message="未验证"), dict(message="未验证", verified=False),
                       dict(message="非布尔成功", verified=1),
                       dict(message="未调用", verified=True, not_called=True)):
            with self.subTest(result=result):
                self.photo.render(checklist())
                self.select()
                self.adapter.activate_next.reset_mock()
                self.adapter.activate_next.return_value = result
                self.photo.activate()
                self.finish()
                self.adapter.activate_next.assert_called_once()
                self.adapter.snapshot.assert_not_called()
                self.assertIsNone(self.photo.state)
                self.assertEqual(str(self.photo.activate_button["state"]), "disabled")

    def test_late_success_after_disconnect_cannot_restore_state_or_status(self):
        self.select()
        self.photo.activate()
        event = self.await_event()
        self.app.shutdown_adapter()
        self.app.state = None
        self.app.status.set("已由用户断开")
        summary, note = self.photo.summary.get(), self.photo.note.get()
        self.deliver(event)
        self.assertIsNone(self.app.adapter)
        self.assertIsNone(self.photo.adapter)
        self.assert_no_write_target()
        self.assertEqual(self.photo.summary.get(), summary)
        self.assertEqual(self.photo.note.get(), note)
        self.assertEqual(self.app.status.get(), "已由用户断开")

    def test_disconnect_before_worker_starts_cancels_dispatch_and_followup_read(self):
        pending = []

        class DeferredThread:
            def __init__(self, *, target, daemon):
                pending.append(target)

            def start(self):
                pass

        self.select()
        # Retain the real work/queue code, controlling only when the OS worker
        # begins. Closing the connection before that point must cancel writes.
        with patch("app.threading.Thread", DeferredThread):
            self.photo.activate()
        self.assertEqual(len(pending), 1)
        self.assertTrue(self.app.busy)
        self.app.shutdown_adapter()
        self.app.state = None
        self.app.status.set("派发前已断开")
        pending[0]()
        self.finish()
        self.adapter.activate_next.assert_not_called()
        self.adapter.snapshot.assert_not_called()
        self.assert_no_write_target()
        self.assertEqual(self.app.status.get(), "派发前已断开")

    def test_late_success_cannot_overwrite_replacement_game_or_adapter(self):
        for replace in ("game", "adapter", "both"):
            with self.subTest(replace=replace):
                self.app.adapter = self.game
                self.photo.adapter = self.adapter
                self.photo.render(checklist())
                self.select()
                self.photo.activate()
                event = self.await_event()
                self.app.busy = False
                if replace in ("game", "both"):
                    self.app.adapter = self.new_game()
                if replace in ("adapter", "both"):
                    self.photo.adapter = self.new_adapter(self.app.adapter)
                replacement = dict(summary="新连接清单", rows=[])
                self.photo.render(replacement)
                self.photo.note.set("新连接说明")
                self.app.status.set("新连接状态")
                self.deliver(event)
                self.assertIs(self.photo.state, replacement)
                self.assertEqual(self.photo.summary.get(), "新连接清单")
                self.assertEqual(self.photo.note.get(), "新连接说明")
                self.assertEqual(self.app.status.get(), "新连接状态")

    def test_late_success_with_old_page_epoch_is_ignored(self):
        self.select()
        self.photo.activate()
        event = self.await_event()
        self.photo._epoch += 1
        self.app.busy = False
        newer = dict(summary="更新的页面结果", rows=[])
        self.photo.render(newer)
        self.app.status.set("更新的状态")
        self.deliver(event)
        self.assertIs(self.photo.state, newer)
        self.assertEqual(self.photo.summary.get(), "更新的页面结果")
        self.assertEqual(self.app.status.get(), "更新的状态")

    def test_late_manual_read_after_disconnect_cannot_repopulate_page(self):
        self.photo.detect()
        event = self.await_event()
        self.app.shutdown_adapter()
        self.app.state = None
        self.app.status.set("读取时断开")
        self.deliver(event)
        self.assert_no_write_target()
        self.assertIsNone(self.photo.adapter)
        self.assertEqual(self.app.status.get(), "读取时断开")
        self.adapter.snapshot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
