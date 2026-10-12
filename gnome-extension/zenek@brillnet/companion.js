import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const xml=`<node><interface name="org.zenek.Desktop1"><method name="Call"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="out"/></method><signal name="Event"><arg type="s"/><arg type="s"/></signal></interface></node>`;
const Proxy=Gio.DBusProxy.makeProxyWrapper(xml);

export default class ZenekCompanion extends Extension {
    enable() {
        this._disabled=false;
        this._sources=new Set();this._signals=[];this._state=null;this._frame=0;this._positioned=false;this._spriteState=null;this._nextFrameAt=0;
        const [,pack]=Gio.File.new_for_path(`${this.path}/assets/zenn/manifest.json`).load_contents(null);
        this._pack=JSON.parse(new TextDecoder().decode(pack));
        this._proxy=new Proxy(Gio.DBus.session,'org.zenek.Desktop1','/org/zenek/Desktop1',()=>this._refresh());
        this._eventSignal=this._proxy.connectSignal('Event',(_p,_s,[kind,raw])=>this._event(kind,JSON.parse(raw)));
        this._signals.push([this._proxy,this._proxy.connect('notify::g-name-owner',()=>this._refresh())]);
        this._sprite=new St.Button({reactive:true,can_focus:true,track_hover:true,accessible_name:'Zenek — otwórz rozmowę'});
        this._icon=new St.Icon({icon_size:144});this._sprite.set_child(this._icon);
        Main.layoutManager.addChrome(this._sprite,{trackFullscreen:false});this._sprite.hide();
        this._sprite.connect('notify::hover',()=>{
            this._hideTooltip();
            if(this._sprite.hover&&this._state?.visibility==='VISIBLE'&&!this._dialog&&!this._drag){
                this._tooltipTimer=this._timer(600,()=>{
                    this._tooltipTimer=null;
                    if(this._sprite.hover&&this._state?.visibility==='VISIBLE'&&!this._dialog&&!this._drag)this._showTooltip();
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        this._sprite.connect('button-press-event',(_a,event)=>{
            this._hideTooltip();
            if(event.get_button()===3){this._indicator.menu.toggle();return Clutter.EVENT_STOP;}
            const [x,y]=event.get_coords();this._drag={x,y,px:this._sprite.x,py:this._sprite.y,moved:false};
            this._grab=global.stage.grab(this._sprite);return Clutter.EVENT_STOP;
        });
        this._sprite.connect('motion-event',(_a,event)=>{
            if(!this._drag)return Clutter.EVENT_PROPAGATE;
            const [x,y]=event.get_coords();const d=this._drag;
            if(Math.abs(x-d.x)+Math.abs(y-d.y)>6)d.moved=true;
            if(d.moved){d.direction=x-d.x>=0?'running-right':'running-left';this._sprite.set_position(d.px+x-d.x,d.py+y-d.y);}
            return Clutter.EVENT_STOP;
        });
        this._sprite.connect('button-release-event',()=>{
            this._grab?.dismiss();this._grab=null;
            if(this._drag?.moved){this._snap();this._savePosition();}else this._openDialog();
            this._drag=null;return Clutter.EVENT_STOP;
        });
        this._sprite.connect('key-press-event',(_a,event)=>{
            if(event.get_key_symbol()===Clutter.KEY_Return){this._openDialog();return Clutter.EVENT_STOP;}
            return Clutter.EVENT_PROPAGATE;
        });
        this._indicator=new PanelMenu.Button(0,'Zenek');
        this._indicatorIcon=new St.Icon({icon_name:'face-smile-symbolic',style_class:'system-status-icon'});
        this._indicator.add_child(this._indicatorIcon);
        Main.panel.addToStatusArea(this.uuid,this._indicator);this._indicator.hide();
        this._captureSwitch=new PopupMenu.PopupSwitchMenuItem('Okresowe zrzuty ekranu',false);
        this._indicator.menu.addMenuItem(this._captureSwitch);
        this._captureSwitch.connect('toggled',(_item,enabled)=>{
            if(this._syncingCapture)return;
            this._call(enabled?'ResumeScreenCapture':'PauseScreenCapture',{},()=>this._call('GetStatus',{},s=>this._apply(s)),()=>this._call('GetStatus',{},s=>this._apply(s)));
        });
        this._captureResume=new PopupMenu.PopupMenuItem('Wznów zrzuty');
        this._captureResume.connect('activate',()=>this._call('ResumeScreenCapture'));
        this._indicator.menu.addMenuItem(this._captureResume);this._captureResume.hide();
        for(const [label,method] of [['Rozmowa','dialog'],['Pokaż Zenka','ShowCompanion'],['Schowaj Zenka','HideCompanion'],['Przestań mówić','quiet'],['Przestań patrzeć','PauseScreenCapture'],['Ustawienia','settings'],['Zatrzymaj Zenka','stop']]){
            const item=new PopupMenu.PopupMenuItem(label);this._indicator.menu.addMenuItem(item);
            item.connect('activate',()=>this._action(method));
        }
        this._signals.push([global.display,global.display.connect('in-fullscreen-changed',()=>this._report())]);
        this._signals.push([Main.layoutManager,Main.layoutManager.connect('monitors-changed',()=>{this._snap();this._report();})]);
        this._signals.push([Main.sessionMode,Main.sessionMode.connect('updated',()=>this._report())]);
        this._signals.push([global.stage,global.stage.connect('captured-event',(_actor,event)=>this._outsideEvent(event))]);
        this._signals.push([global.display,global.display.connect('notify::focus-window',()=>{
            const window=global.display.focus_window;
            const [x,y]=global.get_pointer();
            if(this._dialog&&window&&window!==this._dialogWindow&&!this._insideCompanion(x,y))this._dismissOutside('window-focus');
        })]);
        this._animation=null;this._animationDelay=0;this._lastSpontaneous=0;
        this._timer(4000,()=>{this._report();return GLib.SOURCE_CONTINUE;});
    }
    _timer(ms,fn){const id=GLib.timeout_add(GLib.PRIORITY_DEFAULT,ms,()=>{const result=fn();if(result===GLib.SOURCE_REMOVE)this._sources.delete(id);return result;});this._sources.add(id);return id;}
    _outsideEvent(event){
        if(!this._dialog||![Clutter.EventType.BUTTON_PRESS,Clutter.EventType.TOUCH_BEGIN].includes(event.type()))return Clutter.EVENT_PROPAGATE;
        const [x,y]=event.get_coords();
        if(!this._insideCompanion(x,y))this._dismissOutside('shell-press');
        return Clutter.EVENT_PROPAGATE;
    }
    _insideCompanion(x,y){
        return [this._sprite,this._dialog].some(a=>{
            if(!a?.mapped)return false;
            const [ax,ay]=a.get_transformed_position(),[w,h]=a.get_transformed_size();
            return x>=ax&&x<ax+w&&y>=ay&&y<ay+h;
        });
    }
    _dismissOutside(source){
        this._outsideDismissals=(this._outsideDismissals??0)+1;this._outsideDismissSource=source;
        this._closeDialog();this._report();
    }
    _watchOutsidePointer(){
        // Wayland client events bypass stage captured-event. Query compositor state
        // only while a bubble exists; never grab input or consume the client's click.
        const mask=Clutter.ModifierType.BUTTON1_MASK|Clutter.ModifierType.BUTTON2_MASK|
            Clutter.ModifierType.BUTTON3_MASK|Clutter.ModifierType.BUTTON4_MASK|Clutter.ModifierType.BUTTON5_MASK;
        this._pointerButtons=global.get_pointer()[2]&mask;
        this._outsidePointer=this._timer(16,()=>{
            const [x,y,mods]=global.get_pointer(),buttons=mods&mask;
            const pressed=buttons&~this._pointerButtons;this._pointerButtons=buttons;
            if(pressed&&!this._insideCompanion(x,y)){
                // Let the timer remove itself: closing must not remove a running source.
                this._outsidePointer=null;this._dismissOutside('native-pointer');
                return GLib.SOURCE_REMOVE;
            }
            return GLib.SOURCE_CONTINUE;
        });
    }
    _call(method,p={},cb=null,onError=null){
        if(!this._proxy?.g_name_owner){onError?.('Core niedostępny.');return;}
        this._proxy.CallRemote(method,JSON.stringify(p),(result,error)=>{
            if(this._disabled)return;
            const fail=message=>{if(onError)onError(message);else this._text?.set_text(message);};
            if(error){fail('Core niedostępny.');return;}
            try{const v=JSON.parse(result[0]);if(v.ok)cb?.(v.result);else fail(v.error);}catch{fail('Błąd komunikacji.');}
        });
    }
    _refresh(){if(this._disabled)return;if(!this._proxy?.g_name_owner){this._sprite?.hide();this._indicator?.hide();this._closeDialog();this._state=null;return;}this._call('GetStatus',{},s=>this._apply(s));}
    _event(kind,p){
        if(this._disabled)return;
        if(kind==='StateChanged')this._apply(p);
        else if(kind==='Stopped'){this._sprite.hide();this._indicator.hide();this._closeDialog();}
        else if(kind==='BubbleRequested'&&this._state?.visibility==='VISIBLE'&&!this._composer){
            const now=GLib.get_monotonic_time()/1000000;
            if(this._lastSpontaneous&&now-this._lastSpontaneous<this._state.settings.spontaneous_cooldown_minutes*60)return;
            this._bubble(p.text,p.ttl_ms);
            const dialog=this._dialog;
            if(p.id)this._timer(150,()=>{if(this._dialog===dialog&&dialog?.mapped){this._lastSpontaneous=GLib.get_monotonic_time()/1000000;this._call('UtteranceDisplayed',{id:p.id});}return GLib.SOURCE_REMOVE;});
        }
        else if(['ReplyDelta','ReplyCompleted'].includes(kind)&&this._composer){
            if(this._awaitingTurn){this._pendingReplyEvents.push([kind,p]);return;}
            if(p.turn!==this._activeTurn)return;
            if(kind==='ReplyDelta'){this._reply=(this._reply??'')+p.delta;this._text.set_text((this._sentText?'Ty: '+this._sentText+'\n\nZenek: ':'')+this._reply);}
            else this._text.set_text((this._sentText?'Ty: '+this._sentText+'\n\nZenek: ':'')+p.text);
            this._scrollBottom();
        }
        else if(kind==='ErrorChanged'&&this._text)this._text.set_text(p.message);
    }
    _apply(s){
        const previous=this._state;
        this._state=s;this._indicator.show();
        this._sprite.accessible_name='Zenek — '+(s.animation?.reason??'otwórz rozmowę');
        if(this._tooltip)this._tooltip.set_text(this._tooltipText());
        this._icon.icon_size=48*Math.max(1,Math.min(6,s.settings?.sprite_scale??3));
        const delay=s.visibility!=='VISIBLE'?2000:s.idle||s.animation?.state==='sleeping'?500:Math.round(1000/Math.max(1,Math.min(20,s.settings?.sprite_fps??10)));
        if(delay!==this._animationDelay){
            if(this._animation){GLib.source_remove(this._animation);this._sources.delete(this._animation);}
            this._animationDelay=delay;this._animation=this._timer(delay,()=>{this._animate();return GLib.SOURCE_CONTINUE;});
        }
        this._indicatorIcon.icon_name=s.capture_phase==='SNAPSHOT'?'media-record-symbolic':s.screen==='ACTIVE'?'view-reveal-symbolic':'face-smile-symbolic';
        const captureEnabled=!!s.settings?.capture_enabled;
        this._syncingCapture=true;this._captureSwitch.setToggleState(captureEnabled);this._syncingCapture=false;
        const paused=captureEnabled&&s.screen==='OFF';
        this._captureSwitch.label.set_text(paused?'Okresowe zrzuty — pauza':'Okresowe zrzuty ekranu');
        this._captureResume.visible=paused;
        this._indicator.accessible_name=captureEnabled?'Zenek — zrzuty włączone, '+(paused?(s.capture_pause_reason??'pauza'):s.capture_phase==='SNAPSHOT'?'pobiera klatkę':'czeka na kolejny zrzut'):'Zenek — zrzuty wyłączone';
        if(s.visibility==='VISIBLE'){
            this._sprite.show();
            if(!this._positioned){const m=Main.layoutManager.monitors[s.settings.monitor]??Main.layoutManager.primaryMonitor;
                this._sprite.set_position(s.settings.x>=0?s.settings.x:m.x+m.width-140,s.settings.y>=0?s.settings.y:m.y+m.height-180);this._positioned=true;this._snap();}
        }else{this._hideTooltip();this._sprite.hide();this._closeDialog();}
        if(s.screen==='ACTIVE'&&s.capture_phase==='SNAPSHOT'&&previous?.capture_phase!=='SNAPSHOT')this._report();
    }
    _monitor(){return Main.layoutManager.monitors.find(m=>this._sprite.x>=m.x&&this._sprite.x<m.x+m.width&&this._sprite.y>=m.y&&this._sprite.y<m.y+m.height)??Main.layoutManager.primaryMonitor;}
    _snap(){if(!this._sprite)return;const m=this._monitor();const size=this._icon.icon_size;
        let x=Math.max(m.x,Math.min(m.x+m.width-size,this._sprite.x)),y=Math.max(m.y+35,Math.min(m.y+m.height-size,this._sprite.y));
        for(const edge of [m.x,m.x+m.width-size])if(Math.abs(x-edge)<32)x=edge;
        for(const edge of [m.y+35,m.y+m.height-size])if(Math.abs(y-edge)<32)y=edge;
        this._sprite.set_position(x,y);}
    _savePosition(){if(!this._state?.settings)return;const m=this._monitor();this._call('UpdateSettings',{expected_version:this._state.config_version,patch:{x:Math.round(this._sprite.x),y:Math.round(this._sprite.y),monitor:m.index}});}
    _report(){
        if(!this._state)return;
        const m=this._monitor();
        const locked=Main.sessionMode.isLocked;
        if(locked){this._sprite.hide();this._closeDialog();}
        const fullscreen=global.display.get_monitor_in_fullscreen(m.index);
        if(fullscreen&&this._state.settings?.auto_hide_on_fullscreen){this._sprite.hide();this._closeDialog();}
        const payload={idle_ms:global.backend.get_core_idle_monitor().get_idletime(),locked,fullscreen,
            composing:!!this._engaged,capture_indicator:this._indicator.mapped&&Main.layoutManager.panelBox.visible,
            ui_layout:{sprite_mapped:!!this._sprite.mapped,dialog_mapped:!!this._dialog?.mapped,reply_field:!!this._entry,tooltip_mapped:!!this._tooltip?.mapped,outside_dismissals:this._outsideDismissals??0,outside_dismiss_source:this._outsideDismissSource??'',outside_watcher:!!this._outsidePointer,animation:this._spriteState??'',sprite:[this._sprite.x,this._sprite.y,this._sprite.width,this._sprite.height],dialog:this._dialog?[this._dialog.x,this._dialog.y,this._dialog.width,this._dialog.height]:[]}};
        if(this._state.screen==='ACTIVE'){
            payload.windows=global.display.sort_windows_by_stacking(global.workspace_manager.get_active_workspace().list_windows()).reverse().filter(w=>!w.minimized).map(w=>{
                const r=w.get_frame_rect();const app=(w.get_gtk_application_id()??w.get_wm_class()??'').slice(0,240);
                return {title:(w.get_title()??'').slice(0,2048),app,rect:[r.x,r.y,r.width,r.height],opaque:app.startsWith('org.zenek.')};
            });
        }
        this._call('UIState',payload);
    }
    _animate(){
        if(!this._sprite?.visible)return;
        const animationState=this._state?.animation??{state:'idle'};
        const state=this._drag?.moved?this._drag.direction:animationState.state;
        const selected=this._drag?.moved?null:animationState.frames;
        const identity=state+':'+(selected??'all');
        const now=GLib.get_monotonic_time()/1000;
        this._icon.translation_y=state==='sleeping'?Math.round((Math.sin(now/750)+1)*.75):0;
        if(identity!==this._spriteState){this._spriteState=identity;this._frame=0;this._nextFrameAt=0;}
        if(now<this._nextFrameAt)return;
        const animation=this._pack.animations[state];
        const sequence=selected??animation.frames.map((_v,i)=>i);
        const index=sequence[this._frame];
        this._icon.gicon=Gio.icon_new_for_string(`${this.path}/assets/zenn/${animation.frames[index]}`);
        this._nextFrameAt=now+animation.durations[index];
        this._frame=(this._frame+1)%sequence.length;
    }
    _newDialog(){
        this._hideTooltip();
        this._closeDialog();this._dialog=new St.BoxLayout({orientation:Clutter.Orientation.VERTICAL,style_class:'zenek-dialog',reactive:true});
        this._dialogWindow=global.display.focus_window;
        const scroll=new St.ScrollView({height:160});this._scroll=scroll;this._text=new St.Label({text:'Zenek',style_class:'zenek-text'});
        this._text.clutter_text.line_wrap=true;this._text.clutter_text.ellipsize=0;
        const content=new St.BoxLayout({orientation:Clutter.Orientation.VERTICAL});content.add_child(this._text);
        this._text.clutter_text.selectable=true;
        scroll.set_child(content);this._dialog.add_child(scroll);
        Main.layoutManager.addChrome(this._dialog,{trackFullscreen:false});
        this._dialog.connect('notify::height',()=>this._positionDialog());
        this._dialog.connect('notify::width',()=>this._positionDialog());
        this._positionDialog();
        this._watchOutsidePointer();
    }
    _positionDialog(){
        if(!this._dialog||!this._sprite)return;
        const m=this._monitor(),gap=20,w=this._dialog.width||410,h=this._dialog.height||300,sw=this._sprite.width||this._icon.icon_size,sh=this._sprite.height||this._icon.icon_size;
        const sx=this._sprite.x,sy=this._sprite.y,top=m.y+40,bottom=m.y+m.height;
        let x=Math.max(m.x,Math.min(sx+(sw-w)/2,m.x+m.width-w)),y;
        if(sy-gap-h>=top)y=sy-gap-h;
        else if(sy+sh+gap+h<=bottom)y=sy+sh+gap;
        else if(sx-gap-w>=m.x){x=sx-gap-w;y=Math.max(top,Math.min(sy,bottom-h));}
        else{x=sx+sw+gap;y=Math.max(top,Math.min(sy,bottom-h));}
        this._dialog.set_position(Math.round(x),Math.round(y));
    }
    _openDialog(){
        if(this._state?.visibility!=='VISIBLE')return;
        this._newDialog();this._createComposer(true);
        const dialog=this._dialog,serial=this._sendSerial;
        this._call('GetLatestExchange',{},records=>{if(this._dialog!==dialog||this._sendSerial!==serial)return;this._text?.set_text(records.map(r=>(r.body.role==='user'?'Ty: ':'Zenek: ')+r.body.text).join('\n\n')||'Jestem. O czym pogadamy?');this._scrollBottom();});
    }
    _engage(){
        if(this._engaged)return;
        this._engaged=true;this._call('UserInteraction',{active:true});
    }
    _createComposer(focus){
        this._composer=true;this._engaged=false;this._reply='';this._sentText='';
        this._entry=new St.Entry({hint_text:'Napisz do Zenka…',style_class:'zenek-entry',reactive:true,can_focus:true,x_expand:true});
        this._entry.clutter_text.single_line_mode=false;
        this._entry.clutter_text.line_wrap=true;
        this._entry.clutter_text.line_wrap_mode=Pango.WrapMode.WORD_CHAR;
        this._entry.clutter_text.ellipsize=Pango.EllipsizeMode.NONE;
        this._entry.connect('button-press-event',()=>{
            this._engage();global.stage.set_key_focus(this._entry.clutter_text);return Clutter.EVENT_PROPAGATE;
        });
        this._inputScroll=new St.ScrollView({style_class:'zenek-input-scroll',height:38,hscrollbar_policy:St.PolicyType.NEVER,vscrollbar_policy:St.PolicyType.AUTOMATIC});
        const inputContent=new St.BoxLayout({orientation:Clutter.Orientation.VERTICAL,x_expand:true});
        inputContent.add_child(this._entry);this._inputScroll.set_child(inputContent);
        this._dialog.add_child(this._inputScroll);
        const actions=new St.BoxLayout({style_class:'zenek-actions'});
        for(const [label,fn] of [['Wyślij',()=>this._send()],['Anuluj',()=>this._cancelResponse()],['Zamknij',()=>this._closeDialog()]]){
            const button=new St.Button({label,style_class:'zenek-button',can_focus:true});button.connect('clicked',fn);actions.add_child(button);
        }this._dialog.add_child(actions);
        const navigate=event=>{
            const symbol=event.get_key_symbol();
            if(![Clutter.KEY_Tab,Clutter.KEY_ISO_Left_Tab].includes(symbol))return Clutter.EVENT_PROPAGATE;
            const backwards=symbol===Clutter.KEY_ISO_Left_Tab||event.get_state()&Clutter.ModifierType.SHIFT_MASK;
            this._dialog.navigate_focus(global.stage.get_key_focus(),backwards?St.DirectionType.TAB_BACKWARD:St.DirectionType.TAB_FORWARD,true);
            return Clutter.EVENT_STOP;
        };
        this._dialog.connect('key-press-event',(_actor,event)=>navigate(event));
        this._entry.clutter_text.connect('key-press-event',(_a,event)=>{
            if(navigate(event)===Clutter.EVENT_STOP)return Clutter.EVENT_STOP;
            if(event.get_key_symbol()===Clutter.KEY_Escape){this._cancelResponse();this._closeDialog();return Clutter.EVENT_STOP;}
            if(event.get_key_symbol()===Clutter.KEY_Return&&!(event.get_state()&Clutter.ModifierType.SHIFT_MASK)){this._send();return Clutter.EVENT_STOP;}
            return Clutter.EVENT_PROPAGATE;
        });
        this._entry.clutter_text.connect('key-focus-in',()=>this._engage());
        this._entry.clutter_text.connect('text-changed',()=>{if(this._entry?.get_text())this._engage();this._queueComposerLayout();});
        this._entry.clutter_text.connect('cursor-changed',()=>this._queueComposerLayout());
        this._entry.connect('notify::width',()=>this._queueComposerLayout());
        if(focus){this._engage();global.stage.set_key_focus(this._entry.clutter_text);}
        this._positionDialog();
        this._queueComposerLayout();
    }
    _queueComposerLayout(){
        if(this._inputLayoutSource)return;
        this._inputLayoutSource=this._timer(30,()=>{
            this._inputLayoutSource=null;
            if(!this._entry?.mapped)return GLib.SOURCE_REMOVE;
            const entry=this._entry,text=entry.clutter_text,layout=text.get_layout();
            const [,lineRect]=layout.get_line_readonly(0).get_pixel_extents();
            const lineHeight=Math.max(1,lineRect.height),width=this._entry.width;
            const [,natural]=this._entry.get_preferred_height(width);
            const [,textHeight]=layout.get_pixel_size(),padding=Math.max(0,natural-textHeight);
            const node=this._inputScroll.get_theme_node();
            const outerPadding=node.get_padding(St.Side.TOP)+node.get_padding(St.Side.BOTTOM);
            this._inputScroll.height=Math.ceil(Math.min(natural,4*lineHeight+padding)+outerPadding);
            // Preserve the underlying string; wrapping and scrolling only affect layout.
            this._timer(30,()=>{
                if(this._entry!==entry||!this._inputScroll)return GLib.SOURCE_REMOVE;
                const [ok,_x,y,h]=text.position_to_coords(text.cursor_position);
                const a=this._inputScroll.vadjustment;
                if(ok&&a){
                    const top=y+padding/2,bottom=top+h;
                    if(top<a.value)a.value=Math.max(a.lower,top);
                    else if(bottom>a.value+a.page_size)a.value=Math.min(a.upper-a.page_size,bottom-a.page_size);
                }
                this._positionDialog();return GLib.SOURCE_REMOVE;
            });
            return GLib.SOURCE_REMOVE;
        });
    }
    _scrollBottom(){
        if(this._scrollBottomSource)return;
        this._scrollBottomSource=this._timer(50,()=>{this._scrollBottomSource=null;const a=this._scroll?.vadjustment;if(a)a.value=Math.max(a.lower,a.upper-a.page_size);return GLib.SOURCE_REMOVE;});
    }
    _send(){
        const text=this._entry.get_text();if(!text.trim()||this._awaitingTurn)return;
        this._engage();this._reply='';this._sentText=text;this._activeTurn=null;this._awaitingTurn=true;this._pendingReplyEvents=[];
        const serial=this._sendSerial=(this._sendSerial??0)+1;
        this._text.set_text('Ty: '+text+'\n\nZenek myśli…');
        this._call('SendText',{text},turn=>{
            if(serial!==this._sendSerial||!this._entry)return;
            this._activeTurn=turn;this._awaitingTurn=false;
            if(this._entry.get_text()===text)this._entry.set_text('');
            const pending=this._pendingReplyEvents;this._pendingReplyEvents=[];
            for(const [kind,p] of pending)this._event(kind,p);
        },message=>{
            if(serial!==this._sendSerial)return;
            this._awaitingTurn=false;this._pendingReplyEvents=[];this._text?.set_text(message);
        });
        this._scrollBottom();
    }
    _cancelResponse(){
        this._sendSerial=(this._sendSerial??0)+1;this._activeTurn=null;this._awaitingTurn=false;this._pendingReplyEvents=[];
        this._call('CancelResponse');
    }
    _tooltipText(){return 'Zenek — '+(this._state?.animation?.reason??'Jestem')+'\nKliknij, żeby porozmawiać.';}
    _showTooltip(){
        this._tooltip=new St.Label({text:this._tooltipText(),style_class:'zenek-tooltip',reactive:false});
        this._tooltip.clutter_text.line_wrap=true;
        Main.layoutManager.addChrome(this._tooltip,{trackFullscreen:false});
        this._tooltip.connect('notify::height',()=>this._positionTooltip());this._tooltip.connect('notify::width',()=>this._positionTooltip());
        this._positionTooltip();
    }
    _positionTooltip(){
        if(!this._tooltip)return;
        const m=this._monitor(),w=this._tooltip.width||250,h=this._tooltip.height||60;
        const x=Math.max(m.x,Math.min(this._sprite.x+(this._sprite.width-w)/2,m.x+m.width-w));
        const y=this._sprite.y+this._sprite.height+h+10<=m.y+m.height?this._sprite.y+this._sprite.height+10:this._sprite.y-h-10;
        this._tooltip.set_position(Math.round(x),Math.round(Math.max(m.y+35,Math.min(y,m.y+m.height-h))));
    }
    _hideTooltip(){
        if(this._tooltipTimer){GLib.source_remove(this._tooltipTimer);this._sources.delete(this._tooltipTimer);this._tooltipTimer=null;}
        this._tooltip?.destroy();this._tooltip=null;
    }
    _bubble(text,ttl){
        if(this._composer)return;
        this._newDialog();this._text.set_text(text);this._createComposer(false);
        const dialog=this._dialog,words=text.trim().split(/\s+/).length;
        const reading=Math.max(ttl,this._state?.settings?.bubble_seconds*1000||60000,Math.min(180000,25000+words/3*1000));
        this._bubbleDeadline=GLib.get_monotonic_time()/1000+reading;
        this._timer(reading,()=>{if(this._dialog===dialog&&!this._engaged)this._closeDialog();return GLib.SOURCE_REMOVE;});
    }
    _closeDialog(){
        this._sendSerial=(this._sendSerial??0)+1;this._activeTurn=null;this._awaitingTurn=false;this._pendingReplyEvents=[];
        if(this._outsidePointer){GLib.source_remove(this._outsidePointer);this._sources.delete(this._outsidePointer);this._outsidePointer=null;}
        if(this._inputLayoutSource){GLib.source_remove(this._inputLayoutSource);this._sources.delete(this._inputLayoutSource);this._inputLayoutSource=null;}
        this._dialogWindow=null;
        this._inputScroll=null;
        if(this._engaged&&!this._disabled)this._call('UserInteraction',{active:false});this._dialog?.destroy();this._dialog=null;this._entry=null;this._text=null;this._scroll=null;this._sentText='';this._composer=false;this._engaged=false;
    }
    _action(method){
        if(method==='dialog')this._openDialog();
        else if(method==='settings')Gio.Subprocess.new([GLib.get_home_dir()+'/.local/bin/zenek','settings'],Gio.SubprocessFlags.NONE);
        else if(method==='stop')Gio.Subprocess.new(['systemctl','--user','stop','zenek-core.service'],Gio.SubprocessFlags.NONE);
        else if(method==='quiet')this._call('UpdateSettings',{expected_version:this._state.config_version,patch:{quiet:true}});
        else this._call(method);
    }
    disable(){
        // Stop the source immediately, preserving the owner's periodic preference.
        this._call('SuspendScreenCapture');
        this._closeDialog();
        this._disabled=true;
        this._hideTooltip();
        if(this._proxy&&this._eventSignal)this._proxy.disconnectSignal(this._eventSignal);
        this._closeDialog();
        for(const id of this._sources??[])GLib.source_remove(id);this._sources?.clear();
        for(const [obj,id] of this._signals??[])obj.disconnect(id);
        this._grab?.dismiss();this._closeDialog();this._sprite?.destroy();this._indicator?.destroy();
        this._proxy=null;this._sprite=null;this._indicator=null;
    }
}
