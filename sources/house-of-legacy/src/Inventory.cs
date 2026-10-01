using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;

namespace HouseOfLegacyTrainer
{
    internal static class Inventory
    {
        private const string SupportedId = "3"; // Static evidence: ordinary vegetables.
        private const int SupportedIndex = 3;
        private static long generation;

        public sealed class Entry
        {
            public string Id, Name;
            public int Count;
        }

        public sealed class Snapshot
        {
            public string Summary;
            public List<Entry> Entries;
            public int Capacity;
            internal GameContext Context;
            internal List<List<string>> Items, Names, Config;
            internal List<string>[] Rows;
            internal string[][] OriginalRows;
            internal List<string> Family, NameRow, ConfigRow;
            internal string[] OriginalFamily, OriginalName, OriginalConfig;
            internal List<int> Settings;
            internal int Language, CapturedCapacity, TargetIndex, Used;
            internal long Generation, Total, CapacityInvariant;
            internal string TargetName;
        }

        public static Snapshot Read()
        {
            GameContext.RequireThread();
            long next = ++generation;
            GameContext context = GameContext.Capture();
            RequireNoTransaction();
            List<List<string>> items = Mainload.Prop_have;
            List<string> family = Mainload.FamilyData;
            List<List<string>> config = Mainload.AllPropdata;
            List<List<string>> names = AllText.Text_AllProp;
            List<int> settings = Mainload.SetData;
            if (items == null || items.Count > 10000 || family == null || family.Count <= 5 ||
                config == null || config.Count <= SupportedIndex || names == null || names.Count <= SupportedIndex ||
                settings == null || settings.Count <= 4)
                throw new InvalidOperationException("仓库或物品配置尚未就绪，暂不修改。");

            var s = new Snapshot {
                Context = context, Items = items, Family = family, Config = config, Names = names,
                Settings = settings, Language = settings[4], Generation = next,
                Rows = items.ToArray(), OriginalFamily = family.ToArray(),
                TargetIndex = -1, Entries = new List<Entry>()
            };
            s.CapturedCapacity = Nonnegative(s.OriginalFamily[5], "仓库剩余容量");
            s.Capacity = s.CapturedCapacity;
            s.NameRow = names[SupportedIndex];
            s.ConfigRow = config[SupportedIndex];
            if (s.NameRow == null || s.Language < 0 || s.Language >= s.NameRow.Count ||
                s.NameRow.Count == 0 || s.NameRow[0] != "蔬菜" || string.IsNullOrEmpty(s.NameRow[s.Language]) ||
                s.ConfigRow == null || s.ConfigRow.Count < 2)
                throw new InvalidOperationException("蔬菜物品的名称或配置与已核对结构不符，暂不开放物品增加。");
            Nonnegative(s.ConfigRow[1], "物品分类");
            s.OriginalName = s.NameRow.ToArray();
            s.OriginalConfig = s.ConfigRow.ToArray();
            s.TargetName = s.NameRow[s.Language];
            s.OriginalRows = new string[s.Rows.Length][];
            int matches = 0;
            for (int i = 0; i < s.Rows.Length; i++)
            {
                List<string> row = s.Rows[i];
                if (row == null || row.Count != 2)
                    throw new InvalidOperationException("仓库条目不是已核对的物品编号/数量结构，暂不修改。");
                string[] values = row.ToArray();
                s.OriginalRows[i] = values;
                int id = Nonnegative(values[0], "物品编号");
                if (id >= config.Count || id >= names.Count || config[id] == null || names[id] == null)
                    throw new InvalidOperationException("仓库包含无法在当前配置中核对的物品，暂不修改。");
                int count = Nonnegative(values[1], "物品数量");
                s.Total += count;
                if (s.Total > int.MaxValue)
                    throw new InvalidOperationException("仓库总数量超出游戏整型计算范围，暂不修改。");
                if (values[0] == SupportedId) { matches++; s.TargetIndex = i; }
            }
            s.CapacityInvariant = s.Total + s.CapturedCapacity;
            if (s.CapacityInvariant > int.MaxValue)
                throw new InvalidOperationException("仓库总容量超出已核对的整型计算范围，暂不修改。");
            if (matches > 1)
                throw new InvalidOperationException("仓库中存在重复的蔬菜条目，无法唯一确定修改目标。");
            if (matches == 1)
            {
                int count = Nonnegative(s.OriginalRows[s.TargetIndex][1], "蔬菜数量");
                if (count > 0)
                    s.Entries.Add(new Entry { Id = SupportedId, Name = s.TargetName, Count = count });
                else s.TargetIndex = -1;
            }
            s.Summary = "仓库剩余容量 " + s.Capacity + "；" +
                (s.Entries.Count == 0 ? "当前没有可调整的已持有蔬菜。" : s.TargetName + " " + s.Entries[0].Count + "。") +
                "\n当前仅支持已有蔬菜，单次增加 1–1000，须有足够仓库容量；这是工具限制。";
            ValidateState(s, s.OriginalRows, s.OriginalFamily, s.Total, s.CapturedCapacity);
            return s;
        }

        public static string Add(Snapshot expected, string id, int amount)
        {
            GameContext.RequireThread();
            if (expected == null) throw new InvalidOperationException("请先刷新仓库数据。");
            if (Interlocked.Exchange(ref expected.Used, 1) != 0)
                throw new InvalidOperationException("这次仓库请求已使用，请刷新并核对数量后再操作。");
            // Every error after this point consumes the snapshot. A fresh read is
            // required even for a rejected input; dispatched requests never retry.
            if (expected.Generation != generation)
                throw new InvalidOperationException("仓库读取已被新的刷新替代，请使用最新数据。");
            if (id != SupportedId || expected.TargetIndex < 0)
                throw new InvalidOperationException("目前只支持增加仓库中已经持有且编号唯一的蔬菜。");
            if (amount < 1 || amount > 1000)
                throw new InvalidOperationException("单次增加数量须为 1–1000 的整数；这是工具限制。");
            if (amount > expected.CapturedCapacity)
                throw new InvalidOperationException("仓库剩余容量不足，未修改物品数量。");

            ValidateState(expected, expected.OriginalRows, expected.OriginalFamily,
                expected.Total, expected.CapturedCapacity);
            int index = expected.TargetIndex;
            int before = Nonnegative(expected.OriginalRows[index][1], "蔬菜数量");
            if ((long)before + amount > int.MaxValue)
                throw new InvalidOperationException("操作后的物品数量超出游戏整型范围。");
            int after = before + amount;
            int remaining = expected.CapturedCapacity - amount;
            var resultRows = (string[][])expected.OriginalRows.Clone();
            resultRows[index] = (string[])resultRows[index].Clone();
            resultRows[index][1] = after.ToString(CultureInfo.InvariantCulture);
            var resultFamily = (string[])expected.OriginalFamily.Clone();
            resultFamily[5] = remaining.ToString(CultureInfo.InvariantCulture);
            long resultTotal = expected.Total + amount;
            if (resultTotal + remaining != expected.CapacityInvariant)
                throw new InvalidOperationException("仓库容量核对失败，未执行修改。");
            ValidateState(expected, expected.OriginalRows, expected.OriginalFamily,
                expected.Total, expected.CapturedCapacity);
            try
            {
                // A single main-thread commit, with all strings and arithmetic
                // prepared first. No callbacks, sorting, new rows, or game APIs.
                expected.Rows[index][1] = resultRows[index][1];
                expected.Family[5] = resultFamily[5];
                ValidateState(expected, resultRows, resultFamily, resultTotal, remaining);
            }
            catch (Exception e)
            {
                throw new InvalidOperationException("物品与容量写入已开始，但结果未能完整确认。请求已作废，未自动重试或补偿；请刷新核对物品和容量。" + e.Message, e);
            }
            return expected.TargetName + "：" + before + " → " + after +
                "；仓库剩余容量：" + expected.CapturedCapacity + " → " + remaining +
                "。数量与容量已读回，尚未自动存档。";
        }

        private static void ValidateState(Snapshot s, string[][] rows, string[] family, long total, int capacity)
        {
            s.Context.Validate();
            RequireNoTransaction();
            if (s.Generation != generation || !ReferenceEquals(s.Items, Mainload.Prop_have) ||
                !ReferenceEquals(s.Family, Mainload.FamilyData) || !ReferenceEquals(s.Config, Mainload.AllPropdata) ||
                !ReferenceEquals(s.Names, AllText.Text_AllProp) || !ReferenceEquals(s.Settings, Mainload.SetData) ||
                s.Settings.Count <= 4 || s.Settings[4] != s.Language ||
                s.Config.Count <= SupportedIndex || s.Names.Count <= SupportedIndex ||
                !ReferenceEquals(s.ConfigRow, s.Config[SupportedIndex]) ||
                !ReferenceEquals(s.NameRow, s.Names[SupportedIndex]) || s.Items.Count != s.Rows.Length)
                throw new InvalidOperationException("仓库对象、物品配置或语言已变化，请重新刷新。");
            Match(s.ConfigRow, s.OriginalConfig, "蔬菜配置");
            Match(s.NameRow, s.OriginalName, "物品名称");
            Match(s.Family, family, "家族与仓库容量");
            long actualTotal = 0;
            for (int i = 0; i < s.Rows.Length; i++)
            {
                if (!ReferenceEquals(s.Items[i], s.Rows[i]))
                    throw new InvalidOperationException("仓库条目已被整理或替换，请重新刷新。");
                Match(s.Rows[i], rows[i], "库存条目");
                actualTotal += Nonnegative(s.Rows[i][1], "物品数量");
            }
            int actualCapacity = Nonnegative(s.Family[5], "仓库剩余容量");
            if (actualTotal != total || actualCapacity != capacity || actualTotal + actualCapacity != s.CapacityInvariant)
                throw new InvalidOperationException("库存总量与剩余容量核对未通过，请刷新核对。");
        }

        private static int Nonnegative(string value, string label)
        {
            int result;
            if (!int.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out result) || result < 0 ||
                result.ToString(CultureInfo.InvariantCulture) != value)
                throw new InvalidOperationException(label + "不是已核对的非负整数字符串。");
            return result;
        }

        private static void Match(List<string> actual, string[] expected, string label)
        {
            if (actual == null || actual.Count != expected.Length)
                throw new InvalidOperationException(label + "结构已变化，请重新刷新。");
            for (int i = 0; i < expected.Length; i++)
                if (actual[i] != expected[i])
                    throw new InvalidOperationException(label + "内容已变化，请重新刷新。");
        }

        private static void RequireNoTransaction()
        {
            if (Mainload.isShopPanelOpen)
                throw new InvalidOperationException("请先关闭商店或交易界面，再从暂停菜单调整仓库。");
        }
    }
}
