"""Own SIWC/Core test: cancel a synthetic turn, immediately send another.

Requires capture OFF and no active jobs. No settings changes or credentials
are exported. Only request identifiers/status/timing enter evidence.
"""
import json
import time
from pathlib import Path
from gi.repository import Gio,GLib
from zenek_core.ipc import call,NAME,PATH

start=call('GetStatus')
if start['screen']!='OFF' or start['active_jobs'] or start['locked']:
    raise RuntimeError('Requires capture OFF, no active jobs and unlocked session')
profile=start['settings']['conversation']
if profile['model_id']!='gpt-6.1-sol' or profile['reasoning_effort']!='medium' or profile['status']!='READY':
    raise RuntimeError('Requires owner-selected ready gpt-6.1-sol/medium')
loop=GLib.MainLoop();turns={};outcome={};cancelled_at=None;started=time.monotonic();exit_code=1
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
def finish(status,reason=None):
    global exit_code
    if outcome:return GLib.SOURCE_REMOVE
    call('CancelResponse')
    s=call('GetStatus')
    outcome.update(status=status,reason=reason,model=profile['model_id'],effort=profile['reasoning_effort'],first_cancelled=cancelled_at is not None,new_turn_accepted='second' in turns,new_turn_completed=status=='PASS',cancel_to_new_completion_seconds=round(time.monotonic()-cancelled_at,3) if cancelled_at else None,profile_still_ready=s['settings']['conversation']==profile,paid_api_approved=s['settings']['paid_api_approved'])
    Path('evidence/provider-native-runtime.json').write_text(json.dumps(outcome,indent=2));print(outcome,flush=True)
    exit_code=0 if status=='PASS' else 1;loop.quit();return GLib.SOURCE_REMOVE
def event(_bus,_sender,_path,_interface,_signal,parameters):
    global cancelled_at
    kind,raw=parameters.unpack();p=json.loads(raw)
    try:
        if kind=='ReplyDelta' and p['turn']==turns.get('first') and cancelled_at is None:
            cancelled_at=time.monotonic();call('CancelResponse')
            turns['second']=call('SendText',{'text':'Własny syntetyczny test po anulowaniu. Napisz dokładnie: połączenie działa.'})
        elif kind=='ReplyCompleted':
            if p['turn']==turns.get('first'):finish('FAIL','First turn completed instead of cancelling')
            elif p['turn']==turns.get('second'):finish('PASS' if p['text'].strip().rstrip('.')=='połączenie działa' else 'FAIL','Unexpected synthetic response' if p['text'].strip().rstrip('.')!='połączenie działa' else None)
        elif kind=='ErrorChanged':finish('FAIL',p['message'])
    except Exception as error:finish('FAIL',type(error).__name__+': '+str(error))
subscription=bus.signal_subscribe(NAME,NAME,'Event',PATH,None,Gio.DBusSignalFlags.NONE,event)
def timeout():
    if time.monotonic()-started>45:return finish('FAIL','Timed out waiting for actual model/cancel/replacement')
    return GLib.SOURCE_CONTINUE
GLib.timeout_add(250,timeout)
turns['first']=call('SendText',{'text':'Własny syntetyczny test anulowania. Napisz obszerny tekst, co najmniej 1000 słów, o fikcyjnym robocie zbierającym kamienie na Marsie. Bez sekretów i prawdziwych osób.'})
try:loop.run()
finally:bus.signal_unsubscribe(subscription)
raise SystemExit(exit_code)
