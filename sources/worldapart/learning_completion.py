"""Fill one reviewed learning round once, then observe ordinary game settlement.

This path never injects or calls game methods. Its only possible game write is
the current runtime's CurrentValue float32, set to that round's config limit.
Manual float edits retain their separate 1000-point change limit.
"""
from native_scalar_guard import coordinated_scalar_write

import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import uuid

from learning_write import FloatTarget, FloatWriteOnce
from native_write import K, MBI, process_identity, read_exact_handle
from runtime_paths import initialize_runtime
from write_guard import Refused, UncertainWrite

OBSERVE_SECONDS = 2.0
OBSERVE_INTERVAL = 0.05
MAX_OBSERVATIONS = 41
SUMMARY_FIELDS = (
    "active", "can_complete", "phase", "end_reason", "current_value", "maximum",
    "demon_value", "remaining_seconds", "paused", "result_shown", "result_success",
    "learn_effect_executed", "learn_effect_failed", "callback_invoked",
    "result_exit_handled", "should_complete_on_exit", "round_key", "status",
)


def _summary(state):
    return {key: state[key] for key in SUMMARY_FIELDS if key in state}


def _round_id(key):
    if isinstance(key, str):
        return key  # An already-stored claim key.
    return hashlib.sha256(json.dumps(key, separators=(",", ":"), allow_nan=False).encode("utf8")).hexdigest()


def _require_no_native_pending():
    from acquisition_adapter import native_calls_pending
    if native_calls_pending():
        raise Refused("游戏原生操作尚未完成，未写入学习进度；请先等待结果。")


def _validate_prepared(state):
    if not isinstance(state, dict) or state.get("can_complete") is not True:
        raise Refused((state or {}).get("reason", "当前学习局不能自动完成。")
                      if isinstance(state, dict) else "学习局数据不完整。")
    key = state.get("round_key")
    if (type(key) is not tuple or len(key) != 14 or type(key[0]) is not tuple or len(key[0]) != 2
            or not isinstance(key[0][0], str) or type(key[0][1]) is not int or key[0][1] <= 0
            or any(type(value) is not int for value in key[1:])):
        raise Refused("当前学习局缺少稳定身份，未写入。")
    if state.get("identity") != key:
        raise Refused("当前学习局身份不一致，未写入。")
    target, maximum, runtime = state.get("target"), state.get("maximum"), state.get("runtime")
    panel = state.get("panel")
    if (not isinstance(target, FloatTarget) or target.key != "learning_value"
            or type(maximum) is not int or not 1 <= maximum <= 1_000_000
            or type(runtime) is not int or runtime <= 0 or runtime % 8
            or type(panel) is not int or panel <= 0 or panel % 8 or key[4] != panel
            or target.address != runtime + 0xA8 or key[7] != runtime
            or type(target.minimum) not in (int, float) or target.minimum != 0
            or type(target.maximum) not in (int, float) or target.maximum != float(maximum)
            or not isinstance(target.identity, tuple)):
        raise Refused("学习进度字段或当前配置阈值不匹配，未写入。")
    if (type(target.value) not in (int, float) or not math.isfinite(target.value)
            or not 0 <= target.value <= maximum or state.get("current_value") != target.value):
        raise Refused("当前学习进度无效，未写入。")
    if type(target.anchors) is not tuple or not 1 <= len(target.anchors) <= 4096:
        raise Refused("学习局锚点不完整，未写入。")
    for anchor in target.anchors:
        if (type(anchor) is not tuple or len(anchor) != 2 or type(anchor[0]) is not int
                or anchor[0] <= 0 or not isinstance(anchor[1], str)):
            raise Refused("学习局锚点格式无效，未写入。")
        try:
            raw = bytes.fromhex(anchor[1])
        except ValueError as error:
            raise Refused("学习局锚点格式无效，未写入。") from error
        if not 1 <= len(raw) <= 64:
            raise Refused("学习局锚点范围无效，未写入。")
    guards = state.get("completion_guards")
    expected = {"elapsed_address": runtime + 0x8C, "duration_address": runtime + 0x58,
                "demon_address": runtime + 0xAC, "paused_address": panel + 0x93}
    if (not isinstance(guards, dict) or any(guards.get(k) != v for k, v in expected.items())
            or type(guards.get("paused_address")) is not int or guards["paused_address"] <= 0):
        raise Refused("学习完成前置条件地址不完整，未写入。")
    if (state.get("active") is not True or type(state.get("phase")) is not int
            or state["phase"] not in (1, 2, 3) or type(state.get("end_reason")) is not int
            or state["end_reason"] != 0):
        raise Refused("学习局已经结束，未写入。")
    return target


class _CompletionWriteOnce(FloatWriteOnce):
    """Restricted construction bypasses only the manual delta cap, not guards."""
    def __init__(self, reader, stamp, prepared):
        import struct
        self.target = _validate_prepared(prepared)
        self.reader, self.stamp = reader, stamp
        self.before = struct.pack("<f", self.target.value)
        self.after = struct.pack("<f", float(prepared["maximum"]))
        self.guards = dict(prepared["completion_guards"])
        self.used = self.attempted = False

    @coordinated_scalar_write
    def write_exact(self, address, value):
        import struct
        if (self.used or address != self.target.address or type(value) is not bytes
                or value != self.after or value == self.before):
            raise Refused("自动完成只能单次写入当前局的真实阈值。")
        self.used = True
        handle = K.OpenProcess(0x438, False, self.reader.pid)
        if not handle:
            raise Refused("当前权限不能写入游戏。")
        try:
            if process_identity(handle) != self.stamp:
                raise Refused("游戏进程已变化，未写入。")
            region = MBI()
            if not K.VirtualQueryEx(handle, address, C.byref(region), C.sizeof(region)):
                raise Refused("学习目标内存不可查询，未写入。")
            if (region.State != 0x1000 or region.Type != 0x20000 or region.Protect != 4
                    or not region.BaseAddress or address < region.BaseAddress
                    or address + 4 > region.BaseAddress + region.RegionSize):
                raise Refused("学习目标不是普通可写对象内存，未写入。")
            for pointer, encoded in self.target.anchors:
                expected = bytes.fromhex(encoded)
                if read_exact_handle(handle, pointer, len(expected)) != expected:
                    raise Refused("学习局次或界面已变化，未写入。")
            numbers = [struct.unpack("<f", read_exact_handle(handle, self.guards[key], 4))[0]
                       for key in ("elapsed_address", "duration_address", "demon_address")]
            elapsed, duration, demon = numbers
            if (not all(math.isfinite(v) for v in numbers) or not 0 <= elapsed < duration
                    or not 0 <= demon < 100
                    or read_exact_handle(handle, self.guards["paused_address"], 1) != b"\0"):
                raise Refused("学习局已暂停、到时或达到心魔失败条件，未写入。")
            if read_exact_handle(handle, address, 4) != self.before:
                raise Refused("学习进度刚刚变化，未写入；请重新检测当前局。")
            buffer, count = C.create_string_buffer(value), C.c_size_t()
            _require_no_native_pending()
            self.attempted = True  # No later exception can be called a no-write outcome.
            if not K.WriteProcessMemory(handle, address, buffer, 4, C.byref(count)) or count.value != 4:
                raise UncertainWrite("学习进度写入结果未确认；本局不会自动重试。")
        finally:
            K.CloseHandle(handle)


class _PriorClaim(Exception):
    def __init__(self, event):
        self.event = event


class LearningCompletion:
    def __init__(self, game_adapter, resolver, *, storage_root=None):
        self.game, self.resolver = game_adapter, resolver
        self.directory = Path(storage_root) if storage_root is not None else initialize_runtime()
        self.directory = self.directory / "learning-completion-claims"
        self._lock = threading.Lock()

    @staticmethod
    def _result(status, phase, key, written, observed, message):
        return dict(status=status, phase=phase, round_key=_round_id(key), written=written,
                    observed=_summary(observed), message=message, save_verified=False)

    def _create_claim(self, state):
        key = _round_id(state["round_key"])
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (key + ".json")
        event = dict(version=1, operation="learning_completion", round_key=key,
                     token=uuid.uuid4().hex, status="pending", written=None,
                     pid=self.game.resolver.reader.pid, process_creation_filetime=self.game.stamp[1],
                     created_at=time.time(), address=hex(state["target"].address),
                     before=state["target"].value, after=state["maximum"])
        try:
            with path.open("x", encoding="utf8") as output:
                json.dump(event, output, ensure_ascii=False, allow_nan=False)
                output.flush()
                import os
                os.fsync(output.fileno())
        except FileExistsError:
            try:
                old = json.loads(path.read_text(encoding="utf8"))
                if (not isinstance(old, dict) or old.get("version") != 1
                        or old.get("operation") != "learning_completion" or old.get("round_key") != key
                        or not isinstance(old.get("token"), str) or not isinstance(old.get("status"), str)):
                    raise ValueError("invalid claim")
            except Exception as error:
                raise UncertainWrite("本局完成记录无法核对；为避免重复写入，已停止操作，请保留日志。") from error
            raise _PriorClaim(old)
        except Exception as error:
            # Even a partial exclusive claim is kept: another process must not
            # mistake a failed durable write for permission to enter this round.
            if path.exists():
                raise UncertainWrite("本次尚未写入游戏，但完成记录未能落盘；已保留占用记录，请检查日志目录。") from error
            raise Refused("无法保存学习完成记录，未写入游戏。") from error
        return path, event

    @staticmethod
    def _owned(path, event):
        current = json.loads(path.read_text(encoding="utf8"))
        if current.get("token") != event["token"] or current.get("round_key") != event["round_key"]:
            raise RuntimeError("Learning completion claim ownership changed")

    def _persist(self, path, event):
        import os
        self._owned(path, event)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("x", encoding="utf8") as output:
            json.dump(event, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
        self.game.record(dict(learning_completion=event))

    def _release_unwritten(self, path, event):
        self._owned(path, event)
        path.unlink()  # Only our exact exclusive claim; no other instance can own it.

    def _prior_result(self, event):
        saved = event.get("result")
        if isinstance(saved, dict) and saved.get("status") in ("confirmed", "filled_pending", "failed", "unknown"):
            result = dict(saved, repeated=True, written=False)
            result["message"] = "本局已经尝试完成，没有重复写入。" + saved.get("message", "请核对游戏。")
            return result
        return self._result("unknown", "unknown", event["round_key"], False, {},
                            "本局已有完成请求，之前的结果尚未确认；没有重复写入，请核对游戏。")

    def complete(self, shown):
        if not self._lock.acquire(blocking=False):
            raise Refused("当前学习完成请求仍在处理中，未派发新的写入。")
        try:
            return self._complete(shown)
        finally:
            self._lock.release()

    def _complete(self, shown):
        _require_no_native_pending()
        prepared = self.resolver.prepare_completion(shown)
        target = _validate_prepared(prepared)
        if (prepared["round_key"][0] != self.game.stamp
                or process_identity(self.game.resolver.reader.h) != self.game.stamp):
            raise Refused("游戏进程已变化，未写入。")
        if target.value == target.maximum:
            return self._observe(prepared, written=False, filled=True)
        try:
            path, event = self._create_claim(prepared)
        except _PriorClaim as previous:
            return self._prior_result(previous.event)
        writer, released = None, False
        try:
            fresh = self.resolver.prepare_completion(prepared)
            target = _validate_prepared(fresh)
            if fresh["round_key"] != prepared["round_key"]:
                raise Refused("学习局次已变化，未写入。")
            if target.value == target.maximum:
                self._release_unwritten(path, event)
                released = True
                return self._observe(fresh, written=False, filled=True)
            event.update(before=target.value, after=fresh["maximum"], address=hex(target.address))
            self._persist(path, event)
            writer = _CompletionWriteOnce(self.game.resolver.reader, self.game.stamp, fresh)
            writer.write_exact(target.address, writer.after)
        except Exception as error:
            if writer is None or not writer.attempted:
                try:
                    if not released:
                        self._release_unwritten(path, event)
                except Exception as release_error:
                    raise UncertainWrite("本次尚未写入游戏，但完成记录未能释放；请保留日志后检查。") from release_error
                if isinstance(error, Refused):
                    raise
                raise Refused("完成前核对或记录失败，未写入游戏：" + str(error)) from error
            try:
                event.update(status="unknown", written=None, error=str(error))
                self._persist(path, event)
            except Exception:
                pass  # The already-durable exclusive pending claim blocks retry.
            raise UncertainWrite("学习进度写入已经尝试，结果未确认；本局禁止重试，请核对游戏。") from error
        try:
            try:
                filled = writer.read_exact(target.address, 4) == writer.after
            except Exception:
                filled = False
            event.update(status="progress_written" if filled else "observing", written=True)
            self._persist(path, event)
            result = self._observe(fresh, written=True, filled=filled)
            event.update(status=result["status"], result=result)
            self._persist(path, event)
            return result
        except Exception as error:
            try:
                event.update(status="unknown", written=True, error=str(error))
                self._persist(path, event)
            except Exception:
                pass
            raise UncertainWrite("写入后的学习状态或日志未能确认；本局禁止重试，请核对游戏。") from error

    def _observe(self, prepared, *, written, filled):
        key, started = prepared["round_key"], time.monotonic()
        last, progress_seen, success_seen = {}, filled, False
        for index in range(MAX_OBSERVATIONS):
            try:
                state = self.resolver.observe_completion(prepared)
            except Exception as error:
                return self._result("unknown", "unknown", key, written, last,
                                    "当前局的结果已无法持续核对；不会自动重复写入，请回游戏核对。" + str(error))
            if (not isinstance(state, dict) or state.get("round_key") != key
                    or state.get("identity") != prepared["identity"]):
                return self._result("unknown", "unknown", key, written, last,
                                    "学习局次已切换，无法确认原局结果；没有操作新局，请回游戏核对。")
            last = state
            phase, end = state.get("phase"), state.get("end_reason")
            if type(phase) is not int or type(end) is not int:
                return self._result("unknown", "unknown", key, written, state, "游戏完成状态无效，请回游戏核对。")
            if state.get("learn_effect_failed") is True or phase == 4 and end in (1, 3, 4):
                return self._result("failed", "game_failed", key, written, state,
                                    "游戏已结束本局，但未确认学习成功；本局不会重复写入，请查看游戏提示。")
            success = phase == 4 and end == 2
            current, maximum = state.get("current_value"), state.get("maximum")
            valid_value = (type(current) in (int, float) and math.isfinite(current)
                           and type(maximum) is int and maximum == prepared["maximum"]
                           and 0 <= current <= maximum)
            if (not valid_value or not (success or phase in (1, 2, 3) and end == 0)
                    or success_seen and not success):
                return self._result("unknown", "unknown", key, written, state,
                                    "学习状态已超出可确认范围；本局不会重复写入，请回游戏核对。")
            applied = success and all(state.get(k) is True for k in
                ("result_shown", "result_exit_handled", "learn_effect_executed", "result_success")) and all(
                state.get(k) is False for k in ("learn_effect_failed", "should_complete_on_exit"))
            if applied:
                return self._result("confirmed", "learning_applied", key, written, state,
                                    "游戏已确认学习成功。请回游戏核对，需要保留时手动存档；修改器未验证存档。")
            success_seen |= success
            progress_seen = current == maximum
            if index + 1 >= MAX_OBSERVATIONS or time.monotonic() - started >= OBSERVE_SECONDS:
                break
            time.sleep(min(OBSERVE_INTERVAL, max(0.0, OBSERVE_SECONDS - (time.monotonic() - started))))
        if success_seen:
            return self._result("filled_pending", "round_success", key, written, last,
                                "游戏已判定本局成功，学习效果仍待游戏完成；本局不会重复写入，请回游戏核对。")
        if progress_seen:
            return self._result("filled_pending", "progress_written", key, written, last,
                                "当前局进度已达到所需阈值，尚未确认游戏结算；本局不会重复写入，请回游戏核对。")
        return self._result("unknown", "unknown", key, written, last,
                            "写入后的进度已变化，学习结果未确认；本局不会重复写入，请回游戏核对。")
