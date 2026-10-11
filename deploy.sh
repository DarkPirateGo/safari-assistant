#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — deploy.sh v2026-10-05-1   (vormals „Safari-Assistent", „DARK" bzw. „Safari Assistent")
# Lädt die Offline-Bibliotheken und bringt die App-Dateien ins App-Bundle (Safari Assistant.app).
#
# Ablauf:  0. Offline-Bibliotheken (vendor/) laden, falls sie fehlen — geprüft per SHA-256
#          1. Regressionstests (test-app.js) — bei Fehler: ABBRUCH (ohne Node: übersprungen)
#          2. Downgrade-Sperre — Versionsmarker Quelle vs. Bundle
#          3. Kopieren ins Bundle (nur wenn eines gefunden wird)
#          4. Git-Sicherung — NUR auf ausdrücklichen Wunsch (DEPLOY_COMMIT=1 oder Datei .deploy-commit)
#
# Nutzung:  ./deploy.sh                          (im Projektordner; der Ordner darf überall liegen)
#           DEPLOY_OHNE_TESTS=1 ./deploy.sh       Tests überspringen
#           DARK_APP="/Pfad/zu/Safari Assistant.app" ./deploy.sh   (Name der Variablen bleibt DARK_APP)
# Ohne App-Bundle läuft Safari Assistant auch direkt:  python3 server.py  →  http://localhost:8765
# ═══════════════════════════════════════════════════════════════════
set -u

SRC="$(cd "$(dirname "$0")" && pwd)"
cd "$SRC" || { echo "❌ Projektordner nicht gefunden: $SRC"; exit 1; }

# App-Bundle suchen — neuer Name zuerst, dann eine ältere Installation unter einem früheren Namen
# (2026-10-05-1: „Safari-Assistent.app" am 04./05.10.2026; 2026-10-04-2: „DARK.app" bis 2026-10-04, davor
# „Safari Assistent.app") — die wird weiter aktualisiert.
# Kein Bundle ist kein Fehler: vendor/ und Tests laufen trotzdem (Review P0-1 — vorher brach
# deploy.sh auf einem frischen Klon sofort ab, noch bevor die Bibliotheken geladen waren).
finde_app() {
  local a
  for a in "${DARK_APP:-}" \
           "$HOME/Desktop/Safari Assistant.app" "/Applications/Safari Assistant.app" "$HOME/Applications/Safari Assistant.app" \
           "$HOME/Desktop/Safari-Assistent.app" "/Applications/Safari-Assistent.app" "$HOME/Applications/Safari-Assistent.app" \
           "$HOME/Desktop/DARK.app" "/Applications/DARK.app" "$HOME/Applications/DARK.app" \
           "$HOME/Desktop/Safari Assistent.app" "/Applications/Safari Assistent.app"; do
    [ -n "$a" ] && [ -d "$a/Contents/Resources/safari-assistant" ] && { echo "$a"; return 0; }
  done
  return 1
}
APP="$(finde_app || true)"
DST="${APP:+$APP/Contents/Resources/safari-assistant}"

# fetch-parks.py MUSS mit: fetch-warnzonen.py lädt daraus die Geometrie-Helfer. Ohne die Datei
# stirbt das automatische Nachziehen der Warngebiete im Bundle mit FileNotFoundError (15.09.2026).
# 2026-10-04-1: hilfe.py (Seite /hilfe) und die Oberflächensprache (i18n.js + i18n/<sprache>.js) gehören dazu;
# die Anleitung README*.md kommt unten eigens dazu (Quelle: Projektordner oder release-docs/).
FILES=(index.html mobile.html pois.html dark-logo.jpg icon.png test-app.js test-reisewarnungen.py test-tls.py test-warngebiete.py fetch-warnzonen.py fetch-parks.py fetch-klima.py features-manifest.json server.py rag.py hilfe.py i18n.js i18n/en.js i18n/fr.js i18n/es.js)
README_DATEIEN=(README.md README.de.md README.fr.md README.es.md)

version_of() {  # extrahiert v2026-07-04-1 aus den ersten 3 Zeilen
  head -3 "$1" 2>/dev/null | grep -m1 -o 'v[0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}-[0-9]*' || echo ""
}
sha256_von() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else sha256sum "$1" | cut -d' ' -f1; fi
}

echo "═══ 0/4 Offline-Bibliotheken (vendor/) ═══"
# Bug 8: pois.html braucht Leaflet + MarkerCluster + MapLibre LOKAL — im Busch gibt es kein unpkg.com.
# 2026-09-27 (Audit L4): jede Datei ist per SHA-256 festgelegt. Ein manipuliertes oder umgeleitetes
# CDN kann so keinen fremden Code ins Bundle bringen — vorher wurde nur die Mindestgröße geprüft.
mkdir -p "$SRC/vendor"
VENDOR_FEHLT=0
VENDOR_FALSCH=0
vendor_fetch() {  # $1=Datei $2=URL $3=Mindestgröße (Abbruch-/Truncation-Schutz) $4=SHA-256
  local f="$SRC/vendor/$1"
  if [ -f "$f" ] && [ "$(wc -c < "$f")" -ge "$3" ]; then
    if [ "$(sha256_von "$f")" = "$4" ]; then
      echo "✅ vendor/$1 vorhanden, Prüfsumme stimmt"
    else
      echo "🛑 vendor/$1: Prüfsumme stimmt NICHT — Datei wurde verändert oder ist eine andere Version."
      echo "   Prüfen, dann ersetzen:  rm \"vendor/$1\" && ./deploy.sh   (lädt die festgelegte Version neu)"
      VENDOR_FALSCH=1
    fi
    return 0
  fi
  echo "⬇️  vendor/$1 wird geladen..."
  if curl -fsSL --max-time 60 -o "$f.tmp" "$2" && [ "$(wc -c < "$f.tmp")" -ge "$3" ]; then
    if [ "$(sha256_von "$f.tmp")" = "$4" ]; then
      mv "$f.tmp" "$f" && echo "✅ vendor/$1 geladen und geprüft ($(wc -c < "$f") B)"
    else
      rm -f "$f.tmp"
      echo "🛑 vendor/$1: Download hat die falsche Prüfsumme — NICHT übernommen."
      VENDOR_FALSCH=1
    fi
  else
    rm -f "$f.tmp"
    echo "❌ vendor/$1 konnte nicht geladen werden (offline?)."
    echo "   Einmalig MIT Internet ausführen — ohne diese Dateien ist die Karte offline tot."
    VENDOR_FEHLT=1
  fi
}
vendor_fetch leaflet.js                "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"                              100000 db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a
vendor_fetch leaflet.css               "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"                             10000  a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6
vendor_fetch leaflet.markercluster.js  "https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"  20000  1e4e1d22972a3926f48598e0caf14e3fe7049835d428a344fed4f9e3665b3508
vendor_fetch MarkerCluster.css         "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"         200    614dea0a98ff3f4ead74f04918f6b1d1b9ba435c25b5fc23b21a394d1e3e4d87
vendor_fetch MarkerCluster.Default.css "https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" 500    61258232d98d64dc2a7b1e02130d67421bc5b9bda5994eef70228ff97570c170
vendor_fetch maplibre-gl-4.7.1.js      "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"                      500000 be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1
vendor_fetch maplibre-gl-4.7.1.css     "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"                     30000  576b085fdd9487a65a19215328c1e086c07ce5bf6da09b666b3806d3d008dae9
rm -f "$SRC/vendor/maplibre-gl.js" "$SRC/vendor/maplibre-gl.css" 2>/dev/null   # Bug 9: alte 3.6.2 entsorgen
[ -n "$APP" ] && rm -f "$DST/vendor/maplibre-gl.js" "$DST/vendor/maplibre-gl.css" 2>/dev/null

# Lizenztexte der Bibliotheken: mitgeliefert ist der Standardtext der jeweiligen Lizenz (Kopfzeile
# STANDARD-TEXT-MARKER). Im Arbeitsordner des Maintainers (.deploy-commit) oder mit DEPLOY_LIZENZEN=1 wird
# er mit Internet einmalig durch die Originaldatei ersetzt — in einem fremden Klon nicht (sonst änderten
# sich dort versionierte Dateien).
lizenz_fetch() {  # $1=Datei $2=URL
  local f="$SRC/vendor/$1"
  [ -f "$f" ] && ! grep -q '^STANDARD-TEXT-MARKER$' "$f" && return 0
  if curl -fsSL --max-time 30 -o "$f.tmp" "$2" 2>/dev/null && [ "$(wc -c < "$f.tmp")" -ge 500 ] && grep -qi 'copyright' "$f.tmp"; then
    mv "$f.tmp" "$f" && echo "✅ vendor/$1: Original-Lizenztext geladen"
  else
    rm -f "$f.tmp"
    [ -f "$f" ] && echo "ℹ️  vendor/$1: Original nicht erreichbar — Standardtext bleibt" || echo "⚠️  vendor/$1 fehlt"
  fi
}
if [ -f "$SRC/.deploy-commit" ] || [ "${DEPLOY_LIZENZEN:-0}" = "1" ]; then
  lizenz_fetch LICENSE-leaflet.txt               "https://raw.githubusercontent.com/Leaflet/Leaflet/v1.9.4/LICENSE"
  lizenz_fetch LICENSE-leaflet.markercluster.txt "https://raw.githubusercontent.com/Leaflet/Leaflet.markercluster/v1.5.3/MIT-LICENCE.txt"
  lizenz_fetch LICENSE-maplibre-gl.txt           "https://raw.githubusercontent.com/maplibre/maplibre-gl-js/v4.7.1/LICENSE.txt"
fi

if [ "$VENDOR_FALSCH" = "1" ]; then
  echo ""
  echo "🛑 ABBRUCH: Mindestens eine Bibliothek hat die falsche Prüfsumme (siehe oben)."
  exit 1
fi
[ "$VENDOR_FEHLT" = "1" ] && echo "⚠️  Bibliotheken fehlen — die Karte funktioniert so nicht. Der Vendor-Test wird fehlschlagen."

echo ""
echo "═══ 1/4 Regressionstests ═══"
# Node.js finden — auch wenn es nicht im PATH ist (Homebrew Apple Silicon / Homebrew Intel / Installer)
NODE="$(command -v node || true)"
for p in /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node; do
  [ -z "$NODE" ] && [ -x "$p" ] && NODE="$p"
done
if [ "${DEPLOY_OHNE_TESTS:-0}" = "1" ]; then
  echo "ℹ️  Tests übersprungen (DEPLOY_OHNE_TESTS=1)"
elif [ -z "$NODE" ]; then
  echo "ℹ️  Node.js nicht gefunden — Tests übersprungen. Für Entwickler: brew install node"
elif ! "$NODE" test-app.js; then
  echo ""
  echo "❌ TESTS FEHLGESCHLAGEN — Deploy abgebrochen."
  echo "   Kein Feature darf verschwinden. Erst fixen, dann deployen."
  exit 1
fi

if [ -z "$APP" ]; then
  echo ""
  echo "ℹ️  Kein App-Bundle gefunden (Safari Assistant.app — oder unter altem Namen Safari-Assistent.app, DARK.app bzw. „Safari Assistent.app\" — auf dem Schreibtisch bzw. in Programme)."
  echo "   App bauen:        ./build-app.sh"
  echo "   Ohne App starten: python3 server.py   → dann http://localhost:8765 öffnen"
  echo ""
  echo "🟢 Fertig (ohne Bundle)."
  exit 0
fi
echo ""
echo "📦 App-Bundle: $APP"

echo ""
echo "═══ 2/4 Downgrade-Sperre (Versionsmarker) ═══"
# 2026-10-04-1: auch i18n.js (Marker „Safari Assistant i18n.js vJJJJ-MM-TT-N" im Kopfkommentar)
for f in index.html mobile.html pois.html i18n.js; do
  vsrc=$(version_of "$SRC/$f")
  vdst=$(version_of "$DST/$f")
  if [ -z "$vsrc" ]; then
    echo "⚠️  $f: KEIN Versionsmarker in der Quelle! Bitte vJJJJ-MM-TT-N in den ersten 3 Zeilen ergänzen (HTML: '<!-- Safari Assistant $f vJJJJ-MM-TT-N -->' in Zeile 2)."
    read -p "   Trotzdem deployen? (j/N) " a; [ "$a" = "j" ] || exit 1
  elif [ -n "$vdst" ]; then
    newest=$(printf '%s\n%s\n' "$vsrc" "$vdst" | sort -V | tail -1)
    if [ "$newest" != "$vsrc" ] && [ "$vsrc" != "$vdst" ]; then
      echo "🛑 $f: Quelle ($vsrc) ist ÄLTER als Bundle ($vdst)!"
      echo "   → Typisches Regressions-Muster: Datei wurde aus veralteter Version regeneriert."
      read -p "   Wirklich DOWNGRADE deployen? (j/N) " a; [ "$a" = "j" ] || exit 1
    else
      echo "✅ $f: $vsrc (Bundle: ${vdst:-leer})"
    fi
  else
    echo "✅ $f: $vsrc (Bundle hatte noch keinen Marker)"
  fi
done

echo ""
echo "═══ 3/4 Kopieren ins Bundle ═══"
mkdir -p "$DST/i18n"   # Wörterbücher der Oberflächensprache (i18n/en.js, fr.js, es.js)
for f in "${FILES[@]}"; do
  if [ -f "$SRC/$f" ]; then
    cp "$SRC/$f" "$DST/$f" && echo "✅ $f → Bundle"
  else
    echo "⚠️  $f fehlt im Projektordner — übersprungen"
  fi
done
# Die Anleitung für /hilfe (hilfe.py): im öffentlichen Repo liegen die README-Dateien im Projektordner,
# im Arbeitsordner, aus dem der Release entsteht, in release-docs/. Eine fehlende Übersetzung ist kein
# Fehler — die Seite zeigt dann die englische Fassung mit Hinweis.
for f in "${README_DATEIEN[@]}"; do
  if [ -f "$SRC/$f" ]; then
    cp "$SRC/$f" "$DST/$f" && echo "✅ $f → Bundle"
  elif [ -f "$SRC/release-docs/$f" ]; then
    cp "$SRC/release-docs/$f" "$DST/$f" && echo "✅ release-docs/$f → Bundle"
  fi
done

# Launcher: Programmname aus der Info.plist (Safari Assistant; bei älteren Bundles Safari-Assistent, DARK bzw. „Safari Assistent").
# Ohne lesbare Info.plist: der Name des Bundles (DARK.app → DARK) — das passt auch zu älteren Bundles.
# 2026-09-12: Vorher schrieb nur build-app.sh den Launcher — ein Launcher von vor September sah
# Port 8765 belegt, meldete „wird wiederverwendet" und startete server.py gar nicht.
EXE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$APP/Contents/Info.plist" 2>/dev/null || true)"
EXE="${EXE:-$(basename "$APP" .app)}"
LAUNCHER_DST="$APP/Contents/MacOS/$EXE"
if [ -f "$SRC/launcher_new.sh" ] && [ -d "$APP/Contents/MacOS" ]; then
  if ! cmp -s "$SRC/launcher_new.sh" "$LAUNCHER_DST"; then
    cp "$SRC/launcher_new.sh" "$LAUNCHER_DST" && chmod +x "$LAUNCHER_DST" && echo "✅ launcher_new.sh → Bundle (Contents/MacOS/$EXE) — beim nächsten App-Start aktiv"
  else
    echo "✅ Launcher im Bundle ist aktuell"
  fi
else
  echo "⚠️  Launcher nicht aktualisiert (launcher_new.sh oder Contents/MacOS fehlt)"
fi

# Offline-Bibliotheken (inkl. Lizenztexte)
mkdir -p "$DST/vendor"
for vf in "$SRC/vendor/"*; do
  case "$vf" in *.tmp) continue ;; esac
  [ -f "$vf" ] && cp "$vf" "$DST/vendor/" && echo "✅ vendor/$(basename "$vf") → Bundle"
done

# Offline-Daten (data/) — Parkgrenzen (fetch-parks.py, © OSM/ODbL), Ortsindex (fetch-orte.py,
# GeoNames CC BY 4.0), Klimatologie (fetch-klima.py, NASA POWER). Fehlen ist ok — die Karte fällt
# sichtbar zurück (nie still scheitern).
if [ -f "$SRC/data/parks.geojson" ]; then
  mkdir -p "$DST/data"
  cp "$SRC/data/parks.geojson" "$DST/data/" && echo "✅ data/parks.geojson → Bundle ($(wc -c < "$SRC/data/parks.geojson") B)"
else
  echo "ℹ️  data/parks.geojson fehlt — Overlay nutzt grobe Regionsboxen. Einmalig: python3 fetch-parks.py"
fi
# Die Warngebiete kann auch der Assistent selbst nachziehen — dann liegt die NEUERE Datei im
# Bundle. Ein blindes Kopieren würde sie durch die ältere aus dem Arbeitsordner ersetzen.
if [ -f "$SRC/data/warnzonen.geojson" ]; then
  mkdir -p "$DST/data"
  if [ ! -f "$DST/data/warnzonen.geojson" ] || [ "$SRC/data/warnzonen.geojson" -nt "$DST/data/warnzonen.geojson" ]; then
    cp "$SRC/data/warnzonen.geojson" "$DST/data/" && echo "✅ data/warnzonen.geojson → Bundle ($(wc -c < "$SRC/data/warnzonen.geojson") B)"
  else
    echo "ℹ️  data/warnzonen.geojson im Bundle ist neuer (vom Assistenten nachgeholt) — behalten"
  fi
else
  echo "ℹ️  data/warnzonen.geojson fehlt — der Assistent erzeugt sie mit Internet selbst (oder: python3 fetch-warnzonen.py)"
fi
# Vorrat der Verwaltungsgrenzen: wird NICHT an den Browser ausgeliefert (steht nicht in der
# Statik-Allowlist), der Server braucht sie aber im Bundle, um neue Warngebiete ohne Internet
# zeichnen zu können.
if [ -f "$SRC/data/verwaltungsgebiete.geojson" ]; then
  mkdir -p "$DST/data"
  cp "$SRC/data/verwaltungsgebiete.geojson" "$DST/data/" && echo "✅ data/verwaltungsgebiete.geojson → Bundle ($(( $(wc -c < "$SRC/data/verwaltungsgebiete.geojson") / 1024 )) KB)"
else
  echo "ℹ️  data/verwaltungsgebiete.geojson fehlt — neue Warngebiete brauchen dann Internet. Einmalig: python3 fetch-warnzonen.py --vorrat"
fi
if [ -f "$SRC/data/orte.json" ]; then
  mkdir -p "$DST/data"
  cp "$SRC/data/orte.json" "$DST/data/" && echo "✅ data/orte.json → Bundle ($(wc -c < "$SRC/data/orte.json") B)"
else
  echo "ℹ️  data/orte.json fehlt — Kartensuche ohne Offline-Orte. Einmalig: python3 fetch-orte.py"
fi
# Klimatologie der Regenzeit-Ebene (fetch-klima.py, NASA POWER). Fehlt sie, sagt der 🌧️-Knopf das sichtbar.
if [ -f "$SRC/data/klima.json" ]; then
  mkdir -p "$DST/data"
  cp "$SRC/data/klima.json" "$DST/data/" && echo "✅ data/klima.json → Bundle ($(wc -c < "$SRC/data/klima.json") B)"
else
  echo "ℹ️  data/klima.json fehlt — Regenzeit-Ebene ohne Daten. Einmalig mit Internet: python3 fetch-klima.py"
fi

echo ""
echo "═══ 4/4 Git-Sicherung ═══"
# 2026-09-27 (Review): nur noch auf ausdrücklichen Wunsch. Vorher committete jeder Deploy mit
# „git add -A" — in einem öffentlichen Klon landete so alles Nicht-Ignorierte in der Historie.
if [ "${DEPLOY_COMMIT:-0}" = "1" ] || [ -f "$SRC/.deploy-commit" ]; then
  if [ -d "$SRC/.git" ]; then
    git add -A
    if git diff --cached --quiet; then
      echo "✅ Keine Änderungen — nichts zu committen"
    else
      git commit -m "Deploy $(date '+%Y-%m-%d %H:%M') — $(version_of "$SRC/index.html")" >/dev/null \
        && echo "✅ Git-Commit erstellt: $(git log -1 --oneline)"
    fi
  else
    echo "⚠️  Kein Git-Repo im Projektordner — nichts gesichert"
  fi
else
  echo "ℹ️  Kein automatischer Commit (nur mit DEPLOY_COMMIT=1 oder Datei .deploy-commit)"
fi

echo ""
echo "🟢 DEPLOY ABGESCHLOSSEN — jetzt: Safari Cmd+Shift+R, am iPhone Seite neu laden"
echo "   (iPhone-Versionscheck: ⚙️-Setup-Sheet muss aktuelle Version zeigen)"
