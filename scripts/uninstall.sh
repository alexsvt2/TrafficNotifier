#!/bin/zsh
# Quita la tarea de launchd.
set -euo pipefail

LABEL="com.alexislopez.trafficnotifier"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "Desinstalado."
