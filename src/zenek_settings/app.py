import json
import subprocess
import sys
import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gio,GLib,Gdk
from zenek_core.ipc import call,proxy
from zenek_core.config import DEFAULTS,BASE_PROMPT,INTERNAL_RECORD_KINDS
from zenek_core.personality import prompt_diff

SWITCH_EFFECTS={
    'autostart':('Zenek uruchomi się przy następnym logowaniu.','Uruchamiasz Zenka ręcznie.'),
    'initiative':('Zenek może sam rozpocząć rozmowę, w granicach limitów.','Zenek odpowiada na twoje wiadomości, bez samodzielnych wypowiedzi.'),
    'quiet':('Wstrzymuje spontaniczne wypowiedzi; nadal możesz pisać.','Spontaniczne wypowiedzi są dozwolone przez pozostałe ustawienia.'),
    'background_paused':('Wstrzymuje próby rozmyślania modelu w tle.','Pozwala na rozmyślania zgodnie z trybem, odstępem i limitem.'),
    'allow_capture_while_hidden':('Pozwala kontynuować zatwierdzoną obserwację po schowaniu, tylko ze wskaźnikiem i wyłącznikiem.','Schowanie Zenka zatrzymuje obserwację ekranu.'),
    'observation_memory':('Zapisuje dozwolone tekstowe obserwacje w szyfrowanej pamięci.','Interpretacja obrazu nie dodaje trwałych wspomnień obserwacyjnych.'),
    'auto_hide_on_fullscreen':('Chowa Zenka na monitorze z pełnym ekranem; powrót nie wznawia obserwacji.','Zenek pozostaje widoczny nad pełnym ekranem, jeśli nie schowasz go ręcznie.'),
    'web_enabled':('Pozwala na publiczny research i narzędzia WWW modelu.','Wyłącza research i narzędzia WWW modelu.'),
}
NUMBER_EFFECTS={
    'spontaneous_limit':'Maksymalna liczba samodzielnych wypowiedzi w ostatnich 60 minutach. 0 blokuje wypowiedzi.',
    'spontaneous_cooldown_minutes':'Minimalny odstęp w minutach między pokazanymi wypowiedziami.',
    'idle_threshold_minutes':'Po tylu minutach bezczynności Zenek zasypia i zatrzymuje obserwację.',
    'background_limit':'Maksymalna liczba prób modelu w ostatnich 24 godzinach. 0 blokuje próby.',
    'background_cooldown_minutes':'Minimalny odstęp w minutach między próbami modelu w tle.',
    'bubble_seconds':'Minimalny czas na czytanie spontanicznej chmurki. Pisanie zatrzymuje jej automatyczne zamykanie.',
    'sprite_scale':'Mnożnik rozmiaru postaci: 1 = 48 px, 3 = 144 px.',
    'sprite_fps':'Maksymalna liczba klatek animacji na sekundę. Spoczynek korzysta z wolniejszej animacji.',
    'web_search_limit':'Maksymalna liczba wyszukiwań w ostatnich 24 godzinach. 0 blokuje wyszukiwanie.',
    'web_read_limit':'Maksymalna liczba odczytanych stron w ostatnich 24 godzinach. 0 blokuje odczyt.',
    'screen_snapshot_seconds':'Odstęp między pojedynczymi zrzutami w sekundach. Między zrzutami sesja Portalu jest zamknięta. Nie zmienia limitu interpretacji modelu.',
    'visual_graphics_threshold':'Minimalny szacowany udział grafiki w niemaskowanej części obrazu (%). Najpierw lokalny OCR; niżej tego progu obraz nie trafia do modelu. Puste jednolite obszary nie liczą się jako grafika.',
}

class Settings(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.zenek.Settings")
        self.connect("activate",self.activate)
        self.status=None;self.model_controls={};self.catalog=[]
        self.setting_controls={};self.live_rows={};self.syncing_controls=False
        self._preview_window=None;self._preview_source=0
        self.capture_control=None
        self._personality_window=None;self._personality_page=None;self._personality_signature=None
        self._saved_prompt=None;self._saved_traits={}

    def activate(self,*args):
        if self.get_active_window():self.get_active_window().present();return
        self.window=Adw.ApplicationWindow(application=self,default_width=820,default_height=730,title="Zenek — ustawienia")
        self.toasts=Adw.ToastOverlay();outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header=Adw.HeaderBar();outer.append(header)
        self.banner=Gtk.Label(label="Łączę z Core…",wrap=True,margin_top=8,margin_bottom=8);outer.append(self.banner)
        self.stack=Adw.ViewStack(vexpand=True);outer.append(self.stack)
        switcher=Adw.ViewSwitcherBar(stack=self.stack,reveal=True);outer.append(switcher)
        sidebar=Gtk.StackSidebar(stack=self.stack) if False else None
        title=Adw.ViewSwitcherTitle(stack=self.stack,title="Zenek");header.set_title_widget(title)
        self.toasts.set_child(outer);self.window.set_content(self.toasts)
        self.refresh()
        self.build()
        self.sync_controls()
        self.bus_proxy=proxy();self.bus_proxy.connect("g-signal",self.event)
        GLib.timeout_add_seconds(3,self.poll)
        self.window.present()
        if self.status and self.status.get('auth')=='AUTHORIZED':self.rpc('Models')

    def notice(self,text):self.toasts.add_toast(Adw.Toast(title=str(text)[:180]))
    def rpc(self,method,p=None):
        try:return call(method,p)
        except Exception as e:self.notice(e);return None
    def refresh(self):
        try:self.status=call("GetStatus")
        except Exception:self.status=None
        if self.status:
            self.banner.set_label(f"{self.status.get('release_stage','PREVIEW')} · Core {self.status['version']} · build {self.status.get('core_build','brak')}\n{self.status['visibility']} · {self.status.get('memory','')} · {self.status.get('auth','')}\n"+self.status.get('lastError',''))
        else:self.banner.set_label("Core zatrzymany. Uruchom Zenka w zakładce Uruchamianie.")
        self.sync_controls()
    def poll(self):self.refresh();return GLib.SOURCE_CONTINUE
    def settings(self):return dict(DEFAULTS,**self.status.get('settings',{})) if self.status else DEFAULTS
    def patch(self,patch):
        if not self.status:self.notice("Najpierw uruchom Core");return
        self.rpc("UpdateSettings",dict(patch=patch,expected_version=self.status["config_version"]));self.refresh()
    def event(self,p,sender,name,args):
        if name!="Event":return
        kind,raw=args.unpack();data=json.loads(raw)
        if kind=="Models":
            self.catalog=data
            for profile,(model,effort) in self.model_controls.items():
                model.set_model(Gtk.StringList.new([m['name'] for m in data] or ['Brak modeli']))
                current=self.settings()[profile]["model_id"]
                selected=next((i for i,m in enumerate(data) if m['id']==current),0)
                model.set_selected(selected);self.update_efforts(profile)
            self.notice("Katalog pobrany z konta; dostęp potwierdza dopiero test inference")
        elif kind=="ProfileTest":self.notice(data["profile"]+": "+data["text"])
        elif kind=='WebValidation':self.notice('Test WWW: '+data['status'])
        elif kind=='ImportPreview':self.import_preview_window(data)
        elif kind=='ImportResult':self.text_window('Wynik aktualizacji pamięci',json.dumps(data,ensure_ascii=False,indent=2))
        elif kind=="ErrorChanged":self.notice(data["message"])
        elif kind=="StateChanged":self.status=data;self.sync_controls()

    def page(self,title,icon):
        page=Adw.PreferencesPage(title=title,icon_name=icon)
        self.stack.add_titled_with_icon(page,title,title,icon)
        return page
    def group(self,page,title,description=None):
        g=Adw.PreferencesGroup(title=title,description=description);page.add(g);return g
    def button(self,g,title,action,label="Otwórz"):
        row=Adw.ActionRow(title=title);b=Gtk.Button(label=label,valign=Gtk.Align.CENTER)
        b.connect("clicked",lambda _:action());row.add_suffix(b);row.set_activatable_widget(b);g.add(row);return row
    def switch(self,g,key,title,subtitle=""):
        row=Adw.SwitchRow(title=title,subtitle=subtitle,active=bool(self.settings()[key]))
        def changed(r,_):
            if self.syncing_controls:return
            if key=='autostart':self.autostart(r.get_active())
            else:self.patch({key:r.get_active()})
        row.connect("notify::active",changed);g.add(row);self.setting_controls[key]=(row,'switch',subtitle)
    def number(self,g,key,title,minimum=1,maximum=1000):
        row=Adw.SpinRow(title=title,adjustment=Gtk.Adjustment(value=self.settings()[key],lower=minimum,upper=maximum,step_increment=1,page_increment=5))
        row.connect("notify::value",lambda r,_:None if self.syncing_controls else self.patch({key:int(r.get_value())}));g.add(row)
        self.setting_controls[key]=(row,'number',f'Zakres: {minimum}–{maximum}. '+NUMBER_EFFECTS[key])
    def live_row(self,g,key,title):
        row=Adw.ActionRow(title=title);g.add(row);self.live_rows[key]=row
    def sync_controls(self):
        self.syncing_controls=True
        try:
            values=self.settings()
            for key,(row,kind,description) in self.setting_controls.items():
                row.set_sensitive(bool(self.status))
                current='Brak odczytu — Core zatrzymany.' if not self.status else 'Zapisano: '+('włączone' if values[key] else 'wyłączone') if kind=='switch' else f'Zapisano: {values[key]}.'
                if kind=='switch':
                    on,off=SWITCH_EFFECTS[key]
                    row.set_subtitle(current+'\nWłączone: '+on+'\nWyłączone: '+off+(' '+description if description else ''))
                    if self.status:row.set_active(bool(values[key]))
                elif kind=='number':
                    row.set_subtitle(current+'\n'+description)
                    if self.status:row.set_value(values[key])
                elif key=='screen_comment_priority':
                    labels={'off':'wyłączony','balanced':'zrównoważony','high':'wysoki'}
                    row.set_subtitle(('Zapisano: '+labels[values[key]]+'.' if self.status else 'Brak odczytu — Core zatrzymany.')+'\nWyłączony — tematy z pamięci. Zrównoważony — ekran częściej staje się inspiracją. Wysoki — większa szansa nowego tematu ekranowego.\nRóżnorodność ma pierwszeństwo: bez kolejnych komentarzy o ekranie i najwyżej dwa w ostatnich pięciu. Podobne sceny i powtórzone puenty są pomijane; limity pozostają te same.')
                    if self.status:row.set_selected(['off','balanced','high'].index(values[key]))
                else:
                    row.set_subtitle(('Zapisano: '+values[key]+'.' if self.status else 'Brak odczytu — Core zatrzymany.')+'\nB — lokalna agenda, bez wywołań modelu w tle.\nC — model rozmyśla w granicach limitów; niedostępny profil przełącza działanie na lokalne B.')
                    if self.status:row.set_selected(1 if values[key]=='C' else 0)
            for profile,(model,effort) in self.model_controls.items():
                saved=values[profile]
                model.set_subtitle(f"Zapisano: {saved['model_id']} · stan: {saved['status']}. Wybór poniżej wymaga kliknięcia Zapisz." if self.status else 'Brak odczytu zapisanego profilu — Core zatrzymany.')
                explanations={'none':'bez dodatkowego rozumowania','minimal':'najkrótsze','low':'krótsze','medium':'pośrednie','high':'dokładniejsze','xhigh':'jeszcze dokładniejsze','max':'maksymalne','ultra':'najwyższe','auto':'dobiera model'}
                choices=[]
                if self.catalog and model.get_selected()<len(self.catalog):choices=self.catalog[model.get_selected()]['efforts']
                effort.set_subtitle(f"Zapisano: {saved['reasoning_effort']}. "+' · '.join(f'{v}: {explanations.get(v,v)}' for v in choices))
            s=self.status or {}
            if self.capture_control:
                self.capture_control.set_sensitive(bool(self.status))
                self.capture_control.set_active(bool(s.get('settings',{}).get('capture_enabled')))
                phases={'OFF':'wyłączone','WAITING':'czeka na następny zrzut — sesja Portalu zamknięta','PORTAL':'przygotowuje pojedynczy zrzut','SNAPSHOT':'pobiera pojedynczy zrzut'}
                state='czeka na zgodę Portalu' if s.get('screen')=='AWAITING_PORTAL' else phases.get(s.get('capture_phase','OFF'),'brak odczytu')
                if s.get('settings',{}).get('capture_enabled') and s.get('screen')=='OFF':state='pauza: '+s.get('capture_pause_reason','użyj Wznów zrzuty')
                self.capture_control.set_subtitle('Stan teraz: '+state+'.\nWłączone — plan pozostaje zapisany podczas blokady i bezczynności; wraca po powrocie do aktywnej sesji z zapisaną zgodą. Błąd zatrzymuje próbę, nie wyłącza ustawienia. Wyłączone — brak zrzutów.')
            analysis=s.get('screen_analysis') or {}
            last=s.get('last_vision_request') or {}
            import datetime
            stamp=lambda value:datetime.datetime.fromtimestamp(value).strftime('%H:%M:%S') if value else 'brak'
            modes={'OCR':'lokalny OCR — bez wysyłania obrazu','VISION':'interpretacja wizualna','EMPTY':'brak czytelnej treści'}
            analysis_label=modes.get(analysis.get('mode'),'brak')
            if s.get('redaction_reason') and s.get('capture_last_snapshot',0)>(analysis.get('at') or 0):analysis_label='Odrzucono ostatni zrzut: '+s['redaction_reason']
            visual_label='Udana interpretacja obrazu' if last.get('completed') else 'Ostatnia próba interpretacji obrazu'
            summaries={
                'runtime':f"Postać: {s.get('visibility','brak odczytu')} · Core: {'działa' if self.status else 'zatrzymany'}.",
                'auth':f"Konto: {s.get('auth','brak odczytu')}. Logowanie i wylogowanie dotyczą konta Zenka.",
                'background':f"Działanie teraz: {s.get('activity','brak odczytu')} · aktywne zadania: {', '.join(s.get('active_jobs',[])) or 'brak'}. Zapisany tryb C nie oznacza trwającego wywołania modelu.",
                'capture':f"Ostatni zrzut: {stamp(s.get('capture_last_snapshot'))} · następny: {stamp(s.get('capture_next_snapshot'))}.\n{analysis_label}. Ocena struktury: {stamp(analysis.get('at'))}, grafika: {analysis.get('graphics_percent',0)}%. Okna wysokiego ryzyka: {analysis.get('high_risk_windows',0)}, niskiego: {analysis.get('low_risk_windows',0)}.\n{visual_label}: {stamp(last.get('started_at'))}. Obraz jest wysyłany tylko przy dostatecznej ilości grafiki, zmianie i dostępnych limitach — nie jest transmitowany stale.",
                'web':f"Broker: {s.get('web','brak odczytu')}. Samo włączenie nie oznacza trwającego odczytu strony.",
            }
            for key,row in self.live_rows.items():row.set_subtitle(summaries[key])
            if not self.status:
                for row in self.live_rows.values():row.set_subtitle('Core zatrzymany — brak bieżącego odczytu. Uruchom Zenka, aby zobaczyć aktualny stan.')
            for key,row in getattr(self,'traits',{}).items():
                if self.status and row.get_value()==self._saved_traits.get(key):row.set_value(values['traits'][key])
                row.set_subtitle((f"Zapisano: {values['traits'][key]:.2f}. " if self.status else 'Brak odczytu zapisanej wartości. ')+'Zakres 0–1; edycję stosuje przycisk Zapisz cechy. '+self.trait_effects[key])
            if self.status:self._saved_traits=dict(values['traits'])
            if hasattr(self,'prompt'):
                buffer=self.prompt.get_buffer();draft=buffer.get_text(*buffer.get_bounds(),True)
                if self.status and draft==self._saved_prompt and draft!=values['prompt']:buffer.set_text(values['prompt'])
                if self.status:self._saved_prompt=values['prompt']
                self.update_prompt_notice()
        finally:self.syncing_controls=False
        self.refresh_personality_window()

    def build(self):
        p=self.page("Uruchamianie","system-run-symbolic");g=self.group(p,"Zenek na pulpicie")
        self.live_row(g,'runtime','Aktualne działanie')
        for title,command in [("Uruchom Zenka","start"),("Pokaż Zenka","show"),("Schowaj Zenka","hide"),("Zatrzymaj Zenka","stop")]:
            self.button(g,title,lambda c=command:self.launch(c),"Wykonaj")
        self.switch(g,'autostart','Uruchamiaj przy logowaniu')
        self.group(p,"Instalacja lokalna", "Schowanie pozostawia Core i szyfrowaną pamięć. Zatrzymanie kończy działalność. Autostart dotyczy kolejnego logowania.")
        p=self.page("Konto i modele","avatar-default-symbolic");g=self.group(p,"Konto ChatGPT","Logowanie przez systemową przeglądarkę. Rozmowy i wybrane wspomnienia trafiają do OpenAI; użycie obciąża limity twojego planu.")
        self.live_row(g,'auth','Aktualne konto')
        self.button(g,"Sign in with ChatGPT",lambda:self.rpc("Login"),"Continue with ChatGPT")
        self.button(g,"Przerwij logowanie",lambda:self.rpc("CancelLogin"),"Przerwij")
        self.button(g,"Wyloguj konto Zenka",lambda:self.rpc("Logout"),"Wyloguj")
        self.button(g,"Pobierz katalog konta",lambda:self.rpc("Models"),"Odśwież modele")
        for profile,label in [("conversation","Rozmowa"),("background_cognition","Rozmyślania w tle"),("vision","Interpretacja ekranu")]:
            g=self.group(p,label)
            model=Adw.ComboRow(title="Model",model=Gtk.StringList.new(["Pobierz katalog po zalogowaniu"]))
            effort=Adw.ComboRow(title="Reasoning effort",model=Gtk.StringList.new(["auto"]))
            self.model_controls[profile]=(model,effort);g.add(model);g.add(effort)
            model.connect("notify::selected",lambda _,__,pr=profile:self.update_efforts(pr))
            self.button(g,"Zapisz niezależny profil",lambda pr=profile:self.save_profile(pr),"Zapisz")
            self.button(g,"Sprawdź zapisany model i effort",lambda pr=profile:self.rpc("TestProfile",{"profile":pr}),"Test")
        p=self.page("Osobowość","face-smile-symbolic");g=self.group(p,"Instrukcja Zenka","Zmiana charakteru nie zmienia uprawnień. Każda ręczna zmiana tworzy wersję. Propozycje Zenka wymagają twojego zatwierdzenia.")
        self.button(g,'Propozycje, porównanie i historia',self.personality_window,'Przejrzyj')
        row=Adw.PreferencesRow();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=10,margin_bottom=10,margin_start=10,margin_end=10)
        self.prompt=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR);self.prompt.get_buffer().set_text(self.settings()["prompt"])
        self._saved_prompt=self.settings()['prompt'];self._prompt_status=Gtk.Label(wrap=True,xalign=0);box.append(self._prompt_status)
        self.prompt.get_buffer().connect('changed',lambda _:self.update_prompt_notice())
        scroll=Gtk.ScrolledWindow(min_content_height=180);scroll.set_child(self.prompt);box.append(scroll)
        save=Gtk.Button(label="Zapisz instrukcję");save.connect("clicked",lambda _:self.save_prompt());box.append(save);row.set_child(box);g.add(row)
        self.button(g,"Przywróć bazową instrukcję",lambda:self.patch({"prompt":BASE_PROMPT}),"Przywróć")
        g=self.group(p,"Cechy charakteru");self.traits={}
        self.trait_effects=dict(humor='Wyżej: częstszy humor i ironia.',curiosity='Wyżej: większa ciekawość tematów.',sociability='Wyżej: większa chęć rozpoczynania rozmów.',independence='Wyżej: więcej własnych tematów.',disagreeability='Wyżej: częstsza polemika i zadziorność.',digression='Wyżej: więcej skojarzeń i dygresji.',restraint='Wyżej: rzadsze samodzielne wypowiedzi.',expression='Wyżej: bardziej ekspresyjny język.',interruption_sensitivity='Wyżej: większa ostrożność przy przerywaniu.',memory_continuity='Wyżej: więcej nawiązań do wcześniejszych rozmów.')
        labels=dict(humor="Humor / ironia",curiosity="Ciekawość",sociability="Towarzyskość",independence="Samodzielność tematów",disagreeability="Zadziorność",digression="Dygresje",restraint="Powściągliwość",expression="Ekspresyjność",interruption_sensitivity="Wrażliwość na przerwanie",memory_continuity="Ciągłość pamięci")
        for key,val in self.settings()["traits"].items():
            row=Adw.SpinRow(title=labels[key],adjustment=Gtk.Adjustment(value=val,lower=0,upper=1,step_increment=.05),digits=2);g.add(row);self.traits[key]=row
        self._saved_traits=dict(self.settings()['traits'])
        self.button(g,"Zapisz cechy",lambda:self.patch({"traits":{k:r.get_value() for k,r in self.traits.items()}}),"Zapisz")
        p=self.page("Zachowania","appointment-soon-symbolic");g=self.group(p,"Inicjatywa i cisza")
        self.switch(g,"initiative","Samodzielne inicjatywy")
        self.switch(g,"quiet","Nie przeszkadzać")
        priority=Adw.ComboRow(title='Priorytet ekranu w samodzielnych komentarzach',model=Gtk.StringList.new(['Wyłączony','Zrównoważony','Wysoki']))
        priority.set_selected(['off','balanced','high'].index(self.settings().get('screen_comment_priority','off')));g.add(priority)
        self.setting_controls['screen_comment_priority']=(priority,'choice','')
        priority.connect('notify::selected',lambda r,_:None if self.syncing_controls else self.patch({'screen_comment_priority':['off','balanced','high'][r.get_selected()]}))
        self.number(g,"spontaneous_limit","Limit wypowiedzi / ruchome 60 minut",0,100)
        self.number(g,"spontaneous_cooldown_minutes","Przerwa między wypowiedziami (minuty)")
        self.number(g,"idle_threshold_minutes","Próg bezczynności (minuty)")
        g=self.group(p,"Ciche rozmyślania","Osobny model i effort; brak konfiguracji oznacza lokalne B. Zero inference podczas suspend.")
        self.live_row(g,'background','Aktywność w tle')
        mode=Adw.ComboRow(title='Tryb rozmyślań',model=Gtk.StringList.new(['B — lokalna agenda','C — model w tle']))
        mode.set_selected(1 if self.settings()['background_mode']=='C' else 0);g.add(mode)
        self.setting_controls['background_mode']=(mode,'choice','')
        mode.connect('notify::selected',lambda r,_:None if self.syncing_controls else self.patch({'background_mode':'C' if r.get_selected()==1 else 'B'}))
        self.switch(g,"background_paused","Pauza rozmyślań")
        self.number(g,"background_limit","Limit prób / ruchome 24 godziny",0,1000)
        self.number(g,"background_cooldown_minutes","Przerwa między próbami (minuty)")
        p=self.page("Ekran i prywatność","view-reveal-symbolic");g=self.group(p,"Okresowe zrzuty — Portal + PipeWire","Wybierasz monitor w oknie systemowym. Pojedynczy Print Screen co ustawiony odstęp, lokalne maskowanie i OCR. Głównie tekst: bez wysyłania obrazu. Duży udział grafiki: interpretacja wizualna. Obrazy istnieją tylko w RAM; zrzuty nie wznawiają się same.")
        self.capture_control=Adw.SwitchRow(title='Okresowe zrzuty ekranu')
        self.capture_control.connect('notify::active',lambda r,_:None if self.syncing_controls else (self.rpc('ResumeScreenCapture' if r.get_active() else 'PauseScreenCapture'),self.refresh()))
        g.add(self.capture_control)
        self.live_row(g,'capture','Aktualny stan obserwacji')
        self.number(g,'screen_snapshot_seconds','Odstęp zrzutów (sekundy)',15,3600)
        self.number(g,'visual_graphics_threshold','Próg interpretacji grafiki (%)',10,90)
        self.button(g,"Wznów zrzuty / wybierz źródło",lambda:self.rpc("ResumeScreenCapture"),"Wznów")
        self.button(g,"Przestań patrzeć",lambda:self.rpc("PauseScreenCapture"),"Zatrzymaj")
        self.button(g,'Podgląd dokładnie po maskowaniu',self.preview_window,'Pokaż')
        self.group(p,'Kwalifikacja ryzyka','Wysokie: bankowość, urząd skarbowy, strony gov, ZUS, panele dostawców infrastruktury i Vault — całe okno podlega maskowaniu. Niskie: poczta, social media, terminal i pozostałe okna — treść może służyć obserwacji. Hasła, tokeny i klucze nadal są maskowane. Klasyfikacja korzysta z aplikacji, tytułu i lokalnego OCR widocznego nagłówka przeglądarki; nie odczytuje ukrytego adresu strony.')
        self.switch(g,"allow_capture_while_hidden","Obserwuj także po schowaniu","OFF domyślnie. Samo ON nie otwiera Portalu; wymagana wcześniejsza zgoda, niezależny wskaźnik i kill switch.")
        self.switch(g,"observation_memory","Zapisuj dozwolone tekstowe obserwacje")
        self.group(p,"Szyfrowanie","SQLCipher + GNOME Keyring. Utrata klucza oznacza utratę dostępu; odblokowana sesja nadal może ujawnić pamięć procesowi użytkownika.")
        p=self.page("Pamięć","document-open-recent-symbolic");g=self.group(p,"Zainteresowania i wątki")
        self.interest=Adw.EntryRow(title="Nowe zainteresowanie");g.add(self.interest)
        self.button(g,"Dodaj temat",lambda:self.rpc("AddInterest",{"subject":self.interest.get_text()}),"Dodaj")
        self.button(g,"Przejrzyj / popraw / usuń wspomnienia",self.memory_window,"Otwórz")
        self.button(g,'Usuń wszystkie wspomnienia obserwacyjne',lambda:self.clear_memory('observation_memory'),'Usuń obserwacje')
        self.button(g,'Usuń pamięć rozmów, tematów i wspomnień',lambda:self.clear_memory(None),'Wybierz zakres')
        self.button(g,'Eksport pamięci do nowego lokalnego JSON',self.export_memory,'Eksportuj ręcznie')
        g=self.group(p,'Aktualizuj pamięć projektu','Wskaż oficjalny eksport ChatGPT lub dokumenty projektu Zenek Kwasiborski, a następnie zaznacz potwierdzone wątki. Import działa wyłącznie po twoim kliknięciu. Bez watcherów i automatycznego pobierania. Oryginały i wnioski pozostają osobne.')
        self.button(g,'Wybierz pliki — najpierw podgląd',self.choose_import,'Wybierz')
        self.button(g,'Wstrzymaj import',lambda:self.rpc('PauseImport'),'Pauza')
        self.button(g,'Ostatni stan / wznowienie',self.import_status,'Przejrzyj')
        p=self.page("Wygląd","preferences-desktop-display-symbolic");g=self.group(p,"Postać")
        self.switch(g,"auto_hide_on_fullscreen","Ukrywaj podczas pełnego ekranu","ON domyślnie. Powrót nie ujawnia ręcznie schowanej postaci i nie wznawia obserwacji.")
        self.number(g,"bubble_seconds","Czas spontanicznego dymku (sekundy)",3,120)
        self.number(g,'sprite_scale','Skala pixel art',1,6)
        self.number(g,'sprite_fps','Klatki animacji na sekundę',1,20)
        self.group(p,'ZENN — twój własny pet','Oryginalny arkusz v2: 73 klatki, 9 animacji i 16 spojrzeń. Pisanie kodu, obrona, tworzenie obrazów i aplikacji. Grafiki skopiowane z lokalnego projektu ZENN.')
        p=self.page("Diagnostyka","dialog-information-symbolic");g=self.group(p,"Status komponentów")
        self.button(g,"Pokaż bieżący stan i liczniki",self.diagnostic,"Pokaż")
        g=self.group(p,'WWW Research','Samodzielnie wybrane publiczne tematy; wyszukiwanie MediaWiki i odczyt źródeł. Bez logowania, formularzy i prywatnej pamięci w zapytaniach. Test brokera służy diagnostyce.')
        self.live_row(g,'web','Aktualny stan WWW')
        self.button(g,'Sprawdź izolację i publiczny odczyt',lambda:self.rpc('ValidateWeb'),'Testuj')
        self.switch(g,'web_enabled','Autonomiczny WWW')
        self.number(g,'web_search_limit','Wyszukiwania / ruchome 24 godziny',0,1000)
        self.number(g,'web_read_limit','Strony / ruchome 24 godziny',0,1000)
        self.button(g,'Ostatnie publiczne źródła',lambda:self.text_window('Źródła WWW',json.dumps(self.rpc('GetMemory',{'kind':'web_research'}),ensure_ascii=False,indent=2)),'Pokaż')

    def personality_window(self):
        if self._personality_window:
            self.refresh_personality_window();self._personality_window.present();return self._personality_window
        w=Adw.PreferencesWindow(application=self,title='Osobowość Zenka',transient_for=self.window,destroy_with_parent=True,default_width=780,default_height=700)
        self._personality_window=w
        def closed(*_):
            if self._personality_window is w:self._personality_window=None;self._personality_page=None;self._personality_signature=None
            return False
        w.connect('close-request',closed)
        self.refresh_personality_window();w.present();return w

    def refresh_personality_window(self):
        w=self._personality_window
        if not w:return
        state=self.rpc('GetPersonality') if self.status else None
        signature=json.dumps(state,sort_keys=True)
        if signature==self._personality_signature:return
        self._personality_signature=signature
        if self._personality_page:w.remove(self._personality_page)
        p=Adw.PreferencesPage();w.add(p)
        self._personality_page=p
        if not state:
            self.group(p,'Brak aktualnego odczytu','Core jest niedostępny. Zmiany osobowości wymagają bieżącej wersji z pamięci.');return
        pending=[item for item in state['proposals'] if item['status']=='PENDING']
        g=Adw.PreferencesGroup(title='Rozwijające się „ja”',description='Zenek sam rozwija charakter, wiedzę, zainteresowania i notatki w notebook/. Zmiany osobowości stosuje autonomicznie i zachowuje ich historię. O zmiany kodu może poprosić właściciela.');p.add(g)
        self.button(g,'Model siebie i historia rozwoju',self.self_model_window,'Przejrzyj')
        self.button(g,'Notatnik, rozmowy i rozwój',lambda:subprocess.Popen([sys.executable,'-m','zenek_settings.workspace']),'Otwórz')
        self.button(g,'Prośby o zmianę kodu',lambda:self.text_window('Prośby Zenka',json.dumps(self.rpc('GetMemory',{'kind':'code_request'}),ensure_ascii=False,indent=2)),'Przejrzyj')
        g=Adw.PreferencesGroup(title=f"Starsze propozycje: {len(pending)} · aktywna wersja {state['active']['version']}",description='Zachowane szkice sprzed autonomicznego rozwoju. Nowe zmiany charakteru nie wymagają zatwierdzania.');p.add(g)
        for item in pending:self.button(g,item['proposal']['topic'],lambda i=item:self.review_personality(i),'Porównaj')
        if not pending:g.add(Adw.ActionRow(title='Brak nowych propozycji'))
        g=Adw.PreferencesGroup(title='Historia wersji charakteru');p.add(g)
        for version in state['history']:
            self.button(g,f"Wersja {version['version']} · {version['reason']}",lambda v=version:self.review_version(v),'Przejrzyj')
        g=Adw.PreferencesGroup(title='Odrzucone i odłożone');p.add(g)
        for item in state['proposals']:
            if item['status'] in ('REJECTED','DISMISSED'):g.add(Adw.ActionRow(title=item['proposal']['topic'],subtitle=item['status']))

    def self_model_window(self):
        state=self.rpc('GetSelfModel')
        if not state:return
        lines=[f"Obszary: {state['facet_count']} · zapisane zmiany: {state['revision_count']}"]
        for category,label in state['categories'].items():
            lines+=['',label.upper()]
            rows=[r for r in state['facets'] if r['body']['category']==category]
            if not rows:lines.append('Jeszcze się kształtuje.')
            for r in rows:
                b=r['body'];lines.extend([f"{b['domain']} · wersja {b['revision']} · pewność {b['confidence']:.0%}",b['text'],'Dlaczego: '+b['reason'],f"Źródła: {len(b['source_ids'])} · powiązania: {len(b.get('related_ids',[]))}",''])
        history=self.rpc('GetMemory',{'kind':'self_evolution'}) or []
        if history:
            lines+=['','OSTATNIE ZMIANY']
            for r in history[:15]:
                b=r['body'];lines.extend([b['domain']+': '+(b.get('before') or '(nowy obszar)')+' → '+b['text'],b['reason'],''])
        self.decision_window('Zenek — model siebie','\n'.join(lines),[])

    def review_personality(self,item):
        proposal=item['proposal'];state=self.rpc('GetPersonality')
        if not state:return
        active=state['active']
        diff=prompt_diff(active['prompt'],proposal['prompt'])
        text=proposal['rationale']+'\n\nNowe przesłanki: '+proposal['novelty']+'\nŹródła: '+', '.join(proposal['source_ids'])+'\n\n'+diff+'\n\nCechy: '+json.dumps({k:[active['traits'][k],v] for k,v in proposal['traits'].items()},ensure_ascii=False,indent=2)
        conflict=item['base_version']!=active['version']
        if conflict:text='Instrukcja zmieniła się od stworzenia propozycji. Poniższy diff porównuje ją z obecną wersją.\n\n'+text
        self.decision_window('Propozycja: '+proposal['topic'],text,[('Zatwierdź po porównaniu z obecną wersją' if conflict else 'Zatwierdź',lambda:self.rpc('DecidePersonality',dict(id=item['id'],decision='APPROVED',reviewed_version=active['version'],allow_rebase=conflict))),('Odrzuć',lambda:self.rpc('DecidePersonality',dict(id=item['id'],decision='REJECTED'))),('Odłóż bez stosowania',lambda:self.rpc('DecidePersonality',dict(id=item['id'],decision='DISMISSED')))],keep_on_failure=True)

    def review_version(self,version):
        self.decision_window('Wersja '+str(version['version']),version['prompt']+'\n\n'+json.dumps(version['traits'],indent=2),[('Przywróć tę wersję',lambda:self.rpc('RollbackPersonality',{'version':version['version']}))],keep_on_failure=True)

    def decision_window(self,title,text,actions,keep_on_failure=False):
        w=Adw.Window(application=self,title=title,transient_for=self.window,destroy_with_parent=True,default_width=740,default_height=650)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);outer.append(Adw.HeaderBar())
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_start=12,margin_end=12,margin_top=12,margin_bottom=12);outer.append(box)
        view=Gtk.TextView(editable=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);view.get_buffer().set_text(text)
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_child(view);box.append(scroll)
        status=Gtk.Label(wrap=True,xalign=0,visible=False);box.append(status)
        def perform(action):
            result=action();self.refresh()
            if keep_on_failure and (result is None or result is False or isinstance(result,dict) and result.get('status')=='CONFLICT'):
                status.set_label('Aktywna instrukcja zmieniła się. Zamknij porównanie i otwórz aktualny diff przed ponownym zatwierdzeniem.' if isinstance(result,dict) and result.get('status')=='CONFLICT' else 'Nie zapisano zmiany. Sprawdź połączenie z Core i komunikat błędu.');status.set_visible(True);return
            w.close()
        for label,action in actions:
            button=Gtk.Button(label=label);button.connect('clicked',lambda _,a=action:perform(a));box.append(button)
        w.set_content(outer);w.present()

    def update_prompt_notice(self):
        if not hasattr(self,'_prompt_status'):return
        if not self.status:self._prompt_status.set_label('Brak odczytu aktywnej instrukcji — Core niedostępny.');return
        buffer=self.prompt.get_buffer();draft=buffer.get_text(*buffer.get_bounds(),True)
        self._prompt_status.set_label(f"Aktywna wersja: {self.status.get('personality_version','brak')}. "+('Niezapisany szkic — przycisk Zapisz instrukcję zastosuje tekst z pola.' if draft!=self.settings()['prompt'] else 'Pole pokazuje zapisaną instrukcję.'))

    def update_efforts(self,profile):
        if not self.catalog:return
        model,effort=self.model_controls[profile];index=model.get_selected()
        if index>=len(self.catalog):return
        values=self.catalog[index]["efforts"]
        effort.set_model(Gtk.StringList.new(values));current=self.settings()[profile]["reasoning_effort"]
        effort.set_selected(values.index(current) if current in values else 0)
        self.sync_controls()
    def choose_import(self):
        dialog=Gtk.FileDialog(title='Eksport i dokumenty projektu Zenek Kwasiborski')
        filter=Gtk.FileFilter();filter.set_name('Eksport ChatGPT i teksty projektu')
        for extension in ('*.zip','*.json','*.md','*.txt'):filter.add_pattern(extension)
        filters=Gio.ListStore.new(Gtk.FileFilter);filters.append(filter);dialog.set_filters(filters)
        def selected(dialog,result):
            try:
                files=dialog.open_multiple_finish(result);paths=[files.get_item(i).get_path() for i in range(files.get_n_items())]
                self.rpc('PreviewImport',{'paths':paths})
            except GLib.Error:pass
        dialog.open_multiple(self.window,None,selected)
    def import_preview_window(self,preview):
        w=Adw.PreferencesWindow(title='Potwierdź źródła projektu',transient_for=self.window,default_width=800,default_height=700)
        p=Adw.PreferencesPage();g=Adw.PreferencesGroup(title='Zaznacz wyłącznie projekt Zenek Kwasiborski',description=preview['warning']);p.add(g);w.add(p);rows=[]
        for choice in preview['choices']:
            row=Adw.SwitchRow(title=choice['title'],subtitle=f"{choice['kind']} · {choice['messages']} oryginalnych wpisów · {choice['path']}",active=False);g.add(row);rows.append((choice['key'],row))
        def apply():
            selected=[key for key,row in rows if row.get_active()]
            if not selected:self.notice('Zaznacz potwierdzone źródła projektu');return
            self.rpc('ApplyImport',dict(id=preview['id'],selected=selected,confirmed_project=True));w.close()
        self.button(g,'Potwierdzam przynależność do projektu — aktualizuj pamięć',apply,'Importuj zaznaczone')
        w.present()
    def import_status(self):
        job=self.rpc('GetImportStatus')
        if not job:return
        if job['status']=='PREVIEW':self.import_preview_window(dict(id=job['id'],choices=job['body']['choices'],warning='Zaznacz źródła projektu. Żadna treść nie została zaimportowana.'));return
        actions=[]
        if job['status'] in ('PAUSED','APPLYING'):actions=[('Wznów zatwierdzony wybór',lambda:self.rpc('ApplyImport',dict(id=job['id'],selected=job['body']['selected'],confirmed_project=True)))]
        self.decision_window('Stan importu: '+job['status'],json.dumps(job,ensure_ascii=False,indent=2),actions)
    def save_profile(self,profile):
        if not self.catalog:self.notice("Najpierw pobierz katalog");return
        model,effort=self.model_controls[profile];m=self.catalog[model.get_selected()]
        self.patch({profile:dict(model_id=m["id"],reasoning_effort=m["efforts"][effort.get_selected()],status="UNAVAILABLE")})
    def save_prompt(self):
        b=self.prompt.get_buffer();self.patch({"prompt":b.get_text(b.get_start_iter(),b.get_end_iter(),True)})
    def launch(self,command):
        if command in ("start","stop"):
            subprocess.run(["systemctl","--user",command,"zenek-core.service"],check=False)
        if command in ("start","show","hide"):
            self.rpc("HideCompanion" if command=="hide" else "ShowCompanion")
        self.refresh()
    def autostart(self,value=None):
        from pathlib import Path
        from zenek_core.config import CONFIG
        import os
        new=not self.settings()["autostart"] if value is None else value
        if not self.status:self.notice("Najpierw uruchom Core");return
        directory=Path(os.environ.get("XDG_CONFIG_HOME",Path.home()/".config"))/"autostart"
        path=directory/"zenek-desktop.desktop"
        if new:
            directory.mkdir(exist_ok=True)
            path.write_text('[Desktop Entry]\nType=Application\nName=Zenek\nExec='+str(Path.home()/'.local/bin/zenek')+' start\nX-GNOME-Autostart-enabled=true\n')
        else:path.unlink(missing_ok=True)
        self.patch({"autostart":new});self.notice("Autostart ON" if new else "Autostart OFF")
    def diagnostic(self):
        self.refresh();self.text_window("Stan Zenka",json.dumps(self.status,ensure_ascii=False,indent=2))
    def text_window(self,title,text):
        w=Adw.Window(title=title,transient_for=self.window,default_width=640,default_height=500)
        view=Gtk.TextView(editable=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);view.get_buffer().set_text(text)
        sc=Gtk.ScrolledWindow();sc.set_child(view);w.set_content(sc);w.present()
    def memory_window(self):
        records=self.rpc("GetMemory")
        if records is None:return
        w=Adw.PreferencesWindow(title="Pamięć Zenka",transient_for=self.window,default_width=720,default_height=650)
        p=Adw.PreferencesPage();g=Adw.PreferencesGroup(title="Oryginały i wnioski mają osobne źródła");p.add(g);w.add(p)
        for record in records:
            if record['kind'] in INTERNAL_RECORD_KINDS:continue
            row=Adw.ActionRow(title=record["kind"]+" · "+record["source"],subtitle=json.dumps(record["body"],ensure_ascii=False)[:500]);row.set_subtitle_lines(4)
            button=Gtk.Button(label="Przejrzyj",valign=Gtk.Align.CENTER)
            button.connect("clicked",lambda _,r=record:self.memory_record_window(r))
            row.add_suffix(button);g.add(row)
        w.present()

    def memory_record_window(self,record):
        w=Adw.Window(title='Pamięć Zenka — korekta',transient_for=self.window,default_width=720,default_height=650)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=14,margin_bottom=14,margin_start=14,margin_end=14)
        box.append(Gtk.Label(label=f"{record['kind']} · {record['source']} · pewność {record['confidence']:.2f}",wrap=True))
        field=next((f for f in ('detailed_text','text','subject','note') if f in record['body']),None)
        text=record['body'].get(field,'') if field else json.dumps(record['body'],ensure_ascii=False,indent=2)
        view=Gtk.TextView(editable=bool(field),wrap_mode=Gtk.WrapMode.WORD_CHAR);view.get_buffer().set_text(text)
        scroll=Gtk.ScrolledWindow(vexpand=True);scroll.set_child(view);box.append(scroll)
        actions=[('Pokaż oryginał i metadane',lambda:self.text_window('Oryginał i pochodzenie',json.dumps(record,ensure_ascii=False,indent=2))),('Nie wracaj do tego tematu',lambda:self.rpc('DoNotReturnTopic',{'id':record['id']})),('Usuń to wspomnienie',lambda:self.rpc('DeleteMemory',{'id':record['id']}))]
        if record['kind']=='import_original':actions.insert(1,('Wszystkie źródła importu',lambda:self.text_window('Pochodzenie importu',json.dumps(self.rpc('GetImportReferences',{'id':record['id']}),ensure_ascii=False,indent=2))))
        if field:
            def save():
                b=view.get_buffer();result=self.rpc('CorrectMemory',dict(id=record['id'],field=field,text=b.get_text(b.get_start_iter(),b.get_end_iter(),True)))
                if result is not None:self.notice('Korekta zapisana; oryginał zachowany');w.close()
            actions.insert(0,('Zapisz korektę',save))
        for label,action in actions:
            button=Gtk.Button(label=label);button.connect('clicked',lambda _,a=action:a());box.append(button)
        w.set_content(box);w.present()

    def clear_memory(self,kind):
        title='Usuń obserwacje' if kind else 'Usuń pamięć rozmów i wspomnień'
        description='Usunięcie jest trwałe. '+('Dotyczy zapisanych tekstowych obserwacji.' if kind else 'Dotyczy rozmów, zainteresowań, wątków, importowanych oryginałów i wniosków. Konto, aktywna osobowość i liczniki limitów pozostają dostępne.')
        self.decision_window(title,description,[('Potwierdzam usunięcie',lambda:self.rpc('ClearMemory',dict(kind=kind,confirmed=True)))])

    def export_memory(self):
        dialog=Gtk.FileDialog(title='Eksport do nowego lokalnego JSON',initial_name='zenek-memory.json')
        def selected(dialog,result):
            try:
                path=dialog.save_finish(result).get_path()
                self.decision_window('Jawny eksport pamięci','Wybrany plik: '+str(path)+'\n\nJSON zawiera teksty pamięci bez szyfrowania. Powstanie tylko ten nowy plik lokalny; istniejący plik nie zostanie nadpisany.',[('Zapisz eksport do wybranego pliku',lambda:self.rpc('ExportMemory',dict(path=path,confirmed_plaintext=True)))])
            except GLib.Error:pass
        dialog.save(self.window,None,selected)

    def preview_window(self):
        if self._preview_window:
            self._preview_window.present();return self._preview_window
        w=Adw.Window(application=self,title='Zenek — podgląd po maskowaniu',transient_for=self.window,destroy_with_parent=True,default_width=860,default_height=650)
        self._preview_window=w
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_start=12,margin_end=12,margin_top=12,margin_bottom=12)
        box.append(Adw.HeaderBar())
        label=Gtk.Label(label='Wyłącznie zredagowany obraz w RAM. Podgląd nie włącza obserwacji.',wrap=True);box.append(label)
        picture=Gtk.Picture(vexpand=True,content_fit=Gtk.ContentFit.CONTAIN);box.append(picture)
        def refresh():
            value=self.rpc('GetRedactedPreview')
            if not value:picture.set_paintable(None);label.set_label('Brak aktualnej bezpiecznej klatki. Obserwacja musi być włączona; niepewne obrazy są odrzucane.');return True
            import base64,datetime
            texture=Gdk.Texture.new_from_bytes(GLib.Bytes.new(base64.b64decode(value['png'])))
            picture.set_paintable(texture);label.set_label(f"Po maskowaniu · {value['masks']} obszarów · "+datetime.datetime.fromtimestamp(value['at']).strftime('%H:%M:%S'))
            return True
        button=Gtk.Button(label='Odśwież podgląd');button.connect('clicked',lambda _:refresh());box.append(button)
        stop=Gtk.Button(label='Przestań patrzeć');stop.connect('clicked',lambda _:(self.rpc('PauseScreenCapture'),refresh()));box.append(stop)
        close=Gtk.Button(label='Zamknij podgląd');close.connect('clicked',lambda _:w.close());box.append(close)
        escape=Gtk.EventControllerKey()
        escape.connect('key-pressed',lambda _c,key,*_:((w.close(),True)[1] if key==Gdk.KEY_Escape else False));w.add_controller(escape)
        w.set_content(box);w.present();refresh()
        self._preview_source=GLib.timeout_add_seconds(3,refresh)
        def closed(*args):
            if self._preview_window is not w:return False
            if self._preview_source:GLib.source_remove(self._preview_source);self._preview_source=0
            picture.set_paintable(None)
            if self._preview_window is w:self._preview_window=None
            return False
        w.connect('close-request',closed)
        w.connect('destroy',closed)
        return w

def main():Settings().run([sys.argv[0]])
if __name__=="__main__":main()
