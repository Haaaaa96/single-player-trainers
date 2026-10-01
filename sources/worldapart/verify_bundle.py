"""Build-time check that the EXE contains the current reviewed source/resources."""
import argparse
import hashlib
import json
import marshal
from pathlib import Path
import types

from standalone_selftest import (EXPECTED_ADDITIONAL_MODULES, EXPECTED_CORE_MODULES,
                                 EXPECTED_RESOURCES, validate_bundle_manifest)


def normalized(code):
    return code.replace(co_filename='module.py', co_consts=tuple(
        normalized(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def verify(executable, output=None, *, archive_reader=None):
    root = Path(__file__).resolve().parent
    if archive_reader is None:
        from PyInstaller.archive.readers import CArchiveReader
        archive_reader = CArchiveReader
    archive = archive_reader(str(executable))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    result = {'passed': True, 'executable': str(Path(executable).resolve()),
              'sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
              'modules': [], 'resources': {}}
    required = EXPECTED_CORE_MODULES | EXPECTED_ADDITIONAL_MODULES
    result['missing_modules'] = sorted(required - set(pyz.toc))
    if 'standalone_entry' not in archive.toc:
        result['missing_modules'].append('standalone_entry')
    result['passed'] &= not result['missing_modules']
    for path in list(root.glob('*.py')) + list((root / 'game_runtime').glob('*.py')):
        name = path.stem
        if name not in pyz.toc and (name != 'standalone_entry' or name not in archive.toc):
            continue
        bundled = (marshal.loads(archive.extract(name)) if name == 'standalone_entry' else pyz.extract(name))
        source = compile(path.read_bytes(), str(path), 'exec', optimize=0)
        matches = normalized(bundled) == normalized(source)
        result['modules'].append({'module': name, 'matches_source': matches,
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        result['passed'] &= matches
    manifest = None
    try:
        manifest = json.loads(archive.extract('bundle_manifest.json'))
        validate_bundle_manifest(manifest)
        result['manifest_valid'] = True
    except Exception as error:
        result['manifest_valid'] = False
        result['manifest_error'] = str(error)
        result['passed'] = False
    hashes = manifest.get('resources', {}) if isinstance(manifest, dict) else {}
    hashes = hashes if isinstance(hashes, dict) else {}
    result['missing_resources'] = sorted(EXPECTED_RESOURCES - set(archive.toc))
    for name in sorted(EXPECTED_RESOURCES):
        try:
            current_hash = hashlib.sha256((root / name).read_bytes()).hexdigest()
            bundle_hash = hashlib.sha256(archive.extract(name)).hexdigest()
            matches = current_hash == bundle_hash == hashes.get(name)
            result['resources'][name] = {'matches_source': matches, 'sha256': current_hash}
            result['passed'] &= matches
        except Exception as error:
            result['resources'][name] = {'matches_source': False, 'error': str(error)}
            result['passed'] = False
    forbidden = [name for name in archive.toc if any(token in name.lower() for token in (
        'gameassembly', 'global-metadata', 'changes.jsonl', 'acquisition-pending',
        'classes.json', 'objects.json', 'storagev1'))]
    result['forbidden_entries'] = forbidden
    result['passed'] &= not forbidden
    if output:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    raise SystemExit(verify(args.executable, args.output))
