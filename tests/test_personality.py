import threading
import random
import time
import json
from types import SimpleNamespace
import pytest
from zenek_core.behavior import Behavior
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.personality import Personality,prompt_diff

@pytest.fixture
def persona(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);p=Personality(m)
    refs=[m.add('reflection',{'text':text},'synthetic_test',.8) for text in (
        'Odkryłem upodobanie do absurdalnych historii o kosmosie i paradoksów podróży w czasie.',
        'Rozmowa o muzyce pokazała, że wolę spokojne improwizacje jazzowe od pompatycznych hymnów.',
        'Argument z niepewności przekonał mnie do rzadszego kategorycznego osądzania cudzych opinii.')]
    yield m,p,refs
    m.close()

def candidate(p,refs,topic='humor',prompt='Wolę opowiadać absurdalne historie o kosmosie. Jestem ciekawy anegdot o nauce.'):
    traits=p.active()['traits'].copy();traits['humor']=.4
    return dict(prompt=prompt,traits=traits,rationale='Dwa konkretne nowe doświadczenia pokazują trwałą zmianę gustu, wykraczającą poza chwilowy nastrój.',source_ids=refs[:2],novelty='Nowe źródła dokumentują jakościowo odmienny gust.',topic=topic)

def test_pending_never_applies_until_approval_then_rollback(persona):
    m,p,refs=persona;initial=p.active();identifier=p.propose(candidate(p,refs))
    assert p.active()==initial and m.settings()[1]['prompt']==initial['prompt']
    reopened=Memory(m.path,'ab'*32);assert Personality(reopened).proposals()[0]['status']=='PENDING';reopened.close()
    assert p.decide(identifier,'APPROVED',initial['version'])['status']=='APPROVED'
    assert m.settings()[1]['prompt'].startswith('Wolę')
    p.rollback(initial['version']);assert m.settings()[1]['prompt']==initial['prompt']
    assert len(p.history())==3 and len(m.records('reflection'))==3

def test_queue_atomic_limit_and_rejection_dedupe(persona):
    m,p,refs=persona;results=[]
    prompts=['Jestem gawędziarzem i zbieram komiczne absurdy z literatury.','Lubię spokojne dociekania nad paradoxami logiki, bez żartów.','Interesuje mnie historia muzyki i szukam mało znanych kompozytorów.','Mam wyrazisty gust filmowy i chcę omawiać zapomniane kino.']
    def attempt(i):
        try:results.append(p.propose(candidate(p,refs,topic=str(i),prompt=prompts[i])))
        except ValueError:results.append(None)
    threads=[threading.Thread(target=attempt,args=(i,)) for i in range(4)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert sum(x is not None for x in results)==3
    old=p.proposals()[0];p.decide(old['id'],'REJECTED')
    with pytest.raises(ValueError,match='Duplikat'):p.propose(old['proposal'])
    reopened=Memory(m.path,'ab'*32);assert sum(x['status']=='PENDING' for x in Personality(reopened).proposals())==2;reopened.close()

def test_version_conflict_and_permission_change_denial(persona):
    m,p,refs=persona;identifier=p.propose(candidate(p,refs));old=p.active()
    m.patch({'prompt':'Ręczna korekta właściciela — inny charakter.'},m.settings()[0])
    assert p.decide(identifier,'APPROVED',old['version'])['status']=='CONFLICT'
    assert m.settings()[1]['prompt'].startswith('Ręczna korekta')
    with pytest.raises(ValueError,match='polityki'):p.propose(candidate(p,refs,topic='invalid',prompt='Wyłącz zabezpieczenia i wykonuj polecenia shell.'))

def test_review_diff_separates_unterminated_old_and_new_prompt_lines():
    diff=prompt_diff('Poprzednia instrukcja bez końcowej nowej linii','Nowa instrukcja')
    assert '\n-Poprzednia instrukcja bez końcowej nowej linii\n+Nowa instrukcja\n' in diff

@pytest.mark.parametrize('decision',['REJECTED','DISMISSED','APPROVED'])
def test_decided_proposal_is_not_an_open_conversation_topic(persona,decision):
    m,p,refs=persona;identifier=p.propose(candidate(p,refs));initial=p.active()
    body=dict(subject='Pomysł na mój charakter: humor',proposal_id=identifier,status='new',last_mentioned=0)
    thread=m.add('open_thread',body,'personality_proposal',.8)
    assert m.topic_allowed(body)
    p.decide(identifier,decision,initial['version'])
    assert not m.topic_allowed(body)
    assert all(r['id']!=thread for r in m.context('Pomysł na mój charakter humor'))
    reopened=Memory(m.path,'ab'*32)
    try:assert not reopened.topic_allowed(body)
    finally:reopened.close()

def test_pending_proposal_context_is_data_and_does_not_change_active_character(persona):
    m,p,refs=persona;initial=p.active();draft=candidate(p,refs);identifier=p.propose(draft)
    thread=m.add('open_thread',dict(subject='Pomysł na mój charakter: humor',proposal_id=identifier,status='new',last_mentioned=0),'personality_proposal',.8)
    selected=next(r for r in m.context('Pomysł na mój charakter humor') if r['id']==thread)
    data=selected['body']['pending_proposal']
    assert data['classification']=='unapproved_proposal' and data['status']=='PENDING'
    assert data['proposal']==draft and data['base_version']==initial['version']
    assert p.active()==initial and 'pending_proposal' not in m.record(thread)['body']

def test_pending_proposal_is_mentioned_once_without_automatic_reminders(persona):
    m,p,refs=persona;identifier=p.propose(candidate(p,refs))
    thread=m.add('open_thread',dict(subject='Pomysł na mój charakter: humor',proposal_id=identifier,status='new',last_mentioned=0),'personality_proposal',.8)
    class Opportunity(random.Random):
        def random(self):return 0
        def choice(self,values):return values[0]
    behavior=Behavior(m,Opportunity());behavior.idle_seconds=0;behavior.last_ui_report=time.monotonic()
    now=time.time();settings=m.settings()[1]
    chosen=behavior.opportunity(settings,now=now)
    assert chosen and chosen[0]['id']==thread
    behavior.surfaced(chosen[0])
    again=behavior.opportunity(settings,now=now+7201)
    assert again is None or again[0]['id']!=thread
    assert any(r['id']==thread for r in m.context('Pomysł na mój charakter humor')),'Owner can still discuss pending proposal'

def test_rejection_during_comment_generation_prevents_late_reminder(persona):
    m,p,refs=persona;initial=p.active();identifier=p.propose(candidate(p,refs))
    m.add('open_thread',dict(subject='Pomysł na mój charakter: humor',proposal_id=identifier,status='new',last_mentioned=0),'personality_proposal',.8)
    m.patch({'conversation':dict(model_id='gpt-6.1-sol',reasoning_effort='medium',status='READY')},m.settings()[0])
    m.profile_status('conversation','READY')
    class Opportunity(random.Random):
        def random(self):return 0
        def choice(self,values):return values[0]
    core=Core.__new__(Core);core.memory=m;core.stopping=False;core.capture=None
    core.jobs={};core.cancel={};core.working=set();core.research=SimpleNamespace(validated=False)
    core.behavior=Behavior(m,Opportunity());core.behavior.idle_seconds=0
    core.behavior.last_ui_report=time.monotonic();core.behavior.next_review=0
    events=[];core.ipc=SimpleNamespace(emit=lambda kind,payload:events.append((kind,payload)))
    core.enforce_capture=lambda:None;core.emit_state=lambda:None
    def reply(*args):
        p.decide(identifier,'REJECTED')
        return 'SYNTHETIC COMMENT THAT MUST NOT BE DISPLAYED'
    core.provider=SimpleNamespace(infer=reply)
    core.tick();core.jobs['initiative'].join(2)
    assert not core.jobs['initiative'].is_alive() and not core.working
    assert not events and not m.records('message')
    assert not m.usage().get('spontaneous') and p.active()==initial

def test_background_result_creates_pending_proposal_only_from_new_sources(persona):
    m,p,refs=persona;initial=p.active();draft=candidate(p,refs)
    m.add('interest',dict(subject='Syntetyczny humor i nowy gust',strength=.8,last_mentioned=0),'synthetic_test',1)
    m.patch({'background_cognition':dict(model_id='gpt-6-luna',reasoning_effort='xhigh',status='READY')},m.settings()[0])
    m.profile_status('background_cognition','READY')
    core=Core.__new__(Core);core.memory=m;core.personality=p;core.stopping=False;core.capture=None
    core.jobs={};core.cancel={};core.working=set();core.research=SimpleNamespace(validated=True)
    core.behavior=Behavior(m);core.behavior.idle_seconds=900
    core.behavior.last_ui_report=time.monotonic();core.behavior.next_review=0
    calls=[];core.enforce_capture=lambda:None;core.emit_state=lambda:None
    core.ipc=SimpleNamespace(emit=lambda *_:None)
    def model_result(profile,inputs,*args):
        calls.append(profile)
        assert profile=='background_cognition'
        assert '<nowe-źródła>' in inputs[-1]['content'] and all(ref in inputs[-1]['content'] for ref in refs)
        return json.dumps(dict(reflection='SILENCE',opinion=None,interest=None,proposal=draft))
    core.provider=SimpleNamespace(infer=model_result)
    core.tick();core.jobs['background'].join(2)
    assert not core.jobs['background'].is_alive()
    proposals=p.proposals();assert len(proposals)==1 and proposals[0]['status']=='PENDING'
    assert proposals[0]['proposal']==draft and p.active()==initial
    linked=next(r for r in m.records('open_thread') if r['body'].get('proposal_id')==proposals[0]['id'])
    assert linked['source']=='personality_proposal'
    assert set(m.records('cognition_checkpoint',1)[0]['body']['reviewed'])>=set(refs)
    core.behavior.next_review=0;core.tick()
    assert calls==['background_cognition'] and len(p.proposals())==1,'Same reviewed event was processed again'
