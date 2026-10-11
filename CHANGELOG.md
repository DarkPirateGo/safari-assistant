# Changelog

All notable changes to Safari Assistant are documented here. Each page also carries an internal version marker on line 2 (`vYYYY-MM-DD-N`).

## 2026.10 — first public release (October 2026)

Safari Assistant is an offline AI field assistant for overland travel in southern and eastern Africa, created by DARK. It runs on a Mac with Apple Silicon and opens in your browser; an iPhone can join over your own Wi-Fi. This is the first public release.

### What's in it

- **14 chat modules**, each with its own system prompt, history and model: Mechanics, Nature & Wildlife, Medicine & First Aid, Navigation & Terrain, Dog, Survival & Orientation, Wildlife Photography, Languages, Emergency Chat, Weather & Rainy Seasons, Camp Kitchen and Fitness run on local models through Ollama (default `qwen3.6:35b-a3b`, `gemma4:e4b` for the light modules). Security Situation and Claude are optional online modules that need your own Anthropic API key.
- **Your own manuals:** upload PDFs, such as a workshop manual, a first-aid book or a travel guide, and assign them to a module. The module searches them offline and cites document, chapter and page. Needs PyMuPDF.
- **Photos:** attach a photo of a sign, a part, a plant or an animal and ask about it. With the local modules, the model looks at it on your Mac and nothing is uploaded.
- **Pick the model that fits your Mac:** one setting switches every local module to another model, and the README has a guide to [which model on which Mac](README.md#which-model-on-which-mac). Only 36 GB is measured; other sizes are estimates.
- **Offline map:** vector map from your own `karte.mbtiles` or online OpenStreetMap tiles; a rain-season layer with a day-by-day timeline and the malaria season per month (NASA POWER climatology, 2001–2020, not a forecast); a weather panel with an optional 7-day forecast (Open-Meteo); hazard zones; national park boundaries; offline place search.
- **About 90,000 places** from OpenStreetMap ship with the app, one file per country, imported once: campsites, fuel, water, workshops, hospitals, vets and border posts. Your own GPX, KML and GeoJSON files can be imported too.
- **Official travel advisories** from the German Federal Foreign Office, the UK FCDO and the US Department of State: fetched automatically whenever the Mac is online, readable offline with date and source link. Warned districts are drawn as areas on the map and checked against your position.
- **Emergency Card that works without AI:** emergency and German embassy numbers per country, your position as decimal degrees, degrees/minutes/seconds and Plus Code for radio or satellite messenger, 8 first-aid protocols as fixed text, personal fields, exchange rate, sun times and document deadlines.
- **Trip tools:** checklists, document deadlines, a maintenance plan, a logbook, notes, saved answers, chat history and backups.
- **iPhone view** over your own Wi-Fi: the same modules, an emergency sheet and the map, through the Mac over HTTPS with a local certificate authority and an access code. Pairing by QR code; iPhone mode switches itself off after 12 hours without phone requests.
- **Four languages:** the interface in English, German, French and Spanish; AI answers follow the interface language. A **?** on every page opens the guide in that language, offline.
- **Offline Wikipedia** (optional) via `kiwix-serve`, also from the iPhone.

Offline, nothing leaves the Mac. Everything Safari Assistant sends when it is online is listed in the README under [What goes online](README.md#what-goes-online). No telemetry, no analytics.

### Security and privacy

Safari Assistant was hardened before this release. In short:

- The server listens on the Mac only (`127.0.0.1`); the iPhone listener exists only while iPhone mode is on, needs the access code and speaks HTTPS.
- The local certificate authority is limited to `.local` names and private network addresses, so its key cannot be used to impersonate other websites. New CAs are valid for 825 days.
- Host and `Origin` checks against DNS rebinding and cross-site requests; strict static-file allowlist; `HEAD` requests refused; security headers and a Content-Security-Policy on every response.
- Imported backups are validated, and imported values are escaped where they are shown.
- Vendored map libraries are pinned by SHA-256. No fonts from Google.
- A privacy gate (`tools/privacy_gate.py`, git hooks and a CI job) keeps personal data, backups, track exports, documents, keys and image metadata out of commits. See [docs/PRIVACY-GATE.md](docs/PRIVACY-GATE.md).

The full list of fixes and the threat model: [SECURITY.md](SECURITY.md#security-fixes-in-202610-first-public-release).

### Install

`./deploy.sh` checks the map libraries in `vendor/` (SHA-256 pins) and runs the tests if Node is installed; `./build-app.sh` creates `~/Desktop/Safari Assistant.app`. Running them again updates the app in place and never deletes your data. Step by step: [Quick start](README.md#quick-start).

### Known limitations

- **Not yet field-tested.** Tested on one Mac (Apple Silicon, 36 GB). Other memory sizes are estimates.
- Answers come from language models and can be confidently wrong. Safari Assistant is not a doctor, a mechanic, a vet or a guide, and it cannot call for help. See [Safety and limitations](README.md#safety-and-limitations).
- The English, French and Spanish first-aid protocols are translations of the German text. They were checked against it, but not yet reviewed by first-aid professionals.
- The system prompts are written for a German-speaking traveller (German embassy numbers, pronunciation for German readers). The Mechanics module and the maintenance plan target one vehicle, the Toyota HZJ78 / 1HZ. Exchange rates use EUR as the base currency.
- iPhone mode needs a one-time step on each iPhone: trust the local certificate authority.
- No switch yet to turn off the automatic travel-advisory and exchange-rate requests; see the [roadmap](docs/ROADMAP.md).

### Licence

Safari Assistant's own code is under the [PolyForm Noncommercial License 1.0.0](LICENSE): free for any non-commercial purpose; commercial use needs a separate licence from DARK. It is source-available, not an OSI-approved open-source licence. The `Required Notice:` line in LICENSE must travel with every copy. Map data, place names, climate data, the bundled libraries and the QR code encoder keep their own licences: [NOTICE.md](NOTICE.md). The names "Safari Assistant" and "DARK" and their logos are not licensed for reuse; forks use their own name and logo.

### A note on names

The app was developed privately as *Safari Assistent* (German spelling) and was called *DARK* for a short time before this release; DARK is now only the creator's name. Some internal identifiers keep those names on purpose, so that existing installs keep their data, their macOS permissions and the certificate the iPhone trusts. The list is in the README under [Development and tests](README.md#development-and-tests).

## Earlier history

The development history before the first public release is not published; this repository starts with 2026.10.
