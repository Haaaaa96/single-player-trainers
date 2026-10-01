"""Read-only canonical NPC checklist; two explicit shared-broker activations."""
import json
import struct
from contextlib import contextmanager

from acquisition_context import _Context, require_safe_acquisition_context, AcquisitionContextRefused
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite
from photostone_logic import build_rows, fingerprint, replay_preview, verify_statistics
from photostone_concurrent import read_concurrent, _value_type

SPECS = json.loads((RESOURCE_ROOT / "photostone_specs.json").read_text(encoding="utf8"))
CATALOG = json.loads((RESOURCE_ROOT / "photostone_catalog.json").read_text(encoding="utf8"))["rows"]
NPC_IDS = frozenset(row["npc_id"] for row in CATALOG)


class PhotostoneResolver(RegisteredMiniResolver):
    def __init__(self, game):
        self._class_cache = {}
        super().__init__(game.resolver.reader, SPECS["metadata"], "", metadata_base=game.resolver.meta)
        self.game = game
        self.links = []
        self._read_specs = None

    @contextmanager
    def metadata_read_scope(self):
        # Reuse metadata checks only within ONE read. Every used definition is
        # checked again before returning; refreshes and native preparation do
        # not inherit this cache. Object/field anchors still get fresh proofs.
        self._class_cache = {}
        self._read_specs = {}
        try:
            yield
            if hasattr(self, '_runtime'):
                for fullname in self._read_specs:
                    self._runtime.specs[fullname]
        finally:
            self._read_specs = None
            self._class_cache = {}

    def runtime_spec(self, fullname, reviewed_spec=None):
        cache = getattr(self, '_read_specs', None)
        if cache is None:
            return super().runtime_spec(fullname, reviewed_spec)
        required = frozenset(f['name'] for f in (reviewed_spec or {}).get('fields', []))
        cached = cache.get(fullname)
        if cached is not None and required <= cached[1]:
            return cached[0]
        spec = super().runtime_spec(fullname, reviewed_spec)
        cache[fullname] = spec, required | (cached[1] if cached else frozenset())
        return spec

    def info(self, klass, fullname=None):
        # Use LearningResolver's inspector directly: every concrete or inflated
        # type below is verified against this feature's exact metadata manifest.
        cached = self._class_cache.get(klass)
        if cached is not None:
            if fullname is not None and cached["namespace"] + "." + cached["name"] != fullname:
                raise Refused("留影对象类型不匹配。")
            return cached
        from learning_adapter import LearningResolver
        c = LearningResolver.info(self, klass)
        actual = c["namespace"] + "." + c["name"]
        if fullname is not None and fullname != actual:
            raise Refused("留影对象类型不匹配。")
        spec = self.specs.get(actual)
        if spec is not None:
            spec = self.runtime_spec(actual, spec)
            handle = self.q(klass + 0x68, anchored=True)
            if not handle:
                generic = self.q(klass + 0x60, anchored=True)
                if not generic:
                    raise Refused("留影泛型元数据不存在。")
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] not in (0x11, 0x12) or self.q(generic + 24, anchored=True) != klass:
                    raise Refused("留影泛型定义不一致。")
                handle = struct.unpack_from("<Q", raw)[0]
            if (handle != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or len(c["fields"]) != spec["field_count"]
                    or {f["name"]: int(f["token"], 16) for f in c["fields"]}
                    != {f["name"]: f["token"] for f in spec["fields"]}):
                raise Refused("留影对象与当前元数据不匹配。")
        elif fullname is not None and not c["name"].endswith("[]"):
            raise Refused("留影类型不在审核名单中：" + fullname)
        self._class_cache[klass] = c
        return c

    def anchor(self,address,size):
        if not 0 <= size <= 1024*1024:
            raise Refused("留影读取块大小超出审核范围。")
        if size>4096:
            return b"".join(super(PhotostoneResolver,self).anchor(address+off,min(4096,size-off))
                            for off in range(0,size,4096))
        return super().anchor(address,size)

    def offset(self, c, name, kind, expected=None, *, static=False):
        full = c["namespace"] + "." + c["name"]
        spec = self.specs.get(full)
        if spec is not None:
            spec = self.runtime_spec(full, spec)
        token = next((f["token"] for f in spec["fields"] if f["name"] == name), None) if spec else None
        if token is None:
            raise Refused("留影字段不在审核名单中。")
        offset = self.field(c, name, kind, token, static=static)
        if expected is not None and offset != expected:
            raise Refused("留影字段偏移与已审核代码不同：" + name)
        return offset

    def link(self, address):
        value = self.q(address, anchored=True)
        self.links.append(dict(address=hex(address), expected=hex(value)))
        return value

    def ptr(self, obj, c, name, kind=0x12, expected=None):
        return self.link(obj + self.offset(c, name, kind, expected))

    def scalar(self, obj, c, name, kind=8, expected=None):
        return self.i(obj + self.offset(c, name, kind, expected), anchored=True)

    def flag(self, obj, c, name):
        raw = self.anchor(obj + self.offset(c, name, 2), 1)
        if raw not in (b"\0", b"\1"):
            raise Refused("留影布尔状态无效。")
        return raw == b"\1"

    def string(self, address):
        c = self.obj(address, "System.String")
        length = self.scalar(address, c, "_stringLength", 8, 0x10)
        self.offset(c, "_firstChar", 3, 0x14)
        if not 1 <= length <= 128:
            raise Refused("NPC 实例编号长度异常。")
        return self.anchor(address + 0x14, length * 2).decode("utf-16-le")

    def array_element(self, owner_class, name, fullname):
        """Resolve initialized generic element metadata even when array is null."""
        field = next(f for f in owner_class["fields"] if f["name"] == name)
        data = bytes.fromhex(field["type_data"])
        if len(data) != 16 or data[10] != 0x1D:
            raise Refused("留影集合数组字段类型不同。")
        element = self.anchor(struct.unpack_from("<Q", data)[0], 16)
        if element[10] != 0x15:
            raise Refused("留影集合元素不是已审核泛型。")
        generic = struct.unpack_from("<Q", element)[0]
        klass = self.link(generic + 24)
        if not klass:
            raise Refused("留影集合元素元数据尚未初始化。")
        return self.info(klass, fullname)

    def dictionary(self, address, key_kind, value_kind, *, maximum=4096, key_type=None):
        """Decode verified Dictionary storage; UUID strings remain UUID keys."""
        dc = self.obj(address, "System.Collections.Generic.Dictionary`2")
        entries = self.ptr(address, dc, "_entries", 0x1D, 0x18)
        count = self.scalar(address, dc, "_count", 8, 0x20)
        free = self.scalar(address, dc, "_freeCount", 8, 0x28)
        version = self.scalar(address, dc, "_version", 8, 0x2C)
        self.scalar(address, dc, "_freeList", 8, 0x24)
        if not 0 <= free <= count <= maximum or count and not entries:
            raise Refused("留影字典长度异常。")
        desc = dict(address=hex(address), entries=hex(entries), count=count, free=free,
                    version=version, capacity=0, keyKind=key_kind, valueKind=value_kind,
                    stride=0, items=[])
        ec = self.array_element(dc, "_entries", ".Entry")
        if entries:
            ac = self.obj(entries, ".Entry[]")
            if self.link(int(ac["klass"], 16) + 0x40) != int(ec["klass"], 16):
                raise Refused("留影字典实际元素与声明类型不同。")
        stride = ec["instance_size"] - 16
        key_offset = 8
        value_offset = 16 if key_kind == 0x0E or value_kind in (0x12, 0x0E) else 12
        expected_stride = 24 if value_offset == 16 else 20 if value_kind == 0x15 else 16
        offsets = [self.offset(ec, n, k) - 16 for n, k in
                   [("hashCode", 8), ("next", 8), ("key", key_kind), ("value", value_kind)]]
        if offsets != [0, 4, key_offset, value_offset] or stride != expected_stride:
            raise Refused("留影字典元素布局未经审核。")
        if key_type is not None:
            if key_kind != 0x11:
                raise Refused("留影字典包装键类型无效。")
            _value_type(self, ec, "key", key_type)
        if value_kind == 0x15:
            vf = next(f for f in ec["fields"] if f["name"] == "value")
            generic = struct.unpack_from("<Q", bytes.fromhex(vf["type_data"]))[0]
            vc = self.info(self.link(generic + 24), "System.ValueTuple`2")
            if [self.offset(vc, "Item1", 0x11), self.offset(vc, "Item2", 0x11)] != [16, 20]:
                raise Refused("任务保留入口元组布局不同。")
        desc["stride"] = stride
        if not entries:
            return {}, desc
        capacity = self.q(entries + 24, anchored=True)
        if not count <= capacity <= maximum * 2 + 16:
            raise Refused("留影字典容量异常。")
        desc.update(capacity=capacity, stride=stride)
        raw = self.anchor(entries + 32, count * stride) if count else b""
        result = {}
        for index in range(count):
            row = raw[index * stride:(index + 1) * stride]
            hashed, nxt = struct.unpack_from("<ii", row)
            if not -1 <= nxt < max(1, count):
                raise Refused("留影字典链异常。")
            if hashed < 0:
                continue
            key_ptr = None
            if key_kind == 0x0E:
                key_ptr = struct.unpack_from("<Q", row, key_offset)[0]
                key = self.string(key_ptr)
            else:
                key = struct.unpack_from("<i", row, key_offset)[0]
            if value_kind in (0x12, 0x0E):
                value = struct.unpack_from("<Q", row, value_offset)[0]
                decoded = self.string(value) if value_kind == 0x0E else value
                wire_value = hex(value)
            elif value_kind == 0x15:
                decoded = list(struct.unpack_from("<ii", row, value_offset))
                wire_value = decoded
            else:
                decoded = struct.unpack_from("<i", row, value_offset)[0]
                wire_value = decoded
            if key in result:
                raise Refused("留影字典含重复编号。")
            result[key] = decoded
            desc["items"].append(dict(key=key, value=wire_value, entry=hex(entries + 32 + index * stride),
                                      **({"key_pointer":hex(key_ptr)} if key_ptr else {})))
        if len(result) != count - free:
            raise Refused("留影字典有效条目数量不符。")
        return result, desc

    def quest_owners(self, address):
        """The game owns tasks in HashSet<QuestSpecialStateOwner>, not a map."""
        hc = self.obj(address,"System.Collections.Generic.HashSet`1")
        slots = self.ptr(address,hc,"_slots",0x1D,0x18)
        buckets = self.ptr(address,hc,"_buckets",0x1D,0x10)
        count = self.scalar(address,hc,"_count",8,0x20)
        last = self.scalar(address,hc,"_lastIndex",8,0x24)
        free = self.scalar(address,hc,"_freeList",8,0x28)
        version = self.scalar(address,hc,"_version",8,0x38)
        if not 0 <= count <= last <= 4096 or not -1 <= free < max(1,last):
            raise Refused("任务特殊入口集合长度无效。")
        result = []
        descriptor = dict(kind="hashset",address=hex(address),slots=hex(slots),buckets=hex(buckets),
                          count=count,last_index=last,free_list=free,version=version,capacity=0,items=result)
        sc = self.array_element(hc,"_slots",".Slot")
        if (sc["instance_size"] != 36 or [self.offset(sc,n,k)-16 for n,k in
                [("hashCode",8),("next",8),("value",0x11)]] != [0,4,8]):
            raise Refused("任务特殊入口槽布局不同。")
        _value_type(self,sc,"value",".QuestSpecialStateOwner")
        if not slots:
            if last or count or buckets:
                raise Refused("任务特殊入口集合尚未完整初始化。")
            return result,descriptor
        ac = self.obj(slots,".Slot[]")
        if self.link(int(ac["klass"],16)+0x40) != int(sc["klass"],16):
            raise Refused("任务特殊入口实际元素与声明类型不同。")
        capacity = self.q(slots+24,anchored=True)
        if not last <= capacity <= 8192 or not buckets:
            raise Refused("任务特殊入口集合容量异常。")
        self.obj(buckets,"System.Int32[]")
        bucket_count = self.q(buckets+24,anchored=True)
        if not 1 <= bucket_count <= 8192:
            raise Refused("任务特殊入口桶数量异常。")
        self.anchor(buckets+32,bucket_count*4)
        descriptor["capacity"] = capacity
        raw = self.anchor(slots+32,last*20) if last else b""
        seen = set()
        for index in range(last):
            hashed,nxt,quest,npc,sub = struct.unpack_from("<iiiii",raw,index*20)
            if not -1 <= nxt < max(1,last):
                raise Refused("任务特殊入口槽链异常。")
            if hashed < 0:
                continue
            key = (quest,npc,sub)
            if min(key) <= 0 or key in seen:
                raise Refused("任务特殊入口编号无效或重复。")
            seen.add(key)
            result.append(dict(quest_id=quest,npc_id=npc,sub_id=sub,slot=hex(slots+32+index*20)))
        if len(result) != count:
            raise Refused("任务特殊入口集合计数不符。")
        return result,descriptor

    def usage_records(self, address):
        values, descriptor = self.dictionary(address,8,0x12,maximum=1024)
        records=[]
        for action,record in values.items():
            c = self.obj(record,"Game.Model.NpcInteractionActionUsageRecord")
            used = self.scalar(record,c,"<UsedCount>k__BackingField",8,0x10)
            cycle = struct.unpack("<q",self.anchor(record+self.offset(c,"<CycleKey>k__BackingField",0x0A,0x18),8))[0]
            if action <= 0 or used < 0:
                raise Refused("角色互动使用记录无效。")
            records.append(dict(action_id=action,record=hex(record),used_count=used,cycle_key=cycle))
        return dict(dictionary=descriptor,records=records)

    def ref_list(self, address, *, notifiable=False, maximum=4096):
        if notifiable:
            oc = self.obj(address, "Emei.NotifiableList`1")
            lc = self.info(self.link(int(oc["klass"], 16) + 0x58), "System.Collections.Generic.List`1")
        else:
            lc = self.obj(address, "System.Collections.Generic.List`1")
        array = self.ptr(address, lc, "_items", 0x1D, 0x10)
        count = self.scalar(address, lc, "_size", 8, 0x18)
        self.scalar(address, lc, "_version", 8, 0x1C)
        if not array or not 0 <= count <= maximum:
            raise Refused("留影引用列表未就绪。")
        capacity = self.q(array + 24, anchored=True)
        if not count <= capacity <= maximum * 2:
            raise Refused("留影引用列表容量异常。")
        raw = self.anchor(array + 32, count * 8) if count else b""
        return struct.unpack("<" + "Q" * count, raw), array

    def managers(self):
        context = _Context(self.game.resolver)
        main, _ = context.managers()
        self.anchors.extend((x["address"], x["expected_hex"]) for x in context.anchors)
        mc = self.obj(main, "Game.A1Main")
        listing = self.ptr(main, mc, "_managers", 0x15)
        pointers, _ = self.ref_list(listing, maximum=128)
        found = {}
        for pointer in pointers:
            c = self.obj(pointer, None)
            name = c["namespace"] + "." + c["name"]
            if name in ("Game.NpcLogicManager", "Game.ConfigManager"):
                if name in found:
                    raise Refused("留影管理器不唯一。")
                found[name] = (pointer, self.info(int(c["klass"], 16), name))
        if set(found) != {"Game.NpcLogicManager", "Game.ConfigManager"}:
            raise Refused("留影管理器尚未就绪。")
        return found

    def nullable_int(self, obj, c, name, expected):
        address = obj + self.offset(c, name, 0x15, expected)
        raw = self.anchor(address, 8)
        if raw[0] not in (0, 1):
            raise Refused("留影可空整数标志无效。")
        return struct.unpack_from("<i", raw, 4)[0] if raw[0] else None

    def configuration(self, config_manager, cc):
        tables = self.ptr(config_manager, cc, "<Tables>k__BackingField", 0x12, 0x18)
        tc = self.obj(tables, "LubanDatas.Tables")
        sf = self.link(int(tc["klass"], 16) + 0xB8)
        current = self.link(sf + self.offset(tc, "Current", 0x12, 0, static=True))
        if current != tables:
            raise Refused("游戏配置管理器与当前配置不一致。")
        table = self.ptr(tables, tc, "<TbNpcInteractGameEntry>k__BackingField", 0x12, 0x438)
        bc = self.obj(table, "LubanDatas.TbNpcInteractGameEntry")
        overrides = self.ptr(table, bc, "_overrides", 0x15, 0x20)
        if overrides:
            # The generic override key is composite; only an exactly empty
            # header is accepted, without guessing its element layout.
            oc = self.obj(overrides, "System.Collections.Generic.Dictionary`2")
            count = self.scalar(overrides, oc, "_count", 8, 0x20)
            free = self.scalar(overrides, oc, "_freeCount", 8, 0x28)
            self.scalar(overrides, oc, "_version", 8, 0x2C)
            if not 0 <= count == free <= 4096:
                raise Refused("互动配置存在运行时覆盖，本版暂只支持已审核原始配置。")
        listing = self.ptr(table, bc, "_dataList", 0x15, 0x10)
        rows, _ = self.ref_list(listing, notifiable=True)
        found = {}
        for row in rows:
            c = self.obj(row, "LubanDatas.data.NpcInteractGameEntry")
            npc_id = self.scalar(row, c, "<npcId>k__BackingField", 0x11, 0x10)
            if npc_id not in NPC_IDS:
                continue
            sub_id = self.scalar(row, c, "<subId>k__BackingField", 0x11, 0x14)
            key = (npc_id, sub_id)
            if key in found:
                raise Refused("互动配置存在重复阶段。")
            found[key] = (row, c)
        result = {}
        for cfg in CATALOG:
            key = (cfg["npc_id"], cfg["sub_id"])
            if key not in found:
                continue
            row, c = found[key]
            current = dict(npc_id=key[0], sub_id=key[1],
                depends_sub_id=self.nullable_int(row, c, "<dependsSubId>k__BackingField", 0x18),
                max_success=self.nullable_int(row, c, "<maxSuccessCount>k__BackingField", 0x38),
                game_type=self.scalar(row, c, "<interactGameType>k__BackingField", 0x11, 0x40),
                game_param=self.scalar(row, c, "<interactGameParam>k__BackingField", 8, 0x44),
                unlock_intimacy=self.scalar(row, c, "<UnlockIntimacy>k__BackingField", 8, 0x20),
                priority=self.scalar(row, c, "<triggerPriority>k__BackingField", 8, 0x98),
                reward=self.scalar(row, c, "<reward>k__BackingField", 0x11, 0x64))
            expected = {k:cfg[k] for k in current if k != "game_type"}
            expected["game_type"] = 1
            result[key] = dict(pointer=row, klass=c["klass"], config=current, verified=current == expected)
        return result

    def read(self):
        with self.metadata_read_scope():
            return self._read()

    def _read(self):
        self._class_cache = {}
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("无法确认留影所属存档。")
        self.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        self.links = []
        world = raw["world"]
        wc = self.obj(world, "Game.Model.GameWorldModel")
        npc_dictionary = self.ptr(world, wc, "<NpcModels>k__BackingField", 0x15, 0x38)
        static_ids = self.ptr(world, wc, "<StaticNpcIds>k__BackingField", 0x15, 0x48)
        by_uuid, nd = read_concurrent(self,npc_dictionary,"npc")
        static, sd = read_concurrent(self,static_ids,"static")
        time_obj = self.ptr(world, wc, "<CurrentGameTime>k__BackingField", 0x12, 0x28)
        time_class = self.obj(time_obj, "Game.GameTime")
        date = [self.scalar(time_obj, time_class, n, 8, 0x10+4*i) for i,n in enumerate(["Year","Month","Day","Unit"])]
        if not 0 <= date[0] <= 100000 or not 1 <= date[1] <= 12 or not 1 <= date[2] <= 31 or not 0 <= date[3] <= 1000:
            raise Refused("游戏日期超出可确认范围。")
        managers = self.managers()
        logic, lc = managers["Game.NpcLogicManager"]
        config, cc = managers["Game.ConfigManager"]
        quest_ptr = self.ptr(logic, lc, "_questSpecialStateOwners", 0x15, 0x20)
        quests, qd = self.quest_owners(quest_ptr)
        self.offset(lc,"_isExecutingNpcInteractAction",2,0x2D)
        executing = self.flag(logic, lc, "_isExecutingNpcInteractAction")
        configurations = self.configuration(config, cc)
        context_reason = ""
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            self.anchors.extend((a["address"], a["expected_hex"]) for a in context["anchors"])
        except AcquisitionContextRefused:
            context_reason = "激活留影需在普通场景、战斗和转场结束后进行。"
        if executing:
            context_reason = "游戏正在处理角色互动；请结束当前互动后刷新。"
        npcs = {}
        for uuid, npc in by_uuid.items():
            nc = self.obj(npc, "Game.Model.NpcModel")
            cfg_id = self.scalar(npc, nc, "<NpcCfgId>k__BackingField", 0x11, 0x150)
            if cfg_id not in NPC_IDS:
                continue
            if cfg_id in npcs:
                raise Refused("同一留影角色存在多个运行实例，无法唯一选择。")
            owner = self.ptr(npc, nc, "<GameWorld>k__BackingField", 0x12, 0x168)
            if owner != world:
                raise Refused("留影角色不属于当前世界。")
            status = self.scalar(npc, nc, "<WorldStatus>k__BackingField", 0x11, 0x160)
            intimacy = self.scalar(npc, nc, "<Intimacy>k__BackingField", 8, 0x170)
            runtime = self.ptr(npc, nc, "<NpcInteractionRuntime>k__BackingField", 0x12, 0x1F0)
            statistics = self.ptr(npc, nc, "<MiniGameStatistics>k__BackingField", 0x15, 0x1E8)
            stats, stats_desc = (self.dictionary(statistics, 0x11, 8, maximum=512,
                key_type="LubanDatas.TbNpcInteractGameEntrySubid") if statistics else (None, None))
            if stats is not None and any(k <= 0 or v < 0 for k,v in stats.items()):
                raise Refused("留影成功次数或阶段编号无效。")
            usage, active, usage_state = 0, 0, None
            if runtime:
                rc = self.obj(runtime, "Game.Model.NpcInteractionRuntimeState")
                active = self.scalar(runtime, rc, "<SpecialSubId>k__BackingField", 8, 0x10)
                usage = self.ptr(runtime, rc, "<ActionUsageRecords>k__BackingField", 0x15, 0x18)
                if not usage or active < 0:
                    raise Refused("留影互动运行状态未完整初始化。")
                usage_state = self.usage_records(usage)
            identity = [self.game.stamp, world, raw["player"], uuid, npc, runtime, statistics,
                        active, sorted(stats.items()) if stats is not None else None,
                        stats_desc, usage_state, nd, sd, qd, date, owner, status, intimacy]
            npcs[cfg_id] = dict(pointer=npc, klass=nc["klass"], stats=stats, statistics=stats_desc,
                runtime=runtime, usage=usage, usage_state=usage_state, active_special=active, world_status=status,
                intimacy=intimacy, canonical=static.get(cfg_id) == uuid,
                quest_owned=any(value["npc_id"] == cfg_id for value in quests),
                config_verified={sub:entry["verified"] for (cid,sub),entry in configurations.items() if cid == cfg_id},
                identity=identity)
        result = build_rows(CATALOG, npcs, context_reason=context_reason)
        proof = self.proof()
        owner_links = list({(link["address"], link["expected"]):link for link in self.links}.values())
        result["identity"] = fingerprint([self.game.stamp, world, date, nd, sd])
        proof_bounds = [(a, int(a["address"], 16), int(a["address"], 16) + a["size"]) for a in proof]
        stable_by_npc = {}
        for row in result["rows"]:
            npc = npcs.get(row["npc_id"])
            entry = configurations.get((row["npc_id"], row["sub_id"]))
            if not npc or not entry or not npc["statistics"]:
                continue
            st = npc["statistics"]
            if row['npc_id'] not in stable_by_npc:
                mutable_ranges = [(npc["runtime"]+0x10,4), (int(st["address"],16)+0x20,16),
                                  (int(st["entries"],16)+32, st["count"]*st["stride"])]
                stable_by_npc[row['npc_id']] = [a for a, low, high in proof_bounds
                    if not any(low < start+size and start < high for start,size in mutable_ranges if size)]
            stable = stable_by_npc[row['npc_id']]
            row["native"] = dict(world=hex(world),player=hex(raw["player"]),npc=hex(npc["pointer"]),
                npc_class=npc["klass"],logic_manager=hex(logic),logic_class=lc["klass"],
                runtime=hex(npc["runtime"]),stats=st["address"],usage=hex(npc["usage"]),
                usage_state=npc["usage_state"],
                active_special=npc["active_special"],stats_before=[dict(key=k,value=v) for k,v in sorted(npc["stats"].items())],
                entry=hex(entry["pointer"]),entry_class=entry["klass"],entry_config=entry["config"],
                date=date,date_address=hex(time_obj),npc_dictionary=nd,static_ids=sd,
                quest_owners=qd,statistics=st,owner_links=owner_links,
                post_stable_anchors=stable,anchors=proof,
                npc_id=row["npc_id"],sub_id=row["sub_id"])
        self.append_locations(result, raw, npcs, config)
        return result

    def append_locations(self, result, raw, npcs, config):
        # Location is display data, not an activation precondition. Keep its
        # potentially moving world objects out of native anchors and identities.
        try:
            locations = PhotostoneLocationResolver(self.game).locations(raw, npcs, config)
        except Exception as error:
            locations = {key: dict(location_label="位置暂不可读", location_space_id=None,
                location_reason=f"位置读取失败：{error}。可稍后刷新；留影记录仍独立有效。") for key in npcs}
        for row in result["rows"]:
            row.update(locations.get(row["npc_id"], dict(location_label="角色未生成",
                location_space_id=None, location_reason="当前世界未找到此角色，不能确定其所在场景。")))


class PhotostoneLocationResolver(PhotostoneResolver):
    """Read live NPC locations separately; never return native proof or call code."""

    def space_names(self, config, wanted):
        cc = self.obj(config, "Game.ConfigManager")
        tables = self.ptr(config, cc, "<Tables>k__BackingField", 0x12, 0x18)
        tc = self.obj(tables, "LubanDatas.Tables")
        sf = self.link(int(tc["klass"], 16) + 0xB8)
        if self.link(sf + self.offset(tc, "Current", 0x12, 0, static=True)) != tables:
            raise Refused("场景名称不属于当前游戏配置。")
        table = self.ptr(tables, tc, "<TbSpace>k__BackingField", 0x12, 0xA8)
        bc = self.obj(table, "LubanDatas.TbSpace")
        overrides = self.ptr(table, bc, "_overrides", 0x15, 0x20)
        if overrides:
            dc = self.obj(overrides, "System.Collections.Generic.Dictionary`2")
            count = self.scalar(overrides, dc, "_count", 8, 0x20)
            free = self.scalar(overrides, dc, "_freeCount", 8, 0x28)
            self.scalar(overrides, dc, "_version", 8, 0x2C)
            if not 0 <= count == free <= 8192:
                raise Refused("场景配置存在运行时覆盖，暂不能确认有效名称。")
        listing = self.ptr(table, bc, "_dataList", 0x15, 0x18)
        values, _ = self.ref_list(listing, notifiable=True, maximum=8192)
        indexed = {}
        for value in values:
            sc = self.obj(value, "LubanDatas.data.Space")
            _value_type(self, sc, "<id>k__BackingField", "LubanDatas.TbSpaceId")
            space_id = self.scalar(value, sc, "<id>k__BackingField", 0x11, 0x18)
            if space_id in indexed:
                raise Refused("场景配置编号重复，不能唯一确认名称。")
            indexed[space_id] = value, sc
        labels, paths = {}, {}
        for wanted_id in wanted:
            chain, current = [], wanted_id
            while current and current in indexed:
                if current in chain or len(chain) >= 16:
                    raise Refused("场景父级链存在循环或过深，不能确认地图位置。")
                chain.append(current)
                value, sc = indexed[current]
                if current not in labels:
                    _value_type(self, sc, "<spaceName>k__BackingField", "LubanDatas.L10nText")
                    # Audited L10nText has one Dictionary reference at unboxed
                    # offset 0, as SpaceUuid has one String reference there.
                    languages = self.link(value + self.offset(sc, "<spaceName>k__BackingField", 0x11, 0x30))
                    translations, _ = self.dictionary(languages, 0x0E, 0x0E, maximum=16)
                    labels[current] = (translations.get("zh-Hans") or translations.get("zh-Hant")
                                       or translations.get("en-US") or f"场景 {current}")
                current = self.nullable_int(value, sc, "<fatherSpace>k__BackingField", 0x28)
            if chain:
                if current:
                    labels[current] = f"场景 {current}"
                    chain.append(current)
                parts = []
                for key in reversed(chain):
                    if not parts or parts[-1] != labels[key]:
                        parts.append(labels[key])
                paths[wanted_id] = " / ".join(parts)
        return paths

    def locations(self, raw, npcs, config):
        with self.metadata_read_scope():
            return self._locations(raw, npcs, config)

    def _locations(self, raw, npcs, config):
        # A genuine constructor and a fresh metadata cache are used on every
        # refresh. The parent resolver's proof is never mutated or reused here.
        self._class_cache = {}
        self.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        self.links = []
        world = raw["world"]
        wc = self.obj(world, "Game.Model.GameWorldModel")
        dictionary = self.ptr(world, wc, "<Spaces>k__BackingField", 0x15, 0x30)
        spaces, _ = read_concurrent(self, dictionary, "space")
        locations, pending = {}, {}
        def unknown(label, reason):
            return dict(location_label=label, location_space_id=None, location_reason=reason)
        for npc_id, npc in npcs.items():
            pointer = npc["pointer"]
            nc = self.obj(pointer, "Game.Model.NpcModel")
            if (self.scalar(pointer, nc, "<NpcCfgId>k__BackingField", 0x11, 0x150) != npc_id
                    or self.ptr(pointer, nc, "<GameWorld>k__BackingField", 0x12, 0x168) != world):
                raise Refused("读取位置时角色或所属世界发生变化。")
            status = self.scalar(pointer, nc, "<WorldStatus>k__BackingField", 0x11, 0x160)
            if status != 0:
                locations[npc_id] = unknown("角色未登场" if status == 1 else "角色已离场" if status == 2 else "角色状态未知",
                    "角色当前不处于世界活动状态；不将遗留场景记录显示为可前往的位置。")
                continue
            _value_type(self, nc, "<CurrentSpaceUuid>k__BackingField", "Game.Model.SpaceUuid")
            uuid_pointer = self.link(pointer + self.offset(nc, "<CurrentSpaceUuid>k__BackingField", 0x11, 0x158))
            if not uuid_pointer:
                locations[npc_id] = unknown("尚无所在场景", "角色当前没有场景实例记录。")
                continue
            string_class = self.obj(uuid_pointer, "System.String")
            length = self.scalar(uuid_pointer, string_class, "_stringLength", 8, 0x10)
            uuid = self.string(uuid_pointer) if length else ""
            if not uuid or uuid not in spaces:
                locations[npc_id] = unknown("场景暂不可定位", "角色所在的场景实例尚未载入当前世界，或正在切换；请稍后刷新。")
                continue
            space = spaces[uuid]
            sc = self.obj(space, "Game.Model.SpaceModel")
            if self.ptr(space, sc, "<GameWorld>k__BackingField", 0x12, 0x68) != world:
                raise Refused("角色场景实例不属于当前世界。")
            space_status = self.scalar(space, sc, "<WorldStatus>k__BackingField", 0x11, 0x30)
            _value_type(self, sc, "<SpaceId>k__BackingField", "LubanDatas.TbSpaceId")
            space_id = self.scalar(space, sc, "<SpaceId>k__BackingField", 0x11, 0x24)
            if space_status != 0 or space_id <= 0:
                locations[npc_id] = unknown("场景尚未开放", "角色场景当前未激活、已离场或编号无效；不能保证可前往。")
                continue
            pending[npc_id] = space_id
        names, name_reason = {}, ""
        if pending:
            try:
                names = self.space_names(config, set(pending.values()))
            except Exception as error:
                name_reason = f"场景名称未能核实：{error}。"
        for npc_id, space_id in pending.items():
            name = names.get(space_id)
            locations[npc_id] = dict(location_label=name or f"场景 {space_id}", location_space_id=space_id,
                location_reason=(name_reason or "") + "读取自角色当前场景记录；人物移动后请刷新。" +
                ("" if name else " 当前只能确认场景编号。"))
        self.proof()
        return locations


class PhotostoneAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = PhotostoneResolver(game)
        from photostone_native import PhotostoneNative
        self.native = PhotostoneNative(game, self)

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("留影连接已停止，请核对游戏。")
        if process_identity(self.resolver.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        state = self.resolver.read()
        if process_identity(self.resolver.reader.h) != self.game.stamp:
            raise Refused("读取留影期间游戏进程发生变化。")
        return state

    def current_row(self, shown):
        if not isinstance(shown, dict) or not shown.get("identity"):
            raise Refused("请先读取留影清单并选择阶段。")
        rows = self.snapshot()["rows"]
        fresh = next((r for r in rows if (r["npc_id"],r["sub_id"]) == (shown.get("npc_id"),shown.get("sub_id"))), None)
        if fresh is None or fresh["identity"] != shown["identity"]:
            raise Refused("角色、日期或留影记录已变化，请刷新后重新选择。")
        return fresh

    def prepare_next(self, shown):
        row = self.current_row(shown)
        if not row["can_activate"]:
            raise Refused(row["reason"])
        return dict(row, mode="next")

    def preview_force(self, shown):
        # Advisory location changes must not invalidate an otherwise identical
        # explicit replay confirmation or enter its persisted operation record.
        row = {key: value for key, value in self.current_row(shown).items() if not key.startswith("location_")}
        return replay_preview(row)

    def prepare_solve(self, shown):
        mode = shown.get("mode") if isinstance(shown, dict) else None
        if mode not in ("next", "force"):
            raise Refused("留影操作模式未经确认。")
        row = self.current_row(shown)
        if not row["can_activate" if mode == "next" else "can_force"]:
            raise Refused(row["reason" if mode == "next" else "force_reason"] or "当前阶段不可激活。")
        if mode == "force" and shown.get("force_confirmed") is not True:
            raise Refused("重玩必须先阅读影响预览并明确确认。")
        descriptor = dict(row["native"])
        descriptor["methods"] = {k:self.resolver.method(int(descriptor["logic_class"],16), spec)
                                 for k,spec in SPECS["methods"].items()}
        descriptor["method_specs"] = {key: selected_method_spec(self.resolver, spec)
                                       for key, spec in SPECS["methods"].items()}
        descriptor.update(mode=mode, force_confirmed=mode == "force",
                          round_key=fingerprint([row["identity"],mode]), anchors=self.resolver.proof())
        return dict(row,mode=mode,force_confirmed=mode == "force",native=descriptor)

    def activate_next(self, row):
        return self._dispatch(self.prepare_next(row))

    def force(self, preview, *, confirmed=False):
        if confirmed is not True or not isinstance(preview, dict) or "row" not in preview:
            raise Refused("重玩需要明确确认所选阶段的影响。")
        fresh = self.preview_force(preview["row"])
        if fresh != preview:
            raise Refused("重玩预览已变化，请重新预览。")
        self.game.record(dict(photostone_replay_preview=fresh["effects"], confirmed=True,
                              identity=fresh["identity"], message=fresh["message"]))
        return self._dispatch(dict(fresh["row"],mode="force",force_confirmed=True))

    def _dispatch(self, state):
        if getattr(self.game,"write_enabled",False) is not True:
            raise Refused("当前为只读连接，未激活留影。")
        try:
            return self.native.solve(state)
        except UncertainWrite:
            self.blocked = True
            raise

    def verify_native(self, outcome, state):
        if (outcome.get("npc_id") != state["npc_id"] or outcome.get("sub_id") != state["sub_id"]
                or outcome.get("active_special") != state["sub_id"]):
            raise UncertainWrite("留影激活结果与所选角色或阶段不符，禁止重发。")
        fresh = next((r for r in self.snapshot()["rows"] if (r["npc_id"],r["sub_id"]) == (state["npc_id"],state["sub_id"])),None)
        if fresh is None or fresh["active_special"] != state["sub_id"] or "native" not in fresh:
            raise UncertainWrite("留影激活后未能读回同一阶段，请核对游戏。")
        before, after = state["native"], fresh["native"]
        for field in ("world","player","npc","runtime","stats","usage","date","date_address","entry"):
            if before[field] != after[field]:
                raise UncertainWrite("留影操作后对象、日期或配置发生变化，禁止重发。")
        verify_statistics({r["key"]:r["value"] for r in before["stats_before"]},
                          {r["key"]:r["value"] for r in after["stats_before"]},
                          mode=state["mode"],sub_id=state["sub_id"])
        return dict(verified=True, message=f"已激活 {state['name']} 第 {state['stage']} 段留影。请回游戏选择留影石并正常完成；需要保留时请在游戏内保存。")

    def close(self):
        self.native.close()
