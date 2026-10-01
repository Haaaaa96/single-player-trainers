"""Fully reveal the selected owned stone through its original UI action.

Natural flesh, blooms, cracks and value calculations stay authoritative; no
stone attributes, inventory rewards or exchange selections are manufactured.
"""
import hashlib
import json
import struct
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from dual_cultivation_native import MiniGameOnce

NS = "Game.UI.UPFLogic.GambleStone."
SPECS = json.loads((RESOURCE_ROOT / "jade_specs.json").read_text(encoding="utf8"))
# Rendering-only members removed by the game are not part of this adapter's
# ownership, progress or settlement proof. Keep all fields actually read below.
READ_SPECS = {**SPECS}
_VM = NS + "UPFGambleStonePanelViewModel"
READ_SPECS[_VM] = {**SPECS[_VM], "fields": [f for f in SPECS[_VM]["fields"] if f["name"] not in (
    "BloomRevealed", "m_CrackCoreStrokes", "m_CrackHighlightStrokes", "m_CrackShadowStrokes")]}
METHOD = dict(name="RevealAll", token=0x06010584, rva=0xA86210, argc=0, returns=1,
              prefix="40534883ec3033d2488bd9e8607cffff", params=[])


def exchange_status(state):
    """Describe the game's own decision; revealing a stone is not exchanging it."""
    if state.get("exchanged"):
        return "该原石已经完成兑换。"
    if state.get("ratio", 0) < 1:
        return "原石尚未全部揭示；兑换还需满足游戏的估值和原石类型条件。"
    if state.get("can_exchange") is True:
        return "已全部揭示，游戏当前允许选择兑换；请在游戏内自行确认。"
    if state.get("can_exchange") is False:
        return "已全部揭示，但游戏当前未开放兑换；估值或原石类型尚未满足可兑换条件。"
    return "已全部揭示；当前兑换状态未读到，请刷新或查看游戏。"


class JadeAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = RegisteredMiniResolver(game.resolver.reader, READ_SPECS, NS + "UPFGambleStonePanel",
                                               metadata_base=game.resolver.meta)
        self.native = MiniGameOnce(game, self, operation="jade_reveal_all", method_spec=METHOD,
                                   journal_name="jade-reveal-once.json")

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("刮玉连接已停止。")
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已变化。")
        rr.anchors = []
        manager, panels = rr.registered_panels()
        states = []
        for panel in panels:
            visible = rr.visible_panel(panel)
            if visible is None:
                continue
            pc, actionable = visible
            vm = rr.pointer_field(panel, pc, "m_ViewModel", offset=0xC8)
            if not vm:
                continue
            vc = rr.obj(vm, NS + "UPFGambleStonePanelViewModel")
            stone = rr.pointer_field(vm, vc, "m_SelectedStone", offset=0x28)
            if not stone:
                continue
            sc = rr.obj(stone, NS + "GambleStoneInstance")
            source = rr.pointer_field(stone, sc, "SourceItem", offset=0x58)
            record = rr.pointer_field(stone, sc, "SaveRecord", offset=0x60)
            if not source or not record:
                raise Refused("仅支持当前背包中的真实原石，不修改演示或预览对象。")
            raw = self.game.resolver.resolve()
            if not raw.get("anchor_verified"):
                raise Refused("刮玉当前角色归属未确认。")
            owned = [i for i in raw["items"] if i["object"] == source and i["class_name"] == "Game.Model.Components.GambleStoneBagItem" and i["count"] > 0]
            if len(owned) != 1:
                raise Refused("选中原石并非当前角色持有的唯一背包条目。")
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in raw["anchors"])
            count_address = owned[0]["count_address"]
            rr.anchor(count_address, 4)
            ic = rr.obj(source, "Game.Model.Components.GambleStoneBagItem")
            rc = rr.obj(record, "Game.Model.Player.Components.GambleStoneSaveRecord")
            sid = struct.unpack("<q", rr.anchor(source + rr._field(ic, "<StoneInstanceId>k__BackingField", 0x0A), 8))[0]
            rid = struct.unpack("<q", rr.anchor(record + rr._field(rc, "<InstanceId>k__BackingField", 0x0A), 8))[0]
            item_id = rr.integer(stone, sc, "ItemId")
            seed = rr.integer(stone, sc, "Seed")
            if (sid <= 0 or sid != rid or item_id != owned[0]["item_id"]
                    or rr.integer(record, rc, "<SourceItemId>k__BackingField") != item_id
                    or rr.integer(record, rc, "<Seed>k__BackingField") != seed):
                raise Refused("原石实例、背包与保存记录不一致。")
            details = rr.boolean(stone, sc, "DetailsRestored")
            pending_generation = rr.boolean(record, rc, "<GenerationPending>k__BackingField")
            exchanged = rr.boolean(stone, sc, "Exchanged") or rr.boolean(record, rc, "<Exchanged>k__BackingField")
            can_exchange = rr.boolean(vm, vc, "m_CanExchange")
            ratio = rr.float_field(stone, sc, "RevealRatio", anchored=True)
            value = rr.integer(stone, sc, "CurrentValue")
            record_ratio = rr.float_field(record, rc, "<RevealRatio>k__BackingField", anchored=True)
            record_value = rr.integer(record, rc, "<CurrentValue>k__BackingField")
            if not 0 <= ratio <= 1 or not 0 <= value <= 2147483647:
                raise Refused("原石当前进度或估值不合法。")
            if not details or pending_generation:
                raise Refused("原石细节尚未加载完成，请等待后刷新。")
            for field in ("Template", "Flesh"):
                if not rr.pointer_field(stone, sc, field):
                    raise Refused("原石配置尚未就绪。")
            features = []
            for plural, typename, seen_offset in (("Blooms", "GambleStoneBloomInstance", 0x1C), ("Cracks", "GambleStoneCrackInstance", 0x2C)):
                collection = rr.pointer_field(stone, sc, plural, 0x15)
                for feature in rr.object_list(collection, NS + typename, maximum=64):
                    fc = rr.obj(feature, NS + typename)
                    config = rr.pointer_field(feature, fc, "<Config>k__BackingField")
                    seen_address = feature + rr._field(fc, "<Seen>k__BackingField", 2)
                    if not config or seen_address != feature + seen_offset:
                        raise Refused("玉石特征类型或布局不同。")
                    rr.boolean(feature, fc, "<Seen>k__BackingField")
                    features.append(dict(address=hex(feature), config=hex(config), seen=hex(seen_address), kind=plural))
            flags = []
            for name, expected in (("m_CanScratch", True), ("m_ExchangeChoiceVisible", False), ("m_ExchangeResultVisible", False),
                                   ("m_ScratchSessionActive", False), ("m_ScratchDirty", False), ("m_HasPendingScratchSettlement", False)):
                actual = rr.boolean(vm, vc, name)
                flags.append(dict(address=hex(vm + rr._field(vc, name, 2)), expected=expected, label=name, actual=actual))
            selection = rr.integer(vm, vc, "m_StoneSelectionVersion")
            view_bound = rr.boolean(panel, pc, "m_ViewBound")
            reason = ""
            if exchanged or ratio >= 1:
                reason = exchange_status(dict(exchanged=exchanged, ratio=ratio, can_exchange=can_exchange))
            elif not actionable or not view_bound or any(f["actual"] != f["expected"] for f in flags):
                reason = "请停下刮玉操作，关闭兑换或暂停界面，等待原石状态稳定后刷新。"
            identity = (self.game.stamp, manager, panel, vm, stone, source, record, sid, owned[0]["uid"], item_id, seed, selection)
            key = hashlib.sha256(repr((self.game.stamp, sid, owned[0]["uid"])).encode()).hexdigest()
            descriptor = dict(rr._native_registry, manager=hex(manager), panel=hex(panel), vm=hex(vm), stone=hex(stone), source=hex(source), record=hex(record),
                vm_class=vc["klass"], instance_id=str(sid), source_uid=str(owned[0]["uid"]), item_id=item_id, seed=seed,
                ratio_before=ratio, value_before=value, flags=flags, features=features, round_key=key,
                record_ratio_address=hex(record + rr._field(rc, "<RevealRatio>k__BackingField", 12)),
                record_value_address=hex(record + rr._field(rc, "<CurrentValue>k__BackingField", 8)))
            states.append(dict(active=True, can_solve=not reason, reason=reason, identity=identity, native=descriptor,
                               item_id=item_id, instance_id=str(sid), ratio=ratio, current_value=value,
                               can_exchange=can_exchange, exchanged=exchanged,
                               blooms=sum(f["kind"] == "Blooms" for f in features), cracks=sum(f["kind"] == "Cracks" for f in features)))
        if len(states) > 1:
            raise Refused("存在多个刮玉活动界面，未选择目标。")
        proof = rr.proof()
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        if not states:
            return dict(active=False, can_solve=False, reason="请先进入刮玉界面并选中背包中的原石。")
        states[0]["native"]["anchors"] = proof
        return states[0]

    def prepare_solve(self, shown):
        if not isinstance(shown, dict) or not shown.get("can_solve") or not shown.get("identity"):
            raise Refused("请先读取当前可刮的原石。")
        state = self.snapshot()
        if (not state.get("can_solve") or state.get("identity") != shown["identity"]
                or state["ratio"] != shown["ratio"] or state["current_value"] != shown["current_value"]):
            raise Refused("选中原石或刮玉状态已变化，请刷新。")
        state["native"]["method_info"] = self.resolver.method(int(state["native"]["vm_class"], 16), METHOD)
        state["native"]["method_spec"] = selected_method_spec(self.resolver, METHOD)
        state["native"]["anchors"] = self.resolver.proof()
        return state

    def verify_native(self, outcome, state):
        if (outcome.get("fully_revealed") is not True or outcome.get("record_verified") is not True
                or outcome.get("instance_id") != state["instance_id"] or type(outcome.get("current_value")) is not int
                or not 1 <= outcome["current_value"] <= 2147483647):
            raise UncertainWrite("刮玉已派发，但完整揭示或原石记录未确认；请核对游戏。")
        display = {name: state[name] for name in ("item_id", "instance_id", "blooms", "cracks")}
        display.update(active=True, can_solve=False, ratio=1.0, current_value=outcome["current_value"],
                       can_exchange=None, exchanged=False, result_snapshot=True)
        return dict(verified=True, phase="fully_revealed", settlement_verified=False,
                    display_state=display,
                    message=f"本次原石已全部揭示，游戏估值 {outcome['current_value']}。天然品质与天然裂纹未改变；完整揭示不保证达到兑换门槛。请在游戏内保存。")

    def solve(self, shown):
        try:
            result = self.native.solve(shown)
        except UncertainWrite:
            self.blocked = True
            raise
        # Completion was already checked on the game thread and journalled. A
        # later display-only read failure must neither erase it nor permit retry.
        try:
            fresh = self.snapshot()
        except Exception:
            note = "本次结果已核验；兑换状态刷新失败，请稍后重新读取。"
        else:
            if (not fresh.get("active") or fresh.get("identity") != shown["identity"]):
                note = "当前选择或界面已变化；下面保留本次原石已核验结果，请重新读取当前选择。"
            elif fresh.get("ratio") != 1.0 or fresh.get("current_value") != result["display_state"]["current_value"]:
                note = "原石状态在完成后又发生变化；下面保留本次已核验结果，请重新读取。"
            else:
                result["display_state"] = dict(result["display_state"],
                                               can_exchange=fresh["can_exchange"], exchanged=fresh["exchanged"])
                note = exchange_status(result["display_state"])
        result["message"] += "\n" + note
        return result

    def close(self):
        self.native.close()
