"""UI boundary tests: running puzzle is read-only; uncertain writes stop globally."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from meridian_ui import MeridianPanel, FIELDS
from meridian_write import MeridianTarget
from test_app import FakeVar, FakeWidget
from ui_errors import RefreshAfterWriteError
from write_guard import Refused, UncertainWrite


class MeridianUiTests(unittest.TestCase):
    def setUp(self):
        self.panel = MeridianPanel.__new__(MeridianPanel)
        p = self.panel
        p.app = SimpleNamespace(busy=False, adapter=Mock(), root=Mock(), work=Mock(), status=FakeVar())
        self.target = MeridianTarget("meridian_reveal", 0x1000, 1, ("round",), 0, 999, ((0x2000, "01"),))
        p.state = {"active": True, "can_edit": True, "paused": True,
                   "targets": {self.target.key: self.target}, "values": {self.target.key: 1}}
        p.resolver = Mock()
        p.inputs = {key: FakeVar("2") for key, _ in FIELDS}
        p.currents = {key: FakeVar() for key, _ in FIELDS}
        p.entries = {key: FakeWidget() for key, _ in FIELDS}
        p.buttons = {key: FakeWidget() for key, _ in FIELDS}
        p.note, p.summary, p.warning = FakeVar(), FakeVar(), FakeVar()
        p.detect_button, p.steps, p.cells = FakeWidget(), Mock(), Mock()
        p.solve_button, p.oneclick = FakeWidget(), None
        p.cells.get_children.return_value = ()
        patcher = patch("meridian_ui.messagebox.showwarning")
        self.warning = patcher.start()
        self.addCleanup(patcher.stop)

    def job(self, error=None):
        with patch("meridian_write.MeridianWriteOnce"), patch("meridian_write.set_meridian_value", side_effect=error):
            self.panel.change(self.target.key)
            job, success = self.panel.app.work.call_args.args
            return job(), success

    def test_running_round_disables_writes_even_with_stale_targets(self):
        self.panel.state["can_edit"] = False
        self.panel.update_enabled(True)
        self.assertEqual(self.panel.buttons[self.target.key].options["state"], "disabled")
        self.panel.change(self.target.key)
        self.panel.app.work.assert_not_called()

    def test_only_resolved_resource_can_be_edited(self):
        self.panel.update_enabled(True)
        self.assertEqual(self.panel.buttons[self.target.key].options["state"], "normal")
        self.assertEqual(self.panel.buttons["meridian_time"].options["state"], "disabled")
        self.panel.change("meridian_time")
        self.panel.app.work.assert_not_called()

    def test_bounds_reject_before_scheduling_work(self):
        self.panel.inputs[self.target.key].set("1000")
        self.panel.change(self.target.key)
        self.warning.assert_called_once()
        self.panel.app.work.assert_not_called()

    def test_known_no_write_invalidates_target_and_keeps_connection(self):
        adapter, resolver = self.panel.app.adapter, self.panel.resolver
        result, success = self.job(Refused("暂停已结束"))
        success(result)
        self.assertIs(self.panel.app.adapter, adapter)
        adapter.close.assert_not_called()
        resolver.snapshot.assert_not_called()
        self.assertIsNone(self.panel.state)
        self.assertIn("未修改", self.panel.app.status.get())
        self.assertEqual(self.panel.buttons[self.target.key].options["state"], "disabled")

    def test_uncertain_write_propagates_to_global_stop(self):
        with self.assertRaises(UncertainWrite):
            self.job(UncertainWrite("未确认"))
        self.panel.resolver.snapshot.assert_not_called()

    def test_refresh_failure_after_write_preserves_success_distinction(self):
        self.panel.resolver.snapshot.side_effect = Refused("局次结束")
        with self.assertRaises(RefreshAfterWriteError):
            self.job()

    def test_inactive_round_clears_old_inputs(self):
        self.panel.render({"active": False, "reason": "已结束"})
        self.assertEqual(self.panel.inputs[self.target.key].get(), "")
        self.assertEqual(self.panel.note.get(), "已结束")
        self.assertEqual(self.panel.entries[self.target.key].options["state"], "disabled")

    def test_readonly_values_still_visible_without_write_targets(self):
        self.panel.render({"active": True, "can_edit": False, "values": {self.target.key: 7}, "targets": {}})
        self.assertEqual(self.panel.inputs[self.target.key].get(), "7")
        self.assertIn("7", self.panel.currents[self.target.key].get())
        self.assertEqual(self.panel.entries[self.target.key].options["state"], "disabled")

    def test_paused_state_never_enables_or_schedules_oneclick(self):
        self.panel.update_enabled(True)
        self.assertEqual(self.panel.solve_button.options["state"], "disabled")
        self.panel.solve()
        self.panel.app.work.assert_not_called()

    def solve_job(self, error=None):
        p = self.panel
        p.state["can_solve"], p.state["paused"] = True, False
        p.state["can_edit"] = False
        bridge = Mock()
        bridge.solve.side_effect = error
        bridge.solve.return_value = {"message": "游戏已判胜，等待结算。"}
        with patch("meridian_ui.build_restore_plan", return_value={"can_restore": True}), \
                patch("meridian_oneclick.MeridianOneClick", return_value=bridge):
            p.solve()
            job, success = p.app.work.call_args.args
            return job(), success, bridge

    def test_oneclick_known_rejection_preserves_connection_and_clears_stale_board(self):
        result, success, _ = self.solve_job(Refused("局次变化"))
        success(result)
        self.assertFalse(self.panel.state["active"])
        self.assertIn("未调用", self.panel.app.status.get())
        self.assertIn("局次变化", self.panel.app.status.get())
        self.panel.app.adapter.record.assert_called_once_with(dict(
            operation="meridian_solve", status="not_called", called=False, reason="局次变化"))
        self.panel.app.adapter.close.assert_not_called()

    def test_detect_old_agent_disables_only_native_action_and_keeps_board(self):
        p = self.panel
        state = dict(p.state, can_solve=True)
        p.resolver.snapshot.return_value = state
        with patch("meridian_ui.native_connection_block_reason", return_value="请先保存并重启游戏"):
            p.detect()
            job, success = p.app.work.call_args.args
            success(job())
        self.assertTrue(p.state["active"])
        self.assertEqual(p.solve_button.options["state"], "disabled")
        self.assertEqual(p.buttons[self.target.key].options["state"], "normal")
        self.assertIn("重启游戏", p.note.get())
        p.app.work.reset_mock()
        p.solve()
        p.app.work.assert_not_called()

    def test_no_call_log_failure_does_not_hide_actual_reason(self):
        self.panel.app.adapter.record.side_effect = OSError("disk")
        result, success, _ = self.solve_job(Refused("请先保存并重启游戏"))
        success(result)
        self.assertIn("重启游戏", self.panel.app.status.get())
        self.assertNotIn("刷新当前棋盘", self.panel.note.get())

    def test_oneclick_uncertainty_propagates_and_never_claims_no_call(self):
        with self.assertRaises(UncertainWrite):
            self.solve_job(UncertainWrite("结果不确定"))
        self.assertNotIn("未调用", self.panel.app.status.get())

    def test_oneclick_win_reports_waiting_settlement_and_disables_repeat(self):
        result, success, _ = self.solve_job()
        success(result)
        self.assertIn("等待结算", self.panel.note.get())
        self.assertFalse(self.panel.state["active"])
        self.assertEqual(self.panel.solve_button.options["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
