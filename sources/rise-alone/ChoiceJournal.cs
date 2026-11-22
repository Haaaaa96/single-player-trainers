using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace RiseAlone
{
    public sealed class ChoicePoint
    {
        public string Slot {get;set;}
        public int Round {get;set;}
        public string Scene {get;set;}
        public string Graph {get;set;}
        public string Prompt {get;set;}
        public string EventKey {get;set;}
        public string Channel {get;set;}
        public string Contact {get;set;}
        public string Label {get;set;}
        public string Before {get;set;}
        public string AtClick {get;set;}
        public int[] Risks {get;set;}=Array.Empty<int>();
        public string Failure {get;set;}
    }

    public sealed class ChoiceJournal
    {
        private readonly string folder;
        private string owner;
        private List<ChoicePoint> recent=new List<ChoicePoint>();
        public ChoicePoint Latest {get{return recent.Count==0?null:recent[recent.Count-1];}}
        public ChoiceJournal(string folder){this.folder=folder;}
        public void MoveWithAutoSave(string key){
            if(key==owner)return;
            if(owner==null || recent.Count==0){Select(key);return;}
            var next=JsonSerializer.Deserialize<List<ChoicePoint>>(JsonSerializer.Serialize(recent));
            foreach(var point in next)point.Slot=key;
            string old=owner;owner=key;
            try{Commit(next);}catch{owner=old;throw;}
        }
        public static void ReadTemporary(string payload,Func<string> get,Action<string> set,Action remove,Action load){
            var old=get();
            try{set(payload);load();}
            finally{if(old==null)remove();else set(old);}
        }
        private string PathFor(string key){
            return Path.Combine(folder,Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(key)))+".json");
        }
        public void Select(string key){
            if(key==owner)return;
            owner=null;recent=new List<ChoicePoint>();
            if(String.IsNullOrEmpty(key))return;
            string path=PathFor(key);
            if(File.Exists(path)){
                var data=JsonSerializer.Deserialize<List<ChoicePoint>>(File.ReadAllText(path));
                if(data==null || data.Count>8 || data.Any(p=>p==null || p.Slot!=key || String.IsNullOrEmpty(p.Prompt) || String.IsNullOrEmpty(p.AtClick) || p.Risks==null))
                    throw new InvalidDataException("该档的重选记录无效。");
                recent=data;
            }
            owner=key;
        }
        private void Commit(List<ChoicePoint> next){
            Directory.CreateDirectory(folder);
            string path=PathFor(owner);
            string temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
            try{
                using(var stream=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){
                    JsonSerializer.Serialize(stream,next);stream.Flush(true);
                }
                File.Move(temp,path,true);recent=next;
            }finally{if(File.Exists(temp))File.Delete(temp);}
        }
        public void Record(ChoicePoint point){
            Select(point.Slot);
            if(owner==null || String.IsNullOrEmpty(point.Prompt) || String.IsNullOrEmpty(point.AtClick))throw new InvalidDataException("选择前进度不完整。");
            var next=new List<ChoicePoint>(recent);
            if(next.Count==8)next.RemoveAt(0);
            next.Add(point);Commit(next);
        }
        // Keep the chosen branch (and its pre-choice state) even when failure arrives after another prompt.
        public ChoicePoint Match(int task,string graph,int round){
            if(String.IsNullOrEmpty(graph))return null;
            var branch=recent.FindLast(p=>p.Round==round && p.Risks.Contains(task) && p.Graph==graph);
            return branch??recent.FindLast(p=>p.Round==round && p.Graph==graph);
        }
        public void Pin(ChoicePoint point,string failed){
            var next=new List<ChoicePoint>(recent);
            if(!next.Remove(point))throw new InvalidOperationException("选择记录已变更。");
            string old=point.Failure;point.Failure=failed;
            try{next.Add(point);Commit(next);}catch{point.Failure=old;throw;}
        }
    }
}
