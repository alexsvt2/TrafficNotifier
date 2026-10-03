#!/bin/zsh
# Compila la app de barra de menú (macapp/main.swift) y la deja en
# ~/Applications/TrafficNotifier.app. La app solo controla el servicio de
# launchd (scripts/install.sh); no lo reemplaza.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-/opt/homebrew/bin/python3.13}"
APP="${APP_DIR:-$HOME/Applications}/TrafficNotifier.app"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/traffic_notifier/__init__.py")"

command -v swiftc >/dev/null || { echo "Falta swiftc: instala las Command Line Tools (xcode-select --install)"; exit 1; }

mkdir -p "$APP/Contents/MacOS"
swiftc -O -swift-version 5 "$REPO/macapp/main.swift" -o "$APP/Contents/MacOS/TrafficNotifier"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>TrafficNotifier</string>
    <key>CFBundleIdentifier</key><string>com.alexislopez.trafficnotifier.menu</string>
    <key>CFBundleExecutable</key><string>TrafficNotifier</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>LSUIElement</key><true/>
    <key>TNRepo</key><string>$REPO</string>
    <key>TNPython</key><string>$PYTHON</string>
</dict>
</plist>
PLIST
codesign --force --sign - "$APP" 2>/dev/null

echo "App $VERSION en $APP"
echo "Abrir: open \"$APP\""
