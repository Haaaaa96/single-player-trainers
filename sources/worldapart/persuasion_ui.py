"""One active persuasion session, using the game's normal success settlement."""
from dual_cultivation_ui import MiniGamePanel


class PersuasionPanel(MiniGamePanel):
    title = "秒说服"
    button_text = "立即判定本局说服成功"
    explanation = ("先在游戏内正常进入说服界面，再读取当前局。\n"
                   "无需继续输入说服文字；AI 回复、窥探或输入审核处理中请等待结束后重新读取。\n"
                   "成功后保留游戏倒计时及奖励／任务结算；不会另外发奖，也不跳过互动解锁条件。\n"
                   "本版不跳过结算倒计时。每局只派发一次，结果未确认时不自动重试。")

    def create_adapter(self, game):
        from persuasion_adapter import PersuasionAdapter
        return PersuasionAdapter(game)

    def describe(self, state):
        required = ("npc_id", "topic_id", "progress", "rounds", "max_rounds", "exit_delay_ms")
        if any(key not in state for key in required):
            return state.get("reason") or "当前说服尚未就绪，请等待后刷新。"
        npc = state.get("name") or state["npc_id"]
        topic = state.get("topic") or state["topic_id"]
        status = ("当前可操作：可判定本局说服成功。" if state.get("can_solve") else
                  "当前不可操作：" + (state.get("reason") or "本局尚未就绪，请等待后重新读取。"))
        return (f"角色 {npc} · 话题 {topic}\n"
                f"说服进度 {state['progress']} / {state.get('threshold', '—')} · "
                f"回合 {state['rounds']} / {state['max_rounds']}\n"
                f"{status}\n"
                f"成功后保留约 {state['exit_delay_ms'] / 1000:g} 秒的结果倒计时，再继续游戏结算。")
