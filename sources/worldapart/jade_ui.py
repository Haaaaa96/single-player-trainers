"""Reveal an owned jade stone without manufacturing its innate quality."""
from dual_cultivation_ui import MiniGamePanel
from jade_adapter import exchange_status
from write_guard import Refused, UncertainWrite


class JadePanel(MiniGamePanel):
    title = "刮玉"
    button_text = "一键全部揭示当前原石"
    explanation = ("先在游戏刮玉界面选中背包原石，停下鼠标刮擦并关闭兑换界面。\n"
                   "一次完成整块揭示，保持原石天然品质、花色、裂纹和游戏估值算法。天然裂纹仍可能降低估值。\n"
                   "全部揭示不保证达到兑换门槛；不会生成无裂纹原石或自动兑换物品，请在游戏内保存。\n"
                   "每块原石只派发一次，结果未确认时不自动重试。")

    def create_adapter(self, game):
        from jade_adapter import JadeAdapter
        return JadeAdapter(game)

    def describe(self, state):
        label = "本次已完成原石" if state.get("result_snapshot") else "原石物品"
        return (f"{label} {state['item_id']} · 实例 {state['instance_id']}\n"
                f"已揭示 {state['ratio']:.1%} · 当前估值 {state['current_value']}\n"
                f"原有花色 {state['blooms']} 项 · 原有裂纹 {state['cracks']} 项\n"
                f"{exchange_status(state)}")

    def solve(self):
        if (not self.available() or self.adapter is None or not self.state
                or not self.state.get("can_solve")):
            return
        shown, adapter, game = self.state, self.adapter, self.app.adapter
        self.state = None
        self.summary.set("本次揭示结果尚未确认，请等待核验，不要重复操作。")
        self.update_enabled(False)

        def job():
            try:
                return adapter.solve(shown)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_called=str(error))

        def success(result):
            self.state = None
            if self.app.adapter is not game or self.adapter is not adapter:
                return
            if result.get("not_called"):
                self.summary.set("本次未派发，请重新读取当前原石。")
                text = result["not_called"]
            else:
                self.summary.set(self.describe(result["display_state"]))
                text = result["message"]
            self.note.set(text)
            self.app.status.set(text)
            self.update_enabled(self.app.adapter is not None and not self.app.busy)

        self.app.work(job, success)
