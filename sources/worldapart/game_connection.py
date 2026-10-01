"""Identify one game process, then attempt verified runtime access on any build.

Release/build differences only add warnings. Live object, field and native
method checks remain responsible for accepting each supported operation.
"""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path

from game_adapter import GameAdapter, game_pids
from game_install import executable_path, inspect_installation, same_executable
from native_write import process_identity
from write_guard import Refused

K = C.WinDLL("kernel32", use_last_error=True)
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.CloseHandle.restype = W.BOOL
K.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
K.CreateToolhelp32Snapshot.restype = W.HANDLE


class MODULEENTRY32W(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD),
                ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                ("ProccntUsage", W.DWORD), ("modBaseAddr", C.c_void_p),
                ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
                ("szModule", W.WCHAR * 256), ("szExePath", W.WCHAR * 260)]


K.Module32FirstW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
K.Module32FirstW.restype = W.BOOL
K.Module32NextW.argtypes = [W.HANDLE, C.POINTER(MODULEENTRY32W)]
K.Module32NextW.restype = W.BOOL


def _open_query_handle(pid):
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        raise Refused("游戏进程编号无效。")
    handle = K.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION only.
    if not handle:
        raise OSError(C.get_last_error(), "无法查询游戏进程身份。")
    return handle


def _close_query_handle(handle):
    if handle:
        K.CloseHandle(handle)


def _module_paths(pid):
    """Enumerate names; never read a game object or retain a memory address."""
    handle = K.CreateToolhelp32Snapshot(0x18, pid)  # SNAPMODULE | SNAPMODULE32.
    if handle == C.c_void_p(-1).value or not handle:
        raise OSError(C.get_last_error(), "无法核对游戏模块路径。")
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = C.sizeof(entry)
        ok = K.Module32FirstW(handle, C.byref(entry))
        paths = []
        while ok:
            if len(paths) >= 4096:
                raise Refused("进程模块数量异常，未建立兼容信息连接。")
            if entry.szExePath:
                paths.append(entry.szExePath)
            ok = K.Module32NextW(handle, C.byref(entry))
        error = C.get_last_error()
        if error != 18:  # ERROR_NO_MORE_FILES; partial snapshots are not trusted.
            raise OSError(error, "游戏模块列表在读取时变化，请重新连接。")
        return tuple(paths)
    finally:
        K.CloseHandle(handle)


def _file_key(path):
    return os.path.normcase(str(Path(path).resolve(strict=False))).casefold()


def _verified_engine_modules(paths, installation):
    expected = {name: _file_key(installation.install_directory / name)
                for name in ("GameAssembly.dll", "UnityPlayer.dll")}
    actual = {_file_key(path) for path in paths}
    missing = [name for name, path in expected.items() if path not in actual]
    if missing:
        raise Refused("此进程尚未加载所选目录的 " + "、".join(missing)
                      + "，可能是启动器或游戏尚未就绪。")
    return tuple(str(installation.install_directory / name) for name in expected)


class InformationAdapter:
    """A live process information connection with no game-field capabilities."""
    write_enabled = False
    read_only = True
    resolver = None

    def __init__(self, pid, handle, stamp, compatibility, modules):
        if compatibility.reviewed_files_match:
            raise Refused("已核验游戏应使用正常连接，未创建兼容信息连接。")
        self.pid, self.h, self.stamp = pid, handle, stamp
        self.compatibility = compatibility
        self.game_path = self.executable_path = compatibility.installation.executable_path
        self.install_directory = compatibility.installation.install_directory
        self.modules = modules
        self.blocked = False

    def _check(self):
        if not self.h or self.blocked:
            raise Refused("兼容信息连接已关闭，请重新连接。")
        try:
            current = process_identity(self.h)
        except (OSError, Refused) as error:
            self.blocked = True
            raise Refused("原游戏进程已退出或无法确认，请重新连接。") from error
        if current != self.stamp or not same_executable(current[0], self.executable_path):
            self.blocked = True
            raise Refused("原游戏进程已变化，请重新连接；未沿用旧目标。")

    def snapshot(self):
        self._check()
        return {"read_only": True, "write_enabled": False, "pid": self.pid,
                "process_creation_filetime": self.stamp[1],
                "items": {}, "currencies": {}, "diagnostics": [],
                "compatibility": self.compatibility.as_dict(),
                "verified_module_files": list(self.modules)}

    def refresh(self):
        return self.snapshot()

    def _refuse_modification(self, *args, **kwargs):
        raise Refused("当前为只读兼容信息连接，游戏字段与原生方法尚未核验，修改功能未开放。")

    resolve = _refuse_modification
    set_value = _refuse_modification
    change = _refuse_modification

    def close(self):
        if self.h:
            handle, self.h = self.h, None
            _close_query_handle(handle)


def connect_game(game_path=None):
    """Connect exactly one actual game copy; selection never falls back."""
    selected = executable_path(game_path) if game_path is not None else None
    candidates, failures = [], []
    try:
        for pid in game_pids():
            handle = None
            try:
                handle = _open_query_handle(pid)
                stamp = process_identity(handle)
                actual_path = executable_path(stamp[0])
                if selected is not None and not same_executable(actual_path, selected):
                    continue
                assessment = inspect_installation(actual_path)
                modules = _verified_engine_modules(_module_paths(pid), assessment.installation)
                if process_identity(handle) != stamp:
                    raise Refused("兼容检测期间游戏进程已变化，请重新连接。")
                candidates.append((pid, handle, stamp, assessment, modules))
                handle = None  # Ownership stays with candidates until selection.
            except (OSError, Refused) as error:
                failures.append(str(error))
            finally:
                _close_query_handle(handle)
        if len(candidates) != 1:
            if len(candidates) > 1:
                raise Refused("检测到多个游戏主进程，请选择对应 WorldApart.exe；同一路径运行多份时请只保留一份。")
            if failures:
                raise Refused("未连接游戏：" + failures[0])
            if selected is not None:
                raise Refused("所选 WorldApart.exe 尚未运行，或运行的是其他安装位置；未回退到其他副本。")
            raise Refused("未找到正在运行的 WorldApart.exe，请先启动游戏并进入存档。")
        pid, handle, stamp, assessment, modules = candidates[0]
        adapter = GameAdapter(game_path=assessment.installation.executable_path)
        try:
            if adapter.stamp != stamp or process_identity(handle) != stamp:
                raise Refused("连接期间游戏已重启，未沿用旧进程。")
            if not same_executable(adapter.executable_path, assessment.installation.executable_path):
                raise Refused("正常连接返回了其他游戏副本，未连接。")
            adapter.compatibility = assessment
            adapter.write_enabled = True
            adapter.read_only = False
            return adapter
        except Exception:
            adapter.close()
            raise
    finally:
        for _, handle, _, _, _ in candidates:
            _close_query_handle(handle)
