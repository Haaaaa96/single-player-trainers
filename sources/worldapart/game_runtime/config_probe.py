"""Read only current Luban item configuration through Tables.Current."""
import argparse,json,re,struct,time
from pathlib import Path
import discovery,probe,resolver
from class_scan import scan_classes
from runtime_paths import CACHE_ROOT
HERE=Path(__file__).resolve().parent
CONFIG_NAMES=['LubanDatas.Tables','LubanDatas.TbItem','LubanDatas.TbItemType','LubanDatas.data.Item','LubanDatas.data.ItemType','LubanDatas.L10nText']
# The verified BagModel.IsCurrencyItem
# (Game.dll token 0x060151bd, RVA 0xe9fe00) compares Item.itemType to 5.
CURRENCY_ITEM_TYPE_ID=5

def discover_config(rr):
    r=rr.reader;meta=rr.meta
    # Allocators may place configuration types in a different heap region from
    # GameStoreManager. Use the same bounded current-metadata discovery path.
    specs={name:rr.specs[name] for name in CONFIG_NAMES}
    out,diagnostic=scan_classes(r,meta,specs)
    scanned=diagnostic['read_bytes']
    # Tables has hundreds of unrelated configs; retain only necessary FieldInfo.
    needed={f['name'] for f in rr.specs['LubanDatas.Tables']['fields']}
    out['LubanDatas.Tables']['fields']=[f for f in out['LubanDatas.Tables']['fields'] if f['name'] in needed]
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    (CACHE_ROOT/'config_classes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    return out,scanned

def string(rr,p):
    if not p:return ''
    c=rr.info(rr.q(p),'String','System');n=rr.i(p+16)
    if not 0<=n<=4096:raise resolver.ResolutionError('Unexpected localized string length')
    return rr.exact(p+20,n*2).decode('utf-16-le')

def language_dict(rr,p):
    dc=rr.info(rr.q(p),'Dictionary`2','System.Collections.Generic')
    n=rr.i(p+rr.field(dc,'_count',8))
    if not 0<=n<=16:raise resolver.ResolutionError('Unexpected language dictionary size')
    if not n:return {}
    a=rr.q(p+rr.field(dc,'_entries',0x1d));ac=rr.info(rr.q(a),'Entry[]','')
    ec=rr.info(rr.q(int(ac['klass'],16)+0x40),'Entry','')
    ko=rr.field(ec,'key',0xe)-16;vo=rr.field(ec,'value',0xe)-16;ho=rr.field(ec,'hashCode',8)-16
    stride=ec['instance_size']-16
    if stride!=24 or ko!=8 or vo!=16 or ho!=0:raise resolver.ResolutionError('Unexpected string dictionary entry layout')
    if not n<=rr.q(a+24)<=32:raise resolver.ResolutionError('Unexpected language array capacity')
    out={}
    for i in range(n):
        b=a+32+i*stride
        if rr.i(b+ho)>=0:out[string(rr,rr.q(b+ko))]=string(rr,rr.q(b+vo))
    return out

def localized(rr,obj,c,field,l10nc):
    f=next(f for f in c['fields'] if f['name']==field)
    td=bytes.fromhex(f['type_data'])
    if td[10]!=0x11 or int.from_bytes(td[:8],'little')!=rr.meta+rr.specs['LubanDatas.L10nText']['typeDefinitionFileOffset']:
        raise resolver.ResolutionError('Localized name is not the reviewed L10nText value type')
    # IL2CPP FieldInfo offsets on a value type include its 16-byte boxed header.
    inner=rr.field(l10nc,'<Languages>k__BackingField',0x15)-16
    return language_dict(rr,rr.q(obj+f['offset']+inner))

def list_objects(rr,p,max_count=10000):
    c=rr.info(rr.q(p),'NotifiableList`1','Emei')
    c=rr.info(int(c['parent'],16),'List`1','System.Collections.Generic')
    n=struct.unpack('<i',rr.anchor(p+rr.field(c,'_size',8),4,'configList.size'))[0]
    rr.anchor(p+rr.field(c,'_version',8),4,'configList.version')
    if not 0<=n<=max_count:raise resolver.ResolutionError('Unexpected config list size')
    a=rr.pointer(p+rr.field(c,'_items',0x1d),'configList.items');cap=rr.q(a+24)
    if not n<=cap<=max_count*2:raise resolver.ResolutionError('Unexpected config list capacity')
    data=rr.exact(a+32,n*8) if n else b''
    return list(struct.unpack('<'+'Q'*n,data))

def table_rows(rr,tables,tablesc,table_field,table_full):
    tb=rr.pointer(tables+rr.field(tablesc,table_field,0x12),table_full);tc=rr.object_class(tb,table_full)
    overrides=rr.q(tb+rr.field(tc,'_overrides',0x15))
    override_count=0
    if overrides:
        oc=rr.info(rr.q(overrides),'Dictionary`2','System.Collections.Generic')
        override_count=rr.i(overrides+rr.field(oc,'_count',8))-rr.i(overrides+rr.field(oc,'_freeCount',8))
    if override_count:raise resolver.ResolutionError('Runtime table overrides present; effective-value semantics must be reviewed first')
    return list_objects(rr,rr.pointer(tb+rr.field(tc,'_dataList',0x15),table_full+'._dataList')),tb

def nullable_bool(rr,obj,c,field):
    f=next(f for f in c['fields'] if f['name']==field);td=bytes.fromhex(f['type_data'])
    if td[10]!=0x15:raise resolver.ResolutionError('Expected nullable generic value')
    generic_class=int.from_bytes(td[:8],'little');cached=rr.q(generic_class+24)
    nc=rr.info(cached,'Nullable`1','System')
    has=rr.field(nc,'hasValue',2)-16;val=rr.field(nc,'value',2)-16
    return bool(rr.exact(obj+f['offset']+val,1)[0]) if rr.exact(obj+f['offset']+has,1)[0] else None

def read_config(pid,wanted_ids=None):
    with resolver.Resolver(pid) as rr:
        snapshot=rr.resolve() # establish reviewed active player and root before ancillary config reads
        wanted={item['item_id'] for item in snapshot['items']} if wanted_ids is None else set(wanted_ids)
        if len(wanted)>4096 or any(type(i) is not int or not 0<i<=2147483647 for i in wanted):
            raise resolver.ResolutionError('Invalid requested item IDs')
        path=CACHE_ROOT/'config_classes.json'
        classes=None;scanned=0
        if path.exists():
            try:
                cached=json.loads(path.read_text(encoding='utf8'))
                for name in CONFIG_NAMES:rr.verify_class(int(cached[name]['klass'],16),name)
                classes=cached
            except (resolver.ResolutionError,KeyError,TypeError,ValueError):
                # Cached process addresses never assert identity; rediscover metadata read-only.
                pass
        if classes is None:classes,scanned=discover_config(rr)
        tablek=int(classes['LubanDatas.Tables']['klass'],16);tablesc=rr.verify_class(tablek,'LubanDatas.Tables')
        sf=rr.pointer(tablek+0xb8,'Tables.static_fields')
        tables=rr.pointer(sf+rr.field(tablesc,'Current',0x12,static=True),'Tables.Current')
        if rr.q(tables)!=tablek:raise resolver.ResolutionError('Tables.Current class differs')
        l10nc=rr.verify_class(int(classes['LubanDatas.L10nText']['klass'],16),'LubanDatas.L10nText')
        ic=rr.verify_class(int(classes['LubanDatas.data.Item']['klass'],16),'LubanDatas.data.Item')
        rows,tb=table_rows(rr,tables,tablesc,'<TbItem>k__BackingField','LubanDatas.TbItem')
        items=[]
        for obj in rows:
            if rr.q(obj)!=int(ic['klass'],16):raise resolver.ResolutionError('TbItem contains an unexpected class')
            itemid=rr.i(obj+rr.field(ic,'<id>k__BackingField',0x11))
            if itemid not in wanted:continue
            items.append(dict(id=itemid,config_object=hex(obj),names=localized(rr,obj,ic,'<itemName>k__BackingField',l10nc),
                              item_type_id=rr.i(obj+rr.field(ic,'<itemType>k__BackingField',0x11)),
                              max_count_per_grid=rr.i(obj+rr.field(ic,'<maxCntPerGrid>k__BackingField',8)),
                              can_use=bool(rr.exact(obj+rr.field(ic,'<canUse>k__BackingField',2),1)[0]),
                              can_discard=bool(rr.exact(obj+rr.field(ic,'<canDiscard>k__BackingField',2),1)[0]),
                              auto_use=nullable_bool(rr,obj,ic,'<autoUse>k__BackingField')))
        if {x['id'] for x in items}!=wanted or len(items)!=len(wanted):raise resolver.ResolutionError('Missing or duplicate target item config')
        tc=rr.verify_class(int(classes['LubanDatas.data.ItemType']['klass'],16),'LubanDatas.data.ItemType')
        type_rows,type_tb=table_rows(rr,tables,tablesc,'<TbItemType>k__BackingField','LubanDatas.TbItemType');typemap={}
        for obj in type_rows:
            if rr.q(obj)!=int(tc['klass'],16):raise resolver.ResolutionError('TbItemType unexpected row')
            typeid=rr.i(obj+rr.field(tc,'<id>k__BackingField',0x11))
            if typeid not in {x['item_type_id'] for x in items}:continue
            if typeid in typemap:raise resolver.ResolutionError('Duplicate target item type config')
            typemap[typeid]=dict(type_names=localized(rr,obj,tc,'<typeName>k__BackingField',l10nc),
                                 bag_type_id=rr.i(obj+rr.field(tc,'<bagType>k__BackingField',0x11)),
                                 hide_in_bag=bool(rr.exact(obj+rr.field(tc,'<hideInBag>k__BackingField',2),1)[0]))
        if {x['item_type_id'] for x in items}!=set(typemap):raise resolver.ResolutionError('Missing target item type config')
        for x in items:
            x.update(typemap[x['item_type_id']])
            x['is_currency']=x['item_type_id']==CURRENCY_ITEM_TYPE_ID
            x['currency_classification_source']='BagModel.IsCurrencyItem: Item.itemType == 5 (verified build)'
        for a in rr.anchors:
            if rr.exact(a['address'],a['size']).hex()!=a['expected_hex']:raise resolver.ResolutionError('Root or config collection changed during read: '+a['label'])
        return dict(pid=pid,process_creation_filetime=rr.start_time,captured_unix=time.time(),wanted_ids=sorted(wanted),tables_current=hex(tables),tbitem=hex(tb),tbitemtype=hex(type_tb),config_scan_bytes=scanned,items=items,
                    source='Current runtime Tables.Current -> TbItem._dataList / TbItemType._dataList, no overrides; localized via L10nText.Languages')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    result=read_config(parser.parse_args().pid)
    (HERE/'item_config_verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
