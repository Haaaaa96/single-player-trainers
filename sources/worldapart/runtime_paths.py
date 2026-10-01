"""Separate immutable bundle resources from persistent runtime and safety state."""
from pathlib import Path
import hashlib
import json
import os
import sys

FROZEN = bool(getattr(sys, 'frozen', False))
RESOURCE_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'WorldApartTrainer'
CACHE_ROOT = DATA_ROOT / 'cache' if FROZEN else RESOURCE_ROOT / 'game_runtime'
LOG_ROOT = DATA_ROOT / 'logs' if FROZEN else RESOURCE_ROOT / 'logs'
SAFETY_LOG_ROOT = DATA_ROOT / 'logs'
TERMINAL = frozenset(('verified', 'rejected', 'cancelled', 'not_dispatched'))


def migrate_safety_state(legacy_logs, target_logs):
    """Copy old guards once, without discarding a pending operation or epoch.

    Original files stay in place. Both source and frozen applications subsequently
    use target_logs, so moving/renaming the EXE cannot reset injection history.
    """
    legacy_logs, target_logs = Path(legacy_logs), Path(target_logs)
    target_logs.mkdir(parents=True, exist_ok=True)
    if legacy_logs.resolve() == target_logs.resolve() or not legacy_logs.is_dir():
        return
    tag = hashlib.sha256(str(legacy_logs.resolve()).casefold().encode()).hexdigest()[:20]
    marker = target_logs / ('migrated-' + tag + '.json')
    if marker.exists():
        return
    source = legacy_logs / 'acquisition-pending.json'
    destination = target_logs / source.name
    if source.exists():
        old = json.loads(source.read_text(encoding='utf8'))
        if not isinstance(old, dict) or 'status' not in old:
            raise RuntimeError('旧物品操作记录无法核对，请保留日志后检查。')
        if destination.exists():
            current = json.loads(destination.read_text(encoding='utf8'))
            # Never replace a current pending state. A different pending legacy
            # operation needs human review before either record can be cleared.
            if old != current and (old.get('status') not in TERMINAL or old.get('native_block_reason')):
                raise RuntimeError('发现另一份未确认的旧物品操作，请核对日志后再连接。')
        else:
            with destination.open('xb') as output:
                output.write(source.read_bytes())
                output.flush()
                os.fsync(output.fileno())
    epochs = legacy_logs / 'acquisition-native-epochs.json'
    if epochs.exists():
        old = json.loads(epochs.read_text(encoding='utf8'))
        if old.get('version') != 1 or not isinstance(old.get('processes'), dict):
            raise RuntimeError('旧原生连接记录无法核对，请保留日志后检查。')
        # Epoch claims are authoritative even when the older aggregate record
        # has not been written by a newer trainer version.
        claims = target_logs / 'native-epochs'
        claims.mkdir(exist_ok=True)
        for key, event in old['processes'].items():
            pid, created = key.split(':')
            if not pid.isdecimal() or not created.isdecimal():
                raise RuntimeError('旧原生连接进程标识无效。')
            claim = claims / f'{int(pid)}-{int(created)}.json'
            try:
                with claim.open('x', encoding='utf8') as output:
                    json.dump(event, output, ensure_ascii=False)
            except FileExistsError:
                pass  # An existing claim already prevents reinjection.
    old_claims = legacy_logs / 'native-epochs'
    if old_claims.is_dir():
        new_claims = target_logs / 'native-epochs'
        new_claims.mkdir(exist_ok=True)
        for source in old_claims.glob('*.json'):
            if not all(x.isdecimal() for x in source.stem.split('-')) or source.stem.count('-') != 1:
                raise RuntimeError('旧原生连接文件名无效。')
            try:
                with (new_claims / source.name).open('xb') as output:
                    output.write(source.read_bytes())
            except FileExistsError:
                pass
    temporary = marker.with_suffix('.tmp')
    temporary.write_text(json.dumps({'legacy_logs': str(legacy_logs.resolve()), 'copied': True}), encoding='utf8')
    temporary.replace(marker)


def initialize_runtime(legacy_root=None):
    """Called before the first adapter connection; imports alone do not write."""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    SAFETY_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    if not FROZEN:
        migrate_safety_state(Path(legacy_root or RESOURCE_ROOT) / 'logs', SAFETY_LOG_ROOT)
    else:
        # Supports upgrading a source installation in-place, without embedding
        # development-machine paths into the distributable.
        migrate_safety_state(Path(sys.executable).resolve().parent / 'logs', SAFETY_LOG_ROOT)
    return SAFETY_LOG_ROOT
