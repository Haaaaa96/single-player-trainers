"""Reviewed method whitelist and production request selection, memory only."""
import copy
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from acquisition_adapter import AcquisitionAdapter, METHOD_SPECS
from learning_adapter import LearningResolver
from native_method_profiles import (NATIVE_EVIDENCE, native_variants,
                                    request_method_spec, resolve_reviewed_method)
from persuasion_adapter import METHODS as PERSUASION
from test_scalar_method_profiles import MethodFixture
from write_guard import Refused


def fixture(specs, current):
    specs = {key: dict(spec, parameters=spec['argc'], return_kind=spec['returns'])
             for key, spec in specs.items()}
    return MethodFixture(LearningResolver, specs, current=current)


class NativeMethodProfileTests(unittest.TestCase):
    def test_embedded_method_and_field_evidence_exactly_matches_packaged_json(self):
        root = Path(__file__).parent
        data = json.loads((root/'native_method_evidence.json').read_text(encoding='utf8'))
        source = (root/'acquisition_bridge.js').read_text(encoding='utf8')
        methods = json.loads(re.search(r'const REVIEWED_NATIVE_VARIANTS = (.*);', source)[1])
        self.assertGreaterEqual(len(methods), 48)
        self.assertEqual(methods, {k: {name: value[name] for name in
                         ('name','token','rva','prefix','legacy_rva')}
                         for k, value in data['methods'].items()})
        self.assertEqual(json.loads(re.search(r'const REVIEWED_FIELD_VARIANTS = (.*);', source)[1]),
                         data['fields'])

    def test_descriptor_is_only_a_selector_and_cannot_supply_abi_or_code(self):
        for spec in METHOD_SPECS.values():
            for selected in native_variants(spec):
                hostile = dict(selected, prefix='90', argc=9, returns=1, static=True)
                self.assertEqual(request_method_spec(spec, hostile), selected)
                for key in ('name','token','rva'):
                    bad = dict(selected)
                    bad[key] = 'unreviewed' if key == 'name' else selected[key]+1
                    with self.subTest(key=key), self.assertRaises(Refused):
                        request_method_spec(spec, bad)

    def test_current_callback_renumbering_preserves_roles_and_repeated_lookup(self):
        specs = {key: PERSUASION[key] for key in ('win','lose','close','alive')}
        fx = fixture(specs, True)
        for key, old in specs.items():
            first = resolve_reviewed_method(fx.resolver, fx.klass, old)
            self.assertEqual(first[0], fx.methods[key])
            self.assertEqual(first[1]['token'], fx.selected[key]['token'])
            self.assertEqual(resolve_reviewed_method(fx.resolver, fx.klass, old), first)
        # Same old callback name now denotes another role; actual identity wins.
        win = fx.methods['win']
        fx.memory.put(win+0x48, 'i', fx.selected['lose']['token'])
        with self.assertRaises(Refused):
            resolve_reviewed_method(fx.resolver, fx.klass, specs['win'])

    def test_inventory_real_method_reader_selects_both_profiles_and_adds_proof(self):
        for current in (False, True):
            fx = fixture(METHOD_SPECS, current)
            rr = fx.resolver
            rr.verify_class = lambda klass, fullname: {'name': 'BagModel'}
            fx.memory.put(0x9000, 'Q', fx.klass)
            adapter = AcquisitionAdapter.__new__(AcquisitionAdapter)
            adapter.game = SimpleNamespace(resolver=rr)
            raw = dict(bag=0x9000, anchors=[])
            with patch('probe.verified_mappings', return_value={'game_assembly':[{'base':rr.module}]}):
                for key in METHOD_SPECS:
                    result = adapter._method(raw, key)
                    self.assertEqual(result[0][0], fx.methods[key])
                    self.assertEqual(result[1:3], (fx.selected[key]['token'],fx.selected[key]['rva']))
                    self.assertTrue(any(a['address']==rr.module+result[2] and
                                        a['expected_hex']==fx.selected[key]['prefix'] for a in raw['anchors']))
                fx.memory.store(rr.module+fx.selected['add']['rva'], b'\x90')
                with self.assertRaises(Refused):
                    adapter._method(raw, 'add')

    def test_current_meridian_descriptor_is_selected_by_native_request(self):
        from meridian_oneclick import MeridianOneClick
        from meridian_adapter import METHOD_SPEC
        selected = native_variants(METHOD_SPEC)[1]
        native = dict(method_info='0x1234', method_spec=selected,
                      registry_links=[{'address':'0x2345','expected':'0x3456'}],
                      registry={'dictionary':'0x3456'}, anchors=[{'address':'0x2345','size':1,'expected_hex':'00'}])
        request = MeridianOneClick._request({'native':native}, 12, 'test')
        self.assertEqual(request['method_token'], selected['token'])
        self.assertEqual(request['method_rva'], selected['rva'])
        native['method_spec'] = dict(selected, rva=selected['rva']+1)
        with self.assertRaises(Refused):
            MeridianOneClick._request({'native':native}, 12, 'test')


if __name__ == '__main__':
    unittest.main()
