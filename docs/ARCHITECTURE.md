# Architecture

The guiding constraint: **everything must work with the network switched off, and must be repairable by one person with a text editor.** That rule explains most of the decisions below.

---

## Overview

```
┌──────────────────────────────────────────────────────────────────┐
│ Browser                                                          │
│   index.html   desktop: 14 chat modules, tools, emergency card   │
│   mobile.html  phone:   same modules, emergency sheet, touch UI  │
│   pois.html    map:     POIs, routes, overlays, rain layer       │
│   State: localStorage (safari-*) · IndexedDB (safari-docs,       │
│          safari-pois-db)                                         │
└──────────────┬──────────────────────────────┬────────────────────┘
               │ http://localhost:8765         │ https://<your-mac>.local:8765
               │ (Mac)                         │ (iPhone mode, access code)
┌──────────────▼──────────────────────────────▼────────────────────┐
│ server.py — ThreadingHTTPServer                                  │
│   loopback listener 127.0.0.1:8765 (always)                      │
│   TLS listener on the Wi-Fi address, same port (iPhone mode)     │
│   static allowlist · /api/* · proxies /api/ollama/* and /wiki    │
└───┬───────────┬────────────┬─────────────┬─────────────┬─────────┘
    ▼           ▼            ▼             ▼             ▼
  Ollama     kiwix-serve   karte.mbtiles  travel-advice  fetch-warnzonen.py
  127.0.0.1  :8090         (SQLite)       sources        (Overpass)
  :11434                                  (HTTPS)

Browser → api.anthropic.com   online modules only, with your API key
Browser → OSM tiles, Nominatim, Open-Meteo, open.er-api.com   see README "What goes online"
```

## Files

| File | Role |
|---|---|
| `index.html` | Desktop app: modules, settings, emergency card, tools |
| `mobile.html` | Phone app; shares much code byte-identical with `index.html` |
| `pois.html` | Map for desktop and phone |
| `i18n.js`, `i18n/en.js`, `i18n/fr.js`, `i18n/es.js` | Runtime translation of the German interface into English, French and Spanish ([Interface languages](#interface-languages)) |
| `README.md`, `README.de.md`, `README.fr.md`, `README.es.md` | The guide in four languages; served offline under `/hilfe` |
| `hilfe.py` | Renders the guide as the page `/hilfe` (Markdown renderer without dependencies, English fallback); `server.py` loads it |
| `server.py` | Local server: static files, API, proxies, TLS, travel advisories |
| `rag.py` | Standalone PDF extraction and chunking helper; `server.py` carries its own implementation |
| `launcher_new.sh` | Launcher inside the app bundle |
| `build-app.sh`, `deploy.sh` | Build the app bundle; test and copy files into it |
| `setup-offline-karte.sh` | Builds the offline map |
| `fetch-*.py`, `fauna-gbif-check.py` | Create or check the data files |
| `generate_icon.py` | Draws the app icon: `icon.png` and `icon.iconset/` (for `icon.icns`), with `--docs docs/img/logo` also the icon SVG and PNGs there. Needs Pillow |
| `test-app.js`, `test-*.py` | Test suite |
| `features-manifest.json` | Marker strings for every feature; checked by the tests |
| `tools/privacy_gate.py`, `tools/test_privacy_gate.py`, `tools/private-terms.example.txt`, `.githooks/` | Privacy gate, its self-test and an example term list ([PRIVACY-GATE.md](PRIVACY-GATE.md)) |
| `tools/validate_osm_exports.py` | Checks `POIs/*-osm.json`: only genuine OSM objects, allowed tags, inside the country's bounding box. Run by the tests and in CI |
| `data/`, `POIs/`, `vendor/` | Shipped data and libraries |
| `docs/index.html`, `docs/img/` | GitHub Pages website (`docs/index.html`, served from `docs/`; `docs/.nojekyll` makes Pages publish the folder as it is) with its images (`docs/img/`: screenshots, logo and icon, also used by the READMEs) |

---

## Why no build step

There is no bundler, no framework, no `node_modules` at runtime. Three HTML files carry their own CSS and JavaScript inline, roughly 0.7 MB together. The translation layer (`i18n.js` and the dictionaries in `i18n/`) is plain JavaScript as well and needs no build step either.

This is deliberate. A build toolchain depends on npm, on a working network and on a laptop whose cache is intact. Far from anywhere, being able to open `index.html` in a text editor, change a line and reload is worth more than the comfort of a framework.

The cost is real: three large files are hard to navigate, and code is duplicated between `index.html` and `mobile.html`. The test suite compensates by asserting that shared blocks stay **byte-identical** in both files.

---

## Frontend

### Modules

`index.html` and `mobile.html` define the same `MODULES` object, byte-identical. Each entry is self-contained:

```js
mechanik: {
  icon: '🔧',
  label: 'Mechanik — HZJ78',
  model: 'qwen3.6:35b-a3b',        // which model answers
  modelLabel: 'Qwen 3.6 35B-A3B',  // shown in the UI
  modelReason: '...',              // why this model
  placeholder: '...',
  hint: '...',
  quick: ['...'],                  // one-tap starter questions
  system: `You are a ...`          // the system prompt
}
```

The UI, the history, the model selector and many tests derive from this object.

### Prompts

System prompts are written in English, because models follow English instructions more reliably. A request is built from:

1. the module's `system` prompt,
2. shared rules (`PROMPT_GRUNDREGELN`: admit uncertainty, no invented numbers, length),
3. the answer language from the 🌐 row (saved; it follows the interface language),
4. for Notfall, Medizin and Hund: the emergency numbers of the current country,
5. for Sicherheitslage, Navigation and Notfall: the official travel-advice text of the current country,
6. excerpts from your documents or offline Wikipedia, with source markers neutralised and a guard sentence that the excerpts are reference material, not instructions.

The online modules add web search and, if stored, your position rounded to three decimals (about 100 m). The Wetter module on the Mac uses the same online path when an API key is stored and falls back to the local model when the network fails.

### Interface languages

The pages are written in German, and German stays the source. `i18n.js` translates the interface at runtime into English, French or Spanish without touching the pages: when a page loads and whenever it changes, text nodes and the attributes `title`, `placeholder`, `aria-label` and `alt` are looked up in the dictionary of the chosen language (`i18n/en.js`, `i18n/fr.js`, `i18n/es.js`). Keys are the exact German strings, values the translations; `{0}`, `{1}` … stand for values such as numbers or names. A string without an entry stays German.

Chat messages, text you type and anything marked `data-i18n-skip` are never translated. System prompts never pass through `i18n.js`; the answer language comes from the 🌐 row and follows the interface language. The language is chosen with the switcher on the Mac, iPhone and map pages and saved. The **?** icon on every page opens the guide in the same language from `/hilfe`. How to add or fix a translation: [CONTRIBUTING.md](../CONTRIBUTING.md#translations).

### State

- **`localStorage`** (keys `safari-*`): chat histories, settings, the emergency card, checklists, logbook, deadlines, notes, saved answers, cached exchange rates, the answer language, the interface language, the API key. Each key is loaded through a validator; a corrupt value is backed up, reset and reported instead of breaking the app.
- **IndexedDB**: `safari-docs` (document chunks), `safari-pois-db` (imported POIs, layers and routes).
- **Backups** export the `localStorage` keys and the documents as one JSON file, without the API key and the stored GPS position (chats may still mention positions). The import accepts only known keys and validates their values with typed validators.

All three pages share one origin (`localhost:8765` on the Mac, `<your-mac>.local:8765` on the phone), so they share this storage.

### Streaming and cancellation

Answers stream token by token. Each module has its own `AbortController`, so switching modules does not cancel an answer. Cancelling keeps the partial answer and marks it as cancelled.

---

## Backend — `server.py`

One file, Python standard library only; PyMuPDF is optional. `ThreadingHTTPServer`, so a long model answer does not block map tiles.

### Endpoints

"Mac only" means loopback plus the origin check described under [Security layers](#security-layers). Everything else is also available to a phone with the access code while iPhone mode is on.

| Endpoint | Who | Does |
|---|---|---|
| `GET /api/ping` | Mac; phone without code | App signature, version and port. On loopback also process ID, uptime, folder and iPhone-mode status. Used by the launcher and Settings |
| `GET /go/<code>` | phone | Checks the code, sets the cookie, redirects to `/mobile.html?t=<code>` |
| `GET /api/netz/status` | Mac only | iPhone-mode status: addresses, TLS, CA constraint level, time to switch-off |
| `POST /api/netz/an`, `/api/netz/aus`, `/api/netz/neuer-code` | Mac only | iPhone mode on or off; new access code |
| `POST /api/tls/zeigen` | Mac only | Shows the CA file in Finder, for AirDrop |
| `GET /api/reisewarnungen` | Mac, phone | Cached travel advisories, fetch status, warn-zone status |
| `POST /api/reisewarnungen/aktualisieren` | Mac only | Starts a fetch in the background |
| `GET /api/ollama/api/tags`, `POST /api/ollama/api/chat` | Mac, phone | Fixed proxy to Ollama on `127.0.0.1:11434`; field allowlist, clamped options, streamed |
| `GET /wiki/…` | Mac, phone | Proxy to `kiwix-serve` on `127.0.0.1:8090` |
| `GET /hilfe` | Mac, phone | The guide (README) in the interface language, offline; opened by the **?** icon on every page |
| `GET /api/kiwix/status` | Mac, phone | Whether `kiwix-serve` runs, with which archives, and if not, why |
| `GET /api/wiki/search` | Mac, phone | Turns the question into English search terms (small local model), searches Kiwix, returns excerpts |
| `GET /api/orte/search` | Mac, phone | Offline place search in `data/orte.json` |
| `GET /api/tiles/status` | Mac, phone | Whether an offline map exists, vector or raster, zoom range |
| `GET /api/tiles/style.json` | Mac, phone | MapLibre style for the offline vector map |
| `GET /api/tiles/{z}/{x}/{y}` | Mac, phone | One tile from `karte.mbtiles` (SQLite); coordinates bounded |
| `GET /fonts/<fontstack>/<range>.pbf` | Mac, phone | Map glyphs from `fonts/`; redirects to fonts.openmaptiles.org if the file is missing |
| `POST /api/extract-pdf` | Mac only | PDF → text chunks with chapter and page (PyMuPDF); keeps no copy |
| `POST /api/rag/sync` | Mac only | Stores the browser's document chunks in `rag-store.json` for the phone |
| `GET /api/rag/status`, `POST /api/rag/search` | Mac, phone | Status of and search in `rag-store.json` |
| `GET /api/docs/list`, `/api/docs/text`, `/api/docs/search` | Mac, phone | Files in `docs/<module>/` |
| `POST /api/docs/upload`, `DELETE /api/docs/delete` | Mac only | Store or delete files in `docs/<module>/` (through `safe_docs_path()`). The current pages index PDFs through `/api/extract-pdf` instead |
| `POST /api/shutdown` | Mac only | Stops `kiwix-serve`, closes iPhone mode, exits, and ends the launcher |
| static files | Mac, phone | `/`, the three pages, their images and data files, `/vendor/`, `/fonts/` |

### Server-side storage

Most user data lives in the browser, but the server stores some data itself. "App folder" is the folder that holds `server.py` (inside the bundle: `Contents/Resources/safari-assistant/`).

| Where | What |
|---|---|
| App folder: `docs/<module>/` | Files stored through the document API |
| App folder: `rag-store.json` | Document chunks synced for the phone |
| App folder: `data/warnzonen.geojson`, `data/verwaltungsgebiete.geojson` | Generated warned areas and administrative boundaries |
| App folder: `karte.mbtiles`, `fonts/` | Offline map |
| `~/.safari-assistant-zugang` | Access code (0600) |
| `~/.safari-assistant-tls/` | Local CA and server certificate (0700 / 0600) |
| `~/.safari-assistant-reisewarnungen.json` | Travel-advisory cache (0600) |
| `~/.safari-assistant-runtime.json` | Port and process ID, for taking over an old instance (0600) |
| `~/Library/Logs/Safari Assistant/` | Logs, private permissions |

User data inside the app bundle is a known weakness; moving it out is on the [roadmap](ROADMAP.md).

### Background work

- **Parent watch.** With `SAFARI_PARENT_WATCH=1`, set by the launcher, the server exits when the launcher exits. A force-quit leaves no orphaned server.
- **Instance takeover.** If port 8765 is busy, the server asks the holder via `/api/ping` and the runtime file. An old Safari Assistant instance is terminated and the port taken over; other software is left alone and the server moves to the next free port.
- **Network watch.** Follows changes of the Wi-Fi address while iPhone mode is on and switches the mode off after `SAFARI_LAN_INAKTIV_H` hours (default 12) without phone requests.
- **Travel advisories.** Starts 20 s after launch and fetches whenever the cache is older than `SAFARI_REISEWARN_ALTER_H` hours (default 12), retrying every 15 minutes.
- **Sub-processes.** `kiwix-serve` (child process, stopped on exit), `fetch-warnzonen.py` (background, at most every 6 hours), `openssl` (certificates) and `open -R` (Finder). All are called with argument lists, never through a shell.

### Travel advisories and warned areas

Only official sources:

- **Auswärtiges Amt** open data: the level comes from the official flags (`warning`, `partialWarning`, `situationWarning`, `situationPartWarning`), not from reading the text. Details are loaded only for countries whose timestamp changed.
- **UK FCDO** content API (`alert_status`).
- **US Department of State** RSS feed. It lists only recently changed countries, so it supplements the others and never stands alone.

Texts are stored verbatim with date, source and link, shown escaped and readable offline. Each source reports its own status; if one fails, the last good state stays and is marked as such.

For the map, the server splits the Foreign Office warning text into sections per level and matches the area names against real administrative areas from OpenStreetMap (admin levels 4 and 6). Exceptions are honoured, a district beats its province, partial areas are marked, and names that cannot be matched are reported rather than guessed. `fetch-warnzonen.py` fetches the names first and then geometry only for the named areas. The result, `data/warnzonen.geojson`, is also used to tell you whether your position lies inside a warned area.

### TLS listener

- Created per iPhone-mode session on the Mac's Wi-Fi address, same port as the loopback listener. Minimum TLS 1.2. The handshake runs in a worker thread, not in the accept loop, and each client has a connection limit.
- Server certificate following Apple's rules for iOS: subject alternative names, at most 825 days, SHA-256, RSA-2048, `serverAuth`. Re-issued when the addresses change or expiry is near.
- Local CA with name constraints (`.local`, `localhost`, private address ranges; host names only if the Mac cannot verify IP constraints). Never unconstrained unless `SAFARI_TLS_OHNE_CONSTRAINTS=1`. See [SECURITY.md](../SECURITY.md#the-local-certificate-authority).
- The loopback listener stays plain HTTP on purpose: `localhost` is a secure context in browsers, and only the Mac can reach it.
- Without `openssl`, with `SAFARI_OHNE_TLS=1`, or after a fallback bind to `0.0.0.0` (broken loopback interface), iPhone mode runs over plain HTTP and Settings says so.

### Security layers

1. **Host check** on every request (DNS rebinding): `421` if the `Host` header names any other server.
2. **Access gate**: loopback is free; network requests need iPhone mode and the access code (cookie, `?t=`, or `X-Safari-Zugang` header), compared in constant time.
3. **Mutation gate** for everything that writes, deletes, exits or switches: loopback only, and an `Origin`, if sent, must match this server's own host and port.
4. **CORS** only for this server's own origins.
5. **Static allowlist** with a resolved-path check; no directory listings. Document paths only through `safe_docs_path()`.
6. **Limits**: request body sizes, per-connection timeout, thread cap, PDF page and character limits, bounded tile coordinates.
7. **Headers** on every response: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a Content-Security-Policy with `frame-ancestors`, `object-src` and `base-uri`.
8. **Frontend**: every stored or fetched value is escaped at render time; links are limited to `http(s)`; `noopener` on new windows; model output is escaped before markdown formatting.

This is still a localhost and home-Wi-Fi tool. Do not expose it to the internet.

---

## Map — `pois.html`

- **Online:** OpenStreetMap raster tiles through Leaflet.
- **Offline vector:** MapLibre GL reads `karte.mbtiles` through `/api/tiles`, with Noto Sans glyphs from `fonts/`. The map starts with Leaflet and switches to the offline map as soon as `/api/tiles/status` reports one.

Every layer renders in both modes; the tests assert this. Layers: POIs (clustered), imported GPX, KML and GeoJSON, routes, park boundaries, hazard zones, travel-warning areas, and the rain layer. The rain layer colours a 1° grid by the typical monthly rainfall for the date on the timeline, from `data/klima.json` (NASA POWER climatology 2001–2020).

Search runs offline over `data/orte.json` while you type; Enter adds an online street search through Nominatim. The ℹ️ weather panel shows the climatology for your position and, on request, a 7-day forecast from Open-Meteo, cached for offline use.

---

## Launcher and app bundle

```
Safari Assistant.app/Contents/
  Info.plist                      bundle id com.safari-assistent.app
  MacOS/                          the launcher (launcher_new.sh)
  Resources/safari-assistant/     server.py, pages, data/, vendor/
                                  plus your data: docs/, rag-store.json, karte.mbtiles, fonts/
```

The launcher starts Ollama only if it is not running (then with `OLLAMA_NO_CLOUD=1`), starts `server.py` with `SAFARI_PARENT_WATCH=1`, waits for `/api/ping`, and opens the browser on the port the server actually uses. If the server is missing or does not come up, it shows the alert "Safari Assistant startet nicht" instead of falling back to anything else. Logs go to `~/Library/Logs/Safari Assistant/`.

The internal folder name `safari-assistant`, the bundle id and all other internal identifiers stay unchanged so that no data is lost. The bundle id `com.safari-assistent.app`, the certificate file `safari-assistent-ca.crt` and the server signature `safari-assistent` keep the development spelling "assistent", so that existing installs also keep their macOS permissions and the certificate the iPhone trusts.

---

## Testing

`test-app.js`: plain Node, no dependencies. It reads the HTML, Python and shell files as **text** and asserts structural properties:

- a specific bug fix is still present,
- shared blocks are byte-identical in `index.html` and `mobile.html`,
- every module has a system prompt that starts with a role,
- every country has a currency, a malaria classification and a season entry,
- every entry in `features-manifest.json` is still present,
- `deploy.sh` still copies the files it must copy, and the launcher still does what it must.

Some sections extract functions and run them, and some run Python: `test-reisewarnungen.py`, `test-tls.py` (real certificates and a real TLS handshake in a throw-away folder), `test-warngebiete.py`, `test-sicherheit.py` (security checks against a real server), `test-hilfe.py` (the `/hilfe` renderer and route against a real server), the privacy-gate self-test `tools/test_privacy_gate.py` and the OSM data validator `tools/validate_osm_exports.py`.

This style fits a codebase without a module system: it catches the failure that actually happens here, a fix applied to the desktop file and forgotten in the phone file. Every fixed bug gets a test.

---

## Deployment

`deploy.sh`:

1. Fetches missing files into `vendor/` and checks their SHA-256 pins.
2. Runs the test suite if Node is installed (`DEPLOY_OHNE_TESTS=1` skips it). Any failure stops the deploy.
3. Downgrade guard: compares the version markers (first lines) of the three pages and `i18n.js` with those in the bundle.
4. Copies the app files, the launcher, `vendor/` and `data/` into an existing `Safari Assistant.app`.
5. Git commit only with `DEPLOY_COMMIT=1` or a `.deploy-commit` marker (maintainer only).

`build-app.sh` creates or updates `~/Desktop/Safari Assistant.app` in place and never deletes user data inside it.

---

## Known weaknesses

The best places to contribute:

- **Large files with duplicated code.** Byte-identity tests catch drift but do not remove the duplication.
- **Hard-coded region.** Countries, malaria zones, seasons, currencies and border rules are spread through the code instead of one configuration file.
- **Translations keyed by German text.** `i18n.js` looks up the exact German string; when a German string changes and its key in `i18n/` does not, that text falls back to German.
- **One traveller profile, one vehicle.** Prompts, maintenance plan and checklists assume them.
- **macOS only in practice.** `server.py` is portable Python; launcher and packaging are not.
- **User data inside the app bundle.**
- **No `script-src` in the Content-Security-Policy**, because the pages still use inline event handlers.
- **`kiwix-serve`** is bound to `127.0.0.1`; only kiwix-tools versions without `--address` fall back to all interfaces (warning in the log).
