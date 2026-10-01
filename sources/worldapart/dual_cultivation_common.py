"""Shared readonly canonical panel/method proof for the two minigames."""
import struct
import math
from learning_adapter import LearningResolver
from character_attributes import _deduplicate
from write_guard import Refused
from native_method_profiles import resolve_reviewed_method


def selected_method_spec(resolver, legacy_spec):
    """Attach the entry proved by method(); legacy also supports old fixtures.

    Request builders independently match this against their local whitelist.
    """
    selected = getattr(resolver, '_selected_methods', {})
    return dict(selected.get(legacy_spec['token'], legacy_spec))

class RegisteredMiniResolver(LearningResolver):
    """Reuse the already verified UI singleton primitives, not learning state."""

    def __init__(self, reader, specs, panel_type, **kwargs):
        super().__init__(reader, **kwargs)
        self.specs, self.panel_type = specs, panel_type

    def info(self, klass, fullname=None):
        c = super().info(klass)
        actual = c["namespace"] + "." + c["name"]
        if fullname is not None and actual != fullname:
            raise Refused("小游戏对象类型不匹配。")
        spec = self.specs.get(actual)
        if spec:
            spec = self.runtime_spec(actual, spec)
            handle = self.q(klass + 0x68, anchored=True)
            if handle == 0:
                generic = self.q(klass + 0x60, anchored=True)
                if not generic:
                    raise Refused("小游戏泛型定义不存在。")
                definition = self.q(generic, anchored=True)
                raw = self.anchor(definition, 16)
                if raw[10] not in (0x11, 0x12) or self.q(generic + 24, anchored=True) != klass:
                    raise Refused("小游戏列表泛型定义不匹配。")
                handle = struct.unpack_from("<Q", raw)[0]
            fields = {f["name"]: int(f["token"], 16) for f in c["fields"]}
            if (handle != self.meta + spec["type_definition_offset"]
                    or self.i(klass + 0x11C, anchored=True) != spec["token"]
                    or len(c["fields"]) != spec["field_count"]
                    or any(fields.get(f["name"]) != f["token"] for f in spec["fields"])):
                raise Refused("小游戏对象与当前元数据不匹配。")
        return c

    def _field(self, c, name, kind):
        fullname = c["namespace"] + "." + c["name"]
        spec = self.runtime_spec(fullname, self.specs[fullname])
        expected = next((f["token"] for f in spec["fields"]
                         if f["name"] == name), None)
        if expected is None:
            raise Refused("未审核的小游戏字段。")
        return self.field(c, name, kind, expected)

    def boolean(self, obj, c, name):
        raw = self.anchor(obj + self._field(c, name, 2), 1)
        if raw not in (b"\0", b"\1"):
            raise Refused("小游戏布尔状态不合法。")
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
            raise Refused("游戏正在切换世界，暂不能读取小游戏。")
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
                if c["namespace"] + "." + c["name"] == self.panel_type:
                    panels.append(panel)
        return manager, panels

    def registered_panels(self):
        """Return (manager, candidate pointers), and populate _native_registry."""
        return self._registered_panels()

    def visible_panel(self, panel):
        """Return reviewed class and actionable status; hidden panels return None."""
        pc = self.obj(panel, self.panel_type)
        bc = self.info(int(pc["parent"], 16), "Game.BaseUI")
        if not self.q(panel + 16, anchored=True):
            return None
        if (not self.boolean(panel, bc, "isShowing") or not self.boolean(panel, bc, "isInitialized")
                or self.boolean(panel, bc, "<IsInVisualHide>k__BackingField")):
            return None
        paused = self.boolean(panel, bc, "<IsPaused>k__BackingField")
        interactable = self.boolean(panel, bc, "<IsInteractable>k__BackingField")
        return pc, not paused and interactable

    def pointer_field(self, obj, c, name, kind=0x12, *, offset=None):
        actual = self._field(c, name, kind)
        if offset is not None and actual != offset:
            raise Refused("小游戏引用偏移与已审核代码不同。")
        return self.q(obj + actual, anchored=True)

    def float_field(self, obj, c, name, *, anchored=False):
        address = obj + self._field(c, name, 12)
        raw = self.anchor(address, 4) if anchored else self.exact(address, 4)
        value = struct.unpack("<f", raw)[0]
        if not math.isfinite(value):
            raise Refused("小游戏数值不是有限数。")
        return value

    def object_list(self, address, element_type, *, observable=False, maximum=64):
        """Return immutable pointers and anchor the entire reviewed reference list."""
        if observable:
            oc = self.obj(address, "Loxodon.Framework.Observables.ObservableList`1")
            address = self.pointer_field(address, oc, "items", 0x15)
        lc = self.obj(address, "System.Collections.Generic.List`1")
        count = self.integer(address, lc, "_size")
        self.integer(address, lc, "_version")
        array = self.pointer_field(address, lc, "_items", 0x1D)
        if not 0 <= count <= maximum or not array:
            raise Refused("小游戏列表数量无效。")
        ac = self.obj(array, None)
        if not ac["name"].endswith("[]"):
            raise Refused("小游戏列表数组类型无效。")
        self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), element_type)
        capacity = self.q(array + 24, anchored=True)
        if not count <= capacity <= max(4, maximum * 2):
            raise Refused("小游戏列表容量异常。")
        result = []
        for i in range(count):
            obj = self.q(array + 32 + i * 8, anchored=True)
            self.obj(obj, element_type)
            if obj in result:
                raise Refused("小游戏列表含重复对象。")
            result.append(obj)
        return tuple(result)

    def method(self, klass, spec):
        """Spec: name/token/rva/argc/returns/prefix/static(default False)."""
        method, chosen = resolve_reviewed_method(self, klass, spec)
        if not hasattr(self, '_selected_methods'):
            self._selected_methods = {}
        self._selected_methods[spec['token']] = chosen
        return hex(method)

    def proof(self):
        anchors = _deduplicate(self.anchors)
        if any(self.exact(a, len(h)//2).hex() != h for a, h in anchors):
            raise Refused("读取期间小游戏状态已变化，请刷新。")
        return [dict(address=hex(a), size=len(h)//2, expected_hex=h, label="minigame_context") for a, h in anchors]
