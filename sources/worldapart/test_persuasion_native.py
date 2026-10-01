"""Only mocked shared transport and temporary request journals."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dual_cultivation_native as shared
from persuasion_adapter import METHOD
from persuasion_native import PersuasionOnce
from write_guard import Refused, UncertainWrite


def state(key="a"):
    return dict(identity=(("game",123),4), native=dict(round_key=key*64,
        anchors=[dict(address="0x1000",size=1,expected_hex="00")],
        registry_links=[dict(address="0x6000",expected="0x7000")],
        registry=dict(count=1),method_info="0x8000",npc="0x9000",npc_id=1001,topic_id=2001,session_id=4))


class PersuasionTransportTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.game=SimpleNamespace(stamp=("game",123),resolver=SimpleNamespace(reader=SimpleNamespace(pid=999)),record=Mock())
        self.adapter=Mock();self.adapter.prepare_solve.side_effect=lambda shown:deepcopy(shown)
        self.adapter.verify_native.return_value=dict(verified=True,settlement_verified=False,phase="success_countdown")
        self.requests=[];self.send=True;self.response=dict(status="completed",called=True)
        self.release=Mock();self.session=object();self.prepare=Mock();self.acquire_count=0
        for p in (patch.object(shared,"initialize_runtime",return_value=self.root),
                  patch.dict("sys.modules",{"frida":SimpleNamespace(__version__="17.7.3")}),
                  patch.object(shared,"acquire_connection",side_effect=self.acquire)):
            p.start();self.addCleanup(p.stop)
        self.bridges=[];self.bridge=self.new_bridge();self.addCleanup(self.cleanup)

    def new_bridge(self):
        b=PersuasionOnce(self.game,self.adapter,operation="persuasion_success",method_spec=METHOD,journal_name="persuasion-once.json")
        self.bridges.append(b);return b

    def cleanup(self):
        for b in self.bridges:
            b._native_inflight=False;b.close()
            shared._RETAINED_BRIDGES.discard(b)

    def acquire(self,identity,frida,source,epoch,owner,message,detached,before,check):
        self.assertEqual(identity,(999,123));self.assertEqual(epoch,self.root/"acquisition-native-epochs.json")
        before();self.acquire_count+=1
        def submit(request):
            self.requests.append(request)
            event=self.event(request["persuasion"]["round_key"])
            self.assertEqual(event["status"],"pending")
            if self.send:
                response=dict(self.response,token=request["token"],round_key=request["persuasion"]["round_key"])
                message(dict(type="send",payload=response),None)
        return SimpleNamespace(session=self.session,script=SimpleNamespace(exports_sync=SimpleNamespace(submit=submit)),
                               previous_token=None,prepare=self.prepare,release=self.release)

    def event(self,key="a"*64):
        return json.loads(self.bridge.journal.read_text("utf8"))["rounds"][key]

    def test_request_uses_persuasion_payload_and_shared_epoch(self):
        outcome=self.bridge.solve(state());request=self.requests[0]
        self.assertEqual(request["operation"],"persuasion_success")
        self.assertEqual(request["parameter_count"],2)
        self.assertNotIn("minigame",request);self.assertNotIn("anchors",request["persuasion"])
        self.assertEqual(request["persuasion"]["session_id"],4)
        self.assertEqual(self.event()["status"],"verified")
        self.assertFalse(outcome["settlement_verified"])
        self.release.assert_called_once_with(self.bridge)

    def test_oversized_proofs_are_rejected_before_connection(self):
        for mode in ("size", "count", "envelope"):
            invalid=state()
            if mode=="size":invalid["native"]["anchors"][0]["size"]=4097
            elif mode=="count":invalid["native"]["anchors"]*=20001
            else:invalid["native"]["padding"]="x"*(8*1024*1024)
            with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.acquire_count,0);self.assertEqual(self.requests,[])

    def test_same_session_second_gui_cannot_replay(self):
        self.bridge.solve(state())
        with self.assertRaises(Refused):self.new_bridge().solve(state())
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.acquire_count,1)

    def test_request_busy_or_changed_after_connection_never_submits(self):
        self.adapter.prepare_solve.side_effect=Refused("input pending")
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.acquire_count,0)
        changed=state();changed["identity"]=("new session",)
        self.adapter.prepare_solve.side_effect=[state(),changed]
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.requests,[])
        self.assertEqual(self.event()["status"],"not_dispatched")

    def test_timeout_preserves_unknown_and_cannot_be_resent(self):
        self.send=False
        with patch.object(shared.threading.Event,"wait",return_value=False),self.assertRaises(UncertainWrite):
            self.bridge.solve(state())
        self.assertEqual(self.event()["status"],"unknown")
        self.release.assert_not_called()
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(len(self.requests),1)

    def test_safe_rejection_can_refresh_but_called_rejection_is_unknown(self):
        self.response=dict(status="rejected",called=False,reason="flow cancelled")
        with self.assertRaises(Refused):self.bridge.solve(state())
        self.assertEqual(self.event()["status"],"rejected")
        self.bridge._require_unused("a"*64)
        self.response=dict(status="rejected",called=True,reason="unexpected")
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(self.event()["status"],"unknown")

    def test_return_without_confirmation_or_log_failure_never_becomes_not_called(self):
        self.adapter.verify_native.side_effect=UncertainWrite("markers changed")
        with self.assertRaises(UncertainWrite):self.bridge.solve(state())
        self.assertEqual(self.event()["status"],"unknown")
        with self.assertRaises(Refused):self.new_bridge().solve(state())
        self.assertEqual(len(self.requests),1)

    def test_next_session_reuses_existing_transport_without_unload(self):
        self.bridge.solve(state())
        new=state("b");new["identity"]=("game",5);new["native"]["session_id"]=5
        self.bridge.solve(new)
        self.assertEqual(len(self.requests),2)
        self.assertEqual(self.prepare.call_count,2)
        self.assertEqual(self.release.call_count,2)
        self.assertNotEqual(self.requests[0]["token"],self.requests[1]["token"])


if __name__ == "__main__":
    unittest.main()
