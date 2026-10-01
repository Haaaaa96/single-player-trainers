"""Saved pill talent ranks; the game has no spendable pill-talent points."""
import hashlib
import struct
import threading

from acquisition_context import AcquisitionContextRefused
from alchemy_context import require_safe_alchemy_context
from alchemy_adapter import AlchemyAdapter, AlchemyResolver, DATA, NS
from dual_cultivation_common import selected_method_spec
from dual_cultivation_native import MiniGameOnce
from native_write import process_identity
from write_guard import Refused, UncertainWrite

METHOD = DATA["methods"]["SetTalentRank"]
TALENTS = {int(x["id"]): x for x in DATA["talents"]}
MODEL = "Game.Model.Player.Components.RefiningPillsModel"


def rank_limit(talent_id, player_level):
    if type(talent_id) is not int or talent_id not in TALENTS or type(player_level) is not int or not 1 <= player_level <= 25:
        raise Refused("炼丹天赋或炼丹等级不在已验证范围。")
    return sum(x["required_level"] <= player_level for x in TALENTS[talent_id]["levels"])


def validate_rank(talent_id, value, player_level):
    if type(value) is not int or not 0 <= value <= rank_limit(talent_id, player_level):
        raise Refused(f"请填写 0～{rank_limit(talent_id, player_level)} 的整数天赋等级；保留游戏的炼丹等级要求。")
    return value


def parse_rank(text):
    try:
        value = int(str(text).strip())
    except (ValueError, TypeError) as error:
        raise Refused("天赋等级需要输入整数。") from error
    if str(text).strip() not in (str(value), "+" + str(value)):
        raise Refused("天赋等级需要输入整数。")
    return value


class AlchemyTalentResolver(AlchemyResolver):
    def ranks(self, address):
        if not address:
            return {}, (0, 0, 0, 0, 0)
        dc = self.obj(address, "System.Collections.Generic.Dictionary`2")
        offsets = {n: self.reviewed_field(dc, n, k) for n, k in
                   (("_entries", 0x1D), ("_count", 8), ("_freeCount", 8), ("_version", 8))}
        if offsets != {"_entries": 24, "_count": 32, "_freeCount": 40, "_version": 44}:
            raise Refused("炼丹天赋字典布局异常。")
        array = self.q(address + 24, anchored=True)
        count, free, version = (self.i(address + i, anchored=True) for i in (32, 40, 44))
        if not 0 <= free <= count <= 64 or not array and count:
            raise Refused("炼丹天赋字典长度异常。")
        result = {}
        if array:
            ac = self.obj(array, ".Entry[]")
            ec = self.info(self.q(int(ac["klass"], 16) + 0x40, anchored=True), ".Entry")
            offsets = [self.reviewed_field(ec, n, 8) - 16 for n in ("hashCode", "next", "key", "value")]
            if ec["instance_size"] != 32 or offsets != [0, 4, 8, 12] or not count <= self.q(array + 24, anchored=True) <= 128:
                raise Refused("炼丹天赋字典不是审核过的整数布局。")
            for i in range(count):
                h, nxt, key, value = struct.unpack("<iiii", self.anchor(array + 32 + i * 16, 16))
                if not -1 <= nxt < max(1, count):
                    raise Refused("炼丹天赋链异常。")
                if h < 0:
                    continue
                if key not in TALENTS or key in result or not 1 <= value <= 5:
                    raise Refused("炼丹天赋编号或等级异常。")
                result[key] = value
        if len(result) != count - free:
            raise Refused("炼丹天赋有效条目数不符。")
        return result, (address, array, count, free, version)

    def configuration(self):
        tables, tc = self.tables()
        rows = self.table_rows(tables, tc, "PillTalent", 16)
        if set(rows) != set(TALENTS):
            raise Refused("炼丹天赋配置不是已验证的七项。")
        for talent_id, (pointer, pc) in rows.items():
            levels = self.q(pointer + self.reviewed_field(pc, "<levels>k__BackingField", 0x15), anchored=True)
            current = []
            for item in self.list_objects(levels, 16):
                c = self.obj(item, "LubanDatas.TalentLevel")
                current.append({n: self.i(item + self.reviewed_field(c, "<" + n + ">k__BackingField", 8), anchored=True)
                                for n in ("rank", "required_level", "value", "cost")})
            expected = [{n: x[n] for n in ("rank", "required_level", "value", "cost")} for x in TALENTS[talent_id]["levels"]]
            if current != expected:
                raise Refused("炼丹天赋阈值、费用或效果配置已变化。")
        return tables


class AlchemyTalentAdapter:
    _begin = AlchemyAdapter._begin

    def __init__(self, game):
        self.game, self.blocked = game, False
        self.resolver = AlchemyTalentResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self._lock = threading.Lock()
        self._native = MiniGameOnce(game, self, operation="alchemy_talent_set", method_spec=METHOD,
                                    journal_name="alchemy-talent-actions.json")

    def snapshot(self):
        raw, rr = self._begin(), self.resolver
        player = raw["player"]
        pc = rr.obj(player, "Game.Model.PlayerModel")
        offset = rr.reviewed_field(pc, "refiningPills", 0x12)
        if offset != 0x60:
            raise Refused("炼丹存档组件字段与原生代码不同。")
        model = rr.q(player + offset, anchored=True)
        mc = rr.obj(model, MODEL)
        level = rr.integer(model, mc, "<Level>k__BackingField")
        if not 1 <= level <= 25:
            raise Refused("炼丹等级不在当前配置范围。")
        dictionary = rr.pointer_field(model, mc, "<TalentRanks>k__BackingField", 0x15, offset=0x28)
        ranks, dictionary_identity = rr.ranks(dictionary)
        tables = rr.configuration()
        closed, reason, observed = True, "", []
        for typename in ("UPFRefiningPillsTalentPanel", "UPFRefiningPillsExplorePanel", "UPFRefiningPillsQtePanel"):
            rr.panel_type = NS + typename
            manager, panels = rr.registered_panels()
            for panel in panels:
                c = rr.obj(panel, rr.panel_type)
                bc = rr.info(int(c["parent"], 16), "Game.BaseUI")
                showing = rr.boolean(panel, bc, "isShowing")
                observed.append(dict(panel=hex(panel), name=typename, showing=showing))
                if showing:
                    closed, reason = False, "请先退出炼丹探索、火候及天赋界面，再修改；重开界面刷新效果。"
        try:
            safe = require_safe_alchemy_context(self.game.resolver)
            rr.anchors.extend((a["address"], a["expected_hex"]) for a in safe["anchors"])
        except AcquisitionContextRefused:
            closed, reason = False, "仅在普通稳定场景且炼丹界面关闭时修改天赋。"
        identity = (self.game.stamp, raw["manager"], raw["store"], raw["world"], player, model, level, tables, dictionary_identity)
        anchors = rr.proof()
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused("读取期间角色已变化。")
        rows = {str(key): dict(id=key, name=config["name"]["zh-Hans"], value=ranks.get(key, 0),
                    minimum=0, maximum=rank_limit(key, level), configured_maximum=5,
                    note=config["desc"]["zh-Hans"]) for key, config in TALENTS.items()}
        return dict(active=True, can_edit=closed, reason=reason, identity=identity, player_level=level, rows=rows,
            native=dict(player=hex(player), model=hex(model), model_class=mc["klass"], dictionary=hex(dictionary),
                manager=hex(manager), observed_panels=observed, level=level, before_ranks=ranks,
                anchors=anchors, **rr._native_registry))

    def prepare_solve(self, shown):
        state = self.snapshot()
        if not state["can_edit"]:
            raise Refused(state["reason"])
        if shown is None or shown.get("identity") != state["identity"]:
            raise Refused("炼丹角色、等级或天赋已变化，请重新读取。")
        talent_id, value = shown["talent_id"], shown["desired_rank"]
        validate_rank(talent_id, value, state["player_level"])
        before = state["rows"][str(talent_id)]["value"]
        if before == value:
            raise Refused("目标与当前天赋等级相同，无需修改。")
        state.update(talent_id=talent_id, desired_rank=value)
        native = state["native"]
        native.update(talent_id=talent_id, rank=value, before=before, maximum=rank_limit(talent_id, state["player_level"]),
                      round_key=hashlib.sha256(repr((state["identity"], talent_id, before, value)).encode()).hexdigest(),
                      method_info=self.resolver.method(int(native["model_class"], 16), METHOD))
        native["method_spec"] = selected_method_spec(self.resolver, METHOD)
        native["anchors"] = self.resolver.proof()
        return state

    def verify_native(self, outcome, state):
        if outcome.get("talent_id") != state["talent_id"] or outcome.get("rank") != state["desired_rank"]:
            raise UncertainWrite("炼丹天赋调用后返回值不一致。")
        after = self.snapshot()
        # Setter may create/remove a dictionary slot, including an initially null dictionary.
        if after["identity"][:-1] != state["identity"][:-1]:
            raise UncertainWrite("天赋调用后人物或炼丹等级变化。")
        for key, row in after["rows"].items():
            expected = state["desired_rank"] if int(key) == state["talent_id"] else state["rows"][key]["value"]
            if row["value"] != expected:
                raise UncertainWrite("炼丹天赋调用后复读不一致。")
        return dict(verified=True, phase="talent_updated", snapshot=after,
                    message="炼丹天赋等级已复读确认；重开游戏中的炼丹界面查看，存档后保留。")

    def set_value(self, shown, talent_id, value):
        if not self._lock.acquire(blocking=False):
            raise Refused("炼丹天赋操作正在处理。")
        try:
            validate_rank(talent_id, value, shown["player_level"])
            return self._native.solve(dict(shown, talent_id=talent_id, desired_rank=value))
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        self._native.close()
