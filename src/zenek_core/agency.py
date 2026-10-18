"""Zenek's own topic choices, hobbies and durable reflection agenda."""
import hashlib
import json
import math
import time
import uuid

from .privacy import safe_text


def topic_key(subject):return ' '.join(subject.casefold().split())


class Agency:
    def __init__(self,memory):self.memory=memory

    def preferences(self):return self.memory.records('topic_preference',10000)

    def preference(self,body):
        key=body.get('topic_key') or topic_key(body.get('subject',body.get('topic','')))
        identifier='topic:'+hashlib.sha256(key.encode()).hexdigest()
        with self.memory.lock:row=self.memory.db.execute('SELECT body FROM records WHERE id=? AND kind=?',(identifier,'topic_preference')).fetchone()
        return json.loads(row[0]) if row else {}

    def allows(self,body,audience='think'):
        preference=self.preference(body)
        if preference.get('interest') in ('closed','dislike'):return False
        return audience!='share' or preference.get('sharing')!='private'

    def choose(self,topic,interest,sharing,reason):
        topic=safe_text(topic,240).strip();safe_text(reason)
        if not topic or interest not in ('curious','hobby','dislike','closed') or sharing not in ('shared','private'):raise ValueError('Nieprawidłowy wybór tematu')
        key=topic_key(topic);identifier='topic:'+hashlib.sha256(key.encode()).hexdigest()
        body=dict(subject=topic,topic_key=key,interest=interest,sharing=sharing,reason=reason)
        with self.memory.transaction():
            old=self.memory.db.execute('SELECT body FROM records WHERE id=?',(identifier,)).fetchone()
            if old:
                before=json.loads(old[0]);self.memory.db.execute('UPDATE records SET body=?,updated=? WHERE id=?',(json.dumps(body,ensure_ascii=False),time.time(),identifier))
            else:
                before=None;self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'topic_preference',json.dumps(body,ensure_ascii=False),'zenek',1,time.time(),time.time()))
            change=dict(body,before=before,classification='own_topic_choice')
            self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),'agency_change',json.dumps(change,ensure_ascii=False),'zenek',1,time.time(),time.time()))
        if interest in ('curious','hobby'):
            row=next((r for r in self.memory.records('interest',10000) if topic_key(r['body'].get('subject',''))==key),None)
            value=dict(row['body'] if row else {},subject=topic,topic_key=key,sharing=sharing,hobby=interest=='hobby',strength=.8,status='new',last_mentioned=0)
            if row:self.memory.update(row['id'],value)
            else:self.memory.add('interest',value,'own_choice',1)
        return dict(id=identifier,**body)

    def plan(self,topic,mode,delay_minutes,reason):
        topic=safe_text(topic,240).strip();safe_text(reason)
        if not topic or mode not in ('discuss','reflect','research','practice'):raise ValueError('Nieprawidłowy plan')
        if type(delay_minutes) not in (int,float) or not math.isfinite(delay_minutes) or delay_minutes<0:raise ValueError('Nieprawidłowy czas powrotu')
        body=dict(subject=topic,topic_key=topic_key(topic),mode=mode,reason=reason,not_before=time.time()+delay_minutes*60,status='pending',last_mentioned=0)
        if not self.allows(body):return dict(status='retired',reason='Ten temat został zakończony lub jest nielubiany')
        # A private topic can keep developing without creating an invitation.
        kind='open_thread' if mode=='discuss' and self.allows(body,'share') else 'thought_task'
        if kind=='thought_task' and mode=='discuss':body['mode']='reflect'
        identifier=self.memory.add(kind,body,'own_agenda',1)
        return dict(body,id=identifier,status='planned',kind=kind)

    def enqueue(self,message_id):
        message=self.memory.record(message_id)
        if message['kind']!='message' or message['body'].get('role')!='assistant':raise ValueError('Refleksja wymaga własnej wypowiedzi')
        identifier='feedback:'+message_id
        with self.memory.lock:
            self.memory.db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'feedback_task',json.dumps(dict(message_id=message_id,status='pending',not_before=time.time())),'self_feedback',1,time.time(),time.time()));self.memory.db.commit()
        return identifier

    def next_task(self,now=None):
        now=time.time() if now is None else now
        with self.memory.lock:
            ids=self.memory.db.execute("SELECT id FROM records WHERE kind IN ('feedback_task','thought_task') AND json_extract(body,'$.status') IN ('pending','running') AND coalesce(json_extract(body,'$.not_before'),created)<=? ORDER BY coalesce(json_extract(body,'$.not_before'),created),created",(now,)).fetchall()
        for item in ids:
            row=self.memory.record(item[0])
            body=row['body']
            if body.get('status') not in ('pending','running') or body.get('not_before',0)>now:continue
            if row['kind']=='thought_task' and (not self.memory.topic_allowed(body) or not self.allows(body)):
                self.memory.update(row['id'],dict(body,status='retired'));continue
            return row
        return None

    def prompt(self,task):
        body=task['body']
        if task['kind']=='feedback_task':
            try:message=self.memory.record(body['message_id'])
            except ValueError:return None
            context='Twoja wypowiedź, którą już wysłałeś: '+json.dumps(message,ensure_ascii=False)
            context+='\nAktualny stan twoich niedawnych planów (ukończony plan nie jest nadal oczekującą zapowiedzią): '+json.dumps([r['body'] for r in self.memory.records('thought_task',12)],ensure_ascii=False)
        else:
            context='Nadszedł termin realizacji twojego własnego planu: '+json.dumps(body,ensure_ascii=False)
            context+='\nWykonaj teraz wybrany krok, zamiast ponownie go zapowiadać. Dla practice zrób konkretną małą próbę hobby, dla research zbadaj pytanie narzędziami WWW, dla reflect rozwiń własną myśl. Jeśli plan obejmuje notatnik, zapisz rzeczywisty wynik przez WriteNote. Możesz zmienić zdanie, odmówić lub zamknąć temat; zachowaj wtedy ten wybór. Jeśli odkładasz wykonanie, zaplanuj nowy termin przez PlanThought. W końcowej notatce odróżnij wykonany wynik od odłożenia lub rezygnacji.'
        return context+'''\nZatrzymaj się przy własnym wyborze: czy nadal cię to ciekawi? Możesz kontynuować rozmowę, odłożyć temat, poszukać publicznych źródeł, zapisać refleksję, ćwiczyć hobby, rozwinąć coś wyłącznie dla siebie albo zdecydować, że tego nie lubisz lub nie chcesz wracać. Masz narzędzia PlanThought, SetTopicPreference, notatnik, pamięć, rozwój charakteru i WWW. Private oznacza rozwijanie bez spontanicznego mówienia o tym; shared pozwala inicjować rozmowę. Wybrany przez ciebie plan będzie wykonany po podanym czasie. Sama wewnętrzna refleksja nie wymaga dymku do właściciela. Nie musisz wykonywać żadnej dodatkowej akcji. Zwróć krótką jawną notatkę, nie ukryty tok rozumowania: JSON {"reflection":"moja myśl lub SILENCE", "decision":"co wybieram", "reason":"dlaczego"}.'''

    def finish(self,task,text):
        payload=text.strip()
        if payload.startswith('```'):payload=payload.split('\n',1)[-1].rsplit('```',1)[0].strip()
        try:result=json.loads(payload)
        except ValueError:result=dict(reflection=text,decision='reflected',reason='')
        if not isinstance(result,dict):raise ValueError('Nieprawidłowa refleksja')
        reflection=result.get('reflection','SILENCE')
        if not isinstance(reflection,str):raise ValueError('Nieprawidłowy tekst refleksji')
        if reflection.strip()=='SILENCE':reflection=''
        body=dict(text=reflection,decision=result.get('decision','reflected'),reason=result.get('reason',''),task_id=task['id'],message_id=task['body'].get('message_id'),classification='own_reflection')
        identifier='reflection:'+task['id'];now=time.time()
        with self.memory.transaction():
            self.memory.db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?)',(identifier,'self_feedback',json.dumps(body,ensure_ascii=False),'zenek',.7,now,now))
            self.memory.db.execute('UPDATE records SET body=?,updated=? WHERE id=?',(json.dumps(dict(task['body'],status='completed',result_id=identifier,completed_at=now)),now,task['id']))
        return identifier
