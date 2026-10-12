#!/usr/bin/env bash
set -euo pipefail
task_root=$(cd "$(dirname "$0")/.." && pwd)
task_ui_only=false
case "${1:-}" in
    --ui-only) task_ui_only=true ;;
    '') ;;
    *) printf 'Usage: %s [--ui-only]\n' "$0" >&2; exit 2 ;;
esac
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
task_was_running=false
if ! $task_ui_only && systemctl --user is-active --quiet zenek-core.service; then task_was_running=true; systemctl --user stop zenek-core.service; fi
"$task_root/.venv/bin/python" "$task_root/scripts/prepare-extension.py"
gnome-extensions disable zenek@brillnet
"$task_root/.venv/bin/python" - <<'PY'
from gi.repository import Gio,GLib
import time
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
for attempt in range(50):
    result=bus.call_sync('org.gnome.Shell.Extensions','/org/gnome/Shell/Extensions','org.gnome.Shell.Extensions','GetExtensionInfo',GLib.Variant('(s)',('zenek@brillnet',)),None,Gio.DBusCallFlags.NONE,2000,None).unpack()[0]
    if result['state']==2:break
    time.sleep(.1)
else:raise RuntimeError('Extension did not become inactive')
PY
cp -a "$task_root/gnome-extension/zenek@brillnet/." "$HOME/.local/share/gnome-shell/extensions/zenek@brillnet/"
gnome-extensions enable zenek@brillnet
if $task_was_running; then "$task_root/.venv/bin/zenek" start; fi
