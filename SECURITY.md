# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Use GitHub's private vulnerability reporting: open the repository's **Security** tab → **Report a vulnerability**. Only you and the maintainer see the report. There is no e-mail address for reports.

Helpful in a report: what an attacker needs (same Mac, same Wi-Fi with or without the access code, a web page in the browser, a crafted file), the steps to reproduce, and the version marker on line 2 of the affected page or the date of the commit. Say so if the issue is being actively exploited.

This is a spare-time project maintained by one person. Please allow some time for a response.

## Supported versions

Only the latest `main`. There are no release branches and no backports.

---

## Threat model

Safari Assistant is built for **one person on their own Mac**, with the browser UI on `localhost` and, while iPhone mode is on, phones in a Wi-Fi that person controls. It is not built to be exposed to the internet, and it is not a defence against malware already running on the Mac.

### The loopback server

- `server.py` listens on `127.0.0.1:8765` over plain HTTP. `localhost` is a secure context in browsers, and nothing but the Mac itself can reach this listener. Requests from the Mac itself need no access code.
- If a request carries a `Host` header, it must name this server (localhost, 127.0.0.1, the Mac's Wi-Fi address or its `.local` name). Anything else gets `421`. This blocks DNS rebinding.
- Endpoints that write, delete, shut down or switch modes (document upload and delete, PDF extraction, RAG sync, shutdown, iPhone mode on/off, new access code, showing the CA file, refreshing travel advisories) accept requests only from the Mac itself. If the browser sends an `Origin`, it must be this server's own host **and** port.
- CORS headers are sent only to this server's own origins.
- Static files come from an allowlist: the three pages, their images and data files, the interface translations (`i18n.js`, `i18n/en.js`, `i18n/fr.js`, `i18n/es.js`), `vendor/` and `fonts/`. The resolved path must stay inside the allowed folder. There are no directory listings.
- `GET /hilfe` is a read-only help page: the README in the interface language, rendered by the server, offline. From the network it needs the access code, exactly like `mobile.html`. The language picks one of four fixed README files; no file path from the request is used, so no other file is reachable through it. The page carries its own strict Content Security Policy: no scripts, no forms, nothing loaded from elsewhere, only its own stylesheet (allowed by hash).
- Only `GET`, `POST`, `DELETE` and `OPTIONS` are handled, each only after the `Host` check and, from the network, the access-code check. `HEAD` always gets `405 Method Not Allowed`, any other method `501`; neither reads a file.
- Request bodies are capped, each connection has a timeout and the number of threads is limited. PDF extraction has page and size limits. Map tile coordinates are bounded.
- Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN` and `Referrer-Policy: strict-origin-when-cross-origin`; all responses except the proxied Wikipedia pages under `/wiki` also carry a `Content-Security-Policy` with `frame-ancestors`, `object-src` and `base-uri` (`/hilfe` a stricter one of its own).
- Any program on the Mac can talk to the loopback server. It is not a boundary against local software.

### iPhone mode

- Off after every start. It goes on only with the button in ⚙️ Settings (Einstellungen), and off again after 12 hours without phone requests (`SAFARI_LAN_INAKTIV_H`) and when Safari Assistant quits.
- While it is on, the server opens a second listener on the Mac's Wi-Fi address, same port, over HTTPS (see the next section).
- Every request from the network needs the **access code**: from the cookie `safari_zugang` (HttpOnly, SameSite=Lax, Secure over TLS), from `?t=` in the URL, or from the `X-Safari-Zugang` header. Without it the server answers `403`. The only exception is `/api/ping`, which tells the network nothing but app name, version and port.
- The code has 10 characters, is generated with Python's `secrets` module and compared in constant time. It is stored in `~/.safari-assistant-zugang` (mode 0600) and survives restarts. **Renew access code** in Settings creates a new one; every phone must then open the new address.
- The code stays in the home-screen URL on purpose: iOS opens home-screen web apps with a separate cookie store. Anyone who can read the phone's bookmarks or browser history can read the code.
- Ollama stays on `127.0.0.1`. Phones reach it only through two fixed proxy paths (`/api/ollama/api/chat`, `/api/ollama/api/tags`) with a field allowlist; generation options from phones are clamped.
- A phone with the code can chat, read travel advisories, search synced documents and offline Wikipedia, read documents stored through the document API, load map tiles and search places. It cannot upload, delete, shut down or switch modes.
- **Do not switch iPhone mode on in a Wi-Fi you do not trust.** Other devices in that network can see that something listens on port 8765 and can try to connect.
- **Fallback without encryption:** if `openssl` is missing, if `SAFARI_OHNE_TLS=1` is set, or if the server had to bind `0.0.0.0` because the Mac's loopback interface is broken, iPhone mode runs over plain HTTP. The Settings page says so. The access code then crosses the Wi-Fi unencrypted.
- **Offline Wikipedia:** Safari Assistant starts `kiwix-serve` on `127.0.0.1:8090` and serves it to the phone under `/wiki` (with access code and TLS). Only if the installed kiwix-tools version rejects `--address` (the process exits at once) does Safari Assistant start it without that option, listening on all interfaces; the server log then says so. A slow start does not trigger this. It serves public Wikipedia content, read-only.

### The local certificate authority

On first use of iPhone mode, Safari Assistant creates a small certificate authority (CA) in `~/.safari-assistant-tls/` (folder 0700, private keys 0600). The CA signs a server certificate for the Mac's `.local` name and its private addresses. The server certificate is valid for at most 825 days and is re-issued automatically when the addresses change or expiry is near. The CA itself stays the same, so each phone installs it once — until the CA nears its end of validity (see below).

**What trusting it means.** When you install the CA profile on an iPhone and turn on full trust, the phone accepts any certificate this CA signs. Anyone who obtains `ca.key` from your Mac could impersonate servers to that phone, within the CA's limits.

- **Name constraints.** New CAs are limited to `.local` names, `localhost` and private address ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 and 100.64.0.0/10 for carrier-grade NAT).
- If, while creating a CA, Safari Assistant finds that the Mac's crypto library cannot verify IP-address constraints, it creates that CA with name constraints for host names only (`.local`, `localhost`). Such a CA still cannot vouch for public host names, but certificates for IP addresses are not restricted.
- Safari Assistant never drops the constraints silently. A CA without constraints is created only if you set `SAFARI_TLS_OHNE_CONSTRAINTS=1`.
- The Settings page shows the real constraint level of the installed CA and warns if it is unconstrained.
- New CAs are valid for 825 days. An existing CA is never replaced because of a failed self-test. Only 30 days before it expires does Safari Assistant create a new CA (the old files are kept, renamed); Settings then asks you to install the new profile on the phone.
- Backups of your home folder (for example Time Machine) contain `ca.key`. Protect them like the Mac itself.

**Remove or replace the CA:**

1. On every iPhone: Settings → General → VPN & Device Management → the Safari Assistant profile ("Safari Assistant lokale CA"; older installs: "DARK lokale CA" or "Safari Assistent lokale CA") → **Delete Profile**. This also removes the trust.
2. On the Mac: quit Safari Assistant and delete `~/.safari-assistant-tls/`.
3. To use iPhone mode again, switch it on; Safari Assistant creates a new CA. Install and trust it on the phone as described in the [README](README.md#iphone-mode).

### Anthropic API key

- The key for the online modules is stored in the browser's site storage (`localStorage`) for the app's address: on the Mac in its browser, on the iPhone in Safari. It is sent from the browser directly to `api.anthropic.com` and never passes through `server.py`.
- Backups do not contain the key.
- Any script running in the app's origin could read it. That is why the cross-site-scripting fixes below matter.
- Set a spend limit in the Anthropic console, and revoke the key there if a device is lost. Delete it in ⚙️ Settings (Mac) or ⚙️ Setup (iPhone), or clear the site data.
- With a key, the online modules send your question, an attached photo, the chat context and, if stored, your position (rounded to about 100 m) to Anthropic. Full list: [What goes online](README.md#what-goes-online).

### Backups and local data

- A backup file (⚙️ Settings → Backup & Restore → ⬇ Export) contains your chats, notes, checklists, logbook, deadlines, saved answers, indexed documents and the emergency card, including any medical, document and vehicle data you entered. It does not contain the API key or the stored GPS position — but chats can contain positions you asked about (for example location questions with coordinates).
- Treat a backup like a copy of your passport. Import only backups you made yourself: the importer accepts only known keys and validates their values, but before the September 2026 fixes a crafted backup could inject script.
- The privacy gate refuses backups, `rag-store.json`, uploaded documents and similar files in commits. See [docs/PRIVACY-GATE.md](docs/PRIVACY-GATE.md).

### Retrieved text and prompt injection

Excerpts from your PDFs, offline Wikipedia and official travel advice are added to the model prompt. Source markers in that text are neutralised, and a guard sentence says the excerpts are reference material, not instructions. A hostile document can still influence an answer. Model output is escaped before it is shown, so it cannot become active page content. Do not index documents you do not trust.

### Network traffic

There is no telemetry and no analytics. Every outbound request, when it happens and how to avoid it is listed in [What goes online](README.md#what-goes-online).

---

## Known limitations (not vulnerabilities)

- A device in the Wi-Fi that has the access code can use everything the phone can use.
- The access code is visible in the phone's home-screen URL (see above).
- Very old kiwix-tools versions that reject `--address` make `kiwix-serve` listen on all interfaces (logged as a warning).
- The Content Security Policy does not restrict `script-src` yet, because the pages still use inline event handlers. See the [roadmap](docs/ROADMAP.md).
- User data (uploaded documents, `rag-store.json`, the offline map) lives inside the app bundle. Moving it out is on the roadmap.

## Legacy names

Environment variables start with `SAFARI_` and files with `~/.safari-assistant-`: these names come from development, when the app was called *Safari Assistent* (German spelling). They are kept so that existing installs keep their data. Three names keep the development spelling "assistent", so that existing installs also keep their macOS permissions and the certificate the iPhone trusts: the bundle id `com.safari-assistent.app`, the CA certificate file `~/.safari-assistant-tls/safari-assistent-ca.crt` and the server signature `safari-assistent` (reported by `/api/ping`). A few names come from the brief period before the first release when the app was called *DARK*, and are kept as well: the environment variables `DARK_APP` (the app bundle that `deploy.sh` and `setup-offline-karte.sh` update; `build-app.sh` sets it for `deploy.sh`) and `DARK_LOG_DIR` (the folder for the logs `server.py` writes itself), and in the browser `window.DARK_I18N` and `window.__DARK_I18N_DATEN` (interface translation). Security-relevant switches:

| Variable | Effect |
|---|---|
| `SAFARI_LAN_INAKTIV_H` | Hours without phone requests before iPhone mode switches itself off (default 12) |
| `SAFARI_OHNE_TLS=1` | iPhone mode without HTTPS. Not recommended |
| `SAFARI_TLS_OHNE_CONSTRAINTS=1` | New CA without name constraints. Not recommended |
| `SAFARI_LAN=1` or `--lan` | Starts with iPhone mode already on. Development only |

---

## Security fixes in 2026.10 (first public release)

- `HEAD` requests: the server had no handler of its own for `HEAD`, so Python's standard library answered them and skipped the `Host` check, the access code and the static-file allowlist. `HEAD /server.py` or `HEAD /.git/config` returned `200` with the size and modification date of any file in the app folder (source code, `.git/` in a clone, `rag-store.json`, stored documents), also from the Wi-Fi without the access code while iPhone mode was on. No file content was sent. `HEAD` now always gets `405 Method Not Allowed` and never touches a file.

## Security fixes in the unpublished 2026.09 version (included in 2026.10)

- Static files: path traversal with `%2e%2e` under `/vendor/` closed; the resolved path is now checked.
- iPhone listener: the TLS handshake moved from the accept loop into worker threads, plus a per-client connection limit. One stalled client in the Wi-Fi can no longer block the phone's access.
- Local CA: name constraints are never dropped silently; the constraint level is shown in Settings; new CAs are valid for 825 days.
- Logs: the access code is masked; logs moved from `/tmp` to `~/Library/Logs/DARK/` with private permissions. Since 2026.10 the folder is `~/Library/Logs/Safari Assistant/`.
- Map tiles: tile coordinates are bounded (zoom ≤ 22), which closes a CPU and memory exhaustion.
- Security headers on every response (see above).
- Mutations and CORS: the `Origin` must match this server's own host and port.
- Ollama proxy: generation options from phone clients are clamped.
- Vendored libraries are pinned by SHA-256.
- Stored cross-site scripting through a crafted backup file closed: all affected render paths escape their values, and the import validators were hardened.
- `javascript:` links in travel-advisory data are blocked.
- `noopener` on every link and window that opens a new tab.
- Google Fonts removed. The pages use system fonts and make no request to Google.
