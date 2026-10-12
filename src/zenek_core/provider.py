"""Official SIWC OAuth + Responses; no Desktop token access or tool execution."""
import base64
import asyncio
from contextlib import suppress
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import uuid
import webbrowser

import httpx
import jwt
from .memory import Keyring,MemoryBlocked
from .privacy import safe_text

AUTH="https://auth.openai.com"
API="https://api.openai.com/v1"

class ProviderBlocked(RuntimeError):pass

class Provider:
    def __init__(self,memory):
        self.memory=memory;self.catalog=[];self.auth_status="NOT_CONNECTED"
        self.refresh_lock=threading.Lock();self.login_server=None
        try:
            if self.credentials():self.auth_status="AUTHORIZED"
        except Exception:self.auth_status="MEMORY_BLOCKED"

    def credentials(self):
        raw=Keyring().get("siwc-account")
        return json.loads(raw) if raw else None

    def token(self):
        _,s=self.memory.settings()
        if s["provider"]=="api":
            if not s["paid_api_approved"]:raise ProviderBlocked("API płatne: wymagana jawna zgoda na koszt")
            token=Keyring().get("openai-api")
            if not token:raise ProviderBlocked("Nie podano klucza API")
            return token
        with self.refresh_lock:
            c=self.credentials()
            if not c:raise ProviderBlocked("Continue with ChatGPT: brak autoryzacji Zenka")
            if "chatgpt.tokens.use.direct" not in c["scopes"]:raise ProviderBlocked("Nie przyznano użycia planu ChatGPT")
            if c["expires_at"]<time.time()+60:
                with httpx.Client(timeout=20,trust_env=False) as client:
                    r=client.post(AUTH+"/api/accounts/oauth/token",data=dict(grant_type="refresh_token",client_id=c["client_id"],refresh_token=c["refresh_token"],resource=API))
                    if r.status_code!=200:raise ProviderBlocked("Odnowienie konta nieudane; zaloguj ponownie")
                    t=r.json()
                c.update(access_token=t["access_token"],refresh_token=t.get("refresh_token",c["refresh_token"]),expires_at=time.time()+t["expires_in"])
                if "scope" in t:c["scopes"]=t["scope"].split()
                Keyring().put("siwc-account",json.dumps(c))
            return c["access_token"]

    def models(self):
        token=self.token()
        with httpx.Client(timeout=20,trust_env=False) as client:
            r=client.get(API+"/models",headers={"Authorization":"Bearer "+token})
            if r.status_code!=200:raise ProviderBlocked("Katalog modeli: HTTP "+str(r.status_code))
            d=r.json()
        self.catalog=d.get("models",d.get("data",[]))
        self.catalog=[m for m in self.catalog if m.get("visibility","list")=="list"]
        self.auth_status="AUTHORIZED"
        return [dict(id=m.get("slug",m.get("id")),name=m.get("display_name",m.get("id")),efforts=self.efforts(m),vision="image" in m.get("input_modalities",[])) for m in self.catalog]

    @staticmethod
    def efforts(model):
        values=model.get("supported_reasoning_levels",model.get("supported_reasoning_efforts",[]))
        return ["auto"]+[v.get("effort") if isinstance(v,dict) else v for v in values]

    def infer(self,profile,inputs,instructions,on_delta,cancel):
        selected=self.memory.settings()[1][profile]
        try:return self._infer(profile,inputs,instructions,on_delta,cancel,selected)
        except MemoryBlocked:
            if cancel.is_set():raise ProviderBlocked('Anulowano') from None
            self.auth_status='MEMORY_BLOCKED';self.catalog=[]
            # Shared credentials are unavailable for every profile. Keep each
            # selected model/effort; a later explicit test can restore READY.
            settings=self.memory.settings()[1]
            for name in ('conversation','background_cognition','vision'):
                self.memory.profile_status(name,'UNAVAILABLE',expected=selected if name==profile else settings[name])
            raise ProviderBlocked('GNOME Keyring niedostępny; działa lokalny tryb bez LLM') from None
        except ProviderBlocked as error:
            if not cancel.is_set() and not str(error).startswith(('Limit','Anulowano')):self.memory.profile_status(profile,'UNAVAILABLE',expected=selected)
            raise
        except httpx.HTTPError:
            if cancel.is_set():raise ProviderBlocked('Anulowano') from None
            self.memory.profile_status(profile,'UNAVAILABLE',expected=selected)
            raise ProviderBlocked('Sieć niedostępna; profil LLM wstrzymany') from None

    def _infer(self,profile,inputs,instructions,on_delta,cancel,selected):
        if cancel.is_set():raise ProviderBlocked('Anulowano')
        _,s=self.memory.settings();p=selected
        if not p["model_id"]:raise ProviderBlocked("Model profilu nie został wybrany")
        if not self.catalog:self.models()
        model=next((m for m in self.catalog if m.get("slug",m.get("id"))==p["model_id"]),None)
        if model is None:raise ProviderBlocked("Wybrany model nie występuje w katalogu konta")
        payload=dict(model=p["model_id"],instructions=instructions,input=inputs,store=False,stream=True)
        if p["reasoning_effort"]!="auto":
            if p["reasoning_effort"] not in self.efforts(model):raise ProviderBlocked("Effort niedopuszczalny dla modelu")
            payload["reasoning"]={"effort":p["reasoning_effort"]}
        kind="background" if profile=="background_cognition" else profile
        limit=s["background_limit"] if kind=="background" else s["conversation_limit"]
        gap=s["background_cooldown_minutes"]*60 if kind=="background" else 0
        ticket=self.memory.reserve(kind,86400,limit,gap,model=p["model_id"],effort=p["reasoning_effort"])
        if not ticket:raise ProviderBlocked("Limit lub cooldown profilu")
        try:
            token=self.token()
            if cancel.is_set():raise ProviderBlocked('Anulowano')
            # A private selector loop keeps socket cancellation off the GNOME/Gio loop.
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                output=runner.run(self._stream(payload,token,on_delta,cancel))
            if cancel.is_set():raise ProviderBlocked('Anulowano')
            safe_text(output)
        except Exception:
            self.memory.finish_usage(ticket,'cancelled' if cancel.is_set() else 'failed')
            raise
        self.memory.finish_usage(ticket,"completed")
        self.memory.profile_status(profile,"READY",expected=selected)
        return output

    async def _stream(self,payload,token,on_delta,cancel):
        async def receive():
            output=''
            async with httpx.AsyncClient(timeout=httpx.Timeout(60,read=60),trust_env=False) as client, client.stream("POST",API+"/responses",headers={"Authorization":"Bearer "+token},json=payload) as response:
                if response.status_code!=200:raise ProviderBlocked("Inference HTTP "+str(response.status_code))
                async for line in response.aiter_lines():
                    if cancel.is_set():raise ProviderBlocked("Anulowano")
                    if not line.startswith("data: ") or line=="data: [DONE]":continue
                    event=json.loads(line[6:]);kind=event.get("type")
                    if kind=="response.output_text.delta":
                        delta=event.get("delta","");output+=delta
                        if len(output)>16000:raise ProviderBlocked("Przekroczono lokalny limit odpowiedzi")
                        on_delta(delta)
                    elif kind=="response.completed":return output
                    elif kind in ("response.failed","response.incomplete","error"):
                        raise ProviderBlocked("Inference nie zakończyła się poprawnie")
            raise ProviderBlocked("Strumień zakończył się bez response.completed")
        task=asyncio.create_task(receive())
        try:
            while not task.done():
                if cancel.is_set():raise ProviderBlocked('Anulowano')
                await asyncio.wait({task},timeout=.05)
            if cancel.is_set():raise ProviderBlocked('Anulowano')
            return task.result()
        finally:
            if not task.done():task.cancel()
            with suppress(asyncio.CancelledError):await task

    def login(self,on_status):
        if self.login_server:raise ProviderBlocked("Logowanie już trwa")
        state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        hosts=self.memory.records("host")
        if hosts:host=hosts[0]["body"]["host_id"]
        else:
            host="urn:uuid:"+str(uuid.uuid4());self.memory.add("host",{"host_id":host},"installation",1)
        old=self.credentials();selected=old["client_id"] if old else "dynamic_agent_client"
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                q=parse_qs(urlsplit(self.path).query)
                if urlsplit(self.path).path!="/auth/callback" or not secrets.compare_digest(q.get("state",[""])[0],state):
                    self.send_error(400,"Invalid callback");return
                try:
                    if "error" in q:raise ProviderBlocked("Odmowa autoryzacji")
                    issued=q.get("client_id",[selected])[0]
                    if issued=="dynamic_agent_client" or (old and issued!=selected):raise ProviderBlocked("Nieprawidłowa rejestracja klienta")
                    with httpx.Client(timeout=20,trust_env=False) as client:
                        r=client.post(AUTH+"/api/accounts/oauth/token",data=dict(grant_type="authorization_code",client_id=issued,code=q["code"][0],code_verifier=verifier,redirect_uri=redirect,resource=API))
                        if r.status_code!=200:raise ProviderBlocked("Wymiana kodu nieudana")
                        tokens=r.json()
                        discovery=client.get(AUTH+"/.well-known/openid-configuration").json()
                    if discovery.get("issuer")!=AUTH or not discovery["jwks_uri"].startswith(AUTH+"/"):
                        raise ProviderBlocked("Nieprawidłowy issuer OIDC")
                    jwks=jwt.PyJWKClient(discovery["jwks_uri"])
                    key=jwks.get_signing_key_from_jwt(tokens["id_token"])
                    claims=jwt.decode(tokens["id_token"],key.key,algorithms=["RS256"],audience=issued,issuer=AUTH,options={"require":["exp","iat","sub","nonce"]})
                    if not secrets.compare_digest(claims["nonce"],nonce) or (old and claims["sub"]!=old["subject"]):raise ProviderBlocked("Niezgodna tożsamość OIDC")
                    scopes=tokens["scope"].split()
                    if "chatgpt.tokens.use.direct" not in scopes:raise ProviderBlocked("Brak zgody na użycie planu ChatGPT")
                    c=dict(client_id=issued,subject=claims["sub"],email=claims.get("email",""),scopes=scopes,expires_at=time.time()+tokens["expires_in"],access_token=tokens["access_token"],refresh_token=tokens["refresh_token"],id_token=tokens["id_token"])
                    Keyring().put("siwc-account",json.dumps(c));owner.auth_status="AUTHORIZED"
                    message="Zenek: autoryzacja zakończona. Możesz zamknąć tę kartę."
                except Exception:
                    owner.auth_status="BLOCKED";message="Zenek: autoryzacja nieudana. Spróbuj ponownie z Settings."
                self.send_response(200);self.send_header("Content-Type","text/plain; charset=utf-8");self.end_headers();self.wfile.write(message.encode())
                on_status(owner.auth_status)
                threading.Thread(target=owner.cancel_login,daemon=True).start()
        server=HTTPServer(("127.0.0.1",0),Handler);self.login_server=server
        redirect=f"http://127.0.0.1:{server.server_port}/auth/callback"
        params=dict(client_id=selected,ext_agent_host_id=host,response_type="code",redirect_uri=redirect,scope="openid profile email offline_access resource.invoke chatgpt.tokens.use.direct",resource=API,state=state,nonce=nonce,code_challenge_method="S256",code_challenge=challenge)
        if not old:params["agent_name_hint"]="Zenek Desktop Companion"
        self.auth_status="AWAITING_BROWSER"
        threading.Thread(target=server.serve_forever,daemon=True).start()
        webbrowser.open(AUTH+"/api/accounts/authorize?"+urlencode(params))
        timer=threading.Timer(300,self.cancel_login);timer.daemon=True;timer.start()
        return self.auth_status

    def cancel_login(self):
        server=self.login_server;self.login_server=None
        if server:server.shutdown();server.server_close()
        if self.auth_status=="AWAITING_BROWSER":self.auth_status="NOT_CONNECTED"

    def logout(self):
        self.cancel_login();Keyring().delete("siwc-account");self.catalog=[];self.auth_status="NOT_CONNECTED"
        for p in ("conversation","background_cognition","vision"):self.memory.profile_status(p,"UNAVAILABLE")
