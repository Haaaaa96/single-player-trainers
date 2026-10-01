/* Merged into acquisition_bridge.js. These declarations never attach a second
 * agent: execute() dispatches them on the existing A1Main.Update hook. */
const INTERACTION_METHODS = {
    requirements: nativeSpec({name:'MeetsSpecialEntryRequirements',token:0x06008258,rva:0x1552590,argc:3,
        returns:2,params:[0x12,0x12,2],static:true,prefix:'4053565741564881eca8000000450fb6'}),
    activate: nativeSpec({name:'SetSpecialState',token:0x06008249,rva:0x1555670,argc:3,
        returns:2,params:[0x12,8,2],static:true,prefix:'48895c24084889742410574883ec2041'}),
    force: nativeSpec({name:'ForceSetSpecialState',token:0x0600823d,rva:0x1550ef0,argc:2,
        returns:2,params:[0x11,0x11],static:false,prefix:'48895c2410574883ec30803dd2b7ff06'}),
    persuade: nativeSpec({name:'OnPersuadeResult',token:0x060143ff,rva:0xe1bef0,argc:2,
        returns:1,params:[2,0x11],static:false,prefix:'40535556574883ec28803d9ad4720700'}),
    ended: nativeSpec({name:'OnPersuadeEnded',token:0x0600aec9,rva:0x18df690,argc:2,returns:1,params:[2,0x0e],static:false,prefix:'4889742420574881ecc0000000803da5'}),
    win: nativeSpec({name:'<RunAsync>b__3',token:0x0600ba4c,rva:0x19c90c0,argc:0,returns:1,params:[],static:false,prefix:'48895c24084889742410574883ec2080'}),
    lose: nativeSpec({name:'<RunAsync>b__4',token:0x0600ba4d,rva:0x19c9150,argc:0,returns:1,params:[],static:false,prefix:'48895c24084889742410574883ec2080'}),
    close: nativeSpec({name:'<RunAsync>b__5',token:0x0600ba4e,rva:0x19c8e20,argc:0,returns:1,params:[],static:false,prefix:'4883ec2880791000751a66c741100100'}),
    alive: nativeSpec({name:'<RunAsync>b__6',token:0x0600ba4f,rva:0x19c91e0,argc:0,returns:2,params:[],static:false,prefix:'40534883ec20803d1557b80600488bd9'})
};
function interactionInteger(value,minimum=0,maximum=2147483647) {
    requireValue(Number.isInteger(value)&&value>=minimum&&value<=maximum,'Invalid interaction integer');
    return value;
}
function interactionField(object,klass,name,token,kind,offset,size,proof=true) {
    const fields=klass.add(0x80).readPointer(),count=klass.add(0x124).readU16(),found=[];
    requireValue(!fields.isNull()&&count>0&&count<=512,'Interaction field table invalid');
    for(let i=0;i<count;i++) {
        const field=fields.add(32*i);
        if(field.readPointer().readUtf8String()!==name) continue;
        const type=field.add(8).readPointer();
        samePointer(field.add(16).readPointer(),klass,'Interaction field owner differs');
        requireValue(field.add(28).readU32()===reviewedFieldToken(klass,token,name)&&field.add(24).readS32()===offset&&
            !type.isNull()&&type.add(10).readU8()===kind&&(type.add(11).readU8()&0x7f)===0&&
            (type.add(8).readU16()&0x50)===0&&offset>=16&&offset+size<=klass.add(0xf8).readU32(),
            'Interaction field layout differs: '+klass.add(24).readPointer().readUtf8String()+'.'+
            klass.add(16).readPointer().readUtf8String()+'.'+name);
        found.push(ptr(object).add(offset));
    }
    requireValue(found.length===1,'Interaction field missing or ambiguous');
    if(proof) requireCoverage(found[0],size);
    return found[0];
}
function interactionClass(klass,namespace,name) {
    requireValue(!klass.isNull()&&klass.add(16).readPointer().readUtf8String()===name&&
        klass.add(24).readPointer().readUtf8String()===namespace,'Interaction metadata class differs');
    return klass;
}
function interactionFieldClass(klass,name,namespace,typeName,size) {
    const table=klass.add(0x80).readPointer(),count=klass.add(0x124).readU16();
    requireValue(!table.isNull()&&count>0&&count<=512,'Interaction field metadata missing');
    const matches=[];
    for(let i=0;i<count;i++)if(table.add(i*32).readPointer().readUtf8String()===name)
        matches.push(classFromType(table.add(i*32+8).readPointer()));
    requireValue(matches.length===1,'Interaction value wrapper field ambiguous');
    const c=interactionClass(matches[0],namespace,typeName);
    requireValue(c.add(0xf8).readU32()===size,'Interaction value wrapper size differs');return c;
}
function interactionMethod(address,klass,spec) {
    const method=ptr(address);
    samePointer(method.readPointer(),image.base.add(spec.rva),'Interaction native address differs');
    samePointer(method.add(0x20).readPointer(),klass,'Interaction native owner differs');
    requireValue(methodToken(method)===spec.token&&paramCount(method)===spec.argc&&
        method.add(0x18).readPointer().readUtf8String()===spec.name&&
        Boolean(method.add(0x4c).readU16()&0x10)===spec.static&&
        hexAt(image.base.add(spec.rva),spec.prefix.length/2)===spec.prefix,'Interaction native signature differs');
    function typeKind(type,kind) {
        requireValue(!type.isNull()&&type.add(10).readU8()===kind&&
            (type.add(11).readU8()&0x7f)===0,'Interaction argument or return type differs');
    }
    typeKind(method.add(0x28).readPointer(),spec.returns);
    for(let i=0;i<spec.params.length;i++) typeKind(methodParam(method,i),spec.params[i]);
    return method;
}
function interactionArgumentClass(method,index,namespace,name,size=null) {
    const klass=classFromType(methodParam(method,index));
    requireValue(!klass.isNull()&&klass.add(16).readPointer().readUtf8String()===name&&
        klass.add(24).readPointer().readUtf8String()===namespace&&
        (size===null||klass.add(0xf8).readU32()===size),'Interaction parameter class differs');
}
function interactionInvoke(method,target,values) {
    const args=values.length?Memory.alloc(values.length*8):ptr(0),exception=Memory.alloc(8);
    values.forEach((value,index)=>args.add(index*8).writePointer(value));
    exception.writePointer(ptr(0));
    const result=invoke(method,target,args,exception);
    requireValue(exception.readPointer().isNull(),'Interaction native exception; never retry');
    return result;
}
function interactionBoolean(result) {
    requireValue(!result.isNull(),'Interaction method returned no Boolean');
    className(result,'System','Boolean');
    return boolAt(result.add(16));
}
function interactionScalar(value,boolean=false) {
    const result=Memory.alloc(boolean?1:4);
    if(boolean) result.writeU8(value?1:0); else result.writeS32(interactionInteger(value));
    return result;
}
function interactionLinks(links,proof=true) {
    requireValue(Array.isArray(links)&&links.length>0&&links.length<=20000,'Interaction owner chain missing');
    for(const link of links) {
        if(proof) requireCoverage(link.address,8);
        samePointer(ptr(link.address).readPointer(),link.expected,'Interaction owner chain changed');
    }
}
const usedInteractionRounds=new Set();
function interactionRound(m) {
    requireValue(m&&/^[a-f0-9]{64}$/.test(m.round_key),'Interaction round identity missing');
    requireValue(!usedInteractionRounds.has(m.round_key),'Interaction round was already dispatched; never retry');
}
function interactionDispatch(m) {
    requireValue(Date.now()<=request.deadline,'Interaction request expired before dispatch');
    interactionRound(m);
    // Retained across RPC reset: a fresh token never authorizes the same action.
    usedInteractionRounds.add(m.round_key);
    state='running';
}
function interactionStatistics(address,proof) {
    const dictionary=ptr(address),klass=className(dictionary,'System.Collections.Generic','Dictionary`2');
    for(const [offset,size] of [[0x18,8],[0x20,4],[0x24,4],[0x28,4],[0x2c,4]])
        if(proof) requireCoverage(dictionary.add(offset),size);
    const array=dictionary.add(0x18).readPointer(),count=dictionary.add(0x20).readS32(),
        free=dictionary.add(0x28).readS32(),version=dictionary.add(0x2c).readS32(),
        freeList=dictionary.add(0x24).readS32();
    requireValue(count>=0&&count<=4096&&free>=0&&free<=count&&freeList>=-1&&freeList<Math.max(1,count),
        'Interaction statistics bounds invalid');
    const result={dictionary,array,count,free,version,freeList,capacity:0,items:new Map(),slots:new Map()};
    if(array.isNull()){requireValue(count===0&&free===0,'Interaction statistics missing entries');return result;}
    if(proof) requireCoverage(array.add(24),8);
    result.capacity=array.add(24).readU64().toNumber();
    requireValue(count<=result.capacity&&result.capacity<=8192,'Interaction statistics capacity invalid');
    const ac=className(array,'','Entry[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===32,'Interaction statistics entry size differs');
    // Entry field metadata is independently checked even when the dictionary is empty.
    for(const [name,token,offset] of [['hashCode',0x04001b0d,16],['next',0x04001b0e,20],['key',0x04001b0f,24],['value',0x04001b10,28]])
        interactionField(array.add(16),ec,name,token,name==='key'?0x11:8,offset,4,proof&&count>0);
    const keyClass=interactionFieldClass(ec,'key','LubanDatas','TbNpcInteractGameEntrySubid',20);
    interactionField(ptr(0),keyClass,'<Value>k__BackingField',0x04000bea,8,16,4,false);
    let live=0,dead=0;
    for(let i=0;i<count;i++) {
        const p=array.add(32+i*16);if(proof)requireCoverage(p,16);
        const hash=p.readS32(),next=p.add(4).readS32();
        requireValue(next>=-1&&next<Math.max(1,count),'Interaction statistics chain invalid');
        if(hash<0){dead++;continue;}
        const key=interactionInteger(p.add(8).readS32(),1),value=interactionInteger(p.add(12).readS32());
        requireValue(!result.items.has(key),'Interaction statistics duplicate key');
        result.items.set(key,value);result.slots.set(key,{index:i,address:p});live++;
    }
    requireValue(live===count-free&&dead===free,'Interaction statistics free count differs');
    return result;
}
function interactionExpectedStatistics(actual,expected) {
    requireValue(Array.isArray(expected)&&actual.items.size===expected.length,'Interaction statistics changed');
    const keys=new Set();
    for(const item of expected) {
        interactionInteger(item.key,1);interactionInteger(item.value);
        requireValue(!keys.has(item.key)&&actual.items.get(item.key)===item.value,'Interaction statistics changed');
        keys.add(item.key);
    }
}
function interactionStableAnchors(anchors) {
    requireValue(Array.isArray(anchors)&&anchors.length>0&&anchors.length<=20000,'Interaction post-call proof missing');
    for(const a of anchors) {
        requireValue(Number.isInteger(a.size)&&a.size>0&&a.size<=4096&&typeof a.expected_hex==='string'&&
            a.expected_hex.length===a.size*2,'Interaction post-call proof malformed');
        requireCoverage(a.address,a.size);
        requireValue(hexAt(a.address,a.size)===a.expected_hex,'Interaction protected state changed; never retry');
    }
}
function interactionUuid(address,proof) {
    const p=ptr(address);className(p,'System','String');
    if(proof)requireCoverage(p.add(16),4);
    const n=p.add(16).readS32();
    requireValue(n>0&&n<=128,'Interaction UUID length invalid');
    if(proof)requireCoverage(p.add(20),n*2);
    return p.add(20).readUtf16String(n);
}
function interactionConcurrent(d,proof=true) {
    requireValue(d&&d.kind==='concurrent'&&['npc','static'].includes(d.flavor),'Interaction concurrent map descriptor missing');
    const p=ptr(d.address),c=className(p,'System.Collections.Concurrent','ConcurrentDictionary`2');
    samePointer(interactionField(p,c,'_tables',0x04001acb,0x15,16,8,proof).readPointer(),d.tables,'Interaction concurrent tables changed');
    const tables=ptr(d.tables),tc=className(tables,'','Tables');
    for(const [name,token,offset,expected] of [['_buckets',0x04001ad5,16,d.buckets],['_locks',0x04001ad6,24,d.locks],['_countPerLock',0x04001ad7,32,d.count_per_lock]])
        samePointer(interactionField(tables,tc,name,token,0x1d,offset,8,proof).readPointer(),expected,'Interaction concurrent array changed');
    const buckets=ptr(d.buckets),locks=ptr(d.locks),counts=ptr(d.count_per_lock);
    className(buckets,'','Node[]');className(locks,'System','Object[]');className(counts,'System','Int32[]');
    for(const a of [buckets,locks,counts])if(proof)requireCoverage(a.add(24),8);
    const bn=buckets.add(24).readU64().toNumber(),ln=locks.add(24).readU64().toNumber();
    requireValue(bn===d.bucket_count&&bn>0&&bn<=65536&&ln===d.lock_count&&ln>0&&ln<=4096&&ln<=bn&&
        counts.add(24).readU64().toNumber()===ln,'Interaction concurrent capacity invalid');
    let expectedCount=0;const perLock=[],observedLocks=Array(ln).fill(0);
    for(let i=0;i<ln;i++) {if(proof)requireCoverage(counts.add(32+i*4),4);const n=interactionInteger(counts.add(32+i*4).readS32(),0,32768);perLock.push(n);expectedCount+=n;}
    requireValue(expectedCount===d.count&&expectedCount<=32768&&Array.isArray(d.items)&&d.items.length===expectedCount,'Interaction concurrent count changed');
    const supplied=new Map(),seen=new Set(),keys=new Set(),items=[];
    for(const row of d.items){requireValue(!supplied.has(row.node),'Interaction duplicate node descriptor');supplied.set(row.node,row);}
    const nodeClass=buckets.readPointer().add(0x40).readPointer();
    requireValue(!nodeClass.isNull()&&nodeClass.add(0xf8).readU32()===48,'Interaction concurrent node size differs');
    const uuidClass=interactionFieldClass(nodeClass,d.flavor==='npc'?'_key':'_value','SimpleSave','EntityID',24);
    interactionField(ptr(0),uuidClass,'Id',0x04000036,0x0e,16,8,false);
    if(d.flavor==='static') {
        const idClass=interactionFieldClass(nodeClass,'_key','LubanDatas','TbNpcBaseCfgId',20);
        interactionField(ptr(0),idClass,'<Value>k__BackingField',0x04000b8c,8,16,4,false);
    }
    for(let i=0;i<bn;i++) {
        if(proof)requireCoverage(buckets.add(32+i*8),8);
        let node=buckets.add(32+i*8).readPointer();
        while(!node.isNull()) {
            requireValue(!seen.has(node.toString())&&seen.size<32768,'Interaction concurrent cycle or duplicate node');seen.add(node.toString());
            const row=supplied.get(node.toString());requireValue(row&&row.bucket===i,'Interaction concurrent node changed');
            const nc=className(node,'','Node');samePointer(nc,nodeClass,'Interaction concurrent node class differs');
            const key=interactionField(node,nc,'_key',0x04001ad8,0x11,16,d.flavor==='npc'?8:4,proof);
            const value=interactionField(node,nc,'_value',0x04001ad9,d.flavor==='npc'?0x12:0x11,24,8,proof);
            const next=interactionField(node,nc,'_next',0x04001ada,0x15,32,8,proof).readPointer();
            const hash=interactionField(node,nc,'_hashcode',0x04001adb,8,40,4,proof).readS32();
            requireValue((hash&0x7fffffff)%bn===i&&row.hashcode===hash,'Interaction concurrent hash differs');
            samePointer(next,row.next,'Interaction concurrent chain changed');
            const k=d.flavor==='npc'?interactionUuid(key.readPointer(),proof):interactionInteger(key.readS32(),1);
            const v=d.flavor==='npc'?value.readPointer().toString():interactionUuid(value.readPointer(),proof);
            requireValue(k===row.key&&v===row.value&&!keys.has(k),'Interaction concurrent key or value changed');keys.add(k);
            if(d.flavor==='npc')samePointer(key.readPointer(),row.key_pointer,'Interaction UUID key pointer changed');
            else samePointer(value.readPointer(),row.value_pointer,'Interaction UUID value pointer changed');
            items.push({key:k,value:v,node:node.toString()});observedLocks[i%ln]++;node=next;
        }
    }
    requireValue(seen.size===expectedCount&&observedLocks.every((n,i)=>n===perLock[i]),'Interaction concurrent member count differs');
    return items;
}
function interactionPhotoQuests(m,proof=true) {
    const manager=ptr(m.logic_manager),lc=className(manager,'Game','NpcLogicManager'),d=m.quest_owners;
    requireValue(d&&d.kind==='hashset','Photostone quest owner set missing');
    samePointer(interactionField(manager,lc,'_questSpecialStateOwners',0x040036e6,0x15,32,8,proof).readPointer(),d.address,'Photostone quest owners replaced');
    requireValue(!boolAt(interactionField(manager,lc,'_isExecutingNpcInteractAction',0x040036e9,2,0x2d,1,proof)),'Photostone interaction already executing');
    const set=ptr(d.address),sc=className(set,'System.Collections.Generic','HashSet`1');
    for(const [name,token,kind,offset,size,key] of [['_buckets',0x040004da,0x1d,16,8,'buckets'],['_slots',0x040004db,0x1d,24,8,'slots'],
        ['_count',0x040004dc,8,32,4,'count'],['_lastIndex',0x040004dd,8,36,4,'last_index'],['_freeList',0x040004de,8,40,4,'free_list'],['_version',0x040004e0,8,56,4,'version']]) {
        const at=interactionField(set,sc,name,token,kind,offset,size,proof);
        if(size===8)samePointer(at.readPointer(),d[key],'Photostone quest collection changed');else requireValue(at.readS32()===d[key],'Photostone quest collection changed');
    }
    requireValue(d.count>=0&&d.count<=d.last_index&&d.last_index<=4096&&d.free_list>=-1&&d.free_list<Math.max(1,d.last_index)&&
        Array.isArray(d.items)&&d.items.length===d.count,'Photostone quest set bounds invalid');
    const slots=ptr(d.slots),buckets=ptr(d.buckets);
    if(slots.isNull()){requireValue(d.count===0&&d.last_index===0&&buckets.isNull(),'Photostone quest set uninitialized');return;}
    const ac=className(slots,'','Slot[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===36,'Photostone quest slot size differs');
    for(const [name,token,kind,offset,size] of [['hashCode',0x040004e4,8,16,4],['next',0x040004e5,8,20,4],['value',0x040004e6,0x11,24,12]])
        interactionField(ptr(0),ec,name,token,kind,offset,size,false);
    const oc=interactionFieldClass(ec,'value','','QuestSpecialStateOwner',28);
    for(const [i,name]of ['QuestId','NpcId','SubId'].entries())interactionField(ptr(0),oc,name,0x040036f2+i,0x11,16+i*4,4,false);
    if(proof)requireCoverage(slots.add(24),8);
    requireValue(slots.add(24).readU64().toNumber()===d.capacity&&d.capacity>=d.last_index&&d.capacity<=8192,'Photostone quest capacity changed');
    className(buckets,'System','Int32[]');
    const rows=new Map(d.items.map(x=>[x.slot,x]));requireValue(rows.size===d.count,'Photostone duplicate quest slots');let live=0;
    for(let i=0;i<d.last_index;i++) {
        const p=slots.add(32+i*20);if(proof)requireCoverage(p,20);const hash=p.readS32(),next=p.add(4).readS32();
        requireValue(next>=-1&&next<Math.max(1,d.last_index),'Photostone quest slot chain invalid');
        if(hash<0)continue;live++;const r=rows.get(p.toString());
        requireValue(r&&p.add(8).readS32()===r.quest_id&&p.add(12).readS32()===r.npc_id&&p.add(16).readS32()===r.sub_id&&
            r.quest_id>0&&r.npc_id>0&&r.sub_id>0,'Photostone quest slot changed');
        requireValue(r.npc_id!==m.npc_id,'Photostone NPC special entry reserved by a quest');
    }
    requireValue(live===d.count,'Photostone quest live count differs');
}
function interactionPhotoUsage(m,proof=true) {
    const s=m.usage_state,d=s&&s.dictionary,p=ptr(m.usage);
    requireValue(d&&Array.isArray(s.records)&&Array.isArray(d.items),'Photostone usage proof missing');
    samePointer(d.address,p,'Photostone usage descriptor disconnected');className(p,'System.Collections.Generic','Dictionary`2');
    for(const [o,size]of [[24,8],[32,4],[40,4],[44,4]])if(proof)requireCoverage(p.add(o),size);
    const entries=p.add(24).readPointer(),count=p.add(32).readS32(),free=p.add(40).readS32();
    samePointer(entries,d.entries,'Photostone usage entries changed');
    requireValue(count===d.count&&free===d.free&&p.add(44).readS32()===d.version&&count>=0&&count<=1024&&free>=0&&free<=count&&
        d.items.length===count-free&&s.records.length===count-free,'Photostone usage collection changed');
    if(entries.isNull()){requireValue(count===0&&free===0,'Photostone usage collection uninitialized');return;}
    const ac=className(entries,'','Entry[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===40&&d.stride===24,'Photostone usage entry size differs');
    for(const [name,token,kind,offset,size]of [['hashCode',0x04001b0d,8,16,4],['next',0x04001b0e,8,20,4],['key',0x04001b0f,8,24,4],['value',0x04001b10,0x12,32,8]])
        interactionField(ptr(0),ec,name,token,kind,offset,size,false);
    if(proof)requireCoverage(entries.add(24),8);
    requireValue(entries.add(24).readU64().toNumber()===d.capacity&&d.capacity>=count&&d.capacity<=2064,'Photostone usage capacity changed');
    const rows=new Map(d.items.map(x=>[x.entry,x])),records=new Map(s.records.map(x=>[x.action_id,x]));
    requireValue(rows.size===d.items.length&&records.size===s.records.length,'Photostone duplicate usage descriptor');let live=0;
    for(let i=0;i<count;i++) {
        const e=entries.add(32+i*24);if(proof)requireCoverage(e,24);if(e.readS32()<0)continue;live++;
        const action=e.add(8).readS32(),record=e.add(16).readPointer(),wire=rows.get(e.toString()),r=records.get(action);
        requireValue(action>0&&wire&&r&&wire.key===action&&r.used_count>=0&&Number.isInteger(r.used_count),'Photostone usage identity changed');
        samePointer(record,wire.value,'Photostone usage object changed');samePointer(record,r.record,'Photostone usage record changed');
        const rc=className(record,'Game.Model','NpcInteractionActionUsageRecord');
        requireValue(interactionField(record,rc,'<UsedCount>k__BackingField',0x0400a8b6,8,16,4,proof).readS32()===r.used_count,'Photostone usage count changed');
        const cycle=interactionField(record,rc,'<CycleKey>k__BackingField',0x0400a8b7,0x0a,24,8,proof);
        requireValue(Number.isSafeInteger(r.cycle_key)&&cycle.readS64().toString()===String(r.cycle_key),'Photostone usage cycle changed');
    }
    requireValue(live===count-free,'Photostone usage live count differs');
}
function interactionWorldNpc(world,npc,npcId,d,proof=true) {
    const wc=className(world,'Game.Model','GameWorldModel');
    samePointer(interactionField(world,wc,'<NpcModels>k__BackingField',0x0400a7ea,0x15,0x38,8,proof).readPointer(),d.address,'Interaction canonical NPC map changed');
    requireValue(d.flavor==='npc','Interaction NPC map flavor differs');
    const members=interactionConcurrent(d,proof),matches=members.filter(x=>ptr(x.value).equals(ptr(npc)));
    requireValue(matches.length===1,'Interaction NPC is not a unique world member');
    return matches[0];
}
function interactionPhotoOwner(m,proof) {
    const npc=ptr(m.npc),world=ptr(m.world),runtime=ptr(m.runtime);
    const nc=className(npc,'Game.Model','NpcModel'),wc=className(world,'Game.Model','GameWorldModel'),
        rc=className(runtime,'Game.Model','NpcInteractionRuntimeState');
    className(m.player,'Game.Model','PlayerModel');
    interactionLinks(m.owner_links,proof);
    const f=(o,c,name,token,kind,offset,size)=>interactionField(o,c,name,token,kind,offset,size,proof);
    requireValue(f(npc,nc,'<NpcCfgId>k__BackingField',0x0400a8fe,0x11,0x150,4).readS32()===m.npc_id&&
        f(npc,nc,'<WorldStatus>k__BackingField',0x0400a900,0x11,0x160,4).readS32()===0,'Photostone NPC is unavailable');
    samePointer(f(npc,nc,'<GameWorld>k__BackingField',0x0400a901,0x12,0x168,8).readPointer(),world,'Photostone NPC belongs to another world');
    samePointer(f(world,wc,'<PlayerModel>k__BackingField',0x0400a7e6,0x12,0x18,8).readPointer(),m.player,'Photostone world player changed');
    samePointer(f(npc,nc,'<MiniGameStatistics>k__BackingField',0x0400a913,0x15,0x1e8,8).readPointer(),m.stats,'Photostone statistics replaced');
    samePointer(f(npc,nc,'<NpcInteractionRuntime>k__BackingField',0x0400a914,0x12,0x1f0,8).readPointer(),runtime,'Photostone runtime replaced');
    samePointer(f(runtime,rc,'<ActionUsageRecords>k__BackingField',0x0400a8b5,0x15,0x18,8).readPointer(),m.usage,'Photostone usage collection replaced');
    requireValue(!ptr(m.usage).isNull(),'Photostone usage is uninitialized');
    className(m.usage,'System.Collections.Generic','Dictionary`2');
    const special=f(runtime,rc,'<SpecialSubId>k__BackingField',0x0400a8b3,8,0x10,4);
    samePointer(f(world,wc,'<CurrentGameTime>k__BackingField',0x0400a7e8,0x12,0x28,8).readPointer(),m.date_address,'Photostone date object changed');
    const time=ptr(m.date_address),tc=className(time,'Game','GameTime');
    requireValue(Array.isArray(m.date)&&m.date.length===4&&m.date.every((v,i)=>
        Number.isInteger(v)&&f(time,tc,['Year','Month','Day','Unit'][i],0x04004938+i,8,0x10+i*4,4).readS32()===v),'Photostone date changed');
    return {npc,world,runtime,nc,wc,rc,special};
}
function interactionPhotoEntry(m) {
    const entry=ptr(m.entry),ec=className(entry,'LubanDatas.data','NpcInteractGameEntry'),c=m.entry_config;
    samePointer(ec,m.entry_class,'Photostone configuration class changed');
    requireValue(c&&c.npc_id===m.npc_id&&c.sub_id===m.sub_id&&c.game_type===1&&c.max_success===1,
        'Photostone entry is outside reviewed configuration');
    for(const [name,token,kind,offset,expected] of [
        ['<npcId>k__BackingField',0x040017cd,0x11,0x10,m.npc_id],
        ['<subId>k__BackingField',0x040017ce,0x11,0x14,m.sub_id],
        ['<UnlockIntimacy>k__BackingField',0x040017d0,8,0x20,c.unlock_intimacy],
        ['<interactGameType>k__BackingField',0x040017d4,0x11,0x40,1],
        ['<interactGameParam>k__BackingField',0x040017d5,8,0x44,c.game_param],
        ['<triggerPriority>k__BackingField',0x040017e1,8,0x98,c.priority]])
        requireValue(interactionField(entry,ec,name,token,kind,offset,4).readS32()===expected,'Photostone entry configuration changed');
    // Nullable<Int32> and Nullable<subid wrapper> both use hasValue at +0 and
    // their reviewed four-byte value at +4. Zero is not a fabricated predecessor.
    const depends=interactionField(entry,ec,'<dependsSubId>k__BackingField',0x040017cf,0x15,0x18,8);
    const hasDepends=boolAt(depends);
    requireValue(hasDepends?(Number.isInteger(c.depends_sub_id)&&depends.add(4).readS32()===c.depends_sub_id):c.depends_sub_id===null,
        'Photostone predecessor configuration changed');
    const maximum=interactionField(entry,ec,'<maxSuccessCount>k__BackingField',0x040017d3,0x15,0x38,8);
    requireValue(boolAt(maximum)&&maximum.add(4).readS32()===1,'Photostone success limit changed');
    return {entry,ec,depends:hasDepends?c.depends_sub_id:null};
}
function executePhotostone() {
    const m=request.photostone,force=request.operation==='photostone_force_replay';
    interactionRound(m);
    requireValue(request.operation==='photostone_activate'||force,'Photostone operation not whitelisted');
    requireValue(m.mode===(force?'force':'next')&&(!force||m.force_confirmed===true),'Photostone mode or reset confirmation differs');
    interactionInteger(m.npc_id,1);interactionInteger(m.sub_id,1);
    const owner=interactionPhotoOwner(m,true),configuration=interactionPhotoEntry(m);
    const member=interactionWorldNpc(owner.world,owner.npc,m.npc_id,m.npc_dictionary);
    samePointer(interactionField(owner.world,owner.wc,'<StaticNpcIds>k__BackingField',0x0400a7ec,0x15,0x48,8).readPointer(),m.static_ids.address,'Photostone static ID map changed');
    requireValue(m.static_ids.flavor==='static','Photostone static ID map flavor differs');
    const ids=interactionConcurrent(m.static_ids),selectedIds=ids.filter(x=>x.key===m.npc_id);
    requireValue(selectedIds.length===1&&selectedIds[0].value===member.key,'Photostone static ID is not the selected world NPC');
    interactionPhotoQuests(m);
    interactionPhotoUsage(m);
    requireValue(owner.special.readS32()===m.active_special&&m.active_special===0,'Photostone special entry already active');
    const before=interactionStatistics(m.stats,true);
    interactionExpectedStatistics(before,m.stats_before);
    requireValue(configuration.depends===null||before.items.has(configuration.depends),'Photostone prerequisite key missing');
    requireValue(force||!before.items.has(m.sub_id)||before.items.get(m.sub_id)===0,'Photostone stage is already complete');
    const manager=ptr(m.logic_manager),lc=className(manager,'Game','NpcLogicManager');
    samePointer(lc,m.logic_class,'Photostone logic manager class changed');
    requireValue(m.methods&&Object.keys(m.methods).sort().join(',')==='force,meets,set','Photostone methods incomplete');
    const selected=force?'force':'set',spec=INTERACTION_METHODS[force?'force':'activate'];
    requireRequestMethod(spec);samePointer(request.method_info,m.methods[selected],'Photostone selected method differs');
    const methods={set:interactionMethod(m.methods.set,lc,INTERACTION_METHODS.activate),
        force:interactionMethod(m.methods.force,lc,INTERACTION_METHODS.force),
        meets:interactionMethod(m.methods.meets,lc,INTERACTION_METHODS.requirements)};
    interactionArgumentClass(methods.set,0,'Game.Model','NpcModel');
    interactionArgumentClass(methods.meets,0,'Game.Model','NpcModel');
    interactionArgumentClass(methods.meets,1,'LubanDatas.data','NpcInteractGameEntry');
    interactionArgumentClass(methods.force,0,'LubanDatas','TbNpcBaseCfgId',20);
    interactionArgumentClass(methods.force,1,'LubanDatas','TbNpcInteractGameEntrySubid',20);
    interactionStableAnchors(m.post_stable_anchors);
    const eligible=interactionBoolean(interactionInvoke(methods.meets,ptr(0),[owner.npc,configuration.entry,interactionScalar(force,true)]));
    requireValue(eligible,'Photostone native eligibility denied');
    validateAnchors();
    interactionPhotoOwner(m,true);
    interactionDispatch(m);
    const result=force?interactionInvoke(methods.force,manager,[interactionScalar(m.npc_id),interactionScalar(m.sub_id)]):
        interactionInvoke(methods.set,ptr(0),[owner.npc,interactionScalar(m.sub_id),interactionScalar(true,true)]);
    requireValue(interactionBoolean(result),'Photostone method did not confirm activation; never retry');
    interactionPhotoOwner(m,false);
    interactionPhotoQuests(m,false);
    interactionPhotoUsage(m,false);
    requireValue(owner.special.readS32()===m.sub_id,'Photostone special entry was not retained; never retry');
    const after=interactionStatistics(m.stats,false),had=before.items.has(m.sub_id),expected=m.stats_before.filter(x=>!force||x.key!==m.sub_id);
    interactionExpectedStatistics(after,expected);
    samePointer(after.array,before.array,'Photostone statistics allocation changed; never retry');
    requireValue(after.count===before.count&&after.capacity===before.capacity&&
        after.free===before.free+(force&&had?1:0)&&after.version===((before.version+(force&&had?1:0))|0),
        'Photostone statistics changed beyond the selected operation; never retry');
    interactionStableAnchors(m.post_stable_anchors);
    finish('completed',{called:true,operation:request.operation,round_key:m.round_key,npc_id:m.npc_id,sub_id:m.sub_id,
        activated:true,history_reset:force&&had,previous_success:had?before.items.get(m.sub_id):null,
        active_special:m.sub_id,thread_id:Process.getCurrentThreadId()});
}
function interactionDelegate(d,proof=true) {
    requireValue(d&&d.address&&d.method_info&&d.target,'Persuasion delegate descriptor missing');
    const p=ptr(d.address),kc=p.readPointer();requireValue(!kc.isNull(),'Persuasion delegate missing');
    const mc=interactionClass(kc.add(0x58).readPointer(),'System','MulticastDelegate'),
        dc=interactionClass(mc.add(0x58).readPointer(),'System','Delegate');
    for(const [name,token,offset,expected] of [['method_ptr',0x04000762,16,d.code],['method',0x04000765,40,d.method_info],['method_code',0x04000768,64,d.target]])
        samePointer(interactionField(p,dc,name,token,0x18,offset,8,proof).readPointer(),expected,'Persuasion delegate changed');
    samePointer(interactionField(p,mc,'delegates',0x04000790,0x1d,0x78,8,proof).readPointer(),d.delegates,'Persuasion delegate list changed');
    return p;
}
function interactionPersuasionFlow(m,proof=true) {
    const flow=m.flow,panel=ptr(m.panel),pc=className(panel,'Game','NpcPersuadePanel');
    requireValue(flow&&flow.sub_id===m.sub_id&&!flow.notified&&!flow.ended&&!flow.cancelled,'Persuasion flow already ended');
    const closure=ptr(flow.closure),cc=className(closure,'','<>c__DisplayClass5_0'),
        command=ptr(flow.command),kc=className(command,'Game','MiniGamePersuadeCommand'),
        ctx=ptr(flow.context),xc=className(ctx,'A1.Flow','ProcContext');
    samePointer(cc,flow.closure_class,'Persuasion closure class changed');samePointer(kc,flow.command_class,'Persuasion command class changed');samePointer(xc,flow.context_class,'Persuasion context class changed');
    const field=(o,c,n,t,k,offset,size)=>interactionField(o,c,n,t,k,offset,size,proof);
    requireValue(!boolAt(field(closure,cc,'notified',0x04005bfa,2,16,1)),'Persuasion flow already notified');
    boolAt(field(closure,cc,'win',0x04005bfb,2,17,1));
    samePointer(field(closure,cc,'<>4__this',0x04005bfd,0x12,32,8).readPointer(),command,'Persuasion command replaced');
    samePointer(field(closure,cc,'ctx',0x04005bfe,0x12,40,8).readPointer(),ctx,'Persuasion context replaced');
    requireValue(field(command,kc,'_npcId',0x04005bf7,0x11,16,4).readS32()===m.npc_id&&
        field(command,kc,'_topicId',0x04005bf8,0x11,20,4).readS32()===m.topic_id,'Persuasion command target changed');
    const sub=field(command,kc,'_subId',0x04005bf9,0x15,24,8);
    requireValue(boolAt(sub)&&sub.add(4).readS32()===m.sub_id,'Persuasion command sub-ID changed');
    samePointer(field(ctx,xc,'<Ct>k__BackingField',0x040000d0,0x11,16,8).readPointer(),flow.source,'Persuasion cancellation source changed');
    requireValue(field(ctx,xc,'<ActivationId>k__BackingField',0x040000d1,8,24,4).readS32()===flow.activation_id&&
        !boolAt(field(ctx,xc,'_endedNotified',0x040000d8,2,0x78,1)),'Persuasion context ended or replaced');
    const source=ptr(flow.source);
    if(!source.isNull()) {
        const sc=className(source,'System.Threading','CancellationTokenSource');samePointer(sc,flow.source_class,'Persuasion source class changed');
        const status=field(source,sc,'_state',0x04000a46,8,32,4).readS32();
        requireValue(status>=0&&status<2&&!boolAt(field(source,sc,'_disposed',0x04000a48,2,40,1)),'Persuasion flow cancelled or disposed');
    }
    requireValue(flow.callbacks&&Object.keys(flow.callbacks).sort().join(',')==='alive,close,lose,win','Persuasion callbacks missing');
    for(const [key,name,token,kind,offset] of [['alive','_isFlowAlive',0x0400542c,0x15,0x180],['win','_actionOnWin',0x0400542f,0x12,0x190],
        ['lose','_actionOnLose',0x04005430,0x12,0x198],['close','_actionOnClose',0x04005431,0x12,0x1a0]]) {
        const d=flow.callbacks[key];samePointer(field(panel,pc,name,token,kind,offset,8).readPointer(),d.address,'Persuasion flow callback replaced');
        interactionDelegate(d,proof);samePointer(d.target,closure,'Persuasion callback targets another flow');
        requireValue(ptr(d.delegates).isNull(),'Persuasion callback is multicast');
        interactionMethod(d.method_info,cc,INTERACTION_METHODS[key]);samePointer(d.code,image.base.add(INTERACTION_METHODS[key].rva),'Persuasion callback code differs');
    }
}
function interactionPersuasionEvent(m,proof=true) {
    const callbacks=m.event_callbacks;requireValue(Array.isArray(callbacks)&&callbacks.length>0&&callbacks.length<=16,'Persuasion event callbacks missing');
    const event=ptr(m.event),ec=event.readPointer(),mc=interactionClass(ec.add(0x58).readPointer(),'System','MulticastDelegate');
    const array=interactionField(event,mc,'delegates',0x04000790,0x1d,0x78,8,proof).readPointer();
    let members=[event];
    if(!array.isNull()) {
        className(array,'System','Delegate[]');if(proof)requireCoverage(array.add(24),8);
        const n=array.add(24).readU64().toNumber();requireValue(n===callbacks.length,'Persuasion subscription count changed');
        members=[];for(let i=0;i<n;i++){if(proof)requireCoverage(array.add(32+i*8),8);members.push(array.add(32+i*8).readPointer());}
    }
    requireValue(members.length===callbacks.length,'Persuasion subscription changed');
    let found=0;
    callbacks.forEach((d,i)=>{
        samePointer(members[i],d.address,'Persuasion event subscription changed');interactionDelegate(d,proof);
        requireValue(ptr(d.delegates).isNull(),'Persuasion nested multicast unsupported');
        if(ptr(d.target).equals(ptr(m.panel))) {
            interactionMethod(d.method_info,ptr(m.panel_class),INTERACTION_METHODS.ended);
            samePointer(d.code,image.base.add(INTERACTION_METHODS.ended.rva),'Persuasion panel subscriber code differs');found++;
        }
    });
    requireValue(found===1,'Persuasion panel does not have one normal result subscriber');
}
function interactionPersuasionOwner(m,after=false) {
    const panel=dualJadePanel(m,'Game','NpcPersuadePanel'),pc=panel.readPointer(),npc=ptr(m.npc),nc=className(npc,'Game.Model','NpcModel'),
        world=ptr(m.world),wc=className(world,'Game.Model','GameWorldModel'),input=ptr(m.input_panel),ic=className(input,'Game','DialogueInputPanel');
    className(m.player,'Game.Model','PlayerModel');samePointer(pc,m.panel_class,'Persuasion panel class changed');samePointer(nc,m.npc_class,'Persuasion NPC class changed');samePointer(ic,m.input_class,'Persuasion input class changed');
    const field=(o,c,n,t,k,offset,size)=>interactionField(o,c,n,t,k,offset,size,!after);
    const pf=(n,t,k,o,size)=>field(panel,pc,n,t,k,o,size),nf=(n,t,k,o,size)=>field(npc,nc,n,t,k,o,size);
    samePointer(pf('_subscribedNpc',0x04005425,0x12,0x158,8).readPointer(),npc,'Persuasion panel NPC changed');
    requireValue(pf('_npcId',0x0400542d,0x11,0x188,4).readS32()===m.npc_id&&pf('_topicId',0x0400542e,0x11,0x18c,4).readS32()===m.topic_id&&
        nf('<NpcCfgId>k__BackingField',0x0400a8fe,0x11,0x150,4).readS32()===m.npc_id,'Persuasion target changed');
    samePointer(nf('<GameWorld>k__BackingField',0x0400a901,0x12,0x168,8).readPointer(),world,'Persuasion NPC world changed');
    samePointer(field(world,wc,'<PlayerModel>k__BackingField',0x0400a7e6,0x12,24,8).readPointer(),m.player,'Persuasion current player changed');
    const member=interactionWorldNpc(world,npc,m.npc_id,m.membership.dictionary_descriptor,!after);
    requireValue(member.key===m.membership.uuid&&member.node===m.membership.node&&m.membership.npc_id===m.npc_id,'Persuasion canonical member changed');
    samePointer(m.membership.npc,npc,'Persuasion membership target differs');
    samePointer(pf('DialogueInput',0x0400541d,0x12,0x118,8).readPointer(),input,'Persuasion input panel changed');
    if(!after)requireCoverage(input.add(16),8);requireValue(!input.add(16).readPointer().isNull(),'Persuasion input destroyed');
    const canSubmit=boolAt(field(input,ic,'m_CanSubmit',0x04004c28,2,0x128,1));
    boolAt(field(input,ic,'m_SubmitAvailable',0x04004c29,2,0x129,1));
    requireValue(!boolAt(pf('_userInitiatedClose',0x0400542b,2,0x179,1))&&pf('_peekLoadingCo',0x04005432,0x12,0x1a8,8).readPointer().isNull()&&
        !boolAt(nf('IsProcessingPersuadeMessage',0x0400a8e8,2,0xe8,1)),'Persuasion is closing or processing AI input');
    requireValue(!boolAt(nf('<IsProcessingChatMessage>k__BackingField',0x0400a8dc,2,0xa8,1))&&
        !boolAt(nf('<IsSummarizingChatHistory>k__BackingField',0x0400a8dd,2,0xa9,1)),'Persuasion NPC still has another AI request');
    requireValue(nf('<PersuadeSessionId>k__BackingField',0x0400a8ee,8,0x100,4).readS32()===m.session_id&&
        nf('_persuadeProcessingToken',0x0400a8e9,8,0xec,4).readS32()===m.processing_token,'Persuasion session changed');
    const ended=boolAt(pf('_persuadeEnded',0x04005427,2,0x168,1)),win=boolAt(pf('_settlementIsWin',0x0400542a,2,0x178,1));
    const notified=boolAt(pf('_persuadeResultNotified',0x04005428,2,0x169,1));
    const reason=nf('<LastPersuadeEndReason>k__BackingField',0x0400a8e2,0x11,0xc4,4).readS32(),
        topic=nf('<CurrentPersuadeTopicId>k__BackingField',0x0400a8e3,0x11,0xc8,4).readS32(),
        round=nf('<PersuadeRound>k__BackingField',0x0400a8e4,8,0xcc,4).readS32(),
        emotion=nf('<PersuadeEmotionValue>k__BackingField',0x0400a8e6,8,0xd8,4).readS32(),
        peek=pf('_peekRequestToken',0x04005433,8,0x1b0,4).readS32();
    samePointer(nf('OnPersuadeEnded',0x0400a8f2,0x15,0x120,8).readPointer(),m.event,'Persuasion ended event replaced');
    for(const [name,token,offset,expected] of [['<PersuadeChatMessages>k__BackingField',0x0400a8e5,0xd0,m.chat],['_persuadeLedger',0x0400a8eb,0xf8,m.ledger]]) {
        samePointer(nf(name,token,0x15,offset,8).readPointer(),expected,'Persuasion conversation container changed');className(expected,'System.Collections.Generic','List`1');
    }
    if(after)requireValue(ended&&win&&!canSubmit&&reason===1&&topic===0&&round===0&&emotion===0&&peek===((m.peek_token+1)|0),'Persuasion success state not retained; never retry');
    else requireValue(!ended&&!notified&&canSubmit&&reason===0&&topic===m.topic_id&&peek===m.peek_token&&
        round>=0&&round<=m.config.max_rounds&&pf('_settlementDelayCts',0x04005429,0x12,0x170,8).readPointer().isNull(),'Persuasion is not an idle active session');
    interactionPersuasionFlow(m,!after);interactionPersuasionEvent(m,!after);
    return {npc,nc,panel};
}
function interactionPersuasionConfig(m) {
    const c=m.config,topic=ptr(c.topic_config),tc=className(topic,'LubanDatas.data','NpcPersuadeTopic'),entry=ptr(c.entry_config),ec=className(entry,'LubanDatas.data','NpcInteractGameEntry');
    for(const [obj,kc,name,token,kind,offset,expected] of [
        [topic,tc,'<id>k__BackingField',0x0400182b,0x11,16,m.topic_id],
        [topic,tc,'<maxRounds>k__BackingField',0x0400182d,8,32,c.max_rounds],
        [topic,tc,'<npcId>k__BackingField',0x04001832,0x11,0x48,m.npc_id],
        [entry,ec,'<npcId>k__BackingField',0x040017cd,0x11,16,m.npc_id],
        [entry,ec,'<subId>k__BackingField',0x040017ce,0x11,20,m.sub_id],
        [entry,ec,'<interactGameType>k__BackingField',0x040017d4,0x11,0x40,2],
        [entry,ec,'<interactGameParam>k__BackingField',0x040017d5,8,0x44,m.topic_id]])
        requireValue(interactionField(obj,kc,name,token,kind,offset,4).readS32()===expected,'Persuasion configuration changed');
    interactionInteger(c.max_rounds,1,1000);interactionInteger(c.exit_delay_ms,1,600000);
    const delay=interactionField(topic,tc,'<autoExitDelayMs>k__BackingField',0x04001833,0x15,0x4c,8);
    requireValue(boolAt(delay)&&delay.add(4).readS32()===c.exit_delay_ms,'Persuasion normal countdown changed');
}
function executePersuasion() {
    const m=request.persuasion;interactionRound(m);
    requireValue(request.operation==='persuasion_success','Persuasion operation not whitelisted');
    for(const key of ['npc_id','topic_id','sub_id','session_id'])interactionInteger(m[key],1);
    const owner=interactionPersuasionOwner(m),spec=INTERACTION_METHODS.persuade;
    interactionPersuasionConfig(m);interactionStableAnchors(m.post_stable_anchors);
    requireRequestMethod(spec);const method=interactionMethod(request.method_info,owner.nc,spec);
    interactionArgumentClass(method,1,'Game.Model','PersuadeEndReason',20);
    interactionDispatch(m);
    const result=interactionInvoke(method,owner.npc,[interactionScalar(true,true),interactionScalar(1)]);
    requireValue(result.isNull(),'Persuasion void method returned a value; never retry');
    interactionPersuasionOwner(m,true);interactionStableAnchors(m.post_stable_anchors);
    // Success has been judged. The game still owns its normal countdown,
    // settlement panel, reward delivery and completion callback.
    finish('completed',{called:true,native_won:true,normal_countdown:true,round_key:m.round_key,
        npc_id:m.npc_id,topic_id:m.topic_id,session_id:m.session_id,end_reason:1,
        panel_ended:true,settlement_is_win:true,current_topic_id:0,thread_id:Process.getCurrentThreadId()});
}
