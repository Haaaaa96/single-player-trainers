"""Reviewed pill-refining QTE completion; costs and rewards remain in game code."""
import hashlib
import json
import math
import struct

from acquisition_context import AcquisitionContextRefused, _Context
from alchemy_context import require_safe_alchemy_context
from character_attributes_interact import InteractResolver
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from dual_cultivation_native import MiniGameOnce
from learning_adapter import probe
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

DATA = json.loads((RESOURCE_ROOT / "alchemy_specs.json").read_text(encoding="utf8"))
SPECS = DATA["metadata"]
NS = "Game.UI.UPFLogic.RefiningPills."
PANEL = NS + "UPFRefiningPillsQtePanel"
METHOD = DATA["methods"]["FinishQte"]
# Complete layouts checked against the old native entry and build 25617557's
# current FieldInfo plus FinishQte code. Never mix offsets across these layouts.
QTE_LAYOUTS = (
    dict(_context=0x148, OnQteFinished=0x150, _running=0x106, _stages=0xD0,
         _fireResultDeferred=0x158, _qteResultEmitted=0x159,
         _abortConfirmPending=0x15A, _cinematicPending=0x208),
    dict(_context=0x150, OnQteFinished=0x158, _running=0x106, _stages=0xD0,
         _fireResultDeferred=0x160, _qteResultEmitted=0x161,
         _abortConfirmPending=0x162, _cinematicPending=0x210),
)


def qte_layout(resolver, panel_class):
    kinds = dict(_context=0x12, OnQteFinished=0x15, _stages=0x15)
    actual = {name: resolver._field(panel_class, name, kinds.get(name, 2))
              for name in QTE_LAYOUTS[0]}
    if actual not in QTE_LAYOUTS:
        raise Refused("炼丹状态布局与已审核原生入口不匹配。")
    if actual == QTE_LAYOUTS[1] and resolver._field(panel_class, "_awaitingIgnition", 2) != 0x10C:
        raise Refused("炼丹注入灵力状态与已审核启动入口不匹配。")
    return actual


def validate_qte(values):
    """Validate a running, paid round, without freezing its ticking progress."""
    if any(values.get(k) for k in ("emitted", "deferred", "abort", "cinematic", "refunded")):
        return False, "炼丹正在确认退出、过场或结算，请等待。"
    if values.get("awaiting_ignition"):
        return False, "本局等待注入灵力。请先在游戏内添加灵力开始控火，再读取；修改器不会代为注入。"
    if not values.get("actionable") or not values.get("running"):
        return False, "请先在游戏中正常投入材料并开始炼丹火候小游戏。"
    if values["pending_costs"] and not values["committed"]:
        return False, "本轮材料尚未完成正常扣除，不能自动结算。"
    nums = [values[k] for k in ("progress", "maximum", "fan", "xian", "shen", "remaining", "stage_remaining", "score")]
    if not all(isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x) for x in nums):
        raise Refused("炼丹火候、品质阈值或计时异常。")
    if not (0 <= values["progress"] <= values["maximum"] == DATA["progress_max"]
            and 0 <= values["fan"] <= values["xian"] <= values["shen"] <= values["maximum"]
            and values["shen"] > 0 and 0 < values["remaining"] <= 3600
            and 0 < values["stage_remaining"] <= values["remaining"] + 1
            and 0 <= values["stage"] < values["stage_count"] <= 32 and values["score"] >= 0):
        raise Refused("本轮炼丹配置或数值不在已审核范围。")
    return True, "只完成当前火候局，达到当前配置的最高品阶；材料、丹毒、奖励和自动存档仍由游戏处理。"


class AlchemyResolver(RegisteredMiniResolver):
    def __init__(self, reader, **kwargs):
        # Constructed generic dictionary/entry classes do not carry a direct
        # type-definition handle. Their field tokens/layout are checked below.
        specs = {k: v for k, v in SPECS.items() if k not in ("System.Collections.Generic.Dictionary`2", ".Entry")}
        super().__init__(reader, specs, PANEL, **kwargs)

    def class_address(self, fullname):
        if fullname not in ("Game.UIManager", "Game.ConfigManager", "LubanDatas.Tables"):
            return super().class_address(fullname)
        # These are owned by A1Main's live manager list. A whole-heap scan here
        # can exhaust its budget after the game has run for a while. Follow the
        # already reviewed owner chain; never select an unowned heap object.
        context = _Context(self)
        main, _ = context.managers()
        mc = context.obj(main, "Game.A1Main")
        listing = context.pointer(main + context.field(mc, "_managers", 0x15), "alchemy.managers")
        lc = context.obj(listing, "System.Collections.Generic.List`1")
        count = context.i(listing + context.field(lc, "_size", 8), "alchemy.managers.size")
        if not 1 <= count <= 128:
            raise Refused("炼丹管理器列表长度异常。")
        array = context.pointer(listing + context.field(lc, "_items", 0x1D), "alchemy.managers.items")
        if not count <= context.q(array + 24, "alchemy.managers.capacity") <= 256:
            raise Refused("炼丹管理器列表容量异常。")
        pointers = struct.unpack("<" + "Q" * count,
                                 context.anchor(array + 32, count * 8, "alchemy.managers.entries"))
        owner = "Game.ConfigManager" if fullname == "LubanDatas.Tables" else fullname
        matches = []
        for pointer in pointers:
            c = context.obj(pointer)
            if c["namespace"] + "." + c["name"] == owner:
                matches.append((pointer, self.obj(pointer, owner)))
        if len(matches) != 1:
            raise Refused("炼丹所需管理器未就绪或不唯一：" + owner)
        pointer, c = matches[0]
        if fullname == "LubanDatas.Tables":
            pointer = self.q(pointer + self.reviewed_field(c, "<Tables>k__BackingField", 0x12), anchored=True)
            c = self.obj(pointer, fullname)
        klass = int(c["klass"], 16)
        from class_scan import candidate
        self.runtime_spec(fullname, self.specs[fullname])
        checked, reason = candidate(self.reader, klass, self._runtime.specs[fullname], self.meta)
        if checked is None:
            raise Refused("炼丹管理器类型身份校验失败：" + str(reason))
        context._finish_snapshot("读取期间炼丹管理器发生变化，请刷新。")
        self.anchors.extend((a["address"], a["expected_hex"]) for a in context.anchors)
        return klass

    def info(self, klass, fullname=None):
        if fullname != "LubanDatas.data.Constants":
            return super().info(klass, fullname)
        # This large reviewed class exceeds the ordinary inspector bound. Use
        # its current metadata count only after proving the exact definition.
        spec = self.runtime_spec(fullname, SPECS[fullname])
        count = struct.unpack("<H", self.anchor(klass + 0x124, 2))[0]
        if (count != spec["field_count"] or not 1 <= count <= 1024
                or self.q(klass + 0x78, anchored=True) != klass
                or self.q(klass + 0x68, anchored=True) != self.meta + spec["type_definition_offset"]
                or self.i(klass + 0x11C, anchored=True) != spec["token"]):
            raise Refused("炼丹常量类元数据标识不匹配。")
        name = self.reader.string(self.q(klass + 16, anchored=True))
        namespace = self.reader.string(self.q(klass + 24, anchored=True))
        size = self.i(klass + 0xF8, anchored=True)
        if namespace + "." + name != fullname or not 0x960 <= size <= 65536:
            raise Refused("炼丹常量类名称或大小不匹配。")
        c = probe.inspect_class(self.reader, klass, max_fields=count)
        if (not c or c["namespace"] + "." + c["name"] != fullname
                or len(c["fields"]) != count or c["instance_size"] != size
                or any(int(f["parent"], 16) != klass for f in c["fields"])
                or [(f["name"], int(f["token"], 16)) for f in c["fields"]]
                != [(f["name"], f["token"]) for f in spec["fields"]]):
            raise Refused("炼丹常量字段清单与审核版本不同。")
        return c

    def reviewed_field(self, c, name, kind, *, static=False):
        full = c["namespace"] + "." + c["name"]
        spec = self.runtime_spec(full, SPECS[full]) if full in SPECS else {}
        token = next((f["token"] for f in spec.get("fields", ()) if f["name"] == name), None)
        if token is None:
            raise Refused("炼丹字段未审核。")
        return self.field(c, name, kind, token, static=static)

    tables = InteractResolver.tables
    table_rows = InteractResolver.table_rows
    list_objects = InteractResolver.list_objects

    def maximum(self):
        tables, tc = self.tables()
        table = self.q(tables + self.reviewed_field(tc, "<TbConstants>k__BackingField", 0x12), anchored=True)
        c = self.obj(table, "LubanDatas.TbConstants")
        overrides = self.q(table + self.reviewed_field(c, "_overrides", 0x15), anchored=True)
        if overrides:
            dc = self.obj(overrides, "System.Collections.Generic.Dictionary`2")
            count = self.i(overrides + self.reviewed_field(dc, "_count", 8), anchored=True)
            free = self.i(overrides + self.reviewed_field(dc, "_freeCount", 8), anchored=True)
            self.i(overrides + self.reviewed_field(dc, "_version", 8), anchored=True)
            if not 0 <= count == free <= 1024:
                raise Refused("游戏常量存在运行时覆盖，暂不支持自动炼丹。")
        constants = self.q(table + self.reviewed_field(c, "_data", 0x12), anchored=True)
        cc = self.obj(constants, "LubanDatas.data.Constants")
        offset = self.reviewed_field(cc, "<ALCHEMY_QTE_PROGRESS_MAX>k__BackingField", 8)
        # The current getter (RVA 0xF09700) reads +0x97C; the original
        # reviewed getter reads +0x95C. FieldInfo must independently agree.
        if offset not in (0x95C, 0x97C):
            raise Refused("炼丹进度上限字段与原生 getter 不同。")
        return self.i(constants + offset, anchored=True), constants + offset

    def managed_string(self, address):
        self.obj(address, "System.String")
        size = self.i(address + 16, anchored=True)
        if not 1 <= size <= 80:
            raise Refused("炼丹事务编号无效。")
        text = self.anchor(address + 20, size * 2).decode("utf-16-le", errors="strict")
        if not text.strip():
            raise Refused("炼丹事务编号为空。")
        return text


class AlchemyAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = AlchemyResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self._native = MiniGameOnce(game, self, operation="alchemy_perfect", method_spec=METHOD,
                                    journal_name="alchemy-qte-rounds.json")

    def _begin(self):
        if self.blocked or self.game.blocked or process_identity(self.resolver.reader.h) != self.game.stamp:
            raise Refused("炼丹连接已停止或游戏身份变化，请重新连接。")
        raw = self.game.resolver.resolve()
        if not raw.get("anchor_verified"):
            raise Refused("当前角色身份无法核对。")
        self.resolver.anchors = [(a["address"], a["expected_hex"]) for a in raw["anchors"]]
        return raw

    def snapshot(self):
        raw, rr = self._begin(), self.resolver
        manager, panels = rr.registered_panels()
        states = []
        for panel in panels:
            visible = rr.visible_panel(panel)
            if not visible:
                continue
            pc, actionable = visible
            layout = qte_layout(rr, pc)
            context = rr.pointer_field(panel, pc, "_context", offset=layout["_context"])
            if not context:
                continue
            cc = rr.obj(context, "Game.CondenseContext")
            values = dict(actionable=actionable)
            fields = {"running": "_running", "emitted": "_qteResultEmitted",
                      "deferred": "_fireResultDeferred", "abort": "_abortConfirmPending",
                      "cinematic": "_cinematicPending"}
            for key, name in fields.items():
                values[key] = rr.boolean(panel, pc, name)
            values["awaiting_ignition"] = (rr.boolean(panel, pc, "_awaitingIgnition")
                                          if layout == QTE_LAYOUTS[1] else False)
            for key, name in (("progress", "_progressPct"), ("fan", "_fanThreshold"),
                              ("xian", "_xianThreshold"), ("shen", "_shenThreshold"),
                              ("remaining", "_totalRemainSec"), ("stage_remaining", "_stageRemainSec"), ("score", "_score")):
                values[key] = rr.float_field(panel, pc, name, anchored=key in ("fan", "xian", "shen"))
            values["maximum"], maximum_address = rr.maximum()
            values["stage"] = rr.integer(panel, pc, "_curStageIdx", anchored=False)
            stages = rr.pointer_field(panel, pc, "_stages", 0x15, offset=layout["_stages"])
            sc = rr.obj(stages, "System.Collections.Generic.List`1")
            values["stage_count"] = rr.integer(stages, sc, "_size")
            rr.integer(stages, sc, "_version")
            operation = rr.pointer_field(context, cc, "OperationId", 0x0E, offset=0x68)
            operation_id = rr.managed_string(operation)
            recipe = rr.pointer_field(context, cc, "Recipe", offset=0x18)
            if not recipe:
                raise Refused("本局未选定丹方，不提供自动结算。")
            rr.obj(recipe, "Game.RefiningPillsRecipeCardModel")
            values["pending_costs"] = rr.pointer_field(context, cc, "PendingHerbCosts", 0x15, offset=0x50)
            values["committed"] = rr.boolean(context, cc, "_pendingCostsCommitted")
            values["refunded"] = rr.boolean(context, cc, "HerbsRefunded")
            callback = rr.pointer_field(panel, pc, "OnQteFinished", 0x15, offset=layout["OnQteFinished"])
            if not callback:
                raise Refused("本轮炼丹没有正常结算回调。")
            bc = rr.info(int(pc["parent"], 16), "Game.BaseUI")
            handle = rr.integer(panel, bc, "<HandleToken>k__BackingField")
            can_solve, reason = validate_qte(values)
            try:
                safe = require_safe_alchemy_context(self.game.resolver)
                rr.anchors.extend((a["address"], a["expected_hex"]) for a in safe["anchors"])
            except AcquisitionContextRefused:
                can_solve, reason = False, "战斗、场景切换或结算中不可自动炼丹。"
            identity = (self.game.stamp, raw["manager"], raw["store"], raw["world"], raw["player"],
                        manager, panel, handle, context, recipe, operation, operation_id, callback)
            phase = ("waiting_ignition" if values["awaiting_ignition"] else
                     "running" if values["running"] else "settling")
            states.append(dict(active=True, can_solve=can_solve, reason=reason, phase=phase, identity=identity,
                values=values, native=dict(panel=hex(panel), panel_class=pc["klass"], context=hex(context),
                    recipe=hex(recipe), operation_id=hex(operation), callback=hex(callback), manager=hex(manager),
                    handle=handle, maximum=values["maximum"], maximum_address=hex(maximum_address),
                    stage_count=values["stage_count"], stages=hex(stages), **rr._native_registry)))
        if len(states) > 1:
            raise Refused("发现多个炼丹火候面板，未提供操作目标。")
        proof = rr.proof()
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("读取期间游戏身份变化。")
        if not states:
            return dict(active=False, can_solve=False, reason="请先在游戏中正常投入材料，开始炼丹火候小游戏。", values={})
        state = states[0]
        state["native"].update(anchors=proof, round_key=hashlib.sha256(repr(state["identity"]).encode()).hexdigest())
        return state

    def prepare_solve(self, shown=None):
        state = self.snapshot()
        if not state.get("can_solve"):
            raise Refused(state["reason"])
        if shown is not None and shown.get("identity") != state["identity"]:
            raise Refused("炼丹局次或事务已经变化，请重新读取。")
        state["native"]["method_info"] = self.resolver.method(int(state["native"]["panel_class"], 16), METHOD)
        state["native"]["method_spec"] = selected_method_spec(self.resolver, METHOD)
        state["native"]["anchors"] = self.resolver.proof()
        return state

    def verify_native(self, outcome, state):
        if (outcome.get("running") is not False or outcome.get("progress") != state["native"]["maximum"]
                or outcome.get("quality") != 3 or not (outcome.get("result_emitted") is True or outcome.get("result_deferred") is True)):
            raise UncertainWrite("炼丹结算入口已执行，但当前局的后置状态未完整确认。")
        return dict(verified=True, settlement_verified=False, phase="settling",
                    message="火候已达到最高品阶，游戏正在正常结算；请在游戏中查看成丹、数量和丹毒。")

    def solve(self, shown):
        try:
            return self._native.solve(shown)
        except UncertainWrite:
            self.blocked = True
            raise

    def close(self):
        self._native.close()
