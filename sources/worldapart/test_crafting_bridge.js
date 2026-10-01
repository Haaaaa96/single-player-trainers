'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const mainSource=fs.readFileSync(path.join(__dirname,'acquisition_bridge.js'),'utf8');
const helpers=mainSource.slice(mainSource.indexOf('let currentNativeProfile'),mainSource.indexOf('const UPDATE_CANDIDATES'))+mainSource.slice(mainSource.indexOf('function reviewedRegistryRoot'),mainSource.indexOf('function validateMeridian'));
const source=fs.readFileSync(path.join(__dirname,'crafting_bridge.js'),'utf8');
const legacySpecs=JSON.parse(fs.readFileSync(path.join(__dirname,'crafting_specs.json'),'utf8')).methods;

function fixture(current=false) {
    const evidence=require('./native_method_evidence.json');
    const specs=Object.fromEntries(Object.entries(legacySpecs).map(([k,v])=>[k,current?{...v,...evidence.methods[v.token],parameters:v.parameters}:v]));
    const memory=new Map(),classes=new Map(),parameters=new Map(),anchors=[],writes=[];
    let next=0x3000000,context,result,failActivate=false,noSettlement=false,bonus=0.1,getterFailure=false,afterActivate=null,afterComplete=null;
    const calls=[];
    class P {
        constructor(v){this.v=v instanceof P?v.v:Number(v);}
        add(v){return new P(this.v+v);} sub(v){return new P(this.v-new P(v).v);} toInt32(){return this.v|0;} equals(v){return this.v===new P(v).v;} isNull(){return this.v===0;}
        toString(){return '0x'+this.v.toString(16);} compare(v){return Math.sign(this.v-new P(v).v);}
        readByteArray(n){return Uint8Array.from({length:n},(_,i)=>memory.get(this.v+i)||0).buffer;}
        writeByteArray(b){Array.from(b).forEach((v,i)=>memory.set(this.v+i,v));}
        readU8(){return memory.get(this.v)||0;} writeU8(v){memory.set(this.v,v);}
        readU16(){return Buffer.from(this.readByteArray(2)).readUInt16LE();}
        readU32(){return Buffer.from(this.readByteArray(4)).readUInt32LE();}
        readS32(){return Buffer.from(this.readByteArray(4)).readInt32LE();}
        writeS32(v){if(context?.state==='running')writes.push([this.toString(),v]);const b=Buffer.alloc(4);b.writeInt32LE(v);this.writeByteArray(b);}
        readFloat(){return Buffer.from(this.readByteArray(4)).readFloatLE();}
        writeFloat(v){const b=Buffer.alloc(4);b.writeFloatLE(v);this.writeByteArray(b);}
        readPointer(){return new P(Number(Buffer.from(this.readByteArray(8)).readBigUInt64LE()));}
        writePointer(v){const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(new P(v).v));this.writeByteArray(b);}
        readU64(){const n=this.readPointer().v;return {toNumber:()=>n};}
        readUtf8String(){const b=[];for(let i=0;i<256;i++){const v=this.add(i).readU8();if(!v)break;b.push(v);}return Buffer.from(b).toString();}
    }
    const ptr=v=>new P(v),alloc=()=>{const p=ptr(next);next+=0x1000;return p;};
    const base=ptr(0x1000000);
    const requireValue=(ok,message)=>{if(!ok)throw Error(message);};
    const samePointer=(a,b,message)=>requireValue(ptr(a).equals(b),message);
    function klass(ns,name){const p=alloc(),n=alloc(),s=alloc();n.writeByteArray(Buffer.from(name+'\0'));s.writeByteArray(Buffer.from(ns+'\0'));p.add(16).writePointer(n);p.add(24).writePointer(s);classes.set(p.toString(),[ns,name]);p.add(0xf8).writeS32(0x400);return p;}
    function object(ns,name){const p=alloc();p.writePointer(klass(ns,name));return p;}
    const className=(p,ns,name)=>{const k=ptr(p).readPointer(),pair=classes.get(k.toString());requireValue(pair&&pair[0]===ns&&pair[1]===name,'class mismatch '+name);return k;};
    const hexAt=(a,n)=>Buffer.from(ptr(a).readByteArray(n)).toString('hex');
    function anchor(p,n){p=ptr(p);anchors.push({address:p.toString(),size:n,expected_hex:hexAt(p,n)});}
    function coverage(a,n){const p=ptr(a);requireValue(anchors.some(x=>p.v>=ptr(x.address).v&&p.v+n<=ptr(x.address).v+x.size),'missing coverage');}
    function validate(){for(const a of anchors)requireValue(hexAt(a.address,a.size)===a.expected_hex,'anchor changed');}
    function fields(k,rows){const table=alloc();k.add(0x80).writePointer(table);k.add(0x124).writeS32(rows.length);
        rows.forEach(([name,token,kind,offset],i)=>{if(current)token=evidence.fields[classes.get(k.toString()).join('.')+':'+token]?.token??token;const p=table.add(i*32),s=alloc(),t=alloc();s.writeByteArray(Buffer.from(name+'\0'));t.add(10).writeU8(kind);t.add(11).writeU8(0x80);
            p.writePointer(s);p.add(8).writePointer(t);p.add(16).writePointer(k);p.add(24).writeS32(offset);p.add(28).writeS32(token);});}
    function method(owner,spec){const p=alloc(),n=alloc(),t=alloc();n.writeByteArray(Buffer.from(spec.name+'\0'));t.add(10).writeU8(spec.returns);t.add(11).writeU8(0x80);
        p.writePointer(base.add(spec.rva));p.add(0x18).writePointer(n);p.add(0x20).writePointer(owner);p.add(0x28).writePointer(t);p.add(0x48).writeS32(spec.token);p.add(0x52).writeU8(spec.argc);
        base.add(spec.rva).writeByteArray(Buffer.from(spec.prefix,'hex'));parameters.set(p.toString(),spec.parameters.map(kind=>{const t=alloc();t.add(10).writeU8(kind);t.add(11).writeU8(0x80);return t;}));return p;}
    function list(objects,config=false){const l=object(config?'Emei':'System.Collections.Generic',config?'NotifiableList`1':'List`1'),a=alloc();
        if(config){l.readPointer().add(0x58).writePointer(klass('System.Collections.Generic','List`1'));anchor(l.readPointer().add(0x58),8);}l.add(0x10).writePointer(a);l.add(0x18).writeS32(objects.length);a.add(24).writePointer(objects.length);
        objects.forEach((p,i)=>a.add(32+i*8).writePointer(p));anchor(l,0x20);anchor(a,32+objects.length*8);return l;}
    const panel=object('Game.UI.UPFLogic.Alchemy','UPFAlchemyPanel'),logic=object('Game','AlchemyGameLogic');
    const receipt=object('Game.UI.UPFLogic.Alchemy','AlchemyLaunchCostReceipt'),prototype=object('LubanDatas.data','AlchemyPrototype');
    const player=alloc(),bag=alloc(),combat=alloc();bag.add(16).writePointer(player);combat.add(16).writePointer(player);
    player.add(0x40).writePointer(bag);player.add(0x48).writePointer(combat);anchor(player,0x50);
    panel.add(16).writePointer(0x8888);panel.add(0x100).writePointer(logic);panel.add(0x130).writePointer(receipt);
    [0x42,0x43,0x92,0x18b].forEach(o=>panel.add(o).writeU8(1));
    fields(panel.readPointer(),[['_isPlayingFlyInAnimation',0x04009a53,2,0x208],['_pendingSettlement',0x04009a55,0x12,0x218]]);
    const placement=object('','PlacementSettlementData'),cleared=list([]),added=list([]);
    fields(placement.readPointer(),[['ClearedCells',0x04009a99,0x15,16],['AddedCells',0x04009a9a,0x15,24],
        ['ScoreBefore',0x04009a9b,8,32],['ScoreAfter',0x04009a9c,8,36],['ElementType',0x04009a9d,8,40]]);
    placement.add(16).writePointer(cleared);placement.add(24).writePointer(added);
    placement.add(32).writeS32(-1);placement.add(36).writeS32(-1);panel.add(0x218).writePointer(placement);anchor(placement,48);
    logic.add(16).writePointer(prototype);logic.add(0x58).writeS32(100);
    receipt.add(16).writePointer(bag);receipt.add(24).writePointer(combat);receipt.add(0x3d).writeU8(1);
    const tiers=[100,500,1000].map((score,i)=>{const p=object('LubanDatas','AlchemyScoreTierEntry');p.add(16).writeS32(i+1);p.add(20).writeS32(score);anchor(p,24);return {address:p.toString(),tier_id:i+1,score_min:score};});
    const tierList=list(tiers.map(t=>ptr(t.address)),true);prototype.add(0x50).writePointer(tierList);
    const effects=[15,30].map((required,i)=>{const p=object('Game','AlchemyEffectState'),config=object('LubanDatas','AlchemyEffect'),sourceConfig=object('LubanDatas','AlchemyArtifactAffixSlot');
        p.add(16).writePointer(config);
        for(const c of [config,sourceConfig]){c.add(16).writeS32(2);c.add(20).writeS32(i+1);c.add(24).writeS32(1);c.add(28).writeS32(required);c.add(32).writeS32(i+1);anchor(c,36);}anchor(p,36);
        return {address:p.toString(),config:config.toString(),source_config:sourceConfig.toString(),effect_type:2,sort:i+1,pool_id:i+1,element:1,required,activated:false,affix_id:0,affix_value:0};});
    const effectList=list(effects.map(e=>ptr(e.address)));logic.add(0x48).writePointer(effectList);
    const configList=list(effects.map(e=>ptr(e.source_config)),true);prototype.add(0x48).writePointer(configList);
    const energy=object('System.Collections.Generic','Dictionary`2'),entries=object('','Entry[]');energy.add(0x18).writePointer(entries);energy.add(0x20).writeS32(1);energy.add(0x2c).writeS32(4);
    const ec=klass('','Entry');ec.add(0xf8).writeS32(32);entries.readPointer().add(0x40).writePointer(ec);
    fields(ec,[['hashCode',0x04001b0d,8,16],['next',0x04001b0e,8,20],['key',0x04001b0f,8,24],['value',0x04001b10,8,28]]);
    entries.add(24).writePointer(3);entries.add(32).writeS32(1);entries.add(36).writeS32(-1);entries.add(40).writeS32(1);entries.add(44).writeS32(5);logic.add(0x40).writePointer(energy);
    const registryDictionary=alloc(),registryEntries=alloc();registryDictionary.add(0x18).writePointer(registryEntries);registryDictionary.add(0x20).writeS32(1);
    registryEntries.add(24).writePointer(1);registryEntries.add(32).writeS32(1);registryEntries.add(48).writePointer(panel);
    const manager=object('Game','UIManager');anchor(manager,8);const links=[];let address=current?manager.readPointer().add(0x58):base.add(0x8157868);for(let i=0;i<8;i++){const value=alloc();address.writePointer(value);anchor(address,8);links.push({address:address.toString(),expected:value.toString()});address=value.add(0x80);}
    const methods={};for(const [key,s]of Object.entries(specs))methods[key]=method(key==='complete'?panel.readPointer():logic.readPointer(),s).toString();
    for(const [p,n]of [[panel,0x240],[logic,0xa0],[receipt,0x40],[prototype,0x58],[bag,24],[combat,24],[energy,0x30],[entries,48],[registryDictionary,0x30],[registryEntries,56]])anchor(p,n);
    const m={panel:panel.toString(),logic:logic.toString(),receipt:receipt.toString(),prototype:prototype.toString(),player:player.toString(),bag:bag.toString(),combat:combat.toString(),
        placement:{address:placement.toString(),cleared:cleared.toString(),added:added.toString(),score_before:-1,score_after:-1,element:0,prewarm_complete:false},
        round_key:'a'.repeat(64),manager:manager.toString(),registry_links:links,registry:{dictionary:registryDictionary.toString(),entries:registryEntries.toString(),count:1},methods,
        score_address:logic.add(0x58).toString(),tier_list:tierList.toString(),effect_list:effectList.toString(),config_list:configList.toString(),tiers,effects,
        energy:{address:energy.toString(),entries:entries.toString(),count:1,free:0,version:4},plan:{score_before:100,score_after:1000,tier_minimum:1000,tier_id:3,effect_count:2,energy_updates:[{element:1,address:entries.add(44).v,before:5,after:30}]}};
    const request={anchors,minigame:m,operation:'crafting_complete',method_token:specs.complete.token,method_rva:specs.complete.rva,parameter_count:0,method_info:methods.complete,deadline:Date.now()+10000};
    const invoke=(mi,target,args,exception)=>{const key=Object.keys(methods).find(k=>ptr(methods[k]).equals(mi));calls.push(key);
        if(key==='bonus'){if(getterFailure)throw Error('getter fail');const b=alloc();b.add(16).writeFloat(bonus);return b;}
        if(key==='activate'&&!failActivate){assert.equal(args.readPointer().readU8(),1);effects.forEach(e=>{ptr(e.address).add(24).writeU8(1);ptr(e.address).add(28).writeS32(e.pool_id+10);});}
        if(key==='activate'&&afterActivate)afterActivate();
        if(key==='complete'&&!noSettlement)panel.add(0x228).writeU8(1);
        if(key==='complete'&&afterComplete)afterComplete();return ptr(0);};
    context=vm.createContext({request,state:'validating',image:{base},ptr,requireValue,samePointer,className,hexAt,requireCoverage:coverage,validateAnchors:validate,
        boolAt:p=>{const v=ptr(p).readU8();requireValue(v===0||v===1,'invalid bool');return v===1;},
        methodToken:p=>p.add(0x48).readU32(),paramCount:p=>p.add(0x52).readU8(),methodParam:(p,i)=>parameters.get(p.toString())[i],
        Memory:{alloc},Process:{getCurrentThreadId:()=>42,findRangeByAddress:p=>({base:p,size:4,protection:'rw-'})},invoke,finish:(status,data)=>result={status,...data},Date,console});
    vm.runInContext(helpers+'\ncurrentNativeProfile='+current+';\n'+source,context);
    return {m,request,panel,logic,receipt,prototype,energy,entries,methods,placement,cleared,added,player,bag,combat,ptr,anchors,parameters,context,calls,writes,
        setAfterActivate:fn=>afterActivate=fn,setAfterComplete:fn=>afterComplete=fn,setBonus:v=>bonus=v,setGetterFailure:()=>getterFailure=true,setActivationFailure:()=>failActivate=true,setNoSettlement:()=>noSettlement=true,
        updateAnchors:()=>anchors.forEach(a=>a.expected_hex=hexAt(a.address,a.size)),
        run(){try{vm.runInContext('executeCrafting()',context);}catch(error){result={status:context.state==='running'?'exception':'rejected',called:context.state==='running',reason:error.message};}return result;}};
}

let tests=0;
function test(name,fn){try{fn();tests++;}catch(e){e.message=name+': '+e.message;throw e;}}
function rejected(f){const r=f.run();assert.equal(r.status,'rejected',r.reason);assert.equal(r.called,false);assert.equal(f.writes.length,0);return r;}
test('native configured completion',()=>{const f=fixture(),r=f.run();assert.equal(r.status,'completed',r.reason);assert.equal(r.settlement_started,true);assert.equal(r.effect_count,2);assert.deepEqual(f.calls,['bonus','activate','complete']);assert.equal(f.logic.add(0x58).readS32(),1000);assert.equal(f.entries.add(44).readS32(),30);});
for(const o of [0x42,0x43,0x92,0x18b])test('required active '+o,()=>{const f=fixture();f.panel.add(o).writeU8(0);rejected(f);});
for(const o of [0x58,0x93,0x138,0x188,0x18a,0x228,0x208])test('busy flag '+o,()=>{const f=fixture();f.panel.add(o).writeU8(1);rejected(f);});
test('replaced settlement object',()=>{const f=fixture();f.panel.add(0x218).writePointer(0x800);rejected(f);});
test('receipt not committed',()=>{const f=fixture();f.receipt.add(0x3d).writeU8(0);rejected(f);});
test('receipt already complete',()=>{const f=fixture();f.receipt.add(0x3e).writeU8(1);rejected(f);});
test('score forged beyond config',()=>{const f=fixture();f.m.plan.score_after=99999;rejected(f);});
test('score changed after read',()=>{const f=fixture();f.logic.add(0x58).writeS32(101);rejected(f);});
test('energy target forged',()=>{const f=fixture();f.m.plan.energy_updates[0].address+=4;rejected(f);});
test('energy configured threshold forged',()=>{const f=fixture();f.m.plan.energy_updates[0].after=99;rejected(f);});
test('missing energy update',()=>{const f=fixture();f.m.plan.energy_updates=[];rejected(f);});
test('energy entry changed',()=>{const f=fixture();f.entries.add(44).writeS32(10);rejected(f);});
test('dictionary version changed',()=>{const f=fixture();f.energy.add(0x2c).writeS32(5);rejected(f);});
test('registry chain missing',()=>{const f=fixture();f.m.registry_links=[];rejected(f);});
test('anchor coverage missing',()=>{const f=fixture();f.anchors.length=0;rejected(f);});
test('method owner changed',()=>{const f=fixture();f.ptr(f.methods.activate).add(0x20).writePointer(123);rejected(f);});
test('write region protected',()=>{const f=fixture();f.context.Process.findRangeByAddress=p=>({base:p,size:4,protection:'r--'});rejected(f);});
test('write region partial',()=>{const f=fixture();f.context.Process.findRangeByAddress=p=>({base:p,size:3,protection:'rw-'});rejected(f);});
test('entry value type differs',()=>{const f=fixture();const ec=f.entries.readPointer().add(0x40).readPointer();ec.add(0x80).readPointer().add(3*32+8).readPointer().add(10).writeU8(12);rejected(f);});
test('entry size differs',()=>{const f=fixture();f.entries.readPointer().add(0x40).readPointer().add(0xf8).writeS32(40);rejected(f);});
test('prototype config list differs',()=>{const f=fixture();f.prototype.add(0x48).writePointer(0);rejected(f);});
test('bool param changed',()=>{const f=fixture();f.parameters.get(f.methods.activate)[0].add(10).writeU8(8);rejected(f);});
test('reference param rejected',()=>{const f=fixture();f.parameters.get(f.methods.activate)[0].add(11).writeU8(0xc0);rejected(f);});
for(const value of [-1,NaN,Infinity,11])test('bonus validation '+value,()=>{const f=fixture();f.setBonus(value);rejected(f);assert.deepEqual(f.calls,['bonus']);});
test('getter throws before mutation called false',()=>{const f=fixture();f.setGetterFailure();rejected(f);});
test('deadline expires before mutation',()=>{const f=fixture();f.request.deadline=0;const r=f.run();assert.equal(r.status,'cancelled');assert.equal(r.called,false);assert.equal(f.writes.length,0);});
test('partial activation remains called true unknown',()=>{const f=fixture();f.setActivationFailure();const r=f.run();assert.equal(r.status,'exception');assert.equal(r.called,true);assert.ok(f.writes.length);assert.deepEqual(f.calls,['bonus','activate']);});
test('native guard no settlement remains unknown',()=>{const f=fixture();f.setNoSettlement();const r=f.run();assert.equal(r.status,'exception');assert.equal(r.called,true);});
test('completed prewarm can also be ready',()=>{const f=fixture();f.panel.add(0x189).writeU8(1);f.m.placement.prewarm_complete=true;f.updateAnchors();assert.equal(f.run().status,'completed');});
for(const offset of [0x160,0x168])test('startup coroutine pending '+offset,()=>{const f=fixture();f.panel.add(offset).writePointer(0x800);rejected(f);});
for(const key of ['cleared','added'])test('pending placement cells '+key,()=>{const f=fixture();f[key].add(24).writeS32(1);rejected(f);});
for(const offset of [32,36])test('unconsumed score '+offset,()=>{const f=fixture();f.placement.add(offset).writeS32(0);rejected(f);});
test('consumed nonzero element is legitimate',()=>{const f=fixture();f.placement.add(40).writeS32(5);f.m.placement.element=5;f.updateAnchors();assert.equal(f.run().status,'completed');});
test('invalid placement element refuses',()=>{const f=fixture();f.placement.add(40).writeS32(6);f.m.placement.element=6;f.updateAnchors();rejected(f);});
function changedDuringActivation(name,change){test(name,()=>{const f=fixture();f.setAfterActivate(()=>change(f));const r=f.run();assert.equal(r.status,'exception',r.reason);assert.equal(r.called,true);assert.deepEqual(f.calls,['bonus','activate']);});}
changedDuringActivation('activation callback changes panel logic',f=>f.panel.add(0x100).writePointer(0));
changedDuringActivation('activation callback changes player bag',f=>f.player.add(0x40).writePointer(0));
changedDuringActivation('activation callback closes panel',f=>f.panel.add(0x42).writeU8(0));
changedDuringActivation('activation callback pauses panel',f=>f.panel.add(0x93).writeU8(1));
changedDuringActivation('activation callback starts settlement',f=>f.panel.add(0x228).writeU8(1));
changedDuringActivation('activation callback replaces receipt',f=>f.panel.add(0x130).writePointer(0));
changedDuringActivation('activation callback changes effect list',f=>f.ptr(f.m.effect_list).add(24).writeS32(0));
changedDuringActivation('activation callback changes registry entry',f=>f.ptr(f.m.registry.entries).add(48).writePointer(0));
changedDuringActivation('adjacent unallowed byte in score anchor is checked',f=>f.logic.add(0x5c).writeU8(1));
changedDuringActivation('adjacent energy key is checked',f=>f.entries.add(40).writeS32(2));
changedDuringActivation('permitted score field still requires requested result',f=>f.logic.add(0x58).writeS32(999));
changedDuringActivation('permitted energy field still requires requested result',f=>f.entries.add(44).writeS32(31));
test('complete callback changes original identity is unknown',()=>{const f=fixture();f.setAfterComplete(()=>f.panel.add(0x100).writePointer(0));const r=f.run();assert.equal(r.status,'exception');assert.equal(r.called,true);});
test('complete may normally pause the panel for result modal',()=>{const f=fixture();f.setAfterComplete(()=>f.panel.add(0x93).writeU8(1));assert.equal(f.run().status,'completed');});
test('configuration list must inherit the native List type',()=>{const f=fixture();f.ptr(f.m.tier_list).readPointer().add(0x58).writePointer(f.panel.readPointer());f.updateAnchors();rejected(f);});
test('prototype slot and runtime copy disagree',()=>{const f=fixture();f.ptr(f.m.effects[0].source_config).add(28).writeS32(99);f.updateAnchors();rejected(f);});
test('runtime unsupported effect kind rejected',()=>{const f=fixture();for(const key of ['config','source_config'])f.ptr(f.m.effects[0][key]).add(16).writeS32(1);f.m.effects[0].effect_type=1;f.updateAnchors();rejected(f);});
test('existing finite float affix preserved',()=>{const f=fixture();f.ptr(f.m.effects[0].address).add(32).writeFloat(1.25);f.m.effects[0].affix_value=1.25;f.updateAnchors();assert.equal(f.run().status,'completed');});
changedDuringActivation('activation creates invalid float affix',f=>f.ptr(f.m.effects[0].address).add(32).writeFloat(NaN));
test('current crafting reviewed entries and canonical root',()=>{const f=fixture(true),r=f.run();assert.equal(r.status,'completed',JSON.stringify(r));});
console.log(`${tests} crafting bridge tests passed`);
