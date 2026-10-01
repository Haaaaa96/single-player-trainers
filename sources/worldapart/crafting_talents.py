"""Single reviewed saved smithing talent balance; cached talent pages must close."""
from dataclasses import dataclass, replace
import json
import os
import re
import struct
import threading
import uuid
from acquisition_context import require_safe_acquisition_context, AcquisitionContextRefused
from character_attributes import _deduplicate
from character_attributes_write import AttributeWriteOnce
from native_write import process_identity
from runtime_paths import initialize_runtime
from write_guard import Refused, UncertainWrite
from crafting_adapter import CraftingResolver, SPECS, MODEL, PANEL, TALENT_PANELS
FIELDS = {'crafting_talents': dict(name='炼器天赋点',minimum=0,maximum=1000)}
SAFE = frozenset(('verified','rejected'))

@dataclass(frozen=True)
class CraftingTalentTarget:
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


def parse_crafting_talent_value(text):
    if type(text) is not str or len(text) > 20 or not re.fullmatch(r'-?[0-9]{1,7}', text.strip()):
        raise Refused('请输入整数，不接受小数或科学计数法。')
    return int(text.strip())


def validate_crafting_talent_value(target, value):
    if type(target) is not CraftingTalentTarget or target.key not in FIELDS or not target.can_edit:
        raise Refused('当前炼器天赋或场景不允许修改，请刷新。')
    spec = FIELDS[target.key]
    if (any(type(v) is not int for v in (value, target.value, target.minimum, target.maximum))
            or target.minimum != spec['minimum'] or not 0 < target.maximum <= spec['maximum']
            or not target.minimum <= target.value <= target.maximum
            or not target.minimum <= value <= target.maximum):
        raise Refused(f"允许范围为 {target.minimum}～{target.maximum}（工具限制）。")
    if value == target.value or abs(value - target.value) > 1000:
        raise Refused('目标值应与当前值不同，单次变化最多 1000。')
    if (type(target.address) is not int or target.address <= 0 or target.address % 4
            or type(target.identity) is not tuple or not target.identity
            or type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096):
        raise Refused('炼器天赋目标与身份锚无效。')
    for entry in target.anchors:
        if type(entry) is not tuple or len(entry) != 2:
            raise Refused('炼器天赋身份锚无效。')
        address, raw = entry
        if type(address) is not int or address <= 0 or type(raw) is not str:
            raise Refused('炼器天赋身份锚无效。')
        try:
            data = bytes.fromhex(raw)
        except ValueError as error:
            raise Refused('炼器天赋身份锚无效。') from error
        if not 1 <= len(data) <= 4096 or address < target.address + 4 and address + len(data) > target.address:
            raise Refused('炼器天赋身份锚范围无效。')
    return value


def pack(value):
    return struct.pack('<i', value)


class CraftingTalentWriteOnce(AttributeWriteOnce):
    def __init__(self, reader, stamp, target, *, new_value):
        value = validate_crafting_talent_value(target, new_value)
        self.reader, self.stamp, self.target = reader, stamp, target
        self.before, self.after, self.used = pack(target.value), pack(value), False


def set_crafting_talent_scalar(memory, resolve, shown, value, record):
    value = validate_crafting_talent_value(shown, value)
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        raise Refused('炼器天赋数值或场景已变化，请刷新。')
    event = dict(operation='character_crafting_talent_set', field=shown.key, before=shown.value, after=value)
    record(dict(event, status='attempt'))
    if resolve(shown.key) != shown or memory.read_exact(shown.address, 4) != pack(shown.value):
        record(dict(event, status='rejected'))
        raise Refused('写入前炼器天赋数值或场景已变化，未修改。')
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
        raise UncertainWrite('炼器天赋数值写入未确认，请核对游戏，勿重复操作。') from error
    try:
        current = resolve(shown.key)
        if current != replace(shown, value=value) or memory.read_exact(shown.address, 4) != pack(value):
            raise UncertainWrite('炼器天赋数值写入后回读不符。')
        record(dict(event, status='verified'))
    except Exception as error:
        try:
            record(dict(event, status='unknown'))
        except Exception:
            pass
        raise UncertainWrite('炼器天赋数值写入后核验未完成，请核对游戏。') from error
    return current


class CraftingTalentAdapter:
    def __init__(self, game):
        self.game = game
        self.resolver = CraftingResolver(game.resolver.reader,metadata_base=game.resolver.meta)
        self.blocked,self._lock = False,threading.Lock()
        self.journal = initialize_runtime() / 'crafting-talent-writes' / f'{game.resolver.reader.pid}-{game.stamp[1]}.json'

    def require_ready(self):
        if self.journal.exists():
            try:
                data = json.loads(self.journal.read_text(encoding='utf8'))
                if data.get('version') != 1 or data.get('process_key') != [self.game.resolver.reader.pid, self.game.stamp[1]]:
                    raise ValueError('invalid identity')
                if data.get('status') not in SAFE:
                    raise Refused('该游戏有未确认的炼器天赋点操作，请核对后再处理。')
            except Refused:
                raise
            except Exception as error:
                raise Refused('炼器天赋点操作记录无法核对，请保留日志。') from error

    def record(self, event):
        value = dict(event, version=1, process_key=[self.game.resolver.reader.pid, self.game.stamp[1]])
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temp = self.journal.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        with temp.open('x', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(self.journal)
        self.game.record(dict(crafting_talent=value))

    def snapshot(self):
        rr=self.resolver
        if (self.blocked or self.game.blocked or getattr(self.game,'write_enabled',True) is False
                or process_identity(rr.reader.h)!=self.game.stamp):
            raise Refused('炼器天赋连接已停止或游戏进程变化。')
        raw=self.game.resolver.resolve()
        if not raw.get('anchor_verified'):
            raise Refused('当前角色无法确认。')
        rr.anchors=[(a['address'],a['expected_hex']) for a in raw['anchors']]
        player=raw['player']; pc=rr.obj(player,'Game.Model.PlayerModel')
        model=rr.pointer_field(player,pc,'alchemy',offset=0x50)
        mc=rr.obj(model,MODEL)
        # Unlike Bag/Combat, AlchemyModel's StoredEntityComponent.entity is
        # legitimately null in a loaded save. Ownership is the anchored unique
        # current Player.alchemy reference, not an invented mandatory backref.
        parent=rr.info(int(mc['parent'],16),'SimpleSave.StoredEntityComponent')
        if rr.field(parent,'<entity>k__BackingField',0x12,0x0400003B)!=0x10:
            raise Refused('炼器存档组件父类型布局不同。')
        entity=rr.q(model+0x10,anchored=True)
        if entity not in (0,player):
            raise Refused('炼器存档组件存在不同角色的反向引用。')
        address=rr.at(model,mc,'<TalentPoints>k__BackingField',8,0x28)
        value=rr.i(address)
        version=rr.integer(model,mc,'<TalentStateVersion>k__BackingField')
        if version!=1:
            raise Refused('炼器天赋状态尚未由游戏升级，请先打开天赋界面再关闭。')
        if not rr.pointer_field(model,mc,'<UnlockedTalentIds>k__BackingField',0x15) or not rr.pointer_field(model,mc,'<LearnedTalentIds>k__BackingField',0x15):
            raise Refused('炼器天赋集合尚未初始化。')
        if rr.anchor(rr.module+0x678310,4).hex()!='895128c3':
            raise Refused('炼器天赋点写入语义与已审核版本不同。')
        can_edit,reason=True,''
        try:
            context=require_safe_acquisition_context(self.game.resolver)
            rr.anchors.extend((a['address'],a['expected_hex']) for a in context['anchors'])
        except AcquisitionContextRefused:
            can_edit,reason=False,'请回到稳定普通场景后修改炼器天赋点。'
        try:
            for panel_type in TALENT_PANELS+(PANEL,):
                rr.panel_type=panel_type
                _,panels=rr.registered_panels()
                for panel in panels:
                    if rr.visible_panel(panel) is not None:
                        can_edit,reason=False,'请先关闭游戏内炼器天赋页与炼器棋盘，再修改点数；重开天赋页查看。'
        finally:
            rr.panel_type=PANEL
        proof=rr.proof()
        if process_identity(rr.reader.h)!=self.game.stamp or rr.i(address)!=value:
            raise Refused('读取期间炼器天赋数据变化，请刷新。')
        allowed=0<=value<=1000
        target=CraftingTalentTarget('crafting_talents',value,address,
            (self.game.stamp,raw['manager'],raw['store'],raw['world'],player,model,entity,version),
            _deduplicate((int(a['address'],16),a['expected_hex']) for a in proof),0,1000,can_edit and allowed)
        return dict(target=target,can_edit=can_edit and allowed,
                    reason=reason or ('' if allowed else '当前点数超出本工具0～1000范围，仅供读取。'))

    def resolve(self,key):
        if key!='crafting_talents':
            raise Refused('未知炼器天赋目标。')
        return self.snapshot()['target']

    def set_value(self, shown, value):
        if not self._lock.acquire(blocking=False):
            raise Refused('炼器天赋点操作正在进行。')
        try:
            from native_broker import startup_lock
            from acquisition_adapter import native_calls_pending
            with startup_lock(self.journal):
                if self.blocked or getattr(self.game,'write_enabled',True) is False or native_calls_pending():
                    raise Refused('连接已停止或原生操作未完成，未修改炼器天赋点。')
                self.require_ready()
                memory = CraftingTalentWriteOnce(self.game.resolver.reader, self.game.stamp, shown, new_value=value)
                return set_crafting_talent_scalar(memory, self.resolve, shown, value, self.record)
        except UncertainWrite:
            self.blocked = True
            raise
        finally:
            self._lock.release()

    def close(self):
        pass  # Reader belongs to the shared game adapter; there is no native session.
