using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Threading;
using BepInEx;
using BepInEx.Configuration;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;

namespace HouseOfLegacyTrainer
{
    [BepInPlugin("local.houseoflegacy.trainer", "HouseOfLegacyTrainer", Version)]
    [DefaultExecutionOrder(-32000)]
    public sealed class Plugin : BaseUnityPlugin
    {
        public const string Version = "0.3.0";
        private static Plugin owner;
        private readonly string session = Guid.NewGuid().ToString("N");
        private Rect window = new Rect(12, 55, 590, 720);
        private bool visible, keyHeld, guiKeyHeld, pressLatched;
        private bool focused = true, waitForRelease;
        private int lastToggleFrame = -1;
        private int tab, scene;
        private long requests;
        private GUISkin skin;
        private Font font;
        private Texture2D background;
        private Vector2 scroll, memberScroll;
        private ConfigEntry<KeyCode> hotkey;
        private string status = "正常游戏或人物页直接按 Tab。开窗自动暂停，关窗恢复原状态。";
        private string amount = "10000", reputation = "1", traitPoints = "10", memberTarget = "50", itemAmount = "1";
        private Family.Snapshot family;
        private Traits.Snapshot traits;
        private Members.Snapshot member;
        private Inventory.Snapshot inventory;
        private List<Members.Entry> memberList = new List<Members.Entry>();
        private int field;

        private void Awake()
        {
            if (owner != null) { Logger.LogError("Duplicate trainer rejected"); enabled = false; return; }
            owner = this;
            GameContext.MainThread = Thread.CurrentThread.ManagedThreadId;
            hotkey = Config.Bind("Window", "ToggleKey", KeyCode.Tab, "显示或隐藏修改器；打开时自动暂停，关闭恢复。改键后重启游戏。");
            var keySchema = Config.Bind("Window", "HotkeySchema", 0, "旧版默认F8向Tab的一次性迁移标记。");
            if (keySchema.Value < 1) { if (hotkey.Value == KeyCode.F8) hotkey.Value = KeyCode.Tab; keySchema.Value = 1; Config.Save(); }
            Interaction.ToggleKey = hotkey.Value;
            keyHeld = Input.GetKey(hotkey.Value);
            font = Font.CreateDynamicFontFromOSFont("Microsoft YaHei", 20);
            scene = SceneManager.GetActiveScene().handle;
            Logger.LogInfo("HOL_START version=" + Version + " session=" + session + " pid=" + System.Diagnostics.Process.GetCurrentProcess().Id);
            Logger.LogInfo("HOL_INTERACTION " + Interaction.Initialize() + " key=" + hotkey.Value);
            SceneManager.activeSceneChanged += SceneChanged;
        }

        private void Update()
        {
            if (owner != this) return;
            Interaction.Tick();
            bool held = Input.GetKey(hotkey.Value) || Input.GetKeyDown(hotkey.Value);
            if (!focused || waitForRelease) {
                keyHeld = held;
                if (focused && !held && !guiKeyHeld && !Input.anyKey) {
                    waitForRelease = false; pressLatched = false;
                }
                return;
            }
            bool rising = held && !keyHeld;
            keyHeld = held;
            if (rising) ToggleOnce();
            if (!keyHeld && !guiKeyHeld) pressLatched = false;
            if (visible) {
                try { Interaction.Require(); }
                catch (Exception e) { Logger.LogWarning("HOL_AUTO_CLOSE " + e.Message); SetVisible(false); }
            }
        }
        private void ToggleOnce()
        {
            if (!focused || waitForRelease || pressLatched || lastToggleFrame == Time.frameCount) return;
            pressLatched = true; lastToggleFrame = Time.frameCount;
            SetVisible(!visible);
        }
        private void OnApplicationFocus(bool focused)
        {
            if (owner != this) return;
            this.focused = focused; waitForRelease = true;
            keyHeld = guiKeyHeld = pressLatched = false;
            if (!focused && visible) SetVisible(false);
        }
        private void SceneChanged(Scene oldScene, Scene newScene) { SetVisible(false); scene = newScene.handle; Clear(); }
        private void SetVisible(bool show)
        {
            Clear();
            if (show) {
                try {
                    Interaction.Begin(); visible = true;
                    if (UnityEngine.Object.FindObjectsOfType<InitGameUI>().Any(x => x.isActiveAndEnabled)) tab = 2;
                    else if (MemberPanel.CurrentIndex() >= 0) tab = 1;
                    Refresh();
                } catch (Exception e) { visible = false; Interaction.End(); status = e.Message; Logger.LogWarning("HOL_OPEN_REFUSED " + e.Message); }
            } else { visible = false; Interaction.End(); }
            Logger.LogInfo("HOL_WINDOW visible=" + visible + " session=" + session + " " + Interaction.State +
                " slot=" + Mainload.CunDangIndex_now + " menu=" + Mainload.isGamePausePanelOpen + " date=" + (Mainload.Time_now == null ? "none" : string.Join("/", Mainload.Time_now)));
        }
        private void Clear()
        {
            family = null; member = null; traits = null; inventory = null;
            memberList.Clear();
            GameContext.Epoch++;
        }
        private void Run(string operation, Func<string> action, bool writes = false)
        {
            long request = ++requests;
            if (writes) Logger.LogInfo("HOL_REQUEST " + request + " " + operation + " session=" + session);
            try { status = action(); Logger.LogInfo("HOL_OK " + request + " " + operation + " " + status.Replace('\n', ' ')); }
            catch (Exception e) { Clear(); status = e.Message; Logger.LogWarning("HOL_REFUSED_OR_FAILED " + request + " " + operation + " " + e); }
        }
        private void Refresh()
        {
            var previousId = member == null ? null : member.Id;
            Clear();
            Run("read_tab_" + tab, () => {
                if (tab == 0) { family = Family.Read(); return "家族数据已刷新。"; }
                if (tab == 1) {
                    memberList = Members.List();
                    var entry = memberList.FirstOrDefault(x => x.Id == previousId) ?? memberList.FirstOrDefault(x => x.Index == MemberPanel.CurrentIndex()) ?? memberList.FirstOrDefault();
                    if (entry != null) SelectMember(entry);
                    return "本族成员已刷新，共 " + memberList.Count + " 人。";
                }
                if (tab == 2) { GameContext.RequireThread(); traits = Traits.Read(); return "当前角色创建点数已读取。"; }
                if (tab == 3) { inventory = Inventory.Read(); return "仓库数据已刷新。"; }
                return "游戏版本 " + Mainload.VersionID + "；修改器 " + Version;
            });
        }
        private void SelectMember(Members.Entry entry)
        {
            member = null;
            var read = Members.Read(entry.Index);
            if (read.Id != entry.Id) throw new InvalidOperationException("族人列表已变化，请重新刷新。");
            member = read;
            memberTarget = member.Values[Members.FieldKeys[field]];
        }
        private static int Integer(string text)
        {
            int value;
            if (!int.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out value))
                throw new InvalidOperationException("请输入有效整数。");
            return value;
        }

        private void OnGUI()
        {
            if (owner != this) return;
            var inputEvent = Event.current;
            // IMGUI text editing can consume the raw key state. Both paths share one
            // press latch; GUI repeat KeyDown events cannot toggle until KeyUp.
            if (inputEvent.isKey && inputEvent.keyCode == hotkey.Value) {
                if (inputEvent.type == EventType.KeyDown) {
                    if (!guiKeyHeld) { guiKeyHeld = true; ToggleOnce(); }
                } else if (inputEvent.type == EventType.KeyUp) {
                    guiKeyHeld = false;
                    if (!keyHeld) pressLatched = false;
                }
                inputEvent.Use();
            }
            if (!visible) return;
            var oldSkin = GUI.skin;
            if (skin == null)
            {
                skin = Instantiate(oldSkin); skin.font = font;
                foreach (var style in new[] { skin.label, skin.button, skin.textField, skin.window, skin.toggle, skin.box })
                    style.fontSize = 18;
                skin.label.wordWrap = true;
                skin.button.padding = new RectOffset(10,10,8,8);
                skin.textField.padding = new RectOffset(8,8,8,8);
                background = new Texture2D(1,1); background.SetPixel(0,0,new Color(0.10f,0.12f,0.15f,1)); background.Apply();
                skin.window.normal.background = background; skin.window.onNormal.background = background;
                skin.window.padding = new RectOffset(18,18,40,18);
            }
            try {
                GUI.skin = skin;
                window.width = Mathf.Min(590, Screen.width - 24);
                window.height = Mathf.Min(800, Screen.height - 45);
                window.x = Mathf.Clamp(window.x, 0, Screen.width - window.width);
                window.y = Mathf.Clamp(window.y, 0, Screen.height - window.height);
                window = GUI.Window(25037701, window, Draw, "吾今有世家 · 自用修改器 " + Version);
            } finally { GUI.skin = oldSkin; }
        }
        private void Draw(int id)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label(hotkey.Value + " 开关 · 自动暂停 · 可拖动标题栏\n关闭恢复原状态；修改后按游戏原菜单保存");
            if (GUILayout.Button("关闭", GUILayout.Width(80))) SetVisible(false);
            GUILayout.EndHorizontal();
            int nextTab = GUILayout.Toolbar(tab, new[] { "家族", "族人", "开局特质", "仓库", "说明" }, GUILayout.Height(40));
            if (nextTab != tab) { tab = nextTab; scroll = Vector2.zero; Refresh(); }
            GUILayout.Space(8);
            GUILayout.Label(status, GUILayout.MinHeight(55));
            if (GUILayout.Button("刷新当前页", GUILayout.Height(38))) Refresh();
            scroll = GUILayout.BeginScrollView(scroll);
            GUILayout.Space(10);
            if (tab == 0) DrawFamily();
            else if (tab == 1) DrawMembers();
            else if (tab == 2) DrawTraits();
            else if (tab == 3) DrawInventory();
            else DrawHelp();
            GUILayout.EndScrollView();
            GUILayout.Label("会话 " + session.Substring(0,8) + " · 已读取的数据在关窗或切换存档后失效");
            GUI.DragWindow(new Rect(0,0,window.width,32));
        }
        private void DrawFamily()
        {
            if (family == null) { GUILayout.Label("家族数据尚未就绪。正常游戏或人物页直接打开并刷新。遇到剧情提示请先在游戏里处理。"); return; }
            GUILayout.Label(family.Summary);
            GUILayout.Space(12);
            GUILayout.Label("铜钱变化量（正数增加、负数扣除；单次最多 1,000,000）");
            amount = GUILayout.TextField(amount, 16);
            int delta;
            if (int.TryParse(amount, out delta)) GUILayout.Label("修改后铜钱：" + (family.Money + delta).ToString("N0"));
            if (GUILayout.Button("应用铜钱变化")) {
                var old = family; family = null; member = null; traits = null;
                Run("money", () => Family.ChangeMoney(old, Integer(amount)), true); return;
            }
            GUILayout.Space(18);
            GUILayout.Label("家族声望新增量：本次可加 1–" + family.Remaining + "，最多升一级；按游戏正常规则触发升级。");
            reputation = GUILayout.TextField(reputation, 8);
            if (GUILayout.Button("增加家族声望")) {
                var old = family; family = null; member = null; traits = null;
                Run("reputation", () => Family.AddReputation(old, Integer(reputation)), true);
            }
        }
        private void DrawMembers()
        {
            if (memberList.Count == 0) { GUILayout.Label("当前没有已读取的本族成员。"); return; }
            memberScroll = GUILayout.BeginScrollView(memberScroll, GUILayout.Height(memberList.Count <= 3 ? 52 : 100));
            int currentMember = member == null ? -1 : memberList.FindIndex(x => x.Id == member.Id);
            int selection = GUILayout.SelectionGrid(currentMember, memberList.Select(x => x.Name + " [" + x.Id + "]").ToArray(), 3);
            if (selection >= 0 && selection != currentMember) {
                var chosen = memberList[selection]; Run("select_member", () => { SelectMember(chosen); return "已选中 " + member.Name; });
            }
            GUILayout.EndScrollView();
            if (member == null) { GUILayout.Label("请刷新或重新选择成员，以读取新的修改目标。"); return; }
            GUILayout.Label(member.Name + " · " + member.Summary);
            int next = GUILayout.SelectionGrid(field, Members.FieldKeys.Select(Members.FieldLabel).ToArray(), 4, GUILayout.Height(126));
            if (next != field) { field = next; memberTarget = member.Values[Members.FieldKeys[field]]; }
            string key = Members.FieldKeys[field];
            GUILayout.Label("当前" + Members.FieldLabel(key) + "：" + member.Values[key] + "\n" + member.Limits[key]);
            if (member.Unavailable.ContainsKey(key)) { GUILayout.Label(member.Unavailable[key]); return; }
            if (key == "stamina") {
                if (GUILayout.Button("单次恢复体力至 " + member.StaminaTarget)) {
                    var old = member; member = null; Run("stamina", () => Members.RestoreStamina(old) + MemberPanel.RefreshAfter(old), true);
                }
            } else {
                GUILayout.Label("目标值（直接设置为此值）");
                memberTarget = GUILayout.TextField(memberTarget, 20);
                if (GUILayout.Button("将 " + member.Name + " 的" + Members.FieldLabel(key) + "设为 " + memberTarget)) {
                    var old = member; member = null; Run("member_" + key, () => Members.Apply(old, key, memberTarget) + MemberPanel.RefreshAfter(old), true);
                }
            }
        }
        private void DrawTraits()
        {
            GUILayout.Label("只在新开局的角色创建界面使用。增加可选特质的剩余点数，然后关闭修改器，按原游戏方式选择特质。已创建人物的能力请用“族人”。");
            if (traits == null) return;
            GUILayout.Label(traits.Summary + "\n当前剩余点数：" + traits.Points);
            GUILayout.Label("剩余点数目标（0–1000）");
            traitPoints = GUILayout.TextField(traitPoints, 8);
            if (GUILayout.Button("设置剩余点数为 " + traitPoints)) {
                var old = traits; traits = null;
                Run("traits", () => { GameContext.RequireThread(); return Traits.Apply(old, Integer(traitPoints)); }, true);
            }
            GUILayout.Label("不自动选择、随机或确认角色。剩余点数本身不会成为已建人物的属性。");
        }
        private void DrawInventory()
        {
            GUILayout.Label("目前仅支持增加仓库里已经持有的蔬菜，新增数量会占用相同数量的仓库空间。请先关闭商店/交易，再按 Tab 打开本页。");
            if (inventory == null) return;
            GUILayout.Space(12);
            GUILayout.Label(inventory.Summary);
            if (inventory.Entries.Count == 0) return;
            var entry = inventory.Entries[0];
            GUILayout.Space(12);
            GUILayout.Label("增加数量（1–1000，且不能超过剩余容量）");
            itemAmount = GUILayout.TextField(itemAmount, 8);
            int delta;
            if (int.TryParse(itemAmount, out delta) && delta >= 1 && delta <= 1000 && delta <= inventory.Capacity)
                GUILayout.Label(entry.Name + "：" + entry.Count + " → " + ((long)entry.Count + delta) +
                    "；仓库剩余容量：" + inventory.Capacity + " → " + (inventory.Capacity - delta));
            if (GUILayout.Button("增加 " + entry.Name + " " + itemAmount + " 份")) {
                var old = inventory; inventory = null;
                Run("inventory_" + entry.Id, () => Inventory.Add(old, entry.Id, Integer(itemAmount)), true);
            }
        }
        private void DrawHelp()
        {
            GUILayout.Label("1. 在正常游戏或人物属性页直接按 " + hotkey.Value + "，无需 Esc。开窗自动暂停，关闭恢复进入前状态。\n2. 刷新、核对人物和目标值后应用。每次提交后重新刷新；同一人物的原属性页会在身份核对后同步刷新。\n3. Tab 在文本框中也用于关窗，不做焦点跳转。工具打开时原游戏不接收鼠标、快捷键或滚轮；关窗松开按键后恢复。\n4. 可拖动标题栏，默认放左侧以保留右侧人物页。加载/保存/交易/事件处理中请稍后使用。\n\n不会自动保存，不锁定属性。健康不等于寿命或治愈。\n停用/更新需正常退出游戏后操作本插件目录。热键在BepInEx/config/local.houseoflegacy.trainer.cfg中设置。参考游戏V0.9.03，其它构建按实际结构检查。");
        }
        private void OnApplicationQuit() { Logger.LogInfo("HOL_QUIT session=" + session + " requests=" + requests); }
        private void OnDisable() { if (owner == this) { visible = false; Clear(); Interaction.End(true); } }
        private void OnDestroy() {
            if (owner != this) return;
            SceneManager.activeSceneChanged -= SceneChanged;
            Interaction.Shutdown(); owner = null;
            if (skin != null) Destroy(skin); if (font != null) Destroy(font); if (background != null) Destroy(background);
        }
    }
}
