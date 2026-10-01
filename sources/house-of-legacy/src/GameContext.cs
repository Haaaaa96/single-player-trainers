using System;
using System.Linq;
using System.Threading;
using System.Reflection;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace HouseOfLegacyTrainer
{
    internal sealed class GameContext
    {
        internal static int MainThread;
        internal static long Epoch;
        private int scene;
        private long epoch;
        private string slot, sceneId;
        private int[] date;
        private object members, family, money, items;
        private long lease;
        private float capturedAt;

        internal static void RequireThread()
        {
            if (MainThread == 0 || Thread.CurrentThread.ManagedThreadId != MainThread)
                throw new InvalidOperationException("操作必须在游戏主线程执行。");
        }

        internal static bool IsLoading()
        {
            return UnityEngine.Object.FindObjectsOfType<LoadPanel>().Any(x => x.isActiveAndEnabled) ||
                UnityEngine.Object.FindObjectsOfType<SwichPanel>().Any(x => x.isActiveAndEnabled) ||
                UnityEngine.Object.FindObjectsOfType<GamePausePanelB>().Any(x => x.isActiveAndEnabled);
        }

        private static readonly string[] AllowedPanels = { "isZupuPanelOpen", "isJiaZuDataPanelOpen", "isKunAllCunPanelOpen", "isGamePausePanelOpen" };
        private static readonly FieldInfo[] PanelFlags = typeof(Mainload).GetFields(BindingFlags.Public | BindingFlags.Static)
            .Where(x => x.FieldType == typeof(bool) && x.Name.EndsWith("PanelOpen") && !AllowedPanels.Contains(x.Name)).ToArray();

        internal static void RequireStablePage()
        {
            RequireThread();
            if (IsLoading() || Mainload.isUpdateScene || Mainload.isSwichPanelOpen)
                throw new InvalidOperationException("正在加载、保存或切换场景，请稍后按 Tab。");
            if (UnityEngine.Object.FindObjectsOfType<InitGameUI>().Any(x => x.isActiveAndEnabled)) return;
            if (UnityEngine.Object.FindObjectsOfType<MainUpdate>().Count(x => x.isActiveAndEnabled) != 1)
                throw new InvalidOperationException("请进入正常游戏或角色创建界面后按 Tab。");
            var blocked = PanelFlags.FirstOrDefault(x => (bool)x.GetValue(null));
            if (blocked != null) throw new InvalidOperationException("请先关闭商店、交易或事件等操作面板，再在正常游戏/人物页按 Tab。界面：" + blocked.Name);
        }

        public static GameContext Capture()
        {
            RequireThread();
            Interaction.Require();
            if (UnityEngine.Object.FindObjectsOfType<MainUpdate>().Count(x => x.isActiveAndEnabled) != 1)
                throw new InvalidOperationException("尚未载入可编辑的家族存档。");
            if (string.IsNullOrEmpty(Mainload.CunDangIndex_now) || Mainload.Member_now == null ||
                Mainload.Member_now.Count == 0 || Mainload.FamilyData == null || Mainload.FamilyData.Count < 4 ||
                Mainload.CGNum == null || Mainload.CGNum.Count < 4 || Mainload.Time_now == null || Mainload.Time_now.Count < 3)
                throw new InvalidOperationException("尚未载入可编辑的家族存档。");
            return new GameContext {
                scene = SceneManager.GetActiveScene().handle, epoch = Epoch,
                slot = Mainload.CunDangIndex_now, sceneId = Mainload.SceneID,
                date = Mainload.Time_now.ToArray(), members = Mainload.Member_now,
                family = Mainload.FamilyData, money = Mainload.CGNum, items = Mainload.Prop_have,
                lease = Interaction.Lease, capturedAt = Time.realtimeSinceStartup
            };
        }

        public void Validate()
        {
            var now = Capture();
            if (epoch != Epoch || scene != now.scene || slot != now.slot || sceneId != now.sceneId ||
                !ReferenceEquals(members, now.members) || !ReferenceEquals(family, now.family) ||
                !ReferenceEquals(money, now.money) || !ReferenceEquals(items, now.items) ||
                lease != now.lease || !date.SequenceEqual(now.date) || Time.realtimeSinceStartup - capturedAt > 120)
                throw new InvalidOperationException("存档、日期或界面已变化，或读取已超过两分钟；请刷新后再操作。");
        }
    }
}
