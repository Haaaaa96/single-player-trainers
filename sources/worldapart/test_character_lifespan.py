"""Offline lifespan boundaries, context guards, transport and UI contracts."""
from dataclasses import replace
from pathlib import Path
import copy
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import character_lifespan as life
import character_lifespan_native as native
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(life.LifespanTarget(20, 100, 0., 0x504C, tuple(range(9)) + ((0x5000, 0x5020, 1, 0, 1),),
                                      ((0x1000, "00"),)), **changes)


def context(shown=None):
    shown = shown or target()
    return dict(identity=shown.identity, anchors=shown.anchors, growth=shown.growth, growth_address=shown.growth_address,
                lifecycle=dict(handling=False, handled_age=False, handled_max=False),
                descriptor=dict(player="0x2000", player_class="0x3000", combat="0x4000", combat_class="0x4500",
                    growth_dictionary="0x5000", base_dictionary="0x6000", growth_before=shown.growth,
                    growth_address=hex(shown.growth_address), health_address="0x604c", identity_key="a" * 64,
                    methods=dict(age="0x7000", max="0x7100", modify="0x7200")))


class ValueTests(unittest.TestCase):
    def test_full_entry_anchor_only_expands_matching_short_prefix(self):
        short = (0x1000, "01" * 12)
        full = (0x1000, "01" * 12 + "02" * 4)
        self.assertEqual(life.lifespan_anchors((short, (0x100C,"02"*4)), (full,)),
                         ((0x100C,"02"*4), full))
        with self.assertRaises(Refused):
            life.lifespan_anchors(((0x1000,"ff"*12),), (full,))
        with self.assertRaises(Refused):
            life.lifespan_anchors(((0x2000,"01"),(0x2000,"0102")), (full,))

    def test_only_positive_integer_amounts(self):
        for text, value in (("1", 1), (" 1000 ", 1000)):
            self.assertEqual(life.parse_increase(text), value)
        for text in ("0", "-1", "+1", "1.0", "1e2", "1001", "", "NaN", 1, True):
            with self.subTest(text=text), self.assertRaises(Refused):
                life.parse_increase(text)

    def test_existing_and_absent_growth_support_positive_addition(self):
        self.assertEqual(life.validate_increase(target(), 1000), 1000)
        self.assertEqual(life.validate_increase(target(growth_address=0), 1), 1)
        self.assertEqual(life.validate_increase(target(growth=-5), 1), -4)

    def test_age_equal_to_maximum_is_not_exhausted_in_game(self):
        self.assertEqual(life.validate_increase(target(current_age=100), 1), 1)
        with self.assertRaises(Refused):
            life.validate_increase(target(current_age=101), 1)

    def test_actual_maximum_is_not_limited_by_growth_tool_bound(self):
        self.assertEqual(life.validate_increase(target(maximum=1_000_001), 1), 1)
        self.assertEqual(life.validate_increase(target(maximum=life.MAX_NATIVE_INT), 1), 1)
        with self.assertRaises(Refused):
            life.validate_increase(target(maximum=life.MAX_NATIVE_INT + 1), 1)

    def test_invalid_lifecycle_values_and_precision_are_refused(self):
        cases = [target(exhausted=True), target(can_edit=False), target(maximum=0), target(growth=float('nan')),
                 target(growth=float('inf')), target(current_age=True), target(growth_address=1),
                 target(growth_address=0, growth=1), target(growth=1_000_000), target(identity=()), target(anchors=())]
        for shown in cases:
            with self.subTest(shown=shown), self.assertRaises(Refused):
                life.validate_increase(shown, 1)
        for amount in (0, -1, True, 1.0, 1001):
            with self.assertRaises(Refused):
                life.validate_increase(target(), amount)

    def test_bad_anchor_never_reaches_native(self):
        for anchors in (((0,"00"),), ((0x1000,"zz"),), ((0x1000,""),), ((0x1000,),)):
            with self.assertRaises(Refused):
                life.validate_increase(target(anchors=anchors), 1)


class MethodTests(unittest.TestCase):
    def setUp(self):
        from test_current_resources import SimpleReader
        self.rr=life.LifespanResolver.__new__(life.LifespanResolver)
        self.rr.module,self.klass,self.table=0x10000000,0x1000,0x2000
        self.rr.anchors,self.memory,self.names=[],{},{}
        self.put(self.klass+0x98,'Q',self.table)
        self.put(self.klass+0x120,'H',3)
        self.methods={}
        for i,(key,spec) in enumerate(life.SPECS['methods'].items()):
            mi,name,ret=0x3000+i*0x100,0x5000+i*0x100,0x7000+i*0x100
            self.methods[key]=mi
            for addr,fmt,value in [(self.table+i*8,'Q',mi),(mi,'Q',self.rr.module+spec['rva']),
                    (mi+0x18,'Q',name),(mi+0x20,'Q',self.klass),(mi+0x28,'Q',ret),
                    (mi+0x48,'i',spec['token']),(mi+0x4C,'H',0x86),(mi+0x52,'B',spec['parameters']),
                    (ret+10,'B',spec['return_kind']),(ret+11,'B',0x80)]:self.put(addr,fmt,value)
            self.store(self.rr.module+spec['rva'],bytes.fromhex(spec['prefix']))
            self.names[name]=spec['name']
        self.rr.reader=SimpleReader(self.memory,self.names)

    def put(self,a,fmt,value):self.store(a,struct.pack('<'+fmt,value))

    def store(self,a,data):
        self.memory.update({a+i:b for i,b in enumerate(data)})

    def test_exact_player_getters_and_single_modifier_allow_valuetype_flag(self):
        self.assertEqual(self.rr.lifespan_methods(self.klass),{k:hex(v) for k,v in self.methods.items()})
        self.assertEqual(life.SPECS['methods']['modify']['token'],0x06013E6E)
        self.assertEqual(life.SPECS['methods']['modify']['rva'],0xDC3FB0)

    def test_current_profile_first_and_repeated_read_and_metadata_change(self):
        current = life.SPECS['method_profiles']['reviewed_20260930']
        for key, spec in current.items():
            mi = self.methods[key]
            self.put(mi,'Q',self.rr.module+spec['rva'])
            self.put(mi+0x48,'i',spec['token'])
            self.store(self.rr.module+spec['rva'],bytes.fromhex(spec['prefix']))
        expected = {k:hex(v) for k,v in self.methods.items()}
        self.assertEqual(self.rr.lifespan_methods(self.klass), expected)
        self.assertEqual(self.rr.lifespan_method_profile, 'reviewed_20260930')
        self.rr.anchors.clear()
        self.assertEqual(self.rr.lifespan_methods(self.klass), expected)
        self.assertTrue(self.rr.anchors)
        self.put(self.methods['max']+0x48,'i',life.SPECS['methods']['max']['token'])
        with self.assertRaises(Refused):self.rr.lifespan_methods(self.klass)
        self.assertIsNone(self.rr.lifespan_method_profile)

    def test_current_request_uses_selected_native_evidence(self):
        descriptor = dict(context()['descriptor'], method_profile='reviewed_20260930',
                          anchors=[dict(address='0x1000',size=1,expected_hex='00')])
        request = native.LifespanNative.request(descriptor, 1, 'token', False)
        self.assertEqual(request['method_token'], 0x06013EAC)
        self.assertEqual(request['method_rva'], 0xDF6320)
        descriptor['method_profile'] = 'unreviewed'
        with self.assertRaises(Refused):native.LifespanNative.request(descriptor, 1, 'token', False)

    def test_byref_and_pinned_return_types_are_refused(self):
        for flags in (0x20,0x40,0xA0,0xC0):
            self.put(0x700B,'B',flags)
            with self.subTest(flags=flags),self.assertRaises(Refused):self.rr.lifespan_methods(self.klass)

    def test_static_wrong_owner_parameter_and_code_are_refused(self):
        mi=self.methods['modify']
        for address,fmt,bad,good in [(mi+0x4C,'H',0x96,0x86),(mi+0x20,'Q',0x9999,self.klass),
                                    (mi+0x52,'B',0,1),(0x720A,'B',8,12)]:
            self.put(address,fmt,bad)
            with self.subTest(address=address),self.assertRaises(Refused):self.rr.lifespan_methods(self.klass)
            self.put(address,fmt,good)
        self.put(self.rr.module+life.SPECS['methods']['modify']['rva'],'B',0)
        with self.assertRaises(Refused):self.rr.lifespan_methods(self.klass)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.a = life.LifespanAdapter.__new__(life.LifespanAdapter)
        self.a.blocked = False
        self.a._lock, self.a._native = threading.Lock(), Mock()
        raw = dict(anchor_verified=True, anchors=[dict(address=0x100,expected_hex="00")],
                   player=0x2000, manager=1,store=2,world=3)
        self.a.game = SimpleNamespace(stamp=("game",1), blocked=False,
                    resolver=SimpleNamespace(resolve=Mock(return_value=raw)))
        rr = self.rr = self.a.resolver = Mock()
        rr.reader.h = 9
        rr.obj.side_effect = lambda a, name: {"klass": "0x3000" if a == 0x2000 else "0x4500"}
        self.offsets = {"combat":0x48, "<CurrentLayerId>k__BackingField":0x60,
                       "<PendingRealmBreakthrough>k__BackingField":0x78,"_cultivateInjectBatchDepth":0x68,
                       "<GrowthAttrs>k__BackingField":0x28,"<BaseAttrs>k__BackingField":0x20}
        self.offsets.update({v['name']:v['offset'] for v in life.SPECS['fields'].values()})
        rr.reviewed_field.side_effect = lambda c,n,k: self.offsets[n]
        self.pointers = {0x2048:0x4000,0x4010:0x2000,0x4078:0,0x4028:0x5000,0x4020:0x6000}
        rr.q.side_effect = lambda a, **kw: self.pointers[a]
        self.ints = {0x4060:1,0x4068:0}
        rr.i.side_effect = lambda a, **kw: self.ints[a]
        self.health, self.growth = 100., 0.
        rr.dictionary.side_effect = self.dictionary
        self.flags = {}
        def anchor(a, size):
            data = bytes([self.flags.get(a, 0)]) + bytes(size-1)
            rr.anchors.append((a,data.hex()))
            return data
        rr.anchor.side_effect = anchor
        rr.exact.side_effect = lambda a, size: bytes([self.flags.get(a,0)]) + bytes(size-1)
        rr.lifespan_methods.return_value = dict(age="0x7000",max="0x7100",modify="0x7200")
        self.pid_patch = patch.object(life,"process_identity",return_value=("game",1)).start()
        self.safe = patch.object(life,"require_safe_acquisition_context",return_value=dict(anchors=[])).start()
        self.addCleanup(patch.stopall)

    def dictionary(self, address):
        if address == 0x5000:
            return {8:dict(value=self.growth,address=0x504C)}, [], (address,0x5020,1,0,1)
        return {1:dict(value=self.health,address=0x604C)}, [], (address,0x6020,1,0,1)

    def test_context_pins_player_and_every_lifespan_lifecycle_field(self):
        result = self.a.read_context()
        self.assertEqual(result["growth"],0)
        self.assertEqual(result['descriptor']['player'],'0x2000')
        self.assertTrue({0x21B8,0x21BC,0x21C4,0x5040}.issubset({a for a,_ in result['anchors']}))

    def test_in_progress_and_handled_exhaustion_refuse_before_query(self):
        for offset in (0x1B8,0x1BC,0x1C4):
            self.flags = {0x2000+offset:1}
            with self.assertRaises(Refused): self.a.read_context()
        self.a._native.execute.assert_not_called()

    def test_dead_player_and_transitions_refuse(self):
        self.health = 0.
        with self.assertRaises(Refused): self.a.read_context()
        self.health = 100.
        self.ints[0x4068] = 1
        with self.assertRaises(Refused): self.a.read_context()
        self.ints[0x4068] = 0
        self.pointers[0x4078] = 0x9000
        with self.assertRaises(Refused): self.a.read_context()

    def test_wrong_owner_field_layout_and_scene_refuse(self):
        self.pointers[0x4010] = 0x9000
        with self.assertRaises(Refused): self.a.read_context()
        self.pointers[0x4010] = 0x2000
        self.offsets['m_HandlingLifespanExhaustion'] = 0x1B9
        with self.assertRaises(Refused): self.a.read_context()
        self.offsets['m_HandlingLifespanExhaustion'] = 0x1B8
        self.safe.side_effect = life.AcquisitionContextRefused("battle")
        with self.assertRaises(Refused): self.a.read_context()

    def test_prepare_rejects_stale_shown_identity_and_context(self):
        ctx = self.a.read_context()
        shown = target(identity=ctx['identity'],anchors=ctx['anchors'])
        self.assertEqual(self.a.prepare_native(ctx,shown,1)['amount'],1)
        with self.assertRaises(Refused): self.a.prepare_native(ctx,replace(shown,identity=target().identity),1)
        self.growth = 1.
        with self.assertRaises(Refused): self.a.prepare_native(ctx,shown,1)

    def test_pending_blocks_both_inspection_and_increase(self):
        with patch('acquisition_adapter.native_calls_pending',return_value=True):
            with self.assertRaises(Refused): self.a.snapshot()
            with self.assertRaises(Refused): self.a.increase(target(),1)
        self.a._native.execute.assert_not_called()

    def test_uncertain_inspection_stops_adapter(self):
        self.a._native.execute.side_effect = UncertainWrite('query lost')
        with patch('acquisition_adapter.native_calls_pending',return_value=False),self.assertRaises(UncertainWrite):
            self.a.snapshot()
        self.assertTrue(self.a.blocked)


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.shown = target()
        self.context = context()
        self.descriptor = dict(self.context['descriptor'],anchors=[dict(address='0x1000',size=1,expected_hex='00')])
        self.game = SimpleNamespace(resolver=SimpleNamespace(reader=SimpleNamespace(pid=1234)),
                                   stamp=('worldapart.exe',99),record=Mock())
        self.a = SimpleNamespace(prepare_native=Mock(return_value=self.descriptor),read_context=Mock(return_value=self.context))
        patch.object(native,'initialize_runtime',return_value=Path(self.temp.name)).start()
        patch.dict('sys.modules',frida=SimpleNamespace(__version__='17.7.3')).start()
        self.addCleanup(patch.stopall)
        self.n = native.LifespanNative(self.game,self.a)
        self.addCleanup(lambda:native._LIVE_BRIDGES.discard(self.n))
        self.addCleanup(lambda:native._RETAINED_BRIDGES.discard(self.n))
        self.connection = Mock()
        self.connection.script = SimpleNamespace(exports_sync=SimpleNamespace(submit=Mock()))
        self.behavior = 'success'
        self.acquire = patch.object(native,'acquire_connection',side_effect=self.acquire_connection).start()

    def acquire_connection(self, identity, frida, source, epoch, owner, message, detached, before, check):
        before()
        def submit(request):
            adding = request['operation']=='lifespan_add'
            if self.behavior == 'rpc_error': raise OSError('pipe lost')
            outcome = dict(status='completed',token=request['token'],called=True,mutated=adding,
                           current_age=20,maximum=self.shown.maximum + (1 if adding else 0),growth=1. if adding else 0.,
                           before_maximum=self.shown.maximum,actual_delta=1.,exhausted=False,handling=False,
                           handled_age=False,handled_max=False,identity_key='a'*64)
            if self.behavior == 'rejected': outcome.update(status='rejected',called=False)
            if self.behavior == 'wrong_age': outcome['current_age']=21
            if self.behavior == 'wrong_growth': outcome['growth']=2.
            if self.behavior == 'bad_max': outcome['maximum']=99
            if self.behavior == 'nan_delta': outcome['actual_delta']=float('nan')
            if adding:
                after=target(maximum=101,growth=1.,identity=self.shown.identity[:9]+((0x5000,0x5020,1,0,2),))
                self.a.read_context.return_value=context(after)
            message(dict(type='send',payload=outcome),None)
        self.connection.script.exports_sync.submit.side_effect=submit
        return self.connection

    def test_inspection_uses_readonly_operation_and_native_actual_maximum(self):
        result=self.n.execute(self.context)
        self.assertEqual(result['target'].maximum,100)
        self.assertEqual(result['added'],0)
        self.assertEqual(self.connection.script.exports_sync.submit.call_args.args[0]['operation'],'lifespan_inspect')
        self.assertEqual(self.acquire.call_args.args[0],(1234,99))
        self.connection.release.assert_called_once_with(self.n)

    def test_increase_returns_verified_native_lifespan_and_new_growth_identity(self):
        result=self.n.execute(self.context,self.shown,1)
        self.assertEqual((result['maximum'],result['target'].growth),(101,1.))
        self.assertEqual(self.connection.script.exports_sync.submit.call_count,1)
        self.assertEqual(self.n._ledger()['processes'][self.n.process_key]['status'],'verified')

    def test_success_crossing_growth_tool_bound_does_not_become_unknown(self):
        self.shown = target(maximum=1_000_000)
        result = self.n.execute(self.context, self.shown, 1)
        self.assertEqual(result['target'].maximum, 1_000_001)
        self.assertEqual(result['target'].growth, 1.)
        self.assertEqual(self.n._ledger()['processes'][self.n.process_key]['status'], 'verified')

    def test_rejected_before_modifier_is_safe_to_refresh(self):
        self.behavior='rejected'
        with self.assertRaises(Refused) as caught:self.n.execute(self.context,self.shown,1)
        self.assertNotIsInstance(caught.exception,UncertainWrite)
        self.n.require_ready()

    def test_connection_state_change_prevents_dispatch(self):
        self.a.prepare_native.side_effect=[self.descriptor,Refused('scene changed')]
        with self.assertRaises(Refused):self.n.execute(self.context,self.shown,1)
        self.connection.script.exports_sync.submit.assert_not_called()

    def test_post_dispatch_bad_results_block_all_repeat_operations(self):
        for behavior in ('rpc_error','wrong_age','wrong_growth','bad_max','nan_delta'):
            with self.subTest(behavior=behavior):
                self.n.journal.unlink(missing_ok=True)
                self.behavior=behavior
                with self.assertRaises(UncertainWrite):self.n.execute(self.context,self.shown,1)
                with self.assertRaises(Refused):self.n.require_ready()

    def test_foreign_player_after_success_is_uncertain(self):
        self.a.read_context.side_effect=lambda:context(replace(target(growth=1),identity=('new',)+self.shown.identity[1:]))
        with self.assertRaises(UncertainWrite):self.n.execute(self.context,self.shown,1)

    def test_post_dispatch_journal_failure_never_becomes_safe_refusal(self):
        original=self.n.record
        def record(event):
            if event['status'] in ('verified','unknown'):raise Refused('journal corruption')
            original(event)
        self.n.record=record
        with self.assertRaises(UncertainWrite):self.n.execute(self.context,self.shown,1)


class UiTests(unittest.TestCase):
    def setUp(self):
        from character_lifespan_ui import LifespanPanel
        from test_app import FakeVar,FakeWidget
        self.p=LifespanPanel.__new__(LifespanPanel)
        self.p.app=SimpleNamespace(busy=False,adapter=Mock(),root=Mock(),work=Mock(),status=FakeVar())
        self.p.adapter=Mock()
        self.p.state=dict(target=target(),can_edit=True,current_age=20,maximum=100)
        self.p.summary,self.p.note,self.p.input=FakeVar(),FakeVar(),FakeVar('1')
        self.p.detect_button,self.p.entry,self.p.add_button=FakeWidget(),FakeWidget(),FakeWidget()
        patch('character_lifespan_ui.native_calls_pending',return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_invalid_and_negative_input_never_launch_worker(self):
        self.p.input.set('-1')
        with patch('character_lifespan_ui.messagebox.showwarning') as warning:self.p.change()
        warning.assert_called_once();self.p.app.work.assert_not_called()

    def test_pinned_amount_and_no_unsafe_rollback(self):
        shown=self.p.state['target']
        self.p.change();job,success=self.p.app.work.call_args.args
        self.p.input.set('1000')
        self.p.adapter.increase.return_value=dict(target=replace(shown,maximum=101,growth=1),current_age=20,maximum=101,can_edit=True)
        success(job())
        self.p.adapter.increase.assert_called_once_with(shown,1)
        self.assertIn('100 → 101',self.p.note.get())
        self.assertIn('不提供回退',self.p.app.status.get())

    def test_uncertain_write_reaches_global_stop(self):
        self.p.adapter.increase.side_effect=UncertainWrite('lost')
        self.p.change();job,_=self.p.app.work.call_args.args
        with self.assertRaises(UncertainWrite):job()

    def test_rejection_discards_stale_age_and_target(self):
        self.p.adapter.increase.side_effect=Refused('age changed')
        self.p.change();job,success=self.p.app.work.call_args.args
        success(job())
        self.assertIsNone(self.p.state)
        self.assertEqual(self.p.add_button.options['state'],'disabled')


if __name__=='__main__':
    unittest.main()
