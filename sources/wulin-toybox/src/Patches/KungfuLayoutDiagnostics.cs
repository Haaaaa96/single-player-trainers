// Local addition (2026-09-30): scoped kungfu UI compatibility.
// HaxxToyBox remains licensed under the Apache License 2.0; see LICENSE.txt.
using System.Reflection;
using HaxxToyBox.GUI;
using HarmonyLib;
using TMPro;
using WuLin;

namespace HaxxToyBox.Patches;

internal static class KungfuLayoutDiagnostics
{
    private const string LegacyAssembly = "EnhanceGameplay";
    private const string LegacyType = "EnhanceGameplay.MiscPatch";
    private const string LegacyMethod = "InitLeftPanel_PostPatch";
    private const string ScrollName = "HaxxKungfuScroll";
    private const string ViewportName = "HaxxKungfuViewport";
    private const string ForwardName = "HaxxMoveForward";
    private static readonly Harmony DiagnosticsHarmony = new("HaxxToyBox.KungfuLayoutDiagnostics");
    private static bool _installed;
    private static string _lastError;
    private static long _lastErrorLogAt;

    // Called explicitly from ToyBox.LateInit; deliberately not included in PatchAll.
    public static void Install()
    {
        if (_installed) return;
        try {
            var original = typeof(global::UIKongfuPanel).GetMethod("InitLeftPanel",
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
                null, Type.EmptyTypes, null);
            if (original == null) throw new MissingMethodException("UIKongfuPanel.InitLeftPanel()");

            // Resolve the exact loaded type and signature, never an entire Harmony owner.
            var legacyTypes = AppDomain.CurrentDomain.GetAssemblies()
                .Where(assembly => assembly.GetName().Name == LegacyAssembly)
                .Select(assembly => assembly.GetType(LegacyType, false))
                .Where(type => type != null).ToArray();
            if (legacyTypes.Length > 1) throw new InvalidOperationException("Ambiguous EnhanceGameplay assembly; no patches removed.");
            MethodInfo legacyPostfix = legacyTypes.Length == 1
                ? legacyTypes[0].GetMethod(LegacyMethod,
                    BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.DeclaredOnly,
                    null, new[] { typeof(global::UIKongfuPanel) }, null)
                : null;

            var patches = Harmony.GetPatchInfo(original);
            bool removed = false;
            if (legacyPostfix != null && patches != null && patches.Postfixes.Any(patch => patch.PatchMethod == legacyPostfix)) {
                // Unpatch(original, MethodInfo) is exact-method scoped. Refuse an unexpected
                // registration in another patch category instead of removing that too.
                if (patches.Prefixes.Concat(patches.Transpilers).Concat(patches.Finalizers)
                    .Concat(patches.ILManipulators).Any(patch => patch.PatchMethod == legacyPostfix)) {
                    throw new InvalidOperationException("Legacy method also registered outside postfixes; no patches removed.");
                }
                DiagnosticsHarmony.Unpatch(original, legacyPostfix);
                if (Harmony.GetPatchInfo(original)?.Postfixes.Any(patch => patch.PatchMethod == legacyPostfix) == true)
                    throw new InvalidOperationException("The exact legacy postfix remains registered.");
                removed = true;
                ToyBox.LogMessage("[KungfuLayout] Removed only EnhanceGameplay.MiscPatch.InitLeftPanel_PostPatch(UIKongfuPanel).");
            }

            var diagnostic = typeof(KungfuLayoutDiagnostics).GetMethod(nameof(AfterInitLeftPanel),
                BindingFlags.Static | BindingFlags.NonPublic);
            if (Harmony.GetPatchInfo(original)?.Postfixes.Any(patch => patch.PatchMethod == diagnostic) != true) {
                DiagnosticsHarmony.Patch(original, postfix: new HarmonyMethod(diagnostic) { priority = Priority.Last });
            }
            if (Harmony.GetPatchInfo(original)?.Postfixes.Any(patch => patch.PatchMethod == diagnostic) != true)
                throw new InvalidOperationException("Kungfu compatibility postfix was not registered.");
            _installed = true;
            ToyBox.LogMessage($"[KungfuLayout] Scoped UI compatibility installed; exact legacy postfix {(removed ? "removed" : "not present")}; all other patches retained.");
        }
        catch (Exception exception) {
            LogErrorOnce("Install", exception);
        }
    }

    private static void AfterInitLeftPanel(global::UIKongfuPanel __instance)
    {
        try { ApplyCompatibilityUI(__instance); }
        catch (Exception exception) { LogErrorOnce("Compatibility UI", exception); }
    }

    private static void ApplyCompatibilityUI(global::UIKongfuPanel panel)
    {
        if (panel == null || panel.LearnedSkillPanel == null) return;
        var learned = panel.LearnedSkillPanel;
        var content = learned.GetComponent<RectTransform>();
        var grid = learned.GetComponent<GridLayoutGroup>();
        if (content == null || grid == null || grid.cellSize.x <= 0 || grid.cellSize.y <= 0) return;
        // Current native ClearKongfu (RVA E02BF0) enumerates this exact field's
        // direct children. InitLeftPanel clears its different `content` field.
        // Retain the learned object, its field reference and every native child.
        if (panel.content != null && learned.IsChildOf(panel.content))
            throw new InvalidOperationException("Learned content is inside the native cleared container; wrapping refused.");

        ScrollRect scroll = null;
        if (learned.parent != null && learned.parent.name == ViewportName && learned.parent.parent != null
            && learned.parent.parent.name == ScrollName)
            scroll = learned.parent.parent.GetComponent<ScrollRect>();
        if (scroll == null) {
            var originalParent = learned.parent;
            if (originalParent == null || originalParent.Find(ScrollName) != null)
                throw new InvalidOperationException("Missing parent or unexpected existing kungfu scroll wrapper.");
            int sibling = learned.GetSiblingIndex();
            var scrollObject = new GameObject(ScrollName);
            var outer = scrollObject.AddComponent<RectTransform>();
            outer.SetParent(originalParent, false);
            outer.anchorMin = content.anchorMin;
            outer.anchorMax = content.anchorMax;
            outer.pivot = content.pivot;
            outer.sizeDelta = content.sizeDelta;
            outer.anchoredPosition = content.anchoredPosition;
            outer.localScale = content.localScale;
            outer.localRotation = content.localRotation;
            outer.SetSiblingIndex(sibling);
            scroll = scrollObject.AddComponent<ScrollRect>();
            var viewportObject = new GameObject(ViewportName);
            var viewport = viewportObject.AddComponent<RectTransform>();
            viewport.SetParent(outer, false);
            viewport.anchorMin = Vector2.zero;
            viewport.anchorMax = Vector2.one;
            viewport.offsetMin = Vector2.zero;
            viewport.offsetMax = Vector2.zero;
            viewportObject.AddComponent<RectMask2D>();
            var hitArea = viewportObject.AddComponent<Image>();
            hitArea.color = Color.clear;
            hitArea.raycastTarget = true;
            scroll.viewport = viewport;
            scroll.horizontal = false;
            scroll.vertical = true;
            scroll.movementType = ScrollRect.MovementType.Clamped;
            scroll.scrollSensitivity = 45;
            learned.SetParent(viewport, false);
            content.localScale = Vector3.one;
            content.localRotation = Quaternion.identity;
            content.anchorMin = new Vector2(0, 1);
            content.anchorMax = Vector2.one;
            content.pivot = new Vector2(0.5f, 1);
            content.anchoredPosition = Vector2.zero;
            scroll.content = content;
            ToyBox.LogMessage("[KungfuLayout] Wrapped the original learned content once; native references and children retained.");
        }
        if (scroll.content != content || scroll.viewport == null)
            throw new InvalidOperationException("Kungfu scroll wrapper no longer owns the original content.");

        int activeItems = 0;
        for (int i = 0; i < learned.childCount; i++) {
            var entry = learned.GetChild(i).GetComponent<global::UILearnedSkillPanel>();
            if (entry == null) continue;
            // Native Init hides the reserved tenth slot when no bond skill exists,
            // even when an ordinary overflow skill was bound there earlier.
            if (entry.data != null) entry.gameObject.SetActive(true);
            EnsureForwardButton(panel, entry);
            if (entry.gameObject.activeSelf) activeItems++;
        }
        float viewportWidth = scroll.viewport.rect.width;
        int columns = grid.constraint == GridLayoutGroup.Constraint.FixedColumnCount
            ? Math.Max(1, grid.constraintCount)
            : Math.Max(1, Mathf.FloorToInt((viewportWidth - grid.padding.horizontal + grid.spacing.x)
                / (grid.cellSize.x + grid.spacing.x)));
        grid.constraint = GridLayoutGroup.Constraint.FixedColumnCount;
        grid.constraintCount = columns;
        int rows = (activeItems + columns - 1) / columns;
        float height = grid.padding.vertical + rows * grid.cellSize.y + Math.Max(0, rows - 1) * grid.spacing.y;
        height = Mathf.Max(scroll.viewport.rect.height, height);
        content.sizeDelta = new Vector2(0, height);
        content.anchoredPosition = new Vector2(0, Mathf.Clamp(content.anchoredPosition.y, 0,
            Mathf.Max(0, height - scroll.viewport.rect.height)));
        LayoutRebuilder.ForceRebuildLayoutImmediate(content);
    }

    private static void EnsureForwardButton(global::UIKongfuPanel panel, global::UILearnedSkillPanel entry)
    {
        var existing = entry.transform.Find(ForwardName);
        bool available = panel.chara != null && panel.chara.IsMainCharacter && entry.data != null;
        if (!available) {
            if (existing != null) existing.gameObject.SetActive(false);
            return;
        }
        // Measured native card: 414x99. Keep AddExp at x=50, scale=.3 (right edge 72.5).
        // Both right-hand buttons start at x=78, end at 162, before the type icon at 165.
        var removeRect = entry.RemoveButton?.GetComponent<RectTransform>();
        if (removeRect != null) {
            removeRect.anchoredPosition = new Vector2(120, 25);
            removeRect.sizeDelta = new Vector2(84, 38);
        }
        Button button;
        if (existing == null) {
            var buttonObject = new GameObject(ForwardName);
            var rect = buttonObject.AddComponent<RectTransform>();
            rect.SetParent(entry.transform, false);
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = new Vector2(120, -22);
            rect.sizeDelta = new Vector2(84, 32);
            var image = buttonObject.AddComponent<Image>();
            image.color = new Color(0.20f, 0.29f, 0.40f, 0.95f);
            button = buttonObject.AddComponent<Button>();
            button.targetGraphic = image;
            var labelObject = new GameObject("Label");
            var label = labelObject.AddComponent<TextMeshProUGUI>();
            var labelRect = labelObject.GetComponent<RectTransform>();
            labelRect.SetParent(rect, false);
            labelRect.anchorMin = Vector2.zero;
            labelRect.anchorMax = Vector2.one;
            labelRect.offsetMin = labelRect.offsetMax = Vector2.zero;
            label.text = "前置";
            label.alignment = TextAlignmentOptions.Center;
            label.raycastTarget = false;
            label.color = Color.white;
        }
        else button = existing.GetComponent<Button>();
        if (button == null) return;
        try { StyleForwardLabel(button.GetComponentInChildren<TextMeshProUGUI>(true), entry); }
        catch (Exception exception) { LogErrorOnce("Forward label style", exception); }
        button.gameObject.SetActive(true);
        // Native overflow rows can clone an earlier row. Rebind only our own button
        // to its current entry, never copy scripts or touch native button listeners.
        button.onClick.RemoveAllListeners();
        button.onClick.AddListener(() => MoveToFront(panel, entry));
    }

    private static void StyleForwardLabel(TextMeshProUGUI label, global::UILearnedSkillPanel entry)
    {
        if (label == null) return;
        var font = UiPolish.CjkFont;
        if (font == null && entry.Name != null) font = entry.Name.font;
        if (font != null && label.font != font) label.font = font;
        label.fontSize = 25;
        label.fontSizeMin = label.fontSizeMax = 25;
        label.enableAutoSizing = false;
        label.fontStyle = FontStyles.Normal;
        label.fontWeight = FontWeight.Regular;
        label.outlineWidth = 0;
        // TMP's fontMaterial accessor gives this label an instance. Never mutate
        // font.material or fontSharedMaterial from the native game/font asset.
        var material = label.fontMaterial;
        if (material == null) return;
        if (material.HasProperty("_FaceDilate")) material.SetFloat("_FaceDilate", 0);
        if (material.HasProperty("_OutlineWidth")) material.SetFloat("_OutlineWidth", 0);
        material.DisableKeyword("OUTLINE_ON");
        material.DisableKeyword("UNDERLAY_ON");
        material.DisableKeyword("UNDERLAY_INNER");
    }

    private static void MoveToFront(global::UIKongfuPanel panel, global::UILearnedSkillPanel entry)
    {
        bool changed = false;
        try {
            if (panel == null || entry == null || !entry.gameObject.activeInHierarchy || panel.chara == null
                || !panel.chara.IsMainCharacter || panel.LearnedSkillPanel == null
                || entry.transform.parent != panel.LearnedSkillPanel) return;
            var player = PlayerTeamManager.HasInstance ? PlayerTeamManager.Instance.PlayerDataInstance : null;
            var skill = entry.data;
            if (player == null || player.Pointer != panel.chara.Pointer || skill == null
                || skill.GameCharacterInstance == null || skill.GameCharacterInstance.Pointer != player.Pointer) return;
            var skills = player.KungfuInstances;
            int index = -1;
            for (int i = 0; i < skills.Count; i++) {
                if (skills[i] != null && skills[i].Pointer == skill.Pointer) { index = i; break; }
            }
            if (index <= 0) return;
            skills.RemoveAt(index);
            skills.Insert(0, skill);
            changed = true;
            // The current native InitLeftPanel already calls ClearKongfu itself.
            panel.InitLeftPanel();
            ToyBox.LogMessage("[KungfuLayout] Main-character kungfu moved to front; native panel refreshed.");
        }
        catch (Exception exception) {
            LogErrorOnce(changed ? "Order changed; UI refresh failed (not retried)" : "Move to front", exception);
        }
    }

    private static void LogErrorOnce(string stage, Exception exception)
    {
        string error = stage + ": " + exception.GetType().Name + ": " + exception.Message;
        if (error == _lastError) return;
        long now = Environment.TickCount64;
        if (_lastError != null && now - _lastErrorLogAt < 2000) return;
        _lastError = error;
        _lastErrorLogAt = now;
        ToyBox.LogWarning("[KungfuLayout] " + error);
    }
}
