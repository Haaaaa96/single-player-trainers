"""Exercise real class discovery over bytes, without opening a process."""
from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'game_runtime'))
from class_scan import candidate, scan_classes, discovery_budget_mib
from connection_diagnostics import ConnectionDiagnosticError


class Memory:
    def __init__(self, protect=4):
        self.base = 0x10000
        self.data = bytearray(0x10000)
        self.meta = 0x800000
        self.extra = {}
        self.regions = [dict(base=self.base, size=len(self.data), type=0x20000, protect=protect)]
        self.fail_large = False
        self.fail_pages = set()
        self.read_calls = []
        self.path = 'X:/WorldApart.exe'
        self.closed = False

    def put(self, address, data):
        if self.base <= address and address + len(data) <= self.base + len(self.data):
            self.data[address-self.base:address-self.base+len(data)] = data
        else:
            self.extra[address] = data

    def read(self, address, size):
        self.read_calls.append((address, size))
        if self.fail_large and size > 4096:
            return b''
        if address // 4096 in self.fail_pages:
            return b''
        if self.base <= address < self.base + len(self.data):
            return bytes(self.data[address-self.base:address-self.base+size])
        for start, data in self.extra.items():
            if start <= address < start + len(data):
                return data[address-start:address-start+size]
        return b''

    def u64(self, address):
        data = self.read(address, 8)
        return struct.unpack('<Q', data)[0] if len(data) == 8 else 0

    def string(self, address, limit=256):
        return self.read(address, limit).split(b'\0', 1)[0].decode()

    def close(self):
        self.closed = True

    def add_class(self, name='Game.Player', address=0x11000, *, fields=True, field_table=True,
                  name_offset=0x100, type_offset=0x1000, token=0x02000001):
        namespace, _, short = name.rpartition('.')
        self.put(self.meta+name_offset, short.encode()+bytes(256))
        self.put(self.meta+name_offset+0x300, namespace.encode()+bytes(256))
        image, image_name, field_name, ty = 0x600000, 0x601000, 0x602000, 0x603000
        self.put(image, struct.pack('<Q', image_name))
        self.put(image_name, b'Game.dll'+bytes(256))
        self.put(field_name, b'Count'+bytes(256))
        self.put(ty, bytes(10)+b'\x08'+bytes(5))
        header = bytearray(320)
        for offset, value in [(0,image),(16,self.meta+name_offset),(24,self.meta+name_offset+0x300),
                              (0x68,self.meta+type_offset),(0x78,address),
                              (0x80,address+0x400 if field_table else 0)]:
            struct.pack_into('<Q', header, offset, value)
        struct.pack_into('<I', header, 0xf8, 24)
        struct.pack_into('<I', header, 0x11c, token)
        struct.pack_into('<H', header, 0x124, int(fields))
        self.put(address, header)
        if fields and field_table:
            self.put(address+0x400, struct.pack('<QQQiI',field_name,ty,address,16,0x04000001))
        return dict(name=name, nameFileOffset=name_offset, typeDefinitionFileOffset=type_offset,
                    image_name='Game.dll', token=hex(token), fieldCount=int(fields),
                    fields=[dict(name='Count',token='0x4000001')] if fields else [])


class DiscoveryScanTests(unittest.TestCase):
    def test_reported_live_footprint_gets_bounded_complete_scan_budget(self):
        budget = discovery_budget_mib(4524519424, None)
        self.assertGreater(budget * 1024 * 1024, 4524519424)
        self.assertLessEqual(budget, 16384)
        self.assertEqual(discovery_budget_mib(1024, None), 4096)
        self.assertEqual(discovery_budget_mib(20 * 1024**3, None), 16384)
        self.assertEqual(discovery_budget_mib(4524519424, 4096), 4096)
        for invalid in (True, 0, -1, 16385, float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                discovery_budget_mib(1024, invalid)

    def test_auto_budget_finishes_after_old_limit_and_detects_late_duplicate(self):
        # Scale budgets, not the scanning/candidate path, to exercise the
        # >old-limit case without allocating gigabytes for an offline test.
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                memory = Memory()
                spec = memory.add_class()
                memory.regions.append(dict(base=0x900000, size=0x10000, type=0x20000, protect=4))
                memory.put(0x900000, bytes(0x10000))
                if duplicate:
                    # Sparse fixture inserts must replace the covering block.
                    memory.extra.pop(0x900000)
                    memory.add_class(address=0x901000)
                    block = bytearray(0x10000)
                    for address, data in list(memory.extra.items()):
                        if 0x900000 <= address < 0x910000:
                            block[address-0x900000:address-0x900000+len(data)] = data
                            del memory.extra[address]
                    memory.put(0x900000, bytes(block))
                with patch('class_scan.DEFAULT_MIN_MIB', .1), patch('class_scan.MIN_OVERHEAD_MIB', .01):
                    if duplicate:
                        with self.assertRaises(ConnectionDiagnosticError) as raised:
                            scan_classes(memory, memory.meta, {spec['name']:spec})
                        diag = raised.exception.diagnostic
                        self.assertEqual(diag['outcome'], 'missing_or_ambiguous')
                        self.assertEqual(diag['types'][spec['name']]['valid_candidates'], 2)
                    else:
                        _, diag = scan_classes(memory, memory.meta, {spec['name']:spec})
                        self.assertEqual(diag['outcome'], 'verified')
                    self.assertEqual(diag['budget_mode'], 'automatic')
                    self.assertGreaterEqual(diag['read_bytes'], 0x20000)
                    self.assertIn((0x900000, 0x10000), memory.read_calls)

    def test_auto_hard_cap_remains_enforced(self):
        memory = Memory()
        spec = memory.add_class()
        with patch('class_scan.HARD_MAX_MIB', .01):
            with self.assertRaises(ConnectionDiagnosticError) as raised:
                scan_classes(memory, memory.meta, {spec['name']:spec})
        self.assertEqual(raised.exception.diagnostic['budget_reason'], 'read_limit')
        self.assertEqual(memory.read_calls, [])

    def test_actual_class_fields_and_repeated_scan(self):
        memory = Memory()
        spec = memory.add_class()
        for _ in range(2):
            found, diag = scan_classes(memory, memory.meta, {spec['name']:spec})
            self.assertEqual(found['Game.Player']['klass'], '0x11000')
            self.assertEqual(found['Game.Player']['fields'][0]['offset'], 16)
            self.assertEqual(diag['outcome'], 'verified')
            self.assertEqual(diag['types']['Game.Player']['valid_candidates'], 1)

    def test_read_only_private_pages_are_scanned_without_working_set(self):
        memory = Memory(protect=2)
        spec = memory.add_class()
        found, diag = scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertTrue(found)
        self.assertEqual(diag['region_count'], 1)
        # Memory deliberately has no chunks or working-set API. It therefore
        # models resident and nonresident readable memory identically.

    def test_partial_large_read_does_not_hide_later_pages(self):
        memory = Memory()
        spec = memory.add_class(address=0x16000)
        memory.fail_large = True
        memory.fail_pages.add(0x10000//4096)
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec})
        diag = raised.exception.diagnostic
        self.assertEqual(diag['types']['Game.Player']['valid_candidates'], 1)
        self.assertEqual(diag['unreadable_bytes'], 4096)
        self.assertEqual(diag['partial_reads'], 1)
        self.assertEqual(diag['outcome'], 'incomplete_scan')

    def test_page_fallback_can_succeed_when_all_pages_read(self):
        memory = Memory()
        spec = memory.add_class(address=0x16000)
        memory.fail_large = True
        found, diag = scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertEqual(found['Game.Player']['klass'], '0x16000')
        self.assertEqual(diag['unreadable_bytes'], 0)

    def test_transient_committed_page_gets_one_complete_deferred_reread(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.fail_large=True
        original=memory.read;attempts=[]
        def transient(address,size):
            if address==0x10000 and size==4096:
                attempts.append(address)
                if len(attempts)==1:return b'\0'*1024
            return original(address,size)
        memory.read=transient
        memory.query_region=lambda address:dict(base=address,size=4096,state=0x1000)
        found,diag=scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(found['Game.Player']['klass'],'0x16000')
        self.assertEqual(len(attempts),2)
        self.assertEqual(diag['deferred_pages_rechecked'],1)
        self.assertEqual(diag['recovered_bytes'],3072)
        self.assertEqual(diag['unreadable_bytes'],0)
        self.assertEqual(diag['page_rechecks'][0]['result'],'complete_reread')
        self.assertEqual(diag['candidate_rechecks'],1)

    def test_recovered_page_cannot_hide_a_second_valid_class(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.add_class(address=0x11000)
        memory.fail_large=True;original=memory.read;attempts=[]
        def transient(address,size):
            if address==0x11000 and size==4096:
                attempts.append(address)
                if len(attempts)==1:return b''
            return original(address,size)
        memory.read=transient
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        diag=raised.exception.diagnostic
        self.assertEqual(diag['outcome'],'missing_or_ambiguous')
        self.assertEqual(diag['types']['Game.Player']['valid_candidates'],2)
        self.assertEqual(diag['recovered_pages'],1)

    def test_candidate_straddling_recovered_page_is_reconsidered(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        # Name pointer is in the preceding readable page; the definition
        # pointer is in the temporarily unreadable page. The first candidate
        # header read fails, so its previously-seen marker cannot hide it.
        memory.add_class(address=0x10FB0)
        memory.fail_large=True;original=memory.read;recovered=[False]
        def transient(address,size):
            if address==0x11000 and size==4096 and not recovered[0]:
                recovered[0]=True
                return b''
            if address==0x10FB0 and size==320 and not recovered[0]:return b''
            return original(address,size)
        memory.read=transient
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['valid_candidates'],2)

    def test_page_becoming_free_after_deferred_read_requires_final_query(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.fail_large=True;memory.fail_pages.add(0x10000//4096)
        queries=[]
        def query(address):
            queries.append(address)
            return dict(base=address,size=4096,state=0x1000 if len(queries)==1 else 0x10000)
        memory.query_region=query
        found,diag=scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertTrue(found)
        self.assertEqual(queries,[0x10000]*3)
        self.assertEqual(diag['unreadable_bytes'],0)
        self.assertEqual(diag['retired_pages_rechecked'],1)
        self.assertEqual(diag['page_rechecks'][0]['result'],'finally_free_or_reserved')

    def test_permanently_committed_page_is_not_retried_without_bound(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.fail_large=True;memory.fail_pages.add(0x10000//4096)
        memory.query_region=lambda address:dict(base=address,size=4096,state=0x1000,protect=1)
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(memory.read_calls.count((0x10000,4096)),2)
        self.assertEqual(raised.exception.diagnostic['unreadable_bytes'],4096)
        self.assertEqual(raised.exception.diagnostic['page_rechecks'][0]['result'],'still_incomplete')

    def test_candidate_changed_after_main_scan_is_not_published(self):
        memory=Memory();spec=memory.add_class(address=0x11000)
        memory.regions.append(dict(base=0x900000,size=4096,type=0x20000,protect=4))
        memory.put(0x900000,bytes(4096));original=memory.read
        def changing(address,size):
            raw=original(address,size)
            if address==0x900000:
                memory.put(0x11000+0x11C,struct.pack('<I',0x0200FFFF))
            return raw
        memory.read=changing
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['outcome'],'candidate_changed')

    def test_deferred_page_reread_uses_the_original_time_budget(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.fail_large=True;original=memory.read;reads=[];now=[0]
        def transient(address,size):
            if address==0x10000 and size==4096:
                reads.append(address)
                if len(reads)==1:return b''
                now[0]=121
            return original(address,size)
        memory.read=transient
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec},clock=lambda:now[0])
        self.assertEqual(raised.exception.diagnostic['outcome'],'budget_exhausted')

    def test_number_of_pages_to_recheck_is_bounded(self):
        memory=Memory();spec=memory.add_class(address=0x16000)
        memory.fail_large=True;memory.fail_pages.update((0x10000//4096,0x11000//4096,0x12000//4096))
        with patch('class_scan.MAX_RECHECK_PAGES',2),self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['outcome'],'page_recheck_budget_exhausted')

    def test_freed_or_reserved_pages_are_rechecked_not_treated_as_unreadable(self):
        for state in (0x10000, 0x2000):
            with self.subTest(state=state):
                memory = Memory()
                spec = memory.add_class(address=0x16000)
                memory.fail_large = True
                memory.fail_pages.add(0x10000//4096)
                queries = []
                def query(address):
                    queries.append(address)
                    return dict(base=address, size=4096, state=state)
                memory.query_region = query
                found, diag = scan_classes(memory,memory.meta,{'Game.Player':spec})
                self.assertTrue(found)
                self.assertEqual(diag['unreadable_bytes'], 0)
                self.assertEqual(diag['retired_bytes'], 4096)
                self.assertEqual(queries,[0x10000,0x10000])

    def test_committed_or_unproven_missing_pages_still_refuse(self):
        for region in (None, dict(base=0x10000,size=4096,state=0x1000),
                       dict(base=0x10000,size=2048,state=0x10000),
                       dict(base=0x10001,size=4096,state=0x10000)):
            with self.subTest(region=region):
                memory = Memory()
                spec = memory.add_class(address=0x16000)
                memory.fail_large = True
                memory.fail_pages.add(0x10000//4096)
                memory.query_region = lambda address:region
                with self.assertRaises(ConnectionDiagnosticError) as raised:
                    scan_classes(memory,memory.meta,{'Game.Player':spec})
                self.assertEqual(raised.exception.diagnostic['outcome'],'incomplete_scan')

    def test_recommitted_page_is_read_and_cannot_hide_duplicate(self):
        memory = Memory()
        spec = memory.add_class(address=0x16000)
        memory.add_class(address=0x11000)
        memory.fail_large = True
        memory.fail_pages.add(0x11000//4096)
        queries = []
        def query(address):
            queries.append(address)
            if len(queries) == 1:
                return dict(base=address,size=4096,state=0x10000)
            memory.fail_pages.clear()
            return dict(base=address,size=4096,state=0x1000)
        memory.query_region = query
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['valid_candidates'],2)

    def test_retired_partial_page_does_not_supply_a_stale_candidate(self):
        memory = Memory()
        spec = memory.add_class(address=0x11000)
        memory.fail_large = True
        original = memory.read
        memory.read = lambda address,size: original(address,size)[:2048] if address == 0x11000 and size == 4096 else original(address,size)
        memory.query_region = lambda address:dict(base=address,size=4096,state=0x10000)
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['valid_candidates'],0)

    def test_requery_failure_cannot_publish_retired_span(self):
        memory = Memory()
        spec = memory.add_class(address=0x16000)
        memory.fail_large = True
        memory.fail_pages.add(0x10000//4096)
        results = iter((dict(base=0x10000,size=4096,state=0x10000),None))
        memory.query_region = lambda address: next(results)
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['outcome'],'incomplete_scan')

    def test_final_region_query_deadline_is_enforced(self):
        memory = Memory()
        spec = memory.add_class(address=0x16000)
        memory.fail_large = True
        memory.fail_pages.add(0x10000//4096)
        current = [0]
        queries = []
        def query(address):
            queries.append(address)
            if len(queries) == 2:
                current[0] = 121
            return dict(base=address,size=4096,state=0x10000)
        memory.query_region = query
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec},clock=lambda:current[0])
        self.assertEqual(raised.exception.diagnostic['outcome'],'budget_exhausted')

    def test_same_name_pointer_can_belong_to_distinct_namespaces(self):
        memory = Memory()
        first = memory.add_class(name='Game.Player')
        second = memory.add_class(name='Other.Player', address=0x16000, type_offset=0x2000)
        # Both share the class-name string; keep different namespace pointers.
        memory.put(memory.meta+0x800, b'Game'+bytes(256))
        memory.put(0x11000+24, struct.pack('<Q', memory.meta+0x800))
        found, _ = scan_classes(memory, memory.meta, {s['name']:s for s in (first,second)})
        self.assertEqual(len(found), 2)

    def test_multiple_valid_candidates_are_never_chosen(self):
        memory = Memory()
        spec = memory.add_class()
        memory.add_class(address=0x16000)
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertIn('多个候选', str(raised.exception))
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['valid_candidates'], 2)

    def test_missing_pointer_is_distinct_from_rejected_candidate(self):
        memory = Memory()
        spec = memory.add_class()
        wrong = copy.deepcopy(spec)
        wrong['nameFileOffset'] += 8
        wrong['typeDefinitionFileOffset'] += 8
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':wrong})
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['pointer_hits'], 0)
        memory.put(0x11000+0x68, struct.pack('<Q', memory.meta+999))
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['rejections'],
                         {'type_definition_mismatch': 1})

    def test_copied_name_string_is_found_through_current_type_identity(self):
        memory = Memory()
        spec = memory.add_class()
        memory.put(0x604000, b'Player'+bytes(256))
        memory.put(0x11000+16, struct.pack('<Q', 0x604000))
        found, _ = scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertEqual(found['Game.Player']['klass'], '0x11000')

    def test_uninitialized_field_table_is_diagnosed_but_zero_fields_work(self):
        memory = Memory()
        spec = memory.add_class(field_table=False)
        self.assertEqual(candidate(memory, 0x11000, spec, memory.meta)[1], 'field_table_not_initialized')
        zero = memory.add_class(fields=False, field_table=False)
        self.assertIsNotNone(candidate(memory, 0x11000, zero, memory.meta)[0])

    def test_image_field_identity_and_tokens_are_still_checked(self):
        for offset, data, reason in [
                (0x600000, struct.pack('<Q', 0), 'class_image_mismatch'),
                (0x11000+0x11c, struct.pack('<I', 42), 'class_token_mismatch'),
                (0x11400+16, struct.pack('<Q', 0), 'field_identity_mismatch'),
                (0x11400+28, struct.pack('<I', 42), 'required_field_mismatch')]:
            with self.subTest(reason=reason):
                memory = Memory()
                spec = memory.add_class()
                memory.put(offset, data)
                self.assertEqual(candidate(memory, 0x11000, spec, memory.meta)[1], reason)

    def test_budget_bounds_reads_and_failure_does_not_return_candidates(self):
        memory = Memory()
        spec = memory.add_class()
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec}, max_mib=.01)
        self.assertEqual(raised.exception.diagnostic['outcome'], 'budget_exhausted')
        self.assertEqual(memory.read_calls, [])
        self.assertEqual(raised.exception.diagnostic['budget_mode'], 'explicit')
        self.assertEqual(raised.exception.diagnostic['budget_reason'], 'read_limit')

    def test_deadline_also_applies_when_memory_cannot_be_read(self):
        memory = Memory()
        spec = memory.add_class()
        times = iter((0, 121, 121))
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec}, clock=lambda:next(times))
        self.assertEqual(raised.exception.diagnostic['outcome'], 'budget_exhausted')

        self.assertEqual(raised.exception.diagnostic['budget_reason'], 'time_limit')

    def test_last_read_crossing_deadline_cannot_publish_success(self):
        memory = Memory()
        spec = memory.add_class()
        memory.regions.append(dict(base=0x900000,size=4096,type=0x20000,protect=4))
        memory.put(0x900000, bytes(4096))
        current = [0]
        original = memory.read
        def delayed(address,size):
            result = original(address,size)
            if address == 0x900000:
                current[0] = 121
            return result
        memory.read = delayed
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory,memory.meta,{'Game.Player':spec},clock=lambda:current[0])
        self.assertEqual(raised.exception.diagnostic['outcome'],'budget_exhausted')
        self.assertEqual(raised.exception.diagnostic['types']['Game.Player']['valid_candidates'],1)

    def test_guard_and_noncommitted_ineligible_regions_do_not_get_read(self):
        memory = Memory(protect=4|0x100)
        spec = memory.add_class()
        with self.assertRaises(ConnectionDiagnosticError) as raised:
            scan_classes(memory, memory.meta, {'Game.Player':spec})
        self.assertEqual(raised.exception.diagnostic['region_count'], 0)
        self.assertEqual(memory.read_calls, [])


if __name__ == '__main__':
    unittest.main()
