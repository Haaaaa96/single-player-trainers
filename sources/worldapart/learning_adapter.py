"""Read-only, version-locked resolver for the live Gongfa learning minigame.

The canonical route is UIManager's lazy singleton -> PanelRegistry._instances
-> currently shown LearnGongfaPanel -> _runtime. A leftover heap object is
never selected. No object scan, injection, or game-function call is used.
"""
import math
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "game_runtime"))
import probe
from native_write import process_identity
from write_guard import Refused
from learning_write import FloatTarget
from game_install import validate_installation
from extension_runtime import ExtensionRuntime

# UIManager.CreateInstance (token 0x06008b65) loads this class-info slot.
# RVA 0x15f0e43: mov rcx,[rip+0x6b66a1e]; next instruction allocates UIManager.
UI_MANAGER_CLASS_RVA = 0x8157868
SPECS = {
    "Game.UIManager": (28993284, 0x02000B6C, 49),
    "Game.BaseUI": (29007716, 0x02000C1B, 34),
    "Game.PanelRegistry": (29009124, 0x02000C2C, 2),
    "Game.UI.UPFLogic.LearnGongfa.LearnGongfaPanel": (29223756, 0x020015B0, 63),
    "Game.UI.UPFLogic.LearnGongfa.LearnGongfaRuntime": (29224284, 0x020015B7, 48),
    "LubanDatas.data.MiniGameLearnGongfa": (28880292, 0x02000673, 15),
}
NS = "Game.UI.UPFLogic.LearnGongfa."


class LearningResolver:
    def __init__(self, reader, *, metadata_base=None, module_base=None):
        self.reader = reader
        self.stamp = process_identity(reader.h)
        installation = validate_installation(reader.path)
        self.game_path = installation.executable_path
        self.install_directory = installation.install_directory
        maps = probe.verified_mappings(reader)
        if metadata_base is None:
            metadata_base = maps["metadata"][0]["base"]
        if module_base is None:
            module_base = maps["game_assembly"][0]["base"]
        if (metadata_base != maps["metadata"][0]["base"]
                or module_base != maps["game_assembly"][0]["base"]):
            raise Refused("小游戏地址与当前游戏安装目录的映射不一致。")
        self.meta, self.module = metadata_base, module_base
        runtime = getattr(reader, '_extension_runtime', None)
        if runtime is None:
            runtime = ExtensionRuntime(reader, self.meta)
            reader._extension_runtime = runtime
        elif runtime.meta != self.meta or runtime.reader is not reader:
            raise Refused('扩展元数据不属于当前连接。')
        self._runtime = runtime
        self.anchors = []

    def runtime_spec(self, fullname, reviewed_spec=None):
        if not hasattr(self, '_runtime'):
            return reviewed_spec
        return self._runtime.spec(fullname, reviewed_spec)

    def class_address(self, fullname):
        return self._runtime.class_address(fullname)

    def owned_class_address(self, fullname):
        return self._runtime.owned_class_address(self, fullname)

    def exact(self, address, size):
        raw = self.reader.read(address, size)
        if len(raw) != size:
            raise Refused("小游戏数据读取不完整，请退出过场后刷新。")
        return raw

    def anchor(self, address, size):
        raw = self.exact(address, size)
        self.anchors.append((address, raw.hex()))
        return raw

    def q(self, address, *, anchored=False):
        return struct.unpack("<Q", (self.anchor if anchored else self.exact)(address, 8))[0]

    def i(self, address, *, anchored=False):
        return struct.unpack("<i", (self.anchor if anchored else self.exact)(address, 4))[0]

    def f(self, address):
        value = struct.unpack("<f", self.exact(address, 4))[0]
        if not math.isfinite(value):
            raise Refused("小游戏出现非有限数值，未提供修改目标。")
        return value

    def info(self, klass, fullname=None):
        c = probe.inspect_class(self.reader, klass)
        if not c or any(int(f["parent"], 16) != klass for f in c["fields"]):
            raise Refused("小游戏对象类型无法确认。")
        if fullname and c["namespace"] + "." + c["name"] != fullname:
            raise Refused("小游戏对象类型不匹配。")
        if fullname in SPECS:
            if hasattr(self, '_runtime'):
                spec = self.runtime_spec(fullname)
                offset, token, count = spec['type_definition_offset'], spec['token'], spec['field_count']
                if self.reader.string(self.q(self.q(klass))) != spec['image_name']:
                    raise Refused('界面对象所属程序集不匹配。')
            else:
                offset, token, count = SPECS[fullname]
            if (self.q(klass + 0x68) != self.meta + offset
                    or self.i(klass + 0x11C) != token or len(c["fields"]) != count):
                raise Refused("小游戏元数据标识不匹配。")
        return c

    def obj(self, address, fullname):
        if address <= 0 or address % 8:
            raise Refused("小游戏对象指针无效。")
        return self.info(self.q(address, anchored=True), fullname)

    def field(self, c, name, kind, token=None, *, static=False):
        if hasattr(self, '_runtime'):
            fullname = c['namespace'] + '.' + c['name']
            spec = self.runtime_spec(fullname, {'fields': [{'name': name}]})
            klass = int(c['klass'], 16)
            handle = self.q(klass + 0x68, anchored=True)
            if not handle:
                generic = self.q(klass + 0x60, anchored=True)
                if not generic:
                    raise Refused('字段所属泛型类型无法确认。')
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] not in (0x11, 0x12) or self.q(generic + 24, anchored=True) != klass:
                    raise Refused('字段所属泛型定义不匹配。')
                handle = struct.unpack_from('<Q', raw)[0]
            if (handle != self.meta + spec['type_definition_offset']
                    or self.i(klass + 0x11C, anchored=True) != spec['token']
                    or len(c['fields']) != spec['field_count']
                    or self.reader.string(self.q(self.q(klass))) != spec['image_name']):
                raise Refused('字段所属类型与当前元数据不一致。')
            token = next(f['token'] for f in spec['fields'] if f['name'] == name)
        fields = [f for f in c["fields"] if f["name"] == name]
        if len(fields) != 1:
            raise Refused("小游戏字段不存在或不唯一：" + name)
        f = fields[0]
        data = bytes.fromhex(f["type_data"])
        if len(data) != 16:
            raise Refused("小游戏字段类型数据不完整：" + name)
        attrs = int.from_bytes(data[8:10], "little")
        if (data[10] != kind or bool(attrs & 0x10) != static
                or attrs & 0x40 or token is not None and int(f["token"], 16) != token
                or f["offset"] < 0 or not static and not 16 <= f["offset"] < c["instance_size"]):
            raise Refused("小游戏字段布局不匹配：" + name)
        return f["offset"]

    def _registered_panels(self):
        klass = self.owned_class_address('Game.UIManager')
        mc = self.info(klass, "Game.UIManager")
        parent = self.q(klass + 0x58, anchored=True)
        sc = self.info(parent, "Game.Singleton`1")
        sf = self.q(parent + 0xB8, anchored=True)
        lazy = self.q(sf + self.field(sc, "lazyInstance", 0x15, 0x04000022, static=True), anchored=True)
        lc = self.obj(lazy, "System.Lazy`1")
        manager = self.q(lazy + self.field(lc, "_value", 0x12, 0x0400042D), anchored=True)
        self.obj(manager, "Game.UIManager")
        static = self.q(klass + 0xB8, anchored=True)
        if self.anchor(static + self.field(mc, "<IsWorldUiTeardown>k__BackingField", 2,
                                          0x04003C67, static=True), 1) != b"\0":
            raise Refused("游戏正在切换世界，暂不编辑小游戏。")
        if self.anchor(manager + self.field(mc, "m_IsShuttingDown", 2, 0x04003C68), 1) != b"\0":
            raise Refused("游戏界面正在关闭。")
        registry = self.q(manager + self.field(mc, "_panelRegistry", 0x12, 0x04003C6A), anchored=True)
        rc = self.obj(registry, "Game.PanelRegistry")
        dictionary = self.q(registry + self.field(rc, "_instances", 0x15, 0x0400403E), anchored=True)
        dc = self.obj(dictionary, "System.Collections.Generic.Dictionary`2")
        count = self.i(dictionary + self.field(dc, "_count", 8, 0x04001B01), anchored=True)
        self.anchor(dictionary + self.field(dc, "_version", 8, 0x04001B04), 4)
        if not 0 <= count <= 512:
            raise Refused("游戏面板列表长度异常。")
        if count == 0:
            return manager, []
        array = self.q(dictionary + self.field(dc, "_entries", 0x1D, 0x04001B00), anchored=True)
        ac = self.obj(array, ".Entry[]")
        ec = self.info(self.q(int(ac["klass"], 16) + 0x40), ".Entry")
        stride = ec["instance_size"] - 16
        offsets = [self.field(ec, n, k, t) - 16 for n,k,t in
                   (("hashCode",8,0x04001B0D),("key",0x11,0x04001B0F),("value",0x12,0x04001B10))]
        if stride != 24 or offsets != [0,8,16] or not count <= self.q(array + 24) <= 2048:
            raise Refused("面板注册表布局异常。")
        panels = []
        for index in range(count):
            entry = array + 32 + index * stride
            raw = self.anchor(entry, stride)
            if struct.unpack_from("<i", raw)[0] < 0:
                continue
            panel = struct.unpack_from("<Q", raw, 16)[0]
            if not panel:
                continue
            klass = self.q(panel)
            c = self.info(klass)
            if c["name"] == "LearnGongfaPanel" and c["namespace"] == NS[:-1]:
                panels.append(panel)
        return manager, panels

    def _panel_snapshot(self, manager, panel, *, include_finished=False, allow_hidden=False):
        pc = self.obj(panel, NS + "LearnGongfaPanel")
        bc = self.info(int(pc["parent"],16), "Game.BaseUI")
        # Observation may inspect a just-hidden, still-registered terminal panel.
        # It never follows a destroyed native object or creates targets for it.
        native = self.q(panel + 16, anchored=True)
        if not native:
            return None
        def flag(c, name, token):
            address = panel + self.field(c,name,2,token)
            raw = self.anchor(address,1)
            if raw not in (b"\0", b"\1"):
                raise Refused("学习界面状态标记无效。")
            return bool(raw[0]), address
        showing, _ = flag(bc,"isShowing",0x04003FEB)
        initialized, _ = flag(bc,"isInitialized",0x04003FEC)
        visual_hide, _ = flag(bc,"<IsInVisualHide>k__BackingField",0x04003FEF)
        paused, paused_address = flag(bc,"<IsPaused>k__BackingField",0x04003FF9)
        interactable, _ = flag(bc,"<IsInteractable>k__BackingField",0x04003FF8)
        visible = showing and not visual_hide
        if not initialized or not visible and not allow_hidden:
            return None
        flags = {key: flag(pc,name,token)[0] for key,name,token in (
            ("game_started_notified","_gameStartedNotified",0x04008646),
            ("result_shown","_resultShown",0x0400863B),
            ("result_success","_resultSuccess",0x0400863C),
            ("learn_effect_failed","_learnEffectFailed",0x0400863D),
            ("callback_invoked","_callbackInvoked",0x0400863E),
            ("should_complete_on_exit","_shouldCompleteLearningOnExit",0x0400863F),
            ("learn_effect_executed","_learnEffectExecuted",0x04008640),
            ("result_exit_handled","_resultExitHandled",0x04008641))}
        runtime = self.q(panel + self.field(pc,"_runtime",0x12,0x04008637), anchored=True)
        if not runtime:
            return None
        rt = self.obj(runtime, NS + "LearnGongfaRuntime")
        config = self.q(runtime + self.field(rt,"_config",0x12,0x040086CD), anchored=True)
        if config != self.q(panel + self.field(pc,"_config",0x12,0x04008638), anchored=True):
            raise Refused("面板和小游戏配置已切换，请刷新。")
        cc = self.obj(config,"LubanDatas.data.MiniGameLearnGongfa")
        maximum = self.i(config + self.field(cc,"<comprehend_value_limit>k__BackingField",8,
                                           0x0400165C), anchored=True)
        if not 1 <= maximum <= 1_000_000:
            raise Refused("功法学习阈值超出已支持范围。")
        phase = self.i(runtime + self.field(rt,"<Phase>k__BackingField",0x11,0x040086EA), anchored=True)
        end = self.i(runtime + self.field(rt,"<EndReason>k__BackingField",0x11,0x040086EB), anchored=True)
        if phase == 0 and end == 0 and not flags["game_started_notified"]:
            return None  # An allocated panel/runtime has not started its game yet.
        if phase not in (1,2,3,4) or end not in (0,1,2,3,4):
            raise Refused("学习小游戏阶段或结束原因异常。")
        running = (phase in (1,2,3) and end == 0 and visible
                   and flags["game_started_notified"] and not flags["result_shown"]
                   and not flags["result_exit_handled"])
        terminal = phase == 4 and end != 0
        if not running and not (include_finished and terminal):
            return None
        current_addr = runtime + self.field(rt,"<CurrentValue>k__BackingField",0x0C,0x040086EC)
        star_addr = runtime + self.field(rt,"_epiphanyValue",0x0C,0x040086E7)
        current, stars = self.f(current_addr), self.f(star_addr)
        if not 0 <= current <= maximum or not 0 <= stars <= 100:
            raise Refused("小游戏数值不在有效范围内。")
        uid = self.q(panel + self.field(pc,"_itemUid",0x0A,0x04008639), anchored=True)
        handle = self.i(panel + self.field(bc,"<HandleToken>k__BackingField",8,0x04003FFC), anchored=True)
        initial = self.i(panel + self.field(pc,"_roundInitialValue",8,0x04008642), anchored=True)
        target_identity = []
        for name,kind,token in (("_targetType",0x11,0x04008643),("_targetId",8,0x04008644),
                                ("_targetLevel",8,0x04008645)):
            target_identity.append(self.i(panel + self.field(pc,name,kind,token),anchored=True))
        duration_address = runtime + self.field(rt,"_gameDurationSeconds",0x0C,0x040086D7)
        elapsed_address = runtime + self.field(rt,"_elapsedSeconds",0x0C,0x040086E4)
        demon_address = runtime + self.field(rt,"<DemonValue>k__BackingField",0x0C,0x040086ED)
        duration = struct.unpack("<f",self.anchor(duration_address,4))[0]
        elapsed = self.f(elapsed_address)
        demon = struct.unpack("<f",self.anchor(demon_address,4))[0]
        if (not math.isfinite(duration) or duration <= 0 or elapsed < 0
                or not math.isfinite(demon) or not 0 <= demon <= 100):
            raise Refused("学习小游戏计时或心魔数值异常。")
        remaining = max(0.0,duration-elapsed)
        consumed = self.anchor(runtime + self.field(rt,"_hasConsumedTime",2,0x040086E8),1)
        bounds = self.anchor(runtime + self.field(rt,"_boundsInitialized",2,0x040086E9),1)
        if consumed not in (b"\0",b"\1") or bounds not in (b"\0",b"\1"):
            raise Refused("学习小游戏初始化状态异常。")
        round_key = (self.stamp,self.module,self.meta,manager,panel,native,handle,
                     runtime,config,uid,*target_identity,initial)
        identity = (self.stamp,self.module,self.meta,manager,panel,runtime,config,uid,handle,
                    tuple(self.anchors))
        targets = {
            "learning_value": FloatTarget("learning_value", current_addr, current, identity,
                                           0.0, float(maximum), tuple(self.anchors)),
            "learning_epiphany": FloatTarget("learning_epiphany", star_addr, stars, identity,
                                              0.0, 100.0, tuple(self.anchors)),
        } if running else {}
        reason = ""
        if not running: reason = "当前学习局已结束。"
        elif paused or not interactable: reason = "学习小游戏已暂停或正被其他界面遮挡，请回到小游戏后重试。"
        elif consumed != b"\0" or bounds != b"\1": reason = "学习小游戏尚未就绪或已经开始结算。"
        elif any(flags[k] for k in ("result_success","learn_effect_failed","callback_invoked",
                                  "should_complete_on_exit","learn_effect_executed")):
            reason = "学习小游戏已进入结算，暂不修改。"
        elif demon >= 100: reason = "心魔已满，请等待游戏处理当前结果。"
        elif remaining <= 0: reason = "本局时间已到，请等待游戏处理当前结果。"
        status = "active"
        if terminal:
            status = "round_success" if end == 2 else "failed"
            if flags["learn_effect_failed"]: status = "failed"
        return dict(active=running, reason=reason, can_complete=not reason,
                    round_key=round_key, identity=round_key, panel=panel, runtime=runtime,
                    phase=phase, end_reason=end, status=status, visible=visible, paused=paused,
                    interactable=interactable, demon_value=demon, has_consumed_time=bool(consumed[0]),
                    bounds_initialized=bool(bounds[0]),
                    current_value=current, epiphany_percent=stars, maximum=maximum,
                    remaining_seconds=remaining, targets=targets,
                    target=targets.get("learning_value") if not reason else None,
                    completion_target=targets.get("learning_value") if not reason else None,
                    completion_guards=dict(elapsed_address=elapsed_address,duration_address=duration_address,
                                           demon_address=demon_address,paused_address=paused_address),**flags)

    def snapshot(self, *, include_finished=False, expected_round=None):
        if process_identity(self.reader.h) != self.stamp:
            raise Refused("游戏进程已变化，请重新连接。")
        self.anchors = []
        manager, panels = self._registered_panels()
        if expected_round is not None:
            if type(expected_round) is not tuple or len(expected_round) != 14:
                raise Refused("学习局身份无效。")
            panels = [panel for panel in panels if panel == expected_round[4]]
        states = [state for panel in panels if (state := self._panel_snapshot(
            manager,panel,include_finished=include_finished,allow_hidden=expected_round is not None))]
        if len(states) > 1:
            raise Refused("检测到多个活动学习小游戏，未提供修改目标。")
        if any(self.exact(a,len(bytes.fromhex(h))) != bytes.fromhex(h) for a,h in self.anchors):
            raise Refused("小游戏界面正在变化，请重新刷新。")
        if process_identity(self.reader.h) != self.stamp:
            raise Refused("游戏进程已变化。")
        result = states[0] if states else dict(active=False, can_complete=False,
            reason="请先在游戏中进入功法学习小游戏；已结束的旧对象不可编辑。", targets={})
        if expected_round is not None and result.get("round_key") != expected_round:
            raise Refused("原学习局已关闭、销毁或更换，无法确认本局结算；不会重复修改。")
        return result

    def completion_snapshot(self):
        return self.snapshot(include_finished=True)

    def prepare_completion(self, shown=None):
        expected = shown.get("round_key") if type(shown) is dict else None
        if shown is not None and expected is None:
            raise Refused("请先刷新并确认当前学习小游戏。")
        state = self.completion_snapshot()
        if expected is not None and state.get("round_key") != expected:
            raise Refused("学习局已更换，请刷新；不会修改另一局。")
        if not state.get("can_complete") or state.get("target") is None:
            raise Refused(state["reason"] or "当前学习局不可自动完成。")
        return state

    def observe_completion(self, prepared):
        if type(prepared) is not dict or "round_key" not in prepared:
            raise Refused("缺少原学习局身份，无法核对结果。")
        return self.snapshot(include_finished=True,expected_round=prepared["round_key"])

    def discover(self):
        return self.snapshot()

    def resolve(self, key):
        state = self.snapshot()
        if key not in state["targets"]:
            raise Refused(state["reason"] or "学习修改项不存在。")
        return state["targets"][key]
