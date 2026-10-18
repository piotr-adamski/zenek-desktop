"""Read models for the native notebook, conversation and development views."""
import json
import re

from .agency import Agency
from .notebook import Notebook
from .personality import Personality
from .privacy import safe_text


def title(text,fallback):
    return next((line.lstrip('# ').strip() for line in text.splitlines() if line.strip()),fallback)[:180]


def links(text):return list(dict.fromkeys(url.rstrip(').,;') for url in re.findall(r'https://[^\s<>"\[\]{}]+',text)))


class Workspace:
    def __init__(self,memory,notebook=None):self.memory=memory;self.notebook=notebook or Notebook()

    def notes(self,query=''):
        query=safe_text(query,500).casefold();rows=[]
        for entry in self.notebook.list():
            try:text=self.notebook.read(entry['path'])
            except ValueError:continue
            if query and query not in (entry['path']+' '+text).casefold():continue
            paragraphs=[p.strip() for p in text.split('\n\n') if p.strip() and not p.lstrip().startswith('#')]
            rows.append(dict(entry,title=title(text,entry['path']),preview=(paragraphs[0] if paragraphs else text)[:220]))
        return rows

    def note(self,path):
        text=self.notebook.read(path)
        return dict(path=path,text=text,title=title(text,path),sources=links(text))

    def conversation(self,query='',before=None,limit=40):
        query=safe_text(query,500);limit=min(100,max(1,int(limit)))
        args=[];where="kind='message'"
        if query:
            # SQLite lower() is ASCII-only; use Python casefold for Polish too.
            where+=' AND instr(zenek_casefold(json_extract(body,\'$.text\')),?)>0';args.append(query.casefold())
        if before:
            anchor=self.memory.record(before)
            if anchor['kind']!='message':raise ValueError('To nie jest wiadomość')
            where+=' AND (created<? OR (created=? AND id<?))';args.extend([anchor['created'],anchor['created'],anchor['id']])
        with self.memory.lock:
            self.memory.db.create_function('zenek_casefold',1,lambda value:str(value or '').casefold())
            rows=self.memory.db.execute('SELECT id FROM records WHERE '+where+' ORDER BY created DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
        records=[self.memory.record(row[0]) for row in rows[:limit]]
        paths=[entry['path'] for entry in self.notebook.list()]
        for row in records:
            row['sources']=links(row['body'].get('text',''))
            row['note_paths']=[path for path in paths if path in row['body'].get('text','') or path==row['body'].get('note_path')]
        return dict(messages=list(reversed(records)),has_more=len(rows)>limit,before=records[-1]['id'] if records else None)

    def anchor(self,identifier):
        row=self.memory.record(identifier)
        if row['kind']!='message':raise ValueError('Powrót wymaga wiadomości z rozmowy')
        user_id=row['id'] if row['body'].get('role')=='user' else row['body'].get('in_reply_to')
        exchange=[row]
        if user_id:
            with self.memory.lock:
                ids=self.memory.db.execute("SELECT id FROM records WHERE kind='message' AND (id=? OR json_extract(body,'$.in_reply_to')=?) ORDER BY created,id",(user_id,user_id)).fetchall()
            exchange=[self.memory.record(item[0]) for item in ids]
        return dict(id=row['id'],body=row['body'],created=row['created'],exchange=exchange)

    def development(self,before=None,limit=40):
        labels={'personality_evolution':'Zmiana charakteru','self_evolution':'Rozwijam myśl o sobie','self_feedback':'Moja refleksja po wypowiedzi','agency_change':'Własny wybór tematu','knowledge':'Nowa wiedza','notebook_entry':'Zapisek w notatniku','interest':'Zainteresowanie','code_request':'Prośba o zmianę kodu','thought_task':'Mój plan dla siebie','open_thread':'Wątek do rozmowy'}
        rows=[];history={v['version']:v for v in Personality(self.memory).history()}
        limit=min(100,max(1,int(limit)));args=list(labels);where='kind IN ('+','.join('?' for _ in labels)+") AND (kind!='open_thread' OR source='own_agenda')"
        if before:
            anchor=self.memory.record(before);where+=' AND (updated<? OR (updated=? AND id<?))';args.extend([anchor['updated'],anchor['updated'],anchor['id']])
        with self.memory.lock:ids=self.memory.db.execute('SELECT id FROM records WHERE '+where+' ORDER BY updated DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
        for item in ids[:limit]:
            record=self.memory.record(item[0]);kind=record['kind'];label=labels[kind]
            body=record['body'];value=dict(id=record['id'],kind=kind,label=label,at=record['updated'],title=body.get('subject') or body.get('domain') or body.get('path') or label,text=body.get('rationale') or body.get('reason') or body.get('text') or '',sources=[])
            if kind=='self_feedback':value['title']=str(body.get('decision') or label);value['text']=body.get('text','')+'\n\n'+str(body.get('reason',''))
            if kind=='personality_evolution':
                old=history.get(body['before_version'],{});new=history.get(body['version'],{})
                value.update(before=old.get('prompt',''),after=new.get('prompt',''),traits={k:[old.get('traits',{}).get(k),v] for k,v in new.get('traits',{}).items() if old.get('traits',{}).get(k)!=v})
            if kind=='self_evolution':value.update(before=body.get('before',''),after=body.get('text',''))
            if kind=='agency_change':value.update(interest=body.get('interest'),sharing=body.get('sharing'))
            if body.get('path'):value['note_path']=body['path']
            for ref in body.get('source_ids',[]):
                try:
                    source=self.memory.record(ref);value['sources']+=links(json.dumps(source['body'],ensure_ascii=False))
                except ValueError:pass
            rows.append(value)
        return dict(events=rows,has_more=len(ids)>limit,before=rows[-1]['id'] if rows else None,preferences=Agency(self.memory).preferences(),personality=Personality(self.memory).active())
