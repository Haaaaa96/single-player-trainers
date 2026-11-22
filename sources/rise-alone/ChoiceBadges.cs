using System;
using System.Collections.Generic;
using Il2CppInterop.Runtime;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace RiseAlone
{
    internal static class ChoiceBadges
    {
        private sealed class Option {
            internal TMP_Text Title;
            internal Transform Group;
            internal IntPtr Prompt;
            internal TextMeshProUGUI Hint;
            internal ChoiceRank Rank;
            internal string Warning;
            internal string Summary,LockedSummary;
            internal Func<bool> Allowed;
            internal Rect Bounds;
            internal float FontSize;
        }
        private static readonly List<Option> options=new List<Option>();
        internal static bool Any=>options.Count!=0;

        internal static void Set(TMP_Text title,Transform group,IntPtr prompt,ChoiceRank rank,string warning,Func<bool> allowed){
            Forget(title);
            if(group==null || title==null)return;
            // A pooled group can switch prompts before the old children have been hidden.
            for(int i=options.Count-1;i>=0;i--){
                if(options[i].Group==group && options[i].Prompt!=prompt)Remove(i);
            }
            options.Add(new Option{Title=title,Group=group,Prompt=prompt,Rank=rank,Warning=warning,Allowed=allowed,
                Summary=ChoiceEffects.Describe(rank,false),LockedSummary=ChoiceEffects.Describe(rank,true)});
        }
        internal static void Forget(TMP_Text title){
            for(int i=options.Count-1;i>=0;i--)if(options[i].Title==title)Remove(i);
        }
        private static void Remove(int i){
            var hint=options[i].Hint;
            if(hint!=null){hint.gameObject.SetActive(false);UnityEngine.Object.Destroy(hint.gameObject);}
            options.RemoveAt(i);
        }
        internal static void Clear(){for(int i=options.Count-1;i>=0;i--)Remove(i);}
        private static void Hide(Option option){
            if(option.Hint!=null && option.Hint.gameObject.activeSelf)option.Hint.gameObject.SetActive(false);
        }
        private static TextMeshProUGUI Hint(Option option,RectTransform parent){
            if(option.Hint!=null)return option.Hint;
            var go=new GameObject("RiseAlone.ChoiceTag",new[]{Il2CppType.Of<RectTransform>()});
            // The game clones the first button in a pool, including all its children.
            // Keep our graphics outside both the button and the collection the game enumerates.
            go.transform.SetParent(parent,false);go.layer=parent.gameObject.layer;
            go.AddComponent<LayoutElement>().ignoreLayout=true;
            var hint=go.AddComponent<TextMeshProUGUI>();
            hint.raycastTarget=false;hint.richText=false;hint.enableWordWrapping=false;
            hint.enableAutoSizing=true;hint.alignment=TextAlignmentOptions.Center;
            hint.overflowMode=TextOverflowModes.Ellipsis;
            option.Hint=hint;return hint;
        }
        private static bool Measure(Option option,RectTransform parent){
            var source=option.Title.rectTransform;
            var bounds=option.Title.textBounds;
            if(option.Title.canvas==null || bounds.size.x<=0f || bounds.size.y<=0f)return false;
            var low=parent.InverseTransformPoint(source.TransformPoint(bounds.min));
            var high=parent.InverseTransformPoint(source.TransformPoint(bounds.max));
            option.Bounds=Rect.MinMaxRect(Mathf.Min(low.x,high.x),Mathf.Min(low.y,high.y),Mathf.Max(low.x,high.x),Mathf.Max(low.y,high.y));
            var unit=parent.InverseTransformVector(source.TransformVector(Vector3.up));
            option.FontSize=Mathf.Max(1f,unit.magnitude*option.Title.fontSize*.46f);
            return true;
        }
        private static Rect Viewport(RectTransform parent,TMP_Text title){
            var canvas=title.canvas.rootCanvas;
            var camera=canvas.renderMode==RenderMode.ScreenSpaceOverlay?null:canvas.worldCamera;
            var safe=Screen.safeArea;
            if(safe.width>0 && safe.height>0 &&
               RectTransformUtility.ScreenPointToLocalPointInRectangle(parent,safe.min,camera,out var low) &&
               RectTransformUtility.ScreenPointToLocalPointInRectangle(parent,safe.max,camera,out var high) &&
               high.x>low.x && high.y>low.y)return Rect.MinMaxRect(low.x,low.y,high.x,high.y);
            return parent.rect;
        }
        internal static bool Place(Rect title,Vector2 size,Rect area,List<Rect> occupied,out Rect placed){
            placed=default;
            if(area.width<size.x || area.height<size.y)return false;
            float gap=size.y*.16f;
            float below=title.yMin-gap-size.y,above=title.yMax+gap;
            float center=title.center.x-size.x*.5f;
            var anchors=new[]{new Vector2(center,below),new Vector2(title.xMax+gap,title.center.y-size.y*.5f),
                              new Vector2(title.xMin-gap-size.x,title.center.y-size.y*.5f),new Vector2(center,above)};
            for(int row=0;row<=4;row++){
                foreach(var anchor in anchors){
                    float offset=row==0?0:((row+1)/2)*(size.y+gap)*(row%2==0?1:-1);
                    var box=new Rect(Mathf.Clamp(anchor.x,area.xMin,area.xMax-size.x),
                                     Mathf.Clamp(anchor.y+offset,area.yMin,area.yMax-size.y),size.x,size.y);
                    if(!occupied.Exists(other=>other.Overlaps(box))){placed=box;return true;}
                }
            }
            float bestDistance=float.PositiveInfinity;
            for(float y=area.yMin;y+size.y<=area.yMax;y+=size.y+gap){
                for(float x=area.xMin;x+size.x<=area.xMax;x+=size.x+gap){
                    var box=new Rect(x,y,size.x,size.y);
                    float distance=(box.center-title.center).sqrMagnitude;
                    if(distance>=bestDistance || occupied.Exists(other=>other.Overlaps(box)))continue;
                    bestDistance=distance;placed=box;
                }
            }
            if(!float.IsPositiveInfinity(bestDistance))return true;
            return false;
        }
        private static string Wrap(string text,int columns,out int width,out int lines){
            var result=new System.Text.StringBuilder();
            width=0;lines=0;
            foreach(var paragraph in text.Split('\n')){
                for(int start=0;start<paragraph.Length;){
                    int count=Math.Min(columns,paragraph.Length-start);
                    if(start+count<paragraph.Length){
                        int separator=paragraph.LastIndexOf('、',start+count-1,count);
                        if(separator>=start)count=separator-start+1;
                    }
                    if(lines>0)result.Append('\n');
                    result.Append(paragraph,start,count);
                    width=Math.Max(width,count);lines++;start+=count;
                }
            }
            return result.ToString();
        }
        private static void Draw(Option option,bool best,bool zeroPressure,RectTransform parent,Rect area,List<Rect> occupied,bool expanded=false){
            bool warning=!String.IsNullOrEmpty(option.Warning);
            string prefix=warning?(best?"最佳 · "+option.Warning:option.Warning):(best?"最佳":"");
            string summary=zeroPressure?option.LockedSummary:option.Summary;
            string full=prefix.Length==0?summary:prefix+"\n"+summary;
            float size=0;
            Rect box=default;
            string text=null;
            for(int attempt=0;attempt<3;attempt++){
                size=option.FontSize*(1f-.15f*attempt);
                int columns=expanded?Math.Max(4,(int)(area.width/size)-1):Math.Max(4,Math.Min(30,(int)(area.width*.46f/size)));
                string wrapped=Wrap(full,columns,out int width,out int lines);
                var boxSize=new Vector2((width+.8f)*size,(lines*1.28f+.18f)*size);
                if(Place(option.Bounds,boxSize,area,occupied,out box)){text=wrapped;break;}
            }
            if(text==null){Hide(option);return;}
            occupied.Add(box);
            var hint=Hint(option,parent);
            var rect=hint.rectTransform;
            rect.anchorMin=rect.anchorMax=parent.pivot;rect.pivot=new Vector2(.5f,.5f);
            rect.anchoredPosition=box.center;rect.sizeDelta=box.size;
            if(hint.font!=option.Title.font)hint.font=option.Title.font;
            hint.fontSizeMin=size*.8f;hint.fontSizeMax=size;
            hint.color=warning?new Color(1f,.84f,.52f):best?new Color(.63f,1f,.74f):new Color(1f,.96f,.84f);
            if(hint.text!=text)hint.text=text;
            if(!hint.gameObject.activeSelf)hint.gameObject.SetActive(true);
        }
        private static void RefreshGroup(List<Option> shown,bool zeroPressure){
            var parent=shown[0].Group.parent?.GetComponent<RectTransform>();
            if(parent==null){foreach(var option in shown)Hide(option);return;}
            shown.RemoveAll(option=>{if(Measure(option,parent))return false;Hide(option);return true;});
            if(shown.Count==0)return;
            var area=Viewport(parent,shown[0].Title);
            Option best=null;
            int eligible=0;
            bool tied=false;
            var occupied=new List<Rect>(shown.Count*2);
            foreach(var option in shown){
                occupied.Add(option.Bounds);
                if(!option.Rank.Known)continue;
                try{if(!option.Allowed())continue;}catch(Exception){continue;}
                eligible++;
                int comparison=best==null?1:option.Rank.CompareTo(best.Rank,zeroPressure);
                if(comparison>0){
                    best=option;
                    tied=false;
                }else if(comparison==0){
                    tied=true;
                }
            }
            if(eligible<2 || tied)best=null;
            foreach(var option in shown){
                if(!String.IsNullOrEmpty(option.Warning))Draw(option,option==best,zeroPressure,parent,area,occupied);
            }
            if(best!=null && String.IsNullOrEmpty(best.Warning))Draw(best,true,zeroPressure,parent,area,occupied);
            foreach(var option in shown){
                if(option!=best && String.IsNullOrEmpty(option.Warning))Draw(option,false,zeroPressure,parent,area,occupied);
            }
            if(!shown.Exists(option=>option.Hint==null || !option.Hint.gameObject.activeSelf))return;
            var canvas=shown[0].Title.canvas.rootCanvas;
            var camera=canvas.renderMode==RenderMode.ScreenSpaceOverlay?null:canvas.worldCamera;
            if(!RectTransformUtility.ScreenPointToLocalPointInRectangle(parent,Input.mousePosition,camera,out var mouse))return;
            var focus=shown.Find(option=>option.Bounds.Contains(mouse));
            if(focus==null || (focus.Hint!=null && focus.Hint.gameObject.activeSelf))return;
            var titles=shown.ConvertAll(option=>option.Bounds);
            Draw(focus,focus==best,zeroPressure,parent,area,titles,true);
            if(focus.Hint==null || !focus.Hint.gameObject.activeSelf)return;
            Rect focused=titles[titles.Count-1];
            foreach(var option in shown){
                if(option==focus || option.Hint==null || !option.Hint.gameObject.activeSelf)continue;
                var rect=option.Hint.rectTransform;
                if(focused.Overlaps(new Rect(rect.anchoredPosition-rect.sizeDelta*.5f,rect.sizeDelta)))Hide(option);
            }
        }
        internal static void Refresh(bool zeroPressure=false){
            if(!Any)return;
            var groups=new Dictionary<IntPtr,List<Option>>();
            for(int i=options.Count-1;i>=0;i--){
                var option=options[i];
                if(option.Title==null || option.Group==null){Remove(i);continue;}
                if(!option.Title.isActiveAndEnabled || !option.Group.gameObject.activeInHierarchy){Hide(option);continue;}
                if(!groups.TryGetValue(option.Group.Pointer,out var group)){group=new List<Option>();groups.Add(option.Group.Pointer,group);}
                group.Add(option);
            }
            foreach(var group in groups.Values)RefreshGroup(group,zeroPressure);
        }
    }
}
