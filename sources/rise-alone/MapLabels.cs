using System;
using System.Collections.Generic;
using FrameWork;
using Il2CppInterop.Runtime;
using Script.Mrg;
using Script.Scene;
using Script.Tool;
using Script.UiTool;
using UnityEngine;
using UnityEngine.UI;

namespace RiseAlone
{
    internal static class MapLabels
    {
        private static GameObject layer;
        private static RectTransform host;
        private static Font font;
        private static bool ownsFont;
        private static readonly Dictionary<int,Text> labels=new Dictionary<int,Text>();
        private static readonly Dictionary<int,Text> worldLabels=new Dictionary<int,Text>();
        private static IntPtr scenePointer;
        private static string slotIdentity;
        private static long next;
        internal static bool Visible {get{return layer!=null || worldLabels.Count!=0;}}
        private static void ClearFlat(){
            if(layer!=null){layer.SetActive(false);UnityEngine.Object.Destroy(layer);}
            host=null;layer=null;labels.Clear();
        }
        private static void RemoveWorldExcept(HashSet<int> visible){
            if(worldLabels.Count==0)return;
            foreach(int id in new List<int>(worldLabels.Keys)){
                if(visible!=null && visible.Contains(id))continue;
                var label=worldLabels[id];
                if(label!=null){label.gameObject.SetActive(false);UnityEngine.Object.Destroy(label.gameObject);}
                worldLabels.Remove(id);
            }
        }
        private static void Clear(){
            ClearFlat();RemoveWorldExcept(null);scenePointer=IntPtr.Zero;slotIdentity=null;
        }
        internal static void Release(){
            Clear();
            if(ownsFont && font!=null)UnityEngine.Object.Destroy(font);
            font=null;ownsFont=false;next=0;
        }
        private static bool Surface(out RectTransform group,out RectTransform image){
            group=null;image=null;
            if(UiManager.IsShowUi<MapWindows>()){
                var map=UiManager.GetUi<MapWindows>();
                group=map.RectTransformPointGroup;image=map.RectTransformRawImage;
            }else{
                MapTool view=null;
                if(UiManager.IsShowUi<MapRiWindows>())view=UiManager.GetUi<MapRiWindows>().MapToolView;
                if(view==null && UiManager.IsShowUi<MapYeWindows>())view=UiManager.GetUi<MapYeWindows>().MapToolView;
                if(view!=null && view.isActiveAndEnabled && view.mapImg!=null){group=view.content;image=view.mapImg.rectTransform;}
            }
            return group!=null && group.parent!=null && group.gameObject.activeInHierarchy && image!=null;
        }
        private static void PrepareLayer(RectTransform group){
            if(layer==null || host==null || host.Pointer!=group.Pointer){
                ClearFlat();host=group;
                layer=new GameObject("RiseAlone.LocationLabels",new[]{Il2CppType.Of<RectTransform>()});
                layer.transform.SetParent(group.parent,false);
                layer.layer=group.gameObject.layer;
            }
            var rect=layer.GetComponent<RectTransform>();
            rect.anchorMin=group.anchorMin;rect.anchorMax=group.anchorMax;rect.pivot=group.pivot;
            rect.sizeDelta=group.sizeDelta;rect.anchoredPosition=group.anchoredPosition;
            rect.localScale=group.localScale;rect.localRotation=group.localRotation;
        }
        private static Text Marker(Dictionary<int,Text> cache,int id,Transform parent){
            Text label;
            if(cache.TryGetValue(id,out label) && label!=null)return label;
            if(font==null){font=Font.CreateDynamicFontFromOSFont("Microsoft YaHei UI",17);ownsFont=font!=null;}
            if(font==null)font=Resources.GetBuiltinResource<Font>("Arial.ttf");
            var go=new GameObject("RiseAlone.Location",new[]{Il2CppType.Of<RectTransform>()});
            go.layer=parent.gameObject.layer;
            go.transform.SetParent(parent,false);
            label=go.AddComponent<Text>();label.font=font;label.fontSize=16;
            label.alignment=TextAnchor.MiddleCenter;label.raycastTarget=false;label.supportRichText=false;
            label.color=new Color(1f,.88f,.58f);label.rectTransform.sizeDelta=new Vector2(165,48);
            var outline=go.AddComponent<Outline>();outline.effectColor=new Color(.06f,.07f,.09f,.95f);
            outline.effectDistance=new Vector2(1.4f,-1.4f);
            cache[id]=label;return label;
        }
        private const string Status="未解锁 · 可进入";
        private static void MarkWorld(Map3DTriggerr point,int id,string name,HashSet<int> used){
            var title=point.languageComponent.GetComponent<TMPro.TMP_Text>();
            if(title==null)return;
            var canvas=title.GetComponentInParent<Canvas>(true);
            if(canvas==null || canvas.renderMode!=RenderMode.WorldSpace || !canvas.isActiveAndEnabled)return;
            var label=Marker(worldLabels,id,canvas.transform);
            // The game can hide the icon or title independently. Anchor to it without inheriting its visibility.
            var anchor=title.rectTransform;
            var rect=label.rectTransform;
            rect.pivot=new Vector2(.5f,1f);
            rect.rotation=anchor.rotation;
            rect.position=anchor.TransformPoint(new Vector3(anchor.rect.center.x,anchor.rect.yMin-2f,0f));
            bool named=title.isActiveAndEnabled && !String.IsNullOrWhiteSpace(title.text);
            label.alignment=TextAnchor.UpperCenter;
            label.text=named?Status:name+"\n"+Status;
            used.Add(id);
        }
        internal static void Tick(GameSlot slot){
            if(!Plugin.State.MapLabels || slot==null){if(scenePointer!=IntPtr.Zero || Visible)Clear();next=0;return;}
            long now=Environment.TickCount64;
            if(now<next)return;
            next=now+500;
            try{
                var scene=Map3DScene.Instance;
                if(scene==null || scene.pointGroup==null){Clear();return;}
                if(scenePointer!=scene.Pointer || slotIdentity!=slot.LoadedSlot){
                    Clear();scenePointer=scene.Pointer;slotIdentity=slot.LoadedSlot;
                }
                bool free=!slot.Manager.Is2D;
                RectTransform group=null,image=null;
                bool flat=scene.mapCamera!=null && Surface(out group,out image);
                if(flat)PrepareLayer(group);else ClearFlat();
                if(!free && !flat){RemoveWorldExcept(null);return;}
                var gated=new HashSet<CollType>();
                foreach(var type in FrameWork.Tool.GetMapLockPoint())gated.Add(type);
                var used=new HashSet<int>();
                var worldUsed=new HashSet<int>();
                for(int i=0;i<scene.pointGroup.childCount;i++){
                    var point=scene.pointGroup.GetChild(i).GetComponent<Map3DTriggerr>();
                    if(point==null || point.languageComponent==null)continue;
                    var type=point.collType;
                    if(type==CollType.Test || type==CollType.CheShiDian || (int)type<=0)continue;
                    if(!MapEligibility.ShouldMark(point,gated,slot.Manager))continue;
                    string name=LanguageMrg.GetText(point.languageComponent.key);
                    if(String.IsNullOrWhiteSpace(name))continue;
                    int id=point.GetInstanceID();
                    if(free)MarkWorld(point,id,name,worldUsed);
                    if(!flat)continue;
                    var size=image.rect;
                    var pos2=scene.mapCamera.WorldToViewportPoint(point.transform.position);
                    if(pos2.z<=0 || pos2.x<0 || pos2.y<0 || pos2.x>1 || pos2.y>1)continue;
                    var label=Marker(labels,id,layer.transform);
                    label.text=name+"\n"+Status;
                    label.rectTransform.localPosition=new Vector3((pos2.x-.5f)*size.width,(pos2.y-.5f)*size.height+18f,0f);
                    label.gameObject.SetActive(true);used.Add(id);
                }
                foreach(var pair in labels)if(!used.Contains(pair.Key) && pair.Value!=null)pair.Value.gameObject.SetActive(false);
                RemoveWorldExcept(worldUsed);
            }catch(Exception e){Clear();next=now+3000;Plugin.State.Last="地图标记："+e.GetBaseException().Message;}
        }
    }
}
