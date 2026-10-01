"""Read-only, fail-closed acquisition context check; never loads an agent.

Two independent game owners must agree: a settled MainSpaceHandler selected by
A1Main's registered SpaceManager, and no WaveCombatManager instance. Unknown
handler types remain unsupported even when their names look non-combat-related.
The returned anchors must be checked again on Unity's thread before a call.
"""
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "game_runtime"))
import probe
from runtime_metadata import RuntimeSpecs
from write_guard import Refused

SPECS = json.loads((HERE / "acquisition_context_specs.json").read_text(encoding="utf8"))
A1_MAIN_CLASS_RVA = 0x813A2A0
WAVE_CLASS_RVA = 0x819EBA8
# The locked PE contains the unresolved IL2CPP class usage (type index 71254).
# Awake, get_Instance and set_Instance all resolve THIS exact shared slot before
# creating/publishing a WaveCombatManager. Exact equality is required; arbitrary
# null/invalid class pointers are never interpreted as absence of combat.
WAVE_COLD_USAGE = 0x20022CAD
CODE_PROOFS = {
    0x1434700: "488b05995bd006488b80b8000000488b004883c428",
    0xFFF910: "488b0591f2190783b8e000000000750f488bc8e8982657ff488b0579f21907488b80b8000000488b40684883c428c3",
    0xFF57A2: "488d0dff931a07e892895eff",
    0x15C2480: "807960007403b001c348837950000f97c0c3",
}
# Reviewed code layouts, selected by the actual instructions (never build/hash).
# 25617557: get_Instance still reads static +0/+0x68, Awake resolves the
# same Wave class slot, and IsChangingSpace still tests +0x60 or +0x50.
# Full current method/metadata evidence: build/scene_current_evidence.{json,txt}.
CODE_PROFILES = (
    dict(main_slot=A1_MAIN_CLASS_RVA, wave_slot=WAVE_CLASS_RVA,
         wave_byval=71254, code=CODE_PROOFS),
    dict(main_slot=0x814CEA0, wave_slot=0x81B0D98, wave_byval=71243, code={
        0x1464A70: "488b052984ce06488b80b8000000488b004883c428",
        0x1043310: "488b0581da160783b8e000000000750f488bc8e818ed52ff488b0569da1607488b80b8000000488b40684883c428c3",
        0x10391A2: "488d0def7b1707e812505aff",
        0x15F5670: "807960007403b001c348837950000f97c0c3",
    }),
)


def _reviewed_specs(specs):
    return [{**spec, "name": name,
             "image_name": "mscorlib.dll" if name == "System.Collections.Generic.List`1" else "Game.dll"}
            for name, spec in specs.items()]


class AcquisitionContextRefused(Refused):
    """Context was rejected by local reads, before any acquisition game call."""


class _Context:
    extra_specs = {}

    def __init__(self, resolver):
        self.reader = resolver.reader
        self.meta = resolver.meta
        self.anchors = []
        modules = [r["base"] for r in self.reader.regions
                   if r["type"] == 0x1000000 and r["base"] == r["allocation"]
                   and self.reader.mapped(r["base"]).casefold().endswith("\\gameassembly.dll")]
        if len(modules) != 1:
            raise AcquisitionContextRefused("无法确认游戏场景模块，未执行添加。")
        self.module = modules[0]
        matches = [profile for profile in CODE_PROFILES
                   if all(self.reader.read(self.module + rva, len(bytes.fromhex(expected))).hex() == expected
                          for rva, expected in profile["code"].items())]
        if len(matches) != 1:
            raise AcquisitionContextRefused("场景检测必要入口代码无法确认，未执行添加。")
        self.profile = matches[0]
        self.runtime_specs = RuntimeSpecs(self.reader, self.meta, _reviewed_specs({**SPECS, **self.extra_specs}))
        self._begin_snapshot()

    def _begin_snapshot(self):
        self.anchors = []
        self._used_specs = set()
        for rva, expected in self.profile["code"].items():
            if self.anchor(self.module + rva, len(bytes.fromhex(expected)), "context.code").hex() != expected:
                raise AcquisitionContextRefused("场景检测代码在读取期间变化，未执行添加。")

    def _spec(self, fullname):
        spec = self.runtime_specs[fullname]
        self._used_specs.add(fullname)
        return spec

    def _finish_snapshot(self, message):
        for fullname in self._used_specs:
            self.runtime_specs[fullname]
        for anchor in self.anchors:
            if self.exact(anchor["address"], anchor["size"]).hex() != anchor["expected_hex"]:
                raise AcquisitionContextRefused(message)

    def exact(self, address, size):
        raw = self.reader.read(address, size)
        if len(raw) != size:
            raise AcquisitionContextRefused("场景数据读取不完整，请在普通场景稳定后重试。")
        return raw

    def anchor(self, address, size, label):
        raw = self.exact(address, size)
        self.anchors.append(dict(address=address, size=size, expected_hex=raw.hex(), label=label))
        return raw

    def q(self, address, label):
        return struct.unpack("<Q", self.anchor(address, 8, label))[0]

    def i(self, address, label):
        return struct.unpack("<i", self.anchor(address, 4, label))[0]

    def pointer(self, address, label):
        value = self.q(address, label)
        if not value or value % 8:
            raise AcquisitionContextRefused("场景对象尚未就绪，未执行添加。")
        return value

    def info(self, klass, fullname=None):
        c = probe.inspect_class(self.reader, klass)
        if not c or any(int(f["parent"], 16) != klass for f in c["fields"]):
            raise AcquisitionContextRefused("无法确认场景对象类型，未执行添加。")
        actual = c["namespace"] + "." + c["name"]
        if fullname is not None:
            spec = self._spec(fullname) if fullname in self.runtime_specs else None
            if not spec or actual != fullname:
                raise AcquisitionContextRefused("场景对象类型未受支持，未执行添加。")
            handle = self.q(klass + 0x68, actual + ".metadata")
            if fullname == "System.Collections.Generic.List`1" and handle == 0:
                # Inflated IL2CPP generic classes keep the definition on
                # generic_class.type instead of klass.typeMetadataHandle.
                generic = self.pointer(klass + 0x60, actual + ".generic")
                definition = self.pointer(generic, actual + ".generic.type")
                type_data = self.anchor(definition, 16, actual + ".generic.type_data")
                if type_data[10] != 0x12 or self.q(generic + 24, actual + ".generic.cached_class") != klass:
                    raise AcquisitionContextRefused("管理器泛型列表类型不匹配，未执行添加。")
                handle = struct.unpack_from("<Q", type_data)[0]
            token = self.i(klass + 0x11C, actual + ".token")
            fields = {f["name"]: int(f["token"], 16) for f in c["fields"]}
            expected_fields = {f["name"]: int(f["token"], 16) for f in spec["fields"]}
            if (handle != self.meta + spec["typeDefinitionFileOffset"] or token != int(spec["token"], 16)
                    or len(c["fields"]) != spec["fieldCount"]
                    or len(fields) != len(c["fields"])
                    or any(fields.get(name) != value for name, value in expected_fields.items())):
                raise AcquisitionContextRefused("场景对象与当前元数据身份不同，未执行添加。")
        return c

    def obj(self, address, fullname=None):
        if not address or address % 8:
            raise AcquisitionContextRefused("场景对象指针无效，未执行添加。")
        return self.info(self.pointer(address, "context.object.klass"), fullname)

    def field(self, c, name, kind, *, static=False):
        fields = [f for f in c["fields"] if f["name"] == name]
        if len(fields) != 1:
            raise AcquisitionContextRefused("场景检测字段缺失：" + name)
        f = fields[0]
        data = bytes.fromhex(f["type_data"])
        if len(data) != 16:
            raise AcquisitionContextRefused("场景检测字段类型无效：" + name)
        attrs = int.from_bytes(data[8:10], "little")
        width = 1 if kind == 2 else 4 if kind == 8 else 8
        if (data[10] != kind or bool(attrs & 0x10) != static or attrs & 0x40
                or f["offset"] < 0 or not static and not 16 <= f["offset"] <= c["instance_size"] - width):
            raise AcquisitionContextRefused("场景检测字段布局不匹配：" + name)
        code_offsets = {("Game.A1Main", "_instance"): 0,
                        ("Game.SpaceManager", "_isTransitioning"): 0x60,
                        ("Game.SpaceManager", "_pendingChangeSpaceRequest"): 0x50}
        expected = code_offsets.get((c["namespace"] + "." + c["name"], name))
        if expected is not None and f["offset"] != expected:
            raise AcquisitionContextRefused("场景字段与已核对入口语义不同：" + name)
        return f["offset"]

    def boolean(self, obj, c, name, expected):
        raw = self.anchor(obj + self.field(c, name, 2), 1, "context." + name)
        if raw not in (b"\0", b"\1") or raw != bytes([expected]):
            raise AcquisitionContextRefused("游戏正在初始化、切换或退出场景，暂不能添加物品。")

    def zero_pointer(self, obj, c, name):
        if self.q(obj + self.field(c, name, 0x12), "context." + name):
            raise AcquisitionContextRefused("游戏正在准备或切换场景，暂不能添加物品。")

    def managers(self):
        k = self.pointer(self.module + self.profile["main_slot"], "context.A1Main.class")
        c = self.info(k, "Game.A1Main")
        sf = self.pointer(k + 0xB8, "context.A1Main.static")
        main = self.pointer(sf + self.field(c, "_instance", 0x12, static=True), "context.A1Main.instance")
        self.obj(main, "Game.A1Main")
        self.pointer(main + 16, "context.A1Main.native")
        self.boolean(main, c, "<IsInitialized>k__BackingField", True)
        for name in ("_isDestroying", "m_IsStarting", "m_QuitRequested", "m_QuitAllowed", "m_ManagersDestroyed"):
            self.boolean(main, c, name, False)
        listing = self.pointer(main + self.field(c, "_managers", 0x15), "context.managers")
        lc = self.obj(listing, "System.Collections.Generic.List`1")
        count = self.i(listing + self.field(lc, "_size", 8), "context.managers.size")
        self.i(listing + self.field(lc, "_version", 8), "context.managers.version")
        if not 1 <= count <= 128:
            raise AcquisitionContextRefused("管理器列表长度异常，未执行添加。")
        array = self.pointer(listing + self.field(lc, "_items", 0x1D), "context.managers.items")
        capacity = self.q(array + 24, "context.managers.capacity")
        if not count <= capacity <= 256:
            raise AcquisitionContextRefused("管理器列表容量异常，未执行添加。")
        raw = self.anchor(array + 32, count * 8, "context.managers.entries")
        found = {}
        for address in struct.unpack("<" + "Q" * count, raw):
            c = self.obj(address)
            full = c["namespace"] + "." + c["name"]
            if full in ("Game.SpaceManager", "Game.GameLifecycleManager"):
                if full in found:
                    raise AcquisitionContextRefused("场景管理器不唯一，未执行添加。")
                found[full] = (address, self.info(int(c["klass"], 16), full))
        if set(found) != {"Game.SpaceManager", "Game.GameLifecycleManager"}:
            raise AcquisitionContextRefused("场景管理器未就绪，未执行添加。")
        return main, found

    def no_combat(self, label, refusal):
        """Verify the exact reviewed unresolved usage, or canonical null static."""
        wave_class = self.q(self.module + self.profile["wave_slot"], label + ".class")
        # The unresolved value encodes the current metadata byval type, not a
        # class address. Tie it to both the reviewed instructions and metadata.
        wave_spec = self._spec("Game.Logic.Combat.WaveCombatManager")
        if wave_spec["byval"] != self.profile["wave_byval"]:
            raise AcquisitionContextRefused("战斗类入口与当前元数据类型不同，未执行操作。")
        cold_usage = 0x20000001 | (wave_spec["byval"] << 1)
        if wave_class == cold_usage:
            return "never_initialized", 0
        if not wave_class or wave_class % 8:
            raise AcquisitionContextRefused("无法确认战斗系统状态，未执行操作。")
        wc = self.info(wave_class, "Game.Logic.Combat.WaveCombatManager")
        sf = self.pointer(wave_class + 0xB8, label + ".static")
        offset = self.field(wc, "<Instance>k__BackingField", 0x12, static=True)
        if offset != 0x68:
            raise AcquisitionContextRefused("战斗实例字段与已核对入口语义不同，未执行操作。")
        instance = self.q(sf + offset, label + ".instance")
        if instance:
            raise AcquisitionContextRefused(refusal)
        return "no_instance", 0

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
        handler = self.pointer(space + self.field(sc, "_currentSpaceHandler", 0x12), "context.space.handler")
        hc = self.obj(handler)
        fullname = hc["namespace"] + "." + hc["name"]
        if fullname == "Game.SpaceHandlers.BattleSpaceHandler":
            raise AcquisitionContextRefused("战斗中不能添加物品。请结束战斗并返回普通场景后重试。")
        if fullname != "Game.SpaceHandlers.MainSpaceHandler":
            raise AcquisitionContextRefused("当前场景尚未验证可安全添加物品，请返回城镇或普通场景后重试。")
        self.info(int(hc["klass"], 16), fullname)
        parent = self.pointer(int(hc["klass"], 16) + 0x58, "context.handler.parent")
        self.info(parent, "Game.SpaceHandlers.BaseSpaceHandler")
        wave_state, wave_instance = self.no_combat("context.wave", "战斗或战斗结算尚未结束，请返回普通场景后再添加物品。")
        # Resolve chains are multi-read snapshots. Refuse a transition that
        # happened during those reads, then return the same preconditions for
        # the caller's second check and the main-thread bridge's final check.
        self._finish_snapshot("场景在检测期间发生变化，未执行添加。")
        return dict(status="safe_nonbattle", identity=dict(main=main, space_manager=space,
                    space_handler=handler, space_class=fullname, wave_instance=wave_instance,
                    wave_state=wave_state), anchors=self.anchors)


def require_safe_acquisition_context(resolver):
    """Return a verified stable nonbattle snapshot, or a local-only refusal."""
    try:
        return _Context(resolver).snapshot()
    except AcquisitionContextRefused:
        raise
    except Exception as exc:
        raise AcquisitionContextRefused("无法可靠确认游戏场景，未执行添加；请返回普通场景后刷新。") from exc
