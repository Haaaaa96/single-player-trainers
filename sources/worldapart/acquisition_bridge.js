/* One-shot, evidence-checked IL2CPP invocation at A1Main.Update entry.
 * Whitelisted item, meridian and character operations; no arbitrary RPC or timer retry.
 * Python supplies a reviewed MethodInfo, current-save anchors, and a unique token.
 */
'use strict';
let request = null;
let listener = null;
let expiry = null;
let state = 'idle';
let terminal = null;
const usedTokens = new Set();
const OPERATIONS = ['add', 'remove_test_uid', 'meridian_solve', 'character_growth_set',
    'character_interact_set', 'current_stamina_set', 'current_health_set', 'current_mana_set',
    'lifespan_inspect', 'lifespan_add', 'game_speed_set',
    'alchemy_perfect', 'alchemy_talent_set', 'crafting_complete', 'dual_cultivation_complete', 'jade_reveal_all', 'alchemy_find_recipe',
    'photostone_activate', 'photostone_force_replay', 'persuasion_success'];
const LARGE_CURRENCY_IDS = new Set([50000, 50001, 50002]);
const image = Process.getModuleByName('GameAssembly.dll');
// Reviewed entries are independently checked again on the game thread.
let currentNativeProfile = false;
const REVIEWED_NATIVE_VARIANTS = {"100695898":{"name":"get_BaseScale","token":100695953,"rva":22326560,"prefix":"4883ec28803d5d3c0107007513488d0d","legacy_rva":22117920},"100695900":{"name":"get_EffectiveScale","token":100695955,"rva":22326640,"prefix":"4883ec28803d0f3c010700752b488d0d","legacy_rva":22118000},"100695902":{"name":"SetBaseScale","token":100695957,"rva":22325856,"prefix":"4883ec38803d213f0107000f29742420","legacy_rva":22117216},"100696637":{"name":"ForceSetSpecialState","token":100696694,"rva":22560640,"prefix":"48895c2410574883ec30803d99abfd06","legacy_rva":22351600},"100696649":{"name":"SetSpecialState","token":100696706,"rva":22578944,"prefix":"48895c24084889742410574883ec2041","legacy_rva":22369904},"100696664":{"name":"MeetsSpecialEntryRequirements","token":100696721,"rva":22566432,"prefix":"4053565741564881eca8000000450fb6","legacy_rva":22357392},"100701440":{"name":"CheckEffectActivation","token":100701468,"rva":23960832,"prefix":"405657415641574883ec58803dd558e8","legacy_rva":23759920},"100701454":{"name":"GetBonusRatio","token":100701482,"rva":23975504,"prefix":"40534883ec30803d961fe80600488bd9","legacy_rva":23774592},"100708041":{"name":"OnPersuadeEnded","token":100708101,"rva":26288064,"prefix":"4889742420574881ecc0000000803dbb","legacy_rva":26080912},"100725105":{"name":"IsRecipePoiEnabled","token":100725183,"rva":30396304,"prefix":"4883ec584c8b81c00100004d85c0745d","legacy_rva":30170992},"100726096":{"name":"FinishQte","token":100726177,"rva":30691232,"prefix":"4889742420574883ec30803d9edd8106","legacy_rva":30476464},"100729416":{"name":"RevealSolutionPathForEditor","token":100729431,"rva":10881008,"prefix":"40534883ec20803d368aaf0700488bd9","legacy_rva":10799856},"100730244":{"name":"RevealAll","token":100730323,"rva":11225024,"prefix":"40534883ec3033d2488bd9e8106fffff","legacy_rva":11035152},"100732162":{"name":"OnGameCompleted","token":100732275,"rva":11483568,"prefix":"40565741574883ec50803d005ea60700","legacy_rva":11318992},"100732300":{"name":"Complete","token":100732413,"rva":11472352,"prefix":"48895c2418554883ec30803d058aa607","legacy_rva":11307776},"100739785":{"name":"OnBtnComplete","token":100739906,"rva":13345040,"prefix":"48897c242041564883ec50803d95068a","legacy_rva":12962048},"100744803":{"name":"SetInteractAttributeValue","token":100744875,"rva":14635200,"prefix":"48895c2418554883ec20803d0f64760700","legacy_rva":14442208},"100744804":{"name":"get_CurrentAge","token":100744876,"rva":14639904,"prefix":"48895c2408574883ec20803db0517607","legacy_rva":14446944},"100744805":{"name":"get_MaxLifespan","token":100744877,"rva":14640480,"prefix":"4883ec384883794800750733c04883c4","legacy_rva":14447520},"100744814":{"name":"ModifyMaxLifespan","token":100744886,"rva":14627248,"prefix":"40534883ec20488bd9488b49484885c9","legacy_rva":14434224},"100746239":{"name":"OnPersuadeResult","token":100746313,"rva":15023296,"prefix":"40535556574883ec28803d467b700700","legacy_rva":14794480},"100748032":{"name":"ModifyStamina","token":100748131,"rva":15324784,"prefix":"4883ec380f28d948c744242000000000bac800000041b8c9000000e820fbffff","legacy_rva":15094688},"100748033":{"name":"ModifyHealth","token":100748132,"rva":15323968,"prefix":"4883ec380f28d948c744242000000000ba0100000041b804000000e850feffff","legacy_rva":15093872},"100748034":{"name":"ModifyMana","token":100748133,"rva":15324016,"prefix":"4883ec380f28d948c744242000000000ba1900000041b816000000e820feffff","legacy_rva":15093920},"100748039":{"name":"GetCurrentStamina","token":100748138,"rva":15303024,"prefix":"40534883ec20803d52396c0700488bd97513","legacy_rva":15072928},"100748040":{"name":"GetMaxStamina","token":100748139,"rva":15306080,"prefix":"4883ec284533c0bac9000000e88febffff","legacy_rva":15075984},"100748041":{"name":"GetCurrentHealth","token":100748140,"rva":15302800,"prefix":"40534883ec20803d333a6c0700488bd97513","legacy_rva":15072704},"100748042":{"name":"GetMaxHealth","token":100748141,"rva":15305920,"prefix":"4883ec284533c0ba04000000e82fecffff","legacy_rva":15075824},"100748043":{"name":"GetCurrentMana","token":100748142,"rva":15302912,"prefix":"40534883ec20803dc4396c0700488bd97513","legacy_rva":15072816},"100748044":{"name":"GetMaxMana","token":100748143,"rva":15306032,"prefix":"4883ec284533c0ba16000000e8bfebffff","legacy_rva":15075936},"100748140":{"name":"SetGrowthAttr","token":100748239,"rva":15334592,"prefix":"48895c2408574883ec30803d52be6b0700","legacy_rva":15104496},"100748919":{"name":"SetTalentRank","token":100749018,"rva":15463984,"prefix":"48896c2418564883ec20803d2fc66907","legacy_rva":15264720},"100749727":{"name":"ResolveItemStackMax","token":100749826,"rva":15571072,"prefix":"48895c24105556574883ec50803dcc24","legacy_rva":15339472},"100751271":{"name":"TeleportTo","token":100751370,"rva":16194080,"prefix":"488bc45356574881eca00000000f2970","legacy_rva":15993440},"100751304":{"name":"CheckPoiConsumption","token":100751403,"rva":16179120,"prefix":"40534881ecd0000000803d5ce15e0700","legacy_rva":15978480},"100710988":{"name":"<RunAsync>b__4","token":100711054,"rva":27248480,"prefix":"48895c24084889742410574883ec2080","legacy_rva":27037888},"100710989":{"name":"<RunAsync>b__5","token":100711055,"rva":27248624,"prefix":"48895c24084889742410574883ec2080","legacy_rva":27038032},"100710990":{"name":"<RunAsync>b__6","token":100711056,"rva":27247808,"prefix":"4883ec2880791000751a66c741100100","legacy_rva":27037216},"100710991":{"name":"<RunAsync>b__7","token":100711057,"rva":27248768,"prefix":"40534883ec20803dc044b60600488bd9","legacy_rva":27038176},"100729204":{"name":"RevealSolutionPathForEditor","token":100729219,"rva":10927456,"prefix":"48895c241848896c2420415441564157","legacy_rva":31115312},"100729242":{"name":"RefreshConnectivity","token":100729257,"rva":10923872,"prefix":"44884c24204488442418488954241055","legacy_rva":31111888},"100729272":{"name":"Win","token":100729287,"rva":10933440,"prefix":"48895c2408574883ec40803d35bdae07","legacy_rva":31121856},"100730582":{"name":"RevealAll","token":100730692,"rva":11316176,"prefix":"48895c2408574881ecc0000000803dd3","legacy_rva":11125056},"100730585":{"name":"SetRevealRatio","token":100730695,"rva":11318976,"prefix":"488bc44c8948204c8940184889480853","legacy_rva":11127856},"100730612":{"name":"WriteStoneState","token":100730722,"rva":11327104,"prefix":"488bc448895810488970204889480857","legacy_rva":11135984},"100732174":{"name":"ShowSettlement","token":100732287,"rva":11485440,"prefix":"4053574883ec7880b9f000000000488b","legacy_rva":11320864},"100732176":{"name":"ShowSuccessSettlement","token":100732289,"rva":11486176,"prefix":"40535556574883ec68803dd653a60700","legacy_rva":11321600},"100749713":{"name":"AddItem","token":100749812,"rva":15549920,"prefix":"44894c24204489442418895424104889","legacy_rva":15318480}};
const REVIEWED_FIELD_VARIANTS = {"LubanDatas.data.Item:67114381":{"name":"<id>k__BackingField","token":67114389},"LubanDatas.data.Item:67114388":{"name":"<itemType>k__BackingField","token":67114396},"LubanDatas.data.Item:67114394":{"name":"<autoUse>k__BackingField","token":67114402},"LubanDatas.data.Item:67114397":{"name":"<maxCntPerGrid>k__BackingField","token":67114405},"LubanDatas.data.NpcInteractGameEntry:67114957":{"name":"<npcId>k__BackingField","token":67114965},"LubanDatas.data.NpcInteractGameEntry:67114958":{"name":"<subId>k__BackingField","token":67114966},"LubanDatas.data.NpcInteractGameEntry:67114959":{"name":"<dependsSubId>k__BackingField","token":67114967},"LubanDatas.data.NpcInteractGameEntry:67114960":{"name":"<UnlockIntimacy>k__BackingField","token":67114968},"LubanDatas.data.NpcInteractGameEntry:67114963":{"name":"<maxSuccessCount>k__BackingField","token":67114971},"LubanDatas.data.NpcInteractGameEntry:67114964":{"name":"<interactGameType>k__BackingField","token":67114972},"LubanDatas.data.NpcInteractGameEntry:67114965":{"name":"<interactGameParam>k__BackingField","token":67114973},"LubanDatas.data.NpcInteractGameEntry:67114977":{"name":"<triggerPriority>k__BackingField","token":67114985},"LubanDatas.data.NpcPersuadeTopic:67115051":{"name":"<id>k__BackingField","token":67115059},"LubanDatas.data.NpcPersuadeTopic:67115053":{"name":"<maxRounds>k__BackingField","token":67115061},"LubanDatas.data.NpcPersuadeTopic:67115058":{"name":"<npcId>k__BackingField","token":67115066},"LubanDatas.data.NpcPersuadeTopic:67115059":{"name":"<autoExitDelayMs>k__BackingField","token":67115067},"LubanDatas.data.SignatureArtifact:67115723":{"name":"<lore>k__BackingField","token":67115731},"LubanDatas.data.Skill:67115733":{"name":"<ability_kind>k__BackingField","token":67115741},"LubanDatas.data.Skill:67115734":{"name":"<skill_availability>k__BackingField","token":67115742},"LubanDatas.data.Skill:67115735":{"name":"<levels>k__BackingField","token":67115743},"LubanDatas.data.Skill:67115736":{"name":"<element>k__BackingField","token":67115744},"LubanDatas.data.Skill:67115737":{"name":"<costs>k__BackingField","token":67115745},"LubanDatas.data.Skill:67115738":{"name":"<script>k__BackingField","token":67115746},"LubanDatas.data.Skill:67115739":{"name":"<xmlLink>k__BackingField","token":67115747},"LubanDatas.data.Space:67115789":{"name":"<behaviorTreeAsset>k__BackingField","token":67115797},"LubanDatas.data.Space:67115790":{"name":"<btAssetRandomAction>k__BackingField","token":67115798},"LubanDatas.data.Space:67115791":{"name":"<stage_id>k__BackingField","token":67115799},"LubanDatas.data.Space:67115792":{"name":"<enter_play_type>k__BackingField","token":67115800},".QuestSpecialStateOwner:67122930":{"name":"QuestId","token":67122943},"Game.NpcLogicManager:67122918":{"name":"_questSpecialStateOwners","token":67122931},"Game.NpcLogicManager:67122921":{"name":"_isExecutingNpcInteractAction","token":67122934},"Game.GameTime:67127608":{"name":"Year","token":67127585},"Game.GameTime:67127609":{"name":"Month","token":67127586},"Game.GameTime:67127610":{"name":"Day","token":67127587},"Game.GameTime:67127611":{"name":"Unit","token":67127588},"Game.DialogueInputPanel:67128360":{"name":"m_CanSubmit","token":67128344},"Game.DialogueInputPanel:67128361":{"name":"m_SubmitAvailable","token":67128345},"Game.NpcPersuadePanel:67130397":{"name":"DialogueInput","token":67130412},"Game.NpcPersuadePanel:67130405":{"name":"_subscribedNpc","token":67130420},"Game.NpcPersuadePanel:67130407":{"name":"_persuadeEnded","token":67130422},"Game.NpcPersuadePanel:67130408":{"name":"_persuadeResultNotified","token":67130423},"Game.NpcPersuadePanel:67130409":{"name":"_settlementDelayCts","token":67130424},"Game.NpcPersuadePanel:67130410":{"name":"_settlementIsWin","token":67130425},"Game.NpcPersuadePanel:67130411":{"name":"_userInitiatedClose","token":67130426},"Game.NpcPersuadePanel:67130412":{"name":"_isFlowAlive","token":67130427},"Game.NpcPersuadePanel:67130413":{"name":"_npcId","token":67130428},"Game.NpcPersuadePanel:67130414":{"name":"_topicId","token":67130429},"Game.NpcPersuadePanel:67130415":{"name":"_actionOnWin","token":67130430},"Game.NpcPersuadePanel:67130416":{"name":"_actionOnLose","token":67130431},"Game.NpcPersuadePanel:67130417":{"name":"_actionOnClose","token":67130432},"Game.NpcPersuadePanel:67130418":{"name":"_peekLoadingCo","token":67130433},"Game.NpcPersuadePanel:67130419":{"name":"_peekRequestToken","token":67130434},".<>c__DisplayClass5_0:67132410":{"name":"notified","token":67132430},".<>c__DisplayClass5_0:67132411":{"name":"win","token":67132431},".<>c__DisplayClass5_0:67132413":{"name":"<>4__this","token":67132433},".<>c__DisplayClass5_0:67132414":{"name":"ctx","token":67132434},"Game.MiniGamePersuadeCommand:67132407":{"name":"_npcId","token":67132427},"Game.MiniGamePersuadeCommand:67132408":{"name":"_topicId","token":67132428},"Game.MiniGamePersuadeCommand:67132409":{"name":"_subId","token":67132429},".PlacementSettlementData:67148441":{"name":"ClearedCells","token":67148611},".PlacementSettlementData:67148442":{"name":"AddedCells","token":67148612},".PlacementSettlementData:67148443":{"name":"ScoreBefore","token":67148613},".PlacementSettlementData:67148444":{"name":"ScoreAfter","token":67148614},".PlacementSettlementData:67148445":{"name":"ElementType","token":67148615},"Game.UI.UPFLogic.Alchemy.UPFAlchemyPanel:67148371":{"name":"_isPlayingFlyInAnimation","token":67148541},"Game.UI.UPFLogic.Alchemy.UPFAlchemyPanel:67148373":{"name":"_pendingSettlement","token":67148543},"Game.Model.GameWorldModel:67151846":{"name":"<PlayerModel>k__BackingField","token":67151959},"Game.Model.GameWorldModel:67151848":{"name":"<CurrentGameTime>k__BackingField","token":67151961},"Game.Model.GameWorldModel:67151850":{"name":"<NpcModels>k__BackingField","token":67151963},"Game.Model.GameWorldModel:67151852":{"name":"<StaticNpcIds>k__BackingField","token":67151965},"Game.Model.NpcInteractionRuntimeState:67152051":{"name":"<SpecialSubId>k__BackingField","token":67152164},"Game.Model.NpcInteractionRuntimeState:67152053":{"name":"<ActionUsageRecords>k__BackingField","token":67152166},"Game.Model.NpcInteractionActionUsageRecord:67152054":{"name":"<UsedCount>k__BackingField","token":67152167},"Game.Model.NpcInteractionActionUsageRecord:67152055":{"name":"<CycleKey>k__BackingField","token":67152168},"Game.Model.NpcModel:67152092":{"name":"<IsProcessingChatMessage>k__BackingField","token":67152205},"Game.Model.NpcModel:67152093":{"name":"<IsSummarizingChatHistory>k__BackingField","token":67152206},"Game.Model.NpcModel:67152098":{"name":"<LastPersuadeEndReason>k__BackingField","token":67152211},"Game.Model.NpcModel:67152099":{"name":"<CurrentPersuadeTopicId>k__BackingField","token":67152212},"Game.Model.NpcModel:67152100":{"name":"<PersuadeRound>k__BackingField","token":67152213},"Game.Model.NpcModel:67152101":{"name":"<PersuadeChatMessages>k__BackingField","token":67152214},"Game.Model.NpcModel:67152102":{"name":"<PersuadeEmotionValue>k__BackingField","token":67152215},"Game.Model.NpcModel:67152104":{"name":"IsProcessingPersuadeMessage","token":67152217},"Game.Model.NpcModel:67152105":{"name":"_persuadeProcessingToken","token":67152218},"Game.Model.NpcModel:67152107":{"name":"_persuadeLedger","token":67152220},"Game.Model.NpcModel:67152110":{"name":"<PersuadeSessionId>k__BackingField","token":67152223},"Game.Model.NpcModel:67152114":{"name":"OnPersuadeEnded","token":67152227},"Game.Model.NpcModel:67152126":{"name":"<NpcCfgId>k__BackingField","token":67152239},"Game.Model.NpcModel:67152128":{"name":"<WorldStatus>k__BackingField","token":67152241},"Game.Model.NpcModel:67152129":{"name":"<GameWorld>k__BackingField","token":67152242},"Game.Model.NpcModel:67152147":{"name":"<MiniGameStatistics>k__BackingField","token":67152260},"Game.Model.NpcModel:67152148":{"name":"<NpcInteractionRuntime>k__BackingField","token":67152261},"Game.Model.Components.BagItemBase:67153914":{"name":"ItemId","token":67154039},"Game.Model.Components.BagItemBase:67153915":{"name":"Count","token":67154040},"Game.Model.Components.BagItemBase:67153917":{"name":"IsEquipped","token":67154042},"Game.Model.Components.BagModel:67153979":{"name":"<Items>k__BackingField","token":67154104}};
function reviewedFieldToken(klass, token, name) {
    if (!currentNativeProfile) return token;
    const owner=klass.add(24).readPointer().readUtf8String()+'.'+klass.add(16).readPointer().readUtf8String();
    const field=REVIEWED_FIELD_VARIANTS[owner+':'+String(token)];
    if (!field) return token;
    requireValue(field.name===name, 'Reviewed field identity differs');
    return field.token;
}
function reviewedCodePair(rva, legacyBytes) {
    if (!currentNativeProfile) return [rva,legacyBytes];
    const matches=Object.values(REVIEWED_NATIVE_VARIANTS).filter(v=>v.legacy_rva===rva);
    requireValue(matches.length===1,'Unknown reviewed native code proof');
    return [matches[0].rva,matches[0].prefix];
}
function validateCodePair(rva, legacyBytes, label) {
    const selected=reviewedCodePair(rva,legacyBytes);
    requireValue(hexAt(image.base.add(selected[0]),selected[1].length/2)===selected[1],label);
}
function nativeSpec(legacy) {
    const variant = REVIEWED_NATIVE_VARIANTS[String(legacy.token)];
    if (!variant || variant.legacy_rva !== legacy.rva) return legacy;
    const result = Object.assign({}, legacy);
    for (const key of ['name', 'token', 'rva', 'prefix']) {
        Object.defineProperty(result, key, { enumerable: true,
            get() { return currentNativeProfile ? variant[key] : legacy[key]; } });
    }
    return result;
}
const UPDATE_CANDIDATES = [0x14342d0, 0x1464640];
function reviewedUpdate() {
    const matching = UPDATE_CANDIDATES.filter(rva => {
        try { return hexAt(image.base.add(rva), 13) === '48895c2408574883ec60488bd9'; }
        catch (_) { return false; }
    });
    if (matching.length !== 1) throw new Error('A1Main.Update entry is unrecognized or ambiguous');
    currentNativeProfile = matching[0] === 0x1464640;
    return image.base.add(matching[0]);
}
const invoke = new NativeFunction(image.getExportByName('il2cpp_runtime_invoke'),
    'pointer', ['pointer', 'pointer', 'pointer', 'pointer'], { exceptions: 'steal' });
const paramCount = new NativeFunction(image.getExportByName('il2cpp_method_get_param_count'), 'uint', ['pointer']);
const methodToken = new NativeFunction(image.getExportByName('il2cpp_method_get_token'), 'uint', ['pointer']);
const methodParam = new NativeFunction(image.getExportByName('il2cpp_method_get_param'), 'pointer', ['pointer', 'uint']);
const classFromType = new NativeFunction(image.getExportByName('il2cpp_class_from_type'), 'pointer', ['pointer']);

function hexAt(address, size) {
    return Array.from(new Uint8Array(ptr(address).readByteArray(size)))
        .map(b => b.toString(16).padStart(2, '0')).join('');
}
function finish(status, extra) {
    if (listener !== null) { listener.detach(); listener = null; }
    if (expiry !== null) { clearTimeout(expiry); expiry = null; }
    state = status;
    terminal = Object.assign({ token: request.token, status: status }, extra || {});
    send(terminal);
}
// The source hashes and metadata fields are checked by the Python resolver.
// Re-read its whole registration/round proof on Unity's thread, then independently
// validate the actual board and the single reviewed native method before calling.
const MERIDIAN_METHOD = nativeSpec({ token: 0x06010174, rva: 0x1dac830, argc: 0 });
const MERIDIAN_CODE = [[0x1dac830, '40535556574883ec38803dbe467a0600'],
    [0x1dabad0, '44884c24204488442418488954241055'],
    [0xa4caf0, '40534883ec20803d1ca3af0700488bd9'],
    [0x1dae1c0, '48895c2410574883ec40803d562d7a06']];
const VARIANTS = [3, 6, 6, 2, 6, 1];
const PORTS = [[0, 3], [0, 1], [0, 2], [0, 2, 4], [0, 1, 2], [0, 1, 2, 3, 4, 5]];
function requireValue(ok, message) { if (!ok) throw new Error(message); }
function boolAt(address) {
    const value = ptr(address).readU8();
    requireValue(value === 0 || value === 1, 'Invalid Boolean state');
    return value === 1;
}
function samePointer(a, b, message) { requireValue(ptr(a).equals(ptr(b)), message); }
let coverageRequest = null, coverageAnchors = null, coverageCount = -1, coverageRanges = [];
function covered(address, size) {
    if (!Number.isInteger(size) || size <= 0) return false;
    const first = ptr(address), last = first.add(size);
    if (last.compare(first) <= 0) return false;
    // Large concurrent NPC maps carry split proof blocks. Index their union
    // once per request instead of scanning thousands of anchors for each node.
    if (coverageRequest !== request || coverageAnchors !== request.anchors || coverageCount !== request.anchors.length) {
        coverageRequest = request; coverageAnchors = request.anchors; coverageCount = request.anchors.length;
        const ranges = request.anchors.map(a => {
            const range = {first:ptr(a.address),last:ptr(a.address).add(a.size)};
            requireValue(Number.isInteger(a.size) && a.size>0 && range.last.compare(range.first)>0, 'Invalid proof address interval');
            return range;
        });
        ranges.sort((a,b) => a.first.compare(b.first)); coverageRanges = [];
        for (const range of ranges) {
            const previous = coverageRanges[coverageRanges.length-1];
            if (previous && range.first.compare(previous.last) <= 0) {
                if (range.last.compare(previous.last) > 0) previous.last = range.last;
            } else coverageRanges.push(range);
        }
    }
    let low = 0, high = coverageRanges.length;
    while (low < high) { const mid = (low+high) >>> 1; if (coverageRanges[mid].first.compare(first) <= 0) low=mid+1; else high=mid; }
    return low>0 && last.compare(coverageRanges[low-1].last)<=0;
}
function requireCoverage(address, size) {
    requireValue(covered(address, size), 'Incomplete current identity proof');
}
function className(object, namespace, name) {
    const klass = ptr(object).readPointer();
    requireValue(!klass.isNull(), 'Missing meridian class');
    requireValue(klass.add(16).readPointer().readUtf8String() === name &&
        klass.add(24).readPointer().readUtf8String() === namespace, 'Meridian class differs');
    return klass;
}
function reviewedRegistryRoot(m) {
    requireValue(m && Array.isArray(m.registry_links) && m.registry_links.length >= 8, 'Missing canonical registry chain');
    const first=m.registry_links[0],klass=className(m.manager,'Game','UIManager');
    const address=ptr(first.address);
    if (address.equals(klass.add(0x58))) {
        requireCoverage(m.manager,8);requireCoverage(address,8);
        samePointer(address.readPointer(),first.expected,'Canonical UI parent changed');
    } else {
        // Legacy descriptor retains its directly proved class-info slot.
        samePointer(address,image.base.add(0x8157868),'Wrong legacy UI root');
        requireCoverage(address,8);
    }
}
function validateMeridian(method) {
    const m = request.meridian;
    requireValue(m && typeof m.round_key === 'string' && m.round_key.length > 0, 'Missing meridian round');
    requireValue(request.method_token === MERIDIAN_METHOD.token &&
        request.method_rva === MERIDIAN_METHOD.rva && request.parameter_count === 0,
        'Meridian method is not whitelisted');
    for (const [rva, bytes] of MERIDIAN_CODE) {
        validateCodePair(rva, bytes, 'Meridian code differs');
    }
    const panel = ptr(m.panel), game = ptr(m.vm), config = ptr(m.config);
    const ns = 'Game.UI.UPFLogic.MedGame';
    className(panel, ns, 'MedGamePanel');
    const klass = className(game, ns, 'MedGameViewModel');
    className(config, ns, 'MedGameConfig');
    samePointer(method.add(0x20).readPointer(), klass, 'Meridian method class differs');
    requireValue(method.add(0x18).readPointer().readUtf8String() === 'RevealSolutionPathForEditor',
        'Meridian method name differs');
    requireValue((method.add(0x4c).readU16() & 0x10) === 0 &&
        method.add(0x28).readPointer().add(10).readU8() === 2, 'Meridian method type differs');
    reviewedRegistryRoot(m);
    requireCoverage(panel, 8); requireCoverage(game, 8); requireCoverage(config, 8);
    requireCoverage(panel.add(0xd0), 8); requireCoverage(game.add(0x40), 8);
    requireCoverage(game.add(0x48), 4); requireCoverage(panel.add(0xa8), 4);
    // Every link is taken from token-verified fields in the canonical UI registry.
    requireValue(Array.isArray(m.registry_links) && m.registry_links.length >= 8,
        'Missing current panel registration chain');
    for (const link of m.registry_links) {
        requireCoverage(link.address, 8);
        samePointer(ptr(link.address).readPointer(), link.expected, 'Panel registration chain changed');
    }
    reviewedRegistryRoot(m);
    const registry = m.registry;
    requireValue(registry && Number.isInteger(registry.count) && registry.count > 0 && registry.count <= 512,
        'Invalid panel registry');
    requireCoverage(registry.count_address, 4);
    requireValue(ptr(registry.count_address).readS32() === registry.count, 'Panel registry count changed');
    requireValue(m.registry_links.some(link => ptr(link.expected).equals(ptr(m.manager))), 'Manager chain missing');
    requireValue(m.registry_links.some(link => ptr(link.expected).equals(ptr(registry.dictionary))) &&
        m.registry_links.some(link => ptr(link.expected).equals(ptr(registry.entries))), 'Registry chain incomplete');
    className(m.manager, 'Game', 'UIManager');
    requireValue(!boolAt(ptr(m.manager).add(0x18)), 'UI manager shutting down');
    const entryArray = ptr(registry.entries);
    const capacity = entryArray.add(24).readU64().toNumber();
    requireValue(capacity >= registry.count && capacity <= 2048, 'Registry capacity differs');
    let matches = 0;
    for (let i = 0; i < registry.count; i++) {
        const entry = entryArray.add(32 + i * 24);
        requireCoverage(entry, 24);
        if (entry.readS32() >= 0 && entry.add(16).readPointer().equals(panel)) matches++;
    }
    requireValue(matches === 1, 'Panel is not uniquely registered');
    samePointer(panel.add(0xd0).readPointer(), game, 'Panel round changed');
    samePointer(game.add(0x40).readPointer(), config, 'Round config changed');
    requireValue(game.add(0x48).readS32() === m.seed && panel.add(0xa8).readS32() === m.handle,
        'Round seed or handle changed');
    requireValue(!panel.add(16).readPointer().isNull() && boolAt(panel.add(0x42)) &&
        boolAt(panel.add(0x43)) && !boolAt(panel.add(0x58)), 'Panel is not live');
    for (const offset of [0xf8, 0xf9, 0xfa, 0xfc]) {
        requireValue(!boolAt(panel.add(offset)), 'Panel is loading, settling, or confirming exit');
    }
    requireValue(boolAt(panel.add(0xfb)), 'Board not loaded');
    for (const offset of [0x71, 0x72, 0x73, 0x75, 0x77]) {
        requireValue(!boolAt(game.add(offset)), 'Round is paused, finished, or busy');
    }
    requireValue(boolAt(game.add(0x89)) && game.add(0x108).readS32() === 0, 'Round is not ready');
    requireValue(!game.add(0xc0).readPointer().isNull(), 'Round completion callback missing');
    for (const offset of [0xd0, 0xd8, 0xe0, 0xe8]) {
        requireValue(game.add(offset).readPointer().isNull(), 'Round animation still active');
    }
    requireValue(Number.isInteger(m.cols) && Number.isInteger(m.rows) && m.cols > 0 && m.rows > 0 &&
        m.cols <= 64 && m.rows <= 64 && m.cols * m.rows <= 1024, 'Invalid board dimensions');
    for (const [field, offset] of [['cols', 0x20], ['rows', 0x24], ['start_col', 0x28],
        ['start_row', 0x2c], ['end_col', 0x30], ['end_row', 0x34]]) {
        requireValue(config.add(offset).readS32() === m[field], 'Board configuration changed');
    }
    const remaining = game.add(0x64).readFloat();
    requireValue(Number.isFinite(remaining) && (config.add(0x40).readS32() === -1 || remaining > 0),
        'Round time expired');
    const collection = game.add(0xf8).readPointer();
    className(collection, 'Loxodon.Framework.Observables', 'ObservableList`1');
    const items = collection.add(0x38).readPointer();
    className(items, 'System.Collections.Generic', 'List`1');
    const count = items.add(0x18).readS32(), array = items.add(0x10).readPointer();
    requireValue(Array.isArray(m.cells) && count === m.cols * m.rows && count === m.cells.length &&
        array.add(24).readU64().toNumber() >= count && array.add(24).readU64().toNumber() <= 2048,
        'Incomplete current board');
    const coords = new Map(), addresses = new Set(); let changed = false, starts = 0, ends = 0;
    for (let i = 0; i < count; i++) {
        const cell = m.cells[i], address = array.add(32 + 8 * i).readPointer();
        samePointer(address, cell.address, 'Cell identity changed');
        requireValue(!addresses.has(address.toString()), 'Duplicate board object'); addresses.add(address.toString());
        className(address, ns, 'MedCellViewModel');
        samePointer(address.add(0x28).readPointer(), game, 'Cell belongs to another round');
        for (const [field, offset] of [['col', 0x30], ['row', 0x34], ['kind', 0x38], ['shape', 0x3c],
            ['variant', 0x40], ['rotate_count', 0x6c], ['solution_shape', 0x78], ['solution_variant', 0x7c], ['role', 0x90]]) {
            requireValue(address.add(offset).readS32() === cell[field], 'Cell data changed: ' + field);
        }
        requireValue(boolAt(address.add(0x48)) === cell.hidden && boolAt(address.add(0x74)) === cell.is_generated_path,
            'Cell visibility or solution changed');
        requireValue(Number.isInteger(cell.col) && Number.isInteger(cell.row) && cell.col >= 0 && cell.col < m.cols &&
            cell.row >= 0 && cell.row < m.rows && [0, 1, 2].includes(cell.role) && [0, 1, 2, 3].includes(cell.kind) &&
            Number.isInteger(cell.shape) && cell.shape >= 0 && cell.shape < 6 && Number.isInteger(cell.solution_shape) &&
            cell.solution_shape >= 0 && cell.solution_shape < 6 && cell.variant >= 0 && cell.variant < VARIANTS[cell.shape] &&
            cell.solution_variant >= 0 && cell.solution_variant < VARIANTS[cell.solution_shape] &&
            cell.rotate_count >= 0 && cell.rotate_count <= 1000000, 'Invalid cell values');
        const key = cell.col + ':' + cell.row; requireValue(!coords.has(key), 'Duplicate board coordinate');
        coords.set(key, cell);
        if (cell.role === 1) { starts++; requireValue(cell.col === m.start_col && cell.row === m.start_row, 'Start differs'); }
        if (cell.role === 2) { ends++; requireValue(cell.col === m.end_col && cell.row === m.end_row, 'End differs'); }
        if (cell.is_generated_path && (cell.hidden || cell.kind !== 0 || cell.shape !== cell.solution_shape ||
            cell.variant !== cell.solution_variant || address.add(0x44).readS32() !== cell.solution_variant)) changed = true;
    }
    requireValue(starts === 1 && ends === 1, 'Board endpoints differ');
    requireValue(changed, '原始路线已经对齐，本次未调用；请等待游戏结算或刷新。');
    // Validate the outcome of the helper's real rules, including restored shape,
    // hidden cells and removed obstructions. Do not assume every seed is valid.
    function cellPorts(cell) {
        const shape = cell.is_generated_path ? cell.solution_shape : cell.shape;
        const variant = cell.is_generated_path ? cell.solution_variant : cell.variant;
        return PORTS[shape].map(d => (d + variant) % 6);
    }
    function canConnect(cell) { return cell && (cell.is_generated_path || (!cell.hidden && cell.kind !== 3)); }
    const start = m.start_col + ':' + m.start_row, end = m.end_col + ':' + m.end_row;
    const queue = [start], seen = new Set(queue);
    for (let i = 0; i < queue.length; i++) {
        const cell = coords.get(queue[i]); if (!canConnect(cell)) continue;
        const odd = cell.row & 1;
        const neighbors = [[cell.col + 1, cell.row], [cell.col + odd, cell.row + 1],
            [cell.col - 1 + odd, cell.row + 1], [cell.col - 1, cell.row],
            [cell.col - 1 + odd, cell.row - 1], [cell.col + odd, cell.row - 1]];
        for (const direction of cellPorts(cell)) {
            const key = neighbors[direction].join(':'), target = coords.get(key);
            if (!seen.has(key) && canConnect(target) && cellPorts(target).includes((direction + 3) % 6)) {
                seen.add(key); queue.push(key);
            }
        }
    }
    requireValue(seen.has(end), 'Restored solution does not connect endpoints');
    return game;
}
const GROWTH_ATTRS = new Set([2, 3, 4, 5, 6, 7, 21, 22, 24, 111, 112, 113, 114, 115, 116, 201]);
function growthEntry(dictionary, attr) {
    const count = dictionary.add(0x20).readS32(), array = dictionary.add(0x18).readPointer();
    requireValue(count >= 0 && count <= 512, 'Growth dictionary count invalid');
    if (array.isNull()) { requireValue(count === 0, 'Growth dictionary entries missing'); return null; }
    const capacity = array.add(24).readU64().toNumber();
    requireValue(capacity >= count && capacity <= 2048, 'Growth dictionary capacity invalid');
    let found = null;
    for (let i = 0; i < count; i++) {
        const entry = array.add(32 + i * 16);
        if (entry.readS32() >= 0 && entry.add(8).readS32() === attr) {
            requireValue(found === null, 'Duplicate growth attribute'); found = entry.add(12);
        }
    }
    return found;
}
const GROWTH_METHOD = nativeSpec({name:'SetGrowthAttr',token:0x06014b6c,rva:0xe679f0,argc:2,returns:1,params:[0x11,12],prefix:'48895c2408574883ec30803d981c6e0700'});
function validateGrowth(method) {
    const c = request.character;
    requireValue(c && typeof c.identity_key === 'string' && c.identity_key.length > 0 &&
        Number.isInteger(c.attr_id) && GROWTH_ATTRS.has(c.attr_id), 'Unreviewed character attribute');
    const limit = c.attr_id === 7 ? 1 : c.attr_id >= 111 && c.attr_id <= 116 ? Math.fround(0.1) : 1000;
    requireValue(Number.isFinite(c.value) && c.value >= 0 && c.value <= limit,
        'Missing growth key exceeds its reviewed per-attribute change limit');
    requireValue(request.method_token === GROWTH_METHOD.token && request.method_rva === GROWTH_METHOD.rva &&
        request.parameter_count === 2, 'Growth method is not whitelisted');
    requireValue(hexAt(image.base.add(GROWTH_METHOD.rva), GROWTH_METHOD.prefix.length/2) === GROWTH_METHOD.prefix, 'Growth method code differs');
    const combat = ptr(c.combat), dictionary = ptr(c.dictionary);
    const klass = className(combat, 'Game.Model.Player.Components', 'CombatModel');
    samePointer(klass, c.combat_class, 'Combat class changed');
    samePointer(method.add(0x20).readPointer(), klass, 'Growth method class differs');
    requireValue(method.add(0x18).readPointer().readUtf8String() === 'SetGrowthAttr' &&
        (method.add(0x4c).readU16() & 0x10) === 0 && method.add(0x28).readPointer().add(10).readU8() === 1,
        'Growth method type differs');
    samePointer(combat.add(0x10).readPointer(), c.player, 'Combat owner changed');
    samePointer(combat.add(0x28).readPointer(), dictionary, 'Growth dictionary changed');
    requireValue(!ptr(c.player).isNull() && !dictionary.isNull(), 'Missing character objects');
    className(dictionary, 'System.Collections.Generic', 'Dictionary`2');
    for (const [address, size] of [[combat, 8], [combat.add(0x10), 8], [combat.add(0x28), 8],
        [dictionary.add(0x18), 8], [dictionary.add(0x20), 4]]) requireCoverage(address, size);
    const count = dictionary.add(0x20).readS32(), entries = dictionary.add(0x18).readPointer();
    requireValue(count >= 0 && count <= 512, 'Growth dictionary count invalid');
    for (let i = 0; i < count; i++) {
        // Python intentionally separates structural identity (12 bytes) from
        // the mutable Single value (4 bytes); accept that exact proof layout.
        const entry = entries.add(32 + 16 * i);
        requireCoverage(entry, 12); requireCoverage(entry.add(12), 4);
    }
    requireValue(growthEntry(dictionary, c.attr_id) === null, 'Growth key already exists; refresh before editing');
    return combat;
}
const INTERACT_ATTRS = new Set([1001, 1002, 1003, 1004, 1005]);
const INTERACT_METHOD = nativeSpec({ name: 'SetInteractAttributeValue', token: 0x06013e63, rva: 0xdc5ee0,
    argc: 2, returns: 1, params: [0x11, 8], prefix: '48895c2418554883ec20803d832f780700' });
const STAMINA_METHODS = {
    current: nativeSpec({ name: 'GetCurrentStamina', token: 0x06014b07, rva: 0xe5fea0,
        argc: 0, returns: 12, params: [], prefix: '40534883ec20803d98976e0700488bd97513' }),
    max: nativeSpec({ name: 'GetMaxStamina', token: 0x06014b08, rva: 0xe60a90,
        argc: 0, returns: 12, params: [], prefix: '4883ec284533c0bac9000000e88febffff' }),
    modify: nativeSpec({ name: 'ModifyStamina', token: 0x06014b00, rva: 0xe653a0,
        argc: 1, returns: 2, params: [12], prefix: '4883ec380f28d948c744242000000000bac800000041b8c9000000e820fbffff' })
};
const RESOURCE_OPERATIONS = {
    current_stamina_set: { key: 'current_stamina', attr: 200, minimum: 0, methods: STAMINA_METHODS },
    current_health_set: { key: 'current_health', attr: 1, minimum: 1, methods: {
        current: nativeSpec({ name: 'GetCurrentHealth', token: 0x06014b09, rva: 0xe5fdc0,
            argc: 0, returns: 12, params: [], prefix: '40534883ec20803d79986e0700488bd97513' }),
        max: nativeSpec({ name: 'GetMaxHealth', token: 0x06014b0a, rva: 0xe609f0,
            argc: 0, returns: 12, params: [], prefix: '4883ec284533c0ba04000000e82fecffff' }),
        modify: nativeSpec({ name: 'ModifyHealth', token: 0x06014b01, rva: 0xe65070,
            argc: 1, returns: 2, params: [12], prefix: '4883ec380f28d948c744242000000000ba0100000041b804000000e850feffff' })
    } },
    current_mana_set: { key: 'current_mana', attr: 25, minimum: 0, methods: {
        current: nativeSpec({ name: 'GetCurrentMana', token: 0x06014b0b, rva: 0xe5fe30,
            argc: 0, returns: 12, params: [], prefix: '40534883ec20803d0a986e0700488bd97513' }),
        max: nativeSpec({ name: 'GetMaxMana', token: 0x06014b0c, rva: 0xe60a60,
            argc: 0, returns: 12, params: [], prefix: '4883ec284533c0ba16000000e8bfebffff' }),
        modify: nativeSpec({ name: 'ModifyMana', token: 0x06014b02, rva: 0xe650a0,
            argc: 1, returns: 2, params: [12], prefix: '4883ec380f28d948c744242000000000ba1900000041b816000000e820feffff' })
    } }
};
function validateReviewedMethod(method, klass, spec) {
    samePointer(method.readPointer(), image.base.add(spec.rva), 'Reviewed method address differs');
    samePointer(method.add(0x20).readPointer(), klass, 'Reviewed method class differs');
    requireValue(methodToken(method) === spec.token && paramCount(method) === spec.argc &&
        method.add(0x18).readPointer().readUtf8String() === spec.name &&
        (method.add(0x4c).readU16() & 0x10) === 0, 'Reviewed method signature differs');
    requireValue(hexAt(image.base.add(spec.rva), spec.prefix.length / 2) === spec.prefix,
        'Reviewed method code differs');
    function checkType(type, kind) {
        // IL2CPP v31 uses bit 29 for byref (verified from this DLL's
        // il2cpp_type_is_byref); byte 11's 0x80 is the ordinary value-type
        // marker on Single/Boolean/Int32. Reject all other extra flags.
        requireValue(!type.isNull() && type.add(10).readU8() === kind &&
            (type.add(11).readU8() & 0x7f) === 0, 'Reviewed method argument or return type differs');
    }
    checkType(method.add(0x28).readPointer(), spec.returns);
    for (let i = 0; i < spec.params.length; i++) checkType(methodParam(method, i), spec.params[i]);
}
function requireRequestMethod(spec) {
    requireValue(request.method_token === spec.token && request.method_rva === spec.rva &&
        request.parameter_count === spec.argc, 'Requested method is not whitelisted');
}
// Both reviewed dictionaries use 16-byte entries. The source-side resolver
// proves their generic field layout; this rechecks every live/free slot and
// rejects a stale or duplicate key immediately on the Unity thread.
function characterEntries(dictionary, interact, proof) {
    const found = new Map();
    if (dictionary.isNull()) { requireValue(interact, 'Base attributes missing'); return found; }
    className(dictionary, 'System.Collections.Generic', 'Dictionary`2');
    const count = dictionary.add(0x20).readS32(), free = dictionary.add(0x28).readS32();
    const array = dictionary.add(0x18).readPointer();
    requireValue(free >= 0 && free <= count && count <= (interact ? 64 : 256), 'Character dictionary count invalid');
    if (proof) {
        for (const [address, size] of [[dictionary, 8], [dictionary.add(0x18), 8],
            [dictionary.add(0x20), 4], [dictionary.add(0x28), 4], [dictionary.add(0x2c), 4]]) requireCoverage(address, size);
    }
    if (array.isNull()) { requireValue(count === 0, 'Character dictionary entries missing'); return found; }
    const capacity = array.add(24).readU64().toNumber();
    requireValue(capacity >= count && capacity <= (interact ? 128 : 512), 'Character dictionary capacity invalid');
    if (proof) requireCoverage(array.add(24), 8);
    let live = 0;
    for (let i = 0; i < count; i++) {
        const entry = array.add(32 + i * 16), hash = entry.readS32(), next = entry.add(4).readS32();
        if (proof) requireCoverage(entry, interact ? 16 : 12);
        requireValue(next >= -1 && next < Math.max(1, count), 'Character dictionary chain invalid');
        if (hash < 0) continue;
        live++;
        const key = entry.add(8).readS32(), value = interact ? entry.add(12).readS32() : entry.add(12).readFloat();
        requireValue((interact ? INTERACT_ATTRS.has(key) && value >= 0 :
            key > 0 && Number.isFinite(value) && Math.abs(value) <= 100000000) && !found.has(key),
            'Character dictionary key or value invalid');
        if (proof && !interact) requireCoverage(entry.add(12), 4);
        found.set(key, entry.add(12));
    }
    requireValue(live === count - free, 'Character dictionary free count differs');
    return found;
}
function validateInteract(method) {
    const c = request.character;
    requireValue(c && typeof c.identity_key === 'string' && c.identity_key.length > 0 && INTERACT_ATTRS.has(c.attr_id) &&
        Number.isInteger(c.maximum) && c.maximum >= 1 && c.maximum <= 5700 && Number.isInteger(c.value) &&
        c.value >= 0 && c.value <= Math.min(c.maximum, 1000), 'Invalid missing interaction attribute request');
    requireRequestMethod(INTERACT_METHOD);
    const player = ptr(c.player), dictionary = ptr(c.dictionary), klass = className(player, 'Game.Model', 'PlayerModel');
    samePointer(klass, c.player_class, 'Current player class changed');
    requireCoverage(player, 8); requireCoverage(player.add(0x1a8), 8);
    samePointer(player.add(0x1a8).readPointer(), dictionary, 'Interaction dictionary changed');
    validateReviewedMethod(method, klass, INTERACT_METHOD);
    const argumentClass = classFromType(methodParam(method, 0));
    requireValue(!argumentClass.isNull() && argumentClass.add(16).readPointer().readUtf8String() === 'TbInteractAttributeId' &&
        argumentClass.add(24).readPointer().readUtf8String() === 'LubanDatas', 'Interaction attribute wrapper differs');
    requireValue(!characterEntries(dictionary, true, true).has(c.attr_id), 'Interaction key already exists; refresh before editing');
    return player;
}
function staminaOwner(r, proof) {
    const combat = ptr(r.combat), dictionary = ptr(r.dictionary);
    const klass = className(combat, 'Game.Model.Player.Components', 'CombatModel');
    samePointer(klass, r.combat_class, 'Stamina class changed');
    samePointer(combat.add(0x10).readPointer(), r.player, 'Stamina owner changed');
    samePointer(combat.add(0x20).readPointer(), dictionary, 'Base attributes changed');
    className(r.player, 'Game.Model', 'PlayerModel');
    if (proof) {
        for (const [address, size] of [[combat, 8], [combat.add(0x10), 8], [combat.add(0x20), 8], [ptr(r.player), 8]]) requireCoverage(address, size);
    }
    const entry = characterEntries(dictionary, false, proof).get(RESOURCE_OPERATIONS[request.operation].attr);
    requireValue(entry !== undefined, 'Current resource key is missing; let the game initialize it');
    samePointer(entry, r.address, 'Current stamina address differs');
    return { combat: combat, klass: klass, entry: entry };
}
function floatBits(value) {
    const memory = Memory.alloc(4); memory.writeFloat(value); return hexAt(memory, 4);
}
function validateStamina(method) {
    const r = request.resource;
    const spec = RESOURCE_OPERATIONS[request.operation];
    requireValue(r && r.resource_key === spec.key && typeof r.identity_key === 'string' && r.identity_key.length > 0 && r.methods &&
        Object.keys(r.methods).sort().join(',') === 'current,max,modify', 'Missing stamina identity or methods');
    for (const value of [r.before, r.value]) requireValue(Number.isFinite(value) && value >= spec.minimum && value <= 1000000 &&
        Object.is(Math.fround(value), value), 'Stamina must be an exact bounded Single');
    requireValue(Math.abs(r.value - r.before) <= 1000 && floatBits(r.before) !== floatBits(r.value),
        'Stamina change must be nonzero and at most 1000');
    requireRequestMethod(spec.methods.modify);
    samePointer(method, r.methods.modify, 'Stamina setter identity differs');
    const owner = staminaOwner(r, true);
    requireValue(hexAt(owner.entry, 4) === floatBits(r.before), 'Current stamina changed');
    for (const key of ['current', 'max', 'modify']) validateReviewedMethod(ptr(r.methods[key]), owner.klass, spec.methods[key]);
    return owner.combat;
}
function readStamina(method, target) {
    const exception = Memory.alloc(Process.pointerSize); exception.writePointer(ptr(0));
    const result = invoke(ptr(method), target, ptr(0), exception);
    requireValue(exception.readPointer().isNull(), 'Stamina getter raised an exception');
    requireValue(!result.isNull(), 'Stamina getter returned no value');
    className(result, 'System', 'Single');
    const value = result.add(16).readFloat();
    requireValue(Number.isFinite(value), 'Stamina getter returned nonfinite value');
    return value;
}
function validateAnchors() {
    for (const a of request.anchors) {
        if (hexAt(a.address, a.size) !== a.expected_hex) throw new Error('Current-save anchor changed: ' + a.label);
    }
}
const LIFESPAN_METHODS = {
    age: { name: 'get_CurrentAge', token: 0x06013e64, rva: 0xdc7160, argc: 0,
        returns: 8, params: [], prefix: '48895c2408574883ec20803d041d7807' },
    max: { name: 'get_MaxLifespan', token: 0x06013e65, rva: 0xdc73a0, argc: 0,
        returns: 8, params: [], prefix: '4883ec384883794800750733c04883c4' },
    modify: { name: 'ModifyMaxLifespan', token: 0x06013e6e, rva: 0xdc3fb0, argc: 1,
        returns: 12, params: [12], prefix: '40534883ec20488bd9488b49484885c9' }
};
const LIFESPAN_PROFILES = {
    legacy: LIFESPAN_METHODS,
    reviewed_20260930: {
        age: { name: 'get_CurrentAge', token: 0x06013eac, rva: 0xdf6320, argc: 0,
            returns: 8, params: [], prefix: '48895c2408574883ec20803db0517607' },
        max: { name: 'get_MaxLifespan', token: 0x06013ead, rva: 0xdf6560, argc: 0,
            returns: 8, params: [], prefix: '4883ec384883794800750733c04883c4' },
        modify: { name: 'ModifyMaxLifespan', token: 0x06013eb6, rva: 0xdf31b0, argc: 1,
            returns: 12, params: [12], prefix: '40534883ec20488bd9488b49484885c9' }
    }
};
function lifespanOwner(l, proof) {
    const player = ptr(l.player), combat = ptr(l.combat), growth = ptr(l.growth_dictionary), base = ptr(l.base_dictionary);
    const klass = className(player, 'Game.Model', 'PlayerModel');
    samePointer(klass, l.player_class, 'Lifespan player class changed');
    samePointer(className(combat, 'Game.Model.Player.Components', 'CombatModel'), l.combat_class, 'Lifespan combat class changed');
    samePointer(player.add(0x48).readPointer(), combat, 'Lifespan player component changed');
    samePointer(combat.add(0x10).readPointer(), player, 'Lifespan owner changed');
    samePointer(combat.add(0x28).readPointer(), growth, 'Lifespan growth dictionary replaced');
    samePointer(combat.add(0x20).readPointer(), base, 'Lifespan base dictionary replaced');
    for (const [address, size] of [[player,8], [combat,8], [player.add(0x48),8], [combat.add(0x10),8],
        [combat.add(0x28),8], [combat.add(0x20),8], [player.add(0x1b8),1], [player.add(0x1bc),8], [player.add(0x1c4),8]]) {
        if (proof) requireCoverage(address, size);
    }
    requireValue(!boolAt(player.add(0x1b8)) && !boolAt(player.add(0x1bc)) && !boolAt(player.add(0x1c4)),
        'Lifespan exhaustion is running or has unresolved handled markers; resurrection is not supported');
    const growthEntries = characterEntries(growth, false, proof), baseEntries = characterEntries(base, false, proof);
    const health = baseEntries.get(1);
    requireValue(health !== undefined, 'Health is not initialized');
    samePointer(health, l.health_address, 'Health entry changed');
    requireValue(Number.isFinite(health.readFloat()) && health.readFloat() > 0 && health.readFloat() <= 1000000,
        'Character is not alive');
    return { player, klass, growth, base, growthEntries, baseEntries };
}
function lifespanInteger(method, target) {
    const exception = Memory.alloc(Process.pointerSize); exception.writePointer(ptr(0));
    const result = invoke(ptr(method), target, ptr(0), exception);
    requireValue(exception.readPointer().isNull() && !result.isNull(), 'Lifespan getter failed');
    className(result, 'System', 'Int32');
    const value = result.add(16).readS32();
    requireValue(Number.isInteger(value) && value >= 0 && value <= 2147483647, 'Lifespan getter outside native Int32 bounds');
    return value;
}
function lifespanEntryBits(entries) {
    const result = new Map();
    for (const [key, address] of entries) result.set(key, hexAt(address, 4));
    return result;
}
function executeLifespan() {
    const l = request.lifespan, adding = request.operation === 'lifespan_add';
    requireValue(l && typeof l.identity_key === 'string' && l.identity_key.length > 0 && l.methods &&
        Object.keys(l.methods).sort().join(',') === 'age,max,modify', 'Missing lifespan identity or method set');
    const methods = LIFESPAN_PROFILES[l.method_profile === undefined ? 'legacy' : l.method_profile];
    requireValue(methods && Object.prototype.hasOwnProperty.call(LIFESPAN_PROFILES, l.method_profile === undefined ? 'legacy' : l.method_profile),
        'Unknown lifespan method evidence profile');
    const owner = lifespanOwner(l, true);
    for (const key of ['age','max','modify']) validateReviewedMethod(ptr(l.methods[key]), owner.klass, methods[key]);
    const methodKey = adding ? 'modify' : 'age';
    requireRequestMethod(methods[methodKey]);
    samePointer(request.method_info, l.methods[methodKey], 'Lifespan request method changed');
    requireValue(Number.isFinite(l.growth_before) && Object.is(Math.fround(l.growth_before), l.growth_before) &&
        Math.abs(l.growth_before) <= 1000000, 'Invalid existing lifespan growth');
    const beforeEntry = owner.growthEntries.get(8);
    if (beforeEntry === undefined) {
        requireValue(ptr(l.growth_address).isNull() && l.growth_before === 0, 'Missing lifespan key differs');
    } else {
        samePointer(beforeEntry, l.growth_address, 'Lifespan entry changed');
        requireValue(hexAt(beforeEntry, 4) === floatBits(l.growth_before), 'Lifespan growth changed');
    }
    const age = lifespanInteger(l.methods.age, owner.player), maximum = lifespanInteger(l.methods.max, owner.player);
    requireValue(maximum > 0 && age <= maximum, 'Lifespan is already exhausted; resurrection is not supported');
    validateAnchors();
    if (!adding) {
        finish('completed', { called:true, mutated:false, current_age:age, maximum:maximum,
            growth:l.growth_before, exhausted:false, handling:false, handled_age:false, handled_max:false,
            identity_key:l.identity_key, thread_id:Process.getCurrentThreadId() });
        return;
    }
    requireValue(Number.isInteger(l.amount) && l.amount >= 1 && l.amount <= 1000 &&
        l.expected_age === age && l.expected_maximum === maximum, 'Increase or inspected age/maximum changed');
    const expected = Math.fround(l.growth_before + l.amount);
    requireValue(Number.isFinite(expected) && expected > l.growth_before && expected <= 1000000 &&
        Number.isFinite(l.growth_after) && floatBits(expected) === floatBits(l.growth_after), 'Lifespan growth increase invalid');
    const oldGrowth = lifespanEntryBits(owner.growthEntries), oldBase = lifespanEntryBits(owner.baseEntries);
    const oldVersion = owner.growth.add(0x2c).readS32();
    const argument = Memory.alloc(4); argument.writeFloat(l.amount);
    const argumentsArray = Memory.alloc(Process.pointerSize); argumentsArray.writePointer(argument);
    const exception = Memory.alloc(Process.pointerSize); exception.writePointer(ptr(0));
    if (Date.now() > request.deadline) { finish('cancelled', {called:false,reason:'寿元请求校验时已过期，未增加。'}); return; }
    // Repeat all anchors and live owner checks at the mutation boundary. The
    // getter phase never authorizes a stale inspected target to cross scenes.
    validateAnchors(); lifespanOwner(l, true);
    state = 'running';
    const result = invoke(ptr(l.methods.modify), owner.player, argumentsArray, exception);
    requireValue(exception.readPointer().isNull() && !result.isNull(), 'Lifespan modifier returned exception or no result');
    className(result, 'System', 'Single');
    const actualDelta = result.add(16).readFloat();
    requireValue(Number.isFinite(actualDelta) && actualDelta >= 0, 'Lifespan modifier did not return a finite positive change');
    const afterOwner = lifespanOwner(l, false), afterEntry = afterOwner.growthEntries.get(8);
    requireValue(afterEntry !== undefined && hexAt(afterEntry,4) === floatBits(expected), 'Lifespan growth readback differs');
    requireValue(afterOwner.growth.add(0x2c).readS32() === ((oldVersion + 1) | 0), 'Lifespan dictionary changed beyond the one reviewed operation');
    requireValue(afterOwner.growthEntries.size === oldGrowth.size + (beforeEntry === undefined ? 1 : 0), 'Other lifespan keys changed');
    for (const [key,bits] of oldGrowth) {
        if (key === 8) continue;
        requireValue(afterOwner.growthEntries.has(key) && hexAt(afterOwner.growthEntries.get(key),4) === bits, 'Other growth changed during lifespan addition');
    }
    requireValue(afterOwner.baseEntries.size === oldBase.size, 'Base attributes changed during lifespan addition');
    for (const [key,bits] of oldBase) requireValue(afterOwner.baseEntries.has(key) &&
        hexAt(afterOwner.baseEntries.get(key),4) === bits, 'Base attribute changed during lifespan addition');
    if (actualDelta > 0) requireValue(hexAt(owner.player.add(0x1bc),8) === '0000000000000000' &&
        hexAt(owner.player.add(0x1c4),8) === '0000000000000000', 'Native lifespan wrapper did not clear exhaustion markers');
    const afterAge = lifespanInteger(l.methods.age, owner.player), afterMax = lifespanInteger(l.methods.max, owner.player);
    requireValue(afterAge === age && afterMax >= maximum && afterMax > 0, 'Actual lifespan maximum or age changed unexpectedly');
    finish('completed', {called:true,mutated:true,current_age:afterAge,maximum:afterMax,before_maximum:maximum,
        growth:afterEntry.readFloat(),actual_delta:actualDelta,exhausted:false,handling:false,handled_age:false,handled_max:false,
        identity_key:l.identity_key,thread_id:Process.getCurrentThreadId()});
}

const SPEED_METHODS = {
    base: nativeSpec({name:'get_BaseScale',token:0x06007f5a,rva:0x1517e20,argc:0,returns:12,params:[],prefix:'4883ec28803d07470307007513488d0d'}),
    effective: nativeSpec({name:'get_EffectiveScale',token:0x06007f5c,rva:0x1517e70,argc:0,returns:12,params:[],prefix:'4883ec28803db946030700752b488d0d'}),
    modify: nativeSpec({name:'SetBaseScale',token:0x06007f5e,rva:0x1517b60,argc:1,returns:1,params:[12],prefix:'4883ec38803dcb490307000f29742420'})
};
function speedMethod(method, klass, spec) {
    samePointer(method.readPointer(), image.base.add(spec.rva), 'Speed method address differs');
    samePointer(method.add(0x20).readPointer(), klass, 'Speed method owner differs');
    requireValue(methodToken(method) === spec.token && paramCount(method) === spec.argc &&
        method.add(0x18).readPointer().readUtf8String() === spec.name &&
        (method.add(0x4c).readU16() & 0x10) !== 0, 'Speed static signature differs');
    requireValue(hexAt(image.base.add(spec.rva), spec.prefix.length / 2) === spec.prefix, 'Speed method code differs');
    function checkType(type, kind) {
        requireValue(!type.isNull() && type.add(10).readU8() === kind && (type.add(11).readU8() & 0x7f) === 0,
            'Speed argument or return type differs');
    }
    checkType(method.add(0x28).readPointer(), spec.returns);
    spec.params.forEach((kind, index) => checkType(methodParam(method, index), kind));
}
function speedOwner(s, proof) {
    const klass = ptr(s.klass), statics = ptr(s.static), list = ptr(s.overrides), items = ptr(s.items);
    requireValue(!klass.isNull() && !statics.isNull() && !list.isNull() && !items.isNull(), 'Speed owner not initialized');
    if (!currentNativeProfile) {
        samePointer(image.base.add(0x8149088).readPointer(), klass, 'Speed canonical class changed');
        requireValue(klass.add(0x11c).readS32() === 0x0200099e, 'Speed class differs');
    } else {
        currencyClass(klass,'Game','GameTimeScaleController');
        // Python resolves the current metadata identity. Keep that exact proof
        // stable before and after the setter, without imposing the legacy token.
        for (const [address,size] of [[klass.add(0x68),8],[klass.add(0x11c),4]]) {
            requireValue(request.anchors.some(a => ptr(a.address).equals(address) && a.size === size &&
                a.expected_hex === hexAt(address,size)), 'Speed class identity proof differs');
        }
    }
    requireValue(klass.add(16).readPointer().readUtf8String() === 'GameTimeScaleController' &&
        klass.add(24).readPointer().readUtf8String() === 'Game' &&
        klass.add(0xe0).readS32() === 1, 'Speed class differs');
    samePointer(klass.add(0xb8).readPointer(), statics, 'Speed static storage changed');
    samePointer(statics.readPointer(), list, 'Game speed overrides replaced');
    samePointer(statics.add(8), s.address, 'Speed base address differs');
    className(list, 'System.Collections.Generic', 'List`1');
    samePointer(list.add(0x10).readPointer(), items, 'Speed override array changed');
    className(items, '', 'TimeScaleOverride[]');
    requireValue(Number.isInteger(s.override_count) && s.override_count >= 0 && s.override_count <= 64 &&
        Number.isInteger(s.override_version) && s.override_version >= -2147483648 && s.override_version <= 2147483647 &&
        list.add(0x18).readS32() === s.override_count && list.add(0x1c).readS32() === s.override_version,
        'Speed overrides changed');
    const capacity = items.add(24).readU64().toNumber();
    requireValue(Number.isInteger(s.capacity) && capacity === s.capacity && capacity >= s.override_count && capacity <= 128,
        'Speed override capacity invalid');
    if (proof) {
        for (const [address, size] of [...(!currentNativeProfile ? [[image.base.add(0x8149088),8]] : []),[klass.add(0xb8),8],[klass.add(0xe0),4],
            [statics,8],[statics.add(8),4],[list,8],[list.add(0x10),8],[list.add(0x18),4],[list.add(0x1c),4],[items,8],[items.add(24),8]])
            requireCoverage(address, size);
    }
    let effective = statics.add(8).readFloat();
    const handles = new Set();
    for (let index=0; index<s.override_count; index++) {
        const entry = items.add(32+index*8), handle = entry.readS32(), scale = entry.add(4).readFloat();
        requireValue(handle > 0 && !handles.has(handle) && Number.isFinite(scale) && scale >= 0 && scale <= 100,
            'Speed override entry invalid');
        handles.add(handle);
        // Compare unchanged anchors both before and after SetBaseScale. The
        // setter has no authority to release or replace a game's override.
        requireCoverage(entry,8);
        requireValue(request.anchors.some(a => ptr(a.address).equals(entry) && a.size === 8 && a.expected_hex === hexAt(entry,8)),
            'Speed override contents changed');
        effective = scale;
    }
    requireValue(Number.isFinite(effective) && effective >= 0 && effective <= 100, 'Speed effective value invalid');
    return {klass, statics, effective};
}
function prepareGameSpeed(method) {
    const s = request.speed;
    requireValue(s && typeof s.identity_key === 'string' && /^[a-f0-9]{64}$/.test(s.identity_key) && s.methods &&
        Object.keys(s.methods).sort().join(',') === 'base,effective,modify', 'Speed request identity incomplete');
    requireValue(Number.isFinite(s.value) && Math.fround(s.value) === s.value && s.value >= 0.5 && s.value <= 2 &&
        Number.isFinite(s.before) && s.before >= 0 && s.before <= 100 && Math.fround(s.before) === s.before &&
        Number.isFinite(s.effective_before) && s.effective_before >= 0 && s.effective_before <= 100 &&
        floatBits(s.before) !== floatBits(s.value), 'Speed request out of range or no change');
    if (!currentNativeProfile) requireValue(hexAt(image.base.add(0x1517e40),7) === '488b054112c306', 'Speed canonical code differs');
    requireRequestMethod(SPEED_METHODS.modify);
    samePointer(method, s.methods.modify, 'Speed setter identity differs');
    const owner = speedOwner(s, true);
    for (const key of ['base','effective','modify']) speedMethod(ptr(s.methods[key]), owner.klass, SPEED_METHODS[key]);
    const base = readStamina(s.methods.base, ptr(0)), effective = readStamina(s.methods.effective, ptr(0));
    requireValue(floatBits(base) === floatBits(s.before) && hexAt(owner.statics.add(8),4) === floatBits(s.before) &&
        floatBits(effective) === floatBits(s.effective_before) && floatBits(effective) === floatBits(owner.effective),
        'Speed native readback differs before setting');
    validateAnchors();
    const value = Memory.alloc(4); value.writeFloat(s.value);
    return {target:ptr(0), values:[value]};
}
function completeGameSpeed(result) {
    const s = request.speed;
    requireValue(result.isNull(), 'Speed void setter returned an unexpected value');
    const owner = speedOwner(s, false);
    const value = readStamina(s.methods.base, ptr(0)), effective = readStamina(s.methods.effective, ptr(0));
    const expected = s.override_count ? s.effective_before : s.value;
    requireValue(floatBits(value) === floatBits(s.value) && hexAt(owner.statics.add(8),4) === floatBits(s.value) &&
        floatBits(effective) === floatBits(expected) && floatBits(effective) === floatBits(owner.effective),
        'Speed setter returned but base/effective readback differs; do not retry');
    finish('completed', {called:true, thread_id:Process.getCurrentThreadId(), before:s.before, value,
        effective, override_count:s.override_count, identity_key:s.identity_key});
}

/* Helpers for the shared one-shot bridge. All preparation is read-only.
 * Ops: dual_cultivation_complete / jade_reveal_all, request.minigame.
 * prepareDualCultivation/prepareJade return {target,values}; normal shared
 * invoke is the sole mutation. After invoke/exception check call matching
 * completeDualCultivation/completeJade. Exclude both ops from bag-owner route.
 */
const DUAL_METHOD = nativeSpec({name:'Complete',token:0x06010d8c,rva:0xac8b00,argc:1,returns:1,params:[2],prefix:'48895c2418554883ec30803d99e8a707'});
const JADE_METHOD = nativeSpec({name:'RevealAll',token:0x06010584,rva:0xa86210,argc:0,returns:1,params:[],prefix:'40534883ec3033d2488bd9e8607cffff'});
function dualJadePanel(m, namespace, name) {
    requireValue(m && typeof m.round_key === 'string' && /^[a-f0-9]{64}$/.test(m.round_key), 'Missing minigame identity');
    const panel=ptr(m.panel);
    className(panel,namespace,name);
    requireValue(Array.isArray(m.registry_links) && m.registry_links.length>=8, 'Missing canonical UI registry links');
    reviewedRegistryRoot(m);
    for(const link of m.registry_links) {
        requireCoverage(link.address,8);samePointer(ptr(link.address).readPointer(),link.expected,'UI registry link changed');
    }
    requireValue(m.registry_links.some(l=>ptr(l.expected).equals(ptr(m.manager))),'Missing UI manager');
    className(m.manager,'Game','UIManager');
    requireValue(!boolAt(ptr(m.manager).add(0x18)),'UI manager shutting down');
    const r=m.registry;
    requireValue(r && Number.isInteger(r.count) && r.count>0 && r.count<=512,'Invalid UI registry count');
    for(const v of [r.dictionary,r.entries])requireValue(m.registry_links.some(l=>ptr(l.expected).equals(ptr(v))),'Registry disconnected');
    samePointer(ptr(r.dictionary).add(0x18).readPointer(),r.entries,'Registry array changed');
    samePointer(r.count_address,ptr(r.dictionary).add(0x20),'Registry count address differs');
    requireCoverage(r.count_address,4);requireValue(ptr(r.count_address).readS32()===r.count,'Registry count changed');
    const entries=ptr(r.entries),capacity=entries.add(24).readU64().toNumber();
    requireValue(capacity>=r.count && capacity<=2048,'Registry capacity invalid');
    let count=0;
    for(let i=0;i<r.count;i++) {
        const e=entries.add(32+i*24);requireCoverage(e,24);
        if(e.readS32()>=0 && e.add(16).readPointer().equals(panel))count++;
    }
    requireValue(count===1,'Panel is not uniquely registered');
    for(const [o,n] of [[16,8],[0x42,1],[0x43,1],[0x58,1],[0x92,1],[0x93,1]])requireCoverage(panel.add(o),n);
    requireValue(!panel.add(16).readPointer().isNull() && boolAt(panel.add(0x42)) && boolAt(panel.add(0x43)) &&
        !boolAt(panel.add(0x58)) && boolAt(panel.add(0x92)) && !boolAt(panel.add(0x93)), 'Panel not live or paused');
    return panel;
}
function prepareDualCultivation(method) {
    const m=request.minigame,ns='Game.UI.UPFLogic.DualCultivate';
    const panel=dualJadePanel(m,ns,'DualCultivatePanel'),game=ptr(m.vm),cfg=ptr(m.config);
    const klass=className(game,ns,'DualCultivateGameViewModel');className(cfg,ns,'DualCultivateGameConfig');
    requireRequestMethod(DUAL_METHOD);validateReviewedMethod(method,klass,DUAL_METHOD);
    samePointer(klass,m.vm_class,'Dual class changed');
    for(const [p,n] of [[panel.add(0xd8),8],[game.add(0x28),8],[game.add(0x44),4],[game.add(0x4c),1],
        [game.add(0x58),8],[panel.add(0xe8),8],[panel.add(0xf0),1],[panel.add(0xf1),1]])requireCoverage(p,n);
    samePointer(panel.add(0xd8).readPointer(),game,'Dual panel game changed');
    samePointer(game.add(0x28).readPointer(),cfg,'Dual configuration changed');
    samePointer(game.add(0x58).readPointer(),m.completed,'Dual completion callback changed');
    samePointer(panel.add(0xe8).readPointer(),m.final_callback,'Dual action callback changed');
    // The normal StartGame caller passes a null external notification callback.
    // Its identity remains pinned above; m_Completed owns the actual settlement.
    requireValue(!ptr(m.completed).isNull() && game.add(0x44).readS32()===1 &&
        boolAt(game.add(0x4c)) && !boolAt(panel.add(0xf0)) && !boolAt(panel.add(0xf1)), 'Dual is not active or already settling');
    requireValue(Number.isInteger(m.npc_id) && m.npc_id>0 && Number.isInteger(m.config_id) && m.config_id>0 &&
        panel.add(0xf4).readS32()===m.npc_id && panel.add(0xf8).readS32()===m.config_id &&
        game.add(0x30).readS32()===m.npc_id && game.add(0x34).readS32()===m.config_id,'Dual NPC or configuration identity changed');
    const remaining=game.add(0x38).readFloat();
    requireValue(Number.isFinite(remaining) && remaining>0 && remaining<=m.time_limit &&
        cfg.add(0x10).readS32()===m.time_limit && cfg.add(0x28).readS32()===m.required_resonance,'Dual time expired or config changed');
    const collection=game.add(0x68).readPointer();samePointer(collection,m.slots,'Dual slot collection changed');
    className(collection,'Loxodon.Framework.Observables','ObservableList`1');
    const list=collection.add(0x38).readPointer();className(list,'System.Collections.Generic','List`1');
    const array=list.add(0x10).readPointer(),capacity=array.add(24).readU64().toNumber();
    requireValue(list.add(0x18).readS32()===3 && capacity>=3 && capacity<=6 && Array.isArray(m.slot_objects) && m.slot_objects.length===3,'Dual slots incomplete');
    const unique=new Set();
    for(let i=0;i<3;i++) {
        const slot=array.add(32+i*8).readPointer();requireCoverage(array.add(32+i*8),8);
        samePointer(slot,m.slot_objects[i],'Dual slot changed');className(slot,ns,'DualCultivateSlotViewModel');
        samePointer(slot.add(0x28).readPointer(),game,'Dual slot owner changed');
        requireValue(!unique.has(slot.toString()),'Duplicate dual slot');unique.add(slot.toString());
    }
    for(const [rva,code] of [[0xacb6d0,'40565741574883ec50803d94bca70700'],[0xacbe20,'4053574883ec7880b9f000000000488b'],[0xacc100,'40535556574883ec68803d6ab2a70700']])
        validateCodePair(rva,code,'Dual settlement code differs');
    const win=Memory.alloc(1);win.writeU8(1);
    return {target:game,values:[win]};
}
function completeDualCultivation(result) {
    const m=request.minigame,panel=ptr(m.panel),game=ptr(m.vm);
    requireValue(result.isNull(),'Dual void method returned a value');
    samePointer(panel.add(0xd8).readPointer(),game,'Dual game replaced during completion');
    requireValue(game.add(0x44).readS32()===2 && boolAt(panel.add(0xf0)) && boolAt(panel.add(0xf2)),
        'Dual native success settlement not confirmed; do not repeat');
    finish('completed',{called:true,native_won:true,settlement_started:true,npc_id:m.npc_id,config_id:m.config_id,
        round_key:m.round_key,thread_id:Process.getCurrentThreadId()});
}
function jadeFeatures(m, proof, requireSeen) {
    const expected=m.features;
    requireValue(Array.isArray(expected) && expected.length<=128,'Invalid jade features');
    let cursor=0;
    for(const [kind,offset,name,seenOffset] of [['Blooms',0x98,'GambleStoneBloomInstance',0x1c],['Cracks',0xa0,'GambleStoneCrackInstance',0x2c]]) {
        const list=ptr(m.stone).add(offset).readPointer();className(list,'System.Collections.Generic','List`1');
        const count=list.add(0x18).readS32(),array=list.add(0x10).readPointer(),capacity=array.add(24).readU64().toNumber();
        requireValue(count>=0 && count<=64 && capacity>=count && capacity<=128,'Jade features list invalid');
        if(proof)for(const [p,n] of [[ptr(m.stone).add(offset),8],[list.add(0x18),4],[list.add(0x10),8]])requireCoverage(p,n);
        for(let i=0;i<count;i++) {
            const feature=array.add(32+i*8).readPointer(),e=expected[cursor++];
            requireValue(e && e.kind===kind,'Jade feature set differs');samePointer(feature,e.address,'Jade feature changed');
            className(feature,'Game.UI.UPFLogic.GambleStone',name);
            samePointer(feature.add(0x10).readPointer(),e.config,'Natural jade feature config changed');
            samePointer(feature.add(seenOffset),e.seen,'Jade seen field differs');
            if(proof){requireCoverage(array.add(32+i*8),8);requireCoverage(feature.add(0x10),8);requireCoverage(feature.add(seenOffset),1);}
            if(requireSeen)requireValue(boolAt(feature.add(seenOffset)),'Jade feature not revealed');
        }
    }
    requireValue(cursor===expected.length,'Extra jade feature descriptors');
}
function prepareJade(method) {
    const m=request.minigame,ns='Game.UI.UPFLogic.GambleStone';
    const panel=dualJadePanel(m,ns,'UPFGambleStonePanel'),vm=ptr(m.vm),stone=ptr(m.stone);
    const klass=className(vm,ns,'UPFGambleStonePanelViewModel');className(stone,ns,'GambleStoneInstance');
    requireRequestMethod(JADE_METHOD);validateReviewedMethod(method,klass,JADE_METHOD);
    samePointer(klass,m.vm_class,'Jade VM class changed');
    samePointer(panel.add(0xc8).readPointer(),vm,'Jade panel selection model changed');
    samePointer(vm.add(0x28).readPointer(),stone,'Selected jade stone changed');
    samePointer(stone.add(0x58).readPointer(),m.source,'Jade source inventory object changed');
    samePointer(stone.add(0x60).readPointer(),m.record,'Jade record changed');
    className(m.source,'Game.Model.Components','GambleStoneBagItem');className(m.record,'Game.Model.Player.Components','GambleStoneSaveRecord');
    const record=ptr(m.record),source=ptr(m.source);
    samePointer(m.record_ratio_address,record.add(0x80),'Jade record ratio field differs');
    samePointer(m.record_value_address,record.add(0x88),'Jade record value field differs');
    requireValue(typeof m.instance_id==='string' && /^[1-9][0-9]{0,18}$/.test(m.instance_id) &&
        source.add(0x38).readU64().toString()===m.instance_id && record.add(0x10).readU64().toString()===m.instance_id &&
        record.add(0x18).readS32()===m.item_id && record.add(0x1c).readS32()===m.seed &&
        !boolAt(record.add(0x20)) && !boolAt(record.add(0xa0)),'Jade record identity, generation or exchange differs');
    requireValue(!boolAt(stone.add(0x49)) && boolAt(stone.add(0x68)) && stone.add(0x18).readS32()===m.item_id &&
        stone.add(0x28).readS32()===m.seed && Number.isFinite(m.ratio_before) && m.ratio_before>=0 && m.ratio_before<1 &&
        floatBits(stone.add(0x44).readFloat())===floatBits(m.ratio_before),'Jade exchanged, unfinished loading or already revealed');
    for(const [p,n] of [[panel.add(0xc8),8],[vm.add(0x28),8],[stone.add(0x58),8],[stone.add(0x60),8],
        [stone.add(0x44),4],[stone.add(0x49),1],[stone.add(0x68),1],[ptr(m.record_ratio_address),4],[ptr(m.record_value_address),4]])requireCoverage(p,n);
    const wanted=['m_CanScratch','m_ExchangeChoiceVisible','m_ExchangeResultVisible','m_ScratchSessionActive','m_ScratchDirty','m_HasPendingScratchSettlement'];
    // The reviewed current VM removed three rendering lists before these flags.
    // Keep each method group's exact layout; never accept caller-chosen offsets.
    const offsets=currentNativeProfile
        ? [0xf8,0xfa,0xfb,0x121,0x123,0x124]
        : [0x110,0x112,0x113,0x139,0x13b,0x13c];
    requireValue(Array.isArray(m.flags) && m.flags.length===wanted.length,'Jade activity proof missing');
    wanted.forEach((label,i)=>{
        const f=m.flags[i];requireValue(f.label===label && f.expected===(i===0),'Jade activity proof differs');
        samePointer(f.address,vm.add(offsets[i]),'Jade activity field differs');
        requireCoverage(f.address,1);requireValue(boolAt(f.address)===f.expected,'Jade is busy or exchange is open');
    });
    jadeFeatures(m,true,false);
    for(const [rva,code] of [[0xa9c140,'48895c2408574881ecc0000000803d18'],[0xa9cc30,'488bc44c8948204c8940184889480853'],[0xa9ebf0,'488bc448895810488970204889480857']])
        validateCodePair(rva,code,'Jade reveal/record code differs');
    return {target:vm,values:[]};
}
function completeJade(result) {
    const m=request.minigame,stone=ptr(m.stone);
    requireValue(result.isNull(),'Jade void method returned value');
    samePointer(ptr(m.vm).add(0x28).readPointer(),stone,'Jade selected stone changed while revealing');
    samePointer(stone.add(0x58).readPointer(),m.source,'Jade source changed while revealing');
    samePointer(stone.add(0x60).readPointer(),m.record,'Jade record changed while revealing');
    requireValue(!boolAt(stone.add(0x49)) && stone.add(0x44).readFloat()===1 &&
        ptr(m.record_ratio_address).readFloat()===1,'Jade not fully revealed or record differs');
    jadeFeatures(m,false,true);
    const value=stone.add(0x50).readS32();
    requireValue(value>=1 && ptr(m.record_value_address).readS32()===value &&
        stone.add(0x78).readS32()===stone.add(0x88).readS32() && stone.add(0x88).readS32()>0,
        'Jade native value/mask/record did not agree; do not repeat');
    finish('completed',{called:true,fully_revealed:true,record_verified:true,current_value:value,
        instance_id:m.instance_id,round_key:m.round_key,thread_id:Process.getCurrentThreadId()});
}


/* Insert these declarations before execute(); whitelist both operations and add
 * if (request.operation === 'alchemy_perfect' || request.operation === 'alchemy_talent_set') {
 *   executeAlchemy(method); return;
 * }
 * after validateAnchors() inside execute()'s existing try/catch. The outer catch
 * must keep state==='running' as unknown/called:true. */
const ALCHEMY_QTE_METHOD = nativeSpec({name:'FinishQte', token:0x0600f550, rva:0x1d108b0,
    argc:0, returns:1, params:[], prefix:'4889742420574883ec30803d1f008406'});
const ALCHEMY_TALENT_METHOD = nativeSpec({name:'SetTalentRank', token:0x06014e77, rva:0xe8ebd0,
    argc:2, returns:1, params:[8,8], prefix:'48896c2418564883ec20803d4cac6b07'});
const ALCHEMY_RANK_LEVELS = {
    1000001:[1,5,10,16,21], 1000002:[3,8,14,20,25], 1000003:[1,6,13,19,23],
    1000004:[3,8,14,20,25], 1000005:[4,10,15,20,25],
    1000006:[2,6,11,18,23], 1000007:[4,10,15,20,25]
};
function alchemyRegistry(m, panel) {
    requireValue(m && typeof m.round_key==='string' && /^[0-9a-f]{64}$/.test(m.round_key), 'Missing alchemy identity');
    requireValue(Array.isArray(m.registry_links) && m.registry_links.length>=8, 'Missing alchemy registry proof');
    reviewedRegistryRoot(m);
    for (const link of m.registry_links) {
        requireCoverage(link.address, 8); samePointer(ptr(link.address).readPointer(),link.expected,'Alchemy registry link changed');
    }
    const r=m.registry;
    requireValue(r && Number.isInteger(r.count) && r.count>0 && r.count<=512, 'Alchemy registry invalid');
    for (const p of [m.manager,r.dictionary,r.entries]) requireValue(m.registry_links.some(x=>ptr(x.expected).equals(ptr(p))), 'Alchemy registry link omitted');
    className(m.manager,'Game','UIManager'); requireCoverage(ptr(m.manager).add(0x18),1);
    requireValue(!boolAt(ptr(m.manager).add(0x18)), 'UI manager shutting down');
    requireCoverage(r.count_address,4); requireCoverage(r.version_address,4);
    requireValue(ptr(r.count_address).readS32()===r.count,'Alchemy registry count changed');
    const array=ptr(r.entries),cap=array.add(24).readU64().toNumber();
    requireValue(cap>=r.count && cap<=2048,'Alchemy registry capacity invalid');
    const members=[];
    for(let i=0;i<r.count;i++) {
        const e=array.add(32+i*24); requireCoverage(e,24);
        if(e.readS32()>=0) members.push(e.add(16).readPointer());
    }
    if(panel) requireValue(members.filter(p=>p.equals(panel)).length===1,'Alchemy panel is not uniquely registered');
    return members;
}
function alchemyTalentEntries(dictionary, proof) {
    const result=new Map();
    if(dictionary.isNull()) return result;
    className(dictionary,'System.Collections.Generic','Dictionary`2');
    const array=dictionary.add(24).readPointer(),count=dictionary.add(32).readS32(),free=dictionary.add(40).readS32();
    requireValue(free>=0 && free<=count && count<=64,'Alchemy talent dictionary count invalid');
    if(proof) for(const [p,n] of [[dictionary,8],[dictionary.add(24),8],[dictionary.add(32),4],[dictionary.add(40),4],[dictionary.add(44),4]]) requireCoverage(p,n);
    if(array.isNull()) { requireValue(count===0,'Missing alchemy talent entries'); return result; }
    const cap=array.add(24).readU64().toNumber(); requireValue(cap>=count && cap<=128,'Alchemy talent capacity invalid');
    if(proof) requireCoverage(array.add(24),8);
    for(let i=0;i<count;i++) {
        const e=array.add(32+16*i),h=e.readS32(),next=e.add(4).readS32();
        if(proof) requireCoverage(e,16);
        requireValue(next>=-1 && next<Math.max(1,count),'Alchemy talent chain invalid');
        if(h<0) continue;
        const id=e.add(8).readS32(),v=e.add(12).readS32();
        requireValue(Object.hasOwn(ALCHEMY_RANK_LEVELS,id) && v>=1 && v<=5 && !result.has(id),'Alchemy talent entry invalid');
        result.set(id,v);
    }
    requireValue(result.size===count-free,'Alchemy talent live count invalid'); return result;
}
function executeAlchemy(method) {
    const m=request.minigame, isQte=request.operation==='alchemy_perfect';
    const spec=isQte?ALCHEMY_QTE_METHOD:ALCHEMY_TALENT_METHOD;
    requireRequestMethod(spec);
    let target, values=[], beforeRanks=null;
    const qteOffset = offset => currentNativeProfile && offset >= 0x108 ? offset + 8 : offset;
    if(isQte) {
        const p=ptr(m.panel),c=ptr(m.context); alchemyRegistry(m,p);
        const klass=className(p,'Game.UI.UPFLogic.RefiningPills','UPFRefiningPillsQtePanel');
        samePointer(klass,m.panel_class,'Alchemy panel class changed'); validateReviewedMethod(method,klass,spec);
        className(c,'Game','CondenseContext'); className(m.recipe,'Game','RefiningPillsRecipeCardModel');
        for(const [address,n] of [[p,8],[p.add(16),8],[p.add(0x42),1],[p.add(0x43),1],[p.add(0x58),1],
            [p.add(0x92),1],[p.add(0x93),1],[p.add(0xa8),4],[p.add(0xd0),8],[p.add(qteOffset(0x148)),8],[p.add(qteOffset(0x150)),8],
            [p.add(0x106),1],[p.add(qteOffset(0x158)),1],[p.add(qteOffset(0x159)),1],[p.add(qteOffset(0x15a)),1],[p.add(qteOffset(0x208)),1],
            [p.add(qteOffset(0x118)),4],[p.add(qteOffset(0x11c)),4],[p.add(qteOffset(0x120)),4],[c,8],[c.add(0x18),8],[c.add(0x50),8],
            [c.add(0x60),1],[c.add(0x68),8],[c.add(0x70),1],[ptr(m.maximum_address),4]]) requireCoverage(address,n);
        requireValue(!p.add(16).readPointer().isNull() && boolAt(p.add(0x42)) && boolAt(p.add(0x43)) &&
            !boolAt(p.add(0x58)) && boolAt(p.add(0x92)) && !boolAt(p.add(0x93)), 'Alchemy panel is not actionable');
        requireValue(p.add(0xa8).readS32()===m.handle && boolAt(p.add(0x106)), 'Alchemy round no longer running');
        if(currentNativeProfile) {
            requireCoverage(p.add(0x10c),1);
            requireValue(!boolAt(p.add(0x10c)), 'Alchemy is waiting for normal spirit ignition');
        }
        for(const off of [0x158,0x159,0x15a,0x208]) requireValue(!boolAt(p.add(qteOffset(off))), 'Alchemy round transitioning');
        samePointer(p.add(qteOffset(0x148)).readPointer(),c,'Alchemy context changed');
        samePointer(c.add(0x18).readPointer(),m.recipe,'Alchemy recipe changed');
        samePointer(c.add(0x68).readPointer(),m.operation_id,'Alchemy operation changed');
        const operation=ptr(m.operation_id),n=operation.add(16).readS32();
        requireValue(n>0 && n<=80,'Alchemy operation missing'); requireCoverage(operation,8);requireCoverage(operation.add(16),4);requireCoverage(operation.add(20),n*2);
        samePointer(p.add(qteOffset(0x150)).readPointer(),m.callback,'Alchemy callback changed');requireValue(!ptr(m.callback).isNull(),'Missing alchemy callback');
        requireValue(!boolAt(c.add(0x70)) && (c.add(0x50).readPointer().isNull() || boolAt(c.add(0x60))), 'Alchemy costs not committed or refunded');
        samePointer(p.add(0xd0).readPointer(),m.stages,'Alchemy stages changed');
        const stages=ptr(m.stages),count=stages.add(0x18).readS32(),stage=p.add(0xd8).readS32();
        requireCoverage(stages.add(0x18),4); requireValue(count===m.stage_count && count>0 && count<=32 && stage>=0 && stage<count,'Alchemy stage invalid');
        const max=ptr(m.maximum_address).readS32(),progress=p.add(0xe8).readFloat(),score=p.add(qteOffset(0x108)).readFloat();
        const fan=p.add(qteOffset(0x118)).readFloat(),xian=p.add(qteOffset(0x11c)).readFloat(),shen=p.add(qteOffset(0x120)).readFloat();
        const remaining=p.add(qteOffset(0x10c)).readFloat(),stageRemaining=p.add(0xe4).readFloat();
        requireValue(max===1000 && m.maximum===max && [progress,score,fan,xian,shen,remaining,stageRemaining].every(Number.isFinite) &&
            progress>=0 && progress<=max && score>=0 && fan>=0 && fan<=xian && xian<=shen && shen>0 && shen<=max &&
            remaining>0 && remaining<=3600 && stageRemaining>0 && stageRemaining<=remaining+1,'Alchemy values outside reviewed bounds');
        target=p;
    } else {
        const members=alchemyRegistry(m,null),player=ptr(m.player),model=ptr(m.model),dictionary=ptr(m.dictionary);
        className(player,'Game.Model','PlayerModel');
        const klass=className(model,'Game.Model.Player.Components','RefiningPillsModel');
        samePointer(klass,m.model_class,'Alchemy talent model class changed');validateReviewedMethod(method,klass,spec);
        for(const [p,n] of [[player,8],[player.add(0x60),8],[model,8],[model.add(0x18),4],[model.add(0x28),8]]) requireCoverage(p,n);
        samePointer(player.add(0x60).readPointer(),model,'Alchemy player component changed');
        samePointer(model.add(0x28).readPointer(),dictionary,'Alchemy talent dictionary changed');
        requireValue(Array.isArray(m.observed_panels),'Missing alchemy hidden panels proof');
        for(const obj of members) {
            if(obj.isNull()) continue;
            const k=obj.readPointer();
            const ns=k.add(24).readPointer().readUtf8String(),name=k.add(16).readPointer().readUtf8String();
            if(ns==='Game.UI.UPFLogic.RefiningPills' && ['UPFRefiningPillsTalentPanel','UPFRefiningPillsExplorePanel','UPFRefiningPillsQtePanel'].includes(name)) {
                requireValue(m.observed_panels.some(x=>ptr(x.panel).equals(obj) && x.name===name && x.showing===false),'Alchemy panel proof omitted');
                requireCoverage(obj.add(0x42),1); requireValue(!boolAt(obj.add(0x42)),'Close alchemy screens before editing talents');
            }
        }
        const level=model.add(0x18).readS32();
        requireValue(Number.isInteger(m.talent_id) && Object.hasOwn(ALCHEMY_RANK_LEVELS,m.talent_id) &&
            Number.isInteger(m.rank) && level===m.level && level>=1 && level<=25,'Alchemy talent input invalid');
        const cap=ALCHEMY_RANK_LEVELS[m.talent_id].filter(v=>v<=level).length;
        requireValue(m.maximum===cap && m.rank>=0 && m.rank<=cap,'Alchemy talent level requirement not met');
        beforeRanks=alchemyTalentEntries(dictionary,true);
        requireValue((beforeRanks.get(m.talent_id)||0)===m.before && m.rank!==m.before,'Alchemy talent rank changed or unchanged input');
        const id=Memory.alloc(4),rank=Memory.alloc(4);id.writeS32(m.talent_id);rank.writeS32(m.rank);values=[id,rank];target=model;
    }
    validateAnchors();
    const args=values.length?Memory.alloc(values.length*Process.pointerSize):ptr(0);
    values.forEach((v,i)=>args.add(i*Process.pointerSize).writePointer(v));
    const exception=Memory.alloc(Process.pointerSize);exception.writePointer(ptr(0));
    if(Date.now()>request.deadline) {finish('cancelled',{called:false,reason:'炼丹请求过期，未修改。'});return;}
    state='running'; // BEFORE the first scalar store as well as the game method.
    if(isQte) target.add(0xe8).writeFloat(m.maximum);
    invoke(method,target,args,exception);
    requireValue(exception.readPointer().isNull(),'Alchemy native exception after dispatch');
    if(isQte) {
        samePointer(target.add(qteOffset(0x148)).readPointer(),m.context,'Alchemy context changed during finish');
        const progress=target.add(0xe8).readFloat(),running=boolAt(target.add(0x106));
        const emitted=boolAt(target.add(qteOffset(0x159))),deferred=boolAt(target.add(qteOffset(0x158)));
        requireValue(progress===m.maximum && !running && (emitted || deferred),'Alchemy result not confirmed');
        finish('completed',{called:true,round_key:m.round_key,quality:3,progress:progress,running:running,
            result_emitted:emitted,result_deferred:deferred,thread_id:Process.getCurrentThreadId()});
    } else {
        samePointer(ptr(m.player).add(0x60).readPointer(),target,'Alchemy owner changed during set');
        const dictionary=target.add(0x28).readPointer();
        if(!ptr(m.dictionary).isNull()) samePointer(dictionary,m.dictionary,'Alchemy dictionary replaced during set');
        const after=alchemyTalentEntries(dictionary,false),expected=new Map(beforeRanks);
        if(m.rank===0) expected.delete(m.talent_id); else expected.set(m.talent_id,m.rank);
        requireValue(after.size===expected.size && [...expected].every(([k,v])=>after.get(k)===v),'Alchemy talent readback differs');
        finish('completed',{called:true,round_key:m.round_key,talent_id:m.talent_id,rank:m.rank,thread_id:Process.getCurrentThreadId()});
    }
}


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


// The three reviewed currency IDs can use a larger quantity only after the
// actual current catalogue, balance and native stack limit have been checked.
// Nothing here loops over quantity or creates inventory objects itself.
function currencyClass(klass, namespace, name) {
    requireValue(!klass.isNull() && klass.add(16).readPointer().readUtf8String() === name &&
        klass.add(24).readPointer().readUtf8String() === namespace, 'Currency metadata class differs');
    return klass;
}
function currencyField(object, klass, name, token, kind, offset, size, proof=true, isStatic=false) {
    const count=klass.add(0x124).readU16(), fields=klass.add(0x80).readPointer();
    requireValue(count>0 && count<=512 && !fields.isNull(), 'Currency metadata fields invalid');
    let matches=0;
    for(let i=0;i<count;i++) {
        const field=fields.add(i*32);
        if(field.readPointer().readUtf8String()!==name) continue;
        const type=field.add(8).readPointer();
        samePointer(field.add(16).readPointer(),klass,'Currency field owner differs');
        requireValue(field.add(28).readU32()===reviewedFieldToken(klass,token,name) && field.add(24).readS32()===offset &&
            type.add(10).readU8()===kind && (type.add(11).readU8()&0x7f)===0 &&
            (type.add(8).readU16()&0x50)===(isStatic?0x10:0), 'Currency field type or layout differs');
        matches++;
    }
    requireValue(matches===1,'Currency field missing or ambiguous');
    const address=ptr(object).add(offset);
    if(proof) requireCoverage(address,size);
    return address;
}
function currencyBalance(bag, proof) {
    const bk=className(bag,'Game.Model.Components','BagModel');
    if(proof) {requireCoverage(bag,8);requireCoverage(bag.add(16),8);}
    const list=currencyField(bag,bk,'<Items>k__BackingField',0x0400b03b,0x15,24,8,proof).readPointer();
    className(list,'System.Collections.Generic','List`1');
    const array=list.add(16).readPointer(), count=list.add(24).readS32();
    const ak=className(array,'Game.Model.Components','BagItemBase[]');
    const base=currencyClass(ak.add(0x40).readPointer(),'Game.Model.Components','BagItemBase');
    const capacity=array.add(24).readU64().toNumber();
    requireValue(count>=0 && count<=4000 && capacity>=count && capacity<=8192,'Currency inventory bounds invalid');
    if(proof) for(const [a,n]of [[list,8],[list.add(16),8],[list.add(24),4],[list.add(28),4],
        [array,8],[array.add(24),8],[ak.add(0x40),8]]) requireCoverage(a,n);
    // Verify inherited scalar layouts once, independently of request markers.
    currencyField(array,base,'ItemId',0x0400affa,0x11,16,4,false);
    currencyField(array,base,'Count',0x0400affb,8,20,4,false);
    currencyField(array,base,'IsEquipped',0x0400affd,2,25,1,false);
    let total=0, matches=0;
    const seen=new Set();
    for(let i=0;i<count;i++) {
        const slot=array.add(32+8*i);
        if(proof) requireCoverage(slot,8);
        const item=slot.readPointer(); if(item.isNull()) continue;
        requireValue(!seen.has(item.toString()),'Duplicate currency inventory object');seen.add(item.toString());
        if(proof) {requireCoverage(item,8);requireCoverage(item.add(16),4);}
        if(item.add(16).readS32()!==request.item_id) continue;
        const k=className(item,'Game.Model.Components','BagItem');
        samePointer(k.add(0x58).readPointer(),base,'Currency item base class differs');
        if(proof) {requireCoverage(item.add(20),4);requireCoverage(item.add(25),1);requireCoverage(k.add(0x58),8);}
        requireValue(!boolAt(item.add(25)),'Currency item is equipped');
        const amount=item.add(20).readS32();
        requireValue(amount>=0 && amount<=999999999,'Currency balance invalid');
        total+=amount;matches++;
        requireValue(matches<=1 && total<=999999999,'Split or duplicate currency stacks are unsupported');
    }
    return {total,matches,count};
}
function prepareCurrencyAdd(bag, method) {
    const c=request.currency_proof;
    requireValue(c && Number.isInteger(c.row_index) && c.row_index>=0 && Number.isInteger(c.before) &&
        c.before>=0 && c.before<=999999999 && Number.isInteger(c.maximum) && c.maximum>0 && c.maximum<=999999999,
        'Missing reviewed currency configuration proof');
    const tables=ptr(c.tables), tk=currencyClass(ptr(c.tables_class),'LubanDatas','Tables');
    requireCoverage(tk.add(0xb8),8);
    const sf=tk.add(0xb8).readPointer();requireValue(!sf.isNull(),'Tables static data missing');
    samePointer(currencyField(sf,tk,'Current',0x04000800,0x12,0,8,true,true).readPointer(),tables,'Current configuration root changed');
    samePointer(className(tables,'LubanDatas','Tables'),tk,'Tables class changed');requireCoverage(tables,8);
    const table=currencyField(tables,tk,'<TbItem>k__BackingField',0x04000848,0x12,0x248,8).readPointer();
    const tbc=className(table,'LubanDatas','TbItem');requireCoverage(table,8);
    const overrides=currencyField(table,tbc,'_overrides',0x04000adf,0x15,32,8).readPointer();
    if(!overrides.isNull()) {
        className(overrides,'System.Collections.Generic','Dictionary`2');
        for(const [a,n]of [[overrides,8],[overrides.add(32),4],[overrides.add(40),4],[overrides.add(44),4]])requireCoverage(a,n);
        const count=overrides.add(32).readS32(), free=overrides.add(40).readS32();
        requireValue(count>=0 && count<=10000 && count===free,'Runtime item overrides are unsupported');
    }
    const list=currencyField(table,tbc,'_dataList',0x04000ade,0x15,24,8).readPointer();
    const lc=className(list,'Emei','NotifiableList`1');
    currencyClass(lc.add(0x58).readPointer(),'System.Collections.Generic','List`1');
    const array=list.add(16).readPointer(), count=list.add(24).readS32(), capacity=array.add(24).readU64().toNumber();
    requireValue(count>0 && count<=10000 && capacity>=count && capacity<=20000 && c.row_index<count,
        'Currency configuration list bounds differ');
    for(const [a,n]of [[list,8],[lc.add(0x58),8],[list.add(16),8],[list.add(24),4],[list.add(28),4],
        [array,8],[array.add(24),8],[array.add(32+8*c.row_index),8]]) requireCoverage(a,n);
    const config=ptr(c.config_object);
    samePointer(array.add(32+8*c.row_index).readPointer(),config,'Currency is not the current catalogue row');
    const ic=className(config,'LubanDatas.data','Item');requireCoverage(config,8);
    const id=currencyField(config,ic,'<id>k__BackingField',0x0400158d,0x11,16,4).readS32();
    const type=currencyField(config,ic,'<itemType>k__BackingField',0x04001594,0x11,72,4).readS32();
    const cap=currencyField(config,ic,'<maxCntPerGrid>k__BackingField',0x0400159d,8,100,4).readS32();
    const auto=currencyField(config,ic,'<autoUse>k__BackingField',0x0400159a,0x15,84,2);
    const hasAuto=boolAt(auto), autoUse=boolAt(auto.add(1));
    requireValue(id===request.item_id && LARGE_CURRENCY_IDS.has(id) && type===5 && (!hasAuto || !autoUse) &&
        cap>0 && c.maximum===Math.min(cap,999999999), 'Actual item is not a reviewed currency or has an invalid limit');
    const before=currencyBalance(bag,true);
    requireValue(before.total===c.before && before.total+request.quantity<=c.maximum &&
        before.count+(before.matches===0?1:0)<=4000, 'Currency balance, maximum or required slot changed');
    const bk=className(bag,'Game.Model.Components','BagModel');
    requireRequestMethod(nativeSpec({token:0x06015191,rva:0xe9bdd0,argc:5}));
    validateReviewedMethod(method,bk,nativeSpec({name:'AddItem',token:0x06015191,rva:0xe9bdd0,argc:5,returns:0x12,
        params:[0x11,8,0x11,0x15,0x12],prefix:'44894c24204489442418895424104889'}));
    const stack=ptr(c.stack_method), stackType=stack.add(0x28).readPointer();
    const stackSpec=nativeSpec({name:'ResolveItemStackMax',token:0x0601519f,rva:0xea0fd0,prefix:'48895c24105556574883ec50803d3989'}),stackPrefix=stackSpec.prefix;
    samePointer(stack.readPointer(),image.base.add(stackSpec.rva),'Stack getter code differs');
    samePointer(stack.add(0x20).readPointer(),bk,'Stack getter class differs');
    requireValue(methodToken(stack)===stackSpec.token && paramCount(stack)===2 &&
        stack.add(0x18).readPointer().readUtf8String()==='ResolveItemStackMax' &&
        (stack.add(0x4c).readU16()&0x10)!==0 && stackType.add(10).readU8()===8 &&
        (stackType.add(11).readU8()&0x7f)===0 &&
        hexAt(image.base.add(stackSpec.rva),stackPrefix.length/2)===stackPrefix,'Stack getter signature differs');
    for(const [i,kind] of [[0,0x12],[1,0x11]]) {
        const t=methodParam(stack,i);
        requireValue(t.add(10).readU8()===kind && (t.add(11).readU8()&0x7f)===0,'Stack getter argument differs');
    }
    samePointer(classFromType(methodParam(stack,0)),ic,'Stack getter config parameter differs');
    currencyClass(classFromType(methodParam(stack,1)),'LubanDatas','TbItemId');
    const idArg=Memory.alloc(4);idArg.writeS32(id);
    const args=Memory.alloc(16);args.writePointer(config);args.add(8).writePointer(idArg);
    const error=Memory.alloc(8);error.writePointer(ptr(0));
    const boxed=invoke(stack,ptr(0),args,error);
    requireValue(error.readPointer().isNull() && !boxed.isNull(),'Could not read actual currency stack limit');
    className(boxed,'System','Int32');
    requireValue(boxed.add(16).readS32()===cap,'Actual currency stack limit differs from the reviewed configuration');
    // Getter calls never mark this request as dispatched. All proofs are
    // rechecked before the existing single AddItem mutation point.
    validateAnchors();
    return {config,before:before.total,maximum:c.maximum};
}

/* BEGIN interaction_bridge.js */
/* Merged into acquisition_bridge.js. These declarations never attach a second
 * agent: execute() dispatches them on the existing A1Main.Update hook. */
const INTERACTION_METHODS = {
    requirements: nativeSpec({name:'MeetsSpecialEntryRequirements',token:0x06008258,rva:0x1552590,argc:3,
        returns:2,params:[0x12,0x12,2],static:true,prefix:'4053565741564881eca8000000450fb6'}),
    activate: nativeSpec({name:'SetSpecialState',token:0x06008249,rva:0x1555670,argc:3,
        returns:2,params:[0x12,8,2],static:true,prefix:'48895c24084889742410574883ec2041'}),
    force: nativeSpec({name:'ForceSetSpecialState',token:0x0600823d,rva:0x1550ef0,argc:2,
        returns:2,params:[0x11,0x11],static:false,prefix:'48895c2410574883ec30803dd2b7ff06'}),
    persuade: nativeSpec({name:'OnPersuadeResult',token:0x060143ff,rva:0xe1bef0,argc:2,
        returns:1,params:[2,0x11],static:false,prefix:'40535556574883ec28803d9ad4720700'}),
    ended: nativeSpec({name:'OnPersuadeEnded',token:0x0600aec9,rva:0x18df690,argc:2,returns:1,params:[2,0x0e],static:false,prefix:'4889742420574881ecc0000000803da5'}),
    win: nativeSpec({name:'<RunAsync>b__3',token:0x0600ba4c,rva:0x19c90c0,argc:0,returns:1,params:[],static:false,prefix:'48895c24084889742410574883ec2080'}),
    lose: nativeSpec({name:'<RunAsync>b__4',token:0x0600ba4d,rva:0x19c9150,argc:0,returns:1,params:[],static:false,prefix:'48895c24084889742410574883ec2080'}),
    close: nativeSpec({name:'<RunAsync>b__5',token:0x0600ba4e,rva:0x19c8e20,argc:0,returns:1,params:[],static:false,prefix:'4883ec2880791000751a66c741100100'}),
    alive: nativeSpec({name:'<RunAsync>b__6',token:0x0600ba4f,rva:0x19c91e0,argc:0,returns:2,params:[],static:false,prefix:'40534883ec20803d1557b80600488bd9'})
};
function interactionInteger(value,minimum=0,maximum=2147483647) {
    requireValue(Number.isInteger(value)&&value>=minimum&&value<=maximum,'Invalid interaction integer');
    return value;
}
function interactionField(object,klass,name,token,kind,offset,size,proof=true) {
    const fields=klass.add(0x80).readPointer(),count=klass.add(0x124).readU16(),found=[];
    requireValue(!fields.isNull()&&count>0&&count<=512,'Interaction field table invalid');
    for(let i=0;i<count;i++) {
        const field=fields.add(32*i);
        if(field.readPointer().readUtf8String()!==name) continue;
        const type=field.add(8).readPointer();
        samePointer(field.add(16).readPointer(),klass,'Interaction field owner differs');
        requireValue(field.add(28).readU32()===reviewedFieldToken(klass,token,name)&&field.add(24).readS32()===offset&&
            !type.isNull()&&type.add(10).readU8()===kind&&(type.add(11).readU8()&0x7f)===0&&
            (type.add(8).readU16()&0x50)===0&&offset>=16&&offset+size<=klass.add(0xf8).readU32(),
            'Interaction field layout differs: '+klass.add(24).readPointer().readUtf8String()+'.'+
            klass.add(16).readPointer().readUtf8String()+'.'+name);
        found.push(ptr(object).add(offset));
    }
    requireValue(found.length===1,'Interaction field missing or ambiguous');
    if(proof) requireCoverage(found[0],size);
    return found[0];
}
function interactionClass(klass,namespace,name) {
    requireValue(!klass.isNull()&&klass.add(16).readPointer().readUtf8String()===name&&
        klass.add(24).readPointer().readUtf8String()===namespace,'Interaction metadata class differs');
    return klass;
}
function interactionFieldClass(klass,name,namespace,typeName,size) {
    const table=klass.add(0x80).readPointer(),count=klass.add(0x124).readU16();
    requireValue(!table.isNull()&&count>0&&count<=512,'Interaction field metadata missing');
    const matches=[];
    for(let i=0;i<count;i++)if(table.add(i*32).readPointer().readUtf8String()===name)
        matches.push(classFromType(table.add(i*32+8).readPointer()));
    requireValue(matches.length===1,'Interaction value wrapper field ambiguous');
    const c=interactionClass(matches[0],namespace,typeName);
    requireValue(c.add(0xf8).readU32()===size,'Interaction value wrapper size differs');return c;
}
function interactionMethod(address,klass,spec) {
    const method=ptr(address);
    samePointer(method.readPointer(),image.base.add(spec.rva),'Interaction native address differs');
    samePointer(method.add(0x20).readPointer(),klass,'Interaction native owner differs');
    requireValue(methodToken(method)===spec.token&&paramCount(method)===spec.argc&&
        method.add(0x18).readPointer().readUtf8String()===spec.name&&
        Boolean(method.add(0x4c).readU16()&0x10)===spec.static&&
        hexAt(image.base.add(spec.rva),spec.prefix.length/2)===spec.prefix,'Interaction native signature differs');
    function typeKind(type,kind) {
        requireValue(!type.isNull()&&type.add(10).readU8()===kind&&
            (type.add(11).readU8()&0x7f)===0,'Interaction argument or return type differs');
    }
    typeKind(method.add(0x28).readPointer(),spec.returns);
    for(let i=0;i<spec.params.length;i++) typeKind(methodParam(method,i),spec.params[i]);
    return method;
}
function interactionArgumentClass(method,index,namespace,name,size=null) {
    const klass=classFromType(methodParam(method,index));
    requireValue(!klass.isNull()&&klass.add(16).readPointer().readUtf8String()===name&&
        klass.add(24).readPointer().readUtf8String()===namespace&&
        (size===null||klass.add(0xf8).readU32()===size),'Interaction parameter class differs');
}
function interactionInvoke(method,target,values) {
    const args=values.length?Memory.alloc(values.length*8):ptr(0),exception=Memory.alloc(8);
    values.forEach((value,index)=>args.add(index*8).writePointer(value));
    exception.writePointer(ptr(0));
    const result=invoke(method,target,args,exception);
    requireValue(exception.readPointer().isNull(),'Interaction native exception; never retry');
    return result;
}
function interactionBoolean(result) {
    requireValue(!result.isNull(),'Interaction method returned no Boolean');
    className(result,'System','Boolean');
    return boolAt(result.add(16));
}
function interactionScalar(value,boolean=false) {
    const result=Memory.alloc(boolean?1:4);
    if(boolean) result.writeU8(value?1:0); else result.writeS32(interactionInteger(value));
    return result;
}
function interactionLinks(links,proof=true) {
    requireValue(Array.isArray(links)&&links.length>0&&links.length<=20000,'Interaction owner chain missing');
    for(const link of links) {
        if(proof) requireCoverage(link.address,8);
        samePointer(ptr(link.address).readPointer(),link.expected,'Interaction owner chain changed');
    }
}
const usedInteractionRounds=new Set();
function interactionRound(m) {
    requireValue(m&&/^[a-f0-9]{64}$/.test(m.round_key),'Interaction round identity missing');
    requireValue(!usedInteractionRounds.has(m.round_key),'Interaction round was already dispatched; never retry');
}
function interactionDispatch(m) {
    requireValue(Date.now()<=request.deadline,'Interaction request expired before dispatch');
    interactionRound(m);
    // Retained across RPC reset: a fresh token never authorizes the same action.
    usedInteractionRounds.add(m.round_key);
    state='running';
}
function interactionStatistics(address,proof) {
    const dictionary=ptr(address),klass=className(dictionary,'System.Collections.Generic','Dictionary`2');
    for(const [offset,size] of [[0x18,8],[0x20,4],[0x24,4],[0x28,4],[0x2c,4]])
        if(proof) requireCoverage(dictionary.add(offset),size);
    const array=dictionary.add(0x18).readPointer(),count=dictionary.add(0x20).readS32(),
        free=dictionary.add(0x28).readS32(),version=dictionary.add(0x2c).readS32(),
        freeList=dictionary.add(0x24).readS32();
    requireValue(count>=0&&count<=4096&&free>=0&&free<=count&&freeList>=-1&&freeList<Math.max(1,count),
        'Interaction statistics bounds invalid');
    const result={dictionary,array,count,free,version,freeList,capacity:0,items:new Map(),slots:new Map()};
    if(array.isNull()){requireValue(count===0&&free===0,'Interaction statistics missing entries');return result;}
    if(proof) requireCoverage(array.add(24),8);
    result.capacity=array.add(24).readU64().toNumber();
    requireValue(count<=result.capacity&&result.capacity<=8192,'Interaction statistics capacity invalid');
    const ac=className(array,'','Entry[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===32,'Interaction statistics entry size differs');
    // Entry field metadata is independently checked even when the dictionary is empty.
    for(const [name,token,offset] of [['hashCode',0x04001b0d,16],['next',0x04001b0e,20],['key',0x04001b0f,24],['value',0x04001b10,28]])
        interactionField(array.add(16),ec,name,token,name==='key'?0x11:8,offset,4,proof&&count>0);
    const keyClass=interactionFieldClass(ec,'key','LubanDatas','TbNpcInteractGameEntrySubid',20);
    interactionField(ptr(0),keyClass,'<Value>k__BackingField',0x04000bea,8,16,4,false);
    let live=0,dead=0;
    for(let i=0;i<count;i++) {
        const p=array.add(32+i*16);if(proof)requireCoverage(p,16);
        const hash=p.readS32(),next=p.add(4).readS32();
        requireValue(next>=-1&&next<Math.max(1,count),'Interaction statistics chain invalid');
        if(hash<0){dead++;continue;}
        const key=interactionInteger(p.add(8).readS32(),1),value=interactionInteger(p.add(12).readS32());
        requireValue(!result.items.has(key),'Interaction statistics duplicate key');
        result.items.set(key,value);result.slots.set(key,{index:i,address:p});live++;
    }
    requireValue(live===count-free&&dead===free,'Interaction statistics free count differs');
    return result;
}
function interactionExpectedStatistics(actual,expected) {
    requireValue(Array.isArray(expected)&&actual.items.size===expected.length,'Interaction statistics changed');
    const keys=new Set();
    for(const item of expected) {
        interactionInteger(item.key,1);interactionInteger(item.value);
        requireValue(!keys.has(item.key)&&actual.items.get(item.key)===item.value,'Interaction statistics changed');
        keys.add(item.key);
    }
}
function interactionStableAnchors(anchors) {
    requireValue(Array.isArray(anchors)&&anchors.length>0&&anchors.length<=20000,'Interaction post-call proof missing');
    for(const a of anchors) {
        requireValue(Number.isInteger(a.size)&&a.size>0&&a.size<=4096&&typeof a.expected_hex==='string'&&
            a.expected_hex.length===a.size*2,'Interaction post-call proof malformed');
        requireCoverage(a.address,a.size);
        requireValue(hexAt(a.address,a.size)===a.expected_hex,'Interaction protected state changed; never retry');
    }
}
function interactionUuid(address,proof) {
    const p=ptr(address);className(p,'System','String');
    if(proof)requireCoverage(p.add(16),4);
    const n=p.add(16).readS32();
    requireValue(n>0&&n<=128,'Interaction UUID length invalid');
    if(proof)requireCoverage(p.add(20),n*2);
    return p.add(20).readUtf16String(n);
}
function interactionConcurrent(d,proof=true) {
    requireValue(d&&d.kind==='concurrent'&&['npc','static'].includes(d.flavor),'Interaction concurrent map descriptor missing');
    const p=ptr(d.address),c=className(p,'System.Collections.Concurrent','ConcurrentDictionary`2');
    samePointer(interactionField(p,c,'_tables',0x04001acb,0x15,16,8,proof).readPointer(),d.tables,'Interaction concurrent tables changed');
    const tables=ptr(d.tables),tc=className(tables,'','Tables');
    for(const [name,token,offset,expected] of [['_buckets',0x04001ad5,16,d.buckets],['_locks',0x04001ad6,24,d.locks],['_countPerLock',0x04001ad7,32,d.count_per_lock]])
        samePointer(interactionField(tables,tc,name,token,0x1d,offset,8,proof).readPointer(),expected,'Interaction concurrent array changed');
    const buckets=ptr(d.buckets),locks=ptr(d.locks),counts=ptr(d.count_per_lock);
    className(buckets,'','Node[]');className(locks,'System','Object[]');className(counts,'System','Int32[]');
    for(const a of [buckets,locks,counts])if(proof)requireCoverage(a.add(24),8);
    const bn=buckets.add(24).readU64().toNumber(),ln=locks.add(24).readU64().toNumber();
    requireValue(bn===d.bucket_count&&bn>0&&bn<=65536&&ln===d.lock_count&&ln>0&&ln<=4096&&ln<=bn&&
        counts.add(24).readU64().toNumber()===ln,'Interaction concurrent capacity invalid');
    let expectedCount=0;const perLock=[],observedLocks=Array(ln).fill(0);
    for(let i=0;i<ln;i++) {if(proof)requireCoverage(counts.add(32+i*4),4);const n=interactionInteger(counts.add(32+i*4).readS32(),0,32768);perLock.push(n);expectedCount+=n;}
    requireValue(expectedCount===d.count&&expectedCount<=32768&&Array.isArray(d.items)&&d.items.length===expectedCount,'Interaction concurrent count changed');
    const supplied=new Map(),seen=new Set(),keys=new Set(),items=[];
    for(const row of d.items){requireValue(!supplied.has(row.node),'Interaction duplicate node descriptor');supplied.set(row.node,row);}
    const nodeClass=buckets.readPointer().add(0x40).readPointer();
    requireValue(!nodeClass.isNull()&&nodeClass.add(0xf8).readU32()===48,'Interaction concurrent node size differs');
    const uuidClass=interactionFieldClass(nodeClass,d.flavor==='npc'?'_key':'_value','SimpleSave','EntityID',24);
    interactionField(ptr(0),uuidClass,'Id',0x04000036,0x0e,16,8,false);
    if(d.flavor==='static') {
        const idClass=interactionFieldClass(nodeClass,'_key','LubanDatas','TbNpcBaseCfgId',20);
        interactionField(ptr(0),idClass,'<Value>k__BackingField',0x04000b8c,8,16,4,false);
    }
    for(let i=0;i<bn;i++) {
        if(proof)requireCoverage(buckets.add(32+i*8),8);
        let node=buckets.add(32+i*8).readPointer();
        while(!node.isNull()) {
            requireValue(!seen.has(node.toString())&&seen.size<32768,'Interaction concurrent cycle or duplicate node');seen.add(node.toString());
            const row=supplied.get(node.toString());requireValue(row&&row.bucket===i,'Interaction concurrent node changed');
            const nc=className(node,'','Node');samePointer(nc,nodeClass,'Interaction concurrent node class differs');
            const key=interactionField(node,nc,'_key',0x04001ad8,0x11,16,d.flavor==='npc'?8:4,proof);
            const value=interactionField(node,nc,'_value',0x04001ad9,d.flavor==='npc'?0x12:0x11,24,8,proof);
            const next=interactionField(node,nc,'_next',0x04001ada,0x15,32,8,proof).readPointer();
            const hash=interactionField(node,nc,'_hashcode',0x04001adb,8,40,4,proof).readS32();
            requireValue((hash&0x7fffffff)%bn===i&&row.hashcode===hash,'Interaction concurrent hash differs');
            samePointer(next,row.next,'Interaction concurrent chain changed');
            const k=d.flavor==='npc'?interactionUuid(key.readPointer(),proof):interactionInteger(key.readS32(),1);
            const v=d.flavor==='npc'?value.readPointer().toString():interactionUuid(value.readPointer(),proof);
            requireValue(k===row.key&&v===row.value&&!keys.has(k),'Interaction concurrent key or value changed');keys.add(k);
            if(d.flavor==='npc')samePointer(key.readPointer(),row.key_pointer,'Interaction UUID key pointer changed');
            else samePointer(value.readPointer(),row.value_pointer,'Interaction UUID value pointer changed');
            items.push({key:k,value:v,node:node.toString()});observedLocks[i%ln]++;node=next;
        }
    }
    requireValue(seen.size===expectedCount&&observedLocks.every((n,i)=>n===perLock[i]),'Interaction concurrent member count differs');
    return items;
}
function interactionPhotoQuests(m,proof=true) {
    const manager=ptr(m.logic_manager),lc=className(manager,'Game','NpcLogicManager'),d=m.quest_owners;
    requireValue(d&&d.kind==='hashset','Photostone quest owner set missing');
    samePointer(interactionField(manager,lc,'_questSpecialStateOwners',0x040036e6,0x15,32,8,proof).readPointer(),d.address,'Photostone quest owners replaced');
    requireValue(!boolAt(interactionField(manager,lc,'_isExecutingNpcInteractAction',0x040036e9,2,0x2d,1,proof)),'Photostone interaction already executing');
    const set=ptr(d.address),sc=className(set,'System.Collections.Generic','HashSet`1');
    for(const [name,token,kind,offset,size,key] of [['_buckets',0x040004da,0x1d,16,8,'buckets'],['_slots',0x040004db,0x1d,24,8,'slots'],
        ['_count',0x040004dc,8,32,4,'count'],['_lastIndex',0x040004dd,8,36,4,'last_index'],['_freeList',0x040004de,8,40,4,'free_list'],['_version',0x040004e0,8,56,4,'version']]) {
        const at=interactionField(set,sc,name,token,kind,offset,size,proof);
        if(size===8)samePointer(at.readPointer(),d[key],'Photostone quest collection changed');else requireValue(at.readS32()===d[key],'Photostone quest collection changed');
    }
    requireValue(d.count>=0&&d.count<=d.last_index&&d.last_index<=4096&&d.free_list>=-1&&d.free_list<Math.max(1,d.last_index)&&
        Array.isArray(d.items)&&d.items.length===d.count,'Photostone quest set bounds invalid');
    const slots=ptr(d.slots),buckets=ptr(d.buckets);
    if(slots.isNull()){requireValue(d.count===0&&d.last_index===0&&buckets.isNull(),'Photostone quest set uninitialized');return;}
    const ac=className(slots,'','Slot[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===36,'Photostone quest slot size differs');
    for(const [name,token,kind,offset,size] of [['hashCode',0x040004e4,8,16,4],['next',0x040004e5,8,20,4],['value',0x040004e6,0x11,24,12]])
        interactionField(ptr(0),ec,name,token,kind,offset,size,false);
    const oc=interactionFieldClass(ec,'value','','QuestSpecialStateOwner',28);
    for(const [i,name]of ['QuestId','NpcId','SubId'].entries())interactionField(ptr(0),oc,name,0x040036f2+i,0x11,16+i*4,4,false);
    if(proof)requireCoverage(slots.add(24),8);
    requireValue(slots.add(24).readU64().toNumber()===d.capacity&&d.capacity>=d.last_index&&d.capacity<=8192,'Photostone quest capacity changed');
    className(buckets,'System','Int32[]');
    const rows=new Map(d.items.map(x=>[x.slot,x]));requireValue(rows.size===d.count,'Photostone duplicate quest slots');let live=0;
    for(let i=0;i<d.last_index;i++) {
        const p=slots.add(32+i*20);if(proof)requireCoverage(p,20);const hash=p.readS32(),next=p.add(4).readS32();
        requireValue(next>=-1&&next<Math.max(1,d.last_index),'Photostone quest slot chain invalid');
        if(hash<0)continue;live++;const r=rows.get(p.toString());
        requireValue(r&&p.add(8).readS32()===r.quest_id&&p.add(12).readS32()===r.npc_id&&p.add(16).readS32()===r.sub_id&&
            r.quest_id>0&&r.npc_id>0&&r.sub_id>0,'Photostone quest slot changed');
        requireValue(r.npc_id!==m.npc_id,'Photostone NPC special entry reserved by a quest');
    }
    requireValue(live===d.count,'Photostone quest live count differs');
}
function interactionPhotoUsage(m,proof=true) {
    const s=m.usage_state,d=s&&s.dictionary,p=ptr(m.usage);
    requireValue(d&&Array.isArray(s.records)&&Array.isArray(d.items),'Photostone usage proof missing');
    samePointer(d.address,p,'Photostone usage descriptor disconnected');className(p,'System.Collections.Generic','Dictionary`2');
    for(const [o,size]of [[24,8],[32,4],[40,4],[44,4]])if(proof)requireCoverage(p.add(o),size);
    const entries=p.add(24).readPointer(),count=p.add(32).readS32(),free=p.add(40).readS32();
    samePointer(entries,d.entries,'Photostone usage entries changed');
    requireValue(count===d.count&&free===d.free&&p.add(44).readS32()===d.version&&count>=0&&count<=1024&&free>=0&&free<=count&&
        d.items.length===count-free&&s.records.length===count-free,'Photostone usage collection changed');
    if(entries.isNull()){requireValue(count===0&&free===0,'Photostone usage collection uninitialized');return;}
    const ac=className(entries,'','Entry[]'),ec=ac.add(0x40).readPointer();
    requireValue(!ec.isNull()&&ec.add(0xf8).readU32()===40&&d.stride===24,'Photostone usage entry size differs');
    for(const [name,token,kind,offset,size]of [['hashCode',0x04001b0d,8,16,4],['next',0x04001b0e,8,20,4],['key',0x04001b0f,8,24,4],['value',0x04001b10,0x12,32,8]])
        interactionField(ptr(0),ec,name,token,kind,offset,size,false);
    if(proof)requireCoverage(entries.add(24),8);
    requireValue(entries.add(24).readU64().toNumber()===d.capacity&&d.capacity>=count&&d.capacity<=2064,'Photostone usage capacity changed');
    const rows=new Map(d.items.map(x=>[x.entry,x])),records=new Map(s.records.map(x=>[x.action_id,x]));
    requireValue(rows.size===d.items.length&&records.size===s.records.length,'Photostone duplicate usage descriptor');let live=0;
    for(let i=0;i<count;i++) {
        const e=entries.add(32+i*24);if(proof)requireCoverage(e,24);if(e.readS32()<0)continue;live++;
        const action=e.add(8).readS32(),record=e.add(16).readPointer(),wire=rows.get(e.toString()),r=records.get(action);
        requireValue(action>0&&wire&&r&&wire.key===action&&r.used_count>=0&&Number.isInteger(r.used_count),'Photostone usage identity changed');
        samePointer(record,wire.value,'Photostone usage object changed');samePointer(record,r.record,'Photostone usage record changed');
        const rc=className(record,'Game.Model','NpcInteractionActionUsageRecord');
        requireValue(interactionField(record,rc,'<UsedCount>k__BackingField',0x0400a8b6,8,16,4,proof).readS32()===r.used_count,'Photostone usage count changed');
        const cycle=interactionField(record,rc,'<CycleKey>k__BackingField',0x0400a8b7,0x0a,24,8,proof);
        requireValue(Number.isSafeInteger(r.cycle_key)&&cycle.readS64().toString()===String(r.cycle_key),'Photostone usage cycle changed');
    }
    requireValue(live===count-free,'Photostone usage live count differs');
}
function interactionWorldNpc(world,npc,npcId,d,proof=true) {
    const wc=className(world,'Game.Model','GameWorldModel');
    samePointer(interactionField(world,wc,'<NpcModels>k__BackingField',0x0400a7ea,0x15,0x38,8,proof).readPointer(),d.address,'Interaction canonical NPC map changed');
    requireValue(d.flavor==='npc','Interaction NPC map flavor differs');
    const members=interactionConcurrent(d,proof),matches=members.filter(x=>ptr(x.value).equals(ptr(npc)));
    requireValue(matches.length===1,'Interaction NPC is not a unique world member');
    return matches[0];
}
function interactionPhotoOwner(m,proof) {
    const npc=ptr(m.npc),world=ptr(m.world),runtime=ptr(m.runtime);
    const nc=className(npc,'Game.Model','NpcModel'),wc=className(world,'Game.Model','GameWorldModel'),
        rc=className(runtime,'Game.Model','NpcInteractionRuntimeState');
    className(m.player,'Game.Model','PlayerModel');
    interactionLinks(m.owner_links,proof);
    const f=(o,c,name,token,kind,offset,size)=>interactionField(o,c,name,token,kind,offset,size,proof);
    requireValue(f(npc,nc,'<NpcCfgId>k__BackingField',0x0400a8fe,0x11,0x150,4).readS32()===m.npc_id&&
        f(npc,nc,'<WorldStatus>k__BackingField',0x0400a900,0x11,0x160,4).readS32()===0,'Photostone NPC is unavailable');
    samePointer(f(npc,nc,'<GameWorld>k__BackingField',0x0400a901,0x12,0x168,8).readPointer(),world,'Photostone NPC belongs to another world');
    samePointer(f(world,wc,'<PlayerModel>k__BackingField',0x0400a7e6,0x12,0x18,8).readPointer(),m.player,'Photostone world player changed');
    samePointer(f(npc,nc,'<MiniGameStatistics>k__BackingField',0x0400a913,0x15,0x1e8,8).readPointer(),m.stats,'Photostone statistics replaced');
    samePointer(f(npc,nc,'<NpcInteractionRuntime>k__BackingField',0x0400a914,0x12,0x1f0,8).readPointer(),runtime,'Photostone runtime replaced');
    samePointer(f(runtime,rc,'<ActionUsageRecords>k__BackingField',0x0400a8b5,0x15,0x18,8).readPointer(),m.usage,'Photostone usage collection replaced');
    requireValue(!ptr(m.usage).isNull(),'Photostone usage is uninitialized');
    className(m.usage,'System.Collections.Generic','Dictionary`2');
    const special=f(runtime,rc,'<SpecialSubId>k__BackingField',0x0400a8b3,8,0x10,4);
    samePointer(f(world,wc,'<CurrentGameTime>k__BackingField',0x0400a7e8,0x12,0x28,8).readPointer(),m.date_address,'Photostone date object changed');
    const time=ptr(m.date_address),tc=className(time,'Game','GameTime');
    requireValue(Array.isArray(m.date)&&m.date.length===4&&m.date.every((v,i)=>
        Number.isInteger(v)&&f(time,tc,['Year','Month','Day','Unit'][i],0x04004938+i,8,0x10+i*4,4).readS32()===v),'Photostone date changed');
    return {npc,world,runtime,nc,wc,rc,special};
}
function interactionPhotoEntry(m) {
    const entry=ptr(m.entry),ec=className(entry,'LubanDatas.data','NpcInteractGameEntry'),c=m.entry_config;
    samePointer(ec,m.entry_class,'Photostone configuration class changed');
    requireValue(c&&c.npc_id===m.npc_id&&c.sub_id===m.sub_id&&c.game_type===1&&c.max_success===1,
        'Photostone entry is outside reviewed configuration');
    for(const [name,token,kind,offset,expected] of [
        ['<npcId>k__BackingField',0x040017cd,0x11,0x10,m.npc_id],
        ['<subId>k__BackingField',0x040017ce,0x11,0x14,m.sub_id],
        ['<UnlockIntimacy>k__BackingField',0x040017d0,8,0x20,c.unlock_intimacy],
        ['<interactGameType>k__BackingField',0x040017d4,0x11,0x40,1],
        ['<interactGameParam>k__BackingField',0x040017d5,8,0x44,c.game_param],
        ['<triggerPriority>k__BackingField',0x040017e1,8,0x98,c.priority]])
        requireValue(interactionField(entry,ec,name,token,kind,offset,4).readS32()===expected,'Photostone entry configuration changed');
    // Nullable<Int32> and Nullable<subid wrapper> both use hasValue at +0 and
    // their reviewed four-byte value at +4. Zero is not a fabricated predecessor.
    const depends=interactionField(entry,ec,'<dependsSubId>k__BackingField',0x040017cf,0x15,0x18,8);
    const hasDepends=boolAt(depends);
    requireValue(hasDepends?(Number.isInteger(c.depends_sub_id)&&depends.add(4).readS32()===c.depends_sub_id):c.depends_sub_id===null,
        'Photostone predecessor configuration changed');
    const maximum=interactionField(entry,ec,'<maxSuccessCount>k__BackingField',0x040017d3,0x15,0x38,8);
    requireValue(boolAt(maximum)&&maximum.add(4).readS32()===1,'Photostone success limit changed');
    return {entry,ec,depends:hasDepends?c.depends_sub_id:null};
}
function executePhotostone() {
    const m=request.photostone,force=request.operation==='photostone_force_replay';
    interactionRound(m);
    requireValue(request.operation==='photostone_activate'||force,'Photostone operation not whitelisted');
    requireValue(m.mode===(force?'force':'next')&&(!force||m.force_confirmed===true),'Photostone mode or reset confirmation differs');
    interactionInteger(m.npc_id,1);interactionInteger(m.sub_id,1);
    const owner=interactionPhotoOwner(m,true),configuration=interactionPhotoEntry(m);
    const member=interactionWorldNpc(owner.world,owner.npc,m.npc_id,m.npc_dictionary);
    samePointer(interactionField(owner.world,owner.wc,'<StaticNpcIds>k__BackingField',0x0400a7ec,0x15,0x48,8).readPointer(),m.static_ids.address,'Photostone static ID map changed');
    requireValue(m.static_ids.flavor==='static','Photostone static ID map flavor differs');
    const ids=interactionConcurrent(m.static_ids),selectedIds=ids.filter(x=>x.key===m.npc_id);
    requireValue(selectedIds.length===1&&selectedIds[0].value===member.key,'Photostone static ID is not the selected world NPC');
    interactionPhotoQuests(m);
    interactionPhotoUsage(m);
    requireValue(owner.special.readS32()===m.active_special&&m.active_special===0,'Photostone special entry already active');
    const before=interactionStatistics(m.stats,true);
    interactionExpectedStatistics(before,m.stats_before);
    requireValue(configuration.depends===null||before.items.has(configuration.depends),'Photostone prerequisite key missing');
    requireValue(force||!before.items.has(m.sub_id)||before.items.get(m.sub_id)===0,'Photostone stage is already complete');
    const manager=ptr(m.logic_manager),lc=className(manager,'Game','NpcLogicManager');
    samePointer(lc,m.logic_class,'Photostone logic manager class changed');
    requireValue(m.methods&&Object.keys(m.methods).sort().join(',')==='force,meets,set','Photostone methods incomplete');
    const selected=force?'force':'set',spec=INTERACTION_METHODS[force?'force':'activate'];
    requireRequestMethod(spec);samePointer(request.method_info,m.methods[selected],'Photostone selected method differs');
    const methods={set:interactionMethod(m.methods.set,lc,INTERACTION_METHODS.activate),
        force:interactionMethod(m.methods.force,lc,INTERACTION_METHODS.force),
        meets:interactionMethod(m.methods.meets,lc,INTERACTION_METHODS.requirements)};
    interactionArgumentClass(methods.set,0,'Game.Model','NpcModel');
    interactionArgumentClass(methods.meets,0,'Game.Model','NpcModel');
    interactionArgumentClass(methods.meets,1,'LubanDatas.data','NpcInteractGameEntry');
    interactionArgumentClass(methods.force,0,'LubanDatas','TbNpcBaseCfgId',20);
    interactionArgumentClass(methods.force,1,'LubanDatas','TbNpcInteractGameEntrySubid',20);
    interactionStableAnchors(m.post_stable_anchors);
    const eligible=interactionBoolean(interactionInvoke(methods.meets,ptr(0),[owner.npc,configuration.entry,interactionScalar(force,true)]));
    requireValue(eligible,'Photostone native eligibility denied');
    validateAnchors();
    interactionPhotoOwner(m,true);
    interactionDispatch(m);
    const result=force?interactionInvoke(methods.force,manager,[interactionScalar(m.npc_id),interactionScalar(m.sub_id)]):
        interactionInvoke(methods.set,ptr(0),[owner.npc,interactionScalar(m.sub_id),interactionScalar(true,true)]);
    requireValue(interactionBoolean(result),'Photostone method did not confirm activation; never retry');
    interactionPhotoOwner(m,false);
    interactionPhotoQuests(m,false);
    interactionPhotoUsage(m,false);
    requireValue(owner.special.readS32()===m.sub_id,'Photostone special entry was not retained; never retry');
    const after=interactionStatistics(m.stats,false),had=before.items.has(m.sub_id),expected=m.stats_before.filter(x=>!force||x.key!==m.sub_id);
    interactionExpectedStatistics(after,expected);
    samePointer(after.array,before.array,'Photostone statistics allocation changed; never retry');
    requireValue(after.count===before.count&&after.capacity===before.capacity&&
        after.free===before.free+(force&&had?1:0)&&after.version===((before.version+(force&&had?1:0))|0),
        'Photostone statistics changed beyond the selected operation; never retry');
    interactionStableAnchors(m.post_stable_anchors);
    finish('completed',{called:true,operation:request.operation,round_key:m.round_key,npc_id:m.npc_id,sub_id:m.sub_id,
        activated:true,history_reset:force&&had,previous_success:had?before.items.get(m.sub_id):null,
        active_special:m.sub_id,thread_id:Process.getCurrentThreadId()});
}
function interactionDelegate(d,proof=true) {
    requireValue(d&&d.address&&d.method_info&&d.target,'Persuasion delegate descriptor missing');
    const p=ptr(d.address),kc=p.readPointer();requireValue(!kc.isNull(),'Persuasion delegate missing');
    const mc=interactionClass(kc.add(0x58).readPointer(),'System','MulticastDelegate'),
        dc=interactionClass(mc.add(0x58).readPointer(),'System','Delegate');
    for(const [name,token,offset,expected] of [['method_ptr',0x04000762,16,d.code],['method',0x04000765,40,d.method_info],['method_code',0x04000768,64,d.target]])
        samePointer(interactionField(p,dc,name,token,0x18,offset,8,proof).readPointer(),expected,'Persuasion delegate changed');
    samePointer(interactionField(p,mc,'delegates',0x04000790,0x1d,0x78,8,proof).readPointer(),d.delegates,'Persuasion delegate list changed');
    return p;
}
function interactionPersuasionFlow(m,proof=true) {
    const flow=m.flow,panel=ptr(m.panel),pc=className(panel,'Game','NpcPersuadePanel');
    requireValue(flow&&flow.sub_id===m.sub_id&&!flow.notified&&!flow.ended&&!flow.cancelled,'Persuasion flow already ended');
    const closure=ptr(flow.closure),cc=className(closure,'','<>c__DisplayClass5_0'),
        command=ptr(flow.command),kc=className(command,'Game','MiniGamePersuadeCommand'),
        ctx=ptr(flow.context),xc=className(ctx,'A1.Flow','ProcContext');
    samePointer(cc,flow.closure_class,'Persuasion closure class changed');samePointer(kc,flow.command_class,'Persuasion command class changed');samePointer(xc,flow.context_class,'Persuasion context class changed');
    const field=(o,c,n,t,k,offset,size)=>interactionField(o,c,n,t,k,offset,size,proof);
    requireValue(!boolAt(field(closure,cc,'notified',0x04005bfa,2,16,1)),'Persuasion flow already notified');
    boolAt(field(closure,cc,'win',0x04005bfb,2,17,1));
    samePointer(field(closure,cc,'<>4__this',0x04005bfd,0x12,32,8).readPointer(),command,'Persuasion command replaced');
    samePointer(field(closure,cc,'ctx',0x04005bfe,0x12,40,8).readPointer(),ctx,'Persuasion context replaced');
    requireValue(field(command,kc,'_npcId',0x04005bf7,0x11,16,4).readS32()===m.npc_id&&
        field(command,kc,'_topicId',0x04005bf8,0x11,20,4).readS32()===m.topic_id,'Persuasion command target changed');
    const sub=field(command,kc,'_subId',0x04005bf9,0x15,24,8);
    requireValue(boolAt(sub)&&sub.add(4).readS32()===m.sub_id,'Persuasion command sub-ID changed');
    samePointer(field(ctx,xc,'<Ct>k__BackingField',0x040000d0,0x11,16,8).readPointer(),flow.source,'Persuasion cancellation source changed');
    requireValue(field(ctx,xc,'<ActivationId>k__BackingField',0x040000d1,8,24,4).readS32()===flow.activation_id&&
        !boolAt(field(ctx,xc,'_endedNotified',0x040000d8,2,0x78,1)),'Persuasion context ended or replaced');
    const source=ptr(flow.source);
    if(!source.isNull()) {
        const sc=className(source,'System.Threading','CancellationTokenSource');samePointer(sc,flow.source_class,'Persuasion source class changed');
        const status=field(source,sc,'_state',0x04000a46,8,32,4).readS32();
        requireValue(status>=0&&status<2&&!boolAt(field(source,sc,'_disposed',0x04000a48,2,40,1)),'Persuasion flow cancelled or disposed');
    }
    requireValue(flow.callbacks&&Object.keys(flow.callbacks).sort().join(',')==='alive,close,lose,win','Persuasion callbacks missing');
    for(const [key,name,token,kind,offset] of [['alive','_isFlowAlive',0x0400542c,0x15,0x180],['win','_actionOnWin',0x0400542f,0x12,0x190],
        ['lose','_actionOnLose',0x04005430,0x12,0x198],['close','_actionOnClose',0x04005431,0x12,0x1a0]]) {
        const d=flow.callbacks[key];samePointer(field(panel,pc,name,token,kind,offset,8).readPointer(),d.address,'Persuasion flow callback replaced');
        interactionDelegate(d,proof);samePointer(d.target,closure,'Persuasion callback targets another flow');
        requireValue(ptr(d.delegates).isNull(),'Persuasion callback is multicast');
        interactionMethod(d.method_info,cc,INTERACTION_METHODS[key]);samePointer(d.code,image.base.add(INTERACTION_METHODS[key].rva),'Persuasion callback code differs');
    }
}
function interactionPersuasionEvent(m,proof=true) {
    const callbacks=m.event_callbacks;requireValue(Array.isArray(callbacks)&&callbacks.length>0&&callbacks.length<=16,'Persuasion event callbacks missing');
    const event=ptr(m.event),ec=event.readPointer(),mc=interactionClass(ec.add(0x58).readPointer(),'System','MulticastDelegate');
    const array=interactionField(event,mc,'delegates',0x04000790,0x1d,0x78,8,proof).readPointer();
    let members=[event];
    if(!array.isNull()) {
        className(array,'System','Delegate[]');if(proof)requireCoverage(array.add(24),8);
        const n=array.add(24).readU64().toNumber();requireValue(n===callbacks.length,'Persuasion subscription count changed');
        members=[];for(let i=0;i<n;i++){if(proof)requireCoverage(array.add(32+i*8),8);members.push(array.add(32+i*8).readPointer());}
    }
    requireValue(members.length===callbacks.length,'Persuasion subscription changed');
    let found=0;
    callbacks.forEach((d,i)=>{
        samePointer(members[i],d.address,'Persuasion event subscription changed');interactionDelegate(d,proof);
        requireValue(ptr(d.delegates).isNull(),'Persuasion nested multicast unsupported');
        if(ptr(d.target).equals(ptr(m.panel))) {
            interactionMethod(d.method_info,ptr(m.panel_class),INTERACTION_METHODS.ended);
            samePointer(d.code,image.base.add(INTERACTION_METHODS.ended.rva),'Persuasion panel subscriber code differs');found++;
        }
    });
    requireValue(found===1,'Persuasion panel does not have one normal result subscriber');
}
function interactionPersuasionOwner(m,after=false) {
    const panel=dualJadePanel(m,'Game','NpcPersuadePanel'),pc=panel.readPointer(),npc=ptr(m.npc),nc=className(npc,'Game.Model','NpcModel'),
        world=ptr(m.world),wc=className(world,'Game.Model','GameWorldModel'),input=ptr(m.input_panel),ic=className(input,'Game','DialogueInputPanel');
    className(m.player,'Game.Model','PlayerModel');samePointer(pc,m.panel_class,'Persuasion panel class changed');samePointer(nc,m.npc_class,'Persuasion NPC class changed');samePointer(ic,m.input_class,'Persuasion input class changed');
    const field=(o,c,n,t,k,offset,size)=>interactionField(o,c,n,t,k,offset,size,!after);
    const pf=(n,t,k,o,size)=>field(panel,pc,n,t,k,o,size),nf=(n,t,k,o,size)=>field(npc,nc,n,t,k,o,size);
    samePointer(pf('_subscribedNpc',0x04005425,0x12,0x158,8).readPointer(),npc,'Persuasion panel NPC changed');
    requireValue(pf('_npcId',0x0400542d,0x11,0x188,4).readS32()===m.npc_id&&pf('_topicId',0x0400542e,0x11,0x18c,4).readS32()===m.topic_id&&
        nf('<NpcCfgId>k__BackingField',0x0400a8fe,0x11,0x150,4).readS32()===m.npc_id,'Persuasion target changed');
    samePointer(nf('<GameWorld>k__BackingField',0x0400a901,0x12,0x168,8).readPointer(),world,'Persuasion NPC world changed');
    samePointer(field(world,wc,'<PlayerModel>k__BackingField',0x0400a7e6,0x12,24,8).readPointer(),m.player,'Persuasion current player changed');
    const member=interactionWorldNpc(world,npc,m.npc_id,m.membership.dictionary_descriptor,!after);
    requireValue(member.key===m.membership.uuid&&member.node===m.membership.node&&m.membership.npc_id===m.npc_id,'Persuasion canonical member changed');
    samePointer(m.membership.npc,npc,'Persuasion membership target differs');
    samePointer(pf('DialogueInput',0x0400541d,0x12,0x118,8).readPointer(),input,'Persuasion input panel changed');
    if(!after)requireCoverage(input.add(16),8);requireValue(!input.add(16).readPointer().isNull(),'Persuasion input destroyed');
    const canSubmit=boolAt(field(input,ic,'m_CanSubmit',0x04004c28,2,0x128,1));
    boolAt(field(input,ic,'m_SubmitAvailable',0x04004c29,2,0x129,1));
    requireValue(!boolAt(pf('_userInitiatedClose',0x0400542b,2,0x179,1))&&pf('_peekLoadingCo',0x04005432,0x12,0x1a8,8).readPointer().isNull()&&
        !boolAt(nf('IsProcessingPersuadeMessage',0x0400a8e8,2,0xe8,1)),'Persuasion is closing or processing AI input');
    requireValue(!boolAt(nf('<IsProcessingChatMessage>k__BackingField',0x0400a8dc,2,0xa8,1))&&
        !boolAt(nf('<IsSummarizingChatHistory>k__BackingField',0x0400a8dd,2,0xa9,1)),'Persuasion NPC still has another AI request');
    requireValue(nf('<PersuadeSessionId>k__BackingField',0x0400a8ee,8,0x100,4).readS32()===m.session_id&&
        nf('_persuadeProcessingToken',0x0400a8e9,8,0xec,4).readS32()===m.processing_token,'Persuasion session changed');
    const ended=boolAt(pf('_persuadeEnded',0x04005427,2,0x168,1)),win=boolAt(pf('_settlementIsWin',0x0400542a,2,0x178,1));
    const notified=boolAt(pf('_persuadeResultNotified',0x04005428,2,0x169,1));
    const reason=nf('<LastPersuadeEndReason>k__BackingField',0x0400a8e2,0x11,0xc4,4).readS32(),
        topic=nf('<CurrentPersuadeTopicId>k__BackingField',0x0400a8e3,0x11,0xc8,4).readS32(),
        round=nf('<PersuadeRound>k__BackingField',0x0400a8e4,8,0xcc,4).readS32(),
        emotion=nf('<PersuadeEmotionValue>k__BackingField',0x0400a8e6,8,0xd8,4).readS32(),
        peek=pf('_peekRequestToken',0x04005433,8,0x1b0,4).readS32();
    samePointer(nf('OnPersuadeEnded',0x0400a8f2,0x15,0x120,8).readPointer(),m.event,'Persuasion ended event replaced');
    for(const [name,token,offset,expected] of [['<PersuadeChatMessages>k__BackingField',0x0400a8e5,0xd0,m.chat],['_persuadeLedger',0x0400a8eb,0xf8,m.ledger]]) {
        samePointer(nf(name,token,0x15,offset,8).readPointer(),expected,'Persuasion conversation container changed');className(expected,'System.Collections.Generic','List`1');
    }
    if(after)requireValue(ended&&win&&!canSubmit&&reason===1&&topic===0&&round===0&&emotion===0&&peek===((m.peek_token+1)|0),'Persuasion success state not retained; never retry');
    else requireValue(!ended&&!notified&&canSubmit&&reason===0&&topic===m.topic_id&&peek===m.peek_token&&
        round>=0&&round<=m.config.max_rounds&&pf('_settlementDelayCts',0x04005429,0x12,0x170,8).readPointer().isNull(),'Persuasion is not an idle active session');
    interactionPersuasionFlow(m,!after);interactionPersuasionEvent(m,!after);
    return {npc,nc,panel};
}
function interactionPersuasionConfig(m) {
    const c=m.config,topic=ptr(c.topic_config),tc=className(topic,'LubanDatas.data','NpcPersuadeTopic'),entry=ptr(c.entry_config),ec=className(entry,'LubanDatas.data','NpcInteractGameEntry');
    for(const [obj,kc,name,token,kind,offset,expected] of [
        [topic,tc,'<id>k__BackingField',0x0400182b,0x11,16,m.topic_id],
        [topic,tc,'<maxRounds>k__BackingField',0x0400182d,8,32,c.max_rounds],
        [topic,tc,'<npcId>k__BackingField',0x04001832,0x11,0x48,m.npc_id],
        [entry,ec,'<npcId>k__BackingField',0x040017cd,0x11,16,m.npc_id],
        [entry,ec,'<subId>k__BackingField',0x040017ce,0x11,20,m.sub_id],
        [entry,ec,'<interactGameType>k__BackingField',0x040017d4,0x11,0x40,2],
        [entry,ec,'<interactGameParam>k__BackingField',0x040017d5,8,0x44,m.topic_id]])
        requireValue(interactionField(obj,kc,name,token,kind,offset,4).readS32()===expected,'Persuasion configuration changed');
    interactionInteger(c.max_rounds,1,1000);interactionInteger(c.exit_delay_ms,1,600000);
    const delay=interactionField(topic,tc,'<autoExitDelayMs>k__BackingField',0x04001833,0x15,0x4c,8);
    requireValue(boolAt(delay)&&delay.add(4).readS32()===c.exit_delay_ms,'Persuasion normal countdown changed');
}
function executePersuasion() {
    const m=request.persuasion;interactionRound(m);
    requireValue(request.operation==='persuasion_success','Persuasion operation not whitelisted');
    for(const key of ['npc_id','topic_id','sub_id','session_id'])interactionInteger(m[key],1);
    const owner=interactionPersuasionOwner(m),spec=INTERACTION_METHODS.persuade;
    interactionPersuasionConfig(m);interactionStableAnchors(m.post_stable_anchors);
    requireRequestMethod(spec);const method=interactionMethod(request.method_info,owner.nc,spec);
    interactionArgumentClass(method,1,'Game.Model','PersuadeEndReason',20);
    interactionDispatch(m);
    const result=interactionInvoke(method,owner.npc,[interactionScalar(true,true),interactionScalar(1)]);
    requireValue(result.isNull(),'Persuasion void method returned a value; never retry');
    interactionPersuasionOwner(m,true);interactionStableAnchors(m.post_stable_anchors);
    // Success has been judged. The game still owns its normal countdown,
    // settlement panel, reward delivery and completion callback.
    finish('completed',{called:true,native_won:true,normal_countdown:true,round_key:m.round_key,
        npc_id:m.npc_id,topic_id:m.topic_id,session_id:m.session_id,end_reason:1,
        panel_ended:true,settlement_is_win:true,current_topic_id:0,thread_id:Process.getCurrentThreadId()});
}

/* END interaction_bridge.js */
function execute() {
    if (state !== 'pending') return;
    if (Date.now() > request.deadline) { finish('cancelled', { called: false, reason: '等待主线程超时；未调用游戏方法。' }); return; }
    state = 'validating';
    try {
        if (Process.id !== request.pid) throw new Error('Process identity differs');
        validateAnchors();
        if (request.operation === 'photostone_activate' || request.operation === 'photostone_force_replay') {
            executePhotostone(); return;
        }
        if (request.operation === 'persuasion_success') { executePersuasion(); return; }
        if (request.operation === 'lifespan_inspect' || request.operation === 'lifespan_add') {
            executeLifespan(); return;
        }
        if (request.operation === 'alchemy_perfect' || request.operation === 'alchemy_talent_set') {
            executeAlchemy(ptr(request.method_info)); return;
        }
        if (request.operation === 'crafting_complete') { executeCrafting(); return; }
        if (request.operation === 'alchemy_find_recipe') { executeAlchemyRecipe(); return; }
        const isDual = request.operation === 'dual_cultivation_complete';
        const isJade = request.operation === 'jade_reveal_all';
        const isSpeed = request.operation === 'game_speed_set';
        const isMeridian = request.operation === 'meridian_solve';
        const isGrowth = request.operation === 'character_growth_set';
        const isInteract = request.operation === 'character_interact_set';
        const isStamina = Object.prototype.hasOwnProperty.call(RESOURCE_OPERATIONS, request.operation);
        const bag = isDual || isJade || isSpeed || isMeridian || isGrowth || isInteract || isStamina ? null : ptr(request.bag);
        if (bag !== null && !bag.add(16).readPointer().equals(ptr(request.player))) throw new Error('Bag owner changed');
        const method = ptr(request.method_info);
        if (methodToken(method) !== request.method_token) throw new Error('Method token differs');
        if (paramCount(method) !== request.parameter_count) throw new Error('Method signature differs');
        if (!method.readPointer().equals(image.base.add(request.method_rva))) throw new Error('Method address differs');
        let values, target = bag, resourceVersion, currency;
        if (isDual) {
            ({target, values} = prepareDualCultivation(method));
        } else if (isJade) {
            ({target, values} = prepareJade(method));
        } else if (isSpeed) {
            ({target, values} = prepareGameSpeed(method));
        } else if (isMeridian) {
            target = validateMeridian(method); values = [];
        } else if (isGrowth) {
            target = validateGrowth(method);
            const attr = Memory.alloc(4); attr.writeS32(request.character.attr_id);
            const value = Memory.alloc(4); value.writeFloat(request.character.value);
            values = [attr, value];
        } else if (isInteract) {
            target = validateInteract(method);
            const attr = Memory.alloc(4); attr.writeS32(request.character.attr_id);
            const value = Memory.alloc(4); value.writeS32(request.character.value);
            values = [attr, value];
        } else if (isStamina) {
            target = validateStamina(method);
            const r = request.resource;
            resourceVersion = ptr(r.dictionary).add(0x2c).readS32();
            // These getters do not authorize a mutation. Keep state validating
            // so a failed getter is definitely reported as called:false.
            const before = readStamina(r.methods.current, target), maximum = readStamina(r.methods.max, target);
            requireValue(floatBits(before) === floatBits(r.before), 'Native current stamina differs from displayed value');
            requireValue(maximum > 0 && maximum <= 1000000 && r.value <= maximum, 'Requested stamina exceeds the game maximum');
            const delta = Math.fround(r.value - before);
            requireValue(Math.abs(delta) <= 1000 && floatBits(Math.fround(before + delta)) === floatBits(r.value),
                'Stamina delta cannot produce the exact requested Single');
            validateAnchors();
            const value = Memory.alloc(4); value.writeFloat(delta); values = [value];
        } else if (request.operation === 'add') {
            // Whole-file release hashes are advisory; validate this actual
            // callable for ordinary items as well as for currency requests.
            validateReviewedMethod(method, className(bag,'Game.Model.Components','BagModel'),
                nativeSpec({name:'AddItem',token:0x06015191,rva:0xe9bdd0,argc:5,returns:0x12,
                 params:[0x11,8,0x11,0x15,0x12],prefix:'44894c24204489442418895424104889'}));
            if (!Number.isInteger(request.item_id) || !Number.isInteger(request.quantity) || request.quantity < 1 ||
                request.quantity > (request.item_id === 50000 ? 100000000 :
                    LARGE_CURRENCY_IDS.has(request.item_id) ? 1000000 : 999)) throw new Error('Invalid item request');
            if (LARGE_CURRENCY_IDS.has(request.item_id)) currency = prepareCurrencyAdd(bag, method);
            else requireValue(request.currency_proof === undefined, 'Currency proof cannot enlarge ordinary item limits');
            const id = Memory.alloc(4); id.writeS32(request.item_id);
            const amount = Memory.alloc(4); amount.writeS32(request.quantity);
            const source = Memory.alloc(4); source.writeS32(0);
            // default Nullable<ItemGainContext>, matching GainItemCommand.ExecuteAsync.
            const context = Memory.alloc(64); context.writeByteArray(new Uint8Array(64));
            values = [id, amount, source, context, ptr(0)];
        } else if (request.operation === 'remove_test_uid') {
            const uid = Memory.alloc(8); uid.writeS64(int64(request.uid));
            const source = Memory.alloc(4); source.writeS32(0);
            values = [uid, source];
        } else { throw new Error('Unsupported operation'); }
        const argumentsArray = values.length ? Memory.alloc(values.length * Process.pointerSize) : ptr(0);
        values.forEach((value, i) => argumentsArray.add(i * Process.pointerSize).writePointer(value));
        const exception = Memory.alloc(Process.pointerSize); exception.writePointer(ptr(0));
        if (Date.now() > request.deadline) { finish('cancelled', { called: false, reason: '校验时请求已过期，未调用游戏方法。' }); return; }
        state = 'running'; // Set before entering native code: never eligible for a second call.
        const result = invoke(method, target, argumentsArray, exception);
        const thrown = exception.readPointer();
        if (!thrown.isNull()) { finish('exception', { exception: thrown.toString(), called: true, thread_id: Process.getCurrentThreadId() }); return; }
        if (isDual) {
            completeDualCultivation(result);
        } else if (isJade) {
            completeJade(result);
        } else if (isSpeed) {
            completeGameSpeed(result);
        } else if (isMeridian) {
            requireValue(!result.isNull(), 'Meridian returned no boxed Boolean');
            const changed = boolAt(result.add(16));
            const finished = boolAt(target.add(0x72)), won = boolAt(target.add(0x73));
            const failure = target.add(0x108).readS32();
            requireValue(changed && finished && won && failure === 0,
                '原生调用已返回，但未确认正常胜利；请检查游戏，禁止重复执行。');
            finish('completed', { called: true, thread_id: Process.getCurrentThreadId(), changed: changed,
                native_finished: finished, native_won: won, failure_reason: failure,
                round_key: request.meridian.round_key, result: result.toString() });
        } else if (isGrowth) {
            const c = request.character;
            samePointer(target.add(0x28).readPointer(), c.dictionary, 'Growth dictionary replaced during native call');
            const entry = growthEntry(ptr(c.dictionary), c.attr_id);
            requireValue(entry !== null && hexAt(entry, 4) === hexAt(values[1], 4),
                '成长属性调用已返回，但读回不一致；禁止重复执行。');
            finish('completed', { called: true, thread_id: Process.getCurrentThreadId(), created: true,
                attr_id: c.attr_id, value: entry.readFloat(), identity_key: c.identity_key, result: result.toString() });
        } else if (isInteract) {
            const c = request.character;
            samePointer(className(target, 'Game.Model', 'PlayerModel'), c.player_class, 'Player class changed during native call');
            // SetInteractAttributeValue is allowed to allocate an initially
            // null dictionary. Always follow the current field on read-back.
            const dictionary = target.add(0x1a8).readPointer();
            requireValue(!dictionary.isNull(), 'Interaction dictionary was not initialized');
            if (!ptr(c.dictionary).isNull()) samePointer(dictionary, c.dictionary, 'Interaction dictionary replaced during native call');
            const entry = characterEntries(dictionary, true, false).get(c.attr_id);
            requireValue(entry !== undefined && entry.readS32() === c.value, '资质经验调用已返回，但读回不一致；禁止重复执行。');
            finish('completed', { called: true, thread_id: Process.getCurrentThreadId(), created: true,
                attr_id: c.attr_id, value: entry.readS32(), identity_key: c.identity_key, result: result.toString() });
        } else if (isStamina) {
            const r = request.resource;
            requireValue(!result.isNull(), 'Stamina setter returned no Boolean');
            className(result, 'System', 'Boolean');
            requireValue(boolAt(result.add(16)), 'Stamina setter did not confirm success');
            const after = readStamina(r.methods.current, target), maximum = readStamina(r.methods.max, target);
            const owner = staminaOwner(r, false);
            requireValue(ptr(r.dictionary).add(0x2c).readS32() === ((resourceVersion + 1) | 0),
                'Current resource dictionary changed beyond the one reviewed set_Item');
            requireValue(maximum > 0 && maximum <= 1000000 && after >= RESOURCE_OPERATIONS[request.operation].minimum && after <= maximum &&
                floatBits(after) === floatBits(r.value) && hexAt(owner.entry, 4) === floatBits(r.value),
                '精力方法已返回，但读回不一致；禁止重复执行。');
            finish('completed', { called: true, thread_id: Process.getCurrentThreadId(), result: true,
                before: r.before, value: after, maximum: maximum, identity_key: r.identity_key, resource_key: r.resource_key });
        } else if (currency) {
            samePointer(bag.add(16).readPointer(), request.player, 'Currency bag owner changed after AddItem');
            samePointer(result, currency.config, 'Currency AddItem returned another configuration');
            const after = currencyBalance(bag, false);
            requireValue(after.matches === 1 && after.total === currency.before + request.quantity &&
                after.total <= currency.maximum, 'Currency quantity was not confirmed after AddItem; never retry');
            finish('completed', { called:true, thread_id:Process.getCurrentThreadId(), result:result.toString(),
                before:currency.before, after:after.total, currency_verified:true, maximum:currency.maximum });
        } else {
            finish('completed', { called: true, thread_id: Process.getCurrentThreadId(), result: result.toString() });
        }
    } catch (e) {
        // finish() records the result before sending it. A transport exception
        // after a completed native call must never turn into a safe refusal.
        const called = state === 'running' || Boolean(terminal && terminal.called === true);
        finish(called ? 'unknown' : 'rejected', { called: called, reason: String(e) });
    }
}
rpc.exports = {
    submit(value) {
        if (state !== 'idle') throw new Error('This bridge accepts exactly one request');
        if (Process.arch !== 'x64' || Process.platform !== 'windows') throw new Error('Unexpected process architecture');
        const update = reviewedUpdate();
        if (!value.token || !Array.isArray(value.anchors) || value.anchors.length === 0) throw new Error('Missing request identity');
        if (!OPERATIONS.includes(value.operation)) throw new Error('Unsupported operation');
        if (!Number.isFinite(value.deadline) || value.anchors.length > 20000) throw new Error('Invalid request bounds');
        for (const a of value.anchors) {
            if (!Number.isInteger(a.size) || a.size < 1 || a.size > 4096 ||
                typeof a.expected_hex !== 'string' || !/^[0-9a-f]+$/.test(a.expected_hex) ||
                a.expected_hex.length !== a.size * 2) throw new Error('Invalid request anchor');
        }
        if (usedTokens.has(value.token)) throw new Error('This request token was already used');
        usedTokens.add(value.token);
        request = value;
        coverageRequest = null; coverageAnchors = null; coverageCount = -1; coverageRanges = [];
        state = 'pending';
        expiry = setTimeout(function () {
            if (state === 'pending') finish('cancelled', { called: false, reason: '等待主线程超时；未调用游戏方法。' });
        }, Math.max(1, Math.min(10000, request.deadline - Date.now())));
        listener = Interceptor.attach(update, { onEnter() { execute(); } });
        return { token: request.token, status: state };
    },
    reset(previousToken) {
        if (!request || request.token !== previousToken) throw new Error('Previous request token differs');
        if (!['completed', 'rejected', 'cancelled'].includes(state) || listener !== null || expiry !== null) {
            throw new Error('Previous request is not safely terminal');
        }
        request = null;
        coverageRequest = null; coverageAnchors = null; coverageCount = -1; coverageRanges = [];
        terminal = null;
        state = 'idle';
        return { status: state };
    },
    cancel() {
        if (state === 'pending') finish('cancelled', { called: false, reason: '请求已取消，未调用游戏方法。' });
        return terminal || { token: request ? request.token : null, status: state };
    },
    status() { return terminal || { token: request ? request.token : null, status: state,
        ...(state === 'idle' ? { operations: OPERATIONS.slice() } : {}) }; }
};
