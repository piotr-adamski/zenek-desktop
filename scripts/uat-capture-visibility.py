"""Actual default hide/show and UI-removal capture policy on owner Core.

Never enables capture while hidden; preserves existing consent and settings.
"""
import json
from pathlib import Path
import subprocess
import time
from zenek_core.ipc import call

root=Path(__file__).resolve().parents[1]

def wait(check,message,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        state=call('GetStatus')
        if check(state):return state
        time.sleep(.1)
    raise AssertionError(message)

def closed(state):
    return state['screen']=='OFF' and state['capture_pipeline_state']=='NULL' and not state['capture_portal_session']

def sample(state):
    return {k:state[k] for k in ('visibility','manual_visible','screen','capture_phase','capture_pipeline_state','capture_portal_session','capture_frames')}

original=call('GetStatus')
assert original['visibility']=='VISIBLE' and original['screen']=='ACTIVE'
assert not original['ui_layout'].get('dialog_mapped') and 'conversation' not in original['active_jobs']
core_pid=int(subprocess.check_output(['systemctl','--user','show','zenek-core.service','--property=MainPID','--value'],text=True))
states=[];ui_disabled=False;result=None
try:
    if original['settings']['allow_capture_while_hidden']:
        call('UpdateSettings',{'expected_version':original['config_version'],'patch':{'allow_capture_while_hidden':False}})
    call('HideCompanion')
    hidden=wait(lambda s:closed(s) and s['visibility']=='HIDDEN','Default hide did not stop capture')
    states.append(dict(step='default hide stops',**sample(hidden)))
    assert call('GetRedactedPreview') is None
    time.sleep(3)
    assert call('GetStatus')['capture_frames']==hidden['capture_frames']
    # Actual launcher must show existing hidden Core rather than create another.
    subprocess.run([str(Path.home()/'.local/bin/zenek'),'start'],check=True,timeout=10)
    shown=wait(lambda s:s['visibility']=='VISIBLE' and closed(s),'Launcher restarted capture')
    states.append(dict(step='launcher shows without capture resume',**sample(shown)))
    assert int(subprocess.check_output(['systemctl','--user','show','zenek-core.service','--property=MainPID','--value'],text=True))==core_pid
    call('ResumeScreenCapture')
    wait(lambda s:s['screen']=='ACTIVE' and s['capture_frames']>shown['capture_frames'] and s['capture_phase']=='WAITING','Existing source did not restore')
    subprocess.run(['gnome-extensions','disable','zenek@brillnet'],check=True,timeout=10);ui_disabled=True
    removed=wait(closed,'Removing UI did not close source immediately',seconds=3)
    states.append(dict(step='extension disable stops capture',**sample(removed)))
    assert call('GetRedactedPreview') is None
    time.sleep(3)
    assert call('GetStatus')['capture_frames']==removed['capture_frames']
    subprocess.run(['gnome-extensions','enable','zenek@brillnet'],check=True,timeout=10);ui_disabled=False
    restored=wait(lambda s:s.get('ui_attached') and s['ui_layout'].get('sprite_mapped') and closed(s),'UI enable implicitly resumed capture')
    states.append(dict(step='extension enable leaves capture OFF',**sample(restored)))
    result=dict(status='PASS',scope='actual original Core, installed per-user extension and launcher; default branch tested with hidden exception OFF',core_pid=core_pid,core_build=original['core_build'],states=states,hidden_frames_stopped=True,preview_cleared=True,launcher_shows_same_core=True,show_no_auto_resume=True,ui_disable_source_closed=True,ui_enable_no_auto_resume=True,no_core_restart=True,default_branch_tested_with_hidden_exception_off=True,original_hidden_capture_setting=original['settings']['allow_capture_while_hidden'])
finally:
    if ui_disabled:subprocess.run(['gnome-extensions','enable','zenek@brillnet'],check=True,timeout=10)
    current=call('GetStatus')
    if original['manual_visible'] and not current['manual_visible']:call('ShowCompanion')
    wait(lambda s:s.get('ui_attached') and s['ui_layout'].get('sprite_mapped'),'Owner UI did not return')
    current=call('GetStatus')
    if current['settings']['allow_capture_while_hidden']!=original['settings']['allow_capture_while_hidden']:
        call('UpdateSettings',{'expected_version':current['config_version'],'patch':{'allow_capture_while_hidden':original['settings']['allow_capture_while_hidden']}})
    # Explicit maintenance restoration of the existing owner-enabled plan.
    if original['screen']=='ACTIVE' and call('GetStatus')['screen']=='OFF':
        call('ResumeScreenCapture')
        wait(lambda s:s['screen']=='ACTIVE','Could not restore original capture plan')
    final=call('GetStatus')
    assert final['settings']==original['settings'],'Owner settings changed'
    assert final['core_build']==original['core_build']
if result:
    result['owner_settings_and_capture_plan_restored']=True
    (root/'evidence/capture-visibility-runtime.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
