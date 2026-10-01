"""One bounded current-resource mutation through the shared native connection."""
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
from current_resources import (RESOURCE_SPECS, MAXIMUM, validate_resource_value,
                               resource_identity_after_modify, pack)

SAFE = frozenset(("verified", "rejected", "cancelled", "not_dispatched", "attach_failed"))


class CurrentResourcesNative:
    def __init__(self, game, adapter):
        self.game, self.adapter = game, adapter
        self._native_inflight = False
        self._connection = self._session = self._script = None
        self.safety_logs = initialize_runtime()
        self.journal = self.safety_logs / "current-resources.json"
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
            raise Refused("资源操作记录无法核对，请保留日志后检查。") from exc

    def require_ready(self):
        previous = self._ledger()["processes"].get(self.process_key)
        if previous and previous.get("status") not in SAFE:
            raise Refused("本次游戏进程有未确认的资源操作，请核对游戏，暂不能再次修改。")

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
        self.game.record(dict(current_resource=event))

    @staticmethod
    def request(descriptor, pid, token):
        resource = dict(descriptor)
        anchors, method = resource.pop("anchors"), resource.pop("method_info")
        spec = RESOURCE_SPECS.get(resource.get("resource_key"))
        if spec is None:
            raise Refused("当前资源类型不在已验证白名单。")
        methods = {key: request_method_spec(value, resource.get("method_specs", {}).get(key))
                   for key, value in spec["methods"].items()}
        if (not anchors or not resource.get("identity_key") or set(resource.get("methods", {})) != set(methods)
                or method != resource["methods"]["modify"]):
            raise Refused("资源请求缺少完整身份或方法锚。")
        return dict(operation=spec["operation"], token=token, pid=pid, resource=resource,
                    method_info=method, method_token=methods["modify"]["token"],
                    method_rva=methods["modify"]["rva"], parameter_count=1, anchors=anchors,
                    deadline=int(time.time()*1000)+10000)

    def set_value(self, shown, value):
        normalized = validate_resource_value(shown, value)
        self.require_ready()
        descriptor = self.adapter.prepare_native(shown, normalized)
        pid, created = self.game.resolver.reader.pid, self.game.stamp[1]
        token = uuid.uuid4().hex
        preview = self.request(descriptor, pid, token)
        if descriptor["resource_key"] != shown.key:
            raise Refused("当前资源请求对应的目标已变化。")
        import frida
        if frida.__version__ != "17.7.3":
            raise Refused("资源连接组件版本不匹配。")
        identity = dict(token=token, pid=pid, process_creation_filetime=created,
                        operation=preview["operation"], resource_key=shown.key, before=shown.value, after=normalized)
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
                raise Refused("原生连接组件加载失败，尚未修改资源；请核对游戏后重试。") from exc
            self.record(dict(identity, status="not_dispatched", called=False))
            fresh = self.adapter.prepare_native(shown, normalized)
            if fresh != descriptor:
                raise Refused("连接期间资源或场景发生变化，未修改。")
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
                raise Refused(outcome.get("reason") or "游戏状态或实际资源上限不允许本次修改。")
            post, maximum = outcome.get("value"), outcome.get("maximum")
            if (status != "completed" or outcome.get("called") is not True or outcome.get("result") is not True
                    or outcome.get("identity_key") != descriptor["identity_key"]
                    or outcome.get("resource_key") != shown.key
                    or type(outcome.get("before")) not in (int, float) or pack(outcome["before"]) != pack(shown.value)
                    or type(post) not in (int, float) or not math.isfinite(post) or not RESOURCE_SPECS[shown.key]["minimum"] <= post <= MAXIMUM
                    or type(maximum) not in (int, float) or not math.isfinite(maximum) or not 0 < maximum <= MAXIMUM
                    or post > maximum or pack(post) != pack(normalized)):
                raise UncertainWrite("资源修改已派发，但游戏返回结果未确认；请核对游戏，勿重复操作。")
            current = self.adapter.resolve(shown.key)
            if (current is None or current.key != shown.key or not resource_identity_after_modify(shown.identity, current.identity) or not current.can_edit
                    or current.address != shown.address or pack(current.value) != pack(normalized)):
                raise UncertainWrite("资源修改后的角色或数值回读不符，请核对游戏，勿重复操作。")
            self.record(dict(identity, status="verified", called=True, result=outcome))
            return dict(target=current, current=current.value, maximum=maximum, verified=True, resource_key=shown.key)
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
                raise UncertainWrite("资源派发后的验证未完成，请核对游戏，勿重复操作。") from exc
            raise
        finally:
            self.close()
