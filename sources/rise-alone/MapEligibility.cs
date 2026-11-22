using System.Collections.Generic;
using Script.Mrg;
using Script.Tool;

namespace RiseAlone
{
    internal static class MapEligibility
    {
        internal static bool ShouldMark(Map3DTriggerr point,HashSet<CollType> gated,GameDataMrg manager)
        {
            if(!point.gameObject.activeSelf || point.eventData==null || !gated.Contains(point.collType))return false;
            if(manager.IsUnLockPoint(point.collType.ToString()))return false;
            // The first query matches the map player's interaction prompt. Trigger checks both chapter conditions again.
            FrameWork.Tool.IsCanTrigger(point.collType,out bool canShow,out bool canTrigger,out string _,out VideoGraph graph);
            if(!canShow || !canTrigger || graph==null)return false;
            var chapter=FrameWork.Tool.GetEvenChapterNode(graph);
            return chapter!=null && FrameWork.Tool.IsSuc(chapter.propertyType) && FrameWork.Tool.IsSuc(chapter.showPropertyType);
        }
    }
}
