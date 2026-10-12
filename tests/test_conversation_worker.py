import threading
from types import SimpleNamespace
from zenek_core.main import Core

def test_new_conversation_waits_for_cancel_cleanup_and_old_worker_cannot_clear_new_state():
    core=Core.__new__(Core);core.jobs={};core.cancel={};core.working=set()
    core.behavior=SimpleNamespace(interacting=True,activity='thinking');core.emit_state=lambda:None
    core.ipc=SimpleNamespace(emit=lambda *_:None)
    old_started=threading.Event();old_release=threading.Event();new_started=threading.Event();new_release=threading.Event()
    def old(cancel):old_started.set();assert old_release.wait(2)
    def new(cancel):new_started.set();assert new_release.wait(2)
    core.worker('conversation',old);assert old_started.wait(1)
    old_thread=core.jobs['conversation'];old_cancel=core.cancel['conversation']
    core.worker('conversation',new,replace=True)
    try:
        assert old_cancel.is_set() and not new_started.is_set()
        old_release.set();assert new_started.wait(1);old_thread.join(1)
        assert core.working=={'conversation'} and core.behavior.interacting
        new_release.set();core.jobs['conversation'].join(1)
        assert not core.working and not core.behavior.interacting and core.behavior.activity=='idle'
    finally:
        old_release.set();new_release.set();core.jobs['conversation'].join(2)

def test_user_input_cancels_running_initiative_and_other_low_priority_workers():
    core=Core.__new__(Core);core.memory=object();core.jobs={};core.cancel={};core.working=set()
    core.behavior=SimpleNamespace(interacting=True,activity='thinking',composing=False)
    core.emit_state=lambda:None;core.ipc=SimpleNamespace(emit=lambda *_:None)
    stops=[];core.research=SimpleNamespace(stop=lambda:stops.append(True))
    started={name:threading.Event() for name in ('initiative','background','vision','research','conversation')}
    def work(name):
        def run(cancel):started[name].set();cancel.wait(3)
        return run
    try:
        for name in started:core.worker(name,work(name))
        assert all(event.wait(1) for event in started.values())
        assert core.handle('UserInteraction',{'active':True}) is True
        assert core.behavior.composing and stops==[True]
        for name in ('initiative','background','vision','research'):
            assert core.cancel[name].is_set();core.jobs[name].join(1)
            assert not core.jobs[name].is_alive() and name not in core.working
        assert not core.cancel['conversation'].is_set() and core.working=={'conversation'}
        assert core.handle('UserInteraction',{'active':False}) is True and not core.behavior.composing
    finally:
        for event in core.cancel.values():event.set()
        for worker in core.jobs.values():worker.join(2)
