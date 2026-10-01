"""Mock every process API; these tests never open or modify a real process."""
import ctypes as C
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import native_write as native
from write_guard import PreconditionChanged, Refused, Target


class NativeWriteTests(unittest.TestCase):
    def setUp(self):
        self.target = Target("root", 0x1000, 2, ("player",), 0, 1000)
        self.reader = SimpleNamespace(h=101, pid=202)
        self.stamp = ("fake-worldapart.exe", 303)
        self.api = SimpleNamespace(OpenProcess=Mock(return_value=404),
                                   CloseHandle=Mock(return_value=True),
                                   VirtualQueryEx=Mock(side_effect=self.query),
                                   WriteProcessMemory=Mock(side_effect=self.write))
        self.api_patch = patch.object(native, "K", self.api)
        self.identity_patch = patch.object(native, "process_identity", return_value=self.stamp)
        self.read_patch = patch.object(native, "read_exact_handle", return_value=struct.pack("<i", 2))
        self.api_patch.start()
        self.identity = self.identity_patch.start()
        self.read = self.read_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.addCleanup(self.identity_patch.stop)
        self.addCleanup(self.read_patch.stop)

    @staticmethod
    def query(handle, address, region_pointer, size):
        region = region_pointer._obj
        region.BaseAddress, region.RegionSize = 0x1000, 0x1000
        region.State, region.Type, region.Protect = 0x1000, 0x20000, 4
        return size

    @staticmethod
    def write(handle, address, buffer, size, count_pointer):
        count_pointer._obj.value = size
        return True

    def writer(self, new_value=1000):
        return native.WriteOnce(self.reader, self.stamp, self.target, new_value=new_value)

    def assert_closed_without_write(self):
        self.api.CloseHandle.assert_called_once_with(404)
        self.api.WriteProcessMemory.assert_not_called()

    def test_absolute_payload_single_write_handle_closed(self):
        writer = self.writer()
        writer.write_exact(0x1000, struct.pack("<i", 1000))
        self.api.OpenProcess.assert_called_once_with(0x438, False, 202)
        call = self.api.WriteProcessMemory.call_args.args
        self.assertEqual(call[:2], (404, 0x1000))
        self.assertEqual(C.string_at(call[2], call[3]), struct.pack("<i", 1000))
        self.assertEqual(call[3], 4)
        self.api.CloseHandle.assert_called_once_with(404)
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, struct.pack("<i", 1000))
        self.api.WriteProcessMemory.assert_called_once()
        self.api.OpenProcess.assert_called_once()

    def test_constructor_independently_enforces_policy(self):
        for new_value in (True, 1.0, "3", "", -1, 2, 1001, 2**31):
            with self.subTest(new_value=new_value), self.assertRaises(Refused):
                self.writer(new_value)
        target = Target("item", 0x1000, 2, ("item",), 1, 10000)
        with self.assertRaises(Refused):
            native.WriteOnce(self.reader, self.stamp, target, new_value=1003)
        self.api.OpenProcess.assert_not_called()

    def test_positional_delta_cannot_be_misinterpreted_as_target(self):
        with self.assertRaises(TypeError):
            native.WriteOnce(self.reader, self.stamp, self.target, 1)
        self.api.OpenProcess.assert_not_called()

    def test_wrong_address_or_payload_never_opens_handle(self):
        writer = self.writer()
        for address, payload in ((0x2000, writer.after), (0x1000, struct.pack("<i", 3)),
                                 (0x1000, bytearray(writer.after)), (0x1000, b"123")):
            with self.subTest(address=address, payload=payload), self.assertRaises(Refused):
                writer.write_exact(address, payload)
        self.api.OpenProcess.assert_not_called()
        self.assertFalse(writer.used)

    def test_open_failure_is_not_retried(self):
        self.api.OpenProcess.return_value = 0
        writer = self.writer()
        for _ in range(2):
            with self.assertRaises(Refused):
                writer.write_exact(0x1000, writer.after)
        self.api.OpenProcess.assert_called_once()
        self.api.CloseHandle.assert_not_called()
        self.api.WriteProcessMemory.assert_not_called()

    def test_changed_process_closes_handle(self):
        self.identity.return_value = ("another.exe", 304)
        writer = self.writer()
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_identity_error_closes_handle(self):
        self.identity.side_effect = OSError("mock process query failure")
        writer = self.writer()
        with self.assertRaises(OSError):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_query_failure_closes_handle(self):
        self.api.VirtualQueryEx.side_effect = None
        self.api.VirtualQueryEx.return_value = 0
        writer = self.writer()
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_non_writable_or_outside_region_refused(self):
        for field, value in (("State", 0), ("Type", 0x1000000), ("Protect", 0x40),
                             ("BaseAddress", 0x2000), ("RegionSize", 3)):
            with self.subTest(field=field):
                self.api.CloseHandle.reset_mock()
                def query(*args):
                    result = self.query(*args)
                    setattr(args[2]._obj, field, value)
                    return result
                self.api.VirtualQueryEx.side_effect = query
                writer = self.writer()
                with self.assertRaises(Refused):
                    writer.write_exact(0x1000, writer.after)
                self.assert_closed_without_write()

    def test_stale_value_closes_handle(self):
        self.read.return_value = struct.pack("<i", 3)
        writer = self.writer()
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_read_failure_closes_handle(self):
        self.read.side_effect = OSError("mock read failure")
        writer = self.writer()
        with self.assertRaises(OSError):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_native_write_error_closes_handle_and_never_retries(self):
        self.api.WriteProcessMemory.side_effect = OSError("mock write failure")
        writer = self.writer()
        with self.assertRaises(OSError):
            writer.write_exact(0x1000, writer.after)
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        self.api.CloseHandle.assert_called_once_with(404)
        self.api.WriteProcessMemory.assert_called_once()

    def test_partial_write_closes_handle_and_never_retries(self):
        def partial(handle, address, buffer, size, count):
            count._obj.value = 2
            return True
        self.api.WriteProcessMemory.side_effect = partial
        writer = self.writer()
        with self.assertRaises(OSError):
            writer.write_exact(0x1000, writer.after)
        with self.assertRaises(Refused):
            writer.write_exact(0x1000, writer.after)
        self.api.CloseHandle.assert_called_once_with(404)
        self.api.WriteProcessMemory.assert_called_once()

    def test_reader_limits_and_identity_checked(self):
        writer = self.writer()
        for address, size in ((0x2000, 4), (0x1000, 8)):
            with self.assertRaises(Refused):
                writer.read_exact(address, size)
        self.read.assert_not_called()
        self.assertEqual(writer.read_exact(0x1000, 4), struct.pack("<i", 2))
        self.read.assert_called_once_with(101, 0x1000, 4)
        self.identity.return_value = ("restarted.exe", 999)
        with self.assertRaises(Refused):
            writer.read_exact(0x1000, 4)
        self.api.OpenProcess.assert_not_called()

    def test_battle_start_before_final_write_prevents_os_write(self):
        writer = native.WriteOnce(self.reader, self.stamp, self.target,
                                  new_value=3, preconditions=((0x9000, b'\x00'),))
        self.read.side_effect = lambda handle, address, size: b'\x01' if address == 0x9000 else struct.pack('<i', 2)
        with self.assertRaises(PreconditionChanged):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_missing_scene_memory_prevents_os_write(self):
        writer = native.WriteOnce(self.reader, self.stamp, self.target,
                                  new_value=3, preconditions=((0x9000, b'\x00'),))
        self.read.side_effect = OSError('unloaded scene')
        with self.assertRaises(PreconditionChanged):
            writer.write_exact(0x1000, writer.after)
        self.assert_closed_without_write()

    def test_scene_preconditions_use_actual_write_handle_before_write(self):
        writer = native.WriteOnce(self.reader, self.stamp, self.target,
                                  new_value=3, preconditions=((0x9000, b'\x00'),))
        calls = []
        def read(handle, address, size):
            calls.append(('read', handle, address))
            return b'\x00' if address == 0x9000 else struct.pack('<i', 2)
        self.read.side_effect = read
        def write(*args):
            calls.append(('write', args[0], args[1]))
            return self.write(*args)
        self.api.WriteProcessMemory.side_effect = write
        writer.write_exact(0x1000, writer.after)
        self.assertEqual(calls, [('read', 404, 0x9000), ('read', 404, 0x1000), ('write', 404, 0x1000)])


if __name__ == "__main__":
    unittest.main()
