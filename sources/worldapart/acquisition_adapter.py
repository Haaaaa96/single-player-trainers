"""Acquire real inventory instances through BagModel.AddItem on Unity's thread.

Frida is loaded once per game process and retained until that process exits.
Each request installs one temporary A1Main.Update listener for one native call.
The game creates the item subtype, UID, timestamps, stack splitting and events.
There is no direct item-ID substitution, direct collection write or auto retry.
"""
from pathlib import Path
import json
import math
import sys
import threading
import time
import uuid
import weakref

HERE = Path(__file__).resolve().parent
from runtime_paths import initialize_runtime
sys.path.insert(0, str(HERE / 'vendor'))
from acquisition_catalog import (CURRENCY_ADD_MAXIMUM, CURRENCY_BALANCE_MAXIMUM,
                                 LARGE_CURRENCY_IDS, SPIRIT_STONE_ADD_MAXIMUM,
                                 read_catalogue)
from native_write import process_identity
from write_guard import Refused, UncertainWrite
from item_categories import category_name

MAX_ADD_QUANTITY = 999
ATTACH_FAILURE_MESSAGE = (
    '游戏连接组件加载失败，本次添加尚未调用游戏方法。'
    '已停用创建新物品；已有堆叠仍可在非战斗状态下补充数量。'
    '重新连接修改器也不会自动重试。'
    '请先检查游戏状态并保留日志，等待修复后再恢复获取。'
)
# A timed-out bridge must stay alive even if the UI disconnects. It is released
# only after a late terminal message or process/session termination is observed.
_RETAINED_BRIDGES = set()
_LIVE_BRIDGES = weakref.WeakSet()


class AcquisitionLimitRefused(Refused):
    """An input/balance limit rejected before any acquisition write or call."""
    write_attempted = False


def native_calls_pending():
    """True while any bridge might still enter or be inside a native game call."""
    return any(getattr(bridge, '_native_inflight', False)
               for bridge in set(_LIVE_BRIDGES) | _RETAINED_BRIDGES)

METHODS = {
    'add': ('AddItem', 0x06015191, 0xE9BDD0, 5),
    'currency_stack': ('ResolveItemStackMax', 0x0601519F, 0xEA0FD0, 2),
    'remove_test_uid': ('RemoveByUid', 0x060151C2, 0xEA0700, 2),
}
METHOD_SPECS = {
    'add': dict(name='AddItem', token=0x06015191, rva=0xE9BDD0,
                argc=5, returns=0x12, prefix='44894c24204489442418895424104889'),
    'currency_stack': dict(name='ResolveItemStackMax', token=0x0601519F, rva=0xEA0FD0,
                           argc=2, returns=8, prefix='48895c24105556574883ec50803d3989'),
}


def _validated_process_identity(value):
    """Return only a complete process lifetime, never a PID-only approximation."""
    if not isinstance(value, dict):
        return None
    fields = ('pid', 'process_creation_filetime')
    if any(type(value.get(key)) is not int or value[key] <= 0 for key in fields):
        return None
    return {key: value[key] for key in fields}


def _connected_process_identity(game):
    try:
        return _validated_process_identity(dict(
            pid=game.resolver.reader.pid, process_creation_filetime=game.stamp[1]))
    except (AttributeError, TypeError, IndexError):
        return None


def require_no_unmanaged_agent(resolver):
    """Do not reinitialize an agent left behind by an older trainer instance."""
    checked = set()
    try:
        for region in resolver.reader.iter_regions():
            if region['type'] != 0x1000000:  # MEM_IMAGE
                continue
            allocation = region['allocation']
            if allocation in checked:
                continue
            checked.add(allocation)
            path = resolver.reader.mapped(allocation)
            if not path:
                raise Refused('无法核对游戏已加载模块，已拒绝原生连接。')
            name = path.replace('\\', '/').rsplit('/', 1)[-1].casefold()
            if name.startswith('frida-agent') and name.endswith('.dll'):
                raise Refused('游戏中已有不能复用的原生连接组件；请先保存并重启游戏，'
                              '避免再次加载导致闪退。')
        if not checked:
            raise Refused('未读取到游戏模块，已拒绝原生连接。')
    except Refused:
        raise
    except Exception as error:
        raise Refused('无法核对原生连接状态，未尝试注入。') from error


def native_connection_block_reason(game):
    """Explain an unavailable shared connection without loading an agent."""
    from native_acquisition_session import check_connection_available
    from runtime_paths import SAFETY_LOG_ROOT
    identity = _connected_process_identity(game)
    if identity is None:
        return '无法核对当前游戏进程，原生功能暂不可用。'
    try:
        check_connection_available((identity['pid'], identity['process_creation_filetime']),
            SAFETY_LOG_ROOT / 'acquisition-native-epochs.json',
            lambda: require_no_unmanaged_agent(game.resolver))
    except Refused as error:
        return str(error)
    return ''


def catalog_rows(data):
    rows = []
    for item in data['items']:
        name = item['names'].get('zh-Hans') or item['names'].get('en-US') or f"物品 {item['id']}"
        kind = category_name(item)
        # Auto-used records apply their effects rather than creating an inventory
        # instance, so their postcondition cannot be checked by an item-count test.
        reason = '获得时会自动使用，暂未验证其效果与回退。' if item['auto_use'] is True else ''
        if item.get('hide_in_bag') and item['item_type_id'] != 5:
            reason = '隐藏的系统或剧情计数，暂不作为可获取物品。'
        if name in ('未知功法', 'Unknown Art', '未知的物品', '未知物品', 'Unknown Item',
                    '未知法宝器胚', '未知法宝', '未知的丹药'):
            reason = '游戏配置中的占位条目，尚未确认有效用途。'
        if not 1 <= item['max_count_per_grid'] <= 2147483647:
            reason = '物品配置上限无效。'
        special = item['item_type_id'] in (3, 16, 93, 95)
        large_currency = (type(item['id']) is int and item['id'] in LARGE_CURRENCY_IDS
                          and type(item['item_type_id']) is int and item['item_type_id'] == 5
                          and not reason)
        currency_add_maximum = (SPIRIT_STONE_ADD_MAXIMUM if item['id'] == 50000
                                else CURRENCY_ADD_MAXIMUM)
        rows.append(dict(id=item['id'], name=name, type_name=kind,
                         item_type_id=item['item_type_id'],
                         stack_limit=item['max_count_per_grid'],
                         config_stack_limit=item['max_count_per_grid'],
                         # Estimated only. Actual game AddItem computes the limit.
                         may_split_single=special,
                         can_add=not reason, supported=not reason, reason=reason,
                         large_currency=large_currency,
                         balance_maximum=(min(CURRENCY_BALANCE_MAXIMUM, item['max_count_per_grid'])
                                          if large_currency else None),
                         max_quantity=(min(currency_add_maximum, item['max_count_per_grid'])
                                       if large_currency else 256 if special else MAX_ADD_QUANTITY),
                         names=item['names']))
    return rows


class AcquisitionAdapter:
    def __init__(self, game_adapter):
        self.game = game_adapter
        self._catalog = None
        self._catalog_data = None
        self._lock = threading.Lock()
        self._session = None
        self._script = None
        self._connection = None
        self._native_inflight = False
        _LIVE_BRIDGES.add(self)
        self.blocked = False
        self.blocked_reason = '上次获取结果尚未确认，请先核对背包及获取日志。'
        self.native_block_reason = None
        self.native_block_identity = None
        self.safety_logs = initialize_runtime(HERE)
        self.journal = self.safety_logs / 'acquisition-pending.json'
        if self.journal.exists():
            prior = json.loads(self.journal.read_text(encoding='utf8'))
            self.native_block_reason = prior.get('native_block_reason') or None
            origin = prior.get('native_block_identity')
            if prior.get('status') in ('attaching', 'attach_failed'):
                self.native_block_reason = ATTACH_FAILURE_MESSAGE
                if origin is None:
                    # Older attach journals recorded identity only at top level.
                    origin = prior
            elif prior.get('status') not in ('verified', 'rejected', 'cancelled', 'not_dispatched'):
                self.blocked = True
            self.native_block_identity = _validated_process_identity(origin)
            current_identity = _connected_process_identity(self.game)
            if (not self.blocked and self.native_block_reason and
                    self.native_block_identity is not None and current_identity is not None and
                    self.native_block_identity != current_identity):
                # A failed attachment cannot affect a new process lifetime.
                # Unknown/pending writes remain globally blocked even after a
                # restart; only the clearly scoped native-only block is released.
                self.native_block_reason = None
                self.native_block_identity = None

    def catalog(self, refresh=False):
        if self._catalog is None or refresh:
            rr = self.game.resolver
            if rr is None or process_identity(rr.reader.h) != self.game.stamp:
                raise Refused('游戏连接已变化，请重新连接。')
            data = read_catalogue(rr.reader.pid)
            if data['process_creation_filetime'] != self.game.stamp[1]:
                raise Refused('物品目录来自其他游戏进程。')
            self._catalog_data = data
            self._catalog = catalog_rows(data)
        return list(self._catalog)

    list_catalog = catalog

    def _record(self, event):
        event = dict(event)
        if getattr(self, 'native_block_reason', None):
            # A later successful no-injection edit must not erase an earlier
            # native attachment failure and accidentally re-enable injection.
            event['native_block_reason'] = self.native_block_reason
            event['native_block_identity'] = getattr(self, 'native_block_identity', None)
        self.journal.parent.mkdir(exist_ok=True)
        # Keep the last safety state intact if a write is interrupted. An
        # unfinished attach must survive a trainer restart as a blocked state.
        temporary = self.journal.with_name(self.journal.name + '.' + uuid.uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(event, ensure_ascii=False, indent=2), encoding='utf8')
        temporary.replace(self.journal)
        self.game.record(dict(acquisition=event))

    def _current(self):
        if self.game.resolver is None or process_identity(self.game.resolver.reader.h) != self.game.stamp:
            raise Refused('游戏进程或连接已变化。')
        raw = self.game.resolver.resolve()
        if not raw['anchor_verified']:
            raise Refused('未确认当前角色。')
        return raw

    def _mark_uncertain(self, event):
        self.blocked = True
        if getattr(self, '_native_inflight', False):
            _RETAINED_BRIDGES.add(self)
        try:
            self._record(dict(event, status='unknown'))
        except Exception:
            # The in-memory block is unconditional, including disk-full or a
            # disconnected log folder. Never let a logging failure permit retry.
            pass

    @staticmethod
    def _item_total(raw, item_id):
        return sum(i['count'] for i in raw['items'] if i['item_id'] == item_id)

    def _method(self, raw, operation):
        rr = self.game.resolver
        k = rr.q(raw['bag'])
        c = rr.verify_class(k, 'Game.Model.Components.BagModel')
        if operation in METHOD_SPECS:
            from types import SimpleNamespace
            import struct
            import probe
            from native_method_profiles import resolve_reviewed_method
            # The base inventory resolver uses a different anchor interface.
            # Keep this proof local and include it in the same broker request.
            proof = []
            def anchor(address, size):
                data = rr.exact(address, size)
                proof.append(dict(address=address, size=size, expected_hex=data.hex(),
                                  label='Reviewed bag native method'))
                return data
            def number(address, kind, anchored=False):
                size = struct.calcsize(kind)
                return struct.unpack(kind, anchor(address, size) if anchored else rr.exact(address, size))[0]
            module = probe.verified_mappings(rr.reader)['game_assembly'][0]['base']
            view = SimpleNamespace(reader=rr.reader, module=module, anchor=anchor,
                                   q=lambda a, anchored=False: number(a, '<Q', anchored),
                                   i=lambda a, anchored=False: number(a, '<i', anchored))
            mi, selected = resolve_reviewed_method(view, k, METHOD_SPECS[operation])
            raw['anchors'].extend(proof)
            return (mi, rr.q(mi)), selected['token'], selected['rva'], selected['argc']
        count = int.from_bytes(rr.exact(k + 0x120, 2), 'little')
        methods = rr.q(k + 0x98)
        name, token, rva, argc = METHODS[operation]
        matches = []
        if not 1 <= count <= 256:
            raise Refused('背包方法表数量异常。')
        for i in range(count):
            mi = rr.q(methods + i * 8)
            if rr.reader.string(rr.q(mi + 0x18)) == name and int.from_bytes(rr.exact(mi + 0x48, 4), 'little') == token:
                if rr.exact(mi + 0x52, 1)[0] != argc:
                    raise Refused('背包方法参数数量与已验证版本不同。')
                matches.append((mi, rr.q(mi)))
        if len(matches) != 1:
            raise Refused('未找到唯一的背包方法。')
        return matches[0], token, rva, argc

    def _dispatch(self, raw, operation, extra):
        if self.blocked:
            raise Refused(getattr(self, 'blocked_reason', '上次获取结果尚未确认，已停止获取。'))
        if getattr(self, 'native_block_reason', None):
            raise Refused(self.native_block_reason)
        # Read-only guards run before even loading the injection dependency.
        from acquisition_context import require_safe_acquisition_context
        context = require_safe_acquisition_context(self.game.resolver)
        import frida
        from native_acquisition_session import acquire_connection, NativeStartError
        if frida.__version__ != '17.7.3':
            raise Refused('获取功能依赖的 Frida 版本不匹配。')
        (mi, method_pointer), method_token, method_rva, argc = self._method(raw, operation)
        stack_mi = None
        if extra.get('currency_proof') is not None:
            (stack_mi, _), _, _, _ = self._method(raw, 'currency_stack')
        token = uuid.uuid4().hex
        outcome = {}
        done = threading.Event()
        request = dict(token=token, pid=raw['pid'], operation=operation,
                       method_info=hex(mi), method_token=method_token,
                       method_rva=method_rva, parameter_count=argc,
                       player=hex(raw['player']), bag=hex(raw['bag']),
                       anchors=[{**a, 'address': hex(a['address'])}
                                for a in raw['anchors'] + context['anchors']],
                       deadline=int(time.time() * 1000) + 10000, **extra)
        if extra.get('currency_proof') is not None:
            request['currency_proof'] = dict(extra['currency_proof'], stack_method=hex(stack_mi))
        # Convert RemoveByUid to a version-locked RVA once its PE proof is set.
        if method_rva is None:
            raise Refused('测试清理方法还未配置已验证入口。')

        def on_message(message, _data):
            if message.get('type') == 'send':
                value = message.get('payload', {})
                if value.get('token') == token:
                    outcome.update(value)
                    self._native_inflight = False
                    done.set()
                    if self in _RETAINED_BRIDGES:
                        # Avoid unloading from within Frida's message callback.
                        threading.Thread(target=self.close, daemon=True).start()
            elif message.get('type') == 'error':
                outcome.update(status='unknown', reason=message.get('description', 'bridge error'), token=token)
                done.set()

        identity = dict(pid=raw['pid'],
                        process_creation_filetime=raw.get('process_creation_filetime'))
        self._record(dict(status='not_dispatched', token=token, operation=operation,
                          stage='before_attach', called=False, **identity, **extra))
        try:
            def on_detached(reason, *_details):
                # A lost transport does not prove that native code stopped.
                # Only process termination/replacement releases that assumption.
                if reason in ('process-terminated', 'process-replaced'):
                    self._native_inflight = False
                    _RETAINED_BRIDGES.discard(self)
                elif self._native_inflight:
                    _RETAINED_BRIDGES.add(self)
                if not done.is_set():
                    outcome.update(status='unknown', token=token, stage='detached',
                                   reason=str(reason), called=None)
                    done.set()
            def before_attach():
                # Persist before entering the injector. A new trainer process
                # must never re-load an agent into this same game lifetime.
                self._record(dict(status='attaching', token=token, operation=operation,
                                  stage='attach', called=False, **identity, **extra))
            try:
                self._connection = acquire_connection(
                    (raw['pid'], raw['process_creation_filetime']), frida,
                    (HERE / 'acquisition_bridge.js').read_text(encoding='utf8'),
                    self.safety_logs / 'acquisition-native-epochs.json', self,
                    on_message, on_detached, before_attach,
                    lambda: require_no_unmanaged_agent(self.game.resolver))
                self._session = self._connection.session
                self._script = self._connection.script
                self._connection.prepare()
                self._record(dict(status='not_dispatched', token=token, operation=operation,
                                  stage='connected', called=False, **identity, **extra))
            except NativeStartError as failure:
                error = failure.original
                self.native_block_reason = ATTACH_FAILURE_MESSAGE
                self.native_block_identity = _validated_process_identity(identity)
                event = dict(status='attach_failed', token=token, operation=operation,
                             stage=failure.stage, called=False, **identity, **extra,
                             error_type=type(error).__name__, error=str(error))
                try:
                    self._record(event)
                except Exception:
                    # The previous durable "attaching" state is also blocked.
                    # Do not mask the injection failure with a logging failure.
                    pass
                raise Refused(ATTACH_FAILURE_MESSAGE) from error
            # No request has been sent yet. Refresh identity and anchors after attachment.
            current = self._current()
            refreshed_context = require_safe_acquisition_context(self.game.resolver)
            context_anchors = lambda value: {
                a['address']: (a['size'], a['expected_hex']) for a in value['anchors']}
            if (context['identity'] != refreshed_context['identity'] or
                    context_anchors(context) != context_anchors(refreshed_context)):
                raise Refused('附加期间游戏场景发生变化，未调用；请退出战斗后重新检查。')
            if any(current[k] != raw[k] for k in ('player', 'bag', 'world', 'store')):
                raise Refused('附加期间角色或存档发生变化，未调用。')
            expected_items = [(i['uid'], i['item_id'], i['count'], i['object']) for i in raw['items']]
            actual_items = [(i['uid'], i['item_id'], i['count'], i['object']) for i in current['items']]
            if expected_items != actual_items:
                raise Refused('附加期间背包发生变化，未调用；请刷新后再操作。')
            request['anchors'] = [{**a, 'address': hex(a['address'])}
                                  for a in current['anchors'] + refreshed_context['anchors']]
            # Counts are not part of resolver's pointer anchors. Pin every live
            # item count as well so a purchase/consumption invalidates the request.
            request['anchors'].extend(dict(address=hex(i['count_address']), size=4,
                                           expected_hex=int(i['count']).to_bytes(4, 'little', signed=True).hex(),
                                           label='inventory count ' + str(i['uid'])) for i in current['items'])
            currency_proof = extra.get('currency_proof')
            if currency_proof is not None:
                request['anchors'].extend({**a, 'address': hex(a['address'])}
                                          for a in currency_proof['anchors'])
            request['deadline'] = int(time.time() * 1000) + 10000
            self._record(dict(status='pending', token=token, operation=operation, **extra))
            self._native_inflight = True
            self._connection.previous_token = token
            self._script.exports_sync.submit(request)
            if not done.wait(12):
                # The bridge cancels an unstarted request at its 10-second
                # deadline. Do not issue synchronous RPC here: if native code
                # is still running it might also block an RPC indefinitely.
                outcome.update(status='unknown', token=token,
                               reason='No terminal result within 12 seconds; no retry')
            if outcome.get('status') not in ('completed', 'rejected', 'cancelled'):
                self.blocked = True
                if self._native_inflight:
                    _RETAINED_BRIDGES.add(self)
                self._record(dict(outcome, operation=operation, **extra))
                raise Refused('获取结果不确定，已停止后续获取；请核对背包，不要重复点击。')
            if outcome['status'] != 'completed':
                self._record(dict(outcome, operation=operation, **extra))
                raise Refused(outcome.get('reason', '游戏拒绝了获取请求。'))
            return dict(outcome, operation=operation, **extra)
        except Exception:
            if not outcome and self.journal.exists():
                saved = json.loads(self.journal.read_text(encoding='utf8'))
                if saved.get('status') == 'pending':
                    self.blocked = True
                    if self._native_inflight:
                        _RETAINED_BRIDGES.add(self)
                    self._record(dict(status='unknown', token=token, operation=operation, **extra))
            raise
        finally:
            # Never tear down a possibly running native call automatically.
            self.close()

    def add(self, item_id, quantity):
        if not self._lock.acquire(blocking=False):
            raise Refused('已有获取请求正在处理。')
        called_result = None
        try:
            if self.blocked:
                raise Refused(getattr(self, 'blocked_reason',
                                     '上次获取结果尚未确认，请先核对背包及获取日志。'))
            if type(item_id) is not int or type(quantity) is not int:
                raise Refused('物品编号和获取数量必须是整数。')
            row = next((r for r in self.catalog(refresh=True) if r['id'] == item_id), None)
            if row is None or not row['can_add']:
                raise Refused(row['reason'] if row else '物品编号不在当前游戏目录中。')
            if not 1 <= quantity <= row['max_quantity']:
                raise AcquisitionLimitRefused(f"本物品单次获取数量范围是 1–{row['max_quantity']}，未添加。")
            # Existing reviewed stacks can be increased without loading an
            # injected agent. Never fall back to injection after this path has
            # thrown: it may already have performed the single field write.
            from acquisition_context import require_safe_acquisition_context
            context = require_safe_acquisition_context(self.game.resolver)
            # Currency acquisition preserves the game's gain events via one
            # AddItem request, independent of the balance editor's limits.
            large_currency = (item_id in LARGE_CURRENCY_IDS and row['item_type_id'] == 5)
            existing = None
            if not large_currency:
                from acquisition_existing import try_add_existing
                existing = try_add_existing(self.game, item_id, quantity,
                                            context_anchors=context['anchors'])
            if existing is not None:
                called_result = existing
                self._record(existing)
                return existing
            if getattr(self, 'native_block_reason', None):
                raise Refused(self.native_block_reason)
            before = self._current()
            if any(d.get('reason') not in ('null_entry',) for d in before.get('diagnostics', [])):
                raise Refused('背包含尚未支持或无效的实例，获取会涉及整个背包；请先核对诊断。')
            size_anchor = next((a for a in before.get('anchors', []) if a['label'] == 'Items._size'), None)
            slots = (int.from_bytes(bytes.fromhex(size_anchor['expected_hex']), 'little', signed=True)
                     if size_anchor else len(before['items']))
            total = self._item_total(before, item_id)
            extra = dict(item_id=item_id, quantity=quantity)
            additional_slots = quantity
            if large_currency:
                matches = [item for item in before['items'] if item['item_id'] == item_id]
                if (len(matches) > 1 or any(
                        item.get('class_name') != 'Game.Model.Components.BagItem'
                        or item.get('is_equipped') is not False
                        or type(item.get('count')) is not int or item['count'] < 0
                        for item in matches)):
                    raise Refused('货币实例状态异常，未添加；请重新读取并核对背包。')
                maximum = min(row['config_stack_limit'], CURRENCY_BALANCE_MAXIMUM)
                if not 0 <= total <= maximum or total + quantity > maximum:
                    available = min(row['max_quantity'], max(0, maximum - total))
                    raise AcquisitionLimitRefused(
                        f'当前货币余额 {total:,}，工具总余额上限 {maximum:,}；'
                        f'本次最多可添加 {available:,}。本次请求超过余额上限，未添加。')
                proof = (getattr(self, '_catalog_data', None) or {}).get('currency_proofs', {}).get(item_id)
                if not isinstance(proof, dict) or not proof.get('anchors'):
                    raise Refused('缺少当前货币配置核验信息，未添加；请重新读取物品清单。')
                extra['currency_proof'] = dict(proof, before=total, maximum=maximum)
                # The bridge also checks the game's actual stack limit before
                # invoking AddItem: never assume one new object per currency unit.
                additional_slots = 0 if matches else 1
            if not len(before['items']) <= slots <= 4000 or slots + additional_slots > 4000:
                raise Refused('背包格数接近本工具支持范围，未添加。')
            result = self._dispatch(before, 'add', extra)
            called_result = result
            after = self._current()
            new_total = self._item_total(after, item_id)
            stable = all(before[k] == after[k] for k in ('player', 'bag', 'world', 'store'))
            if not stable or new_total != total + quantity:
                self.blocked = True
                self._record(dict(result, status='unknown', before=total, after=new_total))
                raise Refused('游戏方法已执行，但数量回读不符合预期；请核对背包，不要重试。')
            old_uids = {i['uid'] for i in before['items']}
            result.update(status='verified', verified=True, changed=True, before=total,
                          after=new_total, method='BagModel.AddItem / Unity A1Main.Update',
                          new_uids=[i['uid'] for i in after['items'] if i['uid'] not in old_uids and i['item_id'] == item_id],
                          player=before['player'], bag=before['bag'], pid=before.get('pid'),
                          process_creation_filetime=before.get('process_creation_filetime'))
            self._record(result)
            return result
        except UncertainWrite as error:
            self._mark_uncertain(dict(operation='add', item_id=item_id, quantity=quantity,
                                      route='existing_stack', write_attempted=True,
                                      error_type=type(error).__name__, error=str(error)))
            raise
        except Exception:
            if called_result is not None:
                self._mark_uncertain(called_result)
            raise
        finally:
            self._lock.release()

    def remove_test_addition(self, addition):
        """Undo only a verified one-unit test that created exactly one new UID.

        Deliberately unavailable for an existing stack or arbitrary UID; this is
        a root-agent acceptance helper rather than a general inventory delete UI.
        """
        if not self._lock.acquire(blocking=False):
            raise Refused('已有获取请求正在处理。')
        called_result = None
        try:
            if self.blocked:
                raise Refused('结果不确定时不能自动清理。')
            if (addition.get('status') != 'verified' or addition.get('quantity') != 1 or
                    addition.get('before') != 0 or len(addition.get('new_uids', [])) != 1):
                raise Refused('仅可清理从无到有的一件新增验收物品。')
            raw = self._current()
            if (raw.get('pid') != addition.get('pid') or
                    raw.get('process_creation_filetime') != addition.get('process_creation_filetime')):
                raise Refused('游戏进程已变化，不自动清理旧验收记录。')
            if raw['player'] != addition['player'] or raw['bag'] != addition['bag']:
                raise Refused('角色已变化，不自动清理。')
            uid = addition['new_uids'][0]
            item_id = addition['item_id']
            matches = [i for i in raw['items'] if i['uid'] == uid]
            if (len(matches) != 1 or matches[0]['item_id'] != item_id or
                    matches[0]['count'] != 1 or self._item_total(raw, item_id) != 1):
                raise Refused('验收物品已发生变化，不自动清理。')
            result = self._dispatch(raw, 'remove_test_uid', dict(uid=str(uid), item_id=item_id, quantity=1))
            called_result = result
            after = self._current()
            if (any(after[k] != raw[k] for k in ('player', 'bag', 'world', 'store')) or
                    any(i['uid'] == uid for i in after['items']) or self._item_total(after, item_id) != 0):
                self.blocked = True
                self._record(dict(result, status='unknown'))
                raise Refused('验收物品清理结果不确定，请核对背包。')
            result.update(status='verified', verified=True, changed=True, before=1, after=0,
                          method='BagModel.RemoveByUid / Unity A1Main.Update')
            self._record(result)
            return result
        except Exception:
            if called_result is not None:
                self._mark_uncertain(called_result)
            raise
        finally:
            self._lock.release()

    def close(self):
        if getattr(self, '_native_inflight', False):
            _RETAINED_BRIDGES.add(self)
            return
        # Adapter/UI disconnection only releases the request lease. The process
        # registry keeps the agent and script alive to avoid unsafe re-init.
        connection = getattr(self, '_connection', None)
        if connection is not None:
            connection.release(self)
        self._connection = None
        self._script = None
        self._session = None
        _RETAINED_BRIDGES.discard(self)
