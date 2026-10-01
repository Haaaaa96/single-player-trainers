"""Internal, bounded read-only survey of the 18 GUI pages after a game update.

Run against an already running game with --output PATH, or use the standalone
EXE's --update-check PATH entry. It never starts a game, calls a
native getter, prepares a native request, or exercises a modification. Adapter
constructors are real (and may initialize local safety-log directories).
"""
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
from itertools import islice
import json
from pathlib import Path
import re
import sys
import time


@dataclass(frozen=True)
class Case:
    key: str
    module: str
    klass: str
    method: str
    pages: tuple[str, ...]
    reader_constructor: bool = False


# Only these reviewed read methods are scheduled. In particular, lifespan's
# snapshot calls native getters and must never be used by this survey.
CASES = (
    Case("core", "game_adapter", "GameAdapter", "snapshot", ("角色点数", "背包数量（含已有货币）")),
    Case("attributes", "character_attributes", "CharacterAttributesAdapter", "snapshot", ("人物属性",)),
    Case("interact", "character_attributes_interact", "InteractAttributesAdapter", "snapshot", ("资质与技艺",)),
    Case("profile", "character_profile", "CharacterProfileAdapter", "snapshot", ("修行储备",)),
    Case("resources", "current_resources", "CurrentResourcesAdapter", "snapshot", ("当前资源",)),
    Case("lifespan_read_context", "character_lifespan", "LifespanAdapter", "read_context", ("增加寿元",)),
    Case("speed", "game_speed", "GameSpeedAdapter", "snapshot", ("游戏速度",)),
    Case("learning", "learning_adapter", "LearningResolver", "snapshot", ("功法学习小游戏",), True),
    Case("meridian", "meridian_adapter", "MeridianResolver", "snapshot", ("疏经导脉辅助",), True),
    Case("alchemy", "alchemy_adapter", "AlchemyAdapter", "snapshot", ("炼丹辅助",)),
    Case("alchemy_talents", "alchemy_talents", "AlchemyTalentAdapter", "snapshot", ("炼丹辅助",)),
    Case("alchemy_recipe", "alchemy_recipe", "AlchemyRecipeAdapter", "snapshot", ("丹方探索",)),
    Case("crafting", "crafting_adapter", "CraftingAdapter", "snapshot", ("炼器辅助",)),
    Case("crafting_talents", "crafting_talents", "CraftingTalentAdapter", "snapshot", ("炼器辅助",)),
    Case("dual", "dual_cultivation_adapter", "DualCultivationAdapter", "snapshot", ("双修",)),
    Case("jade", "jade_adapter", "JadeAdapter", "snapshot", ("刮玉",)),
    Case("photostone", "photostone_adapter", "PhotostoneAdapter", "snapshot", ("留影石",)),
    Case("persuasion", "persuasion_adapter", "PersuasionAdapter", "snapshot", ("秒说服",)),
    Case("catalogue", "acquisition_adapter", "AcquisitionAdapter", "catalog", ("添加物品与秘籍",)),
)
FLAGS = ("active", "available", "can_edit", "can_solve", "can_complete", "paused", "blocked")
REASONS = ("reason", "message", "solve_reason", "context_reason", "force_reason")
COLLECTIONS = ("rows", "items", "entries", "states", "targets", "currencies")


def progress(message):
    # PyInstaller's windowed EXE has no stdout. Diagnostics must still run.
    if sys.stdout is not None:
        print(message, flush=True)


def checks_passed(report):
    """A partial survey or a failed close is never a successful check."""
    rows = report.get("modules", {})
    return (report.get("connection", {}).get("status") == "connected"
            and "connection_cleanup" not in report
            and report.get("installation", {}).get("status") == "verified_disk_assessment"
            and set(rows) == {case.key for case in CASES}
            and all(row.get("status") == "reads_complete" and "cleanup" not in row
                    and len(row.get("reads", [])) == 2
                    and all(read.get("status") == "read_complete" for read in row["reads"])
                    for row in rows.values()))


def safe_text(value, *, include_paths=False):
    """Keep bounded diagnostics, never whole objects, pointers or user paths."""
    text = str(value)
    # Exception messages can contain absolute paths even when no installation
    # fields are emitted. Keep surrounding diagnostic words, omit path spans.
    if not include_paths:
        text = re.sub(r"[A-Za-z]:[\\/][^\r\n\"'<>|]*", "[path]", text)
        text = re.sub(r"\\\\[^\r\n\"'<>|]+", "[path]", text)
    text = re.sub(r"\b0x[0-9a-fA-F]+\b", "[hex]", text)
    return text[:2000]


def failure(error, phase, include_paths):
    return {"status": "failed", "phase": phase, "error_type": type(error).__name__,
            "reason": safe_text(error, include_paths=include_paths)}


def summarize(value, *, include_paths=False):
    result = {"result_type": type(value).__name__}
    if not isinstance(value, dict):
        if isinstance(value, (list, tuple)):
            result["count"] = len(value)
        return result
    for key in FLAGS:
        if type(value.get(key)) is bool:
            result[key] = value[key]
    for key in REASONS:
        if isinstance(value.get(key), str):
            result[key] = safe_text(value[key], include_paths=include_paths)
    if value.get("active") is False:
        result["observation"] = "no_active_session; active path not covered"
    elif value.get("available") is False:
        result["observation"] = "unavailable in current state"
    for key in COLLECTIONS:
        collection = value.get(key)
        if isinstance(collection, (dict, list, tuple)):
            result[key + "_count"] = len(collection)
    rows = value.get("rows")
    if isinstance(rows, (dict, list, tuple)):
        reasons = []
        inspected = 0
        for row in islice(rows.values() if isinstance(rows, dict) else rows, 64):
            inspected += 1
            if isinstance(row, dict):
                for key in REASONS:
                    raw = row.get(key)
                    if isinstance(raw, str) and raw:
                        reason = safe_text(raw, include_paths=include_paths)
                        if reason not in reasons and len(reasons) < 8:
                            reasons.append(reason)
        result["row_reasons"] = reasons
        result["rows_inspected_for_reasons"] = inspected
    if "spirit" in value and "path" in value:
        result["point_targets_present"] = True  # Do not export balances/targets.
    return result


def installation_summary(game, include_paths):
    assessment = getattr(game, "compatibility", None)
    if assessment is None:
        return {"status": "unavailable", "reason": "No verified installation assessment returned by connector."}
    data = assessment.as_dict()
    result = {"status": "verified_disk_assessment", "version_source": "selected installation Steam manifest",
              "game_display_version": None, "game_display_version_note": "Not independently read by this survey."}
    for key in ("steam_build_id", "steam_app_id", "reviewed_steam_build_id", "metadata_version",
                "metadata_header_valid", "reviewed_files_match", "mode"):
        result[key] = data.get(key)
    result["files"] = [{key: entry.get(key) for key in (
        "relative_path", "actual_sha256", "size_bytes", "matches_reviewed")}
        for entry in data.get("files", ())]
    result["warnings"] = [safe_text(item, include_paths=include_paths) for item in data.get("warnings", ())]
    if include_paths:
        for key in ("executable_path", "install_directory", "steam_manifest_path"):
            result[key] = data.get(key)
    return result


def survey_case(case, game, *, loader=importlib.import_module, include_paths=False):
    row = {"adapter": case.module + "." + case.klass, "method": case.method,
           "gui_pages": list(case.pages), "reads": [], "read_only": True}
    obj = None
    try:
        if case.key == "core":
            obj = game
            row["construction"] = "real GameAdapter via connect_game; constructor already performs a snapshot"
        else:
            cls = getattr(loader(case.module), case.klass)
            obj = (cls(game.resolver.reader, metadata_base=game.resolver.meta)
                   if case.reader_constructor else cls(game))
            row["construction"] = "constructed"
    except Exception as error:
        row.update(failure(error, "construct", include_paths))
        return row
    try:
        for number in (1, 2):
            try:
                # A second catalogue read must visit the current process, not
                # just return the adapter's cached first result.
                kwargs = {"refresh": True} if case.key == "catalogue" else {}
                value = getattr(obj, case.method)(**kwargs)
                observed = summarize(value, include_paths=include_paths)
                row["reads"].append({"number": number, "status": "read_complete", **observed})
            except Exception as error:
                row["reads"].append({"number": number, **failure(error, "read", include_paths)})
        row["status"] = ("reads_complete" if all(r["status"] == "read_complete" for r in row["reads"])
                         else "read_errors")
    finally:
        if case.key != "core" and hasattr(obj, "close"):
            try:
                obj.close()
            except Exception as error:
                row["cleanup"] = failure(error, "close", include_paths)
    return row


def connect_existing_game(game_path=None):
    # Delayed import keeps --help and offline scheduling tests process-free.
    from game_connection import connect_game
    return connect_game(game_path)


def run_audit(*, game_path=None, include_paths=False, connector=connect_existing_game,
              loader=importlib.import_module):
    from release_info import VERSION
    started = time.monotonic()
    report = {"format": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
              "trainer_version": VERSION, "functional_acceptance_tested": False,
              "read_only": True, "native_calls_requested": False,
              "scope": "Two explicit reads per real instance; current state only. No functional acceptance claim.",
              "limitations": ["No active session does not cover its active path.",
                              "No writes, settlement, rewards, persistence, native getters or broker lifecycle tested.",
                              "Lifespan uses read_context only; total/current lifespan getters are not called.",
                              "Existing discovery caches may be reused; this is not a cold-discovery test."],
              "gui_pages": {}, "modules": {}}
    for case in CASES:
        for page in case.pages:
            report["gui_pages"].setdefault(page, []).append(case.key)
    report["gui_page_count"] = len(report["gui_pages"])
    game = None
    try:
        try:
            game = connector(game_path)
            report["connection"] = {"status": "connected"}
            report["process"] = {"pid": game.resolver.reader.pid,
                                 "creation_filetime": game.stamp[1],
                                 "identity_source": "connect_game verified path and creation time"}
            if include_paths:
                report["process"]["executable_path"] = str(game.stamp[0])
        except Exception as error:
            report["connection"] = failure(error, "connect", include_paths)
            for case in CASES:
                report["modules"][case.key] = {"status": "not_run", "reason": "Game connection failed."}
            return report
        try:
            report["installation"] = installation_summary(game, include_paths)
        except Exception as error:
            report["installation"] = failure(error, "installation_summary", include_paths)
        for case in CASES:
            progress('Read-only check: ' + case.key)
            report["modules"][case.key] = survey_case(case, game, loader=loader, include_paths=include_paths)
            progress('  ' + report["modules"][case.key]["status"])
    finally:
        if game is not None:
            try:
                game.close()
            except Exception as error:
                report["connection_cleanup"] = failure(error, "close", include_paths)
        report["seconds"] = round(time.monotonic() - started, 3)
        report["read_checks_passed"] = checks_passed(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="UTF-8 JSON report path (required).")
    parser.add_argument("--game-path", help="Optional already running WorldApart.exe selection; never launched.")
    parser.add_argument("--include-paths", action="store_true", help="Include local paths; omitted/redacted by default.")
    args = parser.parse_args(argv)
    # Fail before connecting if the destination cannot be opened. Do not leave
    # a long survey without a writable report destination.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        report = run_audit(game_path=args.game_path, include_paths=args.include_paths)
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    failed = not checks_passed(report)
    progress("Read-only survey written; GUI pages: 18. " + ("Some checks failed or are incomplete." if failed else "Reads completed.")
          + " Functional acceptance was not tested.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
