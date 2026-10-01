"""Speed UI tests: fake widgets, no desktop or game operation."""
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import game_speed_ui as ui
from test_game_speed import target
from test_app import FakeVar, FakeWidget
from write_guard import Refused, UncertainWrite


class SpeedUiTests(unittest.TestCase):
    def setUp(self):
        self.p=ui.GameSpeedPanel.__new__(ui.GameSpeedPanel)
        self.p.app=SimpleNamespace(busy=False,adapter=Mock(),root=Mock(),work=Mock(),status=FakeVar())
        self.p.adapter=Mock()
        for n in ('base','effective','input','note'):setattr(self.p,n,FakeVar())
        for n in ('detect_button','entry','button','restore_button'):setattr(self.p,n,FakeWidget())
        self.state=dict(target=target(),base=1.,effective=1.,override_count=0,can_edit=True,reason='')
        self.pending=patch.object(ui,'native_calls_pending',return_value=False).start()
        self.warning=patch.object(ui.messagebox,'showwarning').start();self.addCleanup(patch.stopall)
        self.p.render(self.state)

    def test_game_override_is_visible(self):
        self.p.render(dict(self.state,effective=0.,override_count=1))
        self.assertEqual(self.p.base.get(),'1 ×');self.assertEqual(self.p.effective.get(),'0 ×')
        self.assertIn('覆盖',self.p.note.get())

    def test_restore_one_ignores_text_but_uses_pinned_target(self):
        shown=replace(target(),value=1.5,effective=1.5)
        self.p.render(dict(self.state,target=shown,base=1.5,effective=1.5))
        self.p.input.set('invalid');self.p.change(1.)
        job,done=self.p.app.work.call_args.args
        self.p.adapter.set_value.return_value=self.state
        done(job());self.p.adapter.set_value.assert_called_once_with(shown,1.)

    def test_invalid_noop_and_restoring_already_one_do_not_dispatch(self):
        for v in ('0.1','2.01','1','1e0'):
            self.p.input.set(v);self.p.change()
        self.p.change(1.)
        self.p.app.work.assert_not_called()

    def test_busy_pending_and_unsafe_disable_all_writes(self):
        self.p.input.set('1.5');self.p.app.busy=True;self.p.change()
        self.p.app.busy=False;self.pending.return_value=True;self.p.change();self.p.update_enabled(True)
        self.assertEqual(self.p.restore_button.options['state'],'disabled')
        self.pending.return_value=False;self.p.render(dict(self.state,can_edit=False));self.p.change()
        self.p.app.work.assert_not_called()

    def test_refused_clears_stale_target(self):
        self.p.input.set('1.5');self.p.change();job,done=self.p.app.work.call_args.args
        self.p.adapter.set_value.side_effect=Refused('changed');done(job())
        self.assertIsNone(self.p.state);self.assertEqual(self.p.app.status.get(),'速度未修改。')

    def test_unknown_propagates_to_global_stop(self):
        self.p.input.set('1.5');self.p.change();job,_=self.p.app.work.call_args.args
        self.p.adapter.set_value.side_effect=UncertainWrite('unknown')
        with self.assertRaises(UncertainWrite):job()

    def test_disconnect_does_not_auto_restore(self):
        adapter=self.p.adapter;self.p.disconnect()
        adapter.close.assert_called_once();adapter.set_value.assert_not_called()
        self.assertIsNone(self.p.state)


if __name__=='__main__':unittest.main()
