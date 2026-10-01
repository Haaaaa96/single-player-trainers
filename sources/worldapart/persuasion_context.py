"""Readonly persuasion-scene guard; item acquisition permissions stay unchanged."""
import json

from acquisition_context import (_Context, AcquisitionContextRefused)
from runtime_paths import RESOURCE_ROOT

SINGLE_HANDLER = "Game.SpaceHandlers.SingleSpaceHandler"
MAIN_HANDLER = "Game.SpaceHandlers.MainSpaceHandler"
ALLOWED_HANDLERS = frozenset((MAIN_HANDLER, SINGLE_HANDLER))
_METADATA = json.loads((RESOURCE_ROOT / "persuasion_specs.json").read_text(encoding="utf8"))["metadata"]
HANDLER_SPEC = _METADATA[SINGLE_HANDLER]


class PersuasionContext(_Context):
    extra_specs = {SINGLE_HANDLER: HANDLER_SPEC}

    def snapshot(self, npc):
        self._begin_snapshot()
        # The caller resolves this NPC from the current panel and canonical world.
        # A known handler name alone must not authorize a different NPC's room.
        if type(npc) is not int or npc <= 0 or npc % 8:
            raise AcquisitionContextRefused("当前说服 NPC 身份无效。")
        main, managers = self.managers()
        life, lc = managers["Game.GameLifecycleManager"]
        for name in ("m_IsLeaving", "m_ShuttingDown"):
            self.boolean(life, lc, name, False)
        space, sc = managers["Game.SpaceManager"]
        for name in ("_isTransitioning", "m_IsUnloadingWorld"):
            self.boolean(space, sc, name, False)
        for name in ("_pendingChangeSpaceRequest", "m_TransitionPreparation"):
            self.zero_pointer(space, sc, name)
        handler = self.pointer(space + self.field(sc, "_currentSpaceHandler", 0x12), "persuasion.space.handler")
        hc = self.obj(handler)
        fullname = hc["namespace"] + "." + hc["name"]
        if fullname not in ALLOWED_HANDLERS:
            raise AcquisitionContextRefused("当前不是已验证的角色互动或普通非战斗场景。")
        hc = self.info(int(hc["klass"], 16), fullname)
        parent = self.pointer(int(hc["klass"], 16) + 0x58, "persuasion.handler.parent")
        self.info(parent, "Game.SpaceHandlers.BaseSpaceHandler")
        scene_npc = None
        if fullname == SINGLE_HANDLER:
            offset = self.field(hc, "CurNpc", 0x12)
            if offset != 0x38:
                raise AcquisitionContextRefused("角色互动场景的 NPC 布局未经审核。")
            scene_npc = self.pointer(handler + offset, "persuasion.handler.CurNpc")
            if scene_npc != npc:
                raise AcquisitionContextRefused("当前场景角色与说服对象不同，请重新进入对话后刷新。")
        wave_state, wave_instance = self.no_combat("persuasion.wave", "战斗或战斗结算尚未结束，暂不能使用秒说服。")
        self._finish_snapshot("场景或角色在读取期间变化，未执行说服。")
        return dict(status="safe_persuasion_nonbattle", identity=dict(main=main, space_manager=space,
                    space_handler=handler, space_class=fullname, scene_npc=scene_npc,
                    wave_instance=wave_instance, wave_state=wave_state), anchors=self.anchors)


def require_safe_persuasion_context(resolver, npc):
    try:
        return PersuasionContext(resolver).snapshot(npc)
    except AcquisitionContextRefused as error:
        # Shared lifecycle readers predate minigame guards; retain their actual
        # refusal reason while avoiding item-specific wording on the persuasion page.
        text = str(error).replace("未执行添加", "未执行说服").replace("添加物品", "执行说服")
        if text != str(error):
            raise AcquisitionContextRefused(text) from error
        raise
    except Exception as error:
        raise AcquisitionContextRefused("无法核对当前说服场景，请等待场景和对话稳定后刷新。") from error
