from dual_cultivation_ui import MiniGamePanel


class AlchemyRecipePanel(MiniGamePanel):
    title = "丹方探索"
    button_text = "自动取得本局第一张丹方"
    explanation = ("先正常进入炼丹探索地图，等待药材移动与动画结束。\n"
                   "在当前已显示的丹方中选择最近且可独立触发的一张，按丹炉等级限制，调用游戏定位与收集流程。\n"
                   "本局已有丹方时不替换；不收集附近其他节点，不循环开启下一局。丹毒、经验和后续凝丹仍由游戏处理。\n"
                   "取得本局丹方不等于永久解锁，需继续按游戏正常流程炼制。")

    def create_adapter(self, game):
        from alchemy_recipe import AlchemyRecipeAdapter
        return AlchemyRecipeAdapter(game)

    def describe(self, state):
        target = state.get("candidate")
        return (f"丹炉等级 {state['furnace']}\n候选：{target['name']} · {target['tier']} 阶 · 编号 {target['recipe_id']}"
                if target else f"丹炉等级 {state['furnace']} · 尚无可用候选")
