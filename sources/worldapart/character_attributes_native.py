"""Create missing growth entries through the same process-wide native session."""
import json
import os
import threading
import time
import uuid

from acquisition_adapter import (AcquisitionAdapter, _LIVE_BRIDGES, _RETAINED_BRIDGES,
                                 require_no_unmanaged_agent)
from native_acquisition_session import acquire_connection, NativeStartError
from native_method_profiles import request_method_spec
from runtime_paths import RESOURCE_ROOT, initialize_runtime
from write_guard import Refused, UncertainWrite
from character_attributes_write import pack, validate_attribute_value

SAFE = frozenset(("verified", "rejected", "cancelled", "not_dispatched", "attach_failed"))
METHOD_TOKEN, METHOD_RVA = 0x06014B6C, 0xE679F0


class CharacterAttributesNative:
    def __init__(self, game, adapter):
        self.game, self.adapter = game, adapter
        self._native_inflight = False
        self._connection = self._session = self._script = None
        self.safety_logs = initialize_runtime()
        self.journal = self.safety_logs / "character-attributes.json"
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
            if any(not isinstance(k, str) or not isinstance(v, dict)
                   or not isinstance(v.get("status"), str) for k, v in data["processes"].items()):
                raise ValueError("invalid status")
            return data
        except Exception as exc:
            raise Refused("人物属性操作记录无法核对，请保留日志后检查。") from exc

    def require_ready(self):
        previous = self._ledger()["processes"].get(self.process_key)
        if previous and previous.get("status") not in SAFE:
            raise Refused("本次游戏进程有未确认的人物属性操作，已禁止再次修改；请核对游戏和日志。")

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
        self.game.record(dict(character_attribute=event))

    @staticmethod
    def request(descriptor, pid, token):
        character = dict(descriptor)
        anchors, method = character.pop("anchors"), character.pop("method_info")
        if not anchors or not character.get("identity_key"):
            raise Refused("人物属性请求缺少完整身份锚。")
        spec = request_method_spec(dict(name="SetGrowthAttr", token=METHOD_TOKEN, rva=METHOD_RVA,
                                        prefix="48895c2408574883ec30803d981c6e0700", argc=2), character.get("method_spec"))
        return dict(operation="character_growth_set", token=token, pid=pid,
                    method_info=method, method_token=spec["token"], method_rva=spec["rva"],
                    parameter_count=2, character=character, anchors=anchors,
                    deadline=int(time.time() * 1000) + 10000)

    def set_value(self, shown, value):
        normalized = validate_attribute_value(shown, value)
        self.require_ready()
        descriptor = self.adapter.prepare_native(shown, normalized)
        pid, created = self.game.resolver.reader.pid, self.game.stamp[1]
        token = uuid.uuid4().hex
        self.request(descriptor, pid, token)
        import frida
        if frida.__version__ != "17.7.3":
            raise Refused("人物属性连接组件版本不匹配。")
        identity = dict(token=token, pid=pid, process_creation_filetime=created,
                        operation="character_growth_set", attr_id=shown.attr_id,
                        before=0.0, after=normalized, route="native_create")
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
                self._connection = acquire_connection(
                    (pid, created), frida, (RESOURCE_ROOT / "acquisition_bridge.js").read_text(encoding="utf8"),
                    self.safety_logs / "acquisition-native-epochs.json", self,
                    on_message, on_detached,
                    lambda: self.record(dict(identity, status="attaching", called=False)),
                    lambda: require_no_unmanaged_agent(self.game.resolver))
                self._session, self._script = self._connection.session, self._connection.script
                self._connection.prepare()
            except NativeStartError as exc:
                self.record(dict(identity, status="attach_failed", called=False,
                                 stage=exc.stage, error=str(exc.original)))
                raise Refused("原生连接组件加载失败，尚未创建成长属性；请保存并重启游戏后检查。") from exc
            self.record(dict(identity, status="not_dispatched", called=False))
            fresh = self.adapter.prepare_native(shown, normalized)
            if fresh != descriptor:
                raise Refused("连接期间人物属性或场景发生变化，未调用。")
            request = self.request(fresh, pid, token)
            self.record(dict(identity, status="pending", called=None))
            dispatched = True
            self._native_inflight = True
            self._connection.previous_token = token
            self._script.exports_sync.submit(request)
            if not done.wait(12):
                outcome.update(status="unknown", token=token, reason="等待主线程超时，不自动重试。")
            status = outcome.get("status")
            if status in ("rejected", "cancelled") and outcome.get("called") is False:
                self.record(dict(identity, status=status, called=False, result=outcome))
                dispatched = False
                raise Refused(outcome.get("reason") or "游戏状态发生变化，未创建成长属性。")
            if (status != "completed" or outcome.get("called") is not True
                    or outcome.get("created") is not True or outcome.get("attr_id") != shown.attr_id
                    or outcome.get("identity_key") != descriptor["identity_key"]
                    or type(outcome.get("value")) not in (int, float)
                    or pack(outcome["value"]) != pack(normalized)):
                raise UncertainWrite("成长属性方法已派发，但结果未确认；请核对游戏，勿重复操作。")
            current = self.adapter.resolve(shown.key)
            if (not current.exists or current.identity[:9] != shown.identity[:9]
                    or pack(current.value) != pack(normalized)):
                raise UncertainWrite("成长属性创建后回读不符，请核对游戏，勿重复操作。")
            self.record(dict(identity, status="verified", called=True, result=outcome))
            return current
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
                raise UncertainWrite("人物属性派发后的验证未完成，请核对游戏，勿重复操作。") from exc
            raise
        finally:
            self.close()
