"""Real metadata, class scan, FieldInfo and LearningResolver initialization."""
from contextlib import ExitStack
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import learning_adapter as la
from extension_runtime import ExtensionRuntime, reviewed
from runtime_metadata import RuntimeMetadataError, RuntimeSpecs
from test_runtime_metadata import BASE, MemoryReader, metadata
from write_guard import Refused


UI = 'Game.UIManager'
STAMP = ('C:/Fixture/WorldApart.exe', 42)


class RuntimeRegistrationTests(unittest.TestCase):
    def test_late_type_and_field_registration_uses_index_and_current_tokens(self):
        data, specs = metadata([(UI, 'Game.dll', ['first', 'second']),
                                ('Game.PanelRegistry', 'Game.dll', ['_instances'])],
                               gap=3, token_shift=700, index_shift=99)
        reader = MemoryReader(data)
        runtime = ExtensionRuntime(reader, BASE)
        first = runtime.spec(UI, {'fields':[{'name':'first'}]})
        second = runtime.spec(UI, {'fields':[{'name':'second'}]})
        self.assertEqual(first['token'], int(specs[UI]['token'], 16))
        self.assertEqual(second['fields'], first['fields'])
        self.assertEqual([f['name'] for f in runtime.specs[UI]['fields']], ['first', 'second'])
        self.assertEqual(runtime.spec('Game.PanelRegistry')['name'], 'Game.PanelRegistry')
        strings = struct.unpack_from('<II', data, 0x18)
        self.assertEqual(reader.calls.count(strings), 1)

    def test_adding_requirement_cannot_discard_changed_cached_evidence(self):
        data, _ = metadata([(UI, 'Game.dll', ['first', 'second'])])
        reader = MemoryReader(data)
        runtime = ExtensionRuntime(reader, BASE)
        runtime.spec(UI, {'fields':[{'name':'first'}]})
        fields, _ = struct.unpack_from('<II', data, 0x60)
        struct.pack_into('<I', reader.data, fields + 8, 0x0400F001)
        with self.assertRaisesRegex(RuntimeMetadataError, 'changed|invalidated'):
            runtime.spec(UI, {'fields':[{'name':'second'}]})
        with self.assertRaises(RuntimeMetadataError): runtime.spec(UI)

    def test_ownership_conflict_and_missing_added_field_are_refused(self):
        data, _ = metadata([(UI, 'Game.dll', ['first'])])
        lookup = RuntimeSpecs(MemoryReader(data), BASE, [])
        lookup.register(reviewed(UI))
        lookup[UI]
        with self.assertRaisesRegex(RuntimeMetadataError, 'ownership'):
            lookup.register(dict(name=UI, image_name='Other.dll', fields=[]))
        lookup.register(reviewed(UI, {'fields':[{'name':'missing'}]}))
        with self.assertRaisesRegex(RuntimeMetadataError, 'required field'): lookup[UI]

    def nested(self, *, split_image=False):
        owner = 'System.Collections.Generic.Dictionary`2'
        types = [(owner,'mscorlib.dll',[])]
        if split_image:
            types.append(('Game.Other','Game.dll',[]))
            types.append(('.Entry','mscorlib.dll',['value']))
        else:
            types += [('System.Other','mscorlib.dll',[]),
                      ('.Entry','mscorlib.dll',['wrong']),('.Entry','mscorlib.dll',['value'])]
        data, specs = metadata(types)
        table, _ = struct.unpack_from('<II', data, 0xA0)
        if not split_image:
            struct.pack_into('<i',data,table+2*88+12,specs['System.Other']['byval'])
        selected = len(types)-1
        struct.pack_into('<i',data,table+selected*88+12,specs[owner]['byval'])
        return data, specs, selected

    def test_nested_name_is_selected_by_declaring_type_and_checked_on_repeat(self):
        data, specs, selected = self.nested()
        reader = MemoryReader(data)
        runtime = ExtensionRuntime(reader,BASE)
        result = runtime.spec('.Entry', {'fields':[{'name':'value'}]})
        self.assertEqual(result['typeDef'], selected)
        self.assertEqual(runtime.spec('.Entry'), result)
        owner = specs['System.Collections.Generic.Dictionary`2']
        reader.data[owner['nameFileOffset']] = ord('X')
        with self.assertRaisesRegex(RuntimeMetadataError, 'changed'): runtime.spec('.Entry')

    def test_nested_owner_image_is_part_of_repeat_evidence(self):
        data, _specs, _selected = self.nested(split_image=True)
        reader = MemoryReader(data)
        runtime = ExtensionRuntime(reader,BASE)
        runtime.spec('.Entry')
        images, _ = struct.unpack_from('<II',data,0xA8)
        game_name = struct.unpack_from('<i',data,images+40)[0]
        struct.pack_into('<i',reader.data,images,game_name)
        with self.assertRaisesRegex(RuntimeMetadataError, 'changed'):
            runtime.spec('.Entry')

    def test_nested_unknown_or_ambiguous_declaring_identity_is_refused(self):
        for duplicate_byval in (False, True):
            data, specs, selected = self.nested()
            table, _ = struct.unpack_from('<II',data,0xA0)
            if duplicate_byval:
                struct.pack_into('<i',data,table+88+8,specs['System.Collections.Generic.Dictionary`2']['byval'])
            else:
                struct.pack_into('<i',data,table+selected*88+12,999999)
            with self.subTest(duplicate_byval=duplicate_byval), self.assertRaises(RuntimeMetadataError):
                ExtensionRuntime(MemoryReader(data),BASE).spec('.Entry')


class RawReader:
    """Readable metadata and a single complete private heap, no OS handle."""
    heap_base = 0x20000000
    module = 0x50000000

    def __init__(self, data):
        self.data = bytearray(data)
        self.heap = bytearray(0x30000)
        self.path, self.h, self.pid = STAMP[0], 123, 999
        self.regions = []  # Deliberately stale: new feature classes appeared later.
        self.calls = []
        self.region_queries = 0

    def iter_regions(self):
        self.region_queries += 1
        yield dict(base=self.heap_base,size=len(self.heap),allocation=self.heap_base,type=0x20000,protect=4)

    def read(self,address,size):
        self.calls.append((address,size))
        if BASE <= address < BASE+len(self.data):
            return bytes(self.data[address-BASE:address-BASE+size])
        if self.heap_base <= address < self.heap_base+len(self.heap):
            return bytes(self.heap[address-self.heap_base:address-self.heap_base+size])
        return b''

    def put(self,address,raw):
        offset = address-self.heap_base
        assert 0 <= offset <= len(self.heap)-len(raw)
        self.heap[offset:offset+len(raw)] = raw

    def number(self,address,value,fmt='Q'):
        self.put(address,struct.pack('<'+fmt,value))

    def u64(self,address):
        raw=self.read(address,8)
        return struct.unpack('<Q',raw)[0] if len(raw)==8 else 0

    def string(self,address,limit=256):
        return self.read(address,limit).split(b'\0',1)[0].decode('utf8')


class LearningFixture:
    layouts = {
        UI: ('Game.dll', [('<IsWorldUiTeardown>k__BackingField',0,2,True),
                          ('m_IsShuttingDown',16,2,False),('_panelRegistry',24,0x12,False)]),
        'Game.Singleton`1': ('A1Framework.dll',[('lazyInstance',0,0x15,True)]),
        'System.Lazy`1': ('mscorlib.dll',[('_value',16,0x12,False)]),
        'Game.PanelRegistry': ('Game.dll',[('_instances',16,0x15,False)]),
        'System.Collections.Generic.Dictionary`2': ('mscorlib.dll',[('_count',16,8,False),
                                                   ('_version',20,8,False),('_entries',24,0x1D,False)]),
    }

    def __init__(self):
        data,self.specs=metadata([(name,image,[f[0] for f in fields])
                                 for name,(image,fields) in self.layouts.items()],token_shift=500,index_shift=91)
        self.reader=r=RawReader(data)
        self.classes,self.fields={},{}
        string_start=struct.unpack_from('<I',data,0x18)[0]
        for index,(name,(image,layouts)) in enumerate(self.layouts.items()):
            spec=self.specs[name]
            klass=r.heap_base+0x400*index
            self.classes[name]=klass
            field_table=r.heap_base+0x10000+0x200*index
            image_obj=r.heap_base+0x20000+0x20*index
            image_offset=data.index(image.encode()+b'\0',string_start)
            r.number(image_obj,BASE+image_offset)
            for offset,value in ((0,image_obj),(16,BASE+spec['nameFileOffset']),
                                 (24,BASE+spec['namespaceFileOffset']),(0x68,BASE+spec['typeDefinitionFileOffset']),
                                 (0x78,klass),(0x80,field_table)):
                r.number(klass+offset,value)
            r.number(klass+0xF8,40,'I')
            r.number(klass+0x11C,int(spec['token'],16),'I')
            r.number(klass+0x124,len(layouts),'H')
            for ordinal,(field_name,offset,kind,static) in enumerate(layouts):
                f=spec['fields'][ordinal]
                type_address=r.heap_base+0x18000+index*0x200+ordinal*16
                record=field_table+ordinal*32
                td=bytearray(16);td[8]=0x11 if static else 1;td[10]=kind
                r.put(type_address,td)
                r.put(record,struct.pack('<QQQiI',BASE+f['nameFileOffset'],type_address,klass,offset,int(f['token'],16)))
                self.fields[name,field_name]=(record,type_address)
        self.manager,self.lazy,self.registry,self.dictionary=[r.heap_base+0x24000+i*0x100 for i in range(4)]
        self.ui_static,self.singleton_static=r.heap_base+0x25000,r.heap_base+0x25100
        r.number(self.classes[UI]+0x58,self.classes['Game.Singleton`1'])
        r.number(self.classes[UI]+0xB8,self.ui_static)
        r.number(self.classes['Game.Singleton`1']+0xB8,self.singleton_static)
        for obj,name in ((self.manager,UI),(self.lazy,'System.Lazy`1'),(self.registry,'Game.PanelRegistry'),
                         (self.dictionary,'System.Collections.Generic.Dictionary`2')):
            r.number(obj,self.classes[name])
        r.number(self.singleton_static,self.lazy)
        r.number(self.lazy+16,self.manager)
        r.number(self.manager+24,self.registry)
        r.number(self.registry+16,self.dictionary)

    def context(self):
        stack=ExitStack()
        stack.enter_context(patch.object(la,'process_identity',return_value=STAMP))
        stack.enter_context(patch.object(la,'validate_installation',return_value=SimpleNamespace(
            executable_path=Path(STAMP[0]),install_directory=Path('C:/Fixture'))))
        stack.enter_context(patch.object(la.probe,'verified_mappings',return_value={
            'metadata':[{'base':BASE}], 'game_assembly':[{'base':self.reader.module}]}))
        return stack


class RealLearningRuntimeTests(unittest.TestCase):
    def test_real_constructor_first_repeat_and_new_resolver_reuse_class_with_fresh_regions(self):
        fx=LearningFixture()
        with fx.context():
            resolver=la.LearningResolver(fx.reader)
            first=resolver.snapshot()
            second=resolver.snapshot()
            other=la.LearningResolver(fx.reader)
            self.assertEqual(first,second)
            self.assertEqual(other.snapshot(),first)
            self.assertFalse(first['active'])
            self.assertIs(other._runtime,resolver._runtime)
            self.assertEqual(fx.reader.region_queries,1)
            self.assertEqual(resolver._runtime.classes[UI],fx.classes[UI])
            self.assertFalse(any(address==fx.reader.module+la.UI_MANAGER_CLASS_RVA
                                 for address,_size in fx.reader.calls))

    def test_cached_class_identity_changes_are_refused_without_rescan(self):
        for change in ('token','definition','self'):
            fx=LearningFixture()
            with fx.context():
                resolver=la.LearningResolver(fx.reader)
                resolver.snapshot()
                klass=fx.classes[UI]
                offset,value,fmt={'token':(0x11C,0x0200FFFF,'I'),
                                  'definition':(0x68,BASE+8,'Q'),'self':(0x78,klass+8,'Q')}[change]
                fx.reader.number(klass+offset,value,fmt)
                with self.subTest(change=change), self.assertRaisesRegex(RuntimeMetadataError,'Cached'):
                    resolver.snapshot()
                self.assertEqual(fx.reader.region_queries,1)

    def test_real_fieldinfo_kind_static_token_and_parent_changes_are_refused_on_refresh(self):
        for change in ('kind','static','token','parent'):
            fx=LearningFixture()
            with fx.context():
                resolver=la.LearningResolver(fx.reader)
                resolver.snapshot()
                record,type_address=fx.fields[UI,'m_IsShuttingDown']
                if change=='kind':fx.reader.number(type_address+10,8,'B')
                elif change=='static':fx.reader.number(type_address+8,0x11,'B')
                elif change=='token':fx.reader.number(record+28,0x0400FFFF,'I')
                else:fx.reader.number(record+16,fx.classes[UI]+8)
                with self.subTest(change=change), self.assertRaises((Refused,RuntimeMetadataError)):
                    resolver.snapshot()

    def test_changed_current_field_metadata_cannot_be_accepted_on_repeat(self):
        fx=LearningFixture()
        with fx.context():
            resolver=la.LearningResolver(fx.reader)
            resolver.snapshot()
            field_table=struct.unpack_from('<I',fx.reader.data,0x60)[0]
            ordinal=fx.specs[UI]['fields'][1]['fieldIndex']
            struct.pack_into('<i',fx.reader.data,field_table+ordinal*12+4,9999)
            with self.assertRaises(RuntimeMetadataError):resolver.snapshot()

    def test_runtime_from_other_metadata_mapping_cannot_be_reused(self):
        fx=LearningFixture()
        with fx.context():
            fx.reader._extension_runtime=ExtensionRuntime(fx.reader,BASE+8)
            with self.assertRaisesRegex(Refused,'当前连接'):la.LearningResolver(fx.reader)


if __name__=='__main__':unittest.main()
