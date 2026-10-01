"""Immutable byte fixtures for the actual EntityID ConcurrentDictionary layout."""
import struct
import unittest
from photostone_concurrent import read_concurrent
from write_guard import Refused


class Reader:
    def runtime_spec(self, fullname, reviewed=None):
        return self.specs[fullname]

    def __init__(self, flavor="npc"):
        self.meta=0x100000;self.specs={"SimpleSave.EntityID":{"type_definition_offset":0x100},"LubanDatas.TbNpcBaseCfgId":{"type_definition_offset":0x200}}
        self.memory={};self.flavor=flavor;self.anchors=[]
        self.node_class=0x9000
        key_type="SimpleSave.EntityID" if flavor=="npc" else "LubanDatas.TbNpcBaseCfgId"
        def field(name,full):return dict(name=name,type_data=(struct.pack("<Q",self.meta+self.specs[full]["type_definition_offset"])+b"\0\0\x11\0"+bytes(4)).hex())
        self.nodeinfo=dict(klass=hex(self.node_class),instance_size=48,fields=[field("_key",key_type),field("_value","SimpleSave.EntityID")])
        self.put(0x3018,struct.pack("<Q",3));self.put(0x4018,struct.pack("<Q",2));self.put(0x5018,struct.pack("<Q",2))
        self.put(0x3020,struct.pack("<QQQ",0,0x6000,0));self.put(0x4020,struct.pack("<QQ",0xD000,0xD100));self.put(0x5020,struct.pack("<ii",0,1))
        self.put(0x6000,struct.pack("<Q",self.node_class))
        data=bytearray(28)
        if flavor=="npc":struct.pack_into("<QQ",data,0,0x7000,0x8000)
        else:struct.pack_into("<i",data,0,100000);struct.pack_into("<Q",data,8,0x7000)
        struct.pack_into("<Qi",data,16,0,1);self.put(0x6010,data)
    def put(self,a,b):
        for i,x in enumerate(b):self.memory[a+i]=x
    def anchor(self,a,n):
        raw=bytes(self.memory[a+i] for i in range(n));self.anchors.append((a,raw.hex()));return raw
    def q(self,a,**kw):return struct.unpack("<Q",self.anchor(a,8))[0]
    def obj(self,a,name):return dict(klass=hex(a+0x10000),name=name)
    def info(self,a,name=None):return self.nodeinfo if name==".Node" else dict(klass=hex(a))
    def ptr(self,a,c,n,*args):return {"_tables":0x2000,"_buckets":0x3000,"_locks":0x4000,"_countPerLock":0x5000}[n]
    def link(self,a):return self.node_class if a in (0x13040,0x15040) else self.q(a)
    def offset(self,c,n,k,expected):return expected
    def string(self,p):
        if p!=0x7000:raise Refused("wrong UUID")
        return "45ed0f07-d7ba-446b-a759-9b342798d593"


class ConcurrentTests(unittest.TestCase):
    def test_wrapped_uuid_key_is_normalized(self):
        rr=Reader();values,d=read_concurrent(rr,0x1000,"npc")
        self.assertEqual(list(values.values()),[0x8000]);self.assertEqual(d["kind"],"concurrent")
        self.assertEqual(d["items"][0]["key_pointer"],"0x7000")
        self.assertTrue(any(a==0x3020 for a,_ in rr.anchors))

    def test_static_wrapper_maps_to_same_uuid(self):
        rr=Reader("static");values,d=read_concurrent(rr,0x1000,"static")
        self.assertEqual(values[100000],"45ed0f07-d7ba-446b-a759-9b342798d593")
        self.assertEqual(d["items"][0]["value_pointer"],"0x7000")

    def test_bucket_above_4096_can_be_valid_empty(self):
        rr=Reader();rr.put(0x3018,struct.pack("<Q",4477));rr.put(0x3020,bytes(4477*8))
        # Use disjoint storage because the expanded bucket fixture overlaps the
        # original small fake arrays; redirect locks/counts beyond the buckets.
        old=rr.ptr
        rr.ptr=lambda a,c,n,*args: {"_locks":0x20000,"_countPerLock":0x25000}.get(n,old(a,c,n,*args))
        rr.put(0x20018,struct.pack("<Q",1536));rr.put(0x25018,struct.pack("<Q",1536));rr.put(0x20020,bytes(1536*8));rr.put(0x25020,bytes(1536*4))
        rr.link=lambda a:rr.node_class if a in (0x13040,0x35040) else rr.q(a)
        self.assertEqual(read_concurrent(rr,0x1000,"npc")[0],{})
        self.assertLessEqual(max(len(raw)//2 for _,raw in rr.anchors),4096)

    def test_wrong_wrapper_metadata_refuses(self):
        rr=Reader();rr.nodeinfo["fields"][0]["type_data"]="00"*16
        with self.assertRaises(Refused):read_concurrent(rr,0x1000,"npc")

    def test_wrong_bucket_cycle_and_count_refuse(self):
        for target,data in [(0x6028,struct.pack("<i",2)),(0x6020,struct.pack("<Q",0x6000)),(0x5020,struct.pack("<ii",1,0))]:
            rr=Reader();rr.put(target,data)
            with self.subTest(target=hex(target)),self.assertRaises(Refused):read_concurrent(rr,0x1000,"npc")

    def test_limits_are_bounded(self):
        rr=Reader();rr.put(0x3018,struct.pack("<Q",20000))
        with self.assertRaises(Refused):read_concurrent(rr,0x1000,"npc")


if __name__=="__main__":unittest.main()
