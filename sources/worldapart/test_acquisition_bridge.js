/* Offline contract tests for the one-shot Frida bridge, including 64-bit UIDs. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'acquisition_bridge.js'), 'utf8');

function fixture(operation = 'add', overrides = {}, current = false) {
    const bytes = new Map(); let next = 0x3000000n, callback, timer, detached = false, calls = 0;
    let failNative = false, managedException = false, noWin = false, unchangedReturn = false, getterCalls = 0;
    const options = {}, methodSpecs = new Map(), parameterTypes = new Map(), typeClasses = new Map(), nativeNames = [];
    const emitted = [];
    class P {
        constructor(value) { this.value = value instanceof P ? value.value : BigInt(value); }
        add(value) { return new P(this.value + BigInt(value)); }
        compare(other) { const v = new P(other).value; return this.value < v ? -1 : this.value > v ? 1 : 0; }
        readU8() { return bytes.get(this.value) || 0; }
        readU16() { return Buffer.from(this.readByteArray(2)).readUInt16LE(); }
        readU32() { return Buffer.from(this.readByteArray(4)).readUInt32LE(); }
        readS32() { return Buffer.from(this.readByteArray(4)).readInt32LE(); }
        readFloat() { return Buffer.from(this.readByteArray(4)).readFloatLE(); }
        readU64() { const v = Buffer.from(this.readByteArray(8)).readBigUInt64LE(); return {toNumber:()=>Number(v)}; }
        readUtf8String() { const data=[]; for (let i=0;i<256;i++) {const b=bytes.get(this.value+BigInt(i))||0;if(!b)break;data.push(b);}return Buffer.from(data).toString('utf8'); }
        writeFloat(value) { const b=Buffer.alloc(4);b.writeFloatLE(value);this.writeByteArray(b); }
        writeU8(value) { this.writeByteArray([value]); }
        equals(other) { return this.value === new P(other).value; }
        isNull() { return this.value === 0n; }
        toString() { return '0x' + this.value.toString(16); }
        readByteArray(size) { return Uint8Array.from({length:size}, (_, i) => bytes.get(this.value + BigInt(i)) || 0).buffer; }
        writeByteArray(data) { Array.from(data).forEach((b, i) => bytes.set(this.value + BigInt(i), b)); }
        readPointer() { return new P(Buffer.from(this.readByteArray(8)).readBigUInt64LE()); }
        writePointer(value) { const b=Buffer.alloc(8); b.writeBigUInt64LE(new P(value).value); this.writeByteArray(b); }
        writeS32(value) { const b=Buffer.alloc(4); b.writeInt32LE(value); this.writeByteArray(b); }
        writeS64(value) {
            if (!value || value.kind !== 'Int64') throw new TypeError('Int64 object expected');
            const b=Buffer.alloc(8); b.writeBigInt64LE(value.value); this.writeByteArray(b);
        }
    }
    const ptr = v => new P(v);
    const base = ptr(0x1000000);
    const item = ptr(0x2000000), method = ptr(0x2100000), anchor = ptr(0x2200000);
    const request = Object.assign({operation, token:'one', pid:12, item_id:91002, quantity:1, uid:'9007199254740993',
        player:'0x2300000', bag:item.toString(), method_info:method.toString(),
        method_rva:operation === 'add' ? 0xe9bdd0 : 0xea0700,
        method_token:operation === 'add' ? 0x06015191 : 0x060151c2,
        parameter_count:operation === 'add' ? 5 : 2,
        anchors:[{address:anchor.toString(),size:4,expected_hex:'01000000',label:'current save'}],
        deadline:Date.now()+10000}, overrides);
    base.add(0x14342d0).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
    item.add(16).writePointer(request.player); method.writePointer(base.add(request.method_rva)); anchor.writeS32(1);
    let meridian, character, stamina, interact;
    function addAnchor(address, size) {
        request.anchors.push({address:ptr(address).toString(),size,expected_hex:Buffer.from(ptr(address).readByteArray(size)).toString('hex'),label:'meridian proof'});
    }
    function klass(namespace, name) {
        const k=ptr(next); next+=0x200n;
        const n=ptr(next);next+=0x100n; const ns=ptr(next);next+=0x100n;
        n.writeByteArray(Buffer.from(name+'\0'));ns.writeByteArray(Buffer.from(namespace+'\0'));
        k.add(16).writePointer(n);k.add(24).writePointer(ns);return k;
    }
    function reviewedMethod(address, owner, spec, wrapper) {
        const name=ptr(next);next+=0x100n;const type=ptr(next);next+=0x100n;
        name.writeByteArray(Buffer.from(spec.name+'\0'));type.add(10).writeU8(spec.kind);
        type.add(11).writeU8(spec.kind === 1 ? 0 : 0x80); // Real v31 by-value type marker.
        address.writePointer(base.add(spec.rva));address.add(0x18).writePointer(name);
        address.add(0x20).writePointer(owner);address.add(0x28).writePointer(type);
        address.add(0x48).writeS32(spec.token);address.add(0x52).writeU8(spec.params.length);
        base.add(spec.rva).writeByteArray(Buffer.from(spec.prefix,'hex'));
        const params=spec.params.map(kind=>{const t=ptr(next);next+=0x100n;t.add(10).writeU8(kind);t.add(11).writeU8(0x80);return t;});
        parameterTypes.set(address.toString(),params);methodSpecs.set(address.toString(),spec);
        if(wrapper)typeClasses.set(params[0].toString(),wrapper);
        return params;
    }
    if (operation==='add') {
        const owner=klass('Game.Model.Components','BagModel');item.writePointer(owner);
        reviewedMethod(method,owner,{name:'AddItem',token:0x06015191,rva:0xe9bdd0,
            kind:0x12,params:[0x11,8,0x11,0x15,0x12],prefix:'44894c24204489442418895424104889'});
    }
    if (operation==='meridian_solve') {
        request.method_token=0x06010174;request.method_rva=0x1dac830;request.parameter_count=0;
        for(const [rva,hex] of [[0x1dac830,'40535556574883ec38803dbe467a0600'],
            [0x1dabad0,'44884c24204488442418488954241055'],[0xa4caf0,'40534883ec20803d1ca3af0700488bd9'],
            [0x1dae1c0,'48895c2410574883ec40803d562d7a06']]) base.add(rva).writeByteArray(Buffer.from(hex,'hex'));
        const panel=ptr(0x4000000), game=ptr(0x4001000), config=ptr(0x4002000), manager=ptr(0x4003000);
        const collection=ptr(0x4004000),items=ptr(0x4005000),array=ptr(0x4006000);
        const dictionary=ptr(0x4007000),entries=ptr(0x4008000);
        const ns='Game.UI.UPFLogic.MedGame', gameClass=klass(ns,'MedGameViewModel');
        panel.writePointer(klass(ns,'MedGamePanel'));game.writePointer(gameClass);config.writePointer(klass(ns,'MedGameConfig'));
        manager.writePointer(klass('Game','UIManager'));collection.writePointer(klass('Loxodon.Framework.Observables','ObservableList`1'));
        items.writePointer(klass('System.Collections.Generic','List`1'));
        panel.add(16).writePointer(0xdead0000);panel.add(0xd0).writePointer(game);panel.add(0xa8).writeS32(4);
        for (const o of [0x42,0x43,0xfb]) panel.add(o).writeU8(1);
        game.add(0x40).writePointer(config);game.add(0x48).writeS32(123);game.add(0x89).writeU8(1);
        game.add(0xc0).writePointer(0x123456);game.add(0x64).writeFloat(45);game.add(0xf8).writePointer(collection);
        for (const [o,v] of [[0x20,3],[0x24,1],[0x30,2],[0x40,60]]) config.add(o).writeS32(v);
        collection.add(0x38).writePointer(items);items.add(0x10).writePointer(array);items.add(0x18).writeS32(3);array.add(24).writePointer(3);
        const cells=[],cellClass=klass(ns,'MedCellViewModel');
        for(let i=0;i<3;i++) {
            const address=ptr(0x4010000+i*0x1000),cell={address:address.toString(),col:i,row:0,role:i===0?1:i===2?2:0,
                kind:0,shape:0,variant:i===1?1:0,hidden:i===1,is_generated_path:true,solution_shape:0,solution_variant:0,rotate_count:0};
            address.writePointer(cellClass);address.add(0x28).writePointer(game);array.add(32+8*i).writePointer(address);
            for(const [field,o] of [['col',0x30],['row',0x34],['role',0x90],['kind',0x38],['shape',0x3c],['variant',0x40],
                ['solution_shape',0x78],['solution_variant',0x7c],['rotate_count',0x6c]]) address.add(o).writeS32(cell[field]);
            address.add(0x48).writeU8(cell.hidden?1:0);address.add(0x74).writeU8(1);cells.push(cell);
        }
        const registry_links=[];
        const linkTargets=[ptr(0x4020000),ptr(0x4021000),ptr(0x4022000),ptr(0x4023000),manager,ptr(0x4024000),dictionary,entries];
        let linkAddress=base.add(0x8157868);
        for (let i=0;i<linkTargets.length;i++) {
            linkAddress.writePointer(linkTargets[i]);addAnchor(linkAddress,8);
            registry_links.push({address:linkAddress.toString(),expected:linkTargets[i].toString()});
            linkAddress=linkTargets[i].add(0x80);
        }
        dictionary.add(0x20).writeS32(1);entries.add(24).writePointer(1);entries.add(32).writeS32(1);entries.add(48).writePointer(panel);
        for(const [address,size] of [[panel,8],[game,8],[config,8],[panel.add(0xd0),8],[game.add(0x40),8],
            [game.add(0x48),4],[panel.add(0xa8),4],[dictionary.add(0x20),4],[entries.add(32),24]])addAnchor(address,size);
        method.writePointer(base.add(request.method_rva));method.add(0x20).writePointer(gameClass);
        const name=ptr(0x4030000),type=ptr(0x4031000);name.writeByteArray(Buffer.from('RevealSolutionPathForEditor\0'));
        method.add(0x18).writePointer(name);method.add(0x28).writePointer(type);type.add(10).writeU8(2);
        request.meridian={panel:panel.toString(),vm:game.toString(),config:config.toString(),manager:manager.toString(),
            seed:123,handle:4,cols:3,rows:1,start_col:0,start_row:0,end_col:2,end_row:0,cells,round_key:'round-123',
            registry_links,registry:{dictionary:dictionary.toString(),entries:entries.toString(),count:1,count_address:dictionary.add(0x20).toString()}};
        meridian={panel,game,config,manager,collection,items,array,entries,dictionary,method,base,ptr,cell:i=>ptr(cells[i].address)};
    }
    if (operation==='character_growth_set') {
        request.method_token=0x06014b6c;request.method_rva=0xe679f0;request.parameter_count=2;
        base.add(0xe679f0).writeByteArray(Buffer.from('48895c2408574883ec30803d981c6e0700','hex'));
        const combat=ptr(0x5000000),dictionary=ptr(0x5001000),entries=ptr(0x5002000),player=ptr(0x5003000);
        const k=klass('Game.Model.Player.Components','CombatModel');combat.writePointer(k);
        combat.add(0x10).writePointer(player);combat.add(0x28).writePointer(dictionary);
        dictionary.writePointer(klass('System.Collections.Generic','Dictionary`2'));
        dictionary.add(0x18).writePointer(entries);dictionary.add(0x20).writeS32(1);entries.add(24).writePointer(3);
        entries.add(32).writeS32(1);entries.add(40).writeS32(2);entries.add(44).writeFloat(1.5);
        for(const [address,size] of [[combat,8],[combat.add(0x10),8],[combat.add(0x28),8],
            [dictionary.add(0x18),8],[dictionary.add(0x20),4],[entries.add(32),16]])addAnchor(address,size);
        method.writePointer(base.add(request.method_rva));method.add(0x20).writePointer(k);
        const name=ptr(0x5004000),type=ptr(0x5005000);name.writeByteArray(Buffer.from('SetGrowthAttr\0'));
        method.add(0x18).writePointer(name);method.add(0x28).writePointer(type);type.add(10).writeU8(1);
        request.character={combat:combat.toString(),combat_class:k.toString(),player:player.toString(),dictionary:dictionary.toString(),
            attr_id:3,value:12.5,identity_key:'character-1'};
        character={combat,dictionary,entries,method,base};
    }
    if(operation==='character_interact_set') {
        const player=ptr(0x6000000),dictionary=ptr(0x6001000),entries=ptr(0x6002000);
        const k=klass('Game.Model','PlayerModel'),wrapper=klass('LubanDatas','TbInteractAttributeId');
        player.writePointer(k);player.add(0x1a8).writePointer(dictionary);
        dictionary.writePointer(klass('System.Collections.Generic','Dictionary`2'));
        dictionary.add(0x18).writePointer(entries);dictionary.add(0x20).writeS32(1);entries.add(24).writePointer(4);
        entries.add(32).writeS32(1001);entries.add(36).writeS32(-1);entries.add(40).writeS32(1001);entries.add(44).writeS32(10);
        for(const [address,size] of [[player,8],[player.add(0x1a8),8],[dictionary,8],[dictionary.add(0x18),8],
            [dictionary.add(0x20),4],[dictionary.add(0x28),4],[dictionary.add(0x2c),4],[entries.add(24),8],[entries.add(32),16]]) addAnchor(address,size);
        const spec={name:'SetInteractAttributeValue',token:0x06013e63,rva:0xdc5ee0,kind:1,params:[0x11,8],prefix:'48895c2418554883ec20803d832f780700'};
        request.method_token=spec.token;request.method_rva=spec.rva;request.parameter_count=2;
        const params=reviewedMethod(method,k,spec,wrapper);
        request.character={player:player.toString(),player_class:k.toString(),dictionary:dictionary.toString(),
            attr_id:1002,value:50,maximum:5700,identity_key:'interact-1'};
        interact={player,dictionary,entries,method,base,params,wrapper,k};
    }
    if(['current_stamina_set','current_health_set','current_mana_set'].includes(operation)) {
        const resourceKey=operation.slice(0,-4), isHealth=resourceKey==='current_health', isMana=resourceKey==='current_mana';
        const currentAttr=isHealth?1:isMana?25:200, maxAttr=isHealth?4:isMana?22:201;
        const combat=ptr(0x7000000),dictionary=ptr(0x7001000),entries=ptr(0x7002000),player=ptr(0x7003000);
        const k=klass('Game.Model.Player.Components','CombatModel');combat.writePointer(k);
        player.writePointer(klass('Game.Model','PlayerModel'));combat.add(0x10).writePointer(player);combat.add(0x20).writePointer(dictionary);
        dictionary.writePointer(klass('System.Collections.Generic','Dictionary`2'));
        dictionary.add(0x18).writePointer(entries);dictionary.add(0x20).writeS32(2);entries.add(24).writePointer(4);
        for(const [i,key,value] of [[0,currentAttr,50],[1,maxAttr,100]]) {
            const entry=entries.add(32+i*16);entry.writeS32(key);entry.add(4).writeS32(-1);entry.add(8).writeS32(key);entry.add(12).writeFloat(value);
            addAnchor(entry,12);addAnchor(entry.add(12),4);
        }
        for(const [address,size] of [[combat,8],[player,8],[combat.add(0x10),8],[combat.add(0x20),8],[dictionary,8],
            [dictionary.add(0x18),8],[dictionary.add(0x20),4],[dictionary.add(0x28),4],[dictionary.add(0x2c),4],[entries.add(24),8]])addAnchor(address,size);
        let specs={
            current:{name:'GetCurrentStamina',token:0x06014b07,rva:0xe5fea0,kind:12,params:[],prefix:'40534883ec20803d98976e0700488bd97513'},
            max:{name:'GetMaxStamina',token:0x06014b08,rva:0xe60a90,kind:12,params:[],prefix:'4883ec284533c0bac9000000e88febffff'},
            modify:{name:'ModifyStamina',token:0x06014b00,rva:0xe653a0,kind:2,params:[12],prefix:'4883ec380f28d948c744242000000000bac800000041b8c9000000e820fbffff'}
        };
        if(isHealth)specs={
            current:{name:'GetCurrentHealth',token:0x06014b09,rva:0xe5fdc0,kind:12,params:[],prefix:'40534883ec20803d79986e0700488bd97513'},
            max:{name:'GetMaxHealth',token:0x06014b0a,rva:0xe609f0,kind:12,params:[],prefix:'4883ec284533c0ba04000000e82fecffff'},
            modify:{name:'ModifyHealth',token:0x06014b01,rva:0xe65070,kind:2,params:[12],prefix:'4883ec380f28d948c744242000000000ba0100000041b804000000e850feffff'}
        };
        if(isMana)specs={
            current:{name:'GetCurrentMana',token:0x06014b0b,rva:0xe5fe30,kind:12,params:[],prefix:'40534883ec20803d0a986e0700488bd97513'},
            max:{name:'GetMaxMana',token:0x06014b0c,rva:0xe60a60,kind:12,params:[],prefix:'4883ec284533c0ba16000000e8bfebffff'},
            modify:{name:'ModifyMana',token:0x06014b02,rva:0xe650a0,kind:2,params:[12],prefix:'4883ec380f28d948c744242000000000ba1900000041b816000000e820feffff'}
        };
        const methods={current:ptr(0x7004000),max:ptr(0x7005000),modify:method},params={};
        for(const key of Object.keys(methods))params[key]=reviewedMethod(methods[key],k,specs[key]);
        request.method_token=specs.modify.token;request.method_rva=specs.modify.rva;request.parameter_count=1;
        request.resource={combat:combat.toString(),combat_class:k.toString(),player:player.toString(),dictionary:dictionary.toString(),
            address:entries.add(44).toString(),before:50,value:60,identity_key:'stamina-1',resource_key:resourceKey,
            methods:Object.fromEntries(Object.entries(methods).map(([key,p])=>[key,p.toString()]))};
        stamina={combat,dictionary,entries,player,base,method,methods,params,k,current:entries.add(44),maximum:100,resourceKey,specs,
            singleClass:klass('System','Single'),boolClass:klass('System','Boolean')};
    }
    const context = {
        Process:{arch:'x64',platform:'windows',pointerSize:8,id:12,getCurrentThreadId:()=>99,
            getModuleByName:()=>({base,getExportByName:name=>name})},
        ptr, int64:value=>({kind:'Int64',value:BigInt(value)}),
        Memory:{alloc:n=>{ const value=ptr(next); next+=BigInt(n+32); return value; }},
        NativeFunction:function(name) {
            if(name==='il2cpp_method_get_param_count') return mi=>methodSpecs.has(mi.toString())?mi.add(0x52).readU8():request.parameter_count;
            if(name==='il2cpp_method_get_token') return mi=>methodSpecs.has(mi.toString())?mi.add(0x48).readS32():request.method_token;
            if(name==='il2cpp_method_get_param') return (mi,index)=>parameterTypes.get(mi.toString())[index];
            if(name==='il2cpp_class_from_type') return type=>typeClasses.get(type.toString())||ptr(0);
            return (mi, bag, args, exception)=>{
                if(options.currency && mi.equals(options.currency.stackMethod)) {
                    const c=options.currency;getterCalls++;nativeNames.push('ResolveItemStackMax');
                    assert.ok(bag.isNull());assert.ok(args.readPointer().equals(c.config));
                    assert.equal(args.add(8).readPointer().readS32(),request.item_id);
                    if(options.getterThrow)throw new Error('stack getter failed');
                    exception.writePointer(options.getterException?0x3000:0);
                    if(options.getterNull)return ptr(0);
                    const box=ptr(0x6090000);box.writePointer(options.getterWrongType?c.configClass:c.intClass);
                    box.add(16).writeS32(options.stackLimit===undefined?c.config.add(100).readS32():options.stackLimit);
                    if(options.changeAnchor)anchor.writeS32(2);
                    if(options.expireGetter)request.deadline=Date.now()-1;
                    return box;
                }
                if(['current_stamina_set','current_health_set','current_mana_set'].includes(operation)) {
                    const spec=methodSpecs.get(mi.toString());nativeNames.push(spec.name);
                    assert.equal(bag.toString(),request.resource.combat);
                    if(!spec.name.startsWith('Modify')) {
                        getterCalls++;assert.ok(args.isNull());
                        if(options.getterThrow===getterCalls)throw new Error('getter fault');
                        exception.writePointer(options.getterException===getterCalls?0x3000:0);
                        if(options.getterNull===getterCalls)return ptr(0);
                        const box=ptr(0x7090000+getterCalls*0x100);box.writePointer(options.getterWrongType===getterCalls?stamina.boolClass:stamina.singleClass);
                        const value=spec.name.startsWith('GetCurrent')?stamina.current.readFloat():stamina.maximum;
                        box.add(16).writeFloat(options.getterValues && getterCalls in options.getterValues?options.getterValues[getterCalls]:value);
                        if(options.changeAnchor===getterCalls)anchor.writeS32(2);
                        if(options.expireGetter===getterCalls)request.deadline=Date.now()-1;
                        return box;
                    }
                    calls++;
                    if(failNative)throw new Error('native exception fixture');
                    const delta=args.readPointer().readFloat();
                    assert.equal(delta,Math.fround(request.resource.value-request.resource.before));
                    if(!noWin)stamina.current.writeFloat(unchangedReturn?999:Math.fround(stamina.current.readFloat()+delta));
                    const increment=options.versionIncrement===undefined?1:options.versionIncrement;
                    stamina.dictionary.add(0x2c).writeS32((stamina.dictionary.add(0x2c).readS32()+increment)|0);
                    if(options.changeOwner)stamina.combat.add(0x10).writePointer(0);
                    exception.writePointer(managedException?0x3000:0);
                    if(options.setterNull)return ptr(0);
                    const box=ptr(0x7080000);box.writePointer(stamina.boolClass);box.add(16).writeU8(options.setterFalse?0:1);return box;
                }
                calls++;
                if (failNative) throw new Error('native exception fixture');
                if(operation==='character_interact_set') {
                    const c=request.character;
                    assert.equal(bag.toString(),c.player);assert.equal(args.readPointer().readS32(),c.attr_id);
                    assert.equal(args.add(8).readPointer().readS32(),c.value);
                    if(!noWin) {
                        const d=interact.dictionary,entries=interact.entries;interact.player.add(0x1a8).writePointer(d);d.add(0x18).writePointer(entries);
                        let index=d.add(0x20).readS32();
                        if(d.add(0x28).readS32()>0){index=0;d.add(0x28).writeS32(d.add(0x28).readS32()-1);}
                        else d.add(0x20).writeS32(index+1);
                        const e=entries.add(32+index*16);e.writeS32(c.attr_id);e.add(4).writeS32(-1);e.add(8).writeS32(c.attr_id);e.add(12).writeS32(unchangedReturn?999:c.value);
                    }
                    if(options.changePlayerClass)interact.player.writePointer(0);
                    exception.writePointer(managedException?0x3000:0);return ptr(0);
                } else if(operation==='character_growth_set') {
                    const c=request.character;
                    assert.equal(bag.toString(),c.combat);assert.equal(args.readPointer().readS32(),c.attr_id);
                    assert.equal(args.add(8).readPointer().readFloat(),Math.fround(c.value));
                    if(!noWin) {
                        const count=character.dictionary.add(0x20).readS32();character.dictionary.add(0x18).writePointer(character.entries);
                        character.dictionary.add(0x20).writeS32(count+1);const e=character.entries.add(32+count*16);
                        e.writeS32(c.attr_id);e.add(8).writeS32(c.attr_id);e.add(12).writeFloat(unchangedReturn?999:Math.fround(c.value));
                    }
                    exception.writePointer(managedException?0x3000:0);return ptr(0);
                } else if(operation==='meridian_solve') {
                    assert.equal(bag.toString(),request.meridian.vm);assert.ok(args.isNull());
                    if(!noWin) {meridian.game.add(0x72).writeU8(1);meridian.game.add(0x73).writeU8(1);}
                    const box=ptr(0x4990000);box.add(16).writeU8(unchangedReturn?0:1);
                    exception.writePointer(managedException ? 0x3000 : 0);return box;
                } else if(operation==='add') {
                    assert.equal(Buffer.from(args.readPointer().readByteArray(4)).readInt32LE(),request.item_id);
                    assert.equal(Buffer.from(args.add(8).readPointer().readByteArray(4)).readInt32LE(),request.quantity);
                    assert.ok(Buffer.from(args.add(24).readPointer().readByteArray(28)).equals(Buffer.alloc(28)));
                    assert.ok(args.add(32).readPointer().isNull());
                    if(options.currency) {
                        const c=options.currency;nativeNames.push('AddItem');
                        if(!noWin) {
                            c.bagList.add(24).writeS32(1);c.bagArray.add(32).writePointer(c.currencyItem);
                            c.currencyItem.add(20).writeS32(request.currency_proof.before+request.quantity+(options.postDelta||0));
                        }
                        if(options.changeOwner)c.bag.add(16).writePointer(0);
                        if(options.postItemType)c.currencyItem.writePointer(c.configClass);
                        exception.writePointer(managedException?0x3000:0);
                        return options.wrongResult?ptr(0):c.config;
                    }
                } else {
                    assert.equal(Buffer.from(args.readPointer().readByteArray(8)).readBigInt64LE(),9007199254740993n);
                }
                exception.writePointer(managedException ? 0x3000 : 0); return ptr(0);
            };
        },
        Interceptor:{attach:(_address, callbacks)=>{callback=callbacks.onEnter;return {detach:()=>{detached=true;}};}},
        rpc:{exports:{}},send:value=>emitted.push(value),
        setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{}, Uint8Array, Date, Number, Array
    };
    if(current){
        const evidence=require('./native_method_evidence.json').methods;
        base.add(0x14342d0).writeByteArray(new Uint8Array(13));
        base.add(0x1464640).writeByteArray(Buffer.from('48895c2408574883ec60488bd9','hex'));
        for(const v of Object.values(evidence))base.add(v.rva).writeByteArray(Buffer.from(v.prefix,'hex'));
        const legacy=request.method_token,v=evidence[legacy];assert.ok(v);
        request.method_token=v.token;request.method_rva=v.rva;
        const all=new Map(methodSpecs);all.set(method.toString(),{token:legacy});
        for(const [address,old] of all){const v=evidence[old.token];if(!v)continue;const m=ptr(address);m.writePointer(base.add(v.rva));m.add(0x48).writeS32(v.token);
            m.add(0x18).readPointer().writeByteArray(Buffer.from(v.name+'\0'));if(methodSpecs.has(address))methodSpecs.set(address,{...old,...v});}
    }
    vm.createContext(context); vm.runInContext(source,context);
    return {api:context.rpc.exports,request,anchor,emitted,meridian,character,interact,stamina,options,nativeNames,ptr,addAnchor,
        base,item,method,klass,reviewedMethod,typeClasses,
        syncAnchors:()=>{for(const a of request.anchors)a.expected_hex=Buffer.from(ptr(a.address).readByteArray(a.size)).toString('hex');},
        noWin:()=>{noWin=true;},unchangedReturn:()=>{unchangedReturn=true;},run:()=>callback(),expire:()=>timer(),
        failNative:()=>{failNative=true;},
        managedException:()=>{managedException=true;},
        get calls(){return calls;},get getterCalls(){return getterCalls;},get detached(){return detached;}};
}

{
    const f=fixture(); f.api.submit(f.request); f.run(); f.run();
    assert.equal(f.calls,1); assert.equal(f.emitted[0].status,'completed'); assert.ok(f.detached);
    assert.throws(()=>f.api.submit(f.request),/exactly one/);
}
{
    const f=fixture('remove_test_uid'); f.api.submit(f.request); f.run();
    assert.equal(f.calls,1); assert.equal(f.emitted[0].status,'completed');
}
{
    const f=fixture(); f.api.submit(f.request); f.api.cancel(); f.run();
    assert.equal(f.calls,0); assert.equal(f.emitted[0].status,'cancelled');
}
{
    const f=fixture(); f.api.submit(f.request); f.expire(); f.run();
    assert.equal(f.calls,0); assert.equal(f.emitted[0].status,'cancelled');
}
{
    const f=fixture(); f.api.submit(f.request); f.anchor.writeS32(2); f.run();
    assert.equal(f.calls,0); assert.equal(f.emitted[0].status,'rejected');
}
{
    const f=fixture('add',{quantity:1000}); f.api.submit(f.request); f.run();
    assert.equal(f.calls,0); assert.equal(f.emitted[0].status,'rejected');
}
{
    const f=fixture(); f.api.submit(f.request); f.run();
    assert.equal(f.api.reset('one').status,'idle');
    f.api.submit({...f.request,token:'two'}); f.run();
    assert.equal(f.calls,2); assert.equal(f.emitted[1].token,'two');
}
{
    const f=fixture(); f.api.submit(f.request); f.run();
    assert.throws(()=>f.api.reset('other'),/token differs/);
    f.api.reset('one');
    assert.throws(()=>f.api.submit(f.request),/already used/);
    assert.equal(f.calls,1);
}
{
    const f=fixture(); f.api.submit(f.request);
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    f.api.cancel(); f.api.reset('one');
    f.api.submit({...f.request,token:'two'}); f.run();
    assert.equal(f.calls,1);
}
{
    const f=fixture(); f.failNative(); f.api.submit(f.request); f.run();
    assert.equal(f.emitted[0].status,'unknown');
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    assert.equal(f.calls,1);
}
{
    const f=fixture(); f.api.submit(f.request); f.anchor.writeS32(2); f.run();
    f.api.reset('one'); f.anchor.writeS32(1);
    f.api.submit({...f.request,token:'two'}); f.run();
    assert.equal(f.calls,1); assert.equal(f.emitted[1].status,'completed');
}
{
    const f=fixture(); f.managedException(); f.api.submit(f.request); f.run();
    assert.equal(f.emitted[0].status,'exception');
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    assert.equal(f.calls,1);
}
let meridianTests=0;
function meridianTest(name, test) { try {test();meridianTests++;}catch(e){e.message=name+': '+e.message;throw e;} }
meridianTest('normal native Win',()=>{
    const f=fixture('meridian_solve');f.api.submit(f.request);f.run();f.run();
    assert.equal(f.calls,1);assert.equal(f.emitted[0].status,'completed');assert.equal(f.emitted[0].changed,true);
    assert.equal(f.emitted[0].native_finished,true);assert.equal(f.emitted[0].native_won,true);
    assert.equal(f.emitted[0].failure_reason,0);assert.equal(f.emitted[0].round_key,'round-123');
});
for(const [group,offsets] of [['panel',[0xf8,0xf9,0xfa,0xfc]],['game',[0x71,0x72,0x73,0x75,0x77]]]) {
    for(const offset of offsets) meridianTest(group+' busy '+offset,()=>{
        const f=fixture('meridian_solve');f.api.submit(f.request);f.meridian[group].add(offset).writeU8(1);f.run();
        assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'rejected');
    });
}
for(const offset of [0xd0,0xd8,0xe0,0xe8]) meridianTest('animation '+offset,()=>{
    const f=fixture('meridian_solve');f.api.submit(f.request);f.meridian.game.add(offset).writePointer(0x6000000);f.run();
    assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'rejected');
});
for(const [name,mutate] of [
    ['missing completion',f=>f.meridian.game.add(0xc0).writePointer(0)],
    ['time expired',f=>f.meridian.game.add(0x64).writeFloat(0)],
    ['nan time',f=>f.meridian.game.add(0x64).writeFloat(NaN)],
    ['not loaded',f=>f.meridian.panel.add(0xfb).writeU8(0)],
    ['missing layout',f=>f.meridian.game.add(0x89).writeU8(0)],
    ['failed',f=>f.meridian.game.add(0x108).writeS32(2)],
    ['manager shutdown',f=>f.meridian.manager.add(0x18).writeU8(1)],
    ['owner changed',f=>f.meridian.cell(1).add(0x28).writePointer(0x6000000)],
    ['cell pointer changed',f=>f.meridian.array.add(40).writePointer(0x6000000)],
    ['missing cell',f=>f.meridian.items.add(0x18).writeS32(2)],
    ['cell value changed',f=>f.meridian.cell(1).add(0x40).writeS32(0)],
    ['stale registry',f=>f.meridian.entries.add(48).writePointer(0)],
    ['missing registry proof',f=>{f.request.meridian.registry_links=[];}],
    ['missing anchor coverage',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.meridian.base.add(0x8157868).toString());}],
    ['wrong method token',f=>{f.request.method_token++;}],
    ['wrong method RVA',f=>{f.request.method_rva++;}],
    ['wrong method class',f=>f.meridian.method.add(0x20).writePointer(0x6000000)],
    ['static method',f=>f.meridian.method.add(0x4c).writeU8(0x10)],
    ['patched native body',f=>f.meridian.base.add(0x1dac830).writeU8(0x90)]
]) meridianTest(name,()=>{
    const f=fixture('meridian_solve');mutate(f);f.api.submit(f.request);f.run();
    assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'rejected');
});
meridianTest('no changed path',()=>{
    const f=fixture('meridian_solve');const c=f.request.meridian.cells[1];c.hidden=false;c.variant=0;
    f.meridian.cell(1).add(0x48).writeU8(0);f.meridian.cell(1).add(0x40).writeS32(0);
    f.api.submit(f.request);f.run();assert.equal(f.calls,0);assert.match(f.emitted[0].reason,/原始路线已经对齐/);
});
meridianTest('invalid generated route',()=>{
    const f=fixture('meridian_solve');f.request.meridian.cells[1].solution_variant=1;
    f.meridian.cell(1).add(0x7c).writeS32(1);f.api.submit(f.request);f.run();
    assert.equal(f.calls,0);assert.match(f.emitted[0].reason,/does not connect/);
});
for(const failure of ['noWin','unchangedReturn','failNative','managedException']) meridianTest(failure+' cannot retry',()=>{
    const f=fixture('meridian_solve');f[failure]();f.api.submit(f.request);f.run();f.run();
    assert.equal(f.calls,1);assert.equal(f.emitted[0].status,failure==='managedException'?'exception':'unknown');
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
meridianTest('meridian uses retained script terminal reset',()=>{
    const f=fixture('meridian_solve');f.api.submit(f.request);f.run();f.api.reset('one');
    assert.throws(()=>f.api.submit(f.request),/already used/);assert.equal(f.calls,1);
});
for(const operation of ['meridian_solve','character_growth_set']) {
    meridianTest(operation+' expired before callback is definitely uncalled',()=>{
        const f=fixture(operation);f.request.deadline=Date.now()-1;f.api.submit(f.request);f.run();
        assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'cancelled');assert.equal(f.emitted[0].called,false);
    });
    meridianTest(operation+' timer expiration is definitely uncalled',()=>{
        const f=fixture(operation);f.api.submit(f.request);f.expire();f.run();
        assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'cancelled');assert.equal(f.emitted[0].called,false);
    });
}
meridianTest('new persistent growth key once',()=>{
    const f=fixture('character_growth_set');f.api.submit(f.request);f.run();f.run();
    assert.equal(f.calls,1,JSON.stringify(f.emitted));assert.equal(f.emitted[0].status,'completed');assert.equal(f.emitted[0].created,true);
    assert.equal(f.emitted[0].attr_id,3);assert.equal(f.emitted[0].value,12.5);
});
for(const [name,mutate] of [
    ['percent attribute refused',f=>{f.request.character.attr_id=100;}],
    ['already existing key refused',f=>{f.request.character.attr_id=2;}],
    ['negative growth refused',f=>{f.request.character.value=-1;}],
    ['delta beyond 1000 refused',f=>{f.request.character.value=1001;}],
    ['nonfinite growth refused',f=>{f.request.character.value=NaN;}],
    ['wrong owner',f=>f.character.combat.add(0x10).writePointer(0x9999900)],
    ['wrong dictionary',f=>f.character.combat.add(0x28).writePointer(0x9999900)],
    ['wrong class',f=>{f.request.character.combat_class='0x9999900';}],
    ['missing dictionary anchor',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.character.dictionary.add(0x18).toString());}],
    ['patched growth method',f=>f.character.base.add(0xe679f0).writeU8(0x90)],
    ['wrong growth token',f=>{f.request.method_token++;}],
    ['wrong growth method type',f=>f.character.method.add(0x28).readPointer().add(10).writeU8(2)],
    ['wrong growth method name',f=>f.character.method.add(0x18).readPointer().writeByteArray(Buffer.from('BadMethod\0'))]
])meridianTest(name,()=>{
    const f=fixture('character_growth_set');mutate(f);f.api.submit(f.request);f.run();
    assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'rejected');assert.equal(f.emitted[0].called,false);
});
for(const failure of ['noWin','unchangedReturn','failNative','managedException'])meridianTest('growth '+failure+' stops retries',()=>{
    const f=fixture('character_growth_set');f[failure]();f.api.submit(f.request);f.run();f.run();assert.equal(f.calls,1);
    assert.equal(f.emitted[0].status,failure==='managedException'?'exception':'unknown');
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
for(const value of [0,1000,0.1])meridianTest('growth accepted bound '+value,()=>{
    const f=fixture('character_growth_set');f.request.character.value=value;f.api.submit(f.request);f.run();
    assert.equal(f.calls,1);assert.equal(f.emitted[0].status,'completed');assert.equal(f.emitted[0].value,Math.fround(value));
});
meridianTest('initially empty Growth dictionary',()=>{
    const f=fixture('character_growth_set');f.character.dictionary.add(0x18).writePointer(0);f.character.dictionary.add(0x20).writeS32(0);
    for(const a of f.request.anchors)if(a.address===f.character.dictionary.add(0x18).toString()||a.address===f.character.dictionary.add(0x20).toString()){
        a.expected_hex=Buffer.from(new Uint8Array(f.character.dictionary.add(a.size===8?0x18:0x20).readByteArray(a.size))).toString('hex');
    }
    f.api.submit(f.request);f.run();assert.equal(f.calls,1);assert.equal(f.emitted[0].status,'completed');
});
meridianTest('Python structural12 plus Single4 anchor contract',()=>{
    const f=fixture('character_growth_set'),entry=f.character.entries.add(32);
    f.request.anchors=f.request.anchors.filter(a=>a.address!==entry.toString());
    for(const [offset,size] of [[0,12],[12,4]])f.request.anchors.push({address:entry.add(offset).toString(),size,
        expected_hex:Buffer.from(entry.add(offset).readByteArray(size)).toString('hex'),label:'Python split dictionary entry'});
    f.api.submit(f.request);f.run();assert.equal(f.calls,1);assert.equal(f.emitted[0].status,'completed');
});
for(const [offset,size] of [[0,12],[12,4]])meridianTest('partial entry proof rejected '+offset,()=>{
    const f=fixture('character_growth_set'),entry=f.character.entries.add(32);
    f.request.anchors=f.request.anchors.filter(a=>a.address!==entry.toString());
    f.request.anchors.push({address:entry.add(offset).toString(),size,
        expected_hex:Buffer.from(entry.add(offset).readByteArray(size)).toString('hex'),label:'incomplete Python entry'});
    f.api.submit(f.request);f.run();assert.equal(f.calls,0);assert.equal(f.emitted[0].status,'rejected');
});
let resourceTests=0;
function resourceTest(name,test){try{test();resourceTests++;}catch(e){e.message=name+': '+e.message;throw e;}}
function runRequest(f){f.api.submit(f.request);f.run();return f.emitted[0];}
function refused(f){const out=runRequest(f);assert.equal(f.calls,0,JSON.stringify(out));assert.equal(out.status,'rejected',JSON.stringify(out));assert.equal(out.called,false);}
for(const operation of ['character_interact_set','current_stamina_set']) {
    resourceTest(operation+' succeeds once',()=>{
        const f=fixture(operation),out=runRequest(f);f.run();
        assert.equal(f.calls,1,JSON.stringify(out));assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.called,true);
        assert.equal(out.value,operation==='character_interact_set'?50:60);
        assert.equal(out.identity_key,operation==='character_interact_set'?'interact-1':'stamina-1');
        if(operation==='character_interact_set')assert.equal(out.created,true);
        else {assert.equal(out.maximum,100);assert.equal(out.result,true);assert.equal(out.before,50);
            assert.deepEqual(f.nativeNames,['GetCurrentStamina','GetMaxStamina','ModifyStamina','GetCurrentStamina','GetMaxStamina']);}
        f.api.reset('one');assert.throws(()=>f.api.submit(f.request),/already used/);
    });
    for(const mode of ['deadline','timer','cancel'])resourceTest(operation+' uncalled '+mode,()=>{
        const f=fixture(operation);if(mode==='deadline')f.request.deadline=Date.now()-1;
        f.api.submit(f.request);if(mode==='timer')f.expire();if(mode==='cancel')f.api.cancel();f.run();
        assert.equal(f.calls,0);assert.equal(f.getterCalls,0);assert.equal(f.emitted[0].called,false);assert.equal(f.emitted[0].status,'cancelled');
    });
    for(const failure of ['noWin','unchangedReturn','failNative','managedException'])resourceTest(operation+' '+failure+' no retry',()=>{
        const f=fixture(operation);f[failure]();const out=runRequest(f);f.run();
        assert.equal(f.calls,1,JSON.stringify(out));assert.equal(out.called,true);
        assert.equal(out.status,failure==='managedException'?'exception':'unknown',JSON.stringify(out));
        assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    });
}
for(const [name,mutate] of [
    ['unlisted id',f=>{f.request.character.attr_id=1006;}],
    ['existing id',f=>{f.request.character.attr_id=1001;}],
    ['negative value',f=>{f.request.character.value=-1;}],
    ['fractional value',f=>{f.request.character.value=1.5;}],
    ['change over1000',f=>{f.request.character.value=1001;}],
    ['above realm maximum',f=>{f.request.character.maximum=49;}],
    ['invalid realm maximum',f=>{f.request.character.maximum=5701;}],
    ['zero realm maximum',f=>{f.request.character.maximum=0;}],
    ['nonfinite',f=>{f.request.character.value=NaN;}],
    ['wrong playerclass',f=>{f.request.character.player_class='0x1';}],
    ['player dictionary changed',f=>{f.interact.player.add(0x1a8).writePointer(0);} ],
    ['wrong method token',f=>{f.interact.method.add(0x48).writeS32(1);} ],
    ['wrong method argc',f=>{f.interact.method.add(0x52).writeU8(1);} ],
    ['wrong method class',f=>{f.interact.method.add(0x20).writePointer(1);} ],
    ['wrong method return',f=>{f.interact.method.add(0x28).readPointer().add(10).writeU8(2);} ],
    ['static method',f=>{f.interact.method.add(0x4c).writeU8(0x10);} ],
    ['wrong first argument',f=>{f.interact.params[0].add(10).writeU8(8);} ],
    ['wrong second argument',f=>{f.interact.params[1].add(10).writeU8(12);} ],
    ['byref argument',f=>{f.interact.params[1].add(11).writeU8(0x20);} ],
    ['pinned argument',f=>{f.interact.params[1].add(11).writeU8(0x40);} ],
    ['wrong wrapper',f=>{f.interact.wrapper.add(16).readPointer().writeByteArray(Buffer.from('OtherId\0'));} ],
    ['patched method',f=>{f.interact.base.add(0xdc5ee0).writeU8(0x90);} ],
    ['missing full entry anchor',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.interact.entries.add(32).toString());} ],
    ['bad free count',f=>{f.interact.dictionary.add(0x28).writeS32(2);f.syncAnchors();} ],
    ['bad capacity',f=>{f.interact.entries.add(24).writePointer(129);f.syncAnchors();} ],
    ['bad next',f=>{f.interact.entries.add(36).writeS32(1);f.syncAnchors();} ],
    ['unknown existing id',f=>{f.interact.entries.add(40).writeS32(9000);f.syncAnchors();} ],
    ['negative existing value',f=>{f.interact.entries.add(44).writeS32(-1);f.syncAnchors();} ]
])resourceTest('interact rejects '+name,()=>{const f=fixture('character_interact_set');mutate(f);refused(f);});
for(const value of [0,1000])resourceTest('interact exact bound '+value,()=>{
    const f=fixture('character_interact_set');f.request.character.value=value;const out=runRequest(f);
    assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.value,value);
});
resourceTest('interact initializes null dictionary',()=>{
    const f=fixture('character_interact_set');f.request.character.dictionary='0x0';f.interact.player.add(0x1a8).writePointer(0);
    f.interact.dictionary.add(0x20).writeS32(0);
    f.request.anchors=f.request.anchors.filter(a=>![f.interact.dictionary,f.interact.entries].some(p=>f.ptr(a.address).compare(p)>=0&&f.ptr(a.address).compare(p.add(0x1000))<0));
    f.syncAnchors();const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(f.calls,1);
});
resourceTest('interact creates into free slot',()=>{
    const f=fixture('character_interact_set');f.interact.entries.add(32).writeS32(-1);f.interact.dictionary.add(0x28).writeS32(1);f.syncAnchors();
    const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(f.interact.dictionary.add(0x20).readS32(),1);
});
resourceTest('interact postcall identity loss locks retry',()=>{
    const f=fixture('character_interact_set');f.options.changePlayerClass=true;const out=runRequest(f);
    assert.equal(out.status,'unknown');assert.equal(out.called,true);assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
for(const [name,mutate] of [
    ['negative',f=>{f.request.resource.value=-1;}],
    ['above tool maximum',f=>{f.request.resource.value=1000001;}],
    ['not exact Single',f=>{f.request.resource.value=0.1;}],
    ['nonfinite',f=>{f.request.resource.value=Infinity;}],
    ['noop',f=>{f.request.resource.value=50;}],
    ['over1000delta',f=>{f.request.resource.value=1051;}],
    ['wrong displayed current',f=>{f.request.resource.before=49;}],
    ['wrong current address',f=>{f.request.resource.address=f.stamina.entries.add(60).toString();}],
    ['missing Base200',f=>{f.stamina.entries.add(40).writeS32(202);f.syncAnchors();}],
    ['duplicate Base200',f=>{f.stamina.entries.add(56).writeS32(200);f.syncAnchors();}],
    ['owner changed',f=>{f.stamina.combat.add(0x10).writePointer(0);}],
    ['dictionary changed',f=>{f.stamina.combat.add(0x20).writePointer(0);}],
    ['wrong class',f=>{f.request.resource.combat_class='0x1';}],
    ['missing current anchor',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.stamina.current.toString());}],
    ['missing other value anchor',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.stamina.entries.add(60).toString());}],
    ['missing getter',f=>{delete f.request.resource.methods.max;}],
    ['unreviewed getter token',f=>{f.stamina.methods.current.add(0x48).writeS32(1);}],
    ['getter static',f=>{f.stamina.methods.max.add(0x4c).writeU8(0x10);}],
    ['getter wrong return type',f=>{f.stamina.methods.current.add(0x28).readPointer().add(10).writeU8(8);}],
    ['setter wrong argument',f=>{f.stamina.params.modify[0].add(10).writeU8(8);}],
    ['setter byref argument',f=>{f.stamina.params.modify[0].add(11).writeU8(0x20);}],
    ['setter pinned argument',f=>{f.stamina.params.modify[0].add(11).writeU8(0x40);}],
    ['setter wrong return',f=>{f.stamina.methods.modify.add(0x28).readPointer().add(10).writeU8(1);}],
    ['patched getter',f=>{f.stamina.base.add(0xe60a90).writeU8(0x90);}],
    ['stale context after getter',f=>{f.options.changeAnchor=2;}],
    ['maximum zero',f=>{f.stamina.maximum=0;}],
    ['maximum negative',f=>{f.stamina.maximum=-1;}],
    ['maximum nonfinite',f=>{f.stamina.maximum=NaN;}],
    ['maximum too large',f=>{f.stamina.maximum=1000001;}],
    ['request exceeds game maximum',f=>{f.stamina.maximum=59;}],
    ['getter disagrees with Base',f=>{f.options.getterValues={1:49};}],
    ['Single delta loses target',f=>{f.stamina.current.writeFloat(1000);f.request.resource.before=1000;f.request.resource.value=Math.fround(0.0000001);f.stamina.maximum=1000;f.syncAnchors();}]
])resourceTest('stamina rejects '+name,()=>{const f=fixture('current_stamina_set');mutate(f);refused(f);});
for(const failure of ['getterThrow','getterException','getterNull','getterWrongType'])for(const at of [1,2])resourceTest('stamina '+failure+' before setter '+at,()=>{
    const f=fixture('current_stamina_set');f.options[failure]=at;refused(f);assert.equal(f.getterCalls,at);
});
for(const failure of ['getterThrow','getterException','getterNull','getterWrongType'])for(const at of [3,4])resourceTest('stamina '+failure+' after setter '+at,()=>{
    const f=fixture('current_stamina_set');f.options[failure]=at;const out=runRequest(f);
    assert.equal(f.calls,1);assert.equal(out.status,'unknown');assert.equal(out.called,true);assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
for(const option of ['setterFalse','setterNull','changeOwner'])resourceTest('stamina '+option+' prevents success/retry',()=>{
    const f=fixture('current_stamina_set');f.options[option]=true;const out=runRequest(f);
    assert.equal(out.status,'unknown');assert.equal(out.called,true);assert.equal(f.calls,1);assert.throws(()=>f.api.reset('one'),/not safely terminal/);
});
for(const values of [{3:59},{4:59},{4:1000001}])resourceTest('stamina postread mismatch '+JSON.stringify(values),()=>{
    const f=fixture('current_stamina_set');f.options.getterValues=values;const out=runRequest(f);assert.equal(out.status,'unknown');assert.equal(out.called,true);
});
resourceTest('stamina expires during getters without setter',()=>{
    const f=fixture('current_stamina_set');f.options.expireGetter=2;const out=runRequest(f);
    assert.equal(f.calls,0);assert.equal(f.getterCalls,2);assert.equal(out.status,'cancelled');assert.equal(out.called,false);
});
for(const value of [0,100,Math.fround(50.25)])resourceTest('stamina valid bounded target '+value,()=>{
    const f=fixture('current_stamina_set');f.request.resource.value=value;const out=runRequest(f);
    assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.value,value);
});
resourceTest('stamina accepts exact1000 delta',()=>{
    const f=fixture('current_stamina_set');f.request.resource.value=1050;f.stamina.maximum=1050;
    const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.value,1050);
});
for(const operation of ['current_health_set','current_mana_set']) {
    resourceTest(operation+' reviewed getter setter readback',()=>{
        const f=fixture(operation),out=runRequest(f);f.run();
        assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(f.calls,1);assert.equal(f.getterCalls,4);
        assert.equal(out.resource_key,operation.slice(0,-4));assert.equal(out.value,60);assert.equal(out.maximum,100);
        assert.deepEqual(f.nativeNames,[f.stamina.specs.current.name,f.stamina.specs.max.name,f.stamina.specs.modify.name,
            f.stamina.specs.current.name,f.stamina.specs.max.name]);
    });
    for(const [name,mutate] of [
        ['different resource key',f=>{f.request.resource.resource_key='current_stamina';}],
        ['wrong selected Base attr',f=>{f.stamina.entries.add(40).writeS32(200);f.syncAnchors();}],
        ['wrong actual maximum',f=>{f.stamina.maximum=59;}],
        ['getter type mismatch',f=>{f.stamina.methods.current.add(0x28).readPointer().add(10).writeU8(8);}],
        ['getter token mismatch',f=>{f.stamina.methods.max.add(0x48).writeS32(0x06014b08);}],
        ['setter token mismatch',f=>{f.request.method_token=0x06014b00;}],
        ['setter argument mismatch',f=>{f.stamina.params.modify[0].add(10).writeU8(8);}],
        ['patched setter',f=>{f.stamina.base.add(f.stamina.specs.modify.rva).writeU8(0x90);}],
        ['stale game context',f=>{f.options.changeAnchor=1;}],
        ['missing current anchor',f=>{f.request.anchors=f.request.anchors.filter(a=>a.address!==f.stamina.current.toString());}],
        ['invalid negative value',f=>{f.request.resource.value=-1;}],
        ['over 1000 change',f=>{f.request.resource.value=1051;}],
        ['no-op',f=>{f.request.resource.value=50;}]
    ])resourceTest(operation+' rejects '+name,()=>{const f=fixture(operation);mutate(f);refused(f);});
    for(const failure of ['noWin','unchangedReturn','failNative','managedException'])resourceTest(operation+' '+failure+' locks retries',()=>{
        const f=fixture(operation);f[failure]();const out=runRequest(f);
        assert.equal(out.status,failure==='managedException'?'exception':'unknown');assert.equal(out.called,true);
        assert.equal(f.calls,1);assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    });
}
resourceTest('health minimum one accepted',()=>{
    const f=fixture('current_health_set');f.request.resource.value=1;const out=runRequest(f);
    assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.value,1);
});
resourceTest('health zero target refused without calling getter or setter',()=>{
    const f=fixture('current_health_set');f.request.resource.value=0;refused(f);assert.equal(f.getterCalls,0);
});
resourceTest('health cannot resurrect a zero current value',()=>{
    const f=fixture('current_health_set');f.request.resource.before=0;f.stamina.current.writeFloat(0);f.syncAnchors();
    refused(f);assert.equal(f.getterCalls,0);
});
resourceTest('mana zero target accepted',()=>{
    const f=fixture('current_mana_set');f.request.resource.value=0;assert.equal(runRequest(f).status,'completed');
});
for(const operation of ['current_stamina_set','current_health_set','current_mana_set']) {
    for(const increment of [0,2])resourceTest(operation+' version increment '+increment+' refuses success',()=>{
        const f=fixture(operation);f.options.versionIncrement=increment;const out=runRequest(f);
        assert.equal(out.status,'unknown');assert.equal(out.called,true);assert.throws(()=>f.api.reset('one'),/not safely terminal/);
    });
    resourceTest(operation+' native Int32 version wrap accepted',()=>{
        const f=fixture(operation);f.stamina.dictionary.add(0x2c).writeS32(2147483647);f.syncAnchors();
        const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));
        assert.equal(f.stamina.dictionary.add(0x2c).readS32(),-2147483648);
    });
}
for(const attr of [7,111,112,113,114,115,116]) {
    resourceTest('new growth attribute '+attr+' exact step accepted',()=>{
        const f=fixture('character_growth_set');f.request.character.attr_id=attr;f.request.character.value=attr===7?1:Math.fround(0.1);
        const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.attr_id,attr);
    });
    resourceTest('new growth attribute '+attr+' excessive first step refused',()=>{
        const f=fixture('character_growth_set');f.request.character.attr_id=attr;f.request.character.value=attr===7?1.01:0.11;
        refused(f);
    });
}
resourceTest('resource JSON and bridge mock reviewed method contract agree',()=>{
    const specs=JSON.parse(fs.readFileSync(path.join(__dirname,'current_resources_specs.json'),'utf8'));
    for(const [key,spec] of Object.entries(specs)){
        const f=fixture(spec.operation);
        for(const kind of ['current','max','modify']){
            const bridge=f.stamina.specs[kind],python=spec.methods[kind];
            for(const field of ['name','token','rva','prefix'])assert.equal(bridge[field],python[field]);
            assert.equal(bridge.kind,python.return_kind);assert.equal(bridge.params.length,python.parameters);
        }
        assert.equal(f.request.resource.resource_key,key);
        assert.equal(f.stamina.entries.add(40).readS32(),spec.attr_id);
    }
});
function currencyFixture(id=50000, quantity=1000000, before=123) {
    const f=fixture('add',{item_id:id,quantity}), p=f.ptr;let next=0x6100000;
    function allocate(n=256){const a=p(next);next+=n+32;return a;}
    function fields(k, rows) {
        const data=allocate(rows.length*32);k.add(0x80).writePointer(data);
        k.add(0x124).writeByteArray([rows.length&255,rows.length>>8]);
        rows.forEach(([name,token,kind,offset,staticField=false],i)=>{
            const a=data.add(i*32),n=allocate(),t=allocate();n.writeByteArray(Buffer.from(name+'\0'));
            t.add(8).writeByteArray([staticField?0x10:0,0]);t.add(10).writeU8(kind);
            a.writePointer(n);a.add(8).writePointer(t);a.add(16).writePointer(k);a.add(24).writeS32(offset);a.add(28).writeS32(token);
        });return data;
    }
    const c={bag:f.item,config:p(0x6000000),tables:p(0x6001000),static:p(0x6002000),table:p(0x6003000),
        configList:p(0x6004000),configArray:p(0x6005000),bagList:p(0x6006000),bagArray:p(0x6007000),
        currencyItem:p(0x6008000),stackMethod:p(0x6009000),fields};
    c.tablesClass=f.klass('LubanDatas','Tables');c.configClass=f.klass('LubanDatas.data','Item');
    c.bagClass=f.klass('Game.Model.Components','BagModel');c.baseClass=f.klass('Game.Model.Components','BagItemBase');
    c.itemClass=f.klass('Game.Model.Components','BagItem');c.itemClass.add(0x58).writePointer(c.baseClass);
    c.tableClass=f.klass('LubanDatas','TbItem');c.configListClass=f.klass('Emei','NotifiableList`1');
    c.listClass=f.klass('System.Collections.Generic','List`1');c.configListClass.add(0x58).writePointer(c.listClass);
    c.configArrayClass=f.klass('LubanDatas.data','Item[]');c.bagArrayClass=f.klass('Game.Model.Components','BagItemBase[]');
    c.bagArrayClass.add(0x40).writePointer(c.baseClass);c.intClass=f.klass('System','Int32');
    fields(c.tablesClass,[['Current',0x04000800,0x12,0,true],['<TbItem>k__BackingField',0x04000848,0x12,0x248]]);
    fields(c.tableClass,[['_dataList',0x04000ade,0x15,24],['_overrides',0x04000adf,0x15,32]]);
    c.itemFields=fields(c.configClass,[['<id>k__BackingField',0x0400158d,0x11,16],['<itemType>k__BackingField',0x04001594,0x11,72],
        ['<maxCntPerGrid>k__BackingField',0x0400159d,8,100],['<autoUse>k__BackingField',0x0400159a,0x15,84]]);
    fields(c.bagClass,[['<Items>k__BackingField',0x0400b03b,0x15,24]]);
    fields(c.baseClass,[['ItemId',0x0400affa,0x11,16],['Count',0x0400affb,8,20],['IsEquipped',0x0400affd,2,25]]);
    c.bag.writePointer(c.bagClass);c.bag.add(24).writePointer(c.bagList);
    c.bagList.writePointer(c.listClass);c.bagList.add(16).writePointer(c.bagArray);c.bagList.add(24).writeS32(before===null?0:1);
    c.bagArray.writePointer(c.bagArrayClass);c.bagArray.add(24).writePointer(4);c.bagArray.add(32).writePointer(c.currencyItem);
    c.currencyItem.writePointer(c.itemClass);c.currencyItem.add(16).writeS32(id);c.currencyItem.add(20).writeS32(before||0);
    c.tablesClass.add(0xb8).writePointer(c.static);c.static.writePointer(c.tables);c.tables.writePointer(c.tablesClass);
    c.tables.add(0x248).writePointer(c.table);c.table.writePointer(c.tableClass);c.table.add(24).writePointer(c.configList);
    c.configList.writePointer(c.configListClass);c.configList.add(16).writePointer(c.configArray);c.configList.add(24).writeS32(1);
    c.configArray.writePointer(c.configArrayClass);c.configArray.add(24).writePointer(4);c.configArray.add(32).writePointer(c.config);
    c.config.writePointer(c.configClass);c.config.add(16).writeS32(id);c.config.add(72).writeS32(5);c.config.add(100).writeS32(999999999);
    const addSpec={name:'AddItem',token:0x06015191,rva:0xe9bdd0,kind:0x12,params:[0x11,8,0x11,0x15,0x12],prefix:'44894c24204489442418895424104889'};
    c.addParams=f.reviewedMethod(f.method,c.bagClass,addSpec);
    const stackSpec={name:'ResolveItemStackMax',token:0x0601519f,rva:0xea0fd0,kind:8,params:[0x12,0x11],prefix:'48895c24105556574883ec50803d3989'};
    c.stackParams=f.reviewedMethod(c.stackMethod,c.bagClass,stackSpec);c.stackMethod.add(0x4c).writeByteArray([0x10,0]);
    f.typeClasses.set(c.stackParams[0].toString(),c.configClass);f.typeClasses.set(c.stackParams[1].toString(),f.klass('LubanDatas','TbItemId'));
    f.request.currency_proof={tables:c.tables.toString(),tables_class:c.tablesClass.toString(),config_object:c.config.toString(),
        row_index:0,before:before||0,maximum:999999999,stack_method:c.stackMethod.toString()};
    for(const[a,n]of [[c.bag,32],[c.bagList,32],[c.bagArray,64],[c.bagArrayClass.add(0x40),8],
        [c.currencyItem,28],[c.itemClass.add(0x58),8],[c.tablesClass.add(0xb8),8],[c.static,8],
        [c.tables,8],[c.tables.add(0x248),8],[c.table,40],[c.configList,32],[c.configListClass.add(0x58),8],
        [c.configArray,40],[c.config,20],[c.config.add(72),4],[c.config.add(84),2],[c.config.add(100),4]]) f.addAnchor(a,n);
    f.options.currency=c;f.currency=c;return f;
}
let currencyTests=0;
function currencyTest(name,fn){try{fn();currencyTests++;}catch(e){e.message=name+': '+e.message;throw e;}}
for(const id of [50000,50001,50002])for(const before of [123,null])currencyTest('million '+id+' existing '+before,()=>{
    const f=currencyFixture(id,1000000,before),out=runRequest(f);
    assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.currency_verified,true);
    assert.equal(f.calls,1);assert.equal(f.getterCalls,1);assert.equal(out.after,(before||0)+1000000);
    assert.deepEqual(f.nativeNames,['ResolveItemStackMax','AddItem']);f.run();assert.equal(f.calls,1);
});
for(const before of [123,null])currencyTest('stone hundred million existing '+before,()=>{
    const f=currencyFixture(50000,100000000,before),out=runRequest(f);
    assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(out.currency_verified,true);
    assert.equal(out.after,(before||0)+100000000);assert.equal(f.calls,1);assert.equal(f.getterCalls,1);
    assert.deepEqual(f.nativeNames,['ResolveItemStackMax','AddItem']);f.run();assert.equal(f.calls,1);
});
for(const id of [50001,50002])currencyTest('other currency remains million '+id,()=>{
    refused(currencyFixture(id,1000001));
    refused(currencyFixture(id,100000000));
});
for(const [name,change] of [
    ['currency without proof',f=>delete f.request.currency_proof],
    ['unreviewed id',f=>{f.request.item_id=50003;}],
    ['ordinary spoofed proof',f=>{f.request.item_id=91002;f.request.quantity=1;}],
    ['zero',f=>{f.request.quantity=0;}],['over hundred million',f=>{f.request.quantity=100000001;}],
    ['fraction',f=>{f.request.quantity=1.5;}],['nan',f=>{f.request.quantity=NaN;}],
    ['wrong actual id',f=>f.currency.config.add(16).writeS32(50002)],
    ['wrong actual type',f=>f.currency.config.add(72).writeS32(9)],
    ['auto use',f=>f.currency.config.add(84).writeByteArray([1,1])],
    ['bad nullable',f=>f.currency.config.add(84).writeByteArray([2,0])],
    ['invalid config cap',f=>f.currency.config.add(100).writeS32(0)],
    ['request cap inflated',f=>{f.request.currency_proof.maximum=1000000000;}],
    ['config cap differs',f=>f.currency.config.add(100).writeS32(500000)],
    ['changed balance',f=>f.currency.currencyItem.add(20).writeS32(456)],
    ['negative balance',f=>f.currency.currencyItem.add(20).writeS32(-1)],
    ['equipped currency',f=>f.currency.currencyItem.add(25).writeU8(1)],
    ['wrong row',f=>{f.request.currency_proof.row_index=1;}],
    ['row pointer changed',f=>f.currency.configArray.add(32).writePointer(0)],
    ['tables root changed',f=>f.currency.static.writePointer(0)],
    ['config token changed',f=>f.currency.itemFields.add(28).writeS32(0x400158e)],
    ['config field byref',f=>f.currency.itemFields.add(8).readPointer().add(11).writeU8(0x20)],
    ['config field offset',f=>f.currency.itemFields.add(24).writeS32(20)],
    ['AddItem static',f=>f.method.add(0x4c).writeByteArray([0x10,0])],
    ['AddItem wrong param',f=>f.currency.addParams[1].add(10).writeU8(12)],
    ['AddItem onCommitted must be nongeneric Action',f=>f.currency.addParams[4].add(10).writeU8(0x15)],
    ['stack instance method',f=>f.currency.stackMethod.add(0x4c).writeByteArray([0,0])],
    ['stack wrong return',f=>f.currency.stackMethod.add(0x28).readPointer().add(10).writeU8(12)],
    ['stack byref parameter',f=>f.currency.stackParams[0].add(11).writeU8(0x20)],
    ['stack wrong code',f=>f.base.add(0xea0fd0).writeU8(0)],
    ['stack native single limit',f=>{f.options.stackLimit=1;}],
    ['stack exception',f=>{f.options.getterException=true;}],
    ['stack JS exception',f=>{f.options.getterThrow=true;}],
    ['stack null',f=>{f.options.getterNull=true;}],
    ['stack wrong boxed type',f=>{f.options.getterWrongType=true;}],
    ['invalid inventory size',f=>f.currency.bagList.add(24).writeS32(4001)],
    ['invalid inventory capacity',f=>f.currency.bagArray.add(24).writePointer(9000)],
    ['invalid configuration capacity',f=>f.currency.configArray.add(24).writePointer(20001)],
    ['anchor changes during getter',f=>{f.options.changeAnchor=true;}]
])currencyTest(name,()=>{const f=currencyFixture();change(f);f.syncAnchors();refused(f);});
currencyTest('missing selected config anchor',()=>{
    const f=currencyFixture();f.request.anchors=f.request.anchors.filter(a=>a.address!==f.currency.config.add(72).toString());refused(f);
});
currencyTest('missing balance anchor',()=>{
    const f=currencyFixture();f.request.anchors=f.request.anchors.filter(a=>a.address!==f.currency.currencyItem.toString());refused(f);
});
currencyTest('exact total boundary accepted',()=>{
    const f=currencyFixture(50000,100000000,899999999);assert.equal(runRequest(f).after,999999999);assert.equal(f.calls,1);
});
currencyTest('hundred million crossing total cap rejected',()=>refused(currencyFixture(50000,100000000,900000000)));
currencyTest('at cap plus one rejected',()=>refused(currencyFixture(50000,1,999999999)));
currencyTest('total above cap rejected',()=>refused(currencyFixture(50000,1000000,999000000)));
currencyTest('real lowered cap enforced',()=>{
    const f=currencyFixture(50000,999,100);f.currency.config.add(100).writeS32(1000);f.request.currency_proof.maximum=1000;f.syncAnchors();refused(f);
});
currencyTest('empty historical overrides accepted',()=>{
    const f=currencyFixture(),d=f.ptr(0x6070000);d.writePointer(f.klass('System.Collections.Generic','Dictionary`2'));
    d.add(32).writeS32(2);d.add(40).writeS32(2);f.currency.table.add(32).writePointer(d);f.addAnchor(d,48);f.syncAnchors();
    assert.equal(runRequest(f).status,'completed');
});
currencyTest('active overrides rejected',()=>{
    const f=currencyFixture(),d=f.ptr(0x6070000);d.writePointer(f.klass('System.Collections.Generic','Dictionary`2'));
    d.add(32).writeS32(1);f.currency.table.add(32).writePointer(d);f.addAnchor(d,48);f.syncAnchors();refused(f);
});
currencyTest('duplicate currency slots rejected without quantity loop',()=>{
    const f=currencyFixture();f.currency.bagList.add(24).writeS32(2);f.currency.bagArray.add(40).writePointer(f.currency.currencyItem);f.syncAnchors();refused(f);
});
for(const option of ['wrongResult','changeOwner','postItemType','postDelta'])currencyTest('post mutation '+option+' locks unknown',()=>{
    const f=currencyFixture();f.options[option]=option==='postDelta'?1:true;const out=runRequest(f);
    assert.equal(out.status,'unknown',JSON.stringify(out));assert.equal(out.called,true);assert.equal(f.calls,1);
    assert.throws(()=>f.api.reset('one'),/not safely terminal/);f.run();assert.equal(f.calls,1);
});
currencyTest('post mutation exception retains called true',()=>{
    const f=currencyFixture();f.managedException();const out=runRequest(f);assert.equal(out.status,'exception');assert.equal(out.called,true);assert.equal(f.calls,1);
});
currencyTest('timeout after readonly getter still definitely not called',()=>{
    const f=currencyFixture();f.options.expireGetter=true;const out=runRequest(f);
    assert.equal(out.status,'cancelled');assert.equal(out.called,false);assert.equal(f.calls,0);assert.equal(f.getterCalls,1);
});
currencyTest('pending cancellation invokes neither getter nor setter',()=>{
    const f=currencyFixture();f.api.submit(f.request);f.api.cancel();f.run();
    assert.equal(f.calls,0);assert.equal(f.getterCalls,0);assert.equal(f.emitted[0].called,false);
});
currencyTest('real Python proof uses separate pointer identity and scalar anchors',()=>{
    const f=currencyFixture(),c=f.currency;f.request.anchors=f.request.anchors.slice(0,1);
    for(const[a,n]of [[c.bag,8],[c.bag.add(16),8],[c.bag.add(24),8],[c.bagList,8],[c.bagList.add(16),8],
        [c.bagList.add(24),4],[c.bagList.add(28),4],[c.bagArray,8],[c.bagArray.add(24),8],[c.bagArray.add(32),8],
        [c.bagArrayClass.add(0x40),8],[c.currencyItem,8],[c.currencyItem.add(16),4],[c.currencyItem.add(20),4],
        [c.currencyItem.add(25),1],[c.itemClass.add(0x58),8],[c.tablesClass.add(0xb8),8],[c.static,8],
        [c.tables,8],[c.tables.add(0x248),8],[c.table,8],[c.table.add(24),8],[c.table.add(32),8],
        [c.configList,8],[c.configList.add(16),8],[c.configList.add(24),4],[c.configList.add(28),4],
        [c.configListClass.add(0x58),8],[c.configArray,8],[c.configArray.add(24),8],[c.configArray.add(32),8],
        [c.config,8],[c.config.add(16),4],[c.config.add(72),4],[c.config.add(84),2],[c.config.add(100),4]])f.addAnchor(a,n);
    const out=runRequest(f);assert.equal(out.status,'completed',JSON.stringify(out));assert.equal(f.calls,1);
});
currencyTest('Tables metadata supports more than 256 fields without unbounded scanning',()=>{
    const f=currencyFixture(),c=f.currency;
    const rows=Array.from({length:300},(_,i)=>['irrelevant'+i,0x4000100+i,8,16]);
    rows[298]=['Current',0x04000800,0x12,0,true];rows[299]=['<TbItem>k__BackingField',0x04000848,0x12,0x248];
    c.fields(c.tablesClass,rows);assert.equal(runRequest(f).status,'completed');
});
currencyTest('ordinary item still accepts exact 999',()=>{const f=fixture('add',{quantity:999});assert.equal(runRequest(f).status,'completed');assert.equal(f.calls,1);});
for (const [label,mutate] of [
    ['ordinary item method code changed',f=>f.method.readPointer().writeU8(0)],
    ['ordinary item return type changed',f=>f.method.add(0x28).readPointer().add(10).writeU8(8)],
    ['ordinary item method owner changed',f=>f.method.add(0x20).writePointer(0)],
    ['ordinary item method became static',f=>f.method.add(0x4c).writeU8(0x10)]
]) currencyTest(label,()=>{const f=fixture('add');mutate(f);const out=runRequest(f);
    assert.equal(out.status,'rejected',label);assert.equal(f.calls,0,label);assert.equal(out.called,false,label);});
console.log(`12 inventory + ${meridianTests} meridian/growth + ${resourceTests} interact/resource + ${currencyTests} currency bridge tests passed (offline; no game attached)`);

for(const op of ['add','meridian_solve','character_growth_set','character_interact_set','current_stamina_set','current_health_set','current_mana_set']){const f=fixture(op,{},true);f.api.submit(f.request);f.run();assert.equal(f.emitted[0].status,'completed',op+': '+JSON.stringify(f.emitted[0]));assert.equal(f.calls,1);}
console.log('Current native primary bridge operations: 7 passed');
