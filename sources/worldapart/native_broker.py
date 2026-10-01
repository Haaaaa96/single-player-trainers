"""Authenticated local client for a game-lifetime native connection host.

The host outlives GUI windows. IPC uses bounded JSON frames, never pickle, and
the pipe credential is protected for the current Windows user with DPAPI.
"""
import base64
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from multiprocessing.connection import Client
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid

from write_guard import Refused

PROTOCOL = 1
MAX_MESSAGE = 8 * 1024 * 1024
CONNECT_TIMEOUT = 3
# Console detachment/process groups do not detach a Windows Job. Explicitly
# escape an allowed caller Job; do not silently retry without this protection.
HOST_CREATION_FLAGS = 0x09000208  # BREAKAWAY_FROM_JOB | NO_WINDOW | NEW_PROCESS_GROUP | DETACHED_PROCESS
_CLIENTS = {}
_HOST_PROCESSES = []
_CLIENT_LOCK = threading.RLock()
_PIPE_RE = re.compile(r'\\\\\.\\pipe\\WorldApartTrainer-[0-9a-f]{32}\Z')


class _JobBasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong),
                ('flags', W.DWORD), ('minimum_working_set', C.c_size_t),
                ('maximum_working_set', C.c_size_t), ('active_process_limit', W.DWORD),
                ('affinity', C.c_size_t), ('priority_class', W.DWORD),
                ('scheduling_class', W.DWORD)]


def current_job_details():
    """Query only the calling process; never alter any existing Job/process."""
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    kernel.IsProcessInJob.argtypes = [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)]
    kernel.IsProcessInJob.restype = W.BOOL
    kernel.QueryInformationJobObject.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p]
    kernel.QueryInformationJobObject.restype = W.BOOL
    inside = W.BOOL()
    if not kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, C.byref(inside)):
        raise C.WinError(C.get_last_error())
    if not inside.value:
        return dict(in_job=False, job_limit_flags=0)
    limits = _JobBasicLimits()
    if not kernel.QueryInformationJobObject(None, 2, C.byref(limits), C.sizeof(limits), None):
        raise C.WinError(C.get_last_error())
    return dict(in_job=True, job_limit_flags=int(limits.flags))


_LIFECYCLE_FIELDS = frozenset(('host_pid', 'host_created', 'parent_pid', 'child_pid',
    'in_job', 'job_limit_flags', 'frozen', 'exit_code', 'error_type', 'winerror',
    'connected', 'busy', 'ready', 'monitor_uncertain', 'reason_code', 'has_connection', 'unsafe', 'inflight'))


def record_host_lifecycle(epoch_path, stage, identity=None, **details):
    """Best-effort diagnostics with a fixed nonsecret field whitelist.

    Never record pipe addresses, DPAPI blobs, source code, arbitrary exception
    strings, or request payloads. Diagnostic failure must not change a dispatch
    outcome or grant permission to reattach.
    """
    try:
        if not isinstance(stage, str) or not re.fullmatch('[a-z_]{1,48}', stage):
            return
        value = dict(time=time.time(), pid=os.getpid(), stage=stage)
        if identity is not None:
            pid, created = _identity(identity)
            value.update(game_pid=pid, game_created=created)
        for key, item in details.items():
            if key in _LIFECYCLE_FIELDS and (item is None or type(item) in (bool, int)
                    or isinstance(item, str) and re.fullmatch('[a-zA-Z0-9_-]{1,80}', item)):
                value[key] = item
        directory = Path(epoch_path).parent / 'native-host-lifecycle'
        directory.mkdir(parents=True, exist_ok=True)
        # Each process owns its log. A single append write also bounds threaded
        # interleaving without introducing a lock into native outcome handling.
        path = directory / f'{os.getpid()}.jsonl'
        data = (json.dumps(value, allow_nan=False, separators=(',', ':'))+'\n').encode('utf8')
        handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(handle, data)
        finally:
            os.close(handle)
    except Exception:
        pass


def encode(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf8')
    if len(data) > MAX_MESSAGE:
        raise Refused('原生后台请求过大，未发送。')
    return data


def decode(data):
    if len(data) > MAX_MESSAGE:
        raise Refused('原生后台消息过大。')
    value = json.loads(data.decode('utf8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(value, dict):
        raise Refused('原生后台消息格式无效。')
    return value


class _Blob(C.Structure):
    _fields_ = [('size', W.DWORD), ('data', C.POINTER(C.c_ubyte))]


def _crypt(data, decrypt=False):
    crypt = C.WinDLL('crypt32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [C.POINTER(_Blob), C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, W.DWORD, C.POINTER(_Blob)]
    fn.restype = W.BOOL
    kernel.LocalFree.argtypes = [C.c_void_p]
    kernel.LocalFree.restype = C.c_void_p
    raw = (C.c_ubyte * len(data)).from_buffer_copy(data)
    source, result = _Blob(len(data), raw), _Blob()
    if not fn(C.byref(source), None, None, None, None, 1, C.byref(result)):
        raise C.WinError(C.get_last_error())
    try:
        return C.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def protect(key):
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError('Expected a 32-byte pipe credential')
    return base64.b64encode(_crypt(key)).decode('ascii')


def unprotect(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise Refused('原生后台凭据无效。')
    result = _crypt(base64.b64decode(value, validate=True), decrypt=True)
    if len(result) != 32:
        raise Refused('原生后台凭据长度无效。')
    return result


def host_identity(pid):
    from native_write import process_identity
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel.OpenProcess.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise C.WinError(C.get_last_error())
    try:
        return process_identity(handle)
    finally:
        kernel.CloseHandle(handle)


def _identity(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2 or
            any(type(x) is not int or x <= 0 for x in value)):
        raise Refused('原生后台进程身份无效。')
    return tuple(value)


def endpoint_path(identity, epoch_path):
    pid, created = _identity(identity)
    return Path(epoch_path).parent / 'native-hosts' / f'{pid}-{created}.json'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf8') as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            import os
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_endpoint(path, identity):
    path = Path(path)
    if not path.exists():
        return None
    if path.stat().st_size > 16384:
        raise Refused('原生后台连接记录过大；已停止连接。')
    try:
        value = json.loads(path.read_text(encoding='utf8'))
        if (value.get('protocol') != PROTOCOL or _identity(value.get('identity')) != _identity(identity)
                or not isinstance(value.get('pipe'), str) or not _PIPE_RE.fullmatch(value['pipe'])
                or type(value.get('host_pid')) is not int or value['host_pid'] <= 0
                or type(value.get('host_created')) is not int or value['host_created'] <= 0):
            raise ValueError('Invalid endpoint descriptor')
        return value
    except Exception as error:
        raise Refused('原生后台连接记录无效；请保留日志后检查。') from error


def endpoint_alive(value):
    try:
        return host_identity(value['host_pid'])[1] == value['host_created']
    except (OSError, Refused):
        return False


def _connect_transport(descriptor):
    """Bound pipe opening AND authentication; close any late connection."""
    done, lock, state = threading.Event(), threading.Lock(), dict(expired=False)
    def connect():
        transport = None
        try:
            transport = Client(descriptor['pipe'], family='AF_PIPE', authkey=unprotect(descriptor['auth_protected']))
            with lock:
                if state['expired']:
                    transport.close()
                else:
                    state['transport'] = transport
        except Exception as error:
            with lock:
                state['error'] = error
        finally:
            done.set()
    threading.Thread(target=connect, daemon=True, name='WorldApartTrainer-native-connect').start()
    if not done.wait(CONNECT_TIMEOUT):
        with lock:
            state['expired'] = True
            transport = state.pop('transport', None)
        if transport is not None:
            transport.close()
        raise Refused('原生后台连接或认证超时；不会重复启动或加载组件。')
    if 'error' in state:
        raise Refused('原生后台连接或认证失败；未重试。') from state['error']
    return state['transport']


@contextmanager
def startup_lock(path):
    """A kernel mutex releases on crash; stale files never authorize a retry."""
    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
    kernel.CreateMutexW.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.ReleaseMutex.argtypes = [W.HANDLE]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    name = 'Local\\WorldApartTrainer-NativeHost-' + hashlib.sha256(str(Path(path).resolve()).casefold().encode()).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise C.WinError(C.get_last_error())
    acquired = False
    try:
        result = kernel.WaitForSingleObject(handle, 12000)
        acquired = result in (0, 0x80)
        if not acquired:
            raise Refused('原生后台正在启动，请稍后重试连接；未重复启动。')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _epoch_exists(identity, path):
    path = Path(path)
    if (path.parent / 'native-epochs' / f'{identity[0]}-{identity[1]}.json').exists():
        return True
    if not path.exists():
        return False
    try:
        value = json.loads(path.read_text(encoding='utf8'))
        if value.get('version') != 1 or not isinstance(value.get('processes'), dict):
            raise ValueError('Invalid epoch')
        return f'{identity[0]}:{identity[1]}' in value['processes']
    except Exception as error:
        raise Refused('原生连接记录无法读取；未启动后台或注入。') from error


class RemoteConnection:
    def __init__(self, descriptor, transport=None):
        self.identity = _identity(descriptor['identity'])
        self.transport = transport or _connect_transport(descriptor)
        self.session = self
        self.script = SimpleNamespace(exports_sync=SimpleNamespace(submit=self.submit))
        self.owner = self.callback = self.detached_callback = None
        self.previous_token = None
        self.usable, self.detached = True, False
        self._pending, self._pending_lock, self._send_lock = {}, threading.Lock(), threading.Lock()
        self._thread = threading.Thread(target=self._read, daemon=True, name='WorldApartTrainer-native-events')
        self._thread.start()

    def _read(self):
        try:
            while True:
                value = decode(self.transport.recv_bytes(MAX_MESSAGE))
                if value.get('event') == 'message':
                    callback = self.callback
                    if callback is not None:
                        callback(value['message'], None)
                elif value.get('event') == 'detached':
                    callback = self.detached_callback
                    self.usable, self.detached = False, True
                    if callback is not None:
                        callback(value.get('reason', 'connection-terminated'))
                elif isinstance(value.get('id'), str):
                    with self._pending_lock:
                        pending = self._pending.get(value['id'])
                    if pending is not None:
                        pending['response'] = value
                        pending['event'].set()
                else:
                    raise Refused('原生后台返回了未知消息。')
        except Exception:
            self.usable, self.detached = False, True
            try:
                self.transport.close()
            except Exception:
                pass
            with self._pending_lock:
                for pending in self._pending.values():
                    pending['event'].set()
            callback = self.detached_callback
            if callback is not None:
                callback('connection-terminated')

    def call(self, command, payload=None, timeout=15):
        if not self.usable or self.detached:
            raise Refused('原生后台连接已中断；不自动重发游戏操作，请保留日志并检查。')
        request_id = uuid.uuid4().hex
        pending = dict(event=threading.Event())
        with self._pending_lock:
            self._pending[request_id] = pending
        try:
            frame = encode(dict(id=request_id, command=command, payload=payload or {}))
            def send():
                try:
                    with self._send_lock:
                        # Never transmit a queued command after its caller's
                        # deadline or after an earlier transport failure.
                        if not self.usable or self.detached:
                            raise Refused('原生后台连接已中断，未重发请求。')
                        self.transport.send_bytes(frame)
                except Exception as error:
                    pending['send_error'] = error
                    pending['event'].set()
            threading.Thread(target=send, daemon=True, name='WorldApartTrainer-native-send').start()
            if not pending['event'].wait(timeout) or 'response' not in pending:
                self.close_transport()
                raise Refused('等待原生后台响应失败；不会自动重发游戏操作。')
            response = pending['response']
            if response.get('ok') is not True:
                if response.get('kind') == 'native_start':
                    from native_acquisition_session import NativeStartError
                    raise NativeStartError(response.get('stage', 'host'), RuntimeError(response.get('error', 'Host error')))
                raise Refused(response.get('error', '原生后台拒绝了请求。'))
            return response.get('result')
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def claim(self, owner, callback, detached_callback, source):
        if self.owner is not None:
            raise Refused('原生后台仍有未结束的请求。')
        self.owner, self.callback, self.detached_callback = owner, callback, detached_callback
        try:
            self.call('claim', dict(source=source, source_sha256=hashlib.sha256(source.encode('utf8')).hexdigest()))
        except Exception:
            self.owner = self.callback = self.detached_callback = None
            self.close_transport()  # Let the host release a late, unused claim.
            raise

    def prepare(self):
        self.call('prepare')
        self.previous_token = None

    def submit(self, request):
        return self.call('submit', dict(request=request))

    def release(self, owner):
        if self.owner is owner:
            try:
                if self.usable and not self.detached:
                    self.call('release', timeout=3)
            except Exception:
                # Release failure is not authority to inject another host.
                self.close_transport()
            finally:
                self.owner = self.callback = self.detached_callback = None

    def close_transport(self):
        self.usable, self.detached = False, True
        self.transport.close()


def _connect_existing(descriptor):
    if not endpoint_alive(descriptor):
        return None
    proxy = None
    try:
        proxy = RemoteConnection(descriptor)
        status = proxy.call('status', timeout=3)
        if _identity(status.get('identity')) != _identity(descriptor['identity']):
            proxy.close_transport()
            raise Refused('原生后台对应其他游戏进程，未连接。')
        return proxy
    except Exception as error:
        if proxy is not None:
            proxy.close_transport()
        raise Refused('原生后台仍在运行但无法通信；请保留日志，不会重复加载组件。') from error


def _start_host(identity, epoch_path, path):
    config = dict(protocol=PROTOCOL, identity=list(identity), pipe='\\\\.\\pipe\\WorldApartTrainer-' + uuid.uuid4().hex,
                  auth_protected=protect(os.urandom(32)))
    startup = path.with_name(path.stem + '.' + uuid.uuid4().hex + '.startup.json')
    atomic_json(startup, config)
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command.append(str(Path(__file__).resolve().with_name('standalone_entry.py')))
    command.extend(['--native-host', str(startup)])
    environment = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1')
    try:
        job = current_job_details()
    except Exception as error:
        job = dict(error_type=type(error).__name__)
    record_host_lifecycle(epoch_path, 'launch_requested', identity, frozen=bool(getattr(sys, 'frozen', False)), **job)
    try:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 close_fds=True, creationflags=HOST_CREATION_FLAGS, env=environment)
    except Exception as error:
        record_host_lifecycle(epoch_path, 'launch_failed', identity,
                              error_type=type(error).__name__, winerror=getattr(error, 'winerror', None))
        try:
            startup.unlink(missing_ok=True)
        except OSError:
            pass  # This unused startup file never grants an epoch/attach claim.
        raise Refused('无法独立启动原生后台，未加载游戏组件；请从普通桌面启动修改器并保留日志。') from error
    record_host_lifecycle(epoch_path, 'launch_created', identity, child_pid=child.pid)
    _HOST_PROCESSES.append(child)  # Outliving this GUI is intentional, never terminate on close.
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        descriptor = read_endpoint(path, identity)
        if descriptor is not None and descriptor.get('pipe') == config['pipe']:
            proxy = _connect_existing(descriptor)
            if proxy is not None:
                record_host_lifecycle(epoch_path, 'launch_ready', identity, host_pid=descriptor['host_pid'], host_created=descriptor['host_created'])
                return proxy
        code = child.poll()
        if code is not None:
            record_host_lifecycle(epoch_path, 'launch_exited', identity, child_pid=child.pid, exit_code=code)
            raise Refused('原生后台启动后已退出，未自动重试；请保留后台生命周期日志后检查。')
        time.sleep(0.1)
    record_host_lifecycle(epoch_path, 'launch_timeout', identity, child_pid=child.pid)
    raise Refused('原生后台未能启动；未重试加载，请保留日志后检查。')


def acquire_broker_connection(identity, source, epoch_path, owner, callback, detached_callback,
                              before_attach, check_existing_agent):
    from native_acquisition_session import RESTART_REQUIRED
    identity = _identity(identity)
    with _CLIENT_LOCK:
        proxy = _CLIENTS.get(identity)
        if proxy is None or not proxy.usable or proxy.detached:
            path = endpoint_path(identity, epoch_path)
            with startup_lock(path):
                descriptor = read_endpoint(path, identity)
                proxy = _connect_existing(descriptor) if descriptor is not None else None
                if proxy is None:
                    if _epoch_exists(identity, epoch_path):
                        record_host_lifecycle(epoch_path, 'epoch_without_live_host', identity,
                            host_pid=descriptor['host_pid'] if descriptor else None,
                            host_created=descriptor['host_created'] if descriptor else None)
                        raise Refused(RESTART_REQUIRED)
                    try:
                        check_existing_agent()
                    except Exception as error:
                        record_host_lifecycle(epoch_path, 'prelaunch_agent_check_failed', identity,
                            error_type=type(error).__name__,
                            reason_code='unmanaged_agent' if '不能复用的原生连接组件' in str(error) else 'other')
                        raise
                    proxy = _start_host(identity, epoch_path, path)
                _CLIENTS[identity] = proxy
        # The host durably claims the epoch before attaching. Do not label a
        # GUI journal "attaching" for a reuse/busy rejection: no game method
        # has been dispatched and the caller's not_dispatched remains valid.
        proxy.claim(owner, callback, detached_callback, source)
        return proxy


def broker_status(identity, epoch_path):
    """Read-only: no process creation, files, claims, Frida imports, or attach."""
    identity = _identity(identity)
    with _CLIENT_LOCK:
        proxy = _CLIENTS.get(identity)
        if proxy is not None and proxy.usable and not proxy.detached:
            return proxy.call('status', timeout=3)
    descriptor = read_endpoint(endpoint_path(identity, epoch_path), identity)
    if descriptor is None:
        return None
    proxy = _connect_existing(descriptor)
    if proxy is None:
        return None
    try:
        return proxy.call('status', timeout=3)
    finally:
        proxy.close_transport()
