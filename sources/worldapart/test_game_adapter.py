"""Point mapping and adapter policy with fake snapshots; never opens a process."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import game_adapter
from game_adapter import GameAdapter
from resolver import Resolver, ResolutionError
from write_guard import Refused, Target


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GameAdapter.__new__(GameAdapter)
        self.adapter.blocked = False
        self.adapter.stamp = ("worldapart.exe", 123)
        self.raw = dict(anchor_verified=True, manager=0x1000, store=0x2000,
                        world=0x3000, player=0x4000, bag=0x5000, talent=0x6000,
                        spirit_address=0x6030, spirit=13,
                        path_address=0x6018, path=4,
                        anchors=[dict(address=0x3020, expected_hex="0040000000000000")],
                        items=[dict(item_id=20, uid=7, count=2, object=0x8000,
                                    klass=0x9000, count_address=0x8014,
                                    class_name="Game.Model.Components.BagItem", count_editable=True)])
        self.adapter.resolver = SimpleNamespace(
            reader=SimpleNamespace(h=1, pid=2), resolve=lambda: deepcopy(self.raw))
        self.config = dict(process_creation_filetime=123, tables_current=0xA000,
                           items=[dict(id=20, max_count_per_grid=99,
                                       hide_in_bag=False, auto_use=False, can_discard=True,
                                       names={"zh-Hans": "青瓷素盏"}, config_object=0xB000)])
        self.identity_patch = patch.object(game_adapter, "process_identity", return_value=self.adapter.stamp)
        self.config_patch = patch.object(game_adapter, "read_config", return_value=self.config)
        self.identity_patch.start()
        self.config_patch.start()
        self.addCleanup(self.identity_patch.stop)
        self.addCleanup(self.config_patch.stop)

    def test_path_and_spirit_are_distinct_targets_with_shared_current_player(self):
        state = self.adapter.snapshot()
        self.assertEqual((state["path"].key, state["path"].address, state["path"].value),
                         ("path", 0x6018, 4))
        self.assertEqual((state["spirit"].address, state["spirit"].value), (0x6030, 13))
        self.assertEqual(state["path"].identity, state["spirit"].identity)
        for key in ("path", "spirit"):
            self.assertEqual((state[key].minimum, state[key].maximum), (0, 1000))
            self.assertEqual(self.adapter.resolve(key), state[key])
        item = state["items"]["item:7"]["target"]
        self.assertEqual((item.minimum, item.maximum), (1, 99))

    def test_high_existing_balance_is_shown_unchanged(self):
        self.raw["path"] = 2500
        self.raw["spirit"] = 4500
        state = self.adapter.snapshot()
        self.assertEqual(state["path"].value, 2500)
        self.assertEqual(state["spirit"].value, 4500)
        self.assertEqual(state["path"].maximum, 1000)

    def test_inventory_category_uses_same_live_definition_as_catalogue(self):
        from acquisition_adapter import catalog_rows
        definition = self.config["items"][0]
        definition.update(item_type_id=17, type_names={"zh-Hans": "文玩", "en-US": "Curio"})
        row = self.adapter.snapshot()["items"]["item:7"]
        catalogue = catalog_rows({"items": [definition]})[0]
        self.assertEqual((row["type_name"], row["item_type_id"]), ("文玩", 17))
        self.assertEqual(row["type_name"], catalogue["type_name"])
        self.assertEqual(row["target"].value, 2)

    def test_unknown_category_does_not_remove_reviewed_quantity_target(self):
        row = self.adapter.snapshot()["items"]["item:7"]
        self.assertEqual(row["type_name"], "未知分类")
        self.assertEqual(row["target"].address, 0x8014)

    def test_currency_is_separate_from_hidden_virtual_items(self):
        definition = self.config["items"][0]
        definition.update(is_currency=True, item_type_id=5, hide_in_bag=True,
                          auto_use=None, can_discard=False, max_count_per_grid=999999999)
        self.raw["items"][0]["count"] = 17100
        state = self.adapter.snapshot()
        self.assertEqual(state["items"], {})
        target = state["currencies"]["currency:7"]["target"]
        self.assertEqual((target.minimum, target.maximum, target.value), (0, 1000000, 17100))
        self.assertEqual(self.adapter.resolve("currency:7"), target)
        definition.update(is_currency=False, item_type_id=7)
        state = self.adapter.snapshot()
        self.assertEqual(state["items"], {})
        self.assertEqual(state["currencies"], {})

    def test_currency_zero_is_valid_without_creating_or_removing_objects(self):
        self.config["items"][0].update(is_currency=True, item_type_id=5,
                                        max_count_per_grid=999999999)
        self.raw["items"][0]["count"] = 0
        self.assertEqual(self.adapter.snapshot()["currencies"]["currency:7"]["target"].value, 0)

    def test_reviewed_pill_and_material_use_own_999_limit_with_nullable_auto_use(self):
        self.raw["items"][0]["class_name"] = "Game.Model.Components.PillBagItem"
        self.config["items"][0].update(max_count_per_grid=999, auto_use=None)
        self.assertEqual(self.adapter.snapshot()["items"]["item:7"]["target"].maximum, 999)
        self.config["items"][0]["max_count_per_grid"] = 99
        self.assertEqual(self.adapter.snapshot()["items"]["item:7"]["target"].maximum, 99)

    def test_special_type_or_equipped_entry_stays_diagnostic_only(self):
        self.raw["items"][0].update(count_editable=False, class_name="Game.Model.Components.ArtifactBagItem")
        self.raw["diagnostics"] = [dict(slot=5, reason="null_entry")]
        state = self.adapter.snapshot()
        self.assertEqual(state["items"], {})
        self.assertEqual([x["reason"] for x in state["diagnostics"]], ["null_entry", "quantity_not_reviewed"])
        self.assertEqual(state["spirit"].value, 13)
        self.assertEqual(state["path"].value, 4)

    def test_missing_editability_attestation_never_becomes_target(self):
        del self.raw["items"][0]["count_editable"]
        self.assertEqual(self.adapter.snapshot()["items"], {})

    def test_explicit_auto_use_and_above_cap_stacks_are_not_writable(self):
        self.config["items"][0]["auto_use"] = True
        self.assertEqual(self.adapter.snapshot()["items"], {})
        self.config["items"][0]["auto_use"] = False
        self.raw["items"][0]["count"] = 100
        self.assertEqual(self.adapter.snapshot()["items"], {})

    def test_currency_above_game_stack_cap_is_diagnostic_without_blocking_other_data(self):
        definition = self.config["items"][0]
        definition.update(id=50000, is_currency=True, item_type_id=5,
                          max_count_per_grid=999_999_999, hide_in_bag=True,
                          can_discard=False, auto_use=None)
        self.raw["items"][0].update(item_id=50000, slot=0)
        for balance in (1_000_000_000, 2_147_483_647):
            with self.subTest(balance=balance):
                self.raw["items"][0]["count"] = balance
                state = self.adapter.snapshot()
                self.assertEqual(state["currencies"], {})
                self.assertEqual((state["spirit"].value, state["path"].value), (13, 4))
                self.assertFalse(self.adapter.blocked)
                self.assertEqual(len(state["diagnostics"]), 1)
                row = state["diagnostics"][0]
                self.assertEqual((row["reason"], row["count"], row["stack_limit"]),
                                 ("currency_balance_above_limit", balance, 999_999_999))
                self.assertIn(str(balance), row["message"])
                self.assertIn("999999999", row["message"])
                self.assertEqual(self.raw["items"][0]["count"], balance)
        self.raw["items"][0]["count"] = 999_999_999
        state = self.adapter.snapshot()
        self.assertEqual(state["diagnostics"], [])
        self.assertEqual(state["currencies"]["currency:7"]["target"].value, 999_999_999)

    def test_multiple_stone_stacks_never_expose_per_stack_balance_targets(self):
        definition = self.config["items"][0]
        definition.update(id=50000, is_currency=True, item_type_id=5,
                          max_count_per_grid=999_999_999)
        original = dict(self.raw["items"][0], item_id=50000, slot=0)
        for left, right in ((40, 60), (600_000_000, 600_000_000)):
            with self.subTest(total=left + right):
                self.raw["items"] = [dict(original, count=left),
                    dict(original, count=right, uid=8, object=0x8100,
                         count_address=0x8114, slot=1)]
                state = self.adapter.snapshot()
                self.assertEqual(state["currencies"], {})
                self.assertEqual((state["spirit"].value, state["path"].value), (13, 4))
                self.assertFalse(self.adapter.blocked)
                self.assertEqual([row["reason"] for row in state["diagnostics"]],
                                 ["currency_multiple_stacks", "currency_multiple_stacks"])
        # An uneditable second stack still contributes to the total. Do not
        # count only the writable rows when deciding whether editing is safe.
        self.raw["items"][1]["count_editable"] = False
        self.assertEqual(self.adapter.snapshot()["currencies"], {})

    def test_old_single_stone_target_is_refused_if_another_stack_appears(self):
        from write_guard import set_value
        self.config["items"][0].update(id=50000, is_currency=True, item_type_id=5,
                                        max_count_per_grid=999_999_999)
        self.raw["items"][0].update(item_id=50000, count=40)
        shown = self.adapter.snapshot()["currencies"]["currency:7"]["target"]
        self.raw["items"].append(dict(self.raw["items"][0], uid=8, count=60,
                                     object=0x8100, count_address=0x8114))
        memory, record = Mock(), Mock()
        with self.assertRaises(Refused):
            set_value(memory, self.adapter.resolve, shown, 41, record)
        memory.read_exact.assert_not_called()
        memory.write_exact.assert_not_called()
        record.assert_not_called()

    def test_reader_omitted_unknown_or_duplicate_entries_prevent_unproven_stone_total(self):
        import struct
        from test_inventory_resolver import InventoryResolverTests
        self.config["items"][0].update(id=50000, is_currency=True, item_type_id=5,
                                        max_count_per_grid=999_999_999)
        for hidden_kind in ("unsupported_entry", "duplicate_uid"):
            with self.subTest(hidden_kind=hidden_kind):
                fixture = InventoryResolverTests()
                fixture.setUp()
                first = fixture.slot(0, uid=1, count=40)
                fixture.put(first + 16, struct.pack('<i', 50000))
                hidden = fixture.slot(1, klass=0x1400 if hidden_kind == "unsupported_entry"
                                      else 0x1100, uid=9, count=600_000_000)
                fixture.put(hidden + 16, struct.pack('<i', 50000))
                size = 2
                if hidden_kind == "duplicate_uid":
                    fixture.slot(2, uid=9, count=3)
                    size = 3
                entries, diagnostics = fixture.rr.inventory_entries(fixture.arr, size, fixture.base)
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[0]["item_id"], 50000)
                self.assertTrue(all(row["reason"] == hidden_kind for row in diagnostics))
                self.assertTrue(all("item_id" not in row for row in diagnostics))
                self.raw.update(items=entries, diagnostics=diagnostics)
                state = self.adapter.snapshot()
                self.assertEqual(state["currencies"], {})
                self.assertEqual(state["diagnostics"][-1]["reason"], "currency_balance_unverified")
                self.assertEqual((state["spirit"].value, state["path"].value), (13, 4))
                self.assertFalse(self.adapter.blocked)

    def test_null_slots_and_known_uneditable_items_do_not_block_stone_balance(self):
        self.config["items"][0].update(id=50000, is_currency=True, item_type_id=5,
                                        max_count_per_grid=999_999_999)
        self.raw["items"][0].update(item_id=50000, count=40)
        self.raw["diagnostics"] = [dict(slot=8, reason="null_entry")]
        unsupported = dict(self.raw["items"][0], item_id=20, uid=8, count_editable=False,
                           object=0x8100, count_address=0x8114)
        self.raw["items"].insert(0, unsupported)
        self.config["items"].append(dict(self.config["items"][0], id=20,
                                          is_currency=False, item_type_id=3))
        state = self.adapter.snapshot()
        self.assertEqual(state["currencies"]["currency:7"]["target"].value, 40)
        self.assertEqual([row["reason"] for row in state["diagnostics"]],
                         ["null_entry", "quantity_not_reviewed"])

    def test_config_reclassification_invalidates_shown_identity(self):
        old = self.adapter.snapshot()["items"]["item:7"]["target"]
        self.config["items"][0].update(is_currency=True, item_type_id=5)
        new = self.adapter.snapshot()["currencies"]["currency:7"]["target"]
        self.assertNotEqual(old.identity, new.identity)

    def test_duplicate_item_ids_are_identified_by_individual_uids(self):
        other = deepcopy(self.raw["items"][0])
        other.update(uid=8, object=0x8100, count_address=0x8114)
        self.raw["items"].append(other)
        state = self.adapter.snapshot()
        self.assertEqual(set(state["items"]), {"item:7", "item:8"})
        self.assertIn("7", state["items"]["item:7"]["name"])
        self.assertNotEqual(state["items"]["item:7"]["target"].address,
                            state["items"]["item:8"]["target"].address)

    def test_changed_player_or_anchor_invalidates_target_identity(self):
        old = self.adapter.snapshot()["path"]
        self.raw["player"] += 0x100
        self.assertNotEqual(self.adapter.snapshot()["path"].identity, old.identity)
        self.raw["player"] -= 0x100
        self.raw["anchors"][0]["expected_hex"] = "0050000000000000"
        self.assertNotEqual(self.adapter.snapshot()["path"].identity, old.identity)

    def test_process_change_or_unverified_chain_refused(self):
        with patch.object(game_adapter, "process_identity", return_value=("worldapart.exe", 124)):
            with self.assertRaises(Refused):
                self.adapter.snapshot()
        self.raw["anchor_verified"] = False
        with self.assertRaises(Refused):
            self.adapter.snapshot()

    def test_absolute_value_passed_to_write_layers_once(self):
        shown = self.adapter.snapshot()["path"]
        result = Target(shown.key, shown.address, 100, shown.identity, 0, 1000)
        with patch.object(game_adapter, "WriteOnce") as writer, \
                patch.object(game_adapter, "guarded_set_value", return_value=result) as guarded:
            self.assertEqual(self.adapter.set_value(shown, 100), result)
            writer.assert_called_once_with(self.adapter.resolver.reader, self.adapter.stamp,
                                           shown, new_value=100)
            guarded.assert_called_once_with(writer.return_value, self.adapter.resolve,
                                            shown, 100, self.adapter.record)

    def test_failed_write_blocks_connection_without_retry(self):
        shown = self.adapter.snapshot()["path"]
        with patch.object(game_adapter, "WriteOnce") as writer, \
                patch.object(game_adapter, "guarded_set_value", side_effect=Refused("fake failure")) as guarded:
            with self.assertRaises(Refused):
                self.adapter.set_value(shown, 100)
            with self.assertRaises(Refused):
                self.adapter.set_value(shown, 100)
            self.assertTrue(self.adapter.blocked)
            self.assertEqual(writer.call_count, 1)
            self.assertEqual(guarded.call_count, 1)

    def test_scene_precondition_refusal_keeps_read_connection_usable(self):
        from write_guard import PreconditionChanged
        shown = self.adapter.snapshot()['path']
        guards = ((0x9000, b'\x00'),)
        with patch.object(game_adapter, 'WriteOnce') as writer, \
                patch.object(game_adapter, 'guarded_set_value', side_effect=PreconditionChanged('battle started')):
            with self.assertRaises(PreconditionChanged):
                self.adapter.set_value(shown, 100, preconditions=guards)
        self.assertFalse(self.adapter.blocked)
        writer.assert_called_once_with(self.adapter.resolver.reader, self.adapter.stamp,
                                       shown, new_value=100, preconditions=guards)
        self.assertEqual(self.adapter.snapshot()['path'], shown)

    def test_compatibility_change_only_accepts_single_step(self):
        shown = self.adapter.snapshot()["path"]
        self.adapter.set_value = Mock()
        self.adapter.change(shown, -1)
        self.adapter.set_value.assert_called_once_with(shown, 3)
        for invalid in (0, 2, True, 1.0):
            with self.assertRaises(Refused):
                self.adapter.change(shown, invalid)


class ResolverPointTests(unittest.TestCase):
    def setUp(self):
        self.resolver = Resolver.__new__(Resolver)
        self.resolver.field = Mock(return_value=0x18)
        self.resolver.i = Mock(return_value=4)

    def test_path_resolution_requires_int32_and_reads_exact_field(self):
        component_class = object()
        result = self.resolver.point_balance(0x6000, component_class, "<PathPoints>k__BackingField")
        self.assertEqual(result, (0x6018, 4))
        self.resolver.field.assert_called_once_with(component_class, "<PathPoints>k__BackingField", 8)
        self.resolver.i.assert_called_once_with(0x6018)

    def test_read_range_is_wider_than_edit_range_but_bounded(self):
        for value in (0, 1000, 1_000_000):
            self.resolver.i.return_value = value
            self.assertEqual(self.resolver.point_balance(0x6000, {}, "point")[1], value)
        for invalid in (-1, 1_000_001):
            self.resolver.i.return_value = invalid
            with self.assertRaises(ResolutionError):
                self.resolver.point_balance(0x6000, {}, "point")


if __name__ == "__main__":
    unittest.main()
