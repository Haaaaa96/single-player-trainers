"""Read-only verification of the exact public WorldApartTrainer ZIP payload.

Only an explicitly requested JSON evidence file is written. This tool does not
extract files, run the executable, create a package, or contact a game process.
The frozen EXE must separately pass verify_bundle.py and standalone checks.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


PAYLOAD = (
    'WorldApartTrainer.exe',
    'README.md',
    'THIRD_PARTY_NOTICES.md',
    'licenses/Frida-COPYING.txt',
    'licenses/Frida-COPYING.LIB.txt',
    'licenses/Python-LICENSE.txt',
    'licenses/PyInstaller-COPYING.txt',
    'licenses/PyInstaller-Runtime-Notices.txt',
)
MANIFEST = 'SHA256SUMS.txt'
EXPECTED_ENTRIES = PAYLOAD + (MANIFEST,)
COMPACT_ENTRIES = ('WorldApartTrainer.exe', 'README.txt')
EXECUTABLE_ENTRIES = ('WorldApartTrainer.exe',)
LICENSE_NAMES = tuple(Path(name).name for name in PAYLOAD if name.startswith('licenses/'))

# Detect local/private information without tying this check to a user's login
# name or requiring removal of legitimate third-party authors' attributions.
# Environment-variable instructions such as %LOCALAPPDATA% remain allowed.
PRIVATE_TEXT_PATTERNS = (
    ('absolute Windows user directory', re.compile(r'(?i)\b[a-z]:[\\/]+users(?:[\\/]|\b)')),
    ('absolute Unix user directory', re.compile(r'(?i)/(?:home|Users)/[^\s/\\]+')),
    ('private report repository', re.compile(r'(?i)\bcodex-reports\b')),
    ('local report link', re.compile(r'(?i)(?:\.{1,2}[\\/])+reports[\\/]')),
    ('local backup or knowledge directory', re.compile(
        r'(?i)\b[a-z]:[\\/]+(?:CodexData|GameBackups|GameTrainerBackups|KnowledgeVault)(?:[\\/]|\b)')),
    ('private desktop name', re.compile(r'(?i)\bDESKTOP-[A-Z0-9]+\b')),
)


class ArchiveVerificationError(ValueError):
    """The ZIP or its claimed release inputs failed a distribution check."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _check_entry_names(infos, expected_entries=EXPECTED_ENTRIES):
    names = [entry.filename for entry in infos]
    for entry in infos:
        name = entry.filename
        path = PurePosixPath(name)
        if (entry.orig_filename != name or not name or '\\' in name or path.is_absolute() or
                re.match(r'^[a-zA-Z]:', name) or
                any(part in ('', '.', '..') for part in name.split('/'))):
            raise ArchiveVerificationError(f'Unsafe ZIP member path: {name!r}')
        if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16):
            raise ArchiveVerificationError(f'ZIP member must be a regular file: {name}')
        if entry.flag_bits & 1:
            raise ArchiveVerificationError(f'Encrypted ZIP member is not supported: {name}')
    duplicates = sorted(name for name, count in Counter(names).items() if count != 1)
    if duplicates:
        raise ArchiveVerificationError('Duplicate ZIP members: ' + ', '.join(duplicates))
    if len({name.casefold() for name in names}) != len(names):
        raise ArchiveVerificationError('Case-colliding ZIP member names are not allowed.')
    missing = sorted(set(expected_entries) - set(names))
    extra = sorted(set(names) - set(expected_entries))
    if missing or extra:
        raise ArchiveVerificationError(f'ZIP whitelist mismatch; missing={missing}; extra={extra}')


def _manifest_hashes(data):
    try:
        lines = data.decode('utf-8-sig').splitlines()
    except UnicodeDecodeError as error:
        raise ArchiveVerificationError('SHA256SUMS.txt must be UTF-8 text.') from error
    if len(lines) != len(PAYLOAD):
        raise ArchiveVerificationError('SHA256SUMS.txt must contain exactly eight payload entries.')
    hashes = {}
    for line in lines:
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        if match is None:
            raise ArchiveVerificationError('Invalid SHA256SUMS.txt line; expected SHA256, two spaces, filename.')
        checksum, name = match.groups()
        if name in hashes:
            raise ArchiveVerificationError(f'Duplicate SHA256SUMS.txt entry: {name}')
        hashes[name] = checksum.lower()
    missing = sorted(set(PAYLOAD) - set(hashes))
    extra = sorted(set(hashes) - set(PAYLOAD))
    if missing or extra:
        raise ArchiveVerificationError(f'SHA256SUMS.txt whitelist mismatch; missing={missing}; extra={extra}')
    return hashes


def _check_text(name, data, private_markers):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ArchiveVerificationError(f'Distributed text is not valid UTF-8: {name}') from error
    for label, pattern in PRIVATE_TEXT_PATTERNS:
        if pattern.search(text):
            # Report the category, not the actual private value, to avoid
            # propagating a rejected secret/path into the verification report.
            raise ArchiveVerificationError(f'Private text found in {name}: {label}')
    for marker in private_markers:
        if marker.casefold() in text.casefold():
            raise ArchiveVerificationError(f'Private text found in {name}: supplied private marker')
    return text


def verify_archive(archive_path, *, expected_version, exe_sha256, source_dir,
                   private_markers=(), archive_format='standard', license_source=None):
    """Return evidence on success; reject any mismatch without extracting files."""
    if (not isinstance(expected_version, str) or not expected_version.strip() or
            expected_version != expected_version.strip() or
            '\n' in expected_version or '\r' in expected_version):
        raise ArchiveVerificationError('An explicit, single-line expected version is required.')
    if not isinstance(exe_sha256, str) or re.fullmatch(r'[0-9a-fA-F]{64}', exe_sha256) is None:
        raise ArchiveVerificationError('An explicit 64-digit frozen EXE SHA256 is required.')
    if any(not isinstance(marker, str) or not marker.strip() for marker in private_markers):
        raise ArchiveVerificationError('Private markers must be nonempty strings.')
    if archive_format not in ('standard', 'compact', 'executable', 'documented'):
        raise ArchiveVerificationError('Archive format must be standard, compact, executable or documented.')
    if archive_format == 'documented' and re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:-[A-Za-z0-9._-]+)?', expected_version) is None:
        raise ArchiveVerificationError('Documented package version must be safe for a README filename.')
    versioned_readme = f'README-v{expected_version}.txt'
    expected_entries = {'standard': EXPECTED_ENTRIES, 'compact': COMPACT_ENTRIES,
                        'executable': EXECUTABLE_ENTRIES,
                        'documented': ('WorldApartTrainer.exe', versioned_readme)}[archive_format]
    readme_name = (versioned_readme if archive_format == 'documented' else
                   'README.txt' if archive_format == 'compact' else 'README.md')
    archive_path, source_dir = Path(archive_path), Path(source_dir)
    source = {}
    for name in expected_entries:
        path = source_dir / name
        if not path.is_file():
            raise ArchiveVerificationError(f'Release source file is missing: {name}')
        source[name] = path.read_bytes()
        if not source[name]:
            raise ArchiveVerificationError(f'Release source file is empty: {name}')
    if archive_format == 'standard':
        hashes = _manifest_hashes(source[MANIFEST])
        for name in PAYLOAD:
            if hashes[name] != sha256(source[name]):
                raise ArchiveVerificationError(f'Source SHA256SUMS.txt mismatch: {name}')
    else:
        hashes = {name: sha256(source[name]) for name in expected_entries}
    actual_exe_hash = sha256(source['WorldApartTrainer.exe'])
    if actual_exe_hash != exe_sha256.lower():
        raise ArchiveVerificationError('Frozen EXE SHA256 does not match the release source.')
    license_hashes = {}
    for name in expected_entries:
        if name == 'WorldApartTrainer.exe':
            continue
        text = _check_text(name, source[name], private_markers)
        if name == readme_name:
            first = text.splitlines()[0] if text.splitlines() else ''
            # Accept both "1.0" and "v1.0", while refusing 1.0.1 or 11.0.
            token = r'(?<![A-Za-z0-9_.])v?' + re.escape(expected_version) + r'(?![A-Za-z0-9_.])'
            if re.search(token, first) is None:
                raise ArchiveVerificationError(f'{readme_name} first-line version does not match the expected version.')
            if archive_format == 'compact':
                checksum_lines = [line for line in text.splitlines()
                                  if line.startswith('SHA256 (WorldApartTrainer.exe):')]
                if len(checksum_lines) != 1:
                    raise ArchiveVerificationError('README.txt must contain exactly one EXE SHA256 line.')
                match = re.fullmatch(r'SHA256 \(WorldApartTrainer\.exe\): ([0-9a-fA-F]{64})',
                                     checksum_lines[0])
                if match is None or match[1].lower() != actual_exe_hash:
                    raise ArchiveVerificationError('README.txt EXE SHA256 does not match the frozen executable.')
                licenses = (Path(license_source) if license_source is not None
                            else Path(__file__).resolve().parent / 'licenses')
                # License text may be transported as LF or CRLF, but no other
                # characters or terms may be omitted or rewritten.
                normalized_readme = text.replace('\r\n', '\n').replace('\r', '\n')
                for license_name in LICENSE_NAMES:
                    try:
                        data = (licenses / license_name).read_bytes()
                        license_text = data.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
                    except (OSError, UnicodeDecodeError) as error:
                        raise ArchiveVerificationError(f'Cannot read original license text: {license_name}') from error
                    if not license_text.strip() or license_text not in normalized_readme:
                        raise ArchiveVerificationError(f'README.txt is missing complete original license text: {license_name}')
                    license_hashes[license_name] = sha256(data)
    entries = []
    try:
        with zipfile.ZipFile(archive_path, 'r') as archive:
            _check_entry_names(archive.infolist(), expected_entries)
            for name in expected_entries:
                info = archive.getinfo(name)
                # Bound decompression to the independently supplied frozen
                # source length before reading an entry. ZipFile.read verifies
                # the CRC for each allowed entry as it reaches EOF.
                if info.file_size != len(source[name]):
                    raise ArchiveVerificationError(f'ZIP/source size mismatch: {name}')
                packed = archive.read(info)
                if packed != source[name]:
                    raise ArchiveVerificationError(f'ZIP/source bytes differ: {name}')
                checksum = sha256(packed)
                if name != MANIFEST and checksum != hashes[name]:
                    raise ArchiveVerificationError(f'ZIP SHA256SUMS.txt mismatch: {name}')
                entries.append(dict(name=name, bytes=len(packed), sha256=checksum,
                                    matches_source=True))
    except ArchiveVerificationError:
        raise
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as error:
        raise ArchiveVerificationError(f'ZIP could not be verified (including CRC): {error}') from error
    # Detect source changes during the check instead of approving a ZIP against
    # a set of files that no longer represents the given release directory.
    for name, data in source.items():
        if (source_dir / name).read_bytes() != data:
            raise ArchiveVerificationError(f'Release source changed during verification: {name}')
    return dict(passed=True, version=expected_version, format=archive_format, package=archive_path.name,
                package_bytes=archive_path.stat().st_size,
                package_sha256=sha256(archive_path.read_bytes()),
                frozen_executable_sha256=actual_exe_hash,
                exact_whitelist=True, entry_count=len(entries), crc_ok=True,
                sha256_manifest_valid=True if archive_format == 'standard' else None,
                readme_executable_sha256_valid=True if archive_format == 'compact' else None,
                embedded_license_sha256=license_hashes,
                license_verification=('separate_bundle_check_required' if archive_format in ('executable', 'documented')
                                      else 'complete_original_text' if archive_format == 'compact'
                                      else 'source_files_match'),
                textual_personal_paths_found=False,
                entries=entries)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--exe-sha256', required=True)
    parser.add_argument('--source-dir', required=True, type=Path)
    parser.add_argument('--format', choices=('standard', 'compact', 'executable', 'documented'), default='standard')
    parser.add_argument('--license-source', type=Path,
                        help='Original license-text directory for compact format; defaults to this script\'s licenses directory.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--private-marker', action='append', default=[],
                        help='Additional literal private value to reject in distributed text; repeatable.')
    args = parser.parse_args(argv)
    if args.output and (args.output.resolve() == args.archive.resolve() or
                        args.output.resolve().is_relative_to(args.source_dir.resolve())):
        parser.error('--output must not overwrite the ZIP or write inside the release source directory.')
    try:
        result = verify_archive(args.archive, expected_version=args.expected_version,
                                exe_sha256=args.exe_sha256, source_dir=args.source_dir,
                                private_markers=args.private_marker, archive_format=args.format,
                                license_source=args.license_source)
    except (ArchiveVerificationError, OSError) as error:
        result = dict(passed=False, error=str(error))
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8', newline='\n')
    print(encoded, end='')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
