using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace RiseAlone
{
    public static class StoryActors
    {
        private static readonly Lazy<Dictionary<string, Entry>> clips =
            new Lazy<Dictionary<string, Entry>>(LoadClips);

        private static Dictionary<string, Entry> LoadClips()
        {
            var result = new Dictionary<string, Entry>(StringComparer.Ordinal);
            using var stream = typeof(StoryActors).Assembly.GetManifestResourceStream("RiseAlone.StoryClips");
            using var reader = new StreamReader(stream);
            string line;
            while ((line = reader.ReadLine()) != null)
            {
                int separator = line.IndexOf(' ');
                var person = Catalog.Find(line.Substring(separator + 1));
                if (person == null || person.Full <= 0) throw new InvalidDataException("剧情人物索引无效。");
                result.Add(line.Substring(0, separator), person);
            }
            return result;
        }

        // Some interactive branches are omitted from the gallery. Require both the character's
        // own story graph and a clip named for that character before using its route identity.
        private static readonly (string Graph, string Clip, string Key)[] personalRoutes = {
            ("BaoZuPo", "包租婆", "BZPFavorability"), ("MeiMei", "妹妹", "MMFavorability"),
            ("Victoria", "维多利亚", "WDLYFavorability"), ("Victoria", "Victoria", "WDLYFavorability"),
            ("XiaoFuPo", "小富婆", "XFPFavorability"), ("XiXueGui", "吸血鬼", "XXGFavorability"),
            ("LiQingTong", "李青铜", "LQTFavorability"), ("LaoBanNian", "老板娘", "LBNFavorability"),
            ("LaoBanNian", "酒吧老板娘", "LBNFavorability"), ("LinXiaoYu", "洗脚妹", "XJMFavorability"),
            ("LinXiaoYu", "林小雨", "XJMFavorability"), ("MiShu", "秘书", "MSFavorability"),
            ("ZhiWuNiang", "植物娘", "PZFavorability"), ("PenZai", "盆栽", "PZFavorability")
        };

        public static Entry Played(string graph, string videoPath, string playedId, string committedId)
        {
            if (String.IsNullOrEmpty(graph) || graph == "JieJuTu" || String.IsNullOrEmpty(videoPath) ||
                String.IsNullOrEmpty(playedId) || playedId != committedId)
                return null;
            string clip = videoPath.Substring(videoPath.LastIndexOf('/') + 1);
            if (clip.Contains("黑屏") || clip.Contains("断线")) return null;
            string signature = Convert.ToBase64String(SHA256.HashData(Encoding.UTF8.GetBytes(videoPath)));
            if (clips.Value.TryGetValue(signature, out var person)) return person;
            foreach (var route in personalRoutes)
                if (graph.StartsWith(route.Graph, StringComparison.OrdinalIgnoreCase) &&
                    clip.StartsWith(route.Clip, StringComparison.OrdinalIgnoreCase))
                    return Catalog.Find(route.Key);
            switch (graph)
            {
                case "ChuZuWuRi" when clip == "破屋互动日【带盆栽晒太阳】":
                case "ChuZuWuYe" when clip.StartsWith("破屋互动夜【盆栽】", StringComparison.Ordinal):
                case "GongYuYe" when clip == "场互公寓【盆栽】浇水":
                case "BieShu_Ri" when clip.StartsWith("别墅-日教植物娘", StringComparison.Ordinal) ||
                                       clip.StartsWith("别墅-日植物娘", StringComparison.Ordinal):
                case "BieShu_Ye" when clip.StartsWith("别墅-夜植物娘", StringComparison.Ordinal):
                    return Catalog.Find("PZFavorability");
                case "MiShuGongSi" when clip.StartsWith("三阶办公室重复1AA闲聊", StringComparison.Ordinal) ||
                                        clip.StartsWith("三阶办公室重复1AC欺负她", StringComparison.Ordinal):
                    return Catalog.Find("MSFavorability");
                default:
                    return null;
            }
        }
    }
}
