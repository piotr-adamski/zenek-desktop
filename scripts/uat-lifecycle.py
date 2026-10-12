"""Actual Core lifecycle on a private bus, Keyring and disposable XDG data.

No owner desktop, credentials, service manager or settings are modified.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]


def wait(check, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception:
            pass
        time.sleep(.05)
    raise AssertionError(message)


def child():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    assert runtime.name.startswith('zenek-lifecycle-')
    assert '/run/user/1000/bus' not in os.environ['DBUS_SESSION_BUS_ADDRESS']
    from zenek_core.ipc import call
    from zenek_core.memory import Keyring, Memory

    cores = []
    keyring = None
    logout_marker = 'SYNTHETIC_LOGOUT_ACCESS_CANARY'

    def start():
        process = subprocess.Popen([str(root / '.venv/bin/zenek-core')],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cores.append(process)
        return process

    def stop(process):
        assert call('StopCompanion') == 'STOPPING'
        assert process.wait(timeout=5) == 0
        logs,_=process.communicate(timeout=2)
        assert logout_marker.encode() not in logs,'Synthetic account value appeared in Core logs'
        # There is no supervisor/autostart on this private bus.
        time.sleep(.3)
        try:
            call('GetStatus')
        except Exception:
            return
        raise AssertionError('Core remained available after stop')

    try:
        if '--blocked' in sys.argv:
            blocked = start()
            state = wait(lambda: call('GetStatus'), 'Offline Core did not start')
            assert state['memory'] == 'BLOCKED' and state['auth'] == 'BLOCKED'
            assert state['screen'] == 'OFF' and state['web'] == 'OFF'
            assert state['settings']['background_mode'] == 'C'
            call('HideCompanion'); assert call('GetStatus')['visibility'] == 'HIDDEN'
            call('ShowCompanion'); assert call('GetStatus')['visibility'] == 'VISIBLE'
            assert blocked.poll() is None
            assert not (Path(os.environ['XDG_DATA_HOME']) / 'zenek/memory.db').exists()
            stop(blocked)
            print('ZENEK_BLOCKED_KEYRING_PASS', flush=True)
            return

        keyring = subprocess.Popen(
            ['gnome-keyring-daemon', '--foreground', '--components=secrets', '--unlock'],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        keyring.stdin.write(b'SYNTHETIC_LIFECYCLE_ONLY_PASSWORD'); keyring.stdin.close()
        vault = wait(lambda: Keyring(), 'Private Secret Service not available')
        memory = Memory()
        identifier = memory.add('relationship_note', {'text': 'SYNTHETIC LIFECYCLE NOTE'},
                                'synthetic_lifecycle', .8)
        original_key = vault.get('sqlcipher-key')
        memory_path = memory.path
        profiles=dict(conversation=dict(model_id='gpt-6.1-sol',reasoning_effort='medium',status='READY'),
                      background_cognition=dict(model_id='gpt-6-luna',reasoning_effort='xhigh',status='READY'),
                      vision=dict(model_id='gpt-6-luna',reasoning_effort='xhigh',status='READY'))
        memory.patch(dict(profiles,background_paused=True),memory.settings()[0])
        for profile in profiles:memory.profile_status(profile,'READY')
        # Private Secret Service only. No real account, browser or HTTP request.
        vault.put('siwc-account',json.dumps(dict(access_token=logout_marker)))
        memory.close()
        assert original_key and b'SYNTHETIC LIFECYCLE NOTE' not in memory_path.read_bytes()

        process = start()
        state = wait(lambda: call('GetStatus'), 'Core with Keyring did not start')
        assert state['memory'] == 'SQLCipher + GNOME Keyring'
        assert state['settings']['autostart'] is False and state['screen'] == 'OFF'
        assert state['auth']=='AUTHORIZED'
        call('Logout');logged_out=call('GetStatus')
        assert logged_out['auth']=='NOT_CONNECTED' and vault.get('siwc-account') is None
        for profile,value in profiles.items():
            assert logged_out['settings'][profile]==dict(value,status='UNAVAILABLE')
        assert not logged_out['settings']['paid_api_approved'] and logged_out['settings']['provider']=='siwc'
        assert vault.get('sqlcipher-key')==original_key
        call('HideCompanion'); assert call('GetStatus')['visibility'] == 'HIDDEN'
        call('ShowCompanion'); assert call('GetStatus')['visibility'] == 'VISIBLE'
        assert process.poll() is None
        duplicate = start()
        assert duplicate.wait(timeout=5) == 0
        assert process.poll() is None and call('GetStatus')['running']
        assert any(row['id'] == identifier for row in call('GetMemory'))
        stop(process)
        assert vault.get('sqlcipher-key') == original_key
        assert memory_path.exists() and memory_path.stat().st_mode & 0o777 == 0o600

        # Run the actual uninstaller against disposable installed components.
        # The private bus has no owner systemd/Shell; service integration is
        # therefore outside this filesystem preservation check.
        task_home = Path.home()
        component_paths = [
            '.config/systemd/user/zenek-core.service',
            '.local/share/applications/zenek-desktop.desktop',
            '.local/share/applications/zenek-settings.desktop',
            '.local/bin/zenek', '.config/autostart/zenek-desktop.desktop',
            '.local/share/gnome-shell/extensions/zenek@brillnet/metadata.json',
        ]
        for relative in component_paths:
            path = task_home / relative; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC INSTALLED COMPONENT\n')
        # A disconnected bus must not cause removal while stop is unverified.
        failed_env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS='unix:path='+str(runtime/'missing-bus'))
        refused = subprocess.run(['bash', str(root / 'scripts/uninstall-user.sh')],
                                 env=failed_env, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=10)
        assert refused.returncode != 0
        assert all((task_home / relative).exists() for relative in component_paths)
        assert vault.get('sqlcipher-key') == original_key
        # Uninstall must really stop a running Core even without systemd.
        uninstall_core = start()
        wait(lambda: call('GetStatus'), 'Core for uninstall did not start')
        before_uninstall = memory_path.read_bytes()
        removed = subprocess.run(['bash', str(root / 'scripts/uninstall-user.sh')],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        assert removed.returncode == 0, removed.stderr.decode()[-2000:]
        assert uninstall_core.wait(timeout=5) == 0
        try:call('GetStatus')
        except Exception:pass
        else:raise AssertionError('Uninstall left Core running')
        assert all(not (task_home / relative).exists() for relative in component_paths)
        assert memory_path.read_bytes() == before_uninstall
        assert vault.get('sqlcipher-key') == original_key

        restarted = start()
        state = wait(lambda: call('GetStatus'), 'Core did not restart')
        assert state['screen'] == 'OFF' and not state['capture_portal_session']
        assert state['auth']=='NOT_CONNECTED' and vault.get('siwc-account') is None
        assert any(row['id'] == identifier for row in call('GetMemory'))
        stop(restarted)
        # A collection may lock after Core has already opened SQLCipher.
        # Verify the real Secret Service transition, without sending a request
        # or changing the owner's collection. This is the final private phase.
        memory=Memory()
        for profile in profiles:memory.profile_status(profile,'READY')
        memory.close()
        vault.put('siwc-account',json.dumps(dict(access_token=logout_marker)))
        locked_core=start()
        assert wait(lambda: call('GetStatus'), 'Core for live Keyring lock did not start')['auth']=='AUTHORIZED'
        vault.collection.lock();assert vault.collection.is_locked()
        call('TestProfile',{'profile':'background_cognition'})
        wait(lambda: 'test' not in call('GetStatus')['active_jobs'], 'Keyring failure did not finish')
        blocked_state=call('GetStatus')
        assert blocked_state['auth']=='MEMORY_BLOCKED', 'Locked Keyring was still reported authorized'
        assert all(blocked_state['settings'][profile]['status']=='UNAVAILABLE' for profile in profiles), 'Locked shared credentials left a model READY'
        assert blocked_state['memory']=='SQLCipher + GNOME Keyring' and blocked_state['screen']=='OFF'
        assert not blocked_state['settings']['paid_api_approved']
        assert any(row['id']==identifier for row in call('GetMemory'))
        stop(locked_core)
        result = dict(status='PASS', scope='actual private Core, D-Bus, Secret Service, SQLCipher',
                      missing_keyring_offline_pet=True, no_plaintext_fallback=True,
                      hide_show_same_core=True, duplicate_core_exits=True,
                      explicit_stop_exits_no_restart=True, restart_memory_and_key_preserved=True,
                      actual_uninstall_files_removed_memory_and_key_preserved=True,
                      uninstall_stops_running_core_without_manager=True,
                      unverified_bus_refuses_file_removal=True,
                      uninstall_exit_status=removed.returncode,
                      startup_capture_off=True, default_autostart_off=True,
                      actual_private_logout_removes_account=True,
                      logout_keeps_models_efforts_but_marks_unavailable=True,
                      logout_preserves_memory_and_sqlcipher_key=True,
                      logout_survives_restart=True,
                      synthetic_account_absent_from_core_logs=True,
                      logout_no_paid_api_fallback=True,
                      live_keyring_lock_blocks_auth_and_all_profiles=True,
                      live_keyring_lock_preserves_encrypted_memory=True,
                      owner_session_and_data_unchanged=True,
                      limits='Actual uninstaller stops running private Core and removes disposable installed components while preserving memory/key. Does not prove owner login/logout or live installed Shell teardown; real systemd launcher tested separately.')
        print('ZENEK_LIFECYCLE_UAT ' + json.dumps(result), flush=True)
    finally:
        for process in cores:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        if keyring and keyring.poll() is None:
            keyring.terminate(); keyring.wait(timeout=5)


def parent():
    with tempfile.TemporaryDirectory(prefix='zenek-lifecycle-') as runtime:
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime, PYTHONNOUSERSITE='1')
        for key, folder in [('HOME', 'home'), ('XDG_DATA_HOME', 'home/.local/share'),
                            ('XDG_CONFIG_HOME', 'home/.config'), ('XDG_CACHE_HOME', 'home/.cache')]:
            path = Path(runtime) / folder; path.mkdir(parents=True, mode=0o700, exist_ok=True); env[key] = str(path)
        for key in ('DBUS_SESSION_BUS_ADDRESS', 'GNOME_KEYRING_CONTROL', 'DISPLAY',
                    'WAYLAND_DISPLAY', 'AT_SPI_BUS_ADDRESS'):
            env.pop(key, None)
        command = ['dbus-run-session', '--', str(root / '.venv/bin/python'),
                   str(Path(__file__).resolve()), '--child']
        blocked = subprocess.run(command + ['--blocked'], env=env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        if blocked.returncode or 'ZENEK_BLOCKED_KEYRING_PASS' not in blocked.stdout:
            print(blocked.stdout[-4000:]); raise SystemExit(blocked.returncode or 1)
        result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=50)
        lines = [line for line in result.stdout.splitlines() if line.startswith('ZENEK_LIFECYCLE_UAT ')]
        if result.returncode or not lines:
            print(result.stdout[-4000:]); raise SystemExit(result.returncode or 1)
        value = json.loads(lines[-1].removeprefix('ZENEK_LIFECYCLE_UAT '))
        (root / 'evidence/lifecycle-runtime.json').write_text(json.dumps(value, indent=2) + '\n')
        print(json.dumps(value, indent=2))


if __name__ == '__main__':
    child() if '--child' in sys.argv else parent()
