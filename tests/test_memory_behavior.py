import json
import threading
import time
import pytest
from zenek_core.memory import Memory,MemoryBlocked
from zenek_core.behavior import Behavior

@pytest.fixture
def memory(tmp_path):
    m=Memory(tmp_path/"private"/"memory.db", "ab"*32)
    yield m
    m.close()

def test_encrypted_restart_and_wrong_key(memory):
    text="SYNTHETIC_SECRET_MUST_NOT_APPEAR_ON_DISK"
    memory.add("relationship_note",{"text":text},"synthetic",.5)
    path=memory.path
    assert text.encode() not in path.read_bytes()
    assert not path.read_bytes().startswith(b"SQLite format 3")
    assert path.stat().st_mode & 0o777 == 0o600
    fresh=Memory(path,"ab"*32)
    assert fresh.records("relationship_note")[0]["body"]["text"]==text
    fresh.close()
    with pytest.raises(Exception):Memory(path,"cd"*32)

def test_profiles_are_independent_and_stale_version_fails(memory):
    version,s=memory.settings()
    background=dict(s["background_cognition"])
    memory.patch({"conversation":dict(model_id="synthetic",reasoning_effort="low",status="READY")},version)
    assert memory.settings()[1]["background_cognition"]==background
    assert memory.settings()[1]["conversation"]["status"]=="UNAVAILABLE"
    with pytest.raises(ValueError):memory.patch({"quiet":True},version)

def test_rolling_budget_restart_midnight_cooldown(memory):
    now=1_799_999_000
    assert memory.reserve("background",86400,20,1800,now)
    assert memory.reserve("background",86400,20,1800,now+1799) is None
    for i in range(1,20):assert memory.reserve("background",86400,20,1800,now+1800*i)
    reopened=Memory(memory.path,"ab"*32)
    assert reopened.reserve("background",86400,20,1800,now+1800*20) is None
    assert reopened.reserve("background",86400,20,1800,now+86401)
    reopened.close()

def test_atomic_spontaneous_budget(memory):
    results=[]
    threads=[threading.Thread(target=lambda:results.append(memory.reserve("spontaneous",3600,3,0,now=1000))) for _ in range(12)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert sum(x is not None for x in results)==3

class AlwaysOpportunity:
    def random(self):return 0
    def choice(self,values):return values[0]
    def uniform(self,a,b):return (a+b)/2

def test_idle_lock_hidden_dnd_suspend_and_no_catchup(memory):
    b=Behavior(memory,AlwaysOpportunity());_,s=memory.settings()
    b.idle_seconds=899;b.last_ui_report=time.monotonic()
    assert b.allowed(s)
    b.idle_seconds=900;assert not b.allowed(s)
    b.idle_seconds=0;b.locked=True;assert not b.allowed(s)
    b.locked=False;b.suspended=True;assert not b.allowed(s)
    b.suspended=False;b.manual_visible=False;assert not b.allowed(s)
    b.manual_visible=True;b.fullscreen=True;assert not b.allowed(s)
    s["auto_hide_on_fullscreen"]=False;assert b.allowed(s)
    s["quiet"]=True;assert not b.allowed(s)
    s["quiet"]=False;b.interacting=True;assert not b.allowed(s)
    b.interacting=False;b.fullscreen=False
    first=b.opportunity(s,10000);assert first
    assert b.opportunity(s,10899) is None
    assert b.opportunity(s,10900)
    assert b.opportunity(s,11800)
    assert b.opportunity(s,12700) is None
    # No mandated utterance or backlog on return: opportunity still gated by RNG/context.
    b.idle_seconds=900;assert b.opportunity(s,30000) is None
    assert memory.db.execute("SELECT count(*) FROM usage WHERE kind='initiative_attempt'").fetchone()[0]==3
    assert memory.db.execute("SELECT count(*) FROM usage WHERE kind='spontaneous'").fetchone()[0]==0

def test_slow_generation_cannot_shrink_display_cooldown(memory):
    b=Behavior(memory,AlwaysOpportunity());_,s=memory.settings();b.idle_seconds=0;b.last_ui_report=time.monotonic()
    assert b.opportunity(s,10000)
    # First answer takes ten minutes; the next offer cannot appear 15 minutes
    # after generation began, because the display clock starts later.
    assert b.reserve_display(s,10600)
    assert b.opportunity(s,10900) is None
    assert b.reserve_display(s,11499) is None
    b.composing=True;assert b.reserve_display(s,11500) is None
    b.composing=False;assert b.reserve_display(s,11500)

def test_active_pet_can_stay_silent_over_two_hours_without_catchup(memory):
    class SilentRng(AlwaysOpportunity):
        def random(self):return 1
    b=Behavior(memory,SilentRng());_,s=memory.settings();b.idle_seconds=0;b.last_ui_report=time.monotonic()
    assert b.allowed(s)
    for now in range(10000,20801,300):assert b.opportunity(s,now) is None
    assert not memory.usage(),'Silence must not reserve a minimum number of utterances'
    b.rng=AlwaysOpportunity()
    assert b.opportunity(s,20801)
    assert b.opportunity(s,20802) is None
    assert memory.db.execute('SELECT kind,count(*) FROM usage GROUP BY kind').fetchall()==[('initiative_attempt',1)],'Return must not replay skipped opportunities'
