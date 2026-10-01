"""Offline host lifecycle tests. No Frida import, attach, game, or UI access."""
import hashlib
from multiprocessing.connection import Listener, Client
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from native_acquisition_session import NativeConnection, NativeStartError
from native_broker_host import BrokerHost, GameLifetime, PipePeer, start_authenticated_peer, validated_startup_path
from native_broker import RemoteConnection
from write_guard import Refused


class Peer:
    def __init__(self):
        self.alive, self.request_ids, self.messages = True, set(), []
    def send(self, value):
        self.messages.append(value)
    def close(self):
        self.alive = False


class Script:
    def __init__(self, session):
        self.session, self.state = session, dict(status='idle')
        self.exports_sync = SimpleNamespace(status=lambda: dict(self.state), submit=self.submit, reset=self.reset)
        self.loads = self.unloads = self.resets = self.submits = 0
    def on(self, name, callback):
        self.callback = callback
    def load(self):
        self.loads += 1
        if self.session.fail_load:
            raise RuntimeError('load failure')
    def unload(self):
        self.unloads += 1
        if self.session.fail_unload:
            raise RuntimeError('unload failure')
    def reset(self, token):
        if self.state.get('token') != token or self.state['status'] not in ('completed', 'rejected', 'cancelled'):
            raise Refused('unsafe reset')
        self.resets += 1
        self.state = dict(status='idle')
        return self.state
    def submit(self, request):
        self.submits += 1
        self.state = dict(token=request['token'], status='pending')
        if self.session.message_before_rpc:
            self.state = dict(token=request['token'], status='completed', called=True)
            # Model Frida's separate dispatcher, which must return before the
            # synchronous RPC response is delivered. Same-thread RLock mocks
            # would conceal the original lock inversion.
            done = threading.Event()
            def callback():
                self.callback(dict(type='send', payload=dict(self.state)), None)
                done.set()
            thread = threading.Thread(target=callback, daemon=True)
            thread.start()
            if not done.wait(1):
                raise RuntimeError('Frida callback deadlocked behind RPC lock')
        if self.session.fail_submit:
            raise RuntimeError('RPC response lost')
        return dict(self.state)


class Session:
    def __init__(self):
        self.scripts = []
        self.fail_load = self.fail_unload = self.fail_submit = self.message_before_rpc = False
    def on(self, name, callback):
        self.detached_callback = callback
    def create_script(self, source):
        script = Script(self)
        self.scripts.append(script)
        return script


class HostTests(unittest.TestCase):
    def setUp(self):
        logger=patch('native_broker_host.record_host_lifecycle')
        self.diagnostics=logger.start();self.addCleanup(logger.stop)
        self.checks, self.acquisitions, self.connections = [], [], []
        self.session = Session()
        def acquire(identity, source, path, owner, callback, detached):
            self.acquisitions.append(identity)
            connection = NativeConnection(identity, self.session)
            connection.script = self.session.create_script(source)
            connection.script.on('message', connection._on_message)
            connection.script.load()
            connection.usable = True
            connection.claim(owner, callback, detached)
            self.connections.append(connection)
            return connection
        self.host = BrokerHost((123, 456), 'unused-epoch.json', acquire=acquire,
                               check_game=lambda identity: self.checks.append(identity))
        self.peer = Peer()
    def tearDown(self):
        self.host.stop()
        self.host.events.join()
    def cmd(self, command, payload=None, peer=None, request_id=None):
        return self.host.dispatch(peer or self.peer, dict(id=request_id or uuid.uuid4().hex, command=command, payload=payload or {}))
    def ok(self, command, payload=None, peer=None):
        result = self.cmd(command, payload, peer)
        self.assertTrue(result['ok'], result)
        return result['result']
    def claim(self, peer=None, source='reviewed script'):
        return self.ok('claim', dict(source=source, source_sha256=hashlib.sha256(source.encode()).hexdigest()), peer)
    def prepared(self, peer=None):
        self.claim(peer)
        self.ok('prepare', peer=peer)
    def request(self, **changes):
        return dict(operation='meridian_solve', token=uuid.uuid4().hex, pid=123,
                    deadline=int(time.time()*1000)+10000, anchors=[dict(address='0x1', size=1, expected_hex='00')], **changes)
    def submit(self, peer=None, request=None):
        request = request or self.request()
        self.ok('submit', dict(request=request), peer)
        return request
    def finish(self, request, status='completed', called=True):
        payload = dict(token=request['token'], status=status, called=called)
        self.host.connection.script.state = payload
        self.host.on_message(dict(type='send', payload=payload))
        self.host.events.join()
        return payload

    def test_status_never_attaches(self):
        result = self.ok('status')
        self.assertTrue(result['ready'])
        self.assertFalse(result['busy'])
        self.assertFalse(result['connected'])
        self.assertEqual(self.acquisitions, [])

    def test_claim_and_prepare_attach_once(self):
        self.prepared()
        self.ok('release')
        self.prepared(Peer())
        self.assertEqual(len(self.acquisitions), 1)

    def test_idle_bridge_advertises_bounded_new_operation_without_new_attach(self):
        self.claim()
        self.host.connection.script.state['operations'] = ['future_reviewed_feature']
        self.ok('prepare')
        request = self.request()
        request['operation'] = 'future_reviewed_feature'
        self.submit(request=request)
        self.assertEqual(len(self.acquisitions), 1)

    def test_unadvertised_operation_never_reaches_bridge(self):
        self.claim()
        self.host.connection.script.state['operations'] = ['one_feature']
        self.ok('prepare')
        self.assertFalse(self.cmd('submit', dict(request=self.request()))['ok'])
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_malformed_capabilities_cannot_prepare(self):
        self.claim()
        for operations in (None, [], ['x','x'], ['../bad'], 'meridian_solve', [True], ['x'] * 129):
            with self.subTest(operations=operations):
                self.host.connection.script.state['operations'] = operations
                self.assertFalse(self.cmd('prepare')['ok'])
                self.assertFalse(self.host.prepared)
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_legacy_bridge_still_uses_reviewed_legacy_whitelist(self):
        self.prepared()
        request = self.request()
        request['operation'] = 'future_reviewed_feature'
        self.assertFalse(self.cmd('submit', dict(request=request))['ok'])
        self.submit()

    def test_failed_reprepare_clears_previous_permission(self):
        self.prepared()
        self.host.connection.script.state['operations'] = []
        self.assertFalse(self.cmd('prepare')['ok'])
        self.assertFalse(self.host.prepared)
        self.assertFalse(self.cmd('submit', dict(request=self.request()))['ok'])
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_replaced_script_cannot_inherit_old_capabilities(self):
        self.claim()
        self.host.connection.script.state['operations'] = ['old_feature']
        self.ok('prepare')
        self.ok('release')
        self.claim(source='new reviewed script')
        self.host.connection.script.state['operations'] = ['new_feature']
        self.ok('prepare')
        old = self.request(); old['operation'] = 'old_feature'
        self.assertFalse(self.cmd('submit', dict(request=old))['ok'])
        new = self.request(); new['operation'] = 'new_feature'
        self.submit(request=new)
        self.assertEqual(len(self.acquisitions), 1)

    def test_close_gui_and_reopen_after_completed_uses_same_session(self):
        self.prepared()
        request = self.submit()
        self.finish(request)
        self.host.disconnect(self.peer)
        fresh = Peer()
        self.prepared(fresh)
        self.submit(fresh)
        self.assertEqual(len(self.acquisitions), 1)
        self.assertEqual(len(self.session.scripts), 1)
        self.assertEqual(self.session.scripts[0].submits, 2)

    def test_pending_eof_holds_owner_until_late_safe_result(self):
        self.prepared()
        request = self.submit()
        self.host.disconnect(self.peer)
        fresh = Peer()
        self.assertFalse(self.cmd('claim', dict(source='x', source_sha256=hashlib.sha256(b'x').hexdigest()), fresh)['ok'])
        self.assertTrue(self.host.status()['busy'])
        self.finish(request)
        self.assertIsNone(self.host.owner)
        self.prepared(fresh)
        self.assertEqual(len(self.acquisitions), 1)

    def test_owner_eof_before_submit_releases(self):
        self.prepared()
        self.host.disconnect(self.peer)
        self.assertIsNone(self.host.owner)
        self.prepared(Peer())

    def test_second_owner_and_nonowner_commands_refused(self):
        self.prepared()
        other = Peer()
        for command in ('prepare', 'release'):
            self.assertFalse(self.cmd(command, peer=other)['ok'])
        self.assertFalse(self.cmd('submit', dict(request=self.request()), other)['ok'])
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_pending_cannot_release_prepare_or_resubmit(self):
        self.prepared()
        request = self.submit()
        for command in ('prepare', 'release'):
            self.assertFalse(self.cmd(command)['ok'])
        self.assertFalse(self.cmd('submit', dict(request=request))['ok'])
        self.assertEqual(self.host.connection.script.submits, 1)

    def test_safe_rejected_and_cancelled_release(self):
        for status in ('rejected', 'cancelled'):
            self.prepared()
            request = self.submit()
            self.finish(request, status, False)
            self.ok('release')
            self.assertFalse(self.host.status()['busy'])

    def test_rejected_called_true_is_unsafe(self):
        self.prepared()
        self.finish(self.submit(), 'rejected', True)
        self.assertFalse(self.cmd('release')['ok'])
        self.assertFalse(self.host.status()['ready'])

    def test_unknown_cannot_be_overwritten_by_later_completed(self):
        self.prepared()
        request = self.submit()
        self.finish(request, 'unknown', True)
        self.finish(request)
        self.assertEqual(self.ok('request_status', dict(token=request['token']))['status'], 'unknown')
        self.assertFalse(self.cmd('release')['ok'])

    def test_exception_then_eof_blocks_reclaim(self):
        self.prepared()
        self.finish(self.submit(), 'exception', True)
        self.host.disconnect(self.peer)
        self.assertTrue(self.host.status()['busy'])
        self.assertFalse(self.host.status()['ready'])

    def test_rpc_response_lost_never_replays(self):
        self.prepared()
        self.session.fail_submit = True
        request = self.request()
        result = self.cmd('submit', dict(request=request))
        self.assertEqual(result['kind'], 'unknown')
        self.assertEqual(self.ok('request_status', dict(token=request['token']))['status'], 'unknown')
        self.assertFalse(self.cmd('submit', dict(request=request))['ok'])
        self.assertEqual(self.host.connection.script.submits, 1)

    def test_separate_frida_callback_completes_before_rpc_returns(self):
        self.prepared()
        self.session.message_before_rpc = True
        request = self.submit()
        self.host.events.join()
        self.assertEqual(self.ok('request_status', dict(token=request['token']))['status'], 'completed')
        self.ok('release')

    def test_script_error_locks_future_requests(self):
        self.prepared()
        request = self.submit()
        self.host.on_message(dict(type='error', description='script error'))
        self.host.events.join()
        self.assertFalse(self.host.status()['ready'])
        self.assertEqual(self.ok('request_status', dict(token=request['token']))['status'], 'unknown')

    def test_unrelated_token_does_not_unlock_pending(self):
        self.prepared()
        self.submit()
        self.host.on_message(dict(type='send', payload=dict(token='wrong', status='completed', called=True)))
        self.host.events.join()
        self.assertTrue(self.host.inflight)

    def test_detached_keeps_epoch_ownership_blocked(self):
        self.prepared()
        self.host.connection._on_detached('connection-terminated')
        self.host.events.join()
        self.assertFalse(self.host.status()['ready'])
        self.assertFalse(self.host.status()['connected'])
        self.assertEqual(self.peer.messages[-1]['event'], 'detached')

    def test_source_change_uses_existing_session_after_safe_reset(self):
        self.prepared()
        request = self.submit()
        old = self.host.connection.script
        self.finish(request)
        self.host.disconnect(self.peer)
        fresh = Peer()
        self.claim(fresh, 'new reviewed script')
        self.ok('prepare', peer=fresh)
        self.assertEqual(old.resets, 1)
        self.assertEqual(old.unloads, 1)
        self.assertEqual(len(self.session.scripts), 2)
        self.assertEqual(len(self.acquisitions), 1)
        self.assertFalse(self.cmd('submit', dict(request=request), fresh)['ok'])

    def test_source_change_failure_never_reattaches(self):
        self.prepared()
        self.ok('release')
        self.session.fail_load = True
        source = 'new script'
        result = self.cmd('claim', dict(source=source, source_sha256=hashlib.sha256(source.encode()).hexdigest()))
        self.assertEqual(result['kind'], 'native_start')
        self.assertEqual(result['stage'], 'replace_script')
        self.assertFalse(self.host.status()['ready'])
        self.assertEqual(len(self.acquisitions), 1)

    def test_attach_failure_never_retries(self):
        def failed(*args):
            self.acquisitions.append(args[0])
            raise NativeStartError('attach', RuntimeError('fixture'))
        self.host.acquire = failed
        payload = dict(source='x', source_sha256=hashlib.sha256(b'x').hexdigest())
        self.assertEqual(self.cmd('claim', payload)['kind'], 'native_start')
        self.assertFalse(self.cmd('claim', payload)['ok'])
        self.assertEqual(len(self.acquisitions), 1)

    def test_unmanaged_agent_claim_failure_logs_stage_without_exception_text(self):
        def refused(*args):
            raise Refused('游戏中已有不能复用的原生连接组件；SECRET')
        self.host.acquire=refused
        payload=dict(source='x',source_sha256=hashlib.sha256(b'x').hexdigest())
        self.assertEqual(self.cmd('claim',payload)['kind'],'refused')
        records=[call for call in self.diagnostics.call_args_list if call.args[1]=='claim_failed']
        self.assertEqual(len(records),1)
        self.assertEqual(records[0].kwargs['reason_code'],'unmanaged_agent')
        self.assertNotIn('SECRET',repr(records))
        self.assertTrue(self.host.unsafe)

    def test_busy_claim_rejection_is_diagnosed_without_new_connection(self):
        self.claim()
        payload=dict(source='x',source_sha256=hashlib.sha256(b'x').hexdigest())
        self.assertFalse(self.cmd('claim',payload,peer=Peer())['ok'])
        self.assertEqual(len(self.acquisitions),1)
        self.assertTrue(any(call.args[1]=='claim_rejected' for call in self.diagnostics.call_args_list))

    def test_source_hash_mismatch_does_not_attach(self):
        self.assertFalse(self.cmd('claim', dict(source='x', source_sha256='a'*64))['ok'])
        self.assertEqual(self.acquisitions, [])

    def test_unprepared_submit_does_not_reach_native(self):
        self.claim()
        self.assertFalse(self.cmd('submit', dict(request=self.request()))['ok'])
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_request_whitelist_bounds_and_identity(self):
        self.prepared()
        for key, value in [('pid', 124), ('operation', 'arbitrary_call'), ('token', ''),
                           ('deadline', 0), ('deadline', float('nan')), ('anchors', []),
                           ('deadline', time.time()*1000+60000)]:
            request = self.request()
            request[key] = value
            self.assertFalse(self.cmd('submit', dict(request=request))['ok'], (key, value))
        self.assertEqual(self.host.connection.script.submits, 0)

    def test_duplicate_command_id_does_not_repeat(self):
        request_id = uuid.uuid4().hex
        self.assertTrue(self.cmd('status', request_id=request_id)['ok'])
        self.assertFalse(self.cmd('status', request_id=request_id)['ok'])

    def test_game_identity_query_failure_blocks_without_stopping(self):
        self.prepared()
        def failed(_identity):
            raise OSError('temporary query failure')
        self.host.check_game = failed
        self.assertFalse(self.cmd('status')['ok'])
        self.assertFalse(self.host.stopped)
        self.assertTrue(self.host.connection.usable)

    def test_monitor_uncertain_can_recover_without_detaching(self):
        self.prepared()
        self.host.monitor_uncertain = True
        self.assertFalse(self.host.status()['ready'])
        self.assertFalse(self.cmd('prepare')['ok'])
        self.host.monitor_uncertain = False
        self.ok('prepare')
        self.assertEqual(len(self.acquisitions), 1)

    def test_scalar_claim_release_does_not_attach(self):
        self.ok('claim_scalar')
        self.assertTrue(self.host.status()['busy'])
        self.ok('release_scalar', dict(uncertain=False))
        self.assertFalse(self.host.status()['busy'])
        self.assertEqual(self.acquisitions, [])

    def test_scalar_blocks_native_and_other_scalar_owners(self):
        self.ok('claim_scalar')
        for command in ('claim_scalar', 'prepare'):
            self.assertFalse(self.cmd(command)['ok'])
        self.assertFalse(self.cmd('submit', dict(request=self.request()))['ok'])
        self.assertFalse(self.cmd('claim_scalar', peer=Peer())['ok'])
        self.assertEqual(self.acquisitions, [])

    def test_native_pending_blocks_scalar(self):
        self.prepared()
        self.submit()
        self.assertFalse(self.cmd('claim_scalar', peer=Peer())['ok'])

    def test_scalar_uncertain_release_is_permanent(self):
        self.ok('claim_scalar')
        self.assertFalse(self.ok('release_scalar', dict(uncertain=True))['released'])
        self.assertFalse(self.host.status()['ready'])
        self.assertFalse(self.cmd('release_scalar', dict(uncertain=False))['ok'])

    def test_scalar_eof_is_unknown_not_release(self):
        self.ok('claim_scalar')
        self.host.disconnect(self.peer)
        self.assertTrue(self.host.status()['busy'])
        self.assertFalse(self.host.status()['ready'])
        self.assertFalse(self.cmd('claim_scalar', peer=Peer())['ok'])

    def test_scalar_nonowner_cannot_release(self):
        self.ok('claim_scalar')
        self.assertFalse(self.cmd('release_scalar', dict(uncertain=False), Peer())['ok'])
        self.assertTrue(self.host.scalar)

    def test_real_pipe_gui_disconnect_pending_and_reopen_same_native_session(self):
        pipe = r'\\.\pipe\WorldApartTrainer-' + uuid.uuid4().hex
        key = os.urandom(32)
        listener = Listener(pipe, family='AF_PIPE', authkey=key)
        peers, errors = [], []
        def accept():
            try:
                for _ in range(2):
                    peer = PipePeer(self.host, listener.accept())
                    peers.append(peer)
                    threading.Thread(target=peer.run, daemon=True).start()
            except Exception as exc:
                errors.append(exc)
        threading.Thread(target=accept, daemon=True).start()
        clients = []
        def wait_until(predicate):
            deadline = time.monotonic()+3
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(0.01)
            self.fail('Pipe state did not settle')
        descriptor = dict(identity=[123,456], pipe=pipe, auth_protected='fixture')
        try:
            with patch('native_broker.unprotect', return_value=key):
                first = RemoteConnection(descriptor)
                clients.append(first)
                first.claim(object(), lambda *_: None, lambda *_: None, 'reviewed script')
                first.prepare()
                request = self.request()
                first.submit(request)
                first.close_transport()
                wait_until(lambda: len(peers) == 1 and not peers[0].alive)
                second = RemoteConnection(descriptor)
                clients.append(second)
                self.assertTrue(second.call('status')['busy'])
                with self.assertRaises(Refused):
                    second.call('claim', dict(source='reviewed script',
                        source_sha256=hashlib.sha256(b'reviewed script').hexdigest()))
                self.finish(request)
                wait_until(lambda: self.host.owner is None)
                owner, completed = object(), threading.Event()
                second.claim(owner, lambda *_: completed.set(), lambda *_: None, 'reviewed script')
                second.prepare()
                second_request = self.request()
                second.submit(second_request)
                self.finish(second_request)
                self.assertTrue(completed.wait(2))
                second.release(owner)
                self.assertFalse(second.call('status')['busy'])
                self.assertEqual(len(self.acquisitions), 1)
                self.assertEqual(self.host.connection.script.submits, 2)
                self.assertEqual(errors, [])
        finally:
            for client in clients:
                client.close_transport()
            for peer in peers:
                peer.close()
            listener.close()

    def test_stalled_real_pipe_auth_does_not_block_second_gui_and_expires(self):
        pipe = r'\\.\pipe\WorldApartTrainer-' + uuid.uuid4().hex
        key = os.urandom(32)
        listener = Listener(pipe, family='AF_PIPE', authkey=None)
        transports, accepted = [], threading.Event()
        slots = threading.BoundedSemaphore(8)
        def accept():
            for _ in range(2):
                transport = listener.accept()
                transports.append(transport)
                start_authenticated_peer(self.host, transport, key, slots, timeout=0.2)
            accepted.set()
        thread = threading.Thread(target=accept, daemon=True)
        thread.start()
        stalled = Client(pipe, family='AF_PIPE', authkey=None)
        client = None
        try:
            with patch('native_broker.unprotect', return_value=key):
                client = RemoteConnection(dict(identity=[123,456],pipe=pipe,auth_protected='fixture'))
                self.assertTrue(client.call('status', timeout=1)['ready'])
            self.assertTrue(accepted.wait(1))
            deadline = time.monotonic()+2
            while (not transports[0].closed or slots._value != 8) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(transports[0].closed)
            self.assertEqual(slots._value, 8)
            self.assertEqual(self.acquisitions, [])
            # The deadline closes only the unauthenticated peer.
            self.assertTrue(client.call('status', timeout=1)['ready'])
        finally:
            stalled.close()
            if client:
                client.close_transport()
            # Authentication workers and PipePeer own these server handles.
            # Wait for EOF/expiry cleanup instead of racing their CloseHandle
            # with a second unsynchronised close in the test thread.
            deadline = time.monotonic() + 2
            while not all(transport.closed for transport in transports) and time.monotonic() < deadline:
                time.sleep(0.01)
            listener.close()
            self.assertTrue(all(transport.closed for transport in transports),
                            'Server peers did not release their pipe transports')

    def test_authentication_worker_limit_closes_excess_peer_without_commands(self):
        slots = threading.BoundedSemaphore(8)
        for _ in range(8):
            self.assertTrue(slots.acquire(blocking=False))
        closed = []
        transport = SimpleNamespace(close=lambda: closed.append(True))
        self.assertFalse(start_authenticated_peer(self.host, transport, b'x'*32, slots))
        self.assertEqual(closed, [True])
        self.assertIsNone(self.host.owner)
        self.assertEqual(self.acquisitions, [])
        for _ in range(8):
            slots.release()


class StartupPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'native-hosts'
        self.directory.mkdir()
        self.startup = self.directory / 'fixture.startup.json'
        self.startup.write_text('{}', encoding='utf8')

    def test_existing_startup_in_expected_directory_is_accepted(self):
        self.assertEqual(validated_startup_path(self.startup, self.directory), self.startup.resolve(strict=True))

    def test_different_path_spellings_for_same_real_directory_are_accepted(self):
        # The actual filesystem, not a mocked samefile result, proves that
        # these unequal paths identify the same directory. This reproduces
        # the identity relationship of virtualized AppData without requiring
        # an installed MSIX app or permission to create Windows symlinks.
        alias = self.directory / '..' / self.directory.name
        self.assertNotEqual(self.startup.resolve(strict=True).parent, alias)
        self.assertTrue(self.directory.samefile(alias))
        self.assertEqual(validated_startup_path(self.startup, alias), self.startup.resolve(strict=True))

    def test_same_filename_in_different_directory_is_refused(self):
        other = self.root / 'other'
        other.mkdir()
        outside = other / self.startup.name
        outside.write_bytes(self.startup.read_bytes())
        with self.assertRaises(Refused):
            validated_startup_path(outside, self.directory)

    def test_missing_file_or_expected_directory_is_refused(self):
        for startup, directory in ((self.directory / 'missing.startup.json', self.directory),
                                   (self.startup, self.root / 'missing')):
            with self.subTest(startup=startup, directory=directory), self.assertRaises(Refused):
                validated_startup_path(startup, directory)

    def test_wrong_suffix_oversize_and_directory_are_refused(self):
        wrong_suffix = self.directory / 'fixture.json'
        wrong_suffix.write_text('{}', encoding='utf8')
        oversized = self.directory / 'large.startup.json'
        oversized.write_bytes(b'x' * 16385)
        folder = self.directory / 'folder.startup.json'
        folder.mkdir()
        for startup in (wrong_suffix, oversized, folder):
            with self.subTest(startup=startup), self.assertRaises(Refused):
                validated_startup_path(startup, self.directory)

    def test_identity_query_failure_is_refused(self):
        with patch.object(Path, 'samefile', side_effect=PermissionError('unreadable')):
            with self.assertRaises(Refused):
                validated_startup_path(self.startup, self.directory)

    def test_startup_validation_precedes_config_and_game_access(self):
        from native_broker_host import _main
        with patch('runtime_paths.SAFETY_LOG_ROOT', self.root), \
                patch('native_broker_host.decode') as decode, \
                patch('native_broker_host.host_identity') as identity:
            with self.assertRaises(Refused):
                _main(self.root / 'outside.startup.json')
            decode.assert_not_called()
            identity.assert_not_called()


class HostEntryTests(unittest.TestCase):
    def test_failure_returns_nonzero_without_unhandled_windowed_exception(self):
        from native_broker_host import main
        for error in (Refused('private config details'), OSError(5, 'private config details'),
                      RuntimeError('private config details')):
            with self.subTest(error=type(error).__name__), \
                    patch('native_broker_host._main', side_effect=error) as run, \
                    patch('native_broker_host.record_host_lifecycle') as log:
                self.assertEqual(main('fixture.startup.json'), 1)
                run.assert_called_once_with('fixture.startup.json')
                self.assertEqual([call.args[1] for call in log.call_args_list],
                                 ['host_entry', 'host_unhandled_exit'])
                self.assertEqual(log.call_args.kwargs['error_type'], type(error).__name__)
                self.assertNotIn('private config details', str(log.call_args_list))

    def test_success_preserves_exit_code_and_normal_exit_diagnostic(self):
        from native_broker_host import main
        with patch('native_broker_host._main', return_value=0) as run, \
                patch('native_broker_host.record_host_lifecycle') as log:
            self.assertEqual(main('fixture.startup.json'), 0)
            run.assert_called_once_with('fixture.startup.json')
            self.assertEqual([call.args[1] for call in log.call_args_list], ['host_entry', 'host_normal_exit'])
            self.assertEqual(log.call_args.kwargs, {'exit_code': 0})


class LifetimeTests(unittest.TestCase):
    def lifetime(self, result):
        life = GameLifetime.__new__(GameLifetime)
        life.handle = 1
        life.kernel = SimpleNamespace(WaitForSingleObject=lambda handle, timeout: result)
        return life
    def test_signalled_handle_proves_exit(self):
        self.assertTrue(self.lifetime(0).exited())
    def test_nonsignalled_handle_keeps_session_alive(self):
        self.assertFalse(self.lifetime(0x102).exited())
    def test_failed_wait_does_not_claim_exit(self):
        with self.assertRaises(OSError):
            self.lifetime(0xffffffff).exited()


if __name__ == '__main__':
    unittest.main()
