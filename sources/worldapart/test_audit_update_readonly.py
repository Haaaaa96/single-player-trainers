"""Offline scheduling/privacy checks; no real adapters or process connection."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import audit_update_readonly as audit


class AuditReadonlyTests(unittest.TestCase):
    def test_real_construction_schedule_repeats_same_instance_and_only_reads_lifespan_context(self):
        instances = {}
        closed = []
        game = SimpleNamespace(resolver=SimpleNamespace(reader=object(), meta=123))
        core_reads = []
        game.snapshot = lambda: core_reads.append(1) or {"spirit": object(), "path": object(), "items": {}}

        def loader(module):
            case = next(c for c in audit.CASES if c.module == module)

            class FakeAdapter:
                def __init__(self, owner, **kwargs):
                    self.calls = 0
                    self.asserted_owner = owner
                    self.kwargs = kwargs
                    instances[case.key] = self

                def snapshot(self):
                    if case.key == "lifespan_read_context":
                        raise AssertionError("Lifespan.snapshot would call native getters")
                    self.calls += 1
                    return {"active": False, "reason": "无活动局", "anchors": ["secret"]}

                def read_context(self):
                    self.calls += 1
                    return {"descriptor": {"player": "0x12345678"}}

                def catalog(self, *, refresh=False):
                    self.calls += 1
                    if not refresh:
                        raise AssertionError("Must bypass catalogue cache")
                    return [object()]

                def close(self):
                    closed.append(case.key)

            return SimpleNamespace(**{case.klass: FakeAdapter})

        results = [audit.survey_case(case, game, loader=loader) for case in audit.CASES]
        self.assertEqual(len(core_reads), 2)
        self.assertEqual(len(instances), 18)
        self.assertEqual(len(closed), 18)
        self.assertTrue(all(value.calls == 2 for value in instances.values()))
        self.assertTrue(all(row["status"] == "reads_complete" for row in results))
        self.assertEqual({page for case in audit.CASES for page in case.pages}.__len__(), 18)
        self.assertIn("alchemy_recipe", instances)
        self.assertIs(instances["learning"].asserted_owner, game.resolver.reader)
        self.assertEqual(instances["meridian"].kwargs, {"metadata_base": 123})
        self.assertIs(instances["lifespan_read_context"].asserted_owner, game)
        self.assertNotIn("secret", json.dumps(results))
        self.assertIn("no_active_session", json.dumps(results))

    def test_constructor_read_and_cleanup_errors_are_independent(self):
        case = audit.CASES[1]
        with patch.object(audit.importlib, "import_module"):
            result = audit.survey_case(case, object(), loader=lambda _: (_ for _ in ()).throw(ValueError("constructor")))
        self.assertEqual((result["status"], result["phase"], result["reads"]), ("failed", "construct", []))

        class Flaky:
            def __init__(self, game):
                self.calls = 0

            def snapshot(self):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("first read refused")
                return {"active": False, "reason": "当前无活动局"}

            def close(self):
                raise RuntimeError("cleanup refused")

        result = audit.survey_case(case, object(), loader=lambda _: SimpleNamespace(CharacterAttributesAdapter=Flaky))
        self.assertEqual(result["status"], "read_errors")
        self.assertEqual([r["status"] for r in result["reads"]], ["failed", "read_complete"])
        self.assertEqual(result["cleanup"]["phase"], "close")

    def test_report_failure_closes_game_and_retains_verified_identity_without_paths(self):
        closed = []
        game = SimpleNamespace(resolver=SimpleNamespace(reader=SimpleNamespace(pid=42)),
                               stamp=(r"C:\Users\Private\WorldApart.exe", 123456),
                               close=lambda: closed.append(True))
        game.compatibility = SimpleNamespace(as_dict=lambda: {
            "steam_build_id": "25617557", "metadata_version": 31,
            "executable_path": game.stamp[0], "files": [], "warnings": []})
        with patch.object(audit, "survey_case", side_effect=lambda *a, **k: {"status": "failed", "reason": "module failure"}):
            report = audit.run_audit(connector=lambda _: game)
        self.assertEqual(closed, [True])
        self.assertEqual(len(report["modules"]), len(audit.CASES))
        self.assertEqual(report["gui_page_count"], 18)
        self.assertEqual(report["process"]["creation_filetime"], 123456)
        self.assertEqual(report["installation"]["steam_build_id"], "25617557")
        self.assertIsNone(report["installation"]["game_display_version"])
        self.assertNotIn("Private", json.dumps(report))
        self.assertFalse(report["native_calls_requested"])

    def test_connection_failure_and_error_sanitizing(self):
        def refuse(_):
            raise OSError("unreadable 'C:\\Users\\Private\\save.dat' at 0x12345678")
        report = audit.run_audit(connector=refuse)
        self.assertTrue(all(row["status"] == "not_run" for row in report["modules"].values()))
        self.assertEqual(report["connection"]["phase"], "connect")
        encoded = json.dumps(report)
        self.assertNotIn("Private", encoded)
        self.assertNotIn("12345678", encoded)

    def test_cli_writes_utf8_report_without_serializing_snapshots(self):
        report = {"connection": {"status": "connected"}, "modules": {}, "note": "只读完成"}
        with TemporaryDirectory() as folder:
            output = Path(folder) / "survey.json"
            with patch.object(audit, "run_audit", return_value=report) as run, patch("builtins.print"):
                self.assertEqual(audit.main(["--output", str(output)]), 1)
                run.assert_called_once_with(game_path=None, include_paths=False)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), report)
            self.assertIn("只读完成".encode("utf-8"), output.read_bytes())

    def test_complete_report_requires_all_reads_identity_and_cleanup(self):
        import copy
        report = {"connection": {"status": "connected"},
                  "installation": {"status": "verified_disk_assessment"},
                  "modules": {case.key: {"status": "reads_complete", "reads": [
                      {"status": "read_complete"}, {"status": "read_complete"}]}
                      for case in audit.CASES}}
        self.assertTrue(audit.checks_passed(report))
        for change in (lambda r: r.update(connection_cleanup={"status": "failed"}),
                       lambda r: r["installation"].update(status="failed"),
                       lambda r: r["modules"].pop("core"),
                       lambda r: r["modules"]["core"]["reads"].pop(),
                       lambda r: r["modules"]["core"].update(cleanup={"status": "failed"})):
            changed = copy.deepcopy(report)
            change(changed)
            self.assertFalse(audit.checks_passed(changed))

    def test_windowed_exe_without_stdout_still_returns_connection_failure_report(self):
        with patch.object(audit.sys, "stdout", None):
            audit.progress("read check")
            report = audit.run_audit(connector=lambda _: (_ for _ in ()).throw(OSError("No game")))
        self.assertFalse(report["read_checks_passed"])
        self.assertFalse(report["functional_acceptance_tested"])
        self.assertTrue(report["trainer_version"])


if __name__ == "__main__":
    unittest.main()
