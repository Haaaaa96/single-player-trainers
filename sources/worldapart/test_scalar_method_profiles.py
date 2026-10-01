"""Real MethodInfo reads for scalar legacy/current reviewed native roles."""
import unittest

import character_attributes as ca
import character_attributes_interact as ci
import current_resources as cr
import game_speed as gs
from native_method_profiles import native_variants
from test_game_speed import MemoryFixture
from write_guard import Refused


class MethodFixture:
    def __init__(self, resolver_type, specs, *, current=False, static=False):
        self.memory = m = MemoryFixture()
        self.resolver = resolver_type.__new__(resolver_type)
        self.resolver.reader, self.resolver.module, self.resolver.anchors = m, 0x10000000, []
        self.klass, self.table = 0x1000, 0x2000
        self.methods, self.selected = {}, {}
        m.put(self.klass + 0x98, 'Q', self.table)
        m.put(self.klass + 0x120, 'H', len(specs))
        for index, (key, legacy) in enumerate(specs.items()):
            variants = native_variants(dict(legacy, static=static))
            if current:
                assert len(variants) == 2, key
            spec = variants[-1] if current else variants[0]
            method, name, returns = 0x3000 + index * 0x100, 0x5000 + index * 0x100, 0x7000 + index * 0x100
            self.methods[key], self.selected[key] = method, spec
            for address, value in ((self.table + index*8, method),(method,self.resolver.module+spec['rva']),
                                   (method+0x18,name),(method+0x20,self.klass),(method+0x28,returns)):
                m.put(address,'Q',value)
            m.names[name] = spec['name']
            m.put(method+0x48,'i',spec['token'])
            m.put(method+0x4C,'H',0x96 if static else 0x86)
            m.put(method+0x52,'B',spec['parameters'])
            m.put(returns+10,'B',spec['return_kind'])
            m.store(self.resolver.module+spec['rva'],bytes.fromhex(spec['prefix']))


class ScalarMethodProfileTests(unittest.TestCase):
    def test_single_descriptors_carry_selected_spec_and_method_code_proof(self):
        for module,cls,adapter_cls,key,attr in (
                (ca,ca.AttributeResolver,ca.CharacterAttributesAdapter,'growth:2',2),
                (ci,ci.InteractResolver,ci.InteractAttributesAdapter,'interact:1001',1001)):
            fx=MethodFixture(cls,{'modify':module.METHOD_SPEC},current=True)
            target_type=ci.InteractTarget if module is ci else ca.AttributeTarget
            shown=target_type(key=key,value=0,identity=(1,),anchors=((0x9000,'00'),),attr_id=attr)
            adapter=adapter_cls.__new__(adapter_cls)
            adapter.resolver=fx.resolver
            owner_key='player_class' if module is ci else 'combat_class'
            adapter.snapshot=lambda:dict(rows={key:{'target':shown}},native={
                owner_key:hex(fx.klass),'dictionary':'0x9000','identity_key':'reviewed-fixture'})
            descriptor=adapter.prepare_native(shown,1)
            with self.subTest(module=module.__name__):
                self.assertEqual(descriptor['method_spec'],fx.selected['modify'])
                self.assertEqual(descriptor['method_info'],hex(fx.methods['modify']))
                code=fx.resolver.module+fx.selected['modify']['rva']
                self.assertTrue(any(int(a['address'],16)==code and a['expected_hex']==fx.selected['modify']['prefix']
                                    for a in descriptor['anchors']))

    def test_growth_and_interact_select_actual_legacy_or_current_and_repeat(self):
        for cls, spec in ((ca.AttributeResolver,ca.METHOD_SPEC),(ci.InteractResolver,ci.METHOD_SPEC)):
            for current in (False,True):
                fx = MethodFixture(cls, {'modify':spec},current=current)
                with self.subTest(cls=cls.__name__,current=current):
                    first = fx.resolver.method(fx.klass,include_spec=True)
                    self.assertEqual(first,(fx.methods['modify'],fx.selected['modify']))
                    self.assertEqual(fx.resolver.method(fx.klass,include_spec=True),first)
                    self.assertEqual(fx.resolver.method(fx.klass),first[0])

    def test_resources_and_speed_export_complete_selected_method_maps(self):
        for current in (False,True):
            for key, resource in cr.RESOURCE_SPECS.items():
                fx = MethodFixture(cr.ResourceResolver,resource['methods'],current=current)
                with self.subTest(resource=key,current=current):
                    methods,selected = fx.resolver.resource_methods(fx.klass,key,include_specs=True)
                    self.assertEqual(methods,{name:hex(mi) for name,mi in fx.methods.items()})
                    self.assertEqual(selected,fx.selected)
            fx = MethodFixture(gs.GameSpeedResolver,gs.METHODS,current=current,static=True)
            methods,selected = fx.resolver.methods(fx.klass,include_specs=True)
            self.assertEqual(methods,{name:hex(mi) for name,mi in fx.methods.items()})
            self.assertEqual(selected,fx.selected)

    def test_selected_role_still_rejects_wrong_owner_abi_token_and_code(self):
        for change in ('owner','static','argc','return','byref','token','code'):
            fx = MethodFixture(ca.AttributeResolver,{'modify':ca.METHOD_SPEC},current=True)
            mi=fx.methods['modify'];m=fx.memory
            fx.resolver.method(fx.klass)
            if change=='owner':m.put(mi+0x20,'Q',fx.klass+8)
            elif change=='static':m.put(mi+0x4C,'H',0x96)
            elif change=='argc':m.put(mi+0x52,'B',1)
            elif change=='return':m.put(0x700A,'B',8)
            elif change=='byref':m.put(0x700B,'B',0x40)
            elif change=='token':m.put(mi+0x48,'i',0x06000001)
            else:m.put(fx.resolver.module+fx.selected['modify']['rva'],'B',0)
            with self.subTest(change=change),self.assertRaises(Refused):fx.resolver.method(fx.klass)

    def test_original_method_count_bounds_are_preserved(self):
        for cls,specs,limit,speed in ((ca.AttributeResolver,{'modify':ca.METHOD_SPEC},512,False),
                                    (ci.InteractResolver,{'modify':ci.METHOD_SPEC},512,False),
                                    (cr.ResourceResolver,cr.METHODS,512,False),
                                    (gs.GameSpeedResolver,gs.METHODS,64,True)):
            fx=MethodFixture(cls,specs,current=True,static=speed)
            fx.memory.put(fx.klass+0x120,'H',limit+1)
            with self.subTest(cls=cls.__name__),self.assertRaises(Refused):
                if cls is cr.ResourceResolver:fx.resolver.resource_methods(fx.klass,'current_stamina')
                elif speed:fx.resolver.methods(fx.klass)
                else:fx.resolver.method(fx.klass)


if __name__=='__main__':unittest.main()
