using System;
using FrameWork;
using Script.Scene;
using Script.Tool;

namespace RiseAlone
{
    internal static class ChoiceTimer
    {
        private static VideoItem heldItem;
        private static VideoNode heldNode;
        private static IntPtr heldPlayer;
        private static bool Owned {get{return !System.Object.ReferenceEquals(heldItem,null);}}

        private static bool Matches(VideoItem item){
            return item!=null && heldItem!=null && item.Pointer==heldItem.Pointer && heldNode!=null &&
                item._videoNode==heldNode && item.videoPlayer!=null && item.videoPlayer.Pointer==heldPlayer;
        }
        private static bool Current(VideoItem item){
            var scene=GameScene.Instance;
            return scene!=null && item!=null && scene.videoItem==item && item.isActiveAndEnabled && item._isCanEx;
        }
        private static bool HasChoice(VideoItem item){
            var layer=item.canvasGroup;
            if(layer==null || !(layer.alpha>.01f) || !layer.interactable || !layer.blocksRaycasts)return false;
            var group=item.btnGroup;
            if(group!=null && group.gameObject.activeInHierarchy){
                for(int i=0;i<group.childCount;i++){
                    var child=group.GetChild(i);
                    if(!child.gameObject.activeInHierarchy)continue;
                    var button=child.GetComponent<VideoButton>();
                    if(button!=null && button.isActiveAndEnabled && button._isCanClick && button._videoItem==item &&
                        button._lastVideoNode==item._videoNode && button.canvasGroup!=null && button.canvasGroup.alpha>.01f &&
                        button.canvasGroup.blocksRaycasts && button.bt!=null && button.bt.isActiveAndEnabled &&
                        button.text!=null && button.text.isActiveAndEnabled && !String.IsNullOrWhiteSpace(button.text.text) &&
                        TaskChoices.CanChoose(button,button.GetButtonNode()))return true;
                }
            }
            // On combat prompts the game places the available moves in a separate window.
            if(!item._videoNode.isHasQte || !UiManager.IsShowUi<CombatWindows>())return false;
            var window=UiManager.GetUi<CombatWindows>();
            if(window==null || window.RectTransformBtnGroup==null || !window.RectTransformBtnGroup.gameObject.activeInHierarchy ||
               window._buttonNodes==null || window._buttonNodes.Count==0)return false;
            foreach(var move in window.RectTransformBtnGroup.GetComponentsInChildren<BT>())
                if(move.isActiveAndEnabled && move.IsInteractable())return true;
            return false;
        }
        private static bool ShowsTimer(VideoItem item){
            var node=item._videoNode;
            return node!=null && node.isHasBtn && !node.isLoopVideo && !item._isCanCallPlay &&
                item.isShowButton && !item.isHideButton && item.btnProgressGo!=null && item.btnProgressGo.activeInHierarchy;
        }
        internal static void Forget(){
            heldItem=null;heldNode=null;heldPlayer=IntPtr.Zero;
        }
        internal static void Release(){
            if(!Owned)return;
            var item=heldItem;
            try{
                if(!Matches(item) || !Current(item))return;
                var control=item.videoPlayer.Control;
                if(control!=null && control.IsPaused())item.Play();
            }catch(Exception e){Plugin.State.Last="恢复选择计时失败："+e.GetBaseException().Message;}
            finally{Forget();}
        }
        internal static void ButtonsRemoved(VideoItem __instance){
            if(Owned && heldItem!=null && __instance==heldItem)Release();
        }
        internal static void CheckOwner(){
            if(!Owned)return;
            try{
                if(!Current(heldItem) || !Matches(heldItem)){Forget();return;}
                if(!Plugin.State.CheckChoiceTimer || !ShowsTimer(heldItem) || !HasChoice(heldItem))Release();
            }catch(Exception e){
                Plugin.State.Last="做选择不限时："+e.GetBaseException().Message;
                Release();
            }
        }
        internal static bool BeforeChoices(VideoItem __instance){
            if(!Plugin.State.CheckChoiceTimer)return true;
            var item=__instance;
            try{
                if(!Current(item))return true;
                if(Owned && !Matches(item))Forget();
                if(!ShowsTimer(item) || item.videoPlayer==null)return true;
                var control=item.videoPlayer.Control;
                if(control==null || (!Owned && !control.IsPlaying()) || item.videoPlayer.Info==null)return true;
                var node=item._videoNode;
                double show=node.videoBtnShowTime,hide=node.videoBtnHideTime;
                double duration=item.GetVideoTime(),now=item.GetCurVideoTime();
                // CheckBtn displays a countdown only when the button expires before the clip ends.
                if(Double.IsInfinity(duration) || !(show>=0 && hide>show && hide<duration && now>=show && now<duration))return true;
                double guard=Math.Min(.5,(hide-show)*.5);
                if(now<hide-guard || !HasChoice(item))return true;
                if(control.IsPlaying()){
                    item.Pause("RiseAloneTrainer: 限时选项即将超时，等待选择");
                    heldItem=item;heldNode=node;heldPlayer=item.videoPlayer.Pointer;
                }
                // A slow frame can cross the deadline. Preserve the already visible answers on that frame.
                return now<hide;
            }catch(Exception e){
                Plugin.State.Last="做选择不限时："+e.GetBaseException().Message;
                if(Owned)Release();
                return true;
            }
        }
    }
}
