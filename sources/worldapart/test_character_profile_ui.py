"""Profile UI flow with fake widgets; no Tk window or game."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import character_profile_ui as ui
from test_character_profile import target
from test_app import FakeVar, FakeWidget
from ui_errors import RefreshAfterWriteError
from write_guard import Refused, UncertainWrite


class ProfileUiTests(unittest.TestCase):
    def setUp(self):
        self.panel = ui.CharacterProfilePanel.__new__(ui.CharacterProfilePanel)
        self.panel.app = SimpleNamespace(busy=False,adapter=SimpleNamespace(write_enabled=True),root=Mock(),work=Mock(),status=FakeVar())
        self.panel.adapter = Mock()
        self.panel.controls = {key:SimpleNamespace(current=FakeVar(),input=FakeVar(),note=FakeVar(),entry=FakeWidget(),button=FakeWidget()) for key in ui.FIELDS}
        self.panel.note,self.panel.detect_button = FakeVar(),FakeWidget()
        self.shown = target()
        self.state = dict(can_edit=True,rows={"reserve_exp":dict(name="丹田灵气（储备）",target=self.shown,note="不直接提升修为")})
        self.pending = patch.object(ui,"native_calls_pending",return_value=False).start()
        self.warning = patch.object(ui.messagebox,"showwarning").start()
        self.addCleanup(patch.stopall)
        self.panel.render(self.state)
        self.widgets = self.panel.controls["reserve_exp"]

    def test_refresh_replaces_input_and_explains_target(self):
        self.widgets.input.set("999")
        self.panel.render(self.state)
        self.assertEqual(self.widgets.current.get(),"100")
        self.assertEqual(self.widgets.input.get(),"100")
        self.assertIn("不直接提升修为",self.widgets.note.get())

    def test_displayed_limit_is_from_this_target_and_names_its_source(self):
        self.panel.render(dict(can_edit=True,rows={"reserve_exp":dict(
            target=replace(self.shown,maximum=2500),limit_source="当前境界配置",note="储备") }))
        self.assertIn("0～2500",self.widgets.note.get())
        self.assertIn("当前境界配置",self.widgets.note.get())

    def test_cross_key_target_is_not_editable(self):
        self.panel.render(dict(can_edit=True,rows={"reserve_exp":dict(target=replace(self.shown,key="other"))}))
        self.widgets.input.set("101")
        self.panel.change("reserve_exp")
        self.assertEqual(self.widgets.entry.options["state"],"disabled")
        self.panel.app.work.assert_not_called()

    def test_invalid_input_never_dispatches(self):
        for text in ("-1","100.1","1e3","1101","100"):
            self.widgets.input.set(text)
            self.panel.change("reserve_exp")
        self.panel.app.work.assert_not_called()
        self.assertEqual(self.warning.call_count,5)

    def test_busy_native_pending_readonly_disconnected_and_unsafe_scene_refuse(self):
        self.widgets.input.set("101")
        for flag in ("busy","pending","readonly","disconnected","scene"):
            with self.subTest(flag=flag):
                self.panel.app.busy = flag=="busy"
                self.pending.return_value = flag=="pending"
                self.panel.app.adapter = None if flag=="disconnected" else SimpleNamespace(write_enabled=flag!="readonly")
                self.panel.state["can_edit"] = flag!="scene"
                self.panel.update_enabled(True)
                self.panel.change("reserve_exp")
                self.assertEqual(self.widgets.entry.options["state"],"disabled")
        self.panel.app.work.assert_not_called()

    def test_delayed_job_uses_displayed_target_and_value(self):
        self.widgets.input.set("101")
        self.panel.change("reserve_exp")
        job,success = self.panel.app.work.call_args.args
        self.widgets.input.set("199")
        self.panel.adapter.snapshot.return_value = dict(can_edit=True,rows={"reserve_exp":dict(name="丹田灵气（储备）",target=replace(self.shown,value=101))})
        success(job())
        self.panel.adapter.set_value.assert_called_once_with(self.shown,101)
        self.assertEqual(self.widgets.input.get(),"101")
        self.assertIn("100 → 101",self.panel.app.status.get())

    def test_refused_write_clears_all_old_targets(self):
        self.widgets.input.set("101")
        self.panel.change("reserve_exp")
        job,success = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = Refused("角色变化")
        success(job())
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.widgets.input.get(),"")
        self.assertEqual(self.widgets.current.get(),"—")
        self.assertEqual(self.widgets.entry.options["state"],"disabled")
        self.assertIn("未修改",self.panel.app.status.get())

    def test_uncertain_write_propagates_instead_of_not_written(self):
        self.widgets.input.set("101")
        self.panel.change("reserve_exp")
        job,_ = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = UncertainWrite("partial")
        with self.assertRaises(UncertainWrite):job()

    def test_postwrite_refresh_failure_is_not_presented_as_no_write(self):
        self.widgets.input.set("101")
        self.panel.change("reserve_exp")
        job,_ = self.panel.app.work.call_args.args
        self.panel.adapter.snapshot.side_effect = Refused("changed")
        with self.assertRaises(RefreshAfterWriteError):job()

    def test_refresh_clears_targets_immediately_and_refusal_keeps_them_clear(self):
        self.panel.detect()
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.widgets.input.get(),"")
        job,success = self.panel.app.work.call_args.args
        self.panel.adapter.snapshot.side_effect = Refused("场景变化")
        success(job())
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.widgets.entry.options["state"],"disabled")
        self.assertIn("场景变化",self.panel.note.get())

    def test_missing_or_uneditable_row_never_retains_input(self):
        self.panel.render(dict(can_edit=True,rows={"reserve_exp":dict(target=replace(self.shown,can_edit=False))}))
        self.assertEqual(self.widgets.input.get(),"")
        self.assertEqual(self.widgets.entry.options["state"],"disabled")
        self.panel.render(dict(can_edit=True,rows={}))
        self.assertEqual(self.widgets.current.get(),"—")

    def test_disconnect_closes_only_adapter_and_clears_state(self):
        adapter = self.panel.adapter
        self.panel.disconnect()
        adapter.close.assert_called_once()
        self.assertIsNone(self.panel.adapter)
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.widgets.input.get(),"")
        self.assertEqual(self.panel.detect_button.options["state"],"disabled")


if __name__ == "__main__":unittest.main()
