# Installation

These instructions describe **0.2.0 preview**. Complete source is available in
the [GitHub release](https://github.com/piotr-adamski/zenek-desktop/releases/tag/v0.2.0),
including a source archive and `SHA256SUMS`.

## Supported desktop

Linux with GNOME Shell **50**, **Wayland**, systemd user services and an unlocked
Secret Service compatible Keyring. Python **3.12+**, GTK4/libadwaita, GStreamer,
PipeWire, XDG Desktop Portal with its GNOME backend, Tesseract and Bubblewrap are
required. Full desktop verification used Ubuntu 26.04.1 / GNOME 50.1. Earlier
GNOME versions, X11, KDE, Windows and macOS are not supported by this preview.

On Ubuntu 26.04, an administrator can install prerequisites with:

```bash
sudo apt install git python3-venv python3-pip python3-gi \
  gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gstreamer-1.0 \
  gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-base \
  gstreamer1.0-pipewire pipewire xdg-desktop-portal \
  xdg-desktop-portal-gnome gnome-keyring \
  tesseract-ocr tesseract-ocr-eng tesseract-ocr-pol bubblewrap
```

Package names vary across distributions. This installs missing native dependencies;
**run Zenek's installer without sudo** in your GNOME session. Its virtual environment
uses system site packages for PyGObject. Python dependencies come from PyPI.

## Install

```bash
git clone --branch v0.2.0 https://github.com/piotr-adamski/zenek-desktop.git
cd zenek-desktop
bash scripts/install-user.sh --check
bash scripts/install-user.sh
~/.local/bin/zenek start
~/.local/bin/zenek settings
```

`--check` validates prerequisites without installing anything. Installation copies
the extension, creates user launchers/service and protects data directories.
It does not start Core, enable autostart or overwrite settings. It enables the
extension when GNOME can discover it. A first install may require signing out/in;
no session restart is forced.

Keep the source folder: launchers/service point to its virtual environment.
Moving it requires rerunning installation. Use a source path without literal
double quotes, backslashes or percent characters.

## Update and uninstall

Review the [changelog](../CHANGELOG.md), stop Core, and check for local source
changes before switching versions. Keep the same checkout so its private
`notebook/` remains available. The release-tag install uses a detached checkout;
update it explicitly rather than running `git pull` there:

```bash
zenek stop
git fetch origin --tags
git switch --detach v0.2.0
bash scripts/install-user.sh
zenek start
```

For an intentional development checkout on `main`, use
`git pull --ff-only origin main` instead of switching to a release tag.

If a loaded extension needs its module refreshed, run
`bash scripts/deploy-user-build.sh`. This reloads only Zenek's extension and,
if running, Core. It does not restart GNOME. Existing memory, Keyring records
and settings survive. Review local changes before pulling/updating.

Version 0.2.0 uses the existing SQLCipher record store and Keyring registration.
It retains selected models, budgets and capture/web/autostart preferences;
autonomous character changes retain history and rollback. There is no reset or
new login required solely for this update. Keep a private backup before changing
versions: the database needs its existing Keyring key, and `notebook/` is a
separate plaintext directory. A JSON memory export does not back up notebook files.

```bash
bash scripts/uninstall-user.sh
```

Removal stops/deletes the service, extension, launchers and autostart entry.
It preserves memory and account credentials. Use Settings to disconnect/clear
data if wanted, reviewing or exporting first.

## Default paths

| Item | Path |
| --- | --- |
| Encrypted memory | `~/.local/share/zenek/memory.db` |
| Configuration | `~/.config/zenek` |
| Cache | `~/.cache/zenek` |
| User service | `~/.config/systemd/user/zenek-core.service` |
| Extension | `~/.local/share/gnome-shell/extensions/zenek@brillnet` |
| Launcher | `~/.local/bin/zenek` |
| Autonomous text notes | `notebook/` inside the installed source checkout (not encrypted) |

Core data/config paths respect XDG variables; installation uses conventional
GNOME user locations. Keys and OAuth credentials live in Keyring.

## Troubleshooting

- Extension missing: check `gnome-extensions info zenek@brillnet`; sign out/in
  once if the first install is undiscovered. Confirm Shell 50.
- `MEMORY_BLOCKED`: unlock the login Keyring. Do not delete the encrypted DB as
  a workaround; plaintext fallback is deliberately unavailable.
- No bubble: `zenek start`, then `zenek show`; check quiet/fullscreen/idle/hidden state.
- Capture paused: inspect the tray/Settings reason. Saved ON survives lock/sleep/idle;
  operational Portal errors require **Wznów zrzuty**.
- Profile unavailable: test the selected profile in Settings. Access depends on
  your account. There is no automatic paid fallback.
- No new thoughts or hobby notes: check the background profile, mode/pause state,
  daily budget and your session's idle/lock state. Notes are created when the
  model chooses to write; they are not generated on a fixed publishing schedule.
- Notebook appears empty after moving/replacing the checkout: notes belong to
  its local `notebook/`; Git clones and release archives do not carry private notes.
- Diagnostics: `journalctl --user -u zenek-core.service`. Review private data
  before including any excerpt in a public issue.
