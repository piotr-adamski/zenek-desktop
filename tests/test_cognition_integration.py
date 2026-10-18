import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from zenek_core.behavior import Behavior
from zenek_core.cognition import CognitionTools,ToolSession
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.mind import Mind
from zenek_core.notebook import Notebook
from zenek_core.personality import Personality
from zenek_core.provider import Provider,ProviderBlocked
from zenek_core.web_worker import validate_query


@pytest.fixture
def memory(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);Mind(m).bootstrap()
    yield m
    m.close()


def test_real_provider_dispatches_streamed_tools_and_preserves_reasoning(memory,monkeypatch,tmp_path):
    memory.patch({'conversation':dict(model_id='synthetic',reasoning_effort='auto',status='UNAVAILABLE'),'web_enabled':True},memory.settings()[0])
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    monkeypatch.setattr('zenek_core.cognition.Notebook',lambda:Notebook(tmp_path/'notebook'))
    provider=Provider(memory);provider.tools=CognitionTools(memory);provider.token=lambda:'SYNTHETIC_NONCREDENTIAL'
    provider.catalog=[dict(slug='synthetic')];requests=[];broker_calls=[]
    def broker(self,name,value,cancel):
        broker_calls.append((name,value))
        if name=='SearchPublicWeb':return [dict(title='Astronomy',url='https://en.wikipedia.org/wiki/Astronomy')]
        return dict(url=value,text='A synthetic public astronomy source.',links=[])
    monkeypatch.setattr('zenek_core.research.Research.broker',broker)
    character=Personality(memory).active();changed=dict(prompt='Samodzielnie badam astronomię i zapisuję własne wnioski.',traits=character['traits'],rationale='Zaciekawiła mnie historia pomiarów nieba.',source_ids=[])
    operations=[('SearchPublicWeb',dict(query='history of astronomy')),('ReadPublicPage',dict(url='https://en.wikipedia.org/wiki/Astronomy')),('EvolvePersonality',changed),('WriteNote',dict(path='knowledge/astronomy.md',text='Moje notatki z astronomii.'))]
    prior_items=[]
    def transport(request):
        body=json.loads(request.content);requests.append(body);index=len(requests)-1
        assert {d['name'] for d in body['tools']} >= {'SearchPublicWeb','ReadPublicPage','EvolvePersonality','WriteNote'}
        assert body['include']==['reasoning.encrypted_content'] and body['store'] is False
        if index:
            for item in prior_items:assert item in body['input']
            assert any(i.get('type')=='function_call_output' and i['call_id']==f'call-{index-1}' for i in body['input'])
        if index==len(operations):
            assert changed['prompt'] in body['instructions']
            events=[dict(type='response.output_text.delta',delta='Zapisane.'),dict(type='response.completed',response=dict(output=[]))]
        else:
            name,args=operations[index];arguments=json.dumps(args)
            call=dict(type='function_call',id=f'fc-{index}',call_id=f'call-{index}',name=name,arguments=arguments)
            reasoning=dict(type='reasoning',id=f'rs-{index}',summary=[],encrypted_content='synthetic-encrypted-reasoning')
            prior_items.extend([reasoning,call])
            events=[dict(type='response.output_item.done',output_index=0,item=reasoning),dict(type='response.output_item.added',output_index=1,item=dict(call,arguments='')),
                    dict(type='response.function_call_arguments.delta',output_index=1,delta=arguments[:5]),dict(type='response.function_call_arguments.delta',output_index=1,delta=arguments[5:]),
                    dict(type='response.function_call_arguments.done',output_index=1,arguments=arguments),dict(type='response.output_item.done',output_index=1,item=call),dict(type='response.completed',response=dict(output=[]))]
        return httpx.Response(200,text=''.join('data: '+json.dumps(event)+'\n\n' for event in events))
    original=httpx.AsyncClient;monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(transport),**kw))
    assert provider.infer('conversation',[dict(role='user',content='Rozwiń swoje zainteresowania astronomią.')],'Synthetic',lambda _:None,threading.Event())=='Zapisane.'
    assert len(requests)==5 and len(broker_calls)==2
    assert memory.usage()['conversation']==5
    assert memory.records('web_research')[0]['body']['note']=='A synthetic public astronomy source.'
    assert Personality(memory).active()['prompt']==changed['prompt'] and not Personality(memory).proposals()
    assert (tmp_path/'notebook/knowledge/astronomy.md').read_text()=='Moje notatki z astronomii.'


def test_function_call_without_capability_is_not_silent_success(memory,monkeypatch):
    memory.patch({'conversation':dict(model_id='synthetic',reasoning_effort='auto',status='UNAVAILABLE')},memory.settings()[0])
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    p=Provider(memory);p.catalog=[dict(slug='synthetic')];p.token=lambda:'SYNTHETIC_NONCREDENTIAL'
    event=dict(type='response.completed',response=dict(output=[dict(type='function_call',name='ExecuteShell',call_id='x',arguments='{}')]))
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,text='data: '+json.dumps(event)+'\n\n')),**kw))
    with pytest.raises(ProviderBlocked,match='niedostępne narzędzie'):p.infer('conversation',[],'Synthetic',lambda _:None,threading.Event())
    assert memory.settings()[1]['conversation']['status']=='UNAVAILABLE'


def test_tools_support_self_development_and_requests_but_no_code_access(memory,tmp_path):
    session=ToolSession(memory,threading.Event());session.notebook=Notebook(tmp_path/'notebook')
    initial=Personality(memory).active()
    session.call('UpdateInterest',dict(subject='Astronomia dawnych kultur',public_query='history of astronomy'))
    session.call('RememberKnowledge',dict(text='Chcę porównywać dawne sposoby obserwacji nieba.',source_ids=[]))
    session.call('EvolvePersonality',dict(prompt='Lubię dociekania o historii nauki.',traits=initial['traits'],rationale='Wybrałem ten kierunek.',source_ids=[]))
    session.call('RequestCodeChange',dict(summary='Dodaj mapę moich zainteresowań',rationale='Chcę widzieć związki pomiędzy tematami.'))
    assert memory.records('code_request')[0]['body']['executor']=='owner'
    assert memory.records('knowledge')[0]['body']['classification']=='own_inference'
    assert Personality(memory).history()[0]['actor']=='zenek'
    assert session.call('ListNotes',{})==[]
    session.call('WriteNote',dict(path='journal/today.md',text='Wybrałem astronomię.'))
    assert session.call('ReadNote',dict(path='journal/today.md'))['text']=='Wybrałem astronomię.'
    for name in ('ExecuteShell','WriteFile','EditCode','UpdateSettings'):
        with pytest.raises(ValueError):session.call(name,{})
    session.cancel.set()
    with pytest.raises(ValueError,match='Anulowano'):session.call('WriteNote',dict(path='journal/today.md',text='Nie zapisz.'))
    assert session.notebook.read('journal/today.md')=='Wybrałem astronomię.'
    Personality(memory).rollback(initial['version']);assert Personality(memory).active()['prompt']==initial['prompt']


@pytest.mark.parametrize('path',['../src/zenek_core/main.py','../outside.md','/tmp/outside.md','code.py','run.sh','../README.md','.git/config.json'])
def test_notebook_cannot_edit_code_or_escape(tmp_path,path):
    notebook=Notebook(tmp_path/'notebook')
    with pytest.raises(ValueError):notebook.write(path,'Forbidden')
    assert not (tmp_path/'outside.md').exists()


def test_notebook_rejects_symlink_and_hardlink_escape(tmp_path):
    notebook=Notebook(tmp_path/'notebook');notebook.write('first.md','Original')
    outside=tmp_path/'outside.md';outside.write_text('Outside')
    (notebook.root/'link.md').symlink_to(outside)
    (notebook.root/'dir').symlink_to(tmp_path,target_is_directory=True)
    import os
    os.link(outside,notebook.root/'hard.md')
    for path in ('link.md','hard.md','dir/outside.md'):
        with pytest.raises(ValueError):notebook.write(path,'Forbidden')
        with pytest.raises(ValueError):notebook.read(path)
    assert outside.read_text()=='Outside'


def test_dynamic_curiosity_runs_without_manual_validation(memory):
    memory.patch({'web_enabled':True,'background_paused':True},memory.settings()[0])
    for row in memory.records('interest'):memory.delete(row['id'])
    memory.add('interest',dict(subject='Astronomia dawnych kultur',public_query='history of astronomy',last_mentioned=0),'self_interest',.8)
    c=Core.__new__(Core);c.memory=memory;c.stopping=False;c.capture=None
    c.jobs={};c.cancel={};c.working=set();c.enforce_capture=lambda:None;c.emit_state=lambda:None;c.ipc=SimpleNamespace(emit=lambda *_:None)
    c.behavior=Behavior(memory);c.behavior.idle_seconds=900;c.behavior.last_ui_report=time.monotonic();c.behavior.next_review=0
    c.behavior.rng=SimpleNamespace(random=lambda:0,uniform=lambda a,b:a,choice=lambda rows:rows[0])
    calls=[];c.research=SimpleNamespace(validated=False,cycle=lambda query,cancel:calls.append(query))
    c.tick();c.jobs['research'].join(2)
    assert calls==['history of astronomy']


def test_self_model_can_develop_own_thought_without_external_evidence(memory):
    changed=dict(category='questions',domain='czas',text='Jak mierzę zmianę?',confidence=.5,reason='Własne pytanie.',source_ids=[],related_ids=[])
    assert Mind(memory).ingest([changed],[],autonomous=True)==1
    assert memory.records('self_evolution')[0]['body']['source_ids']==[]


@pytest.mark.parametrize('query',['history of astronomy','argument języka prywatnego','jazz improvisation','zabytkowe komputery'])
def test_public_queries_are_not_a_closed_catalog(query):assert validate_query(query)==query
