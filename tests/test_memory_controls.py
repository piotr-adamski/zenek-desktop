import json
import pytest
from zenek_core.memory import Memory
from zenek_core.config import INTERNAL_RECORD_KINDS

def test_correction_preserves_source_and_filters_original_from_context(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);identifier=m.add('import_original',dict(text='SYNTHETIC WRONG ORIGINAL',role='user'),'owner_selected_import',1)
    m.correct(identifier,'text','SYNTHETIC OWNER CORRECTION')
    row=m.record(identifier);assert row['body']['original_text']=='SYNTHETIC WRONG ORIGINAL' and row['source']=='owner_selected_import'
    context=next(r for r in m.context('OWNER CORRECTION') if r['id']==identifier)
    assert context['body']['text']=='SYNTHETIC OWNER CORRECTION' and 'original_text' not in context['body']
    with pytest.raises(ValueError):m.correct(identifier,'role','developer')
    m.close()

def test_suppression_clear_and_export_keep_limits_and_internal_keys(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);identifier=m.records('interest')[0]['id'];subject=m.record(identifier)['body']['subject']
    m.suppress(identifier);assert not m.topic_allowed(dict(subject=subject,status='new'))
    ticket=m.reserve('background',86400,20);assert ticket
    m.add('host',dict(host_id='SYNTHETIC INTERNAL CLIENT'),'installation',1)
    export=tmp_path/'export.json';m.export(export);payload=json.loads(export.read_text())
    assert not any(r['kind']=='host' for r in payload['records']) and export.stat().st_mode&0o777==0o600
    with pytest.raises(FileExistsError):m.export(export)
    m.clear();assert not m.records('interest') and m.usage()['background']==1 and m.records('host')
    m.close();m=Memory(tmp_path/'db','ab'*32);assert not m.records('interest') and m.usage()['background']==1
    m.close()

@pytest.mark.parametrize('kind',INTERNAL_RECORD_KINDS)
def test_single_record_operations_and_public_list_preserve_internal_configuration(tmp_path,kind):
    m=Memory(tmp_path/'db','ab'*32);identifier=m.add(kind,dict(text='SYNTHETIC INTERNAL CONFIGURATION'),'internal',1);before=m.record(identifier)
    for action in (lambda:m.delete(identifier),lambda:m.correct(identifier,'text','replacement'),lambda:m.suppress(identifier),lambda:m.clear(kind)):
        with pytest.raises(ValueError,match='Konfiguracja wewnętrzna'):action()
        assert m.record(identifier)==before
    assert not m.visible_records(kind) and not any(row['id']==identifier for row in m.visible_records())
    m.clear();assert m.record(identifier)==before
    m.close();m=Memory(tmp_path/'db','ab'*32);assert m.record(identifier)==before;m.close()

def test_visible_records_limit_applies_after_internal_filter_and_regular_delete_works(tmp_path):
    m=Memory(tmp_path/'db','ab'*32)
    visible=m.add('observation_memory',dict(text='SYNTHETIC VISIBLE OBSERVATION'),'test',1)
    for kind in INTERNAL_RECORD_KINDS:m.add(kind,dict(text='SYNTHETIC INTERNAL'),'internal',1)
    assert m.visible_records(limit=1)[0]['id']==visible
    m.delete(visible)
    with pytest.raises(ValueError,match='nie istnieje'):m.record(visible)
    assert all(m.records(kind) for kind in INTERNAL_RECORD_KINDS);m.close()
