using System;
using System.Collections.Generic;
using System.IO;

namespace RiseAlone
{
    internal sealed class TaskNames
    {
        private readonly Dictionary<int,string> keys=new Dictionary<int,string>();
        private readonly Dictionary<string,int> ids=new Dictionary<string,int>(StringComparer.Ordinal);
        private readonly Func<int,string> nativeKey;
        private readonly Func<string,string> localizedTitle;

        internal TaskNames(TextReader originalKeys,Func<int,string> nativeKey,Func<string,string> localizedTitle){
            this.nativeKey=nativeKey;
            this.localizedTitle=localizedTitle;
            string row;
            while((row=originalKeys.ReadLine())!=null){
                var fields=row.Split('\t');
                int id=int.Parse(fields[0]);
                keys.Add(id,fields[1]);ids.Add(fields[1],id);
            }
        }
        private string Key(int id){
            var key=nativeKey(id);
            if(!String.IsNullOrWhiteSpace(key) && !IsPlaceholder(key))return key;
            keys.TryGetValue(id,out key);
            return key;
        }
        private static bool IsPlaceholder(string text){
            return text.IndexOf("AsmResolver",StringComparison.OrdinalIgnoreCase)>=0 ||
                text.StartsWith("EnumValue",StringComparison.Ordinal);
        }
        internal bool TryId(string key,Func<string,int?> nativeId,out int id){
            if(!String.IsNullOrWhiteSpace(key) && !IsPlaceholder(key)){
                if(ids.TryGetValue(key,out id) && Key(id)==key)return true;
                var live=nativeId(key);
                if(live.HasValue && Key(live.Value)==key){id=live.Value;return true;}
            }
            id=-1;return false;
        }
        internal string Title(string key){
            if(String.IsNullOrWhiteSpace(key) || IsPlaceholder(key))return null;
            if(!ids.TryGetValue(key,out var id))return null;
            string verified=ChoiceNames.Get('T',id);
            if(verified==null)return null;
            string title=localizedTitle(key);
            return String.Equals(title,verified,StringComparison.Ordinal)?title:verified;
        }
        internal string Warning(bool certain,int[] affected){
            if(affected.Length==0)return "";
            var names=new List<string>();
            bool unknown=false;
            foreach(int id in affected){
                string name=Title(Key(id));
                if(name==null)unknown=true;
                else if(!names.Contains(name))names.Add(name);
            }
            string prefix=certain?"会中断":"可能中断";
            if(names.Count==0)return prefix+"任务";
            return prefix+"："+String.Join("、",names)+(unknown?"等任务":"");
        }
    }
}
