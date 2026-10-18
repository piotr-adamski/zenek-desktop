import json
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import httpx
import pytest
from zenek_core.memory import Memory
from zenek_core.provider import Provider,ProviderBlocked
from zenek_core.privacy import safe_text

def test_requests_use_selected_profiles_and_only_completed_counts_ready(tmp_path,monkeypatch):
    m=Memory(tmp_path/'db','ab'*32)
    v,s=m.settings()
    for p,model,effort in [('conversation','synthetic-dialog','medium'),('background_cognition','synthetic-background','high')]:
        m.patch({p:dict(model_id=model,reasoning_effort=effort,status='UNAVAILABLE')},m.settings()[0])
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    p=Provider(m);monkeypatch.setattr(p,'token',lambda:'SYNTHETIC_NOT_A_REAL_TOKEN')
    p.catalog=[dict(slug='synthetic-dialog',supported_reasoning_efforts=['medium']),dict(slug='synthetic-background',supported_reasoning_efforts=['high'])]
    captured=[];success=True
    def handler(request):
        assert str(request.url)=='https://api.openai.com/v1/responses'
        captured.append(json.loads(request.content))
        data='data: '+json.dumps(dict(type='response.output_text.delta',delta='Test'))+'\n\n'
        if success:data+='data: {"type":"response.completed"}\n\n'
        return httpx.Response(200,text=data)
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    for profile in ['conversation','background_cognition']:
        assert p.infer(profile,[dict(role='user',content='Synthetic')],'Synthetic',lambda _:None,threading.Event())=='Test'
        assert m.settings()[1][profile]['status']=='READY'
    assert [(x['model'],x['reasoning']['effort']) for x in captured]==[('synthetic-dialog','medium'),('synthetic-background','high')]
    assert all(x['store'] is False and x['stream'] is True and set(x)=={'model','input','instructions','store','stream','reasoning'} for x in captured)
    success=False
    with pytest.raises(ProviderBlocked,match='response.completed'):p.infer('conversation',[],'Synthetic',lambda _:None,threading.Event())
    assert m.settings()[1]['conversation']['status']=='UNAVAILABLE'
    monkeypatch.setattr(p,'_infer',lambda *args:(_ for _ in ()).throw(httpx.ConnectError('Synthetic network outage')))
    with pytest.raises(ProviderBlocked,match='Sieć'):p.infer('background_cognition',[],'Synthetic',lambda _:None,threading.Event())
    assert m.settings()[1]['background_cognition']['status']=='UNAVAILABLE'
    assert m.settings()[1]['provider']=='siwc' and m.settings()[1]['paid_api_approved'] is False
    m.close()

def test_secret_text_is_rejected_before_memory_or_inference():
    for value in ['hasło: SYNTHETIC123','Bearer SYNTHETIC_LONG_TOKEN','sk-SYNTHETIC0123456789ABCDEF']:
        with pytest.raises(ValueError):safe_text(value)

@pytest.mark.parametrize('before_headers',[True,False])
def test_cancel_closes_real_stalled_connection_without_read_timeout(tmp_path,monkeypatch,before_headers):
    m=Memory(tmp_path/'db','ab'*32)
    m.patch({'conversation':dict(model_id='synthetic',reasoning_effort='medium',status='READY')},m.settings()[0]);m.profile_status('conversation','READY')
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    p=Provider(m);p.catalog=[dict(slug='synthetic',supported_reasoning_efforts=['medium'])];p.token=lambda:'SYNTHETIC_NOT_A_REAL_TOKEN'
    started=threading.Event();closed=threading.Event();deltas=[];errors=[]
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            if not before_headers:
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                self.wfile.write(b'data: {"type":"response.output_text.delta","delta":"partial"}\n\n');self.wfile.flush()
            started.set();self.connection.settimeout(2)
            try:
                if self.connection.recv(1)==b'':closed.set()
            except TimeoutError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    serving=threading.Thread(target=server.serve_forever,daemon=True);serving.start()
    monkeypatch.setattr('zenek_core.provider.API',f'http://127.0.0.1:{server.server_port}')
    cancel=threading.Event()
    def request():
        try:p.infer('conversation',[],'Synthetic',deltas.append,cancel)
        except Exception as error:errors.append(error)
    worker=threading.Thread(target=request,daemon=True);worker.start()
    try:
        assert started.wait(2)
        if not before_headers:
            deadline=time.monotonic()+2
            while not deltas and time.monotonic()<deadline:time.sleep(.01)
            assert deltas==['partial']
        then=time.monotonic();cancel.set();worker.join(1)
        assert not worker.is_alive() and time.monotonic()-then<1
        assert closed.wait(1),'Cancellation did not close the actual TCP socket'
        assert len(errors)==1 and isinstance(errors[0],ProviderBlocked) and str(errors[0])=='Anulowano'
        assert m.settings()[1]['conversation']['status']=='READY'
        assert m.db.execute('SELECT status FROM usage').fetchall()==[('cancelled',)]
    finally:
        cancel.set();worker.join(3);server.shutdown();server.server_close();serving.join(1);m.close()

@pytest.mark.parametrize('success',[True,False])
def test_old_model_request_does_not_change_new_profile_status(tmp_path,monkeypatch,success):
    m=Memory(tmp_path/'db','ab'*32)
    m.patch({'conversation':dict(model_id='old-model',reasoning_effort='medium',status='UNAVAILABLE')},m.settings()[0])
    monkeypatch.setattr(Provider,'credentials',lambda self:None)
    p=Provider(m);p.catalog=[dict(slug='old-model',supported_reasoning_efforts=['medium'])];p.token=lambda:'SYNTHETIC_NOT_A_REAL_TOKEN'
    def handler(request):
        m.patch({'conversation':dict(model_id='new-model',reasoning_effort='high',status='UNAVAILABLE')},m.settings()[0])
        if not success:m.profile_status('conversation','READY')
        return httpx.Response(200 if success else 503,text='data: {"type":"response.output_text.delta","delta":"Synthetic"}\n\ndata: {"type":"response.completed"}\n\n')
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    if success:assert p.infer('conversation',[],'Synthetic',lambda _:None,threading.Event())=='Synthetic'
    else:
        with pytest.raises(ProviderBlocked,match='HTTP'):p.infer('conversation',[],'Synthetic',lambda _:None,threading.Event())
    profile=m.settings()[1]['conversation']
    assert profile['model_id']=='new-model' and profile['reasoning_effort']=='high'
    assert profile['status']==('UNAVAILABLE' if success else 'READY')
    m.close()
