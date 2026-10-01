"""Offline proof that a frozen child retains its own bundle after GUI exit."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from native_broker import atomic_json, host_identity, HOST_CREATION_FLAGS, current_job_details
from runtime_paths import RESOURCE_ROOT


def launch(output):
    output = Path(output).resolve()
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Run the lifetime check with a built EXE')
    config = output.with_suffix('.parent.json')
    atomic_json(config, dict(parent_pid=os.getpid(), parent_created=host_identity(os.getpid())[1],
                           parent_bundle=str(RESOURCE_ROOT), output=str(output), parent_job=current_job_details()))
    subprocess.Popen([sys.executable, '--lifetime-self-test-child', str(config)],
        env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'), close_fds=True,
        creationflags=HOST_CREATION_FLAGS, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ready = output.with_suffix('.ready.json')
    deadline = time.monotonic() + 15
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    if not ready.exists():
        raise RuntimeError('Independent child did not start')
    # Returning exits this parent; the child waits for that exact lifetime.
    return 0


def child(config):
    value = json.loads(Path(config).read_text(encoding='utf8'))
    output = Path(value['output'])
    result = dict(passed=False, frozen=bool(getattr(sys, 'frozen', False)),
                  parent_bundle=value['parent_bundle'], child_bundle=str(RESOURCE_ROOT),
                  parent_job=value.get('parent_job'), child_job=current_job_details(),
                  game_connection_attempted=False, native_injection_attempted=False)
    atomic_json(output.with_suffix('.ready.json'), dict(pid=os.getpid(), ready=True))
    try:
        if not result['frozen'] or Path(value['parent_bundle']).resolve() == RESOURCE_ROOT.resolve():
            raise RuntimeError('Child reused the parent temporary bundle')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                alive = host_identity(value['parent_pid'])[1] == value['parent_created']
            except Exception:
                alive = False
            if not alive:
                break
            time.sleep(0.1)
        if alive:
            raise RuntimeError('Parent did not exit before the test deadline')
        # Give its bootloader time to remove the original extraction folder.
        deadline = time.monotonic() + 8
        while Path(value['parent_bundle']).exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        result['parent_exited'] = True
        result['parent_bundle_removed'] = not Path(value['parent_bundle']).exists()
        if not result['parent_bundle_removed']:
            raise RuntimeError('Original bundle cleanup did not finish')
        modules = ['native_broker', 'native_broker_host', 'native_acquisition_session', 'frida', 'frida._frida']
        result['modules'] = {}
        for name in modules:
            module = importlib.import_module(name)
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(RESOURCE_ROOT.resolve()):
                raise RuntimeError('Child loaded external module: ' + name)
            result['modules'][name] = str(path)
        result['bridge_sha256'] = hashlib.sha256((RESOURCE_ROOT / 'acquisition_bridge.js').read_bytes()).hexdigest()
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    atomic_json(output, result)
    return 0 if result['passed'] else 1
