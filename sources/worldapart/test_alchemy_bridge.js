/* Real packaged bridge in a pure-memory Frida model: never opens a process. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8');
const specs=JSON.parse(fs.readFileSync(path.join(__dirname,'alchemy_specs.json'),'utf8')).methods;
function fixture(talent=false,current=false) {
    const bytes=new Map(),emitted=[],params=new Map();let next=0x10000000n,callback,timer,calls=0;
    const options={};
    const shift=o=>current&&o>=0x108?o+8:o;
    class P {
        constructor(v){this.value=v instanceof P?v.value:BigInt(v);}
        add(n){return new P(this.value+BigInt(n));} equals(p){return this.value===new P(p).value;}
        compare(p){const b=new P(p).value;return this.value<b?-1:this.value>b?1:0;}
        isNull(){return this.value===0n;}toString(){return '0x'+this.value.toString(16);}
        readByteArray(n){return Uint8Array.from({length:n},(_,i)=>bytes.get(this.value+BigInt(i))||0).buffer;}
        writeByteArray(v){Array.from(v).forEach((b,i)=>bytes.set(this.value+BigInt(i),b));}
        readU8(){return bytes.get(this.value)||0;}writeU8(v){this.writeByteArray([v]);}
        readU16(){return Buffer.from(this.readByteArray(2)).readUInt16LE();}
        readS32(){return Buffer.from(this.readByteArray(4)).readInt32LE();}
        writeS32(v){const b=Buffer.alloc(4);b.writeInt32LE(v);this.writeByteArray(b);}
        readFloat(){return Buffer.from(this.readByteArray(4)).readFloatLE();}
        writeFloat(v){if(options.storeThrow && this.value===0x40000e8n && v===1000)throw new Error('scalar store error');const b=Buffer.alloc(4);b.writeFloatLE(v);this.writeByteArray(b);}
        readPointer(){return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE());}
        writePointer(v){const b=Buffer.alloc(8);b.writeBigUInt64LE(new P(v).value);this.writeByteArray(b);}
        readU64(){const x=Buffer.from(this.readByteArray(8)).readBigUInt64LE();return{toNumber:()=>Number(x)};}
        readUtf8String(){const a=[];for(let i=0;i<256;i++){const b=this.add(i).readU8();if(!b)break;a.push(b);}return Buffer.from(a).toString('utf8');}
    }
    const ptr=v=>new P(v),alloc=n=>{const p=ptr(next);next+=BigInt(n+32);return p;};
    function klass(ns,name){const p=alloc(512),n=alloc(256),s=alloc(256);n.writeByteArray(Buffer.from(name+'\0'));s.writeByteArray(Buffer.from(ns+'\0'));p.add(16).writePointer(n);p.add(24).writePointer(s);return p;}
    const base=ptr(0x1000000),panel=ptr(0x4000000),context=ptr(0x4010000),recipe=ptr(0x4020000),operation=ptr(0x4030000),stages=ptr(0x4040000),maximum=ptr(0x4050000);
    const manager=ptr(0x4100000),registry=ptr(0x4110000),array=ptr(0x4120000),dictionary=ptr(0x4130000),entries=ptr(0x4140000),player=ptr(0x4150000),model=ptr(0x4160000);
    const panelClass=klass('Game.UI.UPFLogic.RefiningPills','UPFRefiningPillsQtePanel'),modelClass=klass('Game.Model.Player.Components','RefiningPillsModel'),dictClass=klass('System.Collections.Generic','Dictionary`2');
    panel.writePointer(panelClass);panel.add(16).writePointer(0xBEEF);panel.add(0x42).writeU8(talent?0:1);panel.add(0x43).writeU8(1);panel.add(0x92).writeU8(1);panel.add(0xa8).writeS32(10);
    panel.add(0xd0).writePointer(stages);stages.add(0x18).writeS32(3);panel.add(0xe4).writeFloat(15);panel.add(0xe8).writeFloat(123);panel.add(0x106).writeU8(1);
    panel.add(shift(0x108)).writeFloat(7);panel.add(shift(0x10c)).writeFloat(45);panel.add(shift(0x118)).writeFloat(300);panel.add(shift(0x11c)).writeFloat(600);panel.add(shift(0x120)).writeFloat(900);
    panel.add(shift(0x148)).writePointer(context);panel.add(shift(0x150)).writePointer(0xBEEF000);context.writePointer(klass('Game','CondenseContext'));context.add(0x18).writePointer(recipe);
    recipe.writePointer(klass('Game','RefiningPillsRecipeCardModel'));context.add(0x50).writePointer(0xCAFE);context.add(0x60).writeU8(1);context.add(0x68).writePointer(operation);
    operation.writePointer(klass('System','String'));operation.add(16).writeS32(5);operation.add(20).writeByteArray(Buffer.from('round','utf16le'));maximum.writeS32(1000);
    manager.writePointer(klass('Game','UIManager'));registry.add(0x18).writePointer(array);registry.add(0x20).writeS32(1);array.add(24).writePointer(16);array.add(32).writeS32(1);array.add(48).writePointer(panel);
    player.writePointer(klass('Game.Model','PlayerModel'));player.add(0x60).writePointer(model);model.writePointer(modelClass);model.add(0x18).writeS32(5);model.add(0x28).writePointer(dictionary);
    dictionary.writePointer(dictClass);dictionary.add(24).writePointer(entries);dictionary.add(32).writeS32(1);entries.add(24).writePointer(16);
    function entry(i,id,rank){const e=entries.add(32+16*i);e.writeS32(id);e.add(4).writeS32(-1);e.add(8).writeS32(id);e.add(12).writeS32(rank);}
    entry(0,1000002,1);
    const links=[];
    for(const [i,value] of [manager,registry,array,manager,registry,array,manager,registry].entries()){
        const addr=i===0?base.add(0x8157868):ptr(0x4200000+i*16);addr.writePointer(value);links.push({address:addr.toString(),expected:value.toString()});
    }
    const old=talent?specs.SetTalentRank:specs.FinishQte,s=current?{...old,...require('./native_method_evidence.json').methods[old.token]}:old,method=alloc(128),name=alloc(256),returnType=alloc(16),parameterTypes=[];
    name.writeByteArray(Buffer.from(s.name+'\0'));method.writePointer(base.add(s.rva));method.add(0x18).writePointer(name);method.add(0x20).writePointer(talent?modelClass:panelClass);
    returnType.add(10).writeU8(1);method.add(0x28).writePointer(returnType);method.add(0x48).writeS32(s.token);method.add(0x4c).writeByteArray([0x86,0]);method.add(0x52).writeU8(s.argc);
    for(let i=0;i<s.argc;i++){const p=alloc(16);p.add(10).writeU8(8);p.add(11).writeU8(0x80);parameterTypes.push(p);}params.set(method.toString(),parameterTypes);
    base.add(s.rva).writeByteArray(Buffer.from(s.prefix,'hex'));base.add(current?0x1464640:0x14342d0).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    const m={panel:panel.toString(),panel_class:panelClass.toString(),context:context.toString(),recipe:recipe.toString(),operation_id:operation.toString(),callback:'0xbeef000',
        manager:manager.toString(),handle:10,maximum:1000,maximum_address:maximum.toString(),stage_count:3,stages:stages.toString(),round_key:'a'.repeat(64),registry_links:links,
        registry:{dictionary:registry.toString(),entries:array.toString(),count:1,count_address:registry.add(32).toString(),version_address:registry.add(44).toString()}};
    if(talent)Object.assign(m,{player:player.toString(),model:model.toString(),model_class:modelClass.toString(),dictionary:dictionary.toString(),level:5,talent_id:1000001,rank:2,before:0,maximum:2,
        observed_panels:[{panel:panel.toString(),name:'UPFRefiningPillsQtePanel',showing:false}]});
    const request={operation:talent?'alchemy_talent_set':'alchemy_perfect',token:'one',pid:12,minigame:m,method_info:method.toString(),method_token:s.token,method_rva:s.rva,parameter_count:s.argc,
        deadline:Date.now()+10000,anchors:[]};
    function anchor(a,n){request.anchors.push({address:a.toString(),size:n,expected_hex:Buffer.from(a.readByteArray(n)).toString('hex')});}
    for(const l of links)anchor(ptr(l.address),8);
    anchor(manager.add(0x18),1);anchor(registry.add(32),4);anchor(registry.add(44),4);anchor(array.add(32),24);
    if(!talent)for(const [p,n] of [[panel,8],[panel.add(16),8],[panel.add(0x42),1],[panel.add(0x43),1],[panel.add(0x58),1],[panel.add(0x92),1],[panel.add(0x93),1],
        [panel.add(0xa8),4],[panel.add(0xd0),8],[panel.add(shift(0x148)),8],[panel.add(shift(0x150)),8],[panel.add(0x106),1],[panel.add(shift(0x158)),1],[panel.add(shift(0x159)),1],[panel.add(shift(0x15a)),1],[panel.add(shift(0x208)),1],
        [panel.add(shift(0x118)),4],[panel.add(shift(0x11c)),4],[panel.add(shift(0x120)),4],[context,8],[context.add(0x18),8],[context.add(0x50),8],[context.add(0x60),1],[context.add(0x68),8],[context.add(0x70),1],
        [maximum,4],[operation,8],[operation.add(16),4],[operation.add(20),10],[stages.add(24),4]])anchor(p,n);
    else for(const [p,n] of [[panel.add(0x42),1],[player,8],[player.add(0x60),8],[model,8],[model.add(0x18),4],[model.add(0x28),8],[dictionary,8],[dictionary.add(24),8],[dictionary.add(32),4],
        [dictionary.add(40),4],[dictionary.add(44),4],[entries.add(24),8],[entries.add(32),16]])anchor(p,n);
    if(!talent && current)anchor(panel.add(0x10c),1);
    function invoke(_method,target,args,exception){calls++;exception.writePointer(0);
        if(options.throw)throw new Error('native failed');if(options.exception)exception.writePointer(0xDEAD);
        if(talent){assert.ok(target.equals(model));const id=args.readPointer().readS32(),rank=args.add(8).readPointer().readS32();
            if(model.add(0x28).readPointer().isNull()){model.add(0x28).writePointer(dictionary);dictionary.add(32).writeS32(0);dictionary.add(40).writeS32(0);}
            const n=dictionary.add(32).readS32();let index=-1;
            for(let i=0;i<n;i++){const e=entries.add(32+16*i);if(e.readS32()>=0 && e.add(8).readS32()===id)index=i;}
            if(rank===0){if(index>=0){entries.add(32+16*index).writeS32(-1);dictionary.add(40).writeS32(dictionary.add(40).readS32()+1);}}
            else{if(index<0){index=n;dictionary.add(32).writeS32(n+1);}entry(index,id,options.wrongRank?1:rank);}
            if(options.otherTalent)entries.add(44).writeS32(2);
        }else{assert.ok(target.equals(panel));assert.equal(panel.add(0xe8).readFloat(),1000);assert.equal(panel.add(shift(0x108)).readFloat(),7);
            if(!options.stillRunning)panel.add(0x106).writeU8(0);
            if(!options.noResult)panel.add(shift(options.deferred?0x158:0x159)).writeU8(1);
            if(options.wrongProgress)panel.add(0xe8).writeFloat(999);
        }return ptr(0);
    }
    const ctx={Process:{id:12,arch:'x64',platform:'windows',pointerSize:8,getCurrentThreadId:()=>1,getModuleByName:()=>({base,getExportByName:n=>n})},ptr,Memory:{alloc},
        NativeFunction:function(n){if(n==='il2cpp_method_get_param_count')return m=>m.add(0x52).readU8();if(n==='il2cpp_method_get_token')return m=>m.add(0x48).readS32();
            if(n==='il2cpp_method_get_param')return(m,i)=>params.get(m.toString())[i];if(n==='il2cpp_class_from_type')return()=>ptr(0);return invoke;},
        Interceptor:{attach:(_a,c)=>{callback=c.onEnter;return{detach:()=>{}};}},rpc:{exports:{}},send:v=>emitted.push(v),setTimeout:f=>{timer=f;return 1;},clearTimeout:()=>{},Uint8Array,Date,Number,Array};
    vm.createContext(ctx);vm.runInContext(source,ctx);
    return {request,m,options,panel,context,operation,maximum,stages,player,model,dictionary,entries,parameterTypes,method,returnType,base,emitted,get calls(){return calls;},api:ctx.rpc.exports,
        run:()=>callback(),expire:()=>timer(),sync:()=>request.anchors.forEach(a=>a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex'))};
}
let count=0;function test(n,fn){try{fn();count++;}catch(e){e.message=n+': '+e.message;throw e;}}
function execute(f){f.api.submit(f.request);f.run();return f.emitted[0];}
test('normal highest quality invokes finish once without changing score',()=>{const f=fixture(),r=execute(f);f.run();assert.equal(r.status,'completed');assert.equal(r.quality,3);assert.equal(f.calls,1);assert.equal(f.panel.add(0x108).readFloat(),7);assert.throws(()=>f.api.submit(f.request));});
test('deferred fire animation acknowledged as settling',()=>{const f=fixture();f.options.deferred=true;const r=execute(f);assert.equal(r.status,'completed');assert.equal(r.result_deferred,true);});
for(const [offset,value] of [[0x93,1],[0x92,0],[0x106,0],[0x158,1],[0x159,1],[0x15a,1],[0x208,1],[0x42,0]])test('inactive qte flag '+offset,()=>{const f=fixture();f.panel.add(offset).writeU8(value);f.sync();assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);assert.equal(f.panel.add(0xe8).readFloat(),123);});
for(const [offset,value] of [[0xe8,-1],[0xe8,1001],[0xe8,NaN],[0x10c,0],[0xe4,0],[0x120,1001],[0x108,Infinity]])test('invalid ticking value '+offset+'/'+value,()=>{const f=fixture();f.panel.add(offset).writeFloat(value);f.sync();assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);});
test('natural progress does not stale stable proof',()=>{const f=fixture();f.panel.add(0xe8).writeFloat(200);assert.equal(execute(f).status,'completed');});
test('pending material costs refuse',()=>{const f=fixture();f.context.add(0x60).writeU8(0);f.sync();assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);});
test('already paid exploration permits null pending costs',()=>{const f=fixture();f.context.add(0x50).writePointer(0);f.context.add(0x60).writeU8(0);f.sync();assert.equal(execute(f).status,'completed');});
test('refunded context refuses',()=>{const f=fixture();f.context.add(0x70).writeU8(1);f.sync();assert.equal(execute(f).status,'rejected');});
test('new context refuses stale transaction',()=>{const f=fixture();f.panel.add(0x148).writePointer(0x1234);f.sync();assert.equal(execute(f).status,'rejected');});
test('missing operation bytes coverage refuses',()=>{const f=fixture();f.request.anchors=f.request.anchors.filter(a=>a.address!==f.operation.add(20).toString());assert.equal(execute(f).status,'rejected');});
for(const option of ['throw','exception','stillRunning','noResult','wrongProgress'])test('mutation uncertainty is locked '+option,()=>{const f=fixture();f.options[option]=true;const r=execute(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.equal(f.calls,1);assert.throws(()=>f.api.reset('one'));});
test('first scalar store failure already counts uncertain and cannot retry',()=>{const f=fixture();f.options.storeThrow=true;const r=execute(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.equal(f.calls,0);assert.throws(()=>f.api.reset('one'));});
test('talent respects configured level and accepts Int32 value-type marker',()=>{const f=fixture(true),r=execute(f);assert.equal(r.status,'completed');assert.equal(r.rank,2);assert.equal(f.calls,1);});
test('talent zero removes existing slot through game setter',()=>{const f=fixture(true);Object.assign(f.m,{talent_id:1000002,before:1,rank:0,maximum:1});const r=execute(f);assert.equal(r.status,'completed');assert.equal(r.rank,0);assert.equal(f.dictionary.add(40).readS32(),1);});
test('talent initially null dictionary is created by game setter',()=>{const f=fixture(true);f.model.add(0x28).writePointer(0);f.m.dictionary='0x0';f.sync();const r=execute(f);assert.equal(r.status,'completed');assert.equal(f.dictionary.add(32).readS32(),1);});
test('talent existing item is replaced without duplicate',()=>{const f=fixture(true);f.model.add(0x18).writeS32(8);Object.assign(f.m,{level:8,talent_id:1000002,before:1,rank:2,maximum:2});f.sync();const r=execute(f);assert.equal(r.status,'completed');assert.equal(f.dictionary.add(32).readS32(),1);});
for(const rank of [-1,3,6,1.5,NaN])test('talent rank invalid '+rank,()=>{const f=fixture(true);f.m.rank=rank;assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);});
test('talent unknown ID rejected',()=>{const f=fixture(true);f.m.talent_id=1000008;assert.equal(execute(f).status,'rejected');});
test('talent current level changed',()=>{const f=fixture(true);f.model.add(0x18).writeS32(6);f.sync();assert.equal(execute(f).status,'rejected');});
test('talent opened qte refused even stale observed list false',()=>{const f=fixture(true);f.panel.add(0x42).writeU8(1);f.sync();assert.equal(execute(f).status,'rejected');});
test('talent hidden registration proof cannot be omitted',()=>{const f=fixture(true);f.m.observed_panels=[];assert.equal(execute(f).status,'rejected');});
test('talent existing entry proof cannot be omitted',()=>{const f=fixture(true);f.request.anchors=f.request.anchors.filter(a=>a.address!==f.entries.add(32).toString());assert.equal(execute(f).status,'rejected');});
test('talent forged cap cannot bypass native game level',()=>{const f=fixture(true);f.m.maximum=5;f.m.rank=5;assert.equal(execute(f).status,'rejected');});
test('talent wrong player component refused',()=>{const f=fixture(true);f.player.add(0x60).writePointer(0);f.sync();assert.equal(execute(f).status,'rejected');});
for(const flags of [0x20,0x40,0xa0,0xc0])test('talent byref/pinned flags '+flags,()=>{const f=fixture(true);f.parameterTypes[0].add(11).writeU8(flags);assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);});
for(const option of ['throw','exception','wrongRank','otherTalent'])test('talent postdispatch uncertainty '+option,()=>{const f=fixture(true);f.options[option]=true;const r=execute(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.throws(()=>f.api.reset('one'));});
for(const talent of [false,true])for(const action of ['cancel','expire'])test('before-update '+action+' '+talent,()=>{const f=fixture(talent);f.api.submit(f.request);action==='cancel'?f.api.cancel():f.expire();f.run();assert.equal(f.emitted[0].status,'cancelled');assert.equal(f.emitted[0].called,false);assert.equal(f.calls,0);});
for(const talent of [false,true])test('current native and QTE layout '+talent,()=>{const f=fixture(talent,true),r=execute(f);assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(f.calls,1);});
test('current QTE mixed legacy context rejected',()=>{const f=fixture(false,true);f.panel.add(0x150).writePointer(0);f.panel.add(0x148).writePointer(f.context);f.sync();const r=execute(f);assert.equal(r.status,'rejected');assert.equal(f.calls,0);});
test('current ignition pending cannot write or finish',()=>{const f=fixture(false,true);f.panel.add(0x10c).writeU8(1);f.sync();assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);assert.equal(f.panel.add(0xe8).readFloat(),123);});
test('current ignition flag must have proof',()=>{const f=fixture(false,true);f.request.anchors=f.request.anchors.filter(a=>a.address!==f.panel.add(0x10c).toString());assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);});
console.log('alchemy bridge: '+count+' offline tests passed');
