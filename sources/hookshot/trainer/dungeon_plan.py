"""Join authored steps, resource geometry and the typed read-only state catalog."""
import json
import math
import re

from dungeon_state import GameDataIndex, generate_dungeon_state
from dungeon_steps import generate_dungeon_steps


def wide(text):
    return 'L' + json.dumps(text, ensure_ascii=False)


def condition_key(condition):
    return tuple(condition[key] for key in ('type', 'hash', 'expected', 'op'))


def generate_dungeon_plan(rom, out, geometry):
    names = re.findall(r'HK_MAP_ID\(([^)]+)\)', (out / 'map_ids.generated.h').read_text())
    ids = {name: number for number, name in enumerate(names, 1)}
    steps = generate_dungeon_steps(rom)
    if len({step['scene'] for step in steps}) != 12:
        raise ValueError('The base-dungeon step catalog must cover twelve scenes')
    scene_conditions, condition_indices = {}, {}

    def add_condition(scene, condition):
        number = ids[scene]
        items = scene_conditions.setdefault(number, [])
        index = condition_indices.setdefault(number, {})
        key = condition_key(condition)
        if key not in index:
            index[key] = len(items)
            items.append(condition)
        return index[key]

    seen = set()
    for step in steps:
        identity = step['scene'], step['id']
        if identity in seen:
            raise ValueError(f'Duplicate step: {identity}')
        seen.add(identity)
        target = step['target']
        if len(target['xyz']) != 3 or not all(math.isfinite(value) for value in target['xyz']):
            raise ValueError(f'Invalid target: {identity}')
        if step['age'] not in (0, 1, 2) or step['complete_mode'] not in ('all', 'any'):
            raise ValueError(f'Invalid step rules: {identity}')
        for group in ('prereqs', 'complete'):
            step[group + '_indices'] = [add_condition(step['scene'], item) for item in step[group]]

    # Geometry may identify a door's open condition. Unproven conditions remain
    # absent, so the renderer can stop at that door without claiming it is open.
    gates = []
    for edge in geometry['edges']:
        scene = geometry['nodes'][edge['from_node']]['scene']
        if isinstance(scene, int):
            scene = names[scene-1]
        conditions = edge.get('conditions', [])
        mode = edge.get('condition_mode', 'all')
        if not conditions and edge.get('gate_actor'):
            matches = [step for step in steps if step['scene'] == scene and
                       step['target']['actor'] == edge['gate_actor']]
            if len(matches) == 1:
                # The authored step already binds this exact actor to its
                # completion predicate. Never attach a nearby actor's flag.
                conditions = matches[0]['complete']
                mode = matches[0]['complete_mode']
                edge['condition_from_step'] = matches[0]['id']
        gates.append((ids[scene], [add_condition(scene, item) for item in conditions],
                      mode == 'any'))
    index = GameDataIndex(rom)
    inventory = []
    for scene in dict.fromkeys(step['scene'] for step in steps):
        fields = []
        for name in (f'DungeonInfo.{scene}.SmallKeyNum', f'DungeonInfo.{scene}.IsGetBossKey',
                     'WaterTemple_Room00_WaterLevel' if scene == 'WaterTemple' else ''):
            if not name:
                fields.append(-1)
                continue
            try:
                condition = index.condition(name)
            except ValueError:
                fields.append(-1)
            else:
                fields.append(add_condition(scene, condition))
        inventory.append((ids[scene], fields))
    offsets = generate_dungeon_state(rom, out, scene_conditions)
    refs, rows = [], []
    for step in steps:
        scene = ids[step['scene']]
        first_pre = len(refs)
        refs.extend(offsets[scene] + index for index in step['prereqs_indices'])
        first_done = len(refs)
        refs.extend(offsets[scene] + index for index in step['complete_indices'])
        p = step['target']
        rows.append('    {%d, %d, %d, %d, %s, 0x%016xull, %s, %s, %s, %s, %d, %d, %d, %d, %s, %s},' % (
            scene, step['age'], p['floor'], p['room'], ', '.join(f'{v:.6f}f' for v in p['xyz']),
            p['actor'], wide(step['title']), wide(step['action']), wide(step['detail']),
            wide(step.get('transition', '')), first_pre, len(step['prereqs']), first_done,
            len(step['complete']), str(step['complete_mode'] == 'any').lower(), str(step.get('final', False)).lower()))
    advance_refs, advance_rows, advance_report = [], [], []
    for i, step in enumerate(steps):
        start = len(advance_refs)
        for actor in step.get('superseded_by', []):
            matches = [j for j, other in enumerate(steps)
                       if other['scene'] == step['scene'] and other['target']['actor'] == actor]
            if len(matches) != 1 or matches[0] <= i:
                raise ValueError(f"Progress witness must identify one later step: {step['id']}")
            witness = steps[matches[0]]
            if witness['age'] != step['age'] or not witness['target']['gyaml'].startswith('Obj_TBox'):
                raise ValueError(f"Progress witness must be an age-matched native chest: {step['id']}")
            if len(witness['complete']) != 1 or not witness['complete'][0]['name'].startswith('IsTreasureBoxOpen.'):
                raise ValueError(f"Progress witness must use its actual opened flag: {step['id']}")
            advance_refs.append(matches[0])
            advance_report.append({'step': step['id'], 'witness': witness['id'],
                                   'condition': witness['complete'][0]['name']})
        advance_rows.append(f'    {{{start}, {len(advance_refs)-start}}},')
    gate_rows = []
    for scene, indices, any_mode in gates:
        start = len(refs)
        refs.extend(offsets[scene] + index for index in indices)
        gate_rows.append(f'    {{{start}, {len(indices)}, {str(any_mode).lower()}}},')
    code = ['#pragma once', 'static const HkDungeonStep hkDungeonSteps[] = {', *rows, '};',
            'static constexpr int hkDungeonConditionRefs[] = {' + ', '.join(map(str, refs or [-1])) + '};',
            'static constexpr int hkDungeonAdvanceRefs[] = {' + ', '.join(map(str, advance_refs or [-1])) + '};',
            'static constexpr HkDungeonAdvanceRule hkDungeonAdvanceRules[] = {', *advance_rows, '};',
            'static const HkDungeonGateRule hkDungeonGateRules[] = {', *gate_rows, '};']
    code += ['static constexpr HkDungeonRestrictedRoom hkDungeonRestrictedRooms[] = {']
    for scene in geometry['scenes']:
        code.extend('    {%d, %d},' % (scene['scene'], room) for room in scene.get('unsafe_rooms', []))
    code.append('};')
    code.append('static constexpr HkDungeonInventory hkDungeonInventoryFields[] = {')
    for scene, fields in inventory:
        code.append('    {%d, %s},' % (scene, ', '.join(str(offsets[scene]+value if value >= 0 else -1) for value in fields)))
    code.append('};')
    (out / 'dungeon_plan.generated.h').write_text('\n'.join(code) + '\n', encoding='utf-8')
    report = {'steps': steps, 'gate_condition_step_bindings': [
                {'edge': i, 'step': edge['condition_from_step']} for i, edge in enumerate(geometry['edges'])
                if edge.get('condition_from_step')],
              'progress_witnesses': advance_report,
              'condition_counts': {key: len(value) for key, value in scene_conditions.items()},
              'conditions': scene_conditions, 'scenes': {step['scene']: ids[step['scene']] for step in steps}}
    (out / 'dungeon_plan.generated.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report
