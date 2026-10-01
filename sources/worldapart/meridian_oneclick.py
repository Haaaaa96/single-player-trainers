"""One native solution restore per active round, using the shared agent lifetime.

The native helper performs all board changes and ordinary win callbacks. Python
only supplies a freshly proved board and checks the native result; it never
writes cell fields, rewards, victory flags or save data.
"""
import json
import os
import threading
import time
import uuid

from acquisition_adapter import (AcquisitionAdapter, _LIVE_BRIDGES, _RETAINED_BRIDGES,
                                 require_no_unmanaged_agent)
from native_acquisition_session import acquire_connection, NativeStartError
from runtime_paths import RESOURCE_ROOT, initialize_runtime
from write_guard import Refused, UncertainWrite
from native_method_profiles import request_method_spec
from meridian_adapter import METHOD_SPEC

METHOD_TOKEN = 0x06010174
METHOD_RVA = 0x1DAC830
SAFE_NOT_CALLED = frozenset(("not_dispatched", "rejected", "cancelled"))


class MeridianOneClick:
    def __init__(self, game_adapter, resolver):
        self.game, self.resolver = game_adapter, resolver
        self._lock = threading.Lock()
        self._native_inflight = False
        self._connection = self._session = self._script = None
        self.safety_logs = initialize_runtime()
        self.journal = self.safety_logs / "meridian-oneclick.json"
        self._ledger()  # Corrupt safety state must fail before dispatch.
        _LIVE_BRIDGES.add(self)

    close = AcquisitionAdapter.close

    def _ledger(self):
        if not self.journal.exists():
            return dict(version=1, rounds={})
        try:
            value = json.loads(self.journal.read_text(encoding="utf8"))
            if value.get("version") != 1 or not isinstance(value.get("rounds"), dict):
                raise ValueError("unknown journal schema")
            if any(not isinstance(k, str) or len(k) != 64 or not isinstance(v, dict)
                   or not isinstance(v.get("status"), str) for k, v in value["rounds"].items()):
                raise ValueError("invalid round record")
            return value
        except Exception as error:
            raise Refused("一键疏通记录无法读取；已停止操作，请保留日志后检查。") from error

    def _require_unused(self, round_key):
        previous = self._ledger()["rounds"].get(round_key)
        if previous and (previous.get("status") not in SAFE_NOT_CALLED or previous.get("called") is not False):
            raise Refused("本局已派发过一键疏通，或上次结果未确认；禁止重复调用，请核对游戏结算。")

    def _record(self, round_key, event):
        ledger = self._ledger()
        event = dict(event, round_key=round_key, operation="meridian_solve", recorded_at=time.time())
        ledger["rounds"][round_key] = event
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_name(self.journal.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf8") as output:
            json.dump(ledger, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.journal)
        self.game.record(dict(meridian_oneclick=event))

    @staticmethod
    def _request(state, pid, token):
        descriptor = dict(state["native"])
        anchors = descriptor.pop("anchors")
        method = descriptor.pop("method_info")
        selected = request_method_spec(METHOD_SPEC, descriptor.get('method_spec'))
        if (not descriptor.get("registry_links") or not descriptor.get("registry")
                or not isinstance(anchors, list) or not anchors):
            raise Refused("一键疏通缺少完整的游戏面板注册链，未调用。")
        return dict(operation="meridian_solve", token=token, pid=pid,
                    method_info=method, method_token=selected['token'], method_rva=selected['rva'],
                    parameter_count=0, meridian=descriptor, anchors=anchors,
                    deadline=int(time.time() * 1000) + 10000)

    def solve(self, shown):
        if not self._lock.acquire(blocking=False):
            raise Refused("一键疏通请求正在处理中。")
        try:
            return self._solve(shown)
        finally:
            self.close()
            self._lock.release()

    def _solve(self, shown):
        state = self.resolver.prepare_solve(shown)
        round_key = state["native"]["round_key"]
        self._require_unused(round_key)
        pid = self.game.resolver.reader.pid
        created = self.game.stamp[1]
        if type(pid) is not int or type(created) is not int or pid <= 0 or created <= 0:
            raise Refused("游戏进程生命周期不完整，未调用。")
        token = uuid.uuid4().hex
        self._request(state, pid, token)  # Reject malformed descriptors before loading Frida.
        import frida
        if frida.__version__ != "17.7.3":
            raise Refused("一键疏通的连接组件版本不匹配。")
        done, outcome = threading.Event(), {}
        dispatched = False
        identity = dict(pid=pid, process_creation_filetime=created, token=token)

        def on_message(message, _data):
            if message.get("type") == "send":
                value = message.get("payload", {})
                if value.get("token") != token:
                    return
                outcome.update(value)
                if value.get("status") in ("completed", "rejected", "cancelled", "exception"):
                    self._native_inflight = False
                done.set()
                if self in _RETAINED_BRIDGES and not self._native_inflight:
                    threading.Thread(target=self.close, daemon=True).start()
            elif message.get("type") == "error":
                outcome.update(status="unknown", token=token,
                               reason=message.get("description", "native bridge error"))
                done.set()

        def on_detached(reason, *_details):
            if reason in ("process-terminated", "process-replaced"):
                self._native_inflight = False
                _RETAINED_BRIDGES.discard(self)
            elif self._native_inflight:
                _RETAINED_BRIDGES.add(self)
            if not done.is_set():
                outcome.update(status="unknown", token=token, reason=str(reason), stage="detached")
                done.set()

        def before_attach():
            self._record(round_key, dict(identity, status="attaching", called=False))

        try:
            self._record(round_key, dict(identity, status="not_dispatched", called=False))
            try:
                self._connection = acquire_connection(
                    (pid, created), frida, (RESOURCE_ROOT / "acquisition_bridge.js").read_text(encoding="utf8"),
                    self.safety_logs / "acquisition-native-epochs.json", self, on_message,
                    on_detached, before_attach, lambda: require_no_unmanaged_agent(self.game.resolver))
                self._session, self._script = self._connection.session, self._connection.script
                self._connection.prepare()
            except NativeStartError as error:
                self._record(round_key, dict(identity, status="attach_failed", called=False,
                                             stage=error.stage, error=str(error.original)))
                raise Refused("原生连接组件加载失败，未调用疏通方法；请保留日志并重启游戏后再检查。") from error
            self._record(round_key, dict(identity, status="not_dispatched", called=False))
            # Attachment can take seconds. Re-resolve the current panel and the
            # full board, then require exactly the same shown round and cells.
            fresh = self.resolver.prepare_solve(state)
            if (fresh.get("identity") != state.get("identity")
                    or fresh["native"]["round_key"] != round_key
                    or fresh["native"]["cells"] != state["native"]["cells"]):
                raise Refused("连接期间棋盘已变化，未调用；请刷新后再操作。")
            self._require_unused(round_key)
            request = self._request(fresh, pid, token)
            self._record(round_key, dict(identity, status="pending", called=None))
            dispatched = True  # RPC failure after this point is uncertain.
            self._native_inflight = True
            self._connection.previous_token = token
            self._script.exports_sync.submit(request)
            if not done.wait(12):
                outcome.update(status="unknown", token=token, reason="主线程结果等待超时，不自动重试。")
            status = outcome.get("status")
            if status in ("rejected", "cancelled") and outcome.get("called") is False:
                self._record(round_key, dict(identity, **{k: v for k, v in outcome.items() if k != "token"}))
                dispatched = False
                raise Refused(outcome.get("reason") or "游戏状态已变化，未调用一键疏通。")
            if (status != "completed" or outcome.get("called") is not True
                    or outcome.get("changed") is not True
                    or outcome.get("native_won") is not True
                    or outcome.get("native_finished") is not True
                    or type(outcome.get("failure_reason")) is not int or outcome["failure_reason"] != 0):
                raise UncertainWrite("一键疏通已经派发，但胜利结果未确认。已禁止本局重试，请核对游戏画面。")
            result = dict(identity)
            result.update(outcome, status="verified", round_key=round_key,
                          phase="native_win_waiting_settlement", settlement_verified=False,
                          message="游戏已判定本局胜利，等待原游戏结算；奖励和存档尚未由修改器确认。")
            self._record(round_key, result)
            return result
        except Exception as error:
            if dispatched:
                if self._native_inflight:
                    _RETAINED_BRIDGES.add(self)
                try:
                    self._record(round_key, dict(identity, status="unknown", called=None,
                                                 result=outcome, error=str(error)))
                except Exception:
                    pass  # The durable pending entry still prohibits retry.
                if isinstance(error, UncertainWrite):
                    raise
                raise UncertainWrite("一键疏通派发后的结果未能确认；请核对游戏，不要重复操作。") from error
            raise
