"""The frozen diagnostic route must not fall through to GUI or native-host modes."""
import sys
import unittest
from unittest.mock import patch

import audit_update_readonly
import standalone_entry


class UpdateCheckEntryTests(unittest.TestCase):
    def test_routes_to_readonly_checker_and_propagates_failure(self):
        with patch.object(sys, 'argv', ['trainer', '--update-check', 'report.json']), \
                patch.object(audit_update_readonly, 'main', return_value=1) as check:
            self.assertEqual(standalone_entry.main(), 1)
        check.assert_called_once_with(['--output', 'report.json'])

    def test_mixed_modes_rejected_before_any_action(self):
        with patch.object(sys, 'argv', ['trainer', '--update-check', 'report.json',
                                       '--native-host', 'private.json']), \
                patch.object(audit_update_readonly, 'main') as check, \
                patch('sys.stderr'), self.assertRaises(SystemExit) as raised:
            standalone_entry.main()
        self.assertEqual(raised.exception.code, 2)
        check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
