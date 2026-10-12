"""Deploy own tested batch and observe real Portal recovery after own UI disable/enable.

Owner requested the periodic plan to remain enabled. No injected lock/idle,
no OS session changes, no screenshots or private screen text in evidence.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path
from zenek_core.ipc import call

root=Path(__file__).resolve().parents[1]
original=call('GetStatus')
assert not original['locked'] and not original['suspended'] and not original['idle']
assert not original['ui_layout'].get('dialog_mapped') and not original['ui_layout'].get('composing') and 'conversation' not in original['active_jobs']
expected=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((root/'src/zenek_core').glob('*.py')))).hexdigest()[:12]
def pid():return int(subprocess.check_output(['systemctl','--user','show','zenek-core.service','--property=MainPID','--value'],text=True))
def shells():
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if (p/'comm').read_text().strip()=='gnome-shell':result.append(p.name)
        except OSError:pass
    return sorted(result)
def wait(predicate,message,timeout=25):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            state=call('GetStatus')
            if predicate(state):return state
        except RuntimeError:pass
        time.sleep(.2)
    raise AssertionError(message)
keys=('core_build','screen','capture_phase','capture_pipeline_state','capture_portal_session','capture_frames','capture_pause_reason','ui_attached')
def record(state):return dict(**{k:state.get(k) for k in keys},enabled=state['settings']['capture_enabled'])
states={};old_pid=pid();shell_before=shells();disabled=False
try:
    subprocess.run(['bash',str(root/'scripts/deploy-user-build.sh')],check=True)
    start=wait(lambda s:s['core_build']==expected and s['ui_attached'],'New Core/UI not attached')
    new_pid=pid();assert start['settings']==original['settings'],'Deployment changed saved settings'
    states['deployed']=record(start)
    call('ResumeScreenCapture')
    first=wait(lambda s:s['screen']=='ACTIVE' and s['capture_frames']>0 and s['capture_phase']=='WAITING' and not s['capture_portal_session'],'First real restored snapshot did not complete')
    states['enabled']=record(first)
    subprocess.run(['gnome-extensions','disable','zenek@brillnet'],check=True);disabled=True
    paused=wait(lambda s:s['screen']=='OFF' and s['capture_pipeline_state']=='NULL' and not s['capture_portal_session'],'UI removal did not pause source')
    assert paused['settings']['capture_enabled'] and call('GetRedactedPreview') is None
    states['paused']=record(paused)
    subprocess.run(['gnome-extensions','enable','zenek@brillnet'],check=True);disabled=False
    resumed=wait(lambda s:s['ui_attached'] and s['screen']=='ACTIVE' and s['capture_frames']>first['capture_frames'] and s['capture_phase']=='WAITING' and not s['capture_portal_session'],'Saved plan did not resume through real Portal grant')
    states['resumed']=record(resumed)
    assert pid()==new_pid and shells()==shell_before
    assert {k:v for k,v in resumed['settings'].items() if k!='capture_enabled'}=={k:v for k,v in original['settings'].items() if k!='capture_enabled'}
    model=call('GetSelfModel');assert len(model['categories'])==9 and model['facet_count']>=4
    result=dict(status='PASS',source_build=expected,old_pid=old_pid,new_pid=new_pid,states=states,owner_plan_restored_on=True,other_settings_preserved=True,gnome_not_restarted=True,core_survived_ui_pause=True,real_portal_grant_reused=True,source_closed_between_snapshots=True,self_categories=len(model['categories']),self_facets=model['facet_count'],scope='Actual original Core/installed GNOME UI/Portal; real UI loss/resume, no fake OS states. Lock/idle/suspend branches covered by focused regressions, no new physical cycle claimed.')
except Exception as error:
    result=dict(status='FAIL',reason=str(error),states=states)
    raise
finally:
    if disabled:subprocess.run(['gnome-extensions','enable','zenek@brillnet'],check=True)
    if 'result' in locals():
        (root/'evidence/capture-resume-runtime.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
