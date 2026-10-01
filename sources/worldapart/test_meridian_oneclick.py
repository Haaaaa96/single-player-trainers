"""No live game: exercise dispatch lifetime, durable once-only and truthful results."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import meridian_oneclick as mo
from write_guard import Refused, UncertainWrite


def state():
    return dict(identity=(("game", 123), 1), native=dict(
        round_key="a" * 64, panel="0x1000", vm="0x2000", config="0x3000", manager="0x4000",
        cells=[dict(address="0x5000", variant=1)], anchors=[dict(address="0x1000", size=1, expected_hex="00")],
        registry_links=[dict(address="0x6000", expected="0x7000")], registry=dict(count=1),
        method_info="0x8000"))


class OneClickTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.game = SimpleNamespace(stamp=("WorldApart.exe", 123),
                                    resolver=SimpleNamespace(reader=SimpleNamespace(pid=999)), record=Mock())
        self.resolver = Mock()
        self.resolver.prepare_solve.side_effect = lambda shown: deepcopy(state())
        self.requests, self.connections = [], []
        self.response = dict(status="completed", called=True, changed=True, native_finished=True,
                             native_won=True, failure_reason=0)
        self.submit_error = None
        self.send = True
        self.start_error = None
        for patcher in (
            patch.object(mo, "initialize_runtime", return_value=self.root),
            patch.dict("sys.modules", {"frida": SimpleNamespace(__version__="17.7.3")}),
            patch.object(mo, "acquire_connection", side_effect=self.acquire),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bridge = mo.MeridianOneClick(self.game, self.resolver)
        self.addCleanup(self.cleanup_bridge)

    def cleanup_bridge(self):
        self.bridge._native_inflight = False
        self.bridge.close()

    def acquire(self, identity, frida, source, epoch_path, owner, on_message, detached, before, check):
        self.assertEqual(identity, (999, 123))
        self.assertEqual(epoch_path, self.root / "acquisition-native-epochs.json")
        self.assertIn("meridian_solve", source)
        before()
        if self.start_error:
            raise self.start_error
        connection = SimpleNamespace(session=object(), previous_token=None, prepare=Mock(), release=Mock())
        def submit(request):
            self.requests.append(request)
            saved = json.loads(self.bridge.journal.read_text(encoding="utf8"))
            self.assertEqual(saved["rounds"]["a" * 64]["status"], "pending")
            if self.submit_error:
                raise self.submit_error
            if self.send:
                on_message(dict(type="send", payload=dict(self.response, token=request["token"])), None)
        connection.script = SimpleNamespace(exports_sync=SimpleNamespace(submit=submit))
        self.connections.append(connection)
        return connection

    def journal_event(self):
        return json.loads(self.bridge.journal.read_text(encoding="utf8"))["rounds"]["a" * 64]

    def test_success_uses_shared_session_and_records_win_separately_from_settlement(self):
        result = self.bridge.solve(state())
        self.assertEqual(result["phase"], "native_win_waiting_settlement")
        self.assertFalse(result["settlement_verified"])
        self.assertEqual(self.requests[0]["operation"], "meridian_solve")
        self.assertEqual(self.requests[0]["parameter_count"], 0)
        self.assertEqual(self.journal_event()["status"], "verified")
        self.connections[0].release.assert_called_once_with(self.bridge)
        self.assertFalse(self.bridge._native_inflight)

    def test_same_round_never_dispatches_twice_even_after_new_adapter(self):
        self.bridge.solve(state())
        replacement = mo.MeridianOneClick(self.game, self.resolver)
        with self.assertRaises(Refused):
            replacement.solve(state())
        self.assertEqual(len(self.requests), 1)

    def test_changed_board_after_attachment_is_not_dispatched(self):
        changed = state()
        changed["native"]["cells"][0]["variant"] = 2
        self.resolver.prepare_solve.side_effect = [state(), changed]
        with self.assertRaises(Refused):
            self.bridge.solve(state())
        self.assertEqual(self.requests, [])
        self.assertEqual(self.journal_event()["status"], "not_dispatched")

    def test_missing_registry_refused_before_agent_acquisition(self):
        missing = state()
        missing["native"].pop("registry_links")
        self.resolver.prepare_solve.side_effect = None
        self.resolver.prepare_solve.return_value = missing
        with self.assertRaises(Refused):
            self.bridge.solve(missing)
        self.assertEqual(self.connections, [])

    def test_pre_call_rejection_preserves_no_call_and_allows_fresh_retry(self):
        self.response = dict(status="rejected", called=False, reason="paused")
        with self.assertRaises(Refused):
            self.bridge.solve(state())
        self.assertEqual(self.journal_event()["status"], "rejected")
        self.bridge._require_unused("a" * 64)
        self.assertFalse(self.bridge._native_inflight)

    def test_boolean_true_without_native_win_is_unknown_and_never_retried(self):
        self.response.update(native_won=False, native_finished=False)
        with self.assertRaises(UncertainWrite):
            self.bridge.solve(state())
        self.assertEqual(self.journal_event()["status"], "unknown")
        with self.assertRaises(Refused):
            self.bridge.solve(state())
        self.assertEqual(len(self.requests), 1)

    def test_false_return_is_not_published_as_success(self):
        self.response["changed"] = False
        with self.assertRaises(UncertainWrite):
            self.bridge.solve(state())

    def test_submit_transport_error_retains_agent_and_pending_guard(self):
        self.submit_error = RuntimeError("transport lost after RPC dispatch")
        with self.assertRaises(UncertainWrite):
            self.bridge.solve(state())
        self.assertTrue(self.bridge._native_inflight)
        self.assertIn(self.bridge, mo._RETAINED_BRIDGES)
        self.connections[0].release.assert_not_called()
        self.assertEqual(self.journal_event()["status"], "unknown")

    def test_timeout_never_retries_or_unloads_agent(self):
        self.send = False
        with patch("meridian_oneclick.threading.Event.wait", return_value=False):
            with self.assertRaises(UncertainWrite):
                self.bridge.solve(state())
        self.assertTrue(self.bridge._native_inflight)
        self.assertEqual(len(self.requests), 1)
        self.connections[0].release.assert_not_called()

    def test_log_failure_after_call_is_unknown_and_persisted_pending_blocks_retry(self):
        original = self.bridge._record
        def record(key, event):
            if event["status"] in ("verified", "unknown"):
                raise OSError("disk full")
            original(key, event)
        self.bridge._record = record
        with self.assertRaises(UncertainWrite):
            self.bridge.solve(state())
        self.assertEqual(self.journal_event()["status"], "pending")
        with self.assertRaises(Refused):
            self.bridge._require_unused("a" * 64)

    def test_attach_failure_records_no_game_call_and_blocks_same_round(self):
        self.start_error = mo.NativeStartError("attach", RuntimeError("failed"))
        with self.assertRaises(Refused):
            self.bridge.solve(state())
        self.assertEqual(self.requests, [])
        self.assertEqual(self.journal_event()["status"], "attach_failed")
        self.assertIs(self.journal_event()["called"], False)

    def test_corrupt_journal_prevents_native_start(self):
        self.bridge.journal.write_text("{invalid", encoding="utf8")
        with self.assertRaises(Refused):
            self.bridge.solve(state())
        self.assertEqual(self.connections, [])


if __name__ == "__main__":
    unittest.main()
