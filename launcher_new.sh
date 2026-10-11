#!/bin/bash
# Safari Assistant — App-Launcher (liegt im Bundle unter Contents/MacOS/<CFBundleExecutable>), v2026-10-05-1
# Einzige Quelle: launcher_new.sh im Projektordner — build-app.sh und deploy.sh kopieren ihn ins Bundle.

# 2026-09-27 (Audit M1): Logs nicht mehr unter /tmp (für alle Konten lesbar, feste Namen → Symlink-
# Falle), sondern in ~/Library/Logs/Safari Assistant und nur für den eigenen Nutzer lesbar.
# Ordner heißt wie die App (2026-10-05-1: „Safari Assistant" mit Leerzeichen, vorher ~/Library/Logs/DARK;
# server.py benutzt denselben Ordner).
umask 077
LOG_DIR="$HOME/Library/Logs/Safari Assistant"
mkdir -p "$LOG_DIR"
OLLAMA_PID=""

# Ollama NUR starten, falls es nicht schon läuft (z. B. als Ollama.app oder LaunchAgent)
if ! curl -s http://localhost:11434 > /dev/null 2>&1; then
  for OLLAMA_PATH in \
    "/usr/local/bin/ollama" \
    "/opt/homebrew/bin/ollama" \
    "$HOME/.ollama/ollama" \
    "$(which ollama 2>/dev/null)"; do
    if [ -x "$OLLAMA_PATH" ]; then
      # 2026-09-12-1: Ollama bleibt IMMER auf 127.0.0.1 (Ollama-Standard). Das iPhone erreicht es
      # durch den Assistent-Server (/api/ollama/*), und zwar nur im iPhone-Modus mit Zugangscode.
      # Der frühere 0.0.0.0-Zweig mit OLLAMA_ORIGINS ist weg: OLLAMA_ORIGINS schützt nur Browser —
      # per curl konnte jedes Gerät im WLAN Modelle löschen oder ziehen.
      # 2026-09-19: Ollama 0.34.2 statt 0.20.5. Die alten Startvariablen sind weg: OLLAMA_NUM_GPU und
      # OLLAMA_LIBRARY_PATH kennt 0.34.2 nicht mehr, und OLLAMA_LLM_LIBRARY („bypass autodetection")
      # würde die automatische Wahl von Metal/MLX aushebeln. OLLAMA_NO_CLOUD: keine Cloud-Modelle,
      # keine Websuche über ollama.com — dieses System ist offline.
      OLLAMA_NO_CLOUD=1 \
        "$OLLAMA_PATH" serve > "$LOG_DIR/ollama.log" 2>&1 &
      OLLAMA_PID=$!
      sleep 3
      break
    fi
  done
fi

RESOURCES="$(dirname "$0")/../Resources/safari-assistant"
RESOURCES="$(cd "$RESOURCES" && pwd)"

# 2026-09-27 (Review P0-1): Fehlt server.py im Bundle, gibt es KEINEN stillen Ersatz mehr. Vorher
# startete hier „python3 -m http.server" — die Seiten luden, aber jede /api-Anfrage lief ins Leere,
# und die Einstellungen stellten die falsche Diagnose („anderer Prozess auf dem Port").
if [ ! -f "$RESOURCES/server.py" ]; then
  osascript -e 'display alert "Safari Assistant startet nicht" message "server.py fehlt im App-Bundle.\n\nIm Projektordner einmal ausführen:\n./deploy.sh   (oder ./build-app.sh)" as critical' >/dev/null 2>&1
  exit 1
fi

# 2026-09-11-1: KEINE eigene Portsuche mehr. Vorher wich der Launcher bei belegtem 8765 still auf
# 8766 aus — hielt dort eine Waise den Port, öffnete der Browser eine Adresse, unter der nichts
# antwortete (nur per `lsof` im Terminal aufzulösen). Jetzt entscheidet server.py: eine eigene
# Altinstanz wird beendet und der gewohnte Port übernommen, nur fremde Software führt zu einem
# Ausweichport — und der wird unten ausgelesen statt geraten.
# SAFARI_PARENT_WATCH=1: der Server beendet sich mit diesem Launcher. Damit entstehen bei einem
# Force-Quit der App gar keine Waisen mehr.
PORT=8765
cd "$RESOURCES"

# 2026-09-16: Läuft die App unter Rosetta — im Finder unter „Informationen" angehakt, oder von einem
# übersetzten Elternprozess gestartet —, dann startet das universelle python3 als x86_64. Es findet
# dann keine arm64-Bibliothek mehr: PyMuPDF scheiterte mit „incompatible architecture (have 'arm64',
# need 'x86_64')", OBWOHL es installiert war, und pip meldete beim Nachinstallieren stur „already
# satisfied". „arch -arm64" erzwingt den nativen Lauf; auf Intel-Macs schlägt der Test fehl und die
# Zeile bleibt leer, der Aufruf ist dann unverändert.
PY_ARCH=""
# Geprüft wird nicht nur, ob es „arch" gibt, sondern ob GENAU DAS läuft, was gleich gestartet
# wird — sonst stünde die App bei einem nicht-universellen python3 ganz ohne Server da.
if arch -arm64 python3 -c "pass" >/dev/null 2>&1; then PY_ARCH="arch -arm64"; fi

SAFARI_PARENT_WATCH=1 $PY_ARCH python3 "$RESOURCES/server.py" $PORT > "$LOG_DIR/server.log" 2>&1 &
SERVER_PID=$!
# Warten, bis der Server WIRKLICH antwortet (statt blind nach 1 s zu öffnen) und dabei den
# tatsächlichen Port lernen. Stirbt der Server vorher, bricht die Schleife sofort ab.
URL=""
for _ in $(seq 1 60); do
  for P in $PORT $((PORT+1)) $((PORT+2)) $((PORT+3)); do
    if curl -fsS --max-time 1 "http://127.0.0.1:$P/api/ping" 2>/dev/null | grep -q '"app": "safari-assistent"'; then   # Signatur (APP_SIGNATUR in server.py, bleibt so)
      URL="http://localhost:$P/index.html"; break 2
    fi
  done
  kill -0 $SERVER_PID 2>/dev/null || break
  sleep 0.5
done

if [ -n "$URL" ]; then
  open "$URL"
else
  # Nichts scheitert still: statt einer toten Browserseite eine Meldung, die den Weg zeigt.
  osascript -e 'display alert "Safari Assistant startet nicht" message "Der lokale Server ist nicht hochgekommen. Im Terminal nachsehen:\n\ntail -20 ~/Library/Logs/\"Safari Assistant\"/server.log" as critical' >/dev/null 2>&1
fi

cleanup() {
  kill $SERVER_PID 2>/dev/null
  # Ollama nur beenden, wenn dieser Launcher es gestartet hat
  if [ -n "$OLLAMA_PID" ]; then
    kill $OLLAMA_PID 2>/dev/null
  fi
  exit 0
}
trap cleanup SIGTERM SIGINT

wait $SERVER_PID
