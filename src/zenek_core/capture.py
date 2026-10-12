"""Portal consent -> restricted PipeWire fd -> RAM only. No framebuffer fallback."""
import os
import threading
import time
import uuid
import gi
gi.require_version('Gst','1.0');gi.require_version('GstVideo','1.0')
from gi.repository import Gio,GLib,Gst,GstVideo
from PIL import Image
from .memory import Keyring

DEST='org.freedesktop.portal.Desktop';OBJECT='/org/freedesktop/portal/desktop';IFACE='org.freedesktop.portal.ScreenCast'

def unpack(value):
    if isinstance(value,GLib.Variant):return unpack(value.unpack())
    if isinstance(value,dict):return {k:unpack(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [unpack(v) for v in value]
    return value

class Capture:
    def __init__(self,on_frame,on_state,permitted,interval=lambda:60):
        Gst.init(None)
        self.bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.on_frame=on_frame;self.on_state=on_state;self.permitted=permitted
        self.state='OFF';self.session=None;self.pipeline=None;self.fd=None;self.generation=0
        self.pending={};self.signal_ids=[];self.stream={};self.last_sample=0;self.frame_lock=threading.Lock()
        self.last_error='';self.frames=0
        self.interval=interval;self.snapshot_source=0;self.snapshot_timeout=0;self.snapshot_pending=False;self.phase='OFF';self.next_snapshot_at=0;self.last_snapshot_at=0
        self.pipeline_state='NULL';self.state_lock=threading.Lock()
        self.session_epoch=0;self.closed_sessions=0

    def update(self,state):self.state=state;self.on_state()
    def start(self,restore_only=False):
        if self.state!='OFF' or not self.permitted():raise ValueError('Obserwacja wymaga widocznej, aktywnej i odblokowanej sesji')
        self.restore_only=restore_only
        if restore_only and not Keyring().get('portal-restore'):raise ValueError('Brak zapisanej zgody Portalu')
        self.last_error='';self.generation+=1;self.session_epoch=0;self.update('AWAITING_PORTAL')
        self.open_session()

    def open_session(self):
        self.session_epoch+=1;self.phase='PORTAL';self.on_state()
        options={'session_handle_token':GLib.Variant('s','zenek_session_'+uuid.uuid4().hex)}
        self.request('CreateSession',None,options,self.created)

    def request(self,method,session,options,callback):
        generation=self.generation;epoch=self.session_epoch
        token='zenek_'+uuid.uuid4().hex;options=dict(options,handle_token=GLib.Variant('s',token))
        sender=self.bus.get_unique_name()[1:].replace('.','_')
        path='/org/freedesktop/portal/desktop/request/'+sender+'/'+token
        def response(connection,sender,obj,interface,name,params,data):
            sid=self.pending.pop(path,None)
            if sid:self.bus.signal_unsubscribe(sid)
            code,result=unpack(params)
            if generation!=self.generation or epoch!=self.session_epoch:return
            if code!=0 or not self.permitted():
                self.last_error=method+': portal denied/cancelled or session policy changed';self.stop();return
            try:callback(result)
            except Exception as e:
                self.last_error=method+': '+type(e).__name__+(' '+str(e) if isinstance(e,(ValueError,TypeError)) else '')
                self.stop();self.on_state()
        sid=self.bus.signal_subscribe(DEST,'org.freedesktop.portal.Request','Response',path,None,Gio.DBusSignalFlags.NONE,response,None)
        self.pending[path]=sid
        args=GLib.Variant('(a{sv})',(options,)) if method=='CreateSession' else GLib.Variant('(osa{sv})',(session,'',options)) if method=='Start' else GLib.Variant('(oa{sv})',(session,options))
        def complete(connection,result):
            try:connection.call_finish(result)
            except Exception as e:
                if generation==self.generation and epoch==self.session_epoch:self.last_error=method+': '+type(e).__name__;self.stop()
        self.bus.call(DEST,OBJECT,IFACE,method,args,GLib.VariantType.new('(o)'),Gio.DBusCallFlags.NONE,5000,None,complete)

    def created(self,result):
        self.session=result['session_handle']
        sid=self.bus.signal_subscribe(DEST,'org.freedesktop.portal.Session','Closed',self.session,None,Gio.DBusSignalFlags.NONE,lambda *args:self.stop(),None)
        self.signal_ids.append(sid)
        options={'types':GLib.Variant('u',1),'multiple':GLib.Variant('b',False),'cursor_mode':GLib.Variant('u',1)}
        version=self.bus.call_sync(DEST,OBJECT,'org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',(IFACE,'version')),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
        if isinstance(version,GLib.Variant):version=version.unpack()
        if version>=4:
            options['persist_mode']=GLib.Variant('u',2)
            restore=Keyring().get('portal-restore')
            if restore:options['restore_token']=GLib.Variant('s',restore)
            elif self.session_epoch>1 or getattr(self,'restore_only',False):raise ValueError('Brak zapisanej zgody na kolejny zrzut; włącz ponownie ręcznie')
        elif self.session_epoch>1 or getattr(self,'restore_only',False):raise ValueError('Portal nie obsługuje zapamiętania zgody na okresowe zrzuty')
        self.request('SelectSources',self.session,options,lambda _:self.request('Start',self.session,{},self.started))

    def started(self,result):
        if result.get('restore_token'):Keyring().put('portal-restore',result['restore_token'])
        streams=result.get('streams',[])
        if len(streams)!=1:raise ValueError('Wybierz jeden monitor')
        node,props=streams[0]
        if type(node) is not int or node<0 or props.get('source_type')!=1:raise ValueError('Nieprawidłowe źródło')
        value,fds=self.bus.call_with_unix_fd_list_sync(DEST,OBJECT,IFACE,'OpenPipeWireRemote',GLib.Variant('(oa{sv})',(self.session,{})),GLib.VariantType.new('(h)'),Gio.DBusCallFlags.NONE,5000,None,None)
        self.fd=fds.get(value.unpack()[0]);self.stream=props
        self.pipeline=Gst.Pipeline.new('zenek-capture')
        source=Gst.ElementFactory.make('pipewiresrc');source.set_property('fd',self.fd)
        serial=props.get('pipewire-serial')
        if serial is not None:source.set_property('target-object',str(serial))
        else:source.set_property('path',str(node)) # Portal v5 supplies node ID, not object serial.
        source.set_property('always-copy',True)
        convert=Gst.ElementFactory.make('videoconvert');rate=Gst.ElementFactory.make('videorate');rate.set_property('drop-only',True)
        caps=Gst.ElementFactory.make('capsfilter');caps.set_property('caps',Gst.Caps.from_string('video/x-raw,format=RGB,framerate=1/1'))
        sink=Gst.ElementFactory.make('appsink');sink.set_property('emit-signals',True);sink.set_property('max-buffers',1);sink.set_property('drop',True);sink.set_property('sync',False)
        for element in [source,convert,rate,caps,sink]:
            if element is None:raise ValueError('Brak elementu GStreamer')
            self.pipeline.add(element)
        for a,b in zip([source,convert,rate,caps],[convert,rate,caps,sink]):
            if not a.link(b):raise ValueError('Nie udało się połączyć pipeline')
        sink.connect('new-sample',self.sample,self.generation,self.session_epoch)
        bus=self.pipeline.get_bus();bus.add_signal_watch();bus.connect('message',self.message)
        # The session exists only for a shot; the saved grant restores the next one.
        self.phase='SNAPSHOT';self.update('ACTIVE');self.next_snapshot_at=0
        self.snapshot_source=GLib.timeout_add(300,self.take_snapshot,self.generation)

    def set_pipeline_state(self,pipeline,state,generation):
        # PipeWire negotiation can block inside GStreamer. Never hold D-Bus/UI.
        def change():
            with self.state_lock:
                if state!=Gst.State.NULL and (generation!=self.generation or pipeline is not self.pipeline):return
                result=pipeline.set_state(state)
            if result==Gst.StateChangeReturn.FAILURE and state!=Gst.State.NULL:
                def failed():
                    if generation==self.generation and pipeline is self.pipeline:self.last_error='Zmiana stanu źródła nieudana';self.stop()
                    return GLib.SOURCE_REMOVE
                GLib.idle_add(failed)
        threading.Thread(target=change,daemon=True,name='zenek-snapshot-state').start()

    def schedule_snapshot(self,seconds):
        if self.snapshot_source:GLib.source_remove(self.snapshot_source)
        self.next_snapshot_at=time.time()+seconds
        self.snapshot_source=GLib.timeout_add(max(1,int(seconds*1000)),self.begin_snapshot,self.generation)

    def begin_snapshot(self,generation):
        self.snapshot_source=0
        if generation!=self.generation or self.state!='ACTIVE':return GLib.SOURCE_REMOVE
        if not self.permitted():self.stop();return GLib.SOURCE_REMOVE
        self.next_snapshot_at=0;self.open_session();return GLib.SOURCE_REMOVE

    def take_snapshot(self,generation):
        self.snapshot_source=0
        if generation!=self.generation or self.state!='ACTIVE' or not self.pipeline:return GLib.SOURCE_REMOVE
        if not self.permitted():self.stop();return GLib.SOURCE_REMOVE
        with self.frame_lock:self.snapshot_pending=True
        self.phase='SNAPSHOT';self.next_snapshot_at=0;self.on_state()
        self.snapshot_timeout=GLib.timeout_add_seconds(12,self.snapshot_expired,generation)
        self.set_pipeline_state(self.pipeline,Gst.State.PLAYING,generation)
        return GLib.SOURCE_REMOVE

    def snapshot_expired(self,generation):
        self.snapshot_timeout=0
        if generation==self.generation and self.snapshot_pending:
            self.last_error='Przekroczono czas pobrania pojedynczej klatki';self.stop()
        return GLib.SOURCE_REMOVE

    def snapshot_complete(self,generation,epoch=None):
        if generation!=self.generation or self.state!='ACTIVE' or not self.pipeline or epoch is not None and epoch!=self.session_epoch:return GLib.SOURCE_REMOVE
        if self.snapshot_timeout:GLib.source_remove(self.snapshot_timeout);self.snapshot_timeout=0
        self.close_session()
        self.phase='WAITING';self.schedule_snapshot(self.interval());self.on_state();return GLib.SOURCE_REMOVE

    def sample(self,sink,generation,epoch=None):
        sample=sink.emit('pull-sample')
        if not sample:return Gst.FlowReturn.OK
        if generation!=self.generation or epoch is not None and epoch!=self.session_epoch or self.state!='ACTIVE' or not self.permitted():return Gst.FlowReturn.OK
        with self.frame_lock:
            if not self.snapshot_pending:return Gst.FlowReturn.OK
            self.snapshot_pending=False
        self.last_sample=time.monotonic()
        self.last_snapshot_at=time.time()
        self.frames+=1
        stream=dict(self.stream)
        try:
            info=GstVideo.VideoInfo.new_from_caps(sample.get_caps());w,h=info.width,info.height
            if w<1 or h<1 or w*h>16000000:return Gst.FlowReturn.OK
            buffer=sample.get_buffer();success,mapinfo=buffer.map(Gst.MapFlags.READ)
            if not success:return Gst.FlowReturn.OK
            try:image=Image.frombytes('RGB',(w,h),mapinfo.data,'raw','RGB',info.stride[0],1)
            finally:buffer.unmap(mapinfo)
            if generation==self.generation and self.permitted():self.on_frame(image,stream,generation)
            else:image.close()
        finally:GLib.idle_add(self.snapshot_complete,generation,epoch)
        return Gst.FlowReturn.OK

    def message(self,bus,message):
        if not self.pipeline or bus!=self.pipeline.get_bus():return
        if message.type==Gst.MessageType.STATE_CHANGED and message.src==self.pipeline:
            _,state,_=message.parse_state_changed();self.pipeline_state=state.value_nick.upper();self.on_state()
        if message.type in (Gst.MessageType.ERROR,Gst.MessageType.EOS):
            if message.type==Gst.MessageType.ERROR:
                error,_debug=message.parse_error();self.last_error='PipeWire: '+error.message[:300]
            else:self.last_error='PipeWire stream ended'
            self.stop()

    def stop(self):
        self.generation+=1
        for name in ('snapshot_source','snapshot_timeout'):
            source=getattr(self,name)
            if source:GLib.source_remove(source);setattr(self,name,0)
        with self.frame_lock:self.snapshot_pending=False
        self.phase='OFF';self.next_snapshot_at=0
        self.close_session();self.update('OFF')

    def close_session(self):
        if self.pipeline:
            pipeline=self.pipeline;self.pipeline=None;pipeline.get_bus().remove_signal_watch()
            self.set_pipeline_state(pipeline,Gst.State.NULL,self.generation)
        self.pipeline_state='NULL'
        if self.fd is not None:
            os.close(self.fd);self.fd=None
        for path,sid in list(self.pending.items()):
            self.bus.signal_unsubscribe(sid)
            self.bus.call(DEST,path,'org.freedesktop.portal.Request','Close',None,None,Gio.DBusCallFlags.NONE,1000,None,None)
        self.pending.clear()
        for sid in self.signal_ids:self.bus.signal_unsubscribe(sid)
        self.signal_ids=[]
        session=self.session;self.session=None;self.stream={}
        if session:
            def closed(connection,result):
                try:connection.call_finish(result);self.closed_sessions+=1;self.on_state()
                except GLib.Error:
                    if self.state!='OFF':self.last_error='Nie potwierdzono zamknięcia sesji Portalu';self.stop()
            self.bus.call(DEST,session,'org.freedesktop.portal.Session','Close',None,None,Gio.DBusCallFlags.NONE,3000,None,closed)
