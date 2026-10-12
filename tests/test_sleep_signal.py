"""The installed Gio callback shape, on a private bus only."""
import subprocess
import sys


def test_real_gio_sleep_callback_cancels_and_wakes_without_catchup():
    code=r'''
import os,random,threading,time
from types import SimpleNamespace
from gi.repository import Gio,GLib
from zenek_core.main import Core
assert '/run/user/1000/bus' not in os.environ['DBUS_SESSION_BUS_ADDRESS']
core=Core.__new__(Core);core.memory=object()
core.behavior=SimpleNamespace(suspended=False,next_review=0,rng=random.Random(1))
stopped=[];core.capture=SimpleNamespace(stop=lambda:stopped.append('capture'))
core.research=SimpleNamespace(stop=lambda:stopped.append('research'))
core.cancel={name:threading.Event() for name in ('conversation','background','vision','research')}
core.emit_state=lambda:None
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
sid=bus.signal_subscribe(None,'org.zenek.Test','PrepareForSleep','/org/zenek/Test',None,Gio.DBusSignalFlags.NONE,core.prepare_sleep)
def emit(value):
    bus.emit_signal(None,'/org/zenek/Test','org.zenek.Test','PrepareForSleep',GLib.Variant('(b)',(value,)))
    bus.flush_sync(None)
    deadline=time.monotonic()+1
    while time.monotonic()<deadline:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if core.behavior.suspended==value:return
        time.sleep(.005)
    raise AssertionError('Actual Gio callback did not update suspend state')
emit(True)
assert stopped==['capture','research'] and all(event.is_set() for event in core.cancel.values())
before=time.monotonic();emit(False)
assert before+60<=core.behavior.next_review<=time.monotonic()+300
assert stopped==['capture','research'],'Wake restarted capture or research'
bus.signal_unsubscribe(sid)
'''
    result=subprocess.run(['dbus-run-session','--',sys.executable,'-c',code],
                          text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=8)
    assert result.returncode==0,result.stdout
