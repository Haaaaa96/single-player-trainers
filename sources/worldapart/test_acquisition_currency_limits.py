"""Offline checks for the reviewed currencies' one-call acquisition path.

All context, inventory, native dispatch and UI widgets are test doubles. These
tests never open a game process, broker, real Frida session or Tk window. The
dispatcher fixture's journals and epoch claims exist only in a temporary folder.
"""
import copy
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from acquisition_adapter import AcquisitionAdapter, AcquisitionLimitRefused, catalog_rows
from acquisition_catalog import (CURRENCY_ADD_MAXIMUM, CURRENCY_BALANCE_MAXIMUM,
                                 LARGE_CURRENCY_IDS, SPIRIT_STONE_ADD_MAXIMUM)
from acquisition_ui import AcquisitionPanel, add_quantity
from write_guard import Refused


CURRENCIES = sorted(LARGE_CURRENCY_IDS)
BAG_ITEM = 'Game.Model.Components.BagItem'


def add_limit(item_id):
    return SPIRIT_STONE_ADD_MAXIMUM if item_id == 50000 else CURRENCY_ADD_MAXIMUM


def definition(item_id=None, **changes):
    result = dict(id=CURRENCIES[0] if item_id is None else item_id,
                  names={'zh-Hans': '灵石'}, type_names={'zh-Hans': '货币'},
                  item_type_id=5, max_count_per_grid=CURRENCY_BALANCE_MAXIMUM,
                  auto_use=None, hide_in_bag=True)
    result.update(changes)
    return result


def currency_item(item_id=None, count=17_100, uid=1, **changes):
    obj = 0x10000 + uid * 0x100
    result = dict(uid=uid, item_id=CURRENCIES[0] if item_id is None else item_id,
                  count=count, object=obj, address=obj, count_address=obj + 0x14,
                  klass=0x22000, class_name=BAG_ITEM, is_equipped=False,
                  count_editable=True, size=4, type='Int32', slot=uid - 1)
    result.update(changes)
    return result


def inventory(items, slots=None, **changes):
    anchors = []
    if slots is not None:
        anchors.append(dict(address=0x44000, size=4, label='Items._size',
                            expected_hex=slots.to_bytes(4, 'little', signed=True).hex()))
    result = dict(pid=12345, process_creation_filetime=987654321,
                  player=0x1000, bag=0x2000, world=0x3000, store=0x4000,
                  items=items, anchors=anchors, diagnostics=[])
    result.update(changes)
    return result


def proof():
    return dict(tables='0x5000', tables_class='0x6000', config_object='0x7000',
                row_index=3, anchors=[dict(address=0x8000, size=4,
                    expected_hex='01000000', label='reviewed currency config')])


class CurrencyCatalogueLimitTests(unittest.TestCase):
    def test_stone_accepts_hundred_million_and_contributions_keep_one_million(self):
        self.assertEqual(set(CURRENCIES), {50000, 50001, 50002})
        self.assertEqual(CURRENCY_ADD_MAXIMUM, 1_000_000)
        self.assertEqual(SPIRIT_STONE_ADD_MAXIMUM, 100_000_000)
        self.assertEqual(CURRENCY_BALANCE_MAXIMUM, 999_999_999)
        for item_id in CURRENCIES:
            with self.subTest(item_id=item_id):
                row = catalog_rows({'items': [definition(item_id)]})[0]
                self.assertTrue(row['can_add'])
                self.assertEqual(row['max_quantity'], add_limit(item_id))
                self.assertEqual(row['balance_maximum'], CURRENCY_BALANCE_MAXIMUM)

    def test_currency_per_call_limit_respects_smaller_configuration(self):
        for item_id in CURRENCIES:
            maximum = add_limit(item_id)
            for cap in (1, 500, maximum - 1, maximum, maximum + 1, 2_147_483_647):
                with self.subTest(item_id=item_id, cap=cap):
                    row = catalog_rows({'items': [definition(item_id, max_count_per_grid=cap)]})[0]
                    self.assertEqual(row['max_quantity'], min(cap, maximum))
                    self.assertEqual(row['balance_maximum'], min(cap, CURRENCY_BALANCE_MAXIMUM))

    def test_name_or_currency_category_alone_never_grants_million_limit(self):
        for row in (definition(51000),
                    definition(230002, item_type_id=23, hide_in_bag=False),
                    definition(CURRENCIES[0], item_type_id=9, hide_in_bag=False)):
            with self.subTest(row=row):
                result = catalog_rows({'items': [row]})[0]
                self.assertTrue(result['can_add'])
                self.assertEqual(result['max_quantity'], 999)
                self.assertIsNone(result['balance_maximum'])

    def test_auto_use_currency_is_blocked_but_nullable_false_is_allowed(self):
        for auto_use in (True, False, None):
            with self.subTest(auto_use=auto_use):
                row = catalog_rows({'items': [definition(auto_use=auto_use)]})[0]
                self.assertEqual(row['can_add'], auto_use is not True)
                if auto_use is True:
                    self.assertTrue(row['reason'])
                else:
                    self.assertEqual(row['max_quantity'], SPIRIT_STONE_ADD_MAXIMUM)

    def test_ordinary_and_independent_instance_limits_are_unchanged(self):
        ordinary = catalog_rows({'items': [definition(100, item_type_id=9,
            hide_in_bag=False, max_count_per_grid=99)]})[0]
        special = catalog_rows({'items': [definition(101, item_type_id=95,
            hide_in_bag=False, max_count_per_grid=1)]})[0]
        self.assertEqual(ordinary['max_quantity'], 999)
        self.assertEqual(special['max_quantity'], 256)
        self.assertTrue(special['may_split_single'])


class CurrencyAcquisitionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.a = AcquisitionAdapter.__new__(AcquisitionAdapter)
        self.a.game = Mock()
        self.a._lock = threading.Lock()
        self.a.blocked = False
        self.a.native_block_reason = None
        self.a._record = Mock()
        self.a._dispatch = Mock(return_value=dict(token='offline', operation='add',
                                                 status='completed', called=True))
        self.a._current = Mock()
        self.a._catalog_data = {'currency_proofs': {i: proof() for i in CURRENCIES}}
        self.a.catalog = Mock(return_value=catalog_rows(
            {'items': [definition(i) for i in CURRENCIES]}))
        self.existing = Mock(return_value=None)
        self.guard = Mock(return_value={'anchors': []})
        modules = patch.dict('sys.modules', {
            'acquisition_context': SimpleNamespace(require_safe_acquisition_context=self.guard),
            'acquisition_existing': SimpleNamespace(try_add_existing=self.existing)})
        modules.start()
        self.addCleanup(modules.stop)

    def prepare(self, before, after=None):
        self.a._dispatch.reset_mock()
        self.a._dispatch.return_value = dict(token='offline', operation='add',
                                             status='completed', called=True)
        self.a._current.reset_mock()
        self.a._current.side_effect = [before, after] if after is not None else None
        self.a._current.return_value = before
        self.existing.reset_mock()
        self.guard.reset_mock()

    def test_all_three_owned_and_new_currencies_use_one_native_call(self):
        for item_id in CURRENCIES:
            maximum = add_limit(item_id)
            for before_total in (0, 17_100, 1_000_001, CURRENCY_BALANCE_MAXIMUM - maximum):
                with self.subTest(item_id=item_id, before=before_total):
                    before = inventory([currency_item(item_id, before_total)] if before_total else [])
                    after = inventory([currency_item(item_id, before_total + maximum)])
                    self.prepare(before, after)
                    result = self.a.add(item_id, maximum)
                    self.assertTrue(result['verified'])
                    self.assertEqual((result['before'], result['after']),
                                     (before_total, before_total + maximum))
                    self.assertEqual(result['new_uids'], [] if before_total else [1])
                    self.existing.assert_not_called()
                    self.a._dispatch.assert_called_once()
                    raw, operation, extra = self.a._dispatch.call_args.args
                    self.assertIs(raw, before)
                    self.assertEqual(operation, 'add')
                    self.assertEqual((extra['item_id'], extra['quantity']),
                                     (item_id, maximum))
                    self.assertEqual(extra['currency_proof']['before'], before_total)
                    self.assertEqual(extra['currency_proof']['maximum'], CURRENCY_BALANCE_MAXIMUM)
                    for key, value in proof().items():
                        self.assertEqual(extra['currency_proof'][key], value)
                    self.assertNotIn('before', self.a._catalog_data['currency_proofs'][item_id])

    def test_over_per_currency_limit_or_noninteger_quantity_never_reaches_game(self):
        for item_id in CURRENCIES:
            for quantity in (add_limit(item_id) + 1, 0, -1):
                with self.subTest(item_id=item_id, quantity=quantity):
                    with self.assertRaises(AcquisitionLimitRefused) as raised:
                        self.a.add(item_id, quantity)
                    self.assertFalse(raised.exception.write_attempted)
                    self.assertFalse(self.a.blocked)
            for quantity in (True, 1.5, '100000000'):
                with self.subTest(item_id=item_id, quantity=quantity), self.assertRaises(Refused):
                    self.a.add(item_id, quantity)
        self.guard.assert_not_called()
        self.a._current.assert_not_called()
        self.existing.assert_not_called()
        self.a._dispatch.assert_not_called()

    def test_fresh_catalogue_downgrade_refuses_before_dispatch(self):
        self.a.catalog.return_value = catalog_rows({'items': [definition(max_count_per_grid=999)]})
        with self.assertRaises(AcquisitionLimitRefused):
            self.a.add(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)
        self.a.catalog.assert_called_once_with(refresh=True)
        self.a._current.assert_not_called()
        self.existing.assert_not_called()
        self.a._dispatch.assert_not_called()

    def test_balance_and_int32_overflow_are_refused_before_dispatch(self):
        for count, quantity in ((CURRENCY_BALANCE_MAXIMUM, 1),
                                (CURRENCY_BALANCE_MAXIMUM - 1, 2),
                                (2_147_483_647, SPIRIT_STONE_ADD_MAXIMUM), (-1, 1)):
            with self.subTest(count=count, quantity=quantity):
                self.prepare(inventory([currency_item(count=count)]))
                with self.assertRaises(Refused):
                    self.a.add(CURRENCIES[0], quantity)
                self.a._dispatch.assert_not_called()
                self.existing.assert_not_called()

    def test_total_limit_rejection_is_known_not_called_and_allows_corrected_request(self):
        before = CURRENCY_BALANCE_MAXIMUM - 2
        self.prepare(inventory([currency_item(count=before)]))
        with self.assertRaises(AcquisitionLimitRefused) as raised:
            self.a.add(50000, 3)
        self.assertFalse(raised.exception.write_attempted)
        self.assertIn(f'{before:,}', str(raised.exception))
        self.assertIn(f'{CURRENCY_BALANCE_MAXIMUM:,}', str(raised.exception))
        self.assertIn('最多可添加 2', str(raised.exception))
        self.assertFalse(self.a.blocked)
        self.a._dispatch.assert_not_called()
        self.a._record.assert_not_called()
        self.prepare(inventory([currency_item(count=before)]),
                     inventory([currency_item(count=CURRENCY_BALANCE_MAXIMUM)]))
        self.assertEqual(self.a.add(50000, 2)['after'], CURRENCY_BALANCE_MAXIMUM)
        self.a._dispatch.assert_called_once()

    def test_all_currency_hundred_million_boundary_totals_never_exceed_cap(self):
        for item_id in CURRENCIES:
            maximum = add_limit(item_id)
            for before, quantity in ((CURRENCY_BALANCE_MAXIMUM - maximum + 1, maximum),
                                     (CURRENCY_BALANCE_MAXIMUM, 1),
                                     (1_000_000_000, 1)):
                with self.subTest(item_id=item_id, before=before, quantity=quantity):
                    self.prepare(inventory([currency_item(item_id, before)]))
                    with self.assertRaises(AcquisitionLimitRefused):
                        self.a.add(item_id, quantity)
                    self.assertFalse(self.a.blocked)
                    self.a._dispatch.assert_not_called()
                    self.existing.assert_not_called()

    def test_configuration_cap_is_respected_at_exact_boundary(self):
        for configured in (80_000, 2_147_483_647):
            with self.subTest(configured=configured):
                cap = min(configured, CURRENCY_BALANCE_MAXIMUM)
                self.a.catalog.return_value = catalog_rows(
                    {'items': [definition(max_count_per_grid=configured)]})
                self.prepare(inventory([currency_item(count=cap - 1)]),
                             inventory([currency_item(count=cap)]))
                self.assertEqual(self.a.add(CURRENCIES[0], 1)['after'], cap)
                self.assertEqual(self.a._dispatch.call_args.args[2]['currency_proof']['maximum'], cap)
                self.prepare(inventory([currency_item(count=cap)]))
                with self.assertRaises(AcquisitionLimitRefused):
                    self.a.add(CURRENCIES[0], 1)
                self.a._dispatch.assert_not_called()

    def test_owned_currency_needs_no_new_slot_and_new_currency_needs_one(self):
        for owned, slots, allowed in ((True, 4000, True), (False, 3999, True), (False, 4000, False)):
            with self.subTest(owned=owned, slots=slots):
                items = [currency_item(count=10)] if owned else []
                count = 10 if owned else 0
                before = inventory(items, slots=slots)
                after = inventory([currency_item(count=count + SPIRIT_STONE_ADD_MAXIMUM)],
                                  slots=slots + (not owned))
                self.prepare(before, after)
                if allowed:
                    self.assertTrue(self.a.add(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)['verified'])
                    self.a._dispatch.assert_called_once()
                else:
                    with self.assertRaises(Refused):
                        self.a.add(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)
                    self.a._dispatch.assert_not_called()

    def test_ambiguous_specialized_or_equipped_currency_refused(self):
        cases = [[currency_item(), currency_item(uid=2)],
                 [currency_item(class_name='Game.Model.Components.PillBagItem')],
                 [currency_item(is_equipped=True)],
                 [currency_item(class_name='Game.Model.Components.GongfaBagItem')]]
        for items in cases:
            with self.subTest(items=items):
                self.prepare(inventory(items))
                with self.assertRaises(Refused):
                    self.a.add(CURRENCIES[0], 1)
                self.a._dispatch.assert_not_called()
                self.existing.assert_not_called()

    def test_unsupported_inventory_diagnostic_refuses_whole_native_call(self):
        self.prepare(inventory([], diagnostics=[{'reason': 'unsupported_entry'}]))
        with self.assertRaises(Refused):
            self.a.add(CURRENCIES[0], 1)
        self.a._dispatch.assert_not_called()

    def test_missing_or_empty_configuration_proof_refuses(self):
        cases = [{}, {'currency_proofs': {}},
                 {'currency_proofs': {CURRENCIES[0]: dict(proof(), anchors=[])}}]
        for data in cases:
            with self.subTest(data=data):
                self.prepare(inventory([]))
                self.a._catalog_data = data
                with self.assertRaises(Refused):
                    self.a.add(CURRENCIES[0], 1)
                self.a._dispatch.assert_not_called()
                self.existing.assert_not_called()

    def test_battle_gate_runs_before_inventory_or_any_write(self):
        self.guard.side_effect = Refused('战斗中不添加')
        with self.assertRaisesRegex(Refused, '战斗'):
            self.a.add(CURRENCIES[0], CURRENCY_ADD_MAXIMUM)
        self.a._current.assert_not_called()
        self.existing.assert_not_called()
        self.a._dispatch.assert_not_called()

    def test_context_is_checked_before_reading_owned_currency(self):
        calls = Mock()
        calls.attach_mock(self.guard, 'guard')
        calls.attach_mock(self.a._current, 'current')
        self.prepare(inventory([currency_item(count=10)]), inventory([currency_item(count=11)]))
        self.a.add(CURRENCIES[0], 1)
        self.assertEqual([call[0] for call in calls.mock_calls[:2]], ['guard', 'current'])

    def test_blocked_native_never_falls_back_to_existing_stack(self):
        self.existing.return_value = {'status': 'verified', 'before': 1, 'after': 2}
        self.a.native_block_reason = '原生连接已停用'
        with self.assertRaisesRegex(Refused, '原生连接已停用'):
            self.a.add(CURRENCIES[0], 1)
        self.existing.assert_not_called()
        self.a._dispatch.assert_not_called()
        self.a.native_block_reason = None
        self.a.blocked = True
        with self.assertRaises(Refused):
            self.a.add(CURRENCIES[0], 1)
        self.existing.assert_not_called()
        self.a._dispatch.assert_not_called()

    def test_wrong_readback_marks_unknown_and_never_retries(self):
        self.prepare(inventory([currency_item(count=5)]),
                     inventory([currency_item(count=SPIRIT_STONE_ADD_MAXIMUM)]))
        with self.assertRaises(Refused) as raised:
            self.a.add(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)
        self.assertNotIsInstance(raised.exception, AcquisitionLimitRefused)
        self.assertTrue(self.a.blocked)
        self.assertEqual(self.a._record.call_args.args[0]['status'], 'unknown')
        with self.assertRaises(Refused):
            self.a.add(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)
        self.a._dispatch.assert_called_once()
        self.existing.assert_not_called()

    def test_unknown_dispatch_result_is_not_reclassified_as_a_safe_limit_refusal(self):
        self.prepare(inventory([currency_item(count=17_100)]))
        failure = Refused('获取结果不确定，请不要重试')
        self.a._dispatch.side_effect = failure
        with self.assertRaises(Refused) as raised:
            self.a.add(50000, SPIRIT_STONE_ADD_MAXIMUM)
        self.assertIs(raised.exception, failure)
        self.assertNotIsInstance(raised.exception, AcquisitionLimitRefused)
        self.a._dispatch.assert_called_once()
        self.existing.assert_not_called()

    def test_ordinary_existing_path_and_slot_budget_are_not_relaxed(self):
        self.a.catalog.return_value = catalog_rows({'items': [definition(100,
            item_type_id=9, hide_in_bag=False, max_count_per_grid=999)]})
        event = {'status': 'verified', 'before': 10, 'after': 20}
        self.existing.return_value = event
        self.assertIs(self.a.add(100, 10), event)
        self.existing.assert_called_once_with(self.a.game, 100, 10, context_anchors=[])
        self.a._dispatch.assert_not_called()
        self.existing.return_value = None
        self.prepare(inventory([], slots=3500))
        with self.assertRaises(Refused):
            self.a.add(100, 999)
        self.a._dispatch.assert_not_called()


class CurrencyAcquisitionUiTests(unittest.TestCase):
    def test_input_is_added_quantity_for_all_three_and_keeps_ordinary_limit(self):
        for item_id in CURRENCIES:
            row = catalog_rows({'items': [definition(item_id)]})[0]
            with self.subTest(item_id=item_id):
                self.assertEqual(add_quantity(row, str(add_limit(item_id))), add_limit(item_id))
                with self.assertRaises(Refused):
                    add_quantity(row, str(add_limit(item_id) + 1))
        ordinary = catalog_rows({'items': [definition(100, item_type_id=9, hide_in_bag=False)]})[0]
        self.assertEqual(add_quantity(ordinary, '999'), 999)
        with self.assertRaises(Refused):
            add_quantity(ordinary, '1000')

    def panel(self):
        panel = AcquisitionPanel.__new__(AcquisitionPanel)
        panel.app = Mock()
        panel.app.busy = False
        panel.backend = Mock()
        panel.detail = Mock()
        panel.quantity = Mock()
        panel.quantity.get.return_value = '100000000'
        panel.selected = Mock(return_value=catalog_rows({'items': [definition()]})[0])
        return panel

    def test_selection_explains_increment_and_hundred_million_range(self):
        panel = self.panel()
        panel.detail = Mock()
        panel.update_enabled = Mock()
        panel.select()
        text = panel.detail.set.call_args.args[0]
        self.assertIn('100000000', text.replace(',', ''))
        self.assertRegex(text, '新增|添加')
        self.assertIn('余额', text)
        panel.quantity.set.assert_called_once_with('1')

    def test_add_job_sends_one_increment_without_converting_it_to_balance(self):
        panel = self.panel()
        panel.backend.add.return_value = {'verified': True, 'before': 17100, 'after': 100017100}
        panel.add()
        panel.app.work.assert_called_once()
        job, success = panel.app.work.call_args.args
        success(job())
        panel.backend.add.assert_called_once_with(CURRENCIES[0], SPIRIT_STONE_ADD_MAXIMUM)
        panel.app.adapter.snapshot.assert_called_once()
        self.assertIn('100000000', panel.app.render.call_args.args[1].replace(',', ''))


class CurrencyDispatchIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the fixture, not its TestCase inheritance/discovery. Its
        # explicit local-acquire patch uses Mock Frida and a temporary epoch
        # directory; the real broker entry point is never reached.
        import test_acquisition_adapter as fixtures
        self.fixture = fixtures.DispatchSafetyTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.session = self.fixture.frida.attach.return_value
        self.script = self.session.create_script.return_value
        self.script.exports_sync.reset.return_value = {'status': 'idle'}

        def complete(request):
            callback = self.script.on.call_args.args[1]
            callback(dict(type='send', payload=dict(token=request['token'],
                status='completed', called=True)), None)

        self.script.exports_sync.submit.side_effect = complete
        methods = {
            'add': ((0x100, 0x200), 0x06015191, 0xE9BDD0, 5),
            'currency_stack': ((0x300, 0x400), 0x0601519F, 0xEA0FD0, 2),
        }
        self.fixture.a._method = Mock(side_effect=lambda raw, operation: methods[operation])

    def currency_extra(self, before=0):
        return dict(item_id=CURRENCIES[0], quantity=SPIRIT_STONE_ADD_MAXIMUM,
                    currency_proof=dict(proof(), before=before,
                                        maximum=CURRENCY_BALANCE_MAXIMUM))

    def test_currency_proof_and_count_join_refreshed_context_anchors(self):
        f = self.fixture
        live_item = currency_item(count=17_100)
        old_anchor = dict(address=0xA000, size=4, expected_hex='01000000', label='old inventory')
        fresh_anchor = dict(address=0xA008, size=4, expected_hex='02000000', label='fresh inventory')
        f.raw.update(items=[live_item], anchors=[old_anchor])
        fresh = dict(f.raw, anchors=[fresh_anchor])
        f.a._current.return_value = fresh
        extra = self.currency_extra(before=17_100)
        result = f.a._dispatch(f.raw, 'add', extra)
        self.assertEqual(result['status'], 'completed')
        self.script.exports_sync.submit.assert_called_once()
        request = self.script.exports_sync.submit.call_args.args[0]
        expected = [dict(fresh_anchor, address=hex(fresh_anchor['address'])),
                    *[dict(anchor, address=hex(anchor['address'])) for anchor in f.context['anchors']],
                    dict(address=hex(live_item['count_address']), size=4,
                         expected_hex=(17_100).to_bytes(4, 'little', signed=True).hex(),
                         label='inventory count 1'),
                    *[dict(anchor, address=hex(anchor['address'])) for anchor in proof()['anchors']]]
        self.assertEqual(request['anchors'], expected)
        self.assertEqual(request['currency_proof'],
                         dict(extra['currency_proof'], stack_method='0x300'))
        self.assertEqual(request['method_info'], '0x100')
        self.assertNotIn('stack_method', extra['currency_proof'])
        f.a._method.assert_has_calls([call(f.raw, 'add'), call(f.raw, 'currency_stack')])
        self.assertEqual(f.guard.call_count, 2)

    def test_ordinary_currency_ordinary_reuses_session_and_resets_each_token(self):
        f = self.fixture
        payloads = [dict(item_id=180000, quantity=10), self.currency_extra(),
                    dict(item_id=100, quantity=10)]
        tokens = []
        for index, payload in enumerate(payloads):
            adapter = f.a if index == 0 else AcquisitionAdapter(f.game)
            adapter._method = f.a._method
            adapter._current = f.a._current
            result = adapter._dispatch(f.raw, 'add', payload)
            self.assertEqual(result['status'], 'completed')
            tokens.append(result['token'])
            # The outer add workflow normally verifies and journals this state
            # before a GUI releases/reopens its adapter.
            adapter._record(dict(result, status='verified'))
        self.assertEqual(len(set(tokens)), 3)
        f.frida.attach.assert_called_once_with(f.raw['pid'])
        self.session.create_script.assert_called_once()
        self.script.load.assert_called_once()
        self.script.exports_sync.reset.assert_has_calls([call(tokens[0]), call(tokens[1])])
        self.assertEqual(self.script.exports_sync.reset.call_count, 2)
        self.assertEqual(self.script.exports_sync.submit.call_count, 3)
        sent = [entry.args[0] for entry in self.script.exports_sync.submit.call_args_list]
        self.assertNotIn('currency_proof', sent[0])
        self.assertEqual(sent[1]['currency_proof']['stack_method'], '0x300')
        self.assertNotIn('currency_proof', sent[2])
        self.script.unload.assert_not_called()
        self.session.detach.assert_not_called()

    def test_currency_context_identity_or_anchor_change_never_submits(self):
        f = self.fixture
        for change in ('identity', 'anchor'):
            with self.subTest(change=change):
                later = copy.deepcopy(f.context)
                if change == 'identity':
                    later['identity']['space_handler'] += 1
                else:
                    later['anchors'][0]['expected_hex'] = '01000000'
                f.guard.side_effect = [f.context, later]
                with self.assertRaisesRegex(Refused, '场景发生变化'):
                    f.a._dispatch(f.raw, 'add', self.currency_extra())
                self.script.exports_sync.submit.assert_not_called()
                self.assertFalse(f.a._native_inflight)
                self.assertFalse(f.a.blocked)
        f.frida.attach.assert_called_once()
        self.script.unload.assert_not_called()
        self.session.detach.assert_not_called()


if __name__ == '__main__':
    unittest.main()
