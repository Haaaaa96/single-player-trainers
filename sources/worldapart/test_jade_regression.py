"""Completion display and exchange eligibility regression; no game process."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import jade_adapter as jade
import dual_cultivation_ui as common_ui
from jade_ui import JadePanel
from test_app import FakeVar, FakeWidget
from test_dual_jade import fixture
from write_guard import Refused, UncertainWrite


class JadeCompletionTests(unittest.TestCase):
    def setUp(self):
        p = patch.object(jade, "process_identity", return_value=("game", 123))
        p.start()
        self.addCleanup(p.stop)
        self.adapter, self.reader = fixture("jade")
        self.shown = self.adapter.snapshot()
        self.outcome = dict(fully_revealed=True, record_verified=True,
                            instance_id="99", current_value=433)

    def finish(self, *, can_exchange=False):
        outcome = self.adapter.verify_native(self.outcome, self.shown)
        self.adapter.native.solve.return_value = dict(outcome, status="verified")
        fresh = dict(self.shown, ratio=1.0, current_value=433, can_solve=False,
                     can_exchange=can_exchange, exchanged=False)
        self.adapter.snapshot = Mock(return_value=fresh)
        return fresh

    def test_verified_result_already_contains_completed_values_before_display_refresh(self):
        result = self.adapter.verify_native(self.outcome, self.shown)
        self.assertEqual(result["display_state"]["ratio"], 1.0)
        self.assertEqual(result["display_state"]["current_value"], 433)
        self.assertIsNone(result["display_state"]["can_exchange"])
        self.assertFalse(result["display_state"]["can_solve"])
        self.assertIn("不保证达到兑换门槛", result["message"])
        self.assertNotIn("native", result["display_state"])
        self.assertEqual(self.shown["ratio"], .25)

    def test_complete_but_ineligible_is_success_not_a_reveal_failure(self):
        self.finish()
        result = self.adapter.solve(self.shown)
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["display_state"]["can_exchange"])
        self.assertIn("已全部揭示，但游戏当前未开放兑换", result["message"])
        self.adapter.native.solve.assert_called_once_with(self.shown)

    def test_eligible_game_flag_is_shown_without_automatically_exchanging(self):
        self.finish(can_exchange=True)
        result = self.adapter.solve(self.shown)
        self.assertTrue(result["display_state"]["can_exchange"])
        self.assertIn("游戏当前允许选择兑换", result["message"])
        self.adapter.native.solve.assert_called_once()

    def test_read_failure_preserves_verified_progress_value_and_no_retry(self):
        for error in (Refused("loading"), OSError("gone")):
            with self.subTest(error=type(error).__name__):
                self.finish()
                self.adapter.native.solve.reset_mock()
                self.adapter.snapshot.side_effect = error
                result = self.adapter.solve(self.shown)
                self.assertEqual(result["display_state"]["ratio"], 1.0)
                self.assertEqual(result["display_state"]["current_value"], 433)
                self.assertIsNone(result["display_state"]["can_exchange"])
                self.assertIn("刷新失败", result["message"])
                self.assertFalse(self.adapter.blocked)
                self.adapter.native.solve.assert_called_once()

    def test_other_stone_cannot_supply_exchange_status_for_completed_stone(self):
        fresh = self.finish(can_exchange=True)
        fresh["identity"] = ("different stone",)
        result = self.adapter.solve(self.shown)
        self.assertIsNone(result["display_state"]["can_exchange"])
        self.assertEqual(result["display_state"]["instance_id"], "99")
        self.assertIn("当前选择或界面已变化", result["message"])

    def test_closed_panel_preserves_this_stones_verified_result(self):
        self.finish()
        self.adapter.snapshot.return_value = dict(active=False)
        result = self.adapter.solve(self.shown)
        self.assertEqual(result["display_state"]["current_value"], 433)
        self.assertIsNone(result["display_state"]["can_exchange"])

    def test_later_changed_value_or_ratio_is_not_misattributed(self):
        for key, value in (("ratio", .5), ("current_value", 700)):
            with self.subTest(key=key):
                fresh = self.finish(can_exchange=True)
                fresh[key] = value
                result = self.adapter.solve(self.shown)
                self.assertEqual(result["display_state"]["current_value"], 433)
                self.assertEqual(result["display_state"]["ratio"], 1.0)
                self.assertIsNone(result["display_state"]["can_exchange"])
                self.assertIn("完成后又发生变化", result["message"])

    def test_unknown_blocks_and_does_not_do_display_read(self):
        self.adapter.snapshot = Mock()
        self.adapter.native.solve.side_effect = UncertainWrite("unconfirmed")
        with self.assertRaises(UncertainWrite):
            self.adapter.solve(self.shown)
        self.assertTrue(self.adapter.blocked)
        self.adapter.snapshot.assert_not_called()

    def test_pre_dispatch_refusal_does_not_claim_or_refresh_success(self):
        self.adapter.snapshot = Mock()
        self.adapter.native.solve.side_effect = Refused("busy")
        with self.assertRaises(Refused):
            self.adapter.solve(self.shown)
        self.assertFalse(self.adapter.blocked)
        self.adapter.snapshot.assert_not_called()

    def test_refresh_of_completed_low_value_stone_explains_exchange_separately(self):
        self.reader.values[30, "RevealRatio"] = 1.0
        self.reader.values[30, "CurrentValue"] = 433
        self.reader.values[20, "m_CanScratch"] = False
        state = self.adapter.snapshot()
        self.assertFalse(state["can_solve"])
        self.assertFalse(state["can_exchange"])
        self.assertIn("已全部揭示，但游戏当前未开放兑换", state["reason"])

    def test_exchange_status_does_not_invent_a_threshold(self):
        state = dict(ratio=1.0, can_exchange=False, current_value=433)
        text = jade.exchange_status(state)
        self.assertIn("估值或原石类型", text)
        self.assertNotIn("500", text)
        self.assertIn("已经完成兑换", jade.exchange_status(dict(state, exchanged=True)))


class JadeUiRegressionTests(unittest.TestCase):
    def setUp(self):
        self.panel = JadePanel.__new__(JadePanel)
        self.panel.app = SimpleNamespace(busy=False, adapter=SimpleNamespace(write_enabled=True, blocked=False),
                                         work=Mock(), status=FakeVar())
        self.panel.adapter = Mock(blocked=False)
        self.panel.state = dict(active=True, can_solve=True, item_id=930107, instance_id="5",
                                ratio=0.0, current_value=500, blooms=1, cracks=1, can_exchange=False)
        self.panel.summary = FakeVar(self.panel.describe(self.panel.state))
        self.panel.note = FakeVar()
        self.panel.button, self.panel.detect_button = FakeWidget(), FakeWidget()
        p = patch.object(common_ui, "native_calls_pending", return_value=False)
        self.pending = p.start()
        self.addCleanup(p.stop)
        self.display = dict(self.panel.state, ratio=1.0, current_value=433, can_solve=False,
                            result_snapshot=True, can_exchange=False, exchanged=False)
        self.panel.adapter.solve.return_value = dict(message="已全部揭示，但当前未满足兑换条件。",
                                                     display_state=self.display, status="verified")

    def run_solve(self):
        self.panel.solve()
        job, success = self.panel.app.work.call_args.args
        success(job())

    def test_zero_500_summary_becomes_100_433_and_exchange_remains_ineligible(self):
        self.run_solve()
        self.assertIn("已揭示 100.0% · 当前估值 433", self.panel.summary.get())
        self.assertNotIn("当前估值 500", self.panel.summary.get())
        self.assertIn("游戏当前未开放兑换", self.panel.summary.get())
        self.assertIn("本次已完成原石", self.panel.summary.get())
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.button.options["state"], "disabled")

    def test_refresh_failure_keeps_verified_summary_with_unknown_exchange(self):
        self.display["can_exchange"] = None
        self.run_solve()
        self.assertIn("100.0%", self.panel.summary.get())
        self.assertIn("433", self.panel.summary.get())
        self.assertIn("兑换状态未读到", self.panel.summary.get())

    def test_definite_refusal_clears_stale_numbers_and_never_claims_completed(self):
        self.panel.adapter.solve.side_effect = Refused("paused")
        self.run_solve()
        self.assertIn("未派发", self.panel.summary.get())
        self.assertNotIn("500", self.panel.summary.get())
        self.assertEqual(self.panel.note.get(), "paused")

    def test_unknown_propagates_to_global_stop_and_cannot_be_clicked_again(self):
        self.panel.adapter.solve.side_effect = UncertainWrite("unknown")
        self.panel.solve()
        job, _ = self.panel.app.work.call_args.args
        with self.assertRaises(UncertainWrite):
            job()
        self.assertIn("尚未确认", self.panel.summary.get())
        self.assertIsNone(self.panel.state)
        self.panel.solve()
        self.assertEqual(self.panel.app.work.call_count, 1)

    def test_late_result_cannot_render_into_a_different_connection(self):
        self.panel.solve()
        job, success = self.panel.app.work.call_args.args
        self.panel.app.adapter = SimpleNamespace(write_enabled=True, blocked=False)
        success(job())
        self.assertNotIn("100.0%", self.panel.summary.get())

    def test_readonly_busy_or_pending_does_not_dispatch(self):
        self.panel.app.adapter.write_enabled = False
        self.panel.solve()
        self.panel.app.adapter.write_enabled = True
        self.panel.app.busy = True
        self.panel.solve()
        self.panel.app.busy = False
        self.pending.return_value = True
        self.panel.solve()
        self.panel.app.work.assert_not_called()


if __name__ == "__main__":
    unittest.main()
