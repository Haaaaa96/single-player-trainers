import json
from pathlib import Path
import tempfile
import unittest

from runtime_paths import migrate_safety_state


class SafetyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.old = Path(self.temp.name) / 'old'
        self.new = Path(self.temp.name) / 'new'
        self.old.mkdir()
        self.new.mkdir()

    def journal(self, folder, status, **extra):
        path = folder / 'acquisition-pending.json'
        path.write_text(json.dumps(dict(status=status, **extra)), encoding='utf8')
        return path

    def test_pending_and_claims_survive_migration_without_deletion(self):
        old = self.journal(self.old, 'pending', token='live-op')
        claims = self.old / 'native-epochs'
        claims.mkdir()
        (claims / '12-12345.json').write_text('{"pid":12}', encoding='utf8')
        migrate_safety_state(self.old, self.new)
        self.assertEqual((self.new / old.name).read_bytes(), old.read_bytes())
        self.assertTrue((self.new / 'native-epochs' / '12-12345.json').is_file())
        self.assertTrue(old.is_file())
        self.assertTrue((claims / '12-12345.json').is_file())

    def test_existing_pending_is_not_overwritten_by_legacy_verified(self):
        self.journal(self.old, 'verified')
        current = self.journal(self.new, 'pending', token='new-op')
        before = current.read_bytes()
        migrate_safety_state(self.old, self.new)
        self.assertEqual(current.read_bytes(), before)

    def test_conflicting_pending_legacy_stops_migration(self):
        self.journal(self.old, 'unknown', token='old-op')
        current = self.journal(self.new, 'verified', token='new-op')
        before = current.read_bytes()
        with self.assertRaisesRegex(RuntimeError, '未确认'):
            migrate_safety_state(self.old, self.new)
        self.assertEqual(current.read_bytes(), before)
        self.assertFalse(list(self.new.glob('migrated-*')))

    def test_old_aggregate_epochs_become_exclusive_claims(self):
        (self.old / 'acquisition-native-epochs.json').write_text(
            json.dumps({'version': 1, 'processes': {'12:12345': {'pid': 12}}}), encoding='utf8')
        migrate_safety_state(self.old, self.new)
        self.assertEqual(json.loads((self.new / 'native-epochs' / '12-12345.json').read_text()), {'pid': 12})

    def test_verified_no_injection_edit_does_not_erase_legacy_native_block(self):
        self.journal(self.old, 'verified', native_block_reason='earlier attach failed')
        current = self.journal(self.new, 'verified')
        before = current.read_bytes()
        with self.assertRaisesRegex(RuntimeError, '未确认'):
            migrate_safety_state(self.old, self.new)
        self.assertEqual(current.read_bytes(), before)

    def test_migrated_old_pending_does_not_resurrect_after_verified(self):
        self.journal(self.old, 'pending', token='old-op')
        migrate_safety_state(self.old, self.new)
        current = self.journal(self.new, 'verified', token='old-op')
        migrate_safety_state(self.old, self.new)
        self.assertEqual(json.loads(current.read_text())['status'], 'verified')

    def test_missing_legacy_is_not_an_error(self):
        migrate_safety_state(self.old / 'missing', self.new)
        self.assertFalse(list(self.new.iterdir()))

    def test_invalid_epoch_key_cannot_escape_directory(self):
        (self.old / 'acquisition-native-epochs.json').write_text(
            json.dumps({'version': 1, 'processes': {'../12:12345': {'pid': 12}}}), encoding='utf8')
        with self.assertRaises(RuntimeError):
            migrate_safety_state(self.old, self.new)


if __name__ == '__main__':
    unittest.main()
