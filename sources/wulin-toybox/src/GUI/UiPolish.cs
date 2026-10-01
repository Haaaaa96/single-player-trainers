// Modified 2026-09-30: readable system CJK font and Chinese labels for the HaxxToyBox UI.
using TMPro;
using UnityEngine.TextCore.LowLevel;

namespace HaxxToyBox.GUI;

internal static class UiPolish
{
    private static TMP_FontAsset _font;
    private static bool _fontAttempted;
    // Reuse the already-created font for our own additional labels only.
    public static TMP_FontAsset CjkFont => _font;
    private static readonly Dictionary<string, string> Labels = new()
    {
        ["Roles"] = "队伍成员", ["Role"] = "人物", ["Profile"] = "人物属性 · 基础值 · 百分比填 0–1 · 回车提交",
        ["Item"] = "物品", ["Items"] = "物品", ["Martial"] = "武学", ["Martials"] = "武学",
        ["Misc"] = "辅助", ["Traits"] = "天赋", ["Trait"] = "天赋", ["Enter text ..."] = "输入名称或编号",
        ["Rank"] = "品级", ["Name"] = "名称", ["Description"] = "说明", ["Describtion"] = "说明", ["Add"] = "添加",
        ["Enter text..."] = "输入名称或编号", ["消耗\n品"] = "消耗品"
    };

    public static void Apply(GameObject canvas)
    {
        if (canvas == null) return;
        if (!_fontAttempted)
        {
            _fontAttempted = true;
            TryCreateFont(canvas);
        }
        foreach (var label in canvas.GetComponentsInChildren<TMP_Text>(true))
        {
            string originalText = (label.text ?? "").Trim();
            bool profileHeader = originalText == "Profile" || originalText == Labels["Profile"];
            if (_font != null) label.font = _font;
            if (Labels.TryGetValue(originalText, out var translated)) label.text = translated;
            if (profileHeader)
            {
                ExpandProfileHeader(label);
                label.fontSize = 46;
                label.fontSizeMin = 46;
                label.fontSizeMax = 46;
                label.enableAutoSizing = false;
            }
            else if (_font != null)
            {
                // Preserve deliberately larger labels. A failed font replacement must
                // leave the original labels' font sizes and auto-size settings alone.
                // The supplied canvas renders at about 0.625 scale: 38 is ~24 screen pixels.
                label.fontSize = Mathf.Max(label.fontSize, 38);
                label.fontSizeMin = 30;
                label.fontSizeMax = label.fontSize;
                label.enableAutoSizing = true;
            }
            label.raycastTarget = false;
        }
        foreach (var input in canvas.GetComponentsInChildren<TMP_InputField>(true))
        {
            try
            {
                if (input == null) continue;
                // Avoid the TMP_InputField.fontAsset setter that fails for this
                // asset. Update the actual text components directly instead.
                if (_font != null)
                {
                    var text = input.textComponent;
                    if (text != null) text.font = _font;
                    var placeholder = input.placeholder;
                    if (placeholder != null)
                    {
                        var placeholderText = placeholder.GetComponent<TMP_Text>();
                        if (placeholderText != null) placeholderText.font = _font;
                    }
                }
                input.customCaretColor = true;
                input.caretColor = new Color(0.45f, 0.85f, 1f, 1f);
                input.selectionColor = new Color(0.2f, 0.55f, 0.8f, 0.5f);
            }
            catch (Exception ex)
            {
                ToyBox.LogWarning("UI input font/style skipped for one field: " + ex.Message);
            }
        }
    }

    public static void AddVersionLabel(GameObject canvas)
    {
        if (canvas == null || canvas.transform.Find("HaxxVersion") != null) return;
        var labelObject = new GameObject("HaxxVersion");
        labelObject.transform.SetParent(canvas.transform, false);
        var label = labelObject.AddComponent<TextMeshProUGUI>();
        var fallback = canvas.GetComponentInChildren<TMP_Text>(true);
        label.font = _font ?? fallback?.font;
        label.text = "HaxxToyBox v" + MyPluginInfo.PLUGIN_VERSION;
        label.fontSize = 27;
        label.enableWordWrapping = false;
        label.raycastTarget = false;
        label.color = new Color(0.85f, 0.9f, 0.95f, 1f);
        var rect = label.rectTransform;
        rect.anchorMin = rect.anchorMax = rect.pivot = Vector2.zero;
        rect.anchoredPosition = new Vector2(24, 18);
        rect.sizeDelta = new Vector2(560, 44);
    }

    private static void TryCreateFont(GameObject canvas)
    {
        string stage = "resolve-sdf-shader";
        Font sourceFont = null;
        TMP_FontAsset candidate = null;
        Shader borrowedShader = null;
        bool restoreShaderCache = false;
        try
        {
            ToyBox.LogMessage("UI font stage: " + stage);
            if (ShaderUtilities.k_ShaderRef_MobileSDF == null)
            {
                // Stripped shader names can make TMP's dynamic-font factory fail.
                // Borrow a loaded SDF shader; never edit an existing font/material.
                borrowedShader = Shader.Find("TextMeshPro/Mobile/Distance Field");
                if (borrowedShader == null)
                {
                    foreach (var label in canvas.GetComponentsInChildren<TMP_Text>(true))
                    {
                        var originalFont = label.font;
                        var material = originalFont == null ? null : originalFont.material;
                        if (material == null || material.shader == null ||
                            !material.HasProperty("_GradientScale") || !material.HasProperty("_MainTex")) continue;
                        borrowedShader = material.shader;
                        break;
                    }
                }
                if (borrowedShader == null) throw new InvalidOperationException("No loaded TMP SDF shader is available.");
                ShaderUtilities.k_ShaderRef_MobileSDF = borrowedShader;
                restoreShaderCache = true;
                ToyBox.LogMessage("UI font borrowed SDF shader: " + borrowedShader.name);
            }

            stage = "create-os-font";
            ToyBox.LogMessage("UI font stage: " + stage);
            sourceFont = Font.CreateDynamicFontFromOSFont(new[] { "Microsoft YaHei", "Microsoft YaHei UI", "SimHei" }, 32);
            if (sourceFont == null) throw new InvalidOperationException("The operating system font factory returned null.");
            ToyBox.LogMessage("UI font OS font ready: " + sourceFont.name);

            stage = "install-font-file-route";
            ToyBox.LogMessage("UI font stage: " + stage);
            CjkFontFaceLoader.Install(sourceFont);

            stage = "create-tmp-font-asset";
            ToyBox.LogMessage("UI font stage: " + stage);
            candidate = TMP_FontAsset.CreateFontAsset(sourceFont, 64, 8, GlyphRenderMode.SDFAA, 2048, 2048, AtlasPopulationMode.Dynamic, true);
            if (candidate == null) throw new InvalidOperationException("TMP's font asset factory returned null.");

            stage = "validate-tmp-material";
            ToyBox.LogMessage("UI font stage: " + stage);
            if (candidate.material == null || candidate.material.shader == null)
                throw new InvalidOperationException("The new TMP font has no valid material shader.");

            stage = "preserve-font-assets";
            ToyBox.LogMessage("UI font stage: " + stage);
            UnityEngine.Object.DontDestroyOnLoad(sourceFont);
            UnityEngine.Object.DontDestroyOnLoad(candidate);
            _font = candidate;
            ToyBox.LogMessage("UI CJK dynamic font ready: " + sourceFont.name + "; shader=" + candidate.material.shader.name);
        }
        catch (Exception ex)
        {
            _font = null;
            ToyBox.LogWarning($"UI font fallback at {stage}: {ex}");
            try { CjkFontFaceLoader.Unload(); }
            catch (Exception cleanupError) { ToyBox.LogWarning("UI font-face route removal failed: " + cleanupError.Message); }
            // Only these newly created assets belong to this attempt.
            if (candidate != null) UnityEngine.Object.Destroy(candidate);
            if (sourceFont != null) UnityEngine.Object.Destroy(sourceFont);
        }
        finally
        {
            // The created material keeps its shader reference. Leave TMP's global
            // cache as it was, and do not replace a cache changed by someone else.
            if (restoreShaderCache)
            {
                try
                {
                    if (ShaderUtilities.k_ShaderRef_MobileSDF == borrowedShader)
                        ShaderUtilities.k_ShaderRef_MobileSDF = null;
                }
                catch (Exception ex) { ToyBox.LogWarning("UI font shader-cache restore failed: " + ex.Message); }
            }
        }
    }

    // The owner must dispose the ToyBox UI before calling this on plugin unload.
    public static void Unload()
    {
        CjkFontFaceLoader.Unload();
    }

    private static void ExpandProfileHeader(TMP_Text label)
    {
        var rect = label.rectTransform;
        var parent = rect.parent == null ? null : rect.parent.GetComponent<RectTransform>();
        if (parent == null) return;
        var offsetMin = rect.offsetMin;
        var offsetMax = rect.offsetMax;
        rect.anchorMin = new Vector2(0, rect.anchorMin.y);
        rect.anchorMax = new Vector2(1, rect.anchorMax.y);
        rect.offsetMin = new Vector2(20, offsetMin.y);
        rect.offsetMax = new Vector2(-20, offsetMax.y);
        label.enableWordWrapping = false;
    }
}
