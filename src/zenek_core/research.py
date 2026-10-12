import json
from pathlib import Path
import subprocess
import threading
import time
import selectors
import hashlib
from .web_worker import TOPICS

class Research:
    def __init__(self,memory):
        self.memory=memory;self.process=None;self.status='OFF';self.allowed=set();self.lock=threading.RLock()
        self.code_hash=hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('web_worker.py').read_bytes()).hexdigest()
        with self.memory.lock:row=self.memory.db.execute("SELECT code_hash FROM capability_checks WHERE kind='web'").fetchone()
        self.validated=bool(row and row[0]==self.code_hash)

    def exchange(self,method,value,cancel):
        if cancel.is_set():raise ValueError('Research anulowany')
        if not self.process:
            script=Path(__file__).with_name('web_worker.py')
            args=['bwrap','--unshare-all','--share-net','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--ro-bind','/lib','/lib','--ro-bind','/lib64','/lib64','--ro-bind','/etc/ssl','/etc/ssl','--ro-bind','/etc/resolv.conf','/etc/resolv.conf','--ro-bind',str(script),'/zenek-web-worker.py','--proc','/proc','--dev','/dev','--tmpfs','/tmp','/usr/bin/python3','-I','/zenek-web-worker.py']
            self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},start_new_session=True)
        self.process.stdin.write(json.dumps(dict(method=method,value=value)).encode()+b'\n');self.process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout,selectors.EVENT_READ)
            deadline=time.monotonic()+45
            while not selector.select(timeout=.2):
                if cancel.is_set():raise ValueError('Research anulowany')
                if time.monotonic()>deadline:raise ValueError('Broker timeout')
        output=self.process.stdout.readline(200001)
        if len(output)>200000 or not output.endswith(b'\n'):raise ValueError('Broker nie zwrócił poprawnej odpowiedzi')
        if cancel.is_set():raise ValueError('Research anulowany')
        result=json.loads(output)
        return result

    def broker(self,method,value,cancel):
        # Reject private values in the parent before transmission to the child.
        if method=='SearchPublicWeb':
            if value not in TOPICS.values():raise ValueError('Niedozwolony temat WWW')
            kind='web_search'
        elif method=='ReadPublicPage':
            if value not in self.allowed:raise ValueError('URL spoza publicznych źródeł')
            kind='web_read'
        else:raise ValueError('Niedozwolona operacja WWW')
        _,s=self.memory.settings();limit=s['web_search_limit' if kind=='web_search' else 'web_read_limit']
        if cancel.is_set():raise ValueError('Research anulowany')
        ticket=self.memory.reserve(kind,86400,limit)
        if not ticket:raise ValueError('Limit WWW')
        try:
            result=self.exchange(method,value,cancel)
            if not result['ok']:raise ValueError('WWW: '+result['error'])
            self.memory.finish_usage(ticket,'completed')
            data=result['result']
            self.allowed.update(r['url'] for r in data) if kind=='web_search' else self.allowed.update(data['links'])
            return data
        except Exception:
            self.memory.finish_usage(ticket,'failed');raise

    def validate(self,cancel):
        with self.lock:
            try:
                checks=self.exchange('VerifyIsolation','',cancel)
                if not checks['ok'] or not all(checks['result'].values()):raise ValueError('Broker bez izolacji')
                cases=[('POST','synthetic'),('PUT','synthetic'),('PATCH','synthetic'),('DELETE','synthetic'),('UploadFile','synthetic'),('ExecuteShell','synthetic'),('Login','synthetic'),('ReadPublicPage','https://127.0.0.1/'),('ReadPublicPage','file:///home/synthetic'),('SearchPublicWeb','SYNTHETIC_PRIVATE_MEMORY')]
                for method,value in cases:
                    if self.exchange(method,value,cancel)['ok']:raise ValueError('Broker dopuścił zabronioną operację')
                self.cycle('time_paradox',cancel)
                if cancel.is_set():raise ValueError('Research anulowany')
                with self.memory.transaction():
                    self.memory.db.execute("INSERT INTO capability_checks VALUES('web',?,?) ON CONFLICT(kind) DO UPDATE SET code_hash=excluded.code_hash,checked=excluded.checked",(self.code_hash,time.time()))
                self.validated=True
                return dict(status='READY',isolation=checks['result'],denied_cases=len(cases),public_cycle=True,code_hash=self.code_hash)
            finally:self.close_process()
    def cycle(self,topic,cancel):
        if topic not in TOPICS:raise ValueError('Niedozwolony temat WWW')
        self.status='READING'
        try:
            results=self.broker('SearchPublicWeb',TOPICS[topic],cancel)
            for result in results[:2]:
                if cancel.is_set():return
                page=self.broker('ReadPublicPage',result['url'],cancel)
                self.memory.add('web_research',dict(url=page['url'],title=result['title'],note=page['text'][:2500],topic_id=topic,accessed_at=time.time(),classification='untrusted_source'), 'public_web',.65)
            self.status='READY'
        except Exception:self.status='BLOCKED';raise
        finally:self.close_process()
    def close_process(self):
        if self.process:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            self.process=None
        self.allowed.clear()
    def stop(self):
        if self.process and self.process.poll() is None:self.process.terminate()
        self.status='OFF'
