"""Canonical current smithing round. No heap scan or direct reward creation."""
import hashlib
import json
import struct

from acquisition_adapter import native_calls_pending
from character_attributes import _deduplicate
from dual_cultivation_common import RegisteredMiniResolver, selected_method_spec
from learning_adapter import LearningResolver
from native_write import process_identity
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused, UncertainWrite
from crafting_logic import completion_plan, integer

SPECS = json.loads((RESOURCE_ROOT / 'crafting_specs.json').read_text(encoding='utf8'))
PANEL = 'Game.UI.UPFLogic.Alchemy.UPFAlchemyPanel'
LOGIC = 'Game.AlchemyGameLogic'
MODEL = 'Game.Model.Player.Components.AlchemyModel'
TALENT_PANELS = ('Game.UI.UPFLogic.Alchemy.UPFAlchemyTalentPanel', 'Game.AlchemyTalentPanel')
METHODS = SPECS['methods']


class CraftingResolver(RegisteredMiniResolver):
    def __init__(self, reader, **kwargs):
        super().__init__(reader, SPECS['classes'], PANEL, **kwargs)

    def info(self,klass,fullname=None):
        c=LearningResolver.info(self,klass,fullname)
        actual=c['namespace']+'.'+c['name']
        if actual!='Emei.NotifiableList`1':
            return super().info(klass,fullname)
        spec=self.runtime_spec(actual,SPECS['classes'][actual])
        handle=self.q(klass+0x68,anchored=True)
        if handle==0:
            generic=self.q(klass+0x60,anchored=True)
            definition=self.q(generic,anchored=True)
            raw=self.anchor(definition,16)
            if raw[10]!=0x12 or self.q(generic+24,anchored=True)!=klass:
                raise Refused('炼器配置泛型定义不匹配。')
            handle=struct.unpack_from('<Q',raw)[0]
        if (handle!=self.meta+spec['type_definition_offset']
                or self.i(klass+0x11C,anchored=True)!=spec['token']
                or len(c['fields'])!=spec['field_count']
                or {f['name']:int(f['token'],16) for f in c['fields']}!={f['name']:f['token'] for f in spec['fields']}):
            raise Refused('炼器配置列表元数据不匹配。')
        return c

    def at(self, obj, c, name, kind, offset):
        if self._field(c, name, kind) != offset:
            raise Refused('炼器字段偏移与审核代码不同：' + name)
        return obj + offset

    def config_objects(self,address,element_type,maximum=32):
        """Luban uses Emei.NotifiableList<T>, whose base is List<T>."""
        cc=self.obj(address,'Emei.NotifiableList`1')
        parent=self.q(int(cc['klass'],16)+0x58,anchored=True)
        lc=self.info(parent,'System.Collections.Generic.List`1')
        count=self.integer(address,lc,'_size')
        self.integer(address,lc,'_version')
        array=self.pointer_field(address,lc,'_items',0x1D,offset=0x10)
        if not 0<=count<=maximum or not array:
            raise Refused('炼器配置列表长度异常。')
        ac=self.obj(array,None)
        if not ac['name'].endswith('[]'):
            raise Refused('炼器配置列表数组类型无效。')
        self.info(self.q(int(ac['klass'],16)+0x40,anchored=True),element_type)
        capacity=self.q(array+24,anchored=True)
        if not count<=capacity<=maximum*2:
            raise Refused('炼器配置列表容量异常。')
        values=[]
        for index in range(count):
            value=self.q(array+32+index*8,anchored=True)
            self.obj(value,element_type)
            if value in values:raise Refused('炼器配置列表含重复对象。')
            values.append(value)
        return tuple(values)

    def energy_dictionary(self, address):
        c = self.obj(address, 'System.Collections.Generic.Dictionary`2')
        fields = (("_entries",0x1D,0x04001B00,0x18),("_count",8,0x04001B01,0x20),
                  ("_freeCount",8,0x04001B03,0x28),("_version",8,0x04001B04,0x2C))
        for name,kind,token,offset in fields:
            if self.field(c,name,kind,token) != offset:
                raise Refused('炼器元素字典布局不同。')
        entries = self.q(address+0x18, anchored=True)
        count, free = self.i(address+0x20,anchored=True), self.i(address+0x28,anchored=True)
        version = self.i(address+0x2C,anchored=True)
        if not 0 <= free <= count <= 32 or not entries:
            raise Refused('炼器元素字典长度异常。')
        ac = self.obj(entries,'.Entry[]')
        ec = self.info(self.q(int(ac['klass'],16)+0x40,anchored=True),'.Entry')
        offsets = [self.field(ec,n,k,t)-16 for n,k,t in (
            ('hashCode',8,0x04001B0D),('next',8,0x04001B0E),('key',8,0x04001B0F),('value',8,0x04001B10))]
        if ec['instance_size']-16 != 16 or offsets != [0,4,8,12]:
            raise Refused('炼器元素不是 Int32/Int32 字典。')
        if not count <= self.q(entries+24,anchored=True) <= 64:
            raise Refused('炼器元素字典容量异常。')
        result = {}
        for index in range(count):
            entry = entries+32+16*index
            h,nxt,key,value = struct.unpack('<iiii',self.anchor(entry,16))
            if not -1 <= nxt < max(1,count):
                raise Refused('炼器元素字典链异常。')
            if h < 0:
                continue
            integer(key,1,5); integer(value)
            if key in result:
                raise Refused('炼器元素重复。')
            result[key] = dict(value=value,address=entry+12)
        if len(result) != count-free:
            raise Refused('炼器元素数量不一致。')
        return result, dict(address=hex(address),entries=hex(entries),count=count,free=free,version=version)

    def placement_state(self, panel, pc):
        # Starting the actual session cancels prewarming and resets its result
        # flag. Session interaction, not the prewarm result, proves readiness.
        prewarm=self.boolean(panel,pc,'_prewarmComplete')
        for name,offset in (('_pendingSessionCoroutine',0x160),('_prewarmCoroutine',0x168)):
            if self.pointer_field(panel,pc,name,offset=offset):
                raise Refused('炼器启动或预热协程尚未结束，请稍后读取。')
        data=self.pointer_field(panel,pc,'_pendingSettlement',offset=0x218)
        dc=self.obj(data,'.PlacementSettlementData')
        lists={}
        for name,offset in (('ClearedCells',0x10),('AddedCells',0x18)):
            collection=self.pointer_field(data,dc,name,0x15,offset=offset)
            cc=self.obj(collection,'System.Collections.Generic.List`1')
            count=self.integer(collection,cc,'_size')
            self.integer(collection,cc,'_version')
            self.pointer_field(collection,cc,'_items',0x1D,offset=0x10)
            if count!=0:
                raise Refused('炼器落子尚有待播放的格子变化，请等待动画结束。')
            lists[name]=hex(collection)
        before=self.integer(data,dc,'ScoreBefore')
        after=self.integer(data,dc,'ScoreAfter')
        element=self.integer(data,dc,'ElementType')
        if (before,after)!=(-1,-1) or not 0<=element<=5:
            raise Refused('炼器落子尚有待处理的分数结算，请稍后读取。')
        return dict(address=hex(data),cleared=lists['ClearedCells'],added=lists['AddedCells'],
                    score_before=before,score_after=after,element=element,prewarm_complete=prewarm)

    def round(self, panel, raw, manager):
        visible = self.visible_panel(panel)
        if visible is None:
            return None
        pc, actionable = visible
        if not actionable:
            return dict(active=True,can_complete=False,reason='请关闭弹窗并回到活动炼器棋盘。')
        flags = {}
        for name,expected,offset in (
            ('_alchemySessionTerminated',False,0x138),('_hasPendingSession',False,0x188),
            ('_preactivatedForPrewarm',False,0x18A),
            ('_sessionInteractionEnabled',True,0x18B),('m_AlchemySettlementStarted',False,0x228)):
            address=self.at(panel,pc,name,2,offset)
            value=self.boolean(panel,pc,name)
            flags[name]=dict(address=hex(address),expected=expected)
            if value != expected:
                reason={
                    '_alchemySessionTerminated':'当前炼器会话已经结束，请进入新的炼器棋盘。',
                    '_hasPendingSession':'炼器正在启动下一局，请等待棋盘加载完成。',
                    '_preactivatedForPrewarm':'炼器界面仍在预热，请等待正式棋盘加载完成。',
                    '_sessionInteractionEnabled':'当前炼器棋盘尚未开放操作，请等待加载或弹窗结束。',
                    'm_AlchemySettlementStarted':'当前炼器已经开始结算，请在游戏中完成结果页。',
                }[name]
                return dict(active=True,can_complete=False,reason=reason)
        # These offsets are obtained from checked FieldInfo rather than inferred
        # from neighbouring alignment. The native bridge verifies FieldInfo too.
        for name,kind in (('_isPlayingFlyInAnimation',2),):
            offset=self._field(pc,name,kind)
            value=self.boolean(panel,pc,name) if kind==2 else self.q(panel+offset,anchored=True)
            flags[name]=dict(address=hex(panel+offset),expected=False if kind==2 else '0x0',kind=kind,
                             token=next(f['token'] for f in self.runtime_spec(PANEL,SPECS['classes'][PANEL])['fields'] if f['name']==name))
            if value:
                return dict(active=True,can_complete=False,reason='炼器落子动画尚未结束，请稍后读取。')
        placement=self.placement_state(panel,pc)
        logic=self.pointer_field(panel,pc,'_logic',offset=0x100)
        lc=self.obj(logic,LOGIC)
        receipt=self.pointer_field(panel,pc,'_sessionCostReceipt',offset=0x130)
        rc=self.obj(receipt,'Game.UI.UPFLogic.Alchemy.AlchemyLaunchCostReceipt')
        if not self.boolean(receipt,rc,'_launchCommitted') or self.boolean(receipt,rc,'_sessionCompleted'):
            raise Refused('炼器费用凭证尚未提交或已经完成。')
        player=raw['player']
        player_class=self.obj(player,'Game.Model.PlayerModel')
        bag=self.q(player+self.field(player_class,'bag',0x12,0x0400A60E),anchored=True)
        combat=self.q(player+self.field(player_class,'combat',0x12,0x0400A60F),anchored=True)
        if (self.pointer_field(receipt,rc,'_bag',offset=0x10)!=bag
                or self.pointer_field(receipt,rc,'_combat',offset=0x18)!=combat
                or self.q(bag+16,anchored=True)!=player or self.q(combat+16,anchored=True)!=player):
            raise Refused('炼器会话费用不属于当前角色。')
        proto=self.pointer_field(logic,lc,'<Prototype>k__BackingField',offset=0x10)
        proto_class=self.obj(proto,'LubanDatas.data.AlchemyPrototype')
        proto_id=self.integer(proto,proto_class,'<id>k__BackingField',0x11)
        selected_id=self.integer(panel,pc,'_selectedProtoItemId')
        if proto_id<=0 or proto_id!=selected_id:
            raise Refused('当前器胚与炼器会话不一致。')
        generation=self.integer(panel,pc,'_prewarmGeneration')
        reforge=self.q(panel+self._field(pc,'_reforgeTargetUid',10),anchored=True)
        score_address=self.at(logic,lc,'<Score>k__BackingField',8,0x58)
        score=self.i(score_address,anchored=True)
        tier_list=self.pointer_field(proto,proto_class,'<score_tiers>k__BackingField',0x15,offset=0x50)
        tiers=[]
        for address in self.config_objects(tier_list,'LubanDatas.AlchemyScoreTierEntry',maximum=32):
            tc=self.obj(address,'LubanDatas.AlchemyScoreTierEntry')
            tiers.append(dict(address=hex(address),tier_id=self.integer(address,tc,'<tier_id>k__BackingField',0x11),
                              score_min=self.integer(address,tc,'<score_min>k__BackingField')))
        energy=self.pointer_field(logic,lc,'<Energy>k__BackingField',0x15,offset=0x40)
        energies,energy_descriptor=self.energy_dictionary(energy)
        effect_list=self.pointer_field(logic,lc,'<Effects>k__BackingField',0x15,offset=0x48)
        config_list=self.pointer_field(proto,proto_class,'<effects>k__BackingField',0x15,offset=0x48)
        effect_configs=self.config_objects(config_list,
                                        'LubanDatas.AlchemyArtifactAffixSlot',maximum=32)
        effect_pointers=self.object_list(effect_list,'Game.AlchemyEffectState',maximum=32)
        if len(effect_pointers)!=len(effect_configs):
            raise Refused('炼器词条与器胚配置数量不同。')
        effects=[]
        for index,address in enumerate(effect_pointers):
            ec=self.obj(address,'Game.AlchemyEffectState')
            config=self.pointer_field(address,ec,'Config',offset=0x10)
            cc=self.obj(config,'LubanDatas.AlchemyEffect')
            source=effect_configs[index]
            sc=self.obj(source,'LubanDatas.AlchemyArtifactAffixSlot')
            # Initialize converts the immutable artifact slot into a separate
            # runtime AlchemyEffect. Verify all five copied configuration fields.
            copied={}
            for name,kind in (('effect_type',0x11),('effect_id',8),('element_type',0x11),('required_energy',8),('sort',8)):
                field='<'+name+'>k__BackingField'
                value=self.integer(config,cc,field,kind)
                if value!=self.integer(source,sc,field,kind):
                    raise Refused('当前炼器词条的配置值与器胚不一致。')
                copied[name]=value
            if copied['effect_type']!=2:
                raise Refused('当前器胚包含尚未核验的词条类型。')
            effects.append(dict(address=hex(address),config=hex(config),source_config=hex(source),
                effect_type=copied['effect_type'],sort=copied['sort'],pool_id=copied['effect_id'],
                element=copied['element_type'],required=copied['required_energy'],
                activated=self.boolean(address,ec,'IsActivated'),
                affix_id=self.integer(address,ec,'AffixConfigId'),affix_value=self.float_field(address,ec,'AffixValue',anchored=True)))
        plan=completion_plan(score,tiers,effects,energies)
        methods={key:self.method(int(pc['klass'] if key=='complete' else lc['klass'],16),spec)
                 for key,spec in METHODS.items()}
        identity=(self.stamp,raw['manager'],raw['store'],raw['world'],player,manager,panel,
                  self.q(panel+16,anchored=True),logic,receipt,proto,proto_id,generation,reforge)
        round_key=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()
        native=dict(panel=hex(panel),logic=hex(logic),receipt=hex(receipt),prototype=hex(proto),
            player=hex(player),bag=hex(bag),combat=hex(combat),manager=hex(manager),flags=flags,
            score_address=hex(score_address),plan=plan,tiers=tiers,effects=effects,energy=energy_descriptor,placement=placement,
            tier_list=hex(tier_list),effect_list=hex(effect_list),config_list=hex(config_list),methods=methods,
            method_info=methods['complete'],round_key=round_key,**self._native_registry)
        native['method_specs'] = {key: selected_method_spec(self, spec) for key, spec in METHODS.items()}
        native['method_spec'] = native['method_specs']['complete']
        # No gameplay writes occur while reading this descriptor.
        return dict(active=True,can_complete=True,reason='',identity=identity,native=native,
                    score=score,highest_tier=plan['tier_id'],effect_count=len(effects),
                    activated_count=sum(e['activated'] for e in effects))


class CraftingAdapter:
    def __init__(self, game):
        self.game,self.blocked=game,False
        self.resolver=CraftingResolver(game.resolver.reader,metadata_base=game.resolver.meta)
        from dual_cultivation_native import MiniGameOnce
        self.native=MiniGameOnce(game,self,operation='crafting_complete',method_spec=METHODS['complete'],
                                 journal_name='crafting-once.json')
        from crafting_talents import CraftingTalentAdapter
        self.talents=CraftingTalentAdapter(game)

    def snapshot(self):
        if (self.blocked or self.game.blocked or getattr(self.game,'write_enabled',True) is False
                or process_identity(self.resolver.reader.h)!=self.game.stamp):
            raise Refused('炼器连接已停止或游戏进程发生变化。')
        raw=self.game.resolver.resolve()
        if not raw.get('anchor_verified'):
            raise Refused('当前角色身份未核验。')
        rr=self.resolver
        rr.anchors=[(a['address'],a['expected_hex']) for a in raw['anchors']]
        manager,panels=rr.registered_panels()
        rounds=[s for p in panels if (s:=rr.round(p,raw,manager)) is not None]
        if len(rounds)>1:
            raise Refused('存在多个活动炼器面板，不能确定目标。')
        state=rounds[0] if rounds else dict(active=False,can_complete=False,reason='请在游戏中选定器胚与材料，进入活动炼器棋盘后读取。')
        proof=rr.proof()
        if process_identity(rr.reader.h)!=self.game.stamp:
            raise Refused('读取期间游戏进程变化。')
        if state.get('native'):
            state['native']['anchors']=proof
        return state

    def prepare_solve(self, shown):
        if native_calls_pending():
            raise Refused('已有原生请求未完成。')
        fresh=self.snapshot()
        if not fresh.get('can_complete'):
            raise Refused(fresh['reason'])
        if not isinstance(shown,dict) or fresh.get('identity')!=shown.get('identity'):
            raise Refused('炼器局次发生变化，请重新读取。')
        # A player's intervening placement invalidates the shown target even in
        # the same round. We never silently complete a newly changed board.
        for key in ('plan','effects','energy','tiers','placement'):
            if fresh['native'][key]!=shown.get('native',{}).get(key):
                raise Refused('读取后炼器状态发生变化，请刷新。')
        return fresh

    def verify_native(self,outcome,state):
        if (outcome.get('settlement_started') is not True or outcome.get('all_effects_activated') is not True
                or outcome.get('effect_count')!=state['effect_count']
                or outcome.get('tier_id')!=state['highest_tier']):
            raise UncertainWrite('炼器请求已派发，但最高品阶结算未确认；本局禁止重试。')
        return dict(verified=True,phase='settlement_started',settlement_verified=False,
            message='已补齐当前器胚所有词条能量门槛并开始最高品阶结算。词条由游戏按原池生成；请在游戏完成结果页并核对成品。')

    def solve(self,shown):
        try:
            return self.native.solve(shown)
        except UncertainWrite:
            self.blocked=True
            raise

    def close(self):
        self.native.close()
        self.talents.close()
