"""Pure, read-only hints for the version-locked MedGame hex pipe puzzle.

Ports/odd-row neighbours and rotation semantics are transcribed from
MedPipeCatalog..cctor (RVA a50620), MedBoardGenerator.Neighbor (1d959c0),
MedCellViewModel.Rotate (a4cc70), Click/RightClick (a4ba40/a4cc50).
The generated solution is a reference, not a promise that a modified/locked
board can still reach it. Every returned route is independently connected and
each suggested rotation must remain legal under the current cell state.
"""
from heapq import heappop, heappush
from copy import deepcopy

SHAPE_NAMES = ("I", "C", "L", "Y", "T", "X")
VARIANT_COUNTS = (3, 6, 6, 2, 6, 1)
BASE_PORTS = ((0, 3), (0, 1), (0, 2), (0, 2, 4), (0, 1, 2), (0, 1, 2, 3, 4, 5))


def build_restore_plan(state):
    """Prove the actual native helper's restored board connects before dispatch.

    Unlike a legal-click hint, the native helper reveals and unlocks generated
    path cells and restores their generated shape. Nothing is written here.
    Already aligned boards are refused: the helper may otherwise skip refresh.
    """
    denied = dict(can_restore=False, route=[], changed_cells=0, reason="请先进入完整的疏经导脉棋盘。")
    if not isinstance(state, dict) or state.get("active") is not True:
        return denied
    try:
        _validate(state)
        restored = deepcopy(state)
        changed = 0
        for cell in restored["cells"]:
            if not cell["is_generated_path"]:
                continue
            changed += int(cell["hidden"] or cell["kind"] != 0 or
                           cell["shape"] != cell["solution_shape"] or
                           cell["variant"] != cell["solution_variant"])
            cell.update(hidden=False, kind=0, shape=cell["solution_shape"],
                        variant=cell["solution_variant"], rotate_count=0)
        hint = build_hint(restored)
        if not hint["verified_path"] or hint["steps"]:
            return {**denied, "reason": "游戏生成路线未通过完整连通校验，未开放一键疏通。"}
        if changed == 0:
            return {**denied, "route": hint["route"], "reason": "通路已按原解对齐；请等待游戏判定，不重复调用。"}
        return dict(can_restore=True, route=hint["route"], changed_cells=changed,
                    reason=f"可恢复本局原始通路（{changed} 格）；由游戏进行胜利结算。")
    except (ValueError, TypeError, KeyError) as error:
        return {**denied, "reason": str(error)}


def ports(shape, variant):
    if type(shape) is not int or not 0 <= shape < 6:
        raise ValueError("未知经脉形状。")
    if type(variant) is not int or not 0 <= variant < VARIANT_COUNTS[shape]:
        raise ValueError("经脉方向超出范围。")
    return frozenset((p + variant) % 6 for p in BASE_PORTS[shape])


def neighbor(col, row, direction):
    if any(type(v) is not int for v in (col, row, direction)) or not 0 <= direction < 6:
        raise ValueError("六边形坐标或方向无效。")
    odd = row & 1
    return ((col + 1, row), (col + odd, row + 1), (col - 1 + odd, row + 1),
            (col - 1, row), (col - 1 + odd, row - 1), (col + odd, row - 1))[direction]


def rotation_steps(shape, current, desired):
    """Fewest native clicks; +1 is left click, -1 is right click."""
    ports(shape, current)
    ports(shape, desired)
    count = VARIANT_COUNTS[shape]
    forward, backward = (desired - current) % count, (current - desired) % count
    return (forward, 1) if forward <= backward else (backward, -1)


def _validate(state):
    cfg = state.get("config", {})
    rows, cols = cfg.get("rows"), cfg.get("cols")
    if any(type(v) is not int or not 1 <= v <= 64 for v in (rows, cols)) or rows * cols > 1024:
        raise ValueError("棋盘尺寸无效。")
    cells = state.get("cells")
    if not isinstance(cells, (tuple, list)) or len(cells) != rows * cols:
        raise ValueError("棋盘格子不完整。")
    mapped = {}
    for original in cells:
        if not isinstance(original, dict):
            raise ValueError("棋盘格子格式无效。")
        cell = dict(original)
        col, row = cell.get("col"), cell.get("row")
        if (type(col) is not int or type(row) is not int or not 0 <= col < cols or not 0 <= row < rows
                or (col, row) in mapped):
            raise ValueError("棋盘坐标重复或越界。")
        for key, high in (("role", 2), ("kind", 3), ("rotate_count", 1_000_000)):
            if type(cell.get(key)) is not int or not 0 <= cell[key] <= high:
                raise ValueError("棋盘格子状态无效。")
        for key in ("hidden", "is_generated_path"):
            if type(cell.get(key)) is not bool:
                raise ValueError("棋盘格子标记无效。")
        ports(cell.get("shape"), cell.get("variant"))
        ports(cell.get("solution_shape"), cell.get("solution_variant"))
        mapped[col, row] = cell
    starts = [key for key, cell in mapped.items() if cell["role"] == 1]
    ends = [key for key, cell in mapped.items() if cell["role"] == 2]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("棋盘起点或终点不唯一。")
    for label, found in (("start", starts[0]), ("end", ends[0])):
        if found != (cfg.get(label + "_col"), cfg.get(label + "_row")):
            raise ValueError("棋盘起终点与配置不一致。")
    return mapped, starts[0], ends[0]


def _candidate(cell):
    """Return one attainable reference orientation plus required actions."""
    result = dict(cell, clicks=0, direction=0, action="keep", issue="")
    result["target_shape"], result["target_variant"] = cell["shape"], cell["variant"]
    if cell["kind"] == 3:
        result["issue"] = "阻断格不能连通。"
        return result
    # Fixed endpoints and already transformed full-connect cells retain their
    # real ports; substituting the generator's original shape would be false.
    if cell["role"] or cell["shape"] == 5:
        result["action"] = "reveal" if cell["hidden"] else "keep"
        return result
    if cell["shape"] != cell["solution_shape"]:
        result["issue"] = "形状已改变，原始解法不适用。"
        return result
    clicks, direction = rotation_steps(cell["shape"], cell["variant"], cell["solution_variant"])
    if clicks and (cell["kind"] == 2 or cell["kind"] == 1 and clicks > max(0, 1 - cell["rotate_count"])):
        # It may still connect on a different branch in its existing orientation.
        result["issue"] = "已锁定或剩余旋转次数不足，保留当前方向。"
        return result
    result.update(clicks=clicks, direction=direction if clicks else 0,
                  target_variant=cell["solution_variant"])
    result["action"] = ("reveal_rotate" if clicks else "reveal") if cell["hidden"] else ("rotate" if clicks else "keep")
    return result


def build_hint(state):
    """Return independent hints; never calls game APIs or mutates ``state``.

Coordinates are zero-based in returned data and one-based in displayed text.
``verified_path`` proves geometry/rotation feasibility, not sufficient time,
needles, skill availability, or success of a live round.
"""
    empty = dict(summary="请先进入疏经导脉小游戏，再刷新棋盘。", steps=[], cells=[], route=[],
                 verified_path=False, warnings=[])
    if not isinstance(state, dict) or state.get("active") is not True:
        return empty
    try:
        mapped, start, end = _validate(state)
    except (ValueError, TypeError, KeyError) as exc:
        return {**empty, "summary": str(exc), "warnings": ["数据未通过核验，未生成操作步骤。"]}
    candidates = {key: _candidate(cell) for key, cell in mapped.items()
                  if cell["is_generated_path"] or cell["role"]}
    # Only generator-marked cells are used; no arbitrary global solver claim.
    queue, best = [(0, (start,))], {start: 0}
    route = ()
    while queue:
        cost, path = heappop(queue)
        here = path[-1]
        if here == end:
            route = path
            break
        if cost != best[here]:
            continue
        source = candidates[here]
        if source["kind"] == 3:
            continue
        for direction in sorted(ports(source["target_shape"], source["target_variant"])):
            there = neighbor(*here, direction)
            target = candidates.get(there)
            if target is None or target["kind"] == 3:
                continue
            if (direction + 3) % 6 not in ports(target["target_shape"], target["target_variant"]):
                continue
            next_cost = cost + 1 + 10 * (target["clicks"] + int(target["hidden"]))
            if next_cost < best.get(there, float("inf")):
                best[there] = next_cost
                heappush(queue, (next_cost, (*path, there)))
    rendered = []
    for key, cell in mapped.items():
        hint = candidates.get(key, dict(cell, clicks=0, direction=0, action="keep", issue="",
                                        target_shape=cell["shape"], target_variant=cell["variant"]))
        rendered.append({**hint, "on_route": key in route,
                         "ports": sorted(ports(cell["shape"], cell["variant"])),
                         "target_ports": sorted(ports(hint["target_shape"], hint["target_variant"]))})
    if not route:
        warnings = [f"第 {cell['row'] + 1} 行第 {cell['col'] + 1} 列：{cell['issue']}"
                    for cell in candidates.values() if cell["issue"]]
        if any(cell["kind"] in (1, 2) and cell["issue"] and not cell["role"]
               for cell in candidates.values()):
            warnings.append("若已解锁变换技能，可在游戏内变换锁定格后刷新；本提示不会替你使用技能。")
        return {**empty, "cells": rendered, "summary": "当前状态下未找到可按原始解法连通的路线。",
                "warnings": warnings or ["原始路线已改变或数据不一致；请刷新后检查棋盘。"]}
    steps = []
    for key in route:
        cell = candidates[key]
        if cell["action"] == "keep":
            continue
        where = f"第 {cell['row'] + 1} 行第 {cell['col'] + 1} 列"
        parts = []
        if cell["hidden"]:
            parts.append("先单击揭开，等待动画结束")
        if cell["clicks"]:
            parts.append(f"{'左' if cell['direction'] > 0 else '右'}键旋转 {cell['clicks']} 次")
        steps.append({key: cell[key] for key in ("row", "col", "action", "clicks", "direction", "target_shape", "target_variant")}
                     | {"text": where + "：" + "，再".join(parts) + "。"})
    actions = sum(cell["clicks"] + int(cell["hidden"]) for cell in (candidates[key] for key in route))
    warnings = ["提示按当前快照计算；操作后刷新。只显示路线，不自动点击或通关。"]
    remaining = state.get("needle_remaining")
    if type(remaining) is int and 0 <= remaining < actions:
        warnings.append(f"预计需 {actions} 次用针操作，当前剩余 {remaining}；未计途中奖励，可能需要补足针数。")
    return dict(summary=f"找到 {len(route)} 格连通参考路线，需处理 {len(steps)} 格，预计 {actions} 次用针。",
                steps=steps, cells=rendered, route=list(route), verified_path=True, warnings=warnings,
                estimated_needles=actions)
