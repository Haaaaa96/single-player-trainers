"""Bounded plan for the current smithing prototype, never arbitrary item stats."""
from write_guard import Refused

LIMIT = 1_000_000


def integer(value, minimum=0, maximum=LIMIT):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Refused('炼器数据不是允许范围内的整数。')
    return value


def completion_plan(score, tiers, effects, energies):
    """Raise only score and existing energy values to their configured minima.

    Native CheckEffectActivation keeps valid existing affixes and rolls missing
    ones from the ordinary pool. Neither affix identity nor its roll is chosen.
    """
    integer(score)
    if type(tiers) is not list or not 1 <= len(tiers) <= 32:
        raise Refused('器胚品阶配置缺失或过长。')
    ids, thresholds = set(), set()
    for row in tiers:
        tier, threshold = integer(row['tier_id'], 1), integer(row['score_min'], 0)
        if tier in ids or threshold in thresholds:
            raise Refused('器胚品阶编号或门槛重复。')
        ids.add(tier); thresholds.add(threshold)
    highest = max(tiers, key=lambda row: row['score_min'])
    integer(highest['score_min'], 1)
    if type(effects) is not list or len(effects) > 32 or type(energies) is not dict or len(energies) > 5:
        raise Refused('炼器词条或元素列表异常。')
    for element, row in energies.items():
        integer(element, 1, 5); integer(row['value'])
        if type(row['address']) is not int or row['address'] <= 0 or row['address'] % 4:
            raise Refused('炼器元素目标地址无效。')
    requirements = {}
    for effect in effects:
        element = integer(effect['element'], 1, 5)
        integer(effect['pool_id'], 1)
        required = integer(effect['required'], 0)
        if type(effect['activated']) is not bool:
            raise Refused('炼器词条状态无效。')
        if element not in energies:
            raise Refused('本局缺少词条所需元素，不创建字典条目；请重新开始并选齐所需材料。')
        requirements[element] = max(requirements.get(element, 0), required)
    updates = [dict(element=element, address=energies[element]['address'], before=energies[element]['value'],
                    after=max(energies[element]['value'], required))
               for element, required in sorted(requirements.items())]
    return dict(score_before=score, score_after=max(score, highest['score_min']),
                tier_id=highest['tier_id'], tier_minimum=highest['score_min'],
                energy_updates=updates, effect_count=len(effects))
