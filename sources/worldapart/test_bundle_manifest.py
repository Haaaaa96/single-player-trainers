"""Packaging requirements are independent of a potentially incomplete bundle."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import marshal
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import standalone_selftest as st
import verify_bundle as vb

ROOT = Path(__file__).resolve().parent


def manifest():
    return dict(format=1, additional_modules=sorted(st.EXPECTED_ADDITIONAL_MODULES),
                resources={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                           for name in st.EXPECTED_RESOURCES})


class FakeArchive:
    def __init__(self):
        self.source = {p.stem: p for p in list(ROOT.glob('*.py')) + list((ROOT / 'game_runtime').glob('*.py'))}
        self.pyz = type('Pyz', (), {})()
        self.pyz.toc = {name: None for name in st.EXPECTED_CORE_MODULES | st.EXPECTED_ADDITIONAL_MODULES}
        self.pyz.extract = lambda name: compile(self.source[name].read_bytes(), 'bundled.py', 'exec', optimize=0)
        self.resources = {name: (ROOT / name).read_bytes() for name in st.EXPECTED_RESOURCES}
        self.resources['bundle_manifest.json'] = json.dumps(manifest()).encode()
        self.resources['standalone_entry'] = marshal.dumps(compile(self.source['standalone_entry'].read_bytes(),
                                                                  'bundled.py', 'exec', optimize=0))

    @property
    def toc(self):
        return self.resources

    def open_embedded_archive(self, name):
        assert name == 'PYZ.pyz'
        return self.pyz

    def extract(self, name):
        return self.resources[name]


class ManifestTests(unittest.TestCase):
    def test_actual_spec_generates_complete_manifest_without_building(self):
        # Run the packaging recipe only against a temporary fixture. Stub the
        # bundler so no EXE is built, process started, or production build file
        # replaced; exercise the real resource/module selection expressions.
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder)
            for source in ROOT.glob('*.py'):
                (fixture/source.name).touch()
            for source in ROOT.glob('*.json'):
                (fixture/source.name).write_bytes(source.read_bytes())
            for name in ('RELEASE_NOTES.md','THIRD_PARTY_NOTICES.md','acquisition_bridge.js'):
                (fixture/name).write_bytes((ROOT/name).read_bytes())
            hooks = SimpleNamespace(collect_submodules=lambda name:[],copy_metadata=lambda name:[])
            analysis = SimpleNamespace(pure=[],scripts=[],binaries=[],datas=[])
            with patch.dict(sys.modules,{'PyInstaller.utils.hooks':hooks,
                                         'PyInstaller.utils.hooks.tcl_tk': SimpleNamespace(tcltk_info=SimpleNamespace())}):
                runpy.run_path(str(ROOT/'WorldApartTrainer.spec'),init_globals={
                    'SPECPATH':str(fixture),'Analysis':lambda *a,**k:analysis,
                    'PYZ':lambda *a,**k:None,'EXE':lambda *a,**k:None})
            actual = json.loads((fixture/'build'/'bundle_manifest.json').read_text(encoding='utf8'))
            st.validate_bundle_manifest(actual)
            actual['additional_modules'].sort()
            self.assertEqual(actual,manifest())

    def test_current_spec_globs_match_independent_expectations(self):
        modules = {p.stem for prefix in ('meridian', 'character', 'current_resources')
                   for p in ROOT.glob(prefix + '*.py') if not p.name.startswith('test_')}
        modules |= {'native_broker', 'native_broker_host', 'native_scalar_guard', 'game_connection', 'item_categories'}
        modules |= {'game_speed', 'game_speed_native', 'game_speed_ui', 'navigation'}
        modules |= {'extension_runtime', 'native_method_profiles', 'audit_update_readonly'}
        modules |= {p.stem for prefix in ('alchemy', 'crafting', 'dual_cultivation', 'jade', 'photostone', 'persuasion')
                    for p in ROOT.glob(prefix + '*.py')}
        self.assertEqual(modules, st.EXPECTED_ADDITIONAL_MODULES)
        resources = {'engine_runtime_handoff.json', 'acquisition_context_specs.json', 'acquisition_bridge.js',
                     'RELEASE_NOTES.md', 'THIRD_PARTY_NOTICES.md'}
        resources |= {p.name for prefix in ('meridian', 'character_attributes', 'current_resources')
                      for p in ROOT.glob(prefix + '*spec*.json')}
        resources |= {'character_lifespan_specs.json', 'game_speed_specs.json'}
        resources |= {'alchemy_specs.json', 'alchemy_recipe_specs.json', 'crafting_specs.json',
                      'dual_cultivation_specs.json', 'jade_specs.json'}
        resources |= {'photostone_specs.json', 'photostone_catalog.json', 'persuasion_specs.json'}
        resources |= {'native_method_evidence.json'}
        self.assertEqual(resources, st.EXPECTED_RESOURCES)
        st.validate_bundle_manifest(manifest())

    def test_every_new_module_and_resource_is_required_independently(self):
        for name in ('navigation','character_profile','character_profile_ui','character_lifespan',
                     'character_lifespan_native','character_lifespan_ui','game_speed','game_speed_native','game_speed_ui',
                     'extension_runtime','native_method_profiles','audit_update_readonly'):
            data = manifest()
            data['additional_modules'].remove(name)
            with self.subTest(module=name),self.assertRaisesRegex(RuntimeError,name):
                st.validate_bundle_manifest(data)
        for name in ('character_lifespan_specs.json','game_speed_specs.json','native_method_evidence.json'):
            data = manifest()
            del data['resources'][name]
            with self.subTest(resource=name),self.assertRaisesRegex(RuntimeError,name):
                st.validate_bundle_manifest(data)

    def test_omitted_or_extra_manifest_module_rejected(self):
        data = manifest()
        data['additional_modules'].remove('native_broker_host')
        with self.assertRaisesRegex(RuntimeError, r'missing=.*native_broker_host'):
            st.validate_bundle_manifest(data)
        data = manifest()
        data['additional_modules'].append('unexpected_module')
        with self.assertRaisesRegex(RuntimeError, r'extra=.*unexpected_module'):
            st.validate_bundle_manifest(data)

    def test_missing_extra_resource_and_duplicate_module_rejected(self):
        data = manifest()
        data['resources'].pop('character_attributes_interact_specs.json')
        data['resources']['unexpected.json'] = '0' * 64
        with self.assertRaisesRegex(RuntimeError, r'missing=.*character_attributes_interact_specs.*extra=.*unexpected'):
            st.validate_bundle_manifest(data)
        data = manifest()
        data['additional_modules'].append(data['additional_modules'][0])
        with self.assertRaisesRegex(RuntimeError, 'Duplicate'):
            st.validate_bundle_manifest(data)

    def test_invalid_hash_and_schema_rejected(self):
        data = manifest()
        data['resources']['current_resources_specs.json'] = 'not a hash'
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            st.validate_bundle_manifest(data)
        for data in (None, [], dict(manifest(), format=True)):
            with self.assertRaises(RuntimeError):
                st.validate_bundle_manifest(data)

    def test_tabs_and_introduction_are_required_not_just_reported(self):
        st.validate_release_ui(st.EXPECTED_TABS, '2026.09.27.5', '# Version 2026.09.27.5\nFeatures')
        for tabs in (st.EXPECTED_TABS[:-1], st.EXPECTED_TABS + ('unexpected',), tuple(reversed(st.EXPECTED_TABS))):
            with self.assertRaisesRegex(RuntimeError, 'tabs differ'):
                st.validate_release_ui(tabs, 'v5', '# v5')
        for introduction in ('', '# v4\nv5 mentioned only in history', None):
            with self.assertRaisesRegex(RuntimeError, 'release version'):
                st.validate_release_ui(st.EXPECTED_TABS, 'v5', introduction)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.archive = FakeArchive()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.executable = Path(self.temp.name) / 'fixture.exe'
        self.executable.write_bytes(b'not executable; mock archive fixture only')
        self.output = Path(self.temp.name) / 'result.json'

    def run_verify(self):
        with redirect_stdout(io.StringIO()):
            status = vb.verify(self.executable, self.output, archive_reader=lambda name: self.archive)
        return status, json.loads(self.output.read_text(encoding='utf8'))

    def test_complete_source_equivalent_fixture_passes(self):
        status, result = self.run_verify()
        self.assertEqual(status, 0)
        self.assertTrue(result['passed'])
        self.assertEqual(result['missing_modules'], [])
        self.assertEqual(result['missing_resources'], [])

    def test_missing_required_module_is_not_silently_skipped(self):
        self.archive.pyz.toc.pop('native_broker_host')
        status, result = self.run_verify()
        self.assertEqual(status, 1)
        self.assertEqual(result['missing_modules'], ['native_broker_host'])
        self.assertTrue(result['manifest_valid'])

    def test_missing_resource_bytes_fail_even_with_complete_manifest(self):
        del self.archive.resources['current_resources_specs.json']
        status, result = self.run_verify()
        self.assertEqual(status, 1)
        self.assertEqual(result['missing_resources'], ['current_resources_specs.json'])
        self.assertFalse(result['resources']['current_resources_specs.json']['matches_source'])

    def test_incomplete_manifest_is_rejected_even_when_archive_has_all_bytes(self):
        data = manifest()
        data['resources'].pop('character_attributes_interact_specs.json')
        self.archive.resources['bundle_manifest.json'] = json.dumps(data).encode()
        status, result = self.run_verify()
        self.assertEqual(status, 1)
        self.assertFalse(result['manifest_valid'])
        self.assertIn('character_attributes_interact_specs.json', result['manifest_error'])

    def test_missing_entry_script_and_manifest_fail_clearly(self):
        del self.archive.resources['standalone_entry']
        del self.archive.resources['bundle_manifest.json']
        status, result = self.run_verify()
        self.assertEqual(status, 1)
        self.assertIn('standalone_entry', result['missing_modules'])
        self.assertFalse(result['manifest_valid'])


if __name__ == '__main__':
    unittest.main()
