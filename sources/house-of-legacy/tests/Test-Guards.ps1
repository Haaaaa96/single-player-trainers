# Offline boundary checks only: real Members.cs/Family.cs with deliberately small game/context doubles.
# This does not load a game assembly, inspect a save, validate Unity UI, or prove in-game behavior.
# Run in a fresh PowerShell 7 process: pwsh -NoProfile -File ./tests/Test-Guards.ps1
$ErrorActionPreference = 'Stop'
if ('HouseOfLegacyTrainer.GuardChecks' -as [type]) {
    throw 'Run Test-Guards.ps1 in a fresh PowerShell process; its in-memory types are already loaded.'
}
$project = Split-Path -Parent $PSScriptRoot
$sources = foreach ($name in @('Members.cs', 'Family.cs')) {
    $content = Get-Content -Raw -LiteralPath (Join-Path $project "src/$name")
    $content -replace '(?m)^using [^\r\n]+;\r?\n', ''
}
$fixture = @'
public static class Mainload
{
    public static List<List<string>> Member_now;
    public static List<string> CGNum, FamilyData;
    public static List<List<string>> Tip_Show;
    public static List<List<int>> AchDataUpdate;
    public static List<int> SetData;
    public static int ChengHaoLvNum;
}
public static class AllText { public static List<List<string>> Text_TipShow; }
public static class FormulaData
{
    public static int MoneyCalls, ReputationCalls;
    // Fixed double: checks recovery branching, not the real age formula.
    public static int GetTiliMax(int age) { return 25; }
    public static int ShengWangForLv(int level) { return unchecked(level * 20); }
    public static int GetCoinsNum()
    {
        int low = int.Parse(Mainload.CGNum[0]), high = int.Parse(Mainload.CGNum[2]);
        return unchecked(high > 0 ? low + 1000000000 : high < 0 ? low - 1000000000 : low);
    }
    // Minimal reference doubles of inspected IL; calls are counted to prove pre-dispatch refusal.
    public static void ChangeCoins(int delta)
    {
        MoneyCalls++;
        unchecked
        {
            int low = int.Parse(Mainload.CGNum[0]) + delta;
            int high = int.Parse(Mainload.CGNum[2]);
            Mainload.CGNum[0] = low.ToString();
            if (low > 1000000000) {
                Mainload.CGNum[0] = (low - 1000000000).ToString();
                Mainload.CGNum[2] = (high + 1).ToString();
            } else if ((low <= 0 && high > 0) || low < -1000000000) {
                Mainload.CGNum[0] = (low + 1000000000).ToString();
                Mainload.CGNum[2] = (high - 1).ToString();
            }
        }
    }
    public static void FamilyLvSW(int delta)
    {
        ReputationCalls++;
        int level = int.Parse(Mainload.FamilyData[2]);
        if (GetCoinsNum() < 0 || level >= 80) return;
        int reputation = unchecked(int.Parse(Mainload.FamilyData[3]) + delta);
        Mainload.FamilyData[3] = Math.Max(0, reputation).ToString();
        if (reputation < ShengWangForLv(level)) return;
        Mainload.FamilyData[3] = (reputation - ShengWangForLv(level)).ToString();
        Mainload.FamilyData[2] = (++level).ToString();
        for (int i = 1; i <= 4; i++) if (level == Mainload.ChengHaoLvNum * i) {
            Mainload.AchDataUpdate.Add(new List<int> { 6 + i, 1 }); break;
        }
        Mainload.Tip_Show.Add(new List<string> { "2", AllText.Text_TipShow[110][Mainload.SetData[4]].Replace("@", level.ToString()) });
    }
}
namespace HouseOfLegacyTrainer
{
    internal sealed class GameContext
    {
        public static bool Valid = true;
        public static GameContext Capture() { if (!Valid) throw new InvalidOperationException("context"); return new GameContext(); }
        public void Validate() { if (!Valid) throw new InvalidOperationException("context"); }
    }
    public static class GuardChecks
    {
        private static readonly List<string> passed = new List<string>();
        private static void Check(bool value, string name) { if (!value) throw new Exception(name); passed.Add(name); }
        private static void Refuse(Action action, string name)
        {
            bool refused = false;
            try { action(); } catch (InvalidOperationException) { refused = true; } catch (OverflowException) { refused = true; }
            Check(refused, name);
        }
        private static void ResetMember()
        {
            GameContext.Valid = true;
            var row = new List<string>(); for (int i = 0; i < 45; i++) row.Add("0");
            row[0] = "member-a"; row[4] = "甲|其他"; row[6] = "25"; row[7] = "17.25";
            row[8] = "20"; row[9] = "30"; row[10] = "40"; row[11] = "0";
            row[21] = "90"; row[30] = "3"; row[41] = "-1|0|0";
            Mainload.Member_now = new List<List<string>> { row };
        }
        private static void ResetFamily(string low = "10", string high = "0", string level = "1", string reputation = "0")
        {
            GameContext.Valid = true; FormulaData.MoneyCalls = 0; FormulaData.ReputationCalls = 0;
            Mainload.CGNum = new List<string> { low, "99", high, "preserved" };
            Mainload.FamilyData = new List<string> { "family", "other", level, reputation, "tail" };
            Mainload.Tip_Show = new List<List<string>>(); Mainload.AchDataUpdate = new List<List<int>>();
            Mainload.SetData = new List<int> { 0, 0, 0, 0, 0 }; Mainload.ChengHaoLvNum = 2;
            AllText.Text_TipShow = new List<List<string>>();
            for (int i = 0; i <= 110; i++) AllText.Text_TipShow.Add(new List<string> { "level @" });
        }
        public static string[] Run()
        {
            CultureInfo previous = CultureInfo.CurrentCulture;
            try { CultureInfo.CurrentCulture = CultureInfo.InvariantCulture; MembersCases(); FamilyCases(); return passed.ToArray(); }
            finally { CultureInfo.CurrentCulture = previous; }
        }
        private static void MembersCases()
        {
            ResetMember(); var s = Members.Read(0);
            Check(s.Name == "甲" && s.Values["writing"] == "17.25", "Members: first read and identity fields");
            Members.Apply(s, "writing", "18.5"); Check(Mainload.Member_now[0][7] == "18.5", "Members: fractional write");
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: success consumes snapshot");
            s = Members.Read(0); Refuse(() => Members.Apply(s, "health", "0"), "Members: health zero refused");
            Refuse(() => Members.Apply(s, "health", "91"), "Members: failure consumes snapshot");
            Check(Mainload.Member_now[0][21] == "90", "Members: rejected health unchanged");
            s = Members.Read(0); Mainload.Member_now[0][22] = "changed";
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: unrelated column change refused");
            ResetMember(); s = Members.Read(0); Mainload.Member_now[0] = new List<string>(Mainload.Member_now[0]);
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: equal-content row replacement refused");
            ResetMember(); s = Members.Read(0); Mainload.Member_now = new List<List<string>>(Mainload.Member_now);
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: table replacement refused");
            ResetMember(); s = Members.Read(0); Members.Read(0);
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: fresh read invalidates old snapshot");
            ResetMember(); s = Members.Read(0); Members.List();
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: list refresh invalidates snapshot");
            ResetMember(); Mainload.Member_now.Add(new List<string>(Mainload.Member_now[0]));
            Refuse(() => Members.Read(0), "Members: duplicate ID refused");
            ResetMember(); s = Members.Read(0); GameContext.Valid = false;
            Refuse(() => Members.Apply(s, "writing", "19"), "Members: context change refused");
            ResetMember(); s = Members.Read(0); Members.RestoreStamina(s);
            Check(Mainload.Member_now[0][30] == "25", "Members: normal stamina recovery branch");
            ResetMember(); Mainload.Member_now[0][41] = "1|0|0"; s = Members.Read(0); Members.RestoreStamina(s);
            Check(Mainload.Member_now[0][30] == "7", "Members: state stamina ceiling branch");
            ResetMember(); Mainload.Member_now[0][21] = "bad"; s = Members.Read(0);
            Check(s.Unavailable.ContainsKey("health") && !s.Unavailable.ContainsKey("writing"), "Members: invalid field isolated");
            Members.Apply(s, "writing", "18"); Check(Mainload.Member_now[0][7] == "18", "Members: unrelated field still usable");
            ResetMember(); s = Members.Read(0); Refuse(() => Members.Apply(s, "writing", "NaN"), "Members: NaN refused");
            ResetMember(); s = Members.Read(0); Refuse(() => Members.Apply(s, "writing", "100.5"), "Members: range exceeded refused");
            ResetMember(); s = Members.Read(0); Refuse(() => Members.Apply(s, "stamina", "10"), "Members: arbitrary stamina refused");
            ResetMember(); s = Members.Read(0); Exception failure = null;
            var thread = new Thread(() => { try { Members.Apply(s, "writing", "19"); } catch (Exception e) { failure = e; } });
            thread.Start(); thread.Join();
            Check(failure is InvalidOperationException && Mainload.Member_now[0][7] == "17.25", "Members: other thread refused without write");
            ResetMember(); s = Members.Read(0); Members.Apply(s, "renown", "42.125");
            Check(Mainload.Member_now[0][16] == "42.125" && Members.FieldKeys[6] == "stamina", "Members: renown fractional write and old field index preserved");
            ResetMember(); s = Members.Read(0); Refuse(() => Members.Apply(s, "charisma", "12.5"), "Members: fractional charisma refused for integer consumer");
            ResetMember(); s = Members.Read(0); Refuse(() => Members.Apply(s, "cunning", "12.5"), "Members: fractional cunning refused for integer consumer");
            ResetMember(); Mainload.Member_now[0][20] = "7"; s = Members.Read(0); Members.Apply(s, "charisma", "0");
            Check(Mainload.Member_now[0][20] == "0" && Mainload.Member_now[0][21] == "90", "Members: charisma zero allowed and health preserved");
            ResetMember(); s = Members.Read(0); Members.Apply(s, "cunning", "100");
            Check(Mainload.Member_now[0][27] == "100", "Members: cunning supported upper boundary");
            s = Members.Read(0); Refuse(() => Members.Apply(s, "cunning", "101"), "Members: cunning above supported range refused");
            ResetMember(); Mainload.Member_now[0][20] = "12.5"; s = Members.Read(0);
            Check(s.Unavailable.ContainsKey("charisma") && !s.Unavailable.ContainsKey("renown"), "Members: malformed integer field is isolated");
        }
        private static void FamilyCases()
        {
            ResetFamily("999999999", "1"); var s = Family.Read(); Family.ChangeMoney(s, 1);
            Check(Mainload.CGNum[0] == "1000000000" && Mainload.CGNum[2] == "1", "Family: exact billion does not carry");
            Refuse(() => Family.ChangeMoney(s, 1), "Family: successful money snapshot cannot repeat");
            ResetFamily("999999999", "1"); s = Family.Read(); Family.ChangeMoney(s, 2);
            Check(Mainload.CGNum[0] == "1" && Mainload.CGNum[2] == "2" && Mainload.CGNum[1] == "99" && Mainload.CGNum[3] == "preserved", "Family: carry preserves other money fields");
            ResetFamily("5", "1"); s = Family.Read(); Family.ChangeMoney(s, -5);
            Check(Mainload.CGNum[0] == "1000000000" && Mainload.CGNum[2] == "0", "Family: zero remainder borrows");
            ResetFamily(int.MaxValue.ToString()); s = Family.Read();
            Refuse(() => Family.ChangeMoney(s, 1), "Family: Int32 intermediate addition overflow refused");
            Check(FormulaData.MoneyCalls == 0, "Family: addition overflow not dispatched");
            ResetFamily("1000000000", int.MaxValue.ToString()); s = Family.Read();
            Refuse(() => Family.ChangeMoney(s, 1), "Family: segment overflow refused");
            Check(FormulaData.MoneyCalls == 0, "Family: segment overflow not dispatched");
            ResetFamily("0", "9000000"); s = Family.Read();
            Refuse(() => Family.ChangeMoney(s, 1), "Family: tool total balance limit refused");
            ResetFamily("0"); s = Family.Read(); Refuse(() => Family.ChangeMoney(s, -1), "Family: negative result refused");
            Refuse(() => Family.ChangeMoney(s, 1), "Family: failed money snapshot cannot repeat");
            Check(FormulaData.MoneyCalls == 0, "Family: failed snapshot never dispatched");
            ResetFamily(); s = Family.Read(); Mainload.CGNum[1] = "100";
            Refuse(() => Family.ChangeMoney(s, 1), "Family: unrelated money field change refused");
            ResetFamily(); s = Family.Read(); Family.AddReputation(s, 19);
            Check(Mainload.FamilyData[2] == "1" && Mainload.FamilyData[3] == "19" && Mainload.Tip_Show.Count == 0, "Family: reputation below threshold does not level");
            ResetFamily(); s = Family.Read(); Family.AddReputation(s, 20);
            Check(Mainload.FamilyData[2] == "2" && Mainload.FamilyData[3] == "0" && Mainload.Tip_Show.Count == 1 && Mainload.AchDataUpdate.Count == 1, "Family: exact threshold advances once with queues");
            Refuse(() => Family.AddReputation(s, 1), "Family: successful reputation snapshot cannot repeat");
            ResetFamily(); s = Family.Read(); Refuse(() => Family.AddReputation(s, 21), "Family: excess reputation refused");
            Check(FormulaData.ReputationCalls == 0, "Family: excess reputation not dispatched");
            ResetFamily("10", "0", "80"); s = Family.Read();
            Refuse(() => Family.AddReputation(s, 1), "Family: maximum level refused");
            Check(s.Remaining == 0 && FormulaData.ReputationCalls == 0, "Family: maximum level has no pending dispatch");
            ResetFamily(); s = Family.Read(); Mainload.Tip_Show = null;
            Refuse(() => Family.AddReputation(s, 20), "Family: missing upgrade queue refused before mutation");
            Check(FormulaData.ReputationCalls == 0 && Mainload.FamilyData[2] == "1" && Mainload.FamilyData[3] == "0", "Family: incomplete queue leaves family unchanged");
        }
    }
}
'@
$imports = "using System;`nusing System.Collections.Generic;`nusing System.Globalization;`nusing System.Threading;`n"
Add-Type -TypeDefinition ($imports + ($sources -join [Environment]::NewLine) + [Environment]::NewLine + $fixture)
$results = [HouseOfLegacyTrainer.GuardChecks]::Run()
$results | ForEach-Object { "PASS $_" }
"Passed $($results.Count) offline boundary checks. Game/context/formula doubles were used; this is not in-game validation."
