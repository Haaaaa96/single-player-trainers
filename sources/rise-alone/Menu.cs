using System;
using Il2CppInterop.Runtime;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using TMPro;

namespace RiseAlone
{
    internal sealed class Menu
    {
        internal static bool Visible;
        internal static int ConsumeUntil=-1;
        private GameObject root,previousFocus;
        private Font font;
        private Text title,value,status,energyText,favorText,pressureText,miniText;
        private Text rentalHint;
        private InputField input;
        private Button apply,energy,favor,pressure,mini,save;
        private GameObject numbers,assists;
        private Button numbersTab,assistTab,statsTab,peopleTab,npcTab,guard,mapToggle,undo,resume;
        private Text npcHint;
        private Text guardText,mapText,checkpoint;
        private Button choiceTimer;
        private Text choiceTimerText;
        private ChoicePoint shownPoint;
        private bool assistPage;
        private readonly Button[] rows=new Button[14];
        private readonly Text[] rowText=new Text[14];
        private Entry[] entries=Catalog.Stats;
        private Entry selected=Catalog.Stats[0];
        private Reading observed;
        private string displayedSession;
        private bool busy,oldVisible;
        private CursorLockMode oldLock;
        private int clickFrame=-1;
        private long holdStatus;
        private static readonly Color White=new Color(0.95f,0.97f,0.98f);
        private static readonly Color Card=new Color(0.11f,0.16f,0.20f);
        private static readonly Color Normal=new Color(0.19f,0.25f,0.29f);
        private static readonly Color Accent=new Color(0.06f,0.44f,0.41f);
        internal bool CanOpen()
        {
            if(!String.IsNullOrEmpty(Input.compositionString))return false;
            var es=EventSystem.current;
            var focus=es==null?null:es.currentSelectedGameObject;
            if(focus==null || !focus.activeInHierarchy)return true;
            var standard=focus.GetComponent<InputField>();
            var tmp=focus.GetComponent<TMP_InputField>();
            return (standard==null || !standard.isFocused) && (tmp==null || !tmp.isFocused);
        }
        internal void Open()
        {
            if(Visible)return;
            if(root==null){
                try{Build();}catch{Release();throw;}
            }
            var es=EventSystem.current;
            previousFocus=es==null?null:es.currentSelectedGameObject;
            oldVisible=Cursor.visible;oldLock=Cursor.lockState;
            Cursor.lockState=CursorLockMode.None;Cursor.visible=true;
            root.SetActive(true);Visible=true;
            if(es!=null)es.SetSelectedGameObject(null);
            input.text="";observed=null;displayedSession=null;holdStatus=0;
            status.text="";Refresh(GameSlot.Current());
        }
        internal void Close()
        {
            if(!Visible)return;
            TaskChoices.Continue();
            Visible=false;ConsumeUntil=Time.frameCount+1;
            observed=null;displayedSession=null;
            var es=EventSystem.current;
            var focus=es==null?null:es.currentSelectedGameObject;
            bool owned=focus!=null && root!=null && focus.transform.IsChildOf(root.transform);
            if(input!=null && input.isFocused)input.DeactivateInputField();
            if(root!=null)root.SetActive(false);
            if(es!=null && (owned || focus==null))es.SetSelectedGameObject(previousFocus!=null && previousFocus.activeInHierarchy?previousFocus:null);
            previousFocus=null;
            if(Cursor.lockState==CursorLockMode.None)Cursor.lockState=oldLock;
            if(Cursor.visible)Cursor.visible=oldVisible;
        }
        internal void Release()
        {
            if(root!=null)UnityEngine.Object.Destroy(root);
            if(font!=null && ownFont)UnityEngine.Object.Destroy(font);
            root=null;font=null;
        }
        private bool ownFont;
        private static GameObject Node(string name,Transform parent)
        {
            var go=new GameObject(name,new[]{Il2CppType.Of<RectTransform>()});
            go.transform.SetParent(parent,false);return go;
        }
        private static RectTransform Rect(GameObject go){return go.GetComponent<RectTransform>();}
        private static void Fill(GameObject go)
        {
            var r=Rect(go);r.anchorMin=Vector2.zero;r.anchorMax=Vector2.one;r.offsetMin=Vector2.zero;r.offsetMax=Vector2.zero;
        }
        private static void Place(GameObject go,float x,float y,float w,float h)
        {
            var r=Rect(go);r.anchorMin=r.anchorMax=r.pivot=new Vector2(0,1);
            r.sizeDelta=new Vector2(w,h);r.anchoredPosition=new Vector2(x,-y);
        }
        private static Image Bg(GameObject go,Color color)
        {var image=go.AddComponent<Image>();image.color=color;return image;}
        private Text TextNode(Transform parent,string text,int size,TextAnchor align)
        {
            var go=Node("Label",parent);var label=go.AddComponent<Text>();label.font=font;label.fontSize=size;
            label.color=White;label.alignment=align;label.raycastTarget=false;label.supportRichText=false;
            label.horizontalOverflow=HorizontalWrapMode.Wrap;label.verticalOverflow=VerticalWrapMode.Truncate;label.text=text;return label;
        }
        private Text Label(Transform parent,string text,int size,int x,int y,int w,int h)
        {
            var t=TextNode(parent,text,size,TextAnchor.MiddleLeft);Place(t.gameObject,x,y,w,h);return t;
        }
        private Button ButtonAt(Transform parent,string text,int x,int y,int w,int h,Action callback,out Text label,bool strong=false)
        {
            var go=Node("Button",parent);Place(go,x,y,w,h);var image=Bg(go,strong?Accent:Normal);
            var button=go.AddComponent<Button>();button.targetGraphic=image;
            var nav=button.navigation;nav.mode=Navigation.Mode.None;button.navigation=nav;
            label=TextNode(go.transform,text,17,TextAnchor.MiddleCenter);Fill(label.gameObject);
            button.onClick.AddListener((UnityEngine.Events.UnityAction)(Action)(()=>{
                if(!Visible || busy || clickFrame==Time.frameCount)return;
                clickFrame=Time.frameCount;busy=true;
                try{callback();}catch(Exception e){Notice(e.GetBaseException().Message);}finally{busy=false;}
            }));
            return button;
        }
        private void Build()
        {
            font=Font.CreateDynamicFontFromOSFont("Microsoft YaHei UI",20);ownFont=font!=null;
            if(font==null)font=Resources.GetBuiltinResource<Font>("Arial.ttf");
            root=Node("RiseAloneTrainer.Menu",null);root.SetActive(false);
            UnityEngine.Object.DontDestroyOnLoad(root);
            var canvas=root.AddComponent<Canvas>();canvas.renderMode=RenderMode.ScreenSpaceOverlay;canvas.sortingOrder=32760;
            var scaler=root.AddComponent<CanvasScaler>();scaler.uiScaleMode=CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution=new Vector2(980,620);scaler.screenMatchMode=CanvasScaler.ScreenMatchMode.Expand;
            root.AddComponent<GraphicRaycaster>();
            var shield=Node("InputShield",root.transform);Fill(shield);Bg(shield,new Color(0.02f,0.04f,0.06f,0.81f));
            var body=Node("Panel",root.transform);var br=Rect(body);br.anchorMin=br.anchorMax=br.pivot=new Vector2(.5f,.5f);
            br.sizeDelta=new Vector2(900,530);br.anchoredPosition=Vector2.zero;Bg(body,Card);
            var p=body.transform;
            Label(p,"重生2我独自逆袭  ·  修改器",25,24,12,620,42);
            ButtonAt(p,"关闭  `",766,15,110,38,Close,out _);
            numbersTab=ButtonAt(p,"属性修改",24,64,192,40,()=>Page(false),out _);
            assistTab=ButtonAt(p,"辅助功能",226,64,192,40,()=>Page(true),out _);
            numbers=Node("Numbers",p);Fill(numbers);
            assists=Node("Assists",p);Fill(assists);
            var panel=p;p=numbers.transform;
            statsTab=ButtonAt(p,"主角",24,122,104,37,()=>Category(Catalog.Stats),out _);
            peopleTab=ButtonAt(p,"NPC 好感度",136,122,140,37,()=>Category(Catalog.People),out _);
            npcTab=ButtonAt(p,"NPC 属性",284,122,138,37,()=>Category(Catalog.NpcAttributes),out _);
            for(int i=0;i<rows.Length;i++){
                int index=i;rows[i]=ButtonAt(p,"",24+(i%2)*204,170+(i/2)*41,194,36,()=>{
                    if(index<entries.Length)Select(entries[index]);
                },out rowText[i]);
            }
            title=Label(p,"",24,458,127,415,40);value=Label(p,"",19,458,172,415,54);
            Label(p,"目标数值",16,458,237,415,26);
            var field=Node("Amount",p);Place(field,458,272,250,43);var bg=Bg(field,new Color(.94f,.96f,.96f));
            input=field.AddComponent<InputField>();input.targetGraphic=bg;
            var edit=TextNode(field.transform,"",19,TextAnchor.MiddleLeft);Place(edit.gameObject,10,1,218,40);
            edit.color=Card;input.textComponent=edit;input.contentType=InputField.ContentType.IntegerNumber;
            input.characterLimit=15;input.lineType=InputField.LineType.SingleLine;
            var hint=TextNode(field.transform,"输入目标数值",16,TextAnchor.MiddleLeft);Place(hint.gameObject,10,1,218,40);
            hint.color=new Color(.35f,.41f,.43f);input.placeholder=hint;
            apply=ButtonAt(p,"设置数值",720,272,156,43,()=>Action(s=>Plugin.State.SetNumber(s,observed,input.text)),out _,true);
            npcHint=Label(p,"",17,458,335,418,80);
            p=assists.transform;
            Label(p,"辅助开关",21,24,122,398,36);
            energy=ButtonAt(p,"",24,156,398,32,()=>Action(s=>Plugin.State.SetEnergy(s,observed,!Plugin.State.NoEnergyLoss)),out energyText);
            pressure=ButtonAt(p,"",24,192,398,32,()=>Action(s=>Plugin.State.SetZeroPressure(s,observed,!Plugin.State.ZeroPressure)),out pressureText);
            favor=ButtonAt(p,"",24,228,398,32,()=>Action(s=>Plugin.State.SetFavor(s,observed,!Plugin.State.FullFavor)),out favorText);
            mini=ButtonAt(p,"",24,264,398,32,()=>Action(s=>Plugin.State.SetMiniGames(s,observed,!Plugin.State.AutoMiniGames)),out miniText);
            guard=ButtonAt(p,"",24,300,398,32,()=>Action(s=>{
                Plugin.State.SetChoiceGuard(s,observed,!Plugin.State.ChoiceGuard);
                TaskChoices.RefreshVisibleLabels();
            }),out guardText);
            choiceTimer=ButtonAt(p,"",24,336,398,32,()=>Action(s=>Plugin.State.SetUnlimitedChoiceTime(s,observed,!Plugin.State.UnlimitedChoiceTime)),out choiceTimerText);
            mapToggle=ButtonAt(p,"",24,372,398,32,()=>Action(s=>Plugin.State.SetMapLabels(s,observed,!Plugin.State.MapLabels)),out mapText);
            save=ButtonAt(p,"保存设置",24,410,150,38,()=>Action(s=>Plugin.State.SaveSettings(s,observed)),out _,true);
            Label(p,"重启和换档后沿用",16,187,409,230,40);
            Label(p,"任务重选",21,458,122,418,36);
            checkpoint=Label(p,"",18,458,171,418,96);
            undo=ButtonAt(p,"重选上一步",458,285,198,44,()=>{TaskChoices.Restore(GameSlot.Current(),shownPoint);Close();},out _,true);
            resume=ButtonAt(p,"继续当前剧情",668,285,208,44,Close,out _);
            rentalHint=Label(panel,"",16,24,455,852,38);
            rentalHint.color=new Color(1f,.85f,.54f);
            status=Label(panel,"",16,24,494,852,30);
            Page(false);
            PaintList();
        }
        internal void OpenAssists(){Open();Page(true);Refresh(GameSlot.Current());}
        private void Page(bool auxiliary){
            if(numbers==null)return;
            if(input!=null && input.isFocused)input.DeactivateInputField();
            var es=EventSystem.current;
            if(es!=null && es.currentSelectedGameObject!=null && es.currentSelectedGameObject.transform.IsChildOf(root.transform))es.SetSelectedGameObject(null);
            assistPage=auxiliary;input.text="";
            numbers.SetActive(!auxiliary);assists.SetActive(auxiliary);
            numbersTab.targetGraphic.color=auxiliary?Normal:Accent;
            assistTab.targetGraphic.color=auxiliary?Accent:Normal;
            if(Visible)Refresh(GameSlot.Current());
        }
        private void Category(Entry[] list){entries=list;Select(list[0]);}
        private void Select(Entry entry){selected=entry;input.text="";observed=null;PaintList();Refresh(GameSlot.Current());}
        private void PaintList()
        {
            statsTab.targetGraphic.color=entries==Catalog.Stats?Accent:Normal;
            peopleTab.targetGraphic.color=entries==Catalog.People?Accent:Normal;
            npcTab.targetGraphic.color=entries==Catalog.NpcAttributes?Accent:Normal;
            npcHint.text="";
            if(entries==Catalog.NpcAttributes){
                if(selected.Key==Catalog.ZhaoApproval)npcHint.text="后续资产结算时，每点认可度计入 200 万。";
                else if(selected.Key.StartsWith("MM",StringComparison.Ordinal))npcHint.text="这些是妹妹的养成值。剧情里的「妹妹性格发生一些变化」对应这五项。";
                else npcHint.text="这些是盆栽（植物娘）的养成值，可通过夜间照料提升。";
            }
            for(int i=0;i<rows.Length;i++){
                bool active=i<entries.Length;rows[i].gameObject.SetActive(active);
                if(!active)continue;rowText[i].text=entries[i].Name;
                rows[i].targetGraphic.color=selected==entries[i]?Accent:Normal;
            }
        }
        private void Action(Action<ISlot> change)
        {
            var slot=GameSlot.Current();
            try{change(slot);Notice(Plugin.State.Last);}finally{Refresh(slot);}
        }
        private void Notice(string text){if(status!=null)status.text=text;holdStatus=Environment.TickCount64+4600;}
        private static string ValueLabel(Reading current)
        {
            if(current==null)return "进入游戏存档后可修改";
            switch(current.Item.Key){
                case "Execution":return "当前行动力  "+current.Effective+" / "+current.Max;
                case Catalog.OpeningPoints:return "开场可用  "+current.Effective+" 点（可设 0～12）";
                case Catalog.FightPoints:
                    if(String.IsNullOrEmpty(current.CombatTurn))return "进入战斗的选招界面后可修改";
                    return "本场可用  "+current.Effective+" 点（可设 0～12）";
                default:return "基础值  "+current.Base+"     游戏值  "+current.Effective+(current.Item.Full>0?"     满值  "+current.Item.Full:"");
            }
        }
        internal void Refresh(ISlot slot)
        {
            var engine=Plugin.State;
            var current=engine.Read(slot,assistPage?Catalog.Stats[0]:selected);
            if(displayedSession!=null && displayedSession!=(current==null?"":current.Session)){
                input.text="";observed=null;Close();return;
            }
            displayedSession=current==null?"":current.Session;observed=current;
            title.text=selected.Name;
            bool fightPoints=selected.Key==Catalog.FightPoints;
            bool atMoveChoice=current!=null && !String.IsNullOrEmpty(current.CombatTurn);
            value.text=ValueLabel(current);
            energyText.text="行动力不减少     "+(!engine.EnergyAvailable?"不可用":engine.NoEnergyLoss?"开":"关");
            favorText.text="交互人物自动满好感     "+(engine.FullFavor?"开":"关");
            pressureText.text="保持零压力     "+(!engine.PressureAvailable?"不可用":engine.ZeroPressure?"开":"关");
            miniText.text="小游戏自动完成（含按摩）     "+(!engine.MiniGameAvailable?"不可用":engine.AutoMiniGames?"开":"关");
            mini.interactable=current!=null && engine.MiniGameAvailable;
            mapText.text="显示当前可进入的未解锁地点     "+(engine.MapLabels?"开":"关");
            mapToggle.interactable=current!=null;
            choiceTimerText.text="做选择不限时     "+(engine.UnlimitedChoiceTime?"开":"关");
            choiceTimer.interactable=current!=null && engine.ChoiceTimerAvailable;
            guard.interactable=current!=null && engine.ChoiceAvailable;
            guardText.text="任务防误选     "+(!engine.ChoiceAvailable?"不可用":engine.ChoiceGuard?"开":"关");
            if(assistPage){
                shownPoint=TaskChoices.Current(slot);
                checkpoint.text=TaskChoices.Describe(shownPoint);
                undo.interactable=shownPoint!=null;
                resume.gameObject.SetActive(TaskChoices.IsNotice);
            }
            save.interactable=current!=null;
            energy.interactable=current!=null && engine.EnergyAvailable;
            favor.interactable=current!=null && engine.FavorAvailable;
            pressure.interactable=current!=null && engine.PressureAvailable;
            apply.interactable=input.interactable=current!=null && (!fightPoints || atMoveChoice) && !(selected.Key=="Pressure" && engine.ZeroPressure);
            if(Environment.TickCount64>=holdStatus)status.text=engine.Last;
            rentalHint.text=engine.RentalHint(slot);
            if(!assistPage && String.IsNullOrEmpty(rentalHint.text) && (fightPoints || selected.Key==Catalog.OpeningPoints))
                rentalHint.text="开场点数在战斗初始化时带入。本场点数立即生效。海鲜大排档的组合拳消耗 2 点。";
            if(!assistPage && entries==Catalog.People && String.IsNullOrEmpty(rentalHint.text))
                rentalHint.text="进入可识别的剧情、场景互动或人物会话，自动满好感会补满对方的好感。";
        }
    }
}
