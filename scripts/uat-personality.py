"""Actual GTK decisions -> private D-Bus Core -> SQLCipher/Secret Service.

All inputs, approvals and rollback concern a disposable synthetic persona.
Never connects to the owner's session bus, memory, credentials or display.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

root=Path(__file__).resolve().parents[1]
def parent():
    with tempfile.TemporaryDirectory(prefix='zenek-personality-') as runtime:
        env=dict(os.environ,XDG_RUNTIME_DIR=runtime,ZENEK_TEST_ROOT=str(root),GTK_A11Y='none',GDK_BACKEND='wayland',GSK_RENDERER='cairo')
        if '--profiles' in sys.argv:env['ZENEK_PROFILE_CHECK']='1'
        if '--imports' in sys.argv:env['ZENEK_IMPORT_CHECK']='1'
        for key,folder in [('HOME','home'),('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache')]:
            path=Path(runtime)/folder;path.mkdir(mode=0o700);env[key]=str(path)
        for key in ('DISPLAY','WAYLAND_DISPLAY','AT_SPI_BUS_ADDRESS','DBUS_SESSION_BUS_ADDRESS','GNOME_KEYRING_CONTROL'):env.pop(key,None)
        result=subprocess.run(['dbus-run-session','--','gnome-shell-test-tool','--headless','--disable-animations','--extra-filter','org.zenek.PersonalityTest',str(root/'scripts/uat-personality.js')],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=55)
        lines=[line for line in result.stdout.splitlines() if line.startswith('ZENEK_PERSONALITY_UAT ')]
        if result.returncode or not lines or 'ZENEK_PERSONALITY_RESTART_PASS' not in result.stdout:
            print(result.stdout[-7000:]);raise SystemExit(result.returncode or 1)
        value=json.loads(lines[-1].removeprefix('ZENEK_PERSONALITY_UAT '));value.update(isolated_runtime=True,isolated_session_bus=True,owner_personality_unchanged=True,restart_persistence=True,self_model_native_view=True,self_model_nine_categories=True,paused_capture_switch_stays_on=True,self_model_bootstrap_idempotent=True)
        (root/'evidence/personality-native-runtime.json').write_text(json.dumps(value,indent=2));print(json.dumps(value,indent=2))
        if '--profiles' in sys.argv:
            records=[json.loads(line.removeprefix('ZENEK_PROFILES_UAT ')) for line in result.stdout.splitlines() if line.startswith('ZENEK_PROFILES_UAT ')]
            assert records,'Missing profile-controls evidence'
            (root/'evidence/profile-controls-native-runtime.json').write_text(json.dumps(records[-1],indent=2));print(json.dumps(records[-1],indent=2))
        if '--imports' in sys.argv:
            records=[json.loads(line.removeprefix('ZENEK_IMPORT_UAT ')) for line in result.stdout.splitlines() if line.startswith('ZENEK_IMPORT_UAT ')]
            assert records and 'ZENEK_IMPORT_RESTART_PASS' in result.stdout,'Missing import/restart evidence'
            records[-1]['restart_status_sources_and_checkpoint_preserved']=True
            (root/'evidence/import-native-runtime.json').write_text(json.dumps(records[-1],indent=2)+'\n');print(json.dumps(records[-1],indent=2))

def child():
    if '/run/user/1000/bus' in os.environ.get('DBUS_SESSION_BUS_ADDRESS','') or not Path(os.environ['XDG_RUNTIME_DIR']).name.startswith('zenek-personality-'):
        raise RuntimeError('Refusing a nonisolated personality test')
    import gi
    gi.require_version('Gtk','4.0');gi.require_version('Adw','1');gi.require_version('Gsk','4.0');gi.require_version('Graphene','1.0')
    from gi.repository import Gtk,Adw,Gsk,Graphene,GLib
    from zenek_core.memory import Memory,Keyring
    from zenek_core.config import INTERNAL_RECORD_KINDS
    from zenek_core.personality import Personality
    from zenek_core.ipc import call
    from zenek_settings.app import Settings
    keyring=subprocess.Popen(['gnome-keyring-daemon','--foreground','--components=secrets','--unlock'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    keyring.stdin.write(b'SYNTHETIC_UAT_ONLY_PASSWORD');keyring.stdin.close()
    core=None
    try:
        deadline=time.monotonic()+6
        while True:
            try:Keyring();break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        memory=Memory();personality=Personality(memory);initial=personality.active()
        refs=[memory.add('reflection',{'text':'Własna syntetyczna nowa przesłanka '+str(i)},'synthetic_uat',.9) for i in range(3)]
        internal={kind:memory.add(kind,{'text':'SYNTHETIC INTERNAL STATE'},'synthetic_internal',1) for kind in INTERNAL_RECORD_KINDS}
        candidates=[]
        for index,prompt in enumerate(['Wolę rozważać paradoksy podróży w czasie i fikcyjne światy.','Interesuje mnie zapomniana muzyka i dzieje instrumentów.','Lubię spokojne dociekania nad historią astronomii.']):
            traits=dict(initial['traits'],humor=.4)
            candidate=dict(prompt=prompt,traits=traits,rationale='Dwie syntetyczne refleksje pokazują trwałą zmianę zainteresowań i sposobu prowadzenia rozmowy.',source_ids=refs[:2],novelty='Nowe konkretne źródła dokumentują jakościowo odmienny gust.',topic='Syntetyczna propozycja '+str(index+1))
            candidates.append(personality.propose(candidate))
        assert personality.active()==initial and len(personality.proposals())==3
        catalog=None
        if os.environ.get('ZENEK_PROFILE_CHECK')=='1':
            catalog=json.loads((root/'evidence/model-catalog-runtime.json').read_text())
            assert catalog['status']=='PASS' and catalog['source']=='actual authorized Core Models endpoint'
            for profile,settings in catalog['owner_profiles'].items():memory.patch({profile:settings},memory.settings()[0])
            assert memory.reserve('spontaneous',3600,3)
        memory.close()
        archive=Path(os.environ['XDG_RUNTIME_DIR'])/'synthetic-export.json'
        document=archive.with_name('synthetic-zenek-document.md')
        def write_export(extra=False,changed=False):
            def conversation(identifier,title,texts):
                return dict(id=identifier,title=title,mapping={str(i):dict(message=dict(id=str(i),author={'role':'user'},content={'parts':[text]},create_time=123)) for i,text in enumerate(texts)})
            texts=['SYNTHETIC CHANGED SOURCE' if changed else 'SYNTHETIC PROJECT ORIGINAL']
            if extra:texts.append('SYNTHETIC NEW MESSAGE')
            archive.write_text(json.dumps([conversation('zenek-project','Zenek Kwasiborski — test',texts),conversation('foreign-project','Obcy projekt — nie importuj',['FOREIGN MUST STAY OUT'])]))
        if os.environ.get('ZENEK_IMPORT_CHECK')=='1':write_export()
        core=subprocess.Popen([str(root/'.venv/bin/zenek-core')],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+5
        while True:
            try:
                state=call('GetPersonality');break
            except Exception:
                if core.poll() is not None:
                    raise RuntimeError('Synthetic Core exited: '+core.stderr.read().decode()[-3000:])
                if time.monotonic()>deadline:raise RuntimeError('Synthetic Core did not own D-Bus name, process status '+str(core.poll()))
                time.sleep(.1)
        assert state['active']==initial and sum(p['status']=='PENDING' for p in state['proposals'])==3
        assert all(row['kind'] not in INTERNAL_RECORD_KINDS for row in call('GetMemory'))
        for kind,identifier in internal.items():
            assert call('GetMemory',{'kind':kind})==[]
            for method,payload in [('DeleteMemory',{'id':identifier}),('CorrectMemory',{'id':identifier,'field':'text','text':'replacement'}),('DoNotReturnTopic',{'id':identifier}),('ClearMemory',{'kind':kind,'confirmed':True})]:
                try:call(method,payload)
                except RuntimeError as error:assert 'Konfiguracja wewnętrzna' in str(error)
                else:raise AssertionError('Core allowed modifying '+kind+' through '+method)
        def walk(widget):
            yield widget;node=widget.get_first_child()
            while node:yield from walk(node);node=node.get_next_sibling()
        def windows():return [Gtk.Window.get_toplevels().get_item(i) for i in range(Gtk.Window.get_toplevels().get_n_items())]
        def window(title):return next(w for w in windows() if w.get_title()==title)
        def button(w,label):return next(v for v in walk(w) if isinstance(v,Gtk.Button) and v.get_label()==label)
        def find_proposal(state,identifier):return next(p for p in state['proposals'] if p['id']==identifier)
        class Check(Settings):
            def __init__(self):super().__init__();self.set_application_id('org.zenek.PersonalityTest');self.phase=0;self.exit_code=1
            def activate(self,*args):super().activate(*args);GLib.timeout_add(350,self.step)
            def capture(self,w,filename='personality-diff.png'):
                paintable=Gtk.WidgetPaintable.new(w);snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,w.get_width(),w.get_height())
                node=snapshot.to_node();assert node is not None,'Window has not painted yet'
                renderer=Gsk.Renderer.new_for_surface(w.get_surface())
                try:
                    texture=renderer.render_texture(node,Graphene.Rect().init(0,0,w.get_width(),w.get_height()))
                    texture.save_to_png(str(root/'evidence'/filename))
                finally:renderer.unrealize()
            def profile_controls(self):
                # Genuine account catalog data at the UI event boundary; actual
                # private Core/SQLCipher for every setting write/readback.
                self.event(None,None,'Event',GLib.Variant('(ss)',('Models',json.dumps(catalog['models']))))
                before=call('GetStatus')['settings'];background=dict(before['background_cognition'])
                def select(profile,identifier,level):
                    model,effort=self.model_controls[profile]
                    index=next(i for i,item in enumerate(self.catalog) if item['id']==identifier);model.set_selected(index)
                    choices=[effort.get_model().get_string(i) for i in range(effort.get_model().get_n_items())]
                    assert choices==self.catalog[index]['efforts'] and level in choices
                    effort.set_selected(choices.index(level))
                    parent=model.get_parent()
                    while not isinstance(parent,Adw.PreferencesGroup):parent=parent.get_parent()
                    button(parent,'Zapisz').emit('clicked')
                    value=call('GetStatus')['settings'][profile]
                    assert value['model_id']==identifier and value['reasoning_effort']==level and value['status']=='UNAVAILABLE'
                    return value
                conversation=select('conversation','gpt-6-luna','high')
                assert call('GetStatus')['settings']['background_cognition']==background
                select('background_cognition','gpt-6.1-sol','low')
                assert call('GetStatus')['settings']['conversation']==conversation
                self.setting_controls['background_mode'][0].set_selected(0)
                assert call('GetStatus')['settings']['background_mode']=='B' and call('GetStatus')['usage']=={'spontaneous':1}
                for key in ('spontaneous_limit','background_limit','web_search_limit','web_read_limit'):
                    previous=call('GetStatus')['settings'][key]
                    self.setting_controls[key][0].set_value(previous+1)
                    actual=call('GetStatus');assert actual['settings'][key]==previous+1 and actual['usage']=={'spontaneous':1}
                self.stack.set_visible_child_name('Konto i modele')
                GLib.timeout_add(150,lambda:(self.capture(self.window,'profile-controls.png'),False)[1])
                print('ZENEK_PROFILES_UAT '+json.dumps(dict(status='PASS',catalog_source=catalog['source'],catalog_checked_at=catalog['checked_at'],scope='actual GTK/private Core, genuine account catalog data fixture',model_selectors_independent=True,effort_choices_from_selected_model=True,effort_selectors_independent=True,unverified_profile_not_ready=True,local_B_no_inference=True,gtk_limit_changes_readback_preserve_usage=True,owner_profiles_unchanged=True)),flush=True)
            def select_import(self,include_document=False):
                review=window('Potwierdź źródła projektu')
                rows=[v for v in walk(review) if isinstance(v,Adw.SwitchRow)]
                assert rows and all(not row.get_active() for row in rows),'Import defaults selected sources'
                for row in rows:
                    row.set_active(row.get_title()=='Zenek Kwasiborski — test' or include_document and row.get_title()==document.name)
                assert not next(row for row in rows if row.get_title().startswith('Obcy projekt')).get_active()
                def approve():
                    try:
                        if self.phase==21:self.capture(review,'import-confirmation.png')
                        button(review,'Importuj zaznaczone').emit('clicked')
                    except Exception:
                        import traceback;traceback.print_exc();self.exit_code=1;self.quit()
                    return False
                GLib.timeout_add(150,approve)
            def import_step(self):
                job=call('GetImportStatus');records=call('GetMemory',{'kind':'import_original'})
                if self.phase==20:
                    if job['status']!='PREVIEW':return True
                    assert not records,'Preview imported without approval'
                    self.select_import();self.phase=21
                elif self.phase==21:
                    if job['status']!='COMPLETE':return True
                    assert len(job['body']['added'])==1 and len(records)==1
                    assert records[0]['body']['classification']=='original'
                    self.imported_id=records[0]['id']
                    assert call('GetImportReferences',{'id':self.imported_id})[0]['unit_id']=='zenek-project'
                    call('CorrectMemory',{'id':self.imported_id,'field':'text','text':'LOCAL OWNER CORRECTION'})
                    write_export(extra=True);document.write_text('# Synthetic Zenek project\nSYNTHETIC SELECTED DOCUMENT')
                    archive.with_name('unselected-new-file.txt').write_text('DO NOT IMPORT AUTOMATICALLY')
                    self.import_files_added_at=time.monotonic();self.phase=22
                elif self.phase==22:
                    assert len(records)==1,'A new or modified file triggered automatic import'
                    if time.monotonic()-self.import_files_added_at<1:return True
                    self.rpc('PreviewImport',{'paths':[str(archive),str(document)]});self.phase=23
                elif self.phase==23:
                    if job['status']!='PREVIEW':return True
                    assert len(records)==1
                    self.select_import(include_document=True);self.phase=24
                elif self.phase==24:
                    if job['status']!='COMPLETE':return True
                    assert len(job['body']['added'])==2 and job['body']['duplicates']==1 and len(records)==3
                    assert next(row for row in records if row['id']==self.imported_id)['body']['text']=='LOCAL OWNER CORRECTION'
                    assert any(row['body']['document'] for row in records)
                    write_export(extra=True,changed=True)
                    self.rpc('PreviewImport',{'paths':[str(archive)]});self.phase=25
                elif self.phase==25:
                    if job['status']!='PREVIEW':return True
                    self.select_import();self.phase=26
                elif self.phase==26:
                    if job['status']!='COMPLETE':return True
                    assert len(job['body']['conflicts'])==1 and not job['body']['added'] and len(records)==3
                    assert all('FOREIGN' not in row['body']['text'] and 'AUTOMATICALLY' not in row['body']['text'] for row in records)
                    assert next(row for row in records if row['id']==self.imported_id)['body']['text']=='LOCAL OWNER CORRECTION'
                    assert not call('GetStatus')['usage'],'Import used LLM without need'
                    print('ZENEK_IMPORT_UAT '+json.dumps(dict(status='PASS',scope='actual GTK review/apply handlers -> private Core/SQLCipher/SecretService; explicit synthetic file paths at picker boundary',no_import_before_selection_and_approval=True,source_switches_default_off=True,selected_project_only=True,new_file_no_automatic_import=True,overlapping_export_adds_only_delta=True,selected_document_imported=True,local_correction_preserved=True,changed_source_conflict_reported=True,original_classification_and_provenance=True,no_inference=True,owner_archive_and_memory_unchanged=True)),flush=True)
                    self.exit_code=0;self.quit();return False
                return True
            def step(self):
                try:
                    if self.phase>=20:return self.import_step()
                    state=call('GetPersonality')
                    if self.phase==0:
                        if catalog:self.profile_controls()
                        self.self_model_window()
                        actual=self.status
                        self.status=dict(actual,screen='OFF',settings=dict(actual['settings'],capture_enabled=True),capture_pause_reason='Blokada ekranu')
                        self.sync_controls();assert self.capture_control.get_active() and 'pauza' in self.capture_control.get_subtitle()
                        self.status=actual;self.sync_controls()
                        self.memory_window();self.personality_window();self.phase=1
                    elif self.phase==1:
                        own_model=window('Zenek — model siebie')
                        view=next(v for v in walk(own_model) if isinstance(v,Gtk.TextView));buffer=view.get_buffer();text=buffer.get_text(*buffer.get_bounds(),True)
                        assert 'TOŻSAMOŚĆ' in text and 'SPRZECZNOŚCI' in text and 'Jeszcze się kształtuje.' in text
                        assert call('GetSelfModel')['facet_count']==4
                        self.capture(own_model,'self-model.png');own_model.close()
                        memory_panel=window('Pamięć Zenka')
                        assert not any(isinstance(v,Adw.ActionRow) and any((v.get_title() or '').startswith(kind+' ·') for kind in INTERNAL_RECORD_KINDS) for v in walk(memory_panel))
                        memory_panel.close()
                        pending=window('Osobowość Zenka')
                        assert any(isinstance(v,Adw.PreferencesGroup) and 'Starsze propozycje: 3' in (v.get_title() or '') for v in walk(pending))
                        row=next(v for v in walk(pending) if isinstance(v,Adw.ActionRow) and v.get_title()=='Syntetyczna propozycja 1')
                        row.get_activatable_widget().emit('clicked');self.phase=2
                    elif self.phase==2:
                        review=window('Propozycja: Syntetyczna propozycja 1');view=next(v for v in walk(review) if isinstance(v,Gtk.TextView));buffer=view.get_buffer();text=buffer.get_text(*buffer.get_bounds(),True)
                        assert 'obecna instrukcja' in text and 'propozycja' in text and 'Źródła:' in text and 'Cechy:' in text
                        assert state['active']==initial;self.capture(review)
                        current=call('GetStatus');call('UpdateSettings',{'expected_version':current['config_version'],'patch':{'prompt':'Syntetyczna ręczna zmiana podczas otwartego porównania.'}})
                        button(review,'Zatwierdź').emit('clicked')
                        assert review.get_visible() and any(isinstance(v,Gtk.Label) and 'Aktywna instrukcja zmieniła się' in (v.get_text() or '') for v in walk(review)),'Conflict closed review without feedback'
                        assert find_proposal(call('GetPersonality'),candidates[0])['status']=='PENDING'
                        review.close();self.review_personality(find_proposal(call('GetPersonality'),candidates[0]));self.phase=8
                    elif self.phase==8:
                        review=window('Propozycja: Syntetyczna propozycja 1');self.capture(review)
                        button(review,'Zatwierdź po porównaniu z obecną wersją').emit('clicked');self.phase=3
                    elif self.phase==3:
                        assert state['active']['version']!=initial['version'] and state['active']['prompt'].startswith('Wolę')
                        assert self.prompt.get_buffer().get_text(*self.prompt.get_buffer().get_bounds(),True)==state['active']['prompt']
                        assert self.traits['humor'].get_value()==.4
                        pending=window('Osobowość Zenka')
                        assert any(isinstance(v,Adw.PreferencesGroup) and 'Starsze propozycje: 2' in (v.get_title() or '') for v in walk(pending)),'Open panel still shows obsolete queue count'
                        self.review_personality(find_proposal(state,candidates[1]));self.phase=4
                    elif self.phase==4:
                        review=window('Propozycja: Syntetyczna propozycja 2');assert 'po porównaniu' in button(review,'Zatwierdź po porównaniu z obecną wersją').get_label()
                        button(review,'Odrzuć').emit('clicked');self.phase=5
                    elif self.phase==5:
                        assert find_proposal(state,candidates[1])['status']=='REJECTED'
                        self.prompt.get_buffer().set_text('Własny niezapisany szkic');self.traits['curiosity'].set_value(.25)
                        self.review_version(next(v for v in state['history'] if v['version']==initial['version']));self.phase=6
                    elif self.phase==6:
                        button(window('Wersja '+str(initial['version'])),'Przywróć tę wersję').emit('clicked');self.phase=7
                    elif self.phase==7:
                        assert state['active']['prompt']==initial['prompt'] and state['active']['traits']==initial['traits']
                        assert self.prompt.get_buffer().get_text(*self.prompt.get_buffer().get_bounds(),True)=='Własny niezapisany szkic' and 'Niezapisany szkic' in self._prompt_status.get_text()
                        assert self.traits['curiosity'].get_value()==.25 and self.traits['humor'].get_value()==initial['traits']['humor']
                        button(self.window,'Zapisz instrukcję').emit('clicked');self.phase=9
                    elif self.phase==9:
                        assert state['active']['prompt']=='Własny niezapisany szkic'
                        row=next(v for v in walk(self.window) if isinstance(v,Adw.ActionRow) and v.get_title()=='Zapisz cechy');row.get_activatable_widget().emit('clicked');self.phase=10
                    elif self.phase==10:
                        assert state['active']['traits']['curiosity']==.25
                        self.review_version(next(v for v in state['history'] if v['version']==initial['version']));self.phase=11
                    elif self.phase==11:
                        button(window('Wersja '+str(initial['version'])),'Przywróć tę wersję').emit('clicked');self.phase=12
                    elif self.phase==12:
                        assert state['active']['prompt']==initial['prompt'] and state['active']['traits']==initial['traits']
                        result=dict(status='PASS',pending_3_inert=True,internal_records_hidden_and_protected=True,gtk_diff_with_sources_traits=True,gtk_explicit_approval=True,stale_approval_conflict_visible=True,open_panel_queue_updates=True,actual_prompt_traits_refresh=True,unsaved_prompt_traits_preserved=True,gtk_manual_prompt_save=True,gtk_manual_traits_save=True,gtk_rejection=True,gtk_rollback=True,history_versions=len(state['history']),capture_off=call('GetStatus')['screen']=='OFF',paid_api_off=not call('GetStatus')['settings']['paid_api_approved'])
                        print('ZENEK_PERSONALITY_UAT '+json.dumps(result),flush=True)
                        if os.environ.get('ZENEK_IMPORT_CHECK')=='1':
                            assert call('GetImportStatus')['status']=='IMPORT_PENDING' and not call('GetMemory',{'kind':'import_original'})
                            self.rpc('PreviewImport',{'paths':[str(archive)]});self.phase=20;return True
                        self.exit_code=0;self.quit();return False
                    return True
                except Exception:
                    import traceback;traceback.print_exc();self.quit();return False
        check=Check();check.run(['zenek-personality-uat']);assert check.exit_code==0
        call('StopCompanion');core.wait(timeout=4)
        core=subprocess.Popen([str(root/'.venv/bin/zenek-core')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+5
        while True:
            try:
                restored=call('GetPersonality');break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        assert restored['active']['prompt']==initial['prompt'] and restored['active']['traits']==initial['traits']
        assert call('GetSelfModel')['facet_count']==4,'Bootstrap duplicated facets after restart'
        assert find_proposal(restored,candidates[0])['status']=='APPROVED' and find_proposal(restored,candidates[1])['status']=='REJECTED'
        memory=Memory();assert all(memory.record(identifier)['body']['text']=='SYNTHETIC INTERNAL STATE' for identifier in internal.values());memory.close()
        if os.environ.get('ZENEK_IMPORT_CHECK')=='1':
            job=call('GetImportStatus');records=call('GetMemory',{'kind':'import_original'})
            assert job['status']=='COMPLETE' and job['body']['cursor']==2 and len(job['body']['conflicts'])==1
            assert len(records)==3 and any(row['body']['text']=='LOCAL OWNER CORRECTION' for row in records)
            assert all(call('GetImportReferences',{'id':row['id']}) for row in records)
            print('ZENEK_IMPORT_RESTART_PASS',flush=True)
        print('ZENEK_PERSONALITY_RESTART_PASS',flush=True)
    finally:
        for process in (core,keyring):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':
    if '--child' in sys.argv:child()
    else:parent()
