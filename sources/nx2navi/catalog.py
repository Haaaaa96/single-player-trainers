"""Load the pouch catalog from the local game's RomFS, without extracting the image."""
from compression import zstd
from pathlib import Path
import json
import os
import struct

GAME = Path(os.environ["LOCALAPPDATA"]) / "Programs/NX2navi/game"


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def cstring(data, offset):
    return data[offset:data.index(0, offset)].decode("utf-8")


class Byml:
    def __init__(self, data):
        self.data = data
        if data[:2] not in (b"YB", b"BY"):
            raise ValueError("Invalid BYML signature")
        self.endian = "<" if data[:2] == b"YB" else ">"
        keys, strings, self.root = struct.unpack_from(self.endian + "III", data, 4)
        self.keys = self.strings(keys) if keys else []
        self.text = self.strings(strings) if strings else []

    def count(self, offset):
        return int.from_bytes(self.data[offset+1:offset+4],
                              "little" if self.endian == "<" else "big")

    def word(self, offset):
        return struct.unpack_from(self.endian + "I", self.data, offset)[0]

    def strings(self, offset):
        if self.data[offset] != 0xC2:
            raise ValueError("Expected BYML string table")
        return [cstring(self.data, offset + self.word(offset+4+4*i))
                for i in range(self.count(offset))]

    def value(self, kind, word):
        if kind == 0xA0:
            return self.text[word]
        if kind == 0xD0:
            return bool(word)
        if kind == 0xD1:
            return word if word < 0x80000000 else word-0x100000000
        if kind == 0xD2:
            return struct.unpack("<f", struct.pack("<I", word))[0]
        if kind == 0xD3:
            return word
        if kind in (0xD4, 0xD5, 0xD6):
            return struct.unpack_from(self.endian + {0xD4:"q", 0xD5:"Q", 0xD6:"d"}[kind], self.data, word)[0]
        if kind in (0xC0, 0xC1):
            return self.node(word)
        if kind == 0xFF:
            return None
        raise ValueError(f"Unsupported BYML type {kind:#x}")

    def node(self, offset):
        kind = self.data[offset]
        count = self.count(offset)
        if kind == 0xC0:
            types = offset + 4
            words = (types + count + 3) & ~3
            return [self.value(self.data[types+i], self.word(words+4*i))
                    for i in range(count)]
        if kind == 0xC1:
            entries = offset+4
            result = {}
            for i in range(count):
                at = entries+8*i
                index = int.from_bytes(self.data[at:at+3], "little" if self.endian == "<" else "big")
                result[self.keys[index]] = self.value(self.data[at+3], self.word(at+4))
            return result
        raise ValueError(f"Unsupported BYML node {kind:#x}")


class RomFS:
    def __init__(self, game=GAME):
        root = game / "romfs"
        self.image = root / "romfs.bin"
        entries = json.loads((root / "index.json").read_bytes())
        if self.image.stat().st_size != entries["romfs_size"]:
            raise ValueError("RomFS length does not match its index")
        self.entries = {e["path"]: (e["offset"], e["size"]) for e in entries["files"]}
        self.dictionaries = {}

    def read(self, path):
        offset, length = self.entries[path]
        if not 0 < length < 32*1024*1024:
            raise ValueError(f"Unexpected table size for {path}")
        with self.image.open("rb") as f:
            f.seek(offset)
            data = f.read(length)
        if not path.endswith(".zs"):
            return data
        info = zstd.get_frame_info(data)
        if info.decompressed_size > 32*1024*1024:
            raise ValueError(f"Unexpected decompressed size for {path}")
        if info.dictionary_id and not self.dictionaries:
            pack = self.read("Pack/ZsDic.pack.zs")
            if pack[:4] != b"SARC" or pack[20:24] != b"SFAT":
                raise ValueError("Unrecognized dictionary SARC")
            count = struct.unpack_from("<H", pack, 26)[0]
            data_offset = u32(pack, 12)
            for i in range(count):
                _, _, start, end = struct.unpack_from("<IIII", pack, 32+16*i)
                zd = zstd.ZstdDict(pack[data_offset+start:data_offset+end])
                self.dictionaries[zd.dict_id] = zd
        return zstd.decompress(data, zstd_dict=self.dictionaries.get(info.dictionary_id))

    def byml(self, path):
        parser = Byml(self.read(path))
        return parser.node(parser.root)


POUCH = "RSDB/PouchActorInfo.Product.111.rstbl.byml.zs"
UI_POUCH = "UI/Pouch/PouchTable/PouchTable.game__ui__PouchTable.bgyml"
GAME_DATA = "GameData/GameDataList.Product.110.byml.zs"
