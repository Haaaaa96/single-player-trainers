"""Read dungeon topology from the installed game; never infer a vertical edge
from the distance between room centres.  The graph is a schematic room/portal
graph, not a navigation mesh.  Authored transitions carry separate evidence.

All floor numbers below are zero-based indices into MapParam.Floor.  Actor
identities and coordinates are resolved again on each build.  Gate categories
describe what an edge encounters; they are NOT live open/closed state.
"""

from collections import defaultdict
from hashlib import sha256
import json
from math import dist
from pathlib import Path

from world_map import BASE, BANC_SUFFIX, PRIORITY_ITEMS, position

DUNGEONS = tuple(PRIORITY_ITEMS)
NODE_ROOM, NODE_ENTRANCE, NODE_MECHANISM = range(3)
WALK, DOOR, DROP, CLIMB, LIFT, SWIM, STAIRS, HOOKSHOT = range(8)
FREE, ORDINARY_DOOR, MECHANISM_GATE, SMALL_KEY, BOSS_KEY, ACTION_REQUIRED = range(6)

HEADER = '''// Generated from local MapParam / Banc; graph lines are schematic.
#pragma once
#include <stdint.h>
enum { kDgRoom, kDgEntrance, kDgMechanism };
enum { kDgWalk, kDgDoor, kDgDrop, kDgClimb, kDgLift, kDgSwim, kDgStairs, kDgHookshot };
// Categories only. Consult live state separately; 5 is an unresolved action.
enum { kDgFree, kDgOrdinaryDoor, kDgMechanismGate, kDgSmallKey, kDgBossKey, kDgActionRequired };
struct HkDungeonNode { float x,y,z; int scene,floor,room,kind; uint64_t actor; };
struct HkDungeonEdge { int from,to,kind,condition; uint64_t gate_actor,chain_actor; const wchar_t* action; };
struct HkDungeonAnchor { float x,y,z; int scene,floor,room,kind; uint64_t actor; const wchar_t* label; };
struct HkDungeonRoomMap { int scene,raw_room,room; };
'''


def floor_at(row, p):
    return max(0, sum(p[1] >= f['TransY'] for f in row['Floor']) - 1)


def room_floors(row, room):
    # Hidden room rows sometimes omit Floor; their centre still has a real Y.
    return [f - row['MinFloor'] for f in room.get('Floor', [])] or [floor_at(row, room['CenterTrans'])]


def actor_label(kind):
    if not kind.startswith('Obj_'): return ''
    if 'EyeSwitch' in kind: return '瞄准眼睛开关射击'
    if 'DiveSwitch' in kind: return '潜水按下水底开关'
    if 'StepSwitch' in kind or 'Stepswitch' in kind: return '踩下或压住地面开关'
    if 'WaterLevel' in kind or 'WaterSwitch' in kind: return '检查水位机关'
    if 'SwitchHit' in kind: return '击打机关'
    if 'SolarSwitch' in kind: return '把光线照到太阳机关'
    if 'Mirror' in kind: return '调整镜面反射方向'
    if 'Elevator' in kind or 'MoveFloor' in kind or 'FloatFloor' in kind: return '乘坐移动平台，抵达后重新定位'
    if 'Climb' in kind or 'Ladder' in kind: return '攀爬梯子或墙面'
    if 'BrokenStair' in kind: return '引爆炸弹花，降下楼梯'
    if 'Hammer' in kind: return '用巨锤击打机关'
    if 'SpiderWeb' in kind and 'Interactive' not in kind: return '检查蛛网；烧穿或从高处击破'
    if 'SwitchCandle' in kind: return '点燃机关火把'
    if 'HookShotTarget' in kind: return '用钩索瞄准靶点'
    return ''


def build_dungeon_geometry(rom):
    from dungeon_state import GameDataIndex
    game_data = GameDataIndex(rom)
    room_defaults_path='Component/Blackboard/BlackboardParamTable/DungeonRoom.engine__component__BlackboardParamTable.bgyml'
    room_defaults=rom.byml(room_defaults_path)
    default_room=next(v['InitVal'] for v in room_defaults['BlackboardParamS32Array'] if v['BBKey']=='DungeonRoomID')
    if default_room!=0:raise ValueError('DungeonRoomID default changed')
    def group_raw(g):
        if 'DungeonRoomID' in g.get('Dynamic',{}):return g['Dynamic']['DungeonRoomID']
        if any(p.endswith('/DungeonRoom.engine__component__BlackboardInfo.gyml') for p in g.get('Blackboards',[])):return default_room
        return None
    maps = rom.byml(f'{BASE}/MapParam.byml.zs')
    params = {p.name.removesuffix(BANC_SUFFIX): rom.byml(p.as_posix())
              for p in rom.files('Banc/GameBancParam', f'*{BANC_SUFFIX}')}
    ids = {name: i for i, name in enumerate(sorted(set(params) | set(maps)), 1)}
    result = {'schema': 1, 'coordinate_system': 'game XYZ; floors are MapParam.Floor indices',
              'route_kind': 'schematic room/portal graph, not collision-safe navigation',
              'scenes': [], 'nodes': [], 'edges': [], 'anchors': [], 'sources': [], 'room_map': []}
    nodes, edges, anchors = (result[k] for k in ('nodes', 'edges', 'anchors'))

    def node(scene, p, floor, room, kind, actor=0):
        index = len(nodes)
        nodes.append(dict(id=index, xyz=list(p), scene=scene, floor=floor, room=room, kind=kind, actor=actor))
        return index

    def edge(a, b, kind=WALK, condition=FREE, gate=0, chain=0, action='沿当前房间前往通道', source='MapParam.Room.Entrance', reverse=False):
        record = dict(source=source, from_node=a, to_node=b, kind=kind, condition=condition,
                      gate_actor=gate, chain_actor=chain, action=action)
        edges.append(record)
        if reverse:
            reverse_action = {CLIMB:'沿同一梯子或攀爬通道返回，确认落脚点', LIFT:'等待同一升降平台，乘回另一端',
                              SWIM:'检查当前水位，沿水道反向潜行或上浮', STAIRS:'沿同一楼梯或斜坡返回',
                              HOOKSHOT:'确认返程靶点或落脚处，再沿来路返回'}.get(kind,action)
            edges.append(dict(record, from_node=b, to_node=a,action=reverse_action))

    for name in DUNGEONS:
        row, scene = maps[name], ids[name]
        param = params[name]
        base = param['Banc']['Main'].removeprefix('Work/Banc/Scene/').removesuffix('.bcett.json')
        actors = {}
        groups = []
        for part in ('Static', 'Dynamic'):
            path = f'Banc/{base}_{part}.bcett.byml.zs'
            raw = rom.read_raw(path)
            result['sources'].append(dict(path=path, sha256=sha256(raw).hexdigest()))
            data = rom.byml(path)
            actors.update((a['Hash'], a) for a in data.get('Actors', []))
            groups.extend(data.get('AiGroups', []))
        start_node, start_edge, start_anchor = len(nodes), len(edges), len(anchors)
        # Live WorldInfo uses raw room IDs. MapParam's array is sparse/compacted
        # in some scenes (castle final room is raw 63), so normalize by exact
        # centre/entrance identities, never by the player's nearest centre.
        raw_candidates = defaultdict(set)
        map_entrance_room = {e['InstanceID']:ri for ri,r in enumerate(row['Room']) for e in r.get('Entrance',[])}
        for g in groups:
            raw = group_raw(g)
            if raw is None: continue
            hits=set()
            for ref in g.get('References',[]):
                identity=ref['Reference']
                if identity in map_entrance_room:hits.add(map_entrance_room[identity])
                actor=actors.get(identity,{})
                if actor.get('Gyaml')=='DungeonRoomCenterAnchor':
                    hits.update(ri for ri,r in enumerate(row['Room']) if position(r.get('CenterTrans')) and dist(r['CenterTrans'],actor['Translate'])<.05)
            if len(hits)==1:raw_candidates[raw].update(hits)
        raw_rooms={raw:next(iter(hits)) for raw,hits in raw_candidates.items() if len(hits)==1}
        result['room_map'].extend(dict(scene=scene,raw_room=raw,room=ri) for raw,ri in sorted(raw_rooms.items()))
        rooms, portals = {}, {}
        actor_room = {}
        for ri, room in enumerate(row['Room']):
            center = position(room.get('CenterTrans'))
            if center is None: continue
            fs = room_floors(row, room)
            for floor in fs:
                if not 0 <= floor < len(row['Floor']): raise ValueError(f'Invalid floor: {name}/{ri}')
                rooms[ri, floor] = node(scene, center, floor, ri, NODE_ROOM)
            for entry in room.get('Entrance', []):
                p, identity = position(entry.get('Trans')), entry['InstanceID']
                if p is None or identity not in actors: raise ValueError(f'Missing portal actor: {name}/{identity}')
                if dist(p, actors[identity]['Translate']) > .05: raise ValueError(f'Portal moved: {name}/{identity}')
                floor = min(fs, key=lambda f: abs(f-floor_at(row, p)))
                ni = node(scene, p, floor, ri, NODE_ENTRANCE, identity)
                portals[identity] = ni
                actor_room[identity] = ri
                edge(rooms[ri, floor], ni, reverse=True)
        for g in groups:
            refs = g.get('References', [])
            possible = {actor_room[v['Reference']] for v in refs if v['Reference'] in actor_room}
            explicit = raw_rooms.get(group_raw(g))
            if explicit is not None: possible.add(explicit)
            if len(possible) == 1:
                ri = next(iter(possible))
                for ref in refs: actor_room.setdefault(ref['Reference'], ri)
        # MapParam omits several perfectly real rooms' entrance arrays (Jabu
        # 2/7/12/17, Fire 24, etc.). Recover ONLY references explicitly owned
        # by a Banc DungeonRoomID; coordinates alone never assign ownership.
        for g in groups:
            ri = raw_rooms.get(group_raw(g))
            if ri is None or not 0 <= ri < len(row['Room']): continue
            room = row['Room'][ri]
            for ref in g.get('References', []):
                actor = actors.get(ref['Reference'], {})
                if actor.get('Gyaml') != 'DungeonRoomArea' or actor['Hash'] in portals: continue
                p = actor['Translate']
                fs = room_floors(row, room) if room.get('CenterTrans') else [floor_at(row,p)]
                floor = min(fs,key=lambda f:abs(f-floor_at(row,p))) if room.get('Floor') else floor_at(row,p)
                if (ri,floor) not in rooms:
                    center = room.get('CenterTrans',p)
                    rooms[ri,floor] = node(scene,center,floor,ri,NODE_ROOM)
                ni = node(scene,p,floor,ri,NODE_ENTRANCE,actor['Hash'])
                portals[actor['Hash']] = ni
                actor_room[actor['Hash']] = ri
                edge(rooms[ri,floor],ni,source='Banc AiGroup.Dynamic.DungeonRoomID + DungeonRoomArea reference',reverse=True)
        for actor in actors.values():
            explicit = raw_rooms.get(actor.get('Dynamic', {}).get('DefaultDungeonRoomIndex'))
            if explicit is not None: actor_room[actor['Hash']] = explicit
            label = actor_label(actor['Gyaml'])
            if label and position(actor.get('Translate')):
                p = actor['Translate']; ri = actor_room.get(actor['Hash'], -1)
                anchors.append(dict(xyz=p, scene=scene, floor=floor_at(row,p), room=ri,
                                    kind=NODE_MECHANISM, actor=actor['Hash'], label=label,
                                    gyaml=actor['Gyaml'], linked_actors=[v['Dst'] for v in actor.get('Links', [])]))

        # Map doorway identities, and preserve chain/bars even when the
        # corresponding live flag is unavailable. Linked shutter leaf actors
        # carry the explicit rooms on both sides of a physical door.
        doors = [(di, door) for di, layer in enumerate(row['Floor']) for door in layer.get('Door', [])]
        connected = set()
        for di, door in doors:
            actor = actors.get(door['InstanceID'])
            if actor is None: raise ValueError(f'Missing door: {name}/{door["InstanceID"]}')
            linked = [actors.get(v['Dst'], {}) for v in actor.get('Links', [])]
            sides = {raw_rooms.get(v.get('Dynamic', {}).get('DefaultDungeonRoomIndex')) for v in linked
                     if 'Shutter' in v.get('Gyaml', '')}
            sides.discard(None)
            # Some corridors have no MapParam entrance on one side. The door
            # itself still references physical shutter leaves with both room
            # identities. Reuse those real positions, rather than inventing a
            # centre-to-centre edge across an unobserved gap.
            if len(sides)==2:
                for side in sorted(sides):
                    if any(nodes[ni]['room']==side and dist(door['Trans'],nodes[ni]['xyz'])<=6 for ni in portals.values()): continue
                    leaves=[v for v in linked if raw_rooms.get(v.get('Dynamic',{}).get('DefaultDungeonRoomIndex'))==side and 'Shutter' in v.get('Gyaml','')]
                    if not leaves:continue
                    leaf=min(leaves,key=lambda v:dist(v['Translate'],door['Trans']))
                    p=leaf['Translate']; fs=room_floors(row,row['Room'][side]); floor=min(fs,key=lambda f:abs(f-floor_at(row,p)))
                    if (side,floor) not in rooms:rooms[side,floor]=node(scene,row['Room'][side].get('CenterTrans',p),floor,side,NODE_ROOM)
                    ni=node(scene,p,floor,side,NODE_ENTRANCE,leaf['Hash']);portals[leaf['Hash']]=ni
                    edge(rooms[side,floor],ni,source='Banc door Reference -> shutter leaf explicit room',reverse=True)
            possible = sorted((dist(door['Trans'], nodes[ni]['xyz']), ni)
                              for ni in portals.values())
            near = [ni for gap, ni in possible if gap <= 6 and (not sides or nodes[ni]['room'] in sides)]
            if len({nodes[ni]['room'] for ni in near}) < 2:
                near = [ni for gap, ni in possible if gap <= 5]
            if not near: continue
            first = near[0]
            second = next((ni for ni in near if nodes[ni]['room'] != nodes[first]['room']), None)
            if second is None: continue
            chain = door.get('ChainLockHash', 0)
            barred = any(v.get('Name', '').startswith('SwitchShutter') or v.get('Gyaml', '').endswith('Shutter_A_02') for v in linked)
            condition = (BOSS_KEY if door.get('IsBossRoom') else SMALL_KEY) if chain else MECHANISM_GATE if barred else ORDINARY_DOOR
            action = ('使用首领钥匙打开门' if condition == BOSS_KEY else '检查小钥匙并打开锁门' if condition == SMALL_KEY
                      else '检查门闩与关联机关，门打开后通过' if condition == MECHANISM_GATE else '打开门并通过')
            edge(first, second, DOOR, condition, actor['Hash'], chain, action,
                 'MapParam.Floor.Door + Banc door/linked shutter identities', True)
            connected.add(frozenset((first, second)))

        # Only pair mutually closest entrance triggers on the SAME floor.
        # Cross-floor triggers are handled exclusively by authored evidence.
        pi = list(portals.values())
        nearest = {}
        for ni in pi:
            n = nodes[ni]
            options = [(dist(n['xyz'], nodes[nj]['xyz']), nj) for nj in pi
                       if nodes[nj]['room'] != n['room'] and nodes[nj]['floor'] == n['floor']]
            nearest[ni] = min(options, default=(float('inf'), -1))
        for ni in pi:
            gap, nj = nearest[ni]
            if ni >= nj or gap > 5 or nearest[nj][1] != ni or frozenset((ni,nj)) in connected: continue
            nearby_doors = [door for _, door in doors if dist(door['Trans'], nodes[ni]['xyz']) <= 4]
            if nearby_doors: continue  # Do not turn an unresolved door into a free edge.
            edge(ni, nj, action='穿过当前入口进入相邻房间', reverse=True)

        context = dict(name=name, scene=scene, row=row, actors=actors, rooms=rooms, portals=portals,
                       actor_room=actor_room, node=node, edge=edge, nodes=nodes)
        add_authored_transitions(context)
        by_gate = {door['InstanceID']:door for _,door in doors}
        for e in edges[start_edge:]:
            e['conditions']=[]
            e['condition_mode']='all'
            e['requirements']=[]
            door=by_gate.get(e['gate_actor'])
            if door and door.get('ChainLockHash'):
                e['chain_actor']=door['ChainLockHash']
                e['condition']=BOSS_KEY if door.get('IsBossRoom') else SMALL_KEY
                e['conditions']=[game_data.chain_open(e['gate_actor'])]
                e['available_key']=game_data.dungeon_inventory(name,'IsGetBossKey' if door.get('IsBossRoom') else 'SmallKeyNum',1,'eq' if door.get('IsBossRoom') else 'ge')
            if e['kind']==SWIM:
                # Exact value -> height semantics are not yet proven. Do not
                # silently interpret the integer as a particular water level.
                e['condition']=ACTION_REQUIRED
                e['requirements']=['确认水位与目的平台相符；按动作使用重铁靴']
                e['observed_state']=[game_data.condition('WaterTemple_Room00_WaterLevel',kind='Int')] if name=='WaterTemple' else []
            if e['kind']==HOOKSHOT:
                e['requirements'].append('持有适用钩索，确认靶点与返程落脚处')
                if e['condition']==FREE:e['condition']=ACTION_REQUIRED
        within_room = sorted({actor_room.get(door['InstanceID'],-1) for _,door in doors
                              if door.get('ChainLockHash') and not any(
                                  e['gate_actor']==door['InstanceID'] for e in edges[start_edge:])} - {-1})
        # The map room can contain several internal gates or large obstacles.
        # It must not be interpreted as one collision-free straight line.
        within_room = sorted(set(within_room) | set(UNSAFE_ROOMS.get(name,())))
        result['scenes'].append(dict(name=name, scene=scene, min_floor=row['MinFloor'],
                                    floors=len(row['Floor']), first_node=start_node, node_count=len(nodes)-start_node,
                                    first_edge=start_edge, edge_count=len(edges)-start_edge,
                                    first_anchor=start_anchor, anchor_count=len(anchors)-start_anchor,
                                    unsafe_rooms=within_room))
    result['sources'].append(dict(path=f'{BASE}/MapParam.byml.zs', sha256=sha256(rom.read_raw(f'{BASE}/MapParam.byml.zs')).hexdigest()))
    result['coverage'] = [dict(name=s['name'],scene=s['scene'],floors=s['floors'],
                              cross_floor_edges=sum(nodes[e['from_node']]['floor']!=nodes[e['to_node']]['floor']
                                                    for e in edges[s['first_edge']:s['first_edge']+s['edge_count']]),
                              authored_edges=sum(e['source'].startswith('authored:')
                                                 for e in edges[s['first_edge']:s['first_edge']+s['edge_count']]),
                              unsafe_rooms=s['unsafe_rooms']) for s in result['scenes']]
    return result


def add_authored_transitions(ctx):
    """Bounded, reviewed exceptions. See records below; no proximity fallback."""
    def endpoint(value):
        if isinstance(value,int):
            if value not in ctx['portals']: raise ValueError(f'Missing authored portal: {ctx["name"]}/{value:x}')
            return ctx['portals'][value]
        identity,ri,floor = value
        actor = ctx['actors'].get(identity)
        if actor is None: raise ValueError(f'Missing authored actor: {ctx["name"]}/{identity:x}')
        key = (ri,floor)
        if key not in ctx['rooms']:
            p = ctx['row']['Room'][ri].get('CenterTrans',actor['Translate'])
            ctx['rooms'][key] = ctx['node'](ctx['scene'],p,floor,ri,NODE_ROOM)
        ni = ctx['node'](ctx['scene'],actor['Translate'],floor,ri,NODE_MECHANISM,identity)
        ctx['edge'](ctx['rooms'][key],ni,source='authored: reviewed actor room/floor assignment',reverse=True)
        return ni

    for spec in AUTHORED.get(ctx['name'], []):
        a_hash, b_hash, kind, gate, action, source, reverse = spec
        a, b = endpoint(a_hash),endpoint(b_hash)
        if gate and gate not in ctx['actors']: raise ValueError(f'Authored gate changed: {gate:x}')
        ctx['edge'](a,b,kind,MECHANISM_GATE if gate else FREE,gate,0,action,source,reverse)


UNSAFE_ROOMS = {'GerudoTrainingGround': (8,), 'WaterTemple': (0,1,5,6,8,10,17),
                'ShadowTemple': (9,17), 'ForestTemple': (6,27), 'FireTemple': (10,21),
                'InsideJabuJabuBelly': (2,7), 'SpiritTemple': (7,27)}


AUTHORED = {
    'InsideTheDekuTree': [
        (0xeed1aabf47bfbe81,0x91d535d3f6581f65,DROP,0x03de66423437a955,
         '到三层步道后对准中央蛛网跳下，击破后落入地下一层',
         'authored: room0 actual 3F portal eed1aabf47bfbe81 at Y119.2888 is the jump approach; room4 basement trigger is the arrival; horizontal SpiderWeb actor is the gate, not a standing point; https://zeldacentral.com/games/ocarina-of-time-remake/walkthrough/great-deku-tree/',False),
        (0x18d6009481916112,0x095d49c8f8c9e2e6,DROP,0x7fec388ff47465ad,
         '点燃木棒烧穿地面蛛网，再落到下层水池',
         'authored: MapParam room4/9 vertical triggers + horizontal SpiderWeb actor; https://zeldacentral.com/games/ocarina-of-time-remake/walkthrough/great-deku-tree/',False),
    ],
}

# The following records are authored topology, cross-checked against the
# current Switch 2 walkthroughs and the exact local entrance/actor identities.
# They deliberately do not claim to be sampled collision paths.  Every row
# names a concrete movement mechanism; Room.Floor alone is never sufficient.
GUIDES = {
    'InsideTheDekuTree': 'https://zeldacentral.com/games/ocarina-of-time-remake/walkthrough/great-deku-tree/',
    'DodongoCavern': 'https://lobby.loaded.com/game-guides/post/ocarina-of-time-remake-dodongos-cavern-walkthrough-n4Axycyj3PbAVvi',
    'InsideJabuJabuBelly': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-lord-jabu-jabu-belly-walkthrough-switch-2',
    'ForestTemple': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-forest-temple-walkthrough-switch-2',
    'FireTemple': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-fire-temple-walkthrough-switch-2',
    'WaterTemple': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-water-temple-walkthrough-switch-2',
    'ShadowTemple': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-shadow-temple-walkthrough-switch-2',
    'SpiritTemple': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-spirit-temple-walkthrough-twinrova-switch-2',
    'BottomOfTheWell': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-bottom-of-the-well-walkthrough-switch-2',
    'GerudoTrainingGround': 'https://questfern.com/oot/guides/gerudo-training-ground-walkthrough/',
    'IceCavern': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-ice-cavern-walkthrough-switch-2',
    'InsideGanonCastle': 'https://www.nintendolife.com/guides/zelda-ocarina-of-time-inside-ganondorfs-castle-walkthrough-final-dungeon-last-boss-switch-2',
}


def authored(scene,a,b,kind,action,*,gate=0,reverse=True,evidence='reviewed MapParam/Banc endpoint identities'):
    AUTHORED.setdefault(scene,[]).append((a,b,kind,gate,action,'authored: '+evidence+'; '+GUIDES[scene],reverse))


# Deku tree: main hall spiral ascent and climbable wall. The web drops above
# remain one-way and independently gated.
authored('InsideTheDekuTree',0x1274cf8e4a5d9d30,0x65dd5ecb79f5e862,CLIMB,'沿大厅藤蔓和环形步道往返一层与二层')
authored('InsideTheDekuTree',0x65dd5ecb79f5e862,0xeed1aabf47bfbe81,CLIMB,'先清除藤蔓上的蜘蛛，再攀爬到上层步道')
# The second room's falling ladder is an intra-floor landmark, NOT a new
# floor connection merely because its hanging actor is above a threshold.

# Dodongo: ring of bomb flowers identifies the staircase room unambiguously.
authored('DodongoCavern',0xd1f77cf80ffd0593,0xaea81eb2ca1d8452,STAIRS,'在炸弹花缺口引爆连锁，楼梯降下后上楼',gate=0x0c7df998ee4180e1,
         evidence='room10 BombFlower ring + Obj_DodongoCave_BrokenStair_A_01')
authored('DodongoCavern',(0x562f2db3e8559542,1,0),0x3f37a5fe59e50d09,LIFT,'开启上层地面开关后，乘大厅平台往返上下层',gate=0x2d7d78a8bc38ec60)
authored('DodongoCavern',0x42c0e090b0f972cd,0xcf1b3c16168c8bc4,CLIMB,'沿火墙房的台阶上到踏脚平台，射击眼睛开关后继续',gate=0xe9809a0f3155f0ba)

# Jabu: the Ruto cinematic anchors and lift actor are already used by the
# existing reviewed jabu_map.py; Room2's entrance omission is recovered above.
authored('InsideJabuJabuBelly',(0x530456ccfee25875,2,1),(0x972867af099bd11b,3,0),DROP,'跟随露朵从洞口落下，到下层与她交谈',reverse=False,
         evidence='RutoHole DestinationAnchor -> RutoBelow AnchorAction2')
authored('InsideJabuJabuBelly',0xe7c0342dd96bfdc7,0x59f1b8b61a439b69,LIFT,'等待漂浮平台降下，带着露朵乘回一层')
authored('InsideJabuJabuBelly',0x82a9a443125d33c1,0x5b12c1177a7e4dd1,LIFT,'打败大章鱼后乘中央升降台上到高层',gate=0xe86cb93bc02db550,
         evidence='room6 ElevatorLift_A_02 MoveDistance=16.5; BigOcto arena')
authored('InsideJabuJabuBelly',(0x95ae9fcfc8b48537,17,2),(0xbf8625df7b8c6838,1,1),LIFT,'站上返回大厅的平台，随平台下降后重新定位',reverse=False)
# The north corridor is a single authored junction. Its room7 entrance array
# is missing from MapParam; these are real door/Area references, not centres.
authored('InsideJabuJabuBelly',0x4d1e07212b4cb5e4,(0xfb489dacd0d4c4ab,7,1),DOOR,'带露朵穿过北侧入口，进入分叉走廊',gate=0x2872798fb526a9d1,
         evidence='room2 north DungeonRoomArea + door 2872798fb526a9d1 + room7 AiGroup-owned entrance Area fb489dacd0d4c4ab; reviewed north-junction passage')
authored('InsideJabuJabuBelly',(0x935f742d25550dc5,7,1),0xcee41d1a91d0d45f,DOOR,'确认北端门闩解除后穿过入口',gate=0x8ffd43b31852956a,
         evidence='door 8ffd43b31852956a controller DefaultRoom8 references shutter leaf DefaultRoom7; MapParam room8 entrance')
authored('InsideJabuJabuBelly',(0x0bde53d812c543c5,7,1),0x7762c243e5a06e02,DOOR,'按走廊开关要求开门，再进入西侧回旋镖房',gate=0x0f7f479e27e1e3ba,
         evidence='reviewed west branch of room7 junction -> room9 boomerang room; actual door-linked east-facing shutter leaf, authored exterior room assignment')

# Forest: ladders/block room, the two staircases beside Poe paintings, and
# the two ends of the physical well. Main lift requires all four Poe flames.
authored('ForestTemple',0xae8f7f563cf2f862,0x11113c1eb574a224,CLIMB,'按地面箭头推动方块，利用梯子和方块登上二层')
authored('ForestTemple',0xa65692465c6aab80,0xe48eb34b3425744d,STAIRS,'沿幽灵画像房的楼梯往返上下层')
authored('ForestTemple',0x1453a5a93599e679,0x3711e3706744b67c,STAIRS,'沿另一侧画像房的楼梯往返上下层')
authored('ForestTemple',0xaff9f4ad8b4f4f0c,0xc616aa2a75bd1ad1,CLIMB,'井水排空后沿井壁梯子下到井底',gate=0,reverse=True)
authored('ForestTemple',0x77fa0a2d921e1593,0x9453cf350b0dc9b3,CLIMB,'沿井的另一端梯子返回庭院',reverse=True)
authored('ForestTemple',0xb2dc0c1b726d2427,0x1031785b778d7d23,LIFT,'四盏幽灵火焰归位后乘大厅中央电梯下行',gate=0xee839aab45c4c56e)
authored('ForestTemple',0x1031785b778d7d23,0xc80692dbbe55adea,LIFT,'继续乘中央电梯到地下旋转大厅',gate=0xee839aab45c4c56e)
authored('ForestTemple',0xc80692dbbe55adea,0xb902b98ccb97ffd1,LIFT,'电梯停稳后进入地下旋转大厅',gate=0xee839aab45c4c56e)

# Fire: two distinct lift shafts, timed climbing wall, and downward hammer
# chain. The pillar route must never be synthesized as an upward shortcut.
authored('FireTemple',(0xfb8b1302e803c602,21,0),0x57df931e03c01306,LIFT,'推方块到火柱上，站稳后随喷火升到二层',gate=0xfb8b1302e803c602,
         evidence='MovableBox TunnelStartY=119.85/TunnelEndY=125.9 + room4 upper portal')
authored('FireTemple',0xf3dc579093ec4575,0x97eb00880d315ba5,CLIMB,'移动方块登高，击打开关暂熄火墙，再爬上铁网',gate=0x944a40272bfdbb98)
authored('FireTemple',(0x1df7bfb3f044eb6d,24,2),0xd95541b91ae78ad8,LIFT,'击败火焰舞者后乘中央升降台到四层',gate=0xf4abfb38bdc1276c,
         evidence='room24 RiseFloor TunnelEndY=174.53 -> room12 shaft entrance Y173.3')
authored('FireTemple',0xd95541b91ae78ad8,0xfbdfcdd95d6ebfbe,CLIMB,'在开关上方射击或投弹，暂熄火墙后攀上五层',gate=0x3647b2451dc940ea)
authored('FireTemple',0x6cf5f9b91c32aa4a,0xaae155bde1f7aea7,DROP,'用巨锤击落大地板，跟随落到四层',gate=0x5a1c40f18aa9e90e,reverse=False)
authored('FireTemple',0x58ba3a84835ea62c,0x3ece5733e020419e,CLIMB,'沿竖井铁网攀爬至五层出口')
authored('FireTemple',0x13d370dc6aa50258,0x2bf2b6ab58e4b8db,DROP,'用巨锤击落地板，跟随落入下层',gate=0xcd380faa16ab9c27,reverse=False)
authored('FireTemple',0xcf5d84e1c6c02c4c,0x85c64281c100a4ef,DROP,'用巨锤击落中央柱和地板后下落',gate=0x717cde568e9a8c5f,reverse=False)
authored('FireTemple',0xfb5bbe9c8d625d61,0x218ace9b3bb57c13,DROP,'沿已击落的中央柱继续落向首领门大厅',gate=0x717cde568e9a8c5f,reverse=False)
authored('FireTemple',0x218ace9b3bb57c13,0xf8ae6c087c37f98c,DROP,'落到柱顶后返回一层首领门前',gate=0x608cedad0d35542c,reverse=False)

# Water: movement instructions carry the water-level requirement. This is a
# conditional swimming route, not an assertion that every floor is now wet.
authored('WaterTemple',0x757abfc0c492a77f,0x390cae03c4089896,SWIM,'把水位调到二层后脱下重铁靴上浮；下行时穿靴沉底')
authored('WaterTemple',0x390cae03c4089896,0xfcadbd3a461a7988,SWIM,'把水位调到三层后上浮到上层出口；下行时穿重铁靴')
authored('WaterTemple',0x95e221162596f2a2,0x904e98e09b902415,HOOKSHOT,'在中央柱内用钩索上到绿色水位标记所在平台')
authored('WaterTemple',0x786cf388769d9a51,0x357f190e648da125,SWIM,'中央柱浮台升起后穿重铁靴进入下方通道')
authored('WaterTemple',0xc30c5a188554c475,0x73e70f8474cf6f9a,SWIM,'沿水下通道穿靴下潜、在另一端脱靴上浮')
authored('WaterTemple',0x90f9ffcd141bc639,0x86a3d5b35a092f4d,LIFT,'击打开关升降水柱，站在盖板上再触发以升到三层')
authored('WaterTemple',0xd0aa549c7138cc3c,0xee36c543ab3d2c06,SWIM,'沿暗影林克后的水道下行，避开漩涡后重新定位',reverse=False)
authored('WaterTemple',0x757abfc0c492a77f,0x79918bd4c10002fb,SWIM,'穿重铁靴沿东侧一层水道前进，在竖井找到露朵',
         evidence='reviewed east 1F passage to Ruto shaft; actual room0/17 opposed DungeonRoomArea identities at Y100.5/100.0, no intervening door')
authored('WaterTemple',0x79918bd4c10002fb,(0x961836e54b2c4521,17,3),SWIM,'与露朵交谈后脱下重铁靴上浮到三层，在三角标记处降水位',
         evidence='reviewed Ruto shaft float to 3F; room17 lower entrance and actual upper Triforce CheckAttentionActor')

# Shadow: slope and lift shafts have exact paired room triggers. The ferry
# is an obstacle within room17, separately constrained in unsafe_rooms.
authored('ShadowTemple',0x553560d6f5d6f357,0x7d5af7af94546230,STAIRS,'沿下坡通道进入地下二层')
authored('ShadowTemple',0x4eb7448a3af8441f,0x53c293fa1541f03c,LIFT,'等待移动平台，在升降井中下降到地下三层')
authored('ShadowTemple',0x7e437258c1b37d2d,0xb6eecfff08cd01ff,LIFT,'乘断头台洞窟入口的升降台进入地下三层')
authored('ShadowTemple',0x4aac68ed1ecd29f2,0x7476d8965c45379c,LIFT,'乘升降台下到渡船港口')
authored('ShadowTemple',0x46d3d7e75fdc7dc3,0x095b36b3ad881afa,DROP,'从井道落到渡船港口；返回须先推箱建立捷径',reverse=False)

# Spirit: childhood climb, adult wall, staircase approaches to the two Iron
# Knuckles, moving climb wall, and the large statue room's upper galleries.
authored('SpiritTemple',0x0aa66361d399f259,0x928524ed8b4e8190,CLIMB,'清掉墙上蜘蛛后攀爬，炸开裂缝引入阳光')
authored('SpiritTemple',0x2f3baf9d63e37913,0x62d79ff04cbc9094,CLIMB,'清掉拦路敌人后沿远端墙面爬到二层')
authored('SpiritTemple',0xc353753cb5702ea1,0xacfd038aff0fdcbc,STAIRS,'沿铁甲战士前的楼梯上行')
authored('SpiritTemple',0xad823922b1cbeaa3,0xdacee8d2a51c499f,STAIRS,'沿成人侧铁甲战士前的楼梯上行')
authored('SpiritTemple',0xa5e81006539ddc0f,0x9f17ae4e0aa688f3,CLIMB,'用钩索攀上移动墙，继续向上越过滑动墙板')
authored('SpiritTemple',0xc869e26d71926501,0x7879f32eb91c0586,CLIMB,'移动巨石方块打开入口捷径，攀上上层通道',gate=0xdff7b0c3df35784b)
authored('SpiritTemple',0x080ea11fc2969a26,0x6a30f49d3af57158,STAIRS,'沿巨大石像侧面的楼梯登上回廊')
authored('SpiritTemple',0x49d55005a4f6d6ed,0xd9be85bfa7c1729e,HOOKSHOT,'用钩索和石像侧面通道到成人侧上层回廊')

# Well: genuine floor holes are directed downward; the identified exit ladder
# is bidirectional. Other optional holes are not treated as interchangeable.
authored('BottomOfTheWell',0x5e0bd6c5b4845bcb,0xb2d007f0f3ba69df,DROP,'用真实之眼确认中央地洞，再落到地下二层',reverse=False)
authored('BottomOfTheWell',0x36a2cfec2d305a89,0x350276946c19b68d,DROP,'从地板洞口落到下层通道',reverse=False)
authored('BottomOfTheWell',0xc9acc29f3b5552b9,0xc51a6cd0fc2ab15f,CLIMB,'收集银卢比开门后，沿西侧梯子爬回地下一层')
authored('BottomOfTheWell',0xbec0ff73dc0dfb11,0xeb2eced77a63c3e8,CLIMB,'击败死亡之手后穿过南侧假墙，沿两段梯子返回上层')

# Training ground: current remake uses the scarecrow above the drained lava
# statue. Do NOT add the old N64 central-ceiling shortcut to the locked cages.
authored('GerudoTrainingGround',0x6c316f721d5c74b7,0x65b9928be42e206f,HOOKSHOT,'清理狼群并查看隐形通道，用长钩索上到高处出口')
authored('GerudoTrainingGround',0xd5bd3d13a9a4472c,0x97cce9bb280b0ca8,HOOKSHOT,'射击石像眼睛退去熔岩，召出稻草人后用长钩索上高台',gate=0x45a947dc63f3933b)

# Castle tower's room-local stairs are explicit in the remake route; battles
# and locked door edges remain separate and must still be satisfied.
# These two actual trial doors are absent from MapParam.Floor.Door. Keeping
# the Banc controller prevents their close entrance triggers becoming free.
authored('InsideGanonCastle',(0x97a4e8f1c5df78b1,6,0),0xd9f3eb6770b0bcb4,DOOR,'解除试炼门闩后穿过入口',gate=0x8334a2ff30341f78,
         evidence='Banc controller 8334a2ff30341f78 references shutter leaves with explicit rooms6/7; room7 entrance')
authored('InsideGanonCastle',0x788cc4bb2bba38c9,0x8b5331fd3ec5d7ba,DOOR,'解除试炼门闩后穿过入口',gate=0x23869884ffc509e4,
         evidence='MapParam room12/14 opposed entrances 1.74m apart at Y99.76/99.70; actual intervening Banc shutter controller 23869884ffc509e4')
for a,b in [(0x38fcbfee31e32dd8,0xa1a4ff9d9c4592a6),(0x8bb696ff0b3bb152,0xa58cbbe1d4836ca1),
            (0x73adb4050be66471,0x83a93f0f7943b554),(0x9d7b8cf67edb5c55,0xbea4e32b062bea5f),
            (0x604a0b7aa31f7df5,0x729243617c54c2d7)]:
    authored('InsideGanonCastle',a,b,STAIRS,'清理本层敌人、确认门已打开后，沿中央塔楼梯继续上行')

# Additional main-route links whose two entrances are separated by a long
# hall, or where MapParam omitted one side entirely. Door identities remain
# attached to these edges, so the longer connection cannot bypass a lock.
authored('ForestTemple',0x9273d440b2c39da6,0x36c68f258554084e,CLIMB,'沿推箱房的梯子到中层，按地面箭头继续推箱')
authored('ForestTemple',0x3a8faca80e9af03b,0xb2bf0b13572f93da,CLIMB,'利用已就位的方块和梯子爬上高层出口')
authored('ForestTemple',0x9b064bb8e2183b47,0xb9988d138d62f527,WALK,'沿扭曲走廊前进；改变走廊状态后重新确认出口')
authored('InsideGanonCastle',(0x45024f1813142f25,1,0),0x38fcbfee31e32dd8,LIFT,'解除六道结界后进入中央塔，乘升降台上行',gate=0x6d02eb308237ddc8,
         evidence='ElevatedFloor MoveDirection -Y, MoveDistance26.4, top Y128.43 + lower room1 and upper room19')
authored('InsideGanonCastle',0x729243617c54c2d7,0x08fbdef0f2416de6,STAIRS,'沿最后一段塔楼梯上行，用首领钥匙打开顶层门',gate=0x3f687b9542cacfb6)
authored('IceCavern',0x28a239d7f231bc87,0xc6193aa50f711fbe,WALK,'用瓶中蓝火融化红冰，穿过通道进入滑块房',gate=0xa981fb07a128d53b)


def generate_dungeon_geometry(rom, out):
    out = Path(out)
    data = build_dungeon_geometry(rom)
    out.mkdir(parents=True, exist_ok=True)
    (out/'dungeon_geometry.generated.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    f = lambda v:f'{v:.5f}f'
    w = lambda v:'L'+json.dumps(v,ensure_ascii=False)
    lines = [HEADER, 'static constexpr HkDungeonNode hkDungeonNodes[] = {']
    for n in data['nodes']:
        lines.append('    {'+', '.join([*(f(v) for v in n['xyz']),*(str(n[k]) for k in ('scene','floor','room','kind')),f'0x{n["actor"]:016x}ull'])+'},')
    lines.append('};\nstatic constexpr HkDungeonEdge hkDungeonEdges[] = {')
    for e in data['edges']:
        lines.append('    {'+', '.join([*(str(e[k]) for k in ('from_node','to_node','kind','condition')),f'0x{e["gate_actor"]:016x}ull',f'0x{e["chain_actor"]:016x}ull',w(e['action'])])+'},')
    lines.append('};\nstatic constexpr HkDungeonAnchor hkDungeonAnchors[] = {')
    for n in data['anchors']:
        lines.append('    {'+', '.join([*(f(v) for v in n['xyz']),*(str(n[k]) for k in ('scene','floor','room','kind')),f'0x{n["actor"]:016x}ull',w(n['label'])])+'},')
    lines.append('};\n')
    lines.append('static constexpr HkDungeonRoomMap hkDungeonRoomMaps[] = {')
    for entry in data['room_map']:
        lines.append(f'    {{{entry["scene"]}, {entry["raw_room"]}, {entry["room"]}}},')
    lines.append('};\n')
    (out/'dungeon_geometry.generated.h').write_text('\n'.join(lines),encoding='utf-8')
    return data
