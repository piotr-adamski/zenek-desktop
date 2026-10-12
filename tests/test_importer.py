import json
import threading
import zipfile
import pytest
from zenek_core.importer import Importer
from zenek_core.memory import Memory

def export(path,extra=False,changed=False):
    messages=[dict(id='a',text='Corrected source' if changed else 'SYNTHETIC PROJECT ORIGINAL')]
    if extra:messages.append(dict(id='b',text='SYNTHETIC DELTA ORIGINAL'))
    def conversation(identifier,items):return dict(id=identifier,title=identifier,mapping={i['id']:dict(message=dict(id=i['id'],author={'role':'user'},content={'parts':[i['text']]},create_time=123)) for i in items})
    path.write_text(json.dumps([conversation('zenek-project',messages),conversation('foreign-project',[dict(id='other',text='FOREIGN MUST STAY OUT')])]))

def test_selected_delta_preserves_corrections_and_all_references(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);i=Importer(m);p=tmp_path/'export.json';export(p)
    preview=i.preview([str(p)]);choice=next(c['key'] for c in preview['choices'] if c['unit_id']=='zenek-project')
    assert not m.records('import_original')
    result=i.apply(preview['id'],[choice],threading.Event(),True);assert len(result['body']['added'])==1
    original=m.records('import_original')[0];m.update(original['id'],dict(original['body'],text='LOCAL OWNER CORRECTION'))
    export(p,extra=True);preview=i.preview([str(p)]);result=i.apply(preview['id'],[choice],threading.Event(),True)
    assert len(result['body']['added'])==1 and result['body']['duplicates']==1
    assert any(r['body']['text']=='LOCAL OWNER CORRECTION' for r in m.records('import_original'))
    assert not any('FOREIGN' in r['body']['text'] for r in m.records('import_original'))
    second=tmp_path/'extra-export.json';export(second,extra=True);preview=i.preview([str(second)]);key=next(c['key'] for c in preview['choices'] if c['unit_id']=='zenek-project')
    result=i.apply(preview['id'],[key],threading.Event(),True);assert not result['body']['added']
    assert len(i.references(original['id']))==2
    export(p,extra=True,changed=True);preview=i.preview([str(p)]);result=i.apply(preview['id'],[choice],threading.Event(),True)
    assert len(result['body']['conflicts'])==1 and not result['body']['added']
    m.close()

def test_explicit_resume_and_changed_preview_guard(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);i=Importer(m);p=tmp_path/'export.json';export(p,extra=True)
    preview=i.preview([str(p)]);choice=next(c['key'] for c in preview['choices'] if c['unit_id']=='zenek-project')
    cancel=threading.Event();cancel.set();assert i.apply(preview['id'],[choice],cancel,True)['status']=='PAUSED'
    m.close();m=Memory(tmp_path/'db','ab'*32);i=Importer(m)
    assert not m.records('import_original') and i.latest()['status']=='PAUSED'
    cancel.clear();assert i.apply(preview['id'],[choice],cancel,True)['status']=='COMPLETE'
    preview=i.preview([str(p)]);export(p,changed=True)
    with pytest.raises(ValueError,match='zmieniło'):i.apply(preview['id'],[choice],cancel,True)
    m.close()

def test_zip_never_extracts_unselected_files_or_secrets(tmp_path):
    p=tmp_path/'export.json';export(p);z=tmp_path/'export.zip'
    with zipfile.ZipFile(z,'w') as archive:
        archive.writestr('../../escape.txt','DO NOT EXTRACT');archive.writestr('conversations.json',p.read_bytes())
    m=Memory(tmp_path/'db','ab'*32);i=Importer(m);preview=i.preview([str(z)])
    assert len(preview['choices'])==2 and not (tmp_path.parent/'escape.txt').exists()
    with pytest.raises(ValueError):i.apply(preview['id'],[preview['choices'][0]['key']],threading.Event(),False)
    assert not m.records('import_original');m.close()
