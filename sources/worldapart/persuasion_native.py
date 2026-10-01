"""Persuasion shares the existing per-round broker transport; no private attach."""
import json
from dual_cultivation_native import MiniGameOnce
from native_broker import MAX_MESSAGE
from write_guard import Refused


class PersuasionOnce(MiniGameOnce):
    def _request(self, state, pid, token):
        request = super()._request(state, pid, token)
        request["persuasion"] = request.pop("minigame")
        if (len(request["anchors"]) > 20000
                or any(type(a.get("size")) is not int or not 1 <= a["size"] <= 4096 for a in request["anchors"])
                or len(json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf8")) > MAX_MESSAGE-4096):
            raise Refused("当前说服身份证明超出安全传输范围，未调用游戏。")
        return request
