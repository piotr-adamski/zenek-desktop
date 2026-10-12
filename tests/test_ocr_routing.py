import threading
import time
from types import SimpleNamespace
from PIL import Image,ImageDraw
from zenek_core.main import Core
from zenek_core.memory import Memory
from zenek_core.redaction import Redactor

def test_text_screen_uses_safe_local_ocr_without_visual_request(tmp_path):
    m=Memory(tmp_path/'db','ab'*32)
    core=Core.__new__(Core);core.memory=m;core.behavior=SimpleNamespace();core.capture=SimpleNamespace(state='ACTIVE',generation=7)
    lines=[]
    for index,text in enumerate(['Wlasny syntetyczny dokument','Bezpieczna tresc OCR','password: PRIVATE_MUST_NEVER_RETURN']):
        lines.append(dict(level='5',text=text,left='20',top=str(30+index*40),width='300',height='20',block_num='1',par_num='1',line_num=str(index),conf='90'))
    # Text in a high-risk panel must not enter OCR context.
    lines.append(dict(level='5',text='MASKED_PRIVATE_TEXT',left='650',top='40',width='160',height='20',block_num='2',par_num='1',line_num='0',conf='95'))
    core.redactor=Redactor(ocr=lambda _:lines);core.jobs={};core.redacted_preview=None;core.screen_context=None;core.preview_lock=threading.RLock();core.vision_unreported=False
    core.capture_permitted=lambda:True;core.window_metadata=[dict(app='gedit',title='Synthetic',rect=[0,0,600,500]),dict(app='unknown',title='vault-dashboard',rect=[620,0,300,500])];core.metadata_updated=time.monotonic()
    core.emit_state=lambda:None;core.worker=lambda name,fn:fn(threading.Event())
    core.provider=SimpleNamespace(infer=lambda *args:(_ for _ in ()).throw(AssertionError('Text-only screen must not upload an image')))
    core.frame(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),7)
    assert core.last_screen_analysis['mode']=='OCR' and core.last_screen_analysis['graphics_percent']==0
    assert core.screen_context['classification']=='local_ocr'
    assert core.screen_context['text']=='Wlasny syntetyczny dokument\nBezpieczna tresc OCR'
    record=m.records('observation_memory')[0]
    assert record['source']=='desktop_ocr' and 'PRIVATE' not in str(record['body'])
    m.close()

def test_large_graphic_is_detected_but_uniform_background_is_not():
    detector=Redactor(ocr=lambda _:[])
    image=Image.new('RGB',(640,480),'white');draw=ImageDraw.Draw(image)
    for y in range(0,480,16):
        for x in range(0,640,16):draw.rectangle((x,y,x+8,y+8),fill=(x%256,y%256,160))
    result,_,_=detector.process(image,dict(position=[0,0],size=[640,480]),[dict(app='org.zenek.Synthetic',title='Graphic',rect=[0,0,640,480])],True)
    assert detector.last_analysis['graphics_fraction']>.8;result.close()
    result,_,_=detector.process(Image.new('RGB',(640,480),'blue'),dict(position=[0,0],size=[640,480]),[dict(app='gedit',title='Blank',rect=[0,0,640,480])],True)
    assert detector.last_analysis==dict(text='',graphics_fraction=0,ocr_lines=0,high_risk_windows=0,low_risk_windows=1);result.close();detector.reset()
    assert detector.last_analysis is None

def test_large_flat_colored_chart_is_not_mistaken_for_empty_background():
    detector=Redactor(ocr=lambda _:[])
    image=Image.new('RGB',(640,480),'white');ImageDraw.Draw(image).rectangle((0,0,300,479),fill='red')
    result,_,_=detector.process(image,dict(position=[0,0],size=[640,480]),[dict(app='org.zenek.Synthetic',title='Synthetic flat chart',rect=[0,0,640,480])],True)
    assert detector.last_analysis['graphics_fraction']>=.4;result.close()
