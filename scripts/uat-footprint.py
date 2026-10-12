"""Sample actual Core/Shell; optional temporary quiet, no text/images/secrets.

One continuous hour without dialogue is required. Activity resets that window;
restart/build drift or four-hour deadline produces INCOMPLETE, never PASS.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import signal
import sys
import time
from gi.repository import Gio,GLib
from zenek_core.ipc import call

parser=argparse.ArgumentParser();parser.add_argument('--duration',type=int,default=3600);parser.add_argument('--quiet',action='store_true');args=parser.parse_args()
if not 10<=args.duration<=14400:raise ValueError('Duration must be10..14400seconds')
root=Path(__file__).resolve().parents[1];output=root/'evidence/footprint-runtime.json'
core_pid=int(subprocess.check_output(['systemctl','--user','show','zenek-core.service','-p','MainPID','--value'],text=True))
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
shell_pid=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID',GLib.Variant('(s)',('org.gnome.Shell',)),GLib.VariantType.new('(u)'),Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
clock_ticks=os.sysconf('SC_CLK_TCK');page_size=os.sysconf('SC_PAGE_SIZE')
def process(pid):
    fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
    pages=int(Path(f'/proc/{pid}/statm').read_text().split()[1])
    return dict(cpu=sum(int(fields[i]) for i in (11,12,13,14))/clock_ticks,rss_mb=pages*page_size/1048576,start=fields[19])
def code_hash():
    files=sorted((root/'src').rglob('*.py'))+sorted((Path.home()/'.local/share/gnome-shell/extensions/zenek@brillnet').glob('companion-*.js'))
    return hashlib.sha256(b''.join(path.read_bytes() for path in files)).hexdigest()
status=call('GetStatus');build=status.get('core_build');assert build and status.get('release_stage')=='PREVIEW','Requires current identified Core build'
identity={pid:process(pid)['start'] for pid in (core_pid,shell_pid)};source_hash=code_hash()
samples=[];window=[];started=time.monotonic();last_sample=None;last_metrics=None;resets=0;reason=None
original_quiet=status['settings']['quiet'];quiet_owned=False;quiet_version=0;activity_event=False
if args.quiet and not original_quiet:
    quiet_version=call('UpdateSettings',dict(expected_version=status['config_version'],patch={'quiet':True}));quiet_owned=True
def event(_bus,_sender,_path,_interface,_signal,parameters):
    global quiet_owned,activity_event
    kind,raw=parameters.unpack()
    if kind!='StateChanged':return
    state=json.loads(raw)
    if state.get('ui_layout',{}).get('dialog_mapped') or 'conversation' in state.get('active_jobs',[]):activity_event=True
    if quiet_owned and state.get('config_version',0)>quiet_version and not state['settings']['quiet']:quiet_owned=False
subscription=bus.signal_subscribe('org.zenek.Desktop1','org.zenek.Desktop1','Event','/org/zenek/Desktop1',None,Gio.DBusSignalFlags.NONE,event)
def restore_quiet():
    global quiet_owned,subscription
    if quiet_owned:
        current=call('GetStatus')
        if current['settings']['quiet']:call('UpdateSettings',dict(expected_version=current['config_version'],patch={'quiet':original_quiet}))
        quiet_owned=False
    if subscription:bus.signal_unsubscribe(subscription);subscription=0
import atexit
atexit.register(restore_quiet)
def save(state):
    result=dict(status=state,reason=reason,core_pid=core_pid,shell_pid=shell_pid,core_build=build,source_hash=source_hash,started_at=wall_start,elapsed_seconds=round(time.monotonic()-started,1),continuous_no_dialog_seconds=round(window[-1]['elapsed']-window[0]['elapsed'],1) if len(window)>1 else 0,dialogue_resets=resets,samples=len(samples),controlled_quiet=args.quiet,original_quiet=original_quiet,quiet_restore_owned=quiet_owned)
    for label in ('core','shell'):
        values=[row[label+'_rss_mb'] for row in window];cpu=[row[label+'_cpu_percent'] for row in window if row[label+'_cpu_percent'] is not None]
        if values:result[label]=dict(rss_start_mb=round(statistics.median(values[:6]),2),rss_end_mb=round(statistics.median(values[-6:]),2),rss_peak_mb=round(max(values),2),cpu_mean_percent=round(statistics.mean(cpu),2) if cpu else 0,cpu_peak_percent=round(max(cpu),2) if cpu else 0)
    output.write_text(json.dumps(result,indent=2));return result
wall_start=time.time();print(json.dumps(dict(status='RUNNING',monitor_pid=os.getpid(),core_pid=core_pid,shell_pid=shell_pid,core_build=build)),flush=True)
def interrupted(number,_frame):
    global reason
    reason='Measurement interrupted by signal '+str(number)
    restore_quiet();print(json.dumps(save('INCOMPLETE')),flush=True);sys.exit(2)
signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
try:
    while time.monotonic()-started<=14400:
        now=time.monotonic();current={label:process(pid) for label,pid in [('core',core_pid),('shell',shell_pid)]}
        if any(current[label]['start']!=identity[pid] for label,pid in [('core',core_pid),('shell',shell_pid)]):reason='Observed process restarted';break
        s=call('GetStatus')
        if s.get('core_build')!=build or not s.get('ui_attached'):reason='Build changed or UI heartbeat missing';break
        if len(samples)%6==0 and code_hash()!=source_hash:reason='Source/installed extension changed during measurement';break
        elapsed=now-started;row=dict(elapsed=elapsed)
        for label in ('core','shell'):
            row[label+'_rss_mb']=current[label]['rss_mb']
            row[label+'_cpu_percent']=(current[label]['cpu']-last_metrics[label]['cpu'])/(now-last_sample)*100 if last_metrics else None
        samples.append(row)
        talking=activity_event or s.get('ui_layout',{}).get('dialog_mapped') or 'conversation' in s.get('active_jobs',[])
        activity_event=False
        if talking:
            if window:resets+=1
            window=[]
        else:window.append(row)
        result=save('RUNNING')
        if len(samples)%6==1:print(json.dumps(result),flush=True)
        if result['continuous_no_dialog_seconds']>=args.duration:
            if args.duration<3600:reason='Short sampling check; not one-hour acceptance';break
            for label in ('core','shell'):
                metric=result[label]
                if metric['rss_end_mb']-metric['rss_start_mb']>max(64,metric['rss_start_mb']*.5):reason='RSS growth requires review: '+label
                if metric['cpu_mean_percent']>(15 if label=='core' else 30):reason='Sustained CPU requires review: '+label
            if not reason:
                restore_quiet()
                print(json.dumps(save('PASS')),flush=True);raise SystemExit(0)
            break
        last_sample=now;last_metrics=current
        for _ in range(10):
            context=GLib.MainContext.default()
            while context.pending():context.iteration(False)
            time.sleep(1)
    if not reason:reason='Four-hour deadline without continuous no-dialog hour'
except (FileNotFoundError,RuntimeError,GLib.Error) as error:reason=type(error).__name__+': '+str(error)
restore_quiet();print(json.dumps(save('INCOMPLETE')),flush=True);raise SystemExit(2)
