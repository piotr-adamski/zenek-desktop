"""Copy owner's already finalized graphics byte-for-byte. No generation/editing."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

source=Path(sys.argv[1]).resolve()
root=Path(__file__).resolve().parents[1]
target=root/'gnome-extension/zenek@brillnet/assets/zenn'
metadata=json.loads((source/'outputs/ZENN-pet.json').read_text())
sheet=source/'outputs/ZENN-spritesheet.png'
digest=hashlib.sha256(sheet.read_bytes()).hexdigest()
if metadata['name']!='ZENN' or metadata['sha256']!=digest:raise ValueError('ZENN source integrity mismatch')
target.mkdir(parents=True,exist_ok=True)
shutil.copy2(sheet,target/'spritesheet.png')
rows=[('idle',[280,110,110,140,140,320]),('running-right',[120]*7+[220]),('running-left',[120]*7+[220]),('waving',[140]*3+[280]),('jumping',[140]*4+[280]),('failed',[140]*7+[240]),('waiting',[150]*5+[260]),('running',[120]*5+[220]),('review',[150]*5+[280])]
animations={};files={}
for state,durations in rows:
    frames=[]
    for index in range(len(durations)):
        original=source/'work/zenn/final-frames'/state/f'{index:02}.png'
        filename=f'{state}-{index}.png';destination=target/filename
        shutil.copy2(original,destination)
        checksum=hashlib.sha256(original.read_bytes()).hexdigest()
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=checksum:raise ValueError('Frame copy mismatch')
        files[filename]=checksum;frames.append(filename)
    animations[state]=dict(frames=frames,durations=durations)
animations['sleeping']=dict(frames=['idle-2.png'],durations=[600],motion='gentle_breathing')
animations['blinking']=animations['idle']
manifest=dict(name='ZENN',sprite_version=2,cell=[192,208],frames=73,rendered_standard_frames=len(files),source_sha256=digest,animations=animations,frame_sha256=files)
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(root/'evidence/zenn-assets.json').write_text(json.dumps(dict(source=str(source),source_sha256=digest,copied_frames=len(files),atlas_frames=73,original_pixels=True),indent=2)+'\n')
print(json.dumps(dict(name='ZENN',frames=len(files),atlas_frames=73,source_sha256=digest)))
