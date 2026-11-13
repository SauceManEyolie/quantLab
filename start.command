#!/bin/bash
# QuantLab launcher — double-click this file in Finder to start the app.
cd "$(dirname "$0")" || exit 1

echo ""
echo "  ── QuantLab ─────────────────────────────"
echo ""

# Find a usable Python 3.
PY=""
for c in python3 python3.12 python3.11 python3.10 /usr/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "  Python 3 isn't installed."
  echo "  Install it from https://www.python.org/downloads/ then run this again."
  echo ""
  read -n 1 -s -r -p "  Press any key to close..."
  exit 1
fi

# Make sure pandas + numpy are there. Newer macOS Pythons refuse plain pip
# installs ("externally-managed-environment"), so fall back to a local venv.
if ! "$PY" -c "import pandas, numpy" >/dev/null 2>&1; then
  echo "  First run — installing pandas and numpy (about a minute)..."
  echo ""
  if ! "$PY" -m pip install --quiet pandas numpy 2>/dev/null; then
    echo "  System Python is locked down. Building a local environment instead..."
    "$PY" -m venv .venv && .venv/bin/python -m pip install --quiet --upgrade pip pandas numpy
  fi
  [ -x ".venv/bin/python" ] && PY=".venv/bin/python"
fi
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

if ! "$PY" -c "import pandas, numpy" >/dev/null 2>&1; then
  echo ""
  echo "  Couldn't install the dependencies automatically."
  echo "  Open Terminal and run:   pip3 install --user pandas numpy"
  echo ""
  read -n 1 -s -r -p "  Press any key to close..."
  exit 1
fi

echo "  Starting server. Your browser will open shortly."
echo "  Leave this window open while you use the app."
echo "  Press Ctrl+C here to stop it."
echo ""

"$PY" run.py

echo ""
read -n 1 -s -r -p "  Server stopped. Press any key to close..."
