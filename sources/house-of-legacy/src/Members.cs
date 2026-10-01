using System;
using System.Collections.Generic;
using System.Globalization;
using System.Threading;

namespace HouseOfLegacyTrainer
{
    // Schema evidence: MemberNowInfoPanel.OnEnableData; identity: FormulaData.Get_Memberindex.
    // The ranges below are this tool's supported ranges, not a claim about all game/mod limits.
    internal static class Members
    {
        public static readonly string[] FieldKeys = { "writing", "might", "business", "arts", "mood", "health", "stamina", "renown", "charisma", "cunning" };
        private static readonly int[] Columns = { 7, 8, 9, 10, 11, 21, 30, 16, 20, 27 };
        private static readonly string[] Labels = { "文才", "武才", "商才", "艺才", "心情", "健康", "体力", "声名", "魅力", "心机" };
        private static long generation;

        public sealed class Entry
        {
            public int Index;
            public string Id, Name, Summary;
        }

        public sealed class Snapshot
        {
            public int Index;
            public string Id, Name, Summary, StaminaTarget;
            public Dictionary<string, string> Values;
            public Dictionary<string, string> Limits;
            public Dictionary<string, string> Unavailable;
            internal GameContext Context;
            internal List<List<string>> Table;
            internal List<string> Row;
            internal string[] Original;
            internal int OriginalIndex, TableCount, ReadThread, Used;
            internal long Generation;
            internal string CultureName, DecimalSeparator;
        }

        public static string FieldLabel(string key) { return Labels[FieldIndex(key)]; }

        public static List<Entry> List()
        {
            Interlocked.Increment(ref generation); // Refreshing a selection invalidates its old action.
            GameContext context = GameContext.Capture();
            List<List<string>> table = RequireTable();
            int count = table.Count;
            var result = new List<Entry>();
            for (int i = 0; i < count; i++)
            {
                var row = table[i];
                bool readable = row != null && row.Count > 6 && !string.IsNullOrEmpty(row[0]) && !string.IsNullOrEmpty(row[4]);
                result.Add(new Entry {
                    Index = i, Id = readable ? row[0] : "",
                    Name = readable ? MemberName(row[4]) : "资料未就绪",
                    Summary = readable ? "ID " + row[0] + " · 年龄 " + row[6] : "此行身份字段不完整，暂不可修改"
                });
            }
            context.Validate();
            if (!ReferenceEquals(table, Mainload.Member_now) || count != table.Count)
                throw new InvalidOperationException("族人列表已变化，请重新刷新。");
            return result;
        }

        public static Snapshot Read(int index)
        {
            long currentGeneration = Interlocked.Increment(ref generation);
            GameContext context = GameContext.Capture();
            List<List<string>> table = RequireTable();
            if (index < 0 || index >= table.Count) throw new InvalidOperationException("选定族人已不存在，请刷新列表。");
            List<string> row = table[index];
            if (row == null || row.Count <= 30 || string.IsNullOrEmpty(row[0]) || string.IsNullOrEmpty(row[4]))
                throw new InvalidOperationException("该族人的身份或基础字段不完整。");
            RequireUniqueId(table, row[0]);
            var s = new Snapshot {
                Index = index, OriginalIndex = index, Id = row[0], Name = MemberName(row[4]),
                Summary = "ID " + row[0] + " · 年龄 " + row[6],
                Context = context, Table = table, Row = row, Original = row.ToArray(), TableCount = table.Count,
                Generation = currentGeneration, ReadThread = Thread.CurrentThread.ManagedThreadId,
                CultureName = CultureInfo.CurrentCulture.Name,
                DecimalSeparator = CultureInfo.CurrentCulture.NumberFormat.NumberDecimalSeparator,
                Values = new Dictionary<string, string>(), Limits = new Dictionary<string, string>(),
                Unavailable = new Dictionary<string, string>()
            };
            for (int i = 0; i < FieldKeys.Length; i++)
            {
                string key = FieldKeys[i];
                s.Values[key] = row[Columns[i]];
                s.Limits[key] = IsFloatField(i) ? "本工具范围 0–100，可保留小数；游戏面板向下取整" :
                    i == 4 ? "整数 -100–100" : i == 5 ? "整数 1–100；不改寿命，不保证消除疾病" :
                    i == 6 ? "按当前年龄及状态单次恢复" : "本工具范围 0–100，只接受整数";
                try
                {
                    ValidateCurrent(row[Columns[i]], i);
                    if (i == 6)
                    {
                        int maximum = StaminaRecoveryTarget(row);
                        s.StaminaTarget = maximum.ToString(CultureInfo.InvariantCulture);
                        s.Limits[key] = "按当前年龄及状态恢复至 " + s.StaminaTarget;
                    }
                }
                catch (Exception e) { s.Unavailable[key] = e.Message; }
            }
            ValidateSnapshot(s);
            return s;
        }

        public static string Apply(Snapshot expected, string fieldKey, string target)
        {
            Consume(expected);
            int field = FieldIndex(fieldKey);
            if (field == 6) throw new InvalidOperationException("体力请使用“恢复体力”，不接受任意目标值。");
            ValidateSnapshot(expected);
            ValidateCurrent(expected.Original[Columns[field]], field);
            string value;
            if (IsFloatField(field))
            {
                float number = ParseInputFloat(target);
                if (number < 0 || number > 100) throw new InvalidOperationException(Labels[field] + "的本工具输入范围为 0–100。");
                value = number.ToString("R", CultureInfo.CurrentCulture);
            }
            else
            {
                int number = ParseInteger(target, "目标值");
                int minimum = field == 4 ? -100 : field == 5 ? 1 : 0;
                if (number < minimum || number > 100)
                    throw new InvalidOperationException(Labels[field] + "请输入 " + minimum + "–100 的整数。");
                value = number.ToString(CultureInfo.CurrentCulture);
            }
            return Write(expected, field, value);
        }

        public static string RestoreStamina(Snapshot expected)
        {
            Consume(expected);
            ValidateSnapshot(expected);
            ValidateCurrent(expected.Original[30], 6);
            int maximum = StaminaRecoveryTarget(expected.Row);
            int before = ParseInteger(expected.Original[30], "当前体力");
            if (before >= maximum) return MemberName(expected.Original[4]) + "体力已达到当前恢复目标 " + maximum + "，未改动。";
            return Write(expected, 6, maximum.ToString(CultureInfo.CurrentCulture));
        }

        private static string Write(Snapshot s, int field, string value)
        {
            // Only one list element is assigned, on the validated Unity/main-thread context.
            // No save, event, injection, refresh callback, or automatic retry is invoked here.
            ValidateSnapshot(s);
            int column = Columns[field];
            string before = s.Original[column];
            if (string.Equals(before, value, StringComparison.Ordinal))
                return MemberName(s.Original[4]) + "的" + Labels[field] + "已为 " + value + "，未改动。";
            s.Row[column] = value;
            try
            {
                s.Context.Validate();
                ValidateIdentity(s);
                for (int i = 0; i < s.Original.Length; i++)
                    if (!string.Equals(s.Row[i], i == column ? value : s.Original[i], StringComparison.Ordinal))
                        throw new InvalidOperationException("写后整行复读不一致");
            }
            catch (Exception e)
            {
                throw new InvalidOperationException("已执行一次写入，但结果核对失败；请重新读取并检查游戏，不要重复提交。原因：" + e.Message, e);
            }
            return MemberName(s.Original[4]) + " · " + Labels[field] + "：" + before + " → " + value + "（已读回）";
        }

        private static void Consume(Snapshot s)
        {
            if (s == null) throw new InvalidOperationException("请先读取当前族人。");
            if (Interlocked.Exchange(ref s.Used, 1) != 0)
                throw new InvalidOperationException("此快照已使用；无论上次成功或失败，都需重新读取。");
            // Input errors also consume the snapshot. A failed operation never retries itself.
        }

        private static void ValidateSnapshot(Snapshot s)
        {
            if (Thread.CurrentThread.ManagedThreadId != s.ReadThread)
                throw new InvalidOperationException("族人操作必须在原读取的游戏主线程执行。");
            if (s.Generation != Interlocked.Read(ref generation))
                throw new InvalidOperationException("选择或读取已刷新，请使用新的族人快照。");
            if (s.CultureName != CultureInfo.CurrentCulture.Name ||
                s.DecimalSeparator != CultureInfo.CurrentCulture.NumberFormat.NumberDecimalSeparator)
                throw new InvalidOperationException("数值区域设置已变化，请重新读取。");
            s.Context.Validate();
            ValidateIdentity(s);
            for (int i = 0; i < s.Original.Length; i++)
                if (!string.Equals(s.Row[i], s.Original[i], StringComparison.Ordinal))
                    throw new InvalidOperationException("该族人的数据已变化，请重新读取后再操作。");
        }

        private static void ValidateIdentity(Snapshot s)
        {
            if (!ReferenceEquals(s.Table, Mainload.Member_now) || s.Table.Count != s.TableCount ||
                s.OriginalIndex < 0 || s.OriginalIndex >= s.Table.Count ||
                !ReferenceEquals(s.Row, s.Table[s.OriginalIndex]) || s.Row.Count != s.Original.Length ||
                !string.Equals(s.Row[0], s.Original[0], StringComparison.Ordinal))
                throw new InvalidOperationException("族人对象、位置或列表已变化，请重新刷新。");
            RequireUniqueId(s.Table, s.Original[0]);
        }

        private static void RequireUniqueId(List<List<string>> table, string id)
        {
            int matches = 0;
            foreach (var row in table)
                if (row != null && row.Count > 0 && string.Equals(row[0], id, StringComparison.Ordinal)) matches++;
            if (matches != 1) throw new InvalidOperationException("族人 ID 不唯一，无法安全定位。");
        }

        private static List<List<string>> RequireTable()
        {
            if (Mainload.Member_now == null) throw new InvalidOperationException("当前本族成员表尚未就绪。");
            return Mainload.Member_now;
        }

        private static void ValidateCurrent(string value, int field)
        {
            if (IsFloatField(field))
            {
                float number;
                if (!float.TryParse(value, NumberStyles.Float, CultureInfo.CurrentCulture, out number) ||
                    float.IsNaN(number) || float.IsInfinity(number) || number < -100 || number > 100)
                    throw new InvalidOperationException("当前" + Labels[field] + "数值超出已核对的公式范围，暂不修改此项。");
                return;
            }
            int current = ParseInteger(value, "当前" + Labels[field]);
            if (field == 4 && (current < -100 || current > 100))
                throw new InvalidOperationException("当前心情超出已核对的公式范围。");
            if (field == 5 && (current < 1 || current > 100))
                throw new InvalidOperationException("当前健康不在 1–100 内；不操作死亡或未核验状态。");
            if (field == 6 && current < 0) throw new InvalidOperationException("当前体力为负，暂不修改此项。");
            if ((field == 8 || field == 9) && (current < -100 || current > 100))
                throw new InvalidOperationException("当前" + Labels[field] + "超出已核对的公式范围。");
        }

        // CreateMemberEvent.CreatEvent_Shijia: col16 Single.Parse (IL_0392), col20/27
        // Int32.Parse (IL_03aa/03ef). MainUpdate annual growth clamps col20/27 via
        // YiBaiNumChange_Zheng; col16 growth uses YiBaiNumChange. Integer consumers
        // make fractional charisma/cunning unsafe even where growth uses Single internally.
        private static bool IsFloatField(int field) { return field < 4 || field == 7; }

        private static int StaminaRecoveryTarget(List<string> row)
        {
            // MainUpdate.updateMemberNowData IL_302e..30bf uses this exact recovery branch.
            if (row.Count <= 41 || string.IsNullOrEmpty(row[41]))
                throw new InvalidOperationException("体力恢复状态字段不完整。");
            int age = ParseInteger(row[6], "年龄");
            if (age < 0) throw new InvalidOperationException("年龄无效，无法确定体力恢复目标。");
            int maximum = FormulaData.GetTiliMax(age);
            if (maximum <= 0) throw new InvalidOperationException("游戏体力公式未返回正数，暂不修改体力。");
            return row[41] == "-1|0|0" ? maximum : checked((int)Math.Ceiling(maximum / 4.0));
        }

        private static int ParseInteger(string text, string label)
        {
            int value;
            if (!int.TryParse(text, NumberStyles.Integer, CultureInfo.CurrentCulture, out value))
                throw new InvalidOperationException(label + "必须是可解析的整数。");
            return value;
        }

        private static float ParseInputFloat(string text)
        {
            float value;
            const NumberStyles style = NumberStyles.Float;
            if ((!float.TryParse(text, style, CultureInfo.CurrentCulture, out value) &&
                 !float.TryParse(text, style, CultureInfo.InvariantCulture, out value)) ||
                float.IsNaN(value) || float.IsInfinity(value))
                throw new InvalidOperationException("请输入有限数值，可使用小数点，不接受千位分隔符。");
            return value;
        }

        private static int FieldIndex(string key)
        {
            for (int i = 0; i < FieldKeys.Length; i++) if (FieldKeys[i] == key) return i;
            throw new InvalidOperationException("此字段未启用。");
        }

        private static string MemberName(string data) { return data.Split('|')[0]; }
    }
}
