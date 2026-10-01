using System.Reflection;
using HarmonyLib;
using UnityEngine.TextCore.LowLevel;

namespace HaxxToyBox.GUI;

// Route only the ToyBox-owned runtime Font. No game or other mod font is replaced.
internal static class CjkFontFaceLoader
{
    private static readonly Harmony Harmony = new(MyPluginInfo.PLUGIN_GUID + ".CjkFontFace");
    private static readonly MethodInfo Target = AccessTools.Method(typeof(FontEngine), "LoadFontFace", new[] { typeof(Font), typeof(int) });
    private static readonly MethodInfo Prefix = AccessTools.Method(typeof(CjkFontFaceLoader), nameof(LoadFontFacePrefix));
    private static Font _sourceFont;
    private static IntPtr _sourcePointer;
    private static string _fontPath;
    private static bool _installed;
    private static long _loadCount;
    private static FontEngineError? _lastResult;
    private static string _lastException;

    public static void Install(Font sourceFont)
    {
        if (sourceFont == null || sourceFont.Pointer == IntPtr.Zero)
            throw new ArgumentException("A live ToyBox-owned source font is required.", nameof(sourceFont));
        if (_installed)
        {
            if (_sourceFont != null && _sourcePointer == sourceFont.Pointer) return;
            throw new InvalidOperationException("The font-face route already belongs to another ToyBox font.");
        }
        if (Target == null || Prefix == null)
            throw new MissingMethodException("FontEngine.LoadFontFace(Font, int) is unavailable.");

        var fontDirectory = Environment.GetFolderPath(Environment.SpecialFolder.Fonts);
        if (string.IsNullOrWhiteSpace(fontDirectory))
            throw new DirectoryNotFoundException("The Windows Fonts directory is unavailable.");
        string fontPath = Path.Combine(fontDirectory, "msyh.ttc");
        if (!File.Exists(fontPath)) throw new FileNotFoundException("The installed Microsoft YaHei font file is unavailable.", fontPath);

        _sourceFont = sourceFont;
        _sourcePointer = sourceFont.Pointer;
        _fontPath = fontPath;
        _loadCount = 0;
        _lastResult = null;
        _lastException = null;
        try
        {
            Harmony.Patch(Target, prefix: new HarmonyMethod(Prefix));
            _installed = true;
            ToyBox.LogMessage($"UI font-face route installed: file={fontPath}; source=0x{_sourcePointer.ToInt64():X}; faceIndex=0.");
        }
        catch
        {
            Unload();
            throw;
        }
    }

    // Keep this prefix installed after successful creation: TMP reloads the source
    // face when new Chinese characters are added to a dynamic atlas.
    private static bool LoadFontFacePrefix(Font __0, int __1, ref FontEngineError __result)
    {
        if (_sourceFont == null || __0 == null || _sourcePointer == IntPtr.Zero ||
            __0.Pointer != _sourcePointer || _sourceFont.Pointer != _sourcePointer) return true;

        long call = System.Threading.Interlocked.Increment(ref _loadCount);
        try
        {
            __result = FontEngine.LoadFontFace(_fontPath, __1, 0);
            if (call <= 2 || __result != _lastResult)
                ToyBox.LogMessage($"UI font-face file load #{call}: size={__1}; result={__result} ({(int)__result}).");
            _lastResult = __result;
        }
        catch (Exception ex)
        {
            __result = FontEngineError.Invalid_File;
            string error = ex.GetType().Name + ": " + ex.Message;
            if (error != _lastException) ToyBox.LogWarning("UI font-face file load failed: " + error);
            _lastException = error;
            _lastResult = __result;
        }
        return false;
    }

    // Called on creation failure, or by the plugin owner after disposing its UI.
    // Never unload FontEngine globally: its other faces belong to the game.
    public static void Unload()
    {
        _sourcePointer = IntPtr.Zero;
        _sourceFont = null;
        _fontPath = null;
        try
        {
            if (Target != null && Prefix != null) Harmony.Unpatch(Target, Prefix);
            if (_installed) ToyBox.LogMessage($"UI font-face route removed after {_loadCount} matching loads.");
        }
        finally
        {
            _installed = false;
        }
    }
}
