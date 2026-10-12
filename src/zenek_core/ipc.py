import json
from gi.repository import Gio,GLib

NAME="org.zenek.Desktop1"
PATH="/org/zenek/Desktop1"
XML='''<node><interface name="org.zenek.Desktop1">
<method name="Call"><arg name="method" type="s" direction="in"/><arg name="payload" type="s" direction="in"/><arg name="result" type="s" direction="out"/></method>
<signal name="Event"><arg name="kind" type="s"/><arg name="payload" type="s"/></signal>
</interface></node>'''

def proxy():
    return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,Gio.DBusProxyFlags.DO_NOT_AUTO_START,None,NAME,PATH,NAME,None)

def call(method,payload=None):
    result=proxy().call_sync("Call",GLib.Variant("(ss)",(method,json.dumps(payload or {}))),Gio.DBusCallFlags.NO_AUTO_START,5000,None)
    value=json.loads(result.unpack()[0])
    if not value.get("ok"):raise RuntimeError(value.get("error","Błąd Core"))
    return value.get("result")

class IPC:
    def __init__(self,handler):
        self.handler=handler;self.connection=None
        self.owner=Gio.bus_own_name(Gio.BusType.SESSION,NAME,Gio.BusNameOwnerFlags.NONE,self.acquired,None,self.lost)

    def acquired(self,connection,name):
        self.connection=connection
        self.registration=connection.register_object(PATH,Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],self.dispatch,None,None)

    def lost(self,*args):
        self.handler.stop()

    def dispatch(self,connection,sender,path,interface,method,params,invocation):
        try:
            uid=connection.call_sync("org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","GetConnectionUnixUser",GLib.Variant("(s)",(sender,)),GLib.VariantType.new("(u)"),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
            import os
            if uid!=os.getuid():raise ValueError("Nieuprawniony użytkownik")
            operation,raw=params.unpack()
            if len(raw.encode())>65536:raise ValueError("Za duży payload")
            payload=json.loads(raw)
            if not isinstance(payload,dict):raise ValueError("Wymagany obiekt")
            result=self.handler.handle(operation,payload)
            response=dict(ok=True,result=result)
        except Exception as e:
            # Exception text is restricted to our own validation errors.
            response=dict(ok=False,error=str(e) if isinstance(e,(ValueError,RuntimeError)) else type(e).__name__)
        invocation.return_value(GLib.Variant("(s)",(json.dumps(response,ensure_ascii=False),)))

    def emit(self,kind,payload):
        def send():
            if self.connection:self.connection.emit_signal(None,PATH,NAME,"Event",GLib.Variant("(ss)",(kind,json.dumps(payload,ensure_ascii=False))))
            return GLib.SOURCE_REMOVE
        GLib.idle_add(send)
