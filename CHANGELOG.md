# Changelog

All notable changes to Safari Assistant are documented here. Each page also carries an internal version marker on line 2 (`vYYYY-MM-DD-N`).

## 2026.11.1 (November 2026)

An update one week after 2026.11, written while the app is in use on the road in South Africa. Most of it is about getting help where you are: numbers you can call from the 🚨 sheet on the iPhone, news about the places around you, and a faster start of the iPhone page when the Mac is away. Internal versions v2026-11-15-1 to v2026-11-22-1.

### New

- **🛡 Local help here (iPhone 🚨 sheet).** Save numbers you are given on the road (campsite security, a security company a local recommends, a lodge) together with the GPS position and a radius of 2 to 100 km. Whenever you are within that radius again, they appear with a call button, nearest first; otherwise the sheet names the nearest saved entry and its distance. Numbers in national format are allowed and marked as working only with a local SIM. Up to 60 entries, stored only on the iPhone, offline.
- **🚓 Stations and services nearby (iPhone 🚨 sheet).** New script `fetch-notfallkontakte.py` loads police, fire, ranger, security-company, ambulance and sea-rescue stations for all 16 countries from OpenStreetMap into `data/notfallkontakte.json`, which ships with this release (as of 22 November 2026). The sheet lists the nearest ones with a phone number within 100 km (and the nearest police station even without a number), kept on the iPhone for offline use. Only 158 of the 4,353 stations had a phone number, and none of the 295 ranger posts. `--amtlich` additionally saves the official police-station lists of South Africa, Botswana and Malawi for later use.
- **🦏 Parks and rangers (iPhone 🚨 sheet).** 19 numbers of park offices and wildlife authorities in South Africa, Kenya, Uganda, Rwanda, Eswatini, Botswana and Namibia, taken from the operators' own websites, each with its source and the date it was checked (22 November 2026). Inside a park its numbers come first; two older numbers are marked as unconfirmed; for countries without an official number the sheet says so.
- **📍 Near you and 🧭 Summarise the situation here (News, Mac and iPhone).** Items from the last 14 days that mention a place within 250 km of your position come first, with place and distance; places are recognised offline from the bundled place list. The local model can sum them up in at most five points with references — no Claude, no tokens.
- **US embassy alerts as news sources.** The security alerts of the US embassies in all 16 countries (only alerts, not routine notices). 66 built-in sources instead of 50.
- **Travel profile.** Settings → General → Travel profile: who travels, vehicle, route, travel style, dog, in your own words (up to 8,000 characters, with a template). Goes with every question to the local model, to Claude only if you tick it. The iPhone holds it in memory only.
- **📣 Send to all (SOS).** With several channels, one button steps through Messages (all SMS recipients at once) and then each WhatsApp contact.
- **Security Situation with location and source rules.** The web search gets the country of your GPS position, avoids a list of click-bait sites, prefers embassy notices and local media of the last 30 days, and lists the sources it actually cited (on the iPhone too). Longer answers (4,096 tokens) and a note when an answer was cut off.
- **Wikipedia sources under the answer.** The articles found are listed under the answer and open in the offline Wikipedia; follow-up questions keep the topic, misspelt names are mapped to the English article title, and excerpts come from the article text instead of the whole page.
- **Warning areas automatic and on the iPhone.** The server checks every 10 minutes whether the drawn areas still match the stored warning text and redraws them when needed; the iPhone keeps a copy for use without the Mac.
- **Faster iPhone start without the Mac.** If the Mac does not answer, the page is there within about two seconds (before, the iPhone could wait until the connection gave up).
- **Dock icon.** A small native starter (`app-starter.swift`, compiled by `deploy.sh` if the Xcode Command Line Tools are installed): clicking the Dock icon brings the app's tab to the front, Quit in the Dock stops the server. Without a compiler the app starts as before.

### Security fixes

- **Offline Wikipedia readable from the Wi-Fi:** `kiwix-serve` 3.8.2 rejects `--address=127.0.0.1` on macOS, so it fell back to all interfaces. It now uses `::1` first and checks from outside whether the port is closed to the network. See [SECURITY.md](SECURITY.md#security-fixes-in-2026111).

### Fixed

- The offline Wikipedia search asked `kiwix-serve` under the wrong path since 2026-09 and probably found nothing.

### Not tested

- The station and park numbers were not test-called. Station numbers from OpenStreetMap are unverified, and in a June 2026 survey in South Africa more than half of the police stations called did not answer: call the national number first.
- The Dock starter has only been tested through its fallback; whether macOS asks for permission to control Safari depends on your settings.

## 2026.11 (November 2026)

The second release, about five weeks after the first. It brings a redesigned interface, emergency features on the iPhone that work without the Mac, an automatic backup of your data on the Mac, a VPN check, news by topic, and a round of security fixes from an internal review.

### New

- **Redesigned interface.** Mac: system font instead of monospace, no text smaller than 12 px, a calmer sidebar, a red **Emergency** button at the top (Ctrl+Shift+N), Settings split into five tabs (General · AI & models · iPhone · Network & VPN · Data & backup), and the "local AI is not running" notice reduced to one line. iPhone: a header with Settings · current area · Emergency; tapping the area opens a sheet with all areas and tools; the answer language sits behind a 🌐 button.
- **SOS on the iPhone.** 🚨 → **Send position**: gets a fresh GPS fix and puts it under your own prepared text (decimal degrees, accuracy, time, Google Maps link, Plus Code), then opens Messages (iMessage or SMS, chosen by the iPhone per contact) or WhatsApp. You set recipients and text once; they are stored only on the iPhone. You still tap **Send** yourself.
- **Emergency content on the iPhone without the Mac.** After the iPhone has been connected once over HTTPS, the page starts even when the Mac is asleep, closed or not sharing: instant protocols, emergency numbers and your position work; AI answers do not. Optionally, a copy of the Emergency Card can be kept on the iPhone (off by default; HTTPS only; never includes the key-hiding-place field).
- **Automatic backup on the Mac.** Logbook, Emergency Card, deadlines, notes, chats and settings are mirrored a few seconds after each change to `~/.safari-assistant-sicherung/` (owner-only permissions), with daily copies. If the browser storage is empty or different (another port, `127.0.0.1` instead of `localhost`, deleted website data), a banner offers to restore. Not included: uploaded documents and the iPhone's own data — keep using the backup file for those. The Claude key is never included.
- **Backup file with a password.** Export can encrypt the file (AES-256-GCM, key derived with PBKDF2-SHA256, 310,000 rounds, all in the browser). A forgotten password cannot be recovered.
- **Claude key from the Mac to the iPhone.** iPhone ⚙️ → **Get from Mac** shows a four-digit code; the Mac shows the device, its address and the same code and asks you to allow it. The key is held only in memory for at most two minutes and can be picked up once. Optional: a separate key just for the iPhone.
- **VPN check.** Shows clearly whether the Mac is online with or without a VPN, measured from outside for IPv4 and IPv6 separately (so a leak past the tunnel shows). Works with a VPN on the travel router. Remember your VPN's network once; optional confirmation for Mullvad exits. Red banner on the Mac and a bar on the iPhone when there is no VPN. **Goes online:** while a page of the app is open, about once a minute (adjustable): www.cloudflare.com (fallback api.ipify.org / api6.ipify.org) to see your public address, stat.ripe.net to look up the network of that address, and captive.apple.com to detect a Wi-Fi login page; am.i.mullvad.net only if you switch on the Mullvad confirmation. Switch the check off in Settings → Network & VPN.
- **News by topic.** Items from RSS feeds sorted into nine topics (security, borders, fuel, cash, health, natural events, roads & ferries, parks, other) and by country, by a fixed keyword list: official sources (GDACS, CDC, UK FCDO), one newspaper per country and a keyword search. Add your own feeds. Readable offline, also on the iPhone.
- **iPhone pairing in steps.** Certificate → profile by AirDrop → install → trust → QR code. Choose the secure route (HTTPS only) or the quick one; the Mac shows what arrives from the iPhone while you set it up.
- **When the local AI does not answer**, the matching instant protocol and the country's emergency numbers are shown in Medicine, Emergency, Dog and Survival.
- **Claude:** choose the effort level for the online modules. The default model is now `claude-sonnet-5-5` (the previous default, `claude-sonnet-4-6`, may be retired from February 2027). A model you selected yourself stays selected.

### Security fixes

- A crafted backup file could run script in the app through one unescaped field shown on the Emergency Card. Fixed, and the field is now validated as a date.
- Other websites open in the Mac's browser could make the local server start Ollama runs (no data could be read). The Ollama and document-search routes now reject cross-site requests, and the option limits apply to every request.
- The offline Wikipedia now runs on its own port (its own browser origin), so content from ZIM files cannot reach the app's storage. The app warns if your `kiwix-serve` cannot be limited to the Mac.
- The CDN fallback of the map libraries is pinned with Subresource Integrity.
- News fetching connects to exactly the address that was checked (no second DNS lookup), so a feed cannot redirect the Mac into the local network.
- Two attribute values on the iPhone page are now fully escaped.

### Fixes

- iPhone mode: "Fetch is aborted" when switching on (a slow reverse DNS lookup while binding); the server log is written line by line again.
- iPhone access keeps working while a VPN client runs on the Mac.
- Claude answers were cut off after 25 s in total; the time limit now applies only until the answer starts.
- iPhone: the Settings sheet was taller than the screen and could not be scrolled.

### Upgrading

Run `./deploy.sh`, then **quit and reopen Safari Assistant** — the old server keeps running until the app restarts, and new features answer "not found" until then. Reload the page (Cmd+Option+R). On the iPhone, open the app once over HTTPS so it can work without the Mac later.

### Known limitations

- Tested on one Mac (Apple Silicon, 36 GB) and one iPhone; the screenshots and most UI checks were done in Chrome, not Safari.
- SOS with several SMS recipients uses an iOS link format that Apple does not document; test it once with your own number.
- The VPN check, news and automatic backup are new; their first real runs happen on your Mac.
- The English, French and Spanish first-aid protocols are still translations, not yet reviewed by first-aid professionals.
- Everything in "Known limitations" of 2026.10 below still applies.

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
