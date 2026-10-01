"""Fake widgets only: UI prevents stale/range-invalid calls, unknown bubbles up."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import alchemy_ui as ui
from test_app import FakeVar, FakeWidget, FakeTree
from write_guard import Refused, UncertainWrite


class AlchemyUiTests(unittest.TestCase):
    def setUp(self):
        self.p = ui.AlchemyPanel.__new__(ui.AlchemyPanel)
        self.p.app = SimpleNamespace(busy=False, adapter=Mock(), root=Mock(), work=Mock(), status=FakeVar())
        self.p.adapter, self.p.talents = Mock(), Mock()
        self.p.qte_note, self.p.talent_note, self.p.rank = FakeVar(), FakeVar(), FakeVar()
        for name in ("detect_button", "solve_button", "talent_detect", "entry", "set_button"):
            setattr(self.p, name, FakeWidget())
        self.p.tree = FakeTree()
        self.p.state = dict(active=True, can_solve=True, reason="", identity=(1,), values=dict(progress=100, maximum=1000))
        self.p.talent_state = dict(can_edit=True, reason="", player_level=5, identity=(2,),
            rows={"1000001": dict(name="灵视扩界", value=1, maximum=2, note="迷雾探索范围扩大")})
        self.p.tree.insert("", "end", iid="1000001", values=())
        self.p.tree.selection_set("1000001")
        self.pending = patch.object(ui, "native_calls_pending", return_value=False).start()
        self.warning = patch.object(ui.messagebox, "showwarning").start()
        self.addCleanup(patch.stopall)

    def test_pending_or_busy_never_dispatches(self):
        self.pending.return_value = True
        self.p.rank.set("2")
        self.p.solve(); self.p.set_talent(); self.p.update_enabled(True)
        self.p.app.work.assert_not_called()
        self.assertEqual(self.p.solve_button.options["state"], "disabled")
        self.assertEqual(self.p.set_button.options["state"], "disabled")

    def test_readonly_or_disconnected_render_never_reenables(self):
        state = self.p.state
        self.p.app.adapter.write_enabled = False
        self.p.render(state); self.p.select(); self.p.solve(); self.p.detect(); self.p.detect_talents()
        self.p.rank.set("2"); self.p.set_talent()
        self.p.app.work.assert_not_called()
        self.assertEqual(self.p.solve_button.options["state"], "disabled")
        self.assertEqual(self.p.detect_button.options["state"], "disabled")
        self.p.app.adapter = None
        self.p.render(state)
        self.assertEqual(self.p.set_button.options["state"], "disabled")

    def test_refresh_clears_old_targets_before_worker(self):
        self.p.detect()
        self.assertIsNone(self.p.state)
        self.assertEqual(self.p.solve_button.options["state"], "disabled")
        self.p.detect_talents()
        self.assertIsNone(self.p.talent_state)
        self.assertEqual(self.p.tree.selection(), ())
        self.assertEqual(self.p.rank.get(), "")

    def test_stale_not_called_clears_qte_selection(self):
        self.p.solve()
        job, done = self.p.app.work.call_args.args
        self.p.adapter.solve.side_effect = Refused("changed")
        done(job())
        self.assertIsNone(self.p.state)
        self.assertIn("未修改", self.p.app.status.get())

    def test_qte_uncertainty_reaches_global_stop(self):
        self.p.solve()
        job, _ = self.p.app.work.call_args.args
        self.p.adapter.solve.side_effect = UncertainWrite("unknown")
        with self.assertRaises(UncertainWrite):
            job()

    def test_talent_uncertainty_reaches_global_stop(self):
        self.p.rank.set("2"); self.p.set_talent()
        job, _ = self.p.app.work.call_args.args
        self.p.talents.set_value.side_effect = UncertainWrite("unknown")
        with self.assertRaises(UncertainWrite):
            job()

    def test_current_level_cap_is_checked_before_worker(self):
        for value in ("3", "5", "1.5", "nan"):
            self.p.rank.set(value); self.p.set_talent()
        self.p.app.work.assert_not_called()

    def test_talent_closed_context_is_required(self):
        self.p.talent_state["can_edit"] = False
        self.p.rank.set("2"); self.p.set_talent(); self.p.update_enabled(True)
        self.p.app.work.assert_not_called()
        self.assertEqual(self.p.entry.options["state"], "disabled")

    def test_disconnect_only_closes_connections(self):
        first, second = self.p.adapter, self.p.talents
        self.p.disconnect()
        first.close.assert_called_once(); second.close.assert_called_once()
        first.solve.assert_not_called(); second.set_value.assert_not_called()
        self.assertIsNone(self.p.state)
        self.assertIsNone(self.p.talent_state)


if __name__ == "__main__":
    unittest.main()
