/* Offline test of the integrated product bridge: no Frida or game access. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8');
const legacySpecs = JSON.parse(fs.readFileSync(path.join(__dirname,'game_speed_specs.json'),'utf8'));

const specs=legacySpecs;
function fixture(scales=[], before=1, desired=1.5,current=false) {
    const specs={...legacySpecs,methods:Object.fromEntries(Object.entries(legacySpecs.methods).map(([k,s])=>[k,current?{...s,...require('./native_method_evidence.json').methods[s.token]}:s]))};
    const memory=new Map(), methodMap=new Map(), params=new Map(), options={}, events=[];
    let next=0x9000000n, callback, timer, calls=0, getters=0;
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
        readU64() {return {toNumber:()=>Number(this.readPointer().value)};}
        readFloat() {return Buffer.from(this.readByteArray(4)).readFloatLE();}
        writeFloat(v) {const b=Buffer.alloc(4);b.writeFloatLE(v);this.writeByteArray(b);}
        readUtf8String() {const a=[];for(let i=0;i<256;i++){const v=this.add(i).readU8();if(!v)break;a.push(v);}return Buffer.from(a).toString();}
    }
    const ptr=v=>new P(v), alloc=n=>{const p=ptr(next);next+=BigInt(n+16);return p;};
    function string(v) {const p=alloc(256);p.writeByteArray(Buffer.from(v+'\0'));return p;}
    function klass(ns,name) {const p=alloc(0x200);p.add(16).writePointer(string(name));p.add(24).writePointer(string(ns));return p;}
    const base=ptr(0x10000000), k=klass('Game','GameTimeScaleController'), statics=alloc(32), list=alloc(64),items=alloc(128);
    const single=klass('System','Single'), other=klass('System','Boolean'), anchor=alloc(4);
    list.writePointer(klass('System.Collections.Generic','List`1'));
    items.writePointer(klass('','TimeScaleOverride[]'));
    base.add(specs.class_slot_rva).writePointer(k);k.add(0xb8).writePointer(statics);k.add(0xe0).writeS32(1);
    k.add(0x11c).writeS32(current?0x020009a4:0x0200099e);k.add(0x68).writePointer(0x20001000);
    statics.writePointer(list);statics.add(8).writeFloat(before);list.add(0x10).writePointer(items);
    list.add(0x18).writeS32(scales.length);list.add(0x1c).writeS32(9);items.add(24).writePointer(4);anchor.writeS32(7);
    scales.forEach((s,i)=>{items.add(32+i*8).writeS32(i+1);items.add(36+i*8).writeFloat(s);});
    const methods={}, returns={}, argumentsTypes={};
    for (const [key,spec] of Object.entries(specs.methods)) {
        const m=alloc(0x80),type=alloc(16);
        m.writePointer(base.add(spec.rva));m.add(0x18).writePointer(string(spec.name));m.add(0x20).writePointer(k);m.add(0x28).writePointer(type);
        m.add(0x48).writeS32(spec.token);m.add(0x4c).writeU8(0x96);m.add(0x52).writeU8(spec.parameters);
        type.add(10).writeU8(spec.return_kind);type.add(11).writeU8(spec.return_kind===12?0x80:0);
        base.add(spec.rva).writeByteArray(Buffer.from(spec.prefix,'hex'));
        if(spec.parameters) {const t=alloc(16);t.add(10).writeU8(12);t.add(11).writeU8(0x80);params.set(m.toString(),t);argumentsTypes[key]=t;}
        methods[key]=m.toString();returns[key]=type;methodMap.set(m.toString(),{...spec,key});
    }
    base.add(specs.slot_proof_rva).writeByteArray(Buffer.from(specs.slot_proof,'hex'));
    base.add(current?0x1464640:0x14342d0).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    const request={operation:'game_speed_set',token:'speed-one',pid:42,deadline:Date.now()+10000,parameter_count:1,
        method_info:methods.modify,method_token:specs.methods.modify.token,method_rva:specs.methods.modify.rva,anchors:[],
        speed:{klass:k.toString(),static:statics.toString(),overrides:list.toString(),items:items.toString(),address:statics.add(8).toString(),
            before,effective_before:scales.length?scales.at(-1):before,value:desired,override_count:scales.length,override_version:9,capacity:4,methods,identity_key:'a'.repeat(64)}};
    function addAnchor(p,n) {request.anchors.push({address:p.toString(),size:n,expected_hex:Buffer.from(p.readByteArray(n)).toString('hex'),label:'speed proof'});}
    for(const [p,n] of [[base.add(specs.class_slot_rva),8],[k.add(0xb8),8],[k.add(0xe0),4],[statics,8],[statics.add(8),4],
        [list,8],[list.add(0x10),8],[list.add(0x18),4],[list.add(0x1c),4],[items,8],[items.add(24),8],[anchor,4]])addAnchor(p,n);
    if(current) for(const [offset,n] of [[0x68,8],[0x11c,4]])addAnchor(k.add(offset),n);
    scales.forEach((_,i)=>addAnchor(items.add(32+i*8),8));
    const context={ptr,Process:{id:42,arch:'x64',platform:'windows',pointerSize:8,getCurrentThreadId:()=>99,
        getModuleByName:()=>({base,getExportByName:n=>n})},Memory:{alloc},
        NativeFunction:function(name){
            if(name==='il2cpp_method_get_param_count')return m=>m.add(0x52).readU8();
            if(name==='il2cpp_method_get_token')return m=>m.add(0x48).readS32();
            if(name==='il2cpp_method_get_param')return (m,i)=>params.get(m.toString())||ptr(0);
            if(name==='il2cpp_class_from_type')return ()=>ptr(0);
            assert.equal(name,'il2cpp_runtime_invoke');
            return (m,target,args,exception)=>{
                assert.ok(target.isNull(),'static method target must be null');
                const spec=methodMap.get(m.toString());assert.ok(spec);
                if(spec.key==='modify') {
                    calls++;
                    assert.equal(args.readPointer().readFloat(),Math.fround(desired));
                    if(options.setterThrow)throw new Error('setter native fault');
                    if(!options.noChange)statics.add(8).writeFloat(desired);
                    if(options.changeVersion)list.add(0x1c).writeS32(10);
                    if(options.changeOverride)items.add(36).writeFloat(.75);
                    if(options.replaceOwner)base.add(specs.class_slot_rva).writePointer(0);
                    exception.writePointer(options.setterException?0x1234:0);return options.setterValue?ptr(7):ptr(0);
                }
                getters++;assert.ok(args.isNull());
                if(options.getterThrow===getters)throw new Error('getter native fault');
                exception.writePointer(options.getterException===getters?0x1234:0);
                if(options.getterNull===getters)return ptr(0);
                const result=alloc(24);result.writePointer(options.getterType===getters?other:single);
                let value=spec.key==='base'?statics.add(8).readFloat():scales.length?items.add(36+(scales.length-1)*8).readFloat():statics.add(8).readFloat();
                if(options.getterValues && getters in options.getterValues)value=options.getterValues[getters];
                result.add(16).writeFloat(value);
                if(options.changeAnchor===getters)anchor.writeS32(8);
                if(options.expire===getters)request.deadline=Date.now()-1;
                return result;
            };
        },Interceptor:{attach:(_p,h)=>{callback=h.onEnter;return {detach:()=>{}};}},rpc:{exports:{}},send:p=>events.push(p),
        setTimeout:f=>{timer=f;return 1;},clearTimeout:()=>{},Uint8Array,Date,Number,Array};
    vm.createContext(context);vm.runInContext(source,context);
    return {api:context.rpc.exports,request,events,options,base,k,statics,list,items,anchor,methods,returns,argumentsTypes,ptr,
        run:()=>callback(),expire:()=>timer(),get calls(){return calls;},get getters(){return getters;},
        sync:()=>request.anchors.forEach(a=>a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex'))};
}
let count=0;
function test(name,fn) {try {fn();count++;}catch(e){e.message=name+': '+e.message;throw e;}}
function run(f) {f.api.submit(f.request);f.run();return f.events.at(-1);}
test('one static setter exactly once',()=>{const f=fixture();const r=run(f);f.run();assert.equal(f.calls,1);assert.equal(f.getters,4);assert.equal(r.status,'completed');assert.equal(r.effective,1.5);});
for(const scales of [[0],[.25],[1.75,.5]])test('preserve override '+scales,()=>{const f=fixture(scales);const old=Buffer.from(f.items.readByteArray(64));const r=run(f);assert.equal(r.status,'completed');assert.equal(r.value,1.5);assert.equal(r.effective,scales.at(-1));assert.equal(r.override_count,scales.length);assert.deepEqual(Buffer.from(f.items.readByteArray(64)),old);});
for(const before of [.5,1.5,2])test('restore one from '+before,()=>{const f=fixture([],before,1);assert.equal(run(f).status,'completed');assert.equal(f.statics.add(8).readFloat(),1);});
for(const desired of [.5,2])test('valid endpoint '+desired,()=>{assert.equal(run(fixture([],1,desired)).status,'completed');});
for(const desired of [0,.49,2.001,1,NaN,Infinity,true])test('invalid target '+desired,()=>{const f=fixture([],1,desired);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
for(const key of ['base','effective','modify']) {
    test('instance '+key+' rejected',()=>{const f=fixture();f.ptr(f.methods[key]).add(0x4c).writeU8(0x86);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
    for(const flag of [0x20,0x40])test('byref/pinned return '+key+' '+flag,()=>{const f=fixture();f.returns[key].add(11).writeU8(0x80|flag);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
}
for(const flag of [0x20,0x40])test('byref/pinned arg '+flag,()=>{const f=fixture();f.argumentsTypes.modify.add(11).writeU8(0x80|flag);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
for(const change of ['token','rva','params','class','prefix','return','argument'])test('bad method '+change,()=>{
    const f=fixture(),m=f.ptr(f.methods.modify);
    if(change==='token')m.add(0x48).writeS32(7);
    if(change==='rva')m.writePointer(7);
    if(change==='params')m.add(0x52).writeU8(2);
    if(change==='class')m.add(0x20).writePointer(7);
    if(change==='prefix')f.base.add(specs.methods.modify.rva).writeU8(0);
    if(change==='return')f.returns.modify.add(10).writeU8(2);
    if(change==='argument')f.argumentsTypes.modify.add(10).writeU8(8);
    assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);
});
test('missing proof refuses before getters',()=>{const f=fixture();f.request.anchors.splice(0,1);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);assert.equal(f.getters,0);});
test('stale scene rejects',()=>{const f=fixture();f.anchor.writeS32(8);assert.equal(run(f).status,'rejected');assert.equal(f.calls,0);});
for(const which of ['getterThrow','getterException','getterNull','getterType'])test(which+' before setter is called false',()=>{const f=fixture();f.options[which]=1;const r=run(f);assert.equal(r.status,'rejected');assert.equal(r.called,false);assert.equal(f.calls,0);});
test('second getter context change rejects',()=>{const f=fixture();f.options.changeAnchor=2;assert.equal(run(f).called,false);assert.equal(f.calls,0);});
test('deadline after getter cancels without setter',()=>{const f=fixture();f.options.expire=2;const r=run(f);assert.equal(r.status,'cancelled');assert.equal(r.called,false);assert.equal(f.calls,0);});
test('cancel then repeated Update never calls',()=>{const f=fixture();f.api.submit(f.request);f.api.cancel();f.run();f.run();assert.equal(f.calls,0);assert.equal(f.events[0].called,false);});
test('timeout before Update never calls',()=>{const f=fixture();f.api.submit(f.request);f.expire();f.run();assert.equal(f.calls,0);assert.equal(f.events[0].called,false);});
for(const option of ['setterThrow','noChange','changeVersion','replaceOwner','setterValue'])test(option+' is unknown and cannot reset',()=>{const f=fixture();f.options[option]=true;const r=run(f);assert.equal(r.status,'unknown');assert.equal(r.called,true);assert.equal(f.calls,1);assert.throws(()=>f.api.reset(f.request.token));f.run();assert.equal(f.calls,1);});
test('mutated override unknown',()=>{const f=fixture([.25]);f.options.changeOverride=true;assert.equal(run(f).status,'unknown');assert.equal(f.calls,1);});
test('managed exception unknown terminal locked',()=>{const f=fixture();f.options.setterException=true;assert.equal(run(f).status,'exception');assert.throws(()=>f.api.reset(f.request.token));assert.equal(f.calls,1);});
test('post getter failure unknown',()=>{const f=fixture();f.options.getterThrow=3;assert.equal(run(f).status,'unknown');assert.equal(f.calls,1);});
test('success reset does not permit token replay',()=>{const f=fixture();run(f);f.api.reset(f.request.token);assert.throws(()=>f.api.submit(f.request),/already used/);assert.equal(f.calls,1);});
test('current reviewed speed methods with renumbered class token',()=>{const f=fixture([],1,1.5,true),r=run(f);assert.equal(f.k.add(0x11c).readS32(),0x020009a4);assert.equal(r.status,'completed',JSON.stringify(r));assert.equal(f.calls,1);});
for(const [name,offset] of [['type definition',0x68],['token',0x11c]]) {
    test('current missing '+name+' proof refuses before getters',()=>{
        const f=fixture([],1,1.5,true);
        f.request.anchors=f.request.anchors.filter(a=>!f.ptr(a.address).equals(f.k.add(offset)));
        const r=run(f);assert.equal(r.status,'rejected');assert.equal(r.called,false);assert.equal(f.calls,0);assert.equal(f.getters,0);
    });
    test('current changed '+name+' refuses before getters',()=>{
        const f=fixture([],1,1.5,true);
        if(offset===0x68)f.k.add(offset).writePointer(0x20002000);else f.k.add(offset).writeS32(0x020009a5);
        const r=run(f);assert.equal(r.status,'rejected');assert.equal(r.called,false);assert.equal(f.calls,0);assert.equal(f.getters,0);
    });
}
console.log('Game speed integrated bridge tests passed: '+count);
