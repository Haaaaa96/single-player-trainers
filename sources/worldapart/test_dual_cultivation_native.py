"""Only mock transport and temporary safety files; no game or Frida connection."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import Mock, patch
import dual_cultivation_native as mo
from write_guard import Refused, UncertainWrite


def state():
    return dict(identity=(("game", 123), 1), native=dict(round_key="a"*64,
        anchors=[dict(address="0x1000",size=1,expected_hex="00")],
        registry_links=[dict(address="0x6000",expected="0x7000")],registry=dict(count=1),method_info="0x8000"))


class MiniOnceTests(unittest.TestCase):
    def setUp(self):
        directory=TemporaryDirectory();self.addCleanup(directory.cleanup);self.root=Path(directory.name)
        self.game=SimpleNamespace(stamp=("game",123),resolver=SimpleNamespace(reader=SimpleNamespace(pid=999)),record=Mock())
        self.resolver=Mock();self.resolver.prepare_solve.side_effect=lambda shown:deepcopy(state())
        self.resolver.verify_native.return_value=dict(verified=True,settlement_verified=False,phase='settling')
        self.requests=[];self.connections=[];self.submit_error=None;self.start_error=None;self.send=True
        self.response=dict(status='completed',called=True,round_key='a'*64)
        for p in (patch.object(mo,'initialize_runtime',return_value=self.root),
                  patch.dict('sys.modules',{'frida':SimpleNamespace(__version__='17.7.3')}),
                  patch.object(mo,'acquire_connection',side_effect=self.acquire)):
            p.start();self.addCleanup(p.stop)
        self.bridges=[];self.bridge=self.new_bridge();self.addCleanup(self.cleanup_bridges)

    def new_bridge(self):
        b=mo.MiniGameOnce(self.game,self.resolver,operation='dual_cultivation_complete',
                         method_spec=dict(token=0x06010D8C,rva=0xAC8B00,argc=1),journal_name='once.json')
        self.bridges.append(b);return b

    def cleanup_bridges(self):
        for b in self.bridges:b._native_inflight=False;b.close()

    def acquire(self,identity,frida,source,epoch,owner,message,detached,before,check):
        self.assertEqual(identity,(999,123));self.assertEqual(epoch,self.root/'acquisition-native-epochs.json')
        before()
        if self.start_error:raise self.start_error
        c=SimpleNamespace(session=object(),previous_token=None,prepare=Mock(),release=Mock())
        def submit(req):
            self.requests.append(req);self.assertEqual(self.event()['status'],'pending')
            if self.submit_error:raise self.submit_error
            if self.send:message(dict(type='send',payload=dict(self.response,token=req['token'])),None)
        c.script=SimpleNamespace(exports_sync=SimpleNamespace(submit=submit));self.connections.append(c);return c

    def event(self):
        return json.loads(self.bridge.journal.read_text(encoding='utf8'))['rounds']['a'*64]

    def test_success_and_shared_protocol(self):
        result=self.bridge.solve(state());self.assertEqual(result['phase'],'settling')
        self.assertFalse(result['settlement_verified']);req=self.requests[0]
        self.assertEqual(req['operation'],'dual_cultivation_complete');self.assertEqual(req['parameter_count'],1)
        self.assertNotIn('anchors',req['minigame']);self.assertEqual(self.event()['status'],'verified')
        self.connections[0].release.assert_called_once_with(self.bridge)

    def test_second_gui_cannot_replay_verified(self):
        self.bridge.solve(state())
        with self.assertRaises(Refused):self.new_bridge().solve(state())
        self.assertEqual(len(self.requests),1);self.assertEqual(self.event()['status'],'verified')

    def test_state_changes_during_attach_dont_dispatch(self):
        changed=state();changed['identity']=('new',)
        self.resolver.prepare_solve.side_effect=[state(),changed]
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.requests,[]);self.assertEqual(self.event()['status'],'not_dispatched')

    def test_missing_proof_never_acquires(self):
        invalid=state();invalid['native']['registry_links']=[]
        self.resolver.prepare_solve.side_effect=lambda _:invalid
        with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.connections,[])

    def test_rejected_called_false_can_retry_fresh(self):
        self.response=dict(status='rejected',called=False,reason='paused')
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.event()['status'],'rejected');self.bridge._require_unused('a'*64)

    def test_called_true_rejection_is_unknown(self):
        self.response=dict(status='rejected',called=True)
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(self.event()['status'],'unknown')

    def test_mismatched_round_is_unknown(self):
        self.response['round_key']='b'*64
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(len(self.requests),1)

    def test_failed_verification_is_unknown(self):
        self.resolver.verify_native.return_value={'verified':False}
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(self.event()['status'],'unknown')

    def test_transport_error_keeps_native_pending(self):
        self.submit_error=RuntimeError('connection lost')
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertTrue(self.bridge._native_inflight);self.assertIn(self.bridge,mo._RETAINED_BRIDGES)
        self.connections[0].release.assert_not_called()

    def test_timeout_has_no_retry(self):
        self.send=False
        with patch.object(mo.threading.Event,'wait',return_value=False):
            with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(len(self.requests),1);self.assertTrue(self.bridge._native_inflight)

    def test_post_write_log_error_preserves_pending(self):
        record=self.bridge._record
        def fail(key,event):
            if event['status'] in ('verified','unknown'):raise OSError('disk full')
            return record(key,event)
        self.bridge._record=fail
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(self.event()['status'],'pending')
        with self.assertRaises(Refused):self.bridge._require_unused('a'*64)

    def test_attach_failed_no_call_can_recheck_broker_epoch(self):
        self.start_error=mo.NativeStartError('attach',RuntimeError('failed'))
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.requests,[]);self.assertEqual(self.event()['status'],'attach_failed')
        self.assertIs(self.event()['called'],False);self.bridge._require_unused('a'*64)

    def test_connection_refusal_is_durable_without_dispatch_or_retry(self):
        with patch.object(mo, 'acquire_connection', side_effect=Refused('游戏中已有不能复用的原生连接组件')) as acquire:
            with self.assertRaises(Refused):self.bridge.solve(state())
        event=self.event()
        self.assertEqual(event['status'],'not_dispatched')
        self.assertIs(event['called'],False)
        self.assertEqual(event['stage'],'connection')
        self.assertIn('不能复用',event['reason'])
        self.assertEqual(self.requests,[])
        acquire.assert_called_once()

    def test_corrupt_journal_rejects(self):
        self.bridge.journal.write_text('{bad',encoding='utf8')
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.connections,[])

    def test_other_pending_round_same_process_also_blocks(self):
        self.bridge._record('b'*64,dict(status='pending',called=None,pid=999,process_creation_filetime=123))
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.requests,[])

    def test_two_guis_cannot_overwrite_pending_or_verified(self):
        entered,release=threading.Event(),threading.Event()
        def verify(*_):
            entered.set()
            if not release.wait(5):raise RuntimeError('test deadline')
            return dict(verified=True,phase='done')
        self.resolver.verify_native.side_effect=verify;second=self.new_bridge();outcomes=[]
        def work(bridge):
            try:outcomes.append(bridge.solve(state()))
            except Exception as e:outcomes.append(e)
        a=threading.Thread(target=work,args=(self.bridge,));a.start();self.assertTrue(entered.wait(5))
        b=threading.Thread(target=work,args=(second,));b.start();time.sleep(.08)
        self.assertEqual(self.event()['status'],'pending');release.set();a.join(5);b.join(5)
        self.assertFalse(a.is_alive() or b.is_alive());self.assertEqual(len(self.requests),1)
        self.assertEqual(self.event()['status'],'verified');self.assertEqual(sum(isinstance(o,Refused) for o in outcomes),1)


if __name__=='__main__':unittest.main()
