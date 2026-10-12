#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m compileall -q src
.venv/bin/python -m pytest -q
git diff --check
