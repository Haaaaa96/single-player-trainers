"""Regression for legal polymorphic and null bag slots. No real process access."""
import struct
import unittest
from unittest.mock import Mock

import game_adapter  # Installs the package's runtime import path.
from resolver import Resolver, ResolutionError


class InventoryResolverTests(unittest.TestCase):
    def setUp(self):
        self.rr = Resolver.__new__(Resolver)
        self.rr.anchors = []
        self.mem = {}
        self.base = self.make_class(0x1000, "BagItemBase", 56)
        self.normal = self.make_class(0x1100, "BagItem", 56)
        self.pill = self.make_class(0x1200, "PillBagItem", 112)
        self.artifact = self.make_class(0x1300, "ArtifactBagItem", 136)
        self.unknown = self.make_class(0x1400, "UnreviewedBagItem", 56)
        self.classes = {int(c["klass"], 16): c for c in
                        [self.base, self.normal, self.pill, self.artifact, self.unknown]}
        self.setq(0x1100 + 0x58, 0x1000)
        self.setq(0x1200 + 0x58, 0x1100)
        self.setq(0x1300 + 0x58, 0x1000)
        self.rr.exact = self.exact
        self.rr.field = lambda c, name, kind=None: {
            "ItemId": 16, "Count": 20, "IsEquipped": 25, "Uid": 40}[name]
        self.rr.info = lambda k: self.classes[k]
        self.rr.verify_class = Mock(side_effect=self.verify)
        self.arr = 0x4000

    def make_class(self, address, name, size):
        return {"klass": hex(address), "name": name, "namespace": "Game.Model.Components",
                "instance_size": size}

    def setq(self, address, value):
        self.put(address, struct.pack("<Q", value))

    def put(self, address, data):
        for offset, byte in enumerate(data):
            self.mem[address + offset] = byte

    def exact(self, address, size):
        try:
            return bytes(self.mem[address + offset] for offset in range(size))
        except KeyError as exc:
            raise ResolutionError("unreadable fixture memory") from exc

    def verify(self, klass, full):
        c = self.classes[klass]
        if c["namespace"] + "." + c["name"] != full:
            raise ResolutionError("metadata mismatch")
        return c

    def slot(self, index, klass=0x1100, uid=None, count=2, equipped=False):
        obj = 0x8000 + index * 0x100
        self.put(obj, bytes(160))
        self.setq(self.arr + 32 + index * 8, obj)
        self.setq(obj, klass)
        self.put(obj + 16, struct.pack("<ii", 100010 + index, count))
        self.put(obj + 25, bytes([equipped]))
        self.put(obj + 40, struct.pack("<q", index + 1 if uid is None else uid))
        return obj

    def test_ordinary_pill_artifact_and_null_coexist_without_blocking(self):
        self.slot(0)
        self.slot(1, klass=0x1200)
        self.slot(2, klass=0x1300)
        self.setq(self.arr + 32 + 3 * 8, 0)
        items, diagnostics = self.rr.inventory_entries(self.arr, 4, self.base)
        self.assertEqual([x["count_editable"] for x in items], [True, True, False])
        self.assertEqual([x["class_name"] for x in items],
                         ["Game.Model.Components." + n for n in ["BagItem", "PillBagItem", "ArtifactBagItem"]])
        self.assertEqual(diagnostics, [{"slot": 3, "reason": "null_entry", "message": "空背包槽已跳过。"}])
        self.rr.verify_class.assert_any_call(0x1100, "Game.Model.Components.BagItem")
        self.assertIn("Items[1].pill_identity_fields", [a["label"] for a in self.rr.anchors])
        self.assertIn("Items[3]", [a["label"] for a in self.rr.anchors])

    def test_unknown_class_skipped_without_reading_its_layout(self):
        self.slot(0, klass=0x1400)
        self.slot(1)
        items, diagnostics = self.rr.inventory_entries(self.arr, 2, self.base)
        self.assertEqual([x["slot"] for x in items], [1])
        self.assertEqual(diagnostics[0]["reason"], "unsupported_entry")
        self.assertNotIn("Items[0].ItemId", [a["label"] for a in self.rr.anchors])

    def test_reviewed_name_with_failed_metadata_identity_is_not_accepted(self):
        self.slot(0, klass=0x1200)
        self.rr.verify_class.side_effect = ResolutionError("Class token mismatch")
        items, diagnostics = self.rr.inventory_entries(self.arr, 1, self.base)
        self.assertEqual(items, [])
        self.assertIn("Class token mismatch", diagnostics[0]["message"])

    def test_wrong_inheritance_and_cycles_never_expose_targets(self):
        self.slot(0, klass=0x1200)
        self.setq(0x1200 + 0x58, 0x1400)
        self.assertEqual(self.rr.inventory_entries(self.arr, 1, self.base)[0], [])
        self.setq(0x1200 + 0x58, 0x1200)
        self.assertEqual(self.rr.inventory_entries(self.arr, 1, self.base)[0], [])

    def test_duplicate_uids_disable_both_entries(self):
        self.slot(0, uid=9)
        self.slot(1, uid=9)
        self.slot(2, uid=10)
        items, diagnostics = self.rr.inventory_entries(self.arr, 3, self.base)
        self.assertEqual([x["uid"] for x in items], [10])
        self.assertEqual([x["reason"] for x in diagnostics], ["duplicate_uid", "duplicate_uid"])

    def test_equipped_pill_is_readable_but_not_writable(self):
        self.slot(0, klass=0x1200, equipped=True)
        items, diagnostics = self.rr.inventory_entries(self.arr, 1, self.base)
        self.assertEqual(diagnostics, [])
        self.assertFalse(items[0]["count_editable"])
        self.assertTrue(items[0]["is_equipped"])

    def test_invalid_count_does_not_hide_other_valid_entries(self):
        self.slot(0, count=-1)
        self.slot(1)
        items, diagnostics = self.rr.inventory_entries(self.arr, 2, self.base)
        self.assertEqual([x["slot"] for x in items], [1])
        self.assertEqual(diagnostics[0]["reason"], "unsupported_entry")

    def test_zero_count_is_preserved_for_currency_classification(self):
        self.slot(0, count=0)
        items, _ = self.rr.inventory_entries(self.arr, 1, self.base)
        self.assertEqual(items[0]["count"], 0)


if __name__ == "__main__":
    unittest.main()
