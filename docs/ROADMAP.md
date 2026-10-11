# Roadmap

Where Safari Assistant is going, and where help would change its direction. This is not a promise of dates. It is a map of what is missing, so that contributors can see the gaps.

---

## Status

- Used by the author for trip preparation. **Not yet field-tested.** Tested on one machine (Apple Silicon, 36 GB).
- 14 chat modules, 12 of them on local models.
- Offline vector map, rain-season layer, official travel warnings, offline place search, optional offline Wikipedia.
- iPhone view over HTTPS with a local certificate authority.
- Interface in English, German, French and Spanish; the answer language follows it.
- macOS on Apple Silicon only.

---

## Near term

### Second-machine reports

Nobody but the author has completed the setup yet. Every step in [SETUP.md](SETUP.md) is a hypothesis until someone else follows it. A report such as "step 2 fails on macOS 14 with 16 GB" is the most useful contribution right now.

### Travel and vehicle profile

The prompts, the maintenance plan, the checklists and the emergency card are written for one kind of trip: German-speaking travellers with one vehicle (Toyota HZJ78 / 1HZ). A profile in Settings (vehicle, engine, travellers, pets, home country, nationality for the embassy column) would make Safari Assistant useful for other trips. This is the prerequisite for most of the items below.

### Hide modules

Let users hide modules and cards they do not need (for example the dog module and the dog fields on the emergency card).

### Home currency

Exchange rates use EUR as the base. Make the home currency a setting.

### Switch for automatic fetches

Travel advisories and exchange rates are fetched automatically whenever a connection exists. Add a setting that turns this off, next to the existing `SAFARI_OHNE_WARNZONEN_AUTO`.

### Translations

Since 2026.10 the interface and the 8 offline first-aid protocols come in English, German, French and Spanish, and the answer language follows the interface. Open:

- A medical reviewer for the translated first-aid protocols in each language.
- Further languages. See [Translations](../CONTRIBUTING.md#translations).

### Content Security Policy with `script-src`

The pages still use many inline event handlers, so the Content-Security-Policy cannot restrict `script-src` yet. Replace the inline handlers, then add a strict `script-src` and a `connect-src` allowlist.

### User data outside the app bundle

Uploaded documents, `rag-store.json`, the offline map and generated files live inside `Safari Assistant.app`. Move them to a per-user folder, so that the app can be replaced freely and user data is never at risk during a rebuild.

### Pin CI actions to commit SHAs

The workflow uses version tags (`actions/checkout@v4` and others). Pin every action to a full commit SHA.

---

## Further open items

**Security and robustness**

- **Drop the kiwix fallback without `--address`.** Safari Assistant binds `kiwix-serve` to `127.0.0.1` and falls back to all interfaces only for kiwix-tools versions that reject the option; remove the fallback once those versions are gone.
- **Retrieved text into the user turn.** Document and Wikipedia excerpts are added to the system prompt with a guard sentence. Wrapping them in explicit tags inside the last user message would be cleaner.

**Interaction**

- Replace the remaining `prompt()` and `confirm()` flows with inline forms.
- Focus management in overlays, labels on the remaining icon buttons, `prefers-reduced-motion` (keyboard access to the sidebar is done).
- A light theme on desktop and map (the phone has one).
- Regenerate or edit answers; search across chats from the chat view.

**Map**

- Search within imported POIs; distance and bearing from the current position; phone numbers, opening hours and fuel type as separate fields.
- A "navigate to" chooser (`geo:`, OsmAnd, Organic Maps, Apple or Google Maps) instead of OsmAnd only.
- GPS follow mode, distance measurement, recording today's track, elevation profile from GPX.
- Dated personal notes on POIs ("had diesel", "closed") with a freshness filter, stored locally.
- Load the park and climate data on first use instead of on every map open.
- Check for the offline map before the online layer starts, so that no overview tiles are requested from tile.openstreetmap.org when `karte.mbtiles` exists.

**Logbook, health, documents**

- Service reminders by distance or date, with history.
- A medical ID card per traveller, printable and on the phone.
- Medication schedule reminders (without doses from the AI).
- Document deadlines with separate entry, maximum-stay and carnet dates.

---

## Medium term

### Other regions

Countries, malaria zones, seasons, currencies, border rules and emergency numbers are hard-coded across the three pages. They belong in one configuration file. That is the prerequisite for South America, Central Asia, Australia or anywhere else. Each region then needs country data, seasonal patterns, health risks and a POI fetch: mostly research, not code.

### Other vehicles

The Mechanik module knows the Toyota 1HZ diesel. Land Rover Defender, Sprinter, Iveco Daily, Hilux: each is one system prompt plus a vehicle selector. Someone who owns the vehicle writes a better prompt than anyone else.

### Linux and Windows

`server.py` is standard-library Python and ought to run elsewhere. The launcher and the `.app` packaging are macOS-specific. Needs someone with the hardware to try it and report.

### Smaller offline knowledge base

A curated ZIM subset (medicine, species, repair, travel) would be more useful per gigabyte than all of Wikipedia.

### Less duplication

`index.html` and `mobile.html` share code that must stay byte-identical, enforced by tests rather than by structure. Sharing it through one included file, **without introducing a build step**, would remove a whole class of bugs.

---

## Longer term / ideas

Not planned, but the right contributor could make any of these real:

- **Vehicle-mounted server:** a small computer running Safari Assistant permanently, so phones work without a laptop.
- **Voice input and output** with local speech models, hands-free while driving.
- **Photo-first workflow:** camera straight into the Natur or Mechanik module.
- **Shared POI contributions** in an ODbL-clean way.
- **Trip journal:** the logbook grows into a record with photos and positions.

---

## Explicit non-goals

- **A build step.** No bundler, no framework, no `node_modules` at runtime.
- **A cloud backend.** No account, no sync server, no telemetry. Data stays on the machine.
- **An app-store release.** The web app on the home screen works without review cycles and signing identities.
- **Being a navigation app.** [OsmAnd](https://osmand.net) and Organic Maps already do this well. The map is for planning and situational awareness.
- **Replacing professional judgement.** The safety framing in the prompts stays.

---

## How to help

Pick anything above, or something not on the list, and open an [issue](https://github.com/DarkPirateGo/safari-assistant/issues) to say you are starting. [CONTRIBUTING.md](../CONTRIBUTING.md) has the setup and the rules.

If you have taken Safari Assistant into the field, an issue describing what worked and what did not is worth more than a feature.
