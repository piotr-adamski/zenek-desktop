"""Real Portal/PipeWire periodic snapshots of an owned synthetic GTK scene.

Uses prior owner-approved source restoration. No raw images saved. Restores
settings and stops capture; synthetic visual data only may reach SIWC.
"""
import json
from pathlib import Path
import time
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from zenek_core.ipc import call

start=call('GetStatus')
if start['screen']!='OFF' or start['locked'] or start['idle'] or start['active_jobs']:raise RuntimeError('Requires unlocked active user, capture OFF and no model jobs')
original={k:start['settings'][k] for k in ['auto_hide_on_fullscreen','screen_snapshot_seconds']}
app=Gtk.Application(application_id='org.zenek.SnapshotTest');window=None;drawing=None;phase=0;states=[];deadline=time.monotonic()+75;first_at=0;first_count=0;first_request=start.get('last_vision_request');graphic=False;exit_code=0
def patch(values):
 s=call('GetStatus');call('UpdateSettings',dict(expected_version=s['config_version'],patch=values))
def record(s,label):
 states.append(dict(step=label,screen=s['screen'],phase=s['capture_phase'],pipeline=s['capture_pipeline_state'],portal_session_open=s['capture_portal_session'],confirmed_closed_sessions=s['capture_closed_sessions'],frames=s['capture_frames'],analysis=s['screen_analysis'],last_vision_request=s.get('last_vision_request'),animation=s['animation']['state']))
def finish(status,reason=None):
 global exit_code
 call('PauseScreenCapture');window.unfullscreen();patch(original)
 final=call('GetStatus');result=dict(status=status,reason=reason,states=states,final_off=final['screen']=='OFF',preview_cleared=call('GetRedactedPreview') is None,settings_restored=all(final['settings'][k]==v for k,v in original.items()))
 Path('evidence/snapshots-native-runtime.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True);exit_code=0 if status=='PASS' else 1;app.quit();return False
def poll():
 try:return step()
 except Exception as e:return finish('FAIL',type(e).__name__+': '+str(e))
def step():
 global phase,first_at,first_count,graphic
 s=call('GetStatus')
 if time.monotonic()>deadline:return finish('FAIL','Timed out waiting for actual snapshot/analysis')
 if s.get('capture_error') and s['screen']=='OFF':return finish('FAIL',s['capture_error'])
 if phase==0 and s['capture_frames']>=1 and s['capture_pipeline_state']=='NULL' and not s['capture_portal_session'] and s['capture_closed_sessions']>=1 and (s.get('screen_analysis') or {}).get('mode')=='OCR':
  if s.get('last_vision_request')!=first_request:return finish('FAIL','Text-only synthetic scene caused visual upload')
  record(s,'text -> local OCR without visual upload');first_at=time.monotonic();first_count=s['capture_frames'];phase=1
 elif phase==1 and time.monotonic()-first_at>=5:
  if s['capture_frames']!=first_count or s['capture_pipeline_state']!='NULL' or s['capture_portal_session']:return finish('FAIL','Source/session remained active between snapshots')
  record(s,'five seconds idle -> session closed and NULL, no new frames');graphic=True;drawing.queue_draw();phase=2
 elif phase==2 and s['capture_frames']>first_count and s.get('last_vision_request') and s['last_vision_request'].get('completed') and s['capture_pipeline_state']=='NULL' and not s['capture_portal_session'] and s['capture_closed_sessions']>=2:
  record(s,'large synthetic graphic -> visual interpretation');return finish('PASS')
 return True
def draw(_area,cr,width,height):
 if not graphic:
  cr.set_source_rgb(.98,.98,.96);cr.paint();cr.set_source_rgb(.08,.12,.18);cr.select_font_face('Sans');cr.set_font_size(30)
  for index,text in enumerate(['ZENEK: WLASNY TEST OCR','Paradoksy podrozy w czasie.','To jest syntetyczny, niesekretny dokument.','Tekst powinien trafic tylko do lokalnego OCR.','token: SYNTHETIC_SECRET_NEVER_SEND','Ponizsza grafika pojawi sie w drugiej fazie.']):cr.move_to(60,100+index*65);cr.show_text(text)
 else:
  for y in range(0,height,48):
   for x in range(0,width,48):
    cr.set_source_rgb((x%255)/255,(y%255)/255,.3 if (x//48+y//48)%2 else .8);cr.rectangle(x,y,48,48);cr.fill()
def activate(app):
 global window,drawing
 window=Gtk.ApplicationWindow(application=app,title='Zenek — syntetyczne zrzuty OCR i grafika');drawing=Gtk.DrawingArea();drawing.set_draw_func(draw);window.set_child(drawing)
 display=Gdk.Display.get_default();monitors=display.get_monitors();x,y=start['ui_layout']['sprite'][:2]
 for i in range(monitors.get_n_items()):
  monitor=monitors.get_item(i);r=monitor.get_geometry()
  if r.x<=x<r.x+r.width and r.y<=y<r.y+r.height:target=monitor;break
 else:raise RuntimeError('Cannot resolve sprite monitor')
 patch({'auto_hide_on_fullscreen':False,'screen_snapshot_seconds':15});window.present();window.fullscreen_on_monitor(target)
 def begin():call('ResumeScreenCapture');GLib.timeout_add(500,poll);return False
 GLib.timeout_add_seconds(2,begin)
 window.connect('close-request',lambda *_:finish('FAIL','Test window closed before completion'))
app.connect('activate',activate);app.run(['zenek-snapshots-uat']);raise SystemExit(exit_code)
