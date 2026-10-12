import threading
import pytest
from zenek_core.memory import Memory
from zenek_core.research import Research

def test_private_values_are_rejected_before_child_or_budget(tmp_path,monkeypatch):
    m=Memory(tmp_path/'db','ab'*32);r=Research(m)
    def forbidden(*args):raise AssertionError('Private value reached worker')
    monkeypatch.setattr(r,'exchange',forbidden)
    for method,value in [('POST','synthetic'),('SearchPublicWeb','private message'),('ReadPublicPage','https://example.org/PRIVATE')]:
        with pytest.raises(ValueError):r.broker(method,value,threading.Event())
    assert not m.usage();m.close()

@pytest.mark.parametrize('kind,limit',[('web_search',15),('web_read',30)])
def test_web_budget_does_not_reset_at_midnight_or_restart(tmp_path,kind,limit):
    m=Memory(tmp_path/'db','ab'*32);now=1791759590 # Near midnight; rolling time is authoritative.
    for i in range(limit):assert m.reserve(kind,86400,limit,now=now+i)
    m.close();m=Memory(tmp_path/'db','ab'*32)
    assert m.reserve(kind,86400,limit,now=now+100) is None
    assert m.budget(kind,86400,limit,now=now+100)['remaining']==0
    assert m.budget(kind,86400,limit+1,now=now+100)['remaining']==1
    assert m.reserve(kind,86400,limit,now=now+86401)
    m.close()
