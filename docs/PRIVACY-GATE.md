# Privacy gate

`tools/privacy_gate.py` stops private data from reaching this public repository. It runs as a git hook on
every commit and push, in CI on the whole history, and on a plain folder before a release is built.
It needs Python 3.9 or newer and nothing else (stdlib only).

It knows two kinds of rules:

- **A rules** are generic and public: secrets, personal data patterns, dangerous file types, image metadata and
  commit identity. They live in the gate itself and protect every contributor.
- **B rules** are *your* private terms (names, places, numbers). They live in a local file outside the repository
  that is never committed. Hits are always printed as `[redacted]`.

## Quick start

Every contributor, once per clone:

```sh
git config core.hooksPath .githooks        # activates pre-commit, commit-msg and pre-push
git config user.useConfigOnly true         # git must never invent an address from your user and host name
git config user.email "<id>+<user>@users.noreply.github.com"   # GitHub > Settings > Emails
```

Maintainer (additionally):

```sh
git config privacy.allowedNames "DARK"
git config privacy.allowedEmailRegex '(\d+\+)?DarkPirateGo@users\.noreply\.github\.com'
git config privacy.requireUTC true
git config privacy.requireDenylist true
mkdir -p ~/.config/privacy-gate
cp tools/private-terms.example.txt ~/.config/privacy-gate/denylist.txt
chmod 600 ~/.config/privacy-gate/denylist.txt   # then fill in your real terms
python3 tools/privacy_gate.py --paths .         # check the working tree once
```

These settings live in `.git/config` of your clone (or your global git config), never in the repository, so forks
are not affected and contributors can commit under their own names.

## What it checks

| Group | Rules | Examples |
|---|---|---|
| Files | A-F01 forbidden paths | track exports (`.gpx`, `.kml` …), office/PDF/mail files, phone media (`.heic`, `.mov`), archives, databases, logs, keys and certificates, `.env`, `__pycache__`/`.pyc`, `.DS_Store`, app stores and backups (`rag-store.json`, `*backup*.json`), private notes (`TODO.md` …), uploaded documents under `docs/<module>/`, AI assistant settings (`CLAUDE.md`, `.claude/`), any path containing `denylist`, `private-terms*` except the example. Case-insensitive. |
| | A-F02 size | 2 MiB by default; `data/orte.json` 10 MiB, `POIs/*-osm.json` 20 MiB, `vendor/maplibre-gl-*.js` 3 MiB |
| | A-F03 | special or unreadable files (`--paths` only) |
| | A-F04 image metadata | JPEG: EXIF (except purely technical tags), GPS, thumbnails, XMP, IPTC, MPF, APP11 JUMBF/C2PA, comments, data after the end marker. PNG: `tEXt`/`zTXt`/`iTXt`/`tIME`, `eXIf`, C2PA, trailing data. ICNS, WebP, GIF, and base64 `data:image/…` URIs in text files. |
| | A-F05 | app backup / localStorage exports |
| Secrets | A-S01 … A-S11 | private keys, certificates, Anthropic/OpenAI/GitHub/AWS/Google/Slack/HF/GitLab/npm/PyPI/Stripe/Telegram/Discord/SendGrid/Mapbox tokens, JWTs, credentials in URLs, hard-coded passwords |
| Personal data | A-P01 … A-P20 | e-mail addresses (noreply and example addresses are fine), Apple relay and iCloud addresses, `/Users/<name>/` and other home paths, named volumes, device names such as `<name>s-MacBook-Pro`, `.local` host names, public IPs, MAC addresses, IBAN, card numbers, German phone numbers, coordinates in Europe (text, lat/lon keys, DMS, Plus Codes, JSON and GeoJSON parsed structurally), VIN, Toyota frame numbers, pet chip numbers, German plates, travel dates, odometer readings, first-person notes about your dog, car, partner, flat or accounts (German and English) |
| Identity | A-G01 / A-G02 | name / e-mail not in `privacy.allowedNames` / `privacy.allowedEmailRegex` (only if configured) |
| | A-G03 | timezone other than `+0000` reveals where you are: warning, or blocking with `privacy.requireUTC` |
| | A-G04 | signed commit or tag: warning, check that the key's UID is not your real name |
| | A-G05 | always blocked: empty e-mail, Apple relay / icloud.com / me.com / mac.com, and machine or LAN addresses such as `<user>@<hostname>.local` (`.local`, `.lan`, `.home`, `.fritz.box`, `.localdomain`, no dot) |
| | A-G06 | warning: e-mail is not a GitHub noreply address (only when no e-mail regex is configured) |
| Private terms | B-*nn* | every rule of your local term list; *nn* is its line number |

Where the rules look: file contents and file names (staged or pushed), commit messages, tag messages,
branch and tag names, and author, committer and tagger of every commit and tag. Git bots and web merges
(`GitHub`, `dependabot[bot]`, `github-actions[bot]` with their noreply addresses) are always accepted.

Binary files other than images are only checked by name and size. UTF-16 text files are decoded.

**Promo videos (A-F06).** One coded exception lets promo videos for the GitHub Pages site through. This release
ships no videos; the exception stays in the gate for later ones. It allows exactly
`docs/video/safari-assistant-promo-<xx>.mp4` (30 s, vertical) and `docs/video/safari-assistant-desktop-<xx>.mp4`
(60 s, landscape), each with its poster `docs/video/safari-assistant-promo-<xx>-poster.jpg` or
`docs/video/safari-assistant-desktop-<xx>-poster.jpg` (or `.png`), where `<xx>` is two lower-case letters.
Any other video, and anything else under `docs/video/`, stays blocked. Each video may be up to
15 MiB and must be a plain ffmpeg MP4 (brand `isom` or similar, not QuickTime `qt  `; top-level boxes only `ftyp`,
`moov`, `mdat` and padding; no trailing bytes). Their bytes are searched for location and device metadata (`©xyz`,
`loci`, `©mak`, `©mod`, `com.apple.quicktime.*` and `com.android.*` keys, ISO 6709 positions, XMP, C2PA, camera
telemetry); ffmpeg's own `©too` encoder tag is fine. Their readable tags also go through the text rules and your B
terms. The posters are checked like every image (A-F04). A-F06 can never be allowlisted. Render with
`ffmpeg … -map_metadata -1 -f mp4 docs/video/safari-assistant-promo-en.mp4`.

## Modes and exit codes

| Mode | Used by | Scans |
|---|---|---|
| `--staged` | `.githooks/pre-commit` | staged files (as they will be committed) and the effective author/committer (`git var`, including `GIT_AUTHOR_*` overrides) |
| `--commit-msg FILE` | `.githooks/commit-msg` | the message; comment lines and everything below the `>8` scissors line are ignored |
| `--push [REMOTE]` | `.githooks/pre-push` | everything the remote does not have yet: every commit, tag, ref name and file, including files that were added and deleted again inside the pushed range |
| `--all` | CI | the whole history: all refs except `refs/stash` |
| `--paths P …` | you, release builds | files and folders on disk, no git needed; a top-level `.git` folder is skipped, a nested one is reported |

Add `--require-denylist` to any mode to make the local term list mandatory. `--help` lists all options,
`--version` prints the version.

Exit code 0: nothing blocking (warnings are allowed). 1: blocked. 2: usage or configuration error (for example a
required term list that is missing, or a malformed allowlist line).

Every finding prints the rule id, the location (`file:line`, `file (Dateiname / file name)`, `<commit> author`,
`tag v1 message:3`, `ref refs/heads/…`), a masked excerpt (A rules: the first four characters; B rules:
`[redacted]`) and a one-line hint. The last line is a summary with counts. All messages are German first,
English second.

## The local term list (B rules)

The gate looks for the list in this order; the first existing file wins:

1. `$PRIVACY_DENYLIST`
2. `git config privacy.denylist` (a relative path is resolved against the repository's top-level folder)
3. `~/.config/privacy-gate/denylist.txt`

Keep it outside every repository and readable only by you (`chmod 600`; the gate warns otherwise, and also when
the file lies inside the repository). Without a list the gate prints a one-line notice and runs the A rules only.
With `privacy.requireDenylist` (or `--require-denylist`, or `PRIVACY_REQUIRE_DENYLIST=1`) a missing or empty list
fails closed with exit code 2.

The format is documented with made-up examples in `tools/private-terms.example.txt`:

| Kind | Meaning |
|---|---|
| `word: <term>` | whole word, ignoring case and accents |
| `text: <term>` | substring, ignoring case and accents |
| `regex: <python regex>` | matched against the lower-cased, accent-free text |
| `geo: <lat>,<lon>,<km>` | any coordinate pair inside the circle, in either axis order, in text and JSON |
| `allow: <line> <path-glob> <count>` | accept up to `<count>` hits of the rule on `<line>` per matching file |

`allow:` exists for public data that looks like a private term, for example a village with the same name in
`data/orte.json`. When such a file is blocked, the hint prints the exact `allow:` line to add. Because the list is
private, B false positives always go there, never into `.privacy-allowlist`.

## Public exceptions: `.privacy-allowlist`

A tracked file for public strings that trip an A rule, one per line:

```
<rule-id> <path-glob> <exact matched text>
```

Everything after the second space is the exact text. Only public strings belong here, because this file is
published. Secrets (A-S\*), Apple relay/iCloud addresses (A-P02), identity rules (A-G\*), the promo video check
(A-F06) and B rules can never be listed; such a line is a configuration error. The file itself is still checked for
secrets, relay addresses and B terms. A forbidden path can be accepted with `A-F01 <path> <path>`.

## Configuration

Git config keys can be set per clone (`git config …`) or globally (`git config --global …`). An environment
variable overrides the git config for names and the e-mail pattern; for the two `require…` switches any `true`
from either source is enough.

| git config | Environment | Effect |
|---|---|---|
| `privacy.denylist` | `PRIVACY_DENYLIST` | path of the local term list |
| `privacy.requireDenylist` | `PRIVACY_REQUIRE_DENYLIST=1` | the term list is mandatory (fail closed) |
| `privacy.allowedNames` | `PRIVACY_ALLOWED_NAMES` | comma-separated exact names allowed as author, committer and tagger |
| `privacy.allowedEmailRegex` | `PRIVACY_ALLOWED_EMAIL_REGEX` | Python regex; the whole e-mail must match (case-insensitive) |
| `privacy.requireUTC` | `PRIVACY_REQUIRE_UTC=1` | a non-UTC timezone blocks instead of warning |

Without `allowedNames` / `allowedEmailRegex` every name is accepted, but the generic identity rules (A-G05, A-G06,
B terms) still apply. The allowlist also applies to the whole history in `--push` and `--all`: once you merge
contributions that keep their authors, add those names, or configure only the e-mail pattern.

## CI

The `privacy` job in `.github/workflows/ci.yml` checks out the full history, runs
`tools/privacy_gate.py --all`, the self-test `tools/test_privacy_gate.py` and `tools/validate_osm_exports.py`,
with read-only permissions.

- **B rules in CI:** store your term list as the repository secret `PRIVACY_DENYLIST_B64`
  (`base64 < ~/.config/privacy-gate/denylist.txt`). It is used on push events only. Pull requests from forks never
  receive secrets. Without the secret the job prints a notice and runs the A rules only.
- **Identity in CI:** the repository variables `PRIVACY_ALLOWED_NAMES`, `PRIVACY_ALLOWED_EMAIL_REGEX` and
  `PRIVACY_REQUIRE_UTC` are passed on push events only, so pull requests from contributors are not blocked by the
  maintainer's name list.
- B hits appear as `[redacted]`. File, branch and tag names are printed as locations, so a term inside a file or
  branch name is visible in the log; such a name is public in the repository anyway.
- Pin both actions to full commit SHAs once you have verified them.

## Release builds

A release folder can be checked before `git init`:

```sh
cd <release-folder> && python3 tools/privacy_gate.py --require-denylist --paths .
```

`--paths` applies the path, size, content and image rules. Paths are reported relative to the repository root
(or the current folder); a folder with its own `.privacy-allowlist` or `.git`, or outside the current
repository, is scanned as a tree of its own, with its own allowlist. Symbolic links are checked the way git
stores them (as their target path).

## Limits

- `git commit --no-verify` and `git push --no-verify` skip the hooks, and `git rebase`, `cherry-pick` and `merge`
  create commits without the pre-commit hook. The pre-push hook still checks those commits; CI is the last net.
- CI runs *after* the push. When it fails, the data is already on GitHub.
- **Once pushed, treat a leak as permanent.** Revoke and rotate a leaked secret immediately. Rewriting history does
  not remove forks, clones, cached views, pull request refs or the events API. For leaked personal data, delete the
  repository, ask GitHub Support to purge cached views, and start again from a clean history.
- The A rules are patterns. They cannot know your name, address or dog; that is what the B list is for, and it only
  knows what you put into it. Add spelling variants (ü/ue, ß/ss, with and without separators) yourself.
- Only images and promo videos get a binary check; other binary files are judged by name and size only.
- Coordinates: plain pairs (text or JSON arrays) need three or more decimals and are read as latitude, longitude;
  lat/lon keys and GeoJSON `coordinates` (longitude, latitude) need two or more. Coarser values pass. Your home
  belongs in the B list as a `geo:` rule, which checks every pair in either axis order.
- A full scan of the current tree takes about five seconds, mostly for the 6 MB `data/orte.json`. The pre-commit
  hook only scans staged files.

## Recommended GitHub settings

- Account › Settings › Emails: **Keep my email addresses private** and **Block command line pushes that expose my
  email**. This only knows the addresses registered on your account, so the local gate is still needed.
- Repository › Settings › Code security: **Secret scanning** with **Push protection**, and **Private vulnerability
  reporting** (also used for private Code of Conduct reports).
- A branch ruleset for `main`: require the *Privacy gate* status check and block force pushes.
- Public profile: no real name, no location.

## Commit identity

- `git config user.useConfigOnly true`. Without `user.email`, git on macOS invents `<user>@<hostname>.local`,
  which reveals both your user name and your computer's name.
- Use the GitHub noreply address `<id>+<user>@users.noreply.github.com` and a public name.
- Commit with `TZ=UTC`: `TZ=UTC git commit …`, or once in your shell profile `alias git='TZ=UTC git'`. The gate
  warns about other timezones (or blocks with `privacy.requireUTC`).
- Do not sign with a personal GPG key (its UID shows your real name on keyservers). Use no signing or a separate
  SSH signing key. Never add a `.mailmap` that maps old identities.
- Branch and tag names are public too.
- Check before the first push: `git log --format='%an <%ae> | %cn <%ce> | %ad' --date=raw`.

## Self-test

`python3 tools/test_privacy_gate.py` builds throw-away repositories in a temporary folder and checks the gate end
to end, including the real hooks. It never uses your global git configuration or identity and prints one line per
case, then `OK n/n`. All suspicious samples in it are assembled at runtime, so the file passes the gate itself.

## Kurzfassung auf Deutsch

- `tools/privacy_gate.py` verhindert, dass private Daten in dieses öffentliche Repository gelangen: als Git-Hook
  bei Commit und Push, in CI über die ganze Historie und mit `--paths` für Release-Ordner ohne Git.
- **A-Regeln** (öffentlich, im Code): Geheimnisse, persönliche Muster, verbotene Dateitypen, Bild-Metadaten,
  Commit-Identität. **B-Regeln**: deine privaten Begriffe in einer lokalen Datei außerhalb des Repos
  (Standard: `~/.config/privacy-gate/denylist.txt`, `chmod 600`, Vorlage `tools/private-terms.example.txt`).
  B-Treffer erscheinen immer als `[redacted]`.
- Aktivieren: `git config core.hooksPath .githooks` und `git config user.useConfigOnly true`, dazu die
  GitHub-noreply-Adresse als `user.email`.
- Einstellungen per `git config` (Umgebungsvariable hat Vorrang): `privacy.denylist`, `privacy.requireDenylist`,
  `privacy.allowedNames`, `privacy.allowedEmailRegex`, `privacy.requireUTC`. Ohne Namensliste darf jeder unter
  eigenem Namen committen; Relay-, iCloud- und `.local`-Adressen werden trotzdem immer blockiert.
- Zeitzone: Warnung bei allem außer `+0000`; mit `privacy.requireUTC` blockierend. Tipp: `TZ=UTC git commit …`.
- Öffentliche Fehlalarme: Zeile in `.privacy-allowlist`. Private Fehlalarme: `allow:`-Zeile in der lokalen Liste.
- Exit-Codes: 0 ok, 1 blockiert, 2 Aufruf- oder Konfigurationsfehler.
- Grenzen: `--no-verify` umgeht die Hooks, CI ist das letzte Netz. Was einmal gepusht ist, gilt als
  veröffentlicht: Geheimnisse sofort widerrufen, bei persönlichen Daten das Repository löschen und neu anfangen.
- GitHub: E-Mail privat halten und Pushes mit privater Adresse blockieren, Secret Scanning mit Push Protection,
  Private Vulnerability Reporting, Pflicht-Statuscheck *Privacy gate* für `main`.
