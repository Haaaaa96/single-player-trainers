/* Integrated bridge test; mock memory only, no game or Frida. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8');
function fixture(kind='dual',current=false) {
    const evidence=require('./native_method_evidence.json').methods;
    const memory=new Map(),params=new Map(),options={},events=[];
    let next=0x9000000n,callback,timer,calls=0;
    class P {
        constructor(v) {this.value=v instanceof P?v.value:BigInt(v);}
        add(v) {return new P(this.value+BigInt(v));}
        compare(v) {const x=new P(v).value;return this.value<x?-1:this.value>x?1:0;}
        equals(v) {return this.value===new P(v).value;}
        isNull() {return this.value===0n;}
        toString() {return '0x'+this.value.toString(16);}
        readByteArray(n) {return Uint8Array.from({length:n},(_,i)=>memory.get(this.value+BigInt(i))||0).buffer;}
        writeByteArray(b) {Array.from(b).forEach((v,i)=>memory.set(this.value+BigInt(i),v));}
        readPointer() {return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE());}
        writePointer(v) {const b=Buffer.alloc(8);b.writeBigUInt64LE(new P(v).value);this.writeByteArray(b);}
        readS32() {return Buffer.from(this.readByteArray(4)).readInt32LE();}
        writeS32(v) {const b=Buffer.alloc(4);b.writeInt32LE(v);this.writeByteArray(b);}
        readU8() {return memory.get(this.value)||0;}
        writeU8(v) {this.writeByteArray([v]);}
        readU16() {return Buffer.from(this.readByteArray(2)).readUInt16LE();}
        readU64() {const v=this.readPointer().value;return {toNumber:()=>Number(v),toString:()=>v.toString()};}
        readFloat() {return Buffer.from(this.readByteArray(4)).readFloatLE();}
        writeFloat(v) {const b=Buffer.alloc(4);b.writeFloatLE(v);this.writeByteArray(b);}
        readUtf8String() {const a=[];for(let i=0;i<256;i++){const v=this.add(i).readU8();if(!v)break;a.push(v);}return Buffer.from(a).toString();}
        readUtf16String(n) {return Buffer.from(this.readByteArray(n*2)).toString('utf16le');}
    }
    const ptr=v=>new P(v), alloc=n=>{const p=ptr(next);next+=BigInt(n+16);return p;};
    function string(v) {const p=alloc(256);p.writeByteArray(Buffer.from(v+'\0'));return p;}
    function klass(ns,name) {const p=alloc(0x200);p.add(16).writePointer(string(name));p.add(24).writePointer(string(ns));return p;}
    function object(ns,name,size=0x200){const p=alloc(size);p.writePointer(klass(ns,name));return p;}
    const base=ptr(0x10000000),isDual=kind==='dual',ns='Game.UI.UPFLogic.'+(isDual?'DualCultivate':'GambleStone');
    const panel=object(ns,isDual?'DualCultivatePanel':'UPFGambleStonePanel');
    const model=object(ns,isDual?'DualCultivateGameViewModel':'UPFGambleStonePanelViewModel');
    const manager=object('Game','UIManager'),registry=alloc(32),dict=alloc(64),entries=alloc(128);
    const uiClass=manager.readPointer(),parent=alloc(0x200),sf=alloc(32),lazy=alloc(64),staticFields=alloc(32);
    const links=[];
    function link(address,value){address.writePointer(value);links.push({address:address.toString(),expected:value.toString()});}
    if(!current)link(base.add(0x8157868),uiClass);link(uiClass.add(0x58),parent);link(parent.add(0xb8),sf);link(sf,lazy);
    link(lazy.add(0x10),manager);link(uiClass.add(0xb8),staticFields);link(manager.add(0x20),registry);link(registry.add(0x10),dict);link(dict.add(0x18),entries);
    dict.add(0x20).writeS32(1);dict.add(0x2c).writeS32(5);entries.add(24).writePointer(4);
    entries.add(32).writeS32(0);entries.add(48).writePointer(panel);
    panel.add(16).writePointer(7);panel.add(0x42).writeU8(1);panel.add(0x43).writeU8(1);panel.add(0x92).writeU8(1);
    const m={manager:manager.toString(),panel:panel.toString(),vm:model.toString(),vm_class:model.readPointer().toString(),round_key:'a'.repeat(64),registry_links:links,
        registry:{dictionary:dict.toString(),entries:entries.toString(),count:1,count_address:dict.add(0x20).toString(),version_address:dict.add(0x2c).toString()}};
    const request={operation:isDual?'dual_cultivation_complete':'jade_reveal_all',token:'one-round',pid:42,deadline:Date.now()+10000,minigame:m,anchors:[]};
    const addAnchor=(p,n)=>request.anchors.push({address:p.toString(),size:n,expected_hex:Buffer.from(p.readByteArray(n)).toString('hex'),label:'proof'});
    function block(p,n){for(let o=0;o<n;o+=32)addAnchor(p.add(o),Math.min(32,n-o));}
    function list(objects){const p=object('System.Collections.Generic','List`1',64),a=alloc(32+Math.max(4,objects.length)*8);
        p.add(0x10).writePointer(a);p.add(0x18).writeS32(objects.length);p.add(0x1c).writeS32(2);a.add(24).writePointer(Math.max(4,objects.length));
        objects.forEach((x,i)=>a.add(32+i*8).writePointer(x));block(p,32);addAnchor(a.add(24),8);objects.forEach((_,i)=>addAnchor(a.add(32+i*8),8));return p;}
    let cfg,stone,record,item,bloom,crack,slots=[];
    if(isDual){
        cfg=object(ns,'DualCultivateGameConfig');cfg.add(0x10).writeS32(30);cfg.add(0x28).writeS32(100);
        panel.add(0xd8).writePointer(model);panel.add(0xe8).writePointer(0x12345);panel.add(0xf4).writeS32(100);panel.add(0xf8).writeS32(200);
        model.add(0x28).writePointer(cfg);model.add(0x30).writeS32(100);model.add(0x34).writeS32(200);model.add(0x38).writeFloat(20);
        model.add(0x40).writeFloat(10);model.add(0x44).writeS32(1);model.add(0x4c).writeU8(1);model.add(0x58).writePointer(0x54321);
        slots=[0,1,2].map(()=>{const p=object(ns,'DualCultivateSlotViewModel');p.add(0x28).writePointer(model);block(p,0x38);return p;});
        const collection=object('Loxodon.Framework.Observables','ObservableList`1'),items=list(slots);collection.add(0x38).writePointer(items);model.add(0x68).writePointer(collection);
        Object.assign(m,{config:cfg.toString(),npc_id:100,config_id:200,completed:'0x54321',final_callback:'0x12345',slots:collection.toString(),slot_objects:slots.map(x=>x.toString()),time_limit:30,required_resonance:100});
        block(cfg,0x40);block(collection,0x40);block(model,0x38);addAnchor(model.add(0x44),0x2c);
    }else{
        stone=object(ns,'GambleStoneInstance');record=object('Game.Model.Player.Components','GambleStoneSaveRecord');item=object('Game.Model.Components','GambleStoneBagItem');
        panel.add(0xc8).writePointer(model);model.add(0x28).writePointer(stone);
        stone.add(0x18).writeS32(101);stone.add(0x28).writeS32(42);stone.add(0x44).writeFloat(.25);stone.add(0x50).writeS32(100);
        stone.add(0x58).writePointer(item);stone.add(0x60).writePointer(record);stone.add(0x68).writeU8(1);stone.add(0x78).writeS32(5);stone.add(0x88).writeS32(20);
        item.add(0x38).writePointer(99);record.add(0x10).writePointer(99);record.add(0x18).writeS32(101);record.add(0x1c).writeS32(42);record.add(0x80).writeFloat(.25);record.add(0x88).writeS32(100);
        bloom=object(ns,'GambleStoneBloomInstance');crack=object(ns,'GambleStoneCrackInstance');bloom.add(0x10).writePointer(0xbeef);crack.add(0x10).writePointer(0xcafe);
        stone.add(0x98).writePointer(list([bloom]));stone.add(0xa0).writePointer(list([crack]));block(bloom,0x40);block(crack,0x40);
        Object.assign(m,{stone:stone.toString(),source:item.toString(),record:record.toString(),instance_id:'99',source_uid:'1234',item_id:101,seed:42,ratio_before:.25,value_before:100,
            record_ratio_address:record.add(0x80).toString(),record_value_address:record.add(0x88).toString(),features:[
                {address:bloom.toString(),config:'0xbeef',seen:bloom.add(0x1c).toString(),kind:'Blooms'},
                {address:crack.toString(),config:'0xcafe',seen:crack.add(0x2c).toString(),kind:'Cracks'}]});
        m.flags=['m_CanScratch','m_ExchangeChoiceVisible','m_ExchangeResultVisible','m_ScratchSessionActive','m_ScratchDirty','m_HasPendingScratchSettlement'].map((label,i)=>{
            const offsets=current?[0xf8,0xfa,0xfb,0x121,0x123,0x124]:[0x110,0x112,0x113,0x139,0x13b,0x13c];
            const p=model.add(offsets[i]);p.writeU8(i===0?1:0);return {address:p.toString(),expected:i===0,label};});
        block(stone,0xb0);block(record,0xb0);block(item,0x40);block(model,0x160);
    }
    let spec=isDual?{name:'Complete',token:0x06010d8c,rva:0xac8b00,argc:1,prefix:'48895c2418554883ec30803d99e8a707'}:
        {name:'RevealAll',token:0x06010584,rva:0xa86210,argc:0,prefix:'40534883ec3033d2488bd9e8607cffff'};
    if(current)spec={...spec,...evidence[spec.token]};
    const method=alloc(0x80),returnType=alloc(16),param=alloc(16);
    method.writePointer(base.add(spec.rva));method.add(0x18).writePointer(string(spec.name));method.add(0x20).writePointer(model.readPointer());method.add(0x28).writePointer(returnType);
    method.add(0x48).writeS32(spec.token);method.add(0x4c).writeU8(0x86);method.add(0x52).writeU8(spec.argc);returnType.add(10).writeU8(1);param.add(10).writeU8(2);param.add(11).writeU8(0x80);
    params.set(method.toString(),param);base.add(spec.rva).writeByteArray(Buffer.from(spec.prefix,'hex'));
    Object.assign(request,{method_info:method.toString(),method_token:spec.token,method_rva:spec.rva,parameter_count:spec.argc});
    for(const [rva,code] of [[0x14342d0,'48895c2408574883ec60488bd9'],[0xacb6d0,'40565741574883ec50803d94bca70700'],[0xacbe20,'4053574883ec7880b9f000000000488b'],[0xacc100,'40535556574883ec68803d6ab2a70700'],
        [0xa9c140,'48895c2408574881ecc0000000803d18'],[0xa9cc30,'488bc44c8948204c8940184889480853'],[0xa9ebf0,'488bc448895810488970204889480857']]){const v=current?Object.values(evidence).find(v=>v.legacy_rva===rva):null;base.add(current&&rva===0x14342d0?0x1464640:v?.rva??rva).writeByteArray(Buffer.from(v?.prefix??code,'hex'));}
    block(panel,0x100);block(manager,0x40);links.forEach(l=>addAnchor(ptr(l.address),8));addAnchor(dict.add(0x20),4);addAnchor(dict.add(0x2c),4);addAnchor(entries.add(32),24);
    const context={ptr,Process:{id:42,arch:'x64',platform:'windows',pointerSize:8,getCurrentThreadId:()=>99,getModuleByName:()=>({base,getExportByName:n=>n})},Memory:{alloc},
        NativeFunction:function(name){
            if(name==='il2cpp_method_get_param_count')return m=>m.add(0x52).readU8();
            if(name==='il2cpp_method_get_token')return m=>m.add(0x48).readS32();
            if(name==='il2cpp_method_get_param')return m=>params.get(m.toString())||ptr(0);
            if(name==='il2cpp_class_from_type')return ()=>options.vectorClass||ptr(0);
            assert.equal(name,'il2cpp_runtime_invoke');return (mi,target,args,exception)=>{
                if(options.invoke)return options.invoke(mi,target,args,exception);
                calls++;assert.ok(mi.equals(method));assert.ok(target.equals(model));
                if(isDual)assert.equal(args.readPointer().readU8(),1);else assert.ok(args.isNull());
                if(options.throw)throw new Error('native exception');
                if(!options.noChange){
                    if(isDual){model.add(0x44).writeS32(2);panel.add(0xf0).writeU8(1);panel.add(0xf2).writeU8(1);}
                    else {stone.add(0x44).writeFloat(1);record.add(0x80).writeFloat(1);stone.add(0x50).writeS32(70);record.add(0x88).writeS32(70);stone.add(0x78).writeS32(20);bloom.add(0x1c).writeU8(1);crack.add(0x2c).writeU8(1);}
                }
                if(options.after)options.after();exception.writePointer(options.exception?0x123:0);return options.returnValue?ptr(1):ptr(0);
            };
        },Interceptor:{attach:(_p,h)=>{callback=h.onEnter;return {detach:()=>{}};}},rpc:{exports:{}},send:p=>events.push(p),
        setTimeout:f=>{timer=f;return 1;},clearTimeout:()=>{},Uint8Array,Date,Number,Array};
    vm.createContext(context);vm.runInContext(source,context);
    return {api:context.rpc.exports,request,events,options,base,panel,model,manager,entries,dict,method,param,returnType,stone,record,item,bloom,crack,cfg,slots,ptr,
        alloc,klass,object,string,params,addAnchor,block,
        run:()=>callback(),expire:()=>timer(),get calls(){return calls;},sync:()=>request.anchors.forEach(a=>a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex'))};
}
module.exports={fixture};
if(require.main===module){
let tests=0;
function test(name,fn){try{fn();tests++;}catch(e){e.message=name+': '+e.message;throw e;}}
function run(f){f.api.submit(f.request);f.run();return f.events.at(-1);}
for(const kind of ['dual','jade']){
    test(kind+' invokes normal original action once',()=>{const f=fixture(kind),r=run(f);assert.equal(r.status,'completed',JSON.stringify(r));f.run();assert.equal(f.calls,1);assert.equal(r.round_key,'a'.repeat(64));assert.equal(r.called,true);});
    for(const o of [0x42,0x43,0x92])test(kind+' inactive flag '+o,()=>{const f=fixture(kind);f.panel.add(o).writeU8(0);f.sync();assert.equal(run(f).called,false);assert.equal(f.calls,0);});
    for(const o of [0x58,0x93])test(kind+' hidden or paused '+o,()=>{const f=fixture(kind);f.panel.add(o).writeU8(1);f.sync();assert.equal(run(f).called,false);assert.equal(f.calls,0);});
    test(kind+' stale proof rejects',()=>{const f=fixture(kind);f.panel.add(16).writePointer(8);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
    test(kind+' missing registry anchor rejects',()=>{const f=fixture(kind);f.request.anchors=f.request.anchors.filter(a=>a.address!==f.base.add(0x8157868).toString());assert.equal(run(f).called,false);});
    test(kind+' registry panel changed rejects',()=>{const f=fixture(kind);f.entries.add(48).writePointer(9);f.sync();assert.equal(run(f).called,false);});
    for(const flag of [0x20,0x40])test(kind+' bad return flag '+flag,()=>{const f=fixture(kind);f.returnType.add(11).writeU8(flag);assert.equal(run(f).called,false);});
    test(kind+' static method rejects',()=>{const f=fixture(kind);f.method.add(0x4c).writeU8(0x96);assert.equal(run(f).called,false);});
    for(const option of ['throw','noChange','returnValue'])test(kind+' after invocation '+option+' is unknown',()=>{const f=fixture(kind);f.options[option]=true;const r=run(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.equal(f.calls,1);assert.throws(()=>f.api.reset(f.request.token));f.run();assert.equal(f.calls,1);});
    test(kind+' managed exception locks',()=>{const f=fixture(kind);f.options.exception=true;assert.equal(run(f).status,'exception');assert.throws(()=>f.api.reset(f.request.token));});
    test(kind+' timeout before Update is safe',()=>{const f=fixture(kind);f.api.submit(f.request);f.expire();f.run();assert.equal(f.events[0].called,false);assert.equal(f.calls,0);});
    test(kind+' expired deadline safe',()=>{const f=fixture(kind);f.request.deadline=Date.now()-1;assert.equal(run(f).called,false);assert.equal(f.calls,0);});
    test(kind+' cancelled safe',()=>{const f=fixture(kind);f.api.submit(f.request);f.api.cancel();f.run();assert.equal(f.events[0].called,false);assert.equal(f.calls,0);});
    test(kind+' cannot replay same token',()=>{const f=fixture(kind);run(f);f.api.reset(f.request.token);assert.throws(()=>f.api.submit(f.request),/already used/);});
}
for(const flag of [0x20,0x40])test('dual malformed Boolean parameter '+flag,()=>{const f=fixture();f.param.add(11).writeU8(0x80|flag);assert.equal(run(f).called,false);});
test('dual time elapsed rejects',()=>{const f=fixture();f.model.add(0x38).writeFloat(0);f.sync();assert.equal(run(f).called,false);});
test('dual wrong slot owner rejects',()=>{const f=fixture();f.slots[0].add(0x28).writePointer(99);f.sync();assert.equal(run(f).called,false);});
test('dual already settling rejects',()=>{const f=fixture();f.panel.add(0xf0).writeU8(1);f.sync();assert.equal(run(f).called,false);});
test('dual normal null optional action callback completes',()=>{const f=fixture();f.panel.add(0xe8).writePointer(0);f.request.minigame.final_callback='0x0';f.sync();const r=run(f);assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(f.calls,1);});
test('dual null optional callback identity change still rejects',()=>{const f=fixture();f.request.minigame.final_callback='0x0';f.sync();assert.equal(run(f).called,false);assert.equal(f.calls,0);});
test('dual missing actual settlement callback still rejects',()=>{const f=fixture();f.model.add(0x58).writePointer(0);f.request.minigame.completed='0x0';f.sync();assert.equal(run(f).called,false);assert.equal(f.calls,0);});
test('dual win without normal settlement unknown',()=>{const f=fixture();f.options.after=()=>f.panel.add(0xf0).writeU8(0);assert.equal(run(f).status,'unknown');});
test('jade preserves innate configs and accepts natural lower valuation',()=>{const f=fixture('jade');const r=run(f);assert.equal(r.current_value,70);assert.equal(f.bloom.add(0x10).readPointer().toString(),'0xbeef');assert.equal(f.crack.add(0x10).readPointer().toString(),'0xcafe');assert.equal(f.stone.add(0x28).readS32(),42);});
for(const i of [0,1,2,3,4,5])test('jade activity '+i+' refuses',()=>{const f=fixture('jade'),flag=f.request.minigame.flags[i];f.ptr(flag.address).writeU8(flag.expected?0:1);f.sync();assert.equal(run(f).called,false);});
test('jade wrong flag address cannot substitute proof',()=>{const f=fixture('jade');f.request.minigame.flags[1].address=f.panel.add(0x93).toString();assert.equal(run(f).called,false);});
test('jade wrong persistent identity refuses',()=>{const f=fixture('jade');f.record.add(0x10).writePointer(100);f.sync();assert.equal(run(f).called,false);});
test('jade generation pending refuses',()=>{const f=fixture('jade');f.record.add(0x20).writeU8(1);f.sync();assert.equal(run(f).called,false);});
for(const o of [0x49,0x44])test('jade exchanged or full refuses '+o,()=>{const f=fixture('jade');if(o===0x49)f.stone.add(o).writeU8(1);else f.stone.add(o).writeFloat(1);f.sync();assert.equal(run(f).called,false);});
for(const change of ['natural_config','seen','mask','record_value','record_ratio','selection'])test('jade post '+change+' unknown',()=>{const f=fixture('jade');f.options.after=()=>{
    if(change==='natural_config')f.crack.add(0x10).writePointer(1);if(change==='seen')f.crack.add(0x2c).writeU8(0);
    if(change==='mask')f.stone.add(0x78).writeS32(19);if(change==='record_value')f.record.add(0x88).writeS32(71);
    if(change==='record_ratio')f.record.add(0x80).writeFloat(.5);if(change==='selection')f.model.add(0x28).writePointer(1);
};assert.equal(run(f).status,'unknown');assert.equal(f.calls,1);});
for(const kind of ['dual','jade'])test('current '+kind+' entries and canonical root',()=>{const f=fixture(kind,true);f.api.submit(f.request);f.run();const r=f.events.at(-1);assert.equal(r.status,'completed',JSON.stringify(r));});
for(const current of [false,true]){
    for(let i=0;i<6;i++)test('jade '+(current?'current':'legacy')+' rejects other layout field '+i,()=>{
        const f=fixture('jade',current),other=current?[0x110,0x112,0x113,0x139,0x13b,0x13c]:[0xf8,0xfa,0xfb,0x121,0x123,0x124];
        f.request.minigame.flags[i].address=f.model.add(other[i]).toString();
        const r=run(f);assert.equal(r.called,false);assert.equal(f.calls,0);assert.match(r.reason,/Jade activity field differs/);
    });
}
for(let i=0;i<6;i++)test('current jade busy flag '+i+' blocks before call',()=>{
    const f=fixture('jade',true),flag=f.request.minigame.flags[i];
    f.ptr(flag.address).writeU8(flag.expected?0:1);f.sync();
    assert.equal(run(f).called,false);assert.equal(f.calls,0);
});
console.log('Dual/jade integrated bridge tests passed: '+tests);
}
