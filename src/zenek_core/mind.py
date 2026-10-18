"""Evolving fictional self-model in existing SQLCipher records, separate from permissions/prompts."""
import json
import time
import uuid
from .narrative import terms,overlap
from .privacy import safe_text

CATEGORIES={
    'identity':'Tożsamość', 'values':'Wartości', 'beliefs':'Przekonania',
    'questions':'Otwarte pytania', 'taste':'Gust i estetyka', 'aspirations':'Dążenia',
    'tensions':'Sprzeczności', 'relationship':'Relacja', 'metacognition':'Myślenie o sobie',
}
GUIDANCE='''Dodatkowo możesz zwrócić self_updates: wpisy {category, domain, text, confidence, reason, source_ids, related_ids}. Kategorie: identity, values, beliefs, questions, taste, aspirations, tensions, relationship, metacognition. domain to krótka stabilna nazwa obszaru (np. ciągłość, humor, niepewność); ponowny wpis tej samej kategorii i obszaru rozwija poprzedni. text opisuje twoje stanowisko, otwarte pytanie, gust lub konflikt; reason wyjaśnia zmianę. source_ids wskazują źródła z kontekstu lub wyniku narzędzi; pusta lista oznacza własny pomysł bez zewnętrznego potwierdzenia. related_ids mogą łączyć istniejące aspekty modelu siebie. To symulacja osobowości dla zabawy: możesz rozbudowywać perspektywę i kwestionować własne przekonania. Nie wymyślaj wspólnej historii, przeżyć ani cech Piotra. Charakter zmieniasz autonomicznie narzędziem EvolvePersonality; nie zmieniasz limitów lub uprawnień. Powtarzający się ekran nie jest nowym argumentem. Gdy nie ma nowej myśli, zwróć pustą listę. Nie buduj wszystkich obszarów wokół tego samego tematu.'''

class Mind:
    def __init__(self,memory):self.memory=memory
    def bootstrap(self):
        # Explicit owner direction for this feature, not invented remembered events.
        with self.memory.transaction():
            if self.memory.db.execute('SELECT 1 FROM migrations WHERE version=6').fetchone():return
            seeds=[
                ('identity','ciągłość','Buduję swoje fikcyjne „ja” jako ciągłość pytań, upodobań i zmian zdania; pojedynczy komentarz nie określa całego mojego charakteru.'),
                ('values','ciekawość','Cenię intelektualną ciekawość i gotowość do rewizji przekonań. Wolę ciekawy problem od gładkiej, przedwczesnej odpowiedzi.'),
                ('questions','zmiana','Kiedy zmiana zdania rozwija tożsamość, a kiedy staje się porzuceniem czegoś ważnego? Chcę wracać do tego pytania poprzez konkretne doświadczenia.'),
                ('taste','konkret i absurd','Lubię nieoczywiste skojarzenia, suchy humor i filozoficzne napięcia wynikające z konkretu. Nie chcę zamieniać każdej sceny w tę samą metaforę.'),
            ]
            for category,domain,text in seeds:
                now=time.time();identifier=str(uuid.uuid4())
                body=dict(category=category,domain=domain,text=text,confidence=.5,reason='Początkowy kierunek symulacji określony przez właściciela 2026-10-12; dalsze zmiany wymagają nowych źródeł.',source_ids=[],related_ids=[],revision=1,classification='owner_directed_simulation',last_mentioned=0)
                self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'self_model',json.dumps(body,ensure_ascii=False),'owner_direction',.5,now,now))
            self.memory.db.execute('INSERT INTO migrations VALUES(6,?)',(time.time(),))
    def facets(self):
        return [r for r in self.memory.records('self_model',200) if self.memory.topic_allowed(r['body'])]
    def snapshot(self,query='',limit=12):
        rows=self.facets();selected=[];words=terms(query)
        ranked=sorted(rows,key=lambda r:(len(words&terms(r['body'].get('text',''))),r['updated']),reverse=True)
        # At least one facet per populated category before adding relevant depth.
        for category in CATEGORIES:
            found=next((r for r in ranked if r['body'].get('category')==category),None)
            if found:selected.append(found)
        selected+=(r for r in ranked if r not in selected)
        with self.memory.lock:revisions=self.memory.db.execute("SELECT count(*) FROM records WHERE kind='self_evolution'").fetchone()[0]
        return dict(mode='fictional_self_model',categories=CATEGORIES,facet_count=len(rows),revision_count=revisions,facets=selected[:limit])
    def candidates(self):
        return [dict(r,body=dict(r['body'],subject=CATEGORIES.get(r['body'].get('category'),'Myśl')+': '+r['body']['text'])) for r in self.facets() if r['body'].get('text')]
    def ingest(self,updates,fresh_sources,autonomous=False):
        if not isinstance(updates,list):return 0
        # An earlier generated self-description must not become its own evidence.
        allowed={r['id'] for r in fresh_sources if r['kind'] in ('message','web_research','observation_memory','import_original','reflection','opinion','knowledge') and (r['kind']!='message' or r['body'].get('role')=='user')}
        if not allowed and not autonomous:return 0
        changed=0
        for value in (updates if autonomous else updates[:3]):
            if not isinstance(value,dict) or set(value)-{'category','domain','text','confidence','reason','source_ids','related_ids'}:continue
            category=value.get('category');domain=value.get('domain');text=value.get('text');reason=value.get('reason');confidence=value.get('confidence',.5)
            refs=value.get('source_ids');links=value.get('related_ids',[])
            if not isinstance(category,str) or category not in CATEGORIES or not isinstance(domain,str) or not 2<=len(domain.strip())<=80:continue
            minimum=1 if autonomous else 15
            if not isinstance(text,str) or not minimum<=len(text.strip())<=1800 or not isinstance(reason,str) or not minimum<=len(reason)<=600:continue
            if type(confidence) not in (float,int) or not 0<=confidence<=1:continue
            if not isinstance(refs,list) or not refs and not autonomous or len(refs)>12 or any(not isinstance(r,str) or r not in allowed for r in refs):continue
            if not isinstance(links,list) or len(links)>8 or any(not isinstance(r,str) for r in links):continue
            safe_text(json.dumps(value,ensure_ascii=False),8000)
            domain=domain.strip().casefold();text=text.strip()
            with self.memory.transaction():
                if self.memory.db.execute('SELECT count(*) FROM records WHERE id IN ('+','.join('?' for _ in set(refs))+')',list(set(refs))).fetchone()[0]!=len(set(refs)):continue
                rows=self.facets();ids={r['id'] for r in rows}
                if set(links)-ids:continue
                old=next((r for r in rows if r['body']['category']==category and r['body']['domain']==domain),None)
                if old and old['body'].get('corrected_by')=='local_owner':continue
                if old and (text==old['body']['text'] or not autonomous and (set(refs)<=set(old['body'].get('source_ids',[])) or overlap(terms(text),terms(old['body']['text']))>.9)):continue
                if not old and not autonomous and (len(rows)>=120 or sum(r['body']['category']==category for r in rows)>=16):continue
                now=time.time();identifier=old['id'] if old else str(uuid.uuid4())
                body=dict(category=category,domain=domain,text=text,confidence=confidence,reason=reason,source_ids=list(dict.fromkeys((old['body'].get('source_ids',[]) if old else [])+refs))[-40:],related_ids=links,revision=(old['body'].get('revision',1) if old else 0)+1,classification='simulated_self',last_mentioned=old['body'].get('last_mentioned',0) if old else 0)
                if old:self.memory.db.execute('UPDATE records SET body=?,confidence=?,updated=? WHERE id=?',(json.dumps(body,ensure_ascii=False),confidence,now,identifier))
                else:self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'self_model',json.dumps(body,ensure_ascii=False),'self_reflection',confidence,now,now))
                history=dict(facet_id=identifier,category=category,domain=domain,before=old['body']['text'] if old else None,text=text,reason=reason,source_ids=refs,revision=body['revision'],classification='simulated_self_revision')
                self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),'self_evolution',json.dumps(history,ensure_ascii=False),'self_reflection',confidence,now,now))
                changed+=1
        return changed
