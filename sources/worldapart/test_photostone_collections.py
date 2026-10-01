"""Task-owner and usage fixtures retain the live IL2CPP collection shapes."""
import struct
import unittest
from unittest.mock import Mock

from photostone_adapter import PhotostoneResolver
from write_guard import Refused


class QuestReader(PhotostoneResolver):
    def __init__(self, rows=(), *, initialized=True):
        self.meta=0x100000
        self.specs={".QuestSpecialStateOwner":{"type_definition_offset":0x300}}
        self.rows=list(rows);self.initialized=initialized;self.count=len(rows)
        self.kind=0x11;self.bad_stride=False;self.decoded=0
        self.links=[];self.anchors=[]
    def obj(self,a,name):return {"klass":hex(a),"name":name}
    def info(self,a,name=None):return self.array_element(None,None,name)
    def array_element(self,*args):
        self.decoded+=1
        return dict(klass="0x9000",instance_size=40 if self.bad_stride else 36,
                    fields=[dict(name="value",type_data=(struct.pack("<Q",self.meta+0x300)+b"\0\0"+bytes([self.kind])+bytes(5)).hex())])
    def ptr(self,a,c,n,*args):
        return {"_slots":0x3000,"_buckets":0x4000}[n] if self.initialized else 0
    def scalar(self,a,c,n,*args):return {"_count":self.count,"_lastIndex":len(self.rows),"_freeList":-1,"_version":8}[n]
    def offset(self,c,n,k,*args):return {"hashCode":16,"next":20,"value":24}[n]
    def link(self,a):return 0x9000
    def q(self,a,**kw):return max(3,len(self.rows))
    def anchor(self,a,size):
        if a==0x4020:return bytes(size)
        return b"".join(struct.pack("<iiiii",*r) for r in self.rows)


class TaskOwnerTests(unittest.TestCase):
    def test_initialized_slots_decode_three_distinct_ids(self):
        rr=QuestReader([(9,-1,501,193401,17)])
        rows,d=rr.quest_owners(0x1000)
        self.assertEqual(rows,[dict(quest_id=501,npc_id=193401,sub_id=17,slot="0x3020")])
        self.assertEqual((d["kind"],d["count"],d["last_index"],d["capacity"]),("hashset",1,1,3))

    def test_empty_unallocated_set_still_checks_slot_type(self):
        rr=QuestReader(initialized=False)
        self.assertEqual(rr.quest_owners(0x1000)[0],[])
        self.assertGreater(rr.decoded,0)
        for attr,value in (("kind",8),("bad_stride",True)):
            rr=QuestReader(initialized=False);setattr(rr,attr,value)
            with self.subTest(attr=attr),self.assertRaises(Refused):rr.quest_owners(0x1000)

    def test_freed_slot_is_not_a_task_owner(self):
        rr=QuestReader([(-1,-1,0,0,0),(8,-1,12,100231,2)]);rr.count=1
        self.assertEqual(len(rr.quest_owners(0x1000)[0]),1)

    def test_duplicate_invalid_and_broken_chain_fail_closed(self):
        for rows in ([(1,-1,1,2,3),(1,-1,1,2,3)],[(1,-1,0,2,3)],[(1,5,1,2,3)]):
            with self.subTest(rows=rows),self.assertRaises(Refused):QuestReader(rows).quest_owners(0x1000)

    def test_count_mismatch_or_missing_array_fails_closed(self):
        rr=QuestReader([(1,-1,1,2,3)]);rr.count=0
        with self.assertRaises(Refused):rr.quest_owners(0x1000)
        rr=QuestReader([(1,-1,1,2,3)],initialized=False)
        with self.assertRaises(Refused):rr.quest_owners(0x1000)


class UsageTests(unittest.TestCase):
    def reader(self,action=17,used=2,cycle=103020005):
        rr=PhotostoneResolver.__new__(PhotostoneResolver)
        rr.dictionary=Mock(return_value=({action:0x7000},{"entries":"0x6000","count":1,"free":0,"items":[{"key":action,"value":"0x7000"}]}))
        rr.obj=Mock(return_value={"klass":"0x7100"})
        rr.scalar=Mock(return_value=used)
        rr.offset=Mock(return_value=24)
        rr.anchor=Mock(return_value=struct.pack("<q",cycle))
        return rr

    def test_full_record_cycle_and_count_are_preserved(self):
        rr=self.reader(cycle=2**40)
        result=rr.usage_records(0x6000)
        self.assertEqual(result["records"],[dict(action_id=17,record="0x7000",used_count=2,cycle_key=2**40)])
        rr.dictionary.assert_called_once_with(0x6000,8,0x12,maximum=1024)
        rr.anchor.assert_called_once_with(0x7018,8)

    def test_empty_usage_is_known_empty(self):
        rr=self.reader();rr.dictionary.return_value=({},dict(count=0,items=[]))
        self.assertEqual(rr.usage_records(0x6000)["records"],[])
        rr.obj.assert_not_called()

    def test_invalid_usage_is_not_silently_omitted(self):
        for action,used in ((0,1),(17,-1)):
            with self.subTest(action=action,used=used),self.assertRaises(Refused):
                self.reader(action,used).usage_records(0x6000)


class ArrayElementTests(unittest.TestCase):
    def reader(self,array_kind=0x1d,element_kind=0x15,klass=0x9000):
        rr=PhotostoneResolver.__new__(PhotostoneResolver)
        field=struct.pack("<Q",0x2000)+b"\0\0"+bytes([array_kind])+bytes(5)
        owner=dict(fields=[dict(name="_slots",type_data=field.hex())])
        rr.anchor=Mock(return_value=struct.pack("<Q",0x3000)+b"\0\0"+bytes([element_kind])+bytes(5))
        rr.link=Mock(return_value=klass);rr.info=Mock(return_value=dict(klass=hex(klass)))
        return rr,owner

    def test_reads_element_declaration_without_collection_objects(self):
        rr,c=self.reader()
        self.assertEqual(rr.array_element(c,"_slots",".Slot"),dict(klass="0x9000"))
        rr.anchor.assert_called_once_with(0x2000,16)
        rr.link.assert_called_once_with(0x3018)

    def test_wrong_or_uninitialized_metadata_refuses(self):
        for kwargs in ({"array_kind":0x12},{"element_kind":8},{"klass":0}):
            rr,c=self.reader(**kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(Refused):rr.array_element(c,"_slots",".Slot")


if __name__=="__main__":unittest.main()
