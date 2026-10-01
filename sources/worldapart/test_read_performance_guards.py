"""Read optimizations must keep live ownership and end-of-read metadata guards."""
import struct
import unittest
from unittest.mock import Mock, patch

import learning_adapter
from acquisition_context import AcquisitionContextRefused
from extension_runtime import ExtensionRuntime
from photostone_adapter import PhotostoneResolver
from runtime_metadata import RuntimeMetadataError
from test_extension_runtime import LearningFixture, UI
from test_runtime_metadata import BASE, MemoryReader, metadata
from write_guard import Refused


class OwnedLookupTests(unittest.TestCase):
    def fixture(self):
        fx = LearningFixture()
        context = Mock(anchors=[dict(address=fx.registry, expected_hex=fx.reader.read(fx.registry,8).hex())])
        context.managers.return_value = (0x1000, {})
        context.field.side_effect = lambda c,n,k: {'_managers':0x30, '_size':0x18, '_version':0x1c, '_items':0x10}[n]
        context.pointer.side_effect = lambda a,label: {0x1030:0x2000,0x2010:0x3000}[a]
        context.i.return_value = 1
        context.q.return_value = 4
        context.anchor.return_value = struct.pack('<Q', fx.manager)
        context.obj.return_value = dict(namespace='Game', name='UIManager')
        return fx, context

    def test_real_constructor_first_repeat_and_fresh_resolver_without_heap_scan(self):
        fx, context = self.fixture()
        with fx.context(), patch('acquisition_context.CODE_PROFILES', [{'code': {}}]), \
                patch('acquisition_context._Context', return_value=context), \
                patch('extension_runtime.scan_classes', side_effect=AssertionError('unexpected scan')):
            rr = learning_adapter.LearningResolver(fx.reader)
            self.assertFalse(rr.snapshot()['active'])
            self.assertFalse(rr.snapshot()['active'])
            other = learning_adapter.LearningResolver(fx.reader)
            self.assertFalse(other.snapshot()['active'])
            self.assertEqual(context._finish_snapshot.call_count, 3)
            self.assertEqual(fx.reader.region_queries, 0)
            self.assertTrue(any(a == fx.registry for a,_ in rr.anchors))

    def test_changed_class_during_later_read_never_falls_back_to_scan(self):
        for offset,value,fmt in ((0x78,0,'Q'), (0x68,BASE+8,'Q'), (0x11c,0x0200ffff,'I')):
            fx, context = self.fixture()
            with self.subTest(offset=offset), fx.context(), \
                    patch('acquisition_context.CODE_PROFILES', [{'code': {}}]), \
                    patch('acquisition_context._Context', return_value=context), \
                    patch('extension_runtime.scan_classes', side_effect=AssertionError('unexpected scan')):
                rr = learning_adapter.LearningResolver(fx.reader)
                rr.snapshot()
                fx.reader.number(fx.classes[UI]+offset,value,fmt)
                with self.assertRaises((Refused,RuntimeMetadataError)):
                    rr.snapshot()

    def test_owner_missing_duplicate_transition_and_bounds_fail_closed(self):
        for failure in ('missing','duplicate','size','capacity','transition','code_race'):
            fx, context = self.fixture()
            if failure == 'missing': context.obj.return_value = dict(namespace='Game',name='Other')
            if failure == 'duplicate':
                context.i.return_value = 2
                context.anchor.return_value = struct.pack('<QQ',fx.manager,fx.manager)
            if failure == 'size': context.i.return_value = 129
            if failure == 'capacity': context.q.return_value = 0
            if failure == 'transition': context._finish_snapshot.side_effect = AcquisitionContextRefused('changed')
            with self.subTest(failure=failure), fx.context(), \
                    patch('acquisition_context.CODE_PROFILES', [{'code': {}}]), \
                    patch('acquisition_context._Context', return_value=context,
                          side_effect=AcquisitionContextRefused('code changed') if failure=='code_race' else None), \
                    patch('extension_runtime.scan_classes', side_effect=AssertionError('unexpected scan')):
                with self.assertRaises(Refused):
                    learning_adapter.LearningResolver(fx.reader).snapshot()


class PhotostoneReadScopeTests(unittest.TestCase):
    name = 'Game.Model.NpcModel'

    def fixture(self):
        data, _ = metadata([(self.name,'Game.dll',['one','two'])])
        reader = MemoryReader(data)
        rr = PhotostoneResolver.__new__(PhotostoneResolver)
        rr.reader, rr.meta = reader, BASE
        rr._runtime = ExtensionRuntime(reader,BASE)
        return rr, reader

    def change_token(self, reader):
        fields, _ = struct.unpack_from('<II',reader.data,0x60)
        struct.pack_into('<I',reader.data,fields+8,0x0400ffff)

    def test_metadata_reused_only_inside_read_and_revalidated_at_exit(self):
        rr, reader = self.fixture()
        with rr.metadata_read_scope():
            first = rr.runtime_spec(self.name,{'fields':[{'name':'one'}]})
            count = len(reader.calls)
            self.assertIs(first,rr.runtime_spec(self.name,{'fields':[{'name':'one'}]}))
            self.assertEqual(len(reader.calls),count)
        self.assertGreater(len(reader.calls),count)
        self.assertIsNone(rr._read_specs)
        self.assertEqual(rr._class_cache,{})
        with rr.metadata_read_scope():
            rr.runtime_spec(self.name,{'fields':[{'name':'one'}]})
            self.assertGreater(len(reader.calls),count)

    def test_metadata_change_mid_read_and_between_reads_is_rejected(self):
        for mid_read in (True,False):
            rr, reader = self.fixture()
            with self.subTest(mid_read=mid_read), self.assertRaises(RuntimeMetadataError):
                with rr.metadata_read_scope():
                    rr.runtime_spec(self.name)
                    if mid_read: self.change_token(reader)
                self.change_token(reader)
                with rr.metadata_read_scope(): rr.runtime_spec(self.name)
            self.assertIsNone(rr._read_specs)
            self.assertEqual(rr._class_cache,{})

    def test_new_requirements_are_registered_and_missing_field_not_cached(self):
        rr, _ = self.fixture()
        with self.assertRaises(RuntimeMetadataError):
            with rr.metadata_read_scope():
                rr.runtime_spec(self.name,{'fields':[{'name':'one'}]})
                rr.runtime_spec(self.name,{'fields':[{'name':'two'}]})
                rr.runtime_spec(self.name,{'fields':[{'name':'absent'}]})
        self.assertIsNone(rr._read_specs)

    def test_failed_read_clears_metadata_and_class_caches(self):
        rr, _ = self.fixture()
        with self.assertRaisesRegex(Refused,'interrupted'):
            with rr.metadata_read_scope():
                rr.runtime_spec(self.name)
                rr._class_cache[123] = {'old':True}
                raise Refused('interrupted')
        self.assertIsNone(rr._read_specs)
        self.assertEqual(rr._class_cache,{})


if __name__ == '__main__': unittest.main()
