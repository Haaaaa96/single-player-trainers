"""Exercise the opt-in live-check script with an entirely fake adapter."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from write_guard import Target

SOURCE = Path(__file__).resolve().parent / "validation_support.py"
spec = importlib.util.spec_from_file_location("extended_validation_testmodule", SOURCE)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class LiveScriptTests(unittest.TestCase):
    def setUp(self):
        self.values = {"item:10": 1, "item:6": 1, "currency:1": 17100}
        self.rows = {}
        self.baseline = {"raw": {"pid": 10, "spirit": 200, "path": 50, "items": []},
                         "targets": {}, "bag_object_bytes": {}, "learned_nodes": [1],
                         "save_files": [{"path": "save", "sha256": "unchanged"}]}
        for index, (key, value) in enumerate(self.values.items()):
            obj = 0x1000 + index * 0x100
            uid = int(key.split(":")[1])
            data = bytearray(56)
            struct.pack_into("<i", data, 20, value)
            target = {"key": key, "address": obj + 20, "value": value, "identity": (10, obj),
                      "minimum": 0 if key.startswith("currency") else 1,
                      "maximum": 999999999 if key.startswith("currency") else 999,
                      "max_change": 1000000 if key.startswith("currency") else 1000}
            self.baseline["raw"]["items"].append({"uid": uid, "count": value})
            self.baseline["targets"][key] = target
            self.baseline["bag_object_bytes"][str(uid)] = {"object": obj, "size": 56, "bytes": data.hex()}
            self.rows[key] = {"class_name": "Game.Model.Components." + ("PillBagItem" if key == "item:10" else "BagItem"),
                              "category": "currency" if key.startswith("currency") else "item",
                              "item_id": 50000 if key.startswith("currency") else uid}
        self.adapter = SimpleNamespace(resolve=self.resolve, set_value=Mock(side_effect=self.write), close=Mock(),
                                       resolver=SimpleNamespace(resolve=lambda: deepcopy(self.baseline["raw"])))
        self.unexpected = False

    def resolve(self, key):
        row = {**self.baseline["targets"][key], "value": self.values[key]}
        return Target(**row)

    def write(self, shown, new_value):
        self.assertEqual(shown.value, self.values[shown.key])
        self.assertEqual(abs(new_value - shown.value), 1)
        self.values[shown.key] = new_value
        return self.resolve(shown.key)

    def capture(self, adapter):
        obs = deepcopy(self.baseline)
        for key, value in self.values.items():
            obs = validation.expected_after(obs, key, value)
        if self.unexpected and self.values["item:10"] == 2:
            obs["raw"]["spirit"] = 201
        rows = {key: {**row, "target": self.resolve(key)} for key, row in self.rows.items()}
        state = {"items": {key: row for key, row in rows.items() if key.startswith("item")},
                 "currencies": {key: row for key, row in rows.items() if key.startswith("currency")}}
        return state, obs

    def execute(self, flags=()):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "proof.json"
            argv = [str(SOURCE), "--output", str(output), *flags]
            with patch.object(validation, "GameAdapter", return_value=self.adapter), \
                    patch.object(validation, "capture", side_effect=self.capture), \
                    patch.object(validation, "save_hashes", return_value=[]), \
                    patch.object(validation.sys, "argv", argv), patch("builtins.print"):
                try:
                    validation.main()
                except RuntimeError:
                    if not self.unexpected:
                        raise
            return json.loads(output.read_text(encoding="utf8"))

    def test_default_mode_never_calls_write(self):
        result = self.execute()
        self.assertEqual(result["mode"], "read-only")
        self.assertEqual(result["status"], "verified")
        self.adapter.set_value.assert_not_called()
        self.adapter.close.assert_called_once()

    def test_explicit_mode_has_six_single_steps_and_restores_fresh_baseline(self):
        result = self.execute(["--validate-steps"])
        self.assertEqual(result["status"], "verified")
        self.assertEqual(self.adapter.set_value.call_count, 6)
        self.assertEqual([s["after"] for s in result["steps"]], [2, 1, 2, 1, 17101, 17100])
        self.assertEqual(result["baseline"], result["final"])

    def test_unexpected_field_change_stops_before_any_more_writes(self):
        self.unexpected = True
        result = self.execute(["--validate-steps"])
        self.assertEqual(result["status"], "stopped_on_error")
        self.assertEqual(self.adapter.set_value.call_count, 1)
        self.assertEqual(self.values["item:10"], 2)
        self.assertIn("unexpected changes", result["error"])

    def test_wrong_selected_key_or_already_capped_item_is_refused(self):
        state, _ = self.capture(self.adapter)
        args = SimpleNamespace(pill_key="currency:1", material_key=None, currency_key=None)
        with self.assertRaises(validation.Refused):
            validation.select_targets(state, args)
        self.values["item:10"] = 999
        state, _ = self.capture(self.adapter)
        args.pill_key = None
        with self.assertRaises(validation.Refused):
            validation.select_targets(state, args)


if __name__ == "__main__":
    unittest.main()
