"""Passive real owner lock/suspend/resume monitor; no session mutations."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import time
from gi.repository import Gio,GLib
from zenek_core.ipc import call

parser=argparse.ArgumentParser();parser.add_argument('--duration',type=int,default=1800);args=parser.parse_args()
assert 10<=args.duration<=3600
root=Path(__file__).resolve().parents[1];path=root/'evidence/session-cycle-runtime.json'
initial=call('GetStatus');started=time.monotonic();rows=[];system_events=[];last=None;failure=None
core_pid=int(subprocess.check_output(['systemctl','--user','show','zenek-core.service','--property=MainPID','--value'],text=True))
identity=Path(f'/proc/{core_pid}/stat').read_text().rsplit(')',1)[1].split()[19]
session=Gio.bus_get_sync(Gio.BusType.SESSION,None);system=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
seen=dict(active=False,active_capture=False,locked=False,core_suspended=False,sleep=False,wake=False,unlocked_after_wake=False)

def save(status,reason=None):
    value=dict(status=status,reason=reason,scope='passive actual original Core/GNOME/login1; no fake signals or OS mutations',core_pid=core_pid,core_build=initial['core_build'],elapsed_seconds=round(time.monotonic()-started,1),seen=seen,states=rows,login1_events=system_events,original_capture=initial['screen'],no_session_or_config_mutations=True)
    path.write_text(json.dumps(value,indent=2)+'\n');return value

def observe(state):
    global last,failure
    row={key:state.get(key) for key in ('idle','locked','suspended','visibility','screen','capture_phase','capture_pipeline_state','capture_portal_session','capture_frames')}
    if row!=last:
        row['at']=time.time();rows.append(row);last={key:value for key,value in row.items() if key!='at'}
        print(json.dumps(dict(status='OBSERVED',**row)),flush=True)
    if not state.get('idle') and not state.get('locked') and not state.get('suspended'):
        seen['active']=True
        if not seen['locked'] and state['screen']=='ACTIVE':seen['active_capture']=True
    if state.get('locked'):seen['locked']=True
    if state.get('suspended'):seen['core_suspended']=True
    if state.get('idle') or state.get('locked') or state.get('suspended'):
        if state['screen']!='OFF' or state.get('capture_pipeline_state')!='NULL' or state.get('capture_portal_session'):
            failure='Capture remained open in a protected session state'
    if seen['wake'] and seen['locked'] and not state.get('locked') and not state.get('suspended'):
        if state['screen']!='OFF':failure='Capture resumed on unlock without test controller request'
        else:seen['unlocked_after_wake']=True

def event(_bus,_sender,_path,_interface,_name,params):
    kind,raw=params.unpack()
    if kind=='StateChanged':observe(json.loads(raw))

def sleep_event(_bus,_sender,_path,_interface,_name,params):
    sleeping=params.unpack()[0];system_events.append(dict(at=time.time(),sleeping=sleeping))
    seen['sleep' if sleeping else 'wake']=True
    print(json.dumps(dict(status='LOGIN1',sleeping=sleeping)),flush=True)

session.signal_subscribe('org.zenek.Desktop1','org.zenek.Desktop1','Event','/org/zenek/Desktop1',None,Gio.DBusSignalFlags.NONE,event)
system.signal_subscribe('org.freedesktop.login1','org.freedesktop.login1.Manager','PrepareForSleep','/org/freedesktop/login1',None,Gio.DBusSignalFlags.NONE,sleep_event)

def stopped(number,_frame):
    print(json.dumps(save('INCOMPLETE','Monitor stopped by signal '+str(number))),flush=True);raise SystemExit(2)
signal.signal(signal.SIGTERM,stopped);signal.signal(signal.SIGINT,stopped)
observe(initial);print(json.dumps(save('RUNNING')),flush=True)
try:
    while time.monotonic()-started<args.duration:
        context=GLib.MainContext.default()
        while context.pending():context.iteration(False)
        state=call('GetStatus');observe(state)
        assert state['core_build']==initial['core_build'],'Core build changed during cycle'
        assert Path(f'/proc/{core_pid}/stat').read_text().rsplit(')',1)[1].split()[19]==identity,'Core restarted during cycle'
        if failure:print(json.dumps(save('FAIL',failure)),flush=True);raise SystemExit(1)
        if all(seen.values()):
            assert call('GetRedactedPreview') is None
            print(json.dumps(save('PASS')),flush=True);raise SystemExit(0)
        save('RUNNING');time.sleep(.25)
except (RuntimeError,GLib.Error,AssertionError,FileNotFoundError) as error:
    print(json.dumps(save('INCOMPLETE',type(error).__name__+': '+str(error))),flush=True);raise SystemExit(2)
print(json.dumps(save('INCOMPLETE','No full observed owner cycle before deadline')),flush=True);raise SystemExit(2)
