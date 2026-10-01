using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using HarmonyLib;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;

namespace HouseOfLegacyTrainer
{
    // Own only our time-scale and EventSystem changes. Never toggle the game's exit menu,
    // play/pause, speed or one-day request flags. Game input calls are redirected locally
    // in Assembly-CSharp, leaving Unity IMGUI and the trainer's input untouched.
    internal static class Interaction
    {
        internal static bool Active { get; private set; }
        internal static bool Ready { get; private set; }
        internal static long Lease { get; private set; }
        internal static KeyCode ToggleKey = KeyCode.Tab;
        internal static string Failure;
        private static bool releasing;
        private static int scene, releaseFrame;
        private static float previousScale;
        private static Vector3 frozenMouse;
        private static Harmony harmony;
        private static readonly List<EventSystem> systems = new List<EventSystem>();
        private static readonly Dictionary<MethodInfo, MethodInfo> redirects = new Dictionary<MethodInfo, MethodInfo>();
        private const string PatchId = "local.houseoflegacy.trainer.interaction";

        internal static bool Gate { get { return Active || releasing || (Ready && (Input.GetKey(ToggleKey) || Input.GetKeyDown(ToggleKey) || Input.GetKeyUp(ToggleKey))); } }
        internal static string State { get { return "lease=" + Lease + " active=" + Active + " release=" + releasing + " scale=" + Time.timeScale + " prior=" + previousScale + " systems=" + systems.Count; } }

        internal static string Initialize()
        {
            try {
                Add("GetKey", typeof(KeyCode), "ReadKey"); Add("GetKeyDown", typeof(KeyCode), "ReadKeyDown");
                Add("GetKeyUp", typeof(KeyCode), "ReadKeyUp"); Add("GetAxis", typeof(string), "ReadAxis");
                Add("get_anyKeyDown", null, "ReadAnyKeyDown"); Add("get_mousePosition", null, "ReadMousePosition");
                var assembly = typeof(Mainload).Assembly;
                var targets = new HashSet<MethodBase>();
                // Scan the actual assembly's input sites, rather than depending on fixed tokens
                // from a particular build. Unsupported APIs fail the input gate before editing.
                using (var metadata = Mono.Cecil.AssemblyDefinition.ReadAssembly(assembly.Location)) {
                    if (metadata.MainModule.Mvid != assembly.ManifestModule.ModuleVersionId)
                        throw new InvalidOperationException("运行程序集与输入元数据身份不一致。");
                    foreach (var type in AllTypes(metadata.MainModule.Types))
                        foreach (var method in type.Methods) {
                            if (!method.HasBody) continue;
                            foreach (var instruction in method.Body.Instructions) {
                                var call = instruction.Operand as Mono.Cecil.MethodReference;
                                if (call == null || call.DeclaringType.FullName != "UnityEngine.Input") continue;
                                var match = redirects.Keys.Any(x => x.Name == call.Name &&
                                    x.ReturnType.FullName == call.ReturnType.FullName &&
                                    x.GetParameters().Select(p => p.ParameterType.FullName).SequenceEqual(call.Parameters.Select(p => p.ParameterType.FullName)));
                                if (!match) throw new InvalidOperationException("尚未支持的游戏输入入口：" + call.FullName);
                                targets.Add(assembly.ManifestModule.ResolveMethod(method.MetadataToken.ToInt32()));
                            }
                        }
                }
                if (targets.Count == 0) throw new InvalidOperationException("未找到可验证的游戏输入入口。");
                harmony = new Harmony(PatchId);
                var transpiler = new HarmonyMethod(typeof(Interaction).GetMethod("Redirect", BindingFlags.Static | BindingFlags.NonPublic));
                foreach (var target in targets) harmony.Patch(target, transpiler: transpiler);
                // FixedUpdate includes other state/history work besides UpdateTime.
                var clock = AccessTools.Method(typeof(MainUpdate), "FixedUpdate", Type.EmptyTypes);
                if (clock == null || clock.ReturnType != typeof(void)) throw new InvalidOperationException("游戏主更新入口不匹配。");
                harmony.Patch(clock, prefix: new HarmonyMethod(typeof(Interaction).GetMethod("AllowSimulation", BindingFlags.Static | BindingFlags.NonPublic)));
                Ready = true;
                return "inputMethods=" + targets.Count + " clock=MainUpdate.FixedUpdate";
            } catch (Exception e) {
                Ready = false; Failure = "暂停/输入保护初始化失败：" + e.Message;
                if (harmony != null) harmony.UnpatchSelf();
                return Failure;
            }
        }

        private static IEnumerable<Mono.Cecil.TypeDefinition> AllTypes(IEnumerable<Mono.Cecil.TypeDefinition> types)
        { foreach (var type in types) { yield return type; foreach (var nested in AllTypes(type.NestedTypes)) yield return nested; } }
        private static void Add(string original, Type parameter, string replacement)
        {
            var from = typeof(Input).GetMethod(original, BindingFlags.Static | BindingFlags.Public, null,
                parameter == null ? Type.EmptyTypes : new[] { parameter }, null);
            var to = typeof(Interaction).GetMethod(replacement, BindingFlags.Static | BindingFlags.Public);
            if (from == null || to == null) throw new InvalidOperationException("输入方法签名不可用：" + original);
            redirects.Add(from, to);
        }
        private static IEnumerable<CodeInstruction> Redirect(IEnumerable<CodeInstruction> instructions)
        {
            foreach (var instruction in instructions) {
                var method = instruction.operand as MethodInfo;
                MethodInfo replacement;
                if (method != null && redirects.TryGetValue(method, out replacement)) instruction.operand = replacement;
                yield return instruction;
            }
        }
        private static bool AllowSimulation() { return !Active; }
        public static bool ReadKey(KeyCode key) { return !Gate && Input.GetKey(key); }
        public static bool ReadKeyDown(KeyCode key) { return !Gate && Input.GetKeyDown(key); }
        public static bool ReadKeyUp(KeyCode key) { return !Gate && Input.GetKeyUp(key); }
        public static bool ReadAnyKeyDown() { return !Gate && Input.anyKeyDown; }
        public static float ReadAxis(string name) { return Gate ? 0f : Input.GetAxis(name); }
        public static Vector3 ReadMousePosition() { return Active || releasing ? frozenMouse : Input.mousePosition; }

        internal static void Begin()
        {
            GameContext.RequireThread();
            if (!Ready) throw new InvalidOperationException(Failure ?? "输入保护尚未就绪。");
            if (Active || releasing) throw new InvalidOperationException("请松开按键后再打开。");
            GameContext.RequireStablePage();
            float scale = Time.timeScale;
            if (float.IsNaN(scale) || float.IsInfinity(scale) || scale < 0) throw new InvalidOperationException("无法确认游戏时间状态。");
            previousScale = scale; scene = SceneManager.GetActiveScene().handle; frozenMouse = Input.mousePosition;
            Lease++; Active = true;
            try { Time.timeScale = 0; BlockSystems(); Require(); }
            catch { End(true); throw; }
        }
        internal static void Tick()
        {
            if (Active) BlockSystems();
            // Keep UI blocked through the release frame so the close key/click cannot reach it.
            if (releasing && Time.frameCount > releaseFrame + 1 && !Input.anyKey) RestoreSystems();
        }
        private static void BlockSystems()
        {
            foreach (var system in UnityEngine.Object.FindObjectsOfType<EventSystem>())
                if (system.enabled) { if (!systems.Contains(system)) systems.Add(system); system.enabled = false; }
        }
        internal static void Require()
        {
            GameContext.RequireThread();
            if (!Ready || !Active || releasing || scene != SceneManager.GetActiveScene().handle || Time.timeScale != 0 ||
                UnityEngine.Object.FindObjectsOfType<EventSystem>().Any(x => x.enabled))
                throw new InvalidOperationException("工具未持有稳定的暂停与输入保护，请关窗后重新打开。");
            GameContext.RequireStablePage();
        }
        internal static void End(bool immediate = false)
        {
            if (Active) {
                Active = false; Lease++;
                // A different writer changing timeScale supersedes our ownership.
                if (Time.timeScale == 0) Time.timeScale = previousScale;
            }
            if (systems.Count > 0) { releasing = true; releaseFrame = Time.frameCount; }
            if (immediate) RestoreSystems();
        }
        private static void RestoreSystems()
        {
            foreach (var system in systems) if (system != null) system.enabled = true;
            systems.Clear(); releasing = false;
        }
        internal static void Shutdown()
        { End(true); Ready = false; if (harmony != null) harmony.UnpatchSelf(); }
    }
}
