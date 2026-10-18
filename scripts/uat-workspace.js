import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Scripting from 'resource:///org/gnome/shell/ui/scripting.js';
export async function run(){
    for(let i=0;Main.layoutManager._startingUp&&i<60;i++)await Scripting.sleep(50);
    Main.overview.hide();
    const root=GLib.getenv('ZENEK_TEST_ROOT');
    const launcher=new Gio.SubprocessLauncher({flags:Gio.SubprocessFlags.NONE});
    launcher.setenv('WAYLAND_DISPLAY','gnome-shell-test-display',true);
    const child=launcher.spawnv([`${root}/.venv/bin/python`,`${root}/scripts/uat-workspace.py`,'--child']);
    await new Promise((resolve,reject)=>child.wait_check_async(null,(p,r)=>{try{p.wait_check_finish(r);resolve();}catch(error){reject(error);}}));
}
