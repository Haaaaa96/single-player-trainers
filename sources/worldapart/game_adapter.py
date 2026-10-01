"""Runtime-validated adapter; all live targets come from the active save chain."""
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from runtime_paths import LOG_ROOT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "game_runtime"))
from resolver import Resolver
from discovery import connect_discover
from config_probe import read_config
import probe
from native_write import WriteOnce, process_identity
from write_guard import (MAX_CHANGE, SPIRIT_STONE_MAX_CHANGE, PreconditionChanged,
                         Refused, Target, set_value as guarded_set_value)
from game_install import validate_installation, same_executable
from connection_diagnostics import ConnectionDiagnosticError
from item_categories import category_name

# Conservative trainer limits, not claims about the game's natural point caps.
POINT_EDIT_MAXIMUM = 1_000
CURRENCY_EDIT_MAXIMUM = 1_000_000
# Verified TbItem entry: id 50000, itemType 5, maxCntPerGrid 999999999.
# A different item with the same localized name is a mechanism, not currency.
SPIRIT_STONE_ITEM_ID = 50000
SPIRIT_STONE_EDIT_MAXIMUM = 999_999_999
def game_pids():
    class PROCESSENTRY32W(C.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", C.c_size_t), ("th32ModuleID", W.DWORD),
                    ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                    ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    kernel.Process32NextW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = C.sizeof(entry)
        ok = kernel.Process32FirstW(handle, C.byref(entry))
        result = []
        while ok:
            if entry.szExeFile.casefold() == "worldapart.exe":
                result.append(entry.th32ProcessID)
            ok = kernel.Process32NextW(handle, C.byref(entry))
        return result
    finally:
        kernel.CloseHandle(handle)


class GameAdapter:
    def __init__(self, game_path=None):
        self.resolver = None
        self.blocked = False
        selected = validate_installation(game_path).executable_path if game_path is not None else None
        candidates = []
        failures = []
        for pid in game_pids():
            reader = None
            try:
                actual_path = probe.process_path(pid)
                if selected is not None and not same_executable(actual_path, selected):
                    continue
                # Reader checks actual process/file identity; differing release
                # hashes are advisory. Runtime layout checks remain mandatory.
                reader = probe.Reader(pid, expected_path=actual_path)
                probe.verified_mappings(reader)
                candidates.append((pid, reader.installation, process_identity(reader.h)))
            except (OSError, Refused) as error:
                failures.append(str(error))
            finally:
                if reader:
                    reader.close()
        if len(candidates) != 1:
            if len(candidates) > 1:
                raise Refused("检测到多个可连接的游戏主进程，请选择对应 WorldApart.exe；同一路径运行多份时请只保留一份。")
            if failures:
                raise Refused("未连接游戏：" + failures[0])
            if selected is not None:
                raise Refused("所选 WorldApart.exe 尚未运行，或运行的是其他安装位置。请从所选位置启动游戏并进入存档。")
            raise Refused("未找到正在运行的 WorldApart.exe。请启动游戏并进入存档，也可选择游戏程序后重试。")
        pid, installation, selected_stamp = candidates[0]
        self.game_path = self.executable_path = installation.executable_path
        self.install_directory = installation.install_directory
        try:
            try:
                self.resolver = Resolver(pid, expected_path=self.executable_path)
                if process_identity(self.resolver.reader.h) != selected_stamp:
                    raise PreconditionChanged("连接期间游戏已重启，请重新连接。")
                self.resolver.resolve()
            except PreconditionChanged:
                raise
            except Exception as initial_error:
                self.close()
                # Discovery uses the same selected installation, never a global
                # Steam path. A restarted/replaced process is checked again.
                try:
                    connect_discover(pid, expected_path=self.executable_path)
                except ConnectionDiagnosticError as error:
                    # Keep the failing phase without copying local paths from
                    # FileNotFoundError, or dumping a player's data to a log.
                    error.diagnostic['previous_phase'] = {
                        'stage': 'cached_connection', 'error_type': type(initial_error).__name__}
                    raise
                self.resolver = Resolver(pid, expected_path=self.executable_path)
            self.stamp = process_identity(self.resolver.reader.h)
            if self.stamp != selected_stamp:
                raise Refused("连接期间游戏已重启，请重新连接。")
            self.snapshot()
        except Exception:
            self.close()
            raise

    def close(self):
        if self.resolver:
            self.resolver.close()
            self.resolver = None

    def snapshot(self):
        if not self.resolver or self.blocked:
            raise Refused("当前连接已停止，请核对游戏后重新连接。")
        if process_identity(self.resolver.reader.h) != self.stamp:
            raise Refused("游戏进程已变化。")
        raw = self.resolver.resolve()
        if not raw["anchor_verified"]:
            raise Refused("无法确认当前角色。")
        config = read_config(self.resolver.reader.pid, [item["item_id"] for item in raw["items"]])
        if config["process_creation_filetime"] != self.stamp[1]:
            raise Refused("读取配置时游戏进程已变化。")
        # Configuration is read from the game, including names and actual stack limits.
        definitions = {item["id"]: item for item in config["items"]}
        chain = (self.stamp, raw["manager"], raw["store"], raw["world"],
                 raw["player"], raw["bag"], raw["talent"])
        # Pin the anchor byte sequence so a list replacement/reorder also invalidates a shown target.
        anchors = tuple((a["address"], a["expected_hex"]) for a in raw["anchors"])
        spirit = Target("spirit", raw["spirit_address"], raw["spirit"],
                        chain + (anchors,), 0, POINT_EDIT_MAXIMUM)
        path = Target("path", raw["path_address"], raw["path"],
                      chain + (anchors,), 0, POINT_EDIT_MAXIMUM)
        items = {}
        currencies = {}
        diagnostics = list(raw.get("diagnostics", []))
        unresolved_inventory = any(entry.get("reason") != "null_entry"
                                   for entry in raw.get("diagnostics", []))
        for item in raw["items"]:
            definition = definitions[item["item_id"]]
            limit = definition["max_count_per_grid"]
            currency = definition.get("is_currency", False)
            spirit_stone = (currency is True and definition.get("item_type_id") == 5
                            and item["item_id"] == SPIRIT_STONE_ITEM_ID)
            same_id = sum(other["item_id"] == item["item_id"] for other in raw["items"])
            # Unsupported or duplicate-UID entries were omitted by the reader;
            # their IDs are not known, so they may conceal another stone stack.
            if spirit_stone and unresolved_inventory:
                diagnostics.append({"slot": item.get("slot"), "item_id": item["item_id"],
                                    "class_name": item.get("class_name"),
                                    "reason": "currency_balance_unverified",
                                    "message": "背包含无法识别的条目，不能核对灵石总余额；暂不支持灵石余额修改。"})
                continue
            # The reviewed stone balance is one stack. Editing separate stacks
            # could bypass the total-balance limit and cannot be offered here.
            if spirit_stone and same_id > 1:
                diagnostics.append({"slot": item.get("slot"), "item_id": item["item_id"],
                                    "class_name": item.get("class_name"),
                                    "reason": "currency_multiple_stacks",
                                    "message": "灵石存在多个堆叠，暂不支持余额修改；其它条目仍可读取。"})
                continue
            # Both exact BagItem and reviewed PillBagItem use the same Count.
            # Unknown/specialized types are still exposed read-only by resolver.
            if item.get("count_editable") is not True:
                diagnostics.append({"slot": item.get("slot"), "item_id": item["item_id"],
                                    "class_name": item.get("class_name"),
                                    "reason": "quantity_not_reviewed",
                                    "message": "此物品的类型或装备状态暂不支持数量修改。"})
                continue
            minimum = 0 if currency else 1
            # Nullable autoUse is allowed for existing stacks: no acquisition
            # effect is executed by changing their Count. Explicit auto-use
            # entries remain excluded, as do hidden virtual/quest items.
            if currency and 1 < limit <= 2_147_483_647 and item["count"] > limit:
                diagnostics.append({"slot": item.get("slot"), "item_id": item["item_id"],
                                    "class_name": item.get("class_name"),
                                    "reason": "currency_balance_above_limit",
                                    "count": item["count"], "stack_limit": limit,
                                    "message": f"货币当前数量 {item['count']} 超过游戏单格上限 {limit}，该条目暂不支持修改。"})
                continue
            if ((not currency and (definition["hide_in_bag"] or
                                   definition["auto_use"] is True or not definition["can_discard"])) or
                    not 1 < limit <= 2_147_483_647 or not minimum <= item["count"] <= limit):
                continue
            currency_maximum = SPIRIT_STONE_EDIT_MAXIMUM if spirit_stone else CURRENCY_EDIT_MAXIMUM
            maximum = min(limit, currency_maximum) if currency else limit
            max_change = SPIRIT_STONE_MAX_CHANGE if spirit_stone else MAX_CHANGE
            key = ("currency:" if currency else "item:") + str(item["uid"])
            identity = chain + (item["object"], item["klass"], item["item_id"], item["uid"],
                                config["tables_current"], definition["config_object"], limit,
                                definition.get("item_type_id"), currency, anchors)
            target = Target(key, item["count_address"], item["count"], identity,
                            minimum, maximum, max_change)
            name = (definition["names"].get("zh-Hans") or definition["names"].get("en-US")
                    or f"物品 {item['item_id']}")
            if same_id > 1:
                name += f" · 堆叠 {item['uid']}"
            entry = {"name": name, "target": target, "item_id": item["item_id"],
                     "item_type_id": definition.get("item_type_id"),
                     "type_name": category_name(definition),
                     "class_name": item.get("class_name"), "stack_limit": limit,
                     "limit_source": "游戏单格上限与修改器余额上限" if currency else "游戏单格上限",
                     "category": "currency" if currency else "item"}
            (currencies if currency else items)[key] = entry
        return {"spirit": spirit, "path": path, "items": items,
                "currencies": currencies, "diagnostics": diagnostics}

    def resolve(self, key):
        state = self.snapshot()
        if key in ("spirit", "path"):
            return state[key]
        if key in state["currencies"]:
            return state["currencies"][key]["target"]
        if key not in state["items"]:
            raise Refused("所选物品已离开当前背包，未写入。")
        return state["items"][key]["target"]

    def record(self, event):
        folder = LOG_ROOT
        folder.mkdir(parents=True, exist_ok=True)
        payload = {"time": datetime.now().astimezone().isoformat(), **event}
        with (folder / "changes.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())

    def change(self, shown, delta):
        """Retain the old +/-1 API for controlled regression checks."""
        if type(delta) is not int or delta not in (-1, 1):
            raise Refused("兼容接口仅支持加减 1；指定目标数量请使用手动输入。")
        return self.set_value(shown, shown.value + delta)

    def set_value(self, shown, new_value, *, preconditions=()):
        """Set one validated target; no retries after any uncertain operation."""
        if self.blocked or not self.resolver:
            raise Refused("当前连接已停止。")
        try:
            extra = {"preconditions": preconditions} if preconditions else {}
            memory = WriteOnce(self.resolver.reader, self.stamp, shown, new_value=new_value, **extra)
            return guarded_set_value(memory, self.resolve, shown, new_value, self.record)
        except PreconditionChanged:
            # The OS write has not been called. Fresh context can be checked
            # on a later explicit action without invalidating read-only state.
            raise
        except Exception:
            self.blocked = True
            raise
