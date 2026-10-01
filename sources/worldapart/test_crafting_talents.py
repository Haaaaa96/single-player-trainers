"""Synthetic scalar safety tests; no game process is opened."""
from contextlib import nullcontext
from dataclasses import replace
import json
from pathlib import Path
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import crafting_talents as cp
from write_guard import Refused, UncertainWrite


def target(**changes):
    return replace(cp.CraftingTalentTarget("crafting_talents", 100, 0x4028, ("player",),
                                    ((0x100, "00"),), 0, 1000), **changes)


class TalentValueTests(unittest.TestCase):
    def test_integer_parser_rejects_decimal_exponent_bool_and_unbounded_text(self):
        self.assertEqual(cp.parse_crafting_talent_value(" 123 "), 123)
        for text in ("", "1.0", "1e3", True, 1, "+1", "1,000", "12345678", "1" * 21):
            with self.subTest(text=text), self.assertRaises(Refused):
                cp.parse_crafting_talent_value(text)

    def test_talent_has_nonnegative_range_and_thousand_change_limit(self):
        self.assertEqual(cp.validate_crafting_talent_value(target(), 1000), 1000)
        self.assertEqual(cp.validate_crafting_talent_value(target(value=999), 1000), 1000)
        for value in (-1, 1001, 100, 1001, True, 101.0):
            with self.subTest(value=value), self.assertRaises(Refused):
                cp.validate_crafting_talent_value(target(), value)

    def test_forged_policy_identity_and_overlapping_anchor_are_rejected(self):
        for changes in (dict(key="unknown"), dict(minimum=-1), dict(maximum=2000),
                        dict(can_edit=False), dict(address=0), dict(address=0x4029),
                        dict(identity=()), dict(anchors=()), dict(anchors=((0x4027,"0000"),)),
                        dict(anchors=((0x100,"nothex"),)), dict(anchors=((0,"00"),))):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                cp.validate_crafting_talent_value(target(**changes), 101)

    def test_unrelated_fields_are_not_editable_talent_targets(self):
        self.assertEqual(set(cp.FIELDS), {"crafting_talents"})
        with self.assertRaises(Refused):
            cp.validate_crafting_talent_value(target(key="prop_evil"), 101)

    def test_writer_uses_exact_int32_and_inherited_cross_host_guard(self):
        writer = cp.CraftingTalentWriteOnce(Mock(), ("path", 1), target(), new_value=101)
        self.assertEqual(writer.before, struct.pack("<i", 100))
        self.assertEqual(writer.after, struct.pack("<i", 101))
        self.assertIs(cp.CraftingTalentWriteOnce.write_exact, cp.AttributeWriteOnce.write_exact)
        self.assertTrue(writer.write_exact._scalar_coordinated)


class TalentWriteTests(unittest.TestCase):
    def setUp(self):
        self.shown, self.current = target(), target()
        self.data = cp.pack(self.shown.value)
        self.memory, self.record = Mock(), Mock()
        self.memory.read_exact.side_effect = lambda a,n:self.data
        def write(a,data):
            self.data = data
            self.current = replace(self.shown, value=struct.unpack("<i",data)[0])
        self.memory.write_exact.side_effect = write
        self.resolve = Mock(side_effect=lambda key:self.current)

    def run_edit(self):
        return cp.set_crafting_talent_scalar(self.memory,self.resolve,self.shown,101,self.record)

    def test_exact_four_byte_write_and_verified_readback(self):
        self.assertEqual(self.run_edit().value, 101)
        self.memory.write_exact.assert_called_once_with(self.shown.address, cp.pack(101))
        self.assertEqual([c.args[0]["status"] for c in self.record.call_args_list], ["attempt","verified"])

    def test_stale_identity_or_value_never_writes(self):
        self.current = replace(self.shown, identity=("other",))
        with self.assertRaises(Refused):self.run_edit()
        self.current = self.shown
        self.data = cp.pack(102)
        with self.assertRaises(Refused):self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_context_changed_after_durable_attempt_is_rejected(self):
        self.record.side_effect = lambda e:setattr(self,"current",replace(self.shown,can_edit=False))
        with self.assertRaises(Refused):self.run_edit()
        self.memory.write_exact.assert_not_called()
        self.assertEqual(self.record.call_args.args[0]["status"],"rejected")

    def test_attempt_journal_failure_prevents_write(self):
        self.record.side_effect = OSError("disk")
        with self.assertRaises(OSError):self.run_edit()
        self.memory.write_exact.assert_not_called()

    def test_unknown_log_failure_never_masks_original_uncertain(self):
        error = UncertainWrite("partial")
        self.memory.write_exact.side_effect = error
        self.record.side_effect = [None,OSError("disk")]
        with self.assertRaises(UncertainWrite) as caught:self.run_edit()
        self.assertIs(caught.exception,error)
        self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_unexpected_writer_exception_is_unknown(self):
        self.memory.write_exact.side_effect = OSError("possibly partial")
        with self.assertRaises(UncertainWrite):self.run_edit()
        self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_proven_no_write_is_rejected(self):
        self.memory.write_exact.side_effect = Refused("changed")
        with self.assertRaises(Refused) as caught:self.run_edit()
        self.assertNotIsInstance(caught.exception,UncertainWrite)
        self.assertEqual(self.record.call_args.args[0]["status"],"rejected")

    def test_postwrite_identity_change_or_read_failure_is_unknown(self):
        for result in (replace(self.shown,value=101,identity=("other",)), OSError("read")):
            with self.subTest(result=result):
                self.setUp()
                self.resolve.side_effect = [self.shown,self.shown,result]
                with self.assertRaises(UncertainWrite):self.run_edit()
                self.assertEqual(self.record.call_args.args[0]["status"],"unknown")

    def test_verified_and_unknown_journal_failures_remain_uncertain(self):
        self.record.side_effect = [None,OSError("disk"),OSError("disk")]
        with self.assertRaises(UncertainWrite):self.run_edit()
        self.memory.write_exact.assert_called_once()


class TalentJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.adapter = cp.CraftingTalentAdapter.__new__(cp.CraftingTalentAdapter)
        self.adapter.journal = Path(self.tmp.name)/"profile.json"
        self.adapter.game = SimpleNamespace(resolver=SimpleNamespace(reader=SimpleNamespace(pid=123)),stamp=("game",456),record=Mock())
        self.adapter.blocked,self.adapter._lock = False,threading.Lock()

    def test_atomic_journal_contains_identity_and_pending_blocks_new_adapter(self):
        self.adapter.require_ready()
        self.adapter.record(dict(status="attempt"))
        data = json.loads(self.adapter.journal.read_text(encoding="utf8"))
        self.assertEqual(data["process_key"],[123,456])
        self.assertEqual(data["version"],1)
        with self.assertRaises(Refused):self.adapter.require_ready()
        for status in ("verified","rejected"):
            self.adapter.record(dict(status=status))
            self.adapter.require_ready()

    def test_corrupt_wrong_identity_and_unknown_journal_fail_closed(self):
        for data in ("bad",json.dumps(dict(version=1,process_key=[123,999],status="verified")),
                     json.dumps(dict(version=1,process_key=[123,456],status="unknown"))):
            self.adapter.journal.write_text(data,encoding="utf8")
            with self.assertRaises(Refused):self.adapter.require_ready()

    def test_native_pending_stops_before_writer_or_journal(self):
        with patch("native_broker.startup_lock",return_value=nullcontext()), \
             patch("acquisition_adapter.native_calls_pending",return_value=True), \
             patch.object(cp,"CraftingTalentWriteOnce") as writer, self.assertRaises(Refused):
            self.adapter.set_value(target(),101)
        writer.assert_not_called()
        self.assertFalse(self.adapter.journal.exists())
        self.assertTrue(self.adapter._lock.acquire(blocking=False))
        self.adapter._lock.release()


    def test_uncertain_flow_permanently_blocks_adapter_and_releases_local_lock(self):
        with patch("native_broker.startup_lock",return_value=nullcontext()), \
             patch("acquisition_adapter.native_calls_pending",return_value=False), \
             patch.object(cp,"CraftingTalentWriteOnce"), \
             patch.object(cp,"set_crafting_talent_scalar",side_effect=UncertainWrite("unknown")), self.assertRaises(UncertainWrite):
            self.adapter.set_value(target(),101)
        self.assertTrue(self.adapter.blocked)
        self.assertTrue(self.adapter._lock.acquire(blocking=False))
        self.adapter._lock.release()

class TalentSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.adapter=cp.CraftingTalentAdapter.__new__(cp.CraftingTalentAdapter)
        self.adapter.blocked=False
        self.rr=Mock()
        self.rr.reader=SimpleNamespace(h=1)
        self.rr.module=0x100000
        self.rr.obj.return_value=dict(parent='0x7000')
        self.rr.pointer_field.side_effect=lambda obj,c,name,*args,**kw:0x4000 if name=='alchemy' else 0x9000
        self.rr.info.return_value=dict(name='StoredEntityComponent')
        self.rr.field.return_value=16
        self.rr.q.return_value=0
        self.rr.at.return_value=0x4028
        self.rr.i.return_value=2
        self.rr.integer.return_value=1
        self.rr.anchor.return_value=bytes.fromhex('895128c3')
        self.rr.registered_panels.return_value=(0x8000,[])
        self.rr.proof.return_value=[dict(address='0x3050',expected_hex='0040000000000000')]
        self.adapter.resolver=self.rr
        raw=dict(anchor_verified=True,anchors=[],manager=1,store=2,world=3,player=0x3000)
        self.adapter.game=SimpleNamespace(blocked=False,stamp=('game',123),resolver=Mock())
        self.adapter.game.resolver.resolve.return_value=raw
        patch.object(cp,'process_identity',return_value=('game',123)).start()
        self.context=patch.object(cp,'require_safe_acquisition_context',return_value=dict(anchors=[])).start()
        self.addCleanup(patch.stopall)

    def test_null_entity_is_valid_under_anchored_current_player_reference(self):
        state=self.adapter.snapshot()
        self.assertEqual(state['target'].value,2)
        self.assertTrue(state['can_edit'])
        self.assertEqual(state['target'].identity[-2:],(0,1))
        self.rr.field.assert_called_once_with(self.rr.info.return_value,'<entity>k__BackingField',0x12,0x0400003B)

    def test_current_player_entity_backref_is_valid_other_owner_refused(self):
        self.rr.q.return_value=0x3000
        self.assertTrue(self.adapter.snapshot()['can_edit'])
        self.rr.q.return_value=0x3330
        with self.assertRaises(Refused):self.adapter.snapshot()

    def test_unreviewed_parent_field_offset_refused(self):
        self.rr.field.return_value=24
        with self.assertRaises(Refused):self.adapter.snapshot()

    def test_uninitialized_talent_state_or_sets_refuse_without_initialization(self):
        for version in (0,2):
            self.rr.integer.return_value=version
            with self.assertRaises(Refused):self.adapter.snapshot()
        self.rr.integer.return_value=1
        self.rr.pointer_field.side_effect=lambda obj,c,name,*args,**kw:0x4000 if name=='alchemy' else 0
        with self.assertRaises(Refused):self.adapter.snapshot()

    def test_each_visible_talent_or_board_page_disables_editing(self):
        for index in range(3):
            self.rr.registered_panels.side_effect=[(0x8000,[0x9000] if index==i else []) for i in range(3)]
            self.rr.visible_panel.return_value=({},True)
            state=self.adapter.snapshot()
            self.assertFalse(state['can_edit']);self.assertFalse(state['target'].can_edit)
            self.assertIn('关闭',state['reason'])
            self.assertEqual(self.rr.panel_type,cp.PANEL)

    def test_unsafe_scene_and_out_of_range_balance_stay_readonly(self):
        self.context.side_effect=cp.AcquisitionContextRefused('unsafe')
        self.assertFalse(self.adapter.snapshot()['can_edit'])
        self.context.side_effect=None
        self.rr.i.return_value=1001
        self.assertFalse(self.adapter.snapshot()['target'].can_edit)

    def test_setter_code_mismatch_refuses(self):
        self.rr.anchor.return_value=b'\0'*4
        with self.assertRaises(Refused):self.adapter.snapshot()

    def test_readonly_connection_rejects_before_resolving_old_fields(self):
        self.adapter.game.write_enabled=False
        with self.assertRaises(Refused):self.adapter.snapshot()
        self.adapter.game.resolver.resolve.assert_not_called()


if __name__ == "__main__": unittest.main()
