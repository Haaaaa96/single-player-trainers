// Local changes (2026-09-30): pure text matching for the item search.
// HaxxToyBox remains licensed under the Apache License 2.0; see LICENSE.txt.
using System;
using System.Globalization;
using System.Text.RegularExpressions;

namespace HaxxToyBox.GUI;

internal static class SearchText
{
    private static readonly Regex RichTextTag = new Regex("<[^>]*>");

    public static string Normalize(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return string.Empty;
        return (text.IndexOf('<') >= 0 ? RichTextTag.Replace(text, string.Empty) : text).Trim();
    }

    public static bool Matches(string name, int id, string query)
    {
        query = Normalize(query);
        return query.Length == 0
            || Normalize(name).IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0
            || id.ToString(CultureInfo.InvariantCulture).IndexOf(query, StringComparison.OrdinalIgnoreCase) >= 0;
    }
}
