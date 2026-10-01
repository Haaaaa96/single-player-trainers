import unittest
from dataclasses import replace
from unittest.mock import Mock

from acquisition_existing import try_add_existing as add_existing
from write_guard import PreconditionChanged, Refused, Target, UncertainWrite

ANCHORS = [{'address': 0x9000, 'expected_hex': '00', 'size': 1}]
PRECONDITIONS = ((0x9000, b'\x00'),)


def try_add_existing(game, item_id, quantity):
    return add_existing(game, item_id, quantity, context_anchors=ANCHORS)


def existing(uid=1, value=2, maximum=999, item_id=180000, klass='PillBagItem'):
    target = Target(f'item:{uid}', 0x1000 + uid * 4, value, ('player', uid), 1, maximum)
    return {'target': target, 'item_id': item_id,
            'class_name': 'Game.Model.Components.' + klass}


class ExistingAcquisitionTests(unittest.TestCase):
    def game(self, rows):
        game = Mock()
        game.snapshot.return_value = {'items': {r['target'].key: r for r in rows}}
        game.set_value.side_effect = lambda target, value, **kwargs: replace(target, value=value)
        return game

    def test_existing_pill_uses_one_guarded_write(self):
        row = existing()
        game = self.game([row])
        result = try_add_existing(game, 180000, 10)
        game.set_value.assert_called_once_with(row['target'], 12, preconditions=PRECONDITIONS)
        self.assertTrue(result['verified'])
        self.assertFalse(result['native_injection'])
        self.assertEqual(result['new_uids'], [])

    def test_target_999_uses_native_stack_limit(self):
        game = self.game([existing(value=989)])
        self.assertEqual(try_add_existing(game, 180000, 10)['after'], 999)

    def test_no_eligible_stack_does_not_write_anything(self):
        for rows in ([], [existing(item_id=123)], [existing(value=995)],
                     [existing(value=95, maximum=99)], [existing(klass='GongfaBagItem')]):
            with self.subTest(rows=rows):
                game = self.game(rows)
                self.assertIsNone(try_add_existing(game, 180000, 10))
                game.set_value.assert_not_called()

    def test_no_partial_multi_stack_write(self):
        game = self.game([existing(uid=1, value=995), existing(uid=2, value=995)])
        self.assertIsNone(try_add_existing(game, 180000, 8))
        game.set_value.assert_not_called()

    def test_one_valid_stack_chosen_when_another_is_full(self):
        row = existing(uid=2, value=2)
        game = self.game([existing(uid=1, value=999), row])
        try_add_existing(game, 180000, 10)
        game.set_value.assert_called_once_with(row['target'], 12, preconditions=PRECONDITIONS)

    def test_refusal_and_uncertainty_propagate_without_retry(self):
        for error in (Refused('stale'), UncertainWrite('unknown'), OSError('connection lost')):
            game = self.game([existing()])
            game.set_value.side_effect = error
            with self.assertRaises(type(error)):
                try_add_existing(game, 180000, 10)
            game.set_value.assert_called_once()

    def test_wrong_readback_is_uncertain(self):
        row = existing()
        game = self.game([row])
        game.set_value.side_effect = lambda target, value, **kwargs: target
        with self.assertRaises(UncertainWrite):
            try_add_existing(game, 180000, 10)

    def test_invalid_quantity_never_reads_or_writes(self):
        game = Mock()
        for value in (True, 0, -1, 1000, 1.5, '10'):
            with self.subTest(value=value), self.assertRaises(Refused):
                try_add_existing(game, 180000, value)
        game.snapshot.assert_not_called()
        game.set_value.assert_not_called()

    def test_late_scene_change_is_known_no_write_refusal(self):
        from acquisition_context import AcquisitionContextRefused
        game = self.game([existing()])
        game.set_value.side_effect = PreconditionChanged('battle started')
        with self.assertRaises(AcquisitionContextRefused):
            try_add_existing(game, 180000, 10)
        game.set_value.assert_called_once()

    def test_missing_scene_anchors_never_writes(self):
        game = self.game([existing()])
        with self.assertRaises(Refused):
            add_existing(game, 180000, 10, context_anchors=[])
        game.set_value.assert_not_called()


if __name__ == '__main__':
    unittest.main()
