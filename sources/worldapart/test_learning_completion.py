"""Offline completion lifecycle, exclusive claims, and exact float32 boundary tests."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import learning_completion as lc
import learning_write as lw
from write_guard import Refused, UncertainWrite

STAMP = ("d:\\游戏 library\\WorldApart.exe", 12345)
RUNTIME = 0x9000
VALUE = RUNTIME + 0xA8


def state(value=10.0, maximum=2000):
    key = (STAMP, 0x20000, 0x30000, 0x40000, 0x8000, 0x880000, 7,
           RUNTIME, 0xA000, 8, 2, 104, 1, 0)
    anchors = ((RUNTIME, struct.pack("<Q", 0x5000).hex()),
               (RUNTIME + 0xA0, struct.pack("<ii", 1, 0).hex()))
    target = lw.FloatTarget("learning_value", VALUE, value, key, 0.0, float(maximum), anchors)
    return dict(active=True, can_complete=True, reason="", round_key=key, identity=key,
                panel=0x8000, runtime=RUNTIME, phase=1, end_reason=0, current_value=value,
                maximum=maximum, target=target, demon_value=0.0, remaining_seconds=59.0,
                paused=False, result_shown=False, result_success=False, learn_effect_executed=False,
                learn_effect_failed=False, callback_invoked=False, result_exit_handled=False,
                should_complete_on_exit=False, status="active",
                completion_guards=dict(elapsed_address=RUNTIME + 0x8C,
                    duration_address=RUNTIME + 0x58, demon_address=RUNTIME + 0xAC, paused_address=0x8093))


def terminal(prepared, *, applied=False, end=2):
    observed = deepcopy(prepared)
    observed.update(active=False, can_complete=False, phase=4, end_reason=end,
                    current_value=float(prepared["maximum"]), result_shown=True,
                    result_success=end == 2, status="round_success" if end == 2 else "failed",
                    result_exit_handled=applied, learn_effect_executed=applied,
                    should_complete_on_exit=not applied and end == 2)
    return observed


class FakeResolver:
    def __init__(self, prepared):
        self.prepared = prepared
        self.prepares = []
        self.observations = [dict(prepared, current_value=float(prepared["maximum"]))]
        self.prepare_count = self.observe_count = 0

    def prepare_completion(self, shown=None):
        self.prepare_count += 1
        current = self.prepares.pop(0) if self.prepares else self.prepared
        if isinstance(current, Exception):
            raise current
        return deepcopy(current)

    def observe_completion(self, shown):
        self.observe_count += 1
        result = self.observations.pop(0) if len(self.observations) > 1 else self.observations[0]
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prepared = state()
        self.resolver = FakeResolver(self.prepared)
        self.data, self.writes, self.records = {}, [], []
        self.reader = SimpleNamespace(h=1, pid=77)
        self.game = SimpleNamespace(resolver=SimpleNamespace(reader=self.reader), stamp=STAMP,
                                    record=lambda event: self.records.append(deepcopy(event)))
        self.completion = lc.LearningCompletion(self.game, self.resolver, storage_root=self.temp.name)
        self.region_ok = True
        self.write_return = True
        self.write_count = 4
        self.after_write = lambda: None
        for pointer, raw in self.prepared["target"].anchors:
            self.put(pointer, bytes.fromhex(raw))
        self.number(VALUE, self.prepared["current_value"])
        self.number(RUNTIME + 0x8C, 1.0)
        self.number(RUNTIME + 0x58, 60.0)
        self.number(RUNTIME + 0xAC, 0.0)
        self.put(0x8093, b"\0")
        pending_patcher = patch("acquisition_adapter.native_calls_pending", return_value=False)
        pending_patcher.start()
        self.addCleanup(pending_patcher.stop)
        kernel = SimpleNamespace(OpenProcess=lambda *args: 22, CloseHandle=lambda handle: None,
                                 VirtualQueryEx=self.region, WriteProcessMemory=self.write)
        for module, name, value in ((lc, "K", kernel), (lc, "process_identity", lambda handle: STAMP),
                                   (lc, "read_exact_handle", self.read),
                                   (lw, "process_identity", lambda handle: STAMP),
                                   (lw, "read_exact_handle", self.read), (lc, "OBSERVE_SECONDS", 0.0)):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def put(self, address, raw):
        self.data.update({address + i: value for i, value in enumerate(raw)})

    def number(self, address, value):
        self.put(address, struct.pack("<f", value))

    def read(self, handle, address, size):
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError as error:
            raise Refused("short read") from error

    def region(self, handle, address, pointer, size):
        obj = pointer._obj
        obj.BaseAddress, obj.RegionSize = RUNTIME, 0x1000
        obj.State, obj.Type, obj.Protect = 0x1000, 0x20000, 4 if self.region_ok else 2
        return 1

    def write(self, handle, address, buffer, size, count):
        data = bytes(buffer.raw[:size])
        self.writes.append((address, data, size))
        self.put(address, data)
        count._obj.value = self.write_count
        self.after_write()
        return self.write_return

    def run_complete(self):
        return self.completion.complete(self.prepared)

    def claims(self):
        return list((Path(self.temp.name) / "learning-completion-claims").glob("*.json"))

    def test_over_1000_exact_threshold_is_one_write_and_manual_cap_unchanged(self):
        with self.assertRaises(Refused):
            lw.validate_float(self.prepared["target"], 2000)
        result = self.run_complete()
        self.assertEqual(self.writes, [(VALUE, struct.pack("<f", 2000), 4)])
        self.assertEqual((result["status"], result["phase"]), ("filled_pending", "progress_written"))
        self.assertFalse(result["save_verified"])
        self.assertEqual(len(self.claims()), 1)

    def test_only_learning_value_at_exact_runtime_field_can_be_written(self):
        for changed in (replace(self.prepared["target"], key="learning_epiphany"),
                        replace(self.prepared["target"], address=VALUE + 4),
                        replace(self.prepared["target"], maximum=2001)):
            with self.subTest(changed=changed):
                self.resolver.prepared = dict(self.prepared, target=changed)
                with self.assertRaises(Refused):
                    self.run_complete()
        self.assertEqual(self.writes, [])

    def test_invalid_or_unsupported_thresholds_never_claim_or_write(self):
        for maximum in (True, 0, -1, 1_000_001, float("nan")):
            with self.subTest(maximum=maximum):
                self.resolver.prepared = dict(self.prepared, maximum=maximum)
                with self.assertRaises(Refused):
                    self.run_complete()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_native_pending_at_entry_never_prepares_claims_or_writes(self):
        with patch("acquisition_adapter.native_calls_pending", return_value=True):
            with self.assertRaises(Refused):
                self.run_complete()
        self.assertEqual(self.resolver.prepare_count, 0)
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.writes, [])

    def test_native_pending_at_last_write_boundary_releases_unwritten_claim(self):
        with patch("acquisition_adapter.native_calls_pending", side_effect=[False, True]) as pending:
            with self.assertRaises(Refused):
                self.run_complete()
        self.assertEqual(pending.call_count, 2)
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.writes, [])

    def test_wrong_pause_field_is_rejected_before_claim_or_write(self):
        self.resolver.prepared = dict(self.prepared, completion_guards=dict(
            self.prepared["completion_guards"], paused_address=0x8058))
        with self.assertRaises(Refused):
            self.run_complete()
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.writes, [])

    def test_panel_must_match_stable_round_and_be_aligned_positive_pointer(self):
        for panel in (0, -8, 0x8001, 0x8100, True):
            with self.subTest(panel=panel):
                self.resolver.prepared = dict(self.prepared, panel=panel)
                with self.assertRaises(Refused):
                    self.run_complete()
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.writes, [])

    def test_already_full_is_observed_without_write_or_claim(self):
        self.resolver.prepared = state(value=2000.0)
        self.resolver.observations = [terminal(self.resolver.prepared, applied=True)]
        result = self.run_complete()
        self.assertEqual(result["status"], "confirmed")
        self.assertFalse(result["written"])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_naturally_full_during_claim_is_released_without_write(self):
        self.resolver.prepares = [self.prepared, state(value=2000.0)]
        result = self.run_complete()
        self.assertFalse(result["written"])
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_same_round_natural_progress_uses_fresh_prepared_value(self):
        self.resolver.prepares = [self.prepared, state(value=11.0)]
        self.number(VALUE, 11.0)
        self.run_complete()
        self.assertEqual(len(self.writes), 1)
        saved = json.loads(self.claims()[0].read_text(encoding="utf8"))
        self.assertEqual(saved["before"], 11.0)

    def test_round_switch_before_write_releases_claim_and_does_not_touch_new_round(self):
        changed = state()
        key = list(changed["round_key"])
        key[9] += 1
        changed.update(round_key=tuple(key), identity=tuple(key))
        self.resolver.prepares = [self.prepared, changed]
        with self.assertRaises(Refused):
            self.run_complete()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_stale_phase_anchor_blocks_and_proven_no_write_can_retry(self):
        self.put(RUNTIME + 0xA0, struct.pack("<ii", 4, 1))
        with self.assertRaises(Refused):
            self.run_complete()
        self.assertEqual(self.claims(), [])
        self.put(RUNTIME + 0xA0, struct.pack("<ii", 1, 0))
        self.run_complete()
        self.assertEqual(len(self.writes), 1)

    def test_final_pause_deadline_and_demon_guards_prevent_write(self):
        for pointer, raw in ((0x8093, b"\1"), (RUNTIME + 0x8C, struct.pack("<f", 60)),
                             (RUNTIME + 0xAC, struct.pack("<f", 100)),
                             (RUNTIME + 0xAC, struct.pack("<f", float("nan")))):
            before = self.read(None, pointer, len(raw))
            self.put(pointer, raw)
            with self.subTest(pointer=pointer), self.assertRaises(Refused):
                self.run_complete()
            self.put(pointer, before)
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_readonly_region_and_changed_before_bytes_refuse_before_write(self):
        self.region_ok = False
        with self.assertRaises(Refused):
            self.run_complete()
        self.region_ok = True
        self.number(VALUE, 11.0)
        with self.assertRaises(Refused):
            self.run_complete()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_process_change_never_creates_claim(self):
        with patch.object(lc, "process_identity", return_value=(STAMP[0], STAMP[1] + 1)):
            with self.assertRaises(Refused):
                self.run_complete()
        self.assertEqual(self.claims(), [])

    def test_partial_or_failed_win32_write_keeps_claim_and_never_retries(self):
        self.write_count = 2
        with self.assertRaises(UncertainWrite):
            self.run_complete()
        self.assertEqual(len(self.claims()), 1)
        result = self.run_complete()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(self.writes), 1)

    def test_write_exception_keeps_pending_and_is_not_refused(self):
        self.after_write = lambda: (_ for _ in ()).throw(RuntimeError("simulated transport error"))
        with self.assertRaises(UncertainWrite):
            self.run_complete()
        self.assertEqual(len(self.claims()), 1)
        self.assertEqual(len(self.writes), 1)

    def test_duplicate_completed_request_returns_history_without_second_write(self):
        self.resolver.observations = [terminal(self.prepared, applied=True)]
        self.assertEqual(self.run_complete()["status"], "confirmed")
        other = lc.LearningCompletion(self.game, self.resolver, storage_root=self.temp.name)
        repeated = other.complete(self.prepared)
        self.assertEqual(repeated["status"], "confirmed")
        self.assertTrue(repeated["repeated"])
        self.assertFalse(repeated["written"])
        self.assertEqual(len(self.writes), 1)

    def test_two_instances_exclusively_claim_same_round(self):
        other = lc.LearningCompletion(self.game, self.resolver, storage_root=self.temp.name)
        barrier, results = threading.Barrier(2), []
        def claim(completion):
            barrier.wait()
            try:
                completion._create_claim(self.prepared)
                results.append("owner")
            except lc._PriorClaim:
                results.append("blocked")
            except UncertainWrite:
                results.append("blocked")  # A concurrent partial record also fails closed.
        threads = [threading.Thread(target=claim, args=(obj,)) for obj in (self.completion, other)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(results, ["owner", "blocked"])
        self.assertEqual(len(self.claims()), 1)

    def test_corrupt_existing_claim_fails_closed(self):
        self.completion.directory.mkdir()
        path = self.completion.directory / (lc._round_id(self.prepared["round_key"]) + ".json")
        path.write_text("{broken")
        with self.assertRaises(UncertainWrite):
            self.run_complete()
        self.assertEqual(self.writes, [])

    def test_claim_fsync_failure_blocks_before_write(self):
        with patch("os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(UncertainWrite):
                self.run_complete()
        self.assertEqual(self.writes, [])
        self.assertEqual(len(self.claims()), 1)

    def test_log_failure_before_write_releases_claim(self):
        self.game.record = lambda event: (_ for _ in ()).throw(OSError("disk full"))
        with self.assertRaises(Refused):
            self.run_complete()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.claims(), [])

    def test_log_failure_after_write_is_uncertain_and_claim_persists(self):
        calls = []
        def record(event):
            calls.append(event)
            if len(calls) > 1:
                raise Refused("postwrite log failed")
        self.game.record = record
        with self.assertRaises(UncertainWrite):
            self.run_complete()
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(len(self.claims()), 1)

    def test_success_requires_effect_applied_flags_not_only_finished(self):
        self.resolver.observations = [terminal(self.prepared)]
        result = self.run_complete()
        self.assertEqual((result["status"], result["phase"]), ("filled_pending", "round_success"))

    def test_applied_flag_before_effect_return_does_not_confirm(self):
        observed = terminal(self.prepared, applied=True)
        observed["should_complete_on_exit"] = True
        self.resolver.observations = [observed]
        self.assertEqual(self.run_complete()["status"], "filled_pending")

    def test_learning_effect_failure_is_reported_without_retry(self):
        observed = terminal(self.prepared, applied=True)
        observed.update(learn_effect_failed=True, result_success=False)
        self.resolver.observations = [observed]
        result = self.run_complete()
        self.assertEqual(result["status"], "failed")
        self.run_complete()
        self.assertEqual(len(self.writes), 1)

    def test_timeout_and_demon_failure_not_mistaken_for_success(self):
        self.resolver.observations = [terminal(self.prepared, end=4)]
        self.assertEqual(self.run_complete()["status"], "failed")

    def test_readback_failure_can_be_resolved_by_same_round_applied_state(self):
        self.resolver.observations = [terminal(self.prepared, applied=True)]
        with patch.object(lw, "read_exact_handle", side_effect=OSError("late read failure")):
            result = self.run_complete()
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(len(self.writes), 1)

    def test_observation_failure_returns_unknown_and_keeps_claim(self):
        self.resolver.observations = [Refused("original panel disappeared")]
        result = self.run_complete()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(self.claims()), 1)
        self.assertEqual(len(self.writes), 1)

    def test_changed_round_is_unknown_and_never_written(self):
        observed = terminal(self.prepared, applied=True)
        key = list(observed["round_key"])
        key[7] += 0x1000
        observed.update(round_key=tuple(key), identity=tuple(key))
        self.resolver.observations = [observed]
        self.assertEqual(self.run_complete()["status"], "unknown")
        self.assertEqual([write[0] for write in self.writes], [VALUE])

    def test_progress_consumption_is_unknown_not_a_retry(self):
        self.after_write = lambda: self.number(VALUE, 1999.0)
        self.resolver.observations = [dict(self.prepared, current_value=1999.0)]
        self.assertEqual(self.run_complete()["status"], "unknown")
        self.run_complete()
        self.assertEqual(len(self.writes), 1)

    def test_inactive_or_missing_state_is_not_success(self):
        self.resolver.observations = [{"active": False}]
        self.assertEqual(self.run_complete()["status"], "unknown")

    def test_bounded_observation_can_see_success_then_applied(self):
        self.resolver.observations = [dict(self.prepared, current_value=2000.0),
                                      terminal(self.prepared), terminal(self.prepared, applied=True)]
        with patch.object(lc, "OBSERVE_SECONDS", 10), patch.object(lc.time, "sleep"):
            self.assertEqual(self.run_complete()["status"], "confirmed")
        self.assertEqual(self.resolver.observe_count, 3)
        self.assertEqual(len(self.writes), 1)

    def test_observation_has_independent_iteration_bound(self):
        with patch.object(lc, "OBSERVE_SECONDS", 10), patch.object(lc, "MAX_OBSERVATIONS", 3), \
                patch.object(lc.time, "sleep"):
            self.assertEqual(self.run_complete()["status"], "filled_pending")
        self.assertEqual(self.resolver.observe_count, 3)


if __name__ == "__main__":
    unittest.main()
