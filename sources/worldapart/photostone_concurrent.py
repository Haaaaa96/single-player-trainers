"""Canonical readonly ConcurrentDictionary NPC membership; never call a getter."""
import struct
from write_guard import Refused


def anchor_block(rr, address, size):
    """Keep each proof item within the existing broker/bridge 4096-byte limit."""
    if type(size) is not int or not 0 <= size <= 1024*1024:
        raise Refused("NPC 集合读取块大小无效。")
    return b"".join(rr.anchor(address+offset,min(4096,size-offset)) for offset in range(0,size,4096))


def _value_type(rr, klass, field_name, fullname):
    field = next(f for f in klass["fields"] if f["name"] == field_name)
    raw = bytes.fromhex(field["type_data"])
    spec = rr.runtime_spec(fullname, rr.specs[fullname])
    if raw[10] != 0x11 or struct.unpack_from("<Q", raw)[0] != rr.meta + spec["type_definition_offset"]:
        raise Refused("NPC 并发字典值类型包装与已审核元数据不同。")


def read_concurrent(rr, address, flavor, *, max_nodes=4096, max_buckets=16384):
    """Return normalized keys/values plus a main-thread verifiable descriptor.

    npc: EntityID(String UUID) -> NpcModel. static: TbNpcBaseCfgId -> EntityID.
    space: SpaceUuid(String UUID) -> SpaceModel, for isolated display reads only.
    ConcurrentDictionary has no version counter; pin the full bucket array,
    counts, every traversed node and every EntityID string, then recheck proof.
    """
    if flavor not in ("npc", "static", "space"):
        raise Refused("未审核的 NPC 并发字典类型。")
    dc = rr.obj(address,"System.Collections.Concurrent.ConcurrentDictionary`2")
    tables = rr.ptr(address,dc,"_tables",0x15,0x10)
    tc = rr.obj(tables,".Tables")
    buckets = rr.ptr(tables,tc,"_buckets",0x1D,0x10)
    locks = rr.ptr(tables,tc,"_locks",0x1D,0x18)
    counts = rr.ptr(tables,tc,"_countPerLock",0x1D,0x20)
    bc = rr.obj(buckets,".Node[]")
    node_class = rr.link(int(bc["klass"],16)+0x40)
    nc = rr.info(node_class,".Node")
    rr.obj(locks,"System.Object[]")
    cc = rr.obj(counts,"System.Int32[]")
    rr.info(rr.link(int(cc["klass"],16)+0x40),"System.Int32")
    bucket_count = rr.q(buckets+24,anchored=True)
    lock_count = rr.q(locks+24,anchored=True)
    count_count = rr.q(counts+24,anchored=True)
    if not 1 <= bucket_count <= max_buckets or not 1 <= lock_count == count_count <= min(4096,bucket_count):
        raise Refused("NPC 并发字典容量异常。")
    heads_raw = anchor_block(rr,buckets+32,bucket_count*8)
    anchor_block(rr,locks+32,lock_count*8)
    count_values = struct.unpack("<"+"i"*lock_count,anchor_block(rr,counts+32,lock_count*4))
    if any(n<0 for n in count_values) or sum(count_values)>max_nodes:
        raise Refused("NPC 并发字典计数异常。")
    if nc["instance_size"] != 48:
        raise Refused("NPC 并发字典节点大小不同。")
    rr.offset(nc,"_key",0x11,0x10)
    rr.offset(nc,"_value",0x11 if flavor=="static" else 0x12,0x18)
    rr.offset(nc,"_next",0x15,0x20)
    rr.offset(nc,"_hashcode",8,0x28)
    _value_type(rr,nc,"_key",{"npc":"SimpleSave.EntityID", "static":"LubanDatas.TbNpcBaseCfgId",
                             "space":"Game.Model.SpaceUuid"}[flavor])
    if flavor=="static":
        _value_type(rr,nc,"_value","SimpleSave.EntityID")
    result,items,visited = {},[],set()
    observed_counts=[0]*lock_count
    for bucket,head in enumerate(struct.unpack("<"+"Q"*bucket_count,heads_raw)):
        node=head
        while node:
            if node in visited or len(visited)>=max_nodes:
                raise Refused("NPC 并发字典包含循环或重复节点。")
            visited.add(node)
            if rr.link(node)!=node_class:
                raise Refused("NPC 并发字典节点类型变化。")
            data=rr.anchor(node+16,28)
            next_node=struct.unpack_from("<Q",data,16)[0]
            hashed=struct.unpack_from("<i",data,24)[0]
            if (hashed&0x7FFFFFFF)%bucket_count!=bucket:
                raise Refused("NPC 并发字典散列桶归属不符。")
            wire=dict(node=hex(node),next=hex(next_node),hashcode=hashed,bucket=bucket)
            if flavor in ("npc", "space"):
                key_pointer,value=struct.unpack_from("<QQ",data)
                key=rr.string(key_pointer)
                wire.update(key=key,value=hex(value),key_pointer=hex(key_pointer))
                if not value or value%8:
                    raise Refused("NPC 并发字典角色对象为空或未对齐。")
            else:
                key=struct.unpack_from("<i",data)[0]
                value_pointer=struct.unpack_from("<Q",data,8)[0]
                value=rr.string(value_pointer)
                wire.update(key=key,value=value,value_pointer=hex(value_pointer))
                if key<=0:
                    raise Refused("静态角色编号无效。")
            if key in result:
                raise Refused("NPC 并发字典存在重复逻辑编号。")
            result[key]=value;items.append(wire);observed_counts[bucket%lock_count]+=1
            node=next_node
    if tuple(observed_counts)!=count_values:
        raise Refused("NPC 并发字典读取期间计数变化。")
    return result,dict(kind="concurrent",flavor=flavor,address=hex(address),tables=hex(tables),
                       buckets=hex(buckets),locks=hex(locks),count_per_lock=hex(counts),
                       bucket_count=bucket_count,lock_count=lock_count,count=len(result),items=items)
