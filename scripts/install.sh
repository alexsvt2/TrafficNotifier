#!/bin/zsh
# Instala la tarea de launchd que ejecuta la revisión cada 30 min.
set -euo pipefail

LABEL="com.alexislopez.trafficnotifier"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.13}"
LOG="$HOME/Library/Logs/TrafficNotifier.log"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"

[[ -x "$PYTHON" ]] || { echo "No encuentro $PYTHON (usa PYTHON=/ruta/python3.11+)"; exit 1; }
[[ -f "$REPO/config.toml" ]] || { echo "Falta $REPO/config.toml (copia config.example.toml)"; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__REPO__|$REPO|g" -e "s|__LOG__|$LOG|g" \
    "$REPO/launchd/$LABEL.plist" > "$TARGET"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$TARGET"
echo "Instalado. Log: $LOG"
echo "Probar ahora: launchctl kickstart -k gui/$UID/$LABEL"
