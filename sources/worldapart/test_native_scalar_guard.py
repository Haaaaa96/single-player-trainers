"""Only synthetic coordinator peers and mocked WPM; never start a native host."""
from contextlib import contextmanager
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import native_scalar_guard as guard
from write_guard import Refused, UncertainWrite, Target


class ScalarGuardTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.proxy = Mock()
        self.proxy.call.side_effect = self.call
        self.descriptor = {"fixture": "only"}
        @contextmanager
        def lock(path):
            self.events.append("locked")
            try:
                yield
            finally:
                self.events.append("unlocked")
        for name, value in (("startup_lock", lock), ("read_endpoint", Mock(return_value=self.descriptor)),
                            ("_connect_existing", Mock(return_value=self.proxy)),
                            ("_start_host", Mock(side_effect=AssertionError("must not start host")))):
            p = patch.object(guard.broker, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.writer = SimpleNamespace(reader=SimpleNamespace(pid=123), stamp=("worldapart.exe", 456))

    def call(self, command, payload=None, **kw):
        self.events.append((command, payload))
        if command == "claim_scalar":
            return {"claimed": True}
        return {"released": False, "uncertain": True} if payload.get("uncertain") else {"released": True}

    def wrapped(self, method):
        return guard.coordinated_scalar_write(method)

    def test_no_host_means_no_rpc_or_process_creation(self):
        guard.broker.read_endpoint.return_value = None
        method = self.wrapped(lambda writer: self.events.append("validated_and_written"))
        method(self.writer)
        self.assertEqual(self.events, ["locked", "validated_and_written", "unlocked"])
        guard.broker._connect_existing.assert_not_called()
        guard.broker._start_host.assert_not_called()

    def test_lock_and_lease_cover_validation_write_and_release(self):
        method = self.wrapped(lambda writer: self.events.append("validated_and_written"))
        method(self.writer)
        self.assertEqual(self.events, ["locked", ("claim_scalar", None), "validated_and_written",
                                     ("release_scalar", {"uncertain": False}), "unlocked"])
        self.proxy.close_transport.assert_called_once()

    def test_busy_claim_or_dead_host_never_enters_writer(self):
        action = Mock()
        self.proxy.call.side_effect = Refused("native busy")
        with self.assertRaises(Refused):
            self.wrapped(action)(self.writer)
        action.assert_not_called()
        self.proxy.close_transport.assert_called_once()
        guard.broker._connect_existing.return_value = None
        with self.assertRaises(Refused):
            self.wrapped(action)(self.writer)
        action.assert_not_called()
        guard.broker._start_host.assert_not_called()

    def test_invalid_endpoint_and_unconfirmed_claim_never_enter_writer(self):
        action = Mock()
        guard.broker.read_endpoint.side_effect = OSError("unreadable")
        with self.assertRaises(Refused):
            self.wrapped(action)(self.writer)
        guard.broker.read_endpoint.side_effect = None
        self.proxy.call.return_value = {"claimed": False}
        self.proxy.call.side_effect = None
        with self.assertRaises(Refused):
            self.wrapped(action)(self.writer)
        action.assert_not_called()

    def test_prewrite_refusal_releases_safe_and_preserves_refusal(self):
        method = self.wrapped(Mock(side_effect=Refused("target changed")))
        with self.assertRaisesRegex(Refused, "target changed") as caught:
            method(self.writer)
        self.assertNotIsInstance(caught.exception, UncertainWrite)
        self.assertIn(("release_scalar", {"uncertain": False}), self.events)

    def test_partial_or_unexpected_write_failure_marks_host_uncertain(self):
        for error in (UncertainWrite("partial"), OSError("WPM failed")):
            self.events.clear()
            with self.assertRaises(type(error)):
                self.wrapped(Mock(side_effect=error))(self.writer)
            self.assertIn(("release_scalar", {"uncertain": True}), self.events)

    def test_failed_release_after_success_is_uncertain_not_safe_retry(self):
        self.proxy.call.side_effect = [{"claimed": True}, Refused("connection lost")]
        action = Mock()
        with self.assertRaises(UncertainWrite):
            self.wrapped(action)(self.writer)
        action.assert_called_once()
        self.proxy.close_transport.assert_called_once()
        self.assertEqual(self.events[-1], "unlocked")

    def test_failed_release_after_prewrite_refusal_remains_no_write(self):
        self.proxy.call.side_effect = [{"claimed": True}, Refused("connection lost")]
        with self.assertRaises(Refused) as caught:
            self.wrapped(Mock(side_effect=Refused("changed")))(self.writer)
        self.assertNotIsInstance(caught.exception, UncertainWrite)

    def test_invalid_process_identity_never_claims(self):
        for pid, stamp in ((True, ("path", 1)), (0, ("path", 1)), (1, ("path", 0)), (1, ())):
            writer = SimpleNamespace(reader=SimpleNamespace(pid=pid), stamp=stamp)
            with self.assertRaises(Refused):
                self.wrapped(Mock())(writer)
        self.proxy.call.assert_not_called()

    def test_mutex_failure_is_known_no_write(self):
        action = Mock()
        with patch.object(guard.broker, "startup_lock", side_effect=OSError("mutex unavailable")), \
             self.assertRaises(Refused) as caught:
            self.wrapped(action)(self.writer)
        self.assertNotIsInstance(caught.exception, UncertainWrite)
        action.assert_not_called()

    def test_host_must_confirm_it_kept_uncertain_lease_blocked(self):
        self.proxy.call.side_effect = [{"claimed": True}, {"released": True}]
        with self.assertRaises(UncertainWrite):
            self.wrapped(Mock(side_effect=OSError("partial")))(self.writer)

    def test_validation_is_after_wait_not_before(self):
        state = {"expected": 1, "actual": 1}
        def call(command, payload=None, **kw):
            if command == "claim_scalar":
                state["actual"] = 2
            return self.call(command, payload, **kw)
        self.proxy.call.side_effect = call
        written = Mock()
        def action(writer):
            if state["actual"] != state["expected"]:
                raise Refused("changed while queued")
            written()
        with self.assertRaises(Refused):
            self.wrapped(action)(self.writer)
        written.assert_not_called()

    def test_real_writer_revalidates_old_value_after_scalar_claim(self):
        import native_write as nw
        current = bytearray(struct.pack("<i", 2))
        kernel = Mock(OpenProcess=Mock(return_value=123))
        def query(handle, address, ptr, size):
            ptr._obj.BaseAddress, ptr._obj.RegionSize = 0x1000, 0x1000
            ptr._obj.State, ptr._obj.Type, ptr._obj.Protect = 0x1000, 0x20000, 4
            return size
        kernel.VirtualQueryEx.side_effect = query
        def call(command, payload=None, **kw):
            if command == "claim_scalar":
                current[:] = struct.pack("<i", 3)
            return self.call(command, payload, **kw)
        self.proxy.call.side_effect = call
        writer = nw.WriteOnce(self.writer.reader, self.writer.stamp,
                Target("root", 0x1000, 2, ("player",), 0, 1000), new_value=4)
        with patch.object(nw, "K", kernel), patch.object(nw, "process_identity", return_value=self.writer.stamp), \
                patch.object(nw, "read_exact_handle", side_effect=lambda *args: bytes(current)), self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        kernel.WriteProcessMemory.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)
        self.assertIn(("release_scalar", {"uncertain": False}), self.events)

    def test_every_low_level_wpm_owner_is_coordinated(self):
        from native_write import WriteOnce
        from learning_write import FloatWriteOnce
        from learning_completion import _CompletionWriteOnce
        from meridian_write import MeridianWriteOnce
        from character_attributes_write import AttributeWriteOnce
        from character_attributes_interact_write import InteractWriteOnce
        for cls in (WriteOnce, FloatWriteOnce, _CompletionWriteOnce, MeridianWriteOnce, AttributeWriteOnce):
            self.assertTrue(getattr(cls.write_exact, "_scalar_coordinated", False), cls.__name__)
        # The Int32 subclass delegates to the already coordinated base method,
        # avoiding nested claim_scalar attempts against the same host.
        self.assertIs(InteractWriteOnce.__base__, AttributeWriteOnce)


if __name__ == "__main__":
    unittest.main()
