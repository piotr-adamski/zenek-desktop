import time
from zenek_core.memory import Memory
from zenek_core.mind import Mind
from zenek_core.narrative import Variety

def update(ref,**extra):
    return dict(category='beliefs',domain='niepewność',text='Wolę pytania, które ujawniają ukryte założenia, od szybkich odpowiedzi.',confidence=.6,reason='Nowy argument rozmówcy zmienił moją ocenę pewności.',source_ids=[ref],related_ids=[],**extra)

def test_self_model_evolves_with_sources_and_preserves_prompt_and_restart(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);original=m.settings()[1]
    ref=m.add('message',dict(role='user',text='Warto kwestionować pewność własnych odpowiedzi.'),'conversation',1)
    mind=Mind(m);assert mind.ingest([update(ref)],[m.record(ref)])==1
    first=mind.facets()[0];assert mind.snapshot()['revision_count']==1
    assert mind.ingest([update(ref)],[m.record(ref)])==0
    ref2=m.add('message',dict(role='user',text='Sceptycyzm bez działania również jest decyzją.'),'conversation',1)
    newer=update(ref2);newer['text']='Cenię sceptycyzm, ale dostrzegam konflikt między ostrożnością a odwagą działania.'
    assert mind.ingest([newer],[m.record(ref2)])==1
    assert mind.facets()[0]['id']==first['id'] and mind.facets()[0]['body']['revision']==2
    assert len(m.records('self_evolution'))==2 and m.settings()[1]==original
    reopened=Memory(m.path,'ab'*32);assert Mind(reopened).snapshot()['revision_count']==2;reopened.close()
    bad=update(ref2);bad['category']='permissions';assert mind.ingest([bad],[m.record(ref2)])==0
    bad=update('missing');assert mind.ingest([bad],[m.record(ref2)])==0
    own=m.add('reflection',dict(text='Sceptycyzm i działanie mogą współistnieć jako próba, a nie ostateczny werdykt.',source_ids=[ref2],classification='inference'),'background_model',.5)
    internal=update(own);internal['category']='tensions';internal['domain']='ostrożność i działanie'
    assert mind.ingest([internal],[m.record(own)])==1
    m.correct(first['id'],'text','Własna korekta właściciela, zachowaj ją.')
    assert mind.ingest([newer],[m.record(ref2)])==0
    m.close()

def test_screen_hash_changes_do_not_repeat_topic_and_context_deduplicates(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);variety=Variety(m)
    scene='Terminal pokazuje wdrożenie kontenerów docker oraz logi kompilacji aplikacji.'
    first=dict(id='hash1',source='screen_current',body=dict(detailed_text=scene))
    m.add('message',dict(role='assistant',text='Granice kontenera przypominają granice odpowiedzialności.',**variety.metadata(first)),'initiative',.8)
    repeated=dict(first,id='hash2',body=dict(detailed_text=scene+' Zmieniła się godzina i numer kompilacji.'))
    assert not variety.allows(repeated)
    m.add('message',dict(role='assistant',text='Improwizacja jazzowa przypomina rozmowę bez gotowej mapy.',topic_source='memory',topic_terms=['jazz','muzyka','improwiz']),'initiative',.8)
    assert not variety.allows(repeated),'Alternating once must not reset thematic memory'
    assert not variety.accepts_text('Granice kontenera przypominają granice odpowiedzialności.')
    different=dict(id='other',source='screen_current',body=dict(detailed_text='Obraz przedstawia ocean, koralowce, podwodne zwierzęta oraz barwne ryby.'))
    assert variety.allows(different)
    for i in range(20):m.add('observation_memory',dict(detailed_text=scene+f' build {i}'),'desktop_observation',.6)
    selected=m.context(scene,diverse=True)
    assert len([r for r in selected if r['kind']=='observation_memory'])==1
    m.close()

def test_actual_background_worker_updates_self_model_from_new_user_evidence(tmp_path):
    import json
    from types import SimpleNamespace
    from zenek_core.main import Core
    from zenek_core.behavior import Behavior
    from zenek_core.personality import Personality
    m=Memory(tmp_path/'db','ab'*32);Mind(m).bootstrap();Mind(m).bootstrap()
    assert Mind(m).snapshot()['facet_count']==4
    original=m.settings()[1]['prompt']
    ref=m.add('message',dict(role='user',text='Niepewność pozwala rozwijać pytania, ale sceptycyzm nie może paraliżować działania.'),'conversation',1)
    m.patch({'background_cognition':dict(model_id='gpt-6-luna',reasoning_effort='high',status='READY')},m.settings()[0]);m.profile_status('background_cognition','READY')
    c=Core.__new__(Core);c.memory=m;c.stopping=False;c.capture=None;c.personality=Personality(m)
    c.behavior=Behavior(m);c.behavior.idle_seconds=900;c.behavior.last_ui_report=time.monotonic();c.behavior.next_review=0
    c.jobs={};c.cancel={};c.working=set();c.research=SimpleNamespace(validated=False);c.emit_state=lambda:None;c.enforce_capture=lambda:None
    c.ipc=SimpleNamespace(emit=lambda *_:None)
    requests=[]
    def model(profile,inputs,*args):
        assert profile=='background_cognition' and 'self_updates' in inputs[-1]['content']
        assert '<model-siebie>' in inputs[0]['content'] and ref in inputs[-1]['content']
        requests.append(profile)
        return '```json\n'+json.dumps(dict(reflection='SILENCE',self_updates=[update(ref)]))+'\n```'
    c.provider=SimpleNamespace(infer=model)
    c.tick();c.jobs['background'].join(2)
    assert not c.jobs['background'].is_alive() and Mind(m).snapshot()['facet_count']==5
    assert Mind(m).snapshot()['revision_count']==1 and m.settings()[1]['prompt']==original
    c.behavior.next_review=0;c.tick()
    assert len(requests)==1,'Existing reflection cooldown must apply to self development'
    m.close()
