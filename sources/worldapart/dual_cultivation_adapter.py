"""Current registered dual-cultivation round; normal native completion only."""
import hashlib
import json
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from dual_cultivation_native import MiniGameOnce

NS = "Game.UI.UPFLogic.DualCultivate."
SPECS = json.loads((RESOURCE_ROOT / "dual_cultivation_specs.json").read_text(encoding="utf8"))
METHOD = dict(name="Complete", token=0x06010D8C, rva=0xAC8B00, argc=1, returns=1,
              prefix="48895c2418554883ec30803d99e8a707", params=[2])


class DualCultivationAdapter:
    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = RegisteredMiniResolver(game.resolver.reader, SPECS, NS + "DualCultivatePanel",
                                               metadata_base=game.resolver.meta)
        self.native = MiniGameOnce(game, self, operation="dual_cultivation_complete", method_spec=METHOD,
                                   journal_name="dual-cultivation-once.json")

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused("双修连接已停止。")
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
            runtime = rr.pointer_field(panel, pc, "m_Game", offset=0xD8)
            if not runtime:
                continue
            rc = rr.obj(runtime, NS + "DualCultivateGameViewModel")
            cfg = rr.pointer_field(runtime, rc, "m_Config", offset=0x28)
            cc = rr.obj(cfg, NS + "DualCultivateGameConfig")
            npc = rr.integer(panel, pc, "m_NpcId")
            config_id = rr.integer(panel, pc, "m_DualCultivateId")
            if (npc <= 0 or config_id <= 0 or rr.integer(runtime, rc, "m_NpcId") != npc
                    or rr.integer(runtime, rc, "m_DualCultivateId") != config_id):
                raise Refused("双修对象或配置编号不一致。")
            phase = rr.integer(runtime, rc, "m_Phase", 0x11)
            ready = rr.boolean(runtime, rc, "m_IsPresentationReady")
            settlement = rr.boolean(panel, pc, "m_SettlementStarted")
            callback = rr.boolean(panel, pc, "m_ResultCallbackInvoked")
            rr.boolean(panel, pc, "m_PendingResultIsWin")
            completed = rr.pointer_field(runtime, rc, "m_Completed", 0x15, offset=0x58)
            final_callback = rr.pointer_field(panel, pc, "m_ActionOnGameEnd", 0x15, offset=0xE8)
            slots = rr.pointer_field(runtime, rc, "<Slots>k__BackingField", 0x15, offset=0x68)
            slot_objects = rr.object_list(slots, NS + "DualCultivateSlotViewModel", observable=True, maximum=3)
            if len(slot_objects) != 3:
                raise Refused("双修引导槽数量与已验证布局不同。")
            for slot in slot_objects:
                sc = rr.obj(slot, NS + "DualCultivateSlotViewModel")
                if rr.pointer_field(slot, sc, "m_Owner") != runtime:
                    raise Refused("双修引导槽归属不同。")
            required = rr.integer(cfg, cc, "RequiredResonance")
            limit = rr.integer(cfg, cc, "TimeLimitSec")
            remaining = rr.float_field(runtime, rc, "m_TimeRemaining")
            resonance = rr.float_field(runtime, rc, "m_Resonance")
            if not 0 < required <= 1000000 or not 0 < limit <= 86400 or not 0 <= resonance <= 1000000 or not 0 <= remaining <= limit:
                raise Refused("双修配置或当前进度超出可核对范围。")
            reason = ""
            if settlement or callback or phase in (2, 3):
                reason = "本局双修已结束或正在结算，请在游戏内继续结果界面。"
            elif not actionable:
                reason = "双修当前已暂停或被其他界面遮挡，请回游戏恢复后重新读取。"
            elif not ready:
                reason = "双修演出尚未加载完成，请等待游戏就绪后重新读取。"
            elif phase == 0:
                reason = "双修尚未开始，请先按游戏界面提示开始本局，再点击“读取 / 刷新当前局”。"
            elif phase != 1 or remaining <= 0:
                reason = "当前不处于有效的双修进行阶段，或本局时间已经结束。"
            elif not completed:
                reason = "当前双修结算回调尚未就绪，请重新读取。"
            # ExecuteConfiguredFlow's normal caller passes null at RVA 0x14F7644;
            # NotifyGameEnd (0xACB6A0) explicitly tolerates a null external callback.
            # Keep that optional pointer in the identity/proof, while requiring
            # m_Completed, the actual VM -> panel settlement callback, above.
            identity = (self.game.stamp, manager, panel, runtime, cfg, npc, config_id, completed, final_callback, slot_objects)
            key = hashlib.sha256(repr(identity).encode()).hexdigest()
            descriptor = dict(rr._native_registry, manager=hex(manager), panel=hex(panel), vm=hex(runtime), config=hex(cfg),
                panel_class=pc["klass"], vm_class=rc["klass"], npc_id=npc, config_id=config_id,
                completed=hex(completed), final_callback=hex(final_callback), slots=hex(slots),
                slot_objects=[hex(s) for s in slot_objects], required_resonance=required, time_limit=limit, round_key=key)
            states.append(dict(active=True, can_solve=not reason, reason=reason, identity=identity, native=descriptor,
                               npc_id=npc, config_id=config_id, resonance=resonance, required=required, remaining=remaining,
                               phase=phase, presentation_ready=ready, actionable=actionable))
        if len(states) > 1:
            raise Refused("发现多个双修活动界面，无法唯一确认。")
        proof = rr.proof()
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("游戏进程已更换。")
        if not states:
            return dict(active=False, can_solve=False, reason="请先在游戏内正常进入双修小游戏。")
        states[0]["native"]["anchors"] = proof
        return states[0]

    def prepare_solve(self, shown):
        if not isinstance(shown, dict) or not shown.get("can_solve") or not shown.get("identity"):
            raise Refused("请先读取一个正在进行的双修局次。")
        state = self.snapshot()
        if not state.get("can_solve") or state.get("identity") != shown["identity"]:
            raise Refused("双修局次或阶段已变化，请刷新。")
        state["native"]["method_info"] = self.resolver.method(int(state["native"]["vm_class"], 16), METHOD)
        state["native"]["method_spec"] = selected_method_spec(self.resolver, METHOD)
        state["native"]["anchors"] = self.resolver.proof()
        return state

    def verify_native(self, outcome, state):
        if (outcome.get("native_won") is not True or outcome.get("settlement_started") is not True
                or outcome.get("npc_id") != state["npc_id"] or outcome.get("config_id") != state["config_id"]):
            raise UncertainWrite("双修已派发，但正常成功结算未确认；请核对游戏。")
        return dict(verified=True, settlement_verified=False, phase="success_settlement_started",
                    message="游戏已进入本局成功结算；请在游戏内完成奖励界面。正常消耗与道侣关系影响仍由游戏处理。")

    def solve(self, shown):
        try:
            return self.native.solve(shown)
        except UncertainWrite:
            self.blocked = True
            raise

    def close(self):
        self.native.close()
