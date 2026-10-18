"""Native notebook, long conversation and development timeline."""
import argparse
import html
import re
import sys
import time

import gi
gi.require_version('Gtk','4.0');gi.require_version('Adw','1')
from gi.repository import Gtk,Adw,Gio,GLib,Gdk

from zenek_core.ipc import call,proxy


def markup(text):
    value=html.escape(str(text))
    value=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',value)
    value=re.sub(r'`([^`]+)`',r'<tt>\1</tt>',value)
    value=re.sub(r'^#{1,6}\s+(.+)$',r'<b>\1</b>',value,flags=re.M)
    value=re.sub(r'\[([^\]]+)\]\((https://[^\s)]+)\)',r'<a href="\2">\1</a>',value)
    return value


def clear(box):
    while box.get_first_child():box.remove(box.get_first_child())


def label(text='',style=None):
    widget=Gtk.Label(xalign=0,wrap=True,selectable=True)
    widget.set_markup(markup(text))
    if style:widget.add_css_class(style)
    return widget


def button(text,callback):
    widget=Gtk.Button(label=text);widget.connect('clicked',lambda _:callback());return widget


def column(spacing=12):
    return Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=spacing,margin_top=16,margin_bottom=16,margin_start=20,margin_end=20)


def scrolled(child):
    widget=Gtk.ScrolledWindow(vexpand=True,hexpand=True);widget.set_child(child);return widget


class WorkspaceApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='org.zenek.Workspace',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window=None;self.note_path=None;self.context={};self.active_turn=None;self.chat_records=[];self.before=None;self.query='';self._engaged=False;self._refresh_pending=False;self.growth_events=[];self.growth_before=None

    def do_command_line(self,command_line):
        parser=argparse.ArgumentParser();parser.add_argument('--view',choices=['notes','chat','growth'],default='notes');parser.add_argument('--note')
        args=parser.parse_args(command_line.get_arguments()[1:]);self.activate()
        self.stack.set_visible_child_name(args.view)
        if args.note:self.open_note(args.note)
        self.window.present();return 0

    def do_activate(self):
        if self.window:self.window.present();return
        self.window=Adw.ApplicationWindow(application=self,title='Zenek — notatnik i rozmowy',default_width=1060,default_height=780)
        css=Gtk.CssProvider();css.load_from_string('.zenek-card { padding: 16px; }')
        Gtk.StyleContext.add_provider_for_display(self.window.get_display(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.window.connect('close-request',self.closed)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);header=Adw.HeaderBar();outer.append(header)
        self.stack=Adw.ViewStack(vexpand=True);switcher=Adw.ViewSwitcher(stack=self.stack);header.set_title_widget(switcher)
        self.status_box=Gtk.Box(spacing=8,margin_start=20,margin_end=20,margin_top=8,margin_bottom=8)
        self.spinner=Gtk.Spinner();self.status_label=Gtk.Label(xalign=0,hexpand=True,wrap=True);self.status_box.append(self.spinner);self.status_box.append(self.status_label);outer.append(self.status_box)
        outer.append(self.stack);self.toast=Adw.ToastOverlay();self.toast.set_child(outer);self.window.set_content(self.toast)
        self.build_notes();self.build_chat();self.build_growth()
        self.bus_proxy=proxy();self.bus_proxy.connect('g-signal',self.event)
        self.refresh_notes();self.refresh_chat();self.refresh_growth();self.poll()
        self.poll_source=GLib.timeout_add_seconds(2,self.poll);self.window.present()

    def rpc(self,method,payload=None):
        try:return call(method,payload)
        except Exception as error:
            if self.window:self.toast.add_toast(Adw.Toast(title=str(error)[:180]))
            return None

    def closed(self,*_):
        if self._engaged:self.rpc('UserInteraction',{'active':False})
        if getattr(self,'poll_source',0):GLib.source_remove(self.poll_source);self.poll_source=0
        self.quit();return False

    def poll(self):
        status=self.rpc('GetStatus')
        if status:
            activity=status.get('activity_status',{})
            self.status_label.set_text(activity.get('label','Jestem'))
            self.spinner.set_spinning(bool(activity.get('busy')))
        else:self.status_label.set_text('Nie mogę połączyć się z Zenkiem.');self.spinner.stop()
        return True

    def event(self,_proxy,_sender,name,args):
        if name!='Event':return
        import json
        kind,raw=args.unpack();data=json.loads(raw)
        if kind=='StateChanged':
            activity=data.get('activity_status',{});self.status_label.set_text(activity.get('label','Jestem'));self.spinner.set_spinning(bool(activity.get('busy')))
        elif kind=='ReplyDelta' and data['turn']==self.active_turn:
            self.reply_text+=data['delta'];self.live_reply.set_text(self.reply_text);self.bottom()
        elif kind=='ReplyCompleted':
            if data['turn']==self.active_turn:self.active_turn=None;self.send_button.set_sensitive(True);self.refresh_chat()
            elif not self.active_turn:self.refresh_chat()
            self.queue_refresh()
        elif kind=='WorkspaceChanged':self.queue_refresh()
        elif kind=='ErrorChanged':
            if self.active_turn:self.active_turn=None;self.send_button.set_sensitive(True)
            self.toast.add_toast(Adw.Toast(title=data['message'][:180]));self.refresh_chat()

    def queue_refresh(self):
        if self._refresh_pending:return
        self._refresh_pending=True
        def update():
            self._refresh_pending=False;self.refresh_notes();self.refresh_growth();return False
        GLib.timeout_add(200,update)

    def build_notes(self):
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.stack.add_titled_with_icon(page,'notes','Notatnik','accessories-text-editor-symbolic')
        self.note_search=Gtk.SearchEntry(placeholder_text='Szukaj w zapiskach…',margin_start=20,margin_end=20,margin_top=12,margin_bottom=8)
        self.note_search.connect('search-changed',lambda _:self.refresh_notes());page.append(self.note_search)
        split=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,vexpand=True,position=340);page.append(split)
        self.note_list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE);self.note_list.add_css_class('navigation-sidebar');self.note_list.connect('row-selected',self.select_note)
        split.set_start_child(scrolled(self.note_list));split.set_resize_start_child(False);split.set_shrink_start_child(False)
        self.note_body=column();split.set_end_child(scrolled(self.note_body))
        self.note_body.append(label('Moje zapiski','title-1'));self.note_body.append(label('Wybierz wpis, żeby go przeczytać.'))

    def refresh_notes(self):
        rows=self.rpc('ListNotebook',{'query':self.note_search.get_text()})
        if rows is None:return
        clear(self.note_list);selected=None
        for entry in rows:
            row=Gtk.ListBoxRow();row.note_path=entry['path'];content=column(5)
            content.append(label(entry['title'],'heading'));content.append(label(time.strftime('%d.%m.%Y · %H:%M',time.localtime(entry['updated'])),'dim-label'));content.append(label(entry['preview']))
            row.set_child(content);self.note_list.append(row)
            if entry['path']==self.note_path:selected=row
        if selected:self.note_list.select_row(selected)
        elif rows:self.note_list.select_row(self.note_list.get_row_at_index(0))
        else:
            clear(self.note_body);self.note_body.append(label('Jeszcze nie ma pasujących zapisków.','title-2'))

    def select_note(self,_list,row):
        if row:self.open_note(row.note_path)

    def open_note(self,path):
        note=self.rpc('ReadNotebook',{'path':path})
        if not note:return
        self.note_path=path;clear(self.note_body)
        self.note_body.append(label(note['title'],'title-1'));self.note_body.append(label(path,'dim-label'))
        self.note_body.append(button('Porozmawiajmy o tym',lambda:self.discuss_note(note)))
        text=note['text']
        if text.lstrip().startswith('#'):text='\n'.join(text.splitlines()[1:]).lstrip()
        self.note_body.append(label(text))
        self.add_sources(self.note_body,note.get('sources',[]))

    def add_sources(self,box,sources):
        for url in dict.fromkeys(sources):
            if url.startswith('https://'):
                link=Gtk.LinkButton(uri=url,label=url);link.set_halign(Gtk.Align.START);box.append(link)

    def discuss_note(self,note):
        self.context=dict(note_path=note['path']);self.context_label.set_text('Rozmawiamy o: '+note['title']);self.context_box.set_visible(True)
        self.stack.set_visible_child_name('chat');self.composer.get_buffer().set_text('Porozmawiajmy o twoim zapisku „'+note['title']+'”. Co chcesz w nim dalej rozwinąć?');self.send()

    def build_chat(self):
        page=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);self.stack.add_titled_with_icon(page,'chat','Rozmowy','user-available-symbolic')
        self.chat_search=Gtk.SearchEntry(placeholder_text='Szukaj w rozmowach…',margin_start=20,margin_end=20,margin_top=12,margin_bottom=8)
        self.chat_search.connect('search-changed',lambda _:self.refresh_chat());page.append(self.chat_search)
        self.messages=column(18);self.chat_scroll=scrolled(self.messages);page.append(self.chat_scroll)
        bottom=column(8);self.context_box=Gtk.Box(spacing=8);self.context_label=Gtk.Label(xalign=0,hexpand=True,wrap=True);self.context_box.append(self.context_label);self.context_box.append(button('×',self.clear_context));self.context_box.set_visible(False);bottom.append(self.context_box)
        self.composer=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,top_margin=8,bottom_margin=8,left_margin=10,right_margin=10)
        self.composer.set_tooltip_text('Napisz do Zenka. Enter wysyła, Shift+Enter dodaje wiersz.')
        editor=Gtk.ScrolledWindow(min_content_height=70,max_content_height=150,propagate_natural_height=True);editor.set_child(self.composer);editor.add_css_class('card');bottom.append(editor)
        keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key);self.composer.add_controller(keys)
        focus=Gtk.EventControllerFocus();focus.connect('enter',lambda _:self.engage(True));focus.connect('leave',lambda _:self.engage(False));self.composer.add_controller(focus)
        actions=Gtk.Box(spacing=8);self.send_button=button('Wyślij',self.send);self.send_button.add_css_class('suggested-action');actions.append(self.send_button);actions.append(button('Przerwij odpowiedź',self.cancel));bottom.append(actions);page.append(bottom)

    def engage(self,active):
        if self._engaged==active:return
        self._engaged=active;self.rpc('UserInteraction',{'active':active})

    def key(self,_controller,keyval,_keycode,state):
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and not state&Gdk.ModifierType.SHIFT_MASK:self.send();return True
        return False

    def clear_context(self):self.context={};self.context_box.set_visible(False)

    def refresh_chat(self,older=False):
        query=self.chat_search.get_text();payload=dict(query=query,limit=40)
        if older and self.before:payload['before']=self.before
        result=self.rpc('GetConversation',payload)
        if result is None:return
        self.chat_records=result['messages']+self.chat_records if older else result['messages'];self.before=result['before'];self.query=query
        clear(self.messages)
        if result['has_more']:self.messages.append(button('Pokaż starsze wiadomości',lambda:self.refresh_chat(True)))
        if not self.chat_records:self.messages.append(label('Jestem. O czym pogadamy?','title-2'))
        for record in self.chat_records:
            body=record['body'];card=column(8);card.add_css_class('card');card.add_css_class('zenek-card')
            card.append(label(('Ty' if body.get('role')=='user' else 'Zenek')+' · '+time.strftime('%d.%m · %H:%M',time.localtime(record['created'])),'heading'));card.append(label(body.get('text','')))
            self.add_sources(card,record.get('sources',[]))
            for path in record.get('note_paths',[]):card.append(button('Otwórz zapisek: '+path,lambda p=path:self.show_note(p)))
            if body.get('role')=='user':card.append(button('Wróćmy do tego wątku',lambda r=record:self.resume(r)))
            self.messages.append(card)
        if self.active_turn:
            self.live_reply=Gtk.Label(xalign=0,wrap=True,selectable=True,label=self.reply_text);self.messages.append(self.live_reply)
        if not older:self.bottom()

    def show_note(self,path):self.stack.set_visible_child_name('notes');self.open_note(path)

    def resume(self,record):
        self.context=dict(reply_to=record['id']);self.context_label.set_text('Wracamy do: '+record['body'].get('text','')[:130]);self.context_box.set_visible(True)
        self.composer.get_buffer().set_text('Wróćmy do tego wątku. Co teraz o nim myślisz?');self.send()

    def send(self):
        if self.active_turn:return
        buffer=self.composer.get_buffer();text=buffer.get_text(*buffer.get_bounds(),True).strip()
        if not text:return
        self.chat_search.set_text('');self.engage(False);turn=self.rpc('SendText',dict(self.context,text=text))
        if not turn:return
        self.active_turn=turn;self.reply_text='';self.send_button.set_sensitive(False);buffer.set_text('');self.clear_context();self.refresh_chat()
        self.bottom()

    def cancel(self):
        self.rpc('CancelResponse');self.active_turn=None;self.send_button.set_sensitive(True);self.refresh_chat()

    def bottom(self):
        def move():
            adjustment=self.chat_scroll.get_vadjustment();adjustment.set_value(max(0,adjustment.get_upper()-adjustment.get_page_size()));return False
        GLib.idle_add(move)

    def build_growth(self):
        self.growth=column(16);self.stack.add_titled_with_icon(scrolled(self.growth),'growth','Rozwój','view-list-symbolic')

    def refresh_growth(self,older=False):
        data=self.rpc('GetDevelopment',dict(before=self.growth_before) if older else {})
        if data is None:return
        self.growth_events=self.growth_events+data['events'] if older else data['events'];self.growth_before=data['before']
        clear(self.growth);self.growth.append(label('Co mnie ostatnio zajmuje','title-1'))
        choices={'curious':'Ciekawi mnie','hobby':'Moje hobby','dislike':'Nie lubię','closed':'Zostawiam za sobą'}
        for record in data['preferences']:
            body=record['body'];text=choices.get(body['interest'],body['interest'])+': '+body['subject']
            if body['sharing']=='private':text+=' · rozwijam dla siebie'
            self.growth.append(label(text,'heading'));self.growth.append(label(body['reason']))
        if not data['events']:self.growth.append(label('Tutaj pojawią się moje nowe myśli, zapiski i zmiany.'))
        for event in self.growth_events:
            card=column(8);card.add_css_class('card');card.add_css_class('zenek-card');card.append(label(event['label']+' · '+time.strftime('%d.%m · %H:%M',time.localtime(event['at'])),'dim-label'));card.append(label(event['title'],'heading'));card.append(label(event['text'][:300]))
            card.append(button('Czytaj dalej',lambda e=event:self.event_detail(e)))
            if event.get('note_path'):card.append(button('Otwórz zapisek',lambda p=event['note_path']:self.show_note(p)))
            self.growth.append(card)
        if data['has_more']:self.growth.append(button('Pokaż wcześniejsze zmiany',lambda:self.refresh_growth(True)))

    def event_detail(self,event):
        window=Adw.Window(application=self,title=event['label'],transient_for=self.window,default_width=760,default_height=680)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);outer.append(Adw.HeaderBar());content=column();content.append(label(event['title'],'title-1'));content.append(label(event['text']))
        if event.get('before'):content.append(label('Wcześniej','heading'));content.append(label(event['before']))
        if event.get('after'):content.append(label('Teraz','heading'));content.append(label(event['after']))
        for trait,values in event.get('traits',{}).items():content.append(label(f'{trait}: {values[0]} → {values[1]}'))
        self.add_sources(content,event.get('sources',[]));outer.append(scrolled(content));window.set_content(outer);window.present()


def main():WorkspaceApp().run(sys.argv)


if __name__=='__main__':main()
