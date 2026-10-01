"""Reviewed lifespan inspection/add requests on the shared native broker."""
import json
import math
import os
import threading
import time
import uuid

from acquisition_adapter import (AcquisitionAdapter, _LIVE_BRIDGES, _RETAINED_BRIDGES,
                                 require_no_unmanaged_agent)
from character_attributes_native import CharacterAttributesNative
from character_lifespan import SPECS, MAX_NATIVE_INT, LifespanTarget, validate_increase
from character_attributes_write import pack
from native_acquisition_session import acquire_connection, NativeStartError
from native_method_profiles import reviewed_method_profile
from runtime_paths import RESOURCE_ROOT, initialize_runtime
from write_guard import Refused, UncertainWrite


class LifespanNative:
    def __init__(self, game, adapter):
        self.game, self.adapter = game, adapter
        self._native_inflight = False
        self._connection = self._session = self._script = None
        self.safety_logs = initialize_runtime()
        self.journal = self.safety_logs / "character-lifespan.json"
        self.process_key = f"{game.resolver.reader.pid}:{game.stamp[1]}"
        self._ledger()
        _LIVE_BRIDGES.add(self)

    close = AcquisitionAdapter.close
    _ledger = CharacterAttributesNative._ledger
    require_ready = CharacterAttributesNative.require_ready

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
        self.game.record(dict(character_lifespan=event))

    @staticmethod
    def request(descriptor, pid, token, adding):
        lifespan = dict(descriptor)
        anchors = lifespan.pop("anchors")
        key = "modify" if adding else "age"
        methods = reviewed_method_profile(SPECS, lifespan.get("method_profile", "legacy"))
        spec = methods[key]
        if (not anchors or not lifespan.get("identity_key") or
                set(lifespan.get("methods", {})) != set(SPECS["methods"])):
            raise Refused("寿元请求缺少方法与角色身份。")
        return dict(operation="lifespan_add" if adding else "lifespan_inspect", token=token, pid=pid,
                    method_info=lifespan["methods"][key], method_token=spec["token"], method_rva=spec["rva"],
                    parameter_count=spec["parameters"], lifespan=lifespan, anchors=anchors,
                    deadline=int(time.time() * 1000) + 10000)

    def checked_result(self, result, context, shown, amount):
        adding = shown is not None
        descriptor = context["descriptor"]
        age, maximum, growth = result.get("current_age"), result.get("maximum"), result.get("growth")
        expected_growth = validate_increase(shown, amount) if adding else context["growth"]
        if (result.get("status") != "completed" or result.get("called") is not True
                or result.get("mutated") is not adding or result.get("identity_key") != descriptor["identity_key"]
                or type(age) is not int or type(maximum) is not int or not 0 <= age <= maximum <= MAX_NATIVE_INT or maximum <= 0
                or result.get("exhausted") is not False or result.get("handling") is not False
                or result.get("handled_age") is not False or result.get("handled_max") is not False
                or type(growth) not in (int, float) or not math.isfinite(growth)
                or pack(growth) != pack(expected_growth)):
            raise UncertainWrite("寿元请求返回信息未完整确认，连接已停止；请核对游戏，勿重复增加。")
        if adding and (age != shown.current_age or result.get("before_maximum") != shown.maximum
                or maximum < shown.maximum or type(result.get("actual_delta")) not in (int, float)
                or not math.isfinite(result["actual_delta"]) or result["actual_delta"] < 0):
            raise UncertainWrite("增加寿元后的年龄或实际上限未确认，请核对游戏，勿重复操作。")
        fresh = self.adapter.read_context()
        if (fresh["identity"][:9] != context["identity"][:9]
                or pack(fresh["growth"]) != pack(expected_growth)
                or adding and not fresh["growth_address"] or not adding and fresh != context):
            raise UncertainWrite("寿元请求后的角色或成长值回读不符，请核对游戏，勿重复操作。")
        target = LifespanTarget(age, maximum, growth, fresh["growth_address"], fresh["identity"], fresh["anchors"])
        return dict(target=target, current_age=age, maximum=maximum, growth=growth, can_edit=True,
                    exhausted=False, verified=True, added=amount if adding else 0,
                    before_maximum=shown.maximum if adding else maximum,
                    actual_delta=result.get("actual_delta", 0.0))

    def execute(self, context, shown=None, amount=None):
        adding = shown is not None
        if adding:
            validate_increase(shown, amount)
        self.require_ready()
        descriptor = self.adapter.prepare_native(context, shown, amount)
        pid, created = self.game.resolver.reader.pid, self.game.stamp[1]
        token = uuid.uuid4().hex
        preview = self.request(descriptor, pid, token, adding)
        import frida
        if frida.__version__ != "17.7.3":
            raise Refused("寿元连接组件版本不匹配。")
        identity = dict(token=token, pid=pid, process_creation_filetime=created, operation=preview["operation"],
                        amount=amount, growth_before=context["growth"])
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
                outcome.update(status="unknown", reason=message.get("description", "native bridge error"))
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
                self.record(dict(identity, status="attach_failed", called=False, stage=exc.stage, error=str(exc.original)))
                raise Refused("原生连接加载失败，尚未调用寿元方法。") from exc
            self.record(dict(identity, status="not_dispatched", called=False))
            fresh = self.adapter.prepare_native(context, shown, amount)
            if fresh != descriptor:
                raise Refused("连接期间寿元或场景变化，未调用。")
            request = self.request(fresh, pid, token, adding)
            self.record(dict(identity, status="pending", called=None))
            dispatched = self._native_inflight = True
            self._connection.previous_token = token
            self._script.exports_sync.submit(request)
            if not done.wait(12):
                outcome.update(status="unknown", reason="等待游戏主线程超时，不重试。")
            if outcome.get("status") in ("rejected", "cancelled") and outcome.get("called") is False:
                self.record(dict(identity, status=outcome["status"], called=False, result=outcome))
                dispatched = False
                raise Refused(outcome.get("reason") or "角色或寿元状态不允许此操作。")
            result = self.checked_result(outcome, context, shown, amount)
            self.record(dict(identity, status="verified", called=True, result=outcome))
            return result
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
                message = ("寿元增加已派发，但验证未完成；请核对游戏，勿重复增加。" if adding else
                           "寿元查询结果未确认；本次没有请求增加寿元，连接已停止。")
                raise UncertainWrite(message) from exc
            raise
        finally:
            self.close()
