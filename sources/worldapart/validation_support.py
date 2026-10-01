"""Readonly by default. --validate-steps explicitly runs three +/-1 roundtrips.

Never takes restored values from an earlier file or hardcoded character state.
Observed invariants cover the full resolver snapshot (except capture time),
all reviewed bag-object bytes, learned node IDs, all exposed targets, and every
save file's size/hash. They do not claim to cover every field in the game.
"""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

TRAINER = Path(__file__).resolve().parent
HERE = TRAINER / "logs" / "validation"
sys.path.insert(0, str(TRAINER))
from game_adapter import GameAdapter
from write_guard import Refused

SAVE_ROOT = Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/Nuverse/WorldApart/StorageV1"


def raw_state(raw):
    return {key: value for key, value in raw.items() if key != "captured_unix"}


def save_hashes():
    if not SAVE_ROOT.is_dir():
        raise RuntimeError("Expected WorldApart save directory is missing")
    entries = []
    for path in sorted(SAVE_ROOT.rglob("*")):
        if not path.is_file():
            continue
        before = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("Save file changed during hashing: " + str(path))
        entries.append({"path": path.relative_to(SAVE_ROOT).as_posix(),
                        "size": after.st_size, "sha256": digest})
    if not entries:
        raise RuntimeError("No save files found; validation requires an existing save")
    return entries


def learned_nodes(rr, raw):
    tc = rr.object_class(raw["talent"], "Game.Model.Player.Components.TalentPathModel")
    ref = raw["talent"] + rr.field(tc, "<LearnedNodeIds>k__BackingField", 0x15)
    nodes = rr.q(ref)
    if not nodes:
        return {"object": 0, "values": []}
    c = rr.info(rr.q(nodes), "HashSet`1", "System.Collections.Generic")
    count = rr.i(nodes + rr.field(c, "_count", 8))
    last = rr.i(nodes + rr.field(c, "_lastIndex", 8))
    version_address = nodes + rr.field(c, "_version", 8)
    version = rr.i(version_address)
    slots_address = nodes + rr.field(c, "_slots", 0x1d)
    slots = rr.q(slots_address)
    if not slots:
        if count or last:
            raise RuntimeError("Learned-node HashSet has missing storage")
        data = b""
        values = []
    else:
        ac = rr.info(rr.q(slots), "Slot[]", "")
        sc = rr.info(rr.q(int(ac["klass"], 16) + 0x40), "Slot", "")
        if ([rr.field(sc, name, kind) - 16 for name, kind in
             (("hashCode", 8), ("next", 8), ("value", 0x11))] != [0, 4, 8] or
                sc["instance_size"] != 28):
            raise RuntimeError("Learned-node storage layout changed")
        if not 0 <= count <= last <= rr.q(slots + 24) <= 4096:
            raise RuntimeError("Learned-node storage bounds changed")
        data = rr.exact(slots + 32, last * 12)
        values = [value for h, _, value in struct.iter_unpack("<iii", data) if h >= 0]
        if len(values) != len(set(values)) or len(values) != count:
            raise RuntimeError("Learned-node set identity mismatch")
        if rr.exact(slots + 32, len(data)) != data:
            raise RuntimeError("Learned-node slots changed during capture")
    if rr.q(ref) != nodes or rr.q(slots_address) != slots or rr.i(version_address) != version:
        raise RuntimeError("Learned-node set changed during capture")
    return {"object": nodes, "slots": slots, "version": version, "slot_bytes": data.hex(),
            "values": sorted(values)}


def capture(adapter):
    state = adapter.snapshot()
    rr = adapter.resolver
    # Ancillary read helpers may add temporary anchors to rr.anchors. Preserve
    # the resolver's actual output before those helpers run.
    raw = deepcopy(rr.resolve())
    if (state["spirit"].value, state["path"].value) != (raw["spirit"], raw["path"]):
        raise RuntimeError("Talent balance changed during capture")
    rows = {**state["items"], **state["currencies"]}
    raw_items = {item["uid"]: item for item in raw["items"]}
    for row in rows.values():
        target = row["target"]
        uid = int(target.key.split(":", 1)[1])
        if (target.address, target.value) != (raw_items[uid]["count_address"], raw_items[uid]["count"]):
            raise RuntimeError("Bag count changed between adapter and raw capture")
    objects = {}
    for item in raw["items"]:
        c = rr.verify_class(item["klass"], item["class_name"])
        objects[str(item["uid"])] = {"object": item["object"], "size": c["instance_size"],
                                     "bytes": rr.exact(item["object"], c["instance_size"]).hex()}
    nodes = learned_nodes(rr, raw)
    saves = save_hashes()
    if raw_state(rr.resolve()) != raw_state(raw):
        raise RuntimeError("Observed game state changed during capture")
    for obj in objects.values():
        if rr.exact(obj["object"], obj["size"]).hex() != obj["bytes"]:
            raise RuntimeError("Bag object fields changed during capture")
    targets = {"spirit": asdict(state["spirit"]), "path": asdict(state["path"]),
               **{key: asdict(row["target"]) for key, row in rows.items()}}
    return state, {"raw": raw_state(raw), "bag_object_bytes": objects, "learned_nodes": nodes,
                   "targets": targets, "save_files": saves}


def choose(state, option, predicate, label):
    rows = {**state["items"], **state["currencies"]}
    candidates = sorted(key for key, row in rows.items() if predicate(row))
    if option:
        if option not in candidates:
            raise Refused(label + " key does not identify a current approved target")
        key = option
    else:
        if not candidates:
            raise Refused("No currently editable " + label + " target")
        key = candidates[0]
    shown = rows[key]["target"]
    if shown.value >= shown.maximum:
        raise Refused(label + " is already at its cap; this test only adds 1 then restores")
    return key


def select_targets(state, args):
    return [
        choose(state, args.pill_key, lambda row: row["class_name"] == "Game.Model.Components.PillBagItem"
               and row["category"] == "item" and row["target"].maximum == 999, "PillBagItem"),
        choose(state, args.material_key, lambda row: row["class_name"] == "Game.Model.Components.BagItem"
               and row["category"] == "item" and row["target"].maximum == 999, "ordinary 999 material"),
        choose(state, args.currency_key, lambda row: row["category"] == "currency"
               and row["item_id"] == 50000, "Spirit Stone"),
    ]


def expected_after(before, key, value):
    expected = deepcopy(before)
    target = expected["targets"][key]
    uid = int(key.split(":", 1)[1])
    target["value"] = value
    item = next(item for item in expected["raw"]["items"] if item["uid"] == uid)
    item["count"] = value
    obj = expected["bag_object_bytes"][str(uid)]
    data = bytearray.fromhex(obj["bytes"])
    struct.pack_into("<i", data, target["address"] - obj["object"], value)
    obj["bytes"] = data.hex()
    return expected


def compare(actual, expected, stage):
    mismatches = [key for key in expected if actual.get(key) != expected[key]]
    if mismatches:
        raise RuntimeError(stage + ": unexpected changes in " + ", ".join(mismatches))


def persist(path, result):
    # The caller creates an exclusive output file before any attempted write.
    with path.open("w", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-steps", action="store_true", help="Explicitly permit exactly three +1/restore roundtrips")
    parser.add_argument("--pill-key")
    parser.add_argument("--material-key")
    parser.add_argument("--currency-key")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.validate_steps and any((args.pill_key, args.material_key, args.currency_key)):
        parser.error("Target selection is only valid with --validate-steps")
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    output = args.output or HERE / ("extended-live-" + stamp + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never replace an earlier baseline and never accept it as a restore source.
    with output.open("x", encoding="utf8") as stream:
        stream.write("{}\n")
    result = {"mode": "validate-steps" if args.validate_steps else "read-only",
              "started": datetime.now().astimezone().isoformat(), "steps": [], "status": "starting",
              "save_root": str(SAVE_ROOT), "validation_scope": __doc__}
    adapter = None
    try:
        adapter = GameAdapter()
        state, baseline = capture(adapter)
        result["baseline"] = baseline
        result["status"] = "baseline_captured"
        persist(output, result)
        if args.validate_steps:
            selected = select_targets(state, args)
            result["selected"] = selected
            persist(output, result)
            for key in selected:
                _, before = capture(adapter)
                compare(before, baseline, "before " + key)
                shown = adapter.resolve(key)
                if asdict(shown) != before["targets"][key]:
                    raise RuntimeError("Selected target changed before testing")
                for new_value, label in ((shown.value + 1, "increment"), (shown.value, "restore")):
                    current = adapter.resolve(key)
                    expected_current = shown.value if label == "increment" else shown.value + 1
                    if current.value != expected_current or current.identity != shown.identity:
                        raise RuntimeError("Target changed before " + label)
                    step = {"key": key, "operation": label, "before": current.value,
                            "after": new_value, "status": "planned"}
                    result["steps"].append(step)
                    persist(output, result)
                    changed = adapter.set_value(current, new_value)
                    observed = adapter.resolve(key)
                    if observed != changed or observed.identity != shown.identity or observed.value != new_value:
                        raise RuntimeError("Target reread failed after " + label)
                    _, after = capture(adapter)
                    result["last_observation"] = after
                    compare(after, expected_after(baseline, key, new_value), "after " + label + " " + key)
                    step["status"] = "verified"
                    persist(output, result)
        _, final = capture(adapter)
        compare(final, baseline, "final baseline comparison")
        result["final"] = final
        result["status"] = "verified"
        result["completed"] = datetime.now().astimezone().isoformat()
        persist(output, result)
        print(json.dumps({"output": str(output), "mode": result["mode"], "status": result["status"],
                          "verified_steps": len(result["steps"]), "pid": baseline["raw"]["pid"],
                          "spirit": baseline["raw"]["spirit"], "path": baseline["raw"]["path"],
                          "all_observed_fields_and_save_hashes_restored": True}, ensure_ascii=True))
    except Exception as exc:
        result["status"] = "stopped_on_error"
        result["error"] = str(exc)
        # Read only after a failure. Do not retry writes or restore a stale value.
        if adapter is not None and adapter.resolver is not None:
            try:
                result["error_raw_observation"] = adapter.resolver.resolve()
                result["error_save_hashes"] = save_hashes()
            except Exception as observation_error:
                result["error_observation_failure"] = str(observation_error)
        persist(output, result)
        print(json.dumps({"output": str(output), "status": result["status"], "error": str(exc),
                          "action": "Inspect saved step log and current game value; no further writes were attempted."}))
        raise
    finally:
        if adapter is not None:
            adapter.close()


if __name__ == "__main__":
    main()
