"""Fail-closed, read-only WorldApart resolver. No write/injection/debug APIs.

Requires the separately reviewed metadata handoff and class discovery summaries.
Anchors are followed from Singleton<GameStoreManager>.lazyInstance, never by
selecting the only apparent PlayerModel. All addresses are process-lifetime data.
"""
import ctypes as C
import ctypes.wintypes as W
import json
from pathlib import Path
import struct
import time
import probe
from runtime_metadata import RuntimeSpecs
from runtime_paths import RESOURCE_ROOT, CACHE_ROOT

HERE=Path(__file__).resolve().parent
class ResolutionError(RuntimeError):pass

# Only these metadata-reviewed concrete classes may expose BagItemBase fields.
# A new mod/game type is diagnostic-only until its inheritance is reviewed.
BAG_ITEM_CLASSES = frozenset('Game.Model.Components.' + name for name in (
    'BagItem', 'ArtifactBagItem', 'GambleStoneBagItem', 'GongfaBagItem',
    'NpcBagItem', 'PillBagItem'))
COUNT_EDIT_CLASSES = frozenset(('Game.Model.Components.BagItem', 'Game.Model.Components.PillBagItem'))

probe.K.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME),C.POINTER(W.FILETIME)]
probe.K.GetProcessTimes.restype=W.BOOL

class Resolver:
    def __init__(self,pid,*,expected_path=None):
        reviewed={x['name']:x for x in json.loads((RESOURCE_ROOT/'engine_runtime_handoff.json').read_text(encoding='utf-8-sig'))}
        cd=json.loads((CACHE_ROOT/'classes.json').read_text(encoding='utf8'))
        od=json.loads((CACHE_ROOT/'objects.json').read_text(encoding='utf8'))
        if cd['pid']!=pid or od['pid']!=pid:raise ResolutionError('Discovery belongs to a different PID; rediscover read-only first')
        self.meta=int(cd['metadata_base'],16)
        self.known={x['namespace']+'.'+x['name']:int(x['klass'],16) for x in cd['classes'] if x['validated']}
        managers=od.get('managers',[])
        if len(managers)!=1:raise ResolutionError('No uniquely validated GameStoreManager class discovery')
        self.manager_class=int(managers[0]['klass'],16)
        self.anchors=[]
        self.reader=probe.Reader(pid,expected_path=expected_path)
        try:
            maps=probe.verified_mappings(self.reader)
            if maps['metadata'][0]['base']!=self.meta:
                raise ResolutionError('Discovery metadata belongs to a different game process; rediscover read-only first')
            # Optional types are resolved only for the feature requesting them.
            # The mapping lives only as long as this verified reader; stale disk
            # caches never supply metadata offsets or field tokens.
            self.specs=RuntimeSpecs(self.reader,self.meta,reviewed)
            self.game_path=self.reader.installation.executable_path
            self.install_directory=self.reader.install_directory
            times=[W.FILETIME() for _ in range(4)]
            if not probe.K.GetProcessTimes(self.reader.h,*[C.byref(t) for t in times]):
                raise ResolutionError('Process identity unavailable')
            self.start_time=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime
        except Exception:
            self.reader.close()
            raise
    def close(self):self.reader.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def exact(self,a,n):
        b=self.reader.read(a,n)
        if len(b)!=n:raise ResolutionError(f'Short read at {a:#x} ({n} bytes)')
        return b
    def q(self,a):return struct.unpack('<Q',self.exact(a,8))[0]
    def i(self,a):return struct.unpack('<i',self.exact(a,4))[0]
    def anchor(self,a,n,label):
        b=self.exact(a,n);self.anchors.append(dict(address=a,size=n,expected_hex=b.hex(),label=label));return b
    def pointer(self,a,label):
        v=struct.unpack('<Q',self.anchor(a,8,label))[0]
        if not v or v%8:raise ResolutionError(f'Invalid pointer: {label}')
        return v
    def info(self,k,name=None,namespace=None,*,max_fields=512):
        c=probe.inspect_class(self.reader,k,max_fields=max_fields)
        if c is None or name is not None and c['name']!=name or namespace is not None and c['namespace']!=namespace:
            raise ResolutionError(f'Class mismatch at {k:#x}: expected {namespace}.{name}')
        for f in c['fields']:
            if int(f['parent'],16)!=k or len(bytes.fromhex(f['type_data']))!=16:raise ResolutionError('Malformed FieldInfo')
        return c
    def verify_class(self,k,full):
        ns,_,name=full.rpartition('.');spec=self.specs.get(full)
        if spec is None:raise ResolutionError('Missing static metadata specification: '+full)
        c=self.info(k,name,ns,max_fields=max(512,spec['fieldCount']))
        if spec.get('image_name') and self.reader.string(self.q(self.q(k)))!=spec['image_name']:
            raise ResolutionError('Class image mismatch: '+full)
        if self.q(k+0x68)!=self.meta+spec['typeDefinitionFileOffset']:raise ResolutionError('Class metadata handle differs from reviewed type')
        if struct.unpack('<I',self.exact(k+0x11c,4))[0]!=int(spec['token'],16):raise ResolutionError('Class token mismatch')
        if len(c['fields'])!=spec['fieldCount']:raise ResolutionError('Field count mismatch')
        actual={f['name']:f for f in c['fields']}
        for f in spec['fields']:
            af=actual.get(f['name'])
            if not af or af['token']!=f['token']:raise ResolutionError('Static/runtime field mismatch: '+f['name'])
        return c
    def field(self,c,name,kind=None,static=False):
        fs=[f for f in c['fields'] if f['name']==name]
        if len(fs)!=1:raise ResolutionError('Missing or ambiguous field: '+name)
        f=fs[0];tb=bytes.fromhex(f['type_data']);attrs=int.from_bytes(tb[8:10],'little')
        if bool(attrs&0x10)!=static or attrs&0x40:raise ResolutionError('Unexpected static/literal field: '+name)
        if kind is not None and tb[10]!=kind:raise ResolutionError('Unexpected field type: '+name)
        if f['offset']<0 or not static and not 16<=f['offset']<c['instance_size']:raise ResolutionError('Invalid field offset')
        return f['offset']
    def object_class(self,obj,full):
        k=self.pointer(obj,full+'.klass')
        return self.verify_class(k,full)
    def find_inherited_field(self,k,name,depth=8):
        for _ in range(depth):
            c=self.info(k)
            if any(f['name']==name for f in c['fields']):return c,self.field(c,name)
            k=int(c['parent'],16)
            if not k:break
        raise ResolutionError('Inherited field unavailable: '+name)
    def point_balance(self,talent,tc,field_name):
        # Both balances are Int32 on the same verified player component. Keep
        # the read bound wider than the trainer's editing policy so a high
        # existing value can still be displayed without silently clamping it.
        address=talent+self.field(tc,field_name,8)
        value=self.i(address)
        if not 0<=value<=1000000:raise ResolutionError('Talent points outside supported read range: '+field_name)
        return address,value
    def inventory_entries(self,arr,n,base_class):
        """Read reviewed polymorphic entries; unsupported entries never become targets.

        The game's GetItemCount also skips null list elements. Pin even skipped
        slots so a concurrent replacement cannot silently change the snapshot.
        """
        ibk=int(base_class['klass'],16)
        offsets={name:self.field(base_class,name,kind) for name,kind in
                 [('Count',8),('ItemId',0x11),('Uid',0x0a),('IsEquipped',2)]}
        items=[];diagnostics=[];uids={};duplicates=set();classes={}
        for i in range(n):
            label=f'Items[{i}]';obj=struct.unpack('<Q',self.anchor(arr+32+i*8,8,label))[0]
            if not obj:
                diagnostics.append(dict(slot=i,reason='null_entry',message='空背包槽已跳过。'))
                continue
            full=None
            try:
                if obj%8:raise ResolutionError('Unaligned inventory object')
                klass=self.pointer(obj,label+'.klass')
                if klass not in classes:
                    c=self.info(klass);full=c['namespace']+'.'+c['name']
                    if full not in BAG_ITEM_CLASSES:raise ResolutionError('Unreviewed inventory class: '+full)
                    c=self.verify_class(klass,full)
                    # PillBagItem inherits BagItem; other specializations may
                    # inherit BagItemBase directly. Verify every intermediate.
                    parent=klass;seen=set()
                    for depth in range(4):
                        if parent in seen:raise ResolutionError('Cyclic inventory inheritance')
                        seen.add(parent)
                        parent=self.pointer(parent+0x58,full+f'.parent[{depth}]')
                        if parent==ibk:break
                        pc=self.info(parent);pfull=pc['namespace']+'.'+pc['name']
                        if pfull not in BAG_ITEM_CLASSES:raise ResolutionError('Unreviewed inventory ancestor: '+pfull)
                        self.verify_class(parent,pfull)
                    else:raise ResolutionError('Reviewed BagItemBase ancestor not found')
                    if any(off+size>c['instance_size'] for off,size in
                           [(offsets['Count'],4),(offsets['ItemId'],4),(offsets['Uid'],8)]):
                        raise ResolutionError('Inventory object is too small for reviewed base fields')
                    classes[klass]=(full,c)
                full,c=classes[klass]
                item_id=struct.unpack('<i',self.anchor(obj+offsets['ItemId'],4,label+'.ItemId'))[0]
                uid=struct.unpack('<q',self.anchor(obj+offsets['Uid'],8,label+'.Uid'))[0]
                count=self.i(obj+offsets['Count'])
                equipped=bool(self.anchor(obj+offsets['IsEquipped'],1,label+'.IsEquipped')[0])
                if full=='Game.Model.Components.PillBagItem':
                    # Preserve the crafted pill's own recipe/grade/effect fields;
                    # game stacking and consumption change only base.Count.
                    start=base_class['instance_size'];size=c['instance_size']-start
                    self.anchor(obj+start,size,label+'.pill_identity_fields')
                if uid<=0 or item_id<=0 or not 0<=count<=2147483647:
                    raise ResolutionError('Invalid inventory identity/count')
                if uid in uids:duplicates.add(uid)
                uids[uid]=i
                items.append(dict(slot=i,object=obj,address=obj,count_address=obj+offsets['Count'],
                                  klass=klass,class_name=full,item_id=item_id,uid=uid,count=count,
                                  size=4,type='Int32',is_equipped=equipped,
                                  count_editable=full in COUNT_EDIT_CLASSES and not equipped))
            except ResolutionError as exc:
                diagnostics.append(dict(slot=i,object=obj,class_name=full,reason='unsupported_entry',message=str(exc)))
        if duplicates:
            for item in items:
                if item['uid'] in duplicates:
                    diagnostics.append(dict(slot=item['slot'],uid=item['uid'],reason='duplicate_uid',
                                            message='物品唯一编号重复，该条目禁止编辑。'))
            items=[item for item in items if item['uid'] not in duplicates]
        return items,diagnostics
    def roots(self,talent,tc):
        d=self.pointer(talent+self.field(tc,'<SpiritRootPoints>k__BackingField',0x15),'talent.spiritRoots')
        dc=self.info(self.q(d),'Dictionary`2','System.Collections.Generic')
        count=self.i(d+self.field(dc,'_count',8));free=self.i(d+self.field(dc,'_freeCount',8))
        if not 0<=free<=count<=32:raise ResolutionError('Invalid spirit dictionary bounds')
        if not count:return []
        a=self.pointer(d+self.field(dc,'_entries',0x1d),'spiritRoots.entries')
        ac=self.info(self.q(a),'Entry[]','');ec=self.info(self.q(int(ac['klass'],16)+0x40),'Entry','')
        offsets=[self.field(ec,n,8)-16 for n in ['hashCode','next','key','value']]
        if offsets!=[0,4,8,12] or ec['instance_size']!=32:raise ResolutionError('Unexpected dictionary Entry layout')
        cap=self.q(a+24)
        if not count<=cap<=64:raise ResolutionError('Invalid entry array capacity')
        vals=[]
        for i in range(count):
            h,n,key,val=struct.unpack('<iiii',self.exact(a+32+i*16,16))
            if h>=0:vals.append(dict(element_id=key,points=val))
        return vals
    def resolve(self):
        self.anchors=[]
        if self.exact(self.meta,8)!=struct.pack('<II',0xfab11baf,31):raise ResolutionError('Metadata version/mapping changed')
        mc=self.verify_class(self.manager_class,'Game.Model.GameStoreManager')
        sk=self.pointer(self.manager_class+0x58,'GameStoreManager.parent');sc=self.info(sk,'Singleton`1','Game')
        sf=self.pointer(sk+0xb8,'Singleton.static_fields')
        lazy=self.pointer(sf+self.field(sc,'lazyInstance',0x15,static=True),'Singleton.lazyInstance')
        lc=self.info(self.pointer(lazy,'Lazy.klass'),'Lazy`1','System')
        state_offset=self.field(lc,'_state',0x12)
        if self.anchor(lazy+state_offset,8,'Lazy._state')!=bytes(8):raise ResolutionError('Singleton Lazy is not fully initialized; refusing to execute initialization')
        manager=self.pointer(lazy+self.field(lc,'_value',0x12),'Lazy._value')
        if self.pointer(manager,'manager.klass')!=self.manager_class:raise ResolutionError('Lazy value is not GameStoreManager')
        store=self.pointer(manager+self.field(mc,'_gameStore',0x12),'manager._gameStore');storec=self.object_class(store,'Game.Model.GameStore')
        basec,off=self.find_inherited_field(int(storec['klass'],16),'_gameWorld')
        if basec['name']!='BaseStore' or basec['namespace']!='SimpleSave':raise ResolutionError('Unexpected store owner of _gameWorld')
        world=self.pointer(store+off,'store._gameWorld');wc=self.object_class(world,'Game.Model.GameWorldModel')
        player=self.pointer(world+self.field(wc,'<PlayerModel>k__BackingField',0x12),'world.PlayerModel');pc=self.object_class(player,'Game.Model.PlayerModel')
        bag=self.pointer(player+self.field(pc,'bag',0x12),'player.bag');bc=self.object_class(bag,'Game.Model.Components.BagModel')
        talent=self.pointer(player+self.field(pc,'talentPath',0x12),'player.talentPath');tc=self.object_class(talent,'Game.Model.Player.Components.TalentPathModel')
        # Both component owners have been independently observed and must retain the same PlayerModel.
        if self.pointer(bag+16,'bag.owner')!=player or self.pointer(talent+16,'talent.owner')!=player:raise ResolutionError('Component owner is not current player')
        spirit_addr,spirit=self.point_balance(talent,tc,'<SpiritPointRemain>k__BackingField')
        path_addr,path=self.point_balance(talent,tc,'<PathPoints>k__BackingField')
        lst=self.pointer(bag+self.field(bc,'<Items>k__BackingField',0x15),'bag.Items')
        listc=self.info(self.pointer(lst,'Items.klass'),'List`1','System.Collections.Generic')
        n=struct.unpack('<i',self.anchor(lst+self.field(listc,'_size',8),4,'Items._size'))[0]
        self.anchor(lst+self.field(listc,'_version',8),4,'Items._version')
        if not 0<=n<=4096:raise ResolutionError('Unsupported inventory size')
        arr=self.pointer(lst+self.field(listc,'_items',0x1d),'Items._items');ac=self.info(self.pointer(arr,'Items.array.klass'),'BagItemBase[]','Game.Model.Components')
        ibk=self.pointer(int(ac['klass'],16)+0x40,'Items.array.element_class');ibc=self.verify_class(ibk,'Game.Model.Components.BagItemBase')
        cap=struct.unpack('<Q',self.anchor(arr+24,8,'Items.array.capacity'))[0]
        if not n<=cap<=8192:raise ResolutionError('Unsupported inventory capacity')
        items,diagnostics=self.inventory_entries(arr,n,ibc)
        rootvals=self.roots(talent,tc)
        for anchor in self.anchors:
            if self.exact(anchor['address'],anchor['size']).hex()!=anchor['expected_hex']:raise ResolutionError('Anchor changed during snapshot: '+anchor['label'])
        return dict(pid=self.reader.pid,process_path=self.reader.path,process_creation_filetime=self.start_time,
                    anchor_verified=True,anchor_route='Singleton<GameStoreManager>.lazyInstance._value -> _gameStore -> _gameWorld -> PlayerModel',
                    current_player=player,player=player,manager=manager,store=store,world=world,bag=bag,talent=talent,
                    spirit=spirit,spirit_address=spirit_addr,spirit_target=dict(address=spirit_addr,value=spirit,size=4,type='Int32'),spirit_roots=rootvals,items=items,
                    path=path,path_address=path_addr,path_target=dict(address=path_addr,value=path,size=4,type='Int32'),
                    diagnostics=diagnostics,anchors=self.anchors,captured_unix=time.time())

def resolve_current(pid):
    with Resolver(pid) as resolver:return resolver.resolve()

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);args=ap.parse_args()
    result=resolve_current(args.pid)
    (HERE/'resolved.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='anchors'},ensure_ascii=False,indent=2))
