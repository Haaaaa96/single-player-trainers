using System;
using HaxxToyBox.GUI;

// Pure managed checks: no Unity objects, game assemblies or inventory writes.
public static class SearchTextChecks
{
    public static string Run()
    {
        Check(SearchText.Normalize(null) == "", "null query");
        Check(SearchText.Normalize(" \t\u3000") == "", "blank query restores category");
        Check(SearchText.Normalize(" <color=#ff0000><b>金疮药</b></color> ") == "金疮药", "strip nested rich text");
        Check(SearchText.Matches("金疮药", 102345, " 疮药 "), "trimmed Chinese substring");
        Check(SearchText.Matches("Healing Pill", 102345, "pILL"), "case insensitive name");
        Check(SearchText.Matches("金疮药", 102345, "234"), "partial numeric ID");
        Check(SearchText.Matches("<b>剑法</b>", 7, "剑"), "rich text display name");
        Check(!SearchText.Matches("<color=orange>剑法</color>", 7, "orange"), "do not search formatting tags");
        Check(!SearchText.Matches("金疮药", 102345, "不存在"), "zero matching results");
        Check(SearchText.Matches(null, 102345, "234"), "ID works without a name");
        Check(SearchText.Matches("任意物品", 7, "\u3000"), "blank matches every candidate");
        Check(!SearchText.Matches("金疮药", 102345, "102346"), "ID mismatch");
        return "PASS: 12 pure search boundary checks; no game code executed.";
    }

    private static void Check(bool condition, string name)
    {
        if (!condition) throw new InvalidOperationException("Search check failed: " + name);
    }
}
