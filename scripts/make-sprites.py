"""Original Zenek artwork, generated locally; no third party pet assets."""
from pathlib import Path
import json
from PIL import Image,ImageDraw

root=Path(__file__).resolve().parents[1]/"gnome-extension/zenek@brillnet/assets"
root.mkdir(parents=True,exist_ok=True)
states=["idle","roaming","sleeping","waking","curious","thinking","amused","irritated","listening","typing","leaving","returning"]
metadata={"native_size":[32,32],"scale":3,"anchor":[16,30],"hitbox":[4,3,28,31],"animations":{}}
for state in states:
    sheet=Image.new("RGBA",(96*4,96))
    for frame in range(4):
        im=Image.new("RGBA",(32,32));d=ImageDraw.Draw(im)
        y=frame%2 if state not in ("sleeping","thinking") else 0
        d.rectangle((6,30,27,31),fill="#172c3860")
        def box(x1,y1,x2,y2,color):d.rectangle((x1,y1+y,x2,y2+y),fill=color)
        box(7,5,24,19,"#192636");box(5,9,26,17,"#192636")
        box(9,3,11,7,"#192636");box(20,3,22,7,"#192636")
        box(10,4,11,6,"#ef9971");box(20,4,21,6,"#ef9971")
        box(7,8,24,17,"#ffb183");box(9,6,22,18,"#ffb183")
        box(7,17,24,20,"#e7886d");box(9,19,23,27,"#192636")
        box(10,20,22,26,"#69cbb8");box(8,21,9,25,"#4f9f9a");box(23,21,25,25,"#4f9f9a")
        box(14,21,17,23,"#d8fff0");box(14,24,17,25,"#347881")
        step=(frame%2)*2 if state in ("roaming","leaving","returning") else 0
        box(10,27-step,13,29-step,"#ee9970");box(19,27+step//2,22,29+step//2,"#ee9970")
        box(9,29-step,14,30-step,"#192636");box(18,29+step//2,23,30+step//2,"#192636")
        closed=state=="sleeping" or (state=="idle" and frame==3)
        for x in (10,19):
            box(x-1,10,x+3,14,"#192636")
            box(x,11,x+2,13,"#fff6d5")
            if closed:box(x,12,x+2,13,"#192636")
            else:box(x+(1 if state=="curious" else 0),11,x+1,13,"#192636")
        box(14,12,18,12,"#192636")
        if state=="amused":box(13,16,18,17,"#192636");box(14,16,17,16,"#ffffff")
        elif state=="irritated":box(12,9,14,9,"#192636");box(19,9,21,9,"#192636");box(14,17,18,17,"#192636")
        else:box(14,16,17,16,"#a05650")
        if state in ("thinking","curious"):box(25,4,26,6,"#fff5c8");box(25,8,26,8,"#fff5c8")
        if state=="typing":box(8,25,24,28,"#303e57");box(10+frame,25,12+frame,25,"#c7ebd5")
        if state=="sleeping":box(24,2,28,2,"#abc9dc");box(27-frame%2,3,27-frame%2,4,"#abc9dc")
        large=im.resize((96,96),Image.Resampling.NEAREST)
        large.save(root/f"{state}-{frame}.png");sheet.paste(large,(96*frame,0))
    sheet.save(root/f"{state}-sheet.png")
    metadata["animations"][state]=dict(frames=4,fps=10,loop=True,sheet=f"{state}-sheet.png",frame_size=[96,96])
(root/"manifest.json").write_text(json.dumps(metadata,indent=2))
