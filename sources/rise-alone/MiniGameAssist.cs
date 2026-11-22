using System;
using System.IO;
using DG.Tweening;
using FrameWork;
using Script.MiNiGame;
using Script.Scene;
using Script.Tool;
using Script.UiTool;
using Script.MinigameWebView;
using UnityEngine;
using ZenFulcrum.EmbeddedBrowser;

namespace RiseAlone
{
    public static class MiniGameTiming
    {
        // Follow the game's timer so a low frame rate does not prevent long tap sequences.
        public static int TapsDue(int required,int current,float elapsed,float duration,float delta)
        {
            if(required<=0 || current<0 || current>=required || !(duration>0) ||
               !(elapsed>=0 && elapsed<duration) || !(delta>0))return 0;
            double fraction=Math.Min(1,((double)elapsed+delta)/(duration*0.8));
            int due=(int)Math.Floor(fraction*required);
            return Math.Max(0,due-current);
        }
        public static bool InsideBar(float marker,float left,float width)
        {
            return marker>left && marker<left+width;
        }
    }

    internal static class MiniGameAssist
    {
        private static bool Ready()
        {
            return Plugin.State.CheckMiniGames && !TaskChoices.Busy && !Driver.BlocksGameInput && Application.isFocused && Time.deltaTime>0;
        }
        private static GameSlot StorySlot(VideoItem video)
        {
            var scene=GameScene.Instance;
            if(video==null || scene==null || scene.videoItem==null || scene.videoItem.Pointer!=video.Pointer ||
                !video._isCanEx || video._videoNode==null || String.IsNullOrEmpty(video._videoNode.uniqueID))return null;
            var slot=GameSlot.Current();
            return slot!=null && slot.Manager.CurVideoId==video._videoNode.uniqueID ? slot : null;
        }
        internal static void CombatReady(CombatWindows __instance)
        {
            try{
                if(!Ready() || __instance.RectTransformBtnGroup==null || !__instance.RectTransformBtnGroup.gameObject.activeInHierarchy ||
                    __instance.BTPuTon==null || !__instance.BTPuTon.IsInteractable() || !__instance.BTPuTon.gameObject.activeInHierarchy ||
                    __instance._videoNodes==null || __instance._buttonNodes==null || !__instance._videoNodes.ContainsKey("PuTon") ||
                    !__instance._buttonNodes.ContainsKey("PuTon") || !UiManager.IsCanPlay())return;
                var choice=__instance._buttonNodes["PuTon"];
                if(choice==null || __instance._videoNodes["PuTon"]==null || !FrameWork.Tool.IsSuc(choice.usePropertyDatas))return;
                var scene=GameScene.Instance;
                var slot=scene==null?null:StorySlot(scene.videoItem);
                if(slot==null || !Plugin.State.PrepareMiniGame(slot))return;
                __instance.OnClickBtn(__instance.BTPuTon);
            }catch(Exception error){Plugin.State.StopMiniGame(error);}
        }
        internal static void StoryGame(VideoItem __instance)
        {
            try{
                if(!Ready() || !__instance._isCanEx || __instance._videoNode==null || __instance._videoNode.graph==null)return;
                var node=__instance._videoNode;
                bool massage=node.graph.name=="AnMoNv_ChongFu";
                bool drinking=UiManager.IsShowUi<HeJiuWindows>();
                bool combat=UiManager.IsShowUi<CombatWindows>() || UiManager.IsShowUi<Combat2Windows>() || UiManager.IsShowUi<BaoKeMengWindows>();
                if(!(massage || drinking || combat) || !UiManager.IsCanPlay())return;
                var slot=StorySlot(__instance);
                if(slot==null)return;
                var manager=slot.Manager;
                if(combat && manager.EnemyHpMax>0 && manager.EnemyHp>0 && Plugin.State.PrepareMiniGame(slot))
                    manager.EnemyHp=0;
                if(drinking && manager.TargetJiuLian>0 && manager.TmpTargetJiuLian<manager.TargetJiuLian && Plugin.State.PrepareMiniGame(slot))
                    manager.TmpTargetJiuLian=manager.TargetJiuLian;
                if(!node.isHasBtn || __instance.btnGroup==null || !__instance.btnGroup.gameObject.activeInHierarchy)return;
                VideoButton pick=null;
                bool hasVisibleChoice=false;
                int best=0;
                var group=__instance.btnGroup;
                for(int i=0;i<group.childCount;i++){
                    var child=group.GetChild(i);
                    if(!child.gameObject.activeInHierarchy)continue;
                    var button=child.GetComponent<VideoButton>();
                    if(button==null || !button.isActiveAndEnabled || !button._isCanClick || button._videoItem==null || button._videoItem.Pointer!=__instance.Pointer)continue;
                    var option=button.GetButtonNode();
                    if(option==null)continue;
                    hasVisibleChoice=true;
                    if(option.isClickSureTips || option.isOpenUiBtn || option.isHasUseProperty || option.isHasUsePropertyOr)continue;
                    int priority=ChoicePriority(option.buttonName,massage,drinking,combat);
                    if(priority>best){pick=button;best=priority;}
                }
                if(drinking && !drinkFinished && hasVisibleChoice && KnownDrinkGame(node.graph.name) &&
                    Plugin.State.PrepareMiniGame(slot) && PlayDrinkResult(__instance))return;
                if(pick==null || !Plugin.State.PrepareMiniGame(slot))return;
                pick.Click();
            }catch(Exception error){Plugin.State.StopMiniGame(error);}
        }
        private static bool drinkFinished;
        internal static void DrinkStarted(){drinkFinished=false;}
        private static bool KnownDrinkGame(string graph)
        {
            switch(graph){
                case "BaoZuPo_HeJiu":case "BaoZuPo_HeJiuChongFu":case "LaoBanNianHeJiuXiTong":
                case "LaoBanNianHeJiuYouXi":case "MEIMEI_HeJiuXiTong":case "Victoria_HeJiu":
                case "XIAOFUPO_HeJiu":case "ZhaoZong_HeJiu":return true;
                default:return false;
            }
        }
        internal static int ChoicePriority(string name,bool massage,bool drinking,bool combat)
        {
            if(massage){
                switch(name){
                    case "捶背": case "按腿": case "按脚": case "揉肩": case "仙人掌":return 3;
                    // Once there is no treatment left, take the normal end-of-session option.
                    case "离开":return 1;
                }
            }
            if(drinking){
                switch(name){
                    case "干杯":return 4;
                    case "玩骰子": case "游戏时间":return 3;
                }
            }
            if(combat){
                switch(name){
                    case "普通攻击": case "攻击":return 4;
                    case "我就要挑战这个QTE": case "防守":return 3;
                }
            }
            return 0;
        }
        private static bool PlayDrinkResult(VideoItem video)
        {
            var graph=video._videoNode.graph;
            VideoNode destination=null;
            foreach(var node in graph.nodes){
                if(node==null)continue;
                var gate=node.TryCast<VideoIfTargetEbriety>();
                if(gate==null || !gate.IsSuc())continue;
                var port=gate.GetOutputPort("outputSuccess");
                if(port==null)continue;
                var results=FrameWork.Tool.GetAllVideoNodes(port);
                if(results==null || results.Count!=1 || results[0]==null)return false;
                var next=results[0];
                if(next.graph==null || next.graph.Pointer!=graph.Pointer || (destination!=null && destination.Pointer!=next.Pointer))return false;
                destination=next;
            }
            if(destination==null || destination.Pointer==video._videoNode.Pointer)return false;
            drinkFinished=true;
            video.ToNextVideoNode(destination);
            return true;
        }

        internal static bool Negotiation(AiChatWindows __instance)
        {
            try{
                if(!Ready() || GameScene.Instance==null)return true;
                var video=GameScene.Instance.videoItem;
                var slot=GameSlot.Current();
                if(slot==null || video==null || video._videoNode==null || video._videoNode.graph==null ||
                    slot.Manager.CurVideoId!=video._videoNode.uniqueID || !video._videoNode.isShowAiInfo || video._videoNode.graph.name!="TanpPan")return true;
                var result=FrameWork.Tool.GetAllVideoNodesOutNor(video._videoNode,"aiChatSuc2");
                if(result==null || result.Count!=1 || result[0]==null || !Plugin.State.PrepareMiniGame(slot))return true;
                __instance.CheckSuc(new DeepSeekChat.AIChatResultCondition{tag="negotiation_perfect_win"});
                return false;
            }catch(Exception error){Plugin.State.StopMiniGame(error);return false;}
        }

        private static IntPtr pinball;
        private static bool pinballRequested;
        private static Promise<JSONNode> settlementQuery;
        private static long nextSettlementCheck;
        internal static void Reset()
        {
            ResetPinball(IntPtr.Zero);
            drinkFinished=false;
        }
        private static void ResetPinball(IntPtr launcher)
        {
            pinball=launcher;
            pinballRequested=false;
            settlementQuery=null;
            nextSettlementCheck=0;
        }
        internal static void PinballLoaded(MinigameWebViewLauncher __instance)
        {
            ResetPinball(__instance.Pointer);
        }
        internal static void TickPinball(GameSlot slot)
        {
            try{
                if(pinball==IntPtr.Zero || slot==null || !Ready() || !UiManager.IsShowUi<GameWindows>())return;
                var window=UiManager.GetUi<GameWindows>();
                var launcher=window==null?null:window.MinigameWebViewLauncherGameView;
                if(launcher==null || launcher.Pointer!=pinball || !launcher.isActiveAndEnabled || !FrontWindow(window))return;
                var browser=launcher.browser;
                if(browser==null || !browser.IsReady || launcher.gameFolder!="Pinball" || launcher.indexFile!="index.html")return;
                var expected=Path.Combine(Application.streamingAssetsPath,"MiniGame","Pinball","index.html");
                if(!String.Equals(Path.GetFullPath(launcher.GetGamePath()),Path.GetFullPath(expected),StringComparison.OrdinalIgnoreCase))return;
                if(!pinballRequested){
                    if(!Plugin.State.PrepareMiniGame(slot))return;
                    pinballRequested=true;
                    browser.EvalJS(PinballFinishScript,"RiseAloneTrainer");
                }
                if(settlementQuery!=null){
                    if(settlementQuery.CurState==PromiseState.Pending)return;
                    if(settlementQuery.CurState!=PromiseState.Resolved)throw new InvalidOperationException("未能读取收盘状态");
                    var value=settlementQuery.Value;
                    settlementQuery=null;
                    if(value!=null && value.AsJSON=="true"){
                        ResetPinball(IntPtr.Zero);
                        window.CloseUi();
                        return;
                    }
                }
                long now=Environment.TickCount64;
                if(now<nextSettlementCheck)return;
                nextSettlementCheck=now+300;
                settlementQuery=browser.EvalJS(PinballSettledScript,"RiseAloneTrainer").Cast<Promise<JSONNode>>();
            }catch(Exception error){
                ResetPinball(IntPtr.Zero);
                Plugin.State.Last="弹珠机自动收盘已停止："+error.GetBaseException().Message;
            }
        }
        internal const string PinballFinishScript="(()=>{const g=window.game;if(document.title==='牛熊弹珠机' && g && (g.phase==='preopen'||g.phase==='open')){g.preCountdown=0;g.openTime=0;}})()";
        internal const string PinballSettledScript="document.title==='牛熊弹珠机' && !!window.game && window.game.phase==='closed' && window.game.gameEndNotified===true";
        private static bool FrontWindow(UiActor actor)
        {
            var root=actor.transform;
            if(root==null || !root.gameObject.activeInHierarchy || root.parent==null)return false;
            var parent=root.parent;
            for(int i=root.GetSiblingIndex()+1;i<parent.childCount;i++){
                var other=parent.GetChild(i);
                if(!other.gameObject.activeInHierarchy)continue;
                var owner=other.GetComponent<ActorMono>();
                if(owner!=null && owner.GetActor()!=null && owner.GetActor().IsCanJoinPause())return false;
            }
            return true;
        }
        internal static bool AllowQteClick(QteBtn __instance)
        {
            if(!Plugin.State.CheckMiniGames || __instance._data==null)return true;
            return !__instance._data.isSucEx;
        }

        // A prefix lets a completed button skip its timer/input pass in the same frame.
        internal static bool QteUpdate(QteBtn __instance)
        {
            try{
                var button=__instance;
                if(!Ready() || !button._isInit || !button.isActiveAndEnabled)return true;
                var data=button._data;
                if(data==null || data.isSucEx || button._action==null || data.qteType!=button.qteType)return true;
                if(!(button._showTime>0 && button._curTime>=0 && button._curTime<button._showTime))return true;
                int taps=1;
                switch(button.qteType){
                    case QteType.ClickGo:
                        taps=MiniGameTiming.TapsDue(data.clickCount,button._clickCount,button._curTime,button._showTime,Time.deltaTime);
                        if(taps==0)return true;
                        break;
                    case QteType.SlideGo:
                        if(button.ag==null || button.target==null || button._moveTweener==null)return true;
                        var bar=button.target.rectTransform;
                        if(!(bar.sizeDelta.x>0))return true;
                        if(!MiniGameTiming.InsideBar(button.ag.rectTransform.anchoredPosition.x,bar.anchoredPosition.x,bar.sizeDelta.x) &&
                            button._curTime+Time.deltaTime<button._showTime)return true;
                        break;
                    case QteType.KeyGo:
                    case QteType.CondensationGo:
                        break;
                    default:return true;
                }
                var scene=GameScene.Instance;
                if(scene==null || scene.videoItem==null)return true;
                var video=scene.videoItem;
                if(!video._isCanEx || video._videoNode==null || video.qteGroup==null || button.transform.parent==null ||
                    button.transform.parent.Pointer!=video.qteGroup.Pointer || !UiManager.IsCanPlay())return true;
                var slot=GameSlot.Current();
                if(slot==null || slot.Manager.CurVideoId!=video._videoNode.uniqueID || !Plugin.State.PrepareMiniGame(slot))return true;
                if(button.qteType==QteType.SlideGo || button.qteType==QteType.KeyGo){
                    button._isInit=false;
                    if(button.qteType==QteType.SlideGo){
                        TweenExtensions.Kill(button._moveTweener,false);
                        var marker=button.ag.rectTransform;var region=button.target.rectTransform;
                        var position=marker.anchoredPosition;
                        if(!MiniGameTiming.InsideBar(position.x,region.anchoredPosition.x,region.sizeDelta.x)){
                            position.x=region.anchoredPosition.x+region.sizeDelta.x*0.5f;
                            marker.anchoredPosition=position;
                        }
                    }
                    button._action.Invoke();
                    return false;
                }
                for(int i=0;i<taps;i++){
                    button.OnClick();
                    if(data.isSucEx || !button._isInit)return false;
                }
                return true;
            }catch(Exception error){Plugin.State.StopMiniGame(error);return false;}
        }

        internal static void ScratchUpdate(CaiPiaoWindows __instance)
        {
            try{
                if(!Ready() || __instance.isCompleted || __instance.eraseTexture==null || __instance.totalPixels<=0)return;
                if(!FrontWindow(__instance))return;
                if(!Plugin.State.PrepareMiniGame(GameSlot.Current()))return;
                __instance.EraseAll();
                __instance.CheckEraseRatio();
                if(!__instance.isCompleted)throw new InvalidOperationException("本张刮刮卡尚未确认完成。");
            }catch(Exception error){Plugin.State.StopMiniGame(error);}
        }

        internal static void GrabUpdate(Hook __instance)
        {
            try{
                if(!Ready() || !__instance.isActiveAndEnabled)return;
                var game=MiNiGameMrg.Instance;
                if(game==null || game.isOver || game.hook==null || game.hook.Pointer!=__instance.Pointer ||
                    game._timeData==null || game._xlsxMiNiGameLevel==null || !UiManager.IsCanPlay())return;
                int target=game._xlsxMiNiGameLevel.Target;
                var slot=GameSlot.Current();
                if(target< -1 || slot==null || slot.Manager.xlsxMiNiGameLevelKey!=game._xlsxMiNiGameLevel.Key ||
                    !Plugin.State.PrepareMiniGame(slot))return;
                // A9 has no score target. Its timer settles the current score against -1.
                if(target>=0)game.score=Math.Max(game.score,target);
                game.GameOver(true);
                if(!game.isOver)throw new InvalidOperationException("抓取关卡未确认结算。");
            }catch(Exception error){Plugin.State.StopMiniGame(error);}
        }
    }
}
