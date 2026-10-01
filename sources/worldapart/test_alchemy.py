"""Pure offline guards, configuration and postcondition checks for pill alchemy."""
import copy
import struct
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alchemy_adapter import AlchemyAdapter, AlchemyResolver, DATA, QTE_LAYOUTS, qte_layout, validate_qte
from alchemy_talents import (AlchemyTalentAdapter, AlchemyTalentResolver, TALENTS, METHOD as TALENT_METHOD,
                             rank_limit, validate_rank, parse_rank)
from write_guard import Refused, UncertainWrite


class QteLayoutTests(unittest.TestCase):
    def test_both_reviewed_layouts_require_the_complete_field_set(self):
        for layout in QTE_LAYOUTS:
            resolver = SimpleNamespace(_field=Mock(side_effect=lambda c, n, k: 0x10C if n == '_awaitingIgnition' else layout[n]))
            self.assertEqual(qte_layout(resolver, {}), layout)
            self.assertEqual(resolver._field.call_count, len(layout) + (layout == QTE_LAYOUTS[1]))

    def test_new_ignition_flag_must_match_real_start_entry(self):
        resolver = SimpleNamespace(_field=lambda c, n, k: 0x108 if n == '_awaitingIgnition' else QTE_LAYOUTS[1][n])
        with self.assertRaisesRegex(Refused, '灵力'):
            qte_layout(resolver, {})

    def test_partial_shift_or_unknown_layout_refuses(self):
        for altered in ({**QTE_LAYOUTS[0], '_context': 0x150},
                        {**QTE_LAYOUTS[1], '_running': 0x107}):
            resolver = SimpleNamespace(_field=lambda c, n, k: altered[n])
            with self.assertRaises(Refused):
                qte_layout(resolver, {})


class CanonicalManagerGuards(unittest.TestCase):
    """Owner-list rejection paths; real construction/read is also checked live."""
    def fixture(self, *, count=1, capacity=4, pointers=(0x4000,), valid=True):
        rr = AlchemyResolver.__new__(AlchemyResolver)
        rr.reader, rr.meta, rr.anchors = object(), 0x9000, []
        rr.specs = {'Game.UIManager': {}}
        rr._runtime = SimpleNamespace(specs={'Game.UIManager': {}})
        rr.runtime_spec = Mock()
        ui = dict(namespace='Game', name='UIManager', klass='0x5000')
        rr.obj = Mock(return_value=ui)
        context = Mock(anchors=[])
        context.managers.return_value = (0x1000, {})
        context.obj.return_value = ui
        context.field.side_effect = lambda c,n,k: {'_managers':0x30, '_size':0x18, '_items':0x10}[n]
        context.pointer.side_effect = lambda a,label: {0x1030:0x2000,0x2010:0x3000}[a]
        context.i.return_value = count
        context.q.return_value = capacity
        context.anchor.return_value = struct.pack('<'+'Q'*len(pointers), *pointers)
        candidate = Mock(return_value=(ui, None) if valid else (None, 'wrong_metadata'))
        return rr, context, candidate

    def test_canonical_lookup_has_no_heap_scan_and_rechecks_every_read(self):
        rr, context, candidate = self.fixture()
        with patch('alchemy_adapter._Context', return_value=context), patch('class_scan.candidate', candidate), \
                patch('extension_runtime.scan_classes', side_effect=AssertionError('must not scan')):
            self.assertEqual(rr.class_address('Game.UIManager'), 0x5000)
            self.assertEqual(rr.class_address('Game.UIManager'), 0x5000)
        self.assertEqual(candidate.call_count, 2)
        self.assertEqual(context._finish_snapshot.call_count, 2)

    def test_missing_duplicate_overflow_and_bad_metadata_refuse(self):
        for kwargs in (dict(count=0), dict(count=129), dict(capacity=0),
                       dict(count=2,pointers=(0x4000,0x4000)), dict(valid=False)):
            rr, context, candidate = self.fixture(**kwargs)
            with self.subTest(kwargs=kwargs), patch('alchemy_adapter._Context', return_value=context), \
                    patch('class_scan.candidate', candidate), self.assertRaises(Refused):
                rr.class_address('Game.UIManager')

    def test_transition_during_lookup_is_not_cached_as_success(self):
        rr, context, candidate = self.fixture()
        context._finish_snapshot.side_effect = Refused('transition')
        with patch('alchemy_adapter._Context', return_value=context), patch('class_scan.candidate', candidate), \
                self.assertRaisesRegex(Refused, 'transition'):
            rr.class_address('Game.UIManager')


class MaximumGetterLayoutTests(unittest.TestCase):
    def resolver(self, value_offset):
        rr = AlchemyResolver.__new__(AlchemyResolver)
        rr.tables = lambda: (0x1000, {})
        rr.obj = lambda address, full: {}
        rr.reviewed_field = lambda c, name, kind: {
            '<TbConstants>k__BackingField': 0x30, '_overrides': 0x20,
            '_data': 0x10, '<ALCHEMY_QTE_PROGRESS_MAX>k__BackingField': value_offset}[name]
        rr.q = lambda address, **kw: {0x1030: 0x2000, 0x2020: 0, 0x2010: 0x3000}[address]
        rr.i = Mock(side_effect=lambda address, **kw: {0x3000 + value_offset: 1000}[address])
        return rr

    def test_both_getter_layouts_read_the_verified_field(self):
        for offset in (0x95C, 0x97C):
            rr = self.resolver(offset)
            self.assertEqual(rr.maximum(), (1000, 0x3000 + offset))
            rr.i.assert_called_once_with(0x3000 + offset, anchored=True)

    def test_unknown_getter_layout_refuses_before_value_read(self):
        rr = self.resolver(0x960)
        with self.assertRaises(Refused):
            rr.maximum()
        rr.i.assert_not_called()


class LargeConstantsMetadata(unittest.TestCase):
    def setUp(self):
        self.rr = AlchemyResolver.__new__(AlchemyResolver)
        self.rr.meta, self.klass = 0x1000000, 0x2000000
        spec = DATA["metadata"]["LubanDatas.data.Constants"]
        self.count = 709
        self.pointers = {self.klass + 0x78: self.klass,
                         self.klass + 0x68: self.rr.meta + spec["type_definition_offset"],
                         self.klass + 16: 0x3000000, self.klass + 24: 0x3001000}
        self.ints = {self.klass + 0x11C: spec["token"], self.klass + 0xF8: 0xC00}
        self.strings = {0x3000000: "Constants", 0x3001000: "LubanDatas.data"}
        self.rr.anchor = lambda a, n: struct.pack("<H", self.count)
        self.rr.q = lambda a, **kw: self.pointers[a]
        self.rr.i = lambda a, **kw: self.ints[a]
        self.rr.reader = SimpleNamespace(string=lambda a: self.strings[a])
        self.result = dict(namespace="LubanDatas.data", name="Constants", instance_size=0xC00,
            fields=[dict(name=f["name"], token=hex(f["token"]), parent=hex(self.klass)) for f in spec["fields"]])
        self.inspect = patch("alchemy_adapter.probe.inspect_class", return_value=self.result).start()
        self.addCleanup(patch.stopall)

    def test_exact_reviewed_large_class_uses_explicit_bounded_inspector(self):
        self.assertIs(self.rr.info(self.klass, "LubanDatas.data.Constants"), self.result)
        self.inspect.assert_called_once_with(self.rr.reader, self.klass, max_fields=709)

    def test_wrong_count_or_definition_refuses_before_large_parse(self):
        self.count = 710
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")
        self.count = 709
        self.pointers[self.klass + 0x68] += 88
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")
        self.inspect.assert_not_called()

    def test_wrong_name_or_token_refuses_before_large_parse(self):
        self.strings[0x3000000] = "OtherClass"
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")
        self.strings[0x3000000] = "Constants"
        self.ints[self.klass + 0x11C] += 1
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")
        self.inspect.assert_not_called()

    def test_wrong_field_token_or_parent_refuses_after_inspection(self):
        self.result["fields"][0]["token"] = "0x400ffff"
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")
        self.result["fields"][0]["token"] = hex(DATA["metadata"]["LubanDatas.data.Constants"]["fields"][0]["token"])
        self.result["fields"][0]["parent"] = "0xDEAD"
        with self.assertRaises(Refused):
            self.rr.info(self.klass, "LubanDatas.data.Constants")


def qte_values(**changes):
    result = dict(actionable=True, running=True, emitted=False, deferred=False,
        abort=False, cinematic=False, refunded=False, pending_costs=0x1000, committed=True,
        progress=123., maximum=1000, fan=300., xian=600., shen=900.,
        remaining=55., stage_remaining=15., score=3., stage=0, stage_count=3)
    result.update(changes)
    return result


class QteGuards(unittest.TestCase):
    def test_waiting_for_spirit_is_readable_but_cannot_skip_ignition(self):
        for running in (False, True):
            ready, reason = validate_qte(qte_values(awaiting_ignition=True, running=running, stage=-1, stage_remaining=0))
            self.assertFalse(ready)
            self.assertIn('添加灵力', reason)

    def test_running_paid_round_can_finish_without_score_change(self):
        values = qte_values(score=0)
        self.assertTrue(validate_qte(values)[0])
        self.assertEqual(values["score"], 0)

    def test_already_consumed_explore_costs_can_be_null(self):
        self.assertTrue(validate_qte(qte_values(pending_costs=0, committed=False))[0])

    def test_unpaid_round_cannot_finish(self):
        self.assertFalse(validate_qte(qte_values(committed=False))[0])

    def test_paused_finished_transition_and_refund_are_inactive(self):
        for key, value in (("actionable", False), ("running", False), ("emitted", True),
                           ("deferred", True), ("abort", True), ("cinematic", True), ("refunded", True)):
            with self.subTest(key=key):
                self.assertFalse(validate_qte(qte_values(**{key: value}))[0])

    def test_invalid_numbers_and_thresholds_refused(self):
        for change in (dict(progress=float("nan")), dict(score=float("inf")), dict(maximum=1001),
                       dict(progress=-1), dict(progress=1001), dict(shen=1001), dict(shen=0), dict(xian=200),
                       dict(remaining=0), dict(stage_remaining=0), dict(stage_remaining=58),
                       dict(stage=-1), dict(stage=3), dict(stage_count=33), dict(remaining=3601)):
            with self.subTest(change=change), self.assertRaises(Refused):
                validate_qte(qte_values(**change))

    def test_progress_cap_itself_remains_valid(self):
        self.assertTrue(validate_qte(qte_values(progress=1000))[0])


class QteLifecycle(unittest.TestCase):
    def adapter(self):
        adapter = AlchemyAdapter.__new__(AlchemyAdapter)
        adapter.resolver = Mock(_selected_methods={})
        adapter.resolver.method.return_value = "0x9870"
        adapter.resolver.proof.return_value = [dict(address="0x4000", size=4, expected_hex="01000000")]
        adapter.blocked = False
        adapter._native = Mock()
        state = dict(can_solve=True, identity=(1, 2, "operation-guid"), reason="", values=qte_values(),
                     native=dict(panel_class="0x1000", maximum=1000, round_key="x"))
        adapter.snapshot = Mock(return_value=state)
        return adapter, state

    def test_new_round_refused_before_dispatch(self):
        adapter, state = self.adapter()
        with self.assertRaises(Refused):
            adapter.prepare_solve(dict(state, identity=(1, 2, "other-operation")))
        adapter.resolver.method.assert_not_called()

    def test_natural_progress_can_advance_with_same_stable_identity(self):
        adapter, state = self.adapter()
        shown = copy.deepcopy(state)
        state["values"]["progress"] = 200
        result = adapter.prepare_solve(shown)
        self.assertEqual(result["values"]["progress"], 200)
        self.assertEqual(result["native"]["method_info"], "0x9870")

    def test_finished_round_never_produces_write_method(self):
        adapter, state = self.adapter()
        state.update(can_solve=False, reason="settling")
        with self.assertRaises(Refused):
            adapter.prepare_solve(state)
        adapter.resolver.method.assert_not_called()

    def test_finish_only_confirms_transition_not_reward(self):
        adapter, state = self.adapter()
        outcome = dict(running=False, progress=1000, quality=3, result_emitted=False, result_deferred=True)
        result = adapter.verify_native(outcome, state)
        self.assertTrue(result["verified"])
        self.assertEqual(result["phase"], "settling")
        self.assertNotIn("items_added", result)

    def test_incomplete_native_result_is_uncertain(self):
        adapter, state = self.adapter()
        good = dict(running=False, progress=1000, quality=3, result_emitted=True, result_deferred=False)
        for change in (dict(running=True), dict(progress=999), dict(quality=2), dict(result_emitted=False)):
            with self.subTest(change=change), self.assertRaises(UncertainWrite):
                adapter.verify_native(dict(good, **change), state)

    def test_unknown_dispatch_blocks_adapter(self):
        adapter, state = self.adapter()
        adapter._native.solve.side_effect = UncertainWrite("unknown")
        with self.assertRaises(UncertainWrite):
            adapter.solve(state)
        self.assertTrue(adapter.blocked)


class TalentRules(unittest.TestCase):
    def test_seven_true_talents_and_configured_five_levels(self):
        self.assertEqual(set(TALENTS), set(range(1000001, 1000008)))
        for key in TALENTS:
            self.assertEqual(rank_limit(key, 25), 5)
            self.assertEqual(validate_rank(key, 0, 1), 0)

    def test_real_level_boundaries(self):
        self.assertEqual(rank_limit(1000001, 4), 1)
        self.assertEqual(rank_limit(1000001, 5), 2)
        self.assertEqual(rank_limit(1000002, 1), 0)
        self.assertEqual(rank_limit(1000002, 3), 1)
        self.assertEqual(rank_limit(1000007, 24), 4)

    def test_no_arbitrary_points_or_rank_beyond_current_level(self):
        for talent, rank, level in ((1, 1, 5), (1000001, 3, 5), (1000001, -1, 25),
                                   (1000001, 6, 25), (1000001, True, 25), (1000001, 1., 25),
                                   (1000001, 1, 0), (1000001, 1, 26)):
            with self.subTest(talent=talent, rank=rank, level=level), self.assertRaises(Refused):
                validate_rank(talent, rank, level)

    def test_integer_input(self):
        self.assertEqual(parse_rank(" 2 "), 2)
        for text in ("1.0", "1e0", "nan", "", "01", "0x1", True):
            with self.subTest(text=text), self.assertRaises(Refused):
                parse_rank(text)


class TalentDictionary(unittest.TestCase):
    def fixture(self, entries=((1000001, 2),)):
        rr = AlchemyTalentResolver.__new__(AlchemyTalentResolver)
        memory = {}
        def write(a, data):
            memory.update({a+i: b for i, b in enumerate(data)})
        def exact(a, size):
            return bytes(memory.get(a+i, 0) for i in range(size))
        rr.exact, rr.anchors = exact, []
        rr.reader = SimpleNamespace(read=exact)
        dc, ac, ec = {"klass": "0x6000"}, {"klass": "0x7000"}, {"instance_size": 32}
        rr.obj = lambda address, name: dc if address == 0x1000 else ac
        rr.info = lambda *args: ec
        offsets = {"_entries": 24, "_count": 32, "_freeCount": 40, "_version": 44,
                   "hashCode": 16, "next": 20, "key": 24, "value": 28}
        rr.reviewed_field = lambda c, name, kind: offsets[name]
        write(0x1018, struct.pack("<Q", 0x2000)); write(0x1020, struct.pack("<i", len(entries)))
        write(0x2018, struct.pack("<Q", 16)); write(0x7040, struct.pack("<Q", 0x8000))
        for i, (key, value) in enumerate(entries):
            write(0x2020+i*16, struct.pack("<iiii", key, -1, key, value))
        return rr, write

    def test_existing_and_missing_dictionary(self):
        rr, _ = self.fixture()
        ranks, identity = rr.ranks(0x1000)
        self.assertEqual(ranks, {1000001: 2})
        self.assertEqual(identity[:3], (0x1000, 0x2000, 1))
        self.assertIn((0x2020, struct.pack("<iiii", 1000001, -1, 1000001, 2).hex()), rr.anchors)
        self.assertEqual(rr.ranks(0), ({}, (0, 0, 0, 0, 0)))

    def test_duplicate_unknown_and_corrupt_rank(self):
        for entries in (((1000001, 2), (1000001, 3)), ((100, 1),), ((1000001, 6),), ((1000001, -1),)):
            rr, _ = self.fixture(entries)
            with self.subTest(entries=entries), self.assertRaises(Refused):
                rr.ranks(0x1000)

    def test_free_slots_and_count_consistency(self):
        rr, write = self.fixture(((1000001, 2), (1000002, 3)))
        write(0x2030, struct.pack("<i", -1)); write(0x1028, struct.pack("<i", 1))
        self.assertEqual(rr.ranks(0x1000)[0], {1000001: 2})
        write(0x1028, struct.pack("<i", 0))
        with self.assertRaises(Refused):
            rr.ranks(0x1000)

    def test_chain_capacity_and_layout_fail_closed(self):
        for address, data in ((0x2024, struct.pack("<i", 20)), (0x2018, struct.pack("<Q", 129)),
                              (0x1028, struct.pack("<i", 2))):
            rr, write = self.fixture(); write(address, data)
            with self.subTest(address=address), self.assertRaises(Refused):
                rr.ranks(0x1000)


class TalentConfiguration(unittest.TestCase):
    def setUp(self):
        self.rr = AlchemyTalentResolver.__new__(AlchemyTalentResolver)
        self.rows, self.pointers, self.lists, self.ints = {}, {}, {}, {}
        names = ("rank", "required_level", "value", "cost")
        for index, (key, config) in enumerate(TALENTS.items()):
            obj = 0x10000 + index * 0x1000
            self.rows[key] = obj, {}
            self.pointers[obj] = obj + 0x100
            self.lists[obj + 0x100] = []
            for n, level in enumerate(config["levels"]):
                address = obj + 0x200 + n * 32
                self.lists[obj + 0x100].append(address)
                self.ints.update({address + i * 4: level[name] for i, name in enumerate(names)})
        self.rr.tables = Mock(return_value=(0x2000, {}))
        self.rr.table_rows = Mock(return_value=self.rows)
        self.rr.reviewed_field = lambda c, name, kind: 0 if "levels" in name else names.index(name[1:name.index(">")]) * 4
        self.rr.q = lambda p, **kw: self.pointers[p]
        self.rr.i = lambda p, **kw: self.ints[p]
        self.rr.list_objects = lambda p, maximum: self.lists[p]
        self.rr.obj = lambda *args: {}

    def test_all_rank_cost_effect_and_required_level_records_match(self):
        self.assertEqual(self.rr.configuration(), 0x2000)

    def test_changed_runtime_requirement_and_effect_refused(self):
        for offset in (0, 4, 8, 12):
            address = 0x10200 + offset
            old = self.ints[address]
            self.ints[address] += 1
            with self.subTest(offset=offset), self.assertRaises(Refused):
                self.rr.configuration()
            self.ints[address] = old

    def test_missing_or_extra_talent_configuration_refused(self):
        del self.rows[1000001]
        with self.assertRaises(Refused):
            self.rr.configuration()
        self.rows[999] = 0x10000, {}
        with self.assertRaises(Refused):
            self.rr.configuration()


def talent_state():
    rows = {str(key): dict(value=0) for key in TALENTS}
    return dict(can_edit=True, reason="", identity=("process", "player", "model", 5, (100, 200, 0, 0, 1)),
        player_level=5, rows=rows, native=dict(model_class="0x3000"), talent_id=1000001, desired_rank=1)


class TalentLifecycle(unittest.TestCase):
    def fixture(self):
        adapter = AlchemyTalentAdapter.__new__(AlchemyTalentAdapter)
        adapter.resolver = Mock()
        adapter.resolver._selected_methods = {}
        adapter.resolver.method.return_value = "0x6000"
        adapter.resolver.proof.return_value = [dict(address="0x3000", size=8, expected_hex="00"*8)]
        adapter.snapshot = Mock(return_value=talent_state())
        return adapter

    def test_current_scene_or_panel_cannot_be_bypassed(self):
        adapter = self.fixture(); shown = copy.deepcopy(adapter.snapshot())
        adapter.snapshot.return_value.update(can_edit=False, reason="close screens")
        with self.assertRaises(Refused):
            adapter.prepare_solve(shown)
        adapter.resolver.method.assert_not_called()

    def test_changed_player_level_or_dictionary_rejected(self):
        adapter = self.fixture(); shown = copy.deepcopy(adapter.snapshot())
        for identity in (("different",), shown["identity"][:-1] + ((100, 200, 0, 0, 2),)):
            adapter.snapshot.return_value["identity"] = identity
            with self.subTest(identity=identity), self.assertRaises(Refused):
                adapter.prepare_solve(shown)

    def test_success_descriptor_uses_exact_current_rank_and_limit(self):
        adapter = self.fixture(); shown = copy.deepcopy(adapter.snapshot())
        state = adapter.prepare_solve(shown)
        self.assertEqual(state["native"]["rank"], 1)
        self.assertEqual(state["native"]["before"], 0)
        self.assertEqual(state["native"]["maximum"], 2)
        self.assertEqual(len(state["native"]["round_key"]), 64)

    def test_same_rank_does_not_dispatch(self):
        adapter = self.fixture(); shown = copy.deepcopy(adapter.snapshot()); shown["desired_rank"] = 0
        with self.assertRaises(Refused):
            adapter.prepare_solve(shown)
        adapter.resolver.method.assert_not_called()

    def test_current_method_selection_survives_descriptor_and_request(self):
        from dual_cultivation_native import MiniGameOnce
        from test_scalar_method_profiles import MethodFixture

        fixture_spec = dict(TALENT_METHOD, parameters=TALENT_METHOD["argc"],
                            return_kind=TALENT_METHOD["returns"])
        fx = MethodFixture(AlchemyTalentResolver, {"set": fixture_spec}, current=True)
        adapter = AlchemyTalentAdapter.__new__(AlchemyTalentAdapter)
        adapter.resolver = fx.resolver
        state = talent_state()
        state["native"].update(model_class=hex(fx.klass),
                               registry_links=[{"address": "0x9000", "value": "0xa000"}],
                               registry={"count": 1})
        adapter.snapshot = Mock(return_value=state)
        prepared = adapter.prepare_solve(copy.deepcopy(state))
        selected = prepared["native"]["method_spec"]
        self.assertEqual(selected["token"], fx.selected["set"]["token"])
        self.assertNotEqual(selected["token"], TALENT_METHOD["token"])
        self.assertEqual(prepared["native"]["method_info"], hex(fx.methods["set"]))
        transport = MiniGameOnce.__new__(MiniGameOnce)
        transport.operation, transport.method_spec = "alchemy_talent_set", TALENT_METHOD
        request = transport._request(prepared, 123, "offline-fixture")
        self.assertEqual((request["method_token"], request["method_rva"]),
                         (selected["token"], selected["rva"]))
        self.assertEqual(request["minigame"]["method_spec"], selected)
        self.assertTrue(any(a["expected_hex"] == selected["prefix"] for a in request["anchors"]))

    def test_postcondition_allows_dictionary_mutation_not_other_talent(self):
        adapter = self.fixture(); before = copy.deepcopy(adapter.snapshot())
        after = copy.deepcopy(before)
        after["identity"] = before["identity"][:-1] + ((100, 200, 1, 0, 2),)
        after["rows"]["1000001"]["value"] = 1
        adapter.snapshot.return_value = after
        outcome = dict(talent_id=1000001, rank=1)
        self.assertTrue(adapter.verify_native(outcome, before)["verified"])
        after["rows"]["1000002"]["value"] = 1
        with self.assertRaises(UncertainWrite):
            adapter.verify_native(outcome, before)

    def test_postcondition_owner_change_or_return_mismatch_uncertain(self):
        adapter = self.fixture(); before = copy.deepcopy(adapter.snapshot())
        with self.assertRaises(UncertainWrite):
            adapter.verify_native(dict(talent_id=1000002, rank=1), before)
        adapter.snapshot.return_value["identity"] = ("other",)
        with self.assertRaises(UncertainWrite):
            adapter.verify_native(dict(talent_id=1000001, rank=1), before)


if __name__ == "__main__":
    unittest.main()
