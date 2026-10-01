"""Filesystem-only installation checks; fixture files are never executable games."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import game_install as install
from write_guard import Refused


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'Steam Library 游戏' / '任意安装位置'
        self.directory.mkdir(parents=True)
        self.exe = self.directory / 'WorldApart.exe'
        self.header = bytearray(0x80 + 24)
        self.header[:2] = b'MZ'
        struct.pack_into('<I', self.header, 0x3c, 0x80)
        self.header[0x80:0x84] = b'PE\0\0'
        struct.pack_into('<H', self.header, 0x84, 0x8664)
        self.exe.write_bytes(self.header)
        self.payloads = {'GameAssembly.dll': b'reviewed assembly fixture',
                         'WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat': b'reviewed metadata fixture'}
        for relative, payload in self.payloads.items():
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        hashes = patch.object(install, 'HASHES', {key: hashlib.sha256(value).hexdigest()
                                               for key, value in self.payloads.items()})
        hashes.start()
        self.addCleanup(hashes.stop)

    def test_unicode_and_spaces_resolve_without_default_installation(self):
        result = install.validate_installation(self.exe)
        self.assertEqual(result.executable_path, self.exe.resolve())
        self.assertEqual(result.install_directory, self.directory.resolve())

    def test_path_string_and_path_object_are_equivalent(self):
        self.assertEqual(install.validate_installation(str(self.exe)), install.validate_installation(self.exe))

    def test_changed_metadata_is_rehashed_on_next_validation(self):
        install.validate_installation(self.exe)
        (self.directory / list(self.payloads)[1]).write_bytes(b'changed')
        self.assertEqual(install.validate_installation(self.exe).executable_path, self.exe.resolve())
        self.assertEqual(install.inspect_installation(self.exe).changed_files,
                         (install.METADATA_RELATIVE,))

    def test_changed_assembly_is_advisory(self):
        (self.directory / 'GameAssembly.dll').write_bytes(b'other version')
        self.assertEqual(install.validate_installation(self.exe).executable_path, self.exe.resolve())
        self.assertEqual(install.inspect_installation(self.exe).changed_files, ('GameAssembly.dll',))

    def test_missing_each_reviewed_file_is_rejected(self):
        for relative, payload in self.payloads.items():
            with self.subTest(relative=relative):
                path = self.directory / relative
                path.unlink()
                with self.assertRaisesRegex(Refused, '缺失或无法读取'):
                    install.validate_installation(self.exe)
                path.write_bytes(payload)

    def test_cancelled_invalid_relative_and_wrong_executable_inputs_reject(self):
        for value in ('', '  ', None, 7, 'WorldApart.exe', self.directory / 'Other.exe'):
            with self.subTest(value=value), self.assertRaises(Refused):
                install.validate_installation(value)

    def test_missing_executable_rejects_even_when_sibling_data_are_valid(self):
        self.exe.unlink()
        with self.assertRaisesRegex(Refused, '找不到或无法访问'):
            install.validate_installation(self.exe)

    def test_directory_named_worldapart_is_not_program(self):
        self.exe.unlink()
        self.exe.mkdir()
        with self.assertRaisesRegex(Refused, '不是可读取'):
            install.validate_installation(self.exe)

    def test_renamed_text_file_is_not_program(self):
        self.exe.write_text('not a program', encoding='utf8')
        with self.assertRaisesRegex(Refused, '不是有效'):
            install.validate_installation(self.exe)

    def test_invalid_pe_signature_x86_or_dll_rejects(self):
        for offset, content in ((0x80, b'NOPE'), (0x84, struct.pack('<H', 0x14c)),
                                (0x80 + 22, struct.pack('<H', 0x2000))):
            with self.subTest(offset=offset):
                header = self.header.copy()
                header[offset:offset + len(content)] = content
                self.exe.write_bytes(header)
                with self.assertRaisesRegex(Refused, '不.*主程序'):
                    install.validate_installation(self.exe)

    def test_invalid_pe_offset_rejects(self):
        for offset in (0, 0xFFFFFFFF):
            with self.subTest(offset=offset):
                header = self.header.copy()
                struct.pack_into('<I', header, 0x3c, offset)
                self.exe.write_bytes(header)
                with self.assertRaisesRegex(Refused, '文件头无效'):
                    install.validate_installation(self.exe)

    def test_same_executable_handles_case_but_never_other_drive_or_folder(self):
        self.assertTrue(install.same_executable(r'D:\Steam Library 游戏\WorldApart.exe',
                                                r'd:\steam library 游戏\WORLDAPART.EXE'))
        self.assertFalse(install.same_executable(r'C:\Games\WorldApart.exe', r'D:\Games\WorldApart.exe'))
        self.assertFalse(install.same_executable(r'D:\One\WorldApart.exe', r'D:\Two\WorldApart.exe'))

    def steam_install(self, build=install.REVIEWED_STEAM_BUILD, *, app_id='1234', extra=''):
        directory = Path(self.temp.name) / 'Steam Library 游戏' / 'steamapps' / 'common' / 'A1'
        directory.mkdir(parents=True, exist_ok=True)
        self.directory, self.exe = directory, directory / 'WorldApart.exe'
        self.exe.write_bytes(self.header)
        for relative, payload in self.payloads.items():
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        manifest = directory.parent.parent / f'appmanifest_{app_id}.acf'
        manifest.write_text('"AppState"\n{\n"appid" "' + app_id + '"\n"installdir" "A1"\n'
                            '"buildid" "' + build + '"\n' + extra + '\n}\n', encoding='utf8')
        return manifest

    def test_inspection_reviewed_files_is_json_ready_and_has_no_write_targets(self):
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.mode, 'reviewed')
        self.assertTrue(assessment.reviewed_files_match)
        self.assertFalse(assessment.read_only)
        self.assertEqual(assessment.changed_files, ())
        self.assertIsNone(assessment.steam_build_id)
        report = assessment.as_dict()
        self.assertEqual(json.loads(json.dumps(report)), report)
        self.assertNotIn('targets', report)
        self.assertEqual(len(report['files']), 2)

    def test_changed_hash_warns_without_disabling_runtime_attempt(self):
        source = self.directory / 'GameAssembly.dll'
        source.write_bytes(b'a newer native implementation')
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.mode, 'unreviewed')
        self.assertFalse(assessment.read_only)
        self.assertEqual(assessment.changed_files, ('GameAssembly.dll',))
        self.assertEqual(assessment.files[0].actual_sha256, hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertTrue(any('仅作提醒' in warning for warning in assessment.warnings))
        self.assertEqual(install.validate_installation(self.exe), assessment.installation)

    def test_build_marker_change_with_identical_files_warns_and_strict_validation_continues(self):
        manifest = self.steam_install('99999999')
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.steam_build_id, '99999999')
        self.assertEqual(assessment.steam_app_id, '1234')
        self.assertEqual(assessment.steam_manifest_path, manifest.resolve())
        self.assertTrue(assessment.reviewed_files_match)
        self.assertTrue(any('两个核心文件哈希一致' in value for value in assessment.warnings))
        self.assertEqual(install.validate_installation(self.exe), assessment.installation)

    def test_unchanged_build_marker_still_reports_changed_metadata_without_locking(self):
        self.steam_install()
        (self.directory / install.METADATA_RELATIVE).write_bytes(struct.pack('<II', 0xFAB11BAF, 31) + b'new')
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.steam_build_id, install.REVIEWED_STEAM_BUILD)
        self.assertTrue(assessment.metadata_header_valid)
        self.assertEqual(assessment.metadata_version, 31)
        self.assertFalse(assessment.reviewed_files_match)
        self.assertFalse(assessment.read_only)
        self.assertEqual(install.validate_installation(self.exe), assessment.installation)

    def test_new_metadata_format_reports_parser_limit_without_version_gate(self):
        (self.directory / install.METADATA_RELATIVE).write_bytes(struct.pack('<II', 0xFAB11BAF, 32))
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.metadata_version, 32)
        self.assertFalse(assessment.read_only)
        self.assertTrue(any('实际结构不兼容' in value for value in assessment.warnings))

    def test_invalid_metadata_header_does_not_enable_old_parser(self):
        (self.directory / install.METADATA_RELATIVE).write_bytes(b'wrong header')
        assessment = install.inspect_installation(self.exe)
        self.assertFalse(assessment.metadata_header_valid)
        self.assertIsNone(assessment.metadata_version)
        self.assertFalse(assessment.read_only)
        self.assertTrue(any('可能无法读取' in value for value in assessment.warnings))

    def test_manifest_nested_depot_buildid_is_not_app_buildid(self):
        self.steam_install(extra='"InstalledDepots" { "7" { "buildid" "999" } }')
        assessment = install.inspect_installation(self.exe)
        self.assertEqual(assessment.steam_build_id, install.REVIEWED_STEAM_BUILD)
        self.assertEqual(assessment.warnings, ())

    def test_manifest_other_installation_is_ignored(self):
        manifest = self.steam_install('99999999')
        manifest.write_text(manifest.read_text(encoding='utf8').replace('"A1"', '"OtherGame"'), encoding='utf8')
        assessment = install.inspect_installation(self.exe)
        self.assertIsNone(assessment.steam_build_id)
        self.assertTrue(assessment.reviewed_files_match)

    def test_duplicate_manifest_key_is_not_trusted(self):
        self.steam_install(extra='"buildid" "99999999"')
        assessment = install.inspect_installation(self.exe)
        self.assertIsNone(assessment.steam_build_id)
        self.assertTrue(assessment.reviewed_files_match)

    def test_two_manifests_for_same_installation_have_ambiguous_marker(self):
        self.steam_install()
        self.steam_install('99999999', app_id='5678')
        assessment = install.inspect_installation(self.exe)
        self.assertIsNone(assessment.steam_build_id)
        self.assertTrue(any('多个 Steam 清单' in value for value in assessment.warnings))

    def test_invalid_or_oversized_manifest_does_not_block_reviewed_core_files(self):
        for content in ('not vdf', 'x' * (256 * 1024 + 1)):
            manifest = self.steam_install()
            manifest.write_text(content, encoding='utf8')
            with self.subTest(size=len(content)):
                self.assertIsNone(install.inspect_installation(self.exe).steam_build_id)
                self.assertEqual(install.validate_installation(self.exe).executable_path, self.exe.resolve())

    def test_source_change_during_hashing_refuses_instead_of_using_stale_fingerprint(self):
        original = hashlib.file_digest
        def changed(stream, algorithm):
            result = original(stream, algorithm)
            # Change the size as well: a same-length rewrite can retain the
            # observable timestamp while an existing Windows handle is open.
            (self.directory / 'GameAssembly.dll').write_bytes(b'changed during inspection - different size')
            return result
        with patch.object(install.hashlib, 'file_digest', side_effect=changed):
            with self.assertRaisesRegex(Refused, '兼容检测期间变化'):
                install.inspect_installation(self.exe)

    def test_empty_core_file_is_not_a_compatible_installation(self):
        (self.directory / 'GameAssembly.dll').write_bytes(b'')
        with self.assertRaisesRegex(Refused, '大小异常'):
            install.inspect_installation(self.exe)


if __name__ == '__main__':
    unittest.main()
