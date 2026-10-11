#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — baut die macOS-App (Apple Silicon), v2026-10-05-1
#
# Nutzung:  ./build-app.sh                         → ~/Desktop/Safari Assistant.app
#           APP_DIR="/Applications/Safari Assistant.app" ./build-app.sh
#
# Ein vorhandenes Bundle wird NIE gelöscht, sondern aktualisiert (Launcher, Info.plist, App-Dateien):
# im Bundle liegen Nutzerdaten — hochgeladene Dokumente (docs/), rag-store.json, karte.mbtiles,
# fonts/, data/warnzonen.geojson. Vorher löschte „rm -rf" das alles bei jedem Neubau (Review P1-11).
# Die App-Dateien selbst kopiert deploy.sh (eine Liste für beide Wege — vorher landete server.py
# gar nicht im Bundle und die App lief ohne Server, Review P0-1).
# ═══════════════════════════════════════════════════════════════════
set -u

APP_NAME="${APP_NAME:-Safari Assistant}"
APP_DIR="${APP_DIR:-$HOME/Desktop/${APP_NAME}.app}"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources/safari-assistant"   # interner Ordnername bleibt (Daten, Pfade, Rechte)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Ältere Installation unter einem früheren Namen? Dann umbenennen statt eine zweite App zu bauen —
# sonst gäbe es zwei Bundles mit getrennten Dokumenten und Karten.
# Frühere Namen: „Safari-Assistent.app" (04./05.10.2026), „DARK.app" (bis 2026-10-04) und „Safari Assistent.app" (Entwicklung).
ALT_APP=""
for a in "$HOME/Desktop/Safari-Assistent.app" "/Applications/Safari-Assistent.app" "$HOME/Applications/Safari-Assistent.app" \
         "$HOME/Desktop/DARK.app" "/Applications/DARK.app" "$HOME/Applications/DARK.app" "$HOME/Desktop/Safari Assistent.app"; do
  [ -d "$a" ] && { ALT_APP="$a"; break; }
done
if [ -n "$ALT_APP" ] && [ ! -d "$APP_DIR" ] && [ "${NEU_BAUEN:-0}" != "1" ]; then
  echo "ℹ️  Es gibt bereits „$(basename "$ALT_APP")\" — das ist dieselbe App unter altem Namen."
  echo "   Bitte umbenennen statt neu bauen (App vorher beenden):"
  NEU_PFAD="$(dirname "$ALT_APP")/${APP_NAME}.app"
  echo "     mv \"$ALT_APP\" \"$NEU_PFAD\""
  echo "     APP_DIR=\"$NEU_PFAD\" ./build-app.sh   # aktualisiert Launcher, Info.plist und App-Dateien"
  echo "   Trotzdem eine zweite, leere App bauen: NEU_BAUEN=1 ./build-app.sh"
  exit 1
fi

[ -f "$SCRIPT_DIR/launcher_new.sh" ] || { echo "❌ launcher_new.sh fehlt in $SCRIPT_DIR"; exit 1; }

if [ -d "$APP_DIR" ]; then
  echo "🌍 Aktualisiere ${APP_DIR} (Nutzerdaten im Bundle bleiben erhalten) …"
else
  echo "🌍 Baue ${APP_DIR} …"
fi
mkdir -p "$MACOS" "$RESOURCES" || { echo "❌ Kann $APP_DIR nicht anlegen"; exit 1; }

# Launcher: eine Quelle (launcher_new.sh), als Programmdatei der App
cp "$SCRIPT_DIR/launcher_new.sh" "$MACOS/${APP_NAME}" && chmod +x "$MACOS/${APP_NAME}" \
  && echo "  ✓ Launcher → Contents/MacOS/${APP_NAME}"

# Icon (optional): icon.icns neben diesem Skript → AppIcon.icns (siehe generate_icon.py)
ICON_PLIST=""
if [ -f "$SCRIPT_DIR/icon.icns" ]; then
  cp "$SCRIPT_DIR/icon.icns" "$CONTENTS/Resources/AppIcon.icns" && echo "  ✓ App-Icon"
  ICON_PLIST="  <key>CFBundleIconFile</key>
  <string>AppIcon</string>"
fi

# Info.plist — CFBundleIdentifier bleibt „com.safari-assistent.app": macOS knüpft Datenschutz-
# Freigaben (z. B. Zugriff auf Schreibtisch/Dokumente für Wikipedia-ZIMs) daran.
cat > "$CONTENTS/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>com.safari-assistent.app</string>
  <key>CFBundleVersion</key>
  <string>2026.10.04</string>
  <key>CFBundleShortVersionString</key>
  <string>2026.10</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
${ICON_PLIST}
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST
echo "  ✓ Info.plist"

# App-Dateien, Offline-Bibliotheken und Daten: deploy.sh (Tests nur auf Wunsch: DEPLOY_OHNE_TESTS=0)
# DARK_APP: Name der Umgebungsvariablen bleibt (deploy.sh, setup-offline-karte.sh)
DARK_APP="$APP_DIR" DEPLOY_OHNE_TESTS="${DEPLOY_OHNE_TESTS:-1}" "$SCRIPT_DIR/deploy.sh" || {
  echo "❌ deploy.sh ist gescheitert — die App ist unvollständig. Meldung oben lesen."; exit 1; }

# Quarantäne-Flag entfernen: die App ist hier selbst gebaut, nicht heruntergeladen.
xattr -cr "$APP_DIR" 2>/dev/null || true

echo ""
echo "✅ Fertig: $APP_DIR"
echo "▶️  Starten: Doppelklick auf „${APP_NAME}\" (beim ersten Mal ggf. Rechtsklick → Öffnen)"
