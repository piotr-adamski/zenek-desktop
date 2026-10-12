// Official GNOME headless test runner. Synthetic scene only; not active-session UAT.
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
import Shell from 'gi://Shell';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';

export async function run() {
    await Scripting.sleep(1500);
    const ext=Main.extensionManager.lookup('zenek@brillnet');
    if(!ext?.stateObj)throw new Error(`Extension unavailable: ${ext?.state}, ${ext?.errors}`);
    const zenek=ext.stateObj._companion;
    if(!zenek)throw new Error('Companion loader did not complete');
    const s={version:'0.1.0',visibility:'VISIBLE',activity:'idle',idle:false,config_version:1,
        settings:{monitor:0,x:1030,y:510,auto_hide_on_fullscreen:true,bubble_seconds:60}};
    zenek._call=(method,_payload,cb)=>cb?.(method==='SendText'?'synthetic-turn':[]); // Synthetic IPC boundary for render-only smoke.
    zenek._apply(s);zenek._animate();
    if(!zenek._sprite.visible)throw new Error('Sprite is not visible');
    zenek._openDialog();
    if(!zenek._entry)throw new Error('Composer missing');
    zenek._entry.set_text('Syntetyczny test rozmowy');zenek._send();
    zenek._event('ReplyDelta',{turn:'synthetic-turn',delta:'Cześć. Jestem Zenek.'});
    if(!zenek._text.text.endsWith('Cześć. Jestem Zenek.')||!zenek._text.text.startsWith('Ty: Syntetyczny test rozmowy'))throw new Error('Latest exchange not rendered');
    zenek._text.set_text('Ostatnia wymiana\n'.repeat(100));zenek._scrollBottom();
    await Scripting.sleep(200);
    const adjustment=zenek._scroll.vadjustment;
    if(adjustment.value<adjustment.upper-adjustment.page_size-1)throw new Error('Dialog did not scroll to newest entry');
    zenek._text.set_text('Cześć. Jestem Zenek.');
    for(const state of ['idle','running-right','running-left','waving','jumping','failed','waiting','running','review']){
        zenek._apply({...s,animation:{state,reason:'Synthetic render smoke'}});zenek._animate();
        if(!zenek._icon.gicon.to_string().includes(`/zenn/${state}-0.png`))throw new Error(`Wrong ZENN animation: ${state}`);
    }
    zenek._apply({...s,animation:{state:'running',reason:'Synthetic render smoke'}});zenek._animate();
    await Scripting.sleep(500);
    const screenshot=new Shell.Screenshot();
    const output=Gio.File.new_for_path(GLib.getenv('ZENEK_SMOKE_IMAGE'));
    const stream=output.replace(null,false,Gio.FileCreateFlags.NONE,null);
    await screenshot.screenshot(false,stream);stream.close(null);
    zenek._apply({...s,visibility:'HIDDEN'});
    if(zenek._sprite.visible||zenek._dialog)throw new Error('Hidden state leaked UI');
    zenek._apply(s);zenek._bubble('Syntetyczna własna inicjatywa',200);
    await Scripting.sleep(300);
    if(!zenek._dialog||!zenek._entry)throw new Error('Spontaneous bubble has no reply field');
    if(zenek._bubbleDeadline-GLib.get_monotonic_time()/1000<59000)throw new Error('Reading time too short');
    const a=zenek._sprite,b=zenek._dialog;
    if(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y)throw new Error('Bubble covers ZENN');
    zenek._outsideEvent({type:()=>Clutter.EventType.BUTTON_PRESS,get_coords:()=>[0,0]});
    if(zenek._dialog)throw new Error('Outside click did not close bubble');
    ext.stateObj.disable();
    print('ZENEK_GNOME_SMOKE_PASS render composer reply hide show bubble cleanup');
}
