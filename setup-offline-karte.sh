#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — setup-offline-karte.sh v2026-10-05-1
# Baut die Offline-Vektor-Karte (karte.mbtiles, OpenMapTiles-Schema)
# für ganz Afrika + lädt die Label-Schriften. EINMALIG zuhause mit
# schnellem Internet ausführen — Laufzeit mehrere Stunden, ~80 GB
# Platz während des Builds (Ergebnis ~8 GB).
#
# Ablauf:  1. Java 21+ prüfen        (brew install --cask temurin)
#          2. Planetiler laden       (~120 MB, einmalig)
#          3. karte.mbtiles bauen    (lädt Geofabrik-Afrika automatisch)
#          4. Schriften laden        (Noto Sans für Karten-Labels)
#          5. Alles in Projekt + App-Bundle legen
#
# Danach: pois.html erkennt die Karte automatisch (🗺️-Button wird grün)
# und schaltet auf MapLibre-Vektor-Rendering — komplett offline.
# ═══════════════════════════════════════════════════════════════════
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"   # 2026-09-12: eigener Ordner statt festem Desktop-Pfad
# App-Bundle wie in deploy.sh: Safari Assistant.app zuerst, dann ältere Installationen unter früherem Namen
# (Safari-Assistent.app, DARK.app, „Safari Assistent.app"). Die Variable heißt weiter DARK_APP.
DST=""
for a in "${DARK_APP:-}" \
         "$HOME/Desktop/Safari Assistant.app" "/Applications/Safari Assistant.app" "$HOME/Applications/Safari Assistant.app" \
         "$HOME/Desktop/Safari-Assistent.app" "/Applications/Safari-Assistent.app" "$HOME/Applications/Safari-Assistent.app" \
         "$HOME/Desktop/DARK.app" "/Applications/DARK.app" "$HOME/Applications/DARK.app" \
         "$HOME/Desktop/Safari Assistent.app" "/Applications/Safari Assistent.app"; do
  if [ -n "$a" ] && [ -d "$a/Contents/Resources/safari-assistant" ]; then DST="$a/Contents/Resources/safari-assistant"; break; fi
done
cd "$SRC" || { echo "❌ Projektordner nicht gefunden: $SRC"; exit 1; }

echo "═══ 1/5 Java prüfen ═══"
if ! command -v java >/dev/null; then
  echo "❌ Java fehlt. Installation:  brew install --cask temurin"
  exit 1
fi
JV=$(java -version 2>&1 | head -1)
echo "✅ $JV  (Planetiler braucht Java 21+ — bei Fehlern in Schritt 3: brew install --cask temurin)"

echo ""
echo "═══ 2/5 Planetiler laden ═══"
if [ -f planetiler.jar ] && [ "$(wc -c < planetiler.jar)" -ge 50000000 ]; then
  echo "✅ planetiler.jar vorhanden"
else
  curl -fL --progress-bar -o planetiler.jar \
    "https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar"
  echo "✅ planetiler.jar geladen ($(wc -c < planetiler.jar) B)"
fi

echo ""
echo "═══ 3/5 karte.mbtiles bauen (Afrika — deckt alle 16 Reiseländer ab) ═══"
echo "   Dauert mehrere Stunden. Geofabrik-Download (~7 GB) läuft automatisch."
if [ -f karte.mbtiles ]; then
  read -p "   karte.mbtiles existiert schon — neu bauen? (j/N) " a
  [ "${a:-n}" = "j" ] || { echo "   → Build übersprungen"; SKIP_BUILD=1; }
fi
if [ -z "${SKIP_BUILD:-}" ]; then
  # Arbeitsspeicher für Java: die Hälfte des RAM, höchstens 12 GB (vorher fest 12 GB — zu viel für 16-GB-Macs)
  RAM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 17179869184) / 1073741824 ))
  XMX=$(( RAM_GB / 2 )); [ "$XMX" -gt 12 ] && XMX=12; [ "$XMX" -lt 4 ] && XMX=4
  echo "   Java-Speicher: ${XMX} GB (RAM: ${RAM_GB} GB)"
  java -Xmx${XMX}g -jar planetiler.jar --download --area=africa \
    --output=karte.mbtiles --force
  echo "✅ karte.mbtiles gebaut ($(du -h karte.mbtiles | cut -f1))"
fi

echo ""
echo "═══ 4/5 Label-Schriften laden (Noto Sans Regular + Bold als Glyph-PBFs) ═══"
if [ -d "fonts/Noto Sans Regular" ] && [ -d "fonts/Noto Sans Bold" ]; then
  echo "✅ fonts/ vorhanden"
else
  TMPD="$(mktemp -d)"   # 2026-09-27: eigenes Temp-Verzeichnis statt fester /tmp-Namen
  curl -fL --progress-bar -o "$TMPD/omt-fonts.zip" \
    "https://github.com/openmaptiles/fonts/releases/download/v2.0/v2.0.zip"
  mkdir -p "$TMPD/omt-fonts"
  unzip -q "$TMPD/omt-fonts.zip" -d "$TMPD/omt-fonts"
  mkdir -p fonts
  # Ordner robust finden (Zip-Struktur kann eine Ebene tiefer liegen)
  for f in "Noto Sans Regular" "Noto Sans Bold"; do
    SRC_DIR=$(find "$TMPD/omt-fonts" -type d -name "$f" | head -1)
    [ -n "$SRC_DIR" ] || { echo "❌ '$f' nicht im Font-Paket gefunden"; exit 1; }
    rm -rf "fonts/$f" && cp -R "$SRC_DIR" "fonts/$f"
    echo "✅ fonts/$f ($(ls "fonts/$f" | wc -l | tr -d ' ') Dateien)"
  done
  rm -rf "$TMPD"
fi

echo ""
echo "═══ 5/5 Ins App-Bundle kopieren ═══"
[ -n "$DST" ] || { echo "⚠️  Kein App-Bundle gefunden (Safari Assistant.app) — nur der Projektordner ist befüllt. Safari Assistant findet die Karte dort, wenn du python3 server.py startest."; exit 0; }
cp karte.mbtiles "$DST/karte.mbtiles" && echo "✅ karte.mbtiles → Bundle"
mkdir -p "$DST/fonts"
cp -R fonts/* "$DST/fonts/" && echo "✅ fonts/ → Bundle"

echo ""
echo "🟢 FERTIG. Test: App starten → POI-Karte → 🗺️-Button muss grün sein (Vektor),"
echo "   dann WLAN AUS → Karte muss weiter rendern (inkl. Ortsnamen)."
