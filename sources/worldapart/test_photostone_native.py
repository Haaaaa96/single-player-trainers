"""Exercise the real inherited lifecycle and durable journal with fake transport."""
from copy import deepcopy
from unittest.mock import patch
import unittest

import test_dual_cultivation_native as shared_tests
from photostone_native import PhotostoneNative
from write_guard import Refused


def state(mode="next"):
    proof=[dict(address="0x1000",size=1,expected_hex="00")]
    data=dict(mode=mode,round_key="a"*64,npc_id=100000,sub_id=11,world="0x1000",player="0x2000",
              npc="0x3000",logic_manager="0x4000",logic_class="0x4100",runtime="0x5000",
              stats="0x6000",usage="0x7000",active_special=0,stats_before=[],entry="0x8000",
              entry_class="0x8100",entry_config=dict(game_type=1),date=[1,1,1,0],date_address="0x9000",
              methods=dict(set="0xA000",force="0xA100",meets="0xA200"),
              owner_links=[dict(address="0x1000",expected="0x2000")],post_stable_anchors=proof,
              npc_dictionary={},static_ids={},quest_owners={},statistics={},usage_state={},
              force_confirmed=mode=="force",anchors=proof)
    return dict(identity=("game",123),mode=mode,native=data)


class PhotostoneLifecycleTests(shared_tests.MiniOnceTests):
    def setUp(self):
        p=patch.object(shared_tests,"state",side_effect=state)
        p.start();self.addCleanup(p.stop)
        super().setUp()

    def new_bridge(self):
        b=PhotostoneNative(self.game,self.resolver)
        self.bridges.append(b);return b

    def test_success_and_shared_protocol(self):
        result=self.bridge.solve(state())
        self.assertEqual(result["phase"],"settling")
        request=self.requests[0]
        self.assertEqual(request["operation"],"photostone_activate")
        self.assertEqual(request["parameter_count"],3)
        self.assertNotIn("anchors",request["photostone"])
        self.assertEqual(self.event()["status"],"verified")
        self.connections[0].release.assert_called_once_with(self.bridge)

    def test_missing_proof_never_acquires(self):
        invalid=state();invalid["native"]["owner_links"]=[]
        self.resolver.prepare_solve.side_effect=lambda _:invalid
        with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.connections,[])

    def test_force_protocol_has_distinct_method_and_explicit_confirmation(self):
        req=self.bridge._request(state("force"),999,"token")
        self.assertEqual(req["operation"],"photostone_force_replay")
        self.assertEqual(req["parameter_count"],2)
        invalid=state("force");invalid["native"]["force_confirmed"]=False
        with self.assertRaises(Refused):self.bridge._request(invalid,999,"token")

    def test_noop_active_entry_never_attaches(self):
        invalid=state();invalid["native"]["active_special"]=11
        self.resolver.prepare_solve.side_effect=lambda _:invalid
        with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.connections,[])

    def test_non_photo_config_is_rejected_before_attach(self):
        invalid=state();invalid["native"]["entry_config"]["game_type"]=2
        self.resolver.prepare_solve.side_effect=lambda _:invalid
        with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.connections,[])

    def test_oversized_proof_refuses_before_attach(self):
        for proof in ([dict(address="0x1000",size=4097,expected_hex="00"*4097)],
                      [dict(address="0x1000",size=1,expected_hex="00")]*20001):
            invalid=state();invalid["native"]["anchors"]=proof
            self.resolver.prepare_solve.side_effect=lambda _:invalid
            with self.assertRaises(Refused):self.bridge.solve(invalid)
            self.assertEqual(self.connections,[])

    def test_oversized_complete_request_refuses_before_attach(self):
        invalid=state();invalid["native"]["extra"]="x"*(8*1024*1024)
        self.resolver.prepare_solve.side_effect=lambda _:invalid
        with self.assertRaises(Refused):self.bridge.solve(invalid)
        self.assertEqual(self.connections,[])


if __name__=="__main__":unittest.main()
