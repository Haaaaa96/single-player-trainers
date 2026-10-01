"""Pure leave-image checklist and explicit replay policy. No process access."""
import hashlib
import json
from write_guard import Refused, UncertainWrite


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def build_rows(catalog, npcs, *, context_reason=""):
    """NPCs are keyed by verified NpcCfgId, never by the world's UUID key."""
    first = {}
    for cfg in catalog:
        npc = npcs.get(cfg["npc_id"])
        if npc and npc.get("stats") is not None and npc["stats"].get(cfg["sub_id"], 0) < cfg["max_success"]:
            first[cfg["npc_id"]] = min(first.get(cfg["npc_id"], cfg["stage"]), cfg["stage"])
    rows = []
    for cfg in catalog:
        npc = npcs.get(cfg["npc_id"])
        stats = npc.get("stats") if npc else None
        count = stats.get(cfg["sub_id"], 0) if stats is not None else None
        complete = count is not None and count >= cfg["max_success"]
        active = npc.get("active_special", 0) if npc else 0
        dependency = cfg["depends_sub_id"]
        # The audited game uses ContainsKey, including an existing zero count.
        dependency_met = dependency is None or stats is not None and dependency in stats
        reason, force_reason = "", ""
        if cfg["category"] == "deprecated":
            reason = "配置标记为废弃，仅显示，不计入常规完成率。"
        elif cfg["category"] == "quest_pet":
            reason = "宠物／任务专用留影，仅显示；请依游戏任务触发。"
        elif npc is None:
            reason = "当前存档未找到此角色；无法判断是否完成。"
        elif not npc.get("canonical", False):
            reason = "静态角色映射与世界角色字典不一致，仅显示。"
        elif npc.get("world_status") != 0:
            reason = "角色当前未激活或已离开世界，仅显示。"
        elif stats is None or not npc.get("runtime"):
            reason = "角色互动状态尚未初始化；请先在游戏中正常与角色互动。"
        elif npc.get("quest_owned"):
            reason = "角色有任务保留的特殊互动，禁止覆盖。"
        elif active not in (0, cfg["sub_id"]):
            reason = f"角色已有其它特殊互动（编号 {active}），请先正常处理。"
        elif not dependency_met:
            reason = "前置阶段记录尚不存在，请先完成前置留影。"
        elif npc.get("intimacy", -1) < cfg["unlock_intimacy"]:
            reason = "亲密度尚未达到本阶段要求。"
        elif not npc.get("config_verified", {}).get(cfg["sub_id"], False):
            reason = "当前游戏配置未通过本阶段校验，仅显示。"
        elif context_reason:
            reason = context_reason
        force_reason = reason
        # An already active stage is never reset again, even if a success record
        # exists. The user continues that entry in-game before another request.
        can_force = not force_reason and active != cfg["sub_id"]
        if not force_reason and active == cfg["sub_id"]:
            force_reason = "本阶段已激活，不重复删除记录；请先在游戏内继续。"
        if not reason:
            if complete:
                reason = "此阶段已完成；如需重玩，请先预览影响。"
            elif active == cfg["sub_id"]:
                reason = "本阶段已经激活，请回游戏选择留影石。"
            elif first.get(cfg["npc_id"]) != cfg["stage"]:
                reason = "请先激活并完成该角色最前面的未完成阶段。"
        status = ("废弃配置" if cfg["category"] == "deprecated" else
                  "任务／宠物" if cfg["category"] == "quest_pet" else
                  "未生成／未知" if npc is None else
                  "已完成" if complete else "未初始化／未知" if count is None else
                  "已激活" if active == cfg["sub_id"] else "未完成")
        identity = fingerprint([cfg, npc.get("identity") if npc else None, context_reason])
        rows.append(dict(cfg, success_count=count, completed=complete,
                         active_special=active, dependency_met=dependency_met,
                         status=status, reason=reason, force_reason=force_reason,
                         can_activate=not reason, can_force=can_force,
                         identity=identity))
    regular = [r for r in rows if r["category"] == "regular"]
    known = [r for r in regular if r["success_count"] is not None]
    counts = dict(configured=len(rows), regular=len(regular), known=len(known),
                  complete=sum(r["completed"] for r in known), unknown=len(regular)-len(known),
                  quest_pet=sum(r["category"] == "quest_pet" for r in rows),
                  deprecated=sum(r["category"] == "deprecated" for r in rows))
    summary = (f"常规留影已读取 {counts['known']} / {counts['regular']} 段，"
               f"已完成 {counts['complete']} 段；未知 {counts['unknown']} 段。"
               f"任务／宠物 {counts['quest_pet']} 段、废弃配置 {counts['deprecated']} 段单列。")
    return dict(rows=rows, counts=counts, summary=summary)


def replay_preview(row):
    if not isinstance(row, dict) or row.get("can_force") is not True:
        raise Refused(row.get("force_reason") if isinstance(row, dict) and row.get("force_reason")
                      else "请先读取并选择可重玩的常规留影阶段。")
    effects = dict(npc_id=row["npc_id"], sub_id=row["sub_id"],
                   previous_success_count=row["success_count"],
                   active_special_before=row["active_special"],
                   removes_selected_statistics=True, resets_other_stages=False,
                   grants_rewards=False, advances_time=False)
    message = (f"{row['name']} · 第 {row['stage']} 段（编号 {row['sub_id']}）\n"
               f"当前成功次数：{row['success_count']}；当前特殊互动：{row['active_special']}。\n"
               "将调用游戏的指定阶段激活方法，删除本阶段已有成功记录并激活该阶段。"
               "其他阶段记录保持不变；尚未完成的后续阶段仍须满足游戏前置条件。\n"
               "本操作不直接发奖励、不推进时间。之后再次完成游戏可能重复获得正常奖励，"
               "完成率可能下降，失败或中途退出不会自动恢复；仍由游戏检查亲密度及其它前置条件。")
    return dict(row=row, mode="force", identity=row["identity"], effects=effects, message=message)


def verify_statistics(before, after, *, mode, sub_id):
    expected = dict(before)
    if mode == "force":
        expected.pop(sub_id, None)
    elif mode != "next":
        raise Refused("未知留影操作模式。")
    if after != expected:
        raise UncertainWrite("留影操作后的阶段统计不符合预期；请核对游戏，勿重复操作。")
    return True
