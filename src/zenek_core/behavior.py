import random
import time
from .narrative import Variety
from .mind import Mind

class Behavior:
    def __init__(self,memory,rng=None):
        self.memory=memory;self.rng=rng or random.Random()
        self.mood=dict(curiosity=.8,sociability=.55,playfulness=.7,irritability=.2,contemplation=.5,energy=.7)
        self.manual_visible=True;self.fullscreen=False;self.locked=False;self.suspended=False
        self.idle_seconds=None;self.last_ui_report=0;self.interacting=False;self.composing=False
        self.activity="idle";self.next_review=time.monotonic()+self.rng.uniform(15,90)
        self.last_screen_topic=None
        saved=self.memory.records('self_state',1)
        if saved:self.mood.update(saved[0]['body'].get('mood',{}))
        self.last_local_update=time.monotonic()

    def visible(self,s):
        return self.manual_visible and not self.locked and not self.suspended and not (self.fullscreen and s["auto_hide_on_fullscreen"])

    def absent(self,s):
        return self.locked or self.idle_seconds is None or self.idle_seconds>=s["idle_threshold_minutes"]*60 or time.monotonic()-self.last_ui_report>15

    def allowed(self,s):
        return self.visible(s) and not self.absent(s) and not s["quiet"] and s["initiative"] and not self.interacting and not self.composing

    def opportunity(self,s,now=None,screen_topic=None):
        now=time.time() if now is None else now
        if not self.allowed(s): return None
        candidates=self.memory.records("open_thread")+self.memory.records("interest")+Mind(self.memory).candidates()
        variety=Variety(self.memory)
        candidates=[r for r in candidates if self.memory.topic_allowed(r['body']) and now-r["body"].get("last_mentioned",0)>7200]
        candidates=[r for r in candidates if variety.allows(r,now)]
        candidates=[r for r in candidates if not r['body'].get('proposal_id') or not r['body'].get('last_mentioned',0)]
        priority=s.get('screen_comment_priority','off')
        screen=screen_topic if priority!='off' and screen_topic and screen_topic['id']!=self.last_screen_topic and self.memory.topic_allowed(screen_topic['body']) and variety.allows(screen_topic,now) else None
        if not candidates and not screen:return None
        for k in self.mood:self.mood[k]=min(1,max(0,self.mood[k]+self.rng.uniform(-.02,.02)))
        traits=s["traits"]
        score=self.mood["curiosity"]*traits["curiosity"]+self.mood["sociability"]*traits["sociability"]
        score+=max((r['body'].get('strength',.5) for r in candidates),default=.5)*traits['independence']*.3
        if self.rng.random()>score*(1-traits["restraint"])*.6:return None
        if screen and (not candidates or self.rng.random()<({'balanced':.5,'high':.8}.get(priority,0))):candidate=screen
        else:candidate=self.rng.choice(candidates)
        if not self.memory.can_reserve('spontaneous',3600,s['spontaneous_limit'],s['spontaneous_cooldown_minutes']*60,now):return None
        ticket=self.memory.reserve("initiative_attempt",3600,s["spontaneous_limit"],s["spontaneous_cooldown_minutes"]*60,now)
        return (dict(candidate,angle=variety.angle(self.rng)),ticket) if ticket else None

    def reserve_display(self,s,now=None):
        if not self.allowed(s):return None
        return self.memory.reserve('spontaneous',3600,s['spontaneous_limit'],s['spontaneous_cooldown_minutes']*60,now)

    def surfaced(self,record):
        if record.get('source')=='screen_current':self.last_screen_topic=record['id'];return
        body=dict(record["body"],last_mentioned=time.time(),status="surfaced")
        self.memory.update(record["id"],body)

    def local_step(self,s):
        if self.suspended:return
        if self.interacting:self.activity='thinking'
        elif self.absent(s):self.activity='sleeping'
        elif s['quiet']:self.activity='quiet'
        elif time.monotonic()-self.last_local_update>20:
            choices=['idle','roaming','curious','thinking','amused','irritated','listening','waking']
            self.activity=self.rng.choice(choices)
        if time.monotonic()-self.last_local_update>300:
            for k in self.mood:self.mood[k]=min(1,max(0,self.mood[k]+self.rng.uniform(-.03,.03)))
            rows=self.memory.records('self_state',1)
            body=dict(activity=self.activity,mood=self.mood,drives=dict(conversation=self.mood['sociability'],curiosity=self.mood['curiosity'],silence=s['traits']['restraint']))
            if rows:self.memory.update(rows[0]['id'],body)
            else:self.memory.add('self_state',body,'local_behavior',1)
            self.last_local_update=time.monotonic()
