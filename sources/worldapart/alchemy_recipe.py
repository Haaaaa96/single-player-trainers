"""Current alchemy map: find one first recipe through normal collection events."""
import hashlib
import json
import math
import struct

from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from dual_cultivation_native import MiniGameOnce
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite

SPECS = json.loads((RESOURCE_ROOT / "alchemy_recipe_specs.json").read_text(encoding="utf8"))
NS = "Game.Logic.RefiningPills.Map."
UI = "Game.UI.UPFLogic.RefiningPills."
PANEL = UI + "UPFRefiningPillsExplorePanel"
METHODS = SPECS["methods"]


def isolated_recipes(raw, position, radius, furnace):
    """Pick bounded current-map candidates; reject any overlapping POI trigger."""
    if (len(raw) % 36 or not 1 <= len(raw)//36 <= 8192 or not 1 <= furnace <= 5
            or not math.isfinite(radius) or not 0 < radius <= 1000
            or any(not math.isfinite(x) for x in position)):
        raise Refused("丹方地图范围无法核对。")
    rows = []
    ids = set()
    for index in range(len(raw)//36):
        ident, kind, element, tier, _, string_index, x, y, _, _, _ = struct.unpack_from("<iBBHiiiiiii", raw, index*36)
        if ident <= 0 or ident in ids or not 0 <= x <= 1000000 or not 0 <= y <= 1000000:
            raise Refused("丹方地图节点异常。")
        ids.add(ident)
        rows.append(dict(index=index, poi_id=ident, kind=kind, tier=tier & 255, string_index=string_index, x=x, y=y))
    candidates = [r for r in rows if r["kind"] == 2 and 1 <= r["tier"] <= furnace
                  and not any(q["index"] != r["index"] and (q["x"]-r["x"])**2 + (q["y"]-r["y"])**2 <= radius**2
                              for q in rows)]
    return sorted(candidates, key=lambda r: ((r["x"]-position[0])**2 + (r["y"]-position[1])**2, r["index"]))


class AlchemyRecipeAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = RegisteredMiniResolver(game.resolver.reader, SPECS["classes"], PANEL, metadata_base=game.resolver.meta)
        self.native = MiniGameOnce(game, self, operation="alchemy_find_recipe", method_spec=METHODS["teleport"],
                                   journal_name="alchemy-recipe-once.json")

    def _string(self, address):
        r = self.resolver
        r.obj(address, "System.String")
        size = r.i(address + 16, anchored=True)
        if not 0 <= size <= 256:
            raise Refused("丹方文字长度异常。")
        return r.anchor(address + 20, size*2).decode("utf-16le") if size else ""

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("丹方连接已停止。")
        r = self.resolver
        if process_identity(r.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        r.anchors = []
        manager, panels = r.registered_panels()
        visible = [(p, r.visible_panel(p)) for p in panels]
        visible = [(p, v) for p, v in visible if v is not None]
        if len(visible) > 1:
            raise Refused("发现多个炼丹探索界面。")
        if not visible:
            return dict(active=False, can_solve=False, reason="请先在游戏内进入炼丹探索地图。")
        panel, (pc, actionable) = visible[0]
        dataset = r.pointer_field(panel, pc, "_dataset", offset=0x1C0)
        move = r.pointer_field(panel, pc, "_movementController", offset=0x220)
        state = r.pointer_field(panel, pc, "_exploreState", offset=0x228)
        vm = r.pointer_field(panel, pc, "_vm", offset=0x138)
        if not all((dataset, move, state, vm)):
            return dict(active=True, can_solve=False, reason="炼丹地图尚未加载完成。")
        dc = r.obj(dataset, NS + "RefiningPillsMapDataset")
        mc = r.obj(move, NS + "RefiningPillsMovementController")
        sc = r.obj(state, NS + "RefiningPillsExploreState")
        vc = r.obj(vm, UI + "UPFRefiningPillsExplorePanelViewModel")
        if r.pointer_field(move, mc, "_dataset") != dataset or r.pointer_field(move, mc, "_state") != state:
            raise Refused("炼丹地图引用不一致。")
        reason = ""
        if not actionable:
            reason = "请关闭暂停与遮挡界面。"
        for name in ("_mapLoadPending", "_spaceHoldRefine", "_pointerHoldRefine", "_wasInputBlockedByModal",
                     "_portalConfirmOpen", "_isCoveredByFullScreenPanel", "_portalAvgRunning"):
            if r.boolean(panel, pc, name):
                reason = "请等待地图加载或动画结束，并松开操作键。"
        for name in ("_mapLoadCoroutine", "_transitionBlockHandoffCoroutine", "_explodeTransitionCoroutine", "_portalWarpCoroutine"):
            if r.pointer_field(panel, pc, name):
                reason = "地图正在过渡，请稍后刷新。"
        for name in ("_holdingMove", "_pendingExplosionReset", "_simulationSuspended"):
            if r.boolean(move, mc, name):
                reason = "炼丹正在移动、暂停或炸炉；请等待稳定后刷新。"
        phase = r.anchor(move + r._field(mc, "_phase", 0x11), 1)[0]
        if phase != 0:
            reason = "请等当前药材轨迹结束，再自动寻找丹方。"
        active_recipe = r.integer(state, sc, "<ActiveRecipeId>k__BackingField")
        obtained = r.boolean(state, sc, "<HasObtainedRecipeEver>k__BackingField")
        if active_recipe or obtained or r.boolean(vm, vc, "_recipeCardIsFilled"):
            reason = "本次探索已经取得丹方；此功能仅寻找本局第一张丹方。"
        if r.boolean(vm, vc, "_isExplodeTransitionVisible"):
            reason = "正在炸炉结算，不能寻方。"
        furnace = r.integer(panel, pc, "_furnaceLevel")
        config_offset = r._field(mc, "_config", 0x11)
        if config_offset != 48:
            raise Refused("炼丹移动配置布局已变化。")
        radius = struct.unpack("<f", r.anchor(move + 56, 4))[0]
        position = struct.unpack("<ff", r.anchor(move + r._field(mc, "_currentPixel", 0x11), 8))
        poi_list = r.pointer_field(dataset, dc, "<Pois>k__BackingField")
        plc = r.obj(poi_list, NS + "RefiningPillsPoiList")
        array = r.pointer_field(poi_list, plc, "<All>k__BackingField", 0x1D)
        ac = r.obj(array, None)
        ec = r.info(r.q(int(ac["klass"], 16) + 0x40, anchored=True), NS + "RefiningPillsPoi")
        if ec["instance_size"] != 52 or r._field(ec, "X", 8) != 32 or r._field(ec, "Y", 8) != 36:
            raise Refused("炼丹地图节点布局已变化。")
        count = r.q(array + 24, anchored=True)
        if not 1 <= count <= 8192:
            raise Refused("炼丹地图节点数量异常。")
        raw = b"".join(r.anchor(array+32+offset, min(3600, count*36-offset)) for offset in range(0, count*36, 3600))
        candidates = isolated_recipes(raw, position, radius, furnace)
        map_vm = r.pointer_field(vm, vc, "<Map>k__BackingField")
        mvc = r.obj(map_vm, UI + "UPFRefiningPillsExploreMapViewModel")
        collection = r.pointer_field(map_vm, mvc, "<Pois>k__BackingField", 0x15)
        cc = r.obj(collection, "Loxodon.Framework.Observables.ObservableList`1")
        listing = r.pointer_field(collection, cc, "items", 0x15)
        lc = r.obj(listing, "System.Collections.Generic.List`1")
        if r.integer(listing, lc, "_size") != count:
            raise Refused("丹方显示列表和地图不一致。")
        r.integer(listing, lc, "_version")
        views = r.pointer_field(listing, lc, "_items", 0x1D)
        if not count <= r.q(views+24, anchored=True) <= 16384:
            raise Refused("丹方显示列表容量异常。")
        selected = None
        for candidate in candidates:
            pv = r.q(views+32+candidate["index"]*8, anchored=True)
            pvc = r.obj(pv, UI + "UPFRefiningPillsExplorePoiViewModel")
            if not r.boolean(pv, pvc, "_isRecipe"):
                raise Refused("丹方节点显示类型不一致。")
            if not r.boolean(pv, pvc, "_isVisible"):
                continue
            name = self._string(r.pointer_field(pv, pvc, "_label", 14))
            if not name or "未知" in name:
                continue
            selected = dict(candidate, name=name, view=hex(pv))
            break
        if selected is None:
            reason = reason or "当前已显示范围内没有可独立触发的丹方，请探索后刷新。"
        string_pool = r.pointer_field(dataset, dc, "<StringPool>k__BackingField", 0x1D)
        string_count = r.q(string_pool+24, anchored=True)
        if selected:
            ix = selected["string_index"]
            if not 0 <= ix < string_count <= 8192:
                raise Refused("丹方编号索引异常。")
            text = self._string(r.q(string_pool+32+ix*8, anchored=True))
            if not text.isascii() or not text.isdecimal() or not 0 < int(text) <= 2147483647:
                raise Refused("丹方编号不是有效整数。")
            selected["recipe_id"] = int(text)
        callbacks = []
        for owner, klass, names in ((move, mc, ("CanConsumePoi", "OnPositionChanged", "OnPoiConsumed")),
                                     (state, sc, ("OnPoiCollected",))):
            for name in names:
                value = r.pointer_field(owner, klass, name, 0x15)
                if not value:
                    reason = "丹方收集回调尚未就绪。"
                callbacks.append(hex(value))
        # Position is deliberately absent from the once-per-round key. Moving
        # after an uncertain result must never authorize another native call.
        identity = (self.game.stamp, manager, panel, dataset, move, state, vm, tuple(callbacks))
        key = hashlib.sha256(repr(identity).encode()).hexdigest()
        descriptor = dict(r._native_registry, round_key=key, manager=hex(manager), panel=hex(panel),
            dataset=hex(dataset), move=hex(move), state=hex(state), vm=hex(vm), panel_class=pc["klass"],
            move_class=mc["klass"], array=hex(array), count=count, radius=radius, furnace=furnace,
            candidate=selected, callbacks=callbacks, position=list(position))
        proof = r.proof()
        if process_identity(r.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        descriptor["anchors"] = proof
        return dict(active=True, can_solve=not reason, reason=reason, identity=identity, native=descriptor,
                    candidate=selected, furnace=furnace, active_recipe=active_recipe)

    def prepare_solve(self, shown):
        if not isinstance(shown, dict) or not shown.get("can_solve"):
            raise Refused("请先读取可寻找的本局第一张丹方。")
        fresh = self.snapshot()
        if (not fresh.get("can_solve") or fresh["identity"] != shown["identity"]
                or fresh["candidate"] != shown["candidate"]):
            raise Refused("当前丹方、地图或探索状态已变化，请刷新。")
        r, n = self.resolver, fresh["native"]
        n["methods"] = {name: r.method(int(n["panel_class"] if name == "available" else n["move_class"], 16), spec)
                        for name, spec in METHODS.items()}
        n["method_info"] = n["methods"]["teleport"]
        n["method_specs"] = {name: selected_method_spec(r, spec) for name, spec in METHODS.items()}
        n["method_spec"] = n["method_specs"]["teleport"]
        n["anchors"] = r.proof()
        return fresh

    def verify_native(self, outcome, state):
        if outcome.get("recipe_id") != state["candidate"]["recipe_id"] or outcome.get("recipe_collected") is not True:
            raise UncertainWrite("已派发寻方，但当前丹方未确认；请检查游戏，勿重复执行。")
        return dict(verified=True, message=f"已取得本局丹方：{state['candidate']['name']}。后续投药、凝丹与丹方记忆仍按游戏正常流程处理。")

    def solve(self, shown):
        try:
            return self.native.solve(shown)
        except UncertainWrite:
            self.blocked = True
            raise

    def close(self):
        self.native.close()
