"""Offline tests: no game process, memory reads, discovery or injection."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import game_connection as connection
from game_install import CompatibilityAssessment, FileFingerprint, GameInstallation, HASHES
from write_guard import Refused


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.exe = self.make_exe('第一份 游戏')
        self.other = self.make_exe('Second Game')
        self.stamps = {101: (str(self.exe).casefold(), 123456)}
        self.modules = {101: self.engine_modules(self.exe)}
        self.assessments = {str(self.exe).casefold(): self.assessment(self.exe, reviewed=False),
                            str(self.other).casefold(): self.assessment(self.other, reviewed=False)}
        self.inspected = []
        self.closed = MagicMock()
        self.normal = MagicMock()
        self.normal.pid = 101
        self.normal.stamp = self.stamps[101]
        self.normal.executable_path = self.exe
        self.normal_factory = MagicMock(return_value=self.normal)
        def inspect(path):
            self.inspected.append(str(path).casefold())
            return self.assessments[str(path).casefold()]
        patches = (
            patch.object(connection, 'game_pids', side_effect=lambda: list(self.stamps)),
            patch.object(connection, '_open_query_handle', side_effect=lambda pid: pid + 1000),
            patch.object(connection, '_close_query_handle', self.closed),
            patch.object(connection, 'process_identity', side_effect=lambda handle: self.stamps[handle - 1000]),
            patch.object(connection, '_module_paths', side_effect=lambda pid: self.modules[pid]),
            patch.object(connection, 'inspect_installation', side_effect=inspect),
            patch.object(connection, 'GameAdapter', self.normal_factory),
        )
        for patched in patches:
            patched.start()
            self.addCleanup(patched.stop)

    def make_exe(self, name):
        path = self.root / name / 'WorldApart.exe'
        path.parent.mkdir()
        path.write_bytes(b'not an executable; inspection is mocked')
        return path.resolve()

    @staticmethod
    def engine_modules(exe):
        return tuple(str(exe.parent / name) for name in ('WorldApart.exe', 'GameAssembly.dll', 'UnityPlayer.dll'))

    @staticmethod
    def assessment(exe, *, reviewed, build=None):
        files = tuple(FileFingerprint(name, expected, expected if reviewed else 'f' * 64, 20)
                      for name, expected in HASHES.items())
        return CompatibilityAssessment(GameInstallation(exe, exe.parent), files,
                                       steam_build_id=build, warnings=('compatibility notice',),
                                       metadata_version=31, metadata_header_valid=True)

    def live_close_calls(self):
        return [call.args[0] for call in self.closed.call_args_list if call.args[0]]

    def information_adapter(self):
        return connection.InformationAdapter(101, 1101, self.stamps[101],
            self.assessments[str(self.exe).casefold()], self.modules[101])

    def test_unknown_files_attempt_normal_adapter_and_preserve_warning(self):
        adapter = connection.connect_game()
        self.addCleanup(adapter.close)
        self.assertIs(adapter, self.normal)
        self.assertTrue(adapter.write_enabled)
        self.assertFalse(adapter.read_only)
        self.assertFalse(adapter.compatibility.reviewed_files_match)
        self.assertEqual(adapter.compatibility.mode, 'unreviewed')
        self.assertEqual(adapter.compatibility.warnings, ('compatibility notice',))
        self.normal_factory.assert_called_once_with(game_path=self.exe)
        self.assertEqual(self.live_close_calls(), [1101])

    def test_unknown_files_runtime_failure_is_reported_not_blank_success(self):
        self.normal_factory.side_effect = Refused('current player layout mismatch')
        with self.assertRaisesRegex(Refused, 'current player layout mismatch'):
            connection.connect_game()
        self.assertEqual(self.live_close_calls(), [1101])

    def test_extra_mod_modules_and_changed_files_do_not_disable_connection(self):
        self.modules[101] += (str(self.exe.parent / 'winhttp.dll'),
                              str(self.exe.parent / 'BepInEx' / 'plugins' / 'ExampleMod.dll'))
        adapter = connection.connect_game()
        self.assertIs(adapter, self.normal)
        self.assertTrue(adapter.write_enabled)
        self.assertEqual(adapter.compatibility.mode, 'unreviewed')
        self.normal_factory.assert_called_once_with(game_path=self.exe)

    def test_unknown_connection_modification_entrypoints_always_refuse(self):
        adapter = self.information_adapter()
        self.addCleanup(adapter.close)
        for method in (adapter.resolve, adapter.set_value, adapter.change):
            with self.subTest(method=method), self.assertRaisesRegex(Refused, '只读兼容'):
                method('arbitrary', 10)
        self.normal_factory.assert_not_called()

    def test_information_refresh_checks_only_process_identity_and_never_promotes_capability(self):
        adapter = self.information_adapter()
        self.addCleanup(adapter.close)
        self.assessments[str(self.exe).casefold()] = self.assessment(self.exe, reviewed=True)
        adapter.refresh()
        adapter.snapshot()
        self.assertEqual(len(self.inspected), 0)
        self.assertFalse(adapter.write_enabled)
        self.normal_factory.assert_not_called()

    def test_known_core_files_keep_existing_adapter_even_if_build_marker_changed(self):
        assessment = self.assessment(self.exe, reviewed=True, build='99999999')
        self.assessments[str(self.exe).casefold()] = assessment
        adapter = connection.connect_game()
        self.assertIs(adapter, self.normal)
        self.assertIs(adapter.compatibility, assessment)
        self.assertTrue(adapter.write_enabled)
        self.assertFalse(adapter.read_only)
        self.normal_factory.assert_called_once_with(game_path=self.exe)
        self.assertEqual(self.live_close_calls(), [1101])

    def test_launcher_without_engine_modules_is_ignored_when_one_main_process_exists(self):
        self.stamps[102] = (str(self.exe).casefold(), 456789)
        self.modules[102] = (str(self.exe),)
        adapter = connection.connect_game()
        self.addCleanup(adapter.close)
        self.assertEqual(adapter.pid, 101)
        self.assertEqual(self.live_close_calls(), [1102, 1101])

    def test_missing_or_wrong_installation_engine_modules_refuse(self):
        variants = ((str(self.exe),),
                    (str(self.other.parent / 'GameAssembly.dll'), str(self.exe.parent / 'UnityPlayer.dll')),
                    (str(self.exe.parent / 'GameAssembly.dll'), str(self.other.parent / 'UnityPlayer.dll')))
        for paths in variants:
            with self.subTest(paths=paths):
                self.modules[101] = paths
                with self.assertRaisesRegex(Refused, '启动器或游戏尚未就绪'):
                    connection.connect_game()
        self.normal_factory.assert_not_called()

    def test_multiple_real_processes_refuse_and_release_all_query_handles(self):
        self.stamps[102] = (str(self.other).casefold(), 456789)
        self.modules[102] = self.engine_modules(self.other)
        with self.assertRaisesRegex(Refused, '多个游戏主进程'):
            connection.connect_game()
        self.assertCountEqual(self.live_close_calls(), [1101, 1102])
        self.normal_factory.assert_not_called()

    def test_manual_choice_selects_running_copy_without_touching_other_installation(self):
        self.stamps[102] = (str(self.other).casefold(), 456789)
        self.modules[102] = self.engine_modules(self.other)
        self.normal.pid = 102
        self.normal.stamp = self.stamps[102]
        self.normal.executable_path = self.other
        adapter = connection.connect_game(self.other)
        self.addCleanup(adapter.close)
        self.assertEqual(adapter.pid, 102)
        self.assertEqual(self.inspected, [str(self.other).casefold()])
        self.assertEqual(self.live_close_calls(), [1101, 1102])

    def test_manual_choice_never_falls_back_to_other_running_copy(self):
        with self.assertRaisesRegex(Refused, '未回退'):
            connection.connect_game(self.other)
        self.assertEqual(self.inspected, [])
        self.assertEqual(self.live_close_calls(), [1101])

    def test_two_processes_for_same_selected_path_are_ambiguous(self):
        self.stamps[102] = (str(self.exe).casefold(), 456789)
        self.modules[102] = self.engine_modules(self.exe)
        with self.assertRaisesRegex(Refused, '多个游戏主进程'):
            connection.connect_game(self.exe)

    def test_invalid_manual_selection_refuses_before_enumeration(self):
        for value in ('', 'WorldApart.exe', self.exe.parent / 'Other.exe'):
            with self.subTest(value=value), self.assertRaises(Refused):
                connection.connect_game(value)
        self.assertEqual(self.inspected, [])

    def test_no_running_game_does_not_start_anything(self):
        self.stamps.clear()
        with self.assertRaisesRegex(Refused, '未找到正在运行'):
            connection.connect_game()
        self.normal_factory.assert_not_called()

    def test_restarted_pid_during_connection_refuses_and_releases_handle(self):
        with patch.object(connection, 'process_identity', side_effect=[self.stamps[101],
                           (str(self.exe).casefold(), 123457)]):
            with self.assertRaisesRegex(Refused, '进程已变化'):
                connection.connect_game()
        self.assertEqual(self.live_close_calls(), [1101])

    def test_information_refresh_detects_restart_and_remains_blocked(self):
        adapter = self.information_adapter()
        self.addCleanup(adapter.close)
        original = self.stamps[101]
        self.stamps[101] = (original[0], original[1] + 1)
        with self.assertRaisesRegex(Refused, '进程已变化'):
            adapter.snapshot()
        self.stamps[101] = original
        with self.assertRaisesRegex(Refused, '连接已关闭'):
            adapter.snapshot()

    def test_information_close_is_idempotent_and_closed_snapshot_refuses(self):
        adapter = self.information_adapter()
        adapter.close()
        adapter.close()
        self.assertEqual(self.live_close_calls(), [1101])
        with self.assertRaisesRegex(Refused, '连接已关闭'):
            adapter.snapshot()

    def test_failed_normal_adapter_never_falls_back_to_information_mode(self):
        self.assessments[str(self.exe).casefold()] = self.assessment(self.exe, reviewed=True)
        self.normal_factory.side_effect = Refused('runtime validation failed')
        with self.assertRaisesRegex(Refused, 'runtime validation failed'):
            connection.connect_game()
        self.assertEqual(self.live_close_calls(), [1101])

    def test_normal_adapter_returning_new_process_is_closed_and_rejected(self):
        self.assessments[str(self.exe).casefold()] = self.assessment(self.exe, reviewed=True)
        self.normal.stamp = (str(self.exe).casefold(), 999999)
        with self.assertRaisesRegex(Refused, '已重启'):
            connection.connect_game()
        self.normal.close.assert_called_once()

    def test_normal_identity_failure_before_handoff_releases_handle(self):
        with patch.object(connection, 'process_identity', side_effect=[self.stamps[101],
                           self.stamps[101], OSError('exited')]):
            with self.assertRaisesRegex(OSError, 'exited'):
                connection.connect_game()
        self.assertEqual(self.live_close_calls(), [1101])
        self.normal.close.assert_called_once()


class QueryApiTests(unittest.TestCase):
    def test_process_open_requests_limited_query_only(self):
        kernel = SimpleNamespace(OpenProcess=MagicMock(return_value=123))
        with patch.object(connection, 'K', kernel):
            self.assertEqual(connection._open_query_handle(44), 123)
        kernel.OpenProcess.assert_called_once_with(0x1000, False, 44)

    def test_toolhelp_enumeration_returns_only_paths_and_closes_snapshot(self):
        paths = [r'D:\Game\GameAssembly.dll', r'D:\Game\UnityPlayer.dll']
        def first(handle, pointer):
            pointer._obj.szExePath = paths[0]
            return True
        def next_entry(handle, pointer):
            if pointer._obj.szExePath == paths[0]:
                pointer._obj.szExePath = paths[1]
                return True
            return False
        kernel = SimpleNamespace(CreateToolhelp32Snapshot=MagicMock(return_value=321),
                                 Module32FirstW=MagicMock(side_effect=first),
                                 Module32NextW=MagicMock(side_effect=next_entry), CloseHandle=MagicMock())
        with patch.object(connection, 'K', kernel), patch.object(connection.C, 'get_last_error', return_value=18):
            self.assertEqual(connection._module_paths(44), tuple(paths))
        kernel.CreateToolhelp32Snapshot.assert_called_once_with(0x18, 44)
        kernel.CloseHandle.assert_called_once_with(321)

    def test_partial_module_snapshot_is_rejected_and_closed(self):
        kernel = SimpleNamespace(CreateToolhelp32Snapshot=MagicMock(return_value=321),
                                 Module32FirstW=MagicMock(return_value=False), CloseHandle=MagicMock())
        with patch.object(connection, 'K', kernel), patch.object(connection.C, 'get_last_error', return_value=299):
            with self.assertRaises(OSError):
                connection._module_paths(44)
        kernel.CloseHandle.assert_called_once_with(321)


if __name__ == '__main__':
    unittest.main()
