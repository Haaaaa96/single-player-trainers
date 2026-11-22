using System;
using System.IO;
using System.Reflection;
using BepInEx;
using BepInEx.Unity.IL2CPP;
using FrameWork;
using FrameWork.Data;
using HarmonyLib;
using Script.Mrg;
using Script.Scene;
using UnityEngine;
using UnityEngine.SceneManagement;
using Xlsx;

[assembly: AssemblyVersion("1.8.2.0")]
[assembly: AssemblyInformationalVersion("1.8.2-forum.20261122.1")]

namespace RiseAlone
{
    [BepInPlugin("local.risealone.trainer","RiseAloneTrainer","1.8.2")]
    [BepInProcess("重生2我独自逆袭.exe")]
    public sealed class Plugin : BasePlugin
    {
        internal static Engine State;
        internal static bool Contacts, Events;
        internal static bool Story;
        private Harmony hooks;
        private Driver driver;
        public override void Load()
        {
            var settings=new SwitchSettings(Path.Combine(Paths.ConfigPath,"RiseAloneTrainer.switches"));
            try{settings.Load();}catch(Exception e){Log.LogWarning(e.Message);}
            State=new Engine(settings);
            hooks = new Harmony("local.risealone.trainer");
            var choiceType=typeof(TaskChoices);
            bool checkpoint=Hook(typeof(Script.Tool.VideoButton),"ClickSure",Type.EmptyTypes,nameof(TaskChoices.VideoClick),true,choiceType);
            bool taskBefore=Hook(typeof(GameDataMrg),"SetTaskData",new[]{typeof(string),typeof(TaskType)},nameof(TaskChoices.BeforeTask),true,choiceType);
            bool taskAfter=Hook(typeof(GameDataMrg),"SetTaskData",new[]{typeof(string),typeof(TaskType)},nameof(TaskChoices.AfterTask),false,choiceType);
            State.ChoiceAvailable=checkpoint && taskBefore && taskAfter;
            Hook(typeof(Script.Tool.VideoButton),"Init",new[]{typeof(string),typeof(float),typeof(VideoNode),typeof(VideoNode),typeof(ButtonNode),typeof(bool),typeof(Il2CppSystem.Action)},nameof(TaskChoices.VideoLabel),false,choiceType);
            Hook(typeof(GameScene),"PlayVideo",new[]{typeof(VideoNode),typeof(bool),typeof(bool)},nameof(TaskChoices.EnterVideo),true,choiceType);
            var chatNode=typeof(FrameWork.ChatTool.ChatNode);
            Hook(typeof(Script.Tool.ChatSelectItem),"Init",new[]{chatNode,chatNode,typeof(Il2CppSystem.Action)},nameof(TaskChoices.ChatLabel),false,choiceType);
            Hook(typeof(Script.Tool.ChatSelectItem),"OnClick",Type.EmptyTypes,nameof(TaskChoices.ChatClick),true,choiceType);
            Hook(typeof(CombatWindows),"OnClickBtn",new[]{typeof(Script.Tool.BT)},nameof(TaskChoices.CombatClick),true,choiceType);
            Hook(typeof(PhoneWindows),"InitChat",new[]{typeof(Xlsx_Message)},nameof(TaskChoices.PhoneContact),false,choiceType);
            Hook(typeof(EmailWindows),"InitChat",new[]{typeof(Xlsx_Message)},nameof(TaskChoices.EmailContact),false,choiceType);
            bool qte=Hook(typeof(Script.UiTool.QteBtn),"Update",Type.EmptyTypes,nameof(MiniGameAssist.QteUpdate),true,typeof(MiniGameAssist));
            Hook(typeof(Script.UiTool.QteBtn),"OnClick",Type.EmptyTypes,nameof(MiniGameAssist.AllowQteClick),true,typeof(MiniGameAssist));
            bool scratch=Hook(typeof(CaiPiaoWindows),"Update",new[]{typeof(float)},nameof(MiniGameAssist.ScratchUpdate),false,typeof(MiniGameAssist));
            bool grab=Hook(typeof(Script.MiNiGame.Hook),"Update",Type.EmptyTypes,nameof(MiniGameAssist.GrabUpdate),false,typeof(MiniGameAssist));
            bool storyGame=Hook(typeof(Script.Tool.VideoItem),"CheckBtn",Type.EmptyTypes,nameof(ChoicesShown),false);
            bool choiceTimer=Hook(typeof(Script.Tool.VideoItem),"CheckBtn",Type.EmptyTypes,nameof(ChoiceTimer.BeforeChoices),true,typeof(ChoiceTimer));
            bool choiceEnd=Hook(typeof(Script.Tool.VideoItem),"RemoveBtn",Type.EmptyTypes,nameof(ChoiceTimer.ButtonsRemoved),false,typeof(ChoiceTimer));
            State.ChoiceTimerAvailable=choiceTimer && choiceEnd;
            Hook(typeof(HeJiuWindows),"Init",new[]{typeof(bool)},nameof(MiniGameAssist.DrinkStarted),false,typeof(MiniGameAssist));
            bool combat=Hook(typeof(CombatWindows),"Update",new[]{typeof(float)},nameof(MiniGameAssist.CombatReady),false,typeof(MiniGameAssist));
            bool negotiation=Hook(typeof(AiChatWindows),"StartMessage",Type.EmptyTypes,nameof(MiniGameAssist.Negotiation),true,typeof(MiniGameAssist));
            bool pinball=Hook(typeof(Script.MinigameWebView.MinigameWebViewLauncher),"LoadSuccess",
                new[]{typeof(ZenFulcrum.EmbeddedBrowser.JSONNode)},nameof(MiniGameAssist.PinballLoaded),false,typeof(MiniGameAssist));
            State.MiniGameAvailable=qte || scratch || grab || storyGame || combat || negotiation || pinball;
            Contacts=Hook(typeof(PhoneWindows),"InitChat",new[]{typeof(Xlsx_Message)},nameof(Chat),false);
            bool mail=Hook(typeof(EmailWindows),"InitChat",new[]{typeof(Xlsx_Message)},nameof(Chat),false);
            bool dialogue=Hook(typeof(GameScene),"PlayVideo",new[]{typeof(VideoNode),typeof(bool),typeof(bool)},nameof(Played),false);
            bool choice=false;
            try{
                var method=AccessTools.Method(typeof(Script.Tool.ChatSelectItem),"OnClick",Type.EmptyTypes);
                hooks.Patch(method,Prefix(nameof(BeforeReply)),Prefix(nameof(AfterReply)));
                choice=true;
            }catch(Exception error){Log.LogWarning("任务消息回复："+error.Message);}
            Events=Hook(typeof(GameDataMrg),"set_CurEventKey",new[]{typeof(string)},nameof(Map),false);
            Hook(typeof(GameDataMrg),"LoadSaveData",Type.EmptyTypes,nameof(Reset),true);
            var propertyArgs=new[]{typeof(string),typeof(long),typeof(string)};
            bool propertyAdd=Hook(typeof(GameDataMrg),"AddProperty",propertyArgs,nameof(BeforePropertyAdd),true);
            bool propertySet=Hook(typeof(GameDataMrg),"SetProperty",propertyArgs,nameof(BeforePropertySet),true);
            var getArgs=new[]{typeof(string),typeof(string),typeof(long)};
            bool pressureGet=Hook(typeof(GameDataMrg),"GetProperty",getArgs,nameof(PressureRead),false);
            State.EnergyAvailable=propertyAdd && propertySet;
            State.PressureAvailable=propertyAdd && propertySet && pressureGet;
            try {
                var method=AccessTools.Method(typeof(GameScene),"AddProperty",new[]{typeof(Il2CppSystem.Collections.Generic.List<PropertyData>),typeof(VideoNode),typeof(bool)});
                hooks.Patch(method,Prefix(nameof(BeforeStory)),Prefix(nameof(AfterStory)));Story=true;
            } catch(Exception ex){Log.LogWarning("剧情好感入口："+ex.Message);}
            State.FavorAvailable=Contacts || mail || choice || Events || dialogue || Story;
            foreach(var pair in new (Type,string)[]{
                (typeof(GameScene),"CheckInput"),(typeof(Script.Mrg.EventContentMrg),"CheckKeyDown"),
                (typeof(Script.Tool.ClickTouchEvent),"Update"),(typeof(Script.Tool.MapPlayer),"Move"),
                (typeof(Script.Tool.MapPlayer),"CheckJoin"),(typeof(Script.Scene.Map3DScene),"Update"),
                (typeof(FrameWork.Img360BtnWindows),"Move"),(typeof(FrameWork.MapRiWindows),"Move"),
                (typeof(FrameWork.MapYeWindows),"Move"),(typeof(FrameWork.AiChatWindows),"Update"),
                (typeof(Script.UiTool.QteBtn),"CheckClickSpace"),(typeof(Script.UiTool.QteBtn),"CheckKey"),
                (typeof(Script.UiTool.QteBtn),"ClickCheckSlide")})
            {
                try{var method=AccessTools.Method(pair.Item1,pair.Item2);if(method!=null)hooks.Patch(method,Prefix(nameof(AllowGameInput)));}
                catch(Exception e){Log.LogWarning(pair.Item2+"："+e.Message);}
            }
            driver=AddComponent<Driver>();
            Log.LogInfo("RiseAloneTrainer v1.8.2 ready");
        }
        private static HarmonyMethod Prefix(string name){return new HarmonyMethod(typeof(Plugin),name);}
        private bool Hook(Type type,string name,Type[] args,string callback,bool before,Type callbacks=null)
        {
            try {
                var m=AccessTools.Method(type,name,args);
                var h=new HarmonyMethod(callbacks??typeof(Plugin),callback);
                hooks.Patch(m,before?h:null,before?null:h);
                return true;
            } catch(Exception e){Log.LogWarning(name+"："+e.Message); return false;}
        }
        public override bool Unload()
        {
            driver?.CloseMenu();
            TaskChoices.Reset();
            MapLabels.Release();
            ChoiceTimer.Release();
            MiniGameAssist.Reset();
            hooks?.UnpatchSelf();
            if(driver!=null) UnityEngine.Object.Destroy(driver);
            State.Observe(null);
            return true;
        }
        static bool AllowGameInput(){return !Driver.BlocksGameInput;}
        private static void ChoicesShown(Script.Tool.VideoItem __instance){
            MiniGameAssist.StoryGame(__instance);
        }
        static void Reset(){if(TaskChoices.Loading)return;ChoiceTimer.Release();TaskChoices.Reset();MiniGameAssist.Reset();State.Observe(null);}
        static GameSlot CurrentSlotFor(GameDataMrg manager)
        {
            var slot=GameSlot.Current();
            return slot!=null && slot.Manager.Pointer==manager.Pointer?slot:null;
        }
        static void BeforePropertyAdd(GameDataMrg __instance,string __0,ref long __1,string __2)
        {
            BeforePropertyWrite(__instance,__0,ref __1,__2,true);
        }
        static void BeforePropertySet(GameDataMrg __instance,string __0,ref long __1,string __2)
        {
            BeforePropertyWrite(__instance,__0,ref __1,__2,false);
        }
        static void BeforePropertyWrite(GameDataMrg manager,string key,ref long amount,string group,bool additive)
        {
            if(group!="Property")return;
            if(key=="Execution" && State.CheckEnergy){
                if(additive && amount>=0)return;
                try{
                    var active=CurrentSlotFor(manager);
                    if(active!=null)State.BeforeEnergyChange(active,ref amount,additive);
                }catch(Exception error){State.StopEnergy(error);}
                return;
            }
            if(key!="Pressure" || !State.CheckPressure)return;
            try{
                var slot=CurrentSlotFor(manager);
                if(slot!=null)State.BeforePressureChange(slot,ref amount,additive);
            }catch(Exception error){State.StopPressure(error);}
        }
        static void PressureRead(GameDataMrg __instance,string __0,string __1,ref long __result)
        {
            if(__result==0 || __0!="Pressure" || __1!="Property" || !State.CheckPressure)return;
            try{
                var slot=CurrentSlotFor(__instance);
                if(slot!=null)__result=State.PressureReading(slot,__result);
            }catch(Exception error){State.StopPressure(error);}
        }
        static void Chat(Xlsx_Message __0)
        {
            if(!State.CheckFavor || __0==null) return;
            try {
                var slot=GameSlot.Current();
                var person=Catalog.Actor(__0.Key,true);
                if(slot!=null && person!=null)State.Interact(slot,person);
            }
            catch(Exception e){HookFailure(e);}
        }
        static void Played(GameScene __instance,VideoNode __0)
        {
            if(!State.CheckFavor || __0==null || __0.isToNextGroup || __0.isNowToNext)return;
            try{
                var scene=GameScene.Instance;
                if(scene==null || scene.Pointer!=__instance.Pointer || SceneManager.GetActiveScene().name!="Game")return;
                var slot=GameSlot.Current();
                if(slot==null)return;
                var graph=__0.graph;
                if(graph==null)return;
                var person=StoryActors.Played(graph.name,__0.videoPath,__0.uniqueID,slot.Manager.CurVideoId);
                if(person!=null)State.Interact(slot,person);
            }catch(Exception error){HookFailure(error);}
        }

        private sealed class Reply
        {
            public string Session,Prompt,Selected;
            public Entry Person;
            public long? BeforeReward;
        }
        static void BeforeReply(Script.Tool.ChatSelectItem __instance,out Reply __state)
        {
            __state=null;
            if(!State.CheckFavor)return;
            try{
                var prompt=__instance._lastNode;
                var answer=__instance._chatNode;
                if(prompt==null || answer==null || String.IsNullOrEmpty(prompt.uniqueID) || String.IsNullOrEmpty(answer.uniqueID))return;
                var speaker=prompt.isSelfMsg || prompt.icon==null ? null : Catalog.Portrait(prompt.icon.name);
                var reward=SingleFavor(answer.propertyDatas);
                if(speaker!=null && reward!=null && speaker!=reward)return;
                var person=speaker??reward;
                if(person==null)return;
                var slot=GameSlot.Current();
                if(slot==null || slot.Manager.GetMsgSelectId(prompt.uniqueID)==answer.uniqueID)return;
                __state=new Reply{Session=slot.Identity,Prompt=prompt.uniqueID,Selected=answer.uniqueID,Person=person,
                    BeforeReward=speaker==null ? slot.Base(person.Key) : (long?)null};
            }catch(Exception error){HookFailure(error);}
        }
        static void AfterReply(Reply __state)
        {
            if(__state==null || !State.CheckFavor)return;
            try{
                var slot=GameSlot.Current();
                if(slot==null || slot.Identity!=__state.Session || slot.Manager.GetMsgSelectId(__state.Prompt)!=__state.Selected)return;
                if(__state.BeforeReward.HasValue && slot.Base(__state.Person.Key)==__state.BeforeReward.Value)return;
                State.Interact(slot,__state.Person);
            }catch(Exception error){HookFailure(error);}
        }
        static void Map(GameDataMrg __instance,string __0)
        {
            if(!State.CheckFavor || String.IsNullOrEmpty(__0)) return;
            try {
                var slot=GameSlot.Current();
                if(slot==null || slot.Manager.Pointer!=__instance.Pointer) return;
                var data=Xlsx_Event_Query.XlsxDataAsOneKey.ByKeyGetValue(__0);
                if(data!=null && data.Key==__0) State.Interact(slot,Catalog.Actor(data.RoleIcon,false));
            } catch(Exception e){HookFailure(e);}
        }
        internal sealed class StoryChange { public Entry Person; public long Before; public string Session; }
        static void BeforeStory(Il2CppSystem.Collections.Generic.List<PropertyData> __0,out StoryChange __state)
        {
            __state=null;
            if(!State.CheckFavor || __0==null) return;
            try{
                var target=SingleFavor(__0);
                if(target==null)return;
                var slot=GameSlot.Current();State.Observe(slot);
                if(!State.FullFavor || slot==null)return;
                __state=new StoryChange{Person=target,Before=slot.Base(target.Key),Session=State.Session};
            }catch(Exception e){HookFailure(e);}
        }
        static Entry SingleFavor(Il2CppSystem.Collections.Generic.List<PropertyData> changes)
        {
                if(changes==null)return null;
                Entry target=null;
                for(int i=0;i<changes.Count;i++){
                    var p=changes[i];
                    if(p==null || p.isRound || p.PropertyType!=PropertyType.Property) continue;
                    string key=p.propertyTypeValue.ToString();
                    switch(key){
                        case "TSGSNFavorability":key="XFPFavorability";break;
                        case "XXSNFavorability":key="XXGFavorability";break;
                        case "WYFavorability":key="LBNFavorability";break;
                        case "LXYavorability":key="XJMFavorability";break;
                    }
                    var entry=Catalog.Find(key);
                    if(entry==null || entry.Full==0)continue;
                    if(target!=null && target!=entry)return null;
                    target=entry;
                }
                return target;
        }
        static void AfterStory(StoryChange __state)
        {
            if(__state==null || !State.FullFavor)return;
            try{
                var slot=GameSlot.Current();State.Observe(slot);
                if(slot!=null && __state.Session==State.Session && slot.Base(__state.Person.Key)!=__state.Before)
                    State.Interact(slot,__state.Person);
            }catch(Exception e){HookFailure(e);}
        }
        static void HookFailure(Exception e){ State.Last="本次交互未处理："+e.GetBaseException().Message;}
    }

    public sealed class GameSlot : ISlot
    {
        internal GameDataMrg Manager;
        public string Identity { get; private set; }
        public string LoadedSlot { get; private set; }
        private CombatWindows PointsWindow()
        {
            if(!UiManager.IsShowUi<CombatWindows>())return null;
            var window=UiManager.GetUi<CombatWindows>();
            if(window==null || window.RectTransformBtnGroup==null || !window.RectTransformBtnGroup.gameObject.activeInHierarchy)return null;
            return window;
        }
        public string CombatTurn {
            get {
                var window=PointsWindow();
                if(window==null)return null;
                var scene=GameScene.Instance;
                var video=scene==null?null:scene.videoItem;
                if(video==null || video._videoNode==null || String.IsNullOrEmpty(Manager.CurVideoId) ||
                    video._videoNode.uniqueID!=Manager.CurVideoId)return null;
                return window.Pointer+"/"+video.Pointer+"/"+Manager.CurVideoId;
            }
        }
        public void RefreshCombatPoints()
        {
            var window=PointsWindow();
            if(window!=null)window.InitSkillPoint();
        }
        public bool FirstMorningHomePending {
            get {return Manager.CurRound==1 && Manager.IsMorning && Manager.GetPropertyAsEvent("Ex_主线3")==0;}
        }
        internal static GameSlot Current()
        {
            string scene=SceneManager.GetActiveScene().name;
            if(scene!="Game" && scene!="Map3D" && scene!="Map" && scene!="MiNiGame1" &&
               scene!="MinGameLevelSelect" && scene!="Day" && scene!="Night")return null;
            var manager=SingletonAsMono<GameDataMrg>._instance;
            if(manager==null)return null;
            var data=manager.GetData();
            if(data==null || data.Data==null || String.IsNullOrWhiteSpace(GameData.CurKey))return null;
            string loadedSlot=manager.Pointer+"/"+data.Pointer;
            return new GameSlot{Manager=manager,LoadedSlot=loadedSlot,Identity=GameData.CurKey+"/"+loadedSlot};
        }
        public long Base(string key){return Manager.GetPropertyNorEquip(key,"Property",0);}
        public long Effective(string key){return Manager.GetProperty(key,"Property",0);}
        public void Set(string key,long value){Manager.SetProperty(key,value,"Property");}
        public void Backup()
        {
            string source=Path.Combine(Application.persistentDataPath,"SaveData.dat");
            string dir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"RiseAloneTrainer","Backups");
            Directory.CreateDirectory(dir);
            string dest=Path.Combine(dir,"SaveData-"+DateTime.Now.ToString("yyyyMMdd-HHmmss-fff")+"-"+Guid.NewGuid().ToString("N")+".dat");
            using(var input=new FileStream(source,FileMode.Open,FileAccess.Read,FileShare.Read))
            using(var output=new FileStream(dest,FileMode.CreateNew,FileAccess.Write,FileShare.None)){
                if(input.Length==0)throw new IOException("现有存档为空，无法建立备份。");
                input.CopyTo(output);output.Flush(true);
                if(input.Length!=output.Length)throw new IOException("备份长度不符。");
            }
        }
    }

    public sealed class Driver : MonoBehaviour
    {
        public Driver(IntPtr ptr):base(ptr){}
        internal static bool BlocksGameInput {get{return Menu.Visible || (Menu.ConsumeUntil>=0 && Time.frameCount<=Menu.ConsumeUntil);}}
        private Menu menu;
        private long next;
        private string visibleScene;
        private bool fault;
        public void Update()
        {
            try{
                if(menu==null)menu=new Menu();
                if(Input.GetKeyDown(KeyCode.BackQuote) &&
                   !Input.GetKey(KeyCode.LeftControl) && !Input.GetKey(KeyCode.RightControl) &&
                   !Input.GetKey(KeyCode.LeftAlt) && !Input.GetKey(KeyCode.RightAlt) &&
                   !Input.GetKey(KeyCode.LeftShift) && !Input.GetKey(KeyCode.RightShift)){
                    if(Menu.Visible)CloseMenu();
                    else if(menu.CanOpen()){menu.Open();visibleScene=SceneManager.GetActiveScene().name;}
                }
                if(Menu.Visible && SceneManager.GetActiveScene().name!=visibleScene)CloseMenu();
                ChoiceTimer.CheckOwner();
                if(!Menu.Visible && !Plugin.State.Watch && !TaskChoices.Busy && !ChoiceBadges.Any && !MapLabels.Visible)return;
                long now=Environment.TickCount64;
                if(now<next)return;
                next=now+100;
                var slot=GameSlot.Current();
                Plugin.State.Tick(slot);
                TaskChoices.Tick(slot);
                MapLabels.Tick(slot);
                if(slot!=null && TaskChoices.WantsNotice && menu.CanOpen()){
                    menu.OpenAssists();visibleScene=SceneManager.GetActiveScene().name;TaskChoices.NoticeShown();
                }
                MiniGameAssist.TickPinball(slot);
                if(Menu.Visible)menu.Refresh(slot);
                fault=false;
            } catch(Exception e){
                if(!fault)UnityEngine.Debug.LogError("RiseAloneTrainer: "+e.GetBaseException().Message);
                fault=true;CloseMenu();
            }
        }
        internal void CloseMenu(){menu?.Close();}
        public void OnDestroy(){CloseMenu();menu?.Release();}
    }
}
