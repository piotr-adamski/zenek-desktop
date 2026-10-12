"""Configured unavailable models must leave a working local agenda."""
import random
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from zenek_core.behavior import Behavior
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.provider import Provider, ProviderBlocked


class Opportunity(random.Random):
    def random(self):return 0
    def uniform(self, a, b):return a
    def choice(self, values):return values[0]


def test_failed_network_uses_local_agenda_without_automatic_model_retry(tmp_path, monkeypatch):
    memory=Memory(tmp_path/'memory.db', 'ab'*32)
    try:
        memory.patch({'conversation':dict(model_id='gpt-6.1-sol',reasoning_effort='medium',status='READY')},memory.settings()[0])
        memory.profile_status('conversation','READY')
        memory.add('interest',dict(subject='SYNTHETIC ROBOT ROCKS',strength=.8,last_mentioned=0),'synthetic_test',1)
        provider=Provider.__new__(Provider)
        provider.memory=memory;provider.catalog=[]
        provider.token=lambda:'SYNTHETIC_NONCREDENTIAL'
        # Reserve a real unused TCP port without accepting connections. No
        # external request, owner token, HTTP mock or global network change.
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1',0))
            monkeypatch.setattr('zenek_core.provider.API','http://127.0.0.1:'+str(unavailable.getsockname()[1])+'/v1')
            with pytest.raises(ProviderBlocked,match='Sieć niedostępna'):
                provider.infer('conversation',[dict(role='user',content='synthetic')],'synthetic',lambda _:None,threading.Event())
        assert memory.settings()[1]['conversation']['status']=='UNAVAILABLE'
        events=[]
        core=Core.__new__(Core)
        core.memory=memory;core.provider=provider;core.stopping=False;core.capture=None
        core.behavior=Behavior(memory,Opportunity());core.behavior.idle_seconds=0
        core.behavior.last_ui_report=time.monotonic();core.behavior.next_review=0
        core.research=SimpleNamespace(validated=False)
        core.enforce_capture=lambda:None;core.emit_state=lambda:None
        core.ipc=SimpleNamespace(emit=lambda kind,payload:events.append((kind,payload)))
        def unexpected_worker(*args,**kwargs):
            raise AssertionError('An unavailable model was retried autonomously')
        core.worker=unexpected_worker
        core.tick()
        assert len(events)==1 and events[0][0]=='BubbleRequested'
        message=memory.records('message',1)[0]
        assert message['source']=='local_agenda' and 'SYNTHETIC ROBOT ROCKS' in message['body']['text']
        assert memory.usage().get('spontaneous')==1 and not memory.usage().get('conversation')
        assert memory.settings()[1]['provider']=='siwc' and not memory.settings()[1]['paid_api_approved']
        core.behavior.next_review=0;core.tick()
        assert len(events)==1,'Local fallback ignored the normal topic/cooldown rules'
    finally:memory.close()
