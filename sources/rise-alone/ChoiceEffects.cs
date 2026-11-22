using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using FrameWork.ChatTool;
using Script.Mrg;
using Script.Tool;

namespace RiseAlone
{
    internal static class ChoiceNames
    {
        private static readonly Lazy<Dictionary<(char,int),string>> names =
            new Lazy<Dictionary<(char,int),string>>(Read);

        private static Dictionary<(char,int),string> Read(){
            var result=new Dictionary<(char,int),string>();
            using(var stream=typeof(ChoiceNames).Assembly.GetManifestResourceStream("RiseAlone.ChoiceNames"))
            using(var reader=new StreamReader(stream,new System.Text.UTF8Encoding(false,true))){
                string line;
                while((line=reader.ReadLine())!=null){
                    var fields=line.Split('\t');
                    result.Add((fields[0][0],int.Parse(fields[1],CultureInfo.InvariantCulture)),fields[2]);
                }
            }
            return result;
        }
        // Only reviewed Chinese display names enter the hint. Game keys and event parameters never do.
        internal static string Get(char category,int id){
            return names.Value.TryGetValue((category,id),out var name)?name:null;
        }
    }

    internal struct ChoiceRank : IComparable<ChoiceRank>
    {
        internal bool Known;
        internal int Risk,Tasks;
        internal decimal Favor;
        internal Dictionary<(char Kind,int Id,bool Round),decimal> Changes;
        internal bool Uncertain;
        internal List<int> FailureIds,PossibleFailureIds;
        internal double Growth,Resources,Pressure;

        public int CompareTo(ChoiceRank other)=>CompareTo(other,false);
        internal int CompareTo(ChoiceRank other,bool zeroPressure){
            int comparison=Favor.CompareTo(other.Favor);
            if(comparison!=0)return comparison;
            comparison=other.Risk.CompareTo(Risk);
            if(comparison!=0)return comparison;
            comparison=Tasks.CompareTo(other.Tasks);
            if(comparison!=0)return comparison;
            comparison=Growth.CompareTo(other.Growth);
            if(comparison!=0)return comparison;
            return (Resources-(zeroPressure?0:Pressure)).CompareTo(other.Resources-(zeroPressure?0:other.Pressure));
        }
    }

    internal static class ChoiceEffects
    {
        private static bool IsFavor(int id)=>(id>=8 && id<=20) || id==31 || (id>=51 && id<=54);

        private static void Add(ref ChoiceRank rank,(char Kind,int Id,bool Round) key,decimal amount){
            if(amount==0 || (key.Kind=='P' && (key.Id==5 || key.Id==41 || key.Id==71)))return;
            var changes=rank.Changes??=new Dictionary<(char,int,bool),decimal>();
            changes.TryGetValue(key,out var previous);
            changes[key]=previous+amount;
            if(key.Kind=='I'){rank.Resources+=Math.Sign(amount);return;}
            int id=key.Id;
            if(IsFavor(id))rank.Favor+=amount;
            else if((id>=0 && id<=4) || id==21 || (id>=35 && id<=38))rank.Growth+=(double)amount;
            else if(id==39)rank.Growth-=(double)amount;
            else if(id==6)rank.Resources+=Math.Sign(amount)*Math.Log10(1+Math.Abs((double)amount));
            else if(id==7)rank.Pressure+=(double)amount;
        }

        internal static string Describe(ChoiceRank rank,bool zeroPressure){
            var parts=new List<string>();
            if(rank.Changes!=null)foreach(var pair in rank.Changes){
                if(pair.Value==0)continue;
                var key=pair.Key;
                string name=ChoiceNames.Get(key.Kind,key.Id);
                if(name==null){rank.Uncertain=true;continue;}
                if(key.Kind=='P'){
                    if(key.Id==7 && zeroPressure){parts.Add("主角压力保持 0");continue;}
                    if(IsFavor(key.Id))name=key.Id==31?"盆栽好感":name+"好感";
                    else if(key.Id>=0 && key.Id<=7)name="主角"+name;
                    else if(key.Id==55)name="开场战技点";
                    else if(key.Id==63)name="本场战技点";
                }
                string sign=pair.Value>0?"+":"−";
                parts.Add((key.Round?"本回合":"")+name+" "+sign+Math.Abs(pair.Value).ToString(CultureInfo.InvariantCulture));
            }
            if(parts.Count>0)return String.Join("、",parts);
            return !rank.Known || rank.Uncertain?"具体数值待确认":"未见直接数值变化";
        }

        private static void Properties(ref ChoiceRank rank,Il2CppSystem.Collections.Generic.List<PropertyData> values){
            if(values==null)return;
            foreach(var value in values){
                if(value==null)continue;
                if(value.PropertyType==PropertyType.Item)
                    Add(ref rank,('I',(int)value.itemType,value.isRound),value.PropertyValue);
                else if(value.PropertyType==PropertyType.Property)
                    Add(ref rank,('P',(int)value.propertyTypeValue,value.isRound),value.PropertyValue);
            }
        }
        private static void Tasks(ref ChoiceRank rank,Il2CppSystem.Collections.Generic.List<TaskData> tasks,bool conditional){
            if(tasks==null)return;
            foreach(var task in tasks){
                if(task==null)continue;
                if(task.taskType==TaskType.Lose){
                    rank.Risk=Math.Max(rank.Risk,conditional?1:2);
                    var ids=conditional?(rank.PossibleFailureIds??=new List<int>()):(rank.FailureIds??=new List<int>());
                    if(!ids.Contains((int)task.xlsxTaskKey))ids.Add((int)task.xlsxTaskKey);
                }
                else if(!conditional && task.taskType==TaskType.Suc)rank.Tasks+=2;
                else if(!conditional && task.taskType==TaskType.Open)rank.Tasks++;
            }
        }
        internal static ChoiceRank Chat(ChatNode node){
            var rank=new ChoiceRank{Known=node!=null};
            if(node==null)return rank;
            Properties(ref rank,node.propertyDatas);Tasks(ref rank,node.taskData,false);
            return rank;
        }
        internal static ChoiceRank Video(ButtonNode button,VideoNode node){
            var rank=new ChoiceRank{Known=node!=null};
            if(button!=null){
                if(button.isOpenUiBtn)return default;
                if(button.isSetProperty)Properties(ref rank,button.propertyDatas);
                if(button.isClickExEvent && button.eventDatas!=null)
                    foreach(var item in button.eventDatas)if(item!=null && item.isReturn)return rank;
            }
            if(node==null)return rank;
            if(node.isClickBtnPlayAudio && !node.isClickBtnPlayVideo){
                Properties(ref rank,node.VideoEndPropertyData);return rank;
            }
            var visited=new HashSet<IntPtr>();
            for(int i=0;i<8 && node!=null && visited.Add(node.Pointer);i++){
                bool branches=node.isHasBtn || node.isHasQte;
                if(!node.isNowToNext && !node.isToNextGroup){
                    Properties(ref rank,node.PropertyData);Tasks(ref rank,node.taskData,branches);
                }
                if(branches){rank.Uncertain=true;break;}
                Properties(ref rank,node.VideoEndPropertyData);
                if(node.isToGame || node.isToMap || node.isToNextGroup || node.isPlayerEndOver || !node.isPlayerEndPlayerNext)break;
                if(node.isPlayerEndPlayerNextRandom || node.isPlayerEndPlayerNextSequence){
                    CommonNextChanges(ref rank,node);
                    break;
                }
                var links=node.GetOutputPort("nextVideoNode")?.connections;
                if(links==null || links.Count!=1){rank.Uncertain=true;break;}
                var link=links[0];
                node=link==null || String.IsNullOrEmpty(link.fieldName)?null:link.node?.TryCast<VideoNode>();
                if(node==null || i==7 || visited.Contains(node.Pointer))rank.Uncertain=true;
            }
            return rank;
        }

        // Random variants of one action (e.g. singing to the plant) can have identical rewards.
        // Compare their first clips without asking the game to draw a result or advance its sequence.
        private static void CommonNextChanges(ref ChoiceRank rank,VideoNode source){
            rank.Uncertain=true;
            var links=source.GetOutputPort("nextVideoNode")?.connections;
            if(links==null || links.Count==0)return;
            Dictionary<(char Kind,int Id,bool Round),decimal> common=null;
            foreach(var link in links){
                var child=link?.node?.TryCast<VideoNode>();
                if(child==null || link.fieldName!="inputVideoNode" || child.Pointer==source.Pointer ||
                   child.isNowToNext || child.isToNextGroup)return;
                var variant=new ChoiceRank();
                Properties(ref variant,child.PropertyData);
                if(!child.isHasBtn && !child.isHasQte)Properties(ref variant,child.VideoEndPropertyData);
                if(variant.Changes==null)return;
                if(common==null){common=variant.Changes;continue;}
                foreach(var key in new List<(char Kind,int Id,bool Round)>(common.Keys)){
                    if(!variant.Changes.TryGetValue(key,out decimal amount) || common[key]!=amount)common.Remove(key);
                }
                if(common.Count==0)return;
            }
            if(common!=null)foreach(var pair in common)Add(ref rank,pair.Key,pair.Value);
        }
    }
}
