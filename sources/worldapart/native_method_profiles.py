"""Reviewed native variants selected by observed method identity, never build IDs.

Each variant is a complete method group. Callers must still prove the declaring
class, signature, parameters and code bytes before dispatching a native call.
Profile names are evidence identifiers, not game-version compatibility gates.
"""
import json
import struct
from runtime_paths import RESOURCE_ROOT
from write_guard import Refused

NATIVE_EVIDENCE = json.loads((RESOURCE_ROOT / "native_method_evidence.json").read_text(encoding="utf8"))["methods"]


def native_variants(spec):
    """Return only reviewed alternatives, retaining each caller's type contract."""
    variants = [dict(spec)]
    current = NATIVE_EVIDENCE.get(str(spec["token"]))
    if current and current["legacy_rva"] == spec["rva"]:
        selected = dict(spec, **{k: current[k] for k in ("name", "token", "rva", "prefix")})
        count = spec.get("argc", spec.get("parameters"))
        if count is not None and count != current["parameters"]:
            raise Refused("已核验原生方法的参数数量与调用约定不一致。")
        variants.append(selected)
    return variants


def selected_native_spec(resolver, method, spec):
    """Select by live name/token/RVA and prove code; no cached build selection."""
    token = resolver.i(method + 0x48, anchored=True)
    rva = resolver.q(method, anchored=True) - resolver.module
    name = resolver.reader.string(resolver.q(method + 0x18, anchored=True))
    matches = [v for v in native_variants(spec)
               if (v["name"], v["token"], v["rva"]) == (name, token, rva)]
    if len(matches) != 1:
        raise Refused("实际原生方法与已核验入口、名称或token不同。")
    chosen = matches[0]
    prefix = chosen["prefix"]
    if resolver.anchor(resolver.module + rva, len(prefix) // 2).hex() != prefix:
        raise Refused("实际原生方法入口代码与已核验内容不同。")
    return chosen


def resolve_reviewed_method(resolver, klass, spec):
    """Resolve a reviewed role and verify the declaring class and ABI.

    Returns (MethodInfo integer, selected spec). Parameter kind checks remain
    independently enforced by the shared JS before invoking the method.
    """
    names = {v["name"] for v in native_variants(spec)}
    table = resolver.q(klass + 0x98, anchored=True)
    count = struct.unpack("<H", resolver.anchor(klass + 0x120, 2))[0]
    if not 1 <= count <= 1024:
        raise Refused("原生方法表数量异常。")
    candidates = []
    for i in range(count):
        method = resolver.q(table + i * 8, anchored=True)
        if resolver.reader.string(resolver.q(method + 0x18)) not in names:
            continue
        # Renumbered compiler callbacks can retain the old name for another
        # role. Ignore those names only when the token/RVA is not this role.
        token, rva = resolver.i(method + 0x48), resolver.q(method) - resolver.module
        if not any((token, rva) == (v["token"], v["rva"]) for v in native_variants(spec)):
            continue
        chosen = selected_native_spec(resolver, method, spec)
        flags = struct.unpack("<H", resolver.anchor(method + 0x4C, 2))[0]
        returns = resolver.q(method + 0x28, anchored=True)
        argc = chosen.get("argc", chosen.get("parameters"))
        kind = chosen.get("returns", chosen.get("return_kind"))
        if (resolver.q(method + 0x20, anchored=True) != klass
                or bool(flags & 0x10) != bool(chosen.get("static", False))
                or resolver.anchor(method + 0x52, 1) != bytes([argc])
                or resolver.anchor(returns + 10, 1) != bytes([kind])
                or resolver.anchor(returns + 11, 1)[0] & 0x7F):
            raise Refused("原生方法所属类型或调用签名不匹配。")
        candidates.append((method, chosen))
    if len(candidates) != 1:
        raise Refused("已核验原生方法不存在或不唯一。")
    return candidates[0]


def request_method_spec(spec, selected=None):
    """Accept a descriptor selection only if it belongs to the local whitelist."""
    if selected is None:
        return spec
    if not isinstance(selected, dict):
        raise Refused("原生请求方法证据格式不正确。")
    keys = ("name", "token", "rva")
    matches = [v for v in native_variants(spec)
               if all(selected.get(k) == v.get(k) for k in keys)]
    if len(matches) != 1:
        raise Refused("原生请求方法不在本地已核验白名单。")
    return matches[0]


def method_profiles(specs):
    return {"legacy": specs["methods"], **specs.get("method_profiles", {})}


def reviewed_method_profile(specs, profile="legacy"):
    profiles = method_profiles(specs)
    if type(profile) is not str or profile not in profiles:
        raise Refused("原生方法证据配置未知，未调用游戏方法。")
    return profiles[profile]


def select_method_profile(specs, observed):
    """Match the entire name/token/RVA group, rejecting mixed or unknown sets."""
    matches = []
    for profile, methods in method_profiles(specs).items():
        if set(observed) == set(methods) and all(
                observed[key] == (spec["name"], spec["token"], spec["rva"])
                for key, spec in methods.items()):
            matches.append(profile)
    if len(matches) != 1:
        raise Refused("实际原生方法组与已核验签名或入口不同，未调用游戏方法。")
    return matches[0]
