"""Ensure a delayed character edit cannot silently switch to another target."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from character_ui import CharacterPanel, number
import character_attributes_interact  # Load before the isolated growth-module stub.
from test_app import FakeTree, FakeVar, FakeWidget
from write_guard import Refused, UncertainWrite
from ui_errors import RefreshAfterWriteError


class CharacterUiTests(unittest.TestCase):
    def setUp(self):
        self.panel = CharacterPanel.__new__(CharacterPanel)
        self.panel.app = SimpleNamespace(busy=False, adapter=Mock(), root=Mock(), work=Mock(), status=FakeVar())
        self.panel.adapter = Mock()
        self.panel.tree = FakeTree()
        for name in ("input", "detail", "note"):
            setattr(self.panel, name, FakeVar())
        for name in ("detect_button", "entry", "set_button"):
            setattr(self.panel, name, FakeWidget())
        self.targets = {key: SimpleNamespace(key=key, attr_id=int(key.split(":")[1]), value=value, minimum=0., maximum=1000000.)
                        for key, value in (("growth:2", 2.), ("growth:3", 3.))}
        self.state = {"can_edit": True, "rows": {
            key: {"name": name, "layer": "永久成长加成", "target": self.targets[key], "display_value": value}
            for key, name, value in (("growth:2", "攻击", 30.), ("growth:3", "防御", 40.))}}
        self.panel.render(self.state)
        self.module = SimpleNamespace(parse_attribute_value=lambda text: float(text),
                                      validate_attribute_value=Mock(), CharacterAttributesAdapter=Mock())
        self.module_patch = patch.dict(sys.modules, {"character_attributes": self.module})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def select(self, key):
        self.panel.tree.selection_set(key)
        self.panel.select()

    def test_label_separates_growth_and_total(self):
        self.assertEqual(self.panel.tree.rows["growth:2"][:3], ("攻击", "2", "30"))
        self.select("growth:2")
        self.assertEqual(self.panel.input.get(), "2")
        self.assertIn("永久成长加成", self.panel.detail.get())
        self.assertEqual(number(1000000), "1000000")

    def percentage_state(self):
        from character_attributes_write import AttributeTarget
        shown = AttributeTarget("growth:111", .05, ("player",), ((0x2000, "00"),),
                                111, address=0x1000, maximum=1.)
        return shown, dict(can_edit=True, rows={shown.key: dict(name="暴击率", target=shown,
                          layer="永久成长加成", note="按百分点输入。")})

    def test_percentage_display_and_range_do_not_expose_raw_ratio(self):
        shown, state = self.percentage_state()
        self.panel.render(state)
        self.select(shown.key)
        self.assertEqual(self.panel.tree.rows[shown.key][1], "5 个百分点")
        self.assertEqual(self.panel.tree.rows[shown.key][3], "0–100 个百分点")
        self.assertEqual(self.panel.input.get(), "5")
        self.assertIn("0–100 个百分点", self.panel.detail.get())

    def test_percentage_input_converts_once_and_confirmation_uses_display_units(self):
        shown, state = self.percentage_state()
        self.panel.render(state)
        self.select(shown.key)
        self.panel.input.set("6.25")
        self.panel.change()
        job, success = self.panel.app.work.call_args.args
        self.panel.adapter.snapshot.return_value = state
        success(job())
        self.module.validate_attribute_value.assert_called_once_with(shown, .0625)
        self.panel.adapter.set_value.assert_called_once_with(shown, .0625)
        self.assertIn("5 → 6.25 个百分点", self.panel.app.status.get())

    def test_no_selection_and_unsafe_scene_disable_writes(self):
        self.assertEqual(self.panel.entry.options["state"], "disabled")
        self.select("growth:2")
        self.panel.render({**self.state, "can_edit": False, "reason": "正在战斗"})
        self.panel.change()
        self.panel.app.work.assert_not_called()
        self.assertEqual(self.panel.set_button.options["state"], "disabled")

    def test_selection_clears_when_target_disappears(self):
        self.select("growth:2")
        self.panel.render({"can_edit": True, "rows": {}})
        self.assertEqual(self.panel.input.get(), "")
        self.assertEqual(self.panel.set_button.options["state"], "disabled")

    def test_invalid_input_does_not_launch_worker(self):
        self.select("growth:2")
        self.module.validate_attribute_value.side_effect = Refused("超出范围")
        with patch("character_ui.messagebox.showwarning") as warning:
            self.panel.change()
        warning.assert_called_once()
        self.panel.app.work.assert_not_called()

    def test_worker_pins_target_and_value_before_selection_changes(self):
        self.select("growth:2")
        self.panel.input.set("10")
        self.panel.change()
        job, success = self.panel.app.work.call_args.args
        self.select("growth:3")
        self.panel.input.set("99")
        self.panel.adapter.snapshot.return_value = self.state
        result = job()
        self.panel.adapter.set_value.assert_called_once_with(self.targets["growth:2"], 10.)
        success(result)
        self.assertIn("攻击", self.panel.app.status.get())

    def test_refused_write_clears_shown_target_without_claiming_success(self):
        self.select("growth:2")
        self.panel.input.set("4")
        self.panel.change()
        job, success = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = Refused("已切换场景")
        success(job())
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.app.status.get(), "人物属性未修改。")
        self.assertEqual(self.panel.entry.options["state"], "disabled")

    def test_uncertain_write_propagates_to_global_stop(self):
        self.select("growth:2")
        self.panel.input.set("4")
        self.panel.change()
        job, _ = self.panel.app.work.call_args.args
        self.panel.adapter.set_value.side_effect = UncertainWrite("结果未知")
        with self.assertRaises(UncertainWrite):
            job()

    def test_success_followed_by_failed_refresh_is_not_retryable(self):
        self.select("growth:2")
        self.panel.input.set("4")
        self.panel.change()
        job, _ = self.panel.app.work.call_args.args
        self.panel.adapter.snapshot.side_effect = Refused("当前角色已变化")
        with self.assertRaises(RefreshAfterWriteError):
            job()
        self.panel.adapter.set_value.assert_called_once()

    def test_disconnect_closes_bridge_and_clears_values(self):
        self.select("growth:2")
        adapter = self.panel.adapter
        self.panel.disconnect()
        adapter.close.assert_called_once()
        self.assertIsNone(self.panel.adapter)
        self.assertIsNone(self.panel.state)
        self.assertEqual(self.panel.tree.get_children(), ())

    def test_global_disable_and_disconnect_reach_interact_tab(self):
        child = Mock()
        self.panel.interact_panel = child
        self.panel.update_enabled(False)
        child.update_enabled.assert_called_once_with(False)
        self.panel.disconnect()
        child.disconnect.assert_called_once()

    def test_interact_experience_and_level_are_distinct(self):
        self.panel.kind = "interact"
        shown = SimpleNamespace(key="interact:1001", value=569, minimum=0, maximum=1500)
        state = dict(can_edit=True, rows={shown.key: dict(name="灵机", layer="累计经验", target=shown,
                     display_value=6, note="当前境界等级上限 12。")})
        self.panel.render(state)
        self.select(shown.key)
        self.assertEqual(self.panel.tree.rows[shown.key][:3], ("灵机", "569", "6"))
        self.assertEqual(self.panel.input.get(), "569")
        self.assertIn("累计经验", self.panel.detail.get())
        self.assertIn("累计经验", self.panel.note.get())

    def test_interact_uses_integer_validator_and_pins_experience(self):
        from character_attributes_interact_write import InteractTarget
        self.panel.kind = "interact"
        shown = InteractTarget("interact:1001", 569, ("player",), ((0x2000, "00"),),
                               1001, address=0x1000, maximum=1500)
        state = dict(can_edit=True, rows={shown.key: dict(name="灵机", layer="累计经验", target=shown,
                                                         display_value=6)})
        self.panel.render(state)
        self.select(shown.key)
        self.panel.input.set("570")
        self.panel.change()
        job, success = self.panel.app.work.call_args.args
        self.panel.adapter.snapshot.return_value = state
        success(job())
        self.panel.adapter.set_value.assert_called_once_with(shown, 570)
        self.assertIs(type(self.panel.adapter.set_value.call_args.args[1]), int)
        self.assertIn("灵机累计经验：569 → 570", self.panel.app.status.get())

    def test_interact_decimal_input_never_launches_worker(self):
        from character_attributes_interact_write import InteractTarget
        self.panel.kind = "interact"
        shown = InteractTarget("interact:1001", 10, ("player",), ((0x2000, "00"),),
                               1001, address=0x1000, maximum=600)
        self.panel.render(dict(can_edit=True, rows={shown.key: dict(name="灵机", target=shown)}))
        self.select(shown.key)
        self.panel.input.set("10.5")
        with patch("character_ui.messagebox.showwarning") as warning:
            self.panel.change()
        warning.assert_called_once()
        self.panel.app.work.assert_not_called()


if __name__ == "__main__":
    unittest.main()
