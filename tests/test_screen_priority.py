import json
import threading
import time
from types import SimpleNamespace
import pytest
from zenek_core.behavior import Behavior
from zenek_core.main import Core
from zenek_core.memory import Memory

class FixedRng:
    def __init__(self,selection):self.selection=selection;self.calls=0
    def uniform(self,a,b):return (a+b)/2
    def random(self):
        self.calls+=1
        return 0 if self.calls%2 else self.selection
    def choice(self,values):return values[0]

@pytest.mark.parametrize('priority,selection,expected',[('off',0,'original_seed'),('balanced',.49,'screen_current'),('balanced',.51,'original_seed'),('high',.79,'screen_current'),('high',.81,'original_seed')])
def test_priority_routes_topic_without_raising_limits(tmp_path,priority,selection,expected):
    m=Memory(tmp_path/'db','ab'*32);_,s=m.settings();s['screen_comment_priority']=priority
    b=Behavior(m,FixedRng(selection));b.last_ui_report=time.monotonic();b.idle_seconds=0
    screen=dict(id='fresh-screen',source='screen_current',body={'subject':'aktualna niesekretna treść ekranu'})
    opportunity=b.opportunity(s,10000,screen);assert opportunity[0]['source']==expected
    assert b.opportunity(s,10001,screen) is None # Existing rolling cooldown still applies.
    if expected=='screen_current':
        before=m.records();b.surfaced(opportunity[0]);assert m.records()==before
        b.rng=FixedRng(0)
        assert b.opportunity(s,10900,screen)[0]['source']!='screen_current' # Same frame isn't repeated.
    s['quiet']=True;assert b.opportunity(s,20000,screen) is None
    m.close()

def test_screen_context_needs_live_consent_ready_profile_and_fresh_same_generation(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);m.patch({'screen_comment_priority':'high','vision':{'model_id':'synthetic','reasoning_effort':'medium','status':'READY'}},m.settings()[0]);m.profile_status('vision','READY')
    core=Core.__new__(Core);core.memory=m;core.preview_lock=threading.RLock();core.capture=SimpleNamespace(state='ACTIVE',generation=7)
    permitted=True;core.capture_permitted=lambda:permitted
    core.screen_context=dict(id='scene',text='Syntetyczna niesekretna treść',generation=7,observed_at=time.time(),confirmed_mono=time.monotonic(),interpreted_mono=time.monotonic())
    assert core.current_screen_topic()['body']['classification']=='interpretation'
    core.capture.state='OFF';assert core.current_screen_topic() is None
    core.capture.state='ACTIVE';permitted=False;assert core.current_screen_topic() is None
    permitted=True;core.capture.generation=8;assert core.current_screen_topic() is None
    core.capture.generation=7;core.screen_context['confirmed_mono']-=181;assert core.current_screen_topic() is None
    core.screen_context['confirmed_mono']=time.monotonic();core.screen_context['interpreted_mono']-=901;assert core.current_screen_topic() is None
    core.screen_context['interpreted_mono']=time.monotonic();m.profile_status('vision','UNAVAILABLE');assert core.current_screen_topic() is None
    with pytest.raises(ValueError):m.patch({'screen_comment_priority':'always'},m.settings()[0])
    # Older saved configuration reads the safe default, retaining other values.
    body=m.settings()[1];body.pop('screen_comment_priority');m.db.execute('UPDATE settings SET body=?',(json.dumps(body),));m.db.commit()
    assert m.settings()[1]['screen_comment_priority']=='off'
    m.close()
