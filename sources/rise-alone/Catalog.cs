using System;
using System.Collections.Generic;

namespace RiseAlone
{
    public sealed class Entry
    {
        public readonly string Key, Name, Contact, Icon;
        public readonly int Full;
        public Entry(string key, string name, int full = 0, string contact = "", string icon = "")
        { Key = key; Name = name; Full = full; Contact = contact; Icon = icon; }
        public override string ToString() { return Name; }
    }

    public static class Catalog
    {
        public const string OpeningPoints="JiNengDian", FightPoints="TmpJiNengDian";
        public const string ZhaoApproval="ZhaoZon";
        public const int CombatPointLimit=12;
        public static readonly Entry[] Stats = {
            new Entry("Money","金钱"), new Entry("Execution","行动力"),
            new Entry("Stamina","体能"), new Entry("Wisdom","智慧"), new Entry("Charm","魅力"),
            new Entry("Morality","道德"), new Entry("CapacityForLiquor","酒量"), new Entry("Pressure","压力"),
            new Entry(OpeningPoints,"开场战技点"), new Entry(FightPoints,"本场战技点")
        };
        // Full is the denominator in ScoreRoleItem's 100% display in build 26669300.
        public static readonly Entry[] People = {
            new Entry("MMFavorability","妹妹",30,"妹妹","MapMeiMei"),
            new Entry("BZPFavorability","包租婆",30,"包租婆","MapBaoZhuPo"),
            new Entry("WDLYFavorability","维多利亚",21,"维多利亚","MapWeiDuoLiYa"),
            new Entry("XFPFavorability","晓琪（看书少女）",27,"晓琪","MapXiaoQi"),
            new Entry("XXGFavorability","安冉（吸血少女）",23,"安冉","MapXiXueGui"),
            new Entry("LQTFavorability","李青铜",26,"李青铜","MapLiQinTon"),
            new Entry("LBNFavorability","婉瑜（酒吧老板娘）",44,"婉瑜","MapJiuBaLaoBan"),
            new Entry("XJMFavorability","林小雨（233号）",15,"林小雨","MapLinXiaoYu"),
            new Entry("MSFavorability","熙恩（秘书）",15,"秘书","MapMiShu"),
            new Entry("PZFavorability","盆栽（植物娘）",30,"","MapZhiWuNian"),
            new Entry("ZXSNFavorability","哲学少女"), new Entry("DBNFavorability","电波女"),
            new Entry("LJFavorability","雷军"), new Entry("NAMFavorability","女按摩")
        };
        // Paired columns in the menu keep each character's training values together.
        public static readonly Entry[] NpcAttributes = {
            new Entry("MMHeiAn","妹妹 · 黑暗"), new Entry("PenZaiTiNeng","盆栽 · 体能"),
            new Entry("MMZiXing","妹妹 · 自信"), new Entry("PenZaiMeiLi","盆栽 · 魅力"),
            new Entry("MMZiLi","妹妹 · 智力"), new Entry("PenZaiZhiHui","盆栽 · 智慧"),
            new Entry("MMXianHui","妹妹 · 贤惠"), new Entry("PenZaiJiuLian","盆栽 · 酒量"),
            new Entry("MMTiLi","妹妹 · 体能"), new Entry("PenZaiYaLi","盆栽 · 压力"),
            new Entry(ZhaoApproval,"赵总 · 认可度")
        };
        public static Entry Find(string key)
        {
            foreach (var e in Stats) if(e.Key==key) return e;
            foreach (var e in People) if(e.Key==key) return e;
            foreach (var e in NpcAttributes) if(e.Key==key) return e;
            return null;
        }
        public static Entry Actor(string identity, bool phone)
        {
            if (String.IsNullOrEmpty(identity)) return null;
            foreach (var e in People)
                if (e.Full > 0 && identity == (phone ? e.Contact : e.Icon)) return e;
            return null;
        }
        public static long Limit(Entry entry, long energyCap)
        {
            if(entry.Key == "Execution") return energyCap;
            if(entry.Key == OpeningPoints || entry.Key == FightPoints) return CombatPointLimit;
            if(entry.Key == "Money") return 2000000000L;
            return 999999L;
        }
        // Sender portraits in Xlsx_Message. Only a committed reply uses this lookup.
        public static Entry Portrait(string icon)
        {
            switch(icon){
                case "BaoZhuPo2": return Actor("包租婆",true);
                case "MeiMei": return Actor("妹妹",true);
                case "LiQinTon": return Actor("李青铜",true);
                case "LaoBanNian": return Actor("维多利亚",true);
                case "MiShu": return Actor("秘书",true);
                case "XiXueGui": return Actor("安冉",true);
                case "WanYun": return Actor("婉瑜",true);
                case "xiaoqi2": return Actor("晓琪",true);
                case "LinXiaoYu2": return Actor("林小雨",true);
                default: return null;
            }
        }
    }
}
