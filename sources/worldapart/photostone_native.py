"""Use the existing shared native session and durable no-retry request journal."""
import json
import time

from dual_cultivation_native import MiniGameOnce
from photostone_adapter import SPECS
from native_method_profiles import request_method_spec
from write_guard import Refused


class PhotostoneNative(MiniGameOnce):
    def __init__(self, game, adapter):
        super().__init__(game, adapter, operation="photostone",
                         method_spec=SPECS["methods"]["set"],
                         journal_name="photostone-once.json")

    def _request(self, state, pid, token):
        data = dict(state["native"])
        anchors = data.pop("anchors", None)
        mode = data.get("mode")
        if mode not in ("next", "force") or not isinstance(anchors, list) or not anchors:
            raise Refused("留影请求缺少操作模式或身份锚。")
        required = {"round_key","npc_id","sub_id","world","player","npc","logic_manager",
                    "logic_class","runtime","usage","usage_state","stats","active_special","stats_before",
                    "entry","entry_class","entry_config","date","date_address","methods",
                    "owner_links","post_stable_anchors","npc_dictionary","static_ids",
                    "quest_owners","statistics","force_confirmed"}
        if not required.issubset(data) or set(data["methods"]) != set(SPECS["methods"]):
            raise Refused("留影请求缺少完整的世界、角色、配置与方法证据。")
        if (not data["owner_links"] or not data["post_stable_anchors"]
                or data["active_special"] != 0 or data["entry_config"].get("game_type") != 1
                or mode == "force" and data["force_confirmed"] is not True
                or mode == "next" and data["force_confirmed"] is not False):
            raise Refused("留影请求的当前入口或确认状态不允许派发。")
        if not isinstance(data["owner_links"],list) or len(data["owner_links"]) > 20000:
            raise Refused("留影请求的角色归属链超过审核范围。")
        key = "force" if mode == "force" else "set"
        method = request_method_spec(SPECS["methods"][key], data.get("method_specs", {}).get(key))
        for proof in (anchors, data["post_stable_anchors"]):
            if (not isinstance(proof,list) or not 1 <= len(proof) <= 20000
                    or any(type(a.get("size")) is not int or not 1 <= a["size"] <= 4096
                           or not isinstance(a.get("expected_hex"),str)
                           or len(a["expected_hex"]) != a["size"]*2 for a in proof)):
                raise Refused("留影请求的身份锚超过已审核传输范围，未连接原生后台。")
        request = dict(operation="photostone_force_replay" if mode == "force" else "photostone_activate",
                    token=token,pid=pid,method_info=data["methods"][key],method_token=method["token"],
                    method_rva=method["rva"],parameter_count=method["argc"],photostone=data,
                    anchors=anchors,deadline=int(time.time()*1000)+10000)
        # Reserve room for the existing broker's id/command/payload framing.
        if len(json.dumps(request,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf8")) > 8*1024*1024-4096:
            raise Refused("留影请求过大，未连接原生后台；请保留现场供检查。")
        return request
