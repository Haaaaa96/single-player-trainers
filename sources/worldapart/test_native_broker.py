"""Broker client tests: private synthetic transports only; never game/Frida.

The AF_PIPE test below runs a small JSON echo service in a test thread. It is
not the production native host and does not open any game or load any agent.
"""
from contextlib import nullcontext
import hashlib
import json
import ctypes as C
from ctypes import wintypes as W
from multiprocessing.connection import Listener
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import uuid

import native_broker as nb
from write_guard import Refused


def descriptor(identity=(98765,12345)):
    return dict(protocol=1,identity=list(identity),pipe=r"\\.\pipe\WorldApartTrainer-"+"a"*32,
                host_pid=555,host_created=456,auth_protected="test-only")


class FakeTransport:
    def __init__(self):
        self.incoming = queue.Queue()
        self.sent = []
        self.closed = threading.Event()
        self.on_send = None

    def recv_bytes(self, maximum):
        value = self.incoming.get()
        if isinstance(value,Exception):raise value
        if len(value) > maximum:raise OSError("oversized frame")
        return value

    def send_bytes(self, value):
        self.sent.append(nb.decode(value))
        if self.on_send:self.on_send(self.sent[-1])

    def reply(self,request,**changes):
        response = dict(id=request["id"],ok=True,result={})
        response.update(changes)
        self.incoming.put(nb.encode(response))

    def close(self):
        self.closed.set()
        self.incoming.put(EOFError("test disconnected"))


class EncodingTests(unittest.TestCase):
    def test_bounded_json_counts_utf8_bytes_not_characters(self):
        value = {"text":"精力"}
        encoded = nb.encode(value)
        self.assertEqual(nb.decode(encoded),value)
        with patch.object(nb,"MAX_MESSAGE",len(encoded)-1):
            with self.assertRaises(Refused):nb.encode(value)
            with self.assertRaises(Refused):nb.decode(encoded)

    def test_nonfinite_and_non_object_json_are_rejected(self):
        for value in (float("nan"),float("inf"),-float("inf")):
            with self.assertRaises(ValueError):nb.encode({"value":value})
        for raw in (b'[]',b'null',b'"text"',b'{"value":NaN}',b'{"value":Infinity}',b'\xff'):
            with self.subTest(raw=raw),self.assertRaises((Refused,ValueError)):
                nb.decode(raw)

    def test_dpapi_roundtrip_stores_no_plaintext_secret(self):
        secret = b"test-credential-"+b"x"*16
        self.assertEqual(len(secret),32)
        protected = nb.protect(secret)
        self.assertNotEqual(protected,secret.hex())
        self.assertNotIn(secret.decode(),protected)
        self.assertEqual(nb.unprotect(protected),secret)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"endpoint.json"
            nb.atomic_json(path,dict(descriptor(),auth_protected=protected))
            raw = path.read_bytes()
            self.assertNotIn(secret,raw)
            self.assertEqual(list(Path(directory).iterdir()),[path])
            self.assertEqual(nb.unprotect(json.loads(raw)["auth_protected"]),secret)

    def test_dpapi_refuses_wrong_size_or_invalid_ciphertext(self):
        for value in (b"short","x"*32,bytes(33)):
            with self.assertRaises(ValueError):nb.protect(value)
        for value in (None,"!","x"*4097):
            with self.assertRaises((Refused,ValueError,OSError)):
                nb.unprotect(value)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.identity = (98765,12345)
        self.epoch = Path(self.temp.name)/"epochs.json"
        self.path = nb.endpoint_path(self.identity,self.epoch)

    def save(self,value):
        nb.atomic_json(self.path,value)

    def test_pid_and_creation_time_select_independent_endpoint(self):
        self.assertEqual(self.path.name,"98765-12345.json")
        self.assertNotEqual(self.path,nb.endpoint_path((98765,12346),self.epoch))
        for identity in ((1,True),(0,1),(1,0),[1],"1:2",(1,2,3)):
            with self.assertRaises(Refused):nb.endpoint_path(identity,self.epoch)

    def test_endpoint_rejects_pid_or_creation_time_mismatch(self):
        for identity in ((98766,12345),(98765,12346)):
            self.save(descriptor(identity))
            with self.assertRaises(Refused):nb.read_endpoint(self.path,self.identity)

    def test_only_exact_local_named_pipe_prefix_and_hex_nonce_are_allowed(self):
        self.save(descriptor())
        self.assertEqual(nb.read_endpoint(self.path,self.identity)["pipe"],descriptor()["pipe"])
        for pipe in (r"\\remote\pipe\WorldApartTrainer-"+"a"*32,
                     r"\\.\pipe\Other-"+"a"*32,
                     r"\\.\pipe\WorldApartTrainer-"+"a"*31,
                     r"\\.\pipe\WorldApartTrainer-"+"G"*32,
                     descriptor()["pipe"]+"\n","http://localhost",123):
            with self.subTest(pipe=pipe):
                self.save(dict(descriptor(),pipe=pipe))
                with self.assertRaises(Refused):nb.read_endpoint(self.path,self.identity)

    def test_endpoint_size_schema_and_host_identity_are_bounded(self):
        self.save(descriptor())
        for change in (dict(protocol=2),dict(host_pid=True),dict(host_created=0),dict(host_pid="555")):
            self.save(dict(descriptor(),**change))
            with self.assertRaises(Refused):nb.read_endpoint(self.path,self.identity)
        self.path.write_bytes(b" "*16385)
        with self.assertRaises(Refused):nb.read_endpoint(self.path,self.identity)

    def test_pid_reuse_and_dead_host_are_not_alive(self):
        with patch.object(nb,"host_identity",return_value=("host.exe",457)):
            self.assertFalse(nb.endpoint_alive(descriptor()))
        with patch.object(nb,"host_identity",side_effect=OSError("gone")):
            self.assertFalse(nb.endpoint_alive(descriptor()))
        with patch.object(nb,"host_identity",side_effect=Refused("host exited")):
            self.assertFalse(nb.endpoint_alive(descriptor()))


class DiscoveryTests(unittest.TestCase):
    save = EndpointTests.save

    def setUp(self):
        EndpointTests.setUp(self)
        patch.dict(nb._CLIENTS,{},clear=True).start()
        patch.object(nb,"startup_lock",side_effect=lambda path:nullcontext()).start()
        self.start = patch.object(nb,"_start_host").start()
        self.addCleanup(patch.stopall)
        self.owner,self.callback,self.detached,self.before,self.check = object(),Mock(),Mock(),Mock(),Mock()

    def acquire(self):
        return nb.acquire_broker_connection(self.identity,"// source",self.epoch,self.owner,
                                            self.callback,self.detached,self.before,self.check)

    def test_readonly_status_with_no_endpoint_has_no_side_effects(self):
        self.assertIsNone(nb.broker_status(self.identity,self.epoch))
        self.start.assert_not_called()
        self.assertEqual(list(Path(self.temp.name).iterdir()),[])

    def test_dead_host_with_epoch_never_starts_a_replacement(self):
        self.save(descriptor())
        nb.atomic_json(self.epoch,dict(version=1,processes={"98765:12345":{"status":"attached"}}))
        with patch.object(nb,"_connect_existing",return_value=None),self.assertRaises(Refused):self.acquire()
        self.start.assert_not_called()
        self.check.assert_not_called()

    def test_exclusive_epoch_claim_alone_blocks_a_replacement(self):
        claim = self.epoch.parent/"native-epochs"/"98765-12345.json"
        nb.atomic_json(claim,dict(status="attempted"))
        with self.assertRaises(Refused):self.acquire()
        self.start.assert_not_called()

    def test_live_but_uncommunicative_host_never_starts_a_replacement(self):
        self.save(descriptor())
        with patch.object(nb,"_connect_existing",side_effect=Refused("live host unreachable")),self.assertRaises(Refused):
            self.acquire()
        self.start.assert_not_called()
        self.before.assert_not_called()

    def test_cached_host_claim_reuses_client_without_startup_or_scan(self):
        proxy = Mock(usable=True,detached=False)
        nb._CLIENTS[self.identity] = proxy
        self.assertIs(self.acquire(),proxy)
        proxy.claim.assert_called_once_with(self.owner,self.callback,self.detached,"// source")
        self.before.assert_not_called()  # Only the host owns attachment intent.
        self.start.assert_not_called()
        self.check.assert_not_called()

    def test_status_on_existing_host_does_not_claim_or_start(self):
        self.save(descriptor())
        proxy = Mock()
        proxy.call.return_value = dict(identity=list(self.identity),status="idle")
        with patch.object(nb,"_connect_existing",return_value=proxy):
            self.assertEqual(nb.broker_status(self.identity,self.epoch)["status"],"idle")
        proxy.claim.assert_not_called()
        proxy.close_transport.assert_called_once()
        self.start.assert_not_called()

    def test_mismatched_server_identity_is_closed_and_rejected(self):
        proxy = Mock()
        proxy.call.return_value = dict(identity=[98765,99999])
        with patch.object(nb,"endpoint_alive",return_value=True),patch.object(nb,"RemoteConnection",return_value=proxy):
            with self.assertRaises(Refused):nb._connect_existing(descriptor())
        proxy.close_transport.assert_called()

    def test_bad_status_response_closes_transport_instead_of_leaking_reader(self):
        proxy = Mock()
        proxy.call.side_effect = Refused("status timeout")
        with patch.object(nb,"endpoint_alive",return_value=True),patch.object(nb,"RemoteConnection",return_value=proxy):
            with self.assertRaises(Refused):nb._connect_existing(descriptor())
        proxy.close_transport.assert_called_once()


class HostLaunchTests(unittest.TestCase):
    def test_frozen_host_resets_pyinstaller_environment_and_preserves_other_variables(self):
        """Popen is mocked: this test never starts a host process."""
        with tempfile.TemporaryDirectory() as directory:
            epoch = Path(directory)/"epochs.json"
            path = nb.endpoint_path((98765,12345),epoch)
            proxy = Mock()
            with patch.object(nb.sys,"frozen",True,create=True),\
                    patch.dict(os.environ,{"BROKER_TEST_KEEP":"unchanged","PYINSTALLER_RESET_ENVIRONMENT":"0"}),\
                    patch.object(nb.uuid,"uuid4",return_value=uuid.UUID("a"*32)),\
                    patch.object(nb,"protect",return_value="protected-test-key"),\
                    patch.object(nb,"read_endpoint",return_value=descriptor()),\
                    patch.object(nb,"_connect_existing",return_value=proxy),\
                    patch.object(nb,"_HOST_PROCESSES",[]),\
                    patch.object(nb.subprocess,"Popen") as launch:
                before = dict(os.environ)
                self.assertIs(nb._start_host((98765,12345),epoch,path),proxy)
                launch.assert_called_once()
                args,kwargs = launch.call_args
                self.assertEqual(args[0][0],nb.sys.executable)
                self.assertEqual(args[0][1],"--native-host")
                self.assertEqual(len(args[0]),3)
                self.assertEqual(kwargs["env"],dict(before,PYINSTALLER_RESET_ENVIRONMENT="1"))
                self.assertEqual(kwargs["env"]["BROKER_TEST_KEEP"],"unchanged")
                self.assertEqual(dict(os.environ),before)
                self.assertTrue(kwargs["creationflags"] & 0x08000000)
                self.assertTrue(kwargs["creationflags"] & 0x01000000)
                launch.return_value.terminate.assert_not_called()

    def test_breakaway_denied_never_retries_without_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            epoch=Path(directory)/'epochs.json';path=nb.endpoint_path((98765,12345),epoch)
            with patch.object(nb,'protect',return_value='fixture'),\
                    patch.object(nb,'current_job_details',return_value=dict(in_job=True,job_limit_flags=0x2000)),\
                    patch.object(nb.subprocess,'Popen',side_effect=PermissionError('job denied')) as launch:
                with self.assertRaises(Refused):nb._start_host((98765,12345),epoch,path)
                launch.assert_called_once()
                self.assertTrue(launch.call_args.kwargs['creationflags']&0x01000000)
                self.assertEqual(list(path.parent.glob('*.startup.json')),[])
                self.assertFalse((epoch.parent/'native-epochs').exists())

    def test_early_child_exit_is_reported_without_waiting_or_relaunch(self):
        with tempfile.TemporaryDirectory() as directory:
            epoch=Path(directory)/'epochs.json';path=nb.endpoint_path((98765,12345),epoch)
            child=Mock(pid=123,poll=Mock(return_value=1))
            with patch.object(nb,'protect',return_value='fixture'),\
                    patch.object(nb.subprocess,'Popen',return_value=child) as launch,\
                    patch.object(nb.time,'sleep') as sleep:
                with self.assertRaises(Refused):nb._start_host((98765,12345),epoch,path)
                launch.assert_called_once();sleep.assert_not_called();child.terminate.assert_not_called()


class LifecycleLogTests(unittest.TestCase):
    def test_log_contains_only_bounded_diagnostic_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            epoch=Path(directory)/'epochs.json'
            nb.record_host_lifecycle(epoch,'claim_failed',(123,456),host_pid=789,error_type='Refused',
                auth_protected='SECRET',pipe='SECRET',source='SECRET',payload={'token':'SECRET'},
                reason_code='unsafe',arbitrary='SECRET')
            path=epoch.parent/'native-host-lifecycle'/f'{os.getpid()}.jsonl'
            raw=path.read_text();self.assertNotIn('SECRET',raw)
            row=json.loads(raw)
            self.assertEqual((row['game_pid'],row['game_created'],row['stage']),(123,456,'claim_failed'))
            self.assertEqual(row['error_type'],'Refused')
            self.assertTrue(set(row)<=set(nb._LIFECYCLE_FIELDS)|{'pid','time','stage','game_pid','game_created'})

    def test_diagnostic_write_failure_does_not_change_safety_outcome(self):
        with patch.object(nb.os,'open',side_effect=OSError('disk unavailable')):
            nb.record_host_lifecycle(Path(tempfile.gettempdir())/'broker-test'/'epochs.json','claim_failed',(123,456))


class RealJobTests(unittest.TestCase):
    def test_breakaway_child_survives_its_launchers_kill_on_close_job(self):
        """Only disposable Python fixtures enter this Job; never a real host/game."""
        kernel=C.WinDLL('kernel32',use_last_error=True)
        kernel.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR];kernel.CreateJobObjectW.restype=W.HANDLE
        kernel.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD];kernel.SetInformationJobObject.restype=W.BOOL
        kernel.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE];kernel.AssignProcessToJobObject.restype=W.BOOL
        kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
        kernel.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)];kernel.IsProcessInJob.restype=W.BOOL
        kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
        kernel.CloseHandle.argtypes=[W.HANDLE]
        class IO(C.Structure):_fields_=[('values',C.c_ulonglong*6)]
        class Limits(C.Structure):
            _fields_=[('basic',nb._JobBasicLimits),('io',IO),('memory',C.c_size_t*4)]
        job=kernel.CreateJobObjectW(None,None);self.assertTrue(job)
        limit=Limits();limit.basic.flags=0x2800  # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
        self.assertTrue(kernel.SetInformationJobObject(job,9,C.byref(limit),C.sizeof(limit)))
        worker=None;handles=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            # Child processes only observe this private directory and then exit.
            child_code="""import json,os,sys,time
from pathlib import Path
p=Path(sys.argv[1]);p.write_text(json.dumps({'pid':os.getpid()}))
deadline=time.monotonic()+15
while not (p.parent/'stop').exists() and time.monotonic()<deadline:
 if (p.parent/'probe').exists():(p.parent/(p.stem+'.alive')).write_text('alive')
 time.sleep(.02)
"""
            worker_code="""import json,sys,subprocess,time
from pathlib import Path
from native_broker import HOST_CREATION_FLAGS
config=json.loads(sys.stdin.readline());root=Path(config['root'])
children=[]
for name,flags in [('ordinary',HOST_CREATION_FLAGS&~0x01000000),('escaped',HOST_CREATION_FLAGS)]:
 children.append(subprocess.Popen([sys.executable,'-c',config['child'],str(root/(name+'.json'))],creationflags=flags,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,close_fds=True))
time.sleep(15)
"""
            def wait_file(path):
                deadline=time.monotonic()+5
                while not path.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(path.exists(),str(path))
            try:
                worker=subprocess.Popen([sys.executable,'-c',worker_code],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,creationflags=nb.HOST_CREATION_FLAGS,close_fds=True)
                self.assertTrue(kernel.AssignProcessToJobObject(job,int(worker._handle)))
                worker.stdin.write((json.dumps(dict(root=str(root),child=child_code))+'\n').encode());worker.stdin.flush()
                for name in ('ordinary','escaped'):
                    path=root/(name+'.json');wait_file(path)
                    h=kernel.OpenProcess(0x101000,False,json.loads(path.read_text())['pid']);self.assertTrue(h);handles.append(h)
                    inside=W.BOOL();self.assertTrue(kernel.IsProcessInJob(h,job,C.byref(inside)))
                    self.assertEqual(bool(inside.value),name=='ordinary')
                kernel.CloseHandle(job);job=None
                self.assertEqual(kernel.WaitForSingleObject(handles[0],3000),0)
                self.assertEqual(kernel.WaitForSingleObject(handles[1],0),0x102)
                (root/'probe').write_text('probe');wait_file(root/'escaped.alive')
                self.assertIsNotNone(worker.wait(timeout=3))
            finally:
                (root/'stop').write_text('stop')
                if job:kernel.CloseHandle(job)
                if worker:
                    if worker.stdin:worker.stdin.close()
                    worker.wait(timeout=5)
                for h in handles:
                    kernel.WaitForSingleObject(h,5000);kernel.CloseHandle(h)


class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.proxy = nb.RemoteConnection(descriptor(),transport=self.transport)
        self.addCleanup(self.close)

    def close(self):
        self.proxy.close_transport()
        self.proxy._thread.join(1)

    def test_claim_hash_uses_exact_utf8_source(self):
        self.transport.on_send = lambda request:self.transport.reply(request)
        owner,source = object(),"// 精力 bridge\n"
        self.proxy.claim(owner,Mock(),Mock(),source)
        request = self.transport.sent[-1]
        self.assertEqual(request["command"],"claim")
        self.assertEqual(request["payload"]["source"],source)
        self.assertEqual(request["payload"]["source_sha256"],hashlib.sha256(source.encode("utf8")).hexdigest())
        with self.assertRaises(Refused):self.proxy.claim(object(),Mock(),Mock(),source)
        self.assertEqual(len(self.transport.sent),1)

    def test_timeout_sends_submit_only_once_and_discards_pending_id(self):
        with self.assertRaises(Refused):
            self.proxy.call("submit",{"request":{"token":"unique"}},timeout=.01)
        self.assertEqual(len(self.transport.sent),1)
        self.assertEqual(self.transport.sent[0]["command"],"submit")
        self.assertEqual(self.proxy._pending,{})

    def test_disconnection_after_send_never_retries_request(self):
        self.transport.on_send = lambda request:self.transport.close()
        with self.assertRaises(Refused):self.proxy.submit({"token":"one"})
        self.assertEqual(len(self.transport.sent),1)
        self.assertFalse(self.proxy.usable)
        with self.assertRaises(Refused):self.proxy.submit({"token":"one"})
        self.assertEqual(len(self.transport.sent),1)

    def test_late_response_cannot_reopen_timed_out_client(self):
        with self.assertRaises(Refused):self.proxy.call("status",timeout=.01)
        previous = self.transport.sent[-1]
        self.transport.reply(previous,result={"late":True})
        self.transport.on_send = lambda request:self.transport.reply(request,result={"fresh":True})
        with self.assertRaises(Refused):self.proxy.call("status",timeout=1)
        self.assertEqual(len(self.transport.sent),1)

    def test_unknown_frames_fail_closed_and_signal_detachment(self):
        detached = threading.Event()
        self.proxy.detached_callback = lambda reason:detached.set()
        self.transport.incoming.put(nb.encode({"unknown":"message"}))
        self.assertTrue(detached.wait(1))
        self.assertTrue(self.proxy.detached)
        self.assertTrue(self.transport.closed.wait(1))

    def test_native_events_reach_current_owner_only(self):
        event = threading.Event()
        self.proxy.callback = lambda message,data:event.set()
        self.transport.incoming.put(nb.encode(dict(event="message",message={"type":"send","payload":{"token":"one"}})))
        self.assertTrue(event.wait(1))

    def test_failed_claim_closes_transport_and_clears_owner(self):
        self.transport.on_send = lambda request:self.transport.reply(request,ok=False,error="claim denied")
        with self.assertRaises(Refused):self.proxy.claim(object(),Mock(),Mock(),"source")
        self.assertTrue(self.transport.closed.is_set())
        self.assertIsNone(self.proxy.owner)
        self.assertFalse(self.proxy.usable)

    def test_failed_release_closes_pipe_and_clears_owner(self):
        owner = object()
        self.proxy.owner = owner
        self.transport.on_send = lambda request:self.transport.reply(request,ok=False,error="release failed")
        self.proxy.release(owner)
        self.assertTrue(self.transport.closed.is_set())
        self.assertIsNone(self.proxy.owner)
        self.assertFalse(self.proxy.usable)
        self.assertEqual([r["command"] for r in self.transport.sent],["release"])

    def test_blocked_send_obeys_call_deadline_without_retry(self):
        release = threading.Event()
        entered = threading.Event()
        def blocked_send(request):
            entered.set()
            release.wait(2)
        self.transport.on_send = blocked_send
        try:
            started = time.monotonic()
            with self.assertRaises(Refused):
                self.proxy.call("submit",{"request":{"token":"one"}},timeout=.03)
            self.assertTrue(entered.is_set())
            self.assertLess(time.monotonic()-started,1)
            self.assertTrue(self.transport.closed.is_set())
            self.assertFalse(self.proxy.usable)
            self.assertEqual(len(self.transport.sent),1)
            with self.assertRaises(Refused):self.proxy.submit({"token":"one"})
            self.assertEqual(len(self.transport.sent),1)
        finally:release.set()

    def test_send_queued_behind_lock_cannot_arrive_after_timeout(self):
        self.proxy._send_lock.acquire()
        try:
            with self.assertRaises(Refused):
                self.proxy.call("submit",{"request":{"token":"never-sent"}},timeout=.02)
            self.assertTrue(self.transport.closed.is_set())
        finally:self.proxy._send_lock.release()
        # A follow-up call cannot use this expired transport either.
        with self.assertRaises(Refused):self.proxy.call("status",timeout=.02)
        self.assertEqual(self.transport.sent,[])


class ConnectionDeadlineTests(unittest.TestCase):
    def test_auth_timeout_is_bounded_and_closes_late_transport(self):
        release = threading.Event()
        transport = FakeTransport()
        def connect(*args,**kwargs):
            release.wait(2)
            return transport
        try:
            with patch.object(nb,"CONNECT_TIMEOUT",.02),patch.object(nb,"Client",side_effect=connect) as client,\
                    patch.object(nb,"unprotect",return_value=bytes(32)):
                started = time.monotonic()
                with self.assertRaises(Refused):nb._connect_transport(descriptor())
                self.assertLess(time.monotonic()-started,1)
                client.assert_called_once()
                release.set()
                self.assertTrue(transport.closed.wait(1))
        finally:release.set()

    def test_auth_failure_does_not_retry_client(self):
        with patch.object(nb,"Client",side_effect=OSError("pipe lost")) as client,\
                patch.object(nb,"unprotect",return_value=bytes(32)):
            with self.assertRaises(Refused):nb._connect_transport(descriptor())
            client.assert_called_once()


class RealPipeTests(unittest.TestCase):
    def test_gui_transport_disconnect_and_reconnect_use_same_mock_service(self):
        """Actual local Windows pipe and auth; no production host or Frida."""
        key = os.urandom(32)
        value = dict(descriptor(),pipe=r"\\.\pipe\WorldApartTrainer-"+uuid.uuid4().hex,
                     auth_protected=nb.protect(key))
        listener = Listener(value["pipe"],family="AF_PIPE",authkey=key)
        calls,errors = [],[]
        finished = threading.Event()
        def serve():
            try:
                for generation in range(2):
                    transport = listener.accept()
                    try:
                        while True:
                            request = nb.decode(transport.recv_bytes(nb.MAX_MESSAGE))
                            calls.append((generation,request))
                            command = request["command"]
                            result = {"identity":value["identity"],"status":"idle"} if command == "status" else {"status":"ok"}
                            transport.send_bytes(nb.encode(dict(id=request["id"],ok=True,result=result)))
                    except (EOFError,OSError):pass
                    finally:transport.close()
            except Exception as error:errors.append(error)
            finally:
                listener.close()
                finished.set()
        thread = threading.Thread(target=serve,daemon=True)
        thread.start()
        proxies = []
        try:
            with patch.dict("sys.modules",frida=Mock()) as modules:
                for version in ("old source","new source"):
                    proxy = nb.RemoteConnection(value)
                    proxies.append(proxy)
                    self.assertEqual(proxy.call("status",timeout=2)["identity"],value["identity"])
                    owner = object()
                    proxy.claim(owner,Mock(),Mock(),version)
                    proxy.prepare()
                    proxy.submit({"token":version})
                    proxy.release(owner)
                    proxy.close_transport()
                    proxy._thread.join(1)
                modules["frida"].attach.assert_not_called()
            self.assertTrue(finished.wait(2))
            self.assertEqual(errors,[])
            claims = [(generation,request) for generation,request in calls if request["command"] == "claim"]
            self.assertEqual(len(claims),2)
            self.assertEqual([request["payload"]["source_sha256"] for _,request in claims],
                             [hashlib.sha256(source.encode()).hexdigest() for source in ("old source","new source")])
            self.assertEqual(sum(request["command"] == "submit" for _,request in calls),2)
        finally:
            for proxy in proxies:proxy.close_transport()
            listener.close()
            thread.join(1)


if __name__ == "__main__":
    unittest.main()
