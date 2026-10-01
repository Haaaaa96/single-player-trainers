/* Merged into the main-thread bridge. No RPC accepts arbitrary coordinates. */
const RECIPE_METHODS = {
    teleport:nativeSpec({name:'TeleportTo',token:0x060157a7,rva:0xf40a60,argc:1,returns:1,params:[0x11],prefix:'488bc45356574881eca00000000f2970'}),
    collect:nativeSpec({name:'CheckPoiConsumption',token:0x060157c8,rva:0xf3cff0,argc:0,returns:1,params:[],prefix:'40534881ecd0000000803dd1cc600700'}),
    available:nativeSpec({name:'IsRecipePoiEnabled',token:0x0600f171,rva:0x1cc5f70,argc:1,returns:2,params:[8],prefix:'4883ec584c8b81c00100004d85c0745d'})
};
function recipeInvoke(method,target,values) {
    const args=values.length?Memory.alloc(values.length*8):ptr(0),exception=Memory.alloc(8);
    values.forEach((v,i)=>args.add(i*8).writePointer(v));exception.writePointer(ptr(0));
    const result=invoke(method,target,args,exception);
    requireValue(exception.readPointer().isNull(),'Recipe native method threw; inspect game before retrying');
    return result;
}
function recipeRoundAfterMove(m, requireEmpty) {
    const panel=dualJadePanel(m,'Game.UI.UPFLogic.RefiningPills','UPFRefiningPillsExplorePanel');
    const move=ptr(m.move),s=ptr(m.state),d=ptr(m.dataset),vm=ptr(m.vm);
    for(const [a,v] of [[panel.add(0x1c0),d],[panel.add(0x220),move],[panel.add(0x228),s],[panel.add(0x138),vm],
        [move.add(32),d],[move.add(40),s]])samePointer(a.readPointer(),v,'Recipe owner changed during native callback');
    requireValue(move.add(120).readFloat()===m.candidate.x && move.add(124).readFloat()===m.candidate.y,
        'Recipe native movement did not reach its target');
    if(requireEmpty) {
        for(const offset of [0x1d4,0x345,0x346,0x347,0x34c,0x369,0x439])requireValue(!boolAt(panel.add(offset)),'Recipe callback made panel busy');
        for(const offset of [0x1c8,0x210,0x3b8,0x3e0])requireValue(panel.add(offset).readPointer().isNull(),'Recipe callback began transition');
        for(const offset of [0xc1,0xc8,0x130])requireValue(!boolAt(move.add(offset)),'Recipe callback made movement busy');
        requireValue(move.add(0xc0).readU8()===0 && s.add(20).readS32()===0 && !boolAt(s.add(93)) &&
            !boolAt(vm.add(0x90)) && !boolAt(vm.add(0x171)),'Recipe callback changed first-recipe state');
        [move.add(0x208),move.add(0x218),move.add(0x220),s.add(112)].forEach((a,i)=>
            samePointer(a.readPointer(),m.callbacks[i],'Recipe callback replaced collection handlers'));
        samePointer(d.add(40).readPointer().add(16).readPointer(),m.array,'Recipe callback replaced POI dataset');
    }
}
function executeAlchemyRecipe() {
    const m=request.minigame,ns='Game.Logic.RefiningPills.Map',u='Game.UI.UPFLogic.RefiningPills';
    const panel=dualJadePanel(m,u,'UPFRefiningPillsExplorePanel'),move=ptr(m.move),s=ptr(m.state),d=ptr(m.dataset),vm=ptr(m.vm);
    const mc=className(move,ns,'RefiningPillsMovementController'),pc=className(panel,u,'UPFRefiningPillsExplorePanel');
    className(s,ns,'RefiningPillsExploreState');className(d,ns,'RefiningPillsMapDataset');className(vm,u,'UPFRefiningPillsExplorePanelViewModel');
    samePointer(mc,m.move_class,'Recipe movement class changed');samePointer(pc,m.panel_class,'Recipe panel class changed');
    requireRequestMethod(RECIPE_METHODS.teleport);
    requireValue(m.methods && Object.keys(m.methods).sort().join(',')==='available,collect,teleport','Recipe method set incomplete');
    samePointer(request.method_info,m.methods.teleport,'Recipe method differs');
    for(const key of Object.keys(RECIPE_METHODS))validateReviewedMethod(ptr(m.methods[key]),key==='available'?pc:mc,RECIPE_METHODS[key]);
    const vt=classFromType(methodParam(ptr(m.methods.teleport),0));
    requireValue(vt.add(16).readPointer().readUtf8String()==='Vector2' && vt.add(24).readPointer().readUtf8String()==='UnityEngine' &&
        vt.add(0xf8).readS32()===24,'Recipe destination is not the reviewed Vector2');
    for(const [a,v] of [[panel.add(0x1c0),d],[panel.add(0x220),move],[panel.add(0x228),s],[panel.add(0x138),vm],
        [move.add(32),d],[move.add(40),s]]){requireCoverage(a,8);samePointer(a.readPointer(),v,'Recipe owner changed');}
    for(const offset of [0x1d4,0x345,0x346,0x347,0x34c,0x369,0x439]){
        requireCoverage(panel.add(offset),1);requireValue(!boolAt(panel.add(offset)),'Recipe panel busy');
    }
    for(const offset of [0x1c8,0x210,0x3b8,0x3e0]){
        requireCoverage(panel.add(offset),8);requireValue(panel.add(offset).readPointer().isNull(),'Recipe transition active');
    }
    for(const offset of [0xc1,0xc8,0x130]){
        requireCoverage(move.add(offset),1);requireValue(!boolAt(move.add(offset)),'Recipe movement busy');
    }
    requireCoverage(move.add(0xc0),1);requireValue(move.add(0xc0).readU8()===0,'Recipe trajectory not idle');
    for(const [p,n] of [[s.add(20),4],[s.add(93),1],[vm.add(0x90),1],[vm.add(0x171),1],[move.add(56),4],[move.add(120),8],[panel.add(0x278),4]])requireCoverage(p,n);
    requireValue(s.add(20).readS32()===0 && !boolAt(s.add(93)) && !boolAt(vm.add(0x90)) && !boolAt(vm.add(0x171)),'Recipe already obtained or explosion active');
    const cb=[move.add(0x208),move.add(0x218),move.add(0x220),s.add(112)];
    requireValue(Array.isArray(m.callbacks) && m.callbacks.length===4,'Recipe callbacks incomplete');
    cb.forEach((a,i)=>{requireCoverage(a,8);samePointer(a.readPointer(),m.callbacks[i],'Recipe callback changed');requireValue(!a.readPointer().isNull(),'Recipe callback unavailable');});
    const candidate=m.candidate;
    requireValue(candidate && Number.isInteger(candidate.index) && candidate.index>=0 && candidate.index<m.count &&
        Number.isInteger(m.count) && m.count>0 && m.count<=8192 && Number.isFinite(m.radius) && m.radius>0 && m.radius<=1000 &&
        Number.isInteger(m.furnace) && m.furnace>=1 && m.furnace<=5 && panel.add(0x278).readS32()===m.furnace &&
        floatBits(move.add(56).readFloat())===floatBits(m.radius),'Recipe bounds invalid');
    const list=d.add(40).readPointer();className(list,ns,'RefiningPillsPoiList');requireCoverage(d.add(40),8);requireCoverage(list.add(16),8);
    const array=list.add(16).readPointer();samePointer(array,m.array,'Recipe POIs changed');
    requireCoverage(array.add(24),8);requireValue(array.add(24).readU64().toNumber()===m.count,'Recipe POI count changed');
    const poi=array.add(32+candidate.index*36);requireCoverage(poi,36);
    const x=poi.add(16).readS32(),y=poi.add(20).readS32();
    requireValue(poi.readS32()===candidate.poi_id && poi.add(4).readU8()===2 && poi.add(6).readU8()===candidate.tier &&
        candidate.tier>=1 && candidate.tier<=m.furnace && x===candidate.x && y===candidate.y && x>=0 && y>=0 && x<=1000000 && y<=1000000,
        'Recipe target no longer matches current dataset');
    for(let i=0;i<m.count;i++){
        if(i===candidate.index)continue;
        const q=array.add(32+i*36);requireCoverage(q,36);
        const dx=q.add(16).readS32()-x,dy=q.add(20).readS32()-y;
        requireValue(dx*dx+dy*dy>m.radius*m.radius,'Recipe would collect another nearby POI');
    }
    const pool=d.add(56).readPointer(),ix=poi.add(12).readS32();requireCoverage(d.add(56),8);requireCoverage(pool.add(24),8);
    requireValue(ix>=0 && ix<pool.add(24).readU64().toNumber(),'Recipe string index invalid');
    requireCoverage(pool.add(32+ix*8),8);const str=pool.add(32+ix*8).readPointer();className(str,'System','String');
    const len=str.add(16).readS32();requireCoverage(str.add(16),4);requireValue(len>0 && len<=10,'Recipe ID string invalid');requireCoverage(str.add(20),len*2);
    requireValue(str.add(20).readUtf16String(len)===String(candidate.recipe_id),'Recipe ID changed');
    const index=Memory.alloc(4);index.writeS32(candidate.index);
    const enabled=recipeInvoke(ptr(m.methods.available),panel,[index]);
    requireValue(!enabled.isNull(),'Recipe availability result missing');className(enabled,'System','Boolean');
    requireValue(boolAt(enabled.add(16)),'Recipe disabled by game configuration');
    validateAnchors();
    requireValue(Date.now()<=request.deadline,'Recipe request expired');
    const destination=Memory.alloc(8);destination.writeFloat(x);destination.add(4).writeFloat(y);
    state='running';
    requireValue(recipeInvoke(ptr(m.methods.teleport),move,[destination]).isNull(),'Recipe teleport void return differs');
    recipeRoundAfterMove(m,true);
    requireValue(recipeInvoke(ptr(m.methods.collect),move,[]).isNull(),'Recipe collect void return differs');
    recipeRoundAfterMove(m,false);
    requireValue(boolAt(s.add(93)) && s.add(20).readS32()===candidate.recipe_id && boolAt(vm.add(0x90)),
        'Recipe collection did not confirm current recipe; do not repeat');
    finish('completed',{called:true,recipe_collected:true,recipe_id:candidate.recipe_id,round_key:m.round_key,thread_id:Process.getCurrentThreadId()});
}
