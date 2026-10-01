"""Pill-specific stable nonbattle context; does not widen item-add permissions."""
import json

from acquisition_context import (_Context, AcquisitionContextRefused)
from runtime_paths import RESOURCE_ROOT

PILL_HANDLER = "Game.SpaceHandlers.RefiningPillsSpaceHandler"
SUB_HANDLER = "Game.SpaceHandlers.SubSpaceHandler"
ALLOWED_HANDLERS = frozenset(("Game.SpaceHandlers.MainSpaceHandler", PILL_HANDLER))
_METADATA = json.loads((RESOURCE_ROOT / "alchemy_specs.json").read_text(encoding="utf8"))["metadata"]
HANDLER_SPECS = {key: _METADATA[key] for key in (PILL_HANDLER, SUB_HANDLER)}


class AlchemyContext(_Context):
    extra_specs = HANDLER_SPECS

    def snapshot(self):
        self._begin_snapshot()
        main, managers = self.managers()
        life, lc = managers["Game.GameLifecycleManager"]
        for name in ("m_IsLeaving", "m_ShuttingDown"):
            self.boolean(life, lc, name, False)
        space, sc = managers["Game.SpaceManager"]
        for name in ("_isTransitioning", "m_IsUnloadingWorld"):
            self.boolean(space, sc, name, False)
        for name in ("_pendingChangeSpaceRequest", "m_TransitionPreparation"):
            self.zero_pointer(space, sc, name)
        handler = self.pointer(space + self.field(sc, "_currentSpaceHandler", 0x12), "alchemy.space.handler")
        hc = self.obj(handler)
        fullname = hc["namespace"] + "." + hc["name"]
        if fullname not in ALLOWED_HANDLERS:
            raise AcquisitionContextRefused("当前不是已验证的炼丹或普通非战斗场景。")
        self.info(int(hc["klass"], 16), fullname)
        parent = self.pointer(int(hc["klass"], 16) + 0x58, "alchemy.handler.parent")
        if fullname == PILL_HANDLER:
            self.info(parent, SUB_HANDLER)
            parent = self.pointer(parent + 0x58, "alchemy.handler.base_parent")
        self.info(parent, "Game.SpaceHandlers.BaseSpaceHandler")
        wave_state, wave_instance = self.no_combat("alchemy.wave", "战斗或战斗结算尚未结束，暂不能使用炼丹辅助。")
        self._finish_snapshot("场景在读取期间变化，未执行炼丹辅助。")
        return dict(status="safe_alchemy_nonbattle", identity=dict(main=main, space_manager=space,
                    space_handler=handler, space_class=fullname, wave_instance=wave_instance,
                    wave_state=wave_state), anchors=self.anchors)


def require_safe_alchemy_context(resolver):
    try:
        return AlchemyContext(resolver).snapshot()
    except AcquisitionContextRefused:
        raise
    except Exception as error:
        raise AcquisitionContextRefused("无法核对当前炼丹场景，请等待场景稳定后刷新。") from error
