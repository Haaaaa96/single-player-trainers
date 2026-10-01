"""Unified resource UI tests use fake widgets, never a game or Tk window."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import current_resources_ui as cu
from current_resources import StaminaTarget, RESOURCE_SPECS
from test_app import FakeVar, FakeWidget
from write_guard import Refused, UncertainWrite


class StaminaUiTests(unittest.TestCase):
    def setUp(self):
        self.panel = cu.StaminaPanel.__new__(cu.StaminaPanel)
        self.panel.app = SimpleNamespace(busy=False,adapter=Mock(),root=Mock(),work=Mock(),status=FakeVar())
        self.panel.adapter = Mock()
        self.panel.controls = {key: SimpleNamespace(current=FakeVar(), maximum=FakeVar(), input=FakeVar(), note=FakeVar(),
            entry=FakeWidget(), button=FakeWidget()) for key in RESOURCE_SPECS}
        self.panel.note, self.panel.detect_button = FakeVar(), FakeWidget()
        for name in ("current", "maximum", "input", "entry"):
            setattr(self.panel, name, getattr(self.panel.controls["current_stamina"], name))
        self.shown = StaminaTarget(50.,0x1000,("player",),((0x2000,"01000000"),))
        self.row = dict(target=self.shown,current=50.,maximum=None,can_edit=True,reason="")
        self.state = dict(rows={key: dict(self.row,target=replace(self.shown,key=key)) for key in RESOURCE_SPECS})
        self.pending = patch.object(cu,"native_calls_pending",return_value=False).start()
        self.warning = patch.object(cu.messagebox,"showwarning").start()
        self.addCleanup(patch.stopall)
        self.panel.render(self.state)

    def test_refresh_refills_current_without_guessing_maximum(self):
        self.panel.input.set("999")
        self.panel.render(self.state)
        self.assertEqual(self.panel.current.get(),"50")
        self.assertEqual(self.panel.input.get(),"50")
        self.assertIn("游戏实时核对",self.panel.maximum.get())

    def test_invalid_input_never_dispatches(self):
        for value in ("-1","1e99","1051","50"):
            self.panel.input.set(value)
            self.panel.change()
        self.panel.app.work.assert_not_called()
        self.assertEqual(self.warning.call_count,4)

    def test_busy_pending_and_unsafe_scene_all_block(self):
        self.panel.input.set("51")
        self.panel.app.busy = True
        self.panel.change()
        self.panel.app.busy = False
        self.pending.return_value = True
        self.panel.update_enabled(True)
        self.panel.change()
        self.assertEqual(self.panel.entry.options["state"],"disabled")
        self.pending.return_value = False
        self.panel.render(dict(rows={key: dict(row,can_edit=False,reason="战斗") for key,row in self.state["rows"].items()}))
        self.panel.change()
        self.panel.app.work.assert_not_called()

    def test_delayed_job_pins_shown_target_and_input(self):
        self.panel.input.set("51")
        self.panel.change()
        job,success = self.panel.app.work.call_args.args
        self.panel.render(dict(rows={"current_stamina":dict(self.row,target=replace(self.shown,value=60),current=60)}))
        self.panel.input.set("99")
        self.panel.adapter.set_value.return_value = dict(target=replace(self.shown,value=51),current=51,maximum=100,verified=True)
        success(job())
        self.panel.adapter.set_value.assert_called_once_with(self.shown,51)
        self.assertEqual(self.panel.input.get(),"51")
        self.assertIn("100",self.panel.maximum.get())
        self.assertIn("本次操作时",self.panel.maximum.get())
        self.assertIn("50 → 51",self.panel.app.status.get())
        for key in ("current_health", "current_mana"):
            self.assertEqual(self.panel.controls[key].entry.options["state"], "disabled")
            self.assertEqual(self.panel.controls[key].current.get(), "—")

    def test_maximum_rejection_clears_stale_target_and_does_not_claim_write(self):
        self.panel.input.set("51")
        self.panel.change()
        job,success = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = Refused("超过实际精力上限")
        success(job())
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.input.get(),"")
        self.assertEqual(self.panel.current.get(),"—")
        self.assertEqual(self.panel.app.status.get(),"当前精力未修改。")
        self.assertEqual(self.panel.entry.options["state"],"disabled")

    def test_unknown_result_propagates_to_global_stop(self):
        self.panel.input.set("51")
        self.panel.change()
        job,_ = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = UncertainWrite("unknown")
        with self.assertRaises(UncertainWrite):job()

    def test_disconnect_releases_bridge_and_clears_numbers(self):
        adapter = self.panel.adapter
        self.panel.disconnect()
        adapter.close.assert_called_once()
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.input.get(),"")
        self.assertEqual(self.panel.current.get(),"—")

    def test_selected_resource_pins_its_target_without_touching_other_inputs(self):
        self.panel.controls["current_health"].input.set("51")
        self.panel.controls["current_mana"].input.set("999")
        self.panel.change("current_health")
        job,success = self.panel.app.work.call_args.args
        shown = self.state["rows"]["current_health"]["target"]
        self.panel.adapter.set_value.return_value = dict(target=replace(shown,value=51),current=51,maximum=100,verified=True,resource_key=shown.key)
        success(job())
        self.panel.adapter.set_value.assert_called_once_with(shown,51)
        self.assertIn("当前生命：50 → 51",self.panel.app.status.get())
        self.assertEqual(self.panel.controls["current_mana"].input.get(), "")

    def test_zero_health_refused_before_job(self):
        self.panel.controls["current_health"].input.set("0")
        self.panel.change("current_health")
        self.panel.app.work.assert_not_called()
        self.warning.assert_called_once()

    def test_missing_health_does_not_disable_other_two_resources(self):
        state = dict(rows=dict(self.state["rows"]))
        state["rows"]["current_health"] = dict(target=None,can_edit=False,reason="未初始化")
        self.panel.render(state)
        self.assertEqual(self.panel.controls["current_health"].entry.options["state"], "disabled")
        self.assertEqual(self.panel.controls["current_mana"].entry.options["state"], "normal")
        self.assertEqual(self.panel.controls["current_stamina"].entry.options["state"], "normal")


if __name__ == "__main__":
    unittest.main()
