"""Known no-write outcomes keep the connection; uncertainty still stops it."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from learning_ui import LearningPanel
from learning_write import FloatTarget
from test_app import FakeVar, FakeWidget
from write_guard import Refused, UncertainWrite


class LearningUiTests(unittest.TestCase):
    def setUp(self):
        self.panel=LearningPanel.__new__(LearningPanel)
        self.panel.app=SimpleNamespace(busy=False,adapter=Mock(),root=Mock(),work=Mock(),status=FakeVar())
        target=FloatTarget("learning_value",0x1000,0.0,("round",),0.0,300.0,((0x2000,"01"),))
        self.panel.state={"active":True,"targets":{"learning_value":target}}
        self.panel.resolver=Mock()
        self.panel.inputs={"learning_value":FakeVar("1")}
        self.panel.currents={"learning_value":FakeVar("0")}
        self.panel.note=FakeVar()
        self.panel.entries={"learning_value":FakeWidget()}
        self.panel.buttons={"learning_value":FakeWidget()}
        self.panel.detect_button=FakeWidget()
        self.panel.complete_button=FakeWidget()
        self.panel.completion=None

    def test_normal_game_tick_refusal_keeps_adapter_and_invalidates_stale_target(self):
        adapter=self.panel.app.adapter
        resolver=self.panel.resolver
        with patch("learning_write.FloatWriteOnce"),patch("learning_write.set_float_value",side_effect=Refused("数值已变化")):
            self.panel.change("learning_value")
            job,success=self.panel.app.work.call_args.args
            result=job()
        success(result)
        self.assertIs(self.panel.app.adapter,adapter)
        adapter.close.assert_not_called()
        self.assertIsNone(self.panel.state)
        resolver.snapshot.assert_not_called()
        self.assertIn("未修改",self.panel.app.status.get())

    def test_uncertain_write_propagates_to_global_stop_handler(self):
        with patch("learning_write.FloatWriteOnce"),patch("learning_write.set_float_value",side_effect=UncertainWrite("unknown")):
            self.panel.change("learning_value")
            job,_=self.panel.app.work.call_args.args
            with self.assertRaises(UncertainWrite):
                job()
        self.panel.resolver.snapshot.assert_not_called()

    def test_inactive_round_clears_and_disables_targets(self):
        self.panel.render({"active":False,"reason":"没有当前学习局"})
        self.assertEqual(self.panel.inputs["learning_value"].get(),"")
        self.assertEqual(self.panel.entries["learning_value"].options["state"],"disabled")
        self.assertEqual(self.panel.buttons["learning_value"].options["state"],"disabled")
        self.assertEqual(self.panel.complete_button.options["state"],"disabled")

    def test_completion_requires_supported_current_round_and_no_worker(self):
        for busy, can_complete, adapter in ((True, True, Mock()), (False, False, Mock()), (False, True, None)):
            with self.subTest(busy=busy, can_complete=can_complete):
                self.panel.app.busy=busy
                self.panel.app.adapter=adapter
                self.panel.state["can_complete"]=can_complete
                self.panel.complete()
        self.panel.app.work.assert_not_called()

    def test_completion_button_respects_write_enable_and_round_readiness(self):
        self.panel.state["can_complete"]=True
        self.panel.update_enabled(False)
        self.assertEqual(self.panel.complete_button.options["state"],"disabled")
        self.panel.update_enabled(True)
        self.assertEqual(self.panel.complete_button.options["state"],"normal")
        self.panel.state["can_complete"]=False
        self.panel.update_enabled(True)
        self.assertEqual(self.panel.complete_button.options["state"],"disabled")

    def test_completion_pins_shown_round_and_never_uses_manual_input(self):
        self.panel.state["can_complete"]=True
        shown=self.panel.state
        adapter,resolver=self.panel.app.adapter,self.panel.resolver
        with patch("learning_completion.LearningCompletion") as factory:
            factory.return_value.complete.return_value={"status":"confirmed","message":"游戏已确认学习成功，请核对并手动保存。"}
            self.panel.complete()
            job,success=self.panel.app.work.call_args.args
            self.panel.state={"active":False}
            self.panel.inputs["learning_value"].set("999999")
            result=job()
            factory.assert_called_once_with(adapter,resolver)
            factory.return_value.complete.assert_called_once_with(shown)
            success(result)
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.inputs["learning_value"].get(),"")
        self.assertEqual(self.panel.complete_button.options["state"],"disabled")
        self.assertEqual(self.panel.app.status.get(),result["message"])

    def test_pending_result_never_claims_success_or_retries(self):
        self.panel.state["can_complete"]=True
        with patch("learning_completion.LearningCompletion") as factory:
            factory.return_value.complete.return_value={"status":"filled_pending","message":"已填满，等待游戏结算；请勿重复执行。"}
            self.panel.complete()
            job,success=self.panel.app.work.call_args.args
            success(job())
            self.panel.complete()
            factory.return_value.complete.assert_called_once()
        self.assertNotIn("成功",self.panel.app.status.get())
        self.assertEqual(self.panel.complete_button.options["state"],"disabled")

    def test_completion_refusal_keeps_connection_and_clears_stale_round(self):
        self.panel.state["can_complete"]=True
        adapter=self.panel.app.adapter
        with patch("learning_completion.LearningCompletion") as factory:
            factory.return_value.complete.side_effect=Refused("当前局已变化，未写入。")
            self.panel.complete()
            job,success=self.panel.app.work.call_args.args
            success(job())
        self.assertIs(self.panel.app.adapter,adapter)
        adapter.close.assert_not_called()
        self.assertIsNone(self.panel.state)
        self.assertIn("未写入",self.panel.note.get())

    def test_completion_uncertain_write_reaches_global_stop(self):
        self.panel.state["can_complete"]=True
        with patch("learning_completion.LearningCompletion") as factory:
            factory.return_value.complete.side_effect=UncertainWrite("请核对游戏")
            self.panel.complete()
            job,_=self.panel.app.work.call_args.args
            with self.assertRaises(UncertainWrite):
                job()


if __name__=="__main__":
    unittest.main()
