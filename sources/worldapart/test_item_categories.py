"""The two inventory views share labels without inventing an item-type map."""
import unittest

from item_categories import category_name, UNKNOWN_CATEGORY


class CategoryNameTests(unittest.TestCase):
    def test_prefers_chinese_game_label(self):
        self.assertEqual(category_name({"type_names": {"zh-Hans": " 丹药 ", "en-US": "Pills"}}), "丹药")

    def test_english_fallback_matches_preformatted_inventory_row(self):
        label = category_name({"type_names": {"zh-Hans": "", "en-US": "Materials"}})
        self.assertEqual(label, "Materials")
        self.assertEqual(category_name({"type_name": label}), label)

    def test_missing_or_malformed_labels_are_unknown_without_guessing_from_type_id(self):
        for item in ({}, {"item_type_id": 19}, {"type_names": None}, {"type_names": []},
                     {"type_names": {"zh-Hans": 7, "en-US": "  "}},
                     {"type_name": None}, {"type_name": []}, None):
            with self.subTest(item=item):
                self.assertEqual(category_name(item), UNKNOWN_CATEGORY)

    def test_formatting_does_not_mutate_quantity_metadata(self):
        item = {"item_type_id": 19, "max_count_per_grid": 999, "type_names": {"zh-Hans": "材料"}}
        before = dict(item)
        self.assertEqual(category_name(item), "材料")
        self.assertEqual(item, before)


if __name__ == "__main__":
    unittest.main()
