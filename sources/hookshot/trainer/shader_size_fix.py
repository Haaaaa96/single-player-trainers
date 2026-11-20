"""Local Vulkan fix for v2.3.1's valid >1 MiB Ampere compute program.

Apply to retained Builder tools before rebuilding its Vulkan backend, then
rebuild the integrated trainer. This does not patch game data or WebGPU.
The 16 MiB ceiling already bounds validated NVN packages in vk_shader.cpp.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

AMPERE = "gpu/vk/eden/shader_recompiler/frontend/ampere/"
LIMITS = """// Local Hookshot v2.3.1 repair: match the validated NVN package size ceiling.
#pragma once
#include "common/common_types.h"
namespace Shader::Ampere {
inline constexpr u32 MaximumNativeProgramBytes = 16u << 20;
inline constexpr u32 MaximumNativeInstructions = MaximumNativeProgramBytes / 16;
} // namespace Shader::Ampere
"""
EDITS = {
    AMPERE + "program_capture.h": [
        ("    Result Observe(const Instruction& instruction, u32 index) {",
         "    // Callers with a validated package pass its actual complete-instruction count.\n"
         "    // Unknown-length callers retain the original conservative 1 MiB ceiling.\n"
         "    explicit ProgramCaptureState(u32 instruction_count = MaximumInstructions)\n"
         "        : instruction_limit{std::min(instruction_count, MaximumNativeInstructions)} {}\n\n"
         "    Result Observe(const Instruction& instruction, u32 index) {\n"
         "        if (index >= instruction_limit) return Result::InvalidTarget;"),
        ("target >= MaximumInstructions * 16", "target / 16 >= instruction_limit"),
        ("private:\n", "private:\n    const u32 instruction_limit;\n"),
    ],
    AMPERE + "lower_to_maxwell.h": [
        ('#include "common/common_types.h"',
         '#include "common/common_types.h"\n#include "shader_recompiler/frontend/ampere/native_program_limits.h"'),
        ('code.size() > 65536', 'code.size() > MaximumNativeInstructions'),
    ],
    AMPERE + "program_address_map.h": [
        ('#include "common/common_types.h"',
         '#include "common/common_types.h"\n#include "shader_recompiler/frontend/ampere/native_program_limits.h"'),
        ('count > 65536', 'count > MaximumNativeInstructions'),
    ],
    "gpu/vk/vk_shader.cpp": [
        ("    Shader::Ampere::ProgramCaptureState capture;",
         "    if (len < hdr || len > area.size()) {\n"
         '        c.why = "native instruction span exceeds its validated package";\n'
         "        return c;\n"
         "    }\n"
         "    Shader::Ampere::ProgramCaptureState capture{\n"
         "        static_cast<uint32_t>((len - hdr) / sizeof(Instruction))};"),
    ],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply(root, record, check=False):
    changes = []
    # Validate every anchor before any mutation; idempotent on this exact patch.
    for name, edits in EDITS.items():
        path = root / name
        before = path.read_bytes()
        text = before.decode("utf-8").replace("\r\n", "\n")
        for old, new in edits:
            if text.count(new) == 1:
                continue
            if text.count(old) != 1:
                raise ValueError(f"Unexpected upstream source: {name}: {old[:70]}")
            text = text.replace(old, new, 1)
        newline = "\r\n" if b"\r\n" in before else "\n"
        after = text.replace("\n", newline).encode("utf-8")
        changes.append((name, before, after))
    name = AMPERE + "native_program_limits.h"
    path = root / name
    before = path.read_bytes() if path.exists() else b""
    after = LIMITS.encode("utf-8")
    if before and before != after:
        raise ValueError("A different native_program_limits.h already exists")
    changes.append((name, before, after))
    if check:
        if any(before != after for _, before, after in changes):
            raise ValueError("The retained Vulkan sources have not been patched")
        return
    record.mkdir(parents=True, exist_ok=True)
    if (record / "source-patch.json").exists():
        if any(before != after for _, before, after in changes):
            raise ValueError("Refusing to overwrite an existing patch record")
        return
    manifest, diff = [], []
    for name, before, after in changes:
        backup = record / "before-source" / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before)
        manifest.append({"path": name, "before_sha256": sha(before), "after_sha256": sha(after)})
        diff.extend(difflib.unified_diff(before.decode("utf-8").splitlines(True),
                                      after.decode("utf-8").splitlines(True),
                                      "a/" + name, "b/" + name))
    (record / "source.patch").write_text("".join(diff), encoding="utf-8", newline="\n")
    for name, _, after in changes:
        (root / name).write_bytes(after)
        assert (root / name).read_bytes() == after
    (record / "source-patch.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    apply(args.tools, args.record, args.check)
    print("Vulkan native shader size patch verified" if args.check else "Vulkan native shader size patch applied")
