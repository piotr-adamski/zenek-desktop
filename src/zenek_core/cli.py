import argparse
import json
import subprocess
import sys
import time
from .ipc import call

def main():
    parser=argparse.ArgumentParser(prog="zenek")
    parser.add_argument("command",choices=["start","show","hide","stop","status","settings","login","models","cancel","notebook","chat","development"])
    args=parser.parse_args()
    if args.command in ('notebook','chat','development'):
        view={'notebook':'notes','chat':'chat','development':'growth'}[args.command]
        subprocess.run([sys.executable,'-m','zenek_settings.workspace','--view',view],check=True);return
    if args.command=="settings":
        from zenek_settings.app import main as settings
        settings();return
    if args.command=="start":
        subprocess.run(["systemctl","--user","start","zenek-core.service"],check=True)
        for attempt in range(25):
            try:call("ShowCompanion");return
            except Exception:
                if attempt==24:raise
                time.sleep(.2)
    if args.command=="stop":
        subprocess.run(["systemctl","--user","stop","zenek-core.service"],check=True);return
    methods=dict(show="ShowCompanion",hide="HideCompanion",status="GetStatus",login="Login",models="Models",cancel="CancelResponse")
    print(json.dumps(call(methods[args.command]),ensure_ascii=False,indent=2))

if __name__=="__main__":main()
