import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from acquisition_adapter import (AcquisitionAdapter, catalog_rows,
                                 require_no_unmanaged_agent, native_calls_pending)
from write_guard import Refused, UncertainWrite


def row(**changes):
    value = dict(id=100, names={'zh-Hans': '材料'}, type_names={'zh-Hans': '材料'},
                 item_type_id=9, max_count_per_grid=999, auto_use=False)
    value.update(changes)
    return value


def snapshot(items):
    return dict(player=10, bag=20, world=30, store=40, items=items)


def item(uid=1, item_id=100, count=1):
    return dict(uid=uid, item_id=item_id, count=count, object=500 + uid)


class CatalogTests(unittest.TestCase):
    def test_999_is_native_catalog_limit(self):
        r = catalog_rows({'items': [row()]})[0]
        self.assertEqual(r['stack_limit'], 999)
        self.assertEqual(r['max_quantity'], 999)
        self.assertTrue(r['can_add'])

    def test_99_stack_still_allows_many_split_stacks(self):
        r = catalog_rows({'items': [row(max_count_per_grid=99)]})[0]
        self.assertEqual(r['max_quantity'], 999)
        self.assertEqual(r['stack_limit'], 99)

    def test_auto_use_is_visible_with_clear_reason(self):
        r = catalog_rows({'items': [row(auto_use=True)]})[0]
        self.assertFalse(r['can_add'])
        self.assertTrue(r['reason'])

    def test_hidden_system_rejected_but_currency_allowed(self):
        rows = catalog_rows({'items': [row(item_type_id=7, hide_in_bag=True), row(item_type_id=5, hide_in_bag=True)]})
        self.assertFalse(rows[0]['can_add'])
        self.assertTrue(rows[1]['can_add'])

    def test_book_uses_game_initialization_and_bounded_slots(self):
        r = catalog_rows({'items': [row(item_type_id=95, auto_use=None)]})[0]
        self.assertTrue(r['can_add'])
        self.assertTrue(r['may_split_single'])
        self.assertEqual(r['max_quantity'], 256)

    def test_placeholder_book_visible_but_disabled(self):
        r = catalog_rows({'items': [row(names={'zh-Hans': '未知功法'})]})[0]
        self.assertFalse(r['can_add'])

    def test_placeholder_families_disabled_but_named_quest_remains(self):
        for name in ('未知法宝器胚', '未知法宝', '未知的丹药', '未知的物品'):
            with self.subTest(name=name):
                r = catalog_rows({'items': [row(names={'zh-Hans': name})]})[0]
                self.assertFalse(r['can_add'])
                self.assertTrue(r['reason'])
        r = catalog_rows({'items': [row(names={'zh-Hans': '未知罗盘'}, item_type_id=4)]})[0]
        self.assertTrue(r['can_add'])


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = AcquisitionAdapter.__new__(AcquisitionAdapter)
        self.a.game = Mock()
        import threading
        self.a._lock = threading.Lock()
        self.a.blocked = False
        self.a.journal = Path(self.tmp.name) / 'journal.json'
        self.a.catalog = Mock(return_value=catalog_rows({'items': [row()]}))
        self.a._record = Mock()
        self.existing = Mock(return_value=None)
        self.context_guard = Mock(return_value={'anchors': []})
        self.modules = patch.dict('sys.modules', {
            'acquisition_context': SimpleNamespace(require_safe_acquisition_context=self.context_guard),
            'acquisition_existing': SimpleNamespace(try_add_existing=self.existing)})
        self.modules.start()

    def tearDown(self):
        self.modules.stop()
        self.tmp.cleanup()

    def test_new_item_verified_and_new_uid_returned(self):
        self.a._current = Mock(side_effect=[snapshot([]), snapshot([item()])])
        self.a._dispatch = Mock(return_value=dict(token='test', operation='add', item_id=100, quantity=1))
        result = self.a.add(100, 1)
        self.assertTrue(result['verified'])
        self.assertEqual(result['before'], 0)
        self.assertEqual(result['after'], 1)
        self.assertEqual(result['new_uids'], [1])
        self.a._dispatch.assert_called_once()

    def test_999_quantity_uses_native_split_and_verifies_total(self):
        self.a._current = Mock(side_effect=[snapshot([item(count=5)]), snapshot([item(count=999), item(uid=2, count=5)])])
        self.a._dispatch = Mock(return_value=dict(token='test', operation='add', item_id=100, quantity=999))
        result = self.a.add(100, 999)
        self.assertEqual(result['after'], 1004)

    def test_wrong_total_blocks_and_never_retries(self):
        self.a._current = Mock(side_effect=[snapshot([]), snapshot([])])
        self.a._dispatch = Mock(return_value=dict(token='test', item_id=100, quantity=1))
        with self.assertRaises(Refused): self.a.add(100, 1)
        self.assertTrue(self.a.blocked)
        with self.assertRaises(Refused): self.a.add(100, 1)
        self.a._dispatch.assert_called_once()

    def test_changed_character_blocks(self):
        after = snapshot([item()]); after['player'] = 99
        self.a._current = Mock(side_effect=[snapshot([]), after])
        self.a._dispatch = Mock(return_value=dict(token='test', item_id=100, quantity=1))
        with self.assertRaises(Refused): self.a.add(100, 1)
        self.assertTrue(self.a.blocked)

    def test_readback_exception_after_call_blocks(self):
        self.a._current = Mock(side_effect=[snapshot([]), OSError('read lost')])
        self.a._dispatch = Mock(return_value=dict(token='test', item_id=100, quantity=1))
        with self.assertRaises(OSError): self.a.add(100, 1)
        self.assertTrue(self.a.blocked)

    def test_log_failure_after_successful_call_blocks(self):
        self.a._current = Mock(side_effect=[snapshot([]), snapshot([item()])])
        self.a._dispatch = Mock(return_value=dict(token='test', item_id=100, quantity=1))
        self.a._record.side_effect = OSError('disk full')
        with self.assertRaises(OSError): self.a.add(100, 1)
        self.assertTrue(self.a.blocked)

    def test_limits_before_any_dispatch(self):
        self.a._current = Mock()
        for bad in [0, -1, 1000, True, 1.5, '1']:
            with self.subTest(bad=bad), self.assertRaises(Refused): self.a.add(100, bad)
        self.a._current.assert_not_called()

    def test_missing_or_disabled_item_refused(self):
        with self.assertRaises(Refused): self.a.add(99999, 1)
        self.a.catalog.return_value = catalog_rows({'items': [row(auto_use=True)]})
        with self.assertRaises(Refused): self.a.add(100, 1)

    def test_cleanup_exact_new_uid(self):
        addition = dict(status='verified', quantity=1, before=0, new_uids=[1], item_id=100, player=10, bag=20)
        self.a._current = Mock(side_effect=[snapshot([item()]), snapshot([])])
        self.a._dispatch = Mock(return_value=dict(token='clean'))
        result = self.a.remove_test_addition(addition)
        self.assertTrue(result['verified'])
        self.assertEqual(self.a._dispatch.call_args.args[1], 'remove_test_uid')
        self.assertEqual(self.a._dispatch.call_args.args[2]['uid'], '1')

    def test_cleanup_rejects_old_stack_or_altered_item(self):
        addition = dict(status='verified', quantity=1, before=5, new_uids=[], item_id=100, player=10, bag=20)
        with self.assertRaises(Refused): self.a.remove_test_addition(addition)
        addition.update(before=0, new_uids=[1])
        self.a._current = Mock(return_value=snapshot([item(count=2)]))
        with self.assertRaises(Refused): self.a.remove_test_addition(addition)

    def test_cleanup_readback_failure_also_blocks(self):
        addition = dict(status='verified', quantity=1, before=0, new_uids=[1], item_id=100, player=10, bag=20)
        self.a._current = Mock(side_effect=[snapshot([item()]), OSError('read lost')])
        self.a._dispatch = Mock(return_value=dict(token='test', item_id=100, quantity=1))
        with self.assertRaises(OSError): self.a.remove_test_addition(addition)
        self.assertTrue(self.a.blocked)

    def test_existing_stack_can_work_while_native_route_is_blocked(self):
        self.a.native_block_reason = 'native connection disabled'
        result = dict(status='verified', route='existing_stack', before=1, after=11)
        self.existing.return_value = result
        self.a._dispatch = Mock()
        self.assertIs(self.a.add(100, 10), result)
        self.a._dispatch.assert_not_called()
        self.a._record.assert_called_once_with(result)
        self.existing.assert_called_once_with(self.a.game, 100, 10, context_anchors=[])

    def test_missing_existing_stack_respects_native_block(self):
        self.a.native_block_reason = 'native connection disabled'
        self.a._dispatch = Mock()
        with self.assertRaisesRegex(Refused, 'native connection disabled'):
            self.a.add(100, 10)
        self.a._dispatch.assert_not_called()

    def test_existing_write_uncertainty_blocks_without_native_fallback(self):
        self.existing.side_effect = UncertainWrite('write readback failed')
        self.a._dispatch = Mock()
        with self.assertRaises(UncertainWrite):
            self.a.add(100, 10)
        self.assertTrue(self.a.blocked)
        self.assertEqual(self.a._record.call_args.args[0]['status'], 'unknown')
        self.a._dispatch.assert_not_called()
        with self.assertRaises(Refused):
            self.a.add(100, 10)
        self.existing.assert_called_once()

    def test_global_uncertainty_blocks_even_existing_path(self):
        self.a.blocked = True
        with self.assertRaises(Refused):
            self.a.add(100, 10)
        self.existing.assert_not_called()

    def test_existing_refusal_never_falls_back_to_injection(self):
        self.existing.side_effect = Refused('stack changed')
        self.a._dispatch = Mock()
        with self.assertRaisesRegex(Refused, 'stack changed'):
            self.a.add(100, 10)
        self.a._dispatch.assert_not_called()

    def test_existing_route_requires_safe_context_before_write(self):
        self.context_guard.side_effect = Refused('当前战斗')
        with self.assertRaisesRegex(Refused, '当前战斗'):
            self.a.add(100, 10)
        self.existing.assert_not_called()


class DispatchSafetyTests(unittest.TestCase):
    """Exercise the real dispatch lifecycle with no Frida or game attached."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'acquisition_bridge.js').write_text('// offline fixture', encoding='utf8')
        self.here = patch('acquisition_adapter.HERE', self.root)
        self.here.start()
        self.runtime = patch('acquisition_adapter.initialize_runtime', return_value=self.root / 'logs')
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.connections = patch.dict('native_acquisition_session._CONNECTIONS', {}, clear=True)
        self.connections.start()
        # This fixture exercises the in-host Frida lifecycle. Route explicitly
        # to that mocked implementation; never spawn a real broker subprocess.
        from native_acquisition_session import _acquire_local_connection
        local_acquire = patch('native_acquisition_session.acquire_connection', _acquire_local_connection)
        local_acquire.start()
        self.addCleanup(local_acquire.stop)
        self.agent_check = patch('acquisition_adapter.require_no_unmanaged_agent')
        self.agent_check.start()
        self.game = Mock()
        self.a = AcquisitionAdapter(self.game)
        self.raw = dict(pid=23248, process_creation_filetime=123456,
                        player=10, bag=20, world=30, store=40, items=[], anchors=[])
        self.a._method = Mock(return_value=((100, 200), 0x06015191, 0xE9BDD0, 5))
        self.a._current = Mock(return_value=self.raw)
        self.context = dict(status='safe_nonbattle', identity={'space_handler': 600},
                            anchors=[dict(address=700, size=4, expected_hex='00000000',
                                          label='battle state')])
        self.guard = Mock(return_value=self.context)
        self.frida = SimpleNamespace(__version__='17.7.3', attach=Mock())
        self.existing = Mock(return_value=None)
        self.modules = patch.dict('sys.modules', {
            'frida': self.frida,
            'acquisition_context': SimpleNamespace(require_safe_acquisition_context=self.guard),
            'acquisition_existing': SimpleNamespace(try_add_existing=self.existing)})
        self.modules.start()

    def tearDown(self):
        self.agent_check.stop()
        self.connections.stop()
        self.modules.stop()
        self.here.stop()
        self.tmp.cleanup()

    def dispatch(self):
        return self.a._dispatch(self.raw, 'add', dict(item_id=180000, quantity=10))

    def test_attach_failure_records_stage_and_persistently_blocks_retry(self):
        self.frida.attach.side_effect = RuntimeError('process terminated during injection')
        with self.assertRaisesRegex(Refused, '本次添加尚未调用'):
            self.dispatch()
        state = json.loads(self.a.journal.read_text(encoding='utf8'))
        self.assertEqual(state['status'], 'attach_failed')
        self.assertEqual(state['stage'], 'attach')
        self.assertFalse(state['called'])
        self.assertEqual(state['pid'], 23248)
        self.assertEqual(state['process_creation_filetime'], 123456)
        self.assertEqual(state['error_type'], 'RuntimeError')
        self.assertEqual(state['error'], 'process terminated during injection')
        self.assertEqual(state['native_block_identity'],
                         {'pid': 23248, 'process_creation_filetime': 123456})
        self.assertFalse(self.a.blocked)
        self.assertTrue(self.a.native_block_reason)
        self.a._current.assert_not_called()
        with self.assertRaises(Refused):
            self.dispatch()
        reopened = AcquisitionAdapter(self.game)
        self.assertFalse(reopened.blocked)
        self.assertTrue(reopened.native_block_reason)
        with self.assertRaisesRegex(Refused, '不会自动重试'):
            reopened._dispatch(self.raw, 'add', dict(item_id=180000, quantity=10))
        self.frida.attach.assert_called_once_with(23248)

    def test_logging_failure_retains_durable_attaching_block(self):
        real_record = self.a._record
        def record(event):
            if event['status'] == 'attach_failed':
                raise OSError('disk full')
            return real_record(event)
        self.a._record = record
        self.frida.attach.side_effect = RuntimeError('injection failed')
        with self.assertRaisesRegex(Refused, '连接组件加载失败'):
            self.dispatch()
        state = json.loads(self.a.journal.read_text(encoding='utf8'))
        self.assertEqual(state['status'], 'attaching')
        self.assertFalse(state['called'])
        self.assertTrue(AcquisitionAdapter(self.game).native_block_reason)

    def test_existing_success_cannot_clear_durable_native_failure(self):
        self.a.native_block_reason = 'native connection disabled'
        self.a._record(dict(status='verified', route='existing_stack', before=1, after=11))
        reopened = AcquisitionAdapter(self.game)
        self.assertFalse(reopened.blocked)
        self.assertEqual(reopened.native_block_reason, 'native connection disabled')

    def test_combat_refused_before_import_attachment_or_journal(self):
        self.guard.side_effect = Refused('当前处于战斗，停止获取。')
        with self.assertRaisesRegex(Refused, '战斗'):
            self.dispatch()
        self.frida.attach.assert_not_called()
        self.assertFalse(self.a.journal.exists())

    def test_changed_context_after_attach_never_submits(self):
        later = copy.deepcopy(self.context)
        later['identity']['space_handler'] = 601
        self.guard.side_effect = [self.context, later]
        session = self.frida.attach.return_value
        with self.assertRaisesRegex(Refused, '场景发生变化'):
            self.dispatch()
        session.create_script.return_value.exports_sync.submit.assert_not_called()
        session.detach.assert_not_called()
        session.create_script.return_value.unload.assert_not_called()

    def test_changed_context_anchor_after_attach_never_submits(self):
        later = copy.deepcopy(self.context)
        later['anchors'][0]['expected_hex'] = '01000000'
        self.guard.side_effect = [self.context, later]
        session = self.frida.attach.return_value
        with self.assertRaisesRegex(Refused, '场景发生变化'):
            self.dispatch()
        session.create_script.return_value.exports_sync.submit.assert_not_called()

    def test_stable_context_anchors_reach_game_thread_request(self):
        session = self.frida.attach.return_value
        script = session.create_script.return_value
        def submit(request):
            message_callback = script.on.call_args.args[1]
            message_callback(dict(type='send', payload=dict(token=request['token'],
                                                            status='completed', called=True)), None)
        script.exports_sync.submit.side_effect = submit
        result = self.dispatch()
        self.assertEqual(result['status'], 'completed')
        sent = script.exports_sync.submit.call_args.args[0]
        self.assertIn(dict(address=hex(700), size=4, expected_hex='00000000',
                           label='battle state'), sent['anchors'])
        self.assertEqual(self.guard.call_count, 2)

    def test_second_adapter_dispatch_reuses_agent_and_resets_old_token(self):
        session = self.frida.attach.return_value
        script = session.create_script.return_value
        script.exports_sync.reset.return_value = {'status': 'idle'}
        def submit(request):
            callback = script.on.call_args.args[1]
            callback(dict(type='send', payload=dict(token=request['token'],
                                                   status='completed', called=True)), None)
        script.exports_sync.submit.side_effect = submit
        first = self.dispatch()
        self.a._record(dict(first, status='verified'))
        reopened = AcquisitionAdapter(self.game)
        reopened._method = self.a._method
        reopened._current = self.a._current
        second = reopened._dispatch(self.raw, 'add', dict(item_id=180000, quantity=10))
        self.assertNotEqual(first['token'], second['token'])
        self.frida.attach.assert_called_once()
        session.create_script.assert_called_once()
        script.load.assert_called_once()
        script.exports_sync.reset.assert_called_once_with(first['token'])
        script.unload.assert_not_called()
        session.detach.assert_not_called()

    def test_transport_loss_does_not_claim_native_execution_has_stopped(self):
        session = self.frida.attach.return_value
        script = session.create_script.return_value
        def submit(_request):
            session.on.call_args.args[1]('connection-terminated', None)
        script.exports_sync.submit.side_effect = submit
        try:
            with self.assertRaisesRegex(Refused, '结果不确定'):
                self.dispatch()
            self.assertTrue(self.a.blocked)
            self.assertTrue(self.a._native_inflight)
            self.assertTrue(native_calls_pending())
            session.detach.assert_not_called()
            script.unload.assert_not_called()
        finally:
            # Offline fixture teardown only; no actual native operation exists.
            self.a._native_inflight = False
            self.a.close()

    def test_process_termination_releases_inflight_but_keeps_result_uncertain(self):
        session = self.frida.attach.return_value
        script = session.create_script.return_value
        script.exports_sync.submit.side_effect = lambda _request: session.on.call_args.args[1](
            'process-terminated', None)
        with self.assertRaisesRegex(Refused, '结果不确定'):
            self.dispatch()
        self.assertTrue(self.a.blocked)
        self.assertFalse(self.a._native_inflight)


class ExistingAgentTests(unittest.TestCase):
    def resolver(self, paths):
        rr = Mock()
        rr.reader.iter_regions.return_value = [
            dict(type=0x1000000, allocation=i * 4096) for i in range(1, len(paths) + 1)]
        rr.reader.mapped.side_effect = paths
        return rr

    def test_old_agent_prevents_new_attachment(self):
        rr = self.resolver([r'\Device\Volume\WorldApart.exe', r'\Device\Volume\frida-agent.dll'])
        with self.assertRaisesRegex(Refused, '已有不能复用'):
            require_no_unmanaged_agent(rr)

    def test_regular_images_pass_readonly_preflight(self):
        rr = self.resolver([r'\Device\Volume\WorldApart.exe', r'\Device\Volume\GameAssembly.dll'])
        require_no_unmanaged_agent(rr)

    def test_unknown_module_path_refuses(self):
        with self.assertRaisesRegex(Refused, '已加载模块'):
            require_no_unmanaged_agent(self.resolver(['']))


class NativeBlockRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'logs').mkdir()
        self.journal = self.root / 'logs' / 'acquisition-pending.json'
        self.here = patch('acquisition_adapter.HERE', self.root)
        self.here.start()
        self.runtime = patch('acquisition_adapter.initialize_runtime', return_value=self.root / 'logs')
        self.runtime.start()
        self.addCleanup(self.runtime.stop)

    def tearDown(self):
        self.here.stop()
        self.tmp.cleanup()

    def game(self, pid=10, created=1000):
        return SimpleNamespace(
            resolver=SimpleNamespace(reader=SimpleNamespace(pid=pid)),
            stamp=(r'c:\games\worldapart.exe', created), record=Mock())

    def write(self, **changes):
        state = dict(status='attach_failed', pid=10, process_creation_filetime=1000)
        state.update(changes)
        self.journal.write_text(json.dumps(state), encoding='utf8')

    def test_same_pid_new_creation_time_releases_native_only_block(self):
        self.write()
        adapter = AcquisitionAdapter(self.game(created=2000))
        self.assertFalse(adapter.blocked)
        self.assertIsNone(adapter.native_block_reason)
        self.assertIsNone(adapter.native_block_identity)

    def test_new_pid_releases_native_only_block(self):
        self.write()
        adapter = AcquisitionAdapter(self.game(pid=20, created=2000))
        self.assertFalse(adapter.blocked)
        self.assertIsNone(adapter.native_block_reason)

    def test_same_process_identity_remains_blocked(self):
        self.write()
        adapter = AcquisitionAdapter(self.game())
        self.assertFalse(adapter.blocked)
        self.assertTrue(adapter.native_block_reason)
        self.assertEqual(adapter.native_block_identity,
                         {'pid': 10, 'process_creation_filetime': 1000})

    def test_legacy_attaching_journal_uses_top_level_identity(self):
        self.write(status='attaching')
        self.assertTrue(AcquisitionAdapter(self.game()).native_block_reason)
        self.assertIsNone(AcquisitionAdapter(self.game(created=2000)).native_block_reason)

    def test_missing_or_malformed_origin_identity_never_releases(self):
        for fields in ({'pid': None}, {'process_creation_filetime': None},
                       {'pid': True}, {'process_creation_filetime': '1000'},
                       {'native_block_identity': {'pid': 10}}):
            with self.subTest(fields=fields):
                self.write(**fields)
                adapter = AcquisitionAdapter(self.game(pid=20, created=2000))
                self.assertTrue(adapter.native_block_reason)
                self.assertIsNone(adapter.native_block_identity)

    def test_missing_current_identity_never_releases(self):
        self.write()
        adapter = AcquisitionAdapter(self.game(pid=20, created=None))
        self.assertTrue(adapter.native_block_reason)

    def test_unknown_and_pending_stay_globally_blocked_after_restart(self):
        for status in ('unknown', 'pending'):
            with self.subTest(status=status):
                self.write(status=status, native_block_reason='old attach failed',
                           native_block_identity={'pid': 10, 'process_creation_filetime': 1000})
                adapter = AcquisitionAdapter(self.game(pid=20, created=2000))
                self.assertTrue(adapter.blocked)
                self.assertTrue(adapter.native_block_reason)

    def test_existing_success_keeps_origin_identity_for_later_restart(self):
        self.write()
        adapter = AcquisitionAdapter(self.game())
        adapter._record(dict(status='verified', operation='add_existing',
                             pid=999, process_creation_filetime=9999))
        state = json.loads(self.journal.read_text(encoding='utf8'))
        self.assertEqual(state['native_block_identity'],
                         {'pid': 10, 'process_creation_filetime': 1000})
        self.assertTrue(AcquisitionAdapter(self.game()).native_block_reason)
        self.assertIsNone(AcquisitionAdapter(self.game(created=2000)).native_block_reason)

    def test_verified_edit_cannot_invent_missing_origin_from_top_level_identity(self):
        self.write(status='verified', native_block_reason='unknown origin',
                   native_block_identity=None)
        adapter = AcquisitionAdapter(self.game(pid=20, created=2000))
        self.assertTrue(adapter.native_block_reason)
        self.assertIsNone(adapter.native_block_identity)


if __name__ == '__main__':
    unittest.main()
