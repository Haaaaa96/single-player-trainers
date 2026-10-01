"""One Frida agent lifetime per game process; no per-item unload/reinjection."""
from pathlib import Path
import json
import os
import threading
import time
import uuid

from write_guard import Refused

_CONNECTIONS = {}
_ORPHANED_SESSIONS = []
_LOCK = threading.Lock()
_TRAINER_INSTANCE = uuid.uuid4().hex
RESTART_REQUIRED = ('当前游戏保留了另一份或已关闭修改器的原生连接，无法由本修改器复用。'
                    '请先在游戏内保存并重启游戏，再重新连接；不要仅重启修改器。')


class NativeStartError(RuntimeError):
    def __init__(self, stage, original):
        super().__init__(str(original))
        self.stage = stage
        self.original = original


def check_connection_available(identity, epoch_path, check_existing_agent):
    """Read-only availability check; never claims, attaches, or clears history.

    This is an early UI explanation, not permission to skip the atomic claim at
    dispatch. A working connection owned by this trainer is always reused.
    """
    if (not isinstance(identity, tuple) or len(identity) != 2 or
            any(type(value) is not int or value <= 0 for value in identity)):
        raise Refused('缺少有效的游戏进程生命周期，未尝试注入。')
    with _LOCK:
        connection = _CONNECTIONS.get(identity)
        if connection is not None:
            if not connection.usable or connection.detached:
                raise Refused(RESTART_REQUIRED)
            if connection.owner is not None:
                raise Refused('原生连接仍有未结束的请求，请等待当前操作结束。')
            return
        from native_broker import broker_status
        status = broker_status(identity, epoch_path)
        if status is not None:
            if status.get('busy'):
                raise Refused('原生后台仍有未结束的请求，请等待当前操作结束。')
            if not status.get('ready'):
                raise Refused(status.get('reason') or '原生后台连接不可用，请保留日志并重启游戏。')
            return
        path = Path(epoch_path)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf8'))
                if data.get('version') != 1 or not isinstance(data.get('processes'), dict):
                    raise ValueError('invalid epoch schema')
            except Exception as error:
                raise Refused('原生连接记录无法读取；未尝试注入，请保留日志后检查。') from error
            if f'{identity[0]}:{identity[1]}' in data['processes']:
                raise Refused(RESTART_REQUIRED)
        claim = path.parent / 'native-epochs' / f'{identity[0]}-{identity[1]}.json'
        if claim.exists():
            raise Refused(RESTART_REQUIRED)
        check_existing_agent()


def _claim_epoch(path, identity):
    path = Path(path)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf8'))
            if data.get('version') != 1 or not isinstance(data.get('processes'), dict):
                raise ValueError('invalid epoch schema')
        except Exception as error:
            raise Refused('原生连接记录无法读取；未尝试注入，请保留日志后检查。') from error
    else:
        data = dict(version=1, processes={})
    key = f'{identity[0]}:{identity[1]}'
    if key in data['processes']:
        raise Refused(RESTART_REQUIRED)
    entry = dict(pid=identity[0], process_creation_filetime=identity[1],
                 trainer_instance=_TRAINER_INSTANCE,
                 attempted_at=time.time(), status='attach_attempted')
    # Exclusive file creation is the cross-process claim, not just a Python
    # lock: two independently launched trainers cannot both attach this game.
    directory = path.parent / 'native-epochs'
    claim = directory / f'{identity[0]}-{identity[1]}.json'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with claim.open('x', encoding='utf8') as handle:
            json.dump(entry, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise Refused('这个游戏进程已被另一修改器实例或先前连接使用。'
                      '请使用仍然打开的原修改器；原连接已关闭时，请先保存并重启游戏。') from error
    except Exception as error:
        raise Refused('无法保存原生连接记录，已拒绝注入；请检查日志目录。') from error


class NativeConnection:
    def __init__(self, identity, session):
        self.identity = identity
        self.session = session
        self.script = None
        self.owner = None
        self.callback = None
        self.detached_callback = None
        self.detached = False
        self.usable = False
        self.previous_token = None
        session.on('detached', self._on_detached)

    def _on_message(self, message, data):
        callback = self.callback
        if callback is not None:
            callback(message, data)

    def _on_detached(self, reason, *details):
        self.detached = True
        self.usable = False
        callback = self.detached_callback
        if callback is not None:
            callback(reason, *details)
        # The epoch remains on disk: transport loss is not permission to inject
        # another agent into a game process which may still be alive.

    def claim(self, owner, callback, detached_callback):
        if not self.usable or self.detached:
            raise Refused('原生连接已中断，不能在同一游戏进程重新加载；请先重启游戏。')
        if self.owner is not None:
            raise Refused('原生连接仍有未结束的请求，禁止再次获取。')
        self.owner = owner
        self.callback = callback
        self.detached_callback = detached_callback

    def prepare(self):
        if self.previous_token is not None:
            result = self.script.exports_sync.reset(self.previous_token)
            if not isinstance(result, dict) or result.get('status') != 'idle':
                raise Refused('上次原生请求尚未安全结束，禁止再次获取。')
            self.previous_token = None

    def release(self, owner):
        if self.owner is owner:
            self.owner = None
            self.callback = None
            self.detached_callback = None


def _acquire_local_connection(identity, frida, source, epoch_path, owner, callback,
                              detached_callback, before_attach, check_existing_agent):
    """Host-only agent ownership; the GUI must use acquire_connection below."""
    if (not isinstance(identity, tuple) or len(identity) != 2 or
            any(type(value) is not int or value <= 0 for value in identity)):
        raise Refused('缺少有效的游戏进程生命周期，未尝试注入。')
    with _LOCK:
        connection = _CONNECTIONS.get(identity)
        if connection is None:
            check_existing_agent()
            _claim_epoch(epoch_path, identity)
            before_attach()
            try:
                session = frida.attach(identity[0])
            except Exception as error:
                raise NativeStartError('attach', error) from error
            _ORPHANED_SESSIONS.append(session)
            try:
                connection = NativeConnection(identity, session)
            except Exception as error:
                raise NativeStartError('session_events', error) from error
            # Keep even an unusable session alive. A script setup error must
            # never turn into automatic agent unload followed by reinjection.
            _CONNECTIONS[identity] = connection
            stage = 'create_script'
            try:
                connection.script = session.create_script(source)
                connection.script.on('message', connection._on_message)
                stage = 'load_script'
                connection.script.load()
                connection.usable = not connection.detached
            except Exception as error:
                _ORPHANED_SESSIONS.append(connection)
                raise NativeStartError(stage, error) from error
        connection.claim(owner, callback, detached_callback)
        return connection


def acquire_connection(identity, frida, source, epoch_path, owner, callback,
                       detached_callback, before_attach, check_existing_agent):
    # All GUI/native features share this boundary. Only the persistent host
    # imports/uses Frida attachment, so closing the GUI cannot unload its agent.
    from native_broker import acquire_broker_connection
    return acquire_broker_connection(identity, source, epoch_path, owner, callback,
                                     detached_callback, before_attach, check_existing_agent)
