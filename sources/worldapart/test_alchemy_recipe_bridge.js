/* Offline production-bridge tests. Reuse mock memory only; no Frida access. */
'use strict';
const assert=require('node:assert/strict');
const {fixture:memoryFixture}=require('./test_dual_jade_bridge.js');
const legacySpecs=require('./alchemy_recipe_specs.json').methods;
function fixture(current=false){
    const specs=Object.fromEntries(Object.entries(legacySpecs).map(([k,s])=>[k,current?{...s,...require('./native_method_evidence.json').methods[s.token]}:s]));
    const f=memoryFixture('jade',current),{object,alloc,klass,string,ptr,block,addAnchor}=f;
    const ns='Game.Logic.RefiningPills.Map',ui='Game.UI.UPFLogic.RefiningPills';
    const panel=object(ui,'UPFRefiningPillsExplorePanel',0x500),move=object(ns,'RefiningPillsMovementController',0x300),state=object(ns,'RefiningPillsExploreState');
    const data=object(ns,'RefiningPillsMapDataset'),model=object(ui,'UPFRefiningPillsExplorePanelViewModel');
    const list=object(ns,'RefiningPillsPoiList'),array=alloc(32+2*36),pool=alloc(40),text=object('System','String',64);
    const m=f.request.minigame;
    panel.add(16).writePointer(7);panel.add(0x42).writeU8(1);panel.add(0x43).writeU8(1);panel.add(0x92).writeU8(1);
    panel.add(0x1c0).writePointer(data);panel.add(0x220).writePointer(move);panel.add(0x228).writePointer(state);panel.add(0x138).writePointer(model);panel.add(0x278).writeS32(5);
    move.add(32).writePointer(data);move.add(40).writePointer(state);move.add(56).writeFloat(50);move.add(120).writeFloat(100);move.add(124).writeFloat(200);
    data.add(40).writePointer(list);list.add(16).writePointer(array);array.add(24).writePointer(2);
    data.add(56).writePointer(pool);pool.add(24).writePointer(1);pool.add(32).writePointer(text);
    text.add(16).writeS32(7);text.add(20).writeByteArray(Buffer.from('1000002','utf16le'));
    const candidate={index:0,poi_id:378,kind:2,tier:1,string_index:0,x:5007,y:4751,recipe_id:1000002,name:'回元散'};
    const poi=array.add(32);poi.writeS32(378);poi.add(4).writeU8(2);poi.add(6).writeU8(1);poi.add(12).writeS32(0);poi.add(16).writeS32(candidate.x);poi.add(20).writeS32(candidate.y);
    const other=array.add(68);other.writeS32(400);other.add(4).writeU8(1);other.add(16).writeS32(9000);other.add(20).writeS32(9000);
    const callbacks=[move.add(0x208),move.add(0x218),move.add(0x220),state.add(112)];callbacks.forEach((p,i)=>p.writePointer(0x40000+i*16));
    f.entries.add(48).writePointer(panel);
    Object.assign(m,{panel:panel.toString(),move:move.toString(),state:state.toString(),dataset:data.toString(),vm:model.toString(),panel_class:panel.readPointer().toString(),move_class:move.readPointer().toString(),
        array:array.toString(),count:2,radius:50,furnace:5,candidate,callbacks:callbacks.map(p=>p.readPointer().toString()),position:[100,200],methods:{}});
    const methods={},returns={},argumentsTypes={};
    for(const [key,s]of Object.entries(specs)){
        const p=alloc(0x80),t=alloc(16);p.writePointer(f.base.add(s.rva));p.add(0x18).writePointer(string(s.name));p.add(0x20).writePointer((key==='available'?panel:move).readPointer());p.add(0x28).writePointer(t);
        p.add(0x48).writeS32(s.token);p.add(0x4c).writeU8(0x86);p.add(0x52).writeU8(s.argc);t.add(10).writeU8(s.returns);t.add(11).writeU8(s.returns===2?0x80:0);
        if(s.argc){const a=alloc(16);a.add(10).writeU8(key==='teleport'?0x11:8);a.add(11).writeU8(0x80);f.params.set(p.toString(),a);argumentsTypes[key]=a;}
        f.base.add(s.rva).writeByteArray(Buffer.from(s.prefix,'hex'));m.methods[key]=p.toString();methods[key]=p;returns[key]=t;
    }
    const vector=klass('UnityEngine','Vector2');vector.add(0xf8).writeS32(24);f.options.vectorClass=vector;
    Object.assign(f.request,{operation:'alchemy_find_recipe',method_info:m.methods.teleport,method_token:specs.teleport.token,method_rva:specs.teleport.rva,parameter_count:1});
    for(const [p,n]of [[panel,0x460],[move,0x250],[state,128],[model,0x180],[data,64],[list,32],[pool,40],[text,40]])block(p,n);
    addAnchor(array.add(24),8);addAnchor(array.add(32),36);addAnchor(array.add(68),36);addAnchor(text.add(20),14);
    f.sync();const calls=[];const options=f.options;
    options.invoke=(mi,target,args,exception)=>{
        const key=Object.keys(methods).find(k=>methods[k].equals(mi));assert.ok(key);calls.push(key);
        assert.ok(target.equals(key==='available'?panel:move));exception.writePointer(options.exception===key?0x123:0);
        if(options.throw===key)throw new Error('native fault '+key);
        if(key==='available'){
            assert.equal(args.readPointer().readS32(),candidate.index);
            if(options.afterAvailable)options.afterAvailable();if(options.availableNull)return ptr(0);
            const b=object('System',options.availableType?'Int32':'Boolean',24);b.add(16).writeU8(options.disabled?0:1);return b;
        }
        if(key==='teleport'){
            assert.equal(args.readPointer().readFloat(),candidate.x);assert.equal(args.readPointer().add(4).readFloat(),candidate.y);
            if(!options.noTeleport){move.add(120).writeFloat(candidate.x);move.add(124).writeFloat(candidate.y);}
            if(options.afterTeleport)options.afterTeleport();
        }else{
            assert.ok(args.isNull());if(!options.noCollect){state.add(20).writeS32(candidate.recipe_id);state.add(93).writeU8(1);model.add(0x90).writeU8(1);}
            if(options.afterCollect)options.afterCollect();
        }
        return options.returnValue===key?ptr(1):ptr(0);
    };
    return Object.assign({...f},{panel,move,state,data,model,poi,other,pool,text,candidate,methods,returns,argumentsTypes,vector,calls});
}
let count=0;
function test(name,fn){try{fn();count++;}catch(e){e.message=name+': '+e.message;throw e;}}
function run(f){f.api.submit(f.request);f.run();return f.events.at(-1);}
test('available teleport collect once in order',()=>{const f=fixture(),r=run(f);assert.equal(r.status,'completed',JSON.stringify(r));assert.deepEqual(f.calls,['available','teleport','collect']);assert.equal(r.recipe_id,1000002);f.run();assert.equal(f.calls.length,3);});
for(const key of ['teleport','collect','available']){
    test(key+' static refuses',()=>{const f=fixture();f.methods[key].add(0x4c).writeU8(0x96);assert.equal(run(f).called,false);assert.deepEqual(f.calls,[]);});
    for(const flags of [0x20,0x40])test(key+' return flags '+flags,()=>{const f=fixture();f.returns[key].add(11).writeU8(flags);assert.equal(run(f).called,false);assert.deepEqual(f.calls,[]);});
}
for(const flag of [0x20,0x40])test('Vector2 byref/pinned '+flag,()=>{const f=fixture();f.argumentsTypes.teleport.add(11).writeU8(0x80|flag);assert.equal(run(f).called,false);});
test('wrong Vector2 layout rejected',()=>{const f=fixture();f.vector.add(0xf8).writeS32(28);assert.equal(run(f).called,false);});
for(const which of ['disabled','availableNull','availableType'])test('readonly '+which+' rejects without mutation',()=>{const f=fixture();f.options[which]=true;const r=run(f);assert.equal(r.called,false);assert.equal(r.status,'rejected');assert.deepEqual(f.calls,['available']);});
test('readonly availability throw is called false',()=>{const f=fixture();f.options.throw='available';assert.equal(run(f).called,false);});
test('readonly availability exception is called false',()=>{const f=fixture();f.options.exception='available';assert.equal(run(f).called,false);});
test('state changes in getter rejects before teleport',()=>{const f=fixture();f.options.afterAvailable=()=>f.panel.add(0x93).writeU8(1);assert.equal(run(f).called,false);assert.deepEqual(f.calls,['available']);});
for(const which of ['portal','covered','explosion','moving','old_recipe','recipe_card','obtained','phase','paused'])test('guard '+which,()=>{const f=fixture();
    if(which==='portal')f.panel.add(0x34c).writeU8(1);if(which==='covered')f.panel.add(0x369).writeU8(1);if(which==='explosion')f.model.add(0x171).writeU8(1);
    if(which==='moving')f.move.add(0xc1).writeU8(1);if(which==='old_recipe')f.state.add(20).writeS32(5);if(which==='recipe_card')f.model.add(0x90).writeU8(1);
    if(which==='obtained')f.state.add(93).writeU8(1);if(which==='phase')f.move.add(0xc0).writeU8(1);if(which==='paused')f.panel.add(0x93).writeU8(1);
    f.sync();assert.equal(run(f).called,false);assert.deepEqual(f.calls,[]);
});
for(const distance of [0,49,50])test('overlap at '+distance+' refuses',()=>{const f=fixture();f.other.add(16).writeS32(f.candidate.x+distance);f.other.add(20).writeS32(f.candidate.y);f.sync();assert.equal(run(f).called,false);assert.deepEqual(f.calls,[]);});
test('outside radius accepted',()=>{const f=fixture();f.other.add(16).writeS32(f.candidate.x+51);f.other.add(20).writeS32(f.candidate.y);f.sync();assert.equal(run(f).status,'completed');});
test('wrong recipe string refuses',()=>{const f=fixture();f.text.add(20).writeByteArray(Buffer.from('1000003','utf16le'));f.sync();assert.equal(run(f).called,false);});
test('recipe above furnace tier refuses',()=>{const f=fixture();f.poi.add(6).writeU8(6);f.candidate.tier=6;f.sync();assert.equal(run(f).called,false);});
for(const which of ['throw','exception','returnValue'])for(const method of ['teleport','collect'])test(method+' '+which+' uncertain and locked',()=>{
    const f=fixture();f.options[which]=method;const r=run(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.throws(()=>f.api.reset(f.request.token));
    if(method==='teleport')assert.deepEqual(f.calls,['available','teleport']);
});
for(const which of ['move','dataset','state','vm','paused','phase','position','already_recipe'])test('post teleport '+which+' stops before collect',()=>{
    const f=fixture();f.options.afterTeleport=()=>{
        if(which==='move')f.panel.add(0x220).writePointer(0);if(which==='dataset')f.move.add(32).writePointer(0);
        if(which==='state')f.panel.add(0x228).writePointer(0);if(which==='vm')f.panel.add(0x138).writePointer(0);
        if(which==='paused')f.panel.add(0x93).writeU8(1);if(which==='phase')f.move.add(0xc0).writeU8(1);
        if(which==='position')f.move.add(120).writeFloat(999);if(which==='already_recipe')f.state.add(20).writeS32(123);
    };const r=run(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.deepEqual(f.calls,['available','teleport']);
});
test('post collect wrong recipe unknown',()=>{const f=fixture();f.options.afterCollect=()=>f.state.add(20).writeS32(123);assert.equal(run(f).status,'unknown');});
test('post collect owner changed unknown',()=>{const f=fixture();f.options.afterCollect=()=>f.panel.add(0x228).writePointer(0);assert.equal(run(f).status,'unknown');});
test('no collection not success',()=>{const f=fixture();f.options.noCollect=true;assert.equal(run(f).status,'unknown');});
test('cancel before Update no native call',()=>{const f=fixture();f.api.submit(f.request);f.api.cancel();f.run();assert.deepEqual(f.calls,[]);assert.equal(f.events[0].called,false);});
test('deadline safe before readonly getter',()=>{const f=fixture();f.request.deadline=Date.now()-1;assert.equal(run(f).called,false);assert.deepEqual(f.calls,[]);});
test('same token cannot be reused',()=>{const f=fixture();run(f);f.api.reset(f.request.token);assert.throws(()=>f.api.submit(f.request),/already used/);});
test('current recipe three reviewed roles',()=>{const f=fixture(true),r=run(f);assert.equal(r.status,'completed',JSON.stringify(r));assert.deepEqual(f.calls,['available','teleport','collect']);});
console.log('Alchemy recipe integrated bridge tests passed: '+count);
