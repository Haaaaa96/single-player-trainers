"""Real hidden Tk integration; no game/Frida APIs or process reads are used."""
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app import App
from standalone_selftest import EXPECTED_TABS, EXPECTED_NAVIGATION, validate_release_navigation
from write_guard import UncertainWrite


class LifeSkillsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        for module in ('app','crafting_ui','alchemy_ui','dual_cultivation_ui'):
            patch(module+'.native_calls_pending',return_value=False).start()
        self.addCleanup(patch.stopall)
        self.app=App(self.root)
        self.app.work=Mock()
        self.panels=self.app.extensions[-5:]
        self.alchemy,self.recipes,self.crafting,self.dual,self.jade=self.panels

    def all_buttons(self):
        for panel in self.panels:
            if panel is self.alchemy:
                yield from (panel.detect_button,panel.solve_button,panel.talent_detect,panel.set_button)
            elif panel is self.crafting:
                yield from (panel.detect_button,panel.complete_button,panel.set_button)
            else:
                yield from (panel.detect_button,panel.button)

    def assert_disabled(self):
        for button in self.all_buttons():
            self.assertEqual(str(button.cget('state')),'disabled',button.cget('text'))

    def handlers(self):
        for panel in self.panels:
            panel.detect()
            (panel.complete if panel is self.crafting else panel.solve)()
        self.alchemy.detect_talents();self.alchemy.set_talent()
        self.crafting.set_talents()

    def callbacks(self):
        state=dict(active=False,can_solve=True,reason='synthetic old result')
        for panel in (self.alchemy,self.recipes,self.dual,self.jade):
            panel.render(dict(state))
        self.alchemy.render_talents(dict(rows={},can_edit=True,reason='',player_level=1))
        self.crafting.render(dict(round=dict(can_complete=True),talents=dict(can_edit=True)))

    def test_actual_sixteen_pages_and_routes_match_independent_manifest(self):
        titles=tuple(self.app.tabs.tab(tab,'text') for tab in self.app.tabs.tabs())
        self.assertEqual(titles,EXPECTED_TABS)
        groups={str(self.app.navigation.tree.item(group,'text')):
                [self.app.navigation._titles[page] for page in self.app.navigation.tree.get_children(group)]
                for group in self.app.navigation.tree.get_children()}
        validate_release_navigation(groups)
        for title in ('炼丹辅助','丹方探索','炼器辅助','双修','刮玉'):
            self.assertIn(title,self.app._page_refreshers)
        self.assertEqual(tuple(groups['生活技艺']),EXPECTED_NAVIGATION['生活技艺'])

    def test_initial_disconnected_handlers_and_callbacks_never_enable_or_dispatch(self):
        self.assert_disabled()
        self.callbacks();self.handlers()
        self.assert_disabled()
        self.app.work.assert_not_called()

    def test_readonly_callbacks_and_handlers_cannot_enable_new_features(self):
        self.app.adapter=SimpleNamespace(write_enabled=False,blocked=False)
        self.app.state=dict(items={},currencies={})
        self.app.buttons()
        self.callbacks();self.handlers()
        self.assert_disabled()
        self.app.work.assert_not_called()

    def test_busy_callbacks_cannot_reenable_new_features(self):
        self.app.adapter=SimpleNamespace(write_enabled=True,blocked=False)
        self.app.state=dict(items={},currencies={});self.app.busy=True
        self.callbacks();self.handlers()
        self.assert_disabled()
        self.app.work.assert_not_called()

    def test_disconnect_all_new_panels_clears_targets_inputs_and_controls(self):
        self.app.adapter=SimpleNamespace(write_enabled=True,blocked=False,close=Mock())
        self.app.state=dict(items={},currencies={})
        self.callbacks()
        self.crafting.input.set('99');self.alchemy.rank.set('5')
        self.app.shutdown_adapter()
        self.assertIsNone(self.app.adapter)
        for panel in self.panels:
            self.assertIsNone(panel.state)
        self.assertEqual(self.crafting.input.get(),'')
        self.assertEqual(self.alchemy.rank.get(),'')
        self.assert_disabled()

    def test_unknown_result_shuts_down_all_pages_and_clears_stale_targets(self):
        self.app.adapter=SimpleNamespace(write_enabled=True,blocked=False,close=Mock())
        self.app.state=dict(items={},currencies={});self.callbacks()
        success=Mock()
        self.app.events.put((success,None,UncertainWrite('synthetic unknown')))
        with patch('app.messagebox.showerror'):
            self.app.poll()
        self.assertIsNone(self.app.adapter);self.assertIsNone(self.app.state)
        success.assert_not_called()
        for panel in self.panels:self.assertIsNone(panel.state)
        self.assert_disabled()

    def test_close_waits_for_native_result_before_destroying_gui_or_readers(self):
        with patch.object(self.app,'shutdown_adapter') as shutdown, patch.object(self.root,'destroy') as destroy, \
             patch('acquisition_adapter.native_calls_pending',return_value=True), patch('app.messagebox.showwarning'):
            self.app.close()
            shutdown.assert_not_called();destroy.assert_not_called()
        with patch.object(self.app,'shutdown_adapter') as shutdown, patch.object(self.root,'destroy') as destroy, \
             patch('acquisition_adapter.native_calls_pending',return_value=False):
            self.app.close()
            shutdown.assert_called_once();destroy.assert_called_once()


if __name__=='__main__':unittest.main()
