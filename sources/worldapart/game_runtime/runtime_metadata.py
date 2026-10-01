"""Bounded, read-only identities from the currently verified metadata mapping.

The bundled handoff selects reviewed type/field *names*. Its file positions,
tokens and type indices are not compatibility gates. This module never opens a
process or discovers a metadata base; the caller must verify that mapping first.
IL2CPP runtime field kind, static/literal flags, object ownership and write
permissions remain the caller's checks. A metadata type index is not a kind.
"""
from collections.abc import Mapping
import struct


class RuntimeMetadataError(RuntimeError):
    pass


# Short public name used by discovery and resolver error boundaries.
MetadataError = RuntimeMetadataError


MAGIC = 0xFAB11BAF
VERSION = 31
HEADER_SIZE = 256
TYPE_SIZE = 88
FIELD_SIZE = 12
IMAGE_SIZE = 40
MAX_METADATA_BYTES = 256 * 1024 * 1024
MAX_STRING_BYTES = 32 * 1024 * 1024
MAX_TYPE_COUNT = 262144
MAX_IMAGE_COUNT = 4096
MAX_FIELD_COUNT = 1024
MAX_NAME_BYTES = 1024
MAX_READ_BYTES = 1024 * 1024
# One public lookup, including the initial table index; never a reader lifetime.
MAX_TOTAL_READ_BYTES = 64 * 1024 * 1024

# The original small handoff predates image identities. These exact reviewed
# names were checked against metadata 31; never infer an image from a namespace.
# A future reviewed handoff may supply an explicit image/image_name instead.
REVIEWED_IMAGES = {
    'Game.Model.PlayerModel': 'Game.dll',
    'Game.Model.Player.Components.TalentPathModel': 'Game.dll',
    'Game.Model.Components.BagItem': 'Game.dll',
    'Game.Model.Components.BagItemBase': 'Game.dll',
    'Game.Model.Components.BagModel': 'Game.dll',
    'System.Boolean': 'mscorlib.dll',
    'System.Int32': 'mscorlib.dll',
    'System.Int64': 'mscorlib.dll',
    'Game.Model.GameStore': 'Game.dll',
    'Game.Model.GameStoreManager': 'Game.dll',
    'Game.Model.GameWorldModel': 'Game.dll',
    'SimpleSave.StoredEntity': 'SimpleSave.Runtime.dll',
    'LubanDatas.Tables': 'Game.dll',
    'LubanDatas.TbItem': 'Game.dll',
    'LubanDatas.TbItemType': 'Game.dll',
    'LubanDatas.data.Item': 'Game.dll',
    'LubanDatas.data.ItemType': 'Game.dll',
    'LubanDatas.L10nText': 'Game.dll',
    'Game.Model.Components.ArtifactBagItem': 'Game.dll',
    'Game.Model.Components.GambleStoneBagItem': 'Game.dll',
    'Game.Model.Components.GongfaBagItem': 'Game.dll',
    'Game.Model.Components.NpcBagItem': 'Game.dll',
    'Game.Model.Components.PillBagItem': 'Game.dll',
}


class RuntimeSpecs(Mapping):
    """Resolve reviewed specifications on demand for one reader's lifetime.

    The string/type/image tables are read at most once. Missing or incompatible
    optional types fail only when that name is requested. Do not reuse this
    instance across readers/process lifetimes. Repeated access rechecks the
    header and the selected records, not a cached runtime address from disk.
    """

    def __init__(self, reader, metadata_base, reviewed_specs, *, metadata_size=None):
        if (type(metadata_base) is not int or metadata_base <= 0
                or metadata_base + MAX_METADATA_BYTES > 0x7FFFFFFFFFFF):
            raise RuntimeMetadataError('Invalid verified metadata base')
        if metadata_size is not None and (
                type(metadata_size) is not int or metadata_size < HEADER_SIZE):
            raise RuntimeMetadataError('Invalid verified metadata mapping size')
        values = reviewed_specs.values() if isinstance(reviewed_specs, Mapping) else reviewed_specs
        self._reviewed = {}
        for spec in values:
            if not isinstance(spec, Mapping) or not isinstance(spec.get('name'), str) or not spec['name']:
                raise RuntimeMetadataError('Invalid reviewed metadata specification')
            name = spec['name']
            if name in self._reviewed:
                raise RuntimeMetadataError('Duplicate reviewed type: ' + name)
            self._reviewed[name] = dict(spec)
        if len(self._reviewed) > 512:
            raise RuntimeMetadataError('Reviewed type count exceeds bounded lookup')
        self.reader = reader
        self.base = metadata_base
        self._mapping_size = metadata_size
        self._extent = min(metadata_size or MAX_METADATA_BYTES, MAX_METADATA_BYTES)
        self._read_bytes = 0
        self._invalid_reason = None
        self._header = None
        self._cache = {}
        self._evidence = {}
        self._strings_cache = {}

    def __iter__(self):
        return iter(self._reviewed)

    def __len__(self):
        return len(self._reviewed)

    def register(self, spec):
        """Add explicit feature requirements without rereading the table index."""
        if not isinstance(spec, Mapping) or not isinstance(spec.get('name'), str):
            raise RuntimeMetadataError('Invalid additional metadata specification')
        name = spec['name']
        previous = self._reviewed.get(name)
        if previous is not None:
            for key in ('image_name', 'declaring_type'):
                if previous.get(key) != spec.get(key):
                    raise RuntimeMetadataError('Conflicting reviewed type ownership: ' + name)
            merged = {f['name']: f for f in previous['fields']}
            merged.update({f['name']: f for f in spec['fields']})
            if len(merged) == len(previous['fields']):
                return
            if name in self._evidence:
                self._read_bytes = 0
                self._check_evidence(self._evidence[name])
            spec = {**previous, 'fields': list(merged.values())}
        elif len(self._reviewed) >= 512:
            raise RuntimeMetadataError('Reviewed type count exceeds bounded lookup')
        self._reviewed[name] = dict(spec)
        self._cache.pop(name, None)
        self._evidence.pop(name, None)
        if self._header is not None and name not in self._matches:
            self._matches[name] = self._matching_indices(name)

    def _matching_indices(self, full):
        namespace, _, name = full.rpartition('.')
        return [index for index in range(len(self._types) // TYPE_SIZE)
                if self._string(struct.unpack_from('<i', self._types, index * TYPE_SIZE)[0])[0] == name
                and self._string(struct.unpack_from('<i', self._types, index * TYPE_SIZE + 4)[0])[0] == namespace]

    def _declaring_matches(self, index, fullname, image_name):
        declaring = struct.unpack_from('<i', self._types, index * TYPE_SIZE + 12)[0]
        matches = [i for i in range(len(self._types) // TYPE_SIZE)
                   if struct.unpack_from('<i', self._types, i * TYPE_SIZE + 8)[0] == declaring]
        if len(matches) != 1:
            return False
        owner = matches[0]
        ni, ns = struct.unpack_from('<ii', self._types, owner * TYPE_SIZE)
        actual = self._string(ns)[0] + '.' + self._string(ni)[0]
        images = [im for im in self._images if im[1] <= owner < im[1] + im[2]]
        return actual.lstrip('.') == fullname.lstrip('.') and len(images) == 1 and images[0][0] == image_name

    def _read(self, offset, size):
        if offset < 0 or size < 0 or offset + size > self._extent:
            raise RuntimeMetadataError('Metadata read is outside the verified bounds')
        if self._read_bytes + size > MAX_TOTAL_READ_BYTES:
            raise RuntimeMetadataError('Metadata read budget exhausted')
        self._read_bytes += size
        chunks = []
        for start in range(0, size, MAX_READ_BYTES):
            count = min(MAX_READ_BYTES, size - start)
            data = self.reader.read(self.base + offset + start, count)
            if len(data) != count:
                raise RuntimeMetadataError('Truncated or unreadable current metadata')
            chunks.append(data)
        return b''.join(chunks)

    def _table(self, header_offset, stride, max_count):
        offset, size = struct.unpack_from('<II', self._header, header_offset)
        if size % stride or size // stride > max_count:
            raise RuntimeMetadataError('Invalid bounded metadata table at ' + hex(header_offset))
        return offset, size

    def _string(self, index):
        if index in self._strings_cache:
            return self._strings_cache[index]
        if not 0 <= index < len(self._strings):
            raise RuntimeMetadataError('Metadata string index is outside the string table')
        end = self._strings.find(b'\0', index, min(len(self._strings), index + MAX_NAME_BYTES + 1))
        if end < 0:
            raise RuntimeMetadataError('Unterminated or oversized metadata name')
        raw = self._strings[index:end + 1]
        try:
            name = raw[:-1].decode('utf-8', errors='strict')
        except UnicodeDecodeError as exc:
            raise RuntimeMetadataError('Invalid UTF-8 metadata name') from exc
        value = (name, self._string_offset + index, raw)
        self._strings_cache[index] = value
        return value

    def _load(self):
        if self._header is not None:
            return
        header = self._read(0, HEADER_SIZE)
        if struct.unpack_from('<II', header) != (MAGIC, VERSION):
            raise RuntimeMetadataError('Unsupported current metadata format; expected metadata 31')
        sections = []
        extent = HEADER_SIZE
        for pos in range(8, HEADER_SIZE, 8):
            offset, size = struct.unpack_from('<II', header, pos)
            if offset + size > self._extent or (size and offset < HEADER_SIZE):
                raise RuntimeMetadataError('Metadata section exceeds verified bounds')
            if size:
                sections.append((offset, offset + size))
                extent = max(extent, offset + size)
        sections.sort()
        if any(right[0] < left[1] for left, right in zip(sections, sections[1:])):
            raise RuntimeMetadataError('Overlapping metadata sections')
        self._extent = extent
        # Establish the declared end even when the caller has no whole-mapping
        # length. All actual table reads must independently be exact as well.
        self._read(extent - 1, 1)
        self._header = header
        try:
            self._string_offset, string_size = self._table(0x18, 1, MAX_STRING_BYTES)
            self._type_offset, type_size = self._table(0xA0, TYPE_SIZE, MAX_TYPE_COUNT)
            self._image_offset, image_size = self._table(0xA8, IMAGE_SIZE, MAX_IMAGE_COUNT)
            self._field_offset, field_size = self._table(0x60, FIELD_SIZE, 2 * 1024 * 1024)
            if not string_size or not type_size or not image_size:
                raise RuntimeMetadataError('Required metadata tables are empty')
            self._field_count = field_size // FIELD_SIZE
            self._strings = self._read(self._string_offset, string_size)
            self._types = self._read(self._type_offset, type_size)
            self._image_bytes = self._read(self._image_offset, image_size)
            type_count = type_size // TYPE_SIZE
            self._images = []
            for pos in range(0, image_size, IMAGE_SIZE):
                name_index, _assembly, first, count = struct.unpack_from('<iiiI', self._image_bytes, pos)
                if count and (first < 0 or first + count > type_count):
                    raise RuntimeMetadataError('Image type range is outside the type table')
                if not count and not -1 <= first <= type_count:
                    raise RuntimeMetadataError('Invalid empty image type range')
                name, string_offset, raw_name = self._string(name_index)
                if not name:
                    raise RuntimeMetadataError('Empty metadata image name')
                self._images.append((name, first, count, pos, string_offset, raw_name))
            occupied = sorted((v[1], v[1] + v[2]) for v in self._images if v[2])
            if any(right[0] < left[1] for left, right in zip(occupied, occupied[1:])):
                raise RuntimeMetadataError('Ambiguous overlapping metadata image ownership')
            self._matches = {name: [] for name in self._reviewed}
            short_names = {name.rpartition('.')[2] for name in self._reviewed}
            for index in range(type_count):
                name_index, namespace_index = struct.unpack_from('<ii', self._types, index * TYPE_SIZE)
                name = self._string(name_index)[0]
                if name not in short_names:
                    continue
                namespace = self._string(namespace_index)[0]
                full = namespace + '.' + name if namespace else name
                if not namespace and '.' + name in self._matches:
                    self._matches['.' + name].append(index)
                if full in self._matches:
                    self._matches[full].append(index)
            if self._read(0, HEADER_SIZE) != header:
                raise RuntimeMetadataError('Metadata changed while indexing current tables')
        except Exception:
            # A partially initialized index must never be reused after failure.
            self._header = None
            self._strings_cache.clear()
            raise

    def _check_evidence(self, evidence):
        try:
            if self._read(0, HEADER_SIZE) != self._header:
                raise RuntimeMetadataError('Metadata header changed; reconnect read-only')
            for offset, expected in evidence:
                if self._read(offset, len(expected)) != expected:
                    raise RuntimeMetadataError('Selected metadata changed; reconnect read-only')
        except RuntimeMetadataError as exc:
            # Every selected class shares this table index. Even if bytes later
            # return to their old values, a new reader/index is required.
            self._invalid_reason = str(exc)
            self._cache.clear()
            self._evidence.clear()
            self._strings_cache.clear()
            raise

    def __getitem__(self, name):
        if name not in self._reviewed:
            raise KeyError(name)
        if self._invalid_reason is not None:
            raise RuntimeMetadataError('Metadata evidence was invalidated; reconnect read-only: '
                                       + self._invalid_reason)
        self._read_bytes = 0
        self._load()
        if name in self._cache:
            self._check_evidence(self._evidence[name])
            return self._cache[name]
        reviewed = self._reviewed[name]
        image_name = reviewed.get('image_name', reviewed.get('image', REVIEWED_IMAGES.get(name)))
        if not isinstance(image_name, str) or not image_name:
            raise RuntimeMetadataError('Missing reviewed image identity: ' + name)
        candidates = []
        for index in self._matches[name]:
            owners = [image for image in self._images if image[1] <= index < image[1] + image[2]]
            if len(owners) != 1:
                raise RuntimeMetadataError('Missing or ambiguous image owner: ' + name)
            if owners[0][0] == image_name:
                declaring = reviewed.get('declaring_type')
                if declaring and not self._declaring_matches(index, declaring, image_name):
                    continue
                candidates.append((index, owners[0]))
        if len(candidates) != 1:
            raise RuntimeMetadataError('Missing or ambiguous current type in ' + image_name + ': ' + name)
        index, owner = candidates[0]
        type_pos = index * TYPE_SIZE
        raw_type = self._types[type_pos:type_pos + TYPE_SIZE]
        values = struct.unpack('<16i8H2I', raw_type)
        name_index, namespace_index, byval = values[:3]
        parent_type, field_start, field_count, token = values[4], values[8], values[18], values[25]
        if byval < 0 or parent_type < -1 or token >> 24 != 0x02 or not token & 0xFFFFFF:
            raise RuntimeMetadataError('Malformed current type identity: ' + name)
        if field_count > MAX_FIELD_COUNT or (field_count and (
                field_start < 0 or field_start + field_count > self._field_count)):
            raise RuntimeMetadataError('Invalid bounded field range: ' + name)
        if not field_count and not -1 <= field_start <= self._field_count:
            raise RuntimeMetadataError('Invalid empty field range: ' + name)
        _, name_offset, raw_name = self._string(name_index)
        _, namespace_offset, raw_namespace = self._string(namespace_index)
        evidence = [
            (self._type_offset + type_pos, raw_type),
            (self._image_offset + owner[3], self._image_bytes[owner[3]:owner[3] + IMAGE_SIZE]),
            (owner[4], owner[5]), (name_offset, raw_name), (namespace_offset, raw_namespace),
        ]
        if reviewed.get('declaring_type'):
            declaring_byval = values[3]
            declaring_index = next(i for i in range(len(self._types) // TYPE_SIZE)
                if struct.unpack_from('<i', self._types, i * TYPE_SIZE + 8)[0] == declaring_byval)
            declaring_pos = declaring_index * TYPE_SIZE
            declaring_raw = self._types[declaring_pos:declaring_pos + TYPE_SIZE]
            evidence.append((self._type_offset + declaring_pos, declaring_raw))
            for string_index in struct.unpack_from('<ii', declaring_raw):
                _, offset, raw_string = self._string(string_index)
                evidence.append((offset, raw_string))
            declaring_image = next(im for im in self._images
                                   if im[1] <= declaring_index < im[1] + im[2])
            evidence.append((self._image_offset + declaring_image[3],
                             self._image_bytes[declaring_image[3]:declaring_image[3] + IMAGE_SIZE]))
            evidence.append((declaring_image[4], declaring_image[5]))
        raw_fields = self._read(self._field_offset + max(field_start, 0) * FIELD_SIZE,
                                field_count * FIELD_SIZE)
        if raw_fields:
            evidence.append((self._field_offset + field_start * FIELD_SIZE, raw_fields))
        fields = {}
        for ordinal in range(field_count):
            field_name_index, type_index, field_token = struct.unpack_from('<iiI', raw_fields, ordinal * FIELD_SIZE)
            field_name, field_name_offset, raw_field_name = self._string(field_name_index)
            if (not field_name or field_name in fields or type_index < 0
                    or field_token >> 24 != 0x04 or not field_token & 0xFFFFFF):
                raise RuntimeMetadataError('Malformed or duplicate current field: ' + name)
            evidence.append((field_name_offset, raw_field_name))
            fields[field_name] = dict(name=field_name, nameFileOffset=field_name_offset,
                                     fieldIndex=field_start + ordinal, typeIndex=type_index,
                                     token=hex(field_token))
        required = reviewed.get('fields')
        if not isinstance(required, (list, tuple)):
            raise RuntimeMetadataError('Missing reviewed field requirements: ' + name)
        current_fields, seen = [], set()
        for field in required:
            if not isinstance(field, Mapping) or not isinstance(field.get('name'), str):
                raise RuntimeMetadataError('Invalid reviewed field requirement: ' + name)
            field_name = field['name']
            if field_name in seen or field_name not in fields:
                raise RuntimeMetadataError('Missing or duplicate required field: ' + name + '.' + field_name)
            seen.add(field_name)
            current_fields.append({**field, **fields[field_name]})
        current = {**reviewed, 'typeDef': index, 'nameIndex': name_index,
                   'nameFileOffset': name_offset, 'namespaceFileOffset': namespace_offset,
                   'typeDefinitionFileOffset': self._type_offset + type_pos,
                   'byval': byval, 'parentType': parent_type, 'fieldStart': field_start,
                   'fieldCount': field_count, 'token': hex(token), 'fields': current_fields,
                   'image_name': image_name, 'all_fields': list(fields.values())}
        self._check_evidence(evidence)
        self._cache[name], self._evidence[name] = current, evidence
        return current


def resolve_runtime_specs(reader, metadata_base, reviewed_specs, names=None, *, metadata_size=None):
    """Resolve a bounded explicit selection, or every supplied reviewed name."""
    specs = RuntimeSpecs(reader, metadata_base, reviewed_specs, metadata_size=metadata_size)
    return {name: specs[name] for name in (specs if names is None else dict.fromkeys(names))}
