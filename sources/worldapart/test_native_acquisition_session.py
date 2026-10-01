import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from native_acquisition_session import _acquire_local_connection as acquire_connection
from native_acquisition_session import NativeStartError, check_connection_available
from write_guard import Refused


class PersistentSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.epoch = Path(self.tmp.name) / 'epochs.json'
        self.pool = patch.dict('native_acquisition_session._CONNECTIONS', {}, clear=True)
        self.pool.start()
        self.frida = SimpleNamespace(attach=Mock())
        self.owner = object()
        self.callback = Mock()
        self.detached = Mock()
        self.before = Mock()
        self.check = Mock()

    def tearDown(self):
        self.pool.stop()
        self.tmp.cleanup()

    def acquire(self, identity=(10, 1000), owner=None):
        return acquire_connection(identity, self.frida, '// fixture', self.epoch,
                                  owner or self.owner, self.callback, self.detached,
                                  self.before, self.check)

    def test_two_adapters_share_agent_without_unload_or_second_attach(self):
        connection = self.acquire()
        connection.previous_token = 'first'
        connection.script.exports_sync.reset.return_value = {'status': 'idle'}
        connection.release(self.owner)
        other = object()
        again = self.acquire(owner=other)
        self.assertIs(again, connection)
        again.prepare()
        connection.script.exports_sync.reset.assert_called_once_with('first')
        self.frida.attach.assert_called_once_with(10)
        connection.session.create_script.assert_called_once()
        connection.script.load.assert_called_once()
        connection.script.unload.assert_not_called()
        connection.session.detach.assert_not_called()
        self.check.assert_called_once()

    def test_epoch_blocks_reinjection_after_trainer_restart(self):
        connection = self.acquire()
        connection.release(self.owner)
        with patch.dict('native_acquisition_session._CONNECTIONS', {}, clear=True):
            with self.assertRaisesRegex(Refused, '重启游戏'):
                self.acquire()
        self.frida.attach.assert_called_once()

    def test_availability_check_does_not_claim_or_attach(self):
        check_connection_available((10, 1000), self.epoch, self.check)
        self.check.assert_called_once()
        self.frida.attach.assert_not_called()
        self.assertEqual(list(self.epoch.parent.iterdir()), [])

    def test_availability_reuses_this_trainers_connection(self):
        connection = self.acquire()
        connection.release(self.owner)
        check = Mock(side_effect=Refused('loaded agent'))
        check_connection_available((10, 1000), self.epoch, check)
        check.assert_not_called()
        self.frida.attach.assert_called_once()

    def test_availability_detects_old_trainer_before_game_method(self):
        connection = self.acquire()
        connection.release(self.owner)
        original = (self.epoch.parent / 'native-epochs' / '10-1000.json').read_bytes()
        with patch.dict('native_acquisition_session._CONNECTIONS', {}, clear=True):
            with self.assertRaisesRegex(Refused, '不要仅重启修改器'):
                check_connection_available((10, 1000), self.epoch, self.check)
            check_connection_available((10, 2000), self.epoch, self.check)
        self.assertEqual((self.epoch.parent / 'native-epochs' / '10-1000.json').read_bytes(), original)
        self.frida.attach.assert_called_once()

    def test_availability_corrupt_history_refuses_without_attach(self):
        self.epoch.write_text('{bad', encoding='utf8')
        with self.assertRaisesRegex(Refused, '记录无法读取'):
            check_connection_available((10, 1000), self.epoch, self.check)
        self.check.assert_not_called()
        self.frida.attach.assert_not_called()

    def test_availability_keeps_unknown_loaded_agent_guard(self):
        self.check.side_effect = Refused('不能复用的原生连接组件')
        with self.assertRaisesRegex(Refused, '不能复用'):
            check_connection_available((10, 1000), self.epoch, self.check)
        self.frida.attach.assert_not_called()

    def test_availability_rejects_busy_or_lost_connection(self):
        connection = self.acquire()
        with self.assertRaisesRegex(Refused, '未结束'):
            check_connection_available((10, 1000), self.epoch, self.check)
        connection.release(self.owner)
        connection.detached = True
        with self.assertRaisesRegex(Refused, '重启游戏'):
            check_connection_available((10, 1000), self.epoch, self.check)

    def test_new_creation_time_allowed_but_old_epoch_not_overwritten(self):
        self.acquire()
        self.acquire(identity=(10, 2000), owner=object())
        claims = self.epoch.parent / 'native-epochs'
        self.assertEqual({path.name for path in claims.iterdir()}, {'10-1000.json', '10-2000.json'})
        with patch.dict('native_acquisition_session._CONNECTIONS', {}, clear=True):
            with self.assertRaises(Refused): self.acquire(identity=(10, 1000))
        self.assertEqual(self.frida.attach.call_count, 2)

    def test_overlapping_native_request_is_refused(self):
        self.acquire()
        with self.assertRaisesRegex(Refused, '未结束'):
            self.acquire(owner=object())
        self.frida.attach.assert_called_once()

    def test_failed_attach_is_not_retried_after_client_restart(self):
        self.frida.attach.side_effect = RuntimeError('agent failed')
        with self.assertRaises(NativeStartError) as raised:
            self.acquire()
        self.assertEqual(raised.exception.stage, 'attach')
        with self.assertRaisesRegex(Refused, '重启游戏'):
            self.acquire()
        self.frida.attach.assert_called_once()

    def test_script_load_failure_retains_session_and_prevents_reinjection(self):
        self.frida.attach.return_value.create_script.return_value.load.side_effect = RuntimeError('load failed')
        with self.assertRaises(NativeStartError) as raised:
            self.acquire()
        self.assertEqual(raised.exception.stage, 'load_script')
        with self.assertRaisesRegex(Refused, '已中断'):
            self.acquire()
        self.frida.attach.assert_called_once()
        self.frida.attach.return_value.detach.assert_not_called()

    def test_detached_reason_is_forwarded_and_connection_never_reused(self):
        connection = self.acquire()
        detached_callback = connection.session.on.call_args.args[1]
        detached_callback('connection-terminated', None)
        self.detached.assert_called_once_with('connection-terminated', None)
        with self.assertRaisesRegex(Refused, '已中断'):
            self.acquire(owner=object())
        self.frida.attach.assert_called_once()

    def test_bad_epoch_refuses_before_attachment(self):
        self.epoch.write_text('invalid JSON', encoding='utf8')
        with self.assertRaisesRegex(Refused, '记录无法读取'):
            self.acquire()
        self.frida.attach.assert_not_called()

    def test_epoch_write_failure_refuses_before_attachment(self):
        with patch('native_acquisition_session.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(Refused, '无法保存'):
                self.acquire()
        self.frida.attach.assert_not_called()

    def test_existing_exclusive_claim_is_not_overwritten(self):
        from native_acquisition_session import _claim_epoch
        _claim_epoch(self.epoch, (10, 1000))
        claim = self.epoch.parent / 'native-epochs' / '10-1000.json'
        original = claim.read_bytes()
        with self.assertRaisesRegex(Refused, '原连接'):
            _claim_epoch(self.epoch, (10, 1000))
        self.assertEqual(claim.read_bytes(), original)

    def test_unmanaged_agent_refusal_prevents_attachment(self):
        self.check.side_effect = Refused('existing agent')
        with self.assertRaisesRegex(Refused, 'existing agent'):
            self.acquire()
        self.frida.attach.assert_not_called()
        self.assertFalse(self.epoch.exists())

    def test_message_callback_is_current_lease_only(self):
        connection = self.acquire()
        incoming = connection.script.on.call_args.args[1]
        incoming({'type': 'send'}, None)
        self.callback.assert_called_once()
        connection.release(self.owner)
        incoming({'type': 'send'}, None)
        self.callback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
