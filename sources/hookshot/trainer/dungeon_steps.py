"""Authored base-dungeon progression, bound to the installed RomFS at build time.

No coordinates or save hashes are guessed. MQ scenes are deliberately excluded.
The local actor, logic and GameData tables remain the identity authority.
"""
from pathlib import Path
import json
import re

DUNGEONS = (
    "InsideTheDekuTree", "DodongoCavern", "InsideJabuJabuBelly", "ForestTemple",
    "FireTemple", "WaterTemple", "ShadowTemple", "SpiritTemple", "BottomOfTheWell",
    "IceCavern", "GerudoTrainingGround", "InsideGanonCastle",
)

# Original Chinese instructions. Sources verify puzzle mechanics, while hashes,
# actor types, heights, rooms and save predicates are checked locally below.
SOURCE_PAGES = dict(zip(DUNGEONS, (2, 6, 9, 12, 15, 17, 18, 21, 13, 16, 22, 24)))
MODERN_GUIDES = {
    "InsideJabuJabuBelly": "lord-jabu-jabu-belly-walkthrough-switch-2",
    "FireTemple": "fire-temple-walkthrough-switch-2",
    "WaterTemple": "water-temple-walkthrough-switch-2",
    "ShadowTemple": "shadow-temple-walkthrough-switch-2",
    "SpiritTemple": "spirit-temple-walkthrough-twinrova-switch-2",
}
# This chest moves with ForestTemple_Room11_RoomSpin. Its AiGroup also owns
# the three room-11 AirWallEnemy actors; it intentionally has no default room.
ROOM_OVERRIDES = {("ForestTemple", 0x49a3d494a379b083): 11}


def S(actor, gyaml, action, detail, complete, transition="", age=0, prereqs=(), superseded_by=()):
    return dict(actor=int(actor, 16), gyaml=gyaml, action=action, detail=detail,
                complete=(complete,) if isinstance(complete, str) else tuple(complete),
                transition=transition, age=age, prereqs=tuple(prereqs),
                superseded_by=tuple(int(value, 16) for value in superseded_by))


STEPS = {
"InsideTheDekuTree": [
    S("c147069f8aab36c8", "DungeonRoomCenterAnchor", "反弹德库果开门", "从大厅沿梯子到上层侧门，举盾反弹德库果，追上它交谈，再进里间。", "InsideTheDekuTree_RoomB_Cleared", "沿大厅梯子向上", 1),
    S("0b66198d17d6584e", "Obj_TBox_A_02", "取得妖精弹弓", "越过侧室平台开大宝箱；回程射落悬挂梯子，再回大厅。", "IsGet.Weapon_Range_SlingShot", age=1),
    S("03de66423437a955", "Obj_InsideTheDekuTree_SpiderWeb_A_01", "从高处冲破大厅蛛网", "射掉藤蔓上的蜘蛛，爬到大厅高层；站稳后朝中央蛛网跳下，落到地下。", "InsideTheDekuTree_RoomA_Cleared", "先爬高层，再跳落地下", 1),
    S("6bc084a0a8fd372d", "Obj_InsideTheDekuTree_SpiderWeb_A_02", "烧开地下侧门蛛网", "踩地下平台的开关取得火源，用点燃的德库棒沿浅水处过池，烧开门前蛛网。", "InsideTheDekuTree_RoomE_Cleared", age=1),
    S("90c9a2c3a5351e2f", "Obj_EyeSwitch_A_02", "射眼睛机关", "反弹德库果并听取次序提示，然后用弹弓射门上眼睛，进入水池房。", "InsideTheDekuTree_RoomF_Cleared", age=1),
    S("5fc823393e3eed90", "Obj_DiveSwitch_A_01", "潜水踩开关过水池", "潜到水下踩机关，水位降低后乘移动平台躲过横杆；到对岸推箱子登高。", "InsideTheDekuTree_RoomG_Cleared", "潜到水下机关，再乘平台到对岸", 1),
    S("431cae588d121ddf", "Obj_CandleStick_TimeExtinguish_A_01", "点亮火把开门", "把火传到室内未点燃的火把，打开出口；保留德库棒继续烧网。", "InsideTheDekuTree_RoomH_Cleared", age=1),
    S("070e7c2721e7bc62", "Obj_InsideTheDekuTree_SpiderWeb_A_02", "烧网穿过小洞", "清掉挡路蜘蛛，烧开通往小洞的蛛网，从低矮通道回地下大厅上沿。", "InsideTheDekuTree_RoomI_Cleared", age=1),
    S("7fec388ff47465ad", "Obj_InsideTheDekuTree_SpiderWeb_A_01", "烧穿第二张地网", "把箱子推下形成回路，取火后回到地网边，把燃烧的德库棒贴近地网，跳到下一层。", "InsideTheDekuTree_RoomE_Cleared02", "地下大厅上沿 → 更低的水池", 1),
    S("eb15dea71838d33d", "Scrub_Deku_Brothers_Manager", "按中右左反弹德库果", "面对三兄弟，依次处理中间、右边、左边；追上最后一个交谈，打开首领通路。", "InsideTheDekuTree_RoomK_Cleared", age=1),
    S("d45e52e43b253151", "Enemy_DungeonBoss_Gohma", "击败哥玛", "眼睛变红时用弹弓打晕，靠近挥剑；战后收取心之容器并进入光圈。", "HavePlayedEvent.Dm_Deku_BossOut", age=1),
],
"DodongoCavern": [
    S("164debd890fb06cf", "Obj_Stepswitch_A_03", "压住右路开关", "用炸弹花炸开大厅右侧堵墙，穿过小多东哥通道，把石像推到地面开关上。", "DodongoCavern_StepSwitch_04", age=1),
    S("9cbd9c524b24df87", "Enemy_MiddleBoss_Lizalfos", "打败第一组蜥蜴战士", "沿右侧门深入，两个蜥蜴战士都击败后，再穿门去火把房。", "Gimmick_DefeatEnemy_Open_DodongoCave_01", age=1),
    S("6bc6ef87beffba2a", "Obj_CandleStick_TimeExtinguish_A_01", "点亮多东哥房火把", "绕到多东哥尾部攻击；清出路线后用德库棒连续传火，打开返回大厅的门。", "DodongoCavern_CandleStick", age=1),
    S("339dc37878c8ea54", "Obj_StepSwitch_A_01", "打开大厅另一侧", "从侧门回大厅，在高台踩开关，再跨平台到大厅另一侧的楼梯房。", "DodongoCavern_StepSwitch_01", age=1),
    S("c09a2426624b394a", "Obj_StepSwitch_A_01", "炸下阶梯并上楼", "把炸弹花放在两排炸花之间的缺口，引爆后沿下降的阶梯上楼；移开挡梯石像，爬梯踩开关。", "DodongoCavern_StepSwitch_02", "炸花阶梯 → 上层吊桥", 1),
    S("155ce1b2ba5028cf", "Enemy_MiddleBoss_Lizalfos", "通过眼睛机关与第二场战斗", "过吊桥和活动刀刃，炸开高处裂墙；射眼睛暂时熄火，继续击败第二组蜥蜴战士。", ("DodongoCavern_Lizalfos_C_Dead", "DodongoCavern_Lizalfos_D_Dead"), age=1),
    S("a8c7127dd81a8bb9", "Obj_TBox_A_02", "取得炸弹袋", "依次射击两处眼睛机关跨过火台，沿上层通道开大宝箱，取得炸弹袋。", "IsGet.Item_BombBag_Small", age=1),
    S("51ec52c60e8710ab", "Obj_DodongoCave_HugeBone_A_01", "炸亮巨像双眼", "站在巨像上方桥面的两处缺口，分别往左右眼窝投入炸弹；两眼亮起后回大厅下层进入嘴巴。", ("DodongoCavern_BlastedLeftEye", "DodongoCavern_BlastedRightEye"), "上层桥面投弹 → 大厅下层巨口", 1),
    S("f9ffde0455765d4e", "Obj_Stepswitch_A_03", "推箱压住首领门机关", "进巨口后沿右侧绕行，爬箱子走高台，把尽头箱子推入中央凹槽压住开关。", "DodongoCavern_StepSwitch_05", age=1),
    S("c3d76ab0a14ad852", "Enemy_DungeonBoss_Dodongo", "击败多东哥王", "炸开首领前房地板并落下；它吸气时投弹入嘴，倒下后挥剑，滚动时避到安全边缘。战后进入光圈。", "HavePlayedEvent.Dm_DodongoCave_BossOut", "炸开地板 → 首领下层", 1),
],
"InsideJabuJabuBelly": [
    S("cb9b5b7cae7bb261", "Npc_Zora_Ruto_Child_001", "进入地洞房找露朵", "用弹弓射入口天花板肉瘤开门；过水母房继续向前，与露朵交谈并跟随她落入地洞。", "HavePlayedEvent.Get_StoneOfWater_MeetRuto", "入口层 → 露朵落下的地下层", 1),
    S("20c87097e064ff06", "DungeonRoomCenterAnchor", "抱露朵过地下水池", "在下层与露朵反复交谈后抱起她；把她先扔到水池对岸，再踩池底机关升水，过去抱回她。", "InsideJabuJabuBelly_Room14_IsLutoGimmickClear", "地下水池 → 升水到对岸", 1),
    S("4cb5467d30e9d84a", "Obj_TBox_A_02_NoBake", "取得回旋镖", "抱露朵乘浮台回入口层，穿过地洞房到分岔；与她一起压开需要重量的门，清掉飞鱼开宝箱。", "IsGet.Item_Boomerang", "地下浮台 → 分岔层", 1),
    S("15e6223d49a03d63", "Enemy_Tentacle_Red", "切断红触手", "把露朵放在需要持续压住的开关上，进门用回旋镖打触手细处，避开下砸后重复攻击。", "InsideJabuJabuBelly_Enemy_Tentacle_Red_Defeat", age=1),
    S("e3de86ad3e5f9078", "Enemy_Tentacle_Blue", "切断蓝触手", "回分岔取回露朵，沿新开放路线去蓝触手房；用回旋镖攻击细处。", "InsideJabuJabuBelly_Enemy_Tentacle_Blue_Defeat", age=1),
    S("00318ae0175d94a1", "Enemy_Tentacle_Green", "切断绿触手", "从分岔进入最后开放的触手房，清掉水母并用回旋镖切断绿触手。", "InsideJabuJabuBelly_Enemy_Tentacle_Green_Defeat", age=1),
    S("e86cb93bc02db550", "Enemy_MiddleBoss_BigOcto", "带露朵下洞并打大章鱼", "抱露朵回地洞房，从触手消失后的洞落下；把她扔到中央台。用回旋镖定住大章鱼，绕到背后攻击。", "Get_StoneOfWater_BigOctoDefeat", "地洞层 → 大章鱼下层 → 中央台上升", 1),
    S("5ea983f8eb855557", "Obj_InsideJabu_Jabu_StepSwitch_A_03", "压箱打开上层门", "乘中央台上升，回旋镖定住摇晃平台后逐个通过；回升降房上沿，把木箱放在开关上。", "InsideJabuJabuBelly_Gimmick_Onswitch_first", "中首领房升降台 → 上层平台", 1),
    S("4aa3bab028173f0f", "Enemy_DungeonBoss_Barinade", "绕过隔板机关并击败首领", "爬藤蔓后让回旋镖绕过透明隔板击中天花板肉瘤，进入首领房；先断触手和水母，再打晕本体挥剑。", "HavePlayedEvent.Dm_InsideJabu_Jabu_BossOut", age=1),
],
"ForestTemple": [
    S("1041dd4d83575dda", "Obj_TBox_A_01", "取入口树上钥匙", "在入口庭院爬藤蔓到树干高处，用钩索越到宝箱一侧，拿第一把小钥匙。", "ForestTemple_Room00_GetSmallKey", "入口庭院地面 → 树上", 2),
    S("cd11547d5a93dbf6", "Obj_TBox_A_01_NoBake", "清骷髅战士取钥匙", "穿过四火大厅正前方通道，打败骷髅战士，打开出现的小钥匙宝箱。", "ForestTemple_Room06_GetSmallKey", age=2),
    S("2c19226262a217cb", "Obj_StepSwitch_A_01", "到庭院高台降井水", "用时之歌移开挡路方块，进庭院爬藤蔓穿侧室；用钩索到另一侧阳台踩开关。", "ForestTemple_Room07_Cleard", "庭院爬藤蔓 → 高台", 2),
    S("5982ecccbb376369", "Obj_TBox_A_01", "下井取小钥匙", "水位下降后沿井边梯子下到井底，穿水道开宝箱，再沿梯子回大厅。", "ForestTemple_Room09_GetSmallKey", "庭院井口 → 井底 → 庭院", 2),
    # The native bow chest proves the player has progressed beyond this climb,
    # including a flight bypass. It does NOT prove either box/door was operated.
    S("3cbef3aacc759fed", "DungeonRoomCenterAnchor", "推方块搭出登高路线", "从大厅锁门进方块房，按地面箭头推拉两层方块；先腾出梯子，再把方块推入槽形成向上台阶。", ("ForestTemple_Room11_MovableBox_Cleard1", "ForestTemple_Room11_MovableBox_Cleard2"), "方块房下层 → 上层扭曲走廊", 2, superseded_by=("99cc40ac3c369908",)),
    S("99cc40ac3c369908", "Obj_TBox_A_02_NoBake", "取得妖精弓", "穿过扭曲走廊和楼梯，击败房内所有骷髅战士；最后一组须迅速全部解决，再开大宝箱。", "ForestTemple_Room06_GetBow", age=2),
    S("2fa5e3dfba115737", "Obj_TBox_A_01_NoBake", "击败红幽灵取钥匙", "在红色画框楼梯间保持距离射画中幽灵，逼它现身后战斗；开宝箱取钥匙。", "ForestTemple_Room12_GetSmallKey", age=2),
    S("c94fd798679e0e29", "Obj_ForestTemple_SwitchCandleStick_A_04", "找回蓝色火焰", "穿过弓房去另一侧楼梯，射蓝色画框逼幽灵现身并击败它。", "ForestTemple_DefeatBeth", age=2),
    S("49a3d494a379b083", "Obj_TBox_A_03_NoBake", "扭直走廊取首领钥匙", "返回方块房上方，用弓射走廊入口的眼睛使走廊变直；进尽头房下到宝箱处取首领钥匙。", "ForestTemple_Room23_GetBossKey", "变直走廊 → 尽头房下层", 2),
    S("68922f37569af70b", "Obj_TBox_A_01_NoBake", "沿庭院支路补钥匙", "从首领钥匙房的洞落下，清敌后走庭院阳台侧门，击败手怪并开小钥匙宝箱。", "ForestTemple_Room18_GetSmallKey", "钥匙房落洞 → 庭院阳台", 2),
    S("548abfbf66468c00", "Obj_ForestTemple_SwitchCandleStick_A_03", "过落顶房找回绿火", "恢复西走廊的扭曲状态，穿过东侧锁门；借火把射融冰眼机关，落入天花板房，避开落顶并拼好幽灵方块后战斗。", "ForestTemple_DefeatAmy", "东扭曲走廊落洞 → 落顶房", 2),
    S("daa00fb5d8406818", "Enemy_MiddleBoss_Poe_Meg", "辨认真幽灵启动升降台", "回大厅面对四个分身，射最先旋转的真身，重复击败最后的幽灵。", "ForestTemple_DefeatMeg", age=2),
    S("07fe74ca40882a0b", "Enemy_DungeonBoss_PhantomGanon", "转动地下房间并击败首领", "乘大厅中央台下楼，推动转墙并踩齐开关，进首领房；先射出画的真身，再用剑回击魔法球。", "HavePlayedEvent.Dm_ForestTemple_BossOut", "大厅中央升降台 → 地下旋转房", 2),
],
"FireTemple": [
    S("4e328fd6ca19fe0e", "Obj_TBox_A_01", "救首个鼓隆取钥匙", "入口上楼走左门见达鲁尼亚，沿岩浆池边平台到牢门开关，救人并开宝箱。", "FireTemple_GetSmallKey_01", age=2),
    S("36cf66ad4f0b9d14", "Obj_TBox_A_01", "搜岩浆桥一侧牢房", "回入口走另一扇门，检查岩浆桥一侧的洞穴，打开牢门取得小钥匙。", "FireTemple_GetSmallKey_02", age=2),
    S("17a99b8b3e705af7", "Obj_TBox_A_01", "炸开桥另一侧救人", "检查岩浆桥另一侧的裂墙，炸开后进门救鼓隆，开宝箱补齐继续深入的钥匙。", "FireTemple_GetSmallKey_03", age=2),
    S("ae686b6127c55811", "Obj_TBox_A_01", "登岩浆喷柱进入滚石房", "用钥匙到喷柱房，推方块到喷口并乘它上升；爬铁网，过机关后在滚石房寻找牢房钥匙。", "FireTemple_GetSmallKey_04", "喷柱托方块 → 上层铁网 → 滚石房", 2),
    S("b3a812edc57747ca", "Obj_TBox_A_01", "救滚石区另一名鼓隆", "沿滚石房外围通路找另一处牢房，踩机关救人，开宝箱后继续去上层。", "FireTemple_GetSmallKey_05", age=2),
    S("9203677a1637eb0b", "Obj_TBox_A_01", "从上层裂地板下去救人", "由高处通道回滚石区上沿，炸开裂地板，沿露出的梯子下去开牢门取钥匙。", "FireTemple_GetSmallKey_06", "滚石房上沿裂口 → 下层牢房", 2),
    S("85b620f58f55317a", "Obj_TBox_A_01", "跨高台取下一把钥匙", "返回滚石房上沿，沿高台到开关与牢房，打开宝箱；不要从高台直接跳回低层。", "FireTemple_GetSmallKey_07", age=2),
    S("e8f2b9202396f6ec", "Obj_TBox_A_01", "穿火墙迷宫救鼓隆", "沿锁门通道穿过火墙区，留意假门和限时熄火开关，救出侧室鼓隆取得钥匙。", "FireTemple_GetSmallKey_08", age=2),
    S("a7b05ca3e496906e", "Obj_TBox_A_02", "取得大铁锤", "钩索拉出火焰舞者核心并击败；乘平台上行，经过限时阶梯，踩熄火机关后沿窄路到大宝箱。", "FireTemple_GetHammer", "火焰舞者中央平台 → 高层限时阶梯", 2),
    S("c31f81a17795f048", "Obj_TBox_A_03", "用铁锤开回路取首领钥匙", "沿新路线用铁锤砸落柱块和生锈开关，回入口打通被图腾挡住的支路，清敌救人，开首领钥匙宝箱。", "DungeonInfo.FireTemple.IsGetBossKey", "砸落柱块逐层下行 → 入口侧路", 2),
    S("1dff24cca5b5835f", "Enemy_DungeonBoss_Volvagia", "击败瓦尔巴吉亚", "用铁锤完成首领前平台回路；首领从洞里探头时打晕并挥剑，腾空时躲火焰和落石，战后进光圈。", "HavePlayedEvent.Dm_FireTemple_BossOut", age=2),
],
"WaterTemple": [
    S("18802235d7fea602", "Obj_WaterTemple_StoneTablet_A_01", "跟露朵上浮并降低水位", "穿重铁靴到大厅底层找露朵，脱靴沿竖井浮到顶，在王族标记前吹摇篮曲把水降到底。", "HavePlayedEvent.WaterTemple_WaterLevelChange01", "底层露朵竖井 → 顶部水位标记", 2),
    S("fb2ca21db0a9d839", "Obj_TBox_A_01_NoBake", "底层点火清敌取钥匙", "回刚刚竖井底部点燃门边火把，进入侧室打败贝壳敌人，开小钥匙宝箱。", "WaterTemple_Room18_Cleared", "竖井顶部 → 底层", 2),
    S("22bf8064463f9175", "Obj_TBox_A_01", "探索低水位侧道", "低水位下检查底层支路，推拉方块、用钩索过水池机关，在侧道尽头收取小钥匙。", "WaterTemple_Room08_Cleared", age=2),
    S("c29a8885a52ee860", "Obj_WaterTemple_StoneTablet_A_03", "中央塔升到中水位", "用钥匙进中央塔，转身向上用钩索登台，在王族标记前吹摇篮曲升到中水位。当前版本塔底支路是红卢比与收集品，不是主线小钥匙。", "HavePlayedEvent.WaterTemple_WaterLevelChange02", "中央塔底层 → 中层王族标记", 2),
    S("e4d909e591e99f8d", "Obj_TBox_A_01", "中层东侧喷柱取钥匙", "从大厅中层东侧炸开裂墙，穿铁靴过水道；射开关降下喷柱盖，站上去再射开关，升到高处开小钥匙宝箱。", "WaterTemple_Room04_TBox_Open", "中层东水道 → 喷柱托盖上升", 2),
    S("4974202072beaec6", "Enemy_MiddleBoss_DarkLink", "高水位深入并打黑暗林克", "在第三处王族标记升到高水位，过落水平台和钩索机关房；进入倒影房后到树旁触发黑暗林克，稳住节奏攻击。", "WaterTemple_Room22_Cleared", "高水位大厅 → 西侧高层通道", 2),
    S("faa0fc3748e1cbfd", "Obj_TBox_A_02", "取得长钩索", "击败黑暗林克后从新开的出口进入后室，开大宝箱取得长钩索。", "IsGet.Item_Longshot", age=2),
    S("33437a1475511b03", "Obj_TBox_A_01", "中水位北路取最后小钥匙", "走长钩索后室的回流水道回大厅，降水后再升到中水位；射北侧眼睛并长钩索过栅栏，走水道拉出再从侧面推开方块，登上原方块位置取钥匙。", "WaterTemple_Room20_Cleared", "回流下层 → 中水位北侧 → 水下推拉方块", 2),
    S("900901699af3b852", "Obj_TBox_A_03", "绕回流水道取首领钥匙", "移开长钩索宝箱后的时之方块，顺水道避开漩涡；用长钩索通过远处抓点，搜钥匙与岩石水道，进入首领钥匙室。", "DungeonInfo.WaterTemple.IsGetBossKey", "长钩索后室落洞 → 回流水道 → 首领钥匙支路", 2),
    S("ffcd72146bf02283", "Enemy_DungeonBoss_Morpha", "回最高水位打莫法", "把水调到最高，从大厅三层登首领门坡道；站岸边用长钩索拉出核心再挥剑，避开水触手抓取，战后进光圈。", "HavePlayedEvent.Dm_WaterTemple_BossOut", "大厅三层 → 首领门坡道", 2),
],
"ShadowTemple": [
    S("c9b6fa7844300a71", "Obj_TBox_A_02_NoBake", "先取悬浮靴", "用真实之眼辨认入口假墙，沿侧路打败死手，开大宝箱取得悬浮靴。", "IsGet.Armor_Adult_HoverBoot", age=2),
    S("8ea1244fbc64dde5", "DungeonRoomCenterAnchor", "调整鸟像越过大缺口", "用真实之眼找真正骷髅标记，把鸟嘴对准它开门；穿悬浮靴越过缺口，继续下行。", "ShadowTemple_RoomB1FEntrance_Cleared", "入口层悬浮越沟 → 下层通道", 2),
    S("0f6d9d21b4856e49", "Obj_TBox_A_01", "旋转刀房取小钥匙", "炸开通路里的假墙，检查旋转刀房并收齐银卢比；在打开的侧室取得小钥匙。", "ShadowTemple_RoomB2FC_Cleared", age=2),
    S("503da0706624f6da", "Obj_TBox_A_01", "用石块挡住刺板取钥匙", "穿过铡刀与深坑，真实之眼找到可推石块；用它撑住落下刺板，登到上面开钥匙宝箱。", "ShadowTemple_RoomB3FB4FC_Cleared", "铡刀深坑 → 刺板房上方", 2),
    S("924dcaccfe20295d", "DungeonRoomCenterAnchor", "清银卢比与隐形平台", "真实之眼查看平台、尖刺和抓点，收齐银卢比，按打开的门继续搜集通行钥匙。", "ShadowTemple_RoomB3FB4FE_Cleared_All", age=2),
    S("0258b24f2ac0a365", "Obj_TBox_GlassTruth_A_01", "穿风扇通道找隐形钥匙", "强风处穿重铁靴站稳，用真实之眼辨认暗门和隐形宝箱，取得通往船坞的小钥匙。", "ShadowTemple_RoomB3FB4FI_Cleared", age=2),
    # Departure is SaveFileIndex=-1; the persistent boss-key chest is ashore.
    S("1d6ec3b2f9813de8", "DungeonRoomCenterAnchor", "吹摇篮曲乘船", "上船到王族标记吹摇篮曲；航行时处理骷髅战士，船到终点开始下沉前跳向岸边。", "ShadowTemple_RoomB3FB4FJ_Departure", "船坞上船 → 河道尽头跳岸", 2, superseded_by=("7ff8df2fa8e85da9",)),
    S("f872a2d9f751b318", "Obj_TBox_A_01_NoBake", "清手怪取得末段钥匙", "到岸后用真实之眼探索墙后支路，击败分裂手怪并清掉小手，开小钥匙宝箱。", "ShadowTemple_RoomB3FB4FL_Cleared", age=2),
    S("7ff8df2fa8e85da9", "Obj_TBox_A_03", "烧木刺墙取首领钥匙", "到夹墙房，用火焰魔法烧掉合拢的木刺墙，开大锁宝箱取得首领钥匙。", "DungeonInfo.ShadowTemple.IsGetBossKey", age=2),
    S("b5f923c2b1a2c646", "Enemy_DungeonBoss_BongoBongo", "炸倒石像造桥并打首领", "射对岸炸花使石像倒下成桥；用真实之眼与悬浮靴过最后平台，落入首领场。先射双手，再看清本体射眼，靠近攻击。", "HavePlayedEvent.Dm_ShadowTemple_BossOut", "石像桥 → 隐形平台 → 首领地底", 2),
],
"SpiritTemple": [
    S("5e3336b584f8d410", "DungeonRoomCenterAnchor", "幼年钻洞清开入口", "幼年与娜波露交谈后钻左侧小洞，击败石像和蝙蝠，开启两侧通道。", "SpiritTemple_Room02_Unlocked", age=1),
    S("4f26a195e1a40726", "Obj_TBox_A_01_NoBake", "回旋镖架桥并取钥匙", "用回旋镖绕过隔板打机关；借火焰消灭镜像移动的敌人，收银卢比并点燃火把，开钥匙宝箱。", "SpiritTemple_Room05_TBox_On", age=1),
    S("bae7c75f776b1a94", "DungeonRoomCenterAnchor", "炸开高墙引入日光", "用钥匙进中央小洞后的门，爬到上层；清敌，使用炸弹鼠炸开高处裂墙，让日光照到太阳机关。", "HavePlayedEvent.SpiritTemple_Level_Room_07_SunSwitchOn", "幼年入口小洞 → 攀墙上层", 1),
    S("f19252eeb3665718", "Obj_TBox_A_01_NoBake", "巨像上层解太阳方块", "沿巨像大厅阶梯上行，把石像推下压开关；下一房间收齐银卢比，推太阳方块到光束中，拿钥匙继续上楼。", "SpiritTemple_Room10_Unlocked", "巨像大厅 → 上层太阳房", 1),
    S("7eb394786bc466be", "DungeonRoomCenterAnchor", "击败幼年铁甲战士拿银手套", "等铁甲战士挥斧后从侧面反击；胜利后沿出口到室外开银手套宝箱，再回时之神殿变成年。", "IsGet.Armor_Adult_Gauntlet_Silver", "幼年铁甲战士房 → 室外宝箱 → 变成年", 1),
    S("3b5e6ea69d7d2458", "Obj_TBox_A_01", "成年推巨石并收钥匙", "成年回入口推右侧巨石，击中天花板机关；探索滚石银卢比房，移开时之方块收齐后到侧室取钥匙。", "SpiritTemple_Room17_TBox_Open", age=2),
    S("395fab44dc898619", "Obj_SpiritTemple_CapstanMirror_A_01", "转镜开路到巨像大厅", "用钥匙进中央门并攀墙，真实之眼找隐形手怪；旋转镜子照正确太阳，开门回巨像大厅。", "HavePlayedEvent.SpiritTemple_Room19_SunSwitchShutterOpen", "成年入口 → 攀墙到镜子房 → 巨像上层", 2),
    S("1e937e4a772e9fb3", "Obj_TBox_A_01_NoBake", "巨像手掌吹歌取钥匙", "沿阶梯到巨像手掌的王族标记，吹摇篮曲；钩索到另一只手掌打开小钥匙宝箱，再回上层锁门。", "SpiritTemple_Room08_TBox_On_03", "巨像上层阶梯 → 手掌 → 对侧手掌", 2),
    S("5ca47662c24e0bbf", "DungeonRoomCenterAnchor", "取得镜盾", "在巨像手掌王族标记吹摇篮曲取钥匙；穿过火焰敌人房，诱石像压开关，打败第二名铁甲战士后到室外踩开关取镜盾。", "IsGet.Weapon_Shield_Mirror", "巨像手掌 → 上层铁甲战士房 → 室外", 2),
    S("a71e7700463b4bb5", "Obj_TBox_A_01", "反射日光取小钥匙", "带镜盾回刚才需要石像压开关的房间，站在光束下把光反到墙上太阳，开门取钥匙。", "SpiritTemple_Room27_TBox_Open", age=2),
    S("e1d25a9ccd2acdfe", "Obj_TBox_A_03", "攀移动墙取首领钥匙", "用钥匙进入滑动墙房，钩索与攀爬交替登顶；吹摇篮曲开门，破坏假门露眼睛机关，再踩上层开关熄火取首领钥匙。", "DungeonInfo.SpiritTemple.IsGetBossKey", "移动墙低层 → 顶层首领钥匙房", 2),
    S("19f0f5ef3fc8c73e", "Obj_SpiritTemple_Mirror_A_01", "接通镜光并降中央台", "到大镜子房击中开关，炸开旁室裂墙并转动两面镜子，把光送回大镜子；用镜盾照太阳使平台下降，再照巨像脸部开路。", "SpiritTemple_Room31_LightHit_After", "顶部镜室 → 降下巨像大厅平台", 2),
    S("fb4f8981d2886b8c", "Enemy_DungeonBoss_Twinrova", "解救娜波露并击败双生魔女", "钩索到巨像脸部首领门，击败铁甲战士后进入最终场。分体时把一方光束反给另一方；合体后连续吸收三次同属性，再反射并挥剑。", "HavePlayedEvent.Dm_SpiritTemple_BossOut", age=2),
],
"BottomOfTheWell": [
    S("3a200c2c366fc060", "Obj_TriForcePoint_A_10", "幼年入井并排水", "幼年穿过入口假墙，沿环廊到水源前王族标记，吹摇篮曲排干入口附近水坑。", "BottomOfTheWell_Room_01_WaterLevel_Down", age=1),
    S("e721a50e0511d8be", "Obj_TBox_A_02_NoBake", "钻低洞打死手拿真实之眼", "回入口附近排干的水坑，下梯后钻小洞，打败死手开大宝箱。真实之眼到手后本轮主线目标完成，可原路离开。", "IsGet.Armor_GlassTruth", "环廊入口坑 → 下梯钻小洞", 1),
],
"IceCavern": [
    S("40bdb23e7c130135", "DungeonRoomCenterAnchor", "清入口冰怪", "带空瓶入洞，清掉第一间的冰怪，避开落冰，沿开门后的道路到旋转冰刃房。", "IceCavern_Room01_Unlocked", age=2),
    S("af0a7a17099f8d19", "Obj_silverRupeeCounter_03", "收旋转冰刃房银卢比", "沿地面、边台和高处收齐银卢比，避开旋转冰刃；进开门支路，用空瓶装蓝火。", "IceCavern_Room05_Unlocked", age=2),
    S("5f311732ca6be0f4", "Obj_TBox_A_02_NoBake", "推冰块过房取重铁靴", "蓝火融红冰打开方块房路线；推冰块当踏脚石收银卢比，掉下可重置。用蓝火开末段道路，击败白狼后开宝箱，与希克完成对话。", "IsGet.Armor_Adult_HeavyBoot", "推冰块登高 → 深处白狼房", 2),
],
"GerudoTrainingGround": [
    S("bb5ea265515c11c0", "Obj_TBox_A_01_NoBake", "左门清敌拿钥匙", "从大厅左门开始，在限时内清掉骷髅战士，开出现的小钥匙宝箱。训练场可选，保留钥匙用于最后的锁门迷宫。", "GerudoTrainingGround_Room01_AllTBoxOpen", age=2),
    S("814dda3c79fe061c", "DungeonRoomCenterAnchor", "过滚石银卢比试炼", "沿左路收银卢比，钩索够到高处并躲滚石；收齐后继续走开放的门。", "GerudoTrainingGround_Dungeon_Room02_SilverRupee", age=2),
    S("49f747e3fdb01997", "Obj_TBox_GlassTruth_A_01", "用力量和真实之眼找钥匙", "清狼群，银手套推开大方块；真实之眼找暗道和隐形宝箱，清敌后取得隐藏小钥匙。", "GerudoTrainingGround_Room10_AllTBoxOpen", age=2),
    S("a079b1b091faf40f", "Obj_TBox_A_01", "射转盘眼睛拿钥匙", "站转盘上依次射亮石像眼睛，门打开后沿通路取钥匙；不要急着把钥匙消耗在中央右路。", "GerudoTrainingGround_Room04_AllTBoxOpen", age=2),
    S("3cadc194d595b9a3", "Obj_TBox_A_01", "铁锤砸像开机关", "清掉房内敌人，用铁锤砸开石像露出机关，按机关路线去宝箱拿钥匙。", "GerudoTrainingGround_Room05_TBoxOpen_01", age=2),
    S("abb0cdd46e9f5aab", "DungeonRoomCenterAnchor", "收火焰平台银卢比", "利用悬浮靴、钩索和限时开关穿过火焰平台，收齐银卢比开启水下支路。", "GerudoTrainingGround_Dungeon_Room06_SilverRupee", age=2),
    S("3397f157a95cb936", "Obj_TBox_A_01_NoBake", "重铁靴完成水下房", "移开时之方块，穿卓拉服与重铁靴下水，用钩索收齐水下银卢比，再回宝箱取小钥匙。", "GerudoTrainingGround_Room09_AllTBoxOpen", "水面入口 → 水下钩索抓点 → 宝箱", 2),
    S("415c4dae2d3990cc", "Obj_TBox_A_01_NoBake", "右门清敌补钥匙", "回大厅右门，在限时内清掉敌人，开宝箱收最后一组路线所需钥匙。", "GerudoTrainingGround_Room07_AllTBoxOpen", age=2),
    S("9c89b8dc90b11fc9", "Obj_Gerudo_SwitchShutter_A_06", "从中央迷宫左侧首门进入", "带钥匙回中央锁门区，先从入口左侧第一道锁门进入。门是否已开按独立锁状态判断；笼墙内后续门需按现场通道前进。", "@chain", age=2),
    S("3bf55116610cd9f8", "Obj_TBox_A_01", "查找中央迷宫隐藏上层钥匙", "在锁门区用真实之眼检查天花板隐藏通路，沿能攀爬的墙到上层取得钥匙；若当前位置看不到入口，先回已开的通道检查。", "GerudoTrainingGround_Dungeon_Room08_TBox", "锁门迷宫 → 隐藏上层", 2),
    S("1af01d8f10ce451a", "Obj_TBox_A_02", "走中央左路取得冰箭", "进入中央锁门区，优先左路逐门前进；用真实之眼查天花板隐藏攀爬处补钥匙，开终点大宝箱取得冰箭。", "IsGet.Item_Arrow_Ice", "中央迷宫隐形顶洞可登高取钥匙", 2),
],
"InsideGanonCastle": [
    S("a5fce3eecbd89bdf", "Obj_InsideGanonCastle_Core_B_01", "解除森之屏障", "森之试炼先清敌点火，随后利用风向、铁靴与钩索收银卢比；进入末室用光之箭射核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Forest", age=2),
    S("84c85dc21d5a8f35", "Obj_InsideGanonCastle_Core_D_01", "解除水之屏障", "水之试炼装蓝火融红冰，推冰块铺出登高路；用铁锤敲开关打开末室，再以光之箭破核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Water", age=2),
    S("f50c7ad82f346cc6", "Obj_TBox_A_02_NoBake", "暗之试炼取得金手套", "用火箭或火焰点亮路线，真实之眼看隐形平台；沿平台到机关，再用钩索去出现的大宝箱取得金手套。", "IsGet.Armor_Adult_Gauntlet_Gold", age=2),
    S("7020cf871d553ac4", "Obj_InsideGanonCastle_Core_E_01", "解除暗之屏障", "继续利用火把显示的平台和真实之眼，敲击生锈开关开门，光之箭射暗之核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Shadow", age=2),
    S("72aeaccc86fc1980", "Obj_InsideGanonCastle_Core_C_01", "金手套打开火之试炼", "穿鼓隆服在岩浆平台收银卢比，用金手套搬开大柱打开路线；收齐后钩索去出口，光之箭破核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Fire", age=2),
    S("11630cd4e8d9732b", "Obj_InsideGanonCastle_Core_A_01", "解除光之屏障", "金手套移开入口巨柱，真实之眼找隐形敌人；依次取钥匙、吹摇篮曲、收银卢比，识破末端假墙后用光之箭破核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Light", age=2),
    S("ee49f72b52139023", "Obj_InsideGanonCastle_Core_F_01", "解除魂之屏障", "收银卢比开门，用炸弹鼠越过栅栏打机关；火箭烧天花板蛛网，用镜盾把日光照到正确太阳，光之箭破末室核心。", "InsideGanonCastle_Dungeon_BarrierRemove_Spirit", age=2),
    S("4e41f46b051e25f1", "DungeonRoomCenterAnchor", "进入中央塔清守卫", "六道屏障解除后走中央入口，沿塔楼阶梯逐层上行，清掉第一组守卫。", "InsideGanonCastle_Dungeon_Room20_Cleared", "六试炼大厅 → 中央塔逐层上楼", 2),
    S("b249959ceb7f0eca", "DungeonRoomCenterAnchor", "继续清塔楼守卫", "沿唯一上楼通道前进，解决下一组敌人后继续登塔。", "InsideGanonCastle_Dungeon_Room22_Cleared", "中央塔继续上楼", 2),
    S("ed345a357fd30226", "Obj_TBox_A_03_NoBake", "取得最终首领钥匙", "击败铁甲战士，开出现的大锁宝箱，拿首领钥匙后继续上楼。", "DungeonInfo.InsideGanonCastle.IsGetBossKey", age=2),
    S("db3e88762090e6bd", "Enemy_DungeonBoss_Ganondorf", "击败加侬多夫", "登到塔顶，用剑把能量球打回，晕眩时射光之箭再近身攻击。胜利后跟塞尔达下塔，后续逃离与最终战按主线提示继续。", "HavePlayedEvent.Dm_InsideGanonCastle_BossOut", "塔顶首领房 → 跟随塞尔达向下逃离", 2),
],
}


def equipment_prereqs(scene, order, step):
    """Only equipment used by the authored action; no version or file gating."""
    result = list(step["prereqs"])
    if scene == "InsideTheDekuTree" and order >= 2:
        result.append("IsGet.Weapon_Range_SlingShot")
    if scene == "DodongoCavern" and order >= 7:
        result.append("IsGet.Item_BombBag_Small")
    if scene == "InsideJabuJabuBelly" and order >= 3:
        result.append("IsGet.Item_Boomerang")
    if scene == "ForestTemple":
        result.append("IsGet.Item_Hookshot")
        if order >= 6:
            result.append("IsGet.Weapon_Range_Bow")
    if scene == "FireTemple" and order >= 9:
        result.append("IsGet.Item_Hammer")
    if scene == "WaterTemple":
        result.extend(("IsGet.Item_Hookshot", "IsGet.Armor_Adult_HeavyBoot"))
        if step["actor"] in (0x33437a1475511b03, 0x900901699af3b852, 0xffcd72146bf02283):
            result.append("IsGet.Item_Longshot")
    if scene == "ShadowTemple":
        result.append("IsGet.Armor_GlassTruth")
        if order >= 1:
            result.append("IsGet.Armor_Adult_HoverBoot")
    if scene == "SpiritTemple":
        if step["age"] == 2:
            result.append("IsGet.Armor_Adult_Gauntlet_Silver")
        if step["actor"] in (0xa71e7700463b4bb5, 0x19f0f5ef3fc8c73e, 0xfb4f8981d2886b8c):
            result.append("IsGet.Weapon_Shield_Mirror")
    if scene == "GerudoTrainingGround":
        if step["actor"] in (0x49f747e3fdb01997, 0x3bf55116610cd9f8, 0x1af01d8f10ce451a):
            result.append("IsGet.Armor_GlassTruth")
        if step["actor"] == 0x49f747e3fdb01997:
            result.append("IsGet.Armor_Adult_Gauntlet_Silver")
        if step["actor"] == 0x3cadc194d595b9a3:
            result.append("IsGet.Item_Hammer")
        if step["actor"] == 0x3397f157a95cb936:
            result.append("IsGet.Armor_Adult_HeavyBoot")
    if scene == "InsideGanonCastle":
        result.append("IsGet.Item_Arrow_Light")
        if step["actor"] in (0x72aeaccc86fc1980, 0x11630cd4e8d9732b):
            result.append("IsGet.Armor_Adult_Gauntlet_Gold")
    return tuple(dict.fromkeys(result))


def scene_evidence(rom, banc):
    actors, groups = {}, []
    for part in ("Static", "Dynamic"):
        data = rom.byml(f"Banc/{banc}/{banc}_{part}.bcett.byml.zs")
        actors.update((a["Hash"], a) for a in data.get("Actors", []))
        for group in data.get("AiGroups", []):
            path = "Logic/" + Path(group["Logic"]).name + "b"
            try:
                payload = rom.read(path)
            except FileNotFoundError:
                continue
            strings = {v.decode("ascii") for v in re.findall(rb"[\x20-\x7e]{4,}", payload)}
            groups.append((group, path, strings))
    return actors, groups


def generate_dungeon_steps(rom, output=None, regions=None):
    """Return validated steps for the twelve base scenes; optionally write JSON.

    A first-incomplete planner may use later completed steps to skip earlier
    transit instructions. It must not claim every earlier optional chest was
    opened. Boss-death cinematics prove the boss outcome, not the later warp.
    """
    from dungeon_state import GameDataIndex
    index = GameDataIndex(rom)
    maps = rom.byml("Banc/BancBasedResource/MapParam.byml.zs")
    result = []
    for scene in DUNGEONS:
        actors, groups = scene_evidence(rom, scene)
        row = maps[scene]
        floors = row.get("Floor", [])
        portal_rooms = {p["InstanceID"]: ri for ri, room in enumerate(row["Room"])
                        for p in room.get("Entrance", [])}
        prefab_rooms = {}
        for group, _, _ in groups:
            family = str(Path(group["Logic"]).parent)
            explicit = group.get("Dynamic", {}).get("DungeonRoomID")
            if explicit is not None and 0 <= explicit < len(row["Room"]):
                prefab_rooms.setdefault(family, set()).add(explicit)
            for ref in group.get("References", []):
                a = actors.get(ref["Reference"], {})
                if a.get("Gyaml") != "DungeonRoomCenterAnchor":
                    continue
                for ri, room_row in enumerate(row["Room"]):
                    if a.get("Translate") == room_row.get("CenterTrans"):
                        prefab_rooms.setdefault(family, set()).add(ri)
        for order, step in enumerate(STEPS[scene]):
            actor = actors.get(step["actor"])
            if not actor or actor["Gyaml"] != step["gyaml"]:
                raise ValueError(f"{scene} step {order+1}: target actor identity changed")
            xyz = actor.get("Translate")
            if not isinstance(xyz, list) or len(xyz) != 3:
                raise ValueError(f"{scene}: target has no real translation")
            floor = max(0, sum(xyz[1] >= floor["TransY"] for floor in floors) - 1)
            exact_floors = [i for i, f in enumerate(floors)
                            for kind in ("TBox", "Door", "EntranceAnchor")
                            for p in f.get(kind, []) if p.get("InstanceID") == actor["Hash"]]
            if exact_floors:
                floor = exact_floors[0]
            owned_rooms = set()
            for group, _, _ in groups:
                refs = group.get("References", [])
                if not any(r["Reference"] == actor["Hash"] for r in refs):
                    continue
                explicit = group.get("Dynamic", {}).get("DungeonRoomID")
                if explicit is not None and 0 <= explicit < len(row["Room"]):
                    owned_rooms.add(explicit)
                else:
                    candidates = {portal_rooms[r["Reference"]] for r in refs if r["Reference"] in portal_rooms}
                    candidates.update(actors[r["Reference"]].get("Dynamic", {}).get("DefaultDungeonRoomIndex")
                                      for r in refs if r["Reference"] in actors
                                      and 0 <= actors[r["Reference"]].get("Dynamic", {}).get("DefaultDungeonRoomIndex", -1) < len(row["Room"]))
                    if not candidates:
                        candidates.update(prefab_rooms.get(str(Path(group["Logic"]).parent), ()))
                    if len(candidates) == 1:
                        owned_rooms.update(candidates)
            default_room = actor.get("Dynamic", {}).get("DefaultDungeonRoomIndex", -1)
            room = next(iter(owned_rooms)) if len(owned_rooms) == 1 else default_room
            room = ROOM_OVERRIDES.get((scene, actor["Hash"]), room)
            if not 0 <= room < len(row["Room"]):
                raise ValueError(f"{scene} {actor['Hash']:x}: no unambiguous MapParam room")
            official = [f-row["MinFloor"] for f in row["Room"][room].get("Floor", [])]
            if len(official) == 1:
                floor = official[0]
            # Direct open-state is stronger than an 'item appeared' flag and is
            # independent of inventory manipulation outside the dungeon.
            if actor["Gyaml"].startswith("Obj_TBox"):
                complete = [index.chest_open(actor["Hash"])]
            elif step["complete"] == ("@chain",):
                complete = [index.chain_open(actor["Hash"])]
            else:
                complete = [index.condition(name) for name in step["complete"]]
            refs = [path for group, path, strings in groups
                    if any(r["Reference"] == actor["Hash"] for r in group.get("References", []))]
            predicate_refs = sorted({path for _, path, strings in groups
                                     for condition in complete if condition["name"] in strings})
            sources = [f"https://www.zeldaspalace.com/ocarinaoftime/soluce.php?p={SOURCE_PAGES[scene]}"]
            if scene in MODERN_GUIDES:
                sources += ["https://www.nintendolife.com/guides/zelda-ocarina-of-time-" + MODERN_GUIDES[scene]]
            result.append(dict(scene=scene, id=f"{scene}_{order+1:02d}", title=step["action"],
                action=step["action"], detail=step["detail"],
                target=dict(actor=actor["Hash"], gyaml=actor["Gyaml"], xyz=xyz, floor=floor,
                            room=room),
                prereqs=[index.condition(name) for name in equipment_prereqs(scene, order, step)],
                complete=complete, complete_mode="all", age=step["age"],
                superseded_by=list(step["superseded_by"]),
                transition=step["transition"], final=order == len(STEPS[scene])-1,
                evidence=dict(scene_paths=[f"Banc/{scene}/{scene}_Static.bcett.byml.zs",
                                           f"Banc/{scene}/{scene}_Dynamic.bcett.byml.zs"],
                              logic_paths=refs, predicate_logic_paths=predicate_refs,
                              predicate_table="GameData/GameDataList.Product.110.byml.zs",
                              predicate_note=("Exact IsTreasureBoxOpen actor member; value true means this chest is open"
                                              if actor["Gyaml"].startswith("Obj_TBox") else
                                              "Named typed state plus associated local logic/event; not runtime-tested"),
                              sources=sources)))
    if output is not None:
        Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def inspect_scene(rom, banc, pattern):
    actors, groups = scene_evidence(rom, banc)
    for group, path, strings in groups:
        flags = sorted(s for s in strings if re.search(pattern, s) and s.startswith(banc) and "/" not in s)
        if not flags:
            continue
        picked = []
        for ref in group.get("References", []):
            a = actors.get(ref["Reference"])
            if not a:
                continue
            g, d = a["Gyaml"], a.get("Dynamic", {})
            if g.startswith(("Obj_TBox", "Enemy_MiddleBoss", "Enemy_DungeonBoss", "Obj_StepSwitch", "Obj_EyeSwitch", "Obj_DiveSwitch", "Enemy_Tentacle", "Obj_LightSwitch", "Obj_HammerSwitch")) or any(s in g for s in ("WaterLevel", "SilverRupee", "SliderBox", "SpiderWeb_A", "CandleStick", "DodongoFace", "SpiritTemple_Mirror", "RoomCenterAnchor", "Barrier")):
                picked.append(f"{a['Hash']:016x} {g} r{d.get('DefaultDungeonRoomIndex','?')} {d.get('Drop__DropActor','')}")
        print(path.split('/')[-1], ';'.join(flags), '\n  ' + '\n  '.join(picked))


if __name__ == "__main__":
    import sys
    import argparse
    parser = argparse.ArgumentParser(description="Inspect dungeon scene state in an extracted RomFS.")
    parser.add_argument("romfs", type=Path)
    parser.add_argument("scene")
    parser.add_argument("pattern")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
    from catalog import RomFS
    class LocalRomFS(RomFS):
        def __init__(self, root):
            self.root, self.dictionaries = Path(root), {}
        def read_raw(self, path):
            return (self.root / path).read_bytes()
    rom = LocalRomFS(args.romfs)
    inspect_scene(rom, args.scene, args.pattern)
