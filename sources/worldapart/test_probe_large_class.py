"""Realistic IL2CPP UI metadata counts must not break every panel reader."""
import struct
import unittest
from game_adapter import probe


class ClassReader:
    def __init__(self, count):
        self.count = count
        self.reads = 0

    def read(self, address, size):
        self.reads += 1
        if address == 0x1000:
            b = bytearray(320)
            struct.pack_into('<Q', b, 0x78, 0x1000)
            struct.pack_into('<Q', b, 0x80, 0x4000)
            struct.pack_into('<H', b, 0x124, self.count)
            struct.pack_into('<I', b, 0xF8, 4096)
            return bytes(b)
        if 0x4000 <= address < 0x4000 + self.count * 32:
            index = (address-0x4000)//32
            return struct.pack('<QQQiI', 0x100000+index, 0x200000, 0x1000, 16+index*4, 0x04000001+index)
        if address == 0x200000:
            return bytes(10)+b'\x08'+bytes(5)
        raise AssertionError((address, size))

    def string(self, address):
        return f'field{address}'


class LargeClassTests(unittest.TestCase):
    def test_reviewed_300_field_panel_is_completely_parsed(self):
        reader = ClassReader(300)
        result = probe.inspect_class(reader, 0x1000)
        self.assertEqual(len(result['fields']), 300)
        self.assertEqual(result['fields'][-1]['token'], hex(0x04000001+299))
        self.assertEqual(result['fields'][-1]['parent'], '0x1000')

    def test_unreasonable_count_stops_before_field_reads(self):
        reader = ClassReader(513)
        self.assertIsNone(probe.inspect_class(reader, 0x1000))
        self.assertEqual(reader.reads, 1)

    def test_reviewed_large_config_needs_explicit_bounded_limit(self):
        reader = ClassReader(709)
        self.assertIsNone(probe.inspect_class(reader, 0x1000))
        result = probe.inspect_class(reader, 0x1000, max_fields=709)
        self.assertEqual(len(result['fields']), 709)
        self.assertIsNone(probe.inspect_class(ClassReader(710), 0x1000, max_fields=709))

    def test_invalid_limit_rejected_before_process_reads(self):
        for limit in (0, -1, 1025, True, 709.0):
            reader=ClassReader(1)
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                probe.inspect_class(reader,0x1000,max_fields=limit)
            self.assertEqual(reader.reads,0)


if __name__ == '__main__':
    unittest.main()
