"""No display/game needed: stale target, uncertain outcomes and gating."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from dataclasses import replace
import crafting_ui as ui
from test_app import FakeVar, FakeWidget
from test_crafting_talents import target
from write_guard import Refused, UncertainWrite


class CraftingUiTests(unittest.TestCase):
    def setUp(self):
        self.panel=ui.CraftingPanel.__new__(ui.CraftingPanel)
        self.panel.app=SimpleNamespace(busy=False,adapter=SimpleNamespace(write_enabled=True),root=Mock(),work=Mock(),status=FakeVar())
        self.panel.adapter=Mock()
        for key in ('round_note','talent_note','current','input'):setattr(self.panel,key,FakeVar())
        for key in ('detect_button','complete_button','set_button','entry'):setattr(self.panel,key,FakeWidget())
        self.shown=target()
        self.state=dict(round=dict(can_complete=True,score=10,highest_tier=3,effect_count=2,activated_count=1),talents=dict(can_edit=True,target=self.shown))
        self.pending=patch.object(ui,'native_calls_pending',return_value=False).start()
        patch.object(ui.messagebox,'showwarning').start()
        self.addCleanup(patch.stopall)
        self.panel.render(self.state)

    def test_render_replaces_inputs_and_has_independent_round_talent_gates(self):
        self.panel.input.set('900')
        self.panel.render(dict(round=dict(can_complete=False,reason='not in board'),talents=self.state['talents']))
        self.assertEqual(self.panel.input.get(),'100')
        self.assertEqual(self.panel.complete_button.options['state'],'disabled')
        self.assertEqual(self.panel.set_button.options['state'],'normal')

    def test_busy_readonly_disconnected_pending_disable_every_operation(self):
        for flag in ('busy','readonly','disconnected','pending'):
            self.panel.app.busy=flag=='busy';self.pending.return_value=flag=='pending'
            self.panel.app.adapter=None if flag=='disconnected' else SimpleNamespace(write_enabled=flag!='readonly')
            self.panel.update_enabled(True);self.panel.complete();self.panel.set_talents();self.panel.detect()
            for key in ('detect_button','complete_button','set_button','entry'):
                self.assertEqual(getattr(self.panel,key).options['state'],'disabled')
        self.panel.app.work.assert_not_called()

    def test_completion_captures_target_and_clears_both_before_dispatch(self):
        shown=self.panel.state
        self.panel.complete()
        self.assertIsNone(self.panel.state);self.assertIsNone(self.panel.talent_state)
        self.assertEqual(self.panel.input.get(),'')
        job,success=self.panel.app.work.call_args.args
        self.panel.adapter.solve.return_value=dict(message='等待结果页')
        success(job())
        self.panel.adapter.solve.assert_called_once_with(shown)
        self.assertEqual(self.panel.complete_button.options['state'],'disabled')
        self.assertEqual(self.panel.round_note.get(),'等待结果页')

    def test_complete_uncertain_is_never_converted_to_not_called(self):
        self.panel.complete();job,_=self.panel.app.work.call_args.args
        self.panel.adapter.solve.side_effect=UncertainWrite('partial')
        with self.assertRaises(UncertainWrite):job()

    def test_complete_refusal_does_not_restore_old_target(self):
        self.panel.complete();job,success=self.panel.app.work.call_args.args
        self.panel.adapter.solve.side_effect=Refused('changed')
        success(job())
        self.assertIsNone(self.panel.state)
        self.assertIn('changed',self.panel.round_note.get())

    def test_talent_invalid_input_does_not_dispatch(self):
        for value in ('100','-1','1001','1.5','1e2'):
            self.panel.input.set(value);self.panel.set_talents()
        self.panel.app.work.assert_not_called()

    def test_talent_exact_shown_input_and_no_reusable_postwrite_target(self):
        self.panel.input.set('101');self.panel.set_talents()
        job,success=self.panel.app.work.call_args.args
        self.panel.input.set('999')
        self.panel.adapter.talents.set_value.return_value=replace(self.shown,value=101)
        success(job())
        self.panel.adapter.talents.set_value.assert_called_once_with(self.shown,101)
        self.assertEqual(self.panel.current.get(),'101')
        self.assertIsNone(self.panel.talent_state)
        self.assertEqual(self.panel.entry.options['state'],'disabled')

    def test_talent_uncertain_propagates(self):
        self.panel.input.set('101');self.panel.set_talents();job,_=self.panel.app.work.call_args.args
        self.panel.adapter.talents.set_value.side_effect=UncertainWrite('partial')
        with self.assertRaises(UncertainWrite):job()

    def test_read_failure_one_half_does_not_hide_other_half(self):
        self.panel.adapter.snapshot.side_effect=Refused('board unavailable')
        self.panel.adapter.talents.snapshot.return_value=self.state['talents']
        self.panel.detect();job,success=self.panel.app.work.call_args.args
        self.assertIsNone(self.panel.talent_state)
        success(job())
        self.assertIn('board unavailable',self.panel.round_note.get())
        self.assertEqual(self.panel.current.get(),'100')
        self.assertEqual(self.panel.set_button.options['state'],'normal')

    def test_disconnect_closes_and_clears(self):
        adapter=self.panel.adapter;self.panel.disconnect()
        adapter.close.assert_called_once()
        self.assertIsNone(self.panel.adapter);self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.input.get(),'')

    def test_blocked_game_native_or_talent_adapter_cannot_reenable_controls(self):
        for obj in (self.panel.app.adapter,self.panel.adapter,self.panel.adapter.talents):
            obj.blocked=True
            self.panel.update_enabled(True)
            self.panel.detect();self.panel.complete();self.panel.set_talents()
            self.assertEqual(self.panel.detect_button.options['state'],'disabled')
            self.assertEqual(self.panel.complete_button.options['state'],'disabled')
            self.assertEqual(self.panel.set_button.options['state'],'disabled')
            obj.blocked=False
        self.panel.app.work.assert_not_called()


if __name__=='__main__':unittest.main()
