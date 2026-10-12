import time
from types import SimpleNamespace
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.behavior import Behavior

def test_zenn_activity_is_tied_to_real_work_not_random_mood(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);core=Core.__new__(Core)
    core.memory=m;core.behavior=Behavior(m);core.behavior.idle_seconds=0;core.behavior.last_ui_report=time.monotonic()
    core.capture=SimpleNamespace(state='OFF');core.provider=SimpleNamespace(auth_status='AUTHORIZED')
    core.working=set();core.failure_at=0;core.greeting_until=0;core.positive_until=0
    core.behavior.activity='irritated'
    assert core.animation()['state']=='sleeping' # Mood never invents work or failure.
    core.working={'conversation'};assert core.animation()['state']=='running'
    core.working={'vision'};assert core.animation()['state']=='blinking'
    core.working={'research'};assert core.animation()['state']=='blinking'
    core.working=set();core.capture.state='ACTIVE';core.capture.phase='SNAPSHOT';assert core.animation()['state']=='blinking'
    core.capture.phase='WAITING';assert core.animation()['state']=='sleeping'
    core.working=set();core.capture.state='AWAITING_PORTAL';assert core.animation()['state']=='waiting'
    core.capture.state='OFF';core.failure_at=time.monotonic();assert core.animation()['state']=='failed'
    core.behavior.suspended=True;assert core.animation()['state']=='sleeping'
    m.close()

def test_reopening_dialog_returns_only_latest_exchange(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);c=Core.__new__(Core);c.memory=m;c.behavior=Behavior(m)
    for role,text,source in [('user','OLD USER','conversation'),('assistant','OLD REPLY','model_reply'),('user','NEW USER','conversation'),('assistant','NEW REPLY','model_reply')]:m.add('message',dict(role=role,text=text),source,1)
    assert [r['body']['text'] for r in c.handle('GetLatestExchange',{})]==['NEW USER','NEW REPLY']
    m.add('message',dict(role='assistant',text='NEW INITIATIVE'),'initiative',1)
    assert [r['body']['text'] for r in c.handle('GetLatestExchange',{})]==['NEW INITIATIVE']
    m.close()
