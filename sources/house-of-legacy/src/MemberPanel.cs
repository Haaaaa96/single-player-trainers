using System;
using System.Globalization;
using System.Linq;
using UnityEngine;

namespace HouseOfLegacyTrainer
{
    internal static class MemberPanel
    {
        internal static int CurrentIndex()
        {
            var panels = UnityEngine.Object.FindObjectsOfType<PerMemberNowPanel>().Where(x => x.isActiveAndEnabled).ToArray();
            return panels.Length == 1 ? Mainload.MemberIndex_click : -1;
        }
        internal static string RefreshAfter(Members.Snapshot changed)
        {
            try {
                Interaction.Require();
                var panels = UnityEngine.Object.FindObjectsOfType<PerMemberNowPanel>().Where(x => x.isActiveAndEnabled).ToArray();
                if (panels.Length == 0) return "";
                int index = changed.OriginalIndex;
                if (panels.Length != 1 || Mainload.MemberIndex_click != index || Mainload.MemberIndex_clickB != -1 ||
                    !ReferenceEquals(Mainload.Member_now, changed.Table) || index < 0 || index >= changed.Table.Count ||
                    !ReferenceEquals(changed.Table[index], changed.Row) || changed.Row[0] != changed.Id ||
                    changed.Table.Count(x => x != null && x.Count > 0 && x[0] == changed.Id) != 1)
                    return "；原人物页不是同一可刷新目标，请在关窗后重新打开该人物页核对。";
                var root = panels[0].transform.Find("IconShow");
                var icons = root == null ? new PerLiHuiBig[0] : root.GetComponentsInChildren<PerLiHuiBig>();
                if (icons.Length != 1 || icons[0].name != index.ToString(CultureInfo.InvariantCulture) || icons[0].ShowID != 0 || icons[0].isShowInfo)
                    return "；原人物页身份尚未稳定，请关窗后重新打开该人物页核对。";
                // Game's own existing refresh entry. No OnEnable animation or global selection change.
                panels[0].updateShow();
                return "；原人物属性页已同步刷新。";
            } catch (Exception e) {
                // Writing already succeeded. Never label a UI refresh failure as a failed write.
                return "；数值已修改，但原人物页刷新未完成，请关窗重开核对：" + e.Message;
            }
        }
    }
}
