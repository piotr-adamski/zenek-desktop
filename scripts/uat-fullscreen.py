"""Actual GTK fullscreen -> native GNOME signals -> owned extension/Core.

No lock, logout, global settings, pointer injection, or capture activation.
"""
import json
from pathlib import Path
import subprocess
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from zenek_core.ipc import call

app=Gtk.Application(application_id='org.zenek.FullscreenTest')
start=call('GetStatus');initial=start['settings']['auto_hide_on_fullscreen'];pid=subprocess.check_output(['systemctl','--user','show','zenek-core.service','-p','MainPID','--value'],text=True).strip()
if start['locked'] or not start['manual_visible'] or start['screen']!='OFF':raise RuntimeError('Test requires unlocked manually visible UI with capture OFF')
observed=[];phase=0;deadline=time.monotonic()+50;window=None;target=None
def save(s,label):observed.append(dict(step=label,fullscreen=s['fullscreen'],visibility=s['visibility'],manual_visible=s['manual_visible'],screen=s['screen'],sprite_mapped=s['ui_layout'].get('sprite_mapped'),gtk_fullscreen=window.is_fullscreen()))
def patch(value):
 s=call('GetStatus');call('UpdateSettings',dict(expected_version=s['config_version'],patch={'auto_hide_on_fullscreen':value}))
def finish(status,reason=None):
 window.unfullscreen();patch(initial);call('ShowCompanion')
 current=subprocess.check_output(['systemctl','--user','show','zenek-core.service','-p','MainPID','--value'],text=True).strip()
 evidence=dict(status=status,reason=reason,states=observed,core_pid_unchanged=current==pid,auto_resume_capture=False)
 Path('evidence/fullscreen-runtime.json').write_text(json.dumps(evidence,indent=2));print(evidence,flush=True);app.quit();return False
def poll():
 global phase
 s=call('GetStatus')
 if time.monotonic()>deadline:return finish('FAIL','Native transition timeout')
 if phase==0 and s['fullscreen'] and s['visibility']=='HIDDEN' and s['ui_layout'].get('sprite_mapped') is False:
  save(s,'fullscreen ON hides');window.unfullscreen();phase=1
 elif phase==1 and not s['fullscreen'] and s['visibility']=='VISIBLE' and s['ui_layout'].get('sprite_mapped'):
  save(s,'fullscreen exit restores previous visible');call('HideCompanion');window.fullscreen_on_monitor(target);phase=2
 elif phase==2 and s['fullscreen'] and not s['manual_visible']:
  save(s,'manual hidden wins');window.unfullscreen();phase=3
 elif phase==3 and not s['fullscreen'] and s['visibility']=='HIDDEN' and s['ui_layout'].get('sprite_mapped') is False:
  save(s,'exit preserves manual hidden');call('ShowCompanion');patch(False);window.fullscreen_on_monitor(target);phase=4
 elif phase==4 and s['fullscreen'] and s['visibility']=='VISIBLE' and s['ui_layout'].get('sprite_mapped'):
  save(s,'setting OFF disables own auto-hide');return finish('PASS')
 return True
def activate(app):
 global window,target
 window=Gtk.ApplicationWindow(application=app,title='Zenek — test pełnego ekranu',default_width=480,default_height=220)
 window.set_child(Gtk.Label(label='Krótki test Zenka.\nOkno zamknie się automatycznie.'))
 monitors=Gdk.Display.get_default().get_monitors();x,y=start['ui_layout']['sprite'][:2]
 for index in range(monitors.get_n_items()):
  monitor=monitors.get_item(index);r=monitor.get_geometry()
  if r.x<=x<r.x+r.width and r.y<=y<r.y+r.height:target=monitor;break
 if target is None:raise RuntimeError('Cannot resolve sprite monitor')
 window.present();patch(True);GLib.timeout_add_seconds(2,lambda:(window.fullscreen_on_monitor(target),False)[1]);GLib.timeout_add(500,poll)
app.connect('activate',activate);app.run(['zenek-fullscreen-uat'])
