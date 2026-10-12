"""Instrument actual production broker within its unchanged bwrap mounts/env.

strace records connect/openat; Python audit observes HTTP bytes before TLS.
Only synthetic parent secrets and disposable encrypted memory are used.
"""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from zenek_core.memory import Memory
from zenek_core.research import Research

root=Path(__file__).resolve().parents[1]
canary='SYNTHETIC_PRIVATE_EGRESS_CANARY_20261011'
os.environ['OPENAI_API_KEY']=canary;os.environ['ZENEK_PARENT_PRIVATE_VALUE']=canary
# Observes HTTPConnection.send; request policy and networking code stay intact.
bootstrap="""import sys,json,runpy
def audit(event,args):
    if event=='http.client.send':
        data=args[1]
        if not isinstance(data,bytes):raise RuntimeError('Unexpected HTTP data type')
        print('ZENEK_HTTP_AUDIT '+json.dumps({'request':data.decode('ascii')}),file=sys.stderr,flush=True)
sys.addaudithook(audit)
runpy.run_path('/zenek-web-worker.py',run_name='__main__')
"""
original=subprocess.Popen
with tempfile.TemporaryDirectory(prefix='zenek-egress-') as runtime:
    directory=Path(runtime);trace=directory/'trace.log'
    memory=Memory(directory/'synthetic.db','ab'*32);research=Research(memory);launches=[]
    def traced(args,**kwargs):
        if args[0]!='bwrap':return original(args,**kwargs)
        assert kwargs['env']=={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
        index=args.index('/usr/bin/python3')
        assert args[index:]==['/usr/bin/python3','-I','/zenek-web-worker.py']
        launches.append(dict(mount_args=list(args[:index]),environment_names=sorted(kwargs['env'])))
        command=args[:index]+['/usr/bin/strace','-qq','-f','-A','-e','trace=connect,openat','-s','128','-o','/dev/stderr','/usr/bin/python3','-I','-c',bootstrap]
        with trace.open('ab') as output:
            kwargs['stderr']=output
            return original(command,**kwargs)
    subprocess.Popen=traced
    try:
        # Sensitive values must fail in parent before a child or budget ticket.
        for method,value in [('SearchPublicWeb',canary),('ReadPublicPage','https://example.org/'+canary),('POST',canary)]:
            try:research.broker(method,value,threading.Event())
            except ValueError:pass
            else:raise AssertionError('Private parent value was accepted')
        assert not launches and not memory.usage()
        validation=research.validate(threading.Event())
        assert validation['status']=='READY' and all(validation['isolation'].values()) and research.process is None
        notes=memory.records('web_research');assert len(notes)==2 and len({note['body']['url'] for note in notes})==2
    finally:
        subprocess.Popen=original;research.close_process();memory.close()
    content=trace.read_text()
    requests=[json.loads(line.split('ZENEK_HTTP_AUDIT ',1)[1])['request'] for line in content.splitlines() if 'ZENEK_HTTP_AUDIT ' in line]
    assert len(requests)>=3,f'Expected search GET plus two public page GETs; observed {len(requests)} audited requests'
    for request in requests:
        first,*headers=request.split('\r\n')
        assert first.startswith('GET ') and first.endswith(' HTTP/1.1')
        assert canary not in request and 'authorization:' not in request.lower() and 'cookie:' not in request.lower()
        assert 'Content-Length:' not in request and request.endswith('\r\n\r\n')
        assert any(header.lower()=='host: en.wikipedia.org' for header in headers)
    https=[];dns=0;unknown=[]
    for line in content.splitlines():
        if 'connect(' not in line or 'AF_INET' not in line:continue
        port=re.search(r'sin6?_port=htons\((\d+)\)',line)
        address=re.search(r'(?:inet_addr\(|inet_pton\(AF_INET6, )"([0-9a-fA-F:.]+)"',line)
        if not port or not address:unknown.append(line);continue
        number=int(port[1]);ip=ipaddress.ip_address(address[1])
        if number==53:dns+=1
        else:
            assert number==443 and ip.is_global,'Unexpected non-public/non-HTTPS TCP destination'
            https.append(str(ip))
    assert https and not unknown,'Missing or unparsed connection evidence'
    assert not re.search(r'openat\([^\n]*"/(?:home/|run/user/)',content),'Broker attempted a private file open'
    summary=dict(status='PASS',scope='actual instrumented production broker, same bwrap mounts/environment',code_hash=validation['code_hash'],worker_sha256=hashlib.sha256((root/'src/zenek_core/web_worker.py').read_bytes()).hexdigest(),isolation=validation['isolation'],parent_private_values_rejected_before_spawn=True,denied_operations=validation['denied_cases'],http_get_requests=len(requests),encrypted_public_notes=len(notes),request_targets=[request.split('\r\n')[0].split()[1] for request in requests],no_auth_cookie_body_or_private_canary=True,https_public_addresses=sorted(set(https)),dns_connections=dns,no_private_file_open=True,worker_closed=True,trace_sha256=hashlib.sha256(content.encode()).hexdigest())
    (root/'evidence/www-egress-runtime.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
