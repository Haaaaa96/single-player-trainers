"""Normal dual-cultivation entry uses a nullable external end notification.

The game caller clears r9 at RVA 0x14F7644 before StartGame; NotifyGameEnd
(0xACB6A0) checks that optional callback for null. These fixtures exercise the
normal caller shape instead of assuming every delegate is non-null.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dual_cultivation_adapter as dual
import dual_cultivation_ui as ui
from test_app import FakeVar, FakeWidget
from test_dual_jade import fixture
from write_guard import Refused


class DualNullableCallbackRegressionTests(unittest.TestCase):
    def setUp(self):
        identity = patch.object(dual, "process_identity", return_value=("game", 123))
        identity.start()
        self.addCleanup(identity.stop)
        self.adapter, self.fields = fixture("dual")
        self.fields.values[10, "m_ActionOnGameEnd"] = 0

    def test_normal_game_caller_with_null_notification_can_complete(self):
        state = self.adapter.snapshot()
        self.assertTrue(state["active"])
        self.assertTrue(state["can_solve"], state["reason"])
        self.assertEqual(state["phase"], 1)
        self.assertEqual(state["native"]["final_callback"], "0x0")
        self.assertEqual(state["native"]["completed"], "0x32")
        prepared = self.adapter.prepare_solve(state)
        self.assertEqual(prepared["native"]["method_info"], "0x999")
        self.adapter.native.solve.assert_not_called()

    def test_optional_notification_may_still_be_nonnull(self):
        self.fields.values[10, "m_ActionOnGameEnd"] = 51
        self.assertTrue(self.adapter.snapshot()["can_solve"])

    def test_actual_settlement_delegate_is_still_required(self):
        self.fields.values[20, "m_Completed"] = 0
        state = self.adapter.snapshot()
        self.assertFalse(state["can_solve"])
        self.assertIn("结算回调", state["reason"])
        with self.assertRaises(Refused):
            self.adapter.prepare_solve(state)
        self.assertEqual(self.fields.methods, [])

    def test_optional_callback_change_invalidates_shown_round(self):
        for before, after in ((0, 51), (51, 0), (51, 52)):
            with self.subTest(before=before, after=after):
                self.fields.values[10, "m_ActionOnGameEnd"] = before
                shown = self.adapter.snapshot()
                self.fields.values[10, "m_ActionOnGameEnd"] = after
                current = self.adapter.snapshot()
                self.assertNotEqual(shown["native"]["round_key"], current["native"]["round_key"])
                with self.assertRaises(Refused):
                    self.adapter.prepare_solve(shown)
        self.assertEqual(self.fields.methods, [])

    def test_start_overlay_requires_explicit_game_start_and_refresh(self):
        self.fields.values[20, "m_Phase"] = 0
        waiting = self.adapter.snapshot()
        self.assertFalse(waiting["can_solve"])
        self.assertIn("尚未开始", waiting["reason"])
        self.assertIn("游戏界面提示", waiting["reason"])
        self.fields.values[20, "m_Phase"] = 1
        with self.assertRaises(Refused):
            self.adapter.prepare_solve(waiting)
        running = self.adapter.snapshot()
        self.assertEqual(waiting["identity"], running["identity"])
        self.assertTrue(self.adapter.prepare_solve(running)["can_solve"])

    def test_pause_loading_expiry_and_settlement_still_disable(self):
        cases = [(20, "m_IsPresentationReady", False, "加载"),
                 (20, "m_TimeRemaining", 0., "时间"),
                 (20, "m_Phase", 2, "结算"),
                 (20, "m_Phase", 3, "结算"),
                 (10, "m_SettlementStarted", True, "结算"),
                 (10, "m_ResultCallbackInvoked", True, "结算")]
        for obj, field, value, reason in cases:
            with self.subTest(field=field, value=value):
                previous = self.fields.values[obj, field]
                self.fields.values[obj, field] = value
                state = self.adapter.snapshot()
                self.assertFalse(state["can_solve"])
                self.assertIn(reason, state["reason"])
                self.fields.values[obj, field] = previous
        self.fields.actionable = False
        state = self.adapter.snapshot()
        self.assertFalse(state["can_solve"])
        self.assertIn("暂停", state["reason"])

    def test_live_phase_change_after_read_still_refuses_dispatch(self):
        shown = self.adapter.snapshot()
        self.fields.values[20, "m_Phase"] = 2
        with self.assertRaises(Refused):
            self.adapter.prepare_solve(shown)
        self.assertEqual(self.fields.methods, [])


class DualPanelReadRefreshRegressionTests(unittest.TestCase):
    def setUp(self):
        self.panel = ui.DualCultivationPanel.__new__(ui.DualCultivationPanel)
        self.panel.app = SimpleNamespace(
            busy=False, adapter=SimpleNamespace(write_enabled=True, blocked=False),
            work=Mock(), status=FakeVar())
        self.panel.adapter = Mock(blocked=False)
        self.panel.state = None
        for name in ("summary", "note"):
            setattr(self.panel, name, FakeVar())
        for name in ("button", "detect_button"):
            setattr(self.panel, name, FakeWidget())
        pending = patch.object(ui, "native_calls_pending", return_value=False)
        self.pending = pending.start()
        self.addCleanup(pending.stop)
        identity = patch.object(dual, "process_identity", return_value=("game", 123))
        identity.start()
        self.addCleanup(identity.stop)
        self.adapter, self.fields = fixture("dual")
        self.fields.values[10, "m_ActionOnGameEnd"] = 0

    def test_reading_normal_nullable_round_enables_button_without_solving(self):
        self.panel.render(self.adapter.snapshot())
        self.assertEqual(self.panel.button.options["state"], "normal")
        self.assertIn("进行中", self.panel.summary.get())
        self.panel.app.work.assert_not_called()
        self.panel.adapter.solve.assert_not_called()

    def test_reading_after_game_start_reenables_previously_disabled_button(self):
        self.fields.values[20, "m_Phase"] = 0
        self.panel.render(self.adapter.snapshot())
        self.assertEqual(self.panel.button.options["state"], "disabled")
        self.assertEqual(self.panel.detect_button.options["state"], "normal")
        self.assertIn("尚未开始", self.panel.summary.get())
        self.assertIn("重新读取", ui.DualCultivationPanel.explanation)
        self.fields.values[20, "m_Phase"] = 1
        self.panel.render(self.adapter.snapshot())
        self.assertEqual(self.panel.button.options["state"], "normal")
        self.panel.adapter.solve.assert_not_called()

    def test_nullable_callback_does_not_bypass_connection_safety(self):
        state = self.adapter.snapshot()
        self.panel.app.adapter.write_enabled = False
        self.panel.render(state)
        self.assertEqual(self.panel.button.options["state"], "disabled")
        self.panel.app.adapter.write_enabled = True
        self.pending.return_value = True
        self.panel.render(state)
        self.assertEqual(self.panel.button.options["state"], "disabled")
        self.panel.solve()
        self.panel.app.work.assert_not_called()


if __name__ == "__main__":
    unittest.main()
