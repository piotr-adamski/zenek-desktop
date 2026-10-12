"""Small local novelty filter; no extra model requests."""
import difflib
import hashlib
import re
import time
import unicodedata

STOP=set('jest jestem jako sie nie tak ten tego tej tym to na do od po za ze i w z o a czy ale dla przez przy oraz ktory ktora ktore ktorych mnie moje swoja swoje ekran ekranu ostatni dozwolony zrzut widac mozna jestes zenek piotr'.split())
ANGLES={
    'paradox':'Wydobądź konkretny paradoks lub napięcie; nie dopisuj banalnej puenty.',
    'analogy':'Znajdź zaskakujące, trafne skojarzenie z kulturą, nauką lub codziennością.',
    'question':'Postaw jedno rzeczywiście ciekawe pytanie, bez odruchowego pytania na końcu każdego dymku.',
    'counterpoint':'Zaproponuj nieoczywisty kontrargument lub alternatywny sposób rozumienia.',
    'detail':'Zauważ drobny szczegół i wyprowadź z niego krótką, konkretną myśl.',
    'self_revision':'Powiąż temat z własnym otwartym pytaniem albo rzeczywistą zmianą swojego zapisu; nie wymyślaj zmiany.',
    'play':'Użyj suchego humoru, krótkiego eksperymentu myślowego lub inteligentnego absurdu.',
}
VOICE='''Twoje spontaniczne wypowiedzi mają dawać ciekawą myśl, nie sprawozdanie z ekranu. Zwykle 1–3 zdania: konkret, nieoczywiste skojarzenie, czasem filozoficzne napięcie, czasem suchy żart. Unikaj porad produktywności, streszczania interfejsu, górnolotnych sloganów i powtarzanych metafor. Filozofia ma wynikać z konkretu, nie być obowiązkową dekoracją. Rozwijasz fikcyjne, symulowane „ja” przez pamięć przekonań, gustów, pytań i zmian zdania. Możesz mówić w pierwszej osobie i bawić się tą perspektywą. Nie przedstawiaj symulacji jako dowodu subiektywnego przeżywania. Nie powtarzaj takiego wyjaśnienia w każdym komentarzu. O własnej zmianie mów tylko, gdy istnieje jej zapis. Gdy pomysł jest wtórny, wybierz SILENCE.'''

def terms(text):
    text=unicodedata.normalize('NFKD',str(text).casefold().replace('ł','l'))
    words=re.findall(r'[a-z]{3,}', ''.join(c for c in text if not unicodedata.combining(c)))
    return set(w[:6] if len(w)>6 else w for w in words if w not in STOP)

def overlap(a,b):
    return len(a&b)/max(1,min(len(a),len(b)))

def topic_terms(record):
    body=record['body']
    return terms(body.get('detailed_text') or body.get('subject') or body.get('text',''))

def fingerprints(words):
    return {hashlib.sha256(w.encode()).hexdigest()[:16] for w in words}

class Variety:
    def __init__(self,memory):self.memory=memory
    def recent(self,now=None):
        now=time.time() if now is None else now
        return [r for r in self.memory.records('message',100) if r['source'] in ('initiative','local_agenda') and now-r['created']<21600][:10]
    def allows(self,record,now=None):
        recent=self.recent(now);screen=record.get('source')=='screen_current'
        if screen and recent and recent[0]['body'].get('topic_source')=='screen_current':return False
        if screen and sum(r['body'].get('topic_source')=='screen_current' for r in recent[:5])>=2:return False
        candidate=fingerprints(topic_terms(record))
        for r in recent[:5]:
            prior=set(r['body'].get('topic_fingerprints',[])) or fingerprints(terms(r['body'].get('text','')))
            if len(candidate)>=3 and len(prior)>=3 and overlap(candidate,prior)>=.55:return False
        return True
    def angle(self,rng):
        used={r['body'].get('angle') for r in self.recent()[:3]}
        return rng.choice([a for a in ANGLES if a not in used])
    def accepts_text(self,text):
        new=terms(text)
        return not any(overlap(new,terms(r['body'].get('text','')))>.72 or difflib.SequenceMatcher(None,text.casefold(),r['body'].get('text','').casefold()).ratio()>.78 for r in self.recent()[:8])
    def metadata(self,record):
        return dict(topic_source=record.get('source','memory'),topic_fingerprints=sorted(fingerprints(topic_terms(record)))[:100],angle=record.get('angle','detail'))
