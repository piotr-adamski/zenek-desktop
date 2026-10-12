"""Owner risk policy and local OCR masking. Invalid source/detector => discard."""
import csv
import hashlib
import io
import re
import subprocess
import threading
from collections import Counter
from PIL import Image,ImageDraw,ImageChops,ImageStat
from .privacy import SECRET

SECRET_LABELS=re.compile(r'\b(?:password|has[lł]o|passphrase|token|secret|api[ _-]?key|bearer|authorization|credential|private[ _-]?key|access[ _-]?key|session[ _-]?(?:id|cookie)|kod[ _-]?(?:otp|sms|jednorazowy|weryfikacyjny)|otp|2fa)\b',re.I)
PRIVATE_KEY_BEGIN=re.compile(r'BEGIN\s+(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED)\s+)?PRIVATE\s+KEY',re.I)
PRIVATE_KEY_END=re.compile(r'END\s+(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED)\s+)?PRIVATE\s+KEY',re.I)
HIGH_DOMAIN=re.compile(r'(?:\bgov\.[a-z]{2,}\b|\.gov(?:\.[a-z]{2,})?\b|\b(?:zus\.pl|podatki\.gov\.pl|mbank\.pl|ipko\.pl|pko(?:bp)?\.pl|pekao(?:24)?\.pl|ing\.pl|santander\.pl|bankmillennium\.pl|aliorbank\.pl|bnpparibas\.pl|credit-agricole\.pl|aws\.amazon\.com|amazonaws\.com|cloud\.google\.com|firebase\.google\.com|azure\.com|azure\.microsoft\.com|cloudflare\.com|hetzner\.com|digitalocean\.com|ovh(?:cloud)?\.com|linode\.com|vultr\.com|scaleway\.com|upcloud\.com|vercel\.com|supabase\.com|neon\.tech|fly\.io|railway\.(?:com|app)|render\.com)\b|\bvault[-_.](?:dashboard|ui|panel|web)\b)',re.I)
HIGH_TITLE=re.compile(r'\b(?:konto[ -]+bankowe|bankowo[sś][cć]|banking|mBank|iPKO|PKO(?:[ -]+BP)?|Pekao|Santander|Millennium|Alior|BNP[ -]+Paribas|Credit[ -]+Agricole|e[- ]?urz[aą]d|urz[aą]d[ -]+skarbowy|podatki\.gov|ZUS|eZUS|PUE[ -]?ZUS|AWS|Amazon[ -]+Web[ -]+Services|Google[ -]+Cloud|GCP|Azure|Cloudflare|Hetzner|DigitalOcean|OVH(?:cloud)?|Linode|Vultr|Scaleway|UpCloud|Vercel|Supabase|Neon[ -]+Console|Firebase[ -]+Console|Vault[-_ ]*(?:Dashboard|Panel|UI)|HashiCorp[ -]+Vault|Password[ -]+Manager|Mened[zż]er[ -]+hase[lł])\b',re.I)
SECRET_MANAGER_APP=re.compile(r'bitwarden|keepass|1password|onepassword|seahorse|keyring|vault-dashboard',re.I)
LOW_APP=re.compile(r'(?:terminal|ptyxis|konsole|kitty|alacritty|wezterm|xterm|terminator|tilix|thunderbird|protonmail|geary|evolution|org\.gnome\.mail)',re.I)
LOW_TITLE=re.compile(r'\b(?:Gmail|Proton[ -]?Mail|Outlook|Thunderbird|Facebook|LinkedIn|Instagram|Messenger|WhatsApp|Discord|ChatGPT)\b',re.I)
BROWSER_APP=re.compile(r'firefox|chrom(?:e|ium)|msedge|brave|vivaldi|opera|epiphany|browser',re.I)

def high_risk_window(window):
    app=window.get('app','');title=window.get('title','')
    if SECRET_MANAGER_APP.search(app):return True
    if LOW_APP.search(app) or LOW_TITLE.search(title):return False
    return bool(HIGH_DOMAIN.search(title+' '+app) or HIGH_TITLE.search(title) or re.search(r'\b(?:bank|ING|Revolut|Wise|bankowo[sś][cć][ -]+internetowa)\b',title,re.I))

class FrameRejected(ValueError):pass

def subtract(rect,cover):
    x1,y1,x2,y2=rect;a,b,c,d=cover
    left=max(x1,a);top=max(y1,b);right=min(x2,c);bottom=min(y2,d)
    if left>=right or top>=bottom:return [rect]
    pieces=[(x1,y1,x2,top),(x1,bottom,x2,y2),(x1,top,left,bottom),(right,top,x2,bottom)]
    return [r for r in pieces if r[0]<r[2] and r[1]<r[3]]

class Redactor:
    def __init__(self,ocr=None):self.previous=None;self.rejected=0;self.last_reason='';self.ocr=ocr or self.local_ocr;self.ocr_process=None;self.lock=threading.RLock();self.last_analysis=None
    def local_ocr(self,image):
        data=io.BytesIO();image.save(data,format='PNG')
        process=subprocess.Popen(['tesseract','stdin','stdout','-l','eng+pol','--psm','11','tsv'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.ocr_process=process
        try:
            output,_=process.communicate(data.getvalue(),timeout=12)
            if process.returncode:raise FrameRejected('OCR przerwany lub niedostępny')
            return list(csv.DictReader(io.StringIO(output.decode()),delimiter='\t'))
        except subprocess.TimeoutExpired:
            process.kill();process.communicate();raise FrameRejected('OCR timeout') from None
        finally:
            self.ocr_process=None;data.close()
    def reset(self):
        process=self.ocr_process
        if process and process.poll() is None:
            try:process.kill()
            except ProcessLookupError:pass
        with self.lock:
            if self.previous:self.previous.close();self.previous=None
            self.last_analysis=None
    def process(self,image,stream,windows,metadata_fresh):
        try:
            self.last_analysis=None
            if not metadata_fresh or not windows or 'position' not in stream or 'size' not in stream:raise FrameRejected('Brak wiarygodnego źródła/metadanych')
            ox,oy=stream['position'];logical_w,logical_h=stream['size']
            if logical_w<=0 or logical_h<=0:raise FrameRejected('Nieprawidłowa geometria')
            sx=image.width/logical_w;sy=image.height/logical_h
            redacted=image.copy();draw=ImageDraw.Draw(redacted);masks=[];covers=[];window_regions=[]
            for window in windows:
                if not isinstance(window,dict) or len(window.get('rect',[]))!=4:raise FrameRejected('Nieprawidłowe metadane okna')
                title=window.get('title','');app=window.get('app','')
                x,y,w,h=window['rect'];rect=(int((x-ox)*sx),int((y-oy)*sy),int((x+w-ox)*sx),int((y+h-oy)*sy))
                clipped=(max(0,rect[0]),max(0,rect[1]),min(image.width,rect[2]),min(image.height,rect[3]))
                exposed=[clipped] if clipped[0]<clipped[2] and clipped[1]<clipped[3] else []
                for cover in covers:exposed=[piece for part in exposed for piece in subtract(part,cover)]
                if not exposed:continue
                window_regions.append(dict(window=window,rect=rect,exposed=exposed,high=high_risk_window(window)))
                if high_risk_window(window):
                    box=(rect[0]-12,rect[1]-12,rect[2]+12,rect[3]+12)
                    if box[2]>0 and box[3]>0 and box[0]<image.width and box[1]<image.height:
                        box=(max(0,box[0]),max(0,box[1]),min(image.width-1,box[2]),min(image.height-1,box[3]))
                        exposed=[box]
                        for cover in covers:exposed=[piece for part in exposed for piece in subtract(part,cover)]
                        masks.extend(exposed)
                # Only our own opaque GTK windows can exclude hidden underlying pixels.
                if window.get('opaque') is True and app.startswith('org.zenek.'):covers.append(rect)
            # OCR runs locally on RAM data only, before external encoding.
            rows=self.ocr(image)
            lines={}
            for row in rows:
                if int(row.get('level','0'))!=5 or not row.get('text','').strip():continue
                key=tuple(row.get(k) for k in ['block_num','par_num','line_num'])
                lines.setdefault(key,[]).append(row)
            key_blocks=[]
            for line in sorted(lines.values(),key=lambda line:min(int(r['top']) for r in line)):
                text=' '.join(r['text'] for r in line)
                left=min(int(r['left']) for r in line);top=min(int(r['top']) for r in line)
                right=max(int(r['left'])+int(r['width']) for r in line);bottom=max(int(r['top'])+int(r['height']) for r in line)
                containing=[r['rect'] for r in window_regions if r['rect'][0]<=left<r['rect'][2] and r['rect'][1]<=top<r['rect'][3]]
                bounds=(min((r[0] for r in containing),default=0),max((r[2] for r in containing),default=image.width),max((r[3] for r in containing),default=image.height))
                if PRIVATE_KEY_BEGIN.search(text):key_blocks.append([bounds,top-15,None])
                if PRIVATE_KEY_END.search(text):
                    for block in key_blocks:
                        if block[0]==bounds and block[2] is None:block[2]=bottom+15
                for region in window_regions:
                    window=region['window'];rect=region['rect']
                    in_header=rect[0]<=left<rect[2] and rect[1]<=top<rect[1]+min(180,(rect[3]-rect[1])*.25)
                    if not region['high'] and BROWSER_APP.search(window.get('app','')) and in_header and (HIGH_DOMAIN.search(text) or not LOW_TITLE.search(window.get('title','')) and HIGH_TITLE.search(text)):
                        masks.extend(region['exposed']);region['high']=True
                if SECRET_LABELS.search(text) or SECRET.search(text):
                    try:
                        # Include the complete field/value across its window, not only its label.
                        band_left=min((r[0] for r in containing),default=left-20);band_right=max((r[2] for r in containing),default=right+20)
                        masks.append((max(0,band_left),max(0,top-15),min(image.width-1,band_right),min(image.height-1,bottom+15)))
                    except Exception:raise FrameRejected('Niepewne granice sekretu')
            for (left,right,end),start,stop in key_blocks:
                masks.append((max(0,left),max(0,start),min(image.width-1,right),min(image.height-1,stop if stop is not None else end)))
            coverage=Image.new('L',image.size,0);coverage_draw=ImageDraw.Draw(coverage)
            for box in masks:
                draw.rectangle(box,fill=(0,0,0));coverage_draw.rectangle(box,fill=255)
            masked_pixels=coverage.histogram()[255];coverage.close()
            if masked_pixels>image.width*image.height*.9:raise FrameRejected('Zbyt duży obszar ryzyka')
            thumb=redacted.resize((64,40)).convert('L')
            with self.lock:
                changed=self.previous is None or ImageStat.Stat(ImageChops.difference(thumb,self.previous)).mean[0]>3
                if self.previous:self.previous.close()
                self.previous=thumb
            self.last_reason=''
            self.last_analysis=self.analyze(redacted,lines,masks)
            self.last_analysis['high_risk_windows']=sum(r['high'] for r in window_regions)
            self.last_analysis['low_risk_windows']=sum(not r['high'] for r in window_regions)
            return redacted,changed,len(masks)
        except Exception as e:
            self.rejected+=1
            self.last_reason=str(e) if isinstance(e,FrameRejected) else 'detektor niedostępny'
            if 'redacted' in locals():redacted.close()
            raise FrameRejected('Klatka odrzucona: '+(str(e) if isinstance(e,FrameRejected) else 'detektor niedostępny')) from None
        finally:image.close()

    def analyze(self,image,lines,masks):
        """Estimate graphical regions from safe OCR, texture and background contrast."""
        text_map=Image.new('L',image.size,0);hidden=Image.new('L',image.size,0)
        text_draw=ImageDraw.Draw(text_map);hidden_draw=ImageDraw.Draw(hidden);safe_lines=[]
        for box in masks:hidden_draw.rectangle(box,fill=255)
        small=image.resize((64,40),Image.Resampling.NEAREST);small_hidden=hidden.resize((64,40),Image.Resampling.NEAREST)
        colors=Counter(tuple(c//32 for c in small.getpixel((x,y))) for y in range(40) for x in range(64) if small_hidden.getpixel((x,y))==0)
        background=tuple(c*32+16 for c in colors.most_common(1)[0][0]) if colors else (0,0,0)
        small.close();small_hidden.close()
        for line in lines.values():
            text=' '.join(r['text'] for r in line)
            if SECRET_LABELS.search(text) or SECRET.search(text):continue
            box=(min(int(r['left']) for r in line),min(int(r['top']) for r in line),max(int(r['left'])+int(r['width']) for r in line),max(int(r['top'])+int(r['height']) for r in line))
            if any(box[0]<b[2] and box[2]>b[0] and box[1]<b[3] and box[3]>b[1] for b in masks):continue
            margin=max(2,(box[3]-box[1])//2)
            text_draw.rectangle((box[0],box[1]-margin,box[2],box[3]+margin),fill=255)
            if any(float(r.get('conf','100'))<40 for r in line):continue
            safe_lines.append(text)
        graphic=eligible=0
        for y in range(0,image.height,64):
            for x in range(0,image.width,64):
                box=(x,y,min(x+64,image.width),min(y+64,image.height))
                hidden_tile=hidden.crop(box);masked=ImageStat.Stat(hidden_tile).mean[0]/255;hidden_tile.close()
                if masked>0:continue # Mask edges must never count as graphical content.
                area=(box[2]-box[0])*(box[3]-box[1]);eligible+=area
                tile=image.crop(box);stats=ImageStat.Stat(tile);variation=max(stats.stddev);color_distance=max(abs(mean-bg) for mean,bg in zip(stats.mean,background));tile.close()
                text_tile=text_map.crop(box);text_share=ImageStat.Stat(text_tile).mean[0]/255;text_tile.close()
                if (variation>8 or color_distance>35) and text_share<.05:graphic+=area
        text_map.close();hidden.close()
        return dict(text='\n'.join(safe_lines)[:8000],graphics_fraction=graphic/eligible if eligible else 0,ocr_lines=len(safe_lines))
