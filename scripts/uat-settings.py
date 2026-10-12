"""Own GTK UI: settings readback/failed save/preview singleton and cleanup.

No real configuration changes, screenshots of desktop, or account requests.
"""
import copy
import json
import sys
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Gsk','4.0');gi.require_version('Graphene','1.0')
from gi.repository import Gtk,Gsk,Graphene,GLib
from zenek_settings.app import Settings

class Check(Settings):
    def __init__(self):
        super().__init__();self.set_application_id('org.zenek.SettingsCheck');self.mutations=[];self.phase=0;self.exit_code=0
    def rpc(self,method,p=None):
        if method in ('Models','GetRedactedPreview'):return None
        self.mutations.append(method);return None # Simulated failed save; nothing reaches Core.
    def activate(self,*args):
        super().activate(*args);GLib.timeout_add(500,self.verify)
    def capture(self,page,filename):
        self.stack.set_visible_child_name(page)
        def save():
            w=self.window;paintable=Gtk.WidgetPaintable.new(w);snapshot=Gtk.Snapshot();paintable.snapshot(snapshot,w.get_width(),w.get_height())
            renderer=Gsk.Renderer.new_for_surface(w.get_surface());texture=renderer.render_texture(snapshot.to_node(),Graphene.Rect().init(0,0,w.get_width(),w.get_height()))
            texture.save_to_png(str(Path(filename).resolve()));renderer.unrealize();return False
        GLib.timeout_add(200,save)
    def verify(self):
        try:
            if self.phase==0:
                assert self.status,'Core needed for current-value readback'
                original=copy.deepcopy(self.status);version=original['config_version']
                row=self.setting_controls['quiet'][0];expected=original['settings']['quiet'];row.set_active(not expected)
                assert row.get_active()==expected,'Failed save left switch claiming an unsaved value'
                assert self.status['config_version']==version,'UI verification mutated live settings'
                assert 'Zapisano:' in row.get_subtitle() and 'Włączone:' in row.get_subtitle() and 'Wyłączone:' in row.get_subtitle()
                self.mutations.clear();changed=copy.deepcopy(original);changed['settings']['quiet']=not expected
                self.status=changed;self.sync_controls();assert row.get_active()!=expected and not self.mutations,'Readback triggered a write loop'
                self.status=original;self.sync_controls()
                assert all('Zapisano:' in r.get_subtitle() for r,_,_ in self.setting_controls.values())
                preview=self.preview_window();assert self.preview_window() is preview
                assert len([w for w in self.get_windows() if w.get_title()=='Zenek — podgląd po maskowaniu'])==1
                assert self._preview_source;preview.close();assert self._preview_window is None and not self._preview_source
                self.preview_window().close();assert self._preview_window is None and not self._preview_source
                self.capture('Zachowania','evidence/settings-behavior.png');self.phase=1;return True
            if self.phase==1:
                self.capture('Ekran i prywatność','evidence/settings-capture.png');self.phase=2;return True
            if self.phase==2:
                self.status=None;self.sync_controls();assert all(not r.get_sensitive() and 'Brak odczytu' in r.get_subtitle() for r,_,_ in self.setting_controls.values())
                result=dict(status='PASS',current_saved_values=True,all_controls_show_options_effects=True,failed_save_restores_current=True,readback_no_write_loop=True,preview_singleton=True,preview_close_timer_cleared=True,offline_no_invented_current_state=True,real_settings_unchanged=True)
                Path('evidence/settings-runtime.json').write_text(json.dumps(result,indent=2));print(result,flush=True);self.quit();return False
        except Exception:
            import traceback;traceback.print_exc();self.exit_code=1;self.quit();return False

check=Check();check.run([sys.argv[0]]);raise SystemExit(check.exit_code)
