"""Bounded read-only class discovery, including nonresident readable heap pages.

No working-set query decides whether an address may be inspected. Full reads
can page memory in; both attempted bytes and elapsed time are bounded. An
unreadable span is reported, never silently described as a complete scan.
"""
from collections import Counter
import re
import struct
import time

from connection_diagnostics import ConnectionDiagnosticError
import probe


READABLE = frozenset((2, 4, 8, 0x20, 0x40, 0x80))
MAX_RECHECK_PAGES = 16384
DEFAULT_MIN_MIB = 4096
HARD_MAX_MIB = 16384
MIN_OVERHEAD_MIB = 64


def discovery_budget_mib(eligible_bytes, requested):
    """Bound a complete walk plus candidate/page rechecks, never early-accept hits."""
    if requested is not None:
        if type(requested) not in (int, float) or not 0 < requested <= HARD_MAX_MIB:
            raise ValueError('Invalid bounded discovery budget')
        return requested
    mib = 1024 * 1024
    overhead = max(MIN_OVERHEAD_MIB * mib, (eligible_bytes + 3) // 4)
    needed = (eligible_bytes + overhead + mib - 1) // mib
    return min(HARD_MAX_MIB, max(DEFAULT_MIN_MIB, needed))


def candidate(reader, klass, spec, meta):
    """Keep rejection reasons without ever choosing an ambiguous candidate."""
    header = reader.read(klass, 320)
    if len(header) != 320:
        return None, 'class_header_unreadable'
    if struct.unpack_from('<Q', header, 0x78)[0] != klass:
        return None, 'class_self_pointer_mismatch'
    ns, _, name = spec['name'].rpartition('.')
    if (reader.string(struct.unpack_from('<Q', header, 16)[0]) != name
            or reader.string(struct.unpack_from('<Q', header, 24)[0]) != ns):
        return None, 'class_name_mismatch'
    if spec.get('image_name'):
        image = struct.unpack_from('<Q', header)[0]
        if reader.string(reader.u64(image)) != spec['image_name']:
            return None, 'class_image_mismatch'
    if struct.unpack_from('<Q', header, 0x68)[0] != meta + spec['typeDefinitionFileOffset']:
        return None, 'type_definition_mismatch'
    if struct.unpack_from('<I', header, 0x11c)[0] != int(spec['token'], 16):
        return None, 'class_token_mismatch'
    count = struct.unpack_from('<H', header, 0x124)[0]
    if count != spec['fieldCount'] or count > 1024:
        return None, 'field_count_mismatch'
    if count and not struct.unpack_from('<Q', header, 0x80)[0]:
        return None, 'field_table_not_initialized'
    info = probe.inspect_class(reader, klass, max_fields=max(512, count))
    if info is None:
        return None, 'field_table_unreadable'
    fields = {f['name']: f for f in info['fields']}
    if len(fields) != len(info['fields']):
        return None, 'duplicate_field_name'
    if any(int(f['parent'], 16) != klass or len(f['type_data']) != 32 for f in info['fields']):
        return None, 'field_identity_mismatch'
    if any(f['name'] not in fields or fields[f['name']]['token'] != f['token']
           for f in spec['fields']):
        return None, 'required_field_mismatch'
    info['validated'] = True
    return info, None


def scan_classes(reader, meta, specs, *, regions=None, max_mib=None,
                 max_seconds=120, progress=None, clock=time.monotonic):
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 600:
        raise ValueError('Invalid bounded discovery budget')
    selected = [r for r in (reader.regions if regions is None else regions)
                if r['type'] == 0x20000 and not r['protect'] & 0x100
                and r['protect'] & 0xff in READABLE]
    eligible_bytes = sum(r['size'] for r in selected)
    budget_mode = 'automatic' if max_mib is None else 'explicit'
    max_mib = discovery_budget_mib(eligible_bytes, max_mib)
    by_pattern = {}
    for name, spec in specs.items():
        # Some runtimes/patches copy name strings. The current type-definition
        # handle is an independent anchor; full class identity is still checked.
        for key, offset in (('nameFileOffset',16),('typeDefinitionFileOffset',0x68)):
            by_pattern.setdefault(struct.pack('<Q', meta + spec[key]), []).append((name,offset))
    if not by_pattern:
        raise ValueError('Empty class discovery request')
    pattern = re.compile(b'|'.join(re.escape(p) for p in by_pattern))
    found = {name: {} for name in specs}
    seen = {name: set() for name in specs}
    stats = {name: {'pointer_hits': 0, 'rejections': Counter()} for name in specs}
    start = clock()
    last_progress = start
    diagnostic = {'stage': 'class_discovery', 'scan_mode': 'readable_private_pages',
                  'region_count': len(selected), 'eligible_bytes': eligible_bytes,
                  'attempted_bytes': 0, 'read_bytes': 0, 'unreadable_bytes': 0,
                  'partial_reads': 0, 'max_mib': max_mib, 'max_seconds': max_seconds,
                  'budget_mode': budget_mode, 'hard_max_mib': HARD_MAX_MIB,
                  'retired_bytes': 0, 'retired_pages_rechecked': 0,
                  'short_pages': 0, 'initial_short_bytes': 0,
                  'deferred_pages_rechecked': 0, 'recovered_pages': 0,
                  'recovered_bytes': 0, 'max_recheck_pages': MAX_RECHECK_PAGES,
                  'page_rechecks': [], 'candidate_rechecks': 0,
                  'candidate_count': 0, 'max_candidates': 100000,
                  'types': stats}
    retired = []
    deferred = []

    def no_longer_committed(address, size):
        # An enumerated heap span can be released while a live game runs.
        # Only a fresh OS query covering the ENTIRE page proves that it cannot
        # currently hold a live class. Failed queries/protected committed pages
        # remain missing evidence, never an excuse to skip a read failure.
        query = getattr(reader, 'query_region', None)
        if query is None:
            return False
        try:
            region = query(address)
        except OSError:
            return False
        return (isinstance(region, dict) and region.get('state') in (0x10000, 0x2000)
                and region.get('base', address + 1) <= address
                and region.get('base', 0) + region.get('size', 0) >= address + size)

    def finish(reason):
        diagnostic['outcome'] = reason
        diagnostic['seconds'] = round(clock() - start, 3)
        for name in specs:
            stats[name]['valid_candidates'] = len(found[name])
            stats[name]['rejections'] = dict(stats[name]['rejections'])
        return diagnostic

    def read(address, size):
        if diagnostic['attempted_bytes'] + size > max_mib * 1024 * 1024:
            diagnostic.update(budget_reason='read_limit', next_read_bytes=size)
            raise ConnectionDiagnosticError('连接扫描达到读取量上限，尚未完成全部区域检查。可复制诊断。', finish('budget_exhausted'))
        if clock() - start > max_seconds:
            diagnostic['budget_reason'] = 'time_limit'
            raise ConnectionDiagnosticError('连接扫描达到时间上限，未发布可用连接。可复制诊断。', finish('budget_exhausted'))
        diagnostic['attempted_bytes'] += size
        data = reader.read(address, size)
        if clock() - start > max_seconds:
            diagnostic['budget_reason'] = 'time_limit'
            raise ConnectionDiagnosticError('游戏内存读取耗时超过连接上限，未发布可用连接。', finish('budget_exhausted'))
        return data

    def inspect(address, data, *, revisit=False):
        diagnostic['read_bytes'] += len(data)
        for match in pattern.finditer(data):
            for name, offset in by_pattern[match.group()]:
                klass = address + match.start() - offset
                if klass <= 0 or klass % 8:
                    continue
                already_seen = klass in seen[name]
                if already_seen and not revisit:
                    continue
                if not already_seen and diagnostic['candidate_count'] >= diagnostic['max_candidates']:
                    raise ConnectionDiagnosticError('连接扫描候选数量异常，未选择角色对象。',
                                                    finish('candidate_budget_exhausted'))
                if not already_seen:
                    diagnostic['candidate_count'] += 1
                    seen[name].add(klass)
                    stats[name]['pointer_hits'] += 1
                info, reason = candidate(bounded, klass, specs[name], meta)
                if info:
                    found[name].setdefault(klass, info)
                else:
                    stats[name]['rejections'][reason] += 1

    class BoundedReader:
        # Candidate validation is part of the same budget, including strings
        # and FieldInfo reads; a pathological page cannot bypass the deadline.
        def read(self, address, size):
            return read(address, size)

        def u64(self, address):
            data = self.read(address, 8)
            return struct.unpack('<Q', data)[0] if len(data) == 8 else 0

        def string(self, address, limit=256):
            return self.read(address, limit).split(b'\0', 1)[0].decode('utf-8', errors='replace')

    bounded = BoundedReader()

    def short_page(page, page_size, part):
        diagnostic['short_pages'] += 1
        diagnostic['initial_short_bytes'] += page_size - len(part)
        if diagnostic['short_pages'] > MAX_RECHECK_PAGES:
            raise ConnectionDiagnosticError('连接扫描需要复查的页面过多，未发布可用连接。',
                                            finish('page_recheck_budget_exhausted'))
        # Keep bounded concrete evidence. The full work list is also bounded,
        # and every retry shares the original read/time budget.
        row = dict(address=hex(page), size=page_size, initial_read=len(part))
        if len(diagnostic['page_rechecks']) < 64:
            diagnostic['page_rechecks'].append(row)
        missing = page_size - len(part)
        if no_longer_committed(page, page_size):
            row['initial_state'] = 'proven_free_or_reserved'
            retired.append((page, page_size, row))
            diagnostic['retired_bytes'] += missing
        else:
            row['initial_state'] = 'committed_or_unproven'
            deferred.append((page, page_size, missing, row))
            diagnostic['unreadable_bytes'] += missing

    # Pointer matches are aligned to eight bytes, and all chunks/page boundaries
    # are aligned too. No pointer can straddle two complete chunks.
    for region in selected:
        end = region['base'] + region['size']
        for address in range(region['base'], end, 2 * 1024 * 1024):
            size = min(2 * 1024 * 1024, end - address)
            data = read(address, size)
            if len(data) == size:
                inspect(address, data)
            else:
                diagnostic['partial_reads'] += 1
                # Retry by page so one unavailable page cannot hide the rest of
                # its 2 MiB block. Do not count the partial block twice.
                for page in range(address, address + size, 4096):
                    page_size = min(4096, address + size - page)
                    part = read(page, page_size)
                    if len(part) < page_size:
                        short_page(page, page_size, part)
                    else:
                        inspect(page, part)
            if progress and clock() - last_progress > 1:
                progress({'resident_bytes_read': diagnostic['read_bytes'],
                          'seconds': round(clock() - start, 1),
                          'classes_found': sum(bool(v) for v in found.values())})
                last_progress = clock()
    # Read each unresolved page once after the main scan. An initial short read
    # is not evidence that the page will remain unreadable; equally, it cannot
    # be dropped merely because a valid class was already found elsewhere.
    # Inspect only complete reads, never combine partial bytes from two times.
    for page, page_size, old_missing, row in deferred:
        diagnostic['deferred_pages_rechecked'] += 1
        part = read(page, page_size)
        row['retry_read'] = len(part)
        if len(part) == page_size:
            diagnostic['unreadable_bytes'] -= old_missing
            diagnostic['recovered_pages'] += 1
            diagnostic['recovered_bytes'] += old_missing
            row['result'] = 'complete_reread'
            inspect(page, part, revisit=True)
        elif no_longer_committed(page, page_size):
            diagnostic['unreadable_bytes'] -= old_missing
            diagnostic['retired_bytes'] += page_size - len(part)
            row['result'] = 'became_free_or_reserved'
            retired.append((page, page_size, row))
        else:
            diagnostic['unreadable_bytes'] += page_size - len(part) - old_missing
            row['result'] = 'still_incomplete'

    # Recheck retired spans once at completion. Recommitted memory is scanned;
    # its failure or a new duplicate still invalidates the result. The scan is
    # a live observation, not an atomic process snapshot; final candidate and
    # object identity checks remain mandatory in discovery and every write.
    for page, page_size, row in retired:
        diagnostic['retired_pages_rechecked'] += 1
        if not no_longer_committed(page, page_size):
            part = read(page, page_size)
            row['final_read'] = len(part)
            row['result'] = 'recommitted_complete' if len(part) == page_size else 'recommitted_incomplete'
            if len(part) == page_size:
                inspect(page, part, revisit=True)
            diagnostic['unreadable_bytes'] += page_size - len(part)
        else:
            row['result'] = 'finally_free_or_reserved'
    if diagnostic['unreadable_bytes']:
        raise ConnectionDiagnosticError('部分游戏内存暂时无法完整读取，不能确认类型唯一性。请在读档完成后的稳定场景重新连接。',
                                        finish('incomplete_scan'))
    # Candidates can be invalidated during the several-second heap walk.
    # Never publish the early inspection after recovering missing pages.
    for name, classes in found.items():
        for klass, before in classes.items():
            diagnostic['candidate_rechecks'] += 1
            info, reason = candidate(bounded, klass, specs[name], meta)
            if info is None or info != before:
                stats[name]['rejections'][reason or 'class_changed_during_scan'] += 1
                raise ConnectionDiagnosticError('类型在扫描期间发生变化，未发布可用连接，请稳定后重试。',
                                                finish('candidate_changed'))
    missing = [n for n, candidates in found.items() if not candidates]
    ambiguous = [n for n, candidates in found.items() if len(candidates) > 1]
    if missing or ambiguous:
        parts = []
        if missing:
            parts.append('未识别到：' + '、'.join(n.rsplit('.', 1)[-1] for n in missing))
        if ambiguous:
            parts.append('存在多个候选：' + '、'.join(n.rsplit('.', 1)[-1] for n in ambiguous))
        raise ConnectionDiagnosticError('连接未完成。' + '；'.join(parts) + '。可复制诊断查看具体原因。',
                                        finish('missing_or_ambiguous'))
    if clock() - start > max_seconds:
        diagnostic['budget_reason'] = 'time_limit'
        raise ConnectionDiagnosticError('连接检查超过时间上限，未发布可用连接。', finish('budget_exhausted'))
    return {n: next(iter(v.values())) for n, v in found.items()}, finish('verified')
