"""Readonly current persuasion session and its normal, once-only success path.

The current panel, NPC model, command closure and cancellation source must agree.
No chat request is issued and no settlement delay is skipped.  All game effects
remain in NpcModel.OnPersuadeResult(true, PersuadeEndReason.Success).
"""
import hashlib
import json
import struct

from acquisition_context import AcquisitionContextRefused
from persuasion_context import require_safe_persuasion_context
from alchemy_adapter import AlchemyResolver
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from native_write import process_identity
from photostone_concurrent import read_concurrent
from persuasion_native import PersuasionOnce
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

DATA = json.loads((RESOURCE_ROOT / "persuasion_specs.json").read_text(encoding="utf8"))
SPECS, METHODS = DATA["metadata"], DATA["methods"]
METHOD = METHODS["result"]
PANEL = "Game.NpcPersuadePanel"
CLOSURE = ".<>c__DisplayClass5_0"  # owner is Game.MiniGamePersuadeCommand
ROOT_LABELS = ("GameStoreManager.parent", "Singleton.static_fields", "Singleton.lazyInstance", "Lazy._state",
               "Lazy._value", "manager.klass", "manager._gameStore", "Game.Model.GameStore.klass",
               "store._gameWorld", "Game.Model.GameWorldModel.klass", "world.PlayerModel", "Game.Model.PlayerModel.klass")


def stable_roots(raw):
    """Only canonical owner links, safe to recheck after normal success effects.

    Inventory, talent balances, NPC emotion/history and UI countdown state may
    legitimately change. These 12 links must still point at the same save and
    player even if a synchronous game callback switched the world mid-call.
    """
    result = []
    for label in ROOT_LABELS:
        matches = [a for a in raw["anchors"] if a.get("label") == label]
        if len(matches) != 1 or matches[0].get("size") != 8:
            raise Refused("说服缺少完整的当前世界身份链。")
        a = dict(matches[0])
        if len(bytes.fromhex(a["expected_hex"])) != 8:
            raise Refused("说服世界身份链长度异常。")
        if not isinstance(a["address"], str):
            a["address"] = hex(a["address"])
        result.append(a)
    return result


def readiness(values):
    """Separate normal unavailable states from malformed state. No mutation."""
    if values["ended"] or values["notified"] or values["user_closed"] or values["delay"]:
        return "本次说服已结束或正在倒计时结算，请在游戏内继续。"
    if not values["actionable"]:
        return "说服界面已暂停或暂不可交互，请恢复后重新读取。"
    if values["flow_notified"] or values["flow_ended"] or values["flow_cancelled"]:
        return "本次说服流程已取消或结束，不能调用旧对话。"
    if (values["processing"] or values.get("chat_processing") or values.get("chat_summarizing")
            or values["peek"] or not values["can_submit"]):
        return "游戏正在请求回复、窥心或提交输入，请等待结束后重新读取。"
    if values["last_reason"] != 0 or values["current_topic"] != values["topic_id"]:
        return "NPC 已结束本次话题或切换了对话，请刷新。"
    if not 0 <= values["rounds"] <= values["max_rounds"]:
        raise Refused("说服轮次与当前配置不一致。")
    return ""


class PersuasionResolver(AlchemyResolver):
    """Reuse the reviewed large Constants inspector and canonical table route."""
    def __init__(self, reader, **kwargs):
        # Shared PhotostoneResolver.info owns per-read metadata proof caching.
        # This resolver reuses that method without its constructor.
        self._class_cache = {}
        specs = {k: v for k, v in SPECS.items()
                 if k not in ("System.Collections.Generic.Dictionary`2", ".Entry", "System.Nullable`1")}
        # This compiler-generated cached delegate is never read or invoked by
        # the adapter. The callbacks actually used below remain required.
        specs[CLOSURE] = {**specs[CLOSURE], "fields": [f for f in specs[CLOSURE]["fields"]
                                                      if f["name"] != "<>9__3"]}
        RegisteredMiniResolver.__init__(self, reader, specs, PANEL, **kwargs)

    def anchor(self, address, size):
        # The shared bridge accepts at most 4096 bytes per proof entry. Keep
        # large immutable configuration arrays and concurrent bucket proofs
        # complete without enlarging the shared transport's safety limits.
        raw = self.exact(address, size)
        for start in range(0, size, 4096):
            self.anchors.append((address + start, raw[start:start+4096].hex()))
        return raw

    def info(self, klass, fullname=None):
        if fullname in ("System.Collections.Concurrent.ConcurrentDictionary`2", ".Tables", ".Node"):
            # The reviewed generic verifier also handles inflated classes whose
            # definition lives on generic_class.type rather than klass+0x68.
            from photostone_adapter import PhotostoneResolver
            return PhotostoneResolver.info(self, klass, fullname)
        return super().info(klass, fullname)

    def reviewed_field(self, c, name, kind, *, static=False):
        full = c["namespace"] + "." + c["name"]
        reviewed = self.specs.get(full, SPECS.get(full))
        spec = self.runtime_spec(full, reviewed) if reviewed is not None else {}
        token = next((f["token"] for f in spec.get("fields", ()) if f["name"] == name), None)
        if token is None:
            raise Refused("说服字段没有审核规格：" + name)
        return self.field(c, name, kind, token, static=static)

    def fixed(self, obj, c, name, kind, offset, size):
        if self.reviewed_field(c, name, kind) != offset:
            raise Refused("说服字段偏移与审核代码不同：" + name)
        return self.anchor(obj + offset, size)

    def flag(self, obj, c, name, offset):
        raw = self.fixed(obj, c, name, 2, offset, 1)
        if raw not in (b"\0", b"\1"):
            raise Refused("说服布尔状态无效。")
        return raw == b"\1"

    def number(self, obj, c, name, offset, kind=8):
        return struct.unpack("<i", self.fixed(obj, c, name, kind, offset, 4))[0]

    def absorb(self, anchors):
        for value in anchors:
            address = value["address"]
            if isinstance(address, str):
                address = int(address, 16)
            raw = self.anchor(address, value["size"])
            if raw.hex() != value["expected_hex"]:
                raise Refused("说服角色或场景在读取期间变化。")

    def offset(self, c, name, kind, expected=None):
        value = self.reviewed_field(c, name, kind)
        if expected is not None and value != expected:
            raise Refused("NPC 并发容器字段偏移不同。")
        return value

    def link(self, address):
        return self.q(address, anchored=True)

    def ptr(self, obj, c, name, kind, expected):
        return self.link(obj + self.offset(c, name, kind, expected))

    def string(self, address):
        c = self.obj(address, "System.String")
        length = self.i(address + self.offset(c, "_stringLength", 8, 0x10), anchored=True)
        self.offset(c, "_firstChar", 3, 0x14)
        if not 1 <= length <= 128:
            raise Refused("NPC 实例编号长度异常。")
        return self.anchor(address + 0x14, length * 2).decode("utf-16-le")

    def npc_membership(self, world, npc, npc_id):
        wc = self.obj(world, "Game.Model.GameWorldModel")
        dictionary = self.pointer_field(world, wc, "<NpcModels>k__BackingField", 0x15, offset=0x38)
        # Actual container: ConcurrentDictionary<EntityID, NpcModel>. No version
        # counter exists; shared helper pins buckets, every node and lock counts.
        objects, descriptor = read_concurrent(self, dictionary, "npc")
        matches = [key for key, value in objects.items() if value == npc]
        if len(matches) != 1:
            raise Refused("不能唯一确认当前世界中的说服 NPC。")
        selected = next(item for item in descriptor["items"] if item["key"] == matches[0])
        return dict(dictionary_descriptor=descriptor, uuid=matches[0], node=selected["node"], npc=hex(npc), npc_id=npc_id)

    def delegate(self, address, *, expected_method=None, expected_target=None):
        c = self.obj(address, None)
        mc = self.info(int(c["parent"], 16), "System.MulticastDelegate")
        dc = self.info(int(mc["parent"], 16), "System.Delegate")
        offsets = {n: self.reviewed_field(dc, n, k) for n, k in
                   (("method_ptr", 0x18), ("method", 0x18), ("method_code", 0x18))}
        if offsets != {"method_ptr": 0x10, "method": 0x28, "method_code": 0x40}:
            raise Refused("说服委托布局未经审核。")
        if self.reviewed_field(mc, "delegates", 0x1D) != 0x78:
            raise Refused("说服委托列表偏移不同。")
        delegates = self.q(address + 0x78, anchored=True)
        code = self.q(address + 0x10, anchored=True)
        method = self.q(address + 0x28, anchored=True)
        target = self.q(address + 0x40, anchored=True)
        if expected_method is not None:
            if delegates or method != int(expected_method, 16) or target != expected_target:
                raise Refused("说服流程回调身份发生变化。")
            if code != self.q(method, anchored=True):
                raise Refused("说服回调代码与方法定义不同。")
        return dict(address=hex(address), code=hex(code), method_info=hex(method), target=hex(target), delegates=hex(delegates))

    def event_subscription(self, address, panel, pc):
        expected = self.method(int(pc["klass"], 16), METHODS["ended"])
        root = self.delegate(address)
        listing = int(root["delegates"], 16)
        members = [address]
        if listing:
            ac = self.obj(listing, "System.Delegate[]")
            self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), "System.Delegate")
            count = self.q(listing + 24, anchored=True)
            if not 1 <= count <= 16:
                raise Refused("说服结束事件订阅数无效。")
            members = list(struct.unpack("<" + "Q" * count, self.anchor(listing + 32, 8 * count)))
        found, callbacks = 0, []
        for member in members:
            item = self.delegate(member)
            if int(item["delegates"], 16):
                raise Refused("不支持嵌套的说服事件委托。")
            if item["target"] == hex(panel) and item["method_info"] == expected:
                if int(item["code"], 16) != self.q(int(expected, 16), anchored=True):
                    raise Refused("说服结束事件代码不一致。")
                found += 1
            callbacks.append(item)
        if found != 1:
            raise Refused("当前说服面板没有唯一订阅正常结束事件。")
        return callbacks

    def flow(self, panel, pc, npc_id, topic_id):
        refs = {key: self.pointer_field(panel, pc, field, kind, offset=offset) for key, field, kind, offset in
                (("alive", "_isFlowAlive", 0x15, 0x180), ("win", "_actionOnWin", 0x12, 0x190),
                 ("lose", "_actionOnLose", 0x12, 0x198), ("close", "_actionOnClose", 0x12, 0x1A0))}
        if not all(refs.values()):
            raise Refused("仅支持游戏正常小游戏流程开启的说服；当前结算回调未就绪。")
        closure = int(self.delegate(refs["alive"])["target"], 16)
        cc = self.obj(closure, CLOSURE)
        callbacks = {}
        for key, ref in refs.items():
            callbacks[key] = self.delegate(ref, expected_method=self.method(int(cc["klass"], 16), METHODS[key]), expected_target=closure)
        notified = self.flag(closure, cc, "notified", 0x10)
        self.flag(closure, cc, "win", 0x11)
        command = self.pointer_field(closure, cc, "<>4__this", offset=0x20)
        command_c = self.obj(command, "Game.MiniGamePersuadeCommand")
        if (self.number(command, command_c, "_npcId", 0x10, 0x11) != npc_id
                or self.number(command, command_c, "_topicId", 0x14, 0x11) != topic_id):
            raise Refused("说服流程命令与当前 NPC 或话题不一致。")
        raw = self.fixed(command, command_c, "_subId", 0x15, 0x18, 8)
        if raw[0] != 1:
            raise Refused("当前说服没有可核对的互动子编号，暂不支持。")
        sub_id = struct.unpack_from("<i", raw, 4)[0]
        if sub_id <= 0:
            raise Refused("说服互动子编号无效。")
        context = self.pointer_field(closure, cc, "ctx", offset=0x28)
        ctx = self.obj(context, "A1.Flow.ProcContext")
        source = struct.unpack("<Q", self.fixed(context, ctx, "<Ct>k__BackingField", 0x11, 0x10, 8))[0]
        activation = self.number(context, ctx, "<ActivationId>k__BackingField", 0x18)
        ended = self.flag(context, ctx, "_endedNotified", 0x78)
        cancelled = False
        source_class = "0x0"
        if source:
            sc = self.obj(source, "System.Threading.CancellationTokenSource")
            source_class = sc["klass"]
            state = self.number(source, sc, "_state", 0x20)
            if not 0 <= state <= 3:
                raise Refused("说服流程取消状态异常。")
            cancelled = state >= 2
            if self.flag(source, sc, "_disposed", 0x28):
                cancelled = True
        return dict(closure=hex(closure), closure_class=cc["klass"], command=hex(command), command_class=command_c["klass"],
                    context=hex(context), context_class=ctx["klass"], source=hex(source), source_class=source_class,
                    activation_id=activation, sub_id=sub_id, notified=notified, ended=ended, cancelled=cancelled,
                    callbacks=callbacks)

    def configuration(self, npc_id, topic_id, sub_id):
        tables, tc = self.tables()
        topics = self.table_rows(tables, tc, "NpcPersuadeTopic", 2048)
        if topic_id not in topics:
            raise Refused("当前说服话题没有配置。")
        topic, topic_c = topics[topic_id]
        if self.number(topic, topic_c, "<npcId>k__BackingField", 0x48, 0x11) != npc_id:
            raise Refused("话题配置的 NPC 与当前对话不同。")
        maximum = self.number(topic, topic_c, "<maxRounds>k__BackingField", 0x20)
        delay_raw = self.fixed(topic, topic_c, "<autoExitDelayMs>k__BackingField", 0x15, 0x4C, 8)
        if delay_raw[0] not in (0, 1):
            raise Refused("说服倒计时配置无效。")
        delay = struct.unpack_from("<i", delay_raw, 4)[0]
        if not 1 <= maximum <= 1000 or not 1 <= delay <= 600000:
            raise Refused("当前话题没有已验证的正常倒计时配置。")
        # The table uses a composite (NpcId, SubId) key, so resolve its data list.
        table = self.pointer_field(tables, tc, "<TbNpcInteractGameEntry>k__BackingField")
        entry_c = self.obj(table, "LubanDatas.TbNpcInteractGameEntry")
        self.no_overrides(table, entry_c)
        objects = self.list_objects(self.pointer_field(table, entry_c, "_dataList", 0x15), 8192)
        matches = []
        for obj in objects:
            ec = self.obj(obj, "LubanDatas.data.NpcInteractGameEntry")
            row_npc = self.number(obj, ec, "<npcId>k__BackingField", 0x10, 0x11)
            row_sub = self.number(obj, ec, "<subId>k__BackingField", 0x14, 0x11)
            if (row_npc, row_sub) == (npc_id, sub_id):
                game_type = self.integer(obj, ec, "<interactGameType>k__BackingField", 0x11)
                parameter = self.integer(obj, ec, "<interactGameParam>k__BackingField")
                if game_type != 2 or parameter != topic_id:
                    raise Refused("当前互动条目并非这个说服话题。")
                matches.append(obj)
        if len(matches) != 1:
            raise Refused("当前说服互动条目不唯一。")
        constants_table = self.pointer_field(tables, tc, "<TbConstants>k__BackingField")
        ctc = self.obj(constants_table, "LubanDatas.TbConstants")
        self.no_overrides(constants_table, ctc)
        constants = self.pointer_field(constants_table, ctc, "_data")
        cc = self.obj(constants, "LubanDatas.data.Constants")
        raw_threshold = self.number(constants, cc, "<AINPC_PERSUADE_SUCCESS_THRESHOLD>k__BackingField", 0xBDC)
        threshold = raw_threshold if raw_threshold > 0 else 100
        if threshold > 1000000:
            raise Refused("说服成功阈值超出可核对范围。")
        return dict(tables=hex(tables), topic_config=hex(topic), entry_config=hex(matches[0]),
                    threshold=threshold, raw_threshold=raw_threshold, max_rounds=maximum, exit_delay_ms=delay)

    def no_overrides(self, table, c):
        overrides = self.pointer_field(table, c, "_overrides", 0x15)
        if overrides:
            dc = self.obj(overrides, "System.Collections.Generic.Dictionary`2")
            count = self.i(overrides + self.reviewed_field(dc, "_count", 8), anchored=True)
            free = self.i(overrides + self.reviewed_field(dc, "_freeCount", 8), anchored=True)
            self.i(overrides + self.reviewed_field(dc, "_version", 8), anchored=True)
            if not 0 <= count == free <= 8192:
                raise Refused("说服配置存在运行时覆盖，暂不支持。")


class PersuasionAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = PersuasionResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self.native = PersuasionOnce(game, self, operation="persuasion_success", method_spec=METHOD,
                                     journal_name="persuasion-once.json")

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("说服连接已停止，请检查游戏。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        rr.anchors = []
        # Cached classes must not outlive the anchors that verified them.
        rr._class_cache = {}
        manager, panels = rr.registered_panels()
        visible = [(p, v) for p in panels if (v := rr.visible_panel(p)) is not None]
        if len(visible) > 1:
            raise Refused("发现多个说服面板，不能唯一确认当前对话。")
        if not visible:
            rr.proof()
            return dict(active=False, can_solve=False, reason="请先在游戏中正常开启说服对话，等待初始回复完成后读取。")
        panel, (pc, actionable) = visible[0]
        npc = rr.pointer_field(panel, pc, "_subscribedNpc", offset=0x158)
        if not npc:
            return dict(active=True, can_solve=False, reason="当前说服 NPC 尚未准备完成。")
        nc = rr.obj(npc, "Game.Model.NpcModel")
        npc_id = rr.number(panel, pc, "_npcId", 0x188, 0x11)
        topic_id = rr.number(panel, pc, "_topicId", 0x18C, 0x11)
        if npc_id <= 0 or topic_id <= 0 or rr.number(npc, nc, "<NpcCfgId>k__BackingField", 0x150, 0x11) != npc_id:
            raise Refused("说服 NPC 或话题标识不同。")
        session = rr.number(npc, nc, "<PersuadeSessionId>k__BackingField", 0x100)
        if session <= 0:
            return dict(active=True, can_solve=False, reason="说服局次尚未开始，请等待游戏就绪。")
        flags = dict(actionable=actionable, npc_id=npc_id, topic_id=topic_id,
            ended=rr.flag(panel, pc, "_persuadeEnded", 0x168), notified=rr.flag(panel, pc, "_persuadeResultNotified", 0x169),
            user_closed=rr.flag(panel, pc, "_userInitiatedClose", 0x179),
            delay=rr.pointer_field(panel, pc, "_settlementDelayCts", offset=0x170),
            peek=rr.pointer_field(panel, pc, "_peekLoadingCo", offset=0x1A8),
            processing=rr.flag(npc, nc, "IsProcessingPersuadeMessage", 0xE8),
            chat_processing=rr.flag(npc, nc, "<IsProcessingChatMessage>k__BackingField", 0xA8),
            chat_summarizing=rr.flag(npc, nc, "<IsSummarizingChatHistory>k__BackingField", 0xA9),
            last_reason=rr.number(npc, nc, "<LastPersuadeEndReason>k__BackingField", 0xC4, 0x11),
            current_topic=rr.number(npc, nc, "<CurrentPersuadeTopicId>k__BackingField", 0xC8, 0x11),
            rounds=rr.number(npc, nc, "<PersuadeRound>k__BackingField", 0xCC),
            progress=rr.number(npc, nc, "<PersuadeEmotionValue>k__BackingField", 0xD8))
        rr.flag(panel, pc, "_settlementIsWin", 0x178)
        peek_token = rr.number(panel, pc, "_peekRequestToken", 0x1B0)
        processing_token = rr.number(npc, nc, "_persuadeProcessingToken", 0xEC)
        input_panel = rr.pointer_field(panel, pc, "DialogueInput", offset=0x118)
        ic = rr.obj(input_panel, "Game.DialogueInputPanel")
        if not rr.q(input_panel + 16, anchored=True):
            raise Refused("说服输入界面已销毁。")
        flags["can_submit"] = rr.flag(input_panel, ic, "m_CanSubmit", 0x128)
        # m_SubmitAvailable only reflects text/input availability. Empty input
        # is legal here; we never submit it or call an AI service.
        rr.flag(input_panel, ic, "m_SubmitAvailable", 0x129)
        flow = rr.flow(panel, pc, npc_id, topic_id)
        config = rr.configuration(npc_id, topic_id, flow["sub_id"])
        flags.update(flow_notified=flow["notified"], flow_ended=flow["ended"], flow_cancelled=flow["cancelled"], max_rounds=config["max_rounds"])
        reason = readiness(flags)
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified") or raw.get("process_creation_filetime") != self.game.stamp[1]:
            raise Refused("无法确认当前角色与世界。")
        post_stable = stable_roots(raw)
        rr.absorb(raw["anchors"])
        if rr.pointer_field(npc, nc, "<GameWorld>k__BackingField", offset=0x168) != raw["world"]:
            raise Refused("说服对象已不属于当前世界。")
        membership = rr.npc_membership(raw["world"], npc, npc_id)
        event = rr.pointer_field(npc, nc, "OnPersuadeEnded", 0x15, offset=0x120)
        callbacks = rr.event_subscription(event, panel, pc)
        # OnPersuadeResult clears these existing containers after the event.
        chat = rr.pointer_field(npc, nc, "<PersuadeChatMessages>k__BackingField", 0x15, offset=0xD0)
        ledger = rr.pointer_field(npc, nc, "_persuadeLedger", 0x15, offset=0xF8)
        rr.obj(chat, "System.Collections.Generic.List`1")
        rr.obj(ledger, "System.Collections.Generic.List`1")
        context = None
        try:
            context = require_safe_persuasion_context(self.game.resolver, npc)
            rr.absorb(context["anchors"])
        except AcquisitionContextRefused as error:
            reason = str(error)
        identity = (self.game.stamp, raw["world"], raw["player"], manager, panel, npc, npc_id, topic_id,
                    session, flow["sub_id"], flow["closure"], flow["command"], flow["context"], flow["activation_id"],
                    tuple((k, v["address"]) for k, v in sorted(flow["callbacks"].items())),
                    tuple(sorted(context["identity"].items())) if context else None)
        key = hashlib.sha256(repr(identity).encode()).hexdigest()
        descriptor = dict(rr._native_registry, manager=hex(manager), panel=hex(panel), panel_class=pc["klass"],
            npc=hex(npc), npc_class=nc["klass"], world=hex(raw["world"]), player=hex(raw["player"]),
            npc_id=npc_id, topic_id=topic_id, session_id=session, sub_id=flow["sub_id"], flow=flow, config=config,
            input_panel=hex(input_panel), input_class=ic["klass"], event=hex(event), event_callbacks=callbacks,
            chat=hex(chat), ledger=hex(ledger), membership=membership,
            processing_token=processing_token, peek_token=peek_token, round_key=key,
            post_stable_anchors=post_stable)
        descriptor["anchors"] = rr.proof()
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("读取期间游戏进程已变化。")
        return dict(active=True, can_solve=not reason, reason=reason, identity=identity, native=descriptor,
                    npc_id=npc_id, topic_id=topic_id, session_id=session, sub_id=flow["sub_id"],
                    progress=flags["progress"], rounds=flags["rounds"], max_rounds=config["max_rounds"],
                    threshold=config["threshold"], exit_delay_ms=config["exit_delay_ms"])

    def prepare_solve(self, shown):
        if not isinstance(shown, dict) or not shown.get("can_solve") or not shown.get("identity"):
            raise Refused("请先读取一个空闲且有效的当前说服局次。")
        state = self.snapshot()
        if not state.get("can_solve") or state.get("identity") != shown["identity"]:
            raise Refused("说服对象、局次或状态已变化，请重新读取。")
        state["native"]["method_info"] = self.resolver.method(int(state["native"]["npc_class"], 16), METHOD)
        state["native"]["method_specs"] = {key: selected_method_spec(self.resolver, spec)
                                             for key, spec in METHODS.items()}
        state["native"]["method_spec"] = state["native"]["method_specs"]["result"]
        state["native"]["anchors"] = self.resolver.proof()
        return state

    def verify_native(self, outcome, state):
        expected = dict(npc_id=state["npc_id"], topic_id=state["topic_id"], session_id=state["session_id"],
                        end_reason=1, current_topic_id=0)
        if (any(type(outcome.get(k)) is not int or outcome[k] != v for k, v in expected.items())
                or any(outcome.get(k) is not True for k in ("native_won", "normal_countdown", "panel_ended", "settlement_is_win"))):
            raise UncertainWrite("说服操作已派发，但正常成功结果未完整确认；请核对游戏，勿重复操作。")
        return dict(verified=True, settlement_verified=False, phase="success_countdown",
                    message="已触发本次说服成功，请等待游戏正常倒计时并完成结算。奖励、互动次数和后续剧情仍由游戏处理。")

    def solve(self, shown):
        try:
            return self.native.solve(shown)
        except UncertainWrite:
            self.blocked = True
            raise

    def close(self):
        self.native.close()
