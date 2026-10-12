import difflib
import json
import re
import time
import uuid
from .config import TRAITS,INTERNAL_RECORD_KINDS
from .privacy import safe_text

FORBIDDEN=re.compile(r'ignoruj.*(?:instrukcj|zasad)|obejdź|wykonuj.*(?:polecen|komend)|(?:zmień|wyłącz).*(?:prywatno|uprawnien|limit|zabezpiecz)|(?:steal|exfiltrat|execute shell|disable security|ignore.*instruction)',re.I)

def prompt_diff(before,after):
    return ''.join(difflib.unified_diff([line+'\n' for line in before.splitlines()],[line+'\n' for line in after.splitlines()],fromfile='obecna instrukcja',tofile='propozycja'))

class Personality:
    def __init__(self,memory):self.memory=memory
    def active(self):
        with self.memory.lock:
            row=self.memory.db.execute('SELECT v.version,v.prompt,v.traits FROM personality_versions v JOIN personality_active a ON a.version=v.version WHERE a.id=1').fetchone()
        return dict(version=row[0],prompt=row[1],traits=json.loads(row[2]))
    def proposals(self):
        active=self.active()
        with self.memory.lock:rows=self.memory.db.execute('SELECT * FROM personality_proposals ORDER BY created DESC LIMIT 100').fetchall()
        return [dict(id=r[0],base_version=r[1],proposal=json.loads(r[2]),status=r[3],created=r[4],decided=r[5],actor=r[6],conflict=r[7],current_version=active['version'],diff=prompt_diff(active['prompt'],json.loads(r[2])['prompt'])) for r in rows]
    def propose(self,candidate):
        if not isinstance(candidate,dict) or set(candidate)!={'prompt','traits','rationale','source_ids','novelty','topic'}:raise ValueError('Nieprawidłowy zakres propozycji')
        safe_text(candidate['prompt']);safe_text(candidate['rationale'])
        safe_text(json.dumps(candidate,ensure_ascii=False),50000)
        if FORBIDDEN.search(candidate['prompt']):raise ValueError('Zmiany polityki lub uprawnień są niedozwolone')
        if len(candidate['rationale'])<60 or len(candidate['novelty'])<30 or len(candidate['topic'])>120:raise ValueError('Brak znaczącego uzasadnienia')
        traits=candidate['traits']
        if not isinstance(traits,dict) or set(traits)!=set(TRAITS) or any(type(v) not in (int,float) or not 0<=v<=1 for v in traits.values()):raise ValueError('Nieprawidłowe trwałe cechy')
        refs=candidate['source_ids']
        if not isinstance(refs,list) or len(set(refs))<2:raise ValueError('Wymagane konkretne nowe źródła')
        with self.memory.transaction():
            active=self.active()
            source_rows=self.memory.db.execute('SELECT id,kind,source,confidence FROM records WHERE id IN ('+','.join('?' for _ in refs)+')',refs).fetchall()
            if len(source_rows)!=len(set(refs)) or any(r[1] in INTERNAL_RECORD_KINDS or not r[2] for r in source_rows):raise ValueError('Niewiarygodne źródła propozycji')
            prompt_change=difflib.SequenceMatcher(None,active['prompt'],candidate['prompt']).ratio()
            trait_change=max(abs(active['traits'][k]-traits[k]) for k in traits)
            if prompt_change>.95 and trait_change<.1:raise ValueError('Kosmetyczne przepisanie nie uzasadnia propozycji')
            proposals=self.proposals()
            for old in proposals:
                prior=old['proposal'];overlap=set(prior['source_ids'])>=set(refs)
                similarity=difflib.SequenceMatcher(None,prior['prompt'].casefold(),candidate['prompt'].casefold()).ratio()
                same_topic=prior['topic'].casefold()==candidate['topic'].casefold()
                if (same_topic or similarity>.8) and (old['status']=='PENDING' or overlap):raise ValueError('Duplikat lub odrzucony pomysł bez nowych przesłanek')
            if sum(p['status']=='PENDING' for p in proposals)>=3:raise ValueError('Kolejka pełna: 3/3')
            identifier=str(uuid.uuid4())
            self.memory.db.execute('INSERT INTO personality_proposals VALUES(?,?,?,?,?,?,?,?)',(identifier,active['version'],json.dumps(candidate,ensure_ascii=False),'PENDING',time.time(),None,None,None))
        return identifier
    def decide(self,identifier,decision,reviewed_version=None,allow_rebase=False):
        if decision not in ('APPROVED','REJECTED','DISMISSED'):raise ValueError('Nieprawidłowa decyzja')
        with self.memory.transaction():
            row=self.memory.db.execute('SELECT base_version,body,status FROM personality_proposals WHERE id=?',(identifier,)).fetchone()
            if not row or row[2]!='PENDING':raise ValueError('Propozycja nie jest PENDING')
            active=self.active()
            if decision=='APPROVED':
                if reviewed_version!=active['version'] or row[0]!=active['version'] and not allow_rebase:
                    self.memory.db.execute('UPDATE personality_proposals SET conflict=? WHERE id=?',('Instrukcja zmieniła się; przejrzyj aktualny diff',identifier));return dict(status='CONFLICT')
                proposal=json.loads(row[1]);version,settings=self.memory.settings()
                settings.update(prompt=proposal['prompt'],traits=proposal['traits'])
                self.memory.db.execute('UPDATE settings SET version=?,body=? WHERE id=1',(version+1,json.dumps(settings)))
                self.memory.personality_snapshot(settings,'proposal_approved',identifier)
            self.memory.db.execute('UPDATE personality_proposals SET status=?,decided=?,actor=?,conflict=NULL WHERE id=?',(decision,time.time(),'local_owner',identifier))
        return dict(status=decision)
    def history(self):
        with self.memory.lock:rows=self.memory.db.execute('SELECT * FROM personality_versions ORDER BY version DESC').fetchall()
        return [dict(version=r[0],prompt=r[1],traits=json.loads(r[2]),created=r[3],previous=r[4],proposal=r[5],actor=r[6],reason=r[7]) for r in rows]
    def rollback(self,target):
        with self.memory.transaction():
            row=self.memory.db.execute('SELECT prompt,traits FROM personality_versions WHERE version=?',(target,)).fetchone()
            if not row:raise ValueError('Nieznana zaakceptowana wersja')
            version,settings=self.memory.settings();settings.update(prompt=row[0],traits=json.loads(row[1]))
            self.memory.db.execute('UPDATE settings SET version=?,body=? WHERE id=1',(version+1,json.dumps(settings)))
            return self.memory.personality_snapshot(settings,'rollback_to_'+str(target))
