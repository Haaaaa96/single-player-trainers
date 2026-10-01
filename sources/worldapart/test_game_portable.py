"""Offline process/path regressions. Every OS process operation is mocked."""
from contextlib import ExitStack
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import game_adapter as adapter
from game_install import GameInstallation
import learning_adapter
import probe
from write_guard import Refused


FIRST = Path(r'D:\Steam Library 游戏\不同凡尘\WorldApart.exe')
SECOND = Path(r'C:\Other Games\WorldApart.exe')


def installation(path):
    path = Path(path)
    return GameInstallation(path, path.parent)


class ReaderPathTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.open = self.stack.enter_context(patch.object(probe.K, 'OpenProcess', return_value=700))
        self.close = self.stack.enter_context(patch.object(probe.K, 'CloseHandle'))
        self.actual = str(FIRST)
        def query(handle, flags, buffer, size):
            buffer.value = self.actual
            return True
        self.query = self.stack.enter_context(patch.object(probe.K, 'QueryFullProcessImageNameW', side_effect=query))
        self.validate = self.stack.enter_context(patch.object(probe, 'validate_installation', side_effect=installation))
        self.regions = self.stack.enter_context(patch.object(probe.Reader, 'iter_regions', return_value=[]))

    def test_real_process_path_is_hashed_before_regions_are_read(self):
        events = []
        self.validate.side_effect = lambda path: (events.append(('validate', path)), installation(path))[1]
        self.regions.side_effect = lambda: (events.append(('regions',)), [])[1]
        reader = probe.Reader(12, expected_path=FIRST)
        self.addCleanup(reader.close)
        self.assertEqual(events, [('validate', str(FIRST)), ('regions',)])
        self.assertEqual(reader.path, str(FIRST))
        self.assertEqual(reader.install_directory, FIRST.parent)
        self.open.assert_called_once_with(0x410, False, 12)

    def test_manual_path_mismatch_closes_before_hashing_or_memory(self):
        with self.assertRaisesRegex(Refused, '路径不同'):
            probe.Reader(12, expected_path=SECOND)
        self.close.assert_called_once_with(700)
        self.validate.assert_not_called()
        self.regions.assert_not_called()

    def test_wrong_process_name_closes_before_hashing_or_memory(self):
        self.actual = str(FIRST.with_name('SomethingElse.exe'))
        with self.assertRaisesRegex(Refused, '目标进程不是'):
            probe.Reader(12)
        self.close.assert_called_once_with(700)
        self.validate.assert_not_called()
        self.regions.assert_not_called()

    def test_version_failure_closes_before_memory(self):
        self.validate.side_effect = Refused('版本不匹配')
        with self.assertRaisesRegex(Refused, '版本不匹配'):
            probe.Reader(12)
        self.close.assert_called_once_with(700)
        self.regions.assert_not_called()

    def test_path_query_failure_closes(self):
        self.query.side_effect = None
        self.query.return_value = False
        with self.assertRaisesRegex(Refused, '真实路径'):
            probe.Reader(12)
        self.close.assert_called_once_with(700)
        self.validate.assert_not_called()

    def test_invalid_pid_never_calls_os(self):
        for pid in (None, True, 0, -1, 2**32, '12'):
            with self.subTest(pid=pid), self.assertRaises(Refused):
                probe.Reader(pid)
            with self.subTest(path_pid=pid), self.assertRaises(Refused):
                probe.process_path(pid)
        self.open.assert_not_called()

    def test_close_is_idempotent(self):
        reader = probe.Reader(12)
        reader.close()
        reader.close()
        self.close.assert_called_once_with(700)

    def test_process_path_uses_limited_query_rights_and_always_closes(self):
        self.assertEqual(probe.process_path(12), str(FIRST))
        self.open.assert_called_once_with(0x1000, False, 12)
        self.close.assert_called_once_with(700)
        self.validate.assert_not_called()
        self.regions.assert_not_called()

    def test_process_path_query_failure_still_closes(self):
        self.query.side_effect = None
        self.query.return_value = False
        with self.assertRaises(OSError):
            probe.process_path(12)
        self.close.assert_called_once_with(700)


class MappingTests(unittest.TestCase):
    def setUp(self):
        def device(drive, buffer, size):
            devices = {'c:': r'\Device\HarddiskVolume3', 'd:': r'\Device\HarddiskVolume7'}
            buffer.value = devices.get(drive.casefold(), '')
            return len(buffer.value)
        p = patch.object(probe.K, 'QueryDosDeviceW', side_effect=device)
        p.start()
        self.addCleanup(p.stop)

    def test_nt_device_path_matches_actual_drive_unicode_and_case(self):
        self.assertTrue(probe.mapped_path_matches(
            r'\Device\HarddiskVolume7\Steam Library 游戏\不同凡尘\GameAssembly.dll',
            FIRST.parent / 'GameAssembly.dll'))

    def test_same_suffix_on_other_volume_does_not_match(self):
        self.assertFalse(probe.mapped_path_matches(
            r'\Device\HarddiskVolume3\Steam Library 游戏\不同凡尘\GameAssembly.dll',
            FIRST.parent / 'GameAssembly.dll'))

    def test_dos_extended_and_unc_paths(self):
        self.assertTrue(probe.mapped_path_matches(r'\\?\D:\Games\GameAssembly.dll', r'D:\Games\GameAssembly.dll'))
        self.assertTrue(probe.mapped_path_matches(r'\Device\Mup\server\游戏\GameAssembly.dll',
                                                r'\\server\游戏\GameAssembly.dll'))
        self.assertFalse(probe.mapped_path_matches('', FIRST.parent / 'GameAssembly.dll'))
        self.assertFalse(probe.mapped_path_matches(r'\Device\Unknown\a.dll', r'Z:\a.dll'))

    def reader(self, *, other_metadata=False, duplicate=False, wrong_assembly=False):
        meta_path = (SECOND if other_metadata else FIRST).parent / 'WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat'
        dll_path = (SECOND if wrong_assembly else FIRST).parent / 'GameAssembly.dll'
        regions = [dict(base=0x1000, allocation=0x1000, type=0x1000000, protect=0x20, size=0x1000),
                   dict(base=0x3000, allocation=0x3000, type=0x40000, protect=2, size=0x1000)]
        if duplicate:
            regions.append(dict(base=0x5000, allocation=0x5000, type=0x40000, protect=2, size=0x1000))
        return SimpleNamespace(pid=12, path=str(FIRST), install_directory=FIRST.parent, regions=regions,
            mapped=lambda address: str(dll_path if address == 0x1000 else meta_path),
            read=lambda address, size: b'MZ\0\0\0\0\0\0' if address == 0x1000 else struct.pack('<II', 0xfab11baf, 31))

    def test_verified_mapping_requires_both_files_from_selected_directory(self):
        maps = probe.verified_mappings(self.reader())
        self.assertEqual(maps['game_assembly'][0]['base'], 0x1000)
        self.assertTrue(maps['metadata'][0]['installation_matches'])

    def test_wrong_metadata_module_or_duplicate_is_rejected(self):
        for options in ({'other_metadata': True}, {'wrong_assembly': True}, {'duplicate': True}):
            with self.subTest(options=options), self.assertRaisesRegex(Refused, '唯一'):
                probe.verified_mappings(self.reader(**options))


class AdapterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.paths = {10: FIRST, 20: SECOND}
        self.stamps = {10: (10, 100), 20: (20, 200), 1010: (10, 100), 1020: (20, 200)}
        self.readers = []
        self.resolvers = []
        self.pids = self.stack.enter_context(patch.object(adapter, 'game_pids', return_value=[10]))
        self.path = self.stack.enter_context(patch.object(probe, 'process_path', side_effect=lambda pid: str(self.paths[pid])))
        self.validate = self.stack.enter_context(patch.object(adapter, 'validate_installation', side_effect=installation))
        def reader(pid, *, expected_path):
            result = SimpleNamespace(pid=pid, h=pid, path=str(self.paths[pid]),
                                     installation=installation(self.paths[pid]), close=Mock())
            self.readers.append(result)
            return result
        self.reader = self.stack.enter_context(patch.object(probe, 'Reader', side_effect=reader))
        self.maps = self.stack.enter_context(patch.object(probe, 'verified_mappings', return_value={}))
        self.identity = self.stack.enter_context(patch.object(adapter, 'process_identity', side_effect=lambda handle: self.stamps[handle]))
        def resolver(pid, *, expected_path):
            result = SimpleNamespace(reader=SimpleNamespace(h=1000 + pid), resolve=Mock(), close=Mock())
            self.resolvers.append(result)
            return result
        self.resolver = self.stack.enter_context(patch.object(adapter, 'Resolver', side_effect=resolver))
        self.discover = self.stack.enter_context(patch.object(adapter, 'connect_discover'))
        self.snapshot = self.stack.enter_context(patch.object(adapter.GameAdapter, 'snapshot', return_value={}))

    def test_auto_exposes_real_install_and_closes_selection_handle(self):
        game = adapter.GameAdapter()
        self.addCleanup(game.close)
        self.assertEqual(game.executable_path, FIRST)
        self.assertEqual(game.game_path, FIRST)
        self.assertEqual(game.install_directory, FIRST.parent)
        self.reader.assert_called_once_with(10, expected_path=str(FIRST))
        self.resolver.assert_called_once_with(10, expected_path=FIRST)
        self.readers[0].close.assert_called_once()
        self.discover.assert_not_called()

    def test_launcher_is_skipped_when_unique_verified_main_exists(self):
        self.pids.return_value = [20, 10]
        self.maps.side_effect = lambda reader: (_ for _ in ()).throw(Refused('未加载')) if reader.pid == 20 else {}
        game = adapter.GameAdapter()
        self.addCleanup(game.close)
        self.assertEqual(game.executable_path, FIRST)
        self.assertTrue(all(reader.close.call_count == 1 for reader in self.readers))

    def test_two_verified_main_processes_require_selection(self):
        self.pids.return_value = [10, 20]
        with self.assertRaisesRegex(Refused, '多个'):
            adapter.GameAdapter()
        self.resolver.assert_not_called()
        self.discover.assert_not_called()
        self.assertTrue(all(reader.close.call_count == 1 for reader in self.readers))

    def test_manual_selection_filters_other_installation(self):
        self.pids.return_value = [10, 20]
        game = adapter.GameAdapter(game_path=SECOND)
        self.addCleanup(game.close)
        self.assertEqual(game.executable_path, SECOND)
        self.reader.assert_called_once_with(20, expected_path=str(SECOND))
        self.resolver.assert_called_once_with(20, expected_path=SECOND)

    def test_two_instances_same_selected_path_are_rejected(self):
        self.paths[20] = FIRST
        self.pids.return_value = [10, 20]
        with self.assertRaisesRegex(Refused, '多个'):
            adapter.GameAdapter(game_path=FIRST)
        self.resolver.assert_not_called()

    def test_manual_not_running_never_falls_back_to_other_install(self):
        with self.assertRaisesRegex(Refused, '其他安装位置'):
            adapter.GameAdapter(game_path=SECOND)
        self.reader.assert_not_called()
        self.resolver.assert_not_called()
        self.discover.assert_not_called()

    def test_cancel_or_invalid_manual_install_rejected_before_process_enumeration(self):
        self.validate.side_effect = Refused('未选择或版本错误')
        with self.assertRaises(Refused):
            adapter.GameAdapter(game_path='')
        self.pids.assert_not_called()
        self.reader.assert_not_called()

    def test_wrong_running_version_fails_without_discovery(self):
        self.reader.side_effect = Refused('版本不匹配：GameAssembly.dll')
        with self.assertRaisesRegex(Refused, '版本不匹配'):
            adapter.GameAdapter()
        self.resolver.assert_not_called()
        self.discover.assert_not_called()

    def test_rediscovery_keeps_selected_path_locked(self):
        factory = self.resolver.side_effect
        count = 0
        def fail_first(pid, *, expected_path):
            nonlocal count
            count += 1
            if count == 1:
                raise RuntimeError('stale cached discovery')
            return factory(pid, expected_path=expected_path)
        self.resolver.side_effect = fail_first
        game = adapter.GameAdapter(game_path=FIRST)
        self.addCleanup(game.close)
        self.discover.assert_called_once_with(10, expected_path=FIRST)
        self.assertEqual(self.resolver.call_args_list[0], self.resolver.call_args_list[1])

    def test_process_restart_is_rejected_before_snapshot(self):
        self.stamps[1010] = (10, 999)
        with self.assertRaisesRegex(Refused, '已重启'):
            adapter.GameAdapter()
        self.snapshot.assert_not_called()
        self.discover.assert_not_called()
        self.assertTrue(all(resolver.close.call_count == 1 for resolver in self.resolvers))

    def test_no_running_process_does_not_discover(self):
        self.pids.return_value = []
        with self.assertRaisesRegex(Refused, '未找到正在运行'):
            adapter.GameAdapter()
        self.resolver.assert_not_called()
        self.discover.assert_not_called()


class LearningInstallationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.reader = SimpleNamespace(path=str(FIRST), h=100, read=Mock(return_value=bytes.fromhex('48 8b 0d 1e 6a b6 06')))
        self.stack.enter_context(patch.object(learning_adapter, 'process_identity', return_value=(12, 1000)))
        self.validate = self.stack.enter_context(patch.object(learning_adapter, 'validate_installation', side_effect=installation))
        self.maps = self.stack.enter_context(patch.object(probe, 'verified_mappings', return_value={
            'metadata': [{'base': 0x1000}], 'game_assembly': [{'base': 0x5000}]}))

    def test_subresolver_uses_reader_installation_and_verified_module(self):
        result = learning_adapter.LearningResolver(self.reader, metadata_base=0x1000)
        self.validate.assert_called_once_with(str(FIRST))
        self.assertEqual(result.install_directory, FIRST.parent)
        self.assertEqual((result.meta, result.module), (0x1000, 0x5000))
        self.assertIs(result._runtime.reader, self.reader)
        self.assertEqual(result._runtime.meta, 0x1000)
        self.assertIs(result._runtime, self.reader._extension_runtime)
        repeated = learning_adapter.LearningResolver(self.reader, metadata_base=0x1000)
        self.assertIs(repeated._runtime, result._runtime)
        self.reader.read.assert_not_called()  # Current metadata is resolved lazily; no old UI slot gate.

    def test_explicit_wrong_metadata_or_module_is_rejected_before_code_read(self):
        for options in ({'metadata_base': 0x2000}, {'module_base': 0x6000}):
            with self.subTest(options=options), self.assertRaisesRegex(Refused, '映射不一致'):
                learning_adapter.LearningResolver(self.reader, **options)
        self.reader.read.assert_not_called()

    def test_changed_installation_is_rejected_before_mapping_or_code_read(self):
        self.validate.side_effect = Refused('版本不匹配')
        with self.assertRaisesRegex(Refused, '版本不匹配'):
            learning_adapter.LearningResolver(self.reader)
        self.maps.assert_not_called()
        self.reader.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
