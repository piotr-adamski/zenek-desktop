import threading
import time
import gi
gi.require_version('Gst','1.0')
from gi.repository import Gst,GLib
from zenek_core.capture import Capture

def test_real_gstreamer_pipeline_only_delivers_one_snapshot_per_wake():
    class SyntheticSource(Capture):
        def open_session(self):
            self.session_epoch+=1
            self.pipeline=Gst.parse_launch('videotestsrc is-live=true ! video/x-raw,format=RGB,width=64,height=48,framerate=10/1 ! appsink name=sink emit-signals=true max-buffers=1 drop=true sync=false')
            sink=self.pipeline.get_by_name('sink');sink.connect('new-sample',self.sample,self.generation,self.session_epoch)
            bus=self.pipeline.get_bus();bus.add_signal_watch();bus.connect('message',self.message)
            self.phase='SNAPSHOT';self.take_snapshot(self.generation)
    Gst.init(None);capture=SyntheticSource.__new__(SyntheticSource)
    capture.state='ACTIVE';capture.generation=1;capture.permitted=lambda:True;capture.on_state=lambda:None;capture.interval=lambda:60
    capture.snapshot_source=0;capture.snapshot_timeout=0;capture.snapshot_pending=False;capture.phase='WAITING';capture.frame_lock=threading.Lock();capture.last_sample=0;capture.frames=0;capture.stream={};capture.last_error=''
    capture.state_lock=threading.Lock()
    capture.pipeline=None;capture.pipeline_state='NULL';capture.session_epoch=0;capture.fd=None;capture.pending={};capture.signal_ids=[];capture.session=None
    frames=[];capture.on_frame=lambda image,*_:(frames.append(image.size),image.close())
    context=GLib.MainContext.default()
    def spin(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            while context.pending():context.iteration(False)
            time.sleep(.005)
    try:
        capture.begin_snapshot(1);spin(.5)
        assert frames==[(64,48)] and capture.phase=='WAITING' and not capture.snapshot_pending
        assert capture.pipeline is None and capture.pipeline_state=='NULL'
        assert capture.next_snapshot_at-time.time()>58
        spin(.3);assert len(frames)==1 # No continuous frame delivery while waiting.
        if capture.snapshot_source:GLib.source_remove(capture.snapshot_source);capture.snapshot_source=0
        capture.begin_snapshot(1);spin(.5);assert len(frames)==2 and capture.pipeline is None and capture.pipeline_state=='NULL'
    finally:
        capture.generation+=1
        if capture.pipeline:capture.pipeline.set_state(Gst.State.NULL)
        for source in (capture.snapshot_source,capture.snapshot_timeout):
            if source:GLib.source_remove(source)
