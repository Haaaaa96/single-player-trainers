"""One bounded base-speed mutation through the shared native connection."""
import json
import math
import os
import threading
import time
import uuid

from acquisition_adapter import (AcquisitionAdapter, _LIVE_BRIDGES, _RETAINED_BRIDGES,
                                 require_no_unmanaged_agent)
from native_acquisition_session import acquire_connection, NativeStartError
from runtime_paths import RESOURCE_ROOT, initialize_runtime
from native_method_profiles import request_method_spec
from write_guard import Refused, UncertainWrite
from game_speed import METHODS, validate_speed_value, pack

SAFE = frozenset(("verified", "rejected", "cancelled", "not_dispatched", "attach_failed"))


class GameSpeedNative:
    def __init__(self, game, adapter):
        self.game, self.adapter = game, adapter
        self._native_inflight = False
        self._connection = self._session = self._script = None
        self.safety_logs = initialize_runtime()
        self.journal = self.safety_logs / "game-speed.json"
        self.process_key = f"{game.resolver.reader.pid}:{game.stamp[1]}"
        self._ledger()
        _LIVE_BRIDGES.add(self)

    close = AcquisitionAdapter.close

    def _ledger(self):
        if not self.journal.exists():
            return dict(version=1, processes={})
        try:
            data = json.loads(self.journal.read_text(encoding="utf8"))
            if data.get("version") != 1 or not isinstance(data.get("processes"), dict):
                raise ValueError("invalid schema")
            if any(not isinstance(k, str) or not isinstance(v, dict) or not isinstance(v.get("status"), str)
                   for k, v in data["processes"].items()):
                raise ValueError("invalid status")
            return data
        except Exception as exc:
            raise Refused("速度操作记录无法核对，请保留日志后检查。") from exc

    def require_ready(self):
        previous = self._ledger()["processes"].get(self.process_key)
        if previous and previous.get("status") not in SAFE:
            raise Refused("本次游戏进程有未确认的速度操作，请核对游戏，暂不能再次修改。")

    def record(self, event):
        event = dict(event, process_key=self.process_key)
        data = self._ledger()
        data["processes"][self.process_key] = event
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_name(self.journal.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.journal)
        self.game.record(dict(game_speed=event))

    @staticmethod
    def request(descriptor, pid, token):
        resource = dict(descriptor)
        anchors, method = resource.pop("anchors"), resource.pop("method_info")
        if (not anchors or not resource.get("identity_key") or set(resource.get("methods", {})) != set(METHODS)
                or method != resource["methods"]["modify"]):
            raise Refused("速度请求缺少完整身份或方法锚。")
        selected = request_method_spec(METHODS["modify"], resource.get("method_specs", {}).get("modify"))
        return dict(operation="game_speed_set", token=token, pid=pid, speed=resource,
                    method_info=method, method_token=selected["token"],
                    method_rva=selected["rva"], parameter_count=1, anchors=anchors,
                    deadline=int(time.time()*1000)+10000)

    def set_value(self, shown, value):
        normalized = validate_speed_value(shown, value)
        self.require_ready()
        descriptor = self.adapter.prepare_native(shown, normalized)
        pid, created = self.game.resolver.reader.pid, self.game.stamp[1]
        token = uuid.uuid4().hex
        preview = self.request(descriptor, pid, token)
        import frida
        if frida.__version__ != "17.7.3":
            raise Refused("速度连接组件版本不匹配。")
        identity = dict(token=token, pid=pid, process_creation_filetime=created,
                        operation=preview["operation"], before=shown.value, after=normalized)
        outcome, done, dispatched = {}, threading.Event(), False

        def on_message(message, _data):
            if message.get("type") == "send":
                payload = message.get("payload", {})
                if payload.get("token") != token:
                    return
                outcome.update(payload)
                if payload.get("status") in ("completed", "rejected", "cancelled", "exception"):
                    self._native_inflight = False
                done.set()
                if self in _RETAINED_BRIDGES and not self._native_inflight:
                    threading.Thread(target=self.close, daemon=True).start()
            elif message.get("type") == "error":
                outcome.update(status="unknown", token=token, reason=message.get("description", "native bridge error"))
                done.set()

        def on_detached(reason, *_details):
            if reason in ("process-terminated", "process-replaced"):
                self._native_inflight = False
                _RETAINED_BRIDGES.discard(self)
            elif self._native_inflight:
                _RETAINED_BRIDGES.add(self)
            if not done.is_set():
                outcome.update(status="unknown", reason=str(reason), token=token)
                done.set()

        try:
            self.record(dict(identity, status="not_dispatched", called=False))
            try:
                self._connection = acquire_connection((pid, created), frida,
                    (RESOURCE_ROOT / "acquisition_bridge.js").read_text(encoding="utf8"),
                    self.safety_logs / "acquisition-native-epochs.json", self, on_message, on_detached,
                    lambda: self.record(dict(identity, status="attaching", called=False)),
                    lambda: require_no_unmanaged_agent(self.game.resolver))
                self._session, self._script = self._connection.session, self._connection.script
                self._connection.prepare()
            except NativeStartError as exc:
                self.record(dict(identity, status="attach_failed", called=False,
                                 stage=exc.stage, error=str(exc.original)))
                raise Refused("原生连接组件加载失败，尚未修改速度；请核对游戏后重试。") from exc
            self.record(dict(identity, status="not_dispatched", called=False))
            fresh = self.adapter.prepare_native(shown, normalized)
            if fresh != descriptor:
                raise Refused("连接期间速度或场景发生变化，未修改。")
            request = self.request(fresh, pid, token)
            self.record(dict(identity, status="pending", called=None))
            dispatched = True
            self._native_inflight = True
            self._connection.previous_token = token
            self._script.exports_sync.submit(request)
            if not done.wait(12):
                outcome.update(status="unknown", token=token, reason="等待游戏主线程超时，不自动重试。")
            status = outcome.get("status")
            if status in ("rejected", "cancelled") and outcome.get("called") is False:
                self.record(dict(identity, status=status, called=False, result=outcome))
                dispatched = False
                raise Refused(outcome.get("reason") or "游戏状态或实际速度上限不允许本次修改。")
            post, effective = outcome.get("value"), outcome.get("effective")
            expected_effective = shown.effective if shown.override_count else normalized
            if (status != "completed" or outcome.get("called") is not True
                    or outcome.get("identity_key") != descriptor["identity_key"]
                    or type(outcome.get("before")) not in (int, float) or pack(outcome["before"]) != pack(shown.value)
                    or type(post) not in (int, float) or not math.isfinite(post) or not 0.5 <= post <= 2
                    or type(effective) not in (int, float) or not math.isfinite(effective) or not 0 <= effective <= 100
                    or pack(post) != pack(normalized) or pack(effective) != pack(expected_effective)
                    or type(outcome.get("override_count")) is not int or outcome["override_count"] != shown.override_count):
                raise UncertainWrite("速度修改已派发，但游戏返回结果未确认；请核对游戏，勿重复操作。")
            state = self.adapter.snapshot()
            current = state["target"]
            if (current.identity != shown.identity or not current.can_edit or current.address != shown.address
                    or pack(current.value) != pack(normalized) or pack(current.effective) != pack(effective)):
                raise UncertainWrite("速度修改后的控制器或数值回读不符，请核对游戏，勿重复操作。")
            self.record(dict(identity, status="verified", called=True, result=outcome))
            return dict(state, verified=True)

        except Exception as exc:
            if dispatched:
                if self._native_inflight:
                    _RETAINED_BRIDGES.add(self)
                try:
                    self.record(dict(identity, status="unknown", result=outcome, error=str(exc)))
                except Exception:
                    pass
                if isinstance(exc, UncertainWrite):
                    raise
                raise UncertainWrite("速度派发后的验证未完成，请核对游戏，勿重复操作。") from exc
            raise
        finally:
            self.close()
