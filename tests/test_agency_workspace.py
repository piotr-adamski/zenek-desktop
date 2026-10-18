import json
import threading
import time
from types import SimpleNamespace

import pytest

from zenek_core.agency import Agency
from zenek_core.behavior import Behavior
from zenek_core.cognition import ToolSession
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.mind import Mind
from zenek_core.notebook import Notebook
from zenek_core.personality import Personality
from zenek_core.provider import Provider,ProviderBlocked
from zenek_core.workspace import Workspace


@pytest.fixture
def memory(tmp_path):
    value=Memory(tmp_path/'memory.db','cd'*32);Mind(value).bootstrap()
    yield value
    value.close()


def test_private_hobby_can_grow_without_becoming_an_invitation(memory):
    agency=Agency(memory)
    agency.choose('Harmonia jazzowa','hobby','private','Chcę ćwiczyć dla siebie.')
    interest=next(r for r in memory.records('interest') if r['body']['subject']=='Harmonia jazzowa')
    assert memory.topic_allowed(interest['body'])
    assert not memory.topic_allowed(interest['body'],'share')
    plan=agency.plan('Harmonia jazzowa','discuss',10,'Najpierw własna próba.')
    assert plan['kind']=='thought_task' and plan['mode']=='reflect'
    assert agency.next_task(time.time()+59) is None
    assert agency.next_task(time.time()+601)['id']==plan['id']
    assert 'Wykonaj teraz wybrany krok' in agency.prompt(agency.next_task(time.time()+601))
    agency.choose('Harmonia jazzowa','closed','private','Wystarczy mi tej próby.')
    assert agency.next_task(time.time()+601) is None
    assert memory.record(plan['id'])['body']['status']=='retired'
    assert not memory.topic_allowed(interest['body'])
    agency.choose('Harmonia jazzowa','curious','shared','Jednak wracam z własnej woli.')
    assert memory.topic_allowed(interest['body'],'share')


def test_dislike_and_closed_topics_do_not_leak_into_initiative(memory):
    for record in memory.records('interest'):memory.delete(record['id'])
    agency=Agency(memory)
    for subject,interest,sharing in [('Prywatne hobby','hobby','private'),('Porzucony temat','closed','shared'),('Nielubiany temat','dislike','shared')]:
        memory.add('interest',dict(subject=subject,last_mentioned=0),'test',1)
        agency.choose(subject,interest,sharing,'Własny wybór.')
    behavior=Behavior(memory);behavior.last_ui_report=time.monotonic();behavior.idle_seconds=0
    assert behavior.opportunity(memory.settings()[1]) is None
    assert agency.plan('Nielubiany temat','research',0,'Nie podejmuj.')['status']=='retired'


def test_active_private_work_is_not_started_again_by_periodic_tick(memory):
    core=Core.__new__(Core);core.memory=memory;core.stopping=False;core.behavior=Behavior(memory)
    core.jobs={'feedback':SimpleNamespace(is_alive=lambda:True)};core.enforce_capture=lambda:None
    core.feedback_step=lambda _:False;core.behavior.next_review=0
    core.current_screen_topic=lambda:pytest.fail('Periodic work entered while private work is active')
    assert core.tick()
    for delay in (float('nan'),float('inf')):
        with pytest.raises(ValueError):Agency(memory).plan('Rytm','practice',delay,'Próba.')


def test_feedback_is_once_per_utterance_and_finish_is_atomic_and_idempotent(memory):
    agency=Agency(memory);message=memory.add('message',dict(role='assistant',text='Mam własną myśl.'),'model_reply',1)
    first=agency.enqueue(message);assert agency.enqueue(message)==first
    assert len(memory.records('feedback_task'))==1
    task=agency.next_task();assert message in agency.prompt(task)
    result=agency.finish(task,json.dumps(dict(reflection='Chcę zrobić własną próbę.',decision='private hobby',reason='Ciekawość.')))
    assert agency.finish(task,'SILENCE')==result and len(memory.records('self_feedback'))==1
    assert agency.next_task() is None
    assert memory.record(first)['body']['result_id']==result
    with pytest.raises(ValueError):agency.enqueue(result)


def test_core_feedback_executes_private_agenda_without_bubble_or_recursion(memory,tmp_path):
    agency=Agency(memory);agency.choose('Rytm','hobby','private','Lubię układać rytmy.')
    plan=agency.plan('Rytm','practice',0,'Zapiszę własną próbę.')
    memory.profile_status('background_cognition','READY')
    core=Core.__new__(Core);core.memory=memory;core.behavior=Behavior(memory);core.jobs={};core.working=set();core.cancel={}
    calls=[];events=[];core.inputs=lambda text,**kw:[dict(role='user',content=text)];core.instructions=lambda:'test'
    core.workspace_changed=lambda kind:events.append(kind)
    def infer(profile,inputs,instructions,delta,cancel,purpose=None):
        calls.append((profile,purpose,inputs))
        session=ToolSession(memory,cancel);session.notebook=Notebook(tmp_path/'notebook')
        session.call('WriteNote',dict(path='hobbies/rytm.md',text='Moja własna próba: 3 + 2 + 3.'))
        return json.dumps(dict(reflection='Znalazłem rytm, do którego wrócę dla siebie.',decision='practice',reason='Lubię ten układ.'))
    core.provider=SimpleNamespace(infer=infer)
    def worker(name,fn):assert name=='feedback';fn(threading.Event())
    core.worker=worker
    assert core.feedback_step(memory.settings()[1])
    assert calls[0][0:2]==('background_cognition','feedback')
    assert memory.record(plan['id'])['body']['status']=='completed'
    assert (tmp_path/'notebook/hobbies/rytm.md').exists()
    assert events==['self_feedback'] and not memory.records('utterance') and not memory.records('message')
    assert not core.feedback_step(memory.settings()[1])


def test_cancellation_keeps_reflection_pending(memory):
    message=memory.add('message',dict(role='assistant',text='Myśl.'),'test',1);Agency(memory).enqueue(message)
    memory.profile_status('background_cognition','READY')
    core=Core.__new__(Core);core.memory=memory;core.behavior=Behavior(memory);core.jobs={}
    core.inputs=lambda text,**kw:[];core.instructions=lambda:'';core.workspace_changed=lambda _:pytest.fail('Cancelled reflection completed')
    def infer(*args,**kw):args[4].set();return 'SILENCE'
    core.provider=SimpleNamespace(infer=infer);core.worker=lambda _,fn:fn(threading.Event())
    assert core.feedback_step(memory.settings()[1])
    assert Agency(memory).next_task() and not memory.records('self_feedback')


def test_workspace_full_history_paging_polish_search_and_thread_context(memory,tmp_path):
    workspace=Workspace(memory,Notebook(tmp_path/'notebook'))
    identifiers=[memory.add('message',dict(role='user',text=f'Wątek {i}: ŻÓŁĆ'),'test',1) for i in range(65)]
    answer=memory.add('message',dict(role='assistant',text='Własna odpowiedź https://example.org/source.',in_reply_to=identifiers[0]),'test',1)
    first=workspace.conversation(limit=40);second=workspace.conversation(before=first['before'],limit=40)
    assert first['has_more'] and not second['has_more']
    assert {r['id'] for r in first['messages']+second['messages']}==set(identifiers+[answer])
    assert len(workspace.conversation(query='żółć',limit=100)['messages'])==65
    assert len(workspace.anchor(identifiers[0])['exchange'])==2
    assert workspace.conversation(query='example')['messages'][0]['sources']==['https://example.org/source']


def test_notebook_and_timeline_are_readable_linked_and_paged(memory,tmp_path):
    notebook=Notebook(tmp_path/'notebook');notebook.write('hobby/rytm.md','# Moje rytmy\n\nChcę ćwiczyć akcenty.\n\n[Źródło](https://example.org/rytm)')
    workspace=Workspace(memory,notebook)
    assert workspace.notes('AKCENTY')[0]['title']=='Moje rytmy'
    assert workspace.note('hobby/rytm.md')['sources']==['https://example.org/rytm']
    memory.add('message',dict(role='assistant',text='Zapis: notebook/hobby/rytm.md'),'test',1)
    assert workspace.conversation()['messages'][0]['note_paths']==['hobby/rytm.md']
    initial=Personality(memory).active()
    Personality(memory).evolve('Lubię uczyć się rytmu.',initial['traits'],'Własna próba sprawiła mi przyjemność.',[],initial['version'])
    Agency(memory).choose('Rytm','hobby','private','Lubię go ćwiczyć.')
    for i in range(45):memory.add('knowledge',dict(text=f'Własny wniosek {i}.'),'test',.7)
    first=workspace.development(limit=40);second=workspace.development(first['before'],40)
    assert first['has_more'] and not second['has_more']
    change=next(e for e in second['events'] if e['kind']=='personality_evolution')
    assert change['before']==initial['prompt'] and change['after']=='Lubię uczyć się rytmu.'
    assert change['text']=='Własna próba sprawiła mi przyjemność.'


def test_feedback_uses_background_model_without_periodic_cooldown(memory,monkeypatch):
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    memory.patch({'background_cognition':dict(model_id='synthetic',reasoning_effort='auto',status='UNAVAILABLE')},memory.settings()[0])
    provider=Provider(memory);provider.catalog=[dict(slug='synthetic')];provider.token=lambda:'SYNTHETIC_NONCREDENTIAL'
    async def stream(*_):return dict(text='SILENCE',items=[])
    provider._stream=stream
    assert memory.reserve('background',86400,30)
    with pytest.raises(ProviderBlocked,match='cooldown'):provider.infer('background_cognition',[],'',lambda _:None,threading.Event())
    assert provider.infer('background_cognition',[],'',lambda _:None,threading.Event(),purpose='feedback')=='SILENCE'
    assert memory.usage()['background']==2
