using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using UnityEngine;
using UnityEngine.UI;

namespace HouseOfLegacyTrainer
{
    // All entry points are called on Unity's main thread. This module never patches
    // game methods, grants points automatically, confirms a character, or saves.
    internal static class Traits
    {
        internal sealed class Snapshot
        {
            public int Points;
            public string Summary;
            internal InitGameUI Panel;
            internal Transform Parent;
            internal LoadPanel Loading;
            internal Text Tip;
            internal FieldInfo PointsField;
            internal int CapturedPoints;
            internal List<int> Choices, Generated, Talent, Settings;
            internal int[] ChoiceValues, GeneratedValues, TalentValues;
            internal List<List<string>> Config, Members;
            internal List<string>[] Rows;
            internal string[][] RowValues;
            internal int Language;
            internal string Template;
            internal bool FirstGame, Attempted;
        }

        private const BindingFlags InstanceMembers = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        public static Snapshot Read()
        {
            try { return Capture(); }
            catch (InvalidOperationException) { throw; }
            catch (Exception e)
            {
                throw new InvalidOperationException("开局特质读取失败，请重新打开角色创建界面后刷新。" + e.Message, e);
            }
        }

        public static string Apply(Snapshot expected, int target)
        {
            if (target < 0 || target > 1000)
                throw new InvalidOperationException("剩余点数必须为 0 到 1000 的整数。");
            if (expected == null) throw new InvalidOperationException("请先读取当前开局特质点数。");
            if (expected.Attempted)
                throw new InvalidOperationException("这次修改请求已经使用，请刷新并核对当前点数后再操作。");

            Snapshot current = Read();
            if (!Same(expected, current, false))
                throw new InvalidOperationException("创建界面、点数或所选特质已变化，请刷新后重新操作。");
            string title = current.Template.Replace("@", target.ToString(CultureInfo.InvariantCulture));
            expected.Attempted = true; // Consume before the only write, including uncertain failures.
            if (target == current.CapturedPoints)
                return "剩余点数已经是 " + target + "，无需修改。";

            try
            {
                current.PointsField.SetValue(current.Panel, target);
                Snapshot after = Read();
                if (after.CapturedPoints != target || !Same(current, after, true))
                    throw new InvalidOperationException("写入后核对未通过。");
            }
            catch (Exception e)
            {
                throw new InvalidOperationException("点数写入结果未能完整确认。本次请求已作废，请先刷新核对；不要重复加点。" + e.Message, e);
            }

            // Only the original localized counter text changes. Calling InitData or
            // InitShow would reset/randomize the character; CiTiaoShow would also
            // replace the game's current-choice delta labels with base costs.
            try
            {
                current.Tip.text = title;
                if (current.Tip.text != title)
                    throw new InvalidOperationException("计数文字未同步。");
            }
            catch (Exception e)
            {
                return "剩余点数已由 " + current.CapturedPoints + " 改为 " + target +
                    "，但游戏文字刷新失败；请核对数值，不要重复加点。" + e.Message;
            }
            return "开局特质剩余点数：" + current.CapturedPoints + " → " + target +
                "。可在游戏原界面选择特质，角色尚未确认。";
        }

        private static Snapshot Capture()
        {
            Interaction.Require();
            InitGameUI active = null;
            foreach (InitGameUI panel in UnityEngine.Object.FindObjectsOfType<InitGameUI>())
            {
                if (panel == null || !panel.isActiveAndEnabled || !panel.gameObject.activeInHierarchy) continue;
                if (active != null) throw new InvalidOperationException("发现多个角色创建界面，暂不修改。");
                active = panel;
            }
            if (active == null) throw new InvalidOperationException("请先进入“选择角色特质”的角色创建界面。");
            Transform parent = active.transform.parent;
            if (parent == null) throw new InvalidOperationException("角色创建界面尚未就绪。");
            Transform loadTransform = parent.Find("LoadPanel");
            LoadPanel loading = loadTransform == null ? null : loadTransform.GetComponent<LoadPanel>();
            if (loading == null) throw new InvalidOperationException("无法核对角色创建的加载状态，暂不修改。");
            if (loading.gameObject.activeInHierarchy)
                throw new InvalidOperationException("正在确认角色或加载游戏，请等待；此时不能修改开局点数。");
            Transform tipTransform = active.transform.Find("CiTiao/Tip");
            Text tip = tipTransform == null ? null : tipTransform.GetComponent<Text>();
            if (tip == null) throw new InvalidOperationException("尚未找到角色特质点数显示，请等待界面初始化。");

            RequireMethod("CiTiaoBT", new Type[] { typeof(string) });
            RequireMethod("SureBT", Type.EmptyTypes);
            FieldInfo pointsField = RequireField("CiTaio_Point_Have", typeof(int));
            var s = new Snapshot();
            s.Panel = active;
            s.Parent = parent;
            s.Loading = loading;
            s.Tip = tip;
            s.PointsField = pointsField;
            s.CapturedPoints = (int)pointsField.GetValue(active);
            if (s.CapturedPoints < 0) throw new InvalidOperationException("当前剩余点数异常，暂不修改。");
            s.Points = s.CapturedPoints;
            s.Choices = ReadList(active, "AllShuxingCiTiao_Index");
            s.Generated = ReadList(active, "CreateShuXing_CiTiao");
            s.Talent = ReadList(active, "TianFuData");
            s.Config = Mainload.ShuXingCiTiao_Member;
            if (s.Config == null || s.Config.Count < 8 || s.Config.Count > 64 ||
                s.Choices.Count != s.Config.Count || s.Generated.Count != s.Config.Count || s.Talent.Count != 2)
                throw new InvalidOperationException("角色特质选择数据尚未完整初始化，暂不修改。");
            s.ChoiceValues = s.Choices.ToArray();
            s.GeneratedValues = s.Generated.ToArray();
            s.TalentValues = s.Talent.ToArray();
            s.Rows = s.Config.ToArray();
            s.RowValues = new string[s.Rows.Length][];
            for (int i = 0; i < s.Rows.Length; i++)
            {
                List<string> row = s.Rows[i];
                if (row == null || row.Count < 2 || row.Count > 32 || s.ChoiceValues[i] < 0 || s.ChoiceValues[i] >= row.Count)
                    throw new InvalidOperationException("当前角色特质选项与配置不匹配，暂不修改。");
                s.RowValues[i] = row.ToArray();
                int selectedContribution = Contribution(row[s.ChoiceValues[i]]);
                foreach (string option in row)
                {
                    long difference = (long)Contribution(option) - selectedContribution;
                    if (difference < int.MinValue || difference + 1000 > int.MaxValue)
                        throw new InvalidOperationException("角色特质点数计算超出有效范围，暂不修改。");
                }
            }
            s.Settings = Mainload.SetData;
            if (s.Settings == null || s.Settings.Count <= 4)
                throw new InvalidOperationException("游戏语言设置尚未初始化。");
            s.Language = s.Settings[4];
            if (AllText.Text_UIA == null || AllText.Text_UIA.Count <= 36 ||
                AllText.Text_UIA[36] == null || s.Language < 0 || s.Language >= AllText.Text_UIA[36].Count)
                throw new InvalidOperationException("角色特质提示文字尚未初始化。");
            s.Template = AllText.Text_UIA[36][s.Language];
            if (string.IsNullOrEmpty(s.Template) || !s.Template.Contains("@"))
                throw new InvalidOperationException("角色特质提示格式发生变化，暂不修改。");
            s.FirstGame = Mainload.isFirstGame;
            s.Members = Mainload.Member_now;
            s.Summary = "开局角色特质：剩余 " + s.Points + " 点，" + s.Choices.Count +
                " 组选项已就绪。修改后仍由你在原界面选择和确认角色。";
            return s;
        }

        private static FieldInfo RequireField(string name, Type type)
        {
            FieldInfo field = typeof(InitGameUI).GetField(name, InstanceMembers);
            if (field == null || field.IsStatic || field.FieldType != type || field.DeclaringType != typeof(InitGameUI))
                throw new InvalidOperationException("开局特质字段结构不匹配：" + name);
            return field;
        }

        private static void RequireMethod(string name, Type[] parameters)
        {
            MethodInfo method = typeof(InitGameUI).GetMethod(name, InstanceMembers, null, parameters, null);
            if (method == null || method.IsStatic || method.ReturnType != typeof(void) || method.DeclaringType != typeof(InitGameUI))
                throw new InvalidOperationException("开局特质方法结构不匹配：" + name);
        }

        private static List<int> ReadList(InitGameUI panel, string name)
        {
            List<int> list = RequireField(name, typeof(List<int>)).GetValue(panel) as List<int>;
            if (list == null) throw new InvalidOperationException("角色创建数据尚未初始化，请稍后刷新。");
            return list;
        }

        private static int Contribution(string option)
        {
            if (option == null) throw new InvalidOperationException("角色特质配置为空，暂不修改。");
            string[] parts = option.Split('|');
            int lower, upper, value;
            if (parts.Length < 3 || !int.TryParse(parts[0], out lower) || !int.TryParse(parts[1], out upper) ||
                !int.TryParse(parts[2], out value) || lower > upper)
                throw new InvalidOperationException("角色特质配置格式无法核对，暂不修改。");
            return value;
        }

        private static bool Same(Snapshot a, Snapshot b, bool ignorePoints)
        {
            if (a.Panel == null || a.Panel != b.Panel || a.Parent != b.Parent || a.Loading != b.Loading || a.Tip != b.Tip ||
                (!ignorePoints && a.CapturedPoints != b.CapturedPoints) ||
                !ReferenceEquals(a.Choices, b.Choices) || !ReferenceEquals(a.Generated, b.Generated) ||
                !ReferenceEquals(a.Talent, b.Talent) || !ReferenceEquals(a.Config, b.Config) ||
                !ReferenceEquals(a.Settings, b.Settings) || !ReferenceEquals(a.Members, b.Members) ||
                a.Language != b.Language || a.Template != b.Template || a.FirstGame != b.FirstGame ||
                !Equal(a.ChoiceValues, b.ChoiceValues) || !Equal(a.GeneratedValues, b.GeneratedValues) ||
                !Equal(a.TalentValues, b.TalentValues) || a.Rows.Length != b.Rows.Length) return false;
            for (int i = 0; i < a.Rows.Length; i++)
            {
                if (!ReferenceEquals(a.Rows[i], b.Rows[i]) || a.RowValues[i].Length != b.RowValues[i].Length) return false;
                for (int j = 0; j < a.RowValues[i].Length; j++)
                    if (a.RowValues[i][j] != b.RowValues[i][j]) return false;
            }
            return true;
        }

        private static bool Equal(int[] a, int[] b)
        {
            if (a.Length != b.Length) return false;
            for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
            return true;
        }
    }
}
