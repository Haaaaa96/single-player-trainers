using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;

namespace HouseOfLegacyTrainer
{
    internal static class Family
    {
        private const int Segment = 1000000000;
        private const long ToolMoneyLimit = 9000000000000000L;
        private static long generation;

        public sealed class Snapshot
        {
            public string Summary;
            public long Money;
            public int Level, Reputation, Remaining;
            internal GameContext Context;
            internal List<string> Coins, Data;
            internal string[] OriginalCoins, OriginalData;
            internal int ThreadId, Used;
            internal long Generation;
            internal string Culture;
        }

        public static Snapshot Read()
        {
            long current = Interlocked.Increment(ref generation);
            GameContext context = GameContext.Capture();
            if (Mainload.CGNum == null || Mainload.CGNum.Count < 3 ||
                Mainload.FamilyData == null || Mainload.FamilyData.Count < 4)
                throw new InvalidOperationException("家族或资金结构尚未就绪。");
            var s = new Snapshot {
                Context = context, Coins = Mainload.CGNum, Data = Mainload.FamilyData,
                OriginalCoins = Mainload.CGNum.ToArray(), OriginalData = Mainload.FamilyData.ToArray(),
                ThreadId = Thread.CurrentThread.ManagedThreadId, Generation = current,
                Culture = CultureInfo.CurrentCulture.Name
            };
            s.Money = Balance(s.OriginalCoins);
            s.Level = Number(s.OriginalData[2]);
            s.Reputation = Number(s.OriginalData[3]);
            if (s.Level < 1 || s.Level > 80 || s.Reputation < 0)
                throw new InvalidOperationException("家族等级或声望超出已核对的公式范围。");
            s.Remaining = s.Level < 80 ? Math.Max(0, checked(s.Level * 20 - s.Reputation)) : 0;
            s.Summary = "资金 " + s.Money.ToString("N0", CultureInfo.CurrentCulture) +
                " · 家族等级 " + s.Level + " · 声望 " + s.Reputation +
                (s.Level < 80 ? " · 本级还需 " + s.Remaining : " · 已达当前公式等级边界") +
                "\n工具限制：资金单次增减最多 1,000,000；声望单次最多补至下一等级。";
            Validate(s);
            return s;
        }

        public static string ChangeMoney(Snapshot expected, int delta)
        {
            Consume(expected);
            Validate(expected);
            if (delta == 0 || delta < -1000000 || delta > 1000000)
                throw new InvalidOperationException("资金单次请输入非零的 -1,000,000–1,000,000 整数；这是本工具限制。");
            var result = (string[])expected.OriginalCoins.Clone();
            int low = checked(Number(result[0]) + delta);
            int high = Number(result[2]);
            // Match ChangeCoins exactly: carry is > 1e9; borrowing includes remainder == 0.
            bool segmentChanged = false;
            if (low > Segment) { low = checked(low - Segment); high = checked(high + 1); segmentChanged = true; }
            else if (low <= 0 && high > 0) { low = checked(low + Segment); high = checked(high - 1); segmentChanged = true; }
            else if (low < -Segment) { low = checked(low + Segment); high = checked(high - 1); segmentChanged = true; }
            result[0] = low.ToString(CultureInfo.CurrentCulture);
            if (segmentChanged) result[2] = high.ToString(CultureInfo.CurrentCulture);
            long before = Balance(expected.OriginalCoins), after = Balance(result);
            if (after < 0 || after > ToolMoneyLimit || after != checked(before + delta))
                throw new InvalidOperationException("操作后的完整资金余额必须在 0–9,000,000,000,000,000 内；这是本工具支持范围。");
            Validate(expected);
            try
            {
                FormulaData.ChangeCoins(delta);
                ValidateContext(expected);
                Match(expected.Coins, result, "资金");
                Match(expected.Data, expected.OriginalData, "家族");
            }
            catch (Exception e) { throw Dispatched("资金变更", e); }
            return "资金：" + before + " → " + after + "（原函数执行一次，完整余额已读回）";
        }

        public static string AddReputation(Snapshot expected, int delta)
        {
            Consume(expected);
            Validate(expected);
            int level = Number(expected.OriginalData[2]), reputation = Number(expected.OriginalData[3]);
            int threshold = checked(level * 20);
            int remaining = checked(threshold - reputation);
            if (level < 1 || level >= 80 || delta < 1 || delta > remaining)
                throw new InvalidOperationException("本工具声望单次只支持 1 至本级剩余声望，不跨多级；当前剩余 " + Math.Max(0, remaining) + "。");
            int low = Number(expected.OriginalCoins[0]), high = Number(expected.OriginalCoins[2]);
            int coinCheck = high > 0 ? checked(low + Segment) : high < 0 ? checked(low - Segment) : low;
            if (coinCheck < 0 || FormulaData.GetCoinsNum() != coinCheck)
                throw new InvalidOperationException("游戏资金条件未满足或读回不一致，不能增加家族声望。");
            if (FormulaData.ShengWangForLv(level) != threshold)
                throw new InvalidOperationException("家族升级公式已变化，暂不执行此项。");
            int sum = checked(reputation + delta);
            bool advances = sum >= threshold;
            int newLevel = advances ? checked(level + 1) : level;
            int newReputation = advances ? checked(sum - threshold) : sum;
            List<List<string>> tips = null;
            List<List<int>> achievements = null;
            int tipCount = 0, achievementCount = 0, achievementId = 0;
            string tipText = null;
            if (advances)
            {
                // FamilyLvSW mutates reputation/level before queuing these effects; validate first.
                tips = Mainload.Tip_Show;
                achievements = Mainload.AchDataUpdate;
                var text = AllText.Text_TipShow;
                var settings = Mainload.SetData;
                if (tips == null || achievements == null || settings == null || settings.Count <= 4 ||
                    text == null || text.Count <= 110 || text[110] == null ||
                    settings[4] < 0 || settings[4] >= text[110].Count || text[110][settings[4]] == null)
                    throw new InvalidOperationException("家族升级提示配置或事件队列尚未就绪，未调用升级函数。");
                int step = Mainload.ChengHaoLvNum;
                if (step <= 0 || step > int.MaxValue / 4)
                    throw new InvalidOperationException("家族称号成就配置超出已核对范围。");
                for (int i = 1; i <= 4; i++)
                    if (newLevel == checked(step * i)) { achievementId = 6 + i; break; }
                tipText = text[110][settings[4]].Replace("@", newLevel.ToString(CultureInfo.CurrentCulture));
                tipCount = tips.Count;
                achievementCount = achievements.Count;
            }
            var result = (string[])expected.OriginalData.Clone();
            result[3] = newReputation.ToString(CultureInfo.CurrentCulture);
            if (advances) result[2] = newLevel.ToString(CultureInfo.CurrentCulture);
            Validate(expected);
            try
            {
                FormulaData.FamilyLvSW(delta);
                ValidateContext(expected);
                Match(expected.Data, result, "家族");
                Match(expected.Coins, expected.OriginalCoins, "资金");
                if (advances)
                {
                    if (!ReferenceEquals(tips, Mainload.Tip_Show) || tips.Count != tipCount + 1 ||
                        tips[tipCount] == null || tips[tipCount].Count != 2 ||
                        tips[tipCount][0] != "2" || tips[tipCount][1] != tipText)
                        throw new InvalidOperationException("升级提示队列读回不一致");
                    if (!ReferenceEquals(achievements, Mainload.AchDataUpdate) ||
                        achievements.Count != achievementCount + (achievementId == 0 ? 0 : 1))
                        throw new InvalidOperationException("称号成就队列读回不一致");
                    if (achievementId != 0 && (achievements[achievementCount] == null ||
                        achievements[achievementCount].Count != 2 || achievements[achievementCount][0] != achievementId ||
                        achievements[achievementCount][1] != 1))
                        throw new InvalidOperationException("称号成就内容读回不一致");
                }
            }
            catch (Exception e) { throw Dispatched("家族声望变更", e); }
            return "家族等级 " + level + " → " + newLevel + "；声望 " + reputation + " → " + newReputation +
                "（增加 " + delta + "，原函数执行一次并已读回；升级联动不可简单撤销）";
        }

        private static void Consume(Snapshot s)
        {
            if (s == null) throw new InvalidOperationException("请先读取家族数据。");
            if (Interlocked.Exchange(ref s.Used, 1) != 0)
                throw new InvalidOperationException("此家族快照已使用；上次成功或失败后均需重新读取。");
        }

        private static void Validate(Snapshot s)
        {
            ValidateContext(s);
            Match(s.Coins, s.OriginalCoins, "资金");
            Match(s.Data, s.OriginalData, "家族");
        }

        private static void ValidateContext(Snapshot s)
        {
            if (Thread.CurrentThread.ManagedThreadId != s.ThreadId ||
                s.Generation != Interlocked.Read(ref generation) || s.Culture != CultureInfo.CurrentCulture.Name)
                throw new InvalidOperationException("线程、读取快照或区域设置已变化，请在游戏主线程重新读取。");
            s.Context.Validate();
            if (!ReferenceEquals(s.Coins, Mainload.CGNum) || !ReferenceEquals(s.Data, Mainload.FamilyData))
                throw new InvalidOperationException("家族或资金对象已更换，请重新读取。");
        }

        private static void Match(List<string> actual, string[] expected, string name)
        {
            if (actual == null || actual.Count != expected.Length)
                throw new InvalidOperationException(name + "结构已变化。");
            for (int i = 0; i < expected.Length; i++)
                if (!string.Equals(actual[i], expected[i], StringComparison.Ordinal))
                    throw new InvalidOperationException(name + "数据已变化或读回不符，请重新读取。");
        }

        private static int Number(string text)
        {
            int value;
            if (!int.TryParse(text, NumberStyles.Integer, CultureInfo.CurrentCulture, out value))
                throw new InvalidOperationException("资金或家族字段不是有效的 Int32 整数。");
            return value;
        }

        private static long Balance(string[] coins) { return checked((long)Number(coins[2]) * Segment + Number(coins[0])); }

        private static InvalidOperationException Dispatched(string action, Exception e)
        {
            return new InvalidOperationException(action + "已调用一次，但结果未能完整核验；请检查游戏并重新读取，不自动重试或回滚。原因：" + e.Message, e);
        }
    }
}
