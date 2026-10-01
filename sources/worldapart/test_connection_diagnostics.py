"""Small real-Tk checks; no game or native connection is created."""
import json
from pathlib import Path
import queue
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

import app
import connection_diagnostics as diagnostics


class ConnectionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("640x460+30+30")
        self.root.update()
        self.addCleanup(self.root.destroy)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.log_root = Path(temporary.name) / "logs"
        handle = patch.object(diagnostics.runtime_paths, "LOG_ROOT", self.log_root)
        handle.start()
        self.addCleanup(handle.stop)
        self.payload = {
            "stage": "initialized_class_discovery",
            "types": {
                "Player": {"status": "not_found", "candidates": []},
                "Bag": {"status": "rejected", "candidates": [{"reason": "字段类型不符"}]},
                "World": {"status": "ambiguous", "accepted_count": 2},
            },
        }
        self.error = diagnostics.ConnectionDiagnosticError("所需类型未能唯一确认。", self.payload)

    def show(self):
        window = diagnostics.show_connection_error(self.root, self.error)
        self.root.update()
        return window

    def widget(self, window, name):
        return window.nametowidget(f"{window}.content.{name}")

    def test_constructor_has_no_io_and_retains_diagnostic(self):
        self.assertIs(self.error.diagnostic, self.payload)
        self.assertEqual(str(self.error), "所需类型未能唯一确认。")
        self.assertFalse(self.log_root.exists())

    def test_first_display_copy_and_close_use_real_tk_and_save_only_data(self):
        window = self.show()
        self.assertTrue(window.winfo_ismapped())
        details = self.widget(window, "diagnostic_text")
        self.assertEqual(details.cget("state"), "disabled")
        self.assertEqual(json.loads(details.get("1.0", "end-1c")), self.payload)
        self.assertIn("连接未完成", self.widget(window, "summary").cget("text"))
        before = details.get("1.0", "end-1c")
        details.insert("1.0", "must not be editable")
        self.assertEqual(details.get("1.0", "end-1c"), before)
        self.widget(window, "actions.copy").invoke()
        self.assertEqual(json.loads(self.root.clipboard_get()), self.payload)
        files = list(self.log_root.glob("connection-diagnostic-*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text(encoding="utf-8")), self.payload)
        self.assertLess(files[0].stat().st_size, 2048)
        window.geometry("620x440")
        self.root.update()
        for name in ("diagnostic_text", "actions.copy", "actions.close"):
            widget = self.widget(window, name)
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_height(), 15)
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())
        self.widget(window, "actions.close").invoke()
        self.assertFalse(window.winfo_exists())

    def test_repeated_dialog_preserves_each_diagnostic(self):
        self.show().destroy()
        self.show().destroy()
        self.assertEqual(len(list(self.log_root.glob("connection-diagnostic-*.json"))), 2)

    def test_failed_save_keeps_original_error_and_copy_available(self):
        self.log_root.write_text("not a directory", encoding="utf-8")
        window = self.show()
        self.assertIn(str(self.error), self.widget(window, "summary").cget("text"))
        self.assertIn("未能保存", self.widget(window, "status").cget("text"))
        self.widget(window, "actions.copy").invoke()
        self.assertEqual(json.loads(self.root.clipboard_get()), self.payload)

    def test_poll_routes_only_diagnostic_error_and_still_clears_connection(self):
        interface = app.App.__new__(app.App)
        interface.root = Mock()
        interface.events = queue.Queue()
        interface.shutdown_adapter = Mock()
        interface.status = Mock()
        interface.buttons = Mock()
        for error in (self.error, RuntimeError("ordinary failure")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(app, "show_connection_error") as show, \
                    patch.object(app.messagebox, "showerror") as ordinary:
                interface.state = {"old": "target"}
                interface.busy = True
                success = Mock()
                interface.events.put((success, None, error))
                interface.poll()
                success.assert_not_called()
                self.assertIsNone(interface.state)
                self.assertFalse(interface.busy)
                if error is self.error:
                    show.assert_called_once_with(interface.root, error)
                    ordinary.assert_not_called()
                else:
                    show.assert_not_called()
                    ordinary.assert_called_once_with("WorldApartTrainer", str(error), parent=interface.root)
        self.assertEqual(interface.shutdown_adapter.call_count, 2)


if __name__ == "__main__":
    unittest.main()
