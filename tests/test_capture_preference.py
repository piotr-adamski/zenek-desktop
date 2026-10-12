import threading
import time
from types import SimpleNamespace
from gi.repository import GLib
from zenek_core.main import Core
from zenek_core.behavior import Behavior
from zenek_core.memory import Memory

def core_fixture(tmp_path):
    m=Memory(tmp_path/'db','ab'*32);m.patch({'capture_enabled':True},m.settings()[0])
    c=Core.__new__(Core);c.memory=m;c.stopping=False;c.behavior=Behavior(m)
    c.behavior.last_ui_report=time.monotonic();c.behavior.idle_seconds=0
    c.capture_indicator=True;c.capture_auto_resume=False;c.capture_pause_reason=''
    c.preview_lock=threading.RLock();c.redacted_preview=object();c.screen_context=object();c.vision_unreported=True
    c.redactor=SimpleNamespace(reset=lambda:None);c.emit_state=lambda:None;c.cancel={'vision':threading.Event()}
    c.research=SimpleNamespace(stop=lambda:None)
    class Source:
        state='ACTIVE';last_error='';starts=0;restore_only=None
        def stop(self):self.state='OFF';c.capture_changed()
        def start(self,restore_only=False):
            self.restore_only=restore_only;self.starts+=1;self.last_error='';self.state='ACTIVE';c.capture_changed()
    c.capture=Source();return c

def test_lock_idle_hidden_and_ui_loss_preserve_preference_and_resume_once(tmp_path):
    c=core_fixture(tmp_path);m=c.memory;version=m.settings()[0]
    for reason in ('locked','idle','hidden','ui'):
        if reason=='locked':c.behavior.locked=True
        elif reason=='idle':c.behavior.idle_seconds=3600
        elif reason=='hidden':c.behavior.manual_visible=False
        else:c.handle('SuspendScreenCapture',{})
        c.enforce_capture()
        assert c.capture.state=='OFF' and m.settings()[1]['capture_enabled'] and m.settings()[0]==version
        assert c.redacted_preview is None and c.screen_context is None and c.cancel['vision'].is_set()
        c.behavior.locked=False;c.behavior.idle_seconds=0;c.behavior.manual_visible=True;c.behavior.last_ui_report=time.monotonic()
        c.enforce_capture();starts=c.capture.starts;c.enforce_capture()
        assert c.capture.state=='ACTIVE' and c.capture.restore_only and c.capture.starts==starts
    c.handle('PauseScreenCapture',{});c.enforce_capture()
    assert c.capture.state=='OFF' and not m.settings()[1]['capture_enabled']
    m.close()

def test_error_keeps_on_without_retry_loop_and_manual_resume_works(tmp_path):
    c=core_fixture(tmp_path);c.capture.last_error='Portal odmówił';c.capture.stop()
    assert c.memory.settings()[1]['capture_enabled'] and 'Portal odmówił' in c.capture_pause_reason
    for _ in range(3):c.enforce_capture()
    assert c.capture.starts==0
    c.handle('ResumeScreenCapture',{});assert c.capture.starts==1 and c.capture.state=='ACTIVE'
    reopened=Memory(c.memory.path,'ab'*32);assert reopened.settings()[1]['capture_enabled'];reopened.close();c.memory.close()

def test_wake_waits_for_fresh_ui_before_restoring_saved_plan(tmp_path):
    c=core_fixture(tmp_path)
    c.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(True,)))
    assert c.capture.state=='OFF' and c.memory.settings()[1]['capture_enabled']
    c.prepare_sleep(None,None,None,None,None,GLib.Variant('(b)',(False,)))
    c.enforce_capture();assert c.capture.starts==0
    c.behavior.last_ui_report=time.monotonic();c.enforce_capture()
    assert c.capture.starts==1 and c.capture.restore_only
    c.memory.close()
