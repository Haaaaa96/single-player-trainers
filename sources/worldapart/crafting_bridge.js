/* Merge into acquisition_bridge.js; dispatch executeCrafting() on Unity thread.
 * This is not an independently loadable agent and must never be attached alone.
 */
const CRAFTING_METHODS = {
    complete: nativeSpec({name:'OnBtnComplete', token:0x06012ac9, rva:0xc5c900, returns:1, params:[], prefix:'48897c242041564883ec50803d53ba8e'}),
    activate: nativeSpec({name:'CheckEffectActivation', token:0x06009500, rva:0x16a8c30, returns:1, params:[2], prefix:'405657415641574883ec58803d6245ea'}),
    bonus: nativeSpec({name:'GetBonusRatio', token:0x0600950e, rva:0x16ac580, returns:12, params:[], prefix:'40534883ec30803d230cea0600488bd9'})
};
function craftingInt(value, minimum=0, maximum=1000000) {
    requireValue(Number.isInteger(value) && value>=minimum && value<=maximum, 'Invalid crafting integer');
    return value;
}
function craftingField(object, klass, name, token, kind, expectedOffset=null) {
    const count=klass.add(0x124).readU16(), fields=klass.add(0x80).readPointer();
    requireValue(count>0 && count<=256 && !fields.isNull(),'Invalid crafting fields');
    const found=[];
    for(let i=0;i<count;i++) {
        const field=fields.add(i*32);
        if(field.readPointer().readUtf8String()!==name) continue;
        const type=field.add(8).readPointer(), offset=field.add(24).readS32();
        samePointer(field.add(16).readPointer(),klass,'Crafting field owner differs');
        requireValue(field.add(28).readU32()===reviewedFieldToken(klass,token,name) && type.add(10).readU8()===kind &&
            (type.add(8).readU16()&0x50)===0 && (type.add(11).readU8()&0x7f)===0 &&
            offset>=16 && offset<klass.add(0xf8).readU32() &&
            (expectedOffset===null || offset===expectedOffset),'Crafting field layout differs');
        found.push(ptr(object).add(offset));
    }
    requireValue(found.length===1,'Crafting field missing or ambiguous');
    requireCoverage(found[0],kind===2?1:(kind===0x12 || kind===0x15?8:4));
    return found[0];
}
function craftingMethod(address, klass, spec) {
    const method=ptr(address), type=method.add(0x28).readPointer();
    samePointer(method.readPointer(),image.base.add(spec.rva),'Crafting method code differs');
    samePointer(method.add(0x20).readPointer(),klass,'Crafting method owner differs');
    requireValue(methodToken(method)===spec.token && paramCount(method)===spec.params.length &&
        method.add(0x18).readPointer().readUtf8String()===spec.name &&
        (method.add(0x4c).readU16()&0x10)===0 && type.add(10).readU8()===spec.returns &&
        (type.add(11).readU8()&0x7f)===0 &&
        hexAt(image.base.add(spec.rva),spec.prefix.length/2)===spec.prefix,'Crafting method signature differs');
    for(let i=0;i<spec.params.length;i++) {
        const p=methodParam(method,i);
        requireValue(p.add(10).readU8()===spec.params[i] && (p.add(11).readU8()&0x7f)===0,
            'Crafting method parameter differs');
    }
    return method;
}
function craftingInvoke(method,target,values) {
    const args=values.length?Memory.alloc(values.length*8):ptr(0), exception=Memory.alloc(8);
    values.forEach((value,index)=>args.add(index*8).writePointer(value)); exception.writePointer(ptr(0));
    const result=invoke(method,target,args,exception);
    requireValue(exception.readPointer().isNull(),'Crafting native exception; never retry');
    return result;
}
function craftingList(address, expected, namespace, name, config=false) {
    const list=ptr(address);
    if(config) {
        const klass=className(list,'Emei','NotifiableList`1');
        requireCoverage(klass.add(0x58),8);
        // className accepts objects, so use a local pointer slot to inspect the
        // canonical parent class without ever writing a game pointer.
        const parent=Memory.alloc(8);parent.writePointer(klass.add(0x58).readPointer());
        className(parent,'System.Collections.Generic','List`1');
    } else className(list,'System.Collections.Generic','List`1');
    requireCoverage(list.add(0x10),8);requireCoverage(list.add(0x18),4);requireCoverage(list.add(0x1c),4);
    const array=list.add(0x10).readPointer(), size=list.add(0x18).readS32();
    requireValue(Array.isArray(expected) && expected.length<=32 && size===expected.length &&
        !array.isNull() && array.add(24).readU64().toNumber()>=size &&
        array.add(24).readU64().toNumber()<=64,'Crafting list changed');
    requireCoverage(array.add(24),8);
    for(let i=0;i<size;i++) {
        requireCoverage(array.add(32+i*8),8);
        const object=array.add(32+i*8).readPointer();
        samePointer(object,expected[i].address,'Crafting list item changed');
        className(object,namespace,name);
    }
}
function craftingWritable(address) {
    const p=ptr(address), range=Process.findRangeByAddress(p);
    requireValue(range && range.protection==='rw-' && p.compare(range.base)>=0 &&
        p.add(4).compare(range.base.add(range.size))<=0,'Crafting scalar is not ordinary writable memory');
}
function craftingValidateActivationAnchors(m) {
    // A synchronous OnLog delegate can run during activation. Compare every
    // original proof byte except the exact scalar fields this action changes;
    // never discard an entire anchor just because one permitted byte overlaps.
    const changed=[{address:ptr(m.score_address),size:4}];
    for(const update of m.plan.energy_updates) changed.push({address:ptr(update.address),size:4});
    for(const effect of m.effects) {
        changed.push({address:ptr(effect.address).add(24),size:1});
        changed.push({address:ptr(effect.address).add(28),size:8});
    }
    for(const anchor of request.anchors) {
        const first=ptr(anchor.address),last=first.add(anchor.size),actual=hexAt(first,anchor.size);
        let expected=anchor.expected_hex;
        for(const range of changed) {
            const end=range.address.add(range.size);
            if(range.address.compare(last)>=0 || end.compare(first)<=0) continue;
            const begin=range.address.compare(first)>0?range.address:first;
            const stop=end.compare(last)<0?end:last;
            const i=begin.sub(first).toInt32()*2,j=stop.sub(first).toInt32()*2;
            expected=expected.slice(0,i)+actual.slice(i,j)+expected.slice(j);
        }
        requireValue(actual===expected,'Crafting identity or phase changed during activation; never retry');
    }
    requireValue(ptr(m.score_address).readS32()===m.plan.score_after,'Crafting score changed during activation');
    for(const update of m.plan.energy_updates)
        requireValue(ptr(update.address).readS32()===update.after,'Crafting energy changed during activation');
}
function executeCrafting() {
    const m=request.minigame;
    requireValue(m && /^[a-f0-9]{64}$/.test(m.round_key) && request.operation==='crafting_complete',
        'Invalid crafting round identity');
    requireValue(request.method_token===CRAFTING_METHODS.complete.token && request.method_rva===CRAFTING_METHODS.complete.rva &&
        request.parameter_count===0,'Crafting completion method not whitelisted');
    const panel=ptr(m.panel), logic=ptr(m.logic), receipt=ptr(m.receipt), prototype=ptr(m.prototype);
    const pc=className(panel,'Game.UI.UPFLogic.Alchemy','UPFAlchemyPanel');
    const lc=className(logic,'Game','AlchemyGameLogic');
    className(receipt,'Game.UI.UPFLogic.Alchemy','AlchemyLaunchCostReceipt');
    className(prototype,'LubanDatas.data','AlchemyPrototype');
    requireValue(!panel.add(16).readPointer().isNull(),'Destroyed crafting panel');
    for(const offset of [0x42,0x43,0x92]) {requireCoverage(panel.add(offset),1);requireValue(boolAt(panel.add(offset)),'Crafting panel not active');}
    for(const offset of [0x58,0x93,0x138,0x188,0x18a,0x228]) {requireCoverage(panel.add(offset),1);requireValue(!boolAt(panel.add(offset)),'Crafting panel busy or ended');}
    requireCoverage(panel.add(0x18b),1);requireValue(boolAt(panel.add(0x18b)),'Crafting interaction not enabled');
    requireCoverage(panel.add(0x189),1);boolAt(panel.add(0x189));
    for(const offset of [0x160,0x168]) {requireCoverage(panel.add(offset),8);requireValue(panel.add(offset).readPointer().isNull(),'Crafting startup coroutine not complete');}
    const flight=craftingField(panel,pc,'_isPlayingFlyInAnimation',0x04009a53,2);
    const pending=craftingField(panel,pc,'_pendingSettlement',0x04009a55,0x12);
    requireValue(!boolAt(flight),'Crafting placement still animating');
    const placement=m.placement, data=pending.readPointer();
    requireValue(placement && !data.isNull(),'Missing placement settlement state');
    samePointer(data,placement.address,'Placement settlement object replaced');
    const dc=className(data,'','PlacementSettlementData');
    for(const [name,token,offset,key] of [['ClearedCells',0x04009a99,16,'cleared'],['AddedCells',0x04009a9a,24,'added']]) {
        const list=craftingField(data,dc,name,token,0x15,offset).readPointer();
        samePointer(list,placement[key],'Placement cell collection replaced');
        className(list,'System.Collections.Generic','List`1');
        requireCoverage(list.add(0x10),8);requireCoverage(list.add(0x18),4);requireCoverage(list.add(0x1c),4);
        requireValue(list.add(0x18).readS32()===0,'Placement cell animation pending');
    }
    for(const [name,token,offset,key] of [['ScoreBefore',0x04009a9b,32,'score_before'],['ScoreAfter',0x04009a9c,36,'score_after']]) {
        const value=craftingField(data,dc,name,token,8,offset).readS32();
        requireValue(value===-1 && placement[key]===-1,'Placement score settlement pending');
    }
    const element=craftingField(data,dc,'ElementType',0x04009a9d,8,40).readS32();
    requireValue(element===placement.element && element>=0 && element<=5 &&
        boolAt(panel.add(0x189))===placement.prewarm_complete,'Placement/prewarm state changed');
    samePointer(panel.add(0x100).readPointer(),logic,'Crafting logic replaced');
    samePointer(panel.add(0x130).readPointer(),receipt,'Crafting receipt replaced');
    samePointer(logic.add(0x10).readPointer(),prototype,'Crafting prototype replaced');
    for(const [p,n] of [[panel.add(16),8],[panel.add(0x100),8],[panel.add(0x130),8],[logic.add(0x10),8],
                        [receipt.add(0x10),8],[receipt.add(0x18),8],[receipt.add(0x3d),1],[receipt.add(0x3e),1]]) requireCoverage(p,n);
    requireValue(boolAt(receipt.add(0x3d)) && !boolAt(receipt.add(0x3e)),'Crafting cost not committed or already completed');
    samePointer(receipt.add(0x10).readPointer(),m.bag,'Crafting receipt bag changed');
    samePointer(receipt.add(0x18).readPointer(),m.combat,'Crafting receipt combat changed');
    samePointer(ptr(m.bag).add(16).readPointer(),m.player,'Crafting receipt owner changed');
    samePointer(ptr(m.combat).add(16).readPointer(),m.player,'Crafting combat owner changed');
    samePointer(ptr(m.player).add(0x40).readPointer(),m.bag,'Player bag changed');
    samePointer(ptr(m.player).add(0x48).readPointer(),m.combat,'Player combat changed');
    for(const [p,n] of [[ptr(m.player).add(0x40),8],[ptr(m.player).add(0x48),8],
                        [ptr(m.bag).add(16),8],[ptr(m.combat).add(16),8]]) requireCoverage(p,n);
    requireValue(Array.isArray(m.registry_links) && m.registry_links.length>=8,'Missing crafting registration chain');
    reviewedRegistryRoot(m);
    for(const link of m.registry_links) {requireCoverage(link.address,8);samePointer(ptr(link.address).readPointer(),link.expected,'Crafting registry link changed');}
    const registry=m.registry, dictionary=ptr(registry.dictionary), entries=ptr(registry.entries);
    samePointer(dictionary.add(0x18).readPointer(),entries,'Crafting panel registry replaced');
    requireValue(dictionary.add(0x20).readS32()===registry.count && registry.count>0 && registry.count<=512,'Crafting registry changed');
    let matches=0;
    for(let i=0;i<registry.count;i++) {
        const entry=entries.add(32+i*24);requireCoverage(entry,24);
        if(entry.readS32()>=0 && entry.add(16).readPointer().equals(panel)) matches++;
    }
    requireValue(matches===1,'Crafting panel is not uniquely registered');
    const methods={};
    for(const key of Object.keys(CRAFTING_METHODS)) methods[key]=craftingMethod(m.methods[key],key==='complete'?pc:lc,CRAFTING_METHODS[key]);
    samePointer(methods.complete,request.method_info,'Crafting completion descriptor differs');
    const plan=m.plan;
    craftingInt(plan.score_before);craftingInt(plan.score_after);craftingInt(plan.tier_minimum,1);
    requireCoverage(logic.add(0x58),4);samePointer(logic.add(0x58),m.score_address,'Invalid crafting score field');
    requireValue(logic.add(0x58).readS32()===plan.score_before,'Crafting score changed');
    samePointer(prototype.add(0x50).readPointer(),m.tier_list,'Crafting tiers changed');
    craftingList(m.tier_list,m.tiers,'LubanDatas','AlchemyScoreTierEntry',true);
    const tierIds=new Set(),thresholds=new Set();let highest=null;
    for(const tier of m.tiers) {
        const address=ptr(tier.address);requireCoverage(address.add(0x10),4);requireCoverage(address.add(0x14),4);
        const id=craftingInt(address.add(0x10).readS32(),1), threshold=craftingInt(address.add(0x14).readS32());
        requireValue(id===tier.tier_id && threshold===tier.score_min && !tierIds.has(id) && !thresholds.has(threshold),'Crafting tier changed or duplicate');
        tierIds.add(id);thresholds.add(threshold);
        if(highest===null || threshold>highest.score_min) highest=tier;
    }
    requireValue(highest && highest.tier_id===plan.tier_id && highest.score_min===plan.tier_minimum &&
        plan.score_after===Math.max(plan.score_before,highest.score_min),'Crafting plan is not highest configured tier');
    samePointer(logic.add(0x48).readPointer(),m.effect_list,'Crafting effects replaced');
    craftingList(m.effect_list,m.effects,'Game','AlchemyEffectState');
    samePointer(prototype.add(0x48).readPointer(),m.config_list,'Prototype effect configuration replaced');
    craftingList(m.config_list,m.effects.map(effect=>({address:effect.source_config})),'LubanDatas','AlchemyArtifactAffixSlot',true);
    const required=new Map();
    for(const effect of m.effects) {
        const address=ptr(effect.address), config=ptr(effect.config), sourceConfig=ptr(effect.source_config);
        samePointer(address.add(16).readPointer(),config,'Crafting effect config changed');
        className(config,'LubanDatas','AlchemyEffect');
        className(sourceConfig,'LubanDatas','AlchemyArtifactAffixSlot');
        for(const [offset,key] of [[16,'effect_type'],[20,'pool_id'],[24,'element'],[28,'required'],[32,'sort']]) {
            requireCoverage(config.add(offset),4);requireCoverage(sourceConfig.add(offset),4);
            const value=config.add(offset).readS32();
            requireValue(value===sourceConfig.add(offset).readS32() && value===effect[key],
                'Crafting runtime effect differs from prototype slot');
        }
        requireValue(effect.effect_type===2,'Crafting effect type has not been reviewed');
        for(const [p,n] of [[address.add(16),8],[address.add(24),1],[address.add(28),4],[address.add(32),4],
                           [config.add(20),4],[config.add(24),4],[config.add(28),4]]) requireCoverage(p,n);
        const element=craftingInt(config.add(24).readS32(),1,5), energy=craftingInt(config.add(28).readS32());
        requireValue(element===effect.element && energy===effect.required && config.add(20).readS32()===effect.pool_id &&
            boolAt(address.add(24))===effect.activated && address.add(28).readS32()===effect.affix_id &&
            Number.isFinite(effect.affix_value) && address.add(32).readFloat()===effect.affix_value,'Crafting effect state changed');
        required.set(element,Math.max(required.get(element)||0,energy));
    }
    const energy=ptr(m.energy.address), array=ptr(m.energy.entries);
    className(energy,'System.Collections.Generic','Dictionary`2');
    const arrayClass=className(array,'','Entry[]'), entryClass=arrayClass.add(0x40).readPointer();
    requireValue(!entryClass.isNull() && entryClass.add(0xf8).readU32()===32,'Energy entry layout differs');
    samePointer(logic.add(0x40).readPointer(),energy,'Crafting energy replaced');
    samePointer(energy.add(0x18).readPointer(),array,'Crafting energy entries changed');
    const count=energy.add(0x20).readS32(),free=energy.add(0x28).readS32();
    requireValue(count===m.energy.count && free===m.energy.free && energy.add(0x2c).readS32()===m.energy.version &&
        count>=0 && count<=32 && free>=0 && free<=count && array.add(24).readU64().toNumber()>=count &&
        array.add(24).readU64().toNumber()<=64,'Crafting energy structure changed');
    const values=new Map();
    for(let i=0;i<count;i++) {
        const entry=array.add(32+i*16);requireCoverage(entry,16);
        for(const [name,token,offset] of [['hashCode',0x04001b0d,16],['next',0x04001b0e,20],
                                        ['key',0x04001b0f,24],['value',0x04001b10,28]])
            craftingField(entry.add(-16),entryClass,name,token,8,offset);
        if(entry.readS32()<0) continue;
        const key=craftingInt(entry.add(8).readS32(),1,5);craftingInt(entry.add(12).readS32());
        requireValue(!values.has(key),'Duplicate crafting energy');values.set(key,entry.add(12));
    }
    requireValue(values.size===count-free && Array.isArray(plan.energy_updates) && plan.energy_updates.length===required.size,
        'Incomplete crafting energy plan');
    const updates=new Set();
    for(const update of plan.energy_updates) {
        const address=values.get(update.element);
        requireValue(address && required.has(update.element) && !updates.has(update.element),'Unconfigured crafting energy write');
        updates.add(update.element);samePointer(address,update.address,'Wrong crafting energy value address');
        requireValue(address.readS32()===update.before && update.after===Math.max(update.before,required.get(update.element)),
            'Crafting energy plan is not exact configured minimum');
        craftingInt(update.after);
    }
    const bonusBox=craftingInvoke(methods.bonus,logic,[]);
    requireValue(!bonusBox.isNull(),'Crafting bonus unavailable');
    const bonus=bonusBox.add(16).readFloat();
    requireValue(Number.isFinite(bonus) && bonus>=0 && bonus<=10 && plan.score_after*(1+bonus)<=100000000,
        'Crafting score bonus outside reviewed range');
    craftingWritable(logic.add(0x58));
    for(const update of plan.energy_updates) craftingWritable(update.address);
    validateAnchors();
    if(Date.now()>request.deadline) {finish('cancelled',{called:false,reason:'Crafting request expired before mutation'});return;}
    // Completion may legitimately open a result modal, so the post-completion
    // check keeps ownership/object identity without requiring active UI flags.
    const roundPointers=[panel.add(16),panel.add(0x100),panel.add(0x130),logic.add(16),
        receipt.add(16),receipt.add(24),ptr(m.player).add(0x40),ptr(m.player).add(0x48),
        ptr(m.bag).add(16),ptr(m.combat).add(16),logic.add(0x48),prototype.add(0x48),prototype.add(0x50)]
        .map(address=>({address,expected:hexAt(address,8)}));
    // From the first bounded scalar write onward every failure is uncertain.
    state='running';
    for(const update of plan.energy_updates) if(update.before!==update.after) ptr(update.address).writeS32(update.after);
    if(plan.score_before!==plan.score_after) logic.add(0x58).writeS32(plan.score_after);
    const generate=Memory.alloc(1);generate.writeU8(1);
    craftingInvoke(methods.activate,logic,[generate]);
    craftingValidateActivationAnchors(m);
    const activated=m.effects.every(effect=>boolAt(ptr(effect.address).add(24)) && ptr(effect.address).add(28).readS32()>0 &&
        Number.isFinite(ptr(effect.address).add(32).readFloat()));
    requireValue(activated,'Some native affix pools did not activate; do not retry');
    craftingInvoke(methods.complete,panel,[]);
    for(const identity of roundPointers)
        requireValue(hexAt(identity.address,8)===identity.expected,'Crafting identity changed during completion; never retry');
    const started=boolAt(panel.add(0x228));
    requireValue(started,'Native completion did not start; do not retry');
    finish('completed',{called:true,round_key:m.round_key,thread_id:Process.getCurrentThreadId(),
        settlement_started:started,all_effects_activated:true,effect_count:m.effects.length,tier_id:plan.tier_id});
}
