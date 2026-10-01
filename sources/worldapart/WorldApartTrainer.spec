# Reproducible one-file build. Never glob cache, game, save, or log directories.
from pathlib import Path
import hashlib
import json
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH)
resource_names = ['engine_runtime_handoff.json', 'acquisition_context_specs.json', 'acquisition_bridge.js', 'RELEASE_NOTES.md', 'THIRD_PARTY_NOTICES.md']
resource_names += [path.name for path in sorted(root.glob('meridian*spec*.json'))]
resource_names += [path.name for path in sorted(root.glob('character_attributes*spec*.json'))]
resource_names += [path.name for path in sorted(root.glob('current_resources*spec*.json'))]
resource_names += ['character_lifespan_specs.json', 'game_speed_specs.json']
resource_names += ['alchemy_specs.json', 'alchemy_recipe_specs.json', 'crafting_specs.json',
                   'dual_cultivation_specs.json', 'jade_specs.json']
resource_names += ['photostone_specs.json', 'photostone_catalog.json', 'persuasion_specs.json']
resource_names += ['native_method_evidence.json']
additional = [path.stem for path in sorted(root.glob('meridian*.py')) if not path.name.startswith('test_')]
additional += [path.stem for path in sorted(root.glob('character*.py')) if not path.name.startswith('test_')]
additional += [path.stem for path in sorted(root.glob('current_resources*.py')) if not path.name.startswith('test_')]
additional += ['game_speed', 'game_speed_native', 'game_speed_ui', 'navigation']
additional += ['native_broker', 'native_broker_host', 'native_scalar_guard', 'game_connection', 'item_categories']
additional += ['extension_runtime', 'native_method_profiles', 'audit_update_readonly']
additional += ['alchemy_adapter', 'alchemy_context', 'alchemy_talents', 'alchemy_ui', 'alchemy_recipe', 'alchemy_recipe_ui',
               'crafting_adapter', 'crafting_logic', 'crafting_talents', 'crafting_ui',
               'dual_cultivation_common', 'dual_cultivation_native', 'dual_cultivation_adapter',
               'dual_cultivation_ui', 'jade_adapter', 'jade_ui']
additional += ['photostone_logic', 'photostone_adapter', 'photostone_native', 'photostone_ui', 'photostone_concurrent',
               'persuasion_adapter', 'persuasion_context', 'persuasion_native', 'persuasion_ui']
manifest = {'format': 1, 'additional_modules': additional,
            'resources': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in resource_names}}
manifest_path = root / 'build' / 'bundle_manifest.json'
manifest_path.parent.mkdir(exist_ok=True)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
datas = [(str(root / name), '.') for name in resource_names]
datas += [(str(manifest_path), '.')] + copy_metadata('frida')
# Include applicable notices in the executable, without shipping the build tools.
import sys
from PyInstaller.utils.hooks.tcl_tk import tcltk_info
from build_tcl_resources import collect_zip_library
for family in ('tcl', 'tk'):
    if str(getattr(tcltk_info, family + '_data_dir', '')).startswith('//zipfs:'):
        datas += collect_zip_library(sys.base_prefix, root / 'build' / 'tcl-resources',
                                     family, getattr(tcltk_info, family + '_version'))
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    datas.append((str(python_license), 'licenses/python'))
license_dir = root / 'licenses'
if license_dir.is_dir():
    datas += [(str(path), 'licenses') for path in license_dir.iterdir() if path.is_file()]

a = Analysis([str(root / 'standalone_entry.py')],
             pathex=[str(root), str(root / 'game_runtime')],
             binaries=[], datas=datas,
             hiddenimports=collect_submodules('frida') + additional,
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['unittest', 'pydoc', 'pip', 'setuptools', 'PyInstaller'],
             noarchive=False, optimize=0)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name='WorldApartTrainer', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=False, console=False, disable_windowed_traceback=False,
          argv_emulation=False, target_arch=None, codesign_identity=None,
          entitlements_file=None, uac_admin=False)
