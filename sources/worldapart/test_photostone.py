"""Offline policy and collection failures, including UUID-keyed NPC dictionaries."""
from copy import deepcopy
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import photostone_adapter as pa
from photostone_logic import build_rows, replay_preview, verify_statistics
from write_guard import Refused, UncertainWrite


def catalog():
    return [dict(npc_id=100,name="测试角色",stage=s,sub_id=10+s,depends_sub_id=10+s-1 if s>1 else None,
                 max_success=1,game_param=s,reward=600+s,unlock_intimacy=0,priority=1,weight=75,
                 cost_stamina=10,category="regular") for s in (1,2,3)]


def npc(**kw):
    return dict(stats={},runtime=0x2000,active_special=0,canonical=True,world_status=0,
                intimacy=10,quest_owned=False,config_verified={11:True,12:True,13:True},identity=(1,2),**kw)


class PolicyTests(unittest.TestCase):
    def rows(self, changes=None, **kw):
        n=npc();n.update(changes or {});return build_rows(catalog(),{100:n},**kw)["rows"]

    def test_only_first_unfinished_stage_activates(self):
        self.assertEqual([r["can_activate"] for r in self.rows()],[True,False,False])
        self.assertEqual([r["can_activate"] for r in self.rows({"stats":{11:1}})],[False,True,False])

    def test_dependency_is_contains_key_not_positive_count(self):
        rows=self.rows({"stats":{11:0}})
        self.assertTrue(rows[1]["dependency_met"])
        self.assertFalse(rows[1]["can_activate"])
        self.assertTrue(rows[1]["can_force"])
        self.assertFalse(rows[2]["can_force"])

    def test_completion_never_inferred_from_inventory(self):
        rows=self.rows({"stats":{11:1},"inventory_images":[]})
        self.assertTrue(rows[0]["completed"])
        self.assertFalse(self.rows({"inventory_images":[1,2,3]})[0]["completed"])

    def test_missing_npc_unknown_not_zero(self):
        s=build_rows(catalog(),{})
        self.assertEqual(s["counts"]["known"],0)
        self.assertIsNone(s["rows"][0]["success_count"])
        self.assertFalse(s["rows"][0]["can_force"])

    def test_task_and_deprecated_excluded_from_regular_denominator(self):
        cs=catalog();cs[0]["category"]="quest_pet";cs[1]["category"]="deprecated"
        s=build_rows(cs,{100:npc()})
        self.assertEqual(s["counts"]["regular"],1)
        self.assertEqual(s["counts"]["quest_pet"],1)
        self.assertEqual(s["counts"]["deprecated"],1)
        self.assertFalse(s["rows"][0]["can_force"])

    def test_all_unsafe_contexts_block_both_modes(self):
        for change in [{"canonical":False},{"world_status":1},{"world_status":2},
                       {"stats":None},{"runtime":0},{"quest_owned":True},
                       {"active_special":999},{"intimacy":-1},{"config_verified":{}}]:
            with self.subTest(change=change):
                row=self.rows(change)[0]
                self.assertFalse(row["can_activate"]);self.assertFalse(row["can_force"])
        row=self.rows(context_reason="正在战斗")[0]
        self.assertFalse(row["can_activate"]);self.assertFalse(row["can_force"])

    def test_same_active_stage_never_clears_statistics(self):
        for stats in ({},{11:0},{11:1}):
            row=self.rows({"stats":stats,"active_special":11})[0]
            self.assertFalse(row["can_activate"]);self.assertFalse(row["can_force"])

    def test_replay_preview_records_real_effect_not_fake_completion(self):
        row=self.rows({"stats":{11:1,12:1,13:1}})[0]
        p=replay_preview(row)
        self.assertEqual(p["effects"]["previous_success_count"],1)
        self.assertFalse(p["effects"]["resets_other_stages"])
        self.assertFalse(p["effects"]["grants_rewards"])
        self.assertIn("失败或中途退出不会自动恢复",p["message"])

    def test_unknown_stage_preview_refuses(self):
        with self.assertRaises(Refused):replay_preview(self.rows()[2])

    def test_verify_exact_statistics_difference(self):
        before={11:1,12:0,13:2}
        self.assertTrue(verify_statistics(before,before,mode="next",sub_id=11))
        self.assertTrue(verify_statistics(before,{12:0,13:2},mode="force",sub_id=11))
        for invalid in ({},{11:0,12:0,13:2},{12:1,13:2},{12:0}):
            with self.subTest(invalid=invalid),self.assertRaises(UncertainWrite):
                verify_statistics(before,invalid,mode="force",sub_id=11)

    def test_actual_catalog_has_expected_coverage_and_exclusions(self):
        self.assertEqual(len(pa.CATALOG),63)
        self.assertEqual(len({r["npc_id"] for r in pa.CATALOG}),25)
        s=build_rows(pa.CATALOG,{})
        self.assertEqual(s["counts"]["regular"],57)
        self.assertEqual(s["counts"]["quest_pet"],3)
        self.assertEqual(s["counts"]["deprecated"],3)


class DictReader(pa.PhotostoneResolver):
    def __init__(self, key_kind=8, value_kind=8, rows=None):
        self.key_kind,self.value_kind=key_kind,value_kind
        self.rows=rows if rows is not None else [(10,1)]
        self.free=0;self.version=7;self.next_override=None;self.bad_stride=False
        self.anchors=[];self.links=[]
        self.value_offset=16 if key_kind==14 or value_kind in (14,18) else 12
        self.stride=24 if self.value_offset==16 else 16
        self.strings={0x7000:"uuid-one",0x7010:"uuid-two"}
    def obj(self,a,name):return self.info(a,name)
    def info(self,a,name=None):return {"klass":hex(a),"instance_size":16+self.stride+(4 if self.bad_stride else 0)}
    def array_element(self,*args):return self.info(0x5000)
    def link(self,a):return 0x5000
    def ptr(self,a,c,n,*args):return 0x3000
    def scalar(self,a,c,n,*args):return {"_count":len(self.rows),"_freeCount":self.free,"_version":self.version,"_freeList":-1}[n]
    def offset(self,c,n,k,*args):
        if k != {"hashCode":8,"next":8,"key":self.key_kind,"value":self.value_kind}[n]:
            raise Refused("fixture field kind differs")
        return {"hashCode":16,"next":20,"key":24,"value":16+self.value_offset}[n]
    def q(self,a,**kw):return max(3,len(self.rows))
    def string(self,a):return self.strings[a]
    def anchor(self,a,size):
        out=b""
        for index,(key,val) in enumerate(self.rows):
            row=bytearray(self.stride);struct.pack_into("<ii",row,0,index,self.next_override if self.next_override is not None else -1)
            struct.pack_into("<Q" if self.key_kind==14 else "<i",row,8,key)
            struct.pack_into("<Q" if self.value_kind in (14,18) else "<i",row,self.value_offset,val)
            out+=row
        return bytes(out)


class DictionaryTests(unittest.TestCase):
    def test_integer_statistics(self):
        result,d=DictReader(rows=[(11,0),(12,2)]).dictionary(0x1000,8,8)
        self.assertEqual(result,{11:0,12:2});self.assertEqual(d["version"],7)
        self.assertEqual(d["stride"],16)

    def test_actual_statistics_key_wrapper_cannot_be_read_as_bare_int(self):
        rr=DictReader(0x11,8,[(11,0),(12,2)])
        with self.assertRaises(Refused):rr.dictionary(0x1000,8,8)
        with patch.object(pa,"_value_type") as wrapped:
            values,d=rr.dictionary(0x1000,0x11,8,key_type="LubanDatas.TbNpcInteractGameEntrySubid")
        self.assertEqual(values,{11:0,12:2})
        self.assertEqual((d["keyKind"],d["stride"]),(0x11,16))
        self.assertEqual(wrapped.call_args.args[2:],("key","LubanDatas.TbNpcInteractGameEntrySubid"))

    def test_world_uuid_key_is_never_npc_cfg_id(self):
        result,d=DictReader(14,18,[(0x7000,0x8000)]).dictionary(0x1000,14,18)
        self.assertEqual(result,{"uuid-one":0x8000})
        self.assertEqual(d["items"][0]["key_pointer"],"0x7000")

    def test_static_id_map_returns_uuid_for_second_lookup(self):
        result,d=DictReader(17,14,[(100000,0x7000)]).dictionary(0x1000,17,14)
        self.assertEqual(result,{100000:"uuid-one"})
        self.assertEqual(d["items"][0]["value"],"0x7000")

    def test_duplicate_or_free_count_mismatch_refuses(self):
        for rr in (DictReader(rows=[(11,1),(11,2)]),DictReader()):
            if len(rr.rows)==1:rr.free=1
            with self.assertRaises(Refused):rr.dictionary(0x1000,8,8)

    def test_layout_and_chain_refuse(self):
        rr=DictReader();rr.bad_stride=True
        with self.assertRaises(Refused):rr.dictionary(0x1000,8,8)
        rr=DictReader();rr.next_override=99
        with self.assertRaises(Refused):rr.dictionary(0x1000,8,8)


class AdapterTests(unittest.TestCase):
    def fixture(self):
        adapter=pa.PhotostoneAdapter.__new__(pa.PhotostoneAdapter)
        adapter.game=SimpleNamespace(blocked=False,write_enabled=True,stamp=("game",123),resolver=object(),record=Mock())
        adapter.blocked=False
        adapter.resolver=SimpleNamespace(reader=SimpleNamespace(h=1),read=Mock(return_value=build_rows(catalog(),{100:npc()})))
        adapter.native=Mock()
        return adapter

    def test_snapshot_never_invokes_native_methods(self):
        a=self.fixture()
        with patch.object(pa,"process_identity",return_value=a.game.stamp):state=a.snapshot()
        self.assertEqual(len(state["rows"]),3)
        a.native.solve.assert_not_called();a.native.close.assert_not_called()

    def test_process_replaced_refuses_before_read(self):
        a=self.fixture()
        with patch.object(pa,"process_identity",return_value=("game",456)),self.assertRaises(Refused):a.snapshot()
        a.resolver.read.assert_not_called()

    def test_stale_row_refuses(self):
        a=self.fixture();a.snapshot=Mock(return_value=build_rows(catalog(),{100:npc()}))
        row=deepcopy(a.snapshot()["rows"][0]);row["identity"]="stale"
        with self.assertRaises(Refused):a.prepare_next(row)

    def test_force_requires_confirmation_and_current_preview(self):
        a=self.fixture();a.snapshot=Mock(return_value=build_rows(catalog(),{100:npc()}))
        p=a.preview_force(a.snapshot()["rows"][0])
        with self.assertRaises(Refused):a.force(p)
        bad=deepcopy(p);bad["message"]="edited"
        with self.assertRaises(Refused):a.force(bad,confirmed=True)
        a.native.solve.assert_not_called()
        a.force(p,confirmed=True);self.assertTrue(a.native.solve.call_args.args[0]["force_confirmed"])
        a.game.record.assert_called_once()

    def test_uncertain_dispatch_blocks_adapter_without_retry(self):
        a=self.fixture();a.native.solve.side_effect=UncertainWrite("lost")
        with self.assertRaises(UncertainWrite):a._dispatch({})
        self.assertTrue(a.blocked);a.native.solve.assert_called_once()

    def test_readonly_or_missing_write_authority_never_dispatches(self):
        for missing in (False,True):
            a=self.fixture();a.game.write_enabled=False
            if missing:del a.game.write_enabled
            with self.assertRaises(Refused):a._dispatch({})
            a.native.solve.assert_not_called()


if __name__ == "__main__":unittest.main()
