"""Render only Zenek's own GTK widget; never capture the desktop."""
import sys
from pathlib import Path
import gi
gi.require_version('Gtk','4.0');gi.require_version('Gsk','4.0');gi.require_version('Graphene','1.0')
from gi.repository import Gtk,Gsk,Graphene,GLib
from zenek_settings.app import Settings

class Render(Settings):
    def __init__(self):
        super().__init__();self.set_application_id('org.zenek.SettingsRender')
    def activate(self,*args):
        super().activate(*args);self.stack.set_visible_child_name('Osobowość')
        GLib.timeout_add_seconds(2,self.save)
    def save(self):
        w=self.window;paintable=Gtk.WidgetPaintable.new(w);snapshot=Gtk.Snapshot()
        paintable.snapshot(snapshot,w.get_width(),w.get_height());node=snapshot.to_node()
        renderer=Gsk.Renderer.new_for_surface(w.get_surface());rect=Graphene.Rect().init(0,0,w.get_width(),w.get_height())
        texture=renderer.render_texture(node,rect);texture.save_to_png(str(Path('evidence/settings-personality.png').resolve()))
        renderer.unrealize();print('ZENEK_SETTINGS_RENDER_PASS',flush=True);self.quit();return GLib.SOURCE_REMOVE

Render().run([sys.argv[0]])
