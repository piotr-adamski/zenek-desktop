"""Synthetic Wayland client for the isolated GNOME dialog regression."""
import json
import os
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk

app=Gtk.Application(application_id='org.zenek.DialogTest')
def activate(app):
    window=Gtk.ApplicationWindow(application=app,title='Zenek dialog test client',default_width=420,default_height=260)
    window.set_decorated(False)
    surface=Gtk.Button(label='Synthetic click target')
    clicks=Gtk.GestureClick();counter=0
    def pressed(*_):
        nonlocal counter
        counter+=1
        print('CLIENT_CLICK '+str(counter),flush=True)
        Path(os.environ['ZENEK_TEST_CLICK_FILE']).write_text(json.dumps({'clicks':counter}))
    clicks.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);clicks.connect('pressed',pressed);surface.add_controller(clicks)
    window.set_child(surface);window.present()
app.connect('activate',activate)
app.run(['zenek-dialog-test'])
