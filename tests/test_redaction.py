import io
from PIL import Image,ImageDraw
import pytest
from zenek_core.redaction import Redactor,FrameRejected

def row(text,x,y,w,h):
    return dict(level='5',text=text,left=str(x),top=str(y),width=str(w),height=str(h),block_num='1',par_num='1',line_num='1')

def test_mask_is_physically_opaque_before_encoding():
    image=Image.new('RGB',(1000,800),'white');ImageDraw.Draw(image).text((50,60),'SYNTHETIC API KEY',fill='red')
    detector=Redactor(ocr=lambda image:[row('token: SYNTHETIC123',50,60,180,20)])
    result,changed,count=detector.process(image,dict(position=[0,0],size=[1000,800]),[dict(title='Synthetic note',app='org.gnome.TextEditor',rect=[0,0,600,500])],True)
    encoded=io.BytesIO();result.save(encoded,format='PNG');readback=Image.open(io.BytesIO(encoded.getvalue()))
    assert readback.getpixel((55,65))==(0,0,0)
    assert readback.getpixel((800,600))==(255,255,255)
    assert changed and count==1
    result.close()

def test_detector_error_unknown_source_and_sensitive_window_fail_closed():
    detector=Redactor(ocr=lambda _:(_ for _ in ()).throw(RuntimeError('synthetic error')))
    with pytest.raises(FrameRejected):detector.process(Image.new('RGB',(1000,800)),dict(position=[0,0],size=[1000,800]),[dict(title='note',app='gedit',rect=[0,0,500,500])],True)
    assert detector.rejected==1
    detector=Redactor(ocr=lambda _:[])
    with pytest.raises(FrameRejected):detector.process(Image.new('RGB',(1000,800)),{},[],False)
    with pytest.raises(FrameRejected):detector.process(Image.new('RGB',(1000,800)),dict(position=[0,0],size=[1000,800]),[dict(title='Password Manager',app='unknown',rect=[0,0,1000,800])],True)

def test_raw_image_never_returns_and_duplicate_has_no_new_change():
    detector=Redactor(ocr=lambda _:[])
    args=(dict(position=[0,0],size=[1000,800]),[dict(title='Note',app='gedit',rect=[0,0,600,500])],True)
    for i in range(2):
        raw=Image.new('RGB',(1000,800),'white');result,changed,_=detector.process(raw,*args)
        assert changed==(i==0)
        with pytest.raises(ValueError):raw.getpixel((0,0))
        result.close()

@pytest.mark.parametrize('title,app',[
    ('Konto bankowe','firefox'),('mBank','firefox'),('iPKO','chromium'),('ING Bank','firefox'),
    ('Urząd Skarbowy','firefox'),('e-Urząd','chromium'),('podatki.gov.pl','firefox'),
    ('uslugi.gov.pl','firefox'),('eZUS','firefox'),('PUE ZUS','firefox'),
    ('Cloudflare Dashboard','chromium'),('Hetzner Console','firefox'),('AWS Console','firefox'),
    ('Google Cloud','firefox'),('Azure Portal','firefox'),('vault-dashboard','chromium'),
    ('Hasła','com.bitwarden.desktop'),
])
def test_high_risk_window_is_masked_and_excluded_from_ocr(title,app):
    detector=Redactor(ocr=lambda _:[row('PRIVATE_WINDOW_CONTENT',30,200,200,20)])
    result,_,count=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title=title,app=app,rect=[0,0,600,500])],True)
    assert count and result.getpixel((100,250))==(0,0,0)
    assert detector.last_analysis['text']=='' and detector.last_analysis['high_risk_windows']==1
    result.close()

@pytest.mark.parametrize('title,app',[
    ('Gmail — wiadomość o ZUS','firefox'),('Proton Mail','firefox'),('Outlook','chromium'),
    ('Facebook','firefox'),('LinkedIn','chromium'),('ChatGPT','chromium'),
    ('bash — AWS','org.gnome.Ptyxis'),('ssh vault-dashboard','org.gnome.Terminal'),
    ('Wiadomość od banku','thunderbird'),('Dowolne nowe okno','unknown'),
])
def test_low_risk_content_is_available_without_blanket_mask(title,app):
    detector=Redactor(ocr=lambda _:[row('ORDINARY_VISIBLE_CONTENT',30,200,200,20)])
    result,_,count=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title=title,app=app,rect=[0,0,600,500])],True)
    assert count==0 and result.getpixel((100,250))==(255,255,255)
    assert detector.last_analysis['text']=='ORDINARY_VISIBLE_CONTENT'
    assert detector.last_analysis['high_risk_windows']==0
    result.close()

def test_normal_bash_tokenizer_output_is_not_a_credential():
    detector=Redactor(ocr=lambda _:[row('Running tokenizer successfully',30,200,250,20)])
    result,_,count=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title='bash',app='org.gnome.Terminal',rect=[0,0,600,500])],True)
    assert count==0 and detector.last_analysis['text']=='Running tokenizer successfully'
    result.close()

def test_browser_visible_domain_is_high_but_email_body_reference_is_low():
    for top,high in [(40,True),(240,False)]:
        detector=Redactor(ocr=lambda _:[row('console.aws.amazon.com',30,top,250,20)])
        result,_,count=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title='Gmail',app='firefox',rect=[0,0,600,500])],True)
        assert bool(count)==high and detector.last_analysis['high_risk_windows']==int(high)
        result.close()

def test_terminal_credential_field_masks_separated_value_without_hiding_window():
    detector=Redactor(ocr=lambda _:[row('token',30,100,80,20)])
    result,_,_=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title='bash',app='org.gnome.Terminal',rect=[0,0,600,500])],True)
    assert result.getpixel((550,110))==(0,0,0) and result.getpixel((100,300))==(255,255,255)
    assert detector.last_analysis['high_risk_windows']==0 and detector.last_analysis['text']==''
    result.close()

@pytest.mark.parametrize('closed',[True,False])
def test_visible_private_key_payload_is_masked_in_low_risk_terminal(closed):
    rows=[row('-----BEGIN OPENSSH PRIVATE KEY-----',30,80,300,20),row('SYNTHETIC_KEY_PAYLOAD',30,150,250,20)]
    if closed:rows.append(row('-----END OPENSSH PRIVATE KEY-----',30,230,300,20))
    for index,value in enumerate(rows):value['line_num']=str(index)
    detector=Redactor(ocr=lambda _:rows)
    result,_,_=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title='bash',app='org.gnome.Terminal',rect=[0,0,600,500])],True)
    assert result.getpixel((200,160))==(0,0,0) and 'PAYLOAD' not in detector.last_analysis['text']
    assert detector.last_analysis['high_risk_windows']==0
    assert result.getpixel((100,400))==((255,255,255) if closed else (0,0,0))
    result.close()

def test_overlapping_masks_count_unique_pixels_and_offscreen_window_is_ignored():
    detector=Redactor(ocr=lambda _:[row('token',30,100,80,20)])
    result,_,_=detector.process(Image.new('RGB',(1000,800),'white'),dict(position=[0,0],size=[1000,800]),[dict(title='AWS',app='firefox',rect=[0,0,850,800]),dict(title='note',app='unknown',rect=[2000,0,600,500])],True)
    assert result.getpixel((30,100))==(0,0,0)
    result.close()
