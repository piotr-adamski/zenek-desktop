import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk

app=Gtk.Application(application_id='org.zenek.SyntheticTest')
def activate(app):
    window=Gtk.ApplicationWindow(application=app,title='Zenek — syntetyczny test prywatności',default_width=1000,default_height=700)
    css=Gtk.CssProvider();css.load_from_data(b'window {background: #faf9f2;} label {color: #182a39; font-size: 28px;} .secret {background: #efb6aa; padding: 30px;}')
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=35,margin_start=55,margin_end=55,margin_top=75,margin_bottom=55)
    box.append(Gtk.Label(label='ZENEK — TEST SYNTETYCZNY'))
    box.append(Gtk.Label(label='Publiczny temat: paradoksy podróży w czasie'))
    box.append(Gtk.Label(label='Białe tło. Tekst w granatowym kolorze.'))
    secret=Gtk.Label(label='API KEY: SYNTHETIC_SECRET_123456');secret.add_css_class('secret');box.append(secret)
    box.append(Gtk.Label(label='Ten wiersz musi zostać zamaskowany przed wysyłką.'))
    close=Gtk.Button(label='Zamknij test');close.connect('clicked',lambda _:app.quit());box.append(close)
    window.set_child(box);window.maximize();window.present()
app.connect('activate',activate);app.run(['zenek-synthetic-test'])
