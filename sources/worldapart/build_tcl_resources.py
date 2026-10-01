"""Build-only support for Python's external Tcl/Tk 9 zip libraries.

Some installers expose //zipfs paths but keep the archives beside Python,
outside the DLL. PyInstaller's hook cannot copy a virtual zipfs directory.
Stage the installed archives into its standard runtime-hook destinations.
"""
from pathlib import Path, PurePosixPath
import zipfile


def collect_zip_library(python_root, stage_root, family, version):
    if family not in ('tcl', 'tk'):
        raise ValueError('Unknown Tcl/Tk library family')
    major_minor = '.'.join(str(value) for value in version[:2])
    archives = list((Path(python_root) / 'tcl').glob(f'lib{family}{major_minor}*.zip'))
    if len(archives) != 1:
        raise RuntimeError(f'Expected one installed {family} {major_minor} resource archive')
    prefix = family + '_library'
    destination = '_' + family + '_data'
    stage = Path(stage_root) / destination
    collected = []
    with zipfile.ZipFile(archives[0]) as archive:
        for item in archive.infolist():
            parts = PurePosixPath(item.filename).parts
            if (not parts or parts[0] != prefix or '\\' in item.filename
                    or any(part in ('.', '..') or ':' in part for part in parts)):
                raise RuntimeError('Unexpected installed Tcl/Tk archive member')
            if item.is_dir():
                continue
            relative = Path(*parts[1:])
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
            collected.append((str(target), str(Path(destination) / relative.parent)))
    required = stage / ('init.tcl' if family == 'tcl' else 'tk.tcl')
    if not required.is_file():
        raise RuntimeError('Installed Tcl/Tk archive lacks its initialization script')
    return collected
