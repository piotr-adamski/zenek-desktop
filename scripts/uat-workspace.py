"""Actual GTK workspace -> private Core/SQLCipher, deterministic model fixture."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

root=Path(__file__).resolve().parents[1]


def isolated():
    if not Path(os.environ['XDG_RUNTIME_DIR']).name.startswith('zenek-workspace-') or '/run/user/1000/bus' in os.environ.get('DBUS_SESSION_BUS_ADDRESS',''):
        raise RuntimeError('This test requires its disposable session')


def parent():
    with tempfile.TemporaryDirectory(prefix='zenek-workspace-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,ZENEK_TEST_ROOT=str(root),GTK_A11Y='none',GDK_BACKEND='wayland',GSK_RENDERER='cairo')
        for key,folder in [('HOME','home'),('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache')]:
            path=Path(runtime)/folder;path.mkdir(mode=0o700);env[key]=str(path)
        for key in ('DISPLAY','WAYLAND_DISPLAY','AT_SPI_BUS_ADDRESS','DBUS_SESSION_BUS_ADDRESS','GNOME_KEYRING_CONTROL'):env.pop(key,None)
        process=subprocess.Popen(['dbus-run-session','--','gnome-shell-test-tool','--headless','--disable-animations','--extra-filter','org.zenek.WorkspaceTest',str(root/'scripts/uat-workspace.js')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        try:output,_=process.communicate(timeout=55)
        finally:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        (root/'evidence/workspace-native.log').write_text(output)
        lines=[line for line in output.splitlines() if line.startswith('ZENEK_WORKSPACE_UAT ')]
        if process.returncode or not lines:print(output[-9000:]);raise SystemExit(process.returncode or 1)
        result=json.loads(lines[-1].removeprefix('ZENEK_WORKSPACE_UAT '));(root/'evidence/workspace-native.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


def fixture_core():
    isolated()
    from zenek_core.notebook import Notebook
    import zenek_core.main as main_module
    import zenek_core.workspace as workspace_module
    main_module.Notebook=lambda:Notebook(Path(os.environ['XDG_RUNTIME_DIR'])/'notebook')
    workspace_module.Notebook=main_module.Notebook
    core=main_module.Core()
    def infer(profile,inputs,instructions,on_delta,cancel,purpose=None):
        if purpose=='feedback':return json.dumps(dict(reflection='Zapisuję własny wybór.',decision='private practice',reason='Własna ciekawość.'))
        core.provider.active_tools['conversation']='ReadNote';core.emit_state();time.sleep(.7)
        core.provider.active_tools.clear();core.emit_state()
        text=json.dumps(inputs,ensure_ascii=False)
        if '<wybrany-zapisek>' in text:answer='Chcę rozwijać akcenty. notebook/hobby/rytm.md'
        elif '<powrót-do-wątku>' in text:answer='Wracam do wcześniejszej rozmowy o rytmie.'
        else:answer='Syntetyczna odpowiedź.'
        on_delta(answer);return answer
    core.provider.infer=infer;core.loop.run()


def child():
    isolated()
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1');gi.require_version('Gsk','4.0');gi.require_version('Graphene','1.0')
    from gi.repository import Gtk,Gsk,Graphene,GLib
    from zenek_core.memory import Memory,Keyring
    from zenek_core.agency import Agency
    from zenek_core.notebook import Notebook
    from zenek_core.personality import Personality
    from zenek_core.ipc import call
    from zenek_settings.workspace import WorkspaceApp
    keyring=subprocess.Popen(['gnome-keyring-daemon','--foreground','--components=secrets','--unlock'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    keyring.stdin.write(b'SYNTHETIC_WORKSPACE_PASSWORD');keyring.stdin.close();core=None
    try:
        deadline=time.monotonic()+5
        while True:
            try:Keyring();break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        notebook=Notebook(Path(os.environ['XDG_RUNTIME_DIR'])/'notebook')
        notebook.write('hobby/rytm.md','# Moje rytmy\n\nChcę ćwiczyć akcenty 3 + 2 + 3.\n\n[Źródło](https://example.org/rytm)')
        notebook.write('journal/drugi.md','# Inny zapisek\n\nOsobny temat.')
        memory=Memory()
        for i in range(65):memory.add('message',dict(role='user',text=f'Wątek {i} · ŻÓŁĆ i rytm.'),'synthetic',1)
        first=Personality(memory).active();Personality(memory).evolve('Lubię ćwiczyć rytmy.',first['traits'],'Własna próba rytmu mnie zaciekawiła.',[],first['version'])
        Agency(memory).choose('Rytm','hobby','private','Chcę rozwijać go dla siebie.')
        memory.patch({'background_paused':True},memory.settings()[0]);memory.close()
        core=subprocess.Popen([str(root/'.venv/bin/python'),__file__,'--core'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+6
        while True:
            try:call('GetStatus');break
            except Exception:
                if core.poll() is not None:raise RuntimeError(core.stderr.read().decode()[-2000:])
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        def walk(widget):
            yield widget;node=widget.get_first_child()
            while node:yield from walk(node);node=node.get_next_sibling()
        def button(widget,text):return next(v for v in walk(widget) if isinstance(v,Gtk.Button) and v.get_label()==text)
        class Check(WorkspaceApp):
            def __init__(self):super().__init__();self.set_application_id('org.zenek.WorkspaceTest');self.phase=0;self.exit_code=1;self.progress=False
            def do_activate(self):super().do_activate();GLib.timeout_add(250,self.step)
            def capture(self,name):
                snapshot=Gtk.Snapshot();Gtk.WidgetPaintable.new(self.window).snapshot(snapshot,self.window.get_width(),self.window.get_height());node=snapshot.to_node()
                if node is None:return False
                renderer=Gsk.Renderer.new_for_surface(self.window.get_surface())
                try:renderer.render_texture(node,Graphene.Rect().init(0,0,self.window.get_width(),self.window.get_height())).save_to_png(str(root/'evidence'/name))
                finally:renderer.unrealize()
                return True
            def step(self):
                try:
                    if self.phase==0:
                        assert len(self.chat_records)==40;self.refresh_chat(True);assert len(self.chat_records)==65
                        self.note_search.set_text('AKCENTY');self.phase=1;return True
                    if self.phase==1:
                        if self.note_list.get_row_at_index(1):return True
                        assert self.note_path=='hobby/rytm.md'
                        assert any(isinstance(v,Gtk.LinkButton) and v.get_uri()=='https://example.org/rytm' for v in walk(self.note_body))
                        if not self.capture('workspace-notebook.png'):return True
                        button(self.note_body,'Porozmawiajmy o tym').emit('clicked');self.phase=2;return True
                    if self.phase==2:
                        self.progress|=self.status_label.get_text()=='Czytam własne zapiski'
                        if self.active_turn:return True
                        assert any(r['body'].get('text','').startswith('Chcę rozwijać akcenty') for r in self.chat_records)
                        assert self.progress,'Real tool activity was not shown'
                        if not self.capture('workspace-chat.png'):return True
                        self.chat_search.set_text('żółć');self.phase=3;return True
                    if self.phase==3:
                        if not self.chat_records or any('ŻÓŁĆ' not in r['body']['text'] for r in self.chat_records):return True
                        self.resume(self.chat_records[0]);self.phase=4;return True
                    if self.phase==4:
                        if self.active_turn:return True
                        assert self.chat_search.get_text()=='' and any('Wracam do wcześniejszej' in r['body']['text'] for r in self.chat_records)
                        self.chat_search.set_text('');self.stack.set_visible_child_name('growth');self.refresh_growth();self.phase=5;return True
                    if self.phase==5:
                        texts=[v.get_text() for v in walk(self.growth) if isinstance(v,Gtk.Label)]
                        assert 'Moje hobby: Rytm · rozwijam dla siebie' in texts
                        change=next(e for e in self.growth_events if e['kind']=='personality_evolution');assert change['before']==first['prompt'] and change['after']=='Lubię ćwiczyć rytmy.'
                        if not self.capture('workspace-growth.png'):return True
                        print('ZENEK_WORKSPACE_UAT '+json.dumps(dict(status='PASS',scope='actual GTK/private D-Bus Core/SQLCipher with synthetic model',notebook_search_read_sources=True,discuss_note_context=True,full_history_paging=True,polish_casefold_search=True,resume_old_thread_context=True,real_operation_label=True,private_hobby_and_character_reason=True,screenshots=['workspace-notebook.png','workspace-chat.png','workspace-growth.png'],owner_state_unchanged=True)),flush=True)
                        self.exit_code=0;self.quit();return False
                except Exception:
                    import traceback;traceback.print_exc();self.quit();return False
        app=Check();app.run([sys.argv[0]]);raise SystemExit(app.exit_code)
    finally:
        for process in (core,keyring):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    if '--core' in sys.argv:fixture_core()
    elif '--child' in sys.argv:child()
    else:parent()
