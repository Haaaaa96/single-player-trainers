"""No Frida or process is touched: native-creation lifecycle and durable guards."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import character_attributes_native as cn
from character_attributes_write import AttributeTarget
from write_guard import Refused, UncertainWrite


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.game = types.SimpleNamespace(
            resolver=types.SimpleNamespace(reader=types.SimpleNamespace(pid=98765)),
            stamp=("worldapart.exe", 12345), record=Mock())
        self.shown = AttributeTarget("growth:2", 0.0, tuple(range(10)),
                                     ((0x5000, "00000000"),), 2)
        self.after = replace(self.shown, value=1.25, address=0x6000)
        self.descriptor = dict(combat="0x1000", combat_class="0x2000", player="0x3000",
                               dictionary="0x4000", attr_id=2, value=1.25,
                               identity_key="a" * 64, method_info="0x7000",
                               anchors=[dict(address="0x5000", size=4, expected_hex="00000000")])
        self.adapter = types.SimpleNamespace(
            prepare_native=Mock(return_value=self.descriptor), resolve=Mock(return_value=self.after))
        self.runtime_patch = patch.object(cn, "initialize_runtime", return_value=Path(self.temp.name))
        self.runtime_patch.start()
        self.addCleanup(self.runtime_patch.stop)
        self.frida_patch = patch.dict("sys.modules", frida=types.SimpleNamespace(__version__="17.7.3"))
        self.frida_patch.start()
        self.addCleanup(self.frida_patch.stop)
        self.bridge = cn.CharacterAttributesNative(self.game, self.adapter)
        self.addCleanup(lambda: cn._LIVE_BRIDGES.discard(self.bridge))
        self.addCleanup(lambda: cn._RETAINED_BRIDGES.discard(self.bridge))
        self.connection = Mock()
        self.connection.script = types.SimpleNamespace(exports_sync=types.SimpleNamespace(submit=Mock()))
        self.behavior = "success"
        self.acquire_patch = patch.object(cn, "acquire_connection", side_effect=self.acquire)
        self.acquire = self.acquire_patch.start()
        self.addCleanup(self.acquire_patch.stop)

    def acquire(self, identity, frida, source, epoch, owner, message, detached, before, check):
        before()
        def submit(request):
            if self.behavior == "rpc_error":
                raise OSError("transport")
            payload = dict(status="completed", token=request["token"], called=True, created=True,
                           attr_id=2, value=1.25, identity_key="a" * 64)
            if self.behavior == "wrong_value":
                payload["value"] = 1.5
            elif self.behavior == "reject":
                payload.update(status="rejected", called=False, reason="scene changed")
            elif self.behavior == "exception":
                payload.update(status="exception")
            message(dict(type="send", payload=payload), None)
        self.connection.script.exports_sync.submit.side_effect = submit
        return self.connection

    def test_same_shared_bridge_and_epoch_request_contract(self):
        result = self.bridge.set_value(self.shown, 1.25)
        self.assertEqual(result, self.after)
        call = self.acquire.call_args
        self.assertEqual(call.args[0], (98765, 12345))
        self.assertEqual(call.args[3].name, "acquisition-native-epochs.json")
        self.assertIn("character_growth_set", call.args[2])
        request = self.connection.script.exports_sync.submit.call_args.args[0]
        self.assertEqual(request["operation"], "character_growth_set")
        self.assertEqual(request["method_token"], 0x06014B6C)
        self.assertEqual(request["parameter_count"], 2)
        self.assertEqual(request["character"]["value"], 1.25)
        self.assertEqual(self.bridge._ledger()["processes"][self.bridge.process_key]["status"], "verified")
        self.connection.release.assert_called_once_with(self.bridge)

    def test_scene_change_after_attach_never_submits(self):
        self.adapter.prepare_native.side_effect = [self.descriptor, Refused("scene changed")]
        with self.assertRaises(Refused):
            self.bridge.set_value(self.shown, 1.25)
        self.connection.script.exports_sync.submit.assert_not_called()
        self.assertFalse(self.bridge._native_inflight)

    def test_wrong_native_value_is_unknown_and_blocks_reconnect(self):
        self.behavior = "wrong_value"
        with self.assertRaises(UncertainWrite):
            self.bridge.set_value(self.shown, 1.25)
        second = cn.CharacterAttributesNative(self.game, self.adapter)
        self.addCleanup(lambda: cn._LIVE_BRIDGES.discard(second))
        with self.assertRaises(Refused):
            second.require_ready()

    def test_different_player_after_native_call_is_unknown(self):
        self.adapter.resolve.return_value = replace(self.after, identity=("other",) + self.after.identity[1:])
        with self.assertRaises(UncertainWrite):
            self.bridge.set_value(self.shown, 1.25)

    def test_rejected_not_called_request_is_safe_to_retry(self):
        self.behavior = "reject"
        with self.assertRaises(Refused) as caught:
            self.bridge.set_value(self.shown, 1.25)
        self.assertNotIsInstance(caught.exception, UncertainWrite)
        self.bridge.require_ready()

    def test_rpc_error_keeps_connection_retained(self):
        self.behavior = "rpc_error"
        with self.assertRaises(UncertainWrite):
            self.bridge.set_value(self.shown, 1.25)
        self.assertTrue(self.bridge._native_inflight)
        self.assertIn(self.bridge, cn._RETAINED_BRIDGES)
        self.connection.release.assert_not_called()

    def test_exception_after_call_is_uncertain_even_if_transport_ended(self):
        self.behavior = "exception"
        with self.assertRaises(UncertainWrite):
            self.bridge.set_value(self.shown, 1.25)
        with self.assertRaises(Refused):
            self.bridge.require_ready()

    def test_pending_record_blocks_before_attach(self):
        self.bridge.record(dict(status="pending"))
        with self.assertRaises(Refused):
            self.bridge.set_value(self.shown, 1.25)
        self.acquire.assert_not_called()

    def test_corrupt_ledger_never_allows_retry(self):
        self.bridge.journal.write_text("not json", encoding="utf8")
        with self.assertRaises(Refused):
            self.bridge.require_ready()

    def test_native_completed_but_all_postwrite_logs_fail_is_uncertain(self):
        real_record = self.bridge.record
        def record(event):
            if event["status"] in ("verified", "unknown"):
                raise Refused("journal unavailable")
            real_record(event)
        self.bridge.record = record
        with self.assertRaises(UncertainWrite):
            self.bridge.set_value(self.shown, 1.25)
        self.assertEqual(self.bridge._ledger()["processes"][self.bridge.process_key]["status"], "pending")


if __name__ == "__main__":
    unittest.main()
