#!/usr/bin/env bash
set -euo pipefail
owns_name() {
  local reply
  reply=$(gdbus call --session --timeout 2 --dest org.freedesktop.DBus \
    --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.NameHasOwner "$1") || return 2
  case "$reply" in
    '(true,)') return 0 ;;
    '(false,)') return 1 ;;
    *) return 2 ;;
  esac
}
bus_flag() {
  if owns_name "$1"; then printf 'yes'; else
    local result=$?
    if [[ $result == 1 ]]; then printf 'no'; else
      printf 'Nie można sprawdzić sesji. Pliki instalacji pozostają na miejscu.\n' >&2
      return 1
    fi
  fi
}
manager_present=$(bus_flag org.freedesktop.systemd1)
core_present=$(bus_flag org.zenek.Desktop1)
shell_present=$(bus_flag org.gnome.Shell)
if [[ $manager_present == yes ]]; then
  systemctl --user stop zenek-core.service
fi
if [[ $core_present == yes ]] && owns_name org.zenek.Desktop1; then
  # Also handles a manually launched Core without a user service manager.
  gdbus call --session --timeout 5 --dest org.zenek.Desktop1 \
    --object-path /org/zenek/Desktop1 --method org.zenek.Desktop1.Call \
    StopCompanion '{}' >/dev/null
fi
for ((attempt=0; attempt<50; attempt++)); do
  core_present=$(bus_flag org.zenek.Desktop1)
  [[ $core_present == no ]] && break
  sleep .1
done
if [[ $core_present != no ]]; then
  printf 'Core nadal działa. Pliki instalacji pozostają na miejscu.\n' >&2
  exit 1
fi
if [[ $shell_present == yes ]]; then
  gnome-extensions disable zenek@brillnet
fi
rm -f "$HOME/.config/systemd/user/zenek-core.service" "$HOME/.local/share/applications/zenek-desktop.desktop" "$HOME/.local/share/applications/zenek-settings.desktop" "$HOME/.local/bin/zenek" "$HOME/.config/autostart/zenek-desktop.desktop"
rm -rf "$HOME/.local/share/gnome-shell/extensions/zenek@brillnet"
if [[ $manager_present == yes ]]; then systemctl --user daemon-reload; fi
printf 'Usunięto komponenty. Pamięć SQLCipher, konto i klucz Keyring zachowane.\n'
