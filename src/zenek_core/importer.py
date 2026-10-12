"""Explicit local files -> selected project units -> encrypted delta import.

ZIPs are never extracted. Preview does not import text. Original source and local
correction remain distinct; an updated export never overwrites either silently.
"""
import hashlib
import io
import json
from pathlib import Path
import time
import uuid
import zipfile
from .privacy import safe_text

MAX_BYTES=32*1024*1024

def digest(value):return hashlib.sha256(value.encode() if isinstance(value,str) else value).hexdigest()

def read_source(path):
    path=Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.zip','.json','.md','.txt'):raise ValueError('Wybierz plik ZIP, JSON, Markdown lub tekst')
    with path.open('rb') as stream:data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('Plik przekracza 32 MiB')
    raw=data
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members=[m for m in archive.infolist() if m.filename=='conversations.json']
            if len(members)!=1:raise ValueError('ZIP musi zawierać pojedynczy conversations.json')
            item=members[0]
            if item.file_size>MAX_BYTES or item.file_size/max(1,item.compress_size)>200:raise ValueError('Archiwum przekracza bezpieczny limit')
            data=archive.read(item)
        kind='json'
    else:kind=path.suffix.lower()[1:]
    text=data.decode('utf-8-sig')
    if kind!='json':
        safe_text(text,MAX_BYTES)
        return str(path),digest(raw),[dict(id='document',title=path.name,kind='document',project_hint=None,entries=[dict(id='document',role='document',text=text,at=None)])]
    parsed=json.loads(text)
    conversations=parsed if isinstance(parsed,list) else parsed.get('conversations') if isinstance(parsed,dict) else None
    if not isinstance(conversations,list) or len(conversations)>10000:raise ValueError('Nieobsługiwany eksport rozmów')
    units=[]
    for conversation in conversations:
        if not isinstance(conversation,dict):continue
        unit=str(conversation.get('id') or conversation.get('conversation_id') or '')
        if not unit:raise ValueError('Rozmowa bez trwałego identyfikatora')
        entries=[];mapping=conversation.get('mapping',{})
        if isinstance(mapping,dict):
            for node_id,node in mapping.items():
                if not isinstance(node,dict):continue
                message=node.get('message')
                if not isinstance(message,dict):continue
                role=message.get('author',{}).get('role')
                parts=message.get('content',{}).get('parts',[])
                body='\n'.join(p for p in parts if isinstance(p,str))
                if role in ('user','assistant') and body.strip():entries.append(dict(id=str(message.get('id') or node_id),role=role,text=body,at=message.get('create_time'),parent=node.get('parent')))
        else:raise ValueError('Nieprawidłowa struktura rozmowy')
        units.append(dict(id=unit,title=str(conversation.get('title','Bez tytułu'))[:300],kind='conversation',project_hint=conversation.get('project_id') or conversation.get('gizmo_id'),entries=entries))
    if len({u['id'] for u in units})!=len(units):raise ValueError('Powtarzający się identyfikator rozmowy')
    return str(path),digest(raw),units

class Importer:
    def __init__(self,memory):self.memory=memory
    def preview(self,paths):
        if not isinstance(paths,list) or not 1<=len(paths)<=20 or any(not isinstance(p,str) for p in paths):raise ValueError('Wskaż od 1 do 20 konkretnych plików')
        sources=[];choices=[]
        for path in paths:
            resolved,sha,units=read_source(path);source=digest(resolved)
            if any(s['id']==source for s in sources):continue
            sources.append(dict(id=source,path=resolved,sha=sha))
            for unit in units:
                choices.append(dict(key=source+':'+unit['id'],source_id=source,unit_id=unit['id'],title=unit['title'],kind=unit['kind'],project_hint=unit['project_hint'],messages=len(unit['entries']),path=resolved))
        identifier=str(uuid.uuid4());body=dict(sources=sources,choices=choices,selected=[],cursor=0,added=[],duplicates=0,conflicts=[],rejected=0)
        with self.memory.transaction():self.memory.db.execute('INSERT INTO import_jobs VALUES(?,?,?,?)',(identifier,json.dumps(body),'PREVIEW',time.time()))
        return dict(id=identifier,choices=choices,warning='Zaznacz wyłącznie potwierdzone rozmowy i dokumenty projektu Zenek Kwasiborski. Podgląd nie importuje treści.')
    def job(self,identifier):
        with self.memory.lock:row=self.memory.db.execute('SELECT body,status,updated FROM import_jobs WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Nieznany import')
        return dict(id=identifier,body=json.loads(row[0]),status=row[1],updated=row[2])
    def latest(self):
        with self.memory.lock:row=self.memory.db.execute('SELECT id FROM import_jobs ORDER BY updated DESC LIMIT 1').fetchone()
        return self.job(row[0]) if row else dict(status='IMPORT_PENDING')
    def apply(self,identifier,selected,cancel,confirmed=False):
        job=self.job(identifier);body=job['body']
        if not confirmed or not isinstance(selected,list) or not selected or not set(selected)<=set(c['key'] for c in body['choices']):raise ValueError('Potwierdź przynależność zaznaczonych źródeł do projektu')
        if job['status'] not in ('PREVIEW','PAUSED','APPLYING'):raise ValueError('Import nie jest gotowy do aktualizacji')
        if job['status']!='PREVIEW' and selected!=body['selected']:raise ValueError('Wznowienie zachowuje zatwierdzony wybór')
        body['selected']=selected;entries=[]
        for source in body['sources']:
            _,sha,units=read_source(source['path'])
            if sha!=source['sha']:raise ValueError('Źródło zmieniło się po podglądzie; wybierz nowy podgląd')
            for unit in units:
                if source['id']+':'+unit['id'] in selected:
                    for entry in unit['entries']:entries.append((source,unit,entry))
        # Each entry and its cursor advance commit together. Restart resumes only
        # after another explicit Apply/Resume; there is no watcher or startup task.
        for index in range(body['cursor'],len(entries)):
            if cancel.is_set():self.save(identifier,body,'PAUSED');return self.job(identifier)
            source,unit,entry=entries[index]
            with self.memory.transaction():
                self.memory.db.execute('INSERT INTO import_sources VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET hash=excluded.hash',(source['id'],source['path'],source['sha'],time.time()))
                key=digest(entry['role']+'\0'+entry['text'].replace('\r\n','\n').strip());content_hash=digest(entry['text'])
                old=self.memory.db.execute('SELECT fingerprint,content_hash FROM import_refs WHERE source_id=? AND unit_id=? AND entry_id=?',(source['id'],unit['id'],entry['id'])).fetchone()
                if old and old[1]!=content_hash:
                    body['conflicts'].append(dict(source_id=source['id'],unit_id=unit['id'],entry_id=entry['id'],reason='Zmiana oryginału; zachowano dotychczasowy rekord i korekty'))
                elif old:body['duplicates']+=1
                else:
                    try:safe_text(entry['text'],100000)
                    except ValueError:body['rejected']+=1
                    else:
                        existing=self.memory.db.execute('SELECT record_id FROM import_entries WHERE fingerprint=?',(key,)).fetchone()
                        if existing:
                            record_id=existing[0];body['duplicates']+=1
                        else:
                            record_id=str(uuid.uuid4());now=time.time()
                            record=dict(role=entry['role'],text=entry['text'],classification='original',source_id=source['id'],unit_id=unit['id'],entry_id=entry['id'],source_time=entry['at'],project='Zenek Kwasiborski',document=unit['kind']=='document')
                            self.memory.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?)',(record_id,'import_original',json.dumps(record,ensure_ascii=False),'owner_selected_import',1,now,now))
                            self.memory.db.execute('INSERT INTO import_entries VALUES(?,?,?)',(key,record_id,content_hash));body['added'].append(record_id)
                        self.memory.db.execute('INSERT INTO import_refs VALUES(?,?,?,?,?)',(source['id'],unit['id'],entry['id'],key,content_hash))
                body['cursor']=index+1
                self.memory.db.execute('UPDATE import_jobs SET body=?,status=?,updated=? WHERE id=?',(json.dumps(body),'APPLYING',time.time(),identifier))
        self.save(identifier,body,'COMPLETE')
        return self.job(identifier)
    def save(self,identifier,body,status):
        with self.memory.transaction():self.memory.db.execute('UPDATE import_jobs SET body=?,status=?,updated=? WHERE id=?',(json.dumps(body),status,time.time(),identifier))
    def references(self,record_id):
        with self.memory.lock:rows=self.memory.db.execute('SELECT r.source_id,s.path,r.unit_id,r.entry_id FROM import_refs r JOIN import_sources s ON s.id=r.source_id JOIN import_entries e ON e.fingerprint=r.fingerprint WHERE e.record_id=?',(record_id,)).fetchall()
        return [dict(source_id=r[0],path=r[1],unit_id=r[2],entry_id=r[3]) for r in rows]
