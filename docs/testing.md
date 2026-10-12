# Testing and known limitations

## Automated checks

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e '.[dev]'
bash scripts/validate.sh
```

Tests cover encrypted persistence, profiles, cancellation, budgets/cooldowns,
import/corrections, masking/routing, snapshots, capture preference, sourced
self-model revisions, variety and web policy. They use synthetic provider fixtures,
local sockets where cancellation matters and a private Gio test bus. No OpenAI
account is required. GitHub Actions checks source, tests, shell syntax and builds
with Ubuntu 24.04 native GI libraries; that is not a GNOME 50 desktop UAT.

## Native verification scope

The pre-publication build was exercised on Ubuntu 26.04.1 / GNOME 50.1 / Wayland:
native bubble/composer/settings, Keyring, synthetic Portal capture, memory,
UI hide/return, real lock/suspend/wake and standalone Core. The latest capture
change used actual UI loss/recovery and restored snapshots without a Core restart.
Its lock/idle/suspend branches have focused regressions; no new physical cycle
was repeated after that change.

Two owner-excluded scenarios remain **untested**: actual Portal consent revocation
and fresh desktop login with autostart OFF. Intermediate capture states during
the physical sleep cycle were not sampled. These are evidence limits.

`scripts/uat-*` is opt-in. Some scripts use disposable native sessions; others
operate on the installed service, perform inference or capture screenshots.
Read before running, use synthetic content and preserve settings. They are not
the default test command. Raw historical evidence is private; new outputs go to
ignored `evidence/`.

## Preview limits

- GNOME 50 / Wayland only; other distributions have not received independent desktop UAT.
- Polish product UI/persona; English public docs.
- One active SIWC account registration; model availability depends on the account.
- OCR, risk, graphics proportion and topic similarity are heuristic.
- Long-term character coherence/variety require real use. Simulated self is a
  creative feature, not a consciousness assessment.
- No OS execution, automatic filesystem/account-history scanning or hosted service.
- Source distribution only; wheel installation alone omits desktop integration.
- Manual updates; source checkout/virtual environment remain installed runtime.
