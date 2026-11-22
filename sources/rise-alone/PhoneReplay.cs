using System;
using FrameWork;
using Xlsx;

namespace RiseAlone
{
    internal static class PhoneReplay
    {
        internal static void Open(Xlsx_Message contact,Action restore,Func<PhoneWindows,bool> sameContact){
            var main=UiManager.IsOpenUi<MainWindows>()?UiManager.GetUi<MainWindows>():UiManager.OpenUi<MainWindows>();
            var window=main.OpenMessage();
            if(window==null || main._curOpenUi==null || main._curOpenUi.Pointer!=window.Pointer)
                throw new InvalidOperationException("手机页面尚未接入主界面，请返回后再重选。");
            if(window._isChat && window.RectTransformChat.gameObject.activeInHierarchy){
                if(sameContact(window))return;
                throw new InvalidOperationException("另一段手机对话正在播放，请读完后再重选。");
            }
            // Opening the native phone increments its usage counter. Restore before starting the reply chain.
            restore();
            window.InitChat(contact);
        }
    }
}
