import base64
import hashlib
import io
import threading
import time
from types import SimpleNamespace
from PIL import Image,ImageDraw
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.redaction import Redactor

def test_preview_is_exact_redacted_payload_and_kill_clears_it(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);m.patch({'observation_memory':False,'vision':dict(model_id='synthetic',reasoning_effort='medium',status='READY')},m.settings()[0]);m.profile_status('vision','READY')
    core=Core.__new__(Core);core.memory=m;core.behavior=SimpleNamespace();core.capture=SimpleNamespace(state='ACTIVE',generation=7)
    core.redactor=Redactor(ocr=lambda image:[dict(level='5',text='API KEY: SYNTHETIC',left='50',top='60',width='200',height='20',block_num='1',par_num='1',line_num='1')])
    core.jobs={};core.redacted_preview=None;core.preview_lock=threading.RLock();core.vision_unreported=False
    core.capture_permitted=lambda:True;core.window_metadata=[dict(app='gedit',title='Synthetic',rect=[0,0,600,500])];core.metadata_updated=time.monotonic()
    core.emit_state=lambda:None;core.worker=lambda name,fn:fn(threading.Event())
    captured=[]
    def infer(profile,inputs,*args):captured.append(inputs[0]['content'][1]['image_url']);return 'Niesekretny syntetyczny opis'
    core.provider=SimpleNamespace(infer=infer)
    scene=Image.new('RGB',(1000,800),'white');draw=ImageDraw.Draw(scene)
    for y in range(120,800,16):
        for x in range(0,1000,16):draw.rectangle((x,y,x+8,y+8),fill=(x%256,y%256,160))
    core.frame(scene,dict(position=[0,0],size=[1000,800]),7)
    preview=core.handle('GetRedactedPreview',{});png=base64.b64decode(preview['png'])
    assert png==base64.b64decode(captured[0].split(',',1)[1])
    assert hashlib.sha256(png).hexdigest()==core.last_vision_request['png_sha256'] and core.last_vision_request['completed']
    assert Image.open(io.BytesIO(png)).getpixel((55,65))==(0,0,0)
    assert core.screen_context['text']=='Niesekretny syntetyczny opis' and not m.records('observation_memory')
    core.capture.state='OFF';core.capture.generation+=1;core.capture_changed()
    assert core.redacted_preview is None and core.screen_context is None and core.redactor.previous is None and core.handle('GetRedactedPreview',{}) is None
    m.close()
