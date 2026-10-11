# Contributing

Thank you for looking. Safari Assistant started as one person's tool; almost everything that would make it useful to *you* is a contribution nobody has made yet.

**You do not need to be a programmer to help.** Setup reports, corrections to medical or safety content and better documentation are worth as much as code.

Issues and pull requests in English or German are both welcome.

What you contribute is under Safari Assistant's licence, the PolyForm Noncommercial License 1.0.0; see [Licence of contributions](#licence-of-contributions).

---

## Ways to contribute, easiest first

### 1. Use it and say what broke

Open an [issue](https://github.com/DarkPirateGo/safari-assistant/issues). A setup step that did not work, a module that gave a bad answer, a wrong sentence in the docs: all useful. The most useful report right now is a setup on a second machine ("step 2 fails on macOS 14 with 16 GB"). Remove personal data before you paste logs or screenshots; the bug form says what to remove.

### 2. Fix the content, not the code

A large part of Safari Assistant is prose: system prompts, malaria regions, seasonal data, border rules, emergency numbers, first-aid protocols. If you know a region or a subject better than the author, correcting that content needs no programming.

The system prompts live in the `MODULES` object, which exists **byte-identical** in `index.html` and `mobile.html` (see [the rules](#shared-code-stays-byte-identical)). They are written in English.

### 3. Add a module

One object in `MODULES`, in both files:

```js
tauchen: {
  icon: '🤿',
  label: 'Tauchen & Schnorcheln',
  model: 'gemma4:e4b',
  modelLabel: 'Gemma 4 E4B',
  modelReason: 'Schnell — Tauchplanung ist einfacher Text',
  placeholder: 'Tauchplatz, Bedingungen oder Sicherheitsfrage …',
  hint: 'Bereich: Tauchen',
  quick: ['Bedingungen prüfen', 'Dekompressionsregeln', 'Gefahren im Meer'],
  system: `You are a dive instructor with ...`
}
```

The UI, the history, the model badge and several tests derive from it. Look at an existing module for the remaining fields and the sidebar entry.

### 4. Take on something structural

| | Why it matters |
|---|---|
| **More languages** | The interface comes in English, German, French and Spanish. Every further language opens Safari Assistant to more travellers. See [Translations](#translations). |
| **Region configuration** | Countries, malaria zones, seasons, currencies and border rules are hard-coded across the files. One JSON file would open the door to other regions. |
| **Travel and vehicle profile** | The prompts, the maintenance plan and the checklists assume one traveller profile and one vehicle. |
| **Linux / Windows** | `server.py` is portable Python; the launcher and the `.app` packaging are macOS-only. |

More in [docs/ROADMAP.md](docs/ROADMAP.md). Say hello in an issue before you start something large, so that two people do not build the same thing.

---

## Development setup

```bash
git clone https://github.com/DarkPirateGo/safari-assistant.git && cd safari-assistant
git config core.hooksPath .githooks     # activates the privacy gate
node test-app.js                        # run the tests
python3 server.py                       # start the server, then open http://localhost:8765
```

- There is no build step. Edit the HTML, reload the browser. After changing `server.py`, restart it.
- For most work `ollama pull gemma4:e4b` is enough. Set ⚙️ Settings (Einstellungen) → Global Model to `gemma4:e4b`.
- You do not need the offline map or offline Wikipedia for most changes.
- When you run `server.py` from your clone, it writes runtime data into your clone: synced document excerpts (`rag-store.json`), files stored through the document API (`docs/<module>/`), generated warn-zone files (`data/warnzonen.geojson`, `data/verwaltungsgebiete.geojson`) and, if you build it, the offline map. Git ignores them and the privacy gate refuses them; keep it that way.
- To try your changes in the app bundle: `./deploy.sh`, then restart Safari Assistant. Full setup: [docs/SETUP.md](docs/SETUP.md).

### `deploy.sh` switches

| Setting | Effect |
|---|---|
| `DEPLOY_OHNE_TESTS=1 ./deploy.sh` | Skips the test suite |
| `DEPLOY_COMMIT=1 ./deploy.sh`, or a `.deploy-commit` marker file | Commits after deploying. **Maintainer only.** Never set it in a public clone or fork |

Without `DEPLOY_COMMIT=1` or the marker file, `deploy.sh` never touches git.

---

## The rules

### Tests stay green

```bash
node test-app.js
```

Plain Node, no dependencies. The tests read the source files as text and check that a fix or feature is still present, that shared code is byte-identical, that every module has a role, that every country has a currency. Some tests run Python: `test-reisewarnungen.py`, `test-tls.py`, `test-warngebiete.py`, `test-sicherheit.py`, `test-hilfe.py`, the privacy-gate self-test `tools/test_privacy_gate.py` and the OSM data validator `tools/validate_osm_exports.py`. They need `python3`; `test-tls.py` also needs `openssl`. Without them those tests are skipped with a note.

CI runs the same suite on every push and pull request, and compiles every Python file.

**Fixing a bug means adding a test for it.** That is why fixed bugs stay fixed. Copy the style of a nearby test.

### Shared code stays byte-identical

`index.html` (desktop) and `mobile.html` (phone) share code: the `MODULES` object with all system prompts, the prompt rules, the emergency numbers, the first-aid protocols, the country and malaria data, and more. These blocks must stay **byte-identical** in both files. Tests enforce it, because the failure that actually happens is a fix applied to one file and forgotten in the other. If a test says two blocks differ, change both.

### German is the source language

The pages are written in German; `i18n.js` translates the interface at runtime (see [Translations](#translations)). Write new UI strings in German and add their translation to `i18n/en.js`, `i18n/fr.js` and `i18n/es.js`. If you do not speak one of these languages, say so in the pull request. Explain new strings in English in the pull request if that helps reviewers. System prompts are English. Code comments may be German or English.

### Version markers

Line 2 of `index.html`, `mobile.html` and `pois.html` carries a version marker:

```html
<!-- Safari Assistant index.html vYYYY-MM-DD-N -->
```

The marker names the app, written exactly `Safari Assistant`, and the file. `deploy.sh` reads the version from the first three lines, and the tests check exactly this format on line 2. When you change one of the three pages:

1. Bump the marker on line 2.
2. Set `const APP_VERSION` in the same file to the same value. A test checks that they match.
3. Add an entry with marker strings to `features-manifest.json`, so the feature can never disappear unnoticed.

`deploy.sh` compares the markers with the app bundle and stops before a downgrade.

### Keep the internal names

Internal identifiers stay unchanged so that existing installs keep their data, their macOS permissions and the certificate the iPhone trusts: storage keys `safari-*`, IndexedDB `safari-docs` and `safari-pois-db`, the cookie `safari_zugang`, the files `~/.safari-assistant-*`, the `SAFARI_*` environment variables, the bundle folder `Contents/Resources/safari-assistant`, the bundle id `com.safari-assistent.app`, the certificate file `~/.safari-assistant-tls/safari-assistent-ca.crt` and the server signature `safari-assistent` (reported by `/api/ping`). The last three keep the spelling of the development name *Safari Assistent* (German spelling) on purpose. The names from the brief DARK period stay unchanged too: the JavaScript globals `window.DARK_I18N` and `window.__DARK_I18N_DATEN` (every dictionary in `i18n/` calls the latter, see [Translations](#translations)) and the environment variables `DARK_APP` (the app bundle that `deploy.sh` and `setup-offline-karte.sh` update; `build-app.sh` sets it for `deploy.sh`) and `DARK_LOG_DIR` (the folder for the logs `server.py` writes itself). Do not rename them.

### No build step, no framework

Three self-contained HTML files, no bundler, no `node_modules` at runtime. A toolchain you cannot run without internet is a liability. Reasoning: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#why-no-build-step).

### Nothing fails silently

Every missing model, archive, binary or library must produce a specific, actionable message. Someone far from help needs to know *why* something does not work. "Nothing happened" is a bug.

### Offline first

A feature that needs the network must degrade gracefully without it and say that it is degraded. Every new outbound request must be listed in [What goes online](README.md#what-goes-online) in the same pull request.

---

## Privacy gate

After cloning, run once:

```bash
git config core.hooksPath .githooks
```

`tools/privacy_gate.py` then runs on pre-commit, commit-msg and pre-push, and again in CI. It blocks track and waypoint exports (GPX, KML), app backups, `rag-store.json`, uploaded documents, `*.mbtiles` and `*.zim`, keys and secrets, personal paths and host names, and image metadata.

- You can keep your own terms (names, places, numbers) in a local list **outside** the repository.
- Git config keys: `privacy.denylist`, `privacy.requireDenylist`, `privacy.allowedNames`, `privacy.allowedEmailRegex`, `privacy.requireUTC`.
- **Never bypass it with `--no-verify`.** If it flags something harmless, explain it in the pull request.
- Screenshots count too: use a fresh browser profile, a fake position and no real names, medical data, API key, host name or access code.

Details: [docs/PRIVACY-GATE.md](docs/PRIVACY-GATE.md).

---

## Safety-relevant content

The medicine, snakebite, emergency and vehicle-recovery content can influence decisions that hurt people. If you change it:

- Cite a source in the pull request: a field guide, a medical reference, a manual.
- Prefer stating uncertainty over a confident answer. The prompts are written that way on purpose.
- Never add a medication dose. The prompts tell the model not to state or invent doses and to refer to a doctor, a vet or the package insert. Keep that.
- If a change makes an answer more confident, explain why that confidence is warranted.

Reviews of this content are conservative. That is not distrust of you.

---

## Translations

The interface comes in English, German, French and Spanish. German is the source language: the pages are written in German, and `i18n.js` translates the interface at runtime without touching them. The answer language of the AI follows the interface language; system prompts are English and never go through `i18n.js`.

### Interface

- One file per language: `i18n/en.js`, `i18n/fr.js`, `i18n/es.js`.
- Each **key** is the exact German string as the page shows it, on one line with whitespace collapsed. The **value** is the translation. Change values, never keys: a key that does not match the German exactly is never used.
- Keep the placeholders `{0}`, `{1}` …: every one of them, as often as in the key. You may move them within the sentence. Keep emoji, arrows, numbers, units and phone numbers as they are.
- A string without an entry stays German. Text inside an element marked `data-i18n-skip` is never translated.

**Adding a language** touches several files, so open an issue first. `<code>` is the two-letter language code, for example `pt`; `i18n.js` and `hilfe.py` expect two letters.

1. **Dictionary:** create `i18n/<code>.js` with the structure of `i18n/en.js`: the same German keys, your translations as values, and `'<code>'` as the first argument of `window.__DARK_I18N_DATEN(…)`.
2. **`i18n.js`:** add `<code>` to `SPRACHEN`, its 🌐 answer-language value to `ANTWORT` and its date locale (for example `pt-PT`) to `DATUM`.
3. **Language switchers:** a button with `data-ui-lang="<code>"` in `index.html` (sidebar under the app name, and ⚙️ Settings → Interface language) and in `mobile.html` (⚙️ Setup), and an `<option value="<code>">` in the language menu of `pois.html` (`#ui-lang-select`).
4. **Answer language:** in `index.html` and `mobile.html`, add `<code>` to the interface-to-answer map in `ladeAntwortsprache()`. If the 🌐 row does not offer the language yet and the model should answer in it, also add a `lang-btn` button with `data-lang="<value>"` to the 🌐 row, and the value to `ANTWORT_SPRACHEN` and the backup-import validator for `safari-antwortsprache` in `index.html` and to the list in `ladeAntwortsprache()` in `mobile.html`. The values are German language names, for example `Portugiesisch`.
5. **`server.py`:** add `'/i18n/<code>.js'` to `STATIK_DATEIEN`. The server delivers only the files listed there.
6. **`deploy.sh`:** add `i18n/<code>.js` to `FILES` and `README.<code>.md` to `README_DATEIEN`.
7. **`hilfe.py`:** add `<code>` to `SPRACHEN`, the language's own name to `SPRACHNAMEN`, and the page texts (title, back link, language label, the note shown when the guide falls back to English, the missing-guide message) to `TEXTE`.
8. **README:** translate `README.md` into `README.<code>.md` with the language line on top, and add the new language to the language line of every README (see [The guide](#the-guide-readme)).
9. **Tests:** add `<code>` to `SPR64` in `test-app.js`, so the dictionary checks cover the new file. `node test-app.js` must pass.

### Safety texts

The first-aid protocols, the hazard notes and the emergency numbers with their labels are read in situations where a mistranslation can hurt someone. For these:

- Translate exactly what the German says. No softening, no additions, nothing left out.
- Never change a number, a phone number or a fact in a translation. If the German is wrong, fix the German in its own pull request, with a source (see [Safety-relevant content](#safety-relevant-content)).
- A **second reader** who knows both languages checks the translation against the German before it is merged. Name the reviewer in the pull request.

### The guide (README)

The README exists as `README.md` (English), `README.de.md`, `README.fr.md` and `README.es.md`; a new language is `README.<lang>.md`. The **?** icon on every page opens the one for the interface language, offline, served by Safari Assistant itself at `/hilfe`. Keep every translation in step with the others: the same headings in the same order, the same code blocks and the same link targets (translate the link text, never the address; a link to a heading in the same file points at the translated heading). When one README changes, the same change belongs in all of them.

---

## Data and licences

- Do **not** commit copyrighted material: manufacturer manuals, iOverlander exports, commercial map data. See [NOTICE.md](NOTICE.md).
- A new data source needs its licence in `NOTICE.md`, and the licence must allow redistribution.
- Do not commit API keys. Users enter them in the app.

---

## Licence of contributions

Safari Assistant is under the PolyForm Noncommercial License 1.0.0 ([`LICENSE`](LICENSE)). It is a source-available licence, not an open-source licence approved by the OSI; [NOTICE.md](NOTICE.md#safari-assistants-own-code) quotes what it permits. Whatever you contribute — a pull request, a correction, a translation — you contribute under the same licence, and you agree that DARK may also license it under other terms, for example when someone asks for a commercial licence of Safari Assistant. The pull request template asks you to confirm this.

Only contribute what you may pass on: your own knowledge and your own work, or material whose source allows it. Text copied from manuals, field guides, medical references or websites does not belong here. A citation of the source does.

---

## Pull requests

1. Fork, branch from `main`.
2. Make the change, with a test.
3. `node test-app.js` passes.
4. Open the pull request against `main` and fill in the checklist.

Checklist (also in the pull-request template):

- [ ] `node test-app.js` passes
- [ ] A new test covers the fix or feature
- [ ] Shared code in `index.html` and `mobile.html` is still byte-identical
- [ ] Version marker on line 2 and `APP_VERSION` bumped; entry added to `features-manifest.json`
- [ ] Works offline, or is clearly labelled as online and listed in "What goes online"
- [ ] Failures produce a specific message
- [ ] New UI strings are German and have an entry in `i18n/en.js`, `i18n/fr.js` and `i18n/es.js` (or the pull request says which are missing)
- [ ] Privacy gate passed; no personal data in code, commits or screenshots
- [ ] No copyrighted data, no API keys
- [ ] My contribution is under the project's licence (PolyForm Noncommercial 1.0.0), and DARK may also license it under other terms ([Licence of contributions](#licence-of-contributions))

Good pull-request descriptions say **what problem this solves**, not only what changed.

---

## Code of conduct

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Short version: be decent, assume good faith, and remember that someone may rely on this in a situation where being wrong is expensive.
