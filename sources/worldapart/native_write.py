"""Ephemeral user-mode access for exactly one prevalidated Int32 change."""
from native_scalar_guard import coordinated_scalar_write

import ctypes as C
from ctypes import wintypes as W
import struct
from write_guard import PreconditionChanged, Refused, validate_value

K = C.WinDLL("kernel32", use_last_error=True)
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.CloseHandle.restype = W.BOOL
K.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
K.QueryFullProcessImageNameW.restype = W.BOOL
K.GetProcessTimes.argtypes = [W.HANDLE, C.POINTER(W.FILETIME), C.POINTER(W.FILETIME),
                              C.POINTER(W.FILETIME), C.POINTER(W.FILETIME)]
K.GetProcessTimes.restype = W.BOOL
K.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                 C.POINTER(C.c_size_t)]
K.WriteProcessMemory.restype = W.BOOL
K.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t,
                                C.POINTER(C.c_size_t)]
K.ReadProcessMemory.restype = W.BOOL


class MBI(C.Structure):
    _fields_ = [("BaseAddress", C.c_void_p), ("AllocationBase", C.c_void_p),
                ("AllocationProtect", W.DWORD), ("PartitionId", W.WORD),
                ("RegionSize", C.c_size_t), ("State", W.DWORD),
                ("Protect", W.DWORD), ("Type", W.DWORD)]


K.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(MBI), C.c_size_t]
K.VirtualQueryEx.restype = C.c_size_t


def process_identity(handle):
    path = C.create_unicode_buffer(32768)
    size = W.DWORD(len(path))
    if not K.QueryFullProcessImageNameW(handle, 0, path, C.byref(size)):
        raise C.WinError(C.get_last_error())
    created, exited, kernel, user = (W.FILETIME() for _ in range(4))
    if not K.GetProcessTimes(handle, C.byref(created), C.byref(exited),
                             C.byref(kernel), C.byref(user)):
        raise C.WinError(C.get_last_error())
    if exited.dwLowDateTime or exited.dwHighDateTime:
        raise Refused("游戏进程已经退出。")
    stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
    return path.value.casefold(), stamp


def read_exact_handle(handle, address, size):
    value = C.create_string_buffer(size)
    count = C.c_size_t()
    if not K.ReadProcessMemory(handle, address, value, size, C.byref(count)) or count.value != size:
        raise Refused("无法完整读取游戏数据。")
    return value.raw


class WriteOnce:
    def __init__(self, reader, process_stamp, target, *, new_value, preconditions=()):
        # new_value is an absolute target, never a delta. Validate even when
        # callers bypass write_guard.set_value.
        validate_value(target, new_value)
        self.reader = reader
        self.stamp = process_stamp
        self.target = target
        self.before = struct.pack("<i", target.value)
        self.after = struct.pack("<i", new_value)
        self.used = False
        self.preconditions = tuple(preconditions)
        if (len(self.preconditions) > 256 or any(
                type(a) is not int or a <= 0 or type(b) is not bytes or not 1 <= len(b) <= 4096
                for a, b in self.preconditions)):
            raise Refused("附加写入条件无效。")

    def read_exact(self, address, size):
        if address != self.target.address or size != 4:
            raise Refused("读取范围不匹配。")
        if process_identity(self.reader.h) != self.stamp:
            raise Refused("游戏进程已经变化。")
        return read_exact_handle(self.reader.h, address, size)

    @coordinated_scalar_write
    def write_exact(self, address, value):
        if (self.used or address != self.target.address or type(value) is not bytes or
                value != self.after or len(value) != 4):
            raise Refused("写入与已核对目标不一致。")
        self.used = True
        # PROCESS_QUERY_INFORMATION | VM_READ | VM_WRITE | VM_OPERATION.
        # No debug privilege, remote thread, driver, injected DLL, or protection changes.
        handle = K.OpenProcess(0x438, False, self.reader.pid)
        if not handle:
            raise Refused("当前权限不能写入该进程。")
        try:
            if process_identity(handle) != self.stamp:
                raise Refused("游戏已重启，未写入。")
            region = MBI()
            if not K.VirtualQueryEx(handle, address, C.byref(region), C.sizeof(region)):
                raise Refused("目标内存不可查询。")
            if (region.State != 0x1000 or region.Type != 0x20000 or
                    region.Protect != 4 or address < region.BaseAddress or
                    address + 4 > region.BaseAddress + region.RegionSize):
                raise Refused("目标不是普通可写对象内存。")
            # Only the acquisition top-up route supplies these scene anchors.
            # Check through the actual write handle after opening/validating it,
            # immediately before the final Count comparison and OS write. This
            # is fail-closed validation, not an atomic transaction with Unity.
            for guard_address, expected in self.preconditions:
                try:
                    actual = read_exact_handle(handle, guard_address, len(expected))
                except Exception as error:
                    raise PreconditionChanged("场景状态无法复核，未写入数量；请在普通场景稳定后重试。") from error
                if actual != expected:
                    raise PreconditionChanged("场景已变化，未写入数量；战斗结束并返回普通场景后重试。")
            if read_exact_handle(handle, address, 4) != self.before:
                raise Refused("写入前数值已变化。")
            count = C.c_size_t()
            buffer = C.create_string_buffer(value)
            if not K.WriteProcessMemory(handle, address, buffer, 4, C.byref(count)) or count.value != 4:
                raise C.WinError(C.get_last_error())
        finally:
            K.CloseHandle(handle)
