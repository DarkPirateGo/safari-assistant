# Safari Assistant

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/logo/safari-assistant-wordmark-dark.svg"><img src="docs/img/logo/safari-assistant-wordmark-light.svg" alt="Safari Assistant" width="420"></picture></p>

*Diese Anleitung auf: [English](README.md) · **Deutsch** · [Français](README.fr.md) · [Español](README.es.md)*

**Ein Offline-KI-Feldassistent für Overland-Reisen im südlichen und östlichen Afrika: Chat-Module mit lokalen Modellen auf deinem Mac, eine Offline-Karte mit Regenzeiten und amtlichen Reisewarnungen, eine Notfall-Karte, die ohne KI funktioniert, und eine Handy-Ansicht über dein eigenes WLAN.**

Für Macs mit Apple Silicon. Auf Englisch, Deutsch, Französisch und Spanisch. Kostenlos für nicht-kommerzielle Nutzung.

[![CI](https://github.com/DarkPirateGo/safari-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/DarkPirateGo/safari-assistant/actions/workflows/ci.yml)
[![Lizenz: PolyForm Noncommercial](https://img.shields.io/badge/License-PolyForm%20Noncommercial-blue.svg)](LICENSE)

> [!IMPORTANT]
> - **Nur für Macs mit Apple Silicon.**
> - **Welchen Mac du brauchst:** siehe [Welches Modell auf welchem Mac](#welches-modell-auf-welchem-mac).
> - **Stand:** vom Autor für die Reisevorbereitung genutzt. Noch nicht im Feld erprobt. Getestet auf einem einzigen Rechner (Apple Silicon, 36 GB).

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/chat-dark.png"><img src="docs/img/en/chat-light.png" width="250" alt="Ein Chat mit einem der Module von Safari Assistant"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/map-dark.png"><img src="docs/img/en/map-light.png" width="250" alt="Die Offline-Karte von Safari Assistant"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/img/en/emergency-dark.png"><img src="docs/img/en/emergency-light.png" width="250" alt="Die Notfall-Ansicht von Safari Assistant"></picture>
</p>
<p align="center"><sub>Beispielansicht mit Beispieldaten ·
<a href="https://darkpiratego.github.io/safari-assistant/">Website</a></sub></p>

---

## Was Safari Assistant kann

### 14 Chat-Module

Jedes Modul hat seinen eigenen System-Prompt, seinen eigenen Chat-Verlauf und sein eigenes Modell. 12 laufen mit lokalen Modellen über [Ollama](https://ollama.com). 2 sind optionale Online-Module, die deinen eigenen Anthropic-API-Key brauchen.

| Modul (Name in der App) | Wofür | Standardmodell |
|---|---|---|
| 🔧 Mechanik | Fahrzeugdiagnose und Reparatur unterwegs, abgestimmt auf den Toyota HZJ78 / 1HZ-Diesel | `qwen3.6:35b-a3b` |
| 🐘 Natur & Tiere | Tiere und Pflanzen, Artbestimmung, Einschätzung von Gefahren | `qwen3.6:35b-a3b` |
| 🏥 Medizin & Erste Hilfe | Tropen- und Wildnismedizin, Erste Hilfe | `qwen3.6:35b-a3b` |
| 🗺️ Navigation & Gelände | Routen, Gelände, Wasserdurchfahrten, Grenzposten | `qwen3.6:35b-a3b` |
| 🐕 Hund | Gesundheit und Sicherheit des Hundes unterwegs | `qwen3.6:35b-a3b` |
| 🌿 Überleben & Orientierung | Wasser, Unterschlupf, Orientierung, Signale geben | `qwen3.6:35b-a3b` |
| 📸 Wildtier-Fotografie | Wildtierfotografie | `qwen3.6:35b-a3b` |
| 🗣️ Sprachen | Redewendungen und Übersetzung für die Region | `qwen3.6:35b-a3b` |
| 🚨 Notfall-Protokoll | Notfall-Chat, ruhige Anleitung Schritt für Schritt | `qwen3.6:35b-a3b` |
| 🌦️ Wetter & Regenzeiten | Jahreszeiten und Regenzeiten. Auf dem Mac geht es über Claude online, wenn ein API-Key gespeichert ist | `gemma4:e4b` |
| 🍳 Camp-Küche | Kochen mit dem, was im Fahrzeug ist | `gemma4:e4b` |
| 💪 Fitness | Training ohne Geräte | `gemma4:e4b` |
| 🌍 Sicherheitslage — Live | Aktuelle Sicherheitslage, mit Websuche (online) | Claude, wählbar |
| ✦ Claude — Online KI | Allgemeiner Online-Assistent mit Websuche (online) | Claude, wählbar |

- Eine einzige Einstellung stellt alle lokalen Module auf ein anderes Modell um: ⚙️ Einstellungen → **Globales Modell**.
- Das Online-Modell wählst du unter ⚙️ Einstellungen → Claude API → **Liste laden**; dabei fragt Safari Assistant bei Anthropic nach, welche Modelle dein Key nutzen kann.
- **Eigene Handbücher:** Lade PDFs hoch, etwa ein Werkstatthandbuch, ein Erste-Hilfe-Buch oder einen Reiseführer, und ordne sie einem Modul zu (braucht PyMuPDF, siehe [Schnellstart](#schnellstart)). Das Modul durchsucht sie offline und nennt Dokument, Kapitel und Seite.
- **Fotos:** Hänge ein Foto an, etwa von einem Schild, einem Ersatzteil, einer Pflanze oder einem Tier, und frag danach. Bei den lokalen Modulen sieht sich das Modell das Foto auf deinem Mac an; nichts wird hochgeladen.
- Außerdem können Module eine optionale Offline-Wikipedia durchsuchen und daraus zitieren.

### Offline-Karte

- Vektorkarte aus deiner eigenen `karte.mbtiles` (einmal gebaut, siehe [docs/SETUP.md](docs/SETUP.md#6-offline-map), englisch) oder Online-Kacheln von OpenStreetMap.
- 🌧️ **Regen:** Ebene mit den Regenzeiten und einer Zeitleiste Tag für Tag. Tippe auf eine Zelle, dann siehst du für den Monat Regen, Temperaturen, Luftfeuchte, Wind, Sonneneinstrahlung und die Malariasaison. Sie zeigt langjährige Mittelwerte, keine Vorhersage.
- ℹ️ Wetter-Panel für deine Position; online und auf Anfrage eine 7-Tage-Vorhersage von Open-Meteo.
- 🛑 **Warnung:** amtliche Reisewarnungen aus Deutschland, Großbritannien und den USA, automatisch abgerufen, sobald der Mac online ist, und offline lesbar. Gewarnte Distrikte werden als Flächen gezeichnet, und Safari Assistant sagt dir, ob deine Position in einer davon liegt.
- 🦟 **Gefahren:** Gefahrenzonen (Malaria, Tsetse, Großwild, Krokodile), dazu die Grenzen der Nationalparks.
- **Rund 90.000 Orte** aus OpenStreetMap liegen der App bei, eine Datei pro Land in `POIs/`, einmal auf der Karte importiert: Campingplätze, Tankstellen, Wasser, Werkstätten, Krankenhäuser, Tierärzte und Grenzposten. Deine eigenen GPX-, KML- und GeoJSON-Dateien lassen sich ebenfalls importieren.
- Ortssuche offline; Straßensuche online nur, wenn du Enter drückst.

### Notfall-Karte (funktioniert ohne KI)

- Notrufnummern je Land (antippbar) und die Nummern der deutschen Botschaften.
- Deine Position in Dezimalgrad, in Grad/Minuten/Sekunden und als Plus Code, für Funk oder Satelliten-Messenger.
- 8 Erste-Hilfe-Protokolle als fester Text (**Sofort-Protokolle**), mit einem Tippen lesbar.
- Persönliche Felder (Medizinisches, Dokumente, Fahrzeug, Kontakte), Wechselkurs, Sonnenzeiten, Dokumentenfristen.

### Reisewerkzeuge

Checklisten, Dokumentenfristen, ein Wartungsplan (Vorlage für den Toyota HZJ78 / 1HZ, dazu eigene Punkte), ein Logbuch für Tanken und Wartung, Notizen, gespeicherte Antworten, Chat-Verlauf und Backups.

### Handy-Ansicht über dein eigenes WLAN

`mobile.html` läuft auf einem iPhone im selben WLAN: dieselben Module, ein 🚨-Notfallblatt und die Karte, alles über den Mac per HTTPS mit einem Zugangscode. Siehe [iPhone-Modus](#iphone-modus).

### Optional

- **Offline-Wikipedia** über `kiwix-serve` (📚), auch auf dem Handy.
- **Online-Module** mit deinem eigenen Anthropic-API-Key.

Gebiet: 16 Länder — Angola, Äthiopien, Botswana, Burundi, Eswatini, Kenia, Lesotho, Malawi, Mosambik, Namibia, Ruanda, Sambia, Simbabwe, Südafrika, Tansania, Uganda.

---

## Voraussetzungen

| | |
|---|---|
| **Mac** | Apple Silicon, macOS |
| **Arbeitsspeicher** | Entscheidet, welches Modell du nutzen kannst: siehe [Welches Modell auf welchem Mac](#welches-modell-auf-welchem-mac). Das Standardmodell `qwen3.6:35b-a3b` wurde auf einem Mac mit 36 GB gemessen (etwa 22 GB belegt). 32 GB reichen dafür bei voller GPU-Geschwindigkeit wahrscheinlich nicht (Schätzung) |
| **Ollama** | 0.34 oder neuer (getestet mit 0.34.2), von [ollama.com](https://ollama.com) oder per `brew install ollama` |
| **Python** | 3.9 oder neuer. Aus dem Finder gestartet, läuft die App mit `/usr/bin/python3` |
| **Node.js** | nur für die Testsuite |
| **Java 21+** | nur zum Bauen der Offline-Karte |
| **Optional** | PyMuPDF (PDF-Dokumente), kiwix-tools (Offline-Wikipedia), ein Anthropic-API-Key (Online-Module) |

| Download | Größe | Hinweise |
|---|---|---|
| Modelle | 6,6–33,5 GB, je nach Mac | Standardmodelle (`qwen3.6:35b-a3b` und `gemma4:e4b`): 29,6–33,5 GB, etwa 1,5 Stunden bei 50 Mbit/s |
| Offline-Karte (`setup-offline-karte.sh`) | am Ende etwa 8 GB, beim Bauen etwa 80 GB freier Platz | läuft mehrere Stunden |
| Offline-Wikipedia (ZIM-Dateien) | 2–55 GB, je nach Archiv | optional |

Erledige die großen Downloads zu Hause über eine schnelle Leitung, lange vor der Abreise. Ortsverzeichnis, Parkgrenzen, Klimadaten und POIs liegen schon in diesem Repository.

`server.py` ist reines Python und läuft vielleicht auch anderswo, getestet ist aber nur macOS auf Apple Silicon, und die Skripte für das App-Bundle gibt es nur für macOS.

---

## Welches Modell auf welchem Mac

Die gesamte Offline-KI läuft auf dem Mac. Das iPhone schickt seine Fragen nur an den Mac; deshalb entscheidet der gemeinsame Arbeitsspeicher des Macs, welche Modelle du nutzen kannst.

Geprüft am 4. Oktober 2026. Die Downloadgrößen stammen aus der Ollama-Bibliothek. Es sind Spannen, weil Ollama nicht angibt, ob ein Mac den mlx- oder den llamacpp-Build bekommt; plane mit der größeren Zahl. **Gemessene** Werte stammen von einem einzigen Mac: MacBook Pro M5 Max, 36 GB, Ollama 0.34.2, Kontext 16.384 Token. Alles andere ist eine **Schätzung** und nicht mit Safari Assistant getestet.

| Arbeitsspeicher | Modell für Chat und Fotos | Download gesamt (mit `gemma4:e4b`) | Hinweise |
|---|---|---|---|
| 8 GB | `gemma4:e4b` (leichtes Profil) | 6,6–9,5 GB | Schätzung. Sehr knapp, womöglich langsam. Für die Reise nicht empfohlen |
| 16 GB | `gemma4:e4b` (leichtes Profil) | 6,6–9,5 GB | Schätzung. Ein kleines Modell für alles: weniger ausführliche Antworten (nicht per Benchmark geprüft) |
| 24 GB | `gemma4:12b` | 14,6–17,2 GB | Schätzung, ungetestetes Upgrade. Die App selbst schlägt hier das leichte Profil vor |
| 32 GB | `gemma4:26b` | etwa 25,5 GB | Schätzung, ungetestet. Das Standardmodell passt wahrscheinlich nicht vollständig auf die GPU |
| 36–48 GB | `qwen3.6:35b-a3b` (Standard) | 29,6–33,5 GB | **Gemessen mit 36 GB:** 22 GB belegt, 100 % GPU, etwa 92–98 Token/s. 48 GB: Schätzung |
| 64 GB oder mehr | `qwen3.6:35b-a3b` (Standard) | 29,6–33,5 GB | Schätzung: Platz für beide Modelle. Optional: `qwen3.6:35b-a3b-q8_0` (39 GB) für höhere Genauigkeit |

Jeder Mac braucht `gemma4:e4b`: Der Knopf ⚡ **Schnell**, die Offline-Zusammenfassungen von Chats und die Wikipedia-Suchbegriffe nutzen immer dieses Modell. Verwende genau diese Tag-Namen: `gemma4:e4b`, nicht eine Variante wie `gemma4:e4b-it-qat`.

Lade die Modelle einmal mit Internet im Terminal herunter:

```bash
# 8 GB und 16 GB
ollama pull gemma4:e4b

# 24 GB
ollama pull gemma4:12b
ollama pull gemma4:e4b

# 32 GB
ollama pull gemma4:26b
ollama pull gemma4:e4b

# 36 GB oder mehr (Standard der App, keine Einstellung nötig)
ollama pull qwen3.6:35b-a3b
ollama pull gemma4:e4b
```

Dann stellst du das Modell in Safari Assistant ein:

- **8 GB und 16 GB (leichtes Profil):** Klicke im Start-Banner auf **Leichtes Profil**, oder setze ⚙️ Einstellungen → **Globales Modell** auf `gemma4:e4b`.
- **24 GB und 32 GB:** Setze ⚙️ Einstellungen → **Globales Modell** auf `gemma4:12b` oder `gemma4:26b`.
- **iPhone:** Das Handy hat eine eigene Modelleinstellung, die nicht mit dem Mac abgeglichen wird. Stelle dort dasselbe Modell ein: ⚙️ Setup → **Ollama-Modell**.
- **8 GB, wenn `gemma4:e4b` zu langsam ist:** Lade `gemma4:e2b` (4,6–7,5 GB) und setze es auf dem Mac und auf dem iPhone als globales Modell. Der ⚡-Knopf, die Offline-Zusammenfassungen und die Wikipedia-Suchbegriffe nutzen weiterhin `gemma4:e4b`.

> [!TIP]
> Führe nach einer Frage in Safari Assistant `ollama ps` aus. In der Spalte PROCESSOR sollte `100% GPU` stehen. Alles andere, etwa `48%/52% CPU/GPU`, heißt: Das Modell passt nicht auf die GPU, und die Antworten werden deutlich langsamer. Wähle dann ein kleineres Modell.

Gut zu wissen:

- macOS lässt die GPU nur einen Teil des Arbeitsspeichers nutzen: etwa 2/3 auf kleineren Macs und etwa 3/4 auf größeren. Das sind Messungen aus der Community; Apple veröffentlicht keine Formel. Deshalb sind 32 GB für das Standardmodell wahrscheinlich zu wenig (Schätzung).
- Mit dem leichten Profil antworten auch die Module Medizin & Erste Hilfe und Notfall-Protokoll mit dem kleinen Modell. Die Antworten sind kürzer und weniger verlässlich. Prüfe alles, worauf es ankommt.
- Nicht gemessen: ob auf 36 GB beide Modelle zugleich geladen bleiben (falls nicht, dauerte das Neuladen von `qwen3.6:35b-a3b` etwa 5–6 s), die Geschwindigkeit auf anderen Chips sowie die Antwort- und Fotoqualität von `gemma4:12b` und `gemma4:26b`. Anfragen vom iPhone können einen längeren Kontext nutzen (bis 32.768 Token), der mehr Speicher braucht als gemessen.

Quellen: Ollama-Bibliothek ([Qwen3.6](https://ollama.com/library/qwen3.6/tags), [Gemma 4](https://ollama.com/library/gemma4/tags)), [Ollama-FAQ](https://docs.ollama.com/faq), [Apple: recommendedMaxWorkingSetSize](https://developer.apple.com/documentation/metal/mtldevice/recommendedmaxworkingsetsize).

---

## Schnellstart

**1. Installiere Ollama** (0.34 oder neuer) und sorge dafür, dass es läuft. Lade dann die Modelle. Für einen Mac mit 36 GB oder mehr:

```bash
ollama pull qwen3.6:35b-a3b     # Standardmodell, für Macs mit 36 GB oder mehr
ollama pull gemma4:e4b          # kleines Modell: ⚡ Schnell, Zusammenfassungen, leichte Module, Wikipedia-Suchbegriffe
```

Weniger Arbeitsspeicher: Lade die Modelle für deinen Mac aus [Welches Modell auf welchem Mac](#welches-modell-auf-welchem-mac). Umgebungsvariablen sind nicht nötig.

**2. Safari Assistant holen und die App bauen:**

```bash
git clone https://github.com/DarkPirateGo/safari-assistant.git && cd safari-assistant
./deploy.sh        # prüft die Kartenbibliotheken in vendor/, führt die Tests aus, wenn Node installiert ist
./build-app.sh     # erstellt ~/Desktop/Safari Assistant.app
```

**3. Starten** per Doppelklick auf `Safari Assistant.app`. Der Starter startet Ollama, falls es noch nicht läuft, startet den Server und öffnet `http://localhost:8765` in deinem Browser. Kommt der Server nicht hoch, erscheint die Meldung „Safari Assistant startet nicht“. Die Logs liegen in `~/Library/Logs/Safari Assistant/`.

**Ohne App-Bundle:** Führe im Projektordner `python3 server.py` aus und öffne `http://localhost:8765`. Ollama muss dann schon laufen.

Was die beiden Skripte tun:

- `deploy.sh` lädt die Kartenbibliotheken nur dann nach `vendor/`, wenn sie fehlen, und prüft ihre SHA-256-Pins. Es führt die Tests aus, wenn Node installiert ist (überspringen mit `DEPLOY_OHNE_TESTS=1`). Findet es ein vorhandenes `Safari Assistant.app`, kopiert es die App-Dateien hinein; findet es keins, sagt es das. Es committet nie nach git, außer `DEPLOY_COMMIT=1` ist gesetzt oder eine Markierungsdatei `.deploy-commit` existiert; das ist nur für den Maintainer gedacht.
- `build-app.sh` erstellt `~/Desktop/Safari Assistant.app` mit Server, Daten und Bibliotheken. Ein erneuter Aufruf aktualisiert das Bundle an Ort und Stelle. Deine Daten im Bundle werden nie gelöscht: hochgeladene Dokumente, `rag-store.json`, `karte.mbtiles`, `fonts/` und `data/warnzonen.geojson`.

**Aktualisieren:** `git pull && ./deploy.sh`, dann Safari Assistant neu starten.

**PDF-Dokumente (optional):** Installiere PyMuPDF für das Python, mit dem der Server läuft. Für die aus dem Finder gestartete App ist das `/usr/bin/python3 -m pip install --user pymupdf`. Starte Safari Assistant neu. Scheitert ein Upload trotzdem, nennt die Fehlermeldung den genauen Interpreter.

Offline-Karte, Offline-Wikipedia und alle weiteren Details: [docs/SETUP.md](docs/SETUP.md).

---

## iPhone-Modus

1. Am Mac: ⚙️ Einstellungen → **iPhone-Modus** → **Einschalten**. Der Mac lauscht dann zusätzlich auf seiner WLAN-Adresse, am selben Port 8765, per HTTPS. Bei der ersten Nutzung legt Safari Assistant dafür eine lokale Zertifizierungsstelle (CA) an.
2. Einmal pro iPhone dieser CA vertrauen:
   - Die Einstellungen in Safari Assistant zeigen die Zertifikatsdatei samt Knopf **Im Finder zeigen**. Schick die Datei per AirDrop aufs iPhone.
   - iPhone: Einstellungen → **Profil geladen** → Installieren.
   - iPhone: Einstellungen → Allgemein → Info → **Zertifikatsvertrauen** → **„Safari Assistant lokale CA“** einschalten (ältere Installationen: „DARK lokale CA“ oder „Safari Assistent lokale CA“). Diesen Vertrauensschritt vergisst man am häufigsten.
3. Scanne den QR-Code in den Einstellungen mit der iPhone-Kamera, oder öffne `https://<your-mac>.local:8765/go/<code>` in Safari. Das speichert den Zugangscode und öffnet die Handy-Ansicht.
4. Teilen → **Zum Home-Bildschirm**.

Gut zu wissen:

- Nach jedem Start ist der iPhone-Modus aus. Er schaltet sich selbst ab: nach 12 Stunden ohne Anfragen vom Handy und wenn Safari Assistant beendet wird.
- **Schalte ihn nie in einem WLAN ein, dem du nicht vertraust** (Lodge, Camp, Grenze). Nutze deinen eigenen Router oder einen Handy-Hotspot.
- Hochladen, Löschen, Herunterfahren und das Umschalten des Modus gehen nur am Mac selbst.
- Die Adresse enthält den Netzwerknamen des Macs, das Zertifikat ebenso. Gib dem Mac vorher einen neutralen Namen: Systemeinstellungen → Allgemein → Teilen → Lokaler Hostname.
- Die CA ist auf `.local`-Namen und private Adressen beschränkt. Was es bedeutet, ihr zu vertrauen, und wie du sie wieder entfernst: [SECURITY.md](SECURITY.md#the-local-certificate-authority) (englisch).

---

## Was online geht

Offline verlässt nichts den Mac. Mit Verbindung ist das hier alles, was Safari Assistant sendet:

| Was | Wann | Wohin, was gesendet wird | So vermeidest du es |
|---|---|---|---|
| Reisewarnungen | Ab 20 s nach dem Start: immer wenn der Cache älter als 12 h ist, neuer Versuch alle 15 min | Auswärtiges Amt, UK FCDO, US State Department. Keine persönlichen Daten | Noch kein Schalter ([Roadmap](docs/ROADMAP.md)) |
| Flächen der Warngebiete | Nach einem Abruf der Reisewarnungen, wenn sich ein Warntext geändert hat oder noch keine Flächen existieren (höchstens alle 6 h) | Overpass API (OpenStreetMap). Keine persönlichen Daten | `SAFARI_OHNE_WARNZONEN_AUTO=1` |
| Wechselkurse | Wenn die Notfall-Karte (Mac) oder das 🚨-Notfallblatt (Handy) geöffnet wird | open.er-api.com. Keine Position | Noch kein Schalter ([Roadmap](docs/ROADMAP.md)) |
| Kartenkacheln | Solange die Karte Online-Kacheln zeigt; das ist der Standard, bis es eine Offline-`karte.mbtiles` gibt. Mit Offline-Karte laden bei jedem Öffnen der Karte noch einige Übersichtskacheln, bevor sie umschaltet | tile.openstreetmap.org. Die Kacheln verraten das Gebiet, das du dir ansiehst | Offline-Karte bauen |
| Glyphen für Kartenbeschriftungen | Nur wenn `karte.mbtiles` existiert, aber der Ordner `fonts/` dazu fehlt | fonts.openmaptiles.org | `setup-offline-karte.sh` installiert `fonts/` |
| Kartenbibliotheken | Nur wenn Dateien in `vendor/` fehlen | unpkg.com (die Kartenseite weicht dann auf das CDN aus) | `vendor/` vollständig halten (`./deploy.sh`) |
| Ortssuche | Nur wenn du in der Kartensuche Enter drückst | nominatim.openstreetmap.org. Der Suchtext | Tippen ohne Enter sucht nur offline |
| Wetter-Panel | Nur wenn du auf der Karte **Heute** oder **🌐 laden** klickst | api.open-meteo.com. Position, auf etwa 1 km gerundet | Nicht klicken |
| Anthropic | Mit API-Key: wenn du das Modul Claude oder Sicherheitslage nutzt oder auf dem Mac das Modul Wetter & Regenzeiten, und bei **Testen** / **Liste laden** in den Einstellungen | api.anthropic.com. Der Key, deine Frage, ein angehängtes Foto, der Chat-Kontext und, falls gespeichert, deine Position (±100 m) | Key löschen |
| Einmalige Skripte | Nur wenn du sie ausführst | `deploy.sh` → unpkg.com (nur fehlende `vendor/`-Dateien; mit `DEPLOY_LIZENZEN=1` auch raw.githubusercontent.com für die originalen Lizenztexte). `fetch-*.py` → Overpass, GeoNames, NASA POWER. `fauna-gbif-check.py` → GBIF. Kartenbau → GitHub, Geofabrik sowie die Ozean- und Natural-Earth-Dateien, die Planetiler herunterlädt | Nicht ausführen |
| Ollama | Für Safari Assistant nie | Der Starter startet Ollama mit `OLLAMA_NO_CLOUD=1`, falls es nicht läuft. Ein Ollama, das du selbst gestartet hast, behält seine eigenen Einstellungen | – |

Keine Telemetrie, keine Analyse-Tools, keine Schriften von Google.

---

## Sicherheit und Grenzen

Safari Assistant gibt Ratschläge zu Medizin, Schlangenbissen, Fahrzeugreparatur, Wasserdurchfahrten und Notfällen. Die Antworten kommen von Sprachmodellen, die sich mit voller Überzeugung irren können.

- Es ist **kein** Arzt, kein Mechaniker, kein Tierarzt und kein Guide. Es ersetzt weder Ausbildung noch Erste-Hilfe-Set, Satelliten-Kommunikationsgerät oder Urteilsvermögen.
- Prüfe alles, was dir schaden könnte, an einem gedruckten Handbuch, an der Offline-Wikipedia oder mit einem Menschen. Safari Assistant kann keine Hilfe rufen; nimm ein echtes Notfall-Kommunikationsgerät mit.
- **Keine Medikamentendosen**, mit Absicht. Die Prompts weisen das Modell an, keine Dosen zu nennen oder zu erfinden und auf einen Arzt, einen Tierarzt oder den Beipackzettel zu verweisen.
- Die **Notrufnummern** wurden im September 2026 geprüft. Prüfe sie vor der Abreise.
- Die **Sofort-Protokolle** auf Englisch, Französisch und Spanisch sind Übersetzungen des deutschen Texts und noch nicht von Erste-Hilfe-Fachleuten gegengelesen.
- Die **Spalte Botschaften nennt deutsche Botschaften**, für deutsche Staatsangehörige. Alle anderen wenden sich an ihre eigene Botschaft oder ihr Konsulat.
- Die **Flächen der Reisewarnungen** sind eine automatische Auslegung des amtlichen Texts, keine amtlichen Grenzen. Es gilt immer der amtliche Text; jeder Eintrag verlinkt darauf.
- Die **Regen-Ebene** ist eine Klimatologie 2001–2020 von NASA POWER, keine Vorhersage. Regenzeiten verschieben sich von Jahr zu Jahr um Wochen.
- Mit dem **leichten Profil** kommen auch medizinische und Notfall-Antworten vom kleinen Modell `gemma4:e4b`. Macs mit weniger als 36 GB sind mit Safari Assistant nicht getestet; siehe [Welches Modell auf welchem Mac](#welches-modell-auf-welchem-mac).
- Die System-Prompts sind nicht übersetzt. Sie sind für deutschsprachige Reisende geschrieben: Die Botschaftsnummern zum Beispiel sind deutsche, und das Modul Sprachen gibt die Aussprache für deutsche Leser an. Die Antworten kommen trotzdem in der Sprache, die du wählst. Das Modul Mechanik und der Wartungsplan zielen auf ein einziges Fahrzeug. Ein Reiseprofil steht auf der [Roadmap](docs/ROADMAP.md) (englisch). Wechselkurse rechnen mit EUR als Basiswährung.
- Die System-Prompts verlangen vom Modell, Unsicherheit zu benennen und früh zu sagen, wenn professionelle Hilfe nötig ist. Das senkt das Risiko; es beseitigt es nicht.

---

## Sprachen

- **Oberfläche:** Englisch, Deutsch, Französisch und Spanisch. Solange du nichts wählst, nutzt Safari Assistant die Sprache deines Browsers, wenn es eine dieser vier ist, sonst Englisch.
- **Umschalten:** am Mac mit den Knöpfen **DE / EN / FR / ES** unter dem App-Namen in der Seitenleiste oder unter ⚙️ Einstellungen → **Sprache der Oberfläche**. Am iPhone: ⚙️ Setup → **Sprache der Oberfläche**. Auf der Kartenseite: das Sprachmenü in der Kopfzeile. Die Wahl wird gespeichert.
- **KI-Antworten** folgen der Sprache der Oberfläche. Die 🌐-Leiste über dem Eingabefeld stellt die Antwortsprache trotzdem getrennt ein: Deutsch, Englisch, Französisch, Spanisch, Portugiesisch, Swahili oder Afrikaans.
- **Deutsch ist die Ausgangssprache.** Eine Übersetzungsschicht (`i18n.js` mit `i18n/en.js`, `i18n/fr.js` und `i18n/es.js`) übersetzt die Oberfläche zur Laufzeit. Was noch nicht übersetzt ist, bleibt deutsch. Die System-Prompts sind nicht übersetzt; die Antwortsprache sagt dem Modell, in welcher Sprache es antworten soll.
- Auch die 8 **Sofort-Protokolle** sind übersetzt. Die **Notfall-Karte** hat außerdem eine eigene 🌐-Leiste (DE, EN, FR, PT, SW) für ihre Beschriftungen und Tabellenköpfe, um sie einem Helfer zu zeigen.
- Archive der Offline-Wikipedia sind meist englisch. Das kleine lokale Modell macht aus deiner Frage englische Suchbegriffe.
- **Hilfe:** Das **?** auf jeder Seite (Seitenleiste am Mac, Modulleiste und Setup am iPhone, Kopfzeile der Karte) öffnet diese Anleitung in der Sprache der Oberfläche, offline. Der eigene Server von Safari Assistant zeigt sie unter `/hilfe`. Fehlt eine Übersetzung, erscheint die englische Anleitung.

Übersetzungen sind willkommen: [CONTRIBUTING.md](CONTRIBUTING.md#translations) (englisch).

---

## Datenschutz-Schranke

Das Repository hat eine Datenschutz-Schranke (`tools/privacy_gate.py`), damit niemand versehentlich persönliche Daten veröffentlicht. Aktiviere sie einmal nach dem Klonen:

```bash
git config core.hooksPath .githooks
```

Sie läuft bei pre-commit, commit-msg und pre-push und noch einmal in der CI. Sie blockiert Exporte von Tracks und Wegpunkten (GPX, KML), App-Backups, `rag-store.json`, hochgeladene Dokumente, `*.mbtiles` und `*.zim`, Schlüssel und Geheimnisse, persönliche Pfade und Hostnamen sowie Bild-Metadaten. Eigene Begriffe kannst du in einer lokalen Liste außerhalb des Repositorys ergänzen.

Umgehe sie nie mit `--no-verify`. Schlägt sie bei etwas Harmlosem an, schreib das in den Pull Request. Details: [docs/PRIVACY-GATE.md](docs/PRIVACY-GATE.md) (englisch).

---

## Entwicklung und Tests

```bash
node test-app.js
```

Reines Node, keine Abhängigkeiten, kein Build-Schritt. Die Tests lesen die Quelldateien als Text und prüfen, ob Fixes und Funktionen noch da sind. Sie führen außerdem die Python-Tests aus (`test-reisewarnungen.py`, `test-tls.py`, `test-warngebiete.py`, `test-sicherheit.py`, `test-hilfe.py`), den Selbsttest der Datenschutz-Schranke (`tools/test_privacy_gate.py`) und den Prüfer für die OSM-Daten (`tools/validate_osm_exports.py`). Dafür braucht es `python3`, und `test-tls.py` braucht `openssl`; fehlen sie, werden die Tests mit einem Hinweis übersprungen. Die CI führt dieselbe Suite bei jedem Push und jedem Pull Request aus.

Regeln, Konventionen und die Checkliste für Pull Requests: [CONTRIBUTING.md](CONTRIBUTING.md). Wie die Teile zusammenspielen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (englisch).

**Zum Namen.** Der Name wird in jeder Sprache gleich geschrieben: Safari Assistant. Während der Entwicklung hieß die App *Safari Assistent* (deutsche Schreibweise), kurz vor der ersten Veröffentlichung kurzzeitig *DARK*. DARK ist jetzt nur noch der Name ihres Erstellers. Interne Bezeichner bleiben mit Absicht unverändert, damit bestehende Installationen ihre Daten, ihre macOS-Freigaben und das Zertifikat behalten, dem das iPhone vertraut: die Schlüssel im Browserspeicher `safari-*`, die IndexedDB-Datenbanken `safari-docs` und `safari-pois-db`, das Cookie `safari_zugang`, die Dateien `~/.safari-assistant-*`, die Umgebungsvariablen `SAFARI_*`, der Bundle-Ordner `Contents/Resources/safari-assistant`, die Bundle-ID `com.safari-assistent.app`, die Zertifikatsdatei `~/.safari-assistant-tls/safari-assistent-ca.crt` und die Server-Signatur `safari-assistent` (gemeldet von `/api/ping`). Die letzten drei behalten die Schreibweise aus der Entwicklung, „assistent“. Aus der kurzen Zeit als DARK bleiben ebenfalls mit Absicht: die globalen JavaScript-Namen `window.DARK_I18N` und `window.__DARK_I18N_DATEN` (jedes Wörterbuch in `i18n/` ruft Letzteren auf) und die Umgebungsvariablen `DARK_APP` und `DARK_LOG_DIR`.

---

## Lizenzen

- **Code:** [PolyForm Noncommercial License 1.0.0](LICENSE), © 2026 DARK (github.com/DarkPirateGo). Du darfst Safari Assistant für jeden nicht-kommerziellen Zweck kostenlos benutzen, ändern und weitergeben; es ist eine Source-available-Lizenz, keine von der OSI anerkannte Open-Source-Lizenz. Kommerzielle Nutzung braucht eine eigene Lizenz von DARK; frag in einem [Issue](https://github.com/DarkPirateGo/safari-assistant/issues) an. Was die Lizenz erlaubt: [NOTICE.md](NOTICE.md#safari-assistants-own-code) (englisch).
- **Nicht unter PolyForm Noncommercial:**
  - `POIs/*-osm.json` und `data/parks.geojson`: © OpenStreetMap-Mitwirkende, ODbL 1.0
  - `data/orte.json`: GeoNames, CC BY 4.0
  - `data/klima.json`: NASA Langley Research Center, POWER-Projekt
  - `vendor/`: Leaflet (BSD-2-Clause), Leaflet.markercluster (MIT), MapLibre GL JS (BSD-3-Clause)
  - QR-Code-Encoder: angepasst nach Project Nayuki, MIT
  - Die Namen „Safari Assistant“ und „DARK“, Logo und Icon von Safari Assistant (`docs/img/logo/`, `docs/img/social-preview.png`) und das DARK-Logo `dark-logo.jpg`: alle Rechte vorbehalten. Forks müssen sie als Namen und Logo ihrer Version ersetzen. Die Zeile `Required Notice:` in [LICENSE](LICENSE), die DARK als Rechteinhaber nennt, bleibt: Die Lizenz verlangt, dass sie weitergegeben wird.
- **Absichtlich nicht enthalten:** Exporte aus iOverlander, Herstellerhandbücher, Momentaufnahmen von Reisehinweisen.

Vollständige Liste und Lizenztexte: [NOTICE.md](NOTICE.md).

---

## Danksagung

Erstellt von DARK ([github.com/DarkPirateGo](https://github.com/DarkPirateGo)).

Gebaut auf [Ollama](https://ollama.com), [Leaflet](https://leafletjs.com), [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster), [MapLibre GL JS](https://maplibre.org), [Planetiler](https://github.com/onthegomap/planetiler), [OpenMapTiles](https://openmaptiles.org), [Kiwix](https://kiwix.org) und [PyMuPDF](https://pymupdf.readthedocs.io). Daten von den Mitwirkenden bei [OpenStreetMap](https://www.openstreetmap.org/copyright), von [GeoNames](https://www.geonames.org), [NASA POWER](https://power.larc.nasa.gov) und [Open-Meteo](https://open-meteo.com). Reisehinweise vom Auswärtigen Amt, vom britischen FCDO und vom US-Außenministerium (US Department of State). QR-Code-Encoder angepasst nach [Project Nayuki](https://www.nayuki.io/page/qr-code-generator-library).

<p align="center"><a href="https://github.com/DarkPirateGo"><img src="docs/img/dark-logo.jpg" alt="DARK" width="200"></a><br><sub>made by DARK</sub></p>
