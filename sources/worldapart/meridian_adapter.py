"""Version-locked read-only resolver for a registered, live MedGamePanel.

No heap scan, injection, game method invocation or save access. Only a paused
exit-confirmation round with its native timer cancelled yields write targets.
"""
import json
import hashlib
import struct

from learning_adapter import LearningResolver
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused
from meridian_write import MeridianTarget
from native_method_profiles import resolve_reviewed_method

METHOD_SPEC = dict(name='RevealSolutionPathForEditor', token=0x06010174,
                   rva=0x1DAC830, argc=0, returns=2,
                   prefix='40535556574883ec38803dbe467a0600')

SPECS = json.loads((RESOURCE_ROOT / "meridian_specs.json").read_text(encoding="utf8"))
NS = "Game.UI.UPFLogic.MedGame."
VARIANT_COUNTS = (3, 6, 6, 2, 6, 1)
MAX_CELLS = 1024


class MeridianResolver(LearningResolver):
    """Reuse the already verified UI singleton primitives, not learning state."""

    def info(self, klass, fullname=None):
        c = super().info(klass)
        actual = c["namespace"] + "." + c["name"]
        if fullname is not None and actual != fullname:
            raise Refused("疏经导脉对象类型不匹配。")
        spec = SPECS.get(actual)
        if spec:
            spec = self.runtime_spec(actual, spec)
            handle = self.q(klass + 0x68, anchored=True)
            if handle == 0 and actual in (
                    "Loxodon.Framework.Observables.ObservableList`1",
                    "System.Collections.Generic.List`1"):
                generic = self.q(klass + 0x60, anchored=True)
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] != 0x12 or self.q(generic + 24, anchored=True) != klass:
                    raise Refused("疏经导脉列表泛型定义不匹配。")
                handle = struct.unpack_from("<Q", raw)[0]
            fields = {f["name"]: int(f["token"], 16) for f in c["fields"]}
            if (handle != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or len(c["fields"]) != spec["field_count"]
                    or fields != {f["name"]: f["token"] for f in spec["fields"]}):
                raise Refused("疏经导脉对象与当前元数据不匹配。")
        return c

    def _field(self, c, name, kind):
        fullname = c["namespace"] + "." + c["name"]
        spec = self.runtime_spec(fullname, SPECS[fullname])
        expected = next((f["token"] for f in spec["fields"]
                         if f["name"] == name), None)
        if expected is None:
            raise Refused("未审核的疏经导脉字段。")
        return self.field(c, name, kind, expected)

    def boolean(self, obj, c, name):
        raw = self.anchor(obj + self._field(c, name, 2), 1)
        if raw not in (b"\0", b"\1"):
            raise Refused("疏经导脉布尔状态不合法。")
        return raw == b"\1"

    def integer(self, obj, c, name, kind=8, *, anchored=True):
        return self.i(obj + self._field(c, name, kind), anchored=anchored)

    def _registered_panels(self):
        links = []
        def link(address):
            value = self.q(address, anchored=True)
            links.append(dict(address=hex(address), expected=hex(value)))
            return value
        self._native_registry = {}
        klass = self.class_address("Game.UIManager")
        mc = self.info(klass, "Game.UIManager")
        parent = link(klass + 0x58)
        sc = self.info(parent, "Game.Singleton`1")
        sf = link(parent + 0xB8)
        lazy = link(sf + self.field(sc, "lazyInstance", 0x15, 0x04000022, static=True))
        lc = self.obj(lazy, "System.Lazy`1")
        manager = link(lazy + self.field(lc, "_value", 0x12, 0x0400042D))
        self.obj(manager, "Game.UIManager")
        static = link(klass + 0xB8)
        if self.anchor(static + self.field(mc, "<IsWorldUiTeardown>k__BackingField", 2,
                                          0x04003C67, static=True), 1) != b"\0":
            raise Refused("游戏正在切换世界，暂不能读取疏经导脉。")
        if self.boolean(manager, mc, "m_IsShuttingDown"):
            raise Refused("游戏界面正在关闭。")
        registry = link(manager + self._field(mc, "_panelRegistry", 0x12))
        rc = self.obj(registry, "Game.PanelRegistry")
        dictionary = link(registry + self._field(rc, "_instances", 0x15))
        dc = self.obj(dictionary, "System.Collections.Generic.Dictionary`2")
        count = self.i(dictionary + self.field(dc, "_count", 8, 0x04001B01), anchored=True)
        self.anchor(dictionary + self.field(dc, "_version", 8, 0x04001B04), 4)
        if not 0 <= count <= 512:
            raise Refused("游戏面板注册表长度异常。")
        if count == 0:
            return manager, []
        array = link(dictionary + self.field(dc, "_entries", 0x1D, 0x04001B00))
        self._native_registry = dict(registry_links=links,
                                    registry=dict(dictionary=hex(dictionary), entries=hex(array), count=count,
                                      count_address=hex(dictionary + self.field(dc, "_count", 8, 0x04001B01)),
                                      version_address=hex(dictionary + self.field(dc, "_version", 8, 0x04001B04))))
        ac = self.obj(array, ".Entry[]")
        ec = self.info(self.q(int(ac["klass"], 16) + 0x40), ".Entry")
        stride = ec["instance_size"] - 16
        offsets = [self.field(ec, n, k, t) - 16 for n, k, t in
                   (("hashCode", 8, 0x04001B0D), ("key", 0x11, 0x04001B0F),
                    ("value", 0x12, 0x04001B10))]
        if stride != 24 or offsets != [0, 8, 16] or not count <= self.q(array + 24) <= 2048:
            raise Refused("游戏面板注册表布局异常。")
        panels = []
        for index in range(count):
            raw = self.anchor(array + 32 + index * stride, stride)
            if struct.unpack_from("<i", raw)[0] < 0:
                continue
            panel = struct.unpack_from("<Q", raw, 16)[0]
            if panel:
                c = self.info(self.q(panel))
                if c["namespace"] + "." + c["name"] == NS + "MedGamePanel":
                    panels.append(panel)
        return manager, panels

    def _cells(self, runtime, rc, config):
        collection = self.q(runtime + self._field(rc, "<Cells>k__BackingField", 0x15), anchored=True)
        oc = self.obj(collection, "Loxodon.Framework.Observables.ObservableList`1")
        items = self.q(collection + self._field(oc, "items", 0x15), anchored=True)
        lc = self.obj(items, "System.Collections.Generic.List`1")
        count = self.integer(items, lc, "_size")
        self.integer(items, lc, "_version")
        if count != config["cols"] * config["rows"] or not 1 <= count <= MAX_CELLS:
            raise Refused("疏经导脉棋盘格数与关卡尺寸不一致。")
        array = self.q(items + self._field(lc, "_items", 0x1D), anchored=True)
        ac = self.obj(array, None)
        if not ac["name"].endswith("[]"):
            raise Refused("疏经导脉棋盘数组类型不匹配。")
        self.info(self.q(int(ac["klass"], 16) + 0x40), NS + "MedCellViewModel")
        if not count <= self.q(array + 24, anchored=True) <= max(4, 2 * MAX_CELLS):
            raise Refused("疏经导脉棋盘数组容量异常。")
        pointers = b"".join(self.anchor(array + 32 + offset, min(64, count * 8 - offset))
                            for offset in range(0, count * 8, 64))
        cells, coords = [], set()
        fields = [("col", "_col", 8), ("row", "_row", 8), ("role", "<Role>k__BackingField", 0x11),
                  ("kind", "_kind", 0x11), ("shape", "_shape", 0x11), ("variant", "_variant", 8),
                  ("hidden", "_hidden", 2), ("is_generated_path", "_isGeneratedPath", 2),
                  ("solution_shape", "_solutionShape", 0x11), ("solution_variant", "_solutionVariant", 8),
                  ("rotate_count", "_rotateCount", 8)]
        for index in range(count):
            address = struct.unpack_from("<Q", pointers, index * 8)[0]
            cc = self.obj(address, NS + "MedCellViewModel")
            owner_offset = self._field(cc, "_owner", 0x12)
            offsets = {key: (self._field(cc, name, kind), kind) for key, name, kind in fields}
            first = min(owner_offset, *(offset for offset, kind in offsets.values()))
            end = max(owner_offset + 8, *(offset + (1 if kind == 2 else 4) for offset, kind in offsets.values()))
            if end - first > 256:
                raise Refused("疏经导脉格子布局超出审核范围。")
            raw = b"".join(self.anchor(address + pos, min(64, end - pos))
                           for pos in range(first, end, 64))
            if struct.unpack_from("<Q", raw, owner_offset - first)[0] != runtime:
                raise Refused("疏经导脉格子所属局次不同。")
            cell = {"address": hex(address)}
            for key, (offset, kind) in offsets.items():
                if kind == 2:
                    value = raw[offset - first]
                    if value not in (0, 1):
                        raise Refused("疏经导脉格子标记异常。")
                    cell[key] = bool(value)
                else:
                    cell[key] = struct.unpack_from("<i", raw, offset - first)[0]
            coord = (cell["col"], cell["row"])
            if (coord in coords or not 0 <= coord[0] < config["cols"] or not 0 <= coord[1] < config["rows"]
                    or cell["role"] not in range(3) or cell["kind"] not in range(4)
                    or cell["shape"] not in range(6) or cell["solution_shape"] not in range(6)
                    or not 0 <= cell["variant"] < VARIANT_COUNTS[cell["shape"]]
                    or not 0 <= cell["solution_variant"] < VARIANT_COUNTS[cell["solution_shape"]]
                    or not 0 <= cell["rotate_count"] <= 1_000_000):
                raise Refused("疏经导脉格子坐标、管道或旋转数据异常。")
            coords.add(coord)
            cells.append(cell)
        for role, expected in ((1, (config["start_col"], config["start_row"])),
                               (2, (config["end_col"], config["end_row"]))):
            if [(c["col"], c["row"]) for c in cells if c["role"] == role] != [expected]:
                raise Refused("疏经导脉起止穴位与关卡配置不一致。")
        return cells

    def _panel_snapshot(self, manager, panel):
        pc = self.obj(panel, NS + "MedGamePanel")
        bc = self.info(int(pc["parent"], 16), "Game.BaseUI")
        if not self.q(panel + 16, anchored=True):
            return None
        if (not self.boolean(panel, bc, "isShowing") or not self.boolean(panel, bc, "isInitialized")
                or self.boolean(panel, bc, "<IsInVisualHide>k__BackingField")):
            return None
        if (not self.boolean(panel, pc, "_boardLoaded") or self.boolean(panel, pc, "_boardLoading")
                or self.boolean(panel, pc, "_settlementStarted")
                or self.boolean(panel, pc, "_settlementCompletionDelegated")):
            return None
        exit_confirm = self.boolean(panel, pc, "_exitConfirmOpen")
        runtime = self.q(panel + self._field(pc, "_game", 0x12), anchored=True)
        if not runtime:
            return None
        rc = self.obj(runtime, NS + "MedGameViewModel")
        if (self.boolean(runtime, rc, "_finished") or self.boolean(runtime, rc, "_hasWon")
                or self.integer(runtime, rc, "<FailureReason>k__BackingField", 0x11) != 0):
            return None
        paused = self.boolean(runtime, rc, "_paused")
        pending = self.boolean(runtime, rc, "_pendingTransform")
        revealing = self.boolean(runtime, rc, "_revealAnimating")
        completion = self.q(runtime + self._field(rc, "_completed", 0x15), anchored=True)
        animations = [self.q(runtime + self._field(rc, name, 0x12), anchored=True) for name in (
            "_revealAnimationCts", "_bonusFlashCts", "_boardShakeCts", "_winPathAnimationCts")]
        timer = self.q(runtime + self._field(rc, "_timerCts", 0x12), anchored=True)
        self.boolean(runtime, rc, "_timerEnabled")
        if not self.boolean(runtime, rc, "_boardLayoutReady"):
            return None
        config_ptr = self.q(runtime + self._field(rc, "_config", 0x12), anchored=True)
        cc = self.obj(config_ptr, NS + "MedGameConfig")
        config = {key: self.integer(config_ptr, cc, name) for key, name in (
            ("cols", "Cols"), ("rows", "Rows"), ("start_col", "StartCol"), ("start_row", "StartRow"),
            ("end_col", "EndCol"), ("end_row", "EndRow"), ("time_limit", "TimeLimit"),
            ("rotation_limit", "RotationLimit"))}
        if (not 1 <= config["cols"] <= 64 or not 1 <= config["rows"] <= 64
                or config["cols"] * config["rows"] > MAX_CELLS
                or any(not -1 <= config[k] <= 1_000_000 or config[k] == 0
                       for k in ("time_limit", "rotation_limit"))):
            raise Refused("疏经导脉关卡配置超出支持范围。")
        bonus = self.integer(runtime, rc, "_bonusNeedleGained")
        passive = self.integer(runtime, rc, "_passiveNeedleBonus")
        if not 0 <= bonus <= 1_000_000 or not 0 <= passive <= 1_000_000:
            raise Refused("疏经导脉针数奖励异常。")
        total = max(0, config["rotation_limit"] + bonus + passive)
        addresses = {"meridian_time": runtime + self._field(rc, "_timeRemaining", 0x0C),
                     "meridian_needles_used": runtime + self._field(rc, "_needleUsed", 8),
                     "meridian_transform": runtime + self._field(rc, "_transformLeft", 8),
                     "meridian_reveal": runtime + self._field(rc, "_revealLeft", 8)}
        values = {key: (self.f(address) if key == "meridian_time" else self.i(address))
                  for key, address in addresses.items()}
        if any(not 0 <= value <= 1_000_000 for value in values.values()):
            raise Refused("疏经导脉局内资源不在支持范围。")
        cells = self._cells(runtime, rc, config)
        seed = self.integer(runtime, rc, "_seed")
        handle = self.integer(panel, bc, "<HandleToken>k__BackingField")
        identity = (self.stamp, self.module, self.meta, manager, panel, runtime, config_ptr, seed, handle,
                    tuple(cell["address"] for cell in cells))
        can_edit = paused and exit_confirm and not timer and not pending and not revealing
        can_solve = (bool(completion) and not paused and not exit_confirm and not pending
                     and not revealing and not any(animations))
        reason = ("已暂停，可设置本局资源；完成后在游戏里取消退出。" if can_edit else
                  "正在运行或播放效果；需在游戏中点关闭/退出，停在确认窗口（不要确认退出），再刷新。")
        # Anchors are deduplicated in snapshot() before target creation.
        return dict(active=True, reason=reason, message=reason, paused=paused, can_edit=can_edit,
                    can_solve=can_solve,
                    solve_reason=("取消游戏退出确认、等待动画结束后刷新，再一键疏通。" if not can_solve else
                                  "一键只完成当前局，不消耗用针及变换、揭示次数。"),
                    native=dict(panel=hex(panel), vm=hex(runtime), config=hex(config_ptr),
                                manager=hex(manager), seed=seed, handle=handle,
                                **{k: config[k] for k in ("cols", "rows", "start_col", "start_row", "end_col", "end_row")},
                                cells=cells),
                    identity=identity, config=config, cells=cells, values=values, targets={},
                    needle_total=total if config["rotation_limit"] != -1 else None,
                    needle_remaining=(max(0, total - values["meridian_needles_used"])
                                      if config["rotation_limit"] != -1 else None),
                    addresses=addresses)

    def snapshot(self):
        if process_identity(self.reader.h) != self.stamp:
            raise Refused("游戏进程已变化，请重新连接。")
        self.anchors = []
        manager, panels = self._registered_panels()
        states = [s for panel in panels if (s := self._panel_snapshot(manager, panel))]
        if len(states) > 1:
            raise Refused("检测到多个活动疏经导脉面板，未提供修改目标。")
        unique = {}
        for address, raw in self.anchors:
            if address in unique and unique[address] != raw:
                raise Refused("疏经导脉数据在读取时发生变化，请刷新。")
            unique[address] = raw
        anchors = tuple(unique.items())
        if (any(self.exact(address, len(bytes.fromhex(raw))) != bytes.fromhex(raw)
                for address, raw in anchors) or process_identity(self.reader.h) != self.stamp):
            raise Refused("疏经导脉局次或棋盘正在变化，请刷新。")
        if not states:
            return dict(active=False, reason="请先进入疏经导脉小游戏；未开始或已经结束的局不可编辑。",
                        message="请先进入疏经导脉小游戏。", paused=False, can_edit=False,
                        config={}, cells=[], values={}, targets={})
        state = states[0]
        addresses = state.pop("addresses")
        state["native"]["round_key"] = hashlib.sha256(
            json.dumps(state["identity"], separators=(",", ":")).encode("utf8")).hexdigest()
        state["native"].update(getattr(self, "_native_registry", {}))
        state["native"]["anchors"] = [dict(address=hex(address), size=len(raw) // 2,
                                          expected_hex=raw, label="meridian board/registry")
                                        for address, raw in anchors]
        if state["can_edit"]:
            values, config = state["values"], state["config"]
            bounds = {"meridian_transform": (0, 999, "i32"), "meridian_reveal": (0, 999, "i32")}
            if config["rotation_limit"] != -1 and state["needle_total"] <= 1_000_000:
                bounds["meridian_needles_used"] = (0, state["needle_total"], "i32")
            if config["time_limit"] > 0:
                bounds["meridian_time"] = (0.01, min(float(config["time_limit"]), 3600.0), "f32")
            for key, (minimum, maximum, kind) in bounds.items():
                lower = struct.unpack("<f", struct.pack("<f", minimum))[0] if kind == "f32" else minimum
                upper = struct.unpack("<f", struct.pack("<f", maximum))[0] if kind == "f32" else maximum
                if lower <= values[key] <= upper:
                    state["targets"][key] = MeridianTarget(
                        key=key, address=addresses[key], value=values[key], identity=state["identity"],
                        minimum=minimum, maximum=maximum, anchors=anchors, kind=kind)
        return state

    def prepare_solve(self, shown=None):
        """Fresh read-only one-click descriptor; no native call or write."""
        from meridian_logic import build_restore_plan
        state = self.snapshot()
        if not state.get("active") or not state.get("can_solve"):
            raise Refused(state.get("solve_reason") or state.get("reason") or "当前局不可疏通。")
        if shown is not None and state["identity"] != shown.get("identity"):
            raise Refused("疏经导脉局次已变化，未调用；请重新检测。")
        plan = build_restore_plan(state)
        if not plan["can_restore"]:
            raise Refused(plan["reason"])
        vm = int(state["native"]["vm"], 16)
        klass = self.q(vm)
        self.info(klass, NS + "MedGameViewModel")
        proof_start = len(self.anchors)
        method, selected = resolve_reviewed_method(self, klass, METHOD_SPEC)
        if (any(self.exact(int(a["address"], 16), a["size"]).hex() != a["expected_hex"]
                for a in state["native"]["anchors"])
                or process_identity(self.reader.h) != self.stamp):
            raise Refused("校验原生入口期间棋盘变化，未调用；请刷新。")
        state["native"]["method_info"] = hex(method)
        state["native"]["method_spec"] = selected
        state["native"]["anchors"].extend(dict(address=hex(a), size=len(h)//2, expected_hex=h)
                                           for a, h in self.anchors[proof_start:])
        state["restore_plan"] = plan
        return state

    def discover(self):
        return self.snapshot()

    def resolve(self, key):
        state = self.snapshot()
        if key not in state["targets"]:
            raise Refused(state["reason"] or "该疏经导脉资源当前不可编辑。")
        return state["targets"][key]
