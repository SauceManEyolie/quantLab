#!/bin/bash
# Installs (or removes) the spoken QuantLab briefing that runs when you log in.
# Double-click this file in Finder.

cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
LABEL="com.quantlab.greeting"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo ""
echo "  ── QuantLab login briefing ──────────────"
echo ""

if [ "$(uname)" != "Darwin" ]; then
  echo "  This installer is macOS-only."
  read -n 1 -s -r -p "  Press any key to close..."; exit 1
fi

# --- pick a python -----------------------------------------------------------
PY=""
[ -x "$HERE/.venv/bin/python" ] && PY="$HERE/.venv/bin/python"
if [ -z "$PY" ]; then
  for c in python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
    command -v "$c" >/dev/null 2>&1 && { PY="$(command -v $c)"; break; }
  done
fi
if [ -z "$PY" ]; then
  echo "  Python 3 not found. Run start.command first."
  read -n 1 -s -r -p "  Press any key to close..."; exit 1
fi

# --- uninstall path ----------------------------------------------------------
if [ -f "$PLIST" ]; then
  echo "  A login briefing is already installed."
  echo ""
  read -r -p "  Remove it? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "  Removed. It will not run at login any more."
  else
    echo "  Left it alone. Reinstalling over the top..."
  fi
  echo ""
fi

# --- choose a voice ----------------------------------------------------------
echo "  Your Mac's current default voice will be used."
echo "  For a much better one: System Settings > Accessibility > Spoken Content"
echo "  > System Voice > Manage Voices, and download a Siri voice."
echo ""
read -r -p "  Voice name to force (blank = system default): " VOICE
read -r -p "  Your name, so it can greet you (blank = skip): " NAME
echo ""

# --- write the LaunchAgent ---------------------------------------------------
mkdir -p "$HOME/Library/LaunchAgents"
ARGS="        <string>$PY</string>
        <string>$HERE/brief.py</string>
        <string>--delay</string>
        <string>20</string>"
[ -n "$VOICE" ] && ARGS="$ARGS
        <string>--voice</string>
        <string>$VOICE</string>"
[ -n "$NAME" ] && ARGS="$ARGS
        <string>--name</string>
        <string>$NAME</string>"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
$ARGS
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$HERE</string>
    <key>StandardOutPath</key>
    <string>$HERE/greeting.log</string>
    <key>StandardErrorPath</key>
    <string>$HERE/greeting.log</string>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
PLISTEOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
if ! launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  launchctl load "$PLIST" 2>/dev/null   # older macOS
fi

echo "  Installed."
echo ""
echo "  It runs 20 seconds after you log in — enough time for wifi to come up."
echo "  Output is also written to briefing.md, and logged to greeting.log."
echo ""
echo "  To remove it later: double-click this file again and answer y."
echo ""
read -r -p "  Hear it now? [Y/n] " play
if [[ ! "$play" =~ ^[Nn]$ ]]; then
  echo ""
  ARGS_RUN=()
  [ -n "$VOICE" ] && ARGS_RUN+=(--voice "$VOICE")
  [ -n "$NAME" ] && ARGS_RUN+=(--name "$NAME")
  "$PY" "$HERE/brief.py" "${ARGS_RUN[@]}"
fi

echo ""
read -n 1 -s -r -p "  Press any key to close..."
