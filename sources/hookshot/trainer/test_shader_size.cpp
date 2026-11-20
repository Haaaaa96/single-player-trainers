// Bounded, offline regression against the real Ampere capture/lowering headers.
// Requires C++20. No game, GPU, process attachment, or shader cache access.
// Example (PowerShell; $tools is HookshotBuilder/tools):
// & "$tools/llvm-mingw/bin/clang++.exe" --target=x86_64-w64-mingw32 -static -std=c++20 -O1 `
//   "-I$tools/gpu/vk/eden" "-I$tools/gpu/vk/compat" test_shader_size.cpp -o test_shader_size.exe
// Optional argument: failed.code.bin retained from the 2026-11-16 compute shader.
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <span>
#include <string_view>
#include <vector>
#include "shader_recompiler/frontend/ampere/program_capture.h"
#include "shader_recompiler/frontend/ampere/program_address_map.h"
#include "shader_recompiler/frontend/ampere/native_program_limits.h"

using namespace Shader::Ampere;
using CaptureResult = ProgramCaptureState::Result;
static unsigned checks;

static void Check(bool value, const char* expression, int line) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "FAIL line %d: %s\n", line, expression);
        std::exit(1);
    }
}
#define CHECK(value) Check(static_cast<bool>(value), #value, __LINE__)

// Independently specified byte addresses and literal ISA words keep expected
// results separate from production limits, decoding, and address-map writers.
constexpr u32 OldCount = 65536;
constexpr u32 AbsoluteCount = 1048576;
constexpr Instruction Exit{{0x0000794d, 0, 0x03800000, 0}};
constexpr Instruction Nop{{0x00007918, 0, 0, 0}};
constexpr Instruction RealBranch{{0x00009947, 0x000c4360, 0x03800000, 0x000fea00}};

static Instruction Branch(s64 relative) {
    const u64 encoded = static_cast<u64>(relative) & ((u64{1} << 50) - 1);
    return {{0x00007947, static_cast<u32>(encoded),
             0x03800000U | static_cast<u32>(encoded >> 32), 0}};
}

static void TestCapture() {
    CHECK(MaximumNativeProgramBytes == 16777216U);
    CHECK(MaximumNativeInstructions == AbsoluteCount);
    CHECK(ProgramCaptureState::MaximumInstructions == OldCount);
    // 16404 * 16 + 16 + 0xc4360 == 1066160: in 66664 instructions,
    // outside the historical default 65536 instructions.
    CHECK(ProgramCaptureState{}.Observe(RealBranch, 16404) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(RealBranch, 16404) == CaptureResult::Continue);
    CHECK(ProgramCaptureState{66635}.Observe(RealBranch, 16404) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66636}.Observe(RealBranch, 16404) == CaptureResult::Continue);
    CHECK(ProgramCaptureState{OldCount}.Observe(Exit, 65535) == CaptureResult::Complete);
    CHECK(ProgramCaptureState{}.Observe(Exit, 65536) == CaptureResult::InvalidTarget);

    for (u32 count : {65535U, 65536U, 65537U, 66664U}) {
        CHECK(ProgramCaptureState{count}.Observe(Exit, count - 1) == CaptureResult::Complete);
        CHECK(ProgramCaptureState{count}.Observe(Exit, count) == CaptureResult::InvalidTarget);
        CHECK(ProgramCaptureState{count}.Observe(Branch(s64{count} * 16 - 32), 0) == CaptureResult::Continue);
        CHECK(ProgramCaptureState{count}.Observe(Branch(s64{count} * 16 - 16), 0) == CaptureResult::InvalidTarget);
    }
    CHECK(ProgramCaptureState{0}.Observe(Exit, 0) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{1}.Observe(Nop, 1) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(Branch(-32), 0) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(Branch(1), 0) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(Branch(s64{1} << 36), 0) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(Branch(-(s64{1} << 36)), 0) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{66664}.Observe(Branch(-16), 0) == CaptureResult::Continue);
    CHECK(ProgramCaptureState{AbsoluteCount}.Observe(Branch(16777184), 0) == CaptureResult::Continue);
    CHECK(ProgramCaptureState{AbsoluteCount}.Observe(Branch(16777200), 0) == CaptureResult::InvalidTarget);
    // An untrusted count cannot expand the absolute 16 MiB cap.
    const u32 too_large = std::numeric_limits<u32>::max();
    CHECK(ProgramCaptureState{too_large}.Observe(Exit, AbsoluteCount - 1) == CaptureResult::Complete);
    CHECK(ProgramCaptureState{too_large}.Observe(Exit, AbsoluteCount) == CaptureResult::InvalidTarget);
    CHECK(ProgramCaptureState{too_large}.Observe(Branch(16777200), 0) == CaptureResult::InvalidTarget);
    std::puts("capture: actual length, old default, signed 50-bit targets and cap passed");
}

static void TestLowering() {
    // A valid early finish means this checks the input-size guard without
    // lowering a million instructions. Every span still names real storage.
    std::vector<Instruction> code(65537, Nop);
    code[0] = Exit;
    auto lowered = LowerToMaxwell(code);
    CHECK(lowered);
    CHECK(lowered.source_size == 16);
    CHECK(lowered.instructions.size() == 1);
    CHECK(lowered.source_instruction_offsets.size() == 1);
    auto empty = LowerToMaxwell(std::span<const Instruction>{});
    CHECK(!empty);
    CHECK(empty.error == "invalid native program size");
    // One bounded 16 MiB allocation covers the exact cap and cap+1. Reusing
    // valid storage avoids undefined behavior from a fabricated oversized span.
    code.resize(AbsoluteCount + 1, Nop);
    auto at_limit = LowerToMaxwell(std::span<const Instruction>(code.data(), AbsoluteCount));
    CHECK(at_limit);
    CHECK(at_limit.source_size == 16);
    auto too_large = LowerToMaxwell(code);
    CHECK(!too_large);
    CHECK(too_large.error == "invalid native program size");
    CHECK(too_large.instructions.empty());
    CHECK(too_large.source_instruction_offsets.empty());
    std::puts("lowering: old-limit+1, exact 16 MiB, empty and over-cap passed");
}

static std::vector<u64> Map(u32 count) {
    // 16 words of code, then count native-address entries, count and magic.
    // 0x50 is a valid first instruction address; do not use the production
    // AppendNativeAddressMap to construct the test oracle.
    std::vector<u64> code(16ULL + count + 2, 0x50);
    code[code.size() - 2] = count;
    code.back() = 0x50414d4e4544454eULL;
    return code;
}

static void TestAddressMap() {
    auto code = Map(65537);
    CHECK(NativeProgramAddress(code, 65536 * 16) == 0x50U);
    CHECK(!NativeProgramAddress(code, 65537 * 16));
    CHECK(!NativeProgramAddress(code, 1));
    code[16] = 0x58;
    CHECK(NativeProgramAddress(code, 0) == 0x58U);
    for (u64 target : {0x48ULL, 0x51ULL, 0x60ULL, 0x80ULL}) {
        code[16] = target;
        CHECK(!NativeProgramAddress(code, 0));
    }
    code = Map(AbsoluteCount);
    CHECK(NativeProgramAddress(code, (AbsoluteCount - 1) * 16) == 0x50U);
    CHECK(!NativeProgramAddress(code, AbsoluteCount * 16));
    code = Map(AbsoluteCount + 1);
    CHECK(!NativeProgramAddress(code, 0));
    code = {0, 0x50414d4e4544454eULL};
    CHECK(!NativeProgramAddress(code, 0));
    code = {65537, 0x50414d4e4544454eULL};
    CHECK(!NativeProgramAddress(code, 0));
    code = Map(1);
    code.back() = 0;
    CHECK(!NativeProgramAddress(code, 0));
    std::puts("address map: large valid map, exact cap and malformed bounds passed");
}

static void TestRealShader(const char* path) {
    // Captured compute input: hdr=0, len=1066624, end=1066752. The last
    // 128 bytes in the retained blob are padding, not part of the native code.
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    CHECK(input.is_open());
    CHECK(input.tellg() == std::streamoff{1066752});
    input.seekg(0);
    std::vector<Instruction> code(66664);
    CHECK(input.read(reinterpret_cast<char*>(code.data()), 1066624));
    CHECK(code[16404].words == RealBranch.words);
    ProgramCaptureState old_default;
    for (u32 i = 0; i <= 16404; ++i) {
        const auto expected = i == 16404 ? CaptureResult::InvalidTarget : CaptureResult::Continue;
        CHECK(old_default.Observe(code[i], i) == expected);
    }
    ProgramCaptureState capture(66664);
    u32 completed_at = ~0U;
    for (u32 i = 0; i < code.size(); ++i) {
        const auto result = capture.Observe(code[i], i);
        CHECK(result != CaptureResult::InvalidTarget);
        if (result == CaptureResult::Complete) {
            completed_at = i;
            break;
        }
    }
    CHECK(completed_at == 66650);
    code.resize(completed_at + 1);
    auto lowered = LowerToMaxwell(code);
    if (!lowered) std::fprintf(stderr, "real lower: %.*s at %u\n",
        static_cast<int>(lowered.error.size()), lowered.error.data(), lowered.error_offset);
    CHECK(lowered);
    CHECK(lowered.instructions.size() == 103942);
    CHECK(lowered.source_size == 1066416);
    std::puts("real shader: old failure at 16404; capture Complete at 66650; lowered 103942 words");
}

int main(int argc, char** argv) {
    CHECK(argc == 1 || argc == 2);
    TestCapture();
    TestLowering();
    TestAddressMap();
    if (argc == 2) TestRealShader(argv[1]);
    std::printf("PASS: %u checks%s\n", checks, argc == 2 ? " including retained real shader" : " (fixture not requested)");
}
