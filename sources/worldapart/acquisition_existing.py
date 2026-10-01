"""Top up a reviewed existing stack without loading code in the game.

The caller must first verify a stable, non-combat acquisition context. This is
one Count write through GameAdapter's normal guards, never an item creation or
partial multi-stack transaction. A refused/uncertain write must not fall back to
the native acquisition bridge.
"""
from write_guard import PreconditionChanged, Refused, Target, UncertainWrite, validate_value


def try_add_existing(game, item_id, quantity, *, context_anchors):
    if type(item_id) is not int or type(quantity) is not int or not 1 <= quantity <= 999:
        raise Refused("物品编号和新增数量无效。")
    state = game.snapshot()
    candidates = []
    for key, row in state['items'].items():
        target = row['target']
        if (row.get('item_id') == item_id and isinstance(target, Target)
                and key == target.key and key.startswith('item:')
                and row.get('class_name') in (
                    'Game.Model.Components.BagItem', 'Game.Model.Components.PillBagItem')
                and target.minimum <= target.value
                and target.value + quantity <= target.maximum):
            candidates.append((key, target))
    if not candidates:
        return None
    # Fill one already-owned stack; never write a subset and then create objects.
    _, target = min(candidates, key=lambda pair: (pair[1].maximum - pair[1].value, pair[0]))
    new_value = target.value + quantity
    validate_value(target, new_value)
    if not context_anchors:
        raise Refused("缺少场景复核条件，未补充已有物品。")
    preconditions = tuple((a['address'], bytes.fromhex(a['expected_hex'])) for a in context_anchors)
    try:
        actual = game.set_value(target, new_value, preconditions=preconditions)
    except PreconditionChanged as error:
        from acquisition_context import AcquisitionContextRefused
        raise AcquisitionContextRefused(str(error)) from error
    if not (isinstance(actual, Target) and actual.key == target.key
            and actual.address == target.address and actual.identity == target.identity
            and actual.value == new_value):
        raise UncertainWrite("已有物品的数量修改未能核验，已停止；请检查游戏，勿重复添加。")
    return dict(status='verified', verified=True, changed=True, called=False,
                native_injection=False, operation='add_existing', item_id=item_id,
                quantity=quantity, before=target.value, after=actual.value,
                target=target.key, new_uids=[], method='existing stack / guarded Count write')
