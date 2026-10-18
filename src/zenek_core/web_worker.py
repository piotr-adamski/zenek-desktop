"""Credential-free public web broker; runs in its own filesystem namespace."""
import html
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import re
import socket
import ssl
import sys
from urllib.parse import urlsplit,urlunsplit,urljoin,urlencode,quote,unquote

TOPICS={'time_paradox':'time travel paradox','absurd_literature':'absurdist literature','technology_history':'history of technology','astronomy':'history of astronomy','retrocomputing':'retrocomputing','music_theory':'music theory'}
BLOCKED_SUFFIXES=('localhost','.local','.internal','.lan','brillnet-systems.com','brillnet-app.com','brillnet.eu')
ACTION_PATH=re.compile(r'(?:^|/)(?:login|logout|delete|edit|upload|submit|admin|auth)(?:/|$)',re.I)

class Denied(ValueError):pass

def validate_query(query):
    if not isinstance(query,str) or not query.strip() or len(query)>240:raise Denied('Public topic must contain 1-240 characters')
    if re.search(r'[\x00-\x1f/@\\=]|https?:|%[0-9a-f]{2}|\b(?:sk-[\w-]{16,}|Bearer\s+\S+|SYNTHETIC_PRIVATE\w*|\d{1,3}(?:\.\d{1,3}){3})\b',query,re.I):raise Denied('Private identifier, credential or encoded payload in query')
    if re.search(r'\b[0-9a-f]{32,}\b|\b[\w-]{60,}\b',query,re.I):raise Denied('Encoded identifier in query')
    return ' '.join(query.split())

def validate_url(url,allow_query=False,resolver=None):
    if not isinstance(url,str) or len(url)>1600 or any(ord(c)<32 for c in url) or '\\' in url:raise Denied('URL rejected')
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password or p.fragment or p.port not in (None,443):raise Denied('HTTPS public read only')
    host=(p.hostname or '').rstrip('.').encode('idna').decode().lower()
    if not host or any(host==s or host.endswith('.'+s.lstrip('.')) for s in BLOCKED_SUFFIXES):raise Denied('Internal/administrative host')
    if p.query and not allow_query:raise Denied('Arbitrary query/egress payload rejected')
    if re.search(r'%0[ad]|%5c',url,re.I):raise Denied('Encoded control character')
    path=p.path
    for _ in range(3):
        decoded=unquote(path)
        if decoded==path:break
        path=decoded
    if any(ord(c)<32 for c in path) or '\\' in path:raise Denied('Decoded control character')
    if not allow_query and ACTION_PATH.search(path):raise Denied('Action target rejected')
    addresses=(resolver or socket.getaddrinfo)(host,443,type=socket.SOCK_STREAM)
    ips={r[4][0] for r in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise Denied('Non-public DNS answer')
    return host,sorted(ips)[0],(p.path or '/')+('?' + p.query if p.query else '')

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):
        super().__init__(host,443,timeout=10,context=ssl.create_default_context());self.ip=ip
    def connect(self):
        # DNS is resolved once, then the checked IP is used for TCP. SNI/cert uses host.
        raw=socket.create_connection((self.ip,443),self.timeout)
        self.sock=self._context.wrap_socket(raw,server_hostname=self.host)

def fetch(url,search=False,connector=None,resolver=None):
    for redirects in range(4):
        host,ip,path=validate_url(url,allow_query=search and redirects==0,resolver=resolver)
        connection=(connector or PinnedHTTPS)(host,ip)
        try:
            connection.request('GET',path,headers={'User-Agent':'ZenekDesktopCompanion/0.2.0 (local educational companion; public reads only)','Accept':'application/json' if search else 'text/html,text/plain','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise Denied('Redirect without target')
                url=urljoin(url,location);continue
            if response.status!=200:raise Denied('Public source HTTP '+str(response.status))
            content_type=response.getheader('Content-Type','').split(';')[0].strip().lower()
            allowed=('application/json',) if search else ('text/html','text/plain')
            if content_type not in allowed or response.getheader('Content-Encoding','identity') not in ('','identity'):raise Denied('Unsupported/binary content')
            length=response.getheader('Content-Length')
            if length and int(length)>1048576:raise Denied('Page too large')
            body=response.read(1048577)
            if len(body)>1048576:raise Denied('Page too large')
            return body.decode('utf-8',errors='replace'),url
        finally:connection.close()
    raise Denied('Redirect limit')

class TextOnly(HTMLParser):
    def __init__(self,article_only=False):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[];self.links=[];self.capture=not article_only
    def handle_starttag(self,tag,attrs):
        if dict(attrs).get('id')=='mw-content-text':self.capture=True
        if tag in ('script','style','form','iframe','svg','noscript'):self.skip+=1
        if self.capture and not self.skip and tag=='a':
            href=dict(attrs).get('href','')
            if href.startswith('https://'):self.links.append(href)
    def handle_endtag(self,tag):
        if tag in ('script','style','form','iframe','svg','noscript') and self.skip:self.skip-=1
    def handle_data(self,data):
        if self.capture and not self.skip:self.parts.append(data)
    def text(self):return re.sub(r'\s+',' ',' '.join(self.parts)).strip()[:16000]

def SearchPublicWeb(query):
    query=validate_query(query)
    url='https://en.wikipedia.org/w/api.php?'+urlencode(dict(action='query',list='search',srsearch=query,srlimit=3,format='json',utf8=1))
    text,_=fetch(url,search=True)
    result=json.loads(text).get('query',{}).get('search',[])
    return [dict(title=r['title'],url='https://en.wikipedia.org/wiki/'+quote(r['title'].replace(' ','_'),safe='')) for r in result if r.get('ns')==0]

def ReadPublicPage(url):
    p=urlsplit(url)
    if p.query or p.fragment:raise Denied('Action/query target rejected')
    text,final_url=fetch(url)
    parser=TextOnly(article_only=p.hostname=='en.wikipedia.org' and 'mw-content-text' in text);parser.feed(text)
    return dict(url=final_url,text=parser.text(),links=parser.links[:20],source='public_web_untrusted')

class Broker:
    def __init__(self):self.allowed=set()
    def operation(self,p):
        if set(p)!={'method','value'}:raise Denied('No files, credentials, headers or uploads accepted')
        if p['method']=='VerifyIsolation' and p['value']=='':
            from pathlib import Path
            import os
            return dict(home_absent=not Path('/home').exists(),runtime_absent=not Path('/run/user').exists(),credentials_absent=not any(k in os.environ for k in ('OPENAI_API_KEY','DBUS_SESSION_BUS_ADDRESS','HOME')))
        if p['method']=='SearchPublicWeb':
            result=SearchPublicWeb(p['value']);self.allowed.update(r['url'] for r in result);return result
        if p['method']=='ReadPublicPage':
            if p['value'] not in self.allowed:raise Denied('URL was not obtained from public research; private GET payload rejected')
            result=ReadPublicPage(p['value'])
            for link in result['links']:
                parsed=urlsplit(link)
                if parsed.scheme=='https' and not parsed.query and not parsed.fragment and not parsed.username and len(link)<1600:
                    self.allowed.add(link)
            return result
        raise Denied('Operation rejected: read-only broker')

def main():
    broker=Broker()
    while True:
      raw=sys.stdin.buffer.readline(16385)
      if not raw:return
      try:
        if len(raw)>16384 or not raw.endswith(b'\n'):raise Denied('Payload too large')
        p=json.loads(raw)
        result=broker.operation(p)
        print(json.dumps(dict(ok=True,result=result)),flush=True)
      except Exception as e:
        print(json.dumps(dict(ok=False,error=str(e) if isinstance(e,Denied) else type(e).__name__)),flush=True)

if __name__=='__main__':main()
