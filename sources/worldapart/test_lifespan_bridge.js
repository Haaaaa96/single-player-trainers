/* Pure-memory Frida model exercising the real packaged bridge. No game process. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'acquisition_bridge.js'), 'utf8');
const evidence = JSON.parse(fs.readFileSync(path.join(__dirname, 'character_lifespan_specs.json'), 'utf8'));

function fixture(adding = true, missing = false, profile = 'legacy') {
    const specs = profile === 'legacy' ? evidence.methods : evidence.method_profiles[profile];
    const bytes = new Map(), emitted = [], parameters = new Map(), methodNames = new Map();
    let next = 0x10000000n, callback, timer, calls = 0, getters = 0;
    const options = {};
    class P {
        constructor(value) { this.value = value instanceof P ? value.value : BigInt(value); }
        add(value) { return new P(this.value + BigInt(value)); }
        compare(other) { const b = new P(other).value; return this.value < b ? -1 : this.value > b ? 1 : 0; }
        equals(other) { return this.value === new P(other).value; }
        isNull() { return this.value === 0n; }
        toString() { return '0x' + this.value.toString(16); }
        readByteArray(size) { return Uint8Array.from({length:size}, (_, i) => bytes.get(this.value + BigInt(i)) || 0).buffer; }
        writeByteArray(data) { Array.from(data).forEach((b,i) => bytes.set(this.value+BigInt(i),b)); }
        readU8() { return bytes.get(this.value) || 0; }
        writeU8(v) { this.writeByteArray([v]); }
        readU16() { return Buffer.from(this.readByteArray(2)).readUInt16LE(); }
        readS32() { return Buffer.from(this.readByteArray(4)).readInt32LE(); }
        writeS32(v) { const b = Buffer.alloc(4); b.writeInt32LE(v); this.writeByteArray(b); }
        readFloat() { return Buffer.from(this.readByteArray(4)).readFloatLE(); }
        writeFloat(v) { const b = Buffer.alloc(4); b.writeFloatLE(v); this.writeByteArray(b); }
        readPointer() { return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE()); }
        writePointer(v) { const b=Buffer.alloc(8);b.writeBigUInt64LE(new P(v).value);this.writeByteArray(b); }
        readU64() { const value=Buffer.from(this.readByteArray(8)).readBigUInt64LE();return {toNumber:()=>Number(value)}; }
        readUtf8String() { const data=[];for(let i=0;i<256;i++){const b=this.add(i).readU8();if(!b)break;data.push(b);}return Buffer.from(data).toString('utf8'); }
    }
    const ptr = value => new P(value), alloc = size => {const value=ptr(next);next+=BigInt(size+32);return value;};
    function klass(namespace, name) {
        const value=alloc(0x200),n=alloc(256),ns=alloc(256);
        n.writeByteArray(Buffer.from(name+'\0'));ns.writeByteArray(Buffer.from(namespace+'\0'));
        value.add(16).writePointer(n);value.add(24).writePointer(ns);return value;
    }
    const base=ptr(0x1000000),player=ptr(0x4000000),combat=ptr(0x4010000),growth=ptr(0x4020000),baseDict=ptr(0x4030000);
    const growthArray=ptr(0x4040000),baseArray=ptr(0x4050000),anchor=ptr(0x4060000);
    const playerClass=klass('Game.Model','PlayerModel'),combatClass=klass('Game.Model.Player.Components','CombatModel');
    const dictionaryClass=klass('System.Collections.Generic','Dictionary`2'),intClass=klass('System','Int32'),floatClass=klass('System','Single');
    player.writePointer(playerClass);combat.writePointer(combatClass);
    player.add(0x48).writePointer(combat);combat.add(0x10).writePointer(player);
    combat.add(0x20).writePointer(baseDict);combat.add(0x28).writePointer(growth);
    function entry(array, index, key, value) {
        const e=array.add(32+16*index);e.writeS32(key);e.add(4).writeS32(-1);e.add(8).writeS32(key);e.add(12).writeFloat(value);return e.add(12);
    }
    for(const [dictionary,array,count] of [[growth,growthArray,missing?1:2],[baseDict,baseArray,1]]) {
        dictionary.writePointer(dictionaryClass);dictionary.add(0x18).writePointer(array);dictionary.add(0x20).writeS32(count);
        dictionary.add(0x28).writeS32(0);dictionary.add(0x2c).writeS32(10);array.add(24).writePointer(4);
    }
    const attack=entry(growthArray,0,2,3),health=entry(baseArray,0,1,100);
    let lifespan=missing?null:entry(growthArray,1,8,0);
    const methods={},returnTypes={},parameterTypes={};
    for(const [key,s] of Object.entries(specs)) {
        const method=alloc(0x100),name=alloc(256),type=alloc(16);
        methods[key]=method;returnTypes[key]=type;
        name.writeByteArray(Buffer.from(s.name+'\0'));type.add(10).writeU8(s.return_kind);type.add(11).writeU8(0x80);
        method.writePointer(base.add(s.rva));method.add(0x18).writePointer(name);method.add(0x20).writePointer(playerClass);
        method.add(0x28).writePointer(type);method.add(0x48).writeS32(s.token);method.add(0x4c).writeByteArray([0x86,0]);
        method.add(0x52).writeU8(s.parameters);base.add(s.rva).writeByteArray(Buffer.from(s.prefix,'hex'));
        const params=[];
        for(let i=0;i<s.parameters;i++){const p=alloc(16);p.add(10).writeU8(12);p.add(11).writeU8(0x80);params.push(p);}
        parameterTypes[key]=params;parameters.set(method.toString(),params);methodNames.set(method.toString(),key);
    }
    const l={player:player.toString(),player_class:playerClass.toString(),combat:combat.toString(),combat_class:combatClass.toString(),
        growth_dictionary:growth.toString(),base_dictionary:baseDict.toString(),growth_before:0,growth_address:lifespan?lifespan.toString():'0x0',
        health_address:health.toString(),identity_key:'original-player',method_profile:profile,methods:Object.fromEntries(Object.entries(methods).map(([k,v])=>[k,v.toString()]))};
    if(adding)Object.assign(l,{amount:1,expected_age:20,expected_maximum:100,growth_after:1});
    const methodKey=adding?'modify':'age',selected=specs[methodKey];
    const request={operation:adding?'lifespan_add':'lifespan_inspect',token:'one',pid:12,lifespan:l,
        method_info:methods[methodKey].toString(),method_token:selected.token,method_rva:selected.rva,parameter_count:selected.parameters,
        deadline:Date.now()+10000,anchors:[]};
    function addAnchor(a,size){request.anchors.push({address:a.toString(),size,expected_hex:Buffer.from(a.readByteArray(size)).toString('hex'),label:'lifespan proof'});}
    anchor.writeS32(1);addAnchor(anchor,4);
    for(const [a,size] of [[player,8],[combat,8],[player.add(0x48),8],[combat.add(0x10),8],[combat.add(0x20),8],
        [combat.add(0x28),8],[player.add(0x1b8),1],[player.add(0x1bc),8],[player.add(0x1c4),8]])addAnchor(a,size);
    for(const [dictionary,array] of [[growth,growthArray],[baseDict,baseArray]]) {
        for(const [a,size] of [[dictionary,8],[dictionary.add(0x18),8],[dictionary.add(0x20),4],[dictionary.add(0x28),4],
            [dictionary.add(0x2c),4],[array.add(24),8]])addAnchor(a,size);
        for(let i=0;i<dictionary.add(0x20).readS32();i++)addAnchor(array.add(32+16*i),16);
    }
    base.add(profile === 'legacy' ? 0x14342d0 : 0x1464640).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    function invoke(method,target,args,exception) {
        const key=methodNames.get(method.toString());assert.ok(target.equals(player));exception.writePointer(0);
        if(key!=='modify') {
            getters++;
            if(options.getterThrow===getters)throw new Error('getter transport error');
            if(options.getterException===getters)exception.writePointer(0xDEAD);
            if(options.getterNull===getters)return ptr(0);
            const result=alloc(32);result.writePointer(options.getterWrongType===getters?floatClass:intClass);
            const value=key==='age'?(options.age??20):(options.maximum??((options.baseMaximum??100)+(lifespan?lifespan.readFloat():0)));
            result.add(16).writeS32(value);
            if(options.changeAnchor===getters)anchor.writeS32(2);
            if(options.expireGetter===getters)request.deadline=Date.now()-1;
            return result;
        }
        calls++;
        if(options.setterThrow)throw new Error('modifier exception');
        const delta=args.readPointer().readFloat();assert.equal(delta,l.amount);
        if(!lifespan){lifespan=entry(growthArray,1,8,0);growth.add(0x20).writeS32(2);}
        lifespan.writeFloat(options.badGrowth?999:Math.fround(lifespan.readFloat()+delta));
        growth.add(0x2c).writeS32((growth.add(0x2c).readS32()+(options.versionIncrement??1))|0);
        player.add(0x1bc).writePointer(0);player.add(0x1c4).writePointer(0);
        if(options.otherGrowth)attack.writeFloat(4);
        if(options.changeHealth)health.writeFloat(101);
        if(options.ownerChange)combat.add(0x10).writePointer(0);
        if(options.markerAfter)player.add(0x1bc).writeU8(1);
        if(options.setterException)exception.writePointer(0xDEAD);
        if(options.setterNull)return ptr(0);
        const result=alloc(32);result.writePointer(options.setterWrongType?intClass:floatClass);
        result.add(16).writeFloat(options.actualDelta??delta);return result;
    }
    const context={Process:{id:12,arch:'x64',platform:'windows',pointerSize:8,getCurrentThreadId:()=>1,
        getModuleByName:()=>({base,getExportByName:n=>n})},Memory:{alloc},ptr,
        NativeFunction:function(name){
            if(name==='il2cpp_method_get_param_count')return m=>m.add(0x52).readU8();
            if(name==='il2cpp_method_get_token')return m=>m.add(0x48).readS32();
            if(name==='il2cpp_method_get_param')return(m,i)=>parameters.get(m.toString())[i];
            if(name==='il2cpp_class_from_type')return()=>ptr(0);
            return invoke;
        },Interceptor:{attach:(_address,callbacks)=>{callback=callbacks.onEnter;return{detach:()=>{}};}},
        rpc:{exports:{}},send:v=>emitted.push(v),setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{},Uint8Array,Date,Number,Array};
    vm.createContext(context);vm.runInContext(source,context);
    return {request,l,emitted,options,methods,returnTypes,parameterTypes,player,combat,growth,growthArray,baseDict,health,attack,anchor,base,
        get lifespan(){return lifespan;},get calls(){return calls;},get getters(){return getters;},api:context.rpc.exports,
        run:()=>callback(),expire:()=>timer(),syncAnchors:()=>request.anchors.forEach(a=>a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex'))};
}
let count=0;
function test(name,run){try{run();count++;}catch(e){e.message=name+': '+e.message;throw e;}}
function execute(f){f.api.submit(f.request);f.run();return f.emitted[0];}
test('inspection invokes only two readonly getters',()=>{
    const f=fixture(false);const result=execute(f);assert.equal(result.status,'completed');assert.equal(result.mutated,false);
    assert.equal(result.current_age,20);assert.equal(result.maximum,100);assert.equal(f.calls,0);assert.equal(f.getters,2);
    assert.equal(f.lifespan.readFloat(),0);assert.equal(f.growth.add(0x2c).readS32(),10);
});
test('current reviewed profile inspects twice on the same bridge without mutation',()=>{
    const f=fixture(false,false,'reviewed_20260930');
    assert.equal(execute(f).status,'completed');assert.equal(f.calls,0);
    f.api.reset('one');f.request.token='two';f.api.submit(f.request);f.run();
    assert.equal(f.emitted[1].status,'completed');assert.equal(f.getters,4);assert.equal(f.calls,0);
});
test('current reviewed profile preserves one positive native add',()=>{
    const f=fixture(true,false,'reviewed_20260930');
    assert.equal(execute(f).status,'completed');assert.equal(f.calls,1);assert.equal(f.lifespan.readFloat(),1);
});
for(const profile of ['legacy','unknown','__proto__'])test('profile cannot authorize mismatched methods '+profile,()=>{
    const f=fixture(false,false,'reviewed_20260930');f.l.method_profile=profile;
    assert.equal(execute(f).status,'rejected');assert.equal(f.getters,0);assert.equal(f.calls,0);
});
test('two matching Update candidates refuse before installing a hook',()=>{
    const f=fixture(false,false,'reviewed_20260930');
    f.base.add(0x14342d0).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    assert.throws(()=>f.api.submit(f.request),/ambiguous/);assert.equal(f.getters,0);
});
for(const missing of [false,true])test('one positive native add '+missing,()=>{
    const f=fixture(true,missing),result=execute(f);f.run();assert.equal(result.status,'completed');assert.equal(result.mutated,true);
    assert.equal(result.maximum,101);assert.equal(result.growth,1);assert.equal(f.calls,1);assert.equal(f.getters,4);
    assert.throws(()=>f.api.submit(f.request),/exactly one/);
});
test('maximum allowed increase',()=>{
    const f=fixture();f.l.amount=1000;f.l.growth_after=1000;assert.equal(execute(f).status,'completed');assert.equal(f.lifespan.readFloat(),1000);
});
test('actual maximum can cross the Growth tool bound',()=>{
    const f=fixture();f.options.baseMaximum=1000000;f.l.expected_maximum=1000000;
    const result=execute(f);assert.equal(result.status,'completed');assert.equal(result.maximum,1000001);
    assert.equal(result.growth,1);assert.equal(f.calls,1);
});
test('native Int32 maximum is accepted for readonly inspection',()=>{
    const f=fixture(false);f.options.maximum=2147483647;
    assert.equal(execute(f).maximum,2147483647);assert.equal(f.calls,0);
});
for(const amount of [-1,0,1001,1.5,NaN,Infinity])test('invalid amount '+amount,()=>{
    const f=fixture();f.l.amount=amount;assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const field of ['expected_age','expected_maximum'])test('stale '+field,()=>{
    const f=fixture();f.l[field]++;assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const offset of [0x1b8,0x1bc,0x1c4])test('exhaustion marker '+offset,()=>{
    const f=fixture();f.player.add(offset).writeU8(1);f.syncAnchors();const r=execute(f);
    assert.equal(r.status,'rejected');assert.equal(r.called,false);assert.equal(f.calls,0);
});
test('exhausted age refuses; equality remains allowed',()=>{
    const f=fixture();f.options.age=101;assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
    const equal=fixture();equal.options.age=100;equal.l.expected_age=100;assert.equal(execute(equal).status,'completed');
});
test('dead character not resurrected',()=>{
    const f=fixture();f.health.writeFloat(0);f.syncAnchors();assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const flags of [0x20,0x40,0xA0,0xC0])test('return flags '+flags,()=>{
    const f=fixture();f.returnTypes.age.add(11).writeU8(flags);assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const flags of [0x20,0x40])test('parameter flags '+flags,()=>{
    const f=fixture();f.parameterTypes.modify[0].add(11).writeU8(flags);assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const mutate of [f=>f.methods.modify.add(0x48).writeS32(1),f=>f.methods.modify.add(0x52).writeU8(0),
    f=>f.base.add(0xdc3fb0).writeU8(0),f=>f.methods.modify.add(0x20).writePointer(0)])test('wrong method metadata',()=>{
    const f=fixture();mutate(f);assert.equal(execute(f).status,'rejected');assert.equal(f.calls,0);
});
for(const key of ['getterThrow','getterException','getterNull','getterWrongType','changeAnchor'])test('getter guard '+key,()=>{
    const f=fixture();f.options[key]=2;const r=execute(f);assert.equal(r.status,'rejected');assert.equal(r.called,false);assert.equal(f.calls,0);
});
for(const key of ['setterThrow','setterException','setterNull','setterWrongType','badGrowth','otherGrowth','changeHealth','ownerChange','markerAfter'])test('unknown after modifier '+key,()=>{
    const f=fixture();f.options[key]=true;const r=execute(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.equal(f.calls,1);
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
for(const value of [-1,NaN,Infinity])test('invalid actual delta '+value,()=>{
    const f=fixture();f.options.actualDelta=value;assert.equal(execute(f).status,'unknown');assert.equal(f.calls,1);
});
for(const increment of [0,2])test('dictionary version is exact '+increment,()=>{
    const f=fixture();f.options.versionIncrement=increment;assert.equal(execute(f).status,'unknown');
});
test('post-modify getter fault remains unknown',()=>{
    const f=fixture();f.options.getterThrow=3;assert.equal(execute(f).status,'unknown');assert.equal(f.calls,1);
});
test('cancel and timer expiry never modify',()=>{
    for(const cancel of [true,false]){const f=fixture();f.api.submit(f.request);if(cancel)f.api.cancel();else f.expire();f.run();
        assert.equal(f.emitted[0].status,'cancelled');assert.equal(f.calls,0);}
});
test('deadline expiring in getters never reaches modifier',()=>{
    const f=fixture();f.options.expireGetter=2;assert.equal(execute(f).status,'cancelled');assert.equal(f.calls,0);
});
console.log(`lifespan bridge: ${count} offline tests passed`);
