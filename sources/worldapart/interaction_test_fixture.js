/* Offline byte-addressed memory and IL2CPP descriptors. No game/Frida access. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
function memoryFixture(current=false) {
    const evidence=require('./native_method_evidence.json');
    const variant=s=>current&&evidence.methods[s.token]?{...s,...evidence.methods[s.token]}:s;
    const memory=new Map(),parameters=new Map(),typeClasses=new Map(),events=[],options={};
    let next=0x9000000n,callback;
    class P {
        constructor(v){this.value=BigInt.asUintN(64,v instanceof P?v.value:BigInt(v));}
        add(v){return new P(this.value+BigInt(v));} sub(v){return new P(this.value-new P(v).value);}
        compare(v){const x=new P(v).value;return this.value<x?-1:this.value>x?1:0;}
        equals(v){return this.value===new P(v).value;} isNull(){return this.value===0n;}
        toString(){return '0x'+this.value.toString(16);} toInt32(){return Number(this.value)|0;}
        readByteArray(n){return Uint8Array.from({length:n},(_,i)=>memory.get(this.value+BigInt(i))||0).buffer;}
        writeByteArray(b){Array.from(b).forEach((v,i)=>memory.set(this.value+BigInt(i),v));}
        readPointer(){return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE());}
        writePointer(v){const b=Buffer.alloc(8);b.writeBigUInt64LE(new P(v).value);this.writeByteArray(b);}
        readS32(){return Buffer.from(this.readByteArray(4)).readInt32LE();}
        readU32(){return Buffer.from(this.readByteArray(4)).readUInt32LE();}
        writeS32(v){const b=Buffer.alloc(4);b.writeInt32LE(v);this.writeByteArray(b);}
        readU8(){return memory.get(this.value)||0;} writeU8(v){this.writeByteArray([v]);}
        readU16(){return Buffer.from(this.readByteArray(2)).readUInt16LE();}
        readU64(){const v=this.readPointer().value;return {toNumber:()=>Number(v),toString:()=>v.toString()};}
        readS64(){const v=BigInt.asIntN(64,this.readPointer().value);return {toString:()=>v.toString()};}
        readFloat(){return Buffer.from(this.readByteArray(4)).readFloatLE();}
        writeFloat(v){const b=Buffer.alloc(4);b.writeFloatLE(v);this.writeByteArray(b);}
        readUtf8String(){const a=[];for(let i=0;i<256;i++){const v=this.add(i).readU8();if(!v)break;a.push(v);}return Buffer.from(a).toString();}
        readUtf16String(n){return Buffer.from(this.readByteArray(n*2)).toString('utf16le');}
    }
    const ptr=v=>new P(v),alloc=n=>{const p=ptr(next);next+=BigInt(n+16);return p;};
    function string(v){const p=alloc(Buffer.byteLength(v)+1);p.writeByteArray(Buffer.from(v+'\0'));return p;}
    function klass(ns,name,size=0x300){const p=alloc(0x200);p.add(16).writePointer(string(name));p.add(24).writePointer(string(ns));p.add(0xf8).writeS32(size);return p;}
    function object(ns,name,size=0x300){const p=alloc(size);p.writePointer(klass(ns,name,size));return p;}
    function type(kind,cls=null){const t=alloc(16);t.add(10).writeU8(kind);t.add(11).writeU8([2,8,0x11].includes(kind)?0x80:0);if(cls)typeClasses.set(t.toString(),cls);return t;}
    function fields(k,items){const a=alloc(items.length*32);k.add(0x80).writePointer(a);k.add(0x124).writeByteArray([items.length&255,items.length>>8]);
        items.forEach(([name,token,kind,offset,cls],i)=>{const owner=k.add(24).readPointer().readUtf8String()+'.'+k.add(16).readPointer().readUtf8String();
            if(current)token=evidence.fields[owner+':'+token]?.token??token;
            const f=a.add(i*32);f.writePointer(string(name));f.add(8).writePointer(type(kind,cls));f.add(16).writePointer(k);f.add(24).writeS32(offset);f.add(28).writeS32(token);});}
    const base=ptr(0x10000000),request={token:'interaction-one',pid:42,deadline:Date.now()+10000,anchors:[]};
    const addAnchor=(p,n)=>request.anchors.push({address:p.toString(),size:n,expected_hex:Buffer.from(p.readByteArray(n)).toString('hex'),label:'offline proof'});
    function block(p,n){for(let o=0;o<n;o+=256)addAnchor(p.add(o),Math.min(256,n-o));}
    function method(k,s,classes=[]){s=variant(s);const p=alloc(0x80),ret=type(s.returns);p.writePointer(base.add(s.rva));p.add(0x18).writePointer(string(s.name));p.add(0x20).writePointer(k);p.add(0x28).writePointer(ret);
        p.add(0x48).writeS32(s.token);p.add(0x4c).writeU8(s.static?0x91:0x81);p.add(0x52).writeU8(s.argc);
        const ps=s.params.map((kind,i)=>type(kind,classes[i]));parameters.set(p.toString(),ps);base.add(s.rva).writeByteArray(Buffer.from(s.prefix,'hex'));return {address:p,returnType:ret,params:ps};}
    base.add(current?0x1464640:0x14342d0).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    const context={ptr,Process:{id:42,arch:'x64',platform:'windows',pointerSize:8,getCurrentThreadId:()=>99,getModuleByName:()=>({base,getExportByName:n=>n})},Memory:{alloc},
        NativeFunction:function(name){
            if(name==='il2cpp_method_get_param_count')return m=>m.add(0x52).readU8();
            if(name==='il2cpp_method_get_token')return m=>m.add(0x48).readU32();
            if(name==='il2cpp_method_get_param')return (m,i)=>parameters.get(m.toString())?.[i]||ptr(0);
            if(name==='il2cpp_class_from_type')return t=>typeClasses.get(t.toString())||ptr(0);
            if(name==='il2cpp_runtime_invoke')return (...args)=>options.invoke(...args);
            throw Error('unexpected native export '+name);
        },Interceptor:{attach:(_p,h)=>{callback=h.onEnter;return {detach:()=>{}};}},rpc:{exports:{}},send:p=>{if(options.sendFailure)throw Error('send failed');events.push(p);},
        setTimeout:()=>1,clearTimeout:()=>{},Date,console};
    vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8'),context);
    function managedString(s){const p=object('System','String',24+s.length*2);p.add(16).writeS32(s.length);p.add(20).writeByteArray(Buffer.from(s,'utf16le'));block(p,24+s.length*2);return p;}
    function concurrent(flavor,rows){
        const p=object('System.Collections.Concurrent','ConcurrentDictionary`2'),tables=object('','Tables'),buckets=object('','Node[]'),locks=object('System','Object[]'),counts=object('System','Int32[]');
        fields(p.readPointer(),[['_tables',0x04001acb,0x15,16]]);fields(tables.readPointer(),[['_buckets',0x04001ad5,0x1d,16],['_locks',0x04001ad6,0x1d,24],['_countPerLock',0x04001ad7,0x1d,32]]);
        p.add(16).writePointer(tables);tables.add(16).writePointer(buckets);tables.add(24).writePointer(locks);tables.add(32).writePointer(counts);
        buckets.add(24).writePointer(7);locks.add(24).writePointer(1);counts.add(24).writePointer(1);counts.add(32).writeS32(rows.length);
        const uuid=klass('SimpleSave','EntityID',24),id=klass('LubanDatas','TbNpcBaseCfgId',20);fields(uuid,[['Id',0x04000036,0x0e,16]]);fields(id,[['<Value>k__BackingField',0x04000b8c,8,16]]);
        const nc=klass('','Node',48);fields(nc,[['_key',0x04001ad8,0x11,16,flavor==='npc'?uuid:id],['_value',0x04001ad9,flavor==='npc'?0x12:0x11,24,flavor==='static'?uuid:null],['_next',0x04001ada,0x15,32],['_hashcode',0x04001adb,8,40]]);buckets.readPointer().add(0x40).writePointer(nc);
        const items=rows.map(([key,value],i)=>{const node=alloc(48);node.writePointer(nc);const item={key,value,node:node.toString(),next:'0x0',hashcode:i,bucket:i};
            if(flavor==='npc'){const s=managedString(key);node.add(16).writePointer(s);item.key_pointer=s.toString();node.add(24).writePointer(value);}else{node.add(16).writeS32(key);const s=managedString(value);node.add(24).writePointer(s);item.value_pointer=s.toString();}
            buckets.add(32+i*8).writePointer(node);node.add(40).writeS32(i);block(node,48);return item;});
        for(const q of [p,tables,buckets,locks,counts])block(q,0x300);
        return {kind:'concurrent',flavor,address:p.toString(),tables:tables.toString(),buckets:buckets.toString(),locks:locks.toString(),count_per_lock:counts.toString(),bucket_count:7,lock_count:1,count:rows.length,items};
    }
    return {request,base,ptr,alloc,string,managedString,concurrent,klass,object,type,fields,method,variant,addAnchor,block,parameters,typeClasses,events,options,context,api:context.rpc.exports,
        sync:()=>request.anchors.forEach(a=>a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex')),
        run:()=>callback(),submit:()=>{context.rpc.exports.submit(request);callback();return events.at(-1);}};
}
module.exports={memoryFixture};
