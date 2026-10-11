# Setup guide

Everything that does not fit in the Git repository (models, the offline map, offline Wikipedia), plus iPhone mode, updates and troubleshooting.

**Do the large downloads at home on a fast connection, well before you leave.** The map build alone runs for hours, and a half-downloaded archive cannot be repaired without internet.

## Contents

0. [Before you start](#0-before-you-start)
1. [Tools](#1-tools)
2. [AI models](#2-ai-models)
3. [Install Safari Assistant](#3-install-safari-assistant)
4. [First start](#4-first-start)
5. [iPhone mode](#5-iphone-mode)
6. [Offline map](#6-offline-map)
7. [Offline Wikipedia](#7-offline-wikipedia)
8. [Data files and refresh scripts](#8-data-files-and-refresh-scripts)
9. [Your own PDFs](#9-your-own-pdfs)
10. [Files Safari Assistant creates](#10-files-safari-assistant-creates)
11. [Environment variables](#11-environment-variables)
12. [Uninstall and reset](#12-uninstall-and-reset)
13. [Pre-departure checklist](#13-pre-departure-checklist)
14. [Troubleshooting](#troubleshooting)

---

## 0. Before you start

```bash
uname -m                # must print arm64 (Apple Silicon)
sysctl -n hw.memsize    # RAM in bytes; 32 GB = 34359738368
python3 --version       # 3.9 or newer
node --version          # only needed for the tests
java -version           # 21 or newer, only needed to build the offline map
df -h ~                 # free disk space
```

| Component | Size | Needed |
|---|---|---|
| Ollama models `qwen3.6:35b-a3b` and `gemma4:e4b` | 29.6–33.5 GB download (about 1.5 hours at 50 Mbit/s); less on a Mac with less memory, see [Which model on which Mac](../README.md#which-model-on-which-mac) | yes |
| Offline map | about 8 GB final; about 80 GB free space while building | for offline maps |
| Offline Wikipedia (ZIM files) | 2–55 GB, depending on the archive | optional |
| Place index, parks, climate data, POIs | in the repository | included |

---

## 1. Tools

```bash
brew install ollama node          # or Ollama from https://ollama.com and Node from https://nodejs.org
brew install --cask temurin       # Java, only for the offline map build
```

- **Ollama** 0.34 or newer; Safari Assistant was tested with 0.34.2.
- **Python** 3.9 or newer. `/usr/bin/python3` comes with the Xcode Command Line Tools (`xcode-select --install`). The app started from Finder uses exactly this Python.
- **Node.js** is only needed for `node test-app.js`.
- **Java** 21 or newer is only needed for `setup-offline-karte.sh`.
- Optional: **PyMuPDF** for PDF documents ([section 9](#9-your-own-pdfs)), **Pillow** only for `generate_icon.py`, **kiwix-tools** for offline Wikipedia ([section 7](#7-offline-wikipedia)).

---

## 2. AI models

Make sure Ollama runs (the Ollama app, `brew services start ollama` or `ollama serve` in a terminal), then:

```bash
ollama pull qwen3.6:35b-a3b    # default for 9 modules; about 22 GB of RAM in use
ollama pull gemma4:e4b         # Weather, Camp Kitchen, Fitness, and Wikipedia search terms
ollama list                    # both should be listed
```

These are the defaults for a Mac with 36 GB or more. Which models fit a Mac with less memory: [Which model on which Mac](../README.md#which-model-on-which-mac).

- **No environment variables are needed.** When Safari Assistant's launcher starts Ollama itself, it sets `OLLAMA_NO_CLOUD=1` (no Ollama cloud features). If you run Ollama yourself, you can set the same variable.
- **Model tags move.** If a pull fails, check [ollama.com/library](https://ollama.com/library) for the current tag. Then choose the model in ⚙️ Settings (Einstellungen) → **Model per module**, or for all local modules at once in **Global Model**. No file needs editing.
- **Do not expose Ollama.** Leave `OLLAMA_HOST` at its default (`127.0.0.1`) and do not set `OLLAMA_ORIGINS`. Ollama has no authentication. The phone reaches it only through Safari Assistant's proxy, and only while iPhone mode is on.
- **Models on an external SSD:** Ollama reads `OLLAMA_MODELS` from its own environment. See the Ollama FAQ for how to set it on macOS.

### Light profile (8–16 GB RAM)

1. Pull only `gemma4:e4b`.
2. Mac: ⚙️ Settings → **Global Model** → `gemma4:e4b`. The missing-model banner then disappears.
3. iPhone: ⚙️ Setup → **Ollama model** → `gemma4:e4b`. The phone keeps its own setting.

With this profile the medical and emergency modules also answer from the 4B model. Answers get shorter and less reliable, especially for diagnosis. That is a real trade-off.

With 24 GB or 32 GB you can use a larger model instead: `gemma4:12b` or `gemma4:26b` (estimates, untested). Details for every memory size: [Which model on which Mac](../README.md#which-model-on-which-mac).

---

## 3. Install Safari Assistant

```bash
git clone https://github.com/DarkPirateGo/safari-assistant.git && cd safari-assistant
./deploy.sh
./build-app.sh
```

### `deploy.sh`

1. **Map libraries.** Downloads Leaflet, Leaflet.markercluster and MapLibre GL JS into `vendor/` only if they are missing, from unpkg.com, and checks each file against its SHA-256 pin.
2. **Tests.** Runs `node test-app.js` if Node is installed. A failing test stops the deploy. `DEPLOY_OHNE_TESTS=1 ./deploy.sh` skips the tests.
3. **Downgrade guard.** Compares the version markers of the three pages and of `i18n.js` with those in the app bundle and asks before it installs an older file.
4. **Copy.** Copies the app files into an existing `Safari Assistant.app` if it finds one. Besides the server and the three pages, these include the help page (`hilfe.py` and the guide `README.md`, `README.de.md`, `README.fr.md`, `README.es.md`) and the interface translations (`i18n.js`, `i18n/en.js`, `i18n/fr.js`, `i18n/es.js`). It also copies the launcher, `vendor/` and `data/`. Without a bundle it says so; run `./build-app.sh`.
5. **Git.** Commits only if `DEPLOY_COMMIT=1` is set or a `.deploy-commit` marker file exists. That is for the maintainer; never use it in a public clone or fork.

### `build-app.sh`

Creates `~/Desktop/Safari Assistant.app`: the launcher, `Info.plist`, and in `Contents/Resources/safari-assistant/` the server, the three pages, `hilfe.py` with the four README files, `i18n.js` with `i18n/`, `data/` and `vendor/` (copied by `deploy.sh`).

Running it again updates the bundle in place. It never deletes your data inside the bundle: uploaded documents (`docs/`), `rag-store.json`, `karte.mbtiles`, `fonts/` and `data/warnzonen.geojson`.

The app is built on your Mac and is not signed. If macOS refuses to open it the first time, right-click it and choose Open.

### Updating

```bash
git pull && ./deploy.sh
```

Then quit and restart Safari Assistant. Running `./build-app.sh` again is safe too.

### Without an app bundle

```bash
python3 server.py            # default port 8765; python3 server.py 8766 for another port
```

Open `http://localhost:8765`. Ollama must already be running. The server then uses the project folder for its data (map, documents, generated files). `--lan` starts with iPhone mode already on; it is for development only.

---

## 4. First start

Double-click `Safari Assistant.app`. The launcher:

1. starts `ollama serve` with `OLLAMA_NO_CLOUD=1` if Ollama is not already running,
2. starts `server.py` with the `python3` it finds (from Finder: `/usr/bin/python3`),
3. waits until the server answers, then opens `http://localhost:8765/index.html` in your default browser.

If an older Safari Assistant server still holds port 8765, the new one takes it over. If other software holds it, the server uses the next free port and the launcher opens that one. If the server does not come up at all, an alert **"Safari Assistant startet nicht"** ("Safari Assistant does not start") appears. The launcher's alerts are always in German.

**Logs** are in `~/Library/Logs/Safari Assistant/`: `server.log`, `ollama.log`, `kiwix.log`. The first lines of `server.log` show the port, the folder the server uses, the Python it runs under, whether PyMuPDF was found and whether offline Wikipedia runs.

In the app, check ⚙️ Settings → **Test connection** → Test. A banner at the top says when Ollama is not running or a model is missing, with the command that fixes it.

**Interface language:** English, German, French or Spanish. On the Mac: the language buttons under the app name in the sidebar, or ⚙️ Settings → **Interface language**. On the iPhone: ⚙️ Setup → **Interface language**. On the map page: the language menu in the header. The **?** on every page opens the guide (README) in that language, offline, served by Safari Assistant itself at `/hilfe`.

**Quitting:** ⏻ **Quit** at the bottom of the sidebar stops the server, offline Wikipedia and the Ollama that the launcher started.

Your chats, settings and emergency card live in the browser's storage **for this address**. `http://localhost:8765` and `http://localhost:8766` are different addresses with different storage. Keep using the same one.

---

## 5. iPhone mode

You need the Mac and the iPhone in the same Wi-Fi: your own router or a phone hotspot. Internet access is not needed.

### Switch it on

⚙️ Settings → **📱 iPhone Mode** → **Turn on**. The server opens a second listener on the Mac's Wi-Fi address, on the same port, over HTTPS. Settings then show:

- the address `https://<your-mac>.local:8765/go/<code>` and a QR code with the same address,
- an address with the IP (for example `https://192.168.1.23:8765/go/<code>`), only if the certificate covers it,
- the encryption state, the certificate's validity and fingerprint, and the constraint level of the local CA,
- the time until the automatic switch-off.

### Once per iPhone: trust the local CA

1. In Settings, click **Show in Finder** next to the certificate file (`~/.safari-assistant-tls/safari-assistent-ca.crt`). Send it to the iPhone with AirDrop.
2. iPhone: Settings → **Profile Downloaded** → Install.
3. iPhone: Settings → General → About → **Certificate Trust Settings** → turn on **"Safari Assistant lokale CA"** (older installs: "DARK lokale CA" or "Safari Assistent lokale CA").

Step 3 is the one people forget. Without it the certificate error stays. What trusting the CA means, and how to remove it: [SECURITY.md](../SECURITY.md#the-local-certificate-authority).

### Pair the phone

1. Scan the QR code with the iPhone camera, or type the address into Safari. It stores the access code and forwards to the phone view.
2. Share → **Add to Home Screen**. The access code is part of the saved address.

On the phone: the chat modules, ⚙️ **Setup** (API key, Ollama model, light or dark theme), the 🚨 emergency sheet and 📍 the map. Offline Wikipedia opens through the same address under `/wiki`. GPS works on the phone because the page runs over HTTPS.

### Good to know

- iPhone mode is always off after a start. It switches itself off after 12 hours without requests from the phone (`SAFARI_LAN_INAKTIV_H`) and when Safari Assistant quits.
- **Never switch it on in a Wi-Fi you do not trust.**
- **Renew access code** in Settings creates a new access code. Every phone must then open the new address.
- When the Mac changes networks, the `.local` address stays the same. The server follows the new Wi-Fi address, and the server certificate is re-issued automatically; the CA on the phone stays valid.
- The Mac's network name appears in the address and in the certificate. Give the Mac a neutral name before you pair: System Settings → General → Sharing → Local hostname.
- Uploading, deleting, shutting down and switching the mode work only on the Mac.

---

## 6. Offline map

The map is **built** from OpenStreetMap data with [Planetiler](https://github.com/onthegomap/planetiler). The result, `karte.mbtiles`, is rendered by MapLibre in the browser, labels included, without internet.

```bash
./setup-offline-karte.sh
```

1. Checks for Java (21 or newer).
2. Downloads `planetiler.jar` from GitHub.
3. Builds `karte.mbtiles` for Africa. Planetiler downloads the Geofabrik Africa extract plus ocean polygons and Natural Earth data. This runs for **several hours**.
4. Downloads the Noto Sans glyphs for map labels into `fonts/`.
5. Copies the map and `fonts/` into your `Safari Assistant.app` if it finds one.

- **Disk:** about 80 GB free during the build; the final map is about 8 GB. After step 5 the map exists twice, in the project folder and in the app. Keep one copy as a backup, ideally on another drive: without internet you cannot rebuild it.
- **RAM:** the script sets the Java heap to half of the Mac's RAM (4–12 GB).
- **Another region:** change `--area=africa` to another [Geofabrik region](https://download.geofabrik.de/). Note that Safari Assistant's content (countries, warnings, emergency numbers) covers only its 16 countries.

**Check it:** open the map. The 🗺️ **Map** button switches to the offline vector map on its own when `karte.mbtiles` is present. Then switch Wi-Fi off and reload: the map must still render, place names included. If labels are missing, `fonts/` did not arrive; run the script again.

The server uses the first `*.mbtiles` file in its own folder: inside the app bundle, or the project folder if you run `python3 server.py`.

---

## 7. Offline Wikipedia

[Kiwix](https://kiwix.org) packs whole wikis into single `.zim` files. Safari Assistant starts `kiwix-serve` on port 8090 when it finds both the binary and ZIM files, and connects its full-text search to the chat modules.

### The binary

`kiwix-tools` is not in Homebrew. Download the macOS build from [download.kiwix.org/release/kiwix-tools/](https://download.kiwix.org/release/kiwix-tools/), unpack it and put `kiwix-serve` into `~/safari-zim/` (no admin rights needed) or anywhere on your `PATH`. Safari Assistant also looks in `/opt/homebrew/bin/`, `/usr/local/bin/` and the app folder.

If macOS blocks the downloaded binary, remove the quarantine flag: `xattr -d com.apple.quarantine ~/safari-zim/kiwix-serve`.

### The archives

Browse [download.kiwix.org/zim/](https://download.kiwix.org/zim/). File names end in a `YYYY-MM` date that changes; always take the newest from the listing. Sizes range from about 2 GB to about 55 GB. Useful ones:

| Archive | Content |
|---|---|
| `wikipedia/wikipedia_en_medicine_maxi_*.zim` | WikiMed. If you take one archive, take this one |
| `wikivoyage/wikivoyage_en_all_maxi_*.zim` | Travel guides |
| `wikispecies/wikispecies_en_all_maxi_*.zim` | Species reference, pairs with the Nature & Wildlife module |
| `ifixit/ifixit_en_all_*.zim` | Repair guides |
| `wikipedia/wikipedia_en_all_nopic_*.zim` | All of English Wikipedia without images, the largest |

Download with resume, because long downloads drop:

```bash
mkdir -p ~/safari-zim && cd ~/safari-zim
curl -C - -O "https://download.kiwix.org/zim/<folder>/<file>.zim"   # run the same line again to resume
```

### Where to put them

Put the ZIM files into **`~/safari-zim/`**. That folder is outside Desktop and Documents, so macOS privacy protection never blocks the app from reading it. (The server also checks `A_docs/Wiki/` and `Wiki/` in its own folder and two legacy folders; it uses the first folder that contains `*.zim`.)

### Check it

Restart Safari Assistant. `server.log` shows a line starting with `📚 Offline-Wikipedia`. In the app, 📚 **Wikipedia** in the sidebar opens it, and the 📚 toggle in a chat module makes the module search the archives and cite them. On the phone, Wikipedia opens under `/wiki` through the same HTTPS address; if the installed `kiwix-serve` does not support that, the app says so and Wikipedia works only on the Mac.

If nothing starts, `http://localhost:8765/api/kiwix/status` says why.

Safari Assistant starts `kiwix-serve` on `127.0.0.1:8090` only; the phone reaches Wikipedia through Safari Assistant under `/wiki`. Only a kiwix-tools version that rejects `--address` (it exits at once) is started without it, listening on all interfaces; the server log warns about it.

---

## 8. Data files and refresh scripts

Shipped in the repository: `data/orte.json` (place search, GeoNames), `data/parks.geojson` (park boundaries, OpenStreetMap), `data/klima.json` (rain-season layer, NASA POWER) and `POIs/<Country>-osm.json` (points of interest, OpenStreetMap).

Generated on your Mac, never shipped: `data/warnzonen.geojson` and `data/verwaltungsgebiete.geojson` (warned areas and administrative boundaries).

The scripts refresh or regenerate these files. They need internet.

| Script | Source | Output | Notes |
|---|---|---|---|
| `fetch-pois.py` | Overpass API | `POIs/<Country>-osm.json` | One file per country |
| `fetch-parks.py` | Overpass API | `data/parks.geojson` | |
| `fetch-orte.py` | GeoNames dumps | `data/orte.json` | |
| `fetch-klima.py` | NASA POWER | `data/klima.json` | About 1000 requests, 15–40 minutes. Resumes after an interruption |
| `fetch-warnzonen.py` | Overpass API | `data/warnzonen.geojson` | The server runs it automatically (see [What goes online](../README.md#what-goes-online)). `--vorrat` fetches the administrative boundaries of all 16 countries into `data/verwaltungsgebiete.geojson`, so new warning areas can later be drawn without internet |
| `fauna-gbif-check.py` | GBIF | report and CSV | Maintainer tool: checks the curated wildlife data against GBIF records |

Most scripts accept country codes to limit a run, for example `python3 fetch-pois.py NA BW`. `fetch-warnzonen.py` takes the German country names used in the app, for example `python3 fetch-warnzonen.py Kenia Mosambik`. Afterwards run `./deploy.sh` and restart Safari Assistant.

**POIs are not loaded automatically.** Open the map → **+ Import** → choose files from `POIs/`. Each file becomes a layer you can switch on and off. The same tab imports your own GPX, KML and GeoJSON files, for example your own iOverlander export.

Be considerate with Overpass: it is donated infrastructure. Do not run the scripts in a loop.

---

## 9. Your own PDFs

PDF documents need **PyMuPDF** in the Python that runs the server:

```bash
/usr/bin/python3 -m pip install --user pymupdf    # for Safari Assistant.app started from Finder
python3 -m pip install --user pymupdf             # for python3 server.py in a terminal
```

Restart Safari Assistant. If an upload still fails, the error message names the exact interpreter to install into.

Add a PDF in 📄 **Documents**. The Mac's browser sends it to the server, which extracts the text and returns chunks with chapter and page. The browser stores the chunks in its IndexedDB (`safari-docs`); the server keeps no copy of the PDF. For the phone, the browser syncs the chunks to `rag-store.json` in the app folder. Limits: 64 MB and 2,500 pages per PDF.

Good candidates: your vehicle's workshop and owner manuals, a wilderness-medicine handbook, appliance manuals, field guides. Keep them out of Git; manuals are copyrighted.

---

## 10. Files Safari Assistant creates

"App folder" means the folder that holds `server.py`: `Safari Assistant.app/Contents/Resources/safari-assistant/`, or your clone if you run `python3 server.py`.

| Where | What |
|---|---|
| `~/.safari-assistant-zugang` | Access code for iPhone mode (mode 0600) |
| `~/.safari-assistant-tls/` | Local CA and server certificate (folder 0700, private keys 0600) |
| `~/.safari-assistant-reisewarnungen.json` | Cached travel advisories (mode 0600) |
| `~/.safari-assistant-runtime.json` | Port and process ID of the running server (mode 0600) |
| `~/Library/Logs/Safari Assistant/` | `server.log`, `ollama.log`, `kiwix.log` (private permissions) |
| App folder: `rag-store.json` | Document chunks synced for the phone |
| App folder: `docs/<module>/` | Files stored through the document API |
| App folder: `data/warnzonen.geojson`, `data/verwaltungsgebiete.geojson` | Generated warned areas and administrative boundaries |
| App folder: `karte.mbtiles`, `fonts/` | Offline map, if you built it |
| Browser storage for `http://localhost:8765` | Chats, settings, emergency card, API key (`localStorage`, keys `safari-*`); documents and POIs (IndexedDB `safari-docs`, `safari-pois-db`) |
| Safari on the iPhone | The phone's own settings, chats and API key |

The names come from development and stay unchanged on purpose, so that existing installs keep their data. Three internal names keep the spelling of the development name *Safari Assistent* (German spelling), so that existing installs also keep their macOS permissions and the certificate the iPhone trusts: the certificate file `~/.safari-assistant-tls/safari-assistent-ca.crt`, the bundle id `com.safari-assistent.app` and the server signature `safari-assistent` (reported by `/api/ping`).

---

## 11. Environment variables

| Variable | Default | Effect |
|---|---|---|
| `SAFARI_LAN_INAKTIV_H` | 12 | Hours without phone requests before iPhone mode switches itself off (at least 1) |
| `SAFARI_REISEWARN_ALTER_H` | 12 | Age in hours after which the travel advisories are fetched again (at least 1) |
| `SAFARI_OHNE_WARNZONEN_AUTO` | unset | `1` = never fetch warn-zone areas automatically |
| `SAFARI_OHNE_TLS` | unset | `1` = iPhone mode over plain HTTP. Not recommended |
| `SAFARI_TLS_OHNE_CONSTRAINTS` | unset | `1` = create a new CA without name constraints. Not recommended |
| `SAFARI_LAN` | unset | `1` = start with iPhone mode on, like `--lan`. Development only |
| `SAFARI_PARENT_WATCH` | set by the launcher | The server exits when its launcher exits |
| `DARK_LOG_DIR` | `~/Library/Logs/Safari Assistant` | `server.py`: folder for the logs the server writes itself (`kiwix.log`). The launcher always writes `server.log` and `ollama.log` to `~/Library/Logs/Safari Assistant/` |
| `DARK_APP` | unset | `deploy.sh`, `setup-offline-karte.sh`: path of the app bundle to update, tried before the usual places (`Safari Assistant.app` on the Desktop, in `/Applications`, in `~/Applications`, then older installs under a former name). It must contain `Contents/Resources/safari-assistant`. `build-app.sh` sets it when it calls `deploy.sh`; to choose where `build-app.sh` builds, use `APP_DIR` |
| `DEPLOY_OHNE_TESTS` | unset | `deploy.sh`: skip the tests |
| `DEPLOY_COMMIT` | unset | `deploy.sh`: commit after deploying. Maintainer only |
| `DEPLOY_LIZENZEN` | unset | `deploy.sh`: `1` = when online, replace each licence file in `vendor/` that still holds the standard text (header line `STANDARD-TEXT-MARKER`) with the original file from the library's GitHub tag, as in the maintainer's folder (`.deploy-commit`). This changes tracked files |

For `python3 server.py`, set them in the same shell, for example `SAFARI_OHNE_WARNZONEN_AUTO=1 python3 server.py`. For `Safari Assistant.app` started from Finder, set them with `launchctl setenv NAME value` and restart Safari Assistant. `DARK_APP` and `DARK_LOG_DIR` keep the name the app carried briefly before the first release.

---

## 12. Uninstall and reset

1. Quit Safari Assistant.
2. Delete `~/Desktop/Safari Assistant.app`. It contains the offline map, synced documents and generated files; keep a copy of `karte.mbtiles` if you want it.
3. Delete `~/.safari-assistant-zugang`, `~/.safari-assistant-tls/`, `~/.safari-assistant-reisewarnungen.json`, `~/.safari-assistant-runtime.json` and `~/Library/Logs/Safari Assistant/`.
4. In the browser, delete the site data for `localhost:8765`. This removes chats, settings, the emergency card and the API key.
5. On each iPhone: delete the home-screen icon, the website data for `<your-mac>.local`, and the CA profile (Settings → General → VPN & Device Management → Delete Profile).
6. Optional: `ollama rm qwen3.6:35b-a3b gemma4:e4b`, delete `~/safari-zim/`.

Make a backup first (⚙️ Settings → **Backup & Restore** → **⬇ Export**) if you want to keep your data.

---

## 13. Pre-departure checklist

Do this **with Wi-Fi switched off**, at home, at least two weeks before you leave.

- [ ] `ollama list` shows every model the modules use (⚙️ Settings → Model per module)
- [ ] Every offline module answers one real question, without errors
- [ ] Map: the offline vector map renders **with labels**
- [ ] 🌧️ rain layer and timeline show data
- [ ] Offline place search finds a town in each country on your route
- [ ] POI files are imported and markers cluster at low zoom
- [ ] 📚 opens Wikipedia, and a module with the 📚 toggle cites it
- [ ] iPhone mode on: the phone opens the **HTTPS** address without a certificate warning and gets an answer; iPhone mode off: the phone gets no answer
- [ ] GPS works on the phone; the 🚨 sheet shows your position and the right country
- [ ] Emergency card: numbers, currency and sun times for your countries; your own fields filled in
- [ ] Travel advisories were fetched recently (date shown in 🛑 Travel Advisories)
- [ ] Your PDFs are indexed and cited
- [ ] `node test-app.js` passes
- [ ] Everything still works after a full restart of the Mac
- [ ] A backup of the app data exists, and a copy of `karte.mbtiles` and the ZIM files sits on a second drive

---

## Troubleshooting

**Alert "Safari Assistant startet nicht" ("Safari Assistant does not start")**
Read `~/Library/Logs/Safari Assistant/server.log`. If `server.py` is missing in the bundle, run `./build-app.sh` in the project folder.

**Modules answer nothing, or "model not found"**
`curl http://localhost:11434` must answer `Ollama is running`. If it does, compare `ollama list` with the models in ⚙️ Settings → Model per module. Pull the missing model or set **Global Model**.

**Answers are very slow**
The model may not fit in memory. `ollama ps` shows what is loaded. Close other large apps or use the [light profile](#light-profile-816-gb-ram).

**Chats or settings seem gone**
Browser storage belongs to one address. If Safari Assistant opened on another port (`localhost:8766`), another program held 8765. Find it with `lsof -iTCP:8765 -sTCP:LISTEN -n -P`, quit it and restart Safari Assistant.

**Phone: "iPhone Mode is off"** (the server's own reply is German: "iPhone-Modus ist aus")
Switch it on on the Mac. It is off after every start and after 12 hours without phone requests.

**Phone: "Access code missing or wrong"** (the server's own reply is German: "Zugangscode fehlt oder ist falsch")
Open the full address with `/go/<code>` from Settings, not just `/mobile.html`. After **Renew access code**, every phone needs the new address.

**Phone: certificate error or "This connection is not private"**
The CA profile is missing on the phone, or step 3 (Certificate Trust Settings) was skipped. See [section 5](#once-per-iphone-trust-the-local-ca).

**Phone: "… the request was for an HTTP URL with HTTPS-Only enabled"** (German iPhone: "… HTTP-URL bei aktiviertem HTTPS-Only-Modus")
An old `http://` address, for example an old home-screen icon. Take the current address from Settings and add the icon again.

**Phone: the name is not found**
Use the IP address shown below it in Settings. It works without Bonjour.

**Phone: the page does not load at all**
Same Wi-Fi? The macOS firewall may ask to allow incoming connections for Python. With iPhone mode on, `lsof -iTCP:8765 -sTCP:LISTEN -n -P` shows two lines: `127.0.0.1:8765` and the Wi-Fi address.

**Map: "Map library (Leaflet) not loaded"**
Files in `vendor/` are missing. Run `./deploy.sh` once with internet, then restart Safari Assistant.

**Map is black, or labels are missing**
`fonts/` is missing or the server was not restarted after the map build. Run `./setup-offline-karte.sh` again and restart Safari Assistant.

**Rain layer says the climate data is missing**
`data/klima.json` is missing: `python3 fetch-klima.py` with internet, then `./deploy.sh` and restart.

**Travel advisories are empty**
They need internet once. Open 🛑 Travel Advisories and click **Fetch now**; the panel shows each source's status.

**Wikipedia does not start**
Open `http://localhost:8765/api/kiwix/status`. Usually the `kiwix-serve` binary is missing, not executable (`chmod +x`), quarantined (see [section 7](#the-binary)), or the ZIM files are in a folder the server does not check. Moving them to `~/safari-zim/` fixes the macOS permission case.

**PDF import fails**
PyMuPDF is missing in the Python that runs the server. The error message names that Python; install PyMuPDF for it ([section 9](#9-your-own-pdfs)).

Still stuck? Open an [issue](https://github.com/DarkPirateGo/safari-assistant/issues) with the relevant part of `server.log` and what the browser shows. Remove your user paths, host name, IP addresses, access code, position and API key first.
