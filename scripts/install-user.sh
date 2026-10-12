#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONNOUSERSITE=1
task_root=$(cd "$(dirname "$0")/.." && pwd)
task_check_only=false
case "${1:-}" in
  --check) task_check_only=true ;;
  '') ;;
  *) echo "Usage: $0 [--check]" >&2; exit 2 ;;
esac
if (( EUID == 0 )); then echo 'Run as your desktop user, without sudo.' >&2; exit 1; fi
if [[ ${XDG_SESSION_TYPE:-} != wayland ]]; then echo 'A GNOME Wayland desktop session is required.' >&2; exit 1; fi
if ! gnome-shell --version | grep -Eq 'GNOME Shell 50([.]|$)'; then
  echo 'This preview supports GNOME Shell 50 only.' >&2; exit 1
fi
for task_command in python3 systemctl gnome-extensions tesseract bwrap; do
  command -v "$task_command" >/dev/null || { echo "Missing dependency: $task_command" >&2; exit 1; }
done
python3 - <<'PY'
import sys, gi
assert sys.version_info >= (3, 12), 'Python 3.12 or newer is required'
for name, version in [('Gtk', '4.0'), ('Adw', '1'), ('Gst', '1.0'), ('GstVideo', '1.0')]:
    gi.require_version(name, version)
from gi.repository import Gtk, Adw, Gst, GstVideo
Gst.init(None)
for plugin in ['pipewiresrc', 'videoconvert', 'videorate', 'appsink']:
    assert Gst.ElementFactory.find(plugin), f'Missing GStreamer plugin: {plugin}'
PY
systemctl --user show-environment >/dev/null
for task_path in "$task_root" "$HOME"; do
  if [[ $task_path == *'"'* || $task_path == *'\'* || $task_path == *'%'* || $task_path == *$'\n'* ]]; then
    echo 'Install path must not contain double quotes, backslashes, percent signs or newlines.' >&2; exit 1
  fi
done
if $task_check_only; then echo 'Native prerequisites OK. Nothing installed.'; exit 0; fi
python3 -m venv --system-site-packages "$task_root/.venv"
"$task_root/.venv/bin/pip" install -e "$task_root"
"$task_root/.venv/bin/python" "$task_root/scripts/make-sprites.py"
"$task_root/.venv/bin/python" "$task_root/scripts/prepare-extension.py"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/gnome-shell/extensions/zenek@brillnet" "$HOME/.config/systemd/user"
mkdir -p "$HOME/.local/share/zenek" "$HOME/.config/zenek" "$HOME/.cache/zenek"
chmod 700 "$HOME/.local/share/zenek" "$HOME/.config/zenek" "$HOME/.cache/zenek"
cp -a "$task_root/gnome-extension/zenek@brillnet/." "$HOME/.local/share/gnome-shell/extensions/zenek@brillnet/"
ln -sfn "$task_root/.venv/bin/zenek" "$HOME/.local/bin/zenek"
cat > "$HOME/.config/systemd/user/zenek-core.service" <<EOF
[Unit]
Description=Zenek Desktop Companion Core
After=graphical-session.target
PartOf=graphical-session.target
[Service]
Type=simple
ExecStart="$task_root/.venv/bin/zenek-core"
WorkingDirectory="$task_root"
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONNOUSERSITE=1
UMask=0077
Restart=no
KillMode=control-group
TimeoutStopSec=5
NoNewPrivileges=yes
LimitCORE=0
EOF
cat > "$HOME/.local/share/applications/zenek-desktop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Zenek Desktop Companion
Comment=Uruchom lub pokaż Zenka
Exec="$HOME/.local/bin/zenek" start
Icon=face-smile-symbolic
Terminal=false
Categories=Utility;
EOF
cat > "$HOME/.local/share/applications/zenek-settings.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Zenek — ustawienia
Exec="$HOME/.local/bin/zenek" settings
Icon=preferences-system-symbolic
Terminal=false
Categories=Settings;
EOF
systemctl --user daemon-reload
# Deliberately no enable, start, XDG autostart or lingering.
printf 'Zainstalowano per-user. Domyślny autostart nowej instalacji OFF; istniejący wybór zachowany. Uruchom: zenek start\n'
if ! gnome-extensions enable zenek@brillnet; then
  printf 'GNOME nie wykrył nowego rozszerzenia. Może być potrzebne ponowne logowanie; nie restartujemy sesji.\n'
fi
