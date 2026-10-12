"""All durable content in SQLCipher; credentials only in Secret Service."""
import copy
import json
import os
import secrets
import threading
import time
import uuid
import re
from contextlib import contextmanager

import secretstorage
from sqlcipher3 import dbapi2 as cipher
from .config import DATA, DEFAULTS,BASE_PROMPT,LEGACY_BASE_PROMPT,INTERNAL_RECORD_KINDS
from .privacy import safe_text

class MemoryBlocked(RuntimeError):
    pass

class Keyring:
    def __init__(self):
        self.bus = secretstorage.dbus_init()
        self.collection = secretstorage.get_default_collection(self.bus)
        if self.collection.is_locked():
            raise MemoryBlocked("Pamięć zablokowana: odblokuj GNOME Keyring systemowym oknem.")

    def get(self, name):
        items = list(self.collection.search_items({"application":"zenek-desktop", "key":name}))
        return items[0].get_secret().decode() if items else None

    def put(self, name, value):
        if self.collection.is_locked():
            raise MemoryBlocked("GNOME Keyring zablokowany")
        self.collection.create_item("Zenek — "+name,
            {"application":"zenek-desktop", "key":name}, value.encode(), replace=True)

    def delete(self, name):
        for item in self.collection.search_items({"application":"zenek-desktop", "key":name}):
            item.delete()

class Memory:
    def __init__(self, path=None, key=None):
        os.umask(0o077)
        self.path = path or DATA/"memory.db"
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        if key is None:
            vault = Keyring()
            key = vault.get("sqlcipher-key")
            if not key:
                if self.path.exists():
                    raise MemoryBlocked("Brak klucza istniejącej pamięci; baza pozostaje nienaruszona.")
                key = secrets.token_hex(32)
                vault.put("sqlcipher-key", key)
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise MemoryBlocked("Nieprawidłowy klucz pamięci")
        self.lock = threading.RLock()
        self.db = cipher.connect(str(self.path), check_same_thread=False)
        self.db.execute('PRAGMA key="x\''+key+'\'"')
        key = None
        if not self.db.execute("PRAGMA cipher_version").fetchone():
            raise MemoryBlocked("SQLCipher niedostępny; brak fallbacku")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("SELECT count(*) FROM sqlite_master").fetchone()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER,body TEXT);
            CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT,body TEXT,source TEXT,confidence REAL,created REAL,updated REAL);
            CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY,kind TEXT,created REAL,status TEXT,model TEXT,effort TEXT);
            CREATE INDEX IF NOT EXISTS usage_time ON usage(kind,created);
            CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY,applied REAL);
            INSERT OR IGNORE INTO migrations VALUES(1,strftime('%s','now'));
            CREATE TABLE IF NOT EXISTS personality_versions(version INTEGER PRIMARY KEY AUTOINCREMENT,prompt TEXT,traits TEXT,created REAL,previous INTEGER,proposal TEXT,actor TEXT,reason TEXT);
            CREATE TABLE IF NOT EXISTS personality_active(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER REFERENCES personality_versions(version));
            CREATE TABLE IF NOT EXISTS personality_proposals(id TEXT PRIMARY KEY,base_version INTEGER,body TEXT,status TEXT CHECK(status IN ('PENDING','APPROVED','REJECTED','DISMISSED')),created REAL,decided REAL,actor TEXT,conflict TEXT);
            INSERT OR IGNORE INTO migrations VALUES(2,strftime('%s','now'));
            CREATE TABLE IF NOT EXISTS capability_checks(kind TEXT PRIMARY KEY,code_hash TEXT,checked REAL);
            INSERT OR IGNORE INTO migrations VALUES(3,strftime('%s','now'));
            CREATE TABLE IF NOT EXISTS import_sources(id TEXT PRIMARY KEY,path TEXT,hash TEXT,created REAL);
            CREATE TABLE IF NOT EXISTS import_entries(fingerprint TEXT PRIMARY KEY,record_id TEXT,original_hash TEXT);
            CREATE TABLE IF NOT EXISTS import_refs(source_id TEXT,unit_id TEXT,entry_id TEXT,fingerprint TEXT,content_hash TEXT,PRIMARY KEY(source_id,unit_id,entry_id));
            CREATE TABLE IF NOT EXISTS import_jobs(id TEXT PRIMARY KEY,body TEXT,status TEXT,updated REAL);
            INSERT OR IGNORE INTO migrations VALUES(4,strftime('%s','now'));
            CREATE TABLE IF NOT EXISTS memory_controls(id INTEGER PRIMARY KEY CHECK(id=1),seeded INTEGER);
            INSERT OR IGNORE INTO memory_controls VALUES(1,0);
            CREATE TABLE IF NOT EXISTS topic_suppressions(subject TEXT PRIMARY KEY,created REAL);
            INSERT OR IGNORE INTO migrations VALUES(5,strftime('%s','now'));
        """)
        self.db.execute("INSERT OR IGNORE INTO settings VALUES(1,1,?)", (json.dumps(DEFAULTS),))
        self.db.commit()
        if not self.db.execute('SELECT version FROM personality_active WHERE id=1').fetchone():
            with self.transaction():self.personality_snapshot(self.settings()[1],'initial')
        if self.settings()[1]['prompt']==LEGACY_BASE_PROMPT:
            with self.transaction():
                version,settings=self.settings();settings['prompt']=BASE_PROMPT
                self.db.execute('UPDATE settings SET version=?,body=? WHERE id=1',(version+1,json.dumps(settings)))
                self.personality_snapshot(settings,'baseline_1.32_alignment')
        self.path.chmod(0o600)
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise MemoryBlocked("Błąd integralności pamięci")
        if not self.db.execute('SELECT seeded FROM memory_controls WHERE id=1').fetchone()[0]:
            if not self.records('interest'):
                for subject in ["paradoksy podróży w czasie", "absurd w literaturze", "dziwne początki technologii"]:
                    self.add("interest", dict(subject=subject, strength=.7, status="new", last_mentioned=0), "original_seed", 1)
            self.db.execute('UPDATE memory_controls SET seeded=1 WHERE id=1');self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def settings(self):
        with self.lock:
            version, body = self.db.execute("SELECT version,body FROM settings WHERE id=1").fetchone()
            settings=json.loads(body)
            # New optional controls keep their explicit defaults on older databases.
            settings.setdefault('screen_comment_priority','off')
            settings.setdefault('screen_snapshot_seconds',60);settings.setdefault('visual_graphics_threshold',40)
            return version, settings

    def patch(self, patch, expected):
        if not isinstance(patch, dict) or set(patch)-set(DEFAULTS):
            raise ValueError("Nieznane ustawienie")
        with self.transaction():
            version, settings = self.settings()
            if version != expected:
                raise ValueError("Konflikt wersji ustawień; odśwież panel")
            for k,v in patch.items():
                if k in ("conversation","background_cognition","vision"):
                    if not isinstance(v,dict) or set(v)!={"model_id","reasoning_effort","status"}:
                        raise ValueError("Nieprawidłowy profil")
                    if not isinstance(v["model_id"],str) or len(v["model_id"])>120:
                        raise ValueError("Nieprawidłowy model")
                    v = dict(v, status="NOT_CONFIGURED" if not v["model_id"] else "UNAVAILABLE")
                elif k == "traits":
                    if set(v)!=set(DEFAULTS[k]) or any(type(n) not in (int,float) or not 0<=n<=1 for n in v.values()):
                        raise ValueError("Nieprawidłowe cechy")
                elif isinstance(DEFAULTS[k],bool):
                    if type(v) is not bool: raise ValueError("Wymagana wartość logiczna")
                elif isinstance(DEFAULTS[k],int):
                    if type(v) is not int or not -1<=v<=10000: raise ValueError("Nieprawidłowy limit")
                    if k.endswith("minutes") and v<1: raise ValueError("Odstęp musi być dodatni")
                elif not isinstance(v,str) or len(v)>16000:
                    raise ValueError("Nieprawidłowy tekst")
                if k=="prompt":safe_text(v)
                settings[k]=v
            if settings["provider"] not in ("siwc","api") or settings["background_mode"] not in ("B","C"):
                raise ValueError("Nieprawidłowy tryb")
            if settings['screen_comment_priority'] not in ('off','balanced','high'):raise ValueError('Nieprawidłowy priorytet ekranu')
            if not 15<=settings['screen_snapshot_seconds']<=3600:raise ValueError('Odstęp zrzutów musi wynosić od 15 do 3600 sekund')
            if not 10<=settings['visual_graphics_threshold']<=90:raise ValueError('Próg grafiki musi wynosić od 10 do 90 procent')
            self.db.execute("UPDATE settings SET version=?,body=? WHERE id=1",(version+1,json.dumps(settings)))
            if set(patch)&{'prompt','traits'}:self.personality_snapshot(settings,'manual')
        return version+1

    def profile_status(self, profile, status, expected=None):
        with self.transaction():
            version, settings=self.settings()
            if expected is not None and any(settings[profile][key]!=expected[key] for key in ('model_id','reasoning_effort')):return False
            if settings[profile]['status']==status:return True
            settings[profile]["status"]=status
            self.db.execute("UPDATE settings SET version=?,body=? WHERE id=1",(version+1,json.dumps(settings)))
            return True

    def add(self, kind, body, source, confidence=.5, item_id=None):
        safe_text(json.dumps(body,ensure_ascii=False),100000)
        item_id=item_id or str(uuid.uuid4())
        with self.lock:
            self.db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)",(item_id,kind,json.dumps(body,ensure_ascii=False),source,confidence,time.time(),time.time()))
            self.db.commit()
        return item_id

    def records(self, kind=None, limit=200):
        with self.lock:
            rows=self.db.execute("SELECT * FROM records "+("WHERE kind=? " if kind else "")+"ORDER BY created DESC LIMIT ?", (kind,limit) if kind else (limit,)).fetchall()
        return [dict(id=r[0],kind=r[1],body=json.loads(r[2]),source=r[3],confidence=r[4],created=r[5],updated=r[6]) for r in rows]

    def visible_records(self,kind=None,limit=200):
        if kind in INTERNAL_RECORD_KINDS:return []
        with self.lock:
            rows=self.db.execute('SELECT * FROM records WHERE kind NOT IN (?,?,?) '+('AND kind=? ' if kind else '')+'ORDER BY created DESC LIMIT ?',(*INTERNAL_RECORD_KINDS,kind,limit) if kind else (*INTERNAL_RECORD_KINDS,limit)).fetchall()
        return [dict(id=r[0],kind=r[1],body=json.loads(r[2]),source=r[3],confidence=r[4],created=r[5],updated=r[6]) for r in rows]

    def update(self, item_id, body):
        safe_text(json.dumps(body,ensure_ascii=False),100000)
        with self.lock:
            self.db.execute("UPDATE records SET body=?,updated=? WHERE id=?",(json.dumps(body),time.time(),item_id));self.db.commit()

    def delete(self, item_id):
        with self.lock:
            self.editable_record(item_id)
            self.db.execute("DELETE FROM records WHERE id=?",(item_id,));self.db.commit()

    def editable_record(self,item_id):
        record=self.record(item_id)
        if record['kind'] in INTERNAL_RECORD_KINDS:raise ValueError('Konfiguracja wewnętrzna nie jest wspomnieniem')
        return record

    def record(self,item_id):
        with self.lock:row=self.db.execute('SELECT * FROM records WHERE id=?',(item_id,)).fetchone()
        if not row:raise ValueError('Wspomnienie nie istnieje')
        return dict(id=row[0],kind=row[1],body=json.loads(row[2]),source=row[3],confidence=row[4],created=row[5],updated=row[6])

    def correct(self,item_id,field,value):
        if field not in ('text','subject','detailed_text','note') or not isinstance(value,str):raise ValueError('Nieprawidłowa korekta tekstu')
        record=self.editable_record(item_id);body=record['body']
        if field not in body:raise ValueError('To wspomnienie nie zawiera tego pola')
        body.setdefault('original_'+field,body[field]);body[field]=value;body['corrected_by']='local_owner';body['corrected_at']=time.time()
        self.update(item_id,body)

    def suppress(self,item_id):
        record=self.editable_record(item_id);body=dict(record['body'],do_not_mention=True,status='dismissed')
        self.update(item_id,body)
        if body.get('subject'):
            subject=' '.join(body['subject'].casefold().split())
            with self.transaction():self.db.execute('INSERT OR IGNORE INTO topic_suppressions VALUES(?,?)',(subject,time.time()))

    def topic_allowed(self,body):
        if body.get('do_not_mention') or body.get('status') in ('dismissed','expired'):return False
        subject=' '.join(body.get('subject','').casefold().split())
        with self.lock:
            if body.get('proposal_id'):
                proposal=self.db.execute('SELECT status FROM personality_proposals WHERE id=?',(body['proposal_id'],)).fetchone()
                if not proposal or proposal[0]!='PENDING':return False
            return not subject or not self.db.execute('SELECT 1 FROM topic_suppressions WHERE subject=?',(subject,)).fetchone()

    def clear(self,kind=None):
        protected=INTERNAL_RECORD_KINDS
        if kind in protected:raise ValueError('Konfiguracja wewnętrzna nie jest wspomnieniem')
        with self.transaction():
            if kind:self.db.execute('DELETE FROM records WHERE kind=?',(kind,))
            else:self.db.execute('DELETE FROM records WHERE kind NOT IN (?,?,?)',protected)
            # Import fingerprints are tombstones: deleted originals never silently
            # reappear after a delta update. Usage/account/personality are intact.

    def export(self,path):
        from pathlib import Path
        path=Path(path)
        with self.lock:rows=self.db.execute("SELECT * FROM records WHERE kind NOT IN ('host','self_state','cognition_checkpoint') ORDER BY created").fetchall()
        records=[dict(id=r[0],kind=r[1],body=json.loads(r[2]),source=r[3],confidence=r[4],created=r[5],updated=r[6]) for r in rows]
        payload=json.dumps(dict(format='zenek-memory-v1',created=time.time(),records=records),ensure_ascii=False,indent=2).encode()
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as output:output.write(payload)
        return dict(records=len(records),bytes=len(payload),path=str(path))

    def reserve(self, kind, window, limit, cooldown=0, now=None, model="", effort=""):
        now=time.time() if now is None else now
        with self.transaction():
            rows=self.db.execute("SELECT created FROM usage WHERE kind=? AND created>? ORDER BY created DESC",(kind,now-window)).fetchall()
            if len(rows)>=limit or (rows and now-rows[0][0]<cooldown): return None
            identifier=str(uuid.uuid4())
            self.db.execute("INSERT INTO usage VALUES(?,?,?,?,?,?)",(identifier,kind,now,"attempt",model,effort))
            return identifier

    def usage(self):
        with self.lock:
            return {k:n for k,n in self.db.execute("SELECT kind,count(*) FROM usage WHERE created>? GROUP BY kind",(time.time()-86400,))}

    def finish_usage(self, identifier, status):
        with self.lock:
            self.db.execute("UPDATE usage SET status=? WHERE id=?",(status,identifier));self.db.commit()

    def can_reserve(self,kind,window,limit,cooldown=0,now=None):
        now=time.time() if now is None else now
        with self.lock:
            count,last=self.db.execute("SELECT count(*),max(created) FROM usage WHERE kind=? AND created>?",(kind,now-window)).fetchone()
        return count<limit and (last is None or now-last>=cooldown)

    def budget(self,kind,window,limit,cooldown=0,now=None):
        now=time.time() if now is None else now
        with self.lock:
            rows=self.db.execute('SELECT created FROM usage WHERE kind=? AND created>? ORDER BY created',(kind,now-window)).fetchall()
        # Reducing a limit below current usage waits until enough attempts expire.
        wait=max(0,rows[-1][0]+cooldown-now) if rows else 0
        if rows and len(rows)>=limit and limit>0:wait=max(wait,rows[len(rows)-limit][0]+window-now)
        return dict(used=len(rows),limit=limit,remaining=max(0,limit-len(rows)),wait_seconds=round(wait),enabled=limit>0)

    def context(self,query,limit=24,diverse=False):
        # No category blacklist: detailed observations/import originals are eligible.
        words=set(re.findall(r'\w+',query.casefold()))
        with self.lock:rows=self.db.execute("SELECT * FROM records WHERE kind NOT IN ('host','personality_proposal','personality_version','import_checkpoint','cognition_checkpoint')").fetchall()
        candidates=[dict(id=r[0],kind=r[1],body=json.loads(r[2]),source=r[3],confidence=r[4],created=r[5],updated=r[6]) for r in rows]
        candidates=[r for r in candidates if self.topic_allowed(r['body'])]
        for r in candidates:r['body']={k:v for k,v in r['body'].items() if not k.startswith('original_')}
        def score(r):
            terms=set(re.findall(r'\w+',json.dumps(r['body'],ensure_ascii=False).casefold()))
            return len(words&terms)*3+r['confidence']+(1/(1+(time.time()-r['created'])/86400))
        ranked=sorted(candidates,key=score,reverse=True)
        if diverse:
            from .narrative import terms,overlap
            selected=[];counts={};signatures=[]
            for r in ranked:
                if r['kind'] in ('self_model','self_evolution'):continue # Dedicated bounded self-model context.
                signature=terms(r['body'].get('detailed_text') or r['body'].get('text') or r['body'].get('subject',''))
                if counts.get(r['kind'],0)>=4 or len(signature)>3 and any(overlap(signature,other)>.8 for other in signatures):continue
                selected.append(r);signatures.append(signature);counts[r['kind']]=counts.get(r['kind'],0)+1
                if len(selected)>=limit:break
        else:selected=ranked[:limit]
        for record in selected:
            identifier=record['body'].get('proposal_id')
            if identifier:
                with self.lock:proposal=self.db.execute('SELECT base_version,body,status FROM personality_proposals WHERE id=?',(identifier,)).fetchone()
                if proposal and proposal[2]=='PENDING':
                    record['body']['pending_proposal']=dict(classification='unapproved_proposal',status=proposal[2],base_version=proposal[0],proposal=json.loads(proposal[1]))
        return selected

    def close(self):
        with self.lock:self.db.close()

    def personality_snapshot(self,settings,reason,proposal=None):
        old=self.db.execute('SELECT version FROM personality_active WHERE id=1').fetchone()
        cursor=self.db.execute('INSERT INTO personality_versions(prompt,traits,created,previous,proposal,actor,reason) VALUES(?,?,?,?,?,?,?)',
            (settings['prompt'],json.dumps(settings['traits']),time.time(),old[0] if old else None,proposal,'local_owner',reason))
        version=cursor.lastrowid
        self.db.execute('INSERT INTO personality_active VALUES(1,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version',(version,))
        return version
