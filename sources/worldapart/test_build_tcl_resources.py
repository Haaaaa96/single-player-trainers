import tempfile
from pathlib import Path
import unittest
import zipfile

from build_tcl_resources import collect_zip_library


class TclResourceTests(unittest.TestCase):
    def test_external_zip_library_is_staged_for_standard_runtime_hook(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tcl').mkdir()
            with zipfile.ZipFile(root / 'tcl' / 'libtcl9.0.4.zip', 'w') as archive:
                archive.writestr('tcl_library/init.tcl', 'set library_version 9.0')
                archive.writestr('tcl_library/encoding/utf-8.enc', 'test')
            result = collect_zip_library(root, root / 'stage', 'tcl', (9, 0))
            self.assertEqual(len(result), 2)
            self.assertEqual(Path(result[0][0]).read_text(), 'set library_version 9.0')
            self.assertEqual(result[1][1], str(Path('_tcl_data') / 'encoding'))

    def test_archive_cannot_write_outside_staging_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tcl').mkdir()
            with zipfile.ZipFile(root / 'tcl' / 'libtcl9.0.4.zip', 'w') as archive:
                archive.writestr('tcl_library/../../outside', 'bad')
            with self.assertRaises(RuntimeError):
                collect_zip_library(root, root / 'stage', 'tcl', (9, 0))
            self.assertFalse((root / 'outside').exists())


if __name__ == '__main__':
    unittest.main()
