param([string]$SourcePath = (Join-Path $PSScriptRoot '..\src\Inventory.cs'))
$ErrorActionPreference = 'Stop'
# Compile the real Inventory.cs against bounded data/context substitutes in this
# separate PowerShell process. This does not load or call any game assembly.
# The GameContext substitute verifies Inventory invokes the context guard, not
# the real Unity pause/scene/save detection. Runtime and save/reload are untested.
$stubs = @'
namespace HouseOfLegacyTrainer
{
    internal static class Mainload
    {
        internal static List<List<string>> Prop_have, AllPropdata;
        internal static List<string> FamilyData;
        internal static List<int> SetData;
        internal static bool isShopPanelOpen;
    }
    internal static class AllText { internal static List<List<string>> Text_AllProp; }
    internal sealed class GameContext
    {
        internal static int MainThread = Thread.CurrentThread.ManagedThreadId;
        internal static string CurrentSlot = "A";
        private string slot;
        internal static void RequireThread()
        {
            if (Thread.CurrentThread.ManagedThreadId != MainThread)
                throw new InvalidOperationException("wrong test thread");
        }
        internal static GameContext Capture() { RequireThread(); return new GameContext { slot = CurrentSlot }; }
        internal void Validate()
        {
            RequireThread();
            if (slot != CurrentSlot) throw new InvalidOperationException("测试上下文已换档");
        }
    }
    public static class InventoryOfflineChecks
    {
        private static void Reset()
        {
            GameContext.CurrentSlot = "A";
            Mainload.isShopPanelOpen = false;
            Mainload.Prop_have = new List<List<string>> {
                new List<string> { "2", "4" }, new List<string> { "3", "5" }
            };
            Mainload.FamilyData = new List<string> { "family", "surname", "1", "0", "fixed", "7", "tail" };
            Mainload.SetData = new List<int> { 0, 0, 0, 0, 0 };
            Mainload.AllPropdata = new List<List<string>>();
            AllText.Text_AllProp = new List<List<string>>();
            string[] labels = { "香烛", "肥料", "粮食", "蔬菜" };
            for (int i = 0; i < 4; i++)
            {
                Mainload.AllPropdata.Add(new List<string> { "cfg" + i, "2" });
                AllText.Text_AllProp.Add(new List<string> { labels[i], "name" + i });
            }
        }
        private static void Check(bool value, string message)
        {
            if (!value) throw new Exception("FAILED: " + message);
        }
        private static string State()
        {
            var lines = new List<string>();
            foreach (var row in Mainload.Prop_have) lines.Add(string.Join("|", row.ToArray()));
            return string.Join(";", lines.ToArray()) + " :: " + string.Join("|", Mainload.FamilyData.ToArray());
        }
        private static void Rejected(Action action, string reason)
        {
            string before = State();
            bool rejected = false;
            try { action(); }
            catch (InvalidOperationException e)
            {
                Check(e.Message.Contains(reason), "unexpected refusal: " + e.Message);
                rejected = true;
            }
            Check(rejected, "expected refusal: " + reason);
            Check(State() == before, "refused operation changed inventory or family");
        }
        public static string[] Run()
        {
            var output = new List<string>();
            Reset();
            var s = Inventory.Read();
            var root = Mainload.Prop_have;
            var row = Mainload.Prop_have[1];
            Check(s.Entries.Count == 1 && s.Entries[0].Id == "3" && s.Entries[0].Count == 5 && s.Capacity == 7, "read shape");
            Inventory.Add(s, "3", 3);
            Check(Mainload.Prop_have[1][1] == "8" && Mainload.FamilyData[5] == "4", "quantity/capacity direction");
            Check(Mainload.Prop_have[0][1] == "4" && Mainload.FamilyData[6] == "tail", "unrelated fields changed");
            Check(ReferenceEquals(root, Mainload.Prop_have) && ReferenceEquals(row, Mainload.Prop_have[1]), "inventory was rebuilt");
            Check(4 + int.Parse(Mainload.Prop_have[1][1]) + int.Parse(Mainload.FamilyData[5]) == 16, "capacity invariant");
            output.Add("PASS 1: success 5->8, free capacity 7->4; other fields and row identities unchanged");

            Reset(); s = Inventory.Read();
            Rejected(() => Inventory.Add(s, "3", 8), "剩余容量不足");
            Rejected(() => Inventory.Add(s, "3", 1), "请求已使用");
            output.Add("PASS 2: insufficient capacity refuses without writes and consumes request");

            Reset(); s = Inventory.Read(); Inventory.Add(s, "3", 1);
            Rejected(() => Inventory.Add(s, "3", 1), "请求已使用");
            output.Add("PASS 3: second submission after success refuses without a second grant");

            Reset(); s = Inventory.Read(); Mainload.Prop_have[0][1] = "6";
            Rejected(() => Inventory.Add(s, "3", 1), "库存条目内容已变化");
            output.Add("PASS 4: change to another inventory row after reading refuses");

            Reset(); Mainload.Prop_have.Add(new List<string> { "3", "1" });
            Rejected(() => Inventory.Read(), "重复的蔬菜条目");
            output.Add("PASS 5: duplicate target ID is rejected while reading");

            Reset(); s = Inventory.Read(); GameContext.CurrentSlot = "B";
            Rejected(() => Inventory.Add(s, "3", 1), "上下文已换档");
            output.Add("PASS 6: context substitute changing save slot is checked before any writes");

            Reset(); s = Inventory.Read(); Inventory.Read();
            Rejected(() => Inventory.Add(s, "3", 1), "新的刷新替代");
            output.Add("PASS 7: newer read invalidates previous snapshot");
            output.Add("Boundary: real Inventory.cs tested; Mainload, AllText and GameContext are substitutes. No Unity, game methods, persistence, or real save switching tested.");
            return output.ToArray();
        }
    }
}
'@
$source = Get-Content -LiteralPath $SourcePath -Raw -Encoding utf8
Add-Type -TypeDefinition ($source + [Environment]::NewLine + $stubs)
[HouseOfLegacyTrainer.InventoryOfflineChecks]::Run()
