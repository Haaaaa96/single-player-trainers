"""Replace the Frida native library in an unsigned PyInstaller one-file EXE.

No trainer source, PyInstaller installation, or game access is needed.
The original executable is never overwritten. Requires Python 3.11+.
Written for WorldApartTrainer v1.0 / PyInstaller 6 CArchive format.
This helper is provided under the MIT License (see TOOL_LICENSE.txt).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = struct.Struct("!8sIIII64s")
ENTRY = struct.Struct("!IIIIBc")


def pe_machine(data: bytes) -> int:
    if data[:2] != b"MZ" or len(data) < 64:
        raise ValueError("Expected a Windows PE image")
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset + 26 > len(data) or data[offset:offset + 4] != b"PE\0\0":
        raise ValueError("Invalid PE header")
    return struct.unpack_from("<H", data, offset + 4)[0]


def read_archive(data: bytes):
    pos = data.rfind(MAGIC)
    if pos < 0 or pos + COOKIE.size != len(data):
        raise ValueError("Expected an unsigned one-file executable with an EOF archive cookie")
    magic, length, toc_offset, toc_length, version, library = COOKIE.unpack_from(data, pos)
    start = len(data) - length
    if start < 0 or toc_offset < 0 or start + toc_offset + toc_length != pos:
        raise ValueError("Invalid archive bounds")
    toc = data[start + toc_offset:pos]
    cursor = 0
    records = []
    names = set()
    while cursor < len(toc):
        if len(toc) - cursor < ENTRY.size:
            raise ValueError("Truncated archive table")
        size, offset, packed_size, plain_size, compressed, kind = ENTRY.unpack_from(toc, cursor)
        if size < ENTRY.size + 1 or cursor + size > len(toc):
            raise ValueError("Invalid archive entry size")
        if compressed not in (0, 1) or offset + packed_size > toc_offset:
            raise ValueError("Invalid archive entry bounds")
        raw_name = toc[cursor + ENTRY.size:cursor + size]
        if b"\0" not in raw_name:
            raise ValueError("Archive entry is not terminated")
        name = raw_name.rstrip(b"\0").decode("utf-8")
        if kind != b"o" and name in names:
            raise ValueError("Duplicate archive entry")
        names.add(name)
        records.append((name, size, offset, packed_size, plain_size, compressed, kind, raw_name))
        cursor += size
    return start, version, library, records


def replace_library(original: bytes, replacement: bytes):
    if pe_machine(original) != 0x8664 or pe_machine(replacement) != 0x8664:
        raise ValueError("Both images must be Windows x64 PE files")
    start, version, library, records = read_archive(original)
    matches = [r for r in records if r[0].replace("\\", "/") == "frida/_frida.pyd"]
    if len(matches) != 1 or matches[0][6] != b"b":
        raise ValueError("Expected exactly one frida/_frida.pyd binary")
    target = matches[0][0]
    payload = bytearray()
    table = bytearray()
    for name, size, offset, packed_size, plain_size, compressed, kind, raw_name in records:
        if name == target:
            packed = zlib.compress(replacement, 9) if compressed else replacement
            plain_size = len(replacement)
        else:
            packed = original[start + offset:start + offset + packed_size]
        table += ENTRY.pack(size, len(payload), len(packed), plain_size, compressed, kind) + raw_name
        payload += packed
    cookie = COOKIE.pack(MAGIC, len(payload) + len(table) + COOKIE.size,
                         len(payload), len(table), version, library)
    result = original[:start] + payload + table + cookie
    new_start, _, _, new_records = read_archive(result)
    for old, new in zip(records, new_records, strict=True):
        assert old[0] == new[0] and old[6:] == new[6:]
        new_data = result[new_start + new[2]:new_start + new[2] + new[3]]
        if old[0] == target:
            if new[5]:
                new_data = zlib.decompress(new_data)
            assert new_data == replacement
        else:
            assert new_data == original[start + old[2]:start + old[2] + old[3]]
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Unmodified trainer EXE")
    parser.add_argument("--frida", type=Path, required=True, help="Your compatible Frida 17.7.3 x64 _frida.pyd")
    parser.add_argument("--output", type=Path, required=True, help="A NEW modified EXE; must not exist")
    parser.add_argument("--expected-sha256", help="Optional published input EXE SHA256")
    args = parser.parse_args()
    original = args.input.read_bytes()
    old_hash = hashlib.sha256(original).hexdigest()
    if args.expected_sha256 and old_hash != args.expected_sha256.lower():
        parser.error("Input EXE hash does not match --expected-sha256")
    replacement = args.frida.read_bytes()
    output = replace_library(original, replacement)
    # Exclusive creation prevents replacing the original or any existing file.
    with args.output.open("xb") as stream:
        stream.write(output)
    print(json.dumps({"input_sha256": old_hash,
                      "frida_sha256": hashlib.sha256(replacement).hexdigest(),
                      "output_sha256": hashlib.sha256(output).hexdigest(),
                      "output_bytes": len(output),
                      "only_changed_component": "frida/_frida.pyd"}, indent=2))


if __name__ == "__main__":
    main()
