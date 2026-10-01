"""Inspect WorldApart files; release fingerprints are advisory, not a gate.

This module never opens a process, starts a game, or changes installation files.
The running process path, rather than a Steam-library default, is authoritative.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import struct

from write_guard import Refused

EXECUTABLE_NAME = "WorldApart.exe"
REVIEWED_STEAM_BUILD = "25617557"
METADATA_RELATIVE = "WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat"
HASHES = {
    "GameAssembly.dll": "ede8a956051c0c831f79e0874aff28297f41d3fa18c18ad2ca2ff16c33d0938d",
    "WorldApart_Data/il2cpp_data/Metadata/global-metadata.dat":
        "bbeca25f98cfc56bfe48a5bd6dc90b9aadfeb1a6bb8f0dc03ca8da2ef26dbdbc",
}


@dataclass(frozen=True)
class GameInstallation:
    executable_path: Path
    install_directory: Path


@dataclass(frozen=True)
class FileFingerprint:
    relative_path: str
    expected_sha256: str
    actual_sha256: str
    size_bytes: int

    @property
    def matches_reviewed(self):
        return self.actual_sha256 == self.expected_sha256


@dataclass(frozen=True)
class CompatibilityAssessment:
    """Disk evidence for a warning; live layouts and methods decide usability.

    Matching fingerprints do not prove a live target is valid, and differing
    fingerprints alone do not disable the runtime verification path.
    """
    installation: GameInstallation
    files: tuple[FileFingerprint, ...]
    steam_build_id: str | None = None
    steam_app_id: str | None = None
    steam_manifest_path: Path | None = None
    warnings: tuple[str, ...] = ()
    metadata_version: int | None = None
    metadata_header_valid: bool = False

    @property
    def reviewed_files_match(self):
        return (len(self.files) == len(HASHES)
                and {entry.relative_path for entry in self.files} == set(HASHES)
                and all(entry.matches_reviewed for entry in self.files))

    @property
    def changed_files(self):
        return tuple(entry.relative_path for entry in self.files if not entry.matches_reviewed)

    @property
    def mode(self):
        return "reviewed" if self.reviewed_files_match else "unreviewed"

    @property
    def read_only(self):
        return False

    def as_dict(self):
        return {
            "mode": self.mode, "read_only": self.read_only,
            "reviewed_files_match": self.reviewed_files_match,
            "executable_path": str(self.installation.executable_path),
            "install_directory": str(self.installation.install_directory),
            "reviewed_steam_build_id": REVIEWED_STEAM_BUILD,
            "steam_build_id": self.steam_build_id, "steam_app_id": self.steam_app_id,
            "steam_manifest_path": str(self.steam_manifest_path) if self.steam_manifest_path else None,
            "metadata_version": self.metadata_version,
            "metadata_header_valid": self.metadata_header_valid,
            "changed_files": list(self.changed_files), "warnings": list(self.warnings),
            "files": [{"relative_path": entry.relative_path,
                       "expected_sha256": entry.expected_sha256,
                       "actual_sha256": entry.actual_sha256,
                       "size_bytes": entry.size_bytes,
                       "matches_reviewed": entry.matches_reviewed} for entry in self.files],
        }


def executable_path(path, *, must_exist=True):
    """Normalize an explicit executable path; empty/cancelled inputs never auto-fall back."""
    if not isinstance(path, (str, os.PathLike)) or not str(path).strip():
        raise Refused("未选择游戏程序，请选择 WorldApart.exe。")
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise Refused("请选择 WorldApart.exe 的完整路径。")
    if candidate.name.casefold() != EXECUTABLE_NAME.casefold():
        raise Refused("所选文件不是 WorldApart.exe，请选择游戏主程序。")
    try:
        resolved = candidate.resolve(strict=must_exist)
        if must_exist and not resolved.is_file():
            raise Refused("所选 WorldApart.exe 不是可读取的游戏程序文件。")
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, Refused):
            raise
        raise Refused("找不到或无法访问所选 WorldApart.exe，请核对游戏安装位置。") from exc
    if resolved.name.casefold() != EXECUTABLE_NAME.casefold():
        raise Refused("所选链接没有指向 WorldApart.exe 游戏主程序。")
    return resolved


def path_key(path):
    return os.path.normcase(str(executable_path(path, must_exist=False))).casefold()


def same_executable(first, second):
    return path_key(first) == path_key(second)


def _validated_executable(path):
    executable = executable_path(path)
    directory = executable.parent
    try:
        with executable.open("rb") as stream:
            header = stream.read(64)
            if len(header) != 64 or header[:2] != b"MZ":
                raise Refused("所选 WorldApart.exe 不是有效的 Windows x64 游戏程序。")
            pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
            if pe_offset < 64 or pe_offset > executable.stat().st_size - 24:
                raise Refused("所选 WorldApart.exe 的程序文件头无效。")
            stream.seek(pe_offset)
            pe_header = stream.read(24)
            if (len(pe_header) != 24 or pe_header[:4] != b"PE\0\0"
                    or struct.unpack_from("<H", pe_header, 4)[0] != 0x8664
                    or struct.unpack_from("<H", pe_header, 22)[0] & 0x2000):
                raise Refused("所选 WorldApart.exe 不是受支持的 Windows x64 主程序。")
    except OSError as exc:
        raise Refused("无法读取所选 WorldApart.exe，请核对游戏安装位置和访问权限。") from exc
    return executable


def _manifest_values(text):
    """Read only top-level AppState scalar keys from a bounded Steam VDF.

    This descriptive marker never grants access to a runtime layout. Nested
    depot buildids, comments and duplicate keys cannot impersonate AppState.
    """
    token_pattern = re.compile(r'\s+|//[^\r\n]*|"(?:\\.|[^"\\])*"|[{}]')
    tokens = []
    position = 0
    for match in token_pattern.finditer(text):
        if match.start() != position:
            raise ValueError("Invalid Steam manifest syntax.")
        position = match.end()
        token = match.group()
        if token.isspace() or token.startswith("//"):
            continue
        if token.startswith('"'):
            tokens.append(re.sub(r'\\(["\\])', r'\1', token[1:-1]))
        else:
            tokens.append(token)
        if len(tokens) > 32768:
            raise ValueError("Steam manifest token limit exceeded.")
    if position != len(text) or tokens[:2] != ["AppState", "{"]:
        raise ValueError("No unambiguous AppState section.")
    values, depth, index = {}, 1, 2
    while index < len(tokens):
        if tokens[index] == "}":
            depth -= 1
            index += 1
            if depth == 0:
                if index != len(tokens):
                    raise ValueError("Unexpected data after AppState.")
                return values
            continue
        key = tokens[index]
        if key == "{" or index + 1 >= len(tokens):
            raise ValueError("Invalid Steam manifest key.")
        value = tokens[index + 1]
        index += 2
        if value == "{":
            depth += 1
            if depth > 16:
                raise ValueError("Steam manifest nesting limit exceeded.")
        elif value == "}":
            raise ValueError("Invalid Steam manifest value.")
        elif depth == 1:
            key = key.casefold()
            if key in values:
                raise ValueError("Duplicate Steam manifest key.")
            values[key] = value
    raise ValueError("Incomplete Steam manifest.")


def _steam_marker(directory):
    """Best effort: inspect only the selected installation's Steam library."""
    if directory.parent.name.casefold() != "common":
        return None, None, None, ()
    library = directory.parent.parent
    matches = []
    unreadable = False
    try:
        for index, manifest in enumerate(library.glob("appmanifest_*.acf")):
            if index >= 512:
                return None, None, None, ("Steam 清单过多，未确定 build 标识；兼容性仍按核心文件校验。",)
            try:
                with manifest.open("rb") as stream:
                    raw = stream.read(256 * 1024 + 1)
                if len(raw) > 256 * 1024:
                    raise ValueError("Steam manifest too large.")
                data = _manifest_values(raw.decode("utf-8-sig"))
                if data.get("installdir", "").casefold() != directory.name.casefold():
                    continue
                app_id, build_id = data.get("appid", ""), data.get("buildid", "")
                if (not re.fullmatch(r"[0-9]{1,20}", app_id)
                        or not re.fullmatch(r"[0-9]{1,20}", build_id)
                        or manifest.name.casefold() != f"appmanifest_{app_id}.acf"):
                    raise ValueError("Steam manifest identifiers are invalid.")
                matches.append((build_id, app_id, manifest.resolve()))
            except (OSError, UnicodeError, ValueError):
                unreadable = True
    except OSError:
        unreadable = True
    if len(matches) == 1:
        return *matches[0], ()
    if len(matches) > 1:
        return None, None, None, ("多个 Steam 清单指向所选安装目录，build 标识不确定；兼容性仍按核心文件校验。",)
    if unreadable:
        return None, None, None, ("未能可靠读取 Steam build 标识；兼容性仍按核心文件校验。",)
    return None, None, None, ()


def _file_identity(stat):
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def inspect_installation(path):
    """Return compatibility evidence even when a new build changed core files.

    This function does not open a process or grant write access. It never uses
    a version cache; unchanged build text cannot override changed file hashes.
    Missing files or an invalid executable remain ordinary installation errors.
    """
    executable = _validated_executable(path)
    directory = executable.parent
    fingerprints = []
    metadata_header = b""
    for relative, expected in HASHES.items():
        source = directory / relative
        try:
            with source.open("rb") as stream:
                before = os.fstat(stream.fileno())
                maximum = 128 * 1024 * 1024 if relative == METADATA_RELATIVE else 1024 * 1024 * 1024
                if not 0 < before.st_size <= maximum:
                    raise Refused(f"游戏安装文件大小异常，未解释其结构：{relative}。")
                if relative == METADATA_RELATIVE:
                    metadata_header = stream.read(8)
                    stream.seek(0)
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if (_file_identity(before) != _file_identity(os.fstat(stream.fileno()))
                        or _file_identity(before) != _file_identity(source.stat())):
                    raise Refused(f"游戏文件在兼容检测期间变化，请等待更新完成再连接：{relative}。")
        except (OSError, ValueError) as exc:
            raise Refused(f"游戏安装文件缺失或无法读取：{relative}。请核对所选 WorldApart.exe 所在目录。") from exc
        fingerprints.append(FileFingerprint(relative, expected, actual, before.st_size))
    header_valid = len(metadata_header) == 8 and struct.unpack_from("<I", metadata_header)[0] == 0xFAB11BAF
    metadata_version = struct.unpack_from("<I", metadata_header, 4)[0] if header_valid else None
    build_id, app_id, manifest_path, marker_warnings = _steam_marker(directory)
    warnings = list(marker_warnings)
    reviewed = all(entry.matches_reviewed for entry in fingerprints)
    if build_id is not None and build_id != REVIEWED_STEAM_BUILD:
        warnings.append(f"检测到 Steam build {build_id}，与已核验标识 {REVIEWED_STEAM_BUILD} 不同；"
                        + ("两个核心文件哈希一致，可继续使用已核验功能。" if reviewed
                           else "仍会尝试读取；部分功能可能失效。"))
    if not reviewed:
        warnings.append("游戏核心文件与本修改器适配版本不同：" + "、".join(
            entry.relative_path for entry in fingerprints if not entry.matches_reviewed)
            + "。此差异仅作提醒，不限制连接或使用；实际数据结构不兼容的功能会提示失败。")
        if not header_valid:
            warnings.append("metadata 文件头无法识别，当前解析器可能无法读取游戏数据。")
        elif metadata_version != 31:
            warnings.append(f"metadata 格式为 {metadata_version}；当前解析器按格式 31 处理，实际结构不兼容时可能无法读取。")
    return CompatibilityAssessment(GameInstallation(executable, directory), tuple(fingerprints),
                                   build_id, app_id, manifest_path, tuple(warnings),
                                   metadata_version, header_valid)


def validate_installation(path):
    """Validate file accessibility/identity; runtime checks own layout safety."""
    assessment = inspect_installation(path)
    return assessment.installation
