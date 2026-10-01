"""UI request and target guards, without game handles or native calls."""
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app import App
from photostone_ui import PhotostonePanel
from persuasion_ui import PersuasionPanel


def rows():
    return dict(summary="测试清单", rows=[
        dict(name="角色甲", npc_id=1, sub_id=11, identity="one", stage="普通", success_count=1, max_success=1,
             status="已完成", reason="可以查看重玩影响", can_activate=False, can_force=True),
        dict(name="角色甲", npc_id=1, sub_id=12, identity="two", stage="精品", success_count=0, max_success=1,
             status="未完成", reason="前置满足", can_activate=True, can_force=True),
        dict(name="角色乙", npc_id=2, sub_id=1, stage="普通", success_count=None, max_success=1,
             status="无法判定", reason="未生成", can_activate=False, can_force=False)])


class InteractionUiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.cleanup_root)
        for path in ("app.native_calls_pending", "photostone_ui.native_calls_pending",
                     "dual_cultivation_ui.native_calls_pending"):
            p = patch(path, return_value=False)
            p.start()
            self.addCleanup(p.stop)
        self.app = App(self.root)
        self.app.work = Mock()
        self.photo = next(x for x in self.app.extensions if isinstance(x, PhotostonePanel))
        self.persuasion = next(x for x in self.app.extensions if isinstance(x, PersuasionPanel))

    def cleanup_root(self):
        for timer in self.root.tk.call("after", "info"):
            self.root.after_cancel(timer)
        self.root.destroy()

    def connect(self):
        self.app.adapter = SimpleNamespace(write_enabled=True, blocked=False, close=Mock())
        self.app.state = dict(items={}, currencies={})
        self.photo.adapter = SimpleNamespace(blocked=False, close=Mock(), activate_next=Mock(),
                                            preview_force=Mock(), force=Mock(), snapshot=Mock())
        self.photo.render(rows())

    def select(self, key):
        self.photo.tree.selection_set(key)
        self.photo.selected()

    def test_disconnected_or_readonly_callbacks_do_not_enable_actions(self):
        self.photo.render(rows())
        self.select("1")
        self.photo.activate()
        self.photo.preview_force()
        self.persuasion.render(dict(active=False, can_solve=True))
        self.persuasion.solve()
        self.app.work.assert_not_called()
        self.app.adapter = SimpleNamespace(write_enabled=False, blocked=False)
        self.photo.update_enabled(True)
        self.assertEqual(str(self.photo.activate_button["state"]), "disabled")
        self.assertEqual(str(self.persuasion.button["state"]), "disabled")

    def test_unknown_records_are_not_counted_as_unfinished(self):
        self.connect()
        self.photo.mode.set("仅未完成")
        self.photo.filter_rows()
        self.assertEqual(list(self.photo.rows), ["1"])
        self.photo.mode.set("已完成")
        self.photo.filter_rows()
        self.assertEqual(list(self.photo.rows), ["0"])

    def test_persuasion_loading_panel_renders_without_session_fields(self):
        self.connect()
        for reason in ("角色尚未就绪", "本局尚未建立"):
            with self.subTest(reason=reason):
                self.persuasion.render(dict(active=True, can_solve=False, reason=reason))
                self.assertEqual(str(self.persuasion.button["state"]), "disabled")
                self.assertIn(reason, self.persuasion.describe(self.persuasion.state))
        self.app.work.assert_not_called()

    def test_persuasion_complete_read_explains_disabled_reason_above_button(self):
        self.connect()
        self.persuasion.adapter = SimpleNamespace(blocked=False, close=Mock())
        state = dict(active=True, can_solve=False, npc_id=193803, topic_id=19380301,
                     progress=0, threshold=30, rounds=1, max_rounds=6, exit_delay_ms=10000)
        for reason in (
                "本次说服已结束或正在倒计时结算，请在游戏内继续。",
                "说服界面已暂停或暂不可交互，请恢复后重新读取。",
                "游戏正在请求回复、窥心或提交输入，请等待结束后重新读取。",
                "NPC 已结束本次话题或切换了对话，请刷新。"):
            with self.subTest(reason=reason):
                self.persuasion.render(dict(state, reason=reason))
                self.assertIn("当前不可操作：" + reason, self.persuasion.summary.get())
                self.assertIn("说服进度 0 / 30", self.persuasion.summary.get())
                self.assertIn("成功后保留约 10 秒的结果倒计时", self.persuasion.summary.get())
                self.assertEqual(str(self.persuasion.button["state"]), "disabled")
                self.persuasion.solve()
        self.app.work.assert_not_called()

    def test_persuasion_unready_read_without_reason_has_explicit_fallback(self):
        self.connect()
        self.persuasion.render(dict(active=True, can_solve=False, npc_id=1, topic_id=2,
                                    progress=0, rounds=1, max_rounds=6, exit_delay_ms=10000))
        self.assertIn("当前不可操作：本局尚未就绪", self.persuasion.summary.get())
        self.assertEqual(str(self.persuasion.button["state"]), "disabled")

    def test_persuasion_ready_read_displays_actionable_state_and_enables_button(self):
        self.connect()
        self.persuasion.adapter = SimpleNamespace(blocked=False, close=Mock())
        self.persuasion.render(dict(active=True, can_solve=True, reason="", npc_id=1, topic_id=2,
                                    name="角色甲", topic="话题乙", progress=0, threshold=30,
                                    rounds=1, max_rounds=6, exit_delay_ms=10000))
        self.assertIn("角色 角色甲 · 话题 话题乙", self.persuasion.summary.get())
        self.assertIn("当前可操作：可判定本局说服成功。", self.persuasion.summary.get())
        self.assertNotIn("当前不可操作", self.persuasion.summary.get())
        self.assertEqual(str(self.persuasion.button["state"]), "normal")
        self.app.work.assert_not_called()

    def test_force_requires_preview_and_explicit_selected_stage_confirmation(self):
        self.connect()
        self.select("0")
        self.photo.confirmed.set(True)
        self.photo.force()
        self.app.work.assert_not_called()
        self.photo.preview_force()
        job, callback = self.app.work.call_args.args
        preview = dict(message="角色甲普通：将清除成功次数 1", row=dict(self.photo.selected_row()))
        self.photo.adapter.preview_force.return_value = preview
        callback(job())
        self.assertFalse(self.photo.confirmed.get())
        self.assertEqual(str(self.photo.force_button["state"]), "disabled")
        self.photo.confirmed.set(True)
        self.photo.update_enabled(True)
        self.assertEqual(str(self.photo.force_button["state"]), "normal")
        self.select("1")
        self.assertIsNone(self.photo.preview)
        self.assertFalse(self.photo.confirmed.get())

    def test_late_force_preview_cannot_attach_to_another_selected_stage(self):
        self.connect()
        self.select("0")
        self.photo.preview_force()
        _, callback = self.app.work.call_args.args
        self.select("1")
        callback(dict(message="旧目标"))
        self.assertIsNone(self.photo.preview)

    def test_force_rechecks_selection_before_delayed_tree_event(self):
        self.connect()
        self.select("0")
        self.photo.preview = dict(message="原目标", row=dict(self.photo.selected_row()))
        self.photo.confirmed.set(True)
        self.photo.tree.selection_set("1")  # Do not deliver <<TreeviewSelect>> yet.
        self.photo.force()
        self.app.work.assert_not_called()

    def test_activate_clears_target_before_worker_and_cannot_double_submit(self):
        self.connect()
        self.select("1")
        adapter = self.photo.adapter
        self.photo.activate()
        self.assertIsNone(self.photo.state)
        self.photo.activate()
        self.app.work.assert_called_once()
        adapter.activate_next.assert_not_called()
        job, callback = self.app.work.call_args.args
        adapter.activate_next.return_value = dict(message="已激活", verified=True)
        refreshed = rows()
        refreshed["rows"][1].update(status="已激活", can_activate=False)
        adapter.snapshot.return_value = refreshed
        callback(job())
        adapter.activate_next.assert_called_once()
        adapter.snapshot.assert_called_once()
        self.assertEqual(self.photo.selected_row()["status"], "已激活")
        self.assertEqual(str(self.photo.activate_button["state"]), "disabled")

    def test_busy_or_native_pending_cannot_dispatch_cached_target(self):
        self.connect()
        self.select("1")
        self.app.busy = True
        self.photo.activate()
        self.photo.preview_force()
        self.app.busy = False
        with patch("photostone_ui.native_calls_pending", return_value=True):
            self.photo.activate()
            self.photo.update_enabled(True)
            self.assertEqual(str(self.photo.activate_button["state"]), "disabled")
        self.app.work.assert_not_called()

    def test_disconnect_invalidates_preview_and_selection(self):
        self.connect()
        self.select("0")
        self.photo.preview = dict(message="测试")
        self.photo.confirmed.set(True)
        self.app.shutdown_adapter()
        self.assertIsNone(self.photo.state)
        self.assertIsNone(self.photo.preview)
        self.assertEqual(self.photo.tree.get_children(), ())
        self.assertFalse(self.photo.confirmed.get())


if __name__ == "__main__":
    unittest.main()
