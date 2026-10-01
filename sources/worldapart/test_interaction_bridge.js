'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {memoryFixture}=require('./interaction_test_fixture.js');
const photoSpecs=require('./photostone_specs.json').methods;
function photoFixture(force=false,current=false) {
    const f=memoryFixture(current),{object,ptr,klass,alloc,fields,method,block,addAnchor}=f;
    const world=object('Game.Model','GameWorldModel'),npc=object('Game.Model','NpcModel'),player=object('Game.Model','PlayerModel'),
        runtime=object('Game.Model','NpcInteractionRuntimeState'),usage=object('System.Collections.Generic','Dictionary`2'),
        logic=object('Game','NpcLogicManager'),entry=object('LubanDatas.data','NpcInteractGameEntry');
    const time=object('Game','GameTime');
    // Independent FieldInfo read from build 25617557: do not derive the current
    // date tokens from the production variant table (that hid three omissions).
    fields(time.readPointer(),['Year','Month','Day','Unit'].map((n,i)=>[n,(current?0x04004921:0x04004938)+i,8,0x10+i*4]));
    fields(world.readPointer(),[['<PlayerModel>k__BackingField',0x0400a7e6,0x12,0x18],['<CurrentGameTime>k__BackingField',0x0400a7e8,0x12,0x28],['<NpcModels>k__BackingField',0x0400a7ea,0x15,0x38],['<StaticNpcIds>k__BackingField',0x0400a7ec,0x15,0x48]]);
    fields(npc.readPointer(),[['<NpcCfgId>k__BackingField',0x0400a8fe,0x11,0x150],['<WorldStatus>k__BackingField',0x0400a900,0x11,0x160],
        ['<GameWorld>k__BackingField',0x0400a901,0x12,0x168],['<MiniGameStatistics>k__BackingField',0x0400a913,0x15,0x1e8],['<NpcInteractionRuntime>k__BackingField',0x0400a914,0x12,0x1f0]]);
    fields(runtime.readPointer(),[['<SpecialSubId>k__BackingField',0x0400a8b3,8,0x10],['<ActionUsageRecords>k__BackingField',0x0400a8b5,0x15,0x18]]);
    fields(entry.readPointer(),[['<npcId>k__BackingField',0x040017cd,0x11,0x10],['<subId>k__BackingField',0x040017ce,0x11,0x14],
        ['<dependsSubId>k__BackingField',0x040017cf,0x15,0x18],['<UnlockIntimacy>k__BackingField',0x040017d0,8,0x20],
        ['<maxSuccessCount>k__BackingField',0x040017d3,0x15,0x38],['<interactGameType>k__BackingField',0x040017d4,0x11,0x40],
        ['<interactGameParam>k__BackingField',0x040017d5,8,0x44],['<triggerPriority>k__BackingField',0x040017e1,8,0x98]]);
    const stats=object('System.Collections.Generic','Dictionary`2'),array=object('','Entry[]',160),ec=klass('','Entry',32);
    const typeSub=klass('LubanDatas','TbNpcInteractGameEntrySubid',20);fields(typeSub,[['<Value>k__BackingField',0x04000bea,8,16]]);
    array.readPointer().add(0x40).writePointer(ec);fields(ec,[['hashCode',0x04001b0d,8,16],['next',0x04001b0e,8,20],['key',0x04001b0f,0x11,24,typeSub],['value',0x04001b10,8,28]]);
    const rows=force?[{key:10,value:1},{key:11,value:3},{key:99,value:7}]:[{key:10,value:1},{key:99,value:7}];
    stats.add(0x18).writePointer(array);stats.add(0x20).writeS32(rows.length);stats.add(0x24).writeS32(-1);stats.add(0x2c).writeS32(8);array.add(24).writePointer(7);
    rows.forEach((r,i)=>{const p=array.add(32+i*16);p.writeS32(r.key);p.add(4).writeS32(-1);p.add(8).writeS32(r.key);p.add(12).writeS32(r.value);});
    world.add(0x18).writePointer(player);world.add(0x28).writePointer(time);const date=[1,2,3,4];date.forEach((x,i)=>time.add(0x10+i*4).writeS32(x));
    npc.add(0x150).writeS32(100);npc.add(0x168).writePointer(world);npc.add(0x1e8).writePointer(stats);npc.add(0x1f0).writePointer(runtime);runtime.add(0x18).writePointer(usage);
    entry.add(0x10).writeS32(100);entry.add(0x14).writeS32(11);entry.add(0x18).writeU8(1);entry.add(0x1c).writeS32(10);entry.add(0x38).writeU8(1);entry.add(0x3c).writeS32(1);entry.add(0x40).writeS32(1);entry.add(0x44).writeS32(1);
    const typeNpc=klass('LubanDatas','TbNpcBaseCfgId',20),methods={};
    for(const [key,s]of Object.entries(photoSpecs))methods[key]=method(logic.readPointer(),s,key==='force'?[typeNpc,typeSub]:key==='set'?[npc.readPointer()]:[npc.readPointer(),entry.readPointer()]);
    for(const p of [world,npc,player,runtime,usage,logic,entry,stats,time])block(p,0x300);block(array,160);
    const post=f.request.anchors.filter(a=>[world.toString(),usage.toString(),usage.add(256).toString()].includes(a.address));
    const npcMap=f.concurrent('npc',[['npc-uuid',npc.toString()]]),staticMap=f.concurrent('static',[[100,'npc-uuid']]);
    world.add(0x38).writePointer(npcMap.address);world.add(0x48).writePointer(staticMap.address);
    const quest=object('System.Collections.Generic','HashSet`1');fields(quest.readPointer(),[['_buckets',0x040004da,0x1d,16],['_slots',0x040004db,0x1d,24],['_count',0x040004dc,8,32],['_lastIndex',0x040004dd,8,36],['_freeList',0x040004de,8,40],['_version',0x040004e0,8,56]]);quest.add(40).writeS32(-1);block(quest,0x300);
    fields(logic.readPointer(),[['_questSpecialStateOwners',0x040036e6,0x15,32],['_isExecutingNpcInteractAction',0x040036e9,2,0x2d]]);logic.add(32).writePointer(quest);
    const m={usage_state:{dictionary:{address:usage.toString(),entries:'0x0',count:0,free:0,version:0,items:[]},records:[]},quest_owners:{kind:'hashset',address:quest.toString(),slots:'0x0',buckets:'0x0',count:0,last_index:0,free_list:-1,version:0,capacity:0,items:[]},npc_dictionary:npcMap,static_ids:staticMap,mode:force?'force':'next',round_key:'a'.repeat(64),npc_id:100,sub_id:11,npc:npc.toString(),world:world.toString(),player:player.toString(),
        logic_manager:logic.toString(),logic_class:logic.readPointer().toString(),runtime:runtime.toString(),usage:usage.toString(),stats:stats.toString(),active_special:0,
        stats_before:rows.map(r=>({...r})),entry:entry.toString(),entry_class:entry.readPointer().toString(),date,date_address:time.toString(),
        methods:Object.fromEntries(Object.entries(methods).map(([k,v])=>[k,v.address.toString()])),
        owner_links:[{address:world.add(0x18).toString(),expected:player.toString()},{address:npc.add(0x168).toString(),expected:world.toString()}],
        post_stable_anchors:post,entry_config:{npc_id:100,sub_id:11,depends_sub_id:10,max_success:1,game_type:1,game_param:1,unlock_intimacy:0,priority:0,reward:1},force_confirmed:force};
    const selected=force?'force':'set',s=f.variant(photoSpecs[selected]);
    Object.assign(f.request,{operation:force?'photostone_force_replay':'photostone_activate',photostone:m,method_info:m.methods[selected],method_token:s.token,method_rva:s.rva,parameter_count:s.argc});
    const calls=[];f.options.invoke=(mi,target,args,exception)=>{
        const key=Object.keys(methods).find(k=>methods[k].address.equals(mi));assert.ok(key);calls.push(key);exception.writePointer(f.options.exception===key?1:0);
        if(f.options.throw===key)throw Error('native failure');
        if(key==='meets'){
            assert.ok(target.isNull());assert.ok(args.readPointer().equals(npc));assert.ok(args.add(8).readPointer().equals(entry));assert.equal(args.add(16).readPointer().readU8(),force?1:0);
            if(f.options.afterMeets)f.options.afterMeets();
        }else{
            if(key==='set'){assert.ok(target.isNull());assert.ok(args.readPointer().equals(npc));assert.equal(args.add(8).readPointer().readS32(),11);assert.equal(args.add(16).readPointer().readU8(),1);}
            else {assert.ok(target.equals(logic));assert.equal(args.readPointer().readS32(),100);assert.equal(args.add(8).readPointer().readS32(),11);}
            if(!f.options.noChange){runtime.add(0x10).writeS32(11);if(force){array.add(48).writeS32(-1);stats.add(0x24).writeS32(1);stats.add(0x28).writeS32(1);stats.add(0x2c).writeS32(9);}}
            if(f.options.afterMutation)f.options.afterMutation();
        }
        if(f.options.nullReturn===key)return ptr(0);
        const box=object('System',f.options.wrongReturn===key?'Int32':'Boolean',24);box.add(16).writeU8(f.options.denied===key?0:1);return box;
    };
    f.sync();return {...f,m,world,time,npc,player,runtime,usage,logic,entry,stats,array,ec,rows,methods,typeNpc,typeSub,quest,calls};
}
function questRow(f,npcId=99) {
    const {object,klass,fields,block}=f,slots=object('','Slot[]'),buckets=object('System','Int32[]'),ec=klass('','Slot',36),oc=klass('','QuestSpecialStateOwner',28);
    fields(oc,['QuestId','NpcId','SubId'].map((n,i)=>[n,0x040036f2+i,0x11,16+i*4]));
    fields(ec,[['hashCode',0x040004e4,8,16],['next',0x040004e5,8,20],['value',0x040004e6,0x11,24,oc]]);slots.readPointer().add(0x40).writePointer(ec);
    slots.add(24).writePointer(3);slots.add(32).writeS32(0);slots.add(36).writeS32(-1);slots.add(40).writeS32(1);slots.add(44).writeS32(npcId);slots.add(48).writeS32(2);buckets.add(24).writePointer(3);
    f.quest.add(16).writePointer(buckets);f.quest.add(24).writePointer(slots);f.quest.add(32).writeS32(1);f.quest.add(36).writeS32(1);
    Object.assign(f.m.quest_owners,{buckets:buckets.toString(),slots:slots.toString(),count:1,last_index:1,capacity:3,items:[{quest_id:1,npc_id:npcId,sub_id:2,slot:slots.add(32).toString()}]});
    block(slots,0x300);block(buckets,0x300);f.sync();return {slots,buckets,ec,oc};
}
function usageRow(f) {
    const {object,klass,fields,block}=f,entries=object('','Entry[]'),record=object('Game.Model','NpcInteractionActionUsageRecord'),ec=klass('','Entry',40);
    fields(ec,[['hashCode',0x04001b0d,8,16],['next',0x04001b0e,8,20],['key',0x04001b0f,8,24],['value',0x04001b10,0x12,32]]);entries.readPointer().add(0x40).writePointer(ec);
    fields(record.readPointer(),[['<UsedCount>k__BackingField',0x0400a8b6,8,16],['<CycleKey>k__BackingField',0x0400a8b7,0x0a,24]]);
    entries.add(24).writePointer(3);entries.add(32).writeS32(0);entries.add(36).writeS32(-1);entries.add(40).writeS32(2);entries.add(48).writePointer(record);record.add(16).writeS32(3);record.add(24).writePointer(100);
    f.usage.add(24).writePointer(entries);f.usage.add(32).writeS32(1);f.m.usage_state={dictionary:{address:f.usage.toString(),entries:entries.toString(),count:1,free:0,version:0,capacity:3,stride:24,items:[{key:2,value:record.toString(),entry:entries.add(32).toString()}]},records:[{action_id:2,record:record.toString(),used_count:3,cycle_key:100}]};
    block(entries,0x300);block(record,0x300);f.sync();return {entries,record,ec};
}
let count=0;
function test(name,fn){try{fn();count++;}catch(e){e.message=name+': '+e.message;throw e;}}
function refused(f){const r=f.submit();assert.equal(r.status,'rejected',JSON.stringify(r));assert.equal(r.called,false);return r;}
function unknown(f){const r=f.submit();assert.equal(r.status,'unknown',JSON.stringify(r));assert.equal(r.called,true);assert.throws(()=>f.api.reset(f.request.token));return r;}
test('source segment exactly matches standalone declaration',()=>{
    const s=fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8').replace(/\r\n/g,'\n'),a='/* BEGIN interaction_bridge.js */\n',b='\n/* END interaction_bridge.js */';
    assert.equal(s.slice(s.indexOf(a)+a.length,s.indexOf(b)),fs.readFileSync(path.join(__dirname,'interaction_bridge.js'),'utf8').replace(/\r\n/g,'\n'));
});
test('next stage keeps all success records',()=>{const f=photoFixture(),r=f.submit();assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.activated,true);assert.equal(r.history_reset,false);assert.deepEqual(f.calls,['meets','set']);assert.equal(f.stats.add(0x2c).readS32(),8);f.run();assert.equal(f.calls.length,2);});
test('force removes only selected completed key and accepts version increment',()=>{const f=photoFixture(true),r=f.submit();assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(r.previous_success,3);assert.equal(r.history_reset,true);assert.deepEqual(f.calls,['meets','force']);assert.equal(f.array.add(76).readS32(),7);});
test('same round with a fresh token cannot dispatch twice',()=>{const f=photoFixture();assert.equal(f.submit().status,'completed');f.api.reset(f.request.token);f.request.token='fresh';f.runtime.add(16).writeS32(0);f.sync();refused(f);assert.deepEqual(f.calls,['meets','set']);});
for(const force of [false,true])test('same active stage refuses without clearing stats '+force,()=>{const f=photoFixture(force);f.runtime.add(16).writeS32(11);f.m.active_special=11;f.sync();refused(f);assert.deepEqual(f.calls,[]);});
test('different active special refuses',()=>{const f=photoFixture();f.runtime.add(16).writeS32(6);f.m.active_special=6;f.sync();refused(f);});
test('force requires explicit reset mode acknowledgement',()=>{const f=photoFixture(true);f.m.force_confirmed=false;refused(f);});
test('next never replays completed stage',()=>{const f=photoFixture(true);f.request.operation='photostone_activate';f.m.mode='next';refused(f);});
test('predecessor uses key presence including zero per game',()=>{const f=photoFixture();f.array.add(44).writeS32(0);f.m.stats_before[0].value=0;f.sync();assert.equal(f.submit().status,'completed');});
test('missing predecessor rejects before eligibility',()=>{const f=photoFixture();f.array.add(40).writeS32(9);f.m.stats_before[0].key=9;f.sync();refused(f);assert.deepEqual(f.calls,[]);});
test('nullable predecessor mismatch refuses',()=>{const f=photoFixture();f.entry.add(24).writeU8(0);f.sync();refused(f);});
test('uninitialized usage refuses',()=>{const f=photoFixture();f.runtime.add(24).writePointer(0);f.m.usage='0x0';f.sync();refused(f);});
test('unavailable NPC refuses',()=>{const f=photoFixture();f.npc.add(0x160).writeS32(1);f.sync();refused(f);});
test('wrong world refuses',()=>{const f=photoFixture();f.npc.add(0x168).writePointer(123);f.sync();refused(f);});
test('nonphotostone config refuses',()=>{const f=photoFixture();f.entry.add(0x40).writeS32(2);f.m.entry_config.game_type=2;f.sync();refused(f);});
test('stale date before call refuses',()=>{const f=photoFixture();f.time.add(0x18).writeS32(4);refused(f);assert.deepEqual(f.calls,[]);});
for(const key of ['set','force','meets'])test('wrong method flags '+key,()=>{const f=photoFixture();f.methods[key].address.add(0x4c).writeU8(photoSpecs[key].static?0x81:0x91);refused(f);});
for(const kind of ['denied','wrongReturn','nullReturn','exception','throw'])test('eligibility '+kind+' is a safe refusal',()=>{const f=photoFixture();f.options[kind]='meets';refused(f);assert.deepEqual(f.calls,['meets']);});
test('state changed inside eligibility never reaches mutation',()=>{const f=photoFixture();f.options.afterMeets=()=>f.runtime.add(16).writeS32(7);refused(f);assert.deepEqual(f.calls,['meets']);});
for(const kind of ['denied','wrongReturn','nullReturn','exception','throw'])test('mutation '+kind+' is unknown and locked',()=>{const f=photoFixture();f.options[kind]='set';unknown(f);});
test('native reports true without changing entry is unknown',()=>{const f=photoFixture();f.options.noChange=true;unknown(f);});
test('force touches another success count is unknown',()=>{const f=photoFixture(true);f.options.afterMutation=()=>f.array.add(76).writeS32(8);unknown(f);});
test('extra dictionary version increment is unknown',()=>{const f=photoFixture(true);f.options.afterMutation=()=>f.stats.add(0x2c).writeS32(10);unknown(f);});
test('world switch during notification is unknown',()=>{const f=photoFixture();f.options.afterMutation=()=>f.npc.add(0x168).writePointer(123);unknown(f);});
test('date changed by notification is unknown',()=>{const f=photoFixture();f.options.afterMutation=()=>f.time.add(0x18).writeS32(4);unknown(f);});
test('usage changed by notification is unknown',()=>{const f=photoFixture();f.options.afterMutation=()=>f.usage.add(0x2c).writeS32(1);unknown(f);});
test('response transport failure retains called and unknown',()=>{const f=photoFixture();f.options.sendFailure=true;assert.throws(()=>f.submit(),/send failed/);const r=f.api.status();assert.equal(r.called,true);assert.equal(r.status,'unknown');assert.throws(()=>f.api.reset(f.request.token));assert.deepEqual(f.calls,['meets','set']);});
test('cancelled before Update makes no call',()=>{const f=photoFixture();f.api.submit(f.request);f.api.cancel();f.run();assert.deepEqual(f.calls,[]);assert.equal(f.events.at(-1).called,false);});
test('expired before Update makes no call',()=>{const f=photoFixture();f.request.deadline=Date.now()-1;const r=f.submit();assert.equal(r.status,'cancelled');assert.deepEqual(f.calls,[]);});
test('ordinary int key cannot stand in for SubId wrapper',()=>{const f=photoFixture();f.ec.add(0x80).readPointer().add(64+8).readPointer().add(10).writeU8(8);refused(f);});
test('negative concurrent hash uses low 31 bits as game does',()=>{const f=photoFixture();const row=f.m.npc_dictionary.items[0];row.hashcode=-2147483648;f.ptr(row.node).add(40).writeS32(row.hashcode);f.sync();assert.equal(f.submit().status,'completed');});
test('concurrent cycle is rejected',()=>{const f=photoFixture();const row=f.m.npc_dictionary.items[0];row.next=row.node;f.ptr(row.node).add(32).writePointer(row.node);f.sync();refused(f);});
test('static ID cannot resolve a different UUID',()=>{const f=photoFixture();const row=f.m.static_ids.items[0];row.value='other';const p=f.managedString('other');f.ptr(row.node).add(24).writePointer(p);row.value_pointer=p.toString();f.sync();refused(f);});
test('missing world member refuses',()=>{const f=photoFixture();const row=f.m.npc_dictionary.items[0];row.value=f.player.toString();f.ptr(row.node).add(24).writePointer(f.player);f.sync();refused(f);});
test('mismatched lock count refuses',()=>{const f=photoFixture();f.ptr(f.m.npc_dictionary.count_per_lock).add(32).writeS32(2);f.sync();refused(f);});
test('missing concurrent proof refuses',()=>{const f=photoFixture();const b=f.ptr(f.m.npc_dictionary.buckets);f.request.anchors=f.request.anchors.filter(a=>a.address!==b.toString());refused(f);});
test('quest owned by another NPC does not block',()=>{const f=photoFixture();questRow(f);assert.equal(f.submit().status,'completed');});
test('quest owned by selected NPC blocks both normal and force',()=>{for(const mode of [false,true]){const f=photoFixture(mode);questRow(f,100);refused(f);assert.deepEqual(f.calls,[]);}});
test('executing NPC interaction rejects',()=>{const f=photoFixture();f.logic.add(0x2d).writeU8(1);f.sync();refused(f);});
test('quest takes ownership during callback produces unknown',()=>{const f=photoFixture();const q=questRow(f);f.options.afterMutation=()=>q.slots.add(44).writeS32(100);unknown(f);});
test('existing usage counts are preserved',()=>{const f=photoFixture();usageRow(f);assert.equal(f.submit().status,'completed');});
test('callback changes usage count produces unknown',()=>{const f=photoFixture();const u=usageRow(f);f.options.afterMutation=()=>u.record.add(16).writeS32(4);unknown(f);});
test('callback changes usage cycle produces unknown',()=>{const f=photoFixture();const u=usageRow(f);f.options.afterMutation=()=>u.record.add(24).writePointer(101);unknown(f);});
test('realistic owner proof over former 2048 link cap succeeds',()=>{const f=photoFixture();for(let i=0;i<2200;i++){const p=f.alloc(8);p.writePointer(f.world);f.addAnchor(p,8);f.m.owner_links.push({address:p.toString(),expected:f.world.toString()});}assert.equal(f.submit().status,'completed');});
test('large split proof including more than sixteen thousand anchors succeeds',()=>{const f=photoFixture();const missing=16856-f.request.anchors.length;for(let i=0;i<missing;i++)f.addAnchor(f.alloc(8),8);assert.equal(f.request.anchors.length,16856);const r=f.submit();assert.equal(r.status,'completed',JSON.stringify(r));});
test('adjacent proof blocks can cover a single field',()=>{const f=photoFixture();const node=f.ptr(f.m.npc_dictionary.items[0].node);f.request.anchors=f.request.anchors.filter(a=>a.address!==node.toString());f.addAnchor(node,19);f.addAnchor(node.add(19),29);assert.equal(f.submit().status,'completed');});
test('a byte hole between split proof blocks refuses',()=>{const f=photoFixture();const node=f.ptr(f.m.npc_dictionary.items[0].node);f.request.anchors=f.request.anchors.filter(a=>a.address!==node.toString());f.addAnchor(node,19);f.addAnchor(node.add(20),28);refused(f);});
test('operations include new assists and legacy methods together',()=>{const f=photoFixture(),ops=f.api.status().operations;for(const op of ['photostone_activate','photostone_force_replay','persuasion_success','lifespan_inspect','add','alchemy_perfect'])assert.ok(ops.includes(op));});
test('64-bit query address wrap cannot claim low-address coverage',()=>{const f=photoFixture();f.api.submit(f.request);assert.equal(f.context.covered(f.ptr('0xfffffffffffffffc'),8),false);f.api.cancel();});
test('64-bit anchor address wrap is refused',()=>{const f=photoFixture();f.addAnchor(f.ptr('0xfffffffffffffffc'),8);refused(f);});
for(const force of [false,true])test('current reviewed photostone '+force,()=>{const f=photoFixture(force,true);const r=f.submit();assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(f.calls.length,2);});
for(let i=1;i<4;i++)test('current date mismatches still refuse '+i,()=>{
    const f=photoFixture(true,true),fields=f.time.readPointer().add(0x80).readPointer();
    fields.add(i*32+28).writeS32(0x04004938+i);
    const r=f.submit();assert.equal(r.status,'rejected');assert.equal(r.called,false);
    assert.ok(r.reason.includes('Game.GameTime.'+['Year','Month','Day','Unit'][i]));
    assert.equal(f.calls.length,0);
});
console.log('Interaction production bridge tests passed: '+count);
module.exports={photoFixture};
