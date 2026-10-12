"""Run the native Wayland dialog test without using the owner's compositor/bus."""
import json
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import signal

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--native',action='store_true');parser.add_argument('--pointer',action='store_true');parser.add_argument('--real-core',action='store_true');parser.add_argument('--ime',action='store_true');parser.add_argument('--autonomous',action='store_true');parser.add_argument('--capture-menu',action='store_true');args=parser.parse_args()
if args.autonomous and not args.real_core:parser.error('--autonomous requires --real-core')
owner_bus=os.environ.get('DBUS_SESSION_BUS_ADDRESS','unix:path=/run/user/1000/bus')
if args.real_core:
    footprint=root/'evidence/footprint-runtime.json'
    if footprint.exists() and json.loads(footprint.read_text())['status']=='RUNNING':
        parser.error('Wait for the live resource monitor before starting dialogue')
with tempfile.TemporaryDirectory(prefix='zenek-dialog-runtime-') as runtime:
    env=dict(os.environ,XDG_RUNTIME_DIR=runtime,ZENEK_TEST_ROOT=str(root),ZENEK_TEST_CLICK_FILE=runtime+'/clicks.json',GDK_BACKEND='wayland',GSK_RENDERER='cairo')
    env['ZENEK_TEST_COMPOSER_ONLY']='0' if args.native or args.pointer else '1'
    env['ZENEK_TEST_POINTER_ONLY']='1' if args.pointer else '0'
    env['ZENEK_TEST_IME']='1' if args.ime else '0'
    env['ZENEK_TEST_CAPTURE_MENU']='1' if args.capture_menu else '0'
    env['ZENEK_TEST_AUTONOMOUS']='1' if args.autonomous else '0'
    if args.real_core:env['ZENEK_TEST_REAL_CORE_BUS']=owner_bus
    for key,folder in [('HOME','home'),('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache')]:
        path=Path(runtime)/folder;path.mkdir(mode=0o700);env[key]=str(path)
    for key in ('DISPLAY','WAYLAND_DISPLAY','AT_SPI_BUS_ADDRESS','DBUS_SESSION_BUS_ADDRESS'):env.pop(key,None)
    if args.ime:
        for key in ('IBUS_ADDRESS','IBUS_USE_PORTAL','IBUS_DAEMON_ADDRESS'):env.pop(key,None)
        env['IBUS_ADDRESS']='unix:abstract='+Path(runtime).name+'-ibus'
    process=subprocess.Popen(['dbus-run-session','--','gnome-shell-test-tool','--headless','--disable-animations','--extra-filter','org.zenek.DialogTest','--extra-filter','zenek-dialog-test',str(root/'scripts/uat-dialog.js')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    timed_out=False
    try:
        output,_=process.communicate(timeout=1250 if args.autonomous else 100 if args.real_core else 40)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(process.pid,signal.SIGTERM)
        try:output,_=process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);output,_=process.communicate()
    finally:
        # Includes any own compositor/client/activated services still holding
        # the private runtime after the test runner itself exited.
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    (root/'evidence/gnome-smoke.log').write_text(output)
    lines=[line for line in output.splitlines() if line.startswith('ZENEK_DIALOG_UAT ')]
    composer=[line for line in output.splitlines() if line.startswith('ZENEK_COMPOSER_UAT ')]
    pointer=[line for line in output.splitlines() if line.startswith('ZENEK_POINTER_UAT ')]
    if pointer:(root/'evidence/pointer-runtime.json').write_text(json.dumps(json.loads(pointer[-1].removeprefix('ZENEK_POINTER_UAT ')),indent=2)+'\n')
    if composer and not args.native and not args.pointer and not args.ime:(root/'evidence/dialog-composer-runtime.json').write_text(json.dumps(json.loads(composer[-1].removeprefix('ZENEK_COMPOSER_UAT ')),indent=2))
    if process.returncode or timed_out or not lines:
        print('\n'.join(line for line in output.splitlines() if any(s in line for s in ('Script failed','run@','ZENEK_','Native ','Pointer ','Dismiss ','Hover '))));raise SystemExit(process.returncode or 1)
    evidence=json.loads(lines[-1].removeprefix('ZENEK_DIALOG_UAT '));evidence['isolated_runtime']=True;evidence['isolated_session_bus']=True
    filename='evidence/capture-menu-runtime.json' if args.capture_menu else 'evidence/initiative-interruption-runtime.json' if args.autonomous else 'evidence/ime-runtime.json' if args.ime else 'evidence/dialog-real-core-runtime.json' if args.real_core else 'evidence/pointer-runtime.json' if args.pointer else 'evidence/dialog-native-runtime.json' if args.native else 'evidence/dialog-composer-runtime.json'
    (root/filename).write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))
