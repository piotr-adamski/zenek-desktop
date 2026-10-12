// Official GNOME automation runner, isolated headless compositor and private bus.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Shell from 'gi://Shell';
import IBus from 'gi://IBus';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';

const root=GLib.getenv('ZENEK_TEST_ROOT');
const sleep=Scripting.sleep;
function assert(ok,message){if(!ok)throw new Error(message);}
async function wait(fn,message){for(let i=0;i<60;i++){if(fn())return;await sleep(50);}throw new Error(message);}
async function realConversation(ui,keyboard,pointer){
    const bus=GLib.getenv('ZENEK_TEST_REAL_CORE_BUS');
    assert(bus==='unix:path=/run/user/1000/bus','Unexpected Core bus');
    const connection=Gio.DBusConnection.new_for_address_sync(bus,Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,null,null);
    const live=Gio.DBusProxy.new_sync(connection,Gio.DBusProxyFlags.DO_NOT_AUTO_START,null,'org.zenek.Desktop1','/org/zenek/Desktop1','org.zenek.Desktop1',null);
    const allowed=new Set(['GetStatus','GetLatestExchange','SendText','CancelResponse','UserInteraction']);
    function rpc(method,p={}){
        assert(allowed.has(method),'Unexpected Core mutation');
        const raw=live.call_sync('Call',new GLib.Variant('(ss)',[method,JSON.stringify(p)]),Gio.DBusCallFlags.NO_AUTO_START,5000,null).deep_unpack()[0];
        const value=JSON.parse(raw);assert(value.ok,value.error??'Core rejected request');return value.result;
    }
    const original=rpc('GetStatus');
    assert(!original.ui_layout?.dialog_mapped&&!original.ui_layout?.composing&&!original.active_jobs.includes('conversation'),'Owner is using the dialogue');
    assert(original.visibility==='VISIBLE'&&!original.locked&&!original.suspended,'Owner session is unavailable');
    const profile=original.settings.conversation;
    assert(profile.model_id==='gpt-6.1-sol'&&profile.reasoning_effort==='medium'&&profile.status==='READY','Selected conversation profile is not ready');
    assert(!original.settings.paid_api_approved,'Unexpected paid API configuration');
    let lastSent='',completed=new Map(),deltas=new Set(),calls=[],errors=[],ownedInteraction=false,bubbles=0,latestState=original;
    ui._report=()=>{}; // Never report private compositor windows/idle/lock as owner metadata.
    ui._call=(method,p={},cb=null,onError=null)=>{
        if(!allowed.has(method)){onError?.('Method outside dialogue test');return;}
        const owner=rpc('GetStatus');
        if((method==='SendText'||method==='UserInteraction'&&p.active)&&(owner.idle||owner.locked||owner.suspended||owner.visibility!=='VISIBLE')){
            errors.push('Owner session became unavailable');onError?.('Owner session unavailable');return;
        }
        if(['SendText','CancelResponse','UserInteraction'].includes(method)&&(owner.ui_layout?.dialog_mapped||owner.ui_layout?.composing)){
            errors.push('Owner opened dialogue during test');onError?.('Owner dialogue active');return;
        }
        if(method==='CancelResponse'){
            const latest=rpc('GetLatestExchange');
            if(!latest.some(r=>r.body.role==='user'&&r.body.text===lastSent)){errors.push('Test no longer owns latest turn');return;}
        }
        if(method==='SendText')lastSent=p.text;
        if(method==='UserInteraction')ownedInteraction=p.active;
        calls.push(method);
        live.call('Call',new GLib.Variant('(ss)',[method,JSON.stringify(p)]),Gio.DBusCallFlags.NO_AUTO_START,5000,null,(proxy,result)=>{
            try{
                const value=JSON.parse(proxy.call_finish(result).deep_unpack()[0]);
                if(!value.ok)throw new Error(value.error??'Core rejected dialogue');
                cb?.(value.result);
            }catch(error){errors.push(error.message);onError?.(error.message);}
        });
    };
    const signal=live.connect('g-signal',(_proxy,_sender,name,args)=>{
        if(name!=='Event')return;
        const [kind,raw]=args.deep_unpack(),payload=JSON.parse(raw);
        if(kind==='StateChanged')latestState=payload;
        if(kind==='ReplyDelta')deltas.add(payload.turn);
        if(kind==='ReplyCompleted')completed.set(payload.turn,payload.text);
        if(kind==='BubbleRequested')bubbles++;
        if(['StateChanged','ReplyDelta','ReplyCompleted','ErrorChanged','Stopped'].includes(kind))ui._event(kind,payload);
    });
    async function motion(x,y){for(let i=0;i<3;i++){pointer.notify_absolute_motion(GLib.get_monotonic_time(),x,y);await sleep(100);}}
    async function click(x,y){await motion(x,y);pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.PRESSED);await sleep(60);pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.RELEASED);await sleep(120);}
    async function key(symbol){keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.PRESSED);await sleep(30);keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.RELEASED);await sleep(80);}
    async function paste(text){
        St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD,text);
        keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.PRESSED);await key(Clutter.KEY_v);
        keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.RELEASED);await sleep(180);
        assert(ui._entry.get_text()===text,'Polish multiline input changed');
    }
    async function until(fn,message,seconds=30){
        const end=GLib.get_monotonic_time()+seconds*1000000;
        while(GLib.get_monotonic_time()<end){assert(!errors.length,'Dialogue error');if(fn())return;await sleep(50);}
        throw new Error(message);
    }
    try{
        ui._apply(original);await sleep(300);
        await wait(()=>ui._sprite.mapped&&ui._sprite.width>0&&ui._sprite.height>0,'Pet did not receive its first frame allocation');
        if(GLib.getenv('ZENEK_TEST_AUTONOMOUS')==='1'){
            // Observe the normal scheduler. Never start an initiative, alter
            // its clock/limits, or send private compositor session metadata.
            let opportunity;
            await until(()=>{
                const state=latestState;
                if(state.active_jobs.includes('initiative')&&state.visibility==='VISIBLE'&&!state.idle&&!state.locked&&!state.suspended&&!state.ui_layout?.composing&&!state.ui_layout?.dialog_mapped){opportunity=state;return true;}
                return false;
            },'No natural autonomous initiative within twenty minutes',1200);
            const beforeBubbles=bubbles,start=GLib.get_monotonic_time();
            const [px,py]=ui._sprite.get_transformed_position(),[pw,ph]=ui._sprite.get_transformed_size();
            await click(px+pw/2,py+ph/2);
            await wait(()=>ui._entry?.mapped,'Native entry did not open');
            const text='Syntetyczny test przerwania samodzielnego komentarza. Odpowiedz wyłącznie: ZENN_INTERRUPT_OK.';
            await paste(text);
            assert(calls.includes('UserInteraction')&&global.stage.get_key_focus()===ui._entry.clutter_text,'Native input did not engage Core');
            await until(()=>!rpc('GetStatus').active_jobs.includes('initiative'),'Input did not stop autonomous inference',5);
            assert(bubbles===beforeBubbles,'Initiative completed before input interruption; cannot prove cancellation');
            await key(Clutter.KEY_Return);await until(()=>!!ui._activeTurn,'User reply not accepted',5);
            const turn=ui._activeTurn;await until(()=>completed.has(turn),'User reply did not finish');
            assert(deltas.has(turn)&&completed.get(turn).includes('ZENN_INTERRUPT_OK')&&completed.get(turn).length<100,'Unexpected user reply');
            assert(ui._text.text==='Ty: '+text+'\n\nZenek: '+completed.get(turn),'Interrupted comment contaminated reply');
            const state=rpc('GetStatus');
            assert(bubbles===beforeBubbles&&!state.active_jobs.includes('initiative'),'Cancelled initiative surfaced later');
            assert((state.usage.spontaneous??0)===(opportunity.usage.spontaneous??0),'User reply consumed spontaneous budget');
            assert(JSON.stringify(state.settings)===JSON.stringify(opportunity.settings),'Owner settings changed during input test');
            print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'native private GNOME input -> original Core normal autonomous scheduler/SIWC; no forced initiative or fake owner metadata',core_build:state.core_build,model:profile.model_id,effort:profile.reasoning_effort,natural_autonomous_job_observed:true,native_input_interrupts_initiative:true,cancelled_comment_not_displayed:true,user_reply_streamed_exact:true,user_reply_does_not_consume_spontaneous_budget:true,no_stale_fragments:true,seconds_from_interrupt_to_reply:(GLib.get_monotonic_time()-start)/1000000,owner_settings_unchanged:true,owner_pointer_and_clipboard_untouched:true}));
            return;
        }
        const [sx,sy]=ui._sprite.get_transformed_position(),[sw,sh]=ui._sprite.get_transformed_size();
        print('ZENEK_REAL_LAYOUT '+JSON.stringify({sprite:[sx,sy,sw,sh],mapped:ui._sprite.mapped,visibility:ui._state.visibility}));
        await click(sx+sw/2,sy+sh/2);
        print('ZENEK_REAL_CLICK '+JSON.stringify({pointer:global.get_pointer(),dialog:!!ui._dialog,entry_mapped:ui._entry?.mapped,drag:!!ui._drag,visibility:ui._state.visibility}));
        await wait(()=>ui._entry?.mapped&&ui._entry.width>0&&ui._entry.height>0,'Click did not open conversation');
        let [x,y]=ui._entry.get_transformed_position();await click(x+25,y+10);
        assert(global.stage.get_key_focus()===ui._entry.clutter_text,'Composer click did not focus keyboard');
        const text='To syntetyczny test interfejsu, bez faktów o Piotrze. Odpowiedz wyłącznie: ZENN_GUI_OK.\n'+('Zażółć gęślą jaźń. ').repeat(30);
        await paste(text);await sleep(200);
        assert(ui._entry.clutter_text.get_layout().get_line_count()>4,'Input did not wrap past four lines');
        assert(ui._inputScroll.vadjustment.upper>ui._inputScroll.vadjustment.page_size,'Input failed to scroll');
        await key(Clutter.KEY_Return);await until(()=>!!ui._activeTurn,'Send was not accepted',5);
        const first=ui._activeTurn;
        await until(()=>completed.has(first),'Actual model did not complete');
        assert(deltas.has(first),'Actual reply did not stream into UI');
        assert(ui._text.text==='Ty: '+text+'\n\nZenek: '+completed.get(first),'Displayed reply differs from actual completed reply');
        assert(completed.get(first).includes('ZENN_GUI_OK')&&completed.get(first).length<100,'Unexpected synthetic test reply');
        const latest=rpc('GetLatestExchange');
        assert(latest.length===2&&latest[0].body.text===text&&latest[1].body.text===completed.get(first),'Core did not preserve exact exchange');
        const stream=Gio.File.new_for_path(`${root}/evidence/dialog-real-core.png`).replace(null,false,Gio.FileCreateFlags.NONE,null);
        await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
        const lengthy='Syntetyczny test anulowania odpowiedzi. Wypisz liczby od 1 do 400, każdą w osobnym wierszu, bez danych osobowych.';
        await paste(lengthy);await key(Clutter.KEY_Return);
        await until(()=>ui._activeTurn&&ui._activeTurn!==first,'Second send not accepted',5);
        const cancelled=ui._activeTurn;
        await until(()=>deltas.has(cancelled),'No actual delta to cancel');
        assert(!completed.has(cancelled)&&rpc('GetStatus').active_jobs.includes('conversation'),'Long response finished before cancellation could be tested');
        await key(Clutter.KEY_Escape);
        assert(!ui._dialog&&calls.includes('CancelResponse'),'Escape did not cancel and close');
        const replacementStart=GLib.get_monotonic_time();
        const [rx,ry]=ui._sprite.get_transformed_position(),[rw,rh]=ui._sprite.get_transformed_size();
        await click(rx+rw/2,ry+rh/2);
        await wait(()=>ui._entry?.mapped&&ui._entry.width>0&&ui._entry.height>0,'Conversation did not reopen');
        const replacement='To syntetyczny test po anulowaniu, bez danych osobowych. Odpowiedz wyłącznie: ZENN_REPLACEMENT_OK.';
        await paste(replacement);await key(Clutter.KEY_Return);
        await until(()=>ui._activeTurn&&ui._activeTurn!==cancelled,'Replacement not accepted',5);
        const third=ui._activeTurn;await until(()=>completed.has(third),'Replacement did not complete');
        assert(!completed.has(cancelled),'Cancelled turn completed later');
        assert(ui._text.text==='Ty: '+replacement+'\n\nZenek: '+completed.get(third),'Old turn fragments contaminated replacement');
        assert(completed.get(third).includes('ZENN_REPLACEMENT_OK')&&completed.get(third).length<100,'Unexpected replacement reply');
        const now=rpc('GetStatus');
        assert(now.settings.conversation.model_id===profile.model_id&&now.settings.conversation.reasoning_effort===profile.reasoning_effort,'Owner profile changed');
        print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'isolated real GNOME Wayland UI -> original authorized Core/D-Bus/SIWC; no synthetic UIState sent',core_build:now.core_build,model:profile.model_id,effort:profile.reasoning_effort,actual_click_opens_and_focuses:true,polish_multiline_paste_exact:true,four_line_scroll:true,actual_send_stream_reply:true,latest_exchange_readback:true,escape_cancels_actual_stream:true,reopen_and_replacement_reply:true,old_reply_filtered:true,replacement_seconds:(GLib.get_monotonic_time()-replacementStart)/1000000,owner_profiles_unchanged:true,paid_api:false,owner_pointer_and_clipboard_untouched:true}));
    }finally{
        const owner=rpc('GetStatus');
        if(!owner.ui_layout?.composing&&!owner.ui_layout?.dialog_mapped){
            if(owner.active_jobs.includes('conversation')&&rpc('GetLatestExchange').some(r=>r.body.role==='user'&&r.body.text===lastSent))rpc('CancelResponse');
            if(ownedInteraction)rpc('UserInteraction',{active:false});
        }
        ui.disable();live.disconnect(signal);connection.close_sync(null);
    }
}
export async function run(){
    print('ZENEK_DIALOG_START');
    await wait(()=>!Main.layoutManager._startingUp,'Shell startup did not complete');
    const Companion=(await import(Gio.File.new_for_path(`${root}/gnome-extension/zenek@brillnet/companion.js`).get_uri())).default;
    Main.overview.hide();await sleep(400);
    const seat=Clutter.get_default_backend().get_default_seat();
    const keyboard=seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
    const pointer=seat.create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE);
    await sleep(300);
    const launcher=new Gio.SubprocessLauncher({flags:Gio.SubprocessFlags.NONE});
    launcher.setenv('WAYLAND_DISPLAY','gnome-shell-test-display',true);
    let imeDaemon;
    if(GLib.getenv('ZENEK_TEST_IME')==='1'){
        assert(GLib.getenv('IBUS_ADDRESS').includes('zenek-dialog-runtime-'),'IBus address not private');
        launcher.unsetenv('IBUS_USE_PORTAL');
        imeDaemon=launcher.spawnv(['ibus-daemon','--replace','--single','--address',GLib.getenv('IBUS_ADDRESS')]);
        await wait(()=>Main.inputMethod._ibus.is_connected()&&!!Main.inputMethod._context,'Private real IBus did not connect');
        assert(Main.inputMethod._ibus.set_global_engine('xkb:us::eng'),'Private IBus engine unavailable');
        assert(GLib.getenv('GSETTINGS_BACKEND')==='keyfile','Input settings not isolated');
        new Gio.Settings({schema_id:'org.gnome.desktop.input-sources'}).set_strv('xkb-options',['compose:ralt']);
        await sleep(300);
    }
    const client=launcher.spawnv([`${root}/.venv/bin/python`,`${root}/scripts/uat-dialog-client.py`]);
    let native;
    await wait(()=>{native=global.get_window_actors().map(a=>a.meta_window).find(w=>w.get_title()==='Zenek dialog test client');return !!native;},'Native client did not map');
    await wait(()=>native.get_compositor_private()?.mapped,'Native actor did not map');
    native.move_frame(true,40,150);native.activate(global.get_current_time());await sleep(300);
    const nr=native.get_frame_rect();print('Native '+JSON.stringify({wm_class:native.get_wm_class(),app:native.get_gtk_application_id(),rect:[nr.x,nr.y,nr.width,nr.height],mapped:native.get_compositor_private()?.mapped,actor:native.get_compositor_private()?.get_transformed_position(),overview:Main.overview.visible}));
    const theme=St.ThemeContext.get_for_stage(global.stage).get_theme();
    const css=Gio.File.new_for_path(`${root}/gnome-extension/zenek@brillnet/stylesheet.css`);theme.load_stylesheet(css);
    const ui=new Companion({uuid:'zenek@brillnet',name:'Zenek',path:`${root}/gnome-extension/zenek@brillnet`,dir:Gio.File.new_for_path(`${root}/gnome-extension/zenek@brillnet`)});
    const calls=[];ui._refresh=()=>{};ui._call=(method,p={},cb=null)=>{calls.push({method,p});if(method==='GetLatestExchange')cb?.([]);if(method==='SendText')cb?.('synthetic-turn');};
    ui.enable();
    if(GLib.getenv('ZENEK_TEST_REAL_CORE_BUS')){
        try{await realConversation(ui,keyboard,pointer);}finally{client.force_exit();theme.unload_stylesheet(css);}
        return;
    }
    ui._apply({visibility:'VISIBLE',screen:'OFF',animation:{state:'sleeping'},settings:{sprite_scale:3,sprite_fps:10,monitor:0,x:1090,y:70,bubble_seconds:60}});await sleep(150);
    if(GLib.getenv('ZENEK_TEST_CAPTURE_MENU')==='1'){
        const state={...ui._state,settings:{...ui._state.settings,capture_enabled:true},capture_pause_reason:'Blokada ekranu'};
        const before=calls.length;ui._apply(state);
        assert(ui._captureSwitch.state===true&&ui._captureResume.visible,'Saved ON/paused menu mismatch');
        assert(calls.length===before,'Readback toggled capture');
        ui._indicator.menu.open();await sleep(300);
        assert(ui._captureSwitch.mapped,'Quick switch did not render');
        const stream=Gio.File.new_for_path(`${root}/evidence/capture-menu.png`).replace(null,false,Gio.FileCreateFlags.NONE,null);
        await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
        ui._captureSwitch.emit('toggled',false);assert(calls.at(-2)?.method==='PauseScreenCapture'||calls.at(-1)?.method==='PauseScreenCapture','OFF did not reach IPC');
        ui._captureSwitch.emit('toggled',true);assert(calls.at(-2)?.method==='ResumeScreenCapture'||calls.at(-1)?.method==='ResumeScreenCapture','ON did not reach IPC');
        ui._apply({...state,settings:{...state.settings,capture_enabled:false}});assert(!ui._captureSwitch.state&&!ui._captureResume.visible,'OFF readback mismatch');
        ui.disable();assert(calls.some(c=>c.method==='SuspendScreenCapture'),'Disable erased preference');
        client.force_exit();theme.unload_stylesheet(css);
        print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'actual isolated GNOME50 PopupSwitchMenuItem rendering and toggled handlers; IPC fixture',saved_on_during_pause:true,off_on_handlers:true,readback_no_writes:true,resume_action_visible_when_paused:true,disable_preserves_preference:true}));return;
    }
    if(GLib.getenv('ZENEK_TEST_IME')==='1'){
        Main.overview.hide();ui._openDialog();
        await wait(()=>ui._entry?.mapped&&ui._entry.width>0,'IME field not allocated');await sleep(300);
        global.stage.set_key_focus(ui._entry.clutter_text);
        async function key(symbol){keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.PRESSED);await sleep(40);keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.RELEASED);await sleep(120);}
        const sends=()=>calls.filter(c=>c.method==='SendText');
        const context=Main.inputMethod._context;
        // Drive the actual IBus protocol for this composition; virtual keyboard
        // mapping of Multi_key varies with the headless XKB backend.
        context.set_engine('xkb:us::eng');await sleep(200);
        async function imeKey(symbol){
            await context.process_key_event_async(symbol,0,0,-1,null);
            await context.process_key_event_async(symbol,0,IBus.ModifierType.RELEASE_MASK,-1,null);
            await sleep(150);
        }
        await imeKey(IBus.KEY_Multi_key);await imeKey(IBus.KEY_apostrophe);await sleep(300);
        const preedit=ui._entry.clutter_text.get_layout().get_text();
        print('ZENEK_IME_PREEDIT '+JSON.stringify({layout:preedit,committed:ui._entry.get_text(),engine:'xkb:us::eng',connected:Main.inputMethod._ibus.is_connected(),focused:global.stage.get_key_focus()===ui._entry.clutter_text,im_preedit:Main.inputMethod._preeditStr,im_visible:Main.inputMethod._preeditVisible,current_source:Main.inputMethod._currentSource?.id}));
        assert(ui._entry.get_text()===''&&Main.inputMethod._preeditVisible,'Compose prefix did not remain uncommitted');
        assert(!sends().length,'Preedit submitted a message');
        await imeKey(IBus.KEY_a);
        await wait(()=>ui._entry.get_text()==='á'||sends().length>0,'IME did not commit the composed character');
        print('ZENEK_IME_COMMIT '+JSON.stringify({text:ui._entry.get_text(),sent:sends().map(c=>c.p.text),im_preedit:Main.inputMethod._preeditStr,im_visible:Main.inputMethod._preeditVisible,focused:global.stage.get_key_focus()===ui._entry.clutter_text}));
        assert(ui._entry.get_text()==='á'&&!sends().length,'IME composition was submitted prematurely');
        await key(Clutter.KEY_Return);
        assert(sends().length===1&&sends()[0].p.text==='á','Final Enter did not send exact composed character');
        await key(Clutter.KEY_Tab);
        assert(global.stage.get_key_focus()!==ui._entry.clutter_text,'Tab did not leave composer');
        keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.PRESSED);await key(Clutter.KEY_Tab);
        keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.RELEASED);await sleep(100);
        assert(global.stage.get_key_focus()===ui._entry.clutter_text,'Shift+Tab did not restore composer focus');
        ui.disable();assert(ui._sources.size===0,'IME test leaked UI timers');client.force_exit();imeDaemon.force_exit();theme.unload_stylesheet(css);
        print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'actual isolated GNOME Wayland/St.Entry/IBus simple engine via public InputContext key protocol; final Enter/Tab virtual keyboard; IPC send fixture',engine:'xkb:us::eng',compose_preedit_visible:true,preedit_not_submitted:true,compose_commits_exact_character:true,enter_sends_exact_composed_character:true,tab_and_shift_tab_focus_navigation:true,owner_keyboard_and_settings_unchanged:true,no_timers_after_disable:true}));return;
    }
    const dismiss=ui._dismissOutside.bind(ui);ui._dismissOutside=source=>{print('Dismiss '+JSON.stringify({source,pointer:global.get_pointer(),dialog:ui._dialog?[ui._dialog.x,ui._dialog.y,ui._dialog.width,ui._dialog.height]:null}));dismiss(source);};
    const debugSignal=global.stage.connect('captured-event',(_a,e)=>{if(e.type()===Clutter.EventType.BUTTON_PRESS)print('STAGE_PRESS '+e.get_source());return Clutter.EVENT_PROPAGATE;});
    async function move(x,y){for(let i=0;i<3;i++){pointer.notify_absolute_motion(GLib.get_monotonic_time(),x,y);await sleep(100);}print('Pointer '+JSON.stringify({requested:[x,y],actual:global.get_pointer()}));}
    async function click(x,y){await move(x,y);pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.PRESSED);await sleep(60);pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.RELEASED);await sleep(80);}
    const [nax,nay]=native.get_compositor_private().get_transformed_position(),nx=nax+100,ny=nay+100;
    const composer=await checkComposer();print('ZENEK_COMPOSER_UAT '+JSON.stringify({status:'PASS',...composer}));ui._closeDialog();
    // GNOME50 headless virtual device clamps pointer Y to zero. Set the real
    // St hover property to verify rendering/lifecycle, not pointer delivery.
    await sleep(200);ui._sprite.set_hover(true);
    await wait(()=>ui._tooltip?.mapped,'Tooltip did not show after St hover state');
    assert(ui._tooltip.text.includes('Kliknij'),'Tooltip lacks conversation hint');
    await sleep(100);
    const a=ui._sprite,b=ui._tooltip;
    assert(!(a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y),'Tooltip covers pet');
    const tooltipStream=Gio.File.new_for_path(`${root}/evidence/tooltip-hover.png`).replace(null,false,Gio.FileCreateFlags.NONE,null);
    await new Shell.Screenshot().screenshot(false,tooltipStream);tooltipStream.close(null);
    ui._sprite.set_hover(false);await sleep(200);assert(!ui._tooltip&&!ui._tooltipTimer,'Tooltip survived hover exit');
    ui._sprite.set_hover(true);await sleep(100);ui._sprite.set_hover(false);await sleep(700);
    assert(!ui._tooltip&&!ui._tooltipTimer,'Cancelled hover timer created tooltip later');
    if(GLib.getenv('ZENEK_TEST_COMPOSER_ONLY')==='1'){
        ui.disable();assert(ui._sources.size===0,'Timers leaked after disable');global.stage.disconnect(debugSignal);client.force_exit();theme.unload_stylesheet(css);
        print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'composer and St hover state',...composer,tooltip_state_render_and_cleanup:true,tooltip_real_pointer_verified:false,no_timers_after_disable:true}));return;
    }
    await move(ui._sprite.x+50,ui._sprite.y+50);
    await wait(()=>ui._tooltip?.mapped,'Actual pointer hover did not show tooltip');
    await move(600,450);await sleep(150);
    assert(!ui._tooltip&&!ui._tooltipTimer,'Actual hover exit did not clean tooltip');
    const before=[ui._sprite.x,ui._sprite.y];
    await move(before[0]+50,before[1]+50);
    pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.PRESSED);await sleep(120);
    assert(ui._drag,'Actual pointer press did not start pet drag');
    await move(before[0]-30,before[1]+90);
    pointer.notify_button(GLib.get_monotonic_time(),Clutter.BUTTON_PRIMARY,Clutter.ButtonState.RELEASED);await sleep(200);
    assert(!ui._drag&&!ui._grab,'Drag release left a grab');
    assert(ui._sprite.x!==before[0]||ui._sprite.y!==before[1],'Drag did not move pet');
    assert(calls.some(c=>c.method==='UpdateSettings'&&'x' in c.p.patch),'Drag did not save position');
    print('ZENEK_POINTER_UAT '+JSON.stringify({status:'PASS',scope:'actual virtual pointer in isolated GNOME Wayland; setting write IPC fixture',tooltip_real_pointer_verified:true,tooltip_hover_exit_cleanup:true,pet_drag_and_release:true,position_write_requested:true,no_owner_pointer_or_settings_changes:true}));
    if(GLib.getenv('ZENEK_TEST_POINTER_ONLY')==='1'){
        ui.disable();assert(ui._sources.size===0,'Timers leaked after disable');global.stage.disconnect(debugSignal);client.force_exit();theme.unload_stylesheet(css);
        print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',scope:'actual virtual pointer in isolated GNOME Wayland; setting write IPC fixture',tooltip_real_pointer_verified:true,tooltip_hover_exit_cleanup:true,pet_drag_and_release:true,position_write_requested:true,no_timers_after_disable:true,no_owner_pointer_or_settings_changes:true,native_client_click_delivery_verified:false}));return;
    }
    await click(nx,ny);
    await wait(()=>Gio.File.new_for_path(GLib.getenv('ZENEK_TEST_CLICK_FILE')).query_exists(null),'Baseline native click failed');
    ui._openDialog();await sleep(200);
    const dialog=ui._dialog;
    await click(dialog.x+80,dialog.y+60);assert(ui._dialog===dialog,'Click inside closed dialog');
    await click(nx,ny);
    assert(!ui._dialog,'Native click did not dismiss focused composer');
    assert(!ui._outsidePointer,'Pointer watcher remained after closure');
    await wait(()=>Gio.File.new_for_path(GLib.getenv('ZENEK_TEST_CLICK_FILE')).query_exists(null),'Native client did not receive click');
    const focusedSource=ui._outsideDismissSource;
    // Already focused native window: no focus-window transition can save this case.
    native.activate(global.get_current_time());await sleep(100);
    ui._bubble('Synthetic passive bubble',60000);await sleep(150);
    assert(global.display.focus_window===native,'Passive bubble stole native focus');
    await click(nx,ny);assert(!ui._dialog,'Native click in same focused window did not dismiss passive bubble');
    const passiveSource=ui._outsideDismissSource;
    assert(passiveSource==='native-pointer','Same-window case did not exercise compositor button polling');
    async function checkComposer(){
    ui._openDialog();await sleep(150);
    const initialHeight=ui._inputScroll.height;
    const text=('Zażółć gęślą jaźń — abcdefghijklmnopqrstuvwxyz 0123456789. ').repeat(18)+'\nKoniec, zachowaj kolejność.';
    ui._entry.set_text(text);await sleep(300);
    const lines=ui._entry.clutter_text.get_layout().get_line_count();
    const fourLineHeight=ui._inputScroll.height;
    assert(lines>4,'Long text failed to wrap');
    assert(fourLineHeight>initialHeight,'Composer did not grow');
    assert(ui._inputScroll.vadjustment.upper>ui._inputScroll.vadjustment.page_size,'Long input failed to scroll');
    assert(ui._entry.get_text()===text,'Wrapping altered text');
    const stream=Gio.File.new_for_path(`${root}/evidence/dialog-four-lines.png`).replace(null,false,Gio.FileCreateFlags.NONE,null);
    await new Shell.Screenshot().screenshot(false,stream);stream.close(null);
    ui._entry.clutter_text.cursor_position=-1;await sleep(150);
    assert(ui._inputScroll.vadjustment.value>0,'Caret at end did not scroll');
    const scrollValue=ui._inputScroll.vadjustment.value;
    ui._entry.clutter_text.cursor_position=0;await sleep(150);
    assert(ui._inputScroll.vadjustment.value<scrollValue,'Caret at start did not scroll back');
    ui._send();assert(calls.findLast(c=>c.method==='SendText').p.text===text,'SendText changed order or lost text');
    assert(ui._entry.get_text()==='','Accepted message not cleared');
    const originalCall=ui._call;let accept,reject;
    ui._call=(method,p={},cb=null,error=null)=>{if(method==='SendText'){accept=cb;reject=error;}else originalCall(method,p,cb);};
    ui._entry.set_text('Odrzucony tekst pozostaje');ui._send();reject('Syntetyczne odrzucenie');
    assert(ui._entry.get_text()==='Odrzucony tekst pozostaje','Rejected message was lost');
    ui._send();ui._event('ReplyDelta',{turn:'old-turn',delta:'OLD_FRAGMENT'});ui._event('ReplyDelta',{turn:'new-turn',delta:'NEW_FRAGMENT'});accept('new-turn');
    assert(ui._text.text.includes('NEW_FRAGMENT')&&!ui._text.text.includes('OLD_FRAGMENT'),'Mixed old/new reply fragments');
    ui._event('ReplyDelta',{turn:'old-turn',delta:'LATE_OLD'});assert(!ui._text.text.includes('LATE_OLD'),'Late obsolete delta displayed');
    ui._cancelResponse();ui._event('ReplyDelta',{turn:'new-turn',delta:'AFTER_CANCEL'});assert(!ui._text.text.includes('AFTER_CANCEL'),'Cancelled delta displayed');
    ui._entry.set_text('Wysłany tekst');ui._send();ui._entry.set_text('Nowy szkic');accept('next-turn');
    assert(ui._entry.get_text()==='Nowy szkic','Accepted previous send erased newer draft');
    ui._call=originalCall;
    ui._entry.set_text('Pierwsza\nDruga\nTrzecia\nCzwarta');await sleep(200);const four=ui._inputScroll.height;
    ui._entry.set_text('Pierwsza\nDruga\nTrzecia\nCzwarta\nPiąta\nSzósta');await sleep(200);
    assert(Math.abs(ui._inputScroll.height-four)<2,'Composer grew past four lines');
    ui._entry.set_text('Krótko');await sleep(200);assert(ui._inputScroll.height<four,'Composer failed to shrink');
    let history;
    ui._call=(method,p={},cb=null)=>{if(method==='GetLatestExchange')history=cb;else originalCall(method,p,cb);};
    ui._openDialog();ui._entry.set_text('Nowe pytanie');ui._send();history([{body:{role:'assistant',text:'STALE_HISTORY'}}]);
    assert(ui._text.text.includes('Nowe pytanie')&&!ui._text.text.includes('STALE_HISTORY'),'Delayed history overwrote new question');ui._call=originalCall;
    const proxy=ui._proxy,shown=ui._text.text;let remoteCallback;
    ui._proxy={g_name_owner:'synthetic',CallRemote:(_method,_raw,cb)=>remoteCallback=cb};
    Companion.prototype._call.call(ui,'SendText',{},null,()=>{});
    remoteCallback([JSON.stringify({ok:false,error:'STALE_SEND_ERROR'})],null);
    assert(ui._text.text===shown,'Obsolete send error changed current exchange');ui._proxy=proxy;
    ui._entry.set_text('');global.stage.set_key_focus(ui._entry.clutter_text);await sleep(100);
    async function key(symbol){keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.PRESSED);await sleep(30);keyboard.notify_keyval(GLib.get_monotonic_time(),symbol,Clutter.KeyState.RELEASED);await sleep(80);}
    await key(Clutter.KEY_a);assert(ui._entry.get_text()==='a','Virtual keyboard did not type into Shell composer');
    keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.PRESSED);await key(Clutter.KEY_Return);
    keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Shift_L,Clutter.KeyState.RELEASED);await sleep(100);
    assert(ui._entry.get_text()==='a\n','Shift+Enter did not retain newline');
    await key(Clutter.KEY_b);
    keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.PRESSED);await key(Clutter.KEY_a);await key(Clutter.KEY_c);
    keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.RELEASED);await sleep(100);
    ui._entry.set_text('');keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.PRESSED);await key(Clutter.KEY_v);
    keyboard.notify_keyval(GLib.get_monotonic_time(),Clutter.KEY_Control_L,Clutter.KeyState.RELEASED);await sleep(200);
    assert(ui._entry.get_text()==='a\nb','Ctrl+C/Ctrl+V changed multiline clipboard text');
    await key(Clutter.KEY_Return);
    assert(calls.findLast(c=>c.method==='SendText').p.text==='a\nb','Enter did not submit exact multiline input');
    await key(Clutter.KEY_Escape);assert(!ui._dialog&&calls.findLast(c=>c.method==='CancelResponse'),'Escape did not cancel and close');
    return {long_text_chars:text.length,wrapped_lines:lines,initial_height:initialHeight,four_line_height:fourLineHeight,send_text_exact:true,scroll_cursor_both_directions:true,rejected_text_preserved:true,old_reply_filtered:true,newer_draft_preserved:true,delayed_history_filtered:true,virtual_keyboard_type_shift_enter_send_escape:true,virtual_keyboard_multiline_copy_paste:true};
    }
    ui.disable();assert(ui._sources.size===0,'Timers leaked after disable');
    global.stage.disconnect(debugSignal);
    client.force_exit();theme.unload_stylesheet(css);
    const [,bytes]=Gio.File.new_for_path(GLib.getenv('ZENEK_TEST_CLICK_FILE')).load_contents(null);
    const clicks=JSON.parse(new TextDecoder().decode(bytes)).clicks;
    assert(clicks>=3,'Both outside clicks were not delivered to native client');
    print('ZENEK_DIALOG_UAT '+JSON.stringify({status:'PASS',focused_outside_source:focusedSource,passive_same_window_source:passiveSource,native_client_clicks:clicks,...composer,no_watcher_after_close:true,no_timers_after_disable:true}));
}
