"""Spirit-stone limits across resolution, policy, native boundary and UI.

All process APIs, scalar leases and configuration reads are mocked. No game,
broker connection, Tk window or persistent safety record is touched.
"""
from contextlib import contextmanager
from dataclasses import replace
import ctypes as C
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import app
import game_adapter
import native_scalar_guard
import native_write
import test_app as app_fixtures
import test_game_adapter as adapter_fixtures
import test_write_guard as guard_fixtures
import write_guard as guard


def stone_target(value=17_100, maximum=None):
    return guard.Target(
        "currency:7", 0x8014, value, ("reviewed-player", "stone-uid-7"), 0,
        game_adapter.SPIRIT_STONE_EDIT_MAXIMUM if maximum is None else maximum,
        max_change=guard.SPIRIT_STONE_MAX_CHANGE)


class CurrencyResolutionTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing fake save-chain fixture without inheriting or
        # importing its TestCase as a module-level test class.
        adapter_fixtures.AdapterTests.setUp(self)
        self.definition = self.config["items"][0]
        self.definition.update(
            id=game_adapter.SPIRIT_STONE_ITEM_ID, is_currency=True,
            item_type_id=5, hide_in_bag=True, auto_use=None,
            can_discard=False, max_count_per_grid=guard.INT32_MAX,
            names={"zh-Hans": "灵石"})
        self.raw["items"][0].update(item_id=game_adapter.SPIRIT_STONE_ITEM_ID,
                                     count=17_100)

    def target(self):
        return self.adapter.snapshot()["currencies"]["currency:7"]["target"]

    def test_only_reviewed_stone_gets_hundred_million_change_and_larger_balance(self):
        target = self.target()
        self.assertEqual(guard.SPIRIT_STONE_MAX_CHANGE, 100_000_000)
        self.assertEqual(game_adapter.SPIRIT_STONE_EDIT_MAXIMUM, 999_999_999)
        self.assertEqual((target.minimum, target.maximum, target.max_change),
                         (0, 999_999_999, 100_000_000))
        self.assertEqual(self.adapter.resolve(target.key), target)
        self.assertEqual(self.adapter.snapshot()["spirit"].max_change, guard.MAX_CHANGE)
        self.assertEqual(self.adapter.snapshot()["path"].max_change, guard.MAX_CHANGE)

    def test_zero_and_existing_balance_above_old_million_cap_remain_editable(self):
        for value in (0, 100_017_100, game_adapter.SPIRIT_STONE_EDIT_MAXIMUM):
            with self.subTest(value=value):
                self.raw["items"][0]["count"] = value
                self.assertEqual(self.target().value, value)
                self.assertEqual(self.target().max_change, 100_000_000)

    def test_runtime_configuration_still_bounds_target_balance(self):
        for runtime_cap, expected in ((500_000, 500_000),
                                      (1_500_000, 1_500_000),
                                      (guard.INT32_MAX, 999_999_999)):
            with self.subTest(runtime_cap=runtime_cap):
                self.definition["max_count_per_grid"] = runtime_cap
                self.assertEqual(self.target().maximum, expected)

    def test_balance_above_actual_runtime_cap_is_not_exposed_as_writable(self):
        self.definition["max_count_per_grid"] = 500_000
        self.raw["items"][0]["count"] = 500_001
        self.assertEqual(self.adapter.snapshot()["currencies"], {})

    def test_names_never_grant_stone_limit_to_other_currency(self):
        self.raw["items"][0]["item_id"] = game_adapter.SPIRIT_STONE_ITEM_ID + 1
        self.definition["id"] = self.raw["items"][0]["item_id"]
        # Even a counterfeit identical localized name must keep the old limit.
        for name in ("灵石", "Spirit Stone", "其他货币"):
            with self.subTest(name=name):
                self.definition["names"] = {"zh-Hans": name}
                target = self.target()
                self.assertEqual((target.maximum, target.max_change),
                                 (game_adapter.CURRENCY_EDIT_MAXIMUM, guard.MAX_CHANGE))

    def test_item_id_alone_without_exact_currency_classification_is_insufficient(self):
        for currency, item_type in ((True, 17), (True, "5"), (1, 5),
                                    (False, 5), (None, 5)):
            with self.subTest(currency=currency, item_type=item_type):
                self.definition.update(is_currency=currency, item_type_id=item_type,
                                       hide_in_bag=False, can_discard=True)
                state = self.adapter.snapshot()
                rows = list(state["currencies"].values()) + list(state["items"].values())
                self.assertTrue(rows)
                self.assertEqual(rows[0]["target"].max_change, guard.MAX_CHANGE)
        self.definition.update(is_currency=False, item_type_id=17)
        item = self.adapter.snapshot()["items"]["item:7"]["target"]
        with self.assertRaises(guard.Refused):
            guard.validate_value(item, item.value + 1001)

    def test_unreviewed_bag_subtype_does_not_gain_currency_write_access(self):
        self.raw["items"][0]["count_editable"] = False
        state = self.adapter.snapshot()
        self.assertEqual(state["currencies"], {})
        self.assertTrue(state["diagnostics"])

    def test_forged_larger_change_limit_is_rejected_by_fresh_resolution(self):
        self.definition["id"] += 1
        self.raw["items"][0]["item_id"] = self.definition["id"]
        real = self.target()
        forged = replace(real, max_change=guard.SPIRIT_STONE_MAX_CHANGE)
        memory, record = guard_fixtures.FakeMemory(real.value), Mock()
        with self.assertRaises(guard.Refused):
            guard.set_value(memory, self.adapter.resolve, forged,
                            forged.value + 2000, record)
        self.assertEqual(memory.writes, [])
        record.assert_not_called()

    def test_runtime_cap_change_invalidates_previously_shown_stone(self):
        shown = self.target()
        self.definition["max_count_per_grid"] = 2_000_000
        memory, record = guard_fixtures.FakeMemory(shown.value), Mock()
        with self.assertRaises(guard.Refused):
            guard.set_value(memory, self.adapter.resolve, shown,
                            shown.value + 100_000_000, record)
        self.assertEqual(memory.writes, [])
        record.assert_not_called()


class CurrencyPolicyTests(unittest.TestCase):
    def test_full_write_path_enforces_total_and_delta_boundaries_without_retry(self):
        cases = (
            (899_999_999, 999_999_999, True),
            (999_999_999, 899_999_999, True),
            (999_999_998, 999_999_999, True),
            (999_999_999, 1_000_000_000, False),
            (900_000_000, 1_000_000_000, False),
            (1, 100_000_002, False),
            (100_000_001, 0, False),
        )
        for before, after, allowed in cases:
            with self.subTest(before=before, after=after):
                shown = stone_target(before)
                memory, records = guard_fixtures.FakeMemory(before), []
                resolve = Mock(return_value=shown)
                if allowed:
                    result = guard.set_value(memory, resolve, shown, after, records.append)
                    self.assertEqual(result.value, after)
                    self.assertEqual(memory.writes, [(shown.address, struct.pack('<i', after))])
                else:
                    with self.assertRaises(guard.Refused):
                        guard.set_value(memory, resolve, shown, after, records.append)
                    self.assertEqual(memory.writes, [])
                    self.assertEqual(records, [])
                    resolve.assert_not_called()

    def test_hundred_million_increase_and_restore_cross_old_cap_preserve_limit(self):
        shown = stone_target()
        memory, records = guard_fixtures.FakeMemory(shown.value), []
        changed = guard.set_value(memory, lambda _: shown, shown,
                                  shown.value + 100_000_000, records.append)
        self.assertEqual(changed.value, 100_017_100)
        self.assertEqual(changed.max_change, 100_000_000)
        restored = guard.set_value(memory, lambda _: changed, changed,
                                   shown.value, records.append)
        self.assertEqual(restored, shown)
        self.assertEqual([struct.unpack("<i", data)[0] for _, data in memory.writes],
                         [100_017_100, 17_100])
        self.assertEqual([event["status"] for event in records],
                         ["attempt", "verified", "attempt", "verified"])

    def test_hundred_million_and_one_both_directions_refused_before_resolution(self):
        for before, after in ((17_100, 100_017_101), (100_017_101, 17_100)):
            with self.subTest(before=before):
                shown = stone_target(before)
                memory, resolve, record = guard_fixtures.FakeMemory(before), Mock(), Mock()
                with self.assertRaises(guard.Refused):
                    guard.set_value(memory, resolve, shown, after, record)
                self.assertEqual(memory.writes, [])
                resolve.assert_not_called()
                record.assert_not_called()

    def test_zero_runtime_cap_and_tool_balance_cap_remain_enforced(self):
        for before, after, cap in ((0, 100_000_000, 999_999_999),
                                    (100_000_000, 0, 999_999_999),
                                    (499_999, 500_000, 500_000),
                                    (999_999_998, 999_999_999, 999_999_999)):
            with self.subTest(before=before, after=after):
                guard.validate_value(stone_target(before, cap), after)
        for before, after, cap in ((0, -1, 999_999_999),
                                    (500_000, 500_001, 500_000),
                                    (999_999_999, 1_000_000_000, 999_999_999)):
            with self.subTest(before=before, after=after), self.assertRaises(guard.Refused):
                guard.validate_value(stone_target(before, cap), after)

    def test_malformed_change_limits_and_non_currency_escalation_are_refused(self):
        shown = stone_target()
        for maximum_change in (0, -1, True, False, 100_000_000.0, "1000000", None, 100_000_001):
            with self.subTest(maximum_change=maximum_change), self.assertRaises(guard.Refused):
                guard.validate_value(replace(shown, max_change=maximum_change), shown.value + 1)
        for key in ("item:7", "spirit", "path", "currencyish:7"):
            with self.subTest(key=key), self.assertRaises(guard.Refused):
                guard.validate_value(replace(shown, key=key), shown.value + 1)
        ordinary = guard.Target("item:7", 0x8014, 20, ("item",), 1, 2_000_000)
        self.assertEqual(ordinary.max_change, guard.MAX_CHANGE)
        guard.validate_value(ordinary, 1020)
        with self.assertRaises(guard.Refused):
            guard.validate_value(ordinary, 1021)


@contextmanager
def fake_scalar_lease(_identity, **_kwargs):
    yield SimpleNamespace(possible_write=False, uncertain=False)


class CurrencyNativeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.reader = SimpleNamespace(h=101, pid=202)
        self.stamp = ("fake-worldapart.exe", 303)
        self.target = stone_target()
        self.api = SimpleNamespace(OpenProcess=Mock(return_value=404),
                                   CloseHandle=Mock(return_value=True),
                                   VirtualQueryEx=Mock(side_effect=self.query),
                                   WriteProcessMemory=Mock(side_effect=self.write))
        for context in (patch.object(native_write, "K", self.api),
                        patch.object(native_write, "process_identity", return_value=self.stamp),
                        patch.object(native_write, "read_exact_handle", return_value=struct.pack("<i", self.target.value)),
                        patch.object(native_scalar_guard, "scalar_write_guard", fake_scalar_lease)):
            context.start()
            self.addCleanup(context.stop)

    @staticmethod
    def query(_handle, _address, output, size):
        region = output._obj
        region.BaseAddress, region.RegionSize = 0x8000, 0x1000
        region.State, region.Type, region.Protect = 0x1000, 0x20000, 4
        return size

    @staticmethod
    def write(_handle, _address, _buffer, size, output):
        output._obj.value = size
        return True

    def test_native_hundred_million_write_is_exactly_one_int32_and_cannot_repeat(self):
        requested = self.target.value + 100_000_000
        writer = native_write.WriteOnce(self.reader, self.stamp, self.target, new_value=requested)
        writer.write_exact(self.target.address, struct.pack("<i", requested))
        args = self.api.WriteProcessMemory.call_args.args
        self.assertEqual(args[:2], (404, self.target.address))
        self.assertEqual(C.string_at(args[2], args[3]), struct.pack("<i", requested))
        self.assertEqual(args[3], 4)
        with self.assertRaises(guard.Refused):
            writer.write_exact(self.target.address, writer.after)
        self.api.WriteProcessMemory.assert_called_once()
        self.api.OpenProcess.assert_called_once()
        self.api.CloseHandle.assert_called_once_with(404)

    def test_native_constructor_independently_rechecks_both_delta_edges(self):
        for before, after in ((17_100, 100_017_101), (100_017_101, 17_100)):
            with self.subTest(before=before), self.assertRaises(guard.Refused):
                native_write.WriteOnce(self.reader, self.stamp, stone_target(before), new_value=after)
        with self.assertRaises(guard.Refused):
            native_write.WriteOnce(self.reader, self.stamp,
                                   replace(self.target, key="item:7"), new_value=self.target.value + 1)
        self.api.OpenProcess.assert_not_called()
        self.api.WriteProcessMemory.assert_not_called()

    def test_native_constructor_rejects_total_above_cap_before_opening_process(self):
        with self.assertRaises(guard.Refused):
            native_write.WriteOnce(self.reader, self.stamp,
                                   stone_target(999_999_999), new_value=1_000_000_000)
        self.api.OpenProcess.assert_not_called()
        self.api.WriteProcessMemory.assert_not_called()


class CurrencyUiLimitTests(unittest.TestCase):
    def test_selection_shows_each_targets_limit_and_absolute_balance(self):
        panel = app.App.__new__(app.App)
        panel.item_input, panel.item_range = app_fixtures.FakeVar(), app_fixtures.FakeVar()
        panel.buttons = Mock()
        panel.selected_item = Mock()
        cases = (
            (stone_target(), "0–100017100"),
            (replace(stone_target(), max_change=guard.MAX_CHANGE), "16100–18100"),
            (stone_target(999_999_998), "899999998–999999999"),
            (replace(stone_target(1_002_000), maximum=game_adapter.CURRENCY_EDIT_MAXIMUM,
                     max_change=guard.MAX_CHANGE), None),
        )
        for target, available_range in cases:
            with self.subTest(value=target.value, max_change=target.max_change):
                panel.selected_item.return_value = dict(name="测试货币", target=target)
                panel.select_item()
                self.assertEqual(panel.item_input.get(), str(target.value))
                compact = panel.item_range.get().replace(",", "").replace("，", "")
                self.assertIn(f"单次变化量最多 {target.max_change}", compact)
                if available_range is None:
                    self.assertIn("本次没有可设置的目标", compact)
                    self.assertNotIn("本次可设", compact)
                    self.assertNotIn("1001000–1000000", compact)
                else:
                    self.assertIn(f"本次可设 {available_range}", compact)


if __name__ == "__main__":
    unittest.main()
