"""Game-lifetime owner of the shared Frida session; bounded authenticated JSON IPC.

GUI EOF releases only a definitely idle/safely terminal owner. A request whose
outcome is unknown remains locked even if every GUI has disappeared.
"""
import hashlib
import math
import ctypes as C
from ctypes import wintypes as W
from multiprocessing.connection import Listener, deliver_challenge, answer_challenge
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
from types import SimpleNamespace

from native_broker import (PROTOCOL, MAX_MESSAGE, _PIPE_RE, _identity, atomic_json,
                          decode, encode, endpoint_path, host_identity, startup_lock, unprotect,
                          current_job_details, record_host_lifecycle)
from native_acquisition_session import NativeStartError
from write_guard import Refused

OPERATIONS = frozenset(('add', 'remove_test_uid', 'meridian_solve', 'character_growth_set',
                        'character_interact_set', 'current_stamina_set', 'current_health_set', 'current_mana_set'))
SAFE_TERMINALS = frozenset(('completed', 'rejected', 'cancelled'))


def _safe_result(result):
    return (isinstance(result, dict) and result.get('status') in SAFE_TERMINALS and
            (result['status'] == 'completed' or result.get('called') is False))


def checked_game(identity):
    path, created = host_identity(identity[0])
    if created != identity[1] or Path(path).name.casefold() != 'worldapart.exe':
        raise Refused('原生后台对应的游戏进程已退出或更换。')
    return path


def check_attach_target(identity):
    """Independent strict read-only check immediately before the epoch claim."""
    from game_adapter import probe
    from game_connection import _module_paths, _verified_engine_modules
    from acquisition_adapter import require_no_unmanaged_agent
    from native_write import process_identity
    path = checked_game(identity)
    reader = probe.Reader(identity[0], expected_path=path)
    try:
        if process_identity(reader.h)[1] != identity[1]:
            raise Refused('检查期间游戏进程已变化。')
        _verified_engine_modules(_module_paths(identity[0]), reader.installation)
        require_no_unmanaged_agent(SimpleNamespace(reader=reader))
        checked_game(identity)
    finally:
        reader.close()


def acquire_local(identity, source, epoch_path, owner, on_message, on_detached):
    # Source deployments keep their pinned Frida in vendor. The GUI normally
    # initializes this path via acquisition_adapter; the independent host must
    # perform the same bootstrap before importing the dependency.
    import acquisition_adapter
    import frida
    from native_acquisition_session import _acquire_local_connection
    if frida.__version__ != '17.7.3':
        raise Refused('原生后台连接组件版本不匹配。')
    return _acquire_local_connection(identity, frida, source, epoch_path, owner, on_message,
        on_detached, lambda: None, lambda: check_attach_target(identity))


class BrokerHost:
    """Transport-independent state machine, injectable for offline mock tests."""
    def __init__(self, identity, epoch_path, *, acquire=acquire_local, check_game=checked_game):
        self.identity, self.epoch_path = _identity(identity), Path(epoch_path)
        self.acquire, self.check_game = acquire, check_game
        self.connection = self.owner = None
        self.source_sha256 = None
        self.operations = OPERATIONS
        self.token = None
        self.results, self.used_tokens = {}, set()
        self.inflight = self.unsafe = self.prepared = self.stopped = self.scalar = self.monitor_uncertain = False
        self.lock = threading.RLock()
        self.peers = set()
        self.events = queue.Queue()
        threading.Thread(target=self._events, daemon=True, name='WorldApartTrainer-host-events').start()

    def status(self):
        with self.lock:
            connected = self.connection is not None and self.connection.usable and not self.connection.detached
            return dict(identity=list(self.identity), ready=not self.stopped and not self.unsafe and not self.monitor_uncertain and
                        (self.connection is None or connected), busy=self.owner is not None or self.inflight or self.unsafe,
                        connected=bool(connected), source_sha256=self.source_sha256)

    def _check(self):
        if self.stopped or self.monitor_uncertain:
            raise Refused('原生后台已停止。')
        self.check_game(self.identity)

    def _send(self, peer, value):
        if peer is not None and peer.alive:
            try:
                peer.send(value)
            except Exception:
                self.disconnect(peer)

    def _release(self):
        if self.owner is not None and self.connection is not None and not self.scalar:
            self.connection.release(self.owner)
        self.owner = None
        self.prepared = self.scalar = False

    def disconnect(self, peer):
        with self.lock:
            peer.alive = False
            self.peers.discard(peer)
            if self.owner is peer:
                if self.scalar:
                    self.unsafe = True
                elif not self.inflight and not self.unsafe:
                    self._release()

    def on_message(self, message, _data=None):
        # Frida may deliver a message before a synchronous RPC returns. Its
        # callback thread must never wait on dispatch's lock or pipe I/O.
        if isinstance(message, dict) and message.get('type') in ('send', 'error'):
            self.events.put(('message', message))

    def on_detached(self, reason, *_details):
        self.events.put(('detached', str(reason)))

    def _events(self):
        while True:
            event = self.events.get()
            try:
                if event is None:
                    return
                if event[0] == 'message':
                    self._handle_message(event[1])
                else:
                    self._handle_detached(event[1])
            finally:
                self.events.task_done()

    def _handle_message(self, message):
        with self.lock:
            if message.get('type') == 'send':
                result = message.get('payload')
                if not isinstance(result, dict) or not self.token or result.get('token') != self.token:
                    return
                status = result.get('status')
                if not isinstance(status, str) or status not in SAFE_TERMINALS | {'exception', 'unknown'}:
                    return
                # Never accept a second terminal result that would unlock an
                # earlier unknown outcome. The game operation is not retried.
                if self.token in self.results:
                    return
                self.results[self.token] = dict(result)
                self.inflight = False
                self.unsafe = not _safe_result(result)
            elif message.get('type') == 'error':
                self.inflight, self.unsafe = False, True
                if self.token and self.token not in self.results:
                    self.results[self.token] = dict(token=self.token, status='unknown', called=None,
                                                   reason='Native script error')
            else:
                return
            owner = self.owner
            self._send(owner, dict(event='message', message=message))
            if owner is not None and not owner.alive and not self.inflight and not self.unsafe:
                self._release()

    def _handle_detached(self, reason):
        with self.lock:
            record_host_lifecycle(self.epoch_path, 'session_detached', self.identity,
                reason_code=reason if reason in ('process-terminated','process-replaced','connection-terminated','application-requested','device-lost') else 'other')
            self.unsafe = True
            if self.token and self.token not in self.results:
                self.results[self.token] = dict(token=self.token, status='unknown', called=None, reason=str(reason))
            self._send(self.owner, dict(event='detached', reason=str(reason)))

    def _require_owner(self, peer):
        if self.owner is not peer or not peer.alive or self.connection is None or self.scalar:
            raise Refused('此窗口未拥有当前原生请求。')
        if self.unsafe or not self.connection.usable or self.connection.detached:
            raise Refused('原生请求结果未确认，禁止再次执行。')

    def _prepare(self):
        self.prepared = False
        if self.inflight:
            raise Refused('原生请求仍在执行。')
        # Verify the actual JS state, not only GUI/IPC delivery bookkeeping.
        state = self.connection.script.exports_sync.status()
        if not isinstance(state, dict):
            raise Refused('原生脚本状态无效。')
        if state.get('status') != 'idle':
            if (not self.token or state.get('token') != self.token or not _safe_result(state)):
                raise Refused('上次原生请求尚未安全结束。')
            self.connection.previous_token = self.token
            self.connection.prepare()
            state = self.connection.script.exports_sync.status()
            if not isinstance(state, dict) or state.get('status') != 'idle':
                raise Refused('原生脚本未回到空闲状态。')
        elif self.connection.previous_token is not None:
            raise Refused('原生脚本与后台令牌状态不一致。')
        # Feature implementations are replaced with the reviewed JS in the
        # existing session. Learn its bounded whitelist only while idle, so a
        # future feature does not require unloading the native agent/host.
        operations = state.get('operations')
        if 'operations' not in state:
            self.operations = OPERATIONS  # Older compatible bridge contract.
        else:
            if (not isinstance(operations, list) or not 1 <= len(operations) <= 128
                    or any(not isinstance(op, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', op) for op in operations)
                    or len(set(operations)) != len(operations)):
                raise Refused('空闲原生脚本返回了无效功能白名单。')
            self.operations = frozenset(operations)
        self.prepared = True

    def _replace_source(self, source, digest):
        self._prepare()
        record_host_lifecycle(self.epoch_path, 'script_replace_started', self.identity)
        try:
            self.connection.script.unload()
            script = self.connection.session.create_script(source)
            script.on('message', self.connection._on_message)
            self.connection.script = script
            script.load()
            if self.connection.detached:
                raise RuntimeError('Session detached during script replacement')
            self.source_sha256 = digest
            self.prepared = False
            record_host_lifecycle(self.epoch_path, 'script_replace_ready', self.identity)
        except Exception as error:
            record_host_lifecycle(self.epoch_path, 'script_replace_failed', self.identity, error_type=type(error).__name__)
            self.connection.usable = False
            self.unsafe = True
            raise NativeStartError('replace_script', error) from error

    def _claim(self, peer, payload):
        record_host_lifecycle(self.epoch_path, 'claim_received', self.identity,
            has_connection=self.connection is not None, unsafe=self.unsafe, inflight=self.inflight,
            busy=self.owner is not None)
        source, digest = payload.get('source'), payload.get('source_sha256')
        if (set(payload) != {'source', 'source_sha256'} or not isinstance(source, str) or
                not 1 <= len(source.encode('utf8')) <= 2 * 1024 * 1024 or not isinstance(digest, str) or
                not re.fullmatch('[0-9a-f]{64}', digest) or hashlib.sha256(source.encode('utf8')).hexdigest() != digest):
            raise Refused('原生脚本摘要或大小无效。')
        if self.owner is not None or self.inflight or self.unsafe:
            record_host_lifecycle(self.epoch_path, 'claim_rejected', self.identity,
                                 reason_code='busy_or_unsafe', has_connection=self.connection is not None)
            raise Refused('原生后台仍有未安全结束的请求。')
        self.owner = peer
        try:
            if self.connection is None:
                record_host_lifecycle(self.epoch_path, 'first_connection_started', self.identity)
                self.connection = self.acquire(self.identity, source, self.epoch_path, peer,
                                               self.on_message, self.on_detached)
                self.source_sha256 = digest
                record_host_lifecycle(self.epoch_path, 'first_connection_ready', self.identity)
            else:
                self.connection.claim(peer, self.on_message, self.on_detached)
                if digest != self.source_sha256:
                    self._replace_source(source, digest)
            self.prepared = False
            return self.status()
        except Exception as error:
            record_host_lifecycle(self.epoch_path, 'claim_failed', self.identity,
                error_type=type(error).__name__,
                has_connection=self.connection is not None, unsafe=self.unsafe,
                reason_code='unmanaged_agent' if '不能复用的原生连接组件' in str(error) else
                    error.stage if isinstance(error, NativeStartError) and error.stage in
                    ('attach','create_script','load_script','session_events','replace_script') else 'other')
            # A partial attach/replacement is not eligible for another load.
            if self.connection is None or not self.connection.usable or self.connection.detached:
                self.unsafe = True
            if not self.unsafe:
                self._release()
            raise

    def _submit(self, peer, payload):
        self._require_owner(peer)
        request = payload.get('request')
        if set(payload) != {'request'} or not isinstance(request, dict):
            raise Refused('原生请求格式无效。')
        token = request.get('token')
        deadline = request.get('deadline')
        if (request.get('operation') not in self.operations or type(request.get('pid')) is not int or request['pid'] != self.identity[0]
                or not isinstance(token, str) or not 1 <= len(token) <= 128 or token in self.used_tokens
                or type(deadline) not in (int, float) or not math.isfinite(deadline)
                or not time.time() * 1000 < deadline <= time.time() * 1000 + 15000
                or not isinstance(request.get('anchors'), list) or not 1 <= len(request['anchors']) <= 20000):
            raise Refused('原生请求身份、时限或白名单无效。')
        if not self.prepared or self.inflight or len(self.used_tokens) >= 100000:
            raise Refused('原生请求尚未准备或数量超出当前进程限制。')
        self.used_tokens.add(token)
        self.token = self.connection.previous_token = token
        self.inflight, self.prepared = True, False
        try:
            result = self.connection.script.exports_sync.submit(request)
            if not isinstance(result, dict) or result.get('token') != token or result.get('status') not in (
                    'pending', 'completed', 'rejected', 'cancelled', 'exception', 'unknown'):
                raise RuntimeError('Invalid native submit response')
            return result
        except Exception:
            # RPC failure cannot prove whether Unity already received the hook.
            self.unsafe = True
            self.results.setdefault(token, dict(token=token, status='unknown', called=None, reason='Submit response lost'))
            raise

    def dispatch(self, peer, value):
        request_id = value.get('id') if isinstance(value, dict) else None
        try:
            if (not isinstance(value, dict) or set(value) != {'id', 'command', 'payload'} or
                    not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id) or
                    request_id in peer.request_ids or len(peer.request_ids) >= 100000 or not isinstance(value['payload'], dict)):
                raise Refused('原生后台命令格式或编号无效。')
            peer.request_ids.add(request_id)
            command, payload = value['command'], value['payload']
            with self.lock:
                self._check()
                if command == 'status' and not payload:
                    result = self.status()
                elif command == 'claim_scalar' and not payload:
                    if not self.status()['ready'] or self.owner is not None or self.inflight or self.unsafe:
                        raise Refused('原生后台仍有未结束的操作，暂不能直接修改数值。')
                    self.owner, self.scalar = peer, True
                    result = dict(claimed=True)
                elif command == 'release_scalar' and set(payload) <= {'uncertain'} and type(payload.get('uncertain', False)) is bool:
                    if self.owner is not peer or not self.scalar:
                        raise Refused('此窗口未持有数值修改锁。')
                    if payload.get('uncertain', False):
                        self.unsafe = True
                        result = dict(released=False, uncertain=True)
                    elif self.unsafe:
                        raise Refused('数值修改结果未确认，不能解除安全锁。')
                    else:
                        self._release()
                        result = dict(released=True)
                elif command == 'claim':
                    result = self._claim(peer, payload)
                elif command == 'prepare' and not payload:
                    self._require_owner(peer)
                    self._prepare()
                    result = dict(status='idle')
                elif command == 'submit':
                    result = self._submit(peer, payload)
                elif command == 'release' and not payload:
                    self._require_owner(peer)
                    if self.inflight:
                        raise Refused('原生调用尚未结束，不能释放所有权。')
                    self._prepare()
                    self._release()
                    result = dict(released=True)
                elif command == 'request_status' and set(payload) == {'token'} and isinstance(payload['token'], str):
                    token = payload['token']
                    result = self.results.get(token, dict(token=token, status='pending' if token == self.token and self.inflight else 'not_found'))
                else:
                    raise Refused('未知原生后台命令。')
            return dict(id=request_id, ok=True, result=result)
        except Exception as error:
            kind = 'native_start' if isinstance(error, NativeStartError) else 'refused' if isinstance(error, Refused) else 'unknown'
            result = dict(id=request_id, ok=False, error=str(error), kind=kind)
            if isinstance(error, NativeStartError):
                result['stage'] = error.stage
            return result

    def stop(self):
        with self.lock:
            self.stopped = True
            peers = tuple(self.peers)
        for peer in peers:
            peer.close()
        self.events.put(None)
        # Do not detach or delete epochs: this is only called on process exit.


class PipePeer:
    def __init__(self, host, transport):
        self.host, self.transport = host, transport
        self.alive, self.request_ids = True, set()
        self.outgoing = queue.Queue(maxsize=128)
        self.close_lock = threading.Lock()
        with host.lock:
            host.peers.add(self)

    def send(self, value):
        if not self.alive:
            return
        try:
            self.outgoing.put_nowait(encode(value))
        except queue.Full:
            self.close()

    def close(self):
        with self.close_lock:
            if not self.alive:
                return
            self.alive = False
        # Never hold the peer mutex while entering the host lock: a native
        # callback may already hold host.lock and be closing a full outbox.
        self.host.disconnect(self)
        self.transport.close()

    def _write(self):
        try:
            while self.alive:
                try:
                    data = self.outgoing.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.transport.send_bytes(data)
        except Exception:
            self.close()

    def run(self):
        threading.Thread(target=self._write, daemon=True, name='WorldApartTrainer-host-writer').start()
        try:
            while self.alive:
                value = decode(self.transport.recv_bytes(MAX_MESSAGE))
                self.send(self.host.dispatch(self, value))
        except Exception:
            pass
        finally:
            self.close()


class GameLifetime:
    """A stable synchronization handle distinguishes exit from query failure."""
    def __init__(self, identity):
        from native_write import process_identity
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        self.kernel.WaitForSingleObject.restype = W.DWORD
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.handle = self.kernel.OpenProcess(0x101000, False, identity[0])  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            path, created = process_identity(self.handle)
            if created != identity[1] or Path(path).name.casefold() != 'worldapart.exe':
                raise Refused('游戏进程身份已变化，后台未启动。')
        except Exception:
            self.close()
            raise

    def exited(self):
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result == 0:
            return True
        if result == 0x102:
            return False
        raise OSError('Cannot confirm game lifetime')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def start_authenticated_peer(host, transport, authkey, slots, timeout=3):
    """A stalled handshake cannot occupy the shared accept thread forever."""
    if not slots.acquire(blocking=False):
        transport.close()
        return False

    def serve():
        auth_lock = threading.Lock()
        close_lock = threading.Lock()
        finished = expired = False
        holding_slot = True
        deadline = time.monotonic() + timeout

        def close_transport():
            with close_lock:
                try:
                    transport.close()
                except Exception:
                    pass

        class TimedAuthentication:
            def send_bytes(self, value):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Pipe authentication expired')
                transport.send_bytes(value)

            def recv_bytes(self, maximum):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not transport.poll(remaining):
                    raise TimeoutError('Pipe authentication expired')
                return transport.recv_bytes(maximum)

        def expire():
            nonlocal expired
            with auth_lock:
                if finished:
                    return
                expired = True
            close_transport()

        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        try:
            # Identical mutual HMAC ordering to Listener.accept(authkey=...).
            # No PipePeer or application command exists before both succeed.
            timed = TimedAuthentication()
            deliver_challenge(timed, authkey)
            answer_challenge(timed, authkey)
            with auth_lock:
                if expired:
                    raise TimeoutError('Pipe authentication expired')
                finished = True
            timer.cancel()
            slots.release()
            holding_slot = False
            with host.lock:
                if host.stopped:
                    raise Refused('Native host stopped')
                peer = PipePeer(host, transport)
            peer.run()
        except Exception:
            close_transport()
        finally:
            timer.cancel()
            if holding_slot:
                slots.release()

    threading.Thread(target=serve, daemon=True, name='WorldApartTrainer-host-auth').start()
    return True


def validated_startup_path(startup_config_path, directory):
    """Require the actual safety directory, including Windows path aliases.

    MSIX file virtualization can resolve an existing file to its physical
    package cache while its parent directory retains the logical AppData path.
    Compare filesystem identities, not those two path spellings; resolution of
    the file itself still prevents an outside symlink target from being read.
    Missing/inaccessible paths fail closed before any game or pipe access.
    """
    try:
        startup = Path(startup_config_path).resolve(strict=True)
        valid = (startup.parent.samefile(directory)
                 and startup.name.endswith('.startup.json')
                 and startup.is_file() and startup.stat().st_size <= 16384)
    except (OSError, ValueError) as error:
        raise Refused('原生后台启动文件位置无效。') from error
    if not valid:
        raise Refused('原生后台启动文件位置无效。')
    return startup


def _main(startup_config_path):
    from runtime_paths import SAFETY_LOG_ROOT
    startup = validated_startup_path(startup_config_path, SAFETY_LOG_ROOT / 'native-hosts')
    config = decode(startup.read_bytes())
    if set(config) != {'protocol', 'identity', 'pipe', 'auth_protected'} or config['protocol'] != PROTOCOL:
        raise Refused('原生后台启动协议无效。')
    identity = _identity(config['identity'])
    details = dict(parent_pid=os.getppid(), frozen=bool(getattr(sys, 'frozen', False)),
                   host_created=host_identity(os.getpid())[1])
    try:
        details.update(current_job_details())
    except Exception as error:
        details['error_type'] = type(error).__name__
    # A host may belong to a distinct system/bootloader Job. Membership is
    # diagnostic, not blanket rejection; launch uses explicit breakaway from
    # the GUI's inherited Job, and the isolated lifetime test checks that Job.
    record_host_lifecycle(SAFETY_LOG_ROOT / 'acquisition-native-epochs.json', 'host_started', identity, **details)
    if not isinstance(config['pipe'], str) or not _PIPE_RE.fullmatch(config['pipe']):
        raise Refused('原生后台管道地址无效。')
    authkey = unprotect(config['auth_protected'])
    epoch_path = SAFETY_LOG_ROOT / 'acquisition-native-epochs.json'
    endpoint = endpoint_path(identity, epoch_path)
    with startup_lock(endpoint.with_suffix('.host-lock')):
        checked_game(identity)
        lifetime = GameLifetime(identity)
        host = BrokerHost(identity, epoch_path)
        try:
            listener = Listener(config['pipe'], family='AF_PIPE', authkey=None)
            auth_slots = threading.BoundedSemaphore(8)
            descriptor = dict(config, host_pid=os.getpid(), host_created=host_identity(os.getpid())[1])
            atomic_json(endpoint, descriptor)
            startup.unlink(missing_ok=True)
            record_host_lifecycle(epoch_path, 'endpoint_ready', identity, host_pid=os.getpid(), host_created=descriptor['host_created'])

            def accept():
                while not host.stopped:
                    try:
                        transport = listener.accept()
                        start_authenticated_peer(host, transport, authkey, auth_slots)
                    except Exception:
                        if host.stopped:
                            return
                        # A failed authentication must not kill the game owner.
                        time.sleep(0.05)
            threading.Thread(target=accept, daemon=True, name='WorldApartTrainer-host-listener').start()
            next_heartbeat = time.monotonic() + 60
            while not host.stopped:
                time.sleep(1)
                try:
                    exited = lifetime.exited()
                except Exception as error:
                    with host.lock:
                        if not host.monitor_uncertain:
                            record_host_lifecycle(epoch_path, 'game_monitor_uncertain', identity, error_type=type(error).__name__)
                        host.monitor_uncertain = True
                    continue
                with host.lock:
                    if host.monitor_uncertain:
                        record_host_lifecycle(epoch_path, 'game_monitor_recovered', identity)
                    host.monitor_uncertain = False
                if exited:
                    record_host_lifecycle(epoch_path, 'game_exit_confirmed', identity)
                    host.stop()
                elif time.monotonic() >= next_heartbeat:
                    status = host.status()
                    record_host_lifecycle(epoch_path, 'heartbeat', identity,
                        ready=status['ready'], busy=status['busy'], connected=status['connected'])
                    next_heartbeat = time.monotonic() + 60
        finally:
            lifetime.close()
            if 'listener' in locals():
                listener.close()
    return 0


def main(startup_config_path):
    from runtime_paths import SAFETY_LOG_ROOT
    epoch_path = SAFETY_LOG_ROOT / 'acquisition-native-epochs.json'
    record_host_lifecycle(epoch_path, 'host_entry')
    try:
        result = _main(startup_config_path)
    except BaseException as error:
        record_host_lifecycle(epoch_path, 'host_unhandled_exit',
                              error_type=type(error).__name__, winerror=getattr(error, 'winerror', None))
        # A hidden/windowed PyInstaller process would otherwise show its crash
        # dialog and remain alive, making the GUI misreport an exit as timeout.
        # Preserve the bounded diagnostic, fail nonzero, and never retry here.
        return 1
    record_host_lifecycle(epoch_path, 'host_normal_exit', exit_code=result)
    return result
