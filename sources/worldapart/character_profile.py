"""Saved scalar values whose reviewed setters have no events or transitions."""
from dataclasses import dataclass, replace
import json
import os
import re
import struct
import threading
import uuid

from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from character_attributes import _deduplicate, NS
from character_attributes_interact import InteractResolver
from character_attributes_write import AttributeWriteOnce
from native_write import process_identity
from runtime_paths import initialize_runtime
from write_guard import Refused, UncertainWrite

FIELDS = {
    'reserve_exp': dict(name='丹田灵气（储备）', field='<CultivateReserveExp>k__BackingField', token=0x0400AD3B,
                       offset=0x74, minimum=0, maximum=1_000_000, owner='combat'),
}
SAFE = frozenset(('verified', 'rejected'))


@dataclass(frozen=True)
class ProfileTarget:
    key: str
    value: int
    address: int
    identity: tuple
    anchors: tuple
    minimum: int
    maximum: int
    can_edit: bool = True

    @property
    def exists(self):
        return self.address > 0


def parse_profile_value(text):
    if type(text) is not str or len(text) > 20 or not re.fullmatch(r'-?[0-9]{1,7}', text.strip()):
        raise Refused('请输入整数，不接受小数或科学计数法。')
    return int(text.strip())


def validate_profile_value(target, value):
    if type(target) is not ProfileTarget or target.key not in FIELDS or not target.can_edit:
        raise Refused('当前角色或场景不允许修改，请刷新。')
    spec = FIELDS[target.key]
    if (any(type(v) is not int for v in (value, target.value, target.minimum, target.maximum))
            or target.minimum != spec['minimum'] or not 0 < target.maximum <= spec['maximum']
            or not target.minimum <= target.value <= target.maximum
            or not target.minimum <= value <= target.maximum):
        raise Refused(f"允许范围为 {target.minimum}～{target.maximum}（当前境界上限与工具限制取较小值）。")
    if value == target.value or abs(value - target.value) > 1000:
        raise Refused('目标值应与当前值不同，单次变化最多 1000。')
    if (type(target.address) is not int or target.address <= 0 or target.address % 4
            or type(target.identity) is not tuple or not target.identity
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096):
        raise Refused('角色目标与身份锚无效。')
    for entry in target.anchors:
        if type(entry) is not tuple or len(entry) != 2:
            raise Refused('角色身份锚无效。')
        address, raw = entry
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused('角色身份锚无效。')
        try:
            data = bytes.fromhex(raw)
        except ValueError as error:
            raise Refused('角色身份锚无效。') from error
        if not 1 <= len(data) <= 4096 or address < target.address + 4 and address + len(data) > target.address:
            raise Refused('角色身份锚范围无效。')
    return value


def pack(value):
    return struct.pack('<i', value)


class ProfileWriteOnce(AttributeWriteOnce):
    def __init__(self, reader, stamp, target, *, new_value):
        value = validate_profile_value(target, new_value)
        self.reader, self.stamp, self.target = reader, stamp, target
        self.before, self.after, self.used = pack(target.value), pack(value), False


def set_profile_scalar(memory, resolve, shown, value, record):
    value = validate_profile_value(shown, value)
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        raise Refused('角色数值或场景已变化，请刷新。')
    event = dict(operation='character_profile_set', field=shown.key, before=shown.value, after=value)
    record(dict(event, status='attempt'))
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        record(dict(event, status='rejected'))
        raise Refused('写入前角色数值或场景已变化，未修改。')
    try:
        memory.write_exact(shown.address, pack(value))
    except UncertainWrite:
        try:
            record(dict(event, status='unknown'))
        except Exception:
            pass
        raise
    except Refused:
        record(dict(event, status='rejected'))
        raise
    except Exception as error:
        try:
            record(dict(event, status='unknown'))
        except Exception:
            pass
        raise UncertainWrite('角色数值写入未确认，请核对游戏，勿重复操作。') from error
    try:
        current = resolve(shown.key)
        if current != replace(shown, value=value) or memory.read_exact(shown.address, 4) != pack(value):
            raise UncertainWrite('角色数值写入后回读不符。')
        record(dict(event, status='verified'))
    except Exception as error:
        try:
            record(dict(event, status='unknown'))
        except Exception:
            pass
        raise UncertainWrite('角色数值写入后核验未完成，请核对游戏。') from error
    return current


class ProfileResolver(InteractResolver):
    def reserve_limit(self, layer):
        # GetLimit follows layer -> phase -> realm and returns Max(0, this
        # reviewed Int32). There are no cached multipliers in the native path.
        proofs = ((0x14C4D00, '40534883ec20803d1375080700488bd9'),
                  (0x14F8540, '40534883ec20803d3661060700488bd9'))
        matched = [(rva, code) for rva, code in proofs
                   if self.exact(self.module + rva, len(code)//2).hex() == code]
        if len(matched) != 1:
            raise Refused('丹田灵气上限入口与已验证代码不同。')
        self.anchor(self.module + matched[0][0], len(matched[0][1])//2)
        tables, tc = self.tables()
        layers = self.table_rows(tables, tc, 'CultivateLayer', 128)
        phases = self.table_rows(tables, tc, 'CultivatePhase', 64)
        realms = self.table_rows(tables, tc, 'CultivateRealm', 32)
        if layer not in layers:
            raise Refused('当前修为层级没有配置。')
        pointer, klass = layers[layer]
        phase = self.i(pointer + self.reviewed_field(klass, '<phase>k__BackingField', 0x11), anchored=True)
        if phase not in phases:
            raise Refused('当前修为阶段没有配置。')
        pointer, klass = phases[phase]
        realm = self.i(pointer + self.reviewed_field(klass, '<realm>k__BackingField', 0x11), anchored=True)
        if realm not in realms or realm <= 0:
            raise Refused('当前境界没有配置。')
        pointer, klass = realms[realm]
        offset = self.reviewed_field(klass, '<cultivate_reserve_exp_limit>k__BackingField', 8)
        if offset != 0xC0:
            raise Refused('丹田灵气境界上限布局不符。')
        limit = self.i(pointer + offset, anchored=True)
        if not 0 < limit <= 2147483647:
            raise Refused('当前境界不允许储备灵气或上限异常。')
        return tables, realm, limit


class CharacterProfileAdapter:
    def __init__(self, game):
        self.game = game
        self.resolver = ProfileResolver(game.resolver.reader, metadata_base=game.resolver.meta)
        self.blocked, self._lock = False, threading.Lock()
        self.journal = initialize_runtime() / 'profile-writes' / f'{game.resolver.reader.pid}-{game.stamp[1]}.json'

    def require_ready(self):
        if self.journal.exists():
            try:
                data = json.loads(self.journal.read_text(encoding='utf8'))
                if data.get('version') != 1 or data.get('process_key') != [self.game.resolver.reader.pid, self.game.stamp[1]]:
                    raise ValueError('invalid identity')
                if data.get('status') not in SAFE:
                    raise Refused('该游戏有未确认的角色数值操作，请核对后再处理。')
            except Refused:
                raise
            except Exception as error:
                raise Refused('角色数值操作记录无法核对，请保留日志。') from error

    def record(self, event):
        value = dict(event, version=1, process_key=[self.game.resolver.reader.pid, self.game.stamp[1]])
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temp = self.journal.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        with temp.open('x', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(self.journal)
        self.game.record(dict(character_profile=value))

    def snapshot(self):
        if self.blocked or self.game.blocked or not self.game.resolver:
            raise Refused('角色数值连接已停止。')
        rr = self.resolver
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused('游戏进程已变化。')
        raw = self.game.resolver.resolve()
        if not raw.get('anchor_verified'):
            raise Refused('无法确认当前角色。')
        rr.anchors = [(a['address'], a['expected_hex']) for a in raw['anchors']]
        player = raw['player']
        pc = rr.obj(player, 'Game.Model.PlayerModel')
        combat = rr.q(player + rr.reviewed_field(pc, 'combat', 0x12), anchored=True)
        cc = rr.obj(combat, NS + 'CombatModel')
        if rr.q(combat + 0x10, anchored=True) != player:
            raise Refused('修为组件不属于当前角色。')
        layer = rr.i(combat + rr.reviewed_field(cc, '<CurrentLayerId>k__BackingField', 0x11), anchored=True)
        pending = rr.q(combat + rr.reviewed_field(cc, '<PendingRealmBreakthrough>k__BackingField', 0x12), anchored=True)
        depth = rr.i(combat + rr.reviewed_field(cc, '_cultivateInjectBatchDepth', 8), anchored=True)
        tables, realm, native_limit = rr.reserve_limit(layer)
        can_edit, reason = True, ''
        try:
            context = require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a['address'], a['expected_hex']) for a in context['anchors'])
        except AcquisitionContextRefused:
            can_edit, reason = False, '修行储备只能在普通场景、战斗结算结束后修改。'
        if pending or depth:
            can_edit, reason = False, '正在注入修为或突破，请完成后刷新。'
        values = {}
        for key, spec in FIELDS.items():
            owner, klass = (player, pc) if spec['owner'] == 'player' else (combat, cc)
            offset = rr.reviewed_field(klass, spec['field'], 8)
            field = next(f for f in klass['fields'] if f['name'] == spec['field'])
            current_spec = rr.runtime_spec(klass['namespace'] + '.' + klass['name'])
            current_token = next(f['token'] for f in current_spec['fields'] if f['name'] == spec['field'])
            if offset != spec['offset'] or int(field['token'], 16) != current_token:
                raise Refused('角色数值字段与已核验版本不同。')
            values[key] = (owner + offset, rr.i(owner + offset))
        value_anchors = [(address, pack(value).hex()) for address, value in values.values()]
        anchors = _deduplicate(rr.anchors)
        for address, expected in anchors + tuple(value_anchors):
            if rr.exact(address, len(expected)//2).hex() != expected:
                raise Refused('读取期间角色或场景变化，请刷新。')
        if process_identity(rr.reader.h) != self.game.stamp:
            raise Refused('游戏进程已变化。')
        identity = (self.game.stamp, raw['manager'], raw['store'], raw['world'], player, combat, layer,
                    tables, realm, native_limit)
        rows = {}
        for key, spec in FIELDS.items():
            address, value = values[key]
            maximum = min(spec['maximum'], native_limit)
            allowed = spec['minimum'] <= value <= maximum
            target = ProfileTarget(key, value, address, identity,
                _deduplicate(anchors + tuple(a for a in value_anchors if a[0] != address)),
                spec['minimum'], maximum, can_edit and allowed)
            rows[key] = dict(name=spec['name'], target=target,
                limit_source=f'当前境界上限 {native_limit}，工具上限 {spec["maximum"]}，取较小值',
                note='只修改尚未注入的储备灵气；不直接提升当前修为、突破境界或绕过条件。'
                + (' 当前值超出本工具范围，仅供读取。' if not allowed else ''))
        return dict(rows=rows, can_edit=can_edit, reason=reason)

    def resolve(self, key):
        if key not in FIELDS:
            raise Refused('未知角色数值。')
        return self.snapshot()['rows'][key]['target']

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused('角色数值操作正在进行。')
        try:
            from native_broker import startup_lock
            from acquisition_adapter import native_calls_pending
            with startup_lock(self.journal):
                if self.blocked or native_calls_pending():
                    raise Refused('连接已停止或原生操作未完成，未修改角色数值。')
                self.require_ready()
                memory = ProfileWriteOnce(self.game.resolver.reader, self.game.stamp, shown, new_value=value)
                return set_profile_scalar(memory, self.resolve, shown, value, self.record)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        pass  # Reader belongs to the shared game adapter; there is no native session.
