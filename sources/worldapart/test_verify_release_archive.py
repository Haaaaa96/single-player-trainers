"""Small synthetic ZIPs exercise the public package gate without running an EXE."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

import verify_release_archive as verifier


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'release'
        self.archive = self.root / 'WorldApartTrainer-1.0.zip'
        self.data = {name: (f'Public license text: {name}\n').encode()
                     for name in verifier.PAYLOAD}
        self.data['WorldApartTrainer.exe'] = b'MZ\x00offline-exe-fixture'
        self.data['README.md'] = '# WorldApartTrainer v1.0 免费分享测试版\n%LOCALAPPDATA%\\WorldApartTrainer\n'.encode()
        self.freeze()

    def freeze(self):
        self.data[verifier.MANIFEST] = ''.join(
            f'{verifier.sha256(self.data[name])}  {name}\n' for name in verifier.PAYLOAD).encode()
        self.exe_hash = verifier.sha256(self.data['WorldApartTrainer.exe'])
        self.write_source()
        self.pack()

    def write_source(self):
        for name, data in self.data.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def pack(self, entries=None):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_STORED) as archive:
                for name, data in (entries if entries is not None else self.data.items()):
                    archive.writestr(name, data)

    def verify(self, **changes):
        args = dict(expected_version='1.0', exe_sha256=self.exe_hash, source_dir=self.source)
        args.update(changes)
        return verifier.verify_archive(self.archive, **args)

    def test_valid_exact_nine_files_hashes_and_source_match_without_modification(self):
        before = {name: (self.source / name).read_bytes() for name in self.data}
        result = self.verify()
        self.assertTrue(result['passed'])
        self.assertTrue(result['crc_ok'])
        self.assertEqual(result['entry_count'], 9)
        self.assertEqual({entry['name'] for entry in result['entries']}, set(verifier.EXPECTED_ENTRIES))
        self.assertEqual(result['frozen_executable_sha256'], self.exe_hash)
        self.assertEqual(result['package_sha256'], verifier.sha256(self.archive.read_bytes()))
        self.assertEqual(before, {name: (self.source / name).read_bytes() for name in self.data})
        self.pack(reversed(list(self.data.items())))
        self.assertTrue(self.verify()['passed'])

    def test_missing_or_extra_zip_member_is_rejected(self):
        for name in ('licenses/Frida-COPYING.LIB.txt', 'README.md'):
            with self.subTest(missing=name):
                self.pack((n, value) for n, value in self.data.items() if n != name)
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'missing='):
                    self.verify()
        for name in ('GameAssembly.dll', 'logs/session.json', 'FORUM_INTRO.md'):
            with self.subTest(extra=name):
                self.pack([*self.data.items(), (name, b'unwanted')])
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'extra='):
                    self.verify()

    def test_duplicate_and_case_colliding_members_are_rejected(self):
        for name in ('README.md', 'readme.md'):
            with self.subTest(name=name):
                self.pack([*self.data.items(), (name, self.data['README.md'])])
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, '(Duplicate|Case-colliding)'):
                    self.verify()

    def test_traversal_absolute_and_windows_member_paths_are_rejected(self):
        for name in ('../leak.txt', '/leak.txt', 'C:/leak.txt', 'licenses\\leak.txt', 'licenses/../leak.txt'):
            with self.subTest(name=name):
                info = zipfile.ZipInfo(name)
                # Preserve the deliberately invalid path; Windows ZipInfo
                # otherwise normalizes backslashes before writing the fixture.
                info.filename = info.orig_filename = name
                self.pack([*self.data.items(), (info, b'unwanted')])
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'Unsafe ZIP member'):
                    self.verify()
        self.assertFalse((self.root / 'leak.txt').exists())

    def test_symlink_entry_is_rejected_even_with_whitelisted_name_and_bytes(self):
        info = zipfile.ZipInfo('README.md')
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        self.pack([(info if name == 'README.md' else name, data) for name, data in self.data.items()])
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'regular file'):
            self.verify()

    def test_crc_corruption_is_rejected(self):
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.getinfo('WorldApartTrainer.exe')
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data = bytearray(self.archive.read_bytes())
        data[offset] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'CRC'):
            self.verify()

    def test_zip_bytes_must_match_frozen_source_even_if_lengths_are_equal(self):
        changed = dict(self.data)
        changed['README.md'] = changed['README.md'].replace(b'v1.0', b'v2.0')
        self.pack(changed.items())
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'ZIP/source bytes differ: README'):
            self.verify()

    def test_zip_size_mismatch_is_rejected_before_decompression(self):
        changed = dict(self.data, **{'README.md': self.data['README.md'] + b'larger'})
        self.pack(changed.items())
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'ZIP/source size mismatch'):
            self.verify()

    def test_manifest_requires_exact_eight_unique_payload_names(self):
        original = self.data[verifier.MANIFEST]
        lines = original.splitlines()
        cases = [b'\n'.join(lines[:-1]), b'\n'.join([*lines, lines[0]]),
                 b'\n'.join([lines[0], lines[0], *lines[2:]]),
                 original.replace(b'README.md', b'SHA256SUMS.txt'),
                 original.replace(b'  README.md', b' README.md')]
        for manifest in cases:
            with self.subTest(manifest=manifest[:90]):
                self.data[verifier.MANIFEST] = manifest
                self.write_source()
                self.pack()
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'SHA256SUMS'):
                    self.verify()

    def test_manifest_bad_digest_cannot_approve_matching_zip_and_source(self):
        lines = self.data[verifier.MANIFEST].splitlines()
        lines[1] = b'0' * 64 + b'  README.md'
        self.data[verifier.MANIFEST] = b'\n'.join(lines)
        self.write_source()
        self.pack()
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'Source SHA256SUMS.txt mismatch: README'):
            self.verify()

    def test_frozen_exe_hash_parameter_is_required_and_must_match(self):
        for checksum in ('', 'not-a-hash', '0' * 64):
            with self.subTest(checksum=checksum), self.assertRaisesRegex(verifier.ArchiveVerificationError, 'SHA256'):
                self.verify(exe_sha256=checksum)

    def test_first_line_requires_exact_version_not_an_old_or_longer_version(self):
        for text in ('# WorldApartTrainer v1.0.1\n', '# WorldApartTrainer 11.0\n',
                     '# WorldApartTrainer 0.9\nVersion 1.0\n'):
            with self.subTest(text=text):
                self.data['README.md'] = text.encode()
                self.freeze()
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'first-line version'):
                    self.verify()
        self.data['README.md'] = b'# WorldApartTrainer release-candidate\n'
        self.freeze()
        self.assertTrue(self.verify(expected_version='release-candidate')['passed'])

    def test_private_text_is_rejected_without_echoing_the_private_value(self):
        markers = [r'C:\Users\Someone\secret', 'D:/Users/Someone/secret',
                   'https://github.com/private-owner/codex-reports/blob/main/notes.md',
                   '../reports/2026/private.md', 'DESKTOP-EXAMPLE',
                   'D:/GameBackups/WorldApart/save', '/home/someone/private',
                   'D:/CodexData/GameBackups/WorldApart/save',
                   r'D:\CodexData\GameTrainerBackups\WorldApart\receipt',
                   'D:/GameTrainerBackups/WorldApart/receipt']
        for marker in markers:
            with self.subTest(marker=marker):
                self.data['README.md'] = ('# WorldApartTrainer 1.0\n' + marker).encode()
                self.freeze()
                with self.assertRaises(verifier.ArchiveVerificationError) as caught:
                    self.verify()
                self.assertIn('Private text found', str(caught.exception))
                self.assertNotIn(marker, str(caught.exception))

    def test_custom_private_task_marker_and_invalid_text_are_rejected(self):
        self.data['README.md'] = b'# WorldApartTrainer 1.0\nprivate-task-123'
        self.freeze()
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'supplied private marker'):
            self.verify(private_markers=['private-task-123'])
        self.data['README.md'] = b'# WorldApartTrainer 1.0\n\xff'
        self.freeze()
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'UTF-8'):
            self.verify()

    def test_missing_source_license_is_rejected(self):
        # Temporarily rename, rather than delete, the synthetic fixture file.
        source = self.source / 'licenses/Frida-COPYING.txt'
        source.rename(source.with_suffix('.saved'))
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'source file is missing'):
            self.verify()

    def test_cli_writes_success_and_failure_evidence_without_running_executable(self):
        output = self.root / 'evidence.json'
        args = [str(self.archive), '--expected-version', '1.0', '--exe-sha256', self.exe_hash,
                '--source-dir', str(self.source), '--output', str(output)]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(args), 0)
        self.assertTrue(json.loads(output.read_text())['passed'])
        self.pack([*self.data.items(), ('logs/unknown.json', b'private')])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(args), 1)
        failure = json.loads(output.read_text())
        self.assertFalse(failure['passed'])
        self.assertIn('whitelist mismatch', failure['error'])

    def test_cli_cannot_overwrite_zip_or_source_with_evidence(self):
        for output in (self.archive, self.source / 'README.md', self.source / 'new.json'):
            with self.subTest(output=output), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    verifier.main([str(self.archive), '--expected-version', '1.0',
                        '--exe-sha256', self.exe_hash, '--source-dir', str(self.source),
                        '--output', str(output)])
                self.assertEqual(caught.exception.code, 2)
        self.assertTrue(self.verify()['passed'])


class CompactReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'compact'
        self.source.mkdir()
        self.licenses = self.root / 'original-licenses'
        self.licenses.mkdir()
        self.license_texts = {}
        for name in verifier.LICENSE_NAMES:
            text = f'Original {name}\r\nKeep this complete license text.\r\n'
            (self.licenses / name).write_bytes(text.encode())
            self.license_texts[name] = text.replace('\r\n', '\n')
        self.exe = b'MZ\x00compact-offline-fixture'
        self.exe_hash = verifier.sha256(self.exe)
        self.readme = ('WorldApartTrainer v1.0\n'
                       f'SHA256 (WorldApartTrainer.exe): {self.exe_hash}\n\n' +
                       '\n'.join(self.license_texts.values()))
        self.archive = self.root / 'compact.zip'
        self.pack()

    def pack(self, extras=()):
        data = {'WorldApartTrainer.exe': self.exe, 'README.txt': self.readme.encode()}
        for name, value in data.items():
            (self.source / name).write_bytes(value)
        with zipfile.ZipFile(self.archive, 'w') as archive:
            for name, value in [*data.items(), *extras]:
                archive.writestr(name, value)

    def verify(self):
        return verifier.verify_archive(self.archive, expected_version='1.0',
            exe_sha256=self.exe_hash, source_dir=self.source, archive_format='compact',
            license_source=self.licenses)

    def test_two_file_package_and_cli_pass_with_all_five_complete_licenses(self):
        result = self.verify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['entry_count'], 2)
        self.assertTrue(result['readme_executable_sha256_valid'])
        self.assertEqual(set(result['embedded_license_sha256']), set(verifier.LICENSE_NAMES))
        self.assertTrue(result['crc_ok'])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main([str(self.archive), '--format', 'compact',
                '--expected-version', '1.0', '--exe-sha256', self.exe_hash,
                '--source-dir', str(self.source), '--license-source', str(self.licenses)]), 0)

    def test_each_missing_or_modified_license_is_rejected(self):
        original = self.readme
        for name, text in self.license_texts.items():
            for altered in ('', text.replace('complete', 'abbreviated')):
                with self.subTest(name=name, missing=not altered):
                    self.readme = original.replace(text, altered)
                    self.pack()
                    with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'complete original license'):
                        self.verify()

    def test_extra_or_missing_compact_file_is_rejected(self):
        self.pack(extras=[('SHA256SUMS.txt', b'unexpected third file')])
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'extra='):
            self.verify()
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('WorldApartTrainer.exe', self.exe)
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'missing='):
            self.verify()

    def test_readme_hash_must_be_single_exact_frozen_executable_hash(self):
        original = self.readme
        line = f'SHA256 (WorldApartTrainer.exe): {self.exe_hash}'
        for changed in (original.replace(line, ''), original + line + '\n',
                        original.replace(self.exe_hash, '0' * 64),
                        original.replace(self.exe_hash, 'not-a-hash')):
            with self.subTest(changed=changed[:100]):
                self.readme = changed
                self.pack()
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'SHA256'):
                    self.verify()

    def test_compact_readme_keeps_version_and_private_information_gates(self):
        original = self.readme
        for changed, message in ((original.replace('v1.0', 'v1.1'), 'first-line version'),
                                 (original + '\nC:\\Users\\Someone\\private', 'Private text'),
                                 (original + '\ncodex-reports', 'Private text')):
            with self.subTest(message=message):
                self.readme = changed
                self.pack()
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, message):
                    self.verify()

    def test_compact_crc_and_source_bytes_are_still_checked(self):
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.getinfo('WorldApartTrainer.exe')
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        damaged = bytearray(self.archive.read_bytes())
        damaged[offset] ^= 1
        self.archive.write_bytes(damaged)
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'CRC'):
            self.verify()
        self.pack()
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('WorldApartTrainer.exe', self.exe)
            archive.writestr('README.txt', self.readme.replace('v1.0', 'v1.1'))
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'ZIP/source bytes differ'):
            self.verify()


class ExecutableReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'executable'
        self.source.mkdir()
        self.exe = b'MZ\x00executable-only-offline-fixture'
        self.exe_hash = verifier.sha256(self.exe)
        (self.source / 'WorldApartTrainer.exe').write_bytes(self.exe)
        self.archive = self.root / 'only-exe.zip'
        self.pack()

    def pack(self, *, extra=None, payload=None):
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('WorldApartTrainer.exe', self.exe if payload is None else payload)
            if extra:
                archive.writestr(extra, 'Not part of the executable-only package')

    def verify(self, checksum=None):
        return verifier.verify_archive(self.archive, expected_version='1.0',
            exe_sha256=self.exe_hash if checksum is None else checksum,
            source_dir=self.source, archive_format='executable')

    def test_single_executable_passes_without_readme_or_external_licenses(self):
        result = self.verify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['entry_count'], 1)
        self.assertEqual(result['entries'][0]['name'], 'WorldApartTrainer.exe')
        self.assertTrue(result['crc_ok'])
        self.assertEqual(result['license_verification'], 'separate_bundle_check_required')
        self.assertEqual(result['embedded_license_sha256'], {})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main([str(self.archive), '--format', 'executable',
                '--expected-version', '1.0', '--exe-sha256', self.exe_hash,
                '--source-dir', str(self.source)]), 0)

    def test_extra_readme_or_license_is_rejected(self):
        for extra in ('README.txt', 'README.md', 'licenses/Python-LICENSE.txt'):
            with self.subTest(extra=extra):
                self.pack(extra=extra)
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'extra='):
                    self.verify()

    def test_modified_executable_wrong_hash_and_bad_crc_are_rejected(self):
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'frozen|Frozen'):
            self.verify(checksum='0' * 64)
        self.pack(payload=b'XX' + self.exe[2:])
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'ZIP/source bytes differ'):
            self.verify()
        self.pack()
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.getinfo('WorldApartTrainer.exe')
            offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
        data = bytearray(self.archive.read_bytes())
        data[offset] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'CRC'):
            self.verify()


class DocumentedReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)
        self.exe = b'MZ-documented-fixture'
        self.readme = 'WorldApartTrainer v1.3 by: Author\nUsage\n'
        (self.source / 'WorldApartTrainer.exe').write_bytes(self.exe)
        self.archive = self.source / 'release.zip'

    def pack(self, *, include_readme=True, extra=False):
        (self.source / 'README-v1.3.txt').write_text(self.readme, encoding='utf8')
        with zipfile.ZipFile(self.archive, 'w') as archive:
            archive.writestr('WorldApartTrainer.exe', self.exe)
            if include_readme:
                archive.write(self.source / 'README-v1.3.txt', 'README-v1.3.txt')
            if extra:
                archive.writestr('changes.jsonl', b'private log')

    def verify(self, version='1.3'):
        return verifier.verify_archive(self.archive, expected_version=version,
                exe_sha256=verifier.sha256(self.exe), source_dir=self.source,
            archive_format='documented')

    def test_two_file_package_with_versioned_readme(self):
        self.pack()
        result = self.verify()
        self.assertTrue(result['passed'])
        self.assertEqual(result['entry_count'], 2)
        self.assertEqual(result['license_verification'], 'separate_bundle_check_required')

    def test_missing_readme_or_extra_file_is_rejected(self):
        for options in ({'include_readme':False}, {'extra':True}):
            with self.subTest(options=options):
                self.pack(**options)
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'whitelist'):
                    self.verify()

    def test_wrong_version_private_text_and_unsafe_version_are_rejected(self):
        for text, reason in (('WorldApartTrainer v1.2\n', 'version'),
                             ('WorldApartTrainer v1.3\nC:\\Users\\Someone\\private', 'Private')):
            with self.subTest(reason=reason):
                self.readme = text
                self.pack()
                with self.assertRaisesRegex(verifier.ArchiveVerificationError, reason):
                    self.verify()
        with self.assertRaisesRegex(verifier.ArchiveVerificationError, 'safe'):
            self.verify('../1.3')


if __name__ == '__main__':
    unittest.main()
