using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using Il2CppInterop.Runtime;
using FrameWork;
using FrameWork.Data;
using FrameWork.ChatTool;
using LitJson;
using Script.Mrg;
using Script.Scene;
using Script.Tool;
using UnityEngine;
using UnityEngine.SceneManagement;
using Xlsx;

namespace RiseAlone
{
    internal static class TaskChoices
    {
        private sealed class Risk {
            internal int[] Direct,Possible;
        }
        private static readonly Lazy<Dictionary<string,Risk>> index=new Lazy<Dictionary<string,Risk>>(ReadIndex);
        private static readonly Lazy<TaskNames> names=new Lazy<TaskNames>(ReadNames);
        private static readonly ChoiceJournal journal=new ChoiceJournal(Path.Combine(Paths.ConfigPath,"RiseAloneTrainer","ChoiceBackups"));
        private static ChoicePoint notice,replay;
        private static bool showNotice,loading;
        private static long replayDeadline;
        private static int oldSceneHandle;
        private static string entryGraph,entryId,entryData,phone,email;
        private static IntPtr entryOwner;
        private static string activeStory;
        private static IntPtr phoneOwner;
        private static bool reopened;
        private static IntPtr sessionOwner;
        internal static bool Loading {get{return loading;}}
        private static void Sync(GameSlot slot){
            var id=slot.Manager.GetData().Pointer;
            if(sessionOwner==id){journal.MoveWithAutoSave(GameData.CurKey);return;}
            journal.Select(GameData.CurKey);sessionOwner=id;
        }
        internal static bool Busy {get{return notice!=null || replay!=null;}}
        internal static bool WantsNotice {get{return showNotice;}}
        internal static void NoticeShown(){showNotice=false;}
        internal static void Continue(){notice=null;showNotice=false;}
        internal static void Reset(){
            if(loading)return;
            ChoiceBadges.Clear();
            Continue();replay=null;entryData=null;phone=email=null;activeStory=null;sessionOwner=IntPtr.Zero;journal.Select(null);
        }
        private static Dictionary<string,Risk> ReadIndex(){
            var result=new Dictionary<string,Risk>(StringComparer.Ordinal);
            using(var stream=typeof(TaskChoices).Assembly.GetManifestResourceStream("RiseAlone.ChoiceRisks"))
            using(var reader=new StreamReader(stream)){
                string line;
                while((line=reader.ReadLine())!=null){
                    var fields=line.Split('\t');
                    result.Add(fields[0]+"/"+fields[1]+"/"+fields[2],new Risk{Direct=Numbers(fields[3]),Possible=Numbers(fields[4])});
                }
            }
            return result;
        }
        private static int[] Numbers(string s){return s.Length==0?Array.Empty<int>():Array.ConvertAll(s.Split(','),int.Parse);}
        private static Risk GetRisk(string kind,BaseNode node,Il2CppSystem.Collections.Generic.List<TaskData> tasks){
            var direct=new HashSet<int>();
            var possible=new HashSet<int>();
            Risk known;
            if(node.graph!=null && index.Value.TryGetValue(kind+"/"+node.graph.name+"/"+node.uniqueID,out known)){
                possible.UnionWith(known.Possible);
            }
            // Use the actual loaded destination for definite warnings, including on modified game builds.
            if(tasks!=null)foreach(var t in tasks){
                if(t==null || t.taskType!=TaskType.Lose)continue;
                possible.Add((int)t.xlsxTaskKey);
                var v=node.TryCast<VideoNode>();
                if(v==null || (!v.isHasBtn && !v.isHasQte))direct.Add((int)t.xlsxTaskKey);
            }
            return new Risk{Direct=direct.ToArray(),Possible=possible.ToArray()};
        }
        private static TaskNames ReadNames(){
            using(var stream=typeof(TaskChoices).Assembly.GetManifestResourceStream("RiseAlone.TaskKeys"))
            using(var reader=new StreamReader(stream))return new TaskNames(reader,NativeTaskKey,LocalizedTaskTitle);
        }
        private static string NativeTaskKey(int id){
            try{return Il2CppSystem.Enum.GetName(Il2CppType.Of<Xlsx_Task_Key>(),id);}
            catch(Exception){return null;}
        }
        private static int? NativeTaskId(string key){
            try{return Il2CppSystem.Convert.ToInt32(Il2CppSystem.Enum.Parse(Il2CppType.Of<Xlsx_Task_Key>(),key));}
            catch(Exception){return null;}
        }
        private static string LocalizedTaskTitle(string key){
            try{
                var row=Xlsx_Task_Query.XlsxDataAsOneKey?.ByKeyGetValue(key);
                if(row==null || row.Key!=key || String.IsNullOrEmpty(row.Title))return null;
                string title=LanguageMrg.GetText(row.Title);
                return title==row.Title?null:title;
            }catch(Exception){return null;}
        }
        private static void Label(TMPro.TMP_Text title,Transform group,BaseNode prompt,Risk risk,ChoiceRank rank,Func<bool> allowed){
            string warning="";
            var direct=new HashSet<int>(risk?.Direct??Array.Empty<int>());
            var possible=new HashSet<int>(risk?.Possible??Array.Empty<int>());
            if(rank.FailureIds!=null)direct.UnionWith(rank.FailureIds);
            if(rank.PossibleFailureIds!=null)possible.UnionWith(rank.PossibleFailureIds);
            if(direct.Count!=0 || possible.Count!=0){
                bool certain=direct.Count>0;
                rank.Risk=Math.Max(rank.Risk,certain?2:1);
                warning=names.Value.Warning(certain,(certain?direct:possible).ToArray());
                if(certain){
                    possible.ExceptWith(direct);
                    if(possible.Count>0)warning+="　"+names.Value.Warning(false,possible.ToArray());
                }
            }
            ChoiceBadges.Set(title,group,prompt==null?IntPtr.Zero:prompt.Pointer,rank,warning,allowed);
        }
        internal static bool CanChoose(VideoButton view,ButtonNode button){
            if(!view._isCanClick || view.bt==null || !view.bt.IsInteractable() || button==null)return false;
            if(button.isCheckVideoExists && !FrameWork.Tool.IsUnLockAllVideo(button.videoUnlockDatas))return false;
            if(button.isHasUseProperty && !FrameWork.Tool.IsSuc(button.usePropertyDatas))return false;
            return !button.isHasUsePropertyOr || FrameWork.Tool.IsSucOr(button.usePropertyDatasOr);
        }
        internal static void VideoLabel(VideoButton __instance){
            if(__instance==null || __instance.text==null)return;
            var view=__instance;
            try{
                var node=view.GetVideoNode();var button=view.GetButtonNode();
                var risk=node==null?null:GetRisk("Video",node,node.taskData);
                ChoiceRank rank=default;
                try{rank=ChoiceEffects.Video(button,node);}catch(Exception){}
                Label(view.text,view.transform.parent,view._lastVideoNode,risk,rank,()=>CanChoose(view,button));
            }catch(Exception){ChoiceBadges.Forget(view.text);}
        }
        internal static void ChatLabel(ChatSelectItem __instance){
            if(__instance==null || __instance.text==null)return;
            var view=__instance;
            try{
                var node=view._chatNode;
                var risk=node==null?null:GetRisk("Chat",node,node.taskData);
                ChoiceRank rank=default;
                try{rank=ChoiceEffects.Chat(node);}catch(Exception){}
                Label(view.text,view.transform.parent,view._lastNode,risk,rank,
                    ()=>node!=null && FrameWork.Tool.IsSuc(node.fistPropertyDatas));
            }catch(Exception){ChoiceBadges.Forget(view.text);}
        }
        internal static void PhoneContact(PhoneWindows __instance,Xlsx_Message __0){
            phoneOwner=__instance.Pointer;phone=__0?.Key;
        }
        internal static void RefreshVisibleLabels(){
            if(!Plugin.State.CheckChoices)Continue();
            var group=GameScene.Instance?.videoItem?.btnGroup;
            if(group!=null)foreach(var button in group.GetComponentsInChildren<VideoButton>()){
                VideoLabel(button);
            }
            if(UiManager.IsShowUi<PhoneWindows>())
                RefreshChat(UiManager.GetUi<PhoneWindows>().transform);
            if(UiManager.IsShowUi<EmailWindows>())
                RefreshChat(UiManager.GetUi<EmailWindows>().transform);
        }
        private static void RefreshChat(Transform window){
            foreach(var item in window.GetComponentsInChildren<ChatSelectItem>()){
                ChatLabel(item);
            }
        }
        internal static void EmailContact(Xlsx_Message __0){email=__0==null?null:__0.Key;}
        private static string Serialize(GameSlot slot,string eventKey=null,string prompt=null){
            var manager=slot.Manager;
            var clone=JsonMapper.ToObject<SavedData>(JsonMapper.ToJson(manager.GetData()));
            clone.Key=GameData.CurKey;
            clone.Data[manager._unLockSaveKeyStr]=JsonMapper.ToJson(manager._unLockKeys);
            clone.Data[manager._roundUnLockDicStr]=JsonMapper.ToJson(manager._roundUnLockDic);
            if(prompt!=null){
                clone.Data["CurVideoId"]=prompt;
                clone.Data["CurEventKey"]=eventKey;
            }
            return JsonMapper.ToJson(clone);
        }
        internal static void EnterVideo(GameScene __instance,VideoNode __0){
            if(!Plugin.State.CheckChoices || replay!=null || __0==null || __0.graph==null || __0.isToNextGroup)return;
            try{
                activeStory=__0.graph.name;
                entryData=null;
                if(!__0.isHasBtn || GameScene.Instance==null || GameScene.Instance.Pointer!=__instance.Pointer)return;
                var slot=GameSlot.Current();
                var graph=__0.graph.TryCast<VideoGraph>();
                if(slot==null || graph==null || String.IsNullOrEmpty(__0.uniqueID))return;
                entryData=Serialize(slot,graph.xlsxEventKey,__0.uniqueID);
                entryOwner=slot.Manager.GetData().Pointer;entryId=__0.uniqueID;entryGraph=graph.name;
            }catch(Exception e){Error(e);}
        }
        private static ChoicePoint Make(GameSlot slot,string graph,string prompt,string channel,string label,Risk risk){
            Sync(slot);
            var point=new ChoicePoint{Slot=GameData.CurKey,Round=slot.Manager.CurRound,Scene=SceneManager.GetActiveScene().name,
                Graph=graph,Prompt=prompt,EventKey=slot.Manager.CurEventKey,Channel=channel,Label=label,Risks=risk.Possible,AtClick=Serialize(slot)};
            if((channel=="Video" || channel=="Combat") && entryData!=null && entryId==prompt && entryGraph==graph && entryOwner==slot.Manager.GetData().Pointer)
                point.Before=entryData;
            return point;
        }
        private static VideoNode LiveVideo(GameSlot slot){
            var scene=GameScene.Instance;
            if(slot==null || scene==null || scene.videoItem==null)return null;
            var node=scene.videoItem._videoNode;
            return node!=null && node.graph!=null && !String.IsNullOrEmpty(node.uniqueID) && node.uniqueID==slot.Manager.CurVideoId?node:null;
        }
        internal static bool VideoClick(VideoButton __instance){
            if(Busy)return false;
            CaptureVideo(__instance);return true;
        }
        private static void CaptureVideo(VideoButton __instance){
            if(!Plugin.State.CheckChoices || Busy)return;
            try{
                var slot=GameSlot.Current();var prompt=LiveVideo(slot);
                var branch=__instance.GetVideoNode();var button=__instance.GetButtonNode();
                if(prompt==null || branch==null || button==null || button.isOpenUiBtn || !__instance._isCanClick ||
                   !__instance.isActiveAndEnabled || __instance._videoItem==null || __instance._videoItem.Pointer!=GameScene.Instance.videoItem.Pointer)return;
                if(button.isCheckVideoExists && !FrameWork.Tool.IsUnLockAllVideo(button.videoUnlockDatas))return;
                if(button.isHasUseProperty && !FrameWork.Tool.IsSuc(button.usePropertyDatas))return;
                if(button.isHasUsePropertyOr && !FrameWork.Tool.IsSucOr(button.usePropertyDatasOr))return;
                var point=Make(slot,prompt.graph.name,prompt.uniqueID,"Video",button.buttonName,GetRisk("Video",branch,branch.taskData));
                journal.Record(point);
            }catch(Exception e){Error(e);}
        }
        internal static bool ChatClick(ChatSelectItem __instance){
            if(Busy)return false;
            CaptureChat(__instance);return true;
        }
        private static void CaptureChat(ChatSelectItem __instance){
            if(!Plugin.State.CheckChoices || Busy)return;
            try{
                var parent=__instance._lastNode;var answer=__instance._chatNode;var slot=GameSlot.Current();
                if(slot==null || !__instance.isActiveAndEnabled || parent==null || answer==null || answer.graph==null ||
                   String.IsNullOrEmpty(parent.uniqueID) || !String.IsNullOrEmpty(slot.Manager.GetMsgSelectId(parent.uniqueID)) ||
                   !FrameWork.Tool.IsSuc(answer.fistPropertyDatas))return;
                string channel=null,contact=null;
                if(UiManager.IsShowUi<PhoneWindows>() && __instance.transform.IsChildOf(UiManager.GetUi<PhoneWindows>().transform)){channel="Phone";contact=phone;}
                else if(UiManager.IsShowUi<EmailWindows>() && __instance.transform.IsChildOf(UiManager.GetUi<EmailWindows>().transform)){channel="Email";contact=email;}
                if(String.IsNullOrEmpty(contact))return;
                var point=Make(slot,answer.graph.name,parent.uniqueID,channel,LanguageMrg.GetText(answer.selectName),GetRisk("Chat",answer,answer.taskData));
                point.Contact=contact;journal.Record(point);
            }catch(Exception e){Error(e);}
        }
        internal static bool CombatClick(CombatWindows __instance,BT __0){
            if(Busy)return false;
            CaptureCombat(__instance,__0);return true;
        }
        private static void CaptureCombat(CombatWindows __instance,BT __0){
            if(!Plugin.State.CheckChoices || Busy || __0==null)return;
            try{
                var slot=GameSlot.Current();var prompt=LiveVideo(slot);
                if(prompt==null || String.IsNullOrEmpty(slot.CombatTurn) || !__0.IsInteractable() ||
                   !__0.gameObject.activeInHierarchy || UiManager.GetUi<CombatWindows>().Pointer!=__instance.Pointer)return;
                string key=CombatKey(__instance,__0);
                if(key==null || __instance._buttonNodes==null || __instance._videoNodes==null ||
                   !__instance._buttonNodes.ContainsKey(key) || !__instance._videoNodes.ContainsKey(key))return;
                var button=__instance._buttonNodes[key];var branch=__instance._videoNodes[key];
                if(button==null || branch==null || !FrameWork.Tool.IsSuc(button.usePropertyDatas))return;
                journal.Record(Make(slot,prompt.graph.name,prompt.uniqueID,"Combat",button.buttonName,GetRisk("Video",branch,branch.taskData)));
            }catch(Exception e){Error(e);}
        }
        private static string CombatKey(CombatWindows w,BT b){
            if(b==w.BTPuTon)return "PuTon";
            if(b==w.BTJinSheng)return "JinShengGonJi";
            if(b==w.BTZhuHe)return "ZhuHeQuan";
            if(b==w.BTJunTi)return "JunTiQuan";
            if(b==w.BTRuLaiShengZhang)return "RuLaiShengZhang";
            if(b==w.BTXiXueGuiHuiFu)return "XiXueGuiHuiXue";
            if(b==w.BTYonCun)return "YonChun";
            if(b==w.BTTaoPao)return "TaoPao";
            if(b==w.BTDaoJu)return "DaoJuShiYon";
            return null;
        }
        internal static void BeforeTask(GameDataMrg __instance,string __0,TaskType __1,out bool __state){
            __state=false;
            if(__1!=TaskType.Lose || Busy || !Plugin.State.CheckChoices || String.IsNullOrEmpty(__0))return;
            try{var slot=GameSlot.Current();__state=slot!=null && slot.Manager.Pointer==__instance.Pointer && __instance.GetTaskState(__0)!=TaskType.Lose;}
            catch(Exception e){Error(e);}
        }
        internal static void AfterTask(GameDataMrg __instance,string __0,bool __state){
            if(!__state)return;
            try{
                if(__instance.GetTaskState(__0)!=TaskType.Lose)return;
                int task;
                if(!names.Value.TryId(__0,NativeTaskId,out task))return;
                var last=journal.Latest;
                if(last==null)return;
                var slot=GameSlot.Current();
                if(slot==null || slot.Manager.Pointer!=__instance.Pointer)return;
                Sync(slot);last=journal.Latest;
                if(last==null)return;
                string graph=(last.Channel=="Video" || last.Channel=="Combat")?(LiveVideo(slot)?.graph.name??activeStory):last.Graph;
                var point=journal.Match(task,graph,slot.Manager.CurRound);
                if(point==null)return;
                journal.Pin(point,__0);notice=point;showNotice=true;
            }catch(Exception e){Error(e);}
        }
        internal static ChoicePoint Current(ISlot slot){
            if(slot==null || !Plugin.State.CheckChoices || replay!=null)return null;
            if(notice!=null)return notice;
            var live=slot as GameSlot;
            if(live==null)return null;
            try{Sync(live);return journal.Latest;}catch(Exception e){Error(e);return null;}
        }
        internal static bool IsNotice {get{return notice!=null;}}
        internal static string Describe(ChoicePoint p){
            if(p==null)return "遇到剧情选项或消息回复后，这里会显示可重选的位置。";
            string heading="最近的选择";
            if(!String.IsNullOrEmpty(p.Failure)){
                string title=names.Value.Title(p.Failure);
                heading=title==null?"任务已中断":"「"+title+"」已中断";
            }
            return heading+"\n第 "+p.Round+" 回合　"+p.Label;
        }
        // Borrow one slot's in-memory read source for the duration of the original loader.
        // Preserve the saved slot on disk and the other slots in GameData's dictionary.
        private static void ReadSnapshot(GameDataMrg manager,string contents){
            var clone=JsonMapper.ToObject<SavedData>(contents);
            if(clone==null || clone.Data==null || String.IsNullOrEmpty(clone.Key))throw new InvalidDataException("重选记录无法读取。");
            clone.Key=GameData.CurKey;
            var key=GameData.CurDataKey;
            var dict=GameData._dataDic;
            loading=true;
            try{
                ChoiceJournal.ReadTemporary(JsonMapper.ToJson(clone),()=>dict.ContainsKey(key)?dict[key]:null,
                    v=>GameData.SetStringNotSave(key,v),()=>dict.Remove(key),()=>manager.LoadSaveData());
                var restored=manager.GetData();
                if(restored==null || restored.Key!=clone.Key || restored.Round!=clone.Round || restored.Data.Count!=clone.Data.Count)
                    throw new InvalidDataException("读回的选择记录不完整。");
                foreach(var item in clone.Data){
                    if(!restored.Data.ContainsKey(item.Key) || restored.Data[item.Key]!=item.Value)
                        throw new InvalidDataException("读回的剧情状态与选择前的记录不同。");
                }
                manager.SetIsNew(false);sessionOwner=restored.Pointer;
                Plugin.State.RebindAfterReselect(GameSlot.Current());
            }finally{loading=false;}
        }
        internal static void Restore(GameSlot slot,ChoicePoint expected){
            if(slot==null || replay!=null || expected==null || !System.Object.ReferenceEquals(Current(slot),expected))
                throw new InvalidOperationException("重选位置已变更，请重新查看。");
            if(expected.Slot!=GameData.CurKey && !System.Object.ReferenceEquals(notice,expected))
                throw new InvalidOperationException("请在原存档中重选。");
            Scenes destination;
            if(!Enum.TryParse(expected.Scene,out destination))throw new InvalidOperationException("无法识别原场景。");
            slot.Backup();
            string prior=Serialize(slot);
            oldSceneHandle=SceneManager.GetActiveScene().handle;
            reopened=false;replay=expected;Continue();
            try{
                ReadSnapshot(slot.Manager,expected.Before??expected.AtClick);
                LoadMrg.Load(destination,LoadSceneMode.Single,0.2f,null);
                replayDeadline=Environment.TickCount64+90000;
            }catch{
                replay=null;ReadSnapshot(slot.Manager,prior);throw;
            }
        }
        internal static void Tick(GameSlot slot){
            ChoiceBadges.Refresh(Plugin.State.ZeroPressure);
            var point=replay;
            if(point==null)return;
            try{
                if(Environment.TickCount64>replayDeadline)throw new InvalidOperationException("等待原组选项超时，保护点仍保留。");
                var scene=SceneManager.GetActiveScene();
                if(slot==null || scene.handle==oldSceneHandle || scene.name!=point.Scene)return;
                if(point.Channel=="Video" || point.Channel=="Combat"){
                    var node=LiveVideo(slot);
                    if(node==null || node.uniqueID!=point.Prompt || node.graph.name!=point.Graph)return;
                    if(point.Channel=="Combat"){
                        if(String.IsNullOrEmpty(slot.CombatTurn))return;
                        ReadSnapshot(slot.Manager,point.AtClick);slot.RefreshCombatPoints();replay=null;
                        Plugin.State.Last="已回到战斗选招。";return;
                    }
                    var group=GameScene.Instance.videoItem.btnGroup;
                    if(group==null || !group.gameObject.activeInHierarchy)return;
                    for(int i=0;i<group.childCount;i++){
                        var b=group.GetChild(i).GetComponent<VideoButton>();
                        if(b==null || !b.isActiveAndEnabled || !b._isCanClick)continue;
                        ReadSnapshot(slot.Manager,point.AtClick);
                        entryData=point.Before;entryGraph=point.Graph;entryId=point.Prompt;entryOwner=slot.Manager.GetData().Pointer;
                        replay=null;
                        Plugin.State.Last="已回到原来的选项。";return;
                    }
                }else if(!reopened){
                    var contact=Xlsx_Message_Query.XlsxDataAsOneKey.ByKeyGetValue(point.Contact);
                    if(contact==null || contact.Key!=point.Contact)throw new InvalidOperationException("找不到原联系人。");
                    reopened=true;
                    if(point.Channel=="Phone"){
                        PhoneReplay.Open(contact,()=>ReadSnapshot(slot.Manager,point.AtClick),
                            window=>phoneOwner==window.Pointer && phone==point.Contact);
                    }else{
                        ReadSnapshot(slot.Manager,point.AtClick);
                        UiManager.OpenUi<EmailWindows>().InitChat(contact);
                    }
                }else{
                    Transform window=null;
                    if(point.Channel=="Phone" && UiManager.IsShowUi<PhoneWindows>())window=UiManager.GetUi<PhoneWindows>().transform;
                    if(point.Channel=="Email" && UiManager.IsShowUi<EmailWindows>())window=UiManager.GetUi<EmailWindows>().transform;
                    if(window==null)return;
                    foreach(var item in window.GetComponentsInChildren<ChatSelectItem>()){
                        if(item.isActiveAndEnabled && item._lastNode!=null && item._lastNode.uniqueID==point.Prompt &&
                           item._lastNode.graph!=null && item._lastNode.graph.name==point.Graph &&
                           (point.Channel=="Phone"?phone:email)==point.Contact){
                            replay=null;Plugin.State.Last="已回到原来的回复选项。";return;
                        }
                    }
                }
            }catch(Exception e){replay=null;Error(e);}
        }
        private static void Error(Exception e){Plugin.State.Last="任务保护："+e.GetBaseException().Message;}
    }
}
