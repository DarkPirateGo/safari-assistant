#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy_gate.py - Datenschutz-Schranke / privacy gate (Safari Assistant, PolyForm Noncommercial 1.0.0).

Blockiert Commits, Pushes und Release-Bäume, die private Daten enthalten.
Blocks commits, pushes and release trees that contain private data.

A rules are generic and public (this file). B rules come from a LOCAL term list that is never
committed. Stdlib only, runs on Python 3.9+.  Usage: --help.   Docs: docs/PRIVACY-GATE.md
"""
import base64
import bisect
import fnmatch
import html
import json
import math
import os
import re
import stat
import struct
import subprocess
import sys
import unicodedata
from decimal import Decimal

VERSION = '2.2.0'
ALLOWLIST_FILE = '.privacy-allowlist'
DEFAULT_TERMS = os.path.join('~', '.config', 'privacy-gate', 'denylist.txt')
MIB = 1024 * 1024
MAX_BYTES_DEFAULT = 2 * MIB
SIZE_ALLOW = [('data/orte.json', 10), ('POIs/*-osm.json', 20), ('vendor/maplibre-gl-*.js', 3),
              ('docs/video/safari-assistant-promo-[a-z][a-z].mp4', 15),
              ('docs/video/safari-assistant-desktop-[a-z][a-z].mp4', 15)]  # MiB (fnmatchcase: [a-z] is case-sensitive)
JSON_EXT = ('.json', '.geojson', '.topojson', '.webmanifest')
PRINT_PER_GROUP = 3            # printed findings per rule and file (the rest is summarised)
PRINT_MAX = 150                # printed findings overall
EXIT_OK, EXIT_BLOCKED, EXIT_CONFIG = 0, 1, 2

HELP = """privacy_gate.py %s - Datenschutz-Schranke / privacy gate

Aufruf / usage:  python3 tools/privacy_gate.py MODUS/MODE [--require-denylist]

Modi / modes:
  --staged            pre-commit: Index + Identität / staged files + author/committer identity
  --commit-msg FILE   commit-msg: die Commit-Nachricht / the commit message
  --push [REMOTE]     pre-push: alles Neue für den Remote (stdin von git) / everything new for the remote
  --all               CI: gesamte Historie (Commits, Tags, Refs, Dateien) / whole history
  --paths P [P ...]   Dateien/Ordner, auch ohne git (Release-Baum) / files or folders, git not needed
  --require-denylist  lokale Term-Liste ist Pflicht / local term list is mandatory (fail closed)
  --help, --version

Git-Konfiguration / git config         Umgebung / environment (gewinnt / wins)
  privacy.denylist           <Pfad/path>     PRIVACY_DENYLIST
  privacy.requireDenylist    true|false      PRIVACY_REQUIRE_DENYLIST=1
  privacy.allowedNames       "Name1,Name2"   PRIVACY_ALLOWED_NAMES
  privacy.allowedEmailRegex  <Regex>         PRIVACY_ALLOWED_EMAIL_REGEX
  privacy.requireUTC         true|false      PRIVACY_REQUIRE_UTC=1
  allowedEmailRegex: ganze Adresse, ohne Groß/Klein / full match, case-insensitive
  Pflicht-Schalter: ein "true" aus irgendeiner Quelle genügt / switches: any "true" wins

Term-Liste / term list: $PRIVACY_DENYLIST -> privacy.denylist -> ~/.config/privacy-gate/denylist.txt
  (außerhalb des Repos, chmod 600 / outside the repo, chmod 600; Vorlage / template:
   tools/private-terms.example.txt)
Öffentliche Ausnahmen / public exceptions: .privacy-allowlist
Exit: 0 ok (Warnungen erlaubt / warnings allowed), 1 blockiert / blocked,
      2 Aufruf- oder Konfigurationsfehler / usage or configuration error
Doku / docs: docs/PRIVACY-GATE.md
""" % VERSION


class ConfigError(Exception):
    """Usage or configuration problem -> exit 2."""

    def __init__(self, de, en):
        Exception.__init__(self, '%s / %s' % (de, en))


class GitError(Exception):
    pass


# ================================================================== A: forbidden paths (case-insensitive)
# The only two path rules that the promo video exception (A-F06, see PROMO_VIDEO) lifts - for exactly those names.
RX_MEDIA = r'\.(heic|heif|dng|cr2|cr3|nef|arw|raf|orf|rw2|tiff?|psd|mov|mp4|m4v|avi|3gp|m4a|wav|aac|mp3|caf|aiff?)$'
RX_DOCS_UPLOADS = r'(^|/)docs/(?!img/)[^/]+/'
FORBIDDEN_PATHS = [(re.compile(rx, re.I), de, en) for rx, de, en in [
    (r'(^|/)\.git(/|$)', 'Git-Interna', 'git internals'),
    (r'\.(mbtiles|pmtiles|zim|osm\.pbf|jar)$', 'große Karten-/Wiki-/Binärdatei', 'large map/wiki/binary artefact'),
    (r'\.(pem|key|p12|pfx|jks|keystore|crt|cer|der|csr|srl|kdbx|keychain(-db)?|gpg|asc|ovpn|mobileprovision|provisionprofile)$',
     'Schlüssel/Zertifikat/Passwortspeicher', 'key/certificate/credential store'),
    (r'(^|/)(id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|known_hosts|authorized_keys|\.netrc|\.npmrc|\.pypirc)$',
     'SSH-/Zugangsdatei', 'ssh/credentials file'),
    (r'(^|/)\.env(\.(?!example$)[^/]*)?$', '.env-Datei', '.env file'),
    (r'(^|/)(secrets?|credentials?)(\.[a-z0-9]+)?$', 'Geheimnis-Datei', 'secrets file'),
    (r'\.(gpx|kml|kmz|fit|tcx|gdb|nmea|igc|ov2|loc)$', 'Track-/Wegpunkt-Export (Standortverlauf)',
     'track/waypoint export (location history)'),
    (r'\.(docx?|xlsx?|pptx?|odt|ods|odp|pages|numbers|keynote|pdf|rtf|eml|emlx|msg|mbox|vcf|ics)$',
     'Office-/PDF-/Mail-/Kontakt-Dokument', 'office/pdf/mail/contact document'),
    (RX_MEDIA, 'Kamera-/Handy-/Scan-Medien', 'camera/phone/scan media'),
    (r'\.(zip|7z|rar|tar|tgz|gz|bz2|xz|zst|dmg|pkg|iso|img)$', 'Archiv/Disk-Image', 'archive/disk image'),
    (r'\.(sqlite3?|db|realm|leveldb|ldb|log|har|webarchive|pcapng?|sav)$', 'Datenbank/Log/Browser-Mitschnitt',
     'database/log/browser capture'),
    (r'(^|/)__pycache__/|\.py[cod]$', 'kompiliertes Python (enthält absoluten Pfad)', 'compiled python (embeds absolute path)'),
    (r'(^|/)(\.DS_Store|\._[^/]*|Icon\r|Thumbs\.db|desktop\.ini|\.localized)$|(^|/)(__MACOSX|\.Spotlight-V100|\.Trashes|\.fseventsd|\.TemporaryItems)(/|$)',
     'Betriebssystem-Metadaten', 'OS metadata'),
    (r'(^|/)[^/]+\.app/', 'App-Bundle (enthält Laufzeitdaten)', 'app bundle (contains runtime data)'),
    (r'(^|/)rag-store\.json|backup[^/]*\.json$|(^|/)safari-assist[ae]nt-backup-', 'App-Speicher/Backup-Export',
     'app runtime store/backup export'),
    (r'(^|/)(TODO|BUGLOG|NOTES?|NOTIZEN|PRIVATE?)(\.[a-z]+)?$', 'private Notizen', 'private notes'),
    (r'(^|/)(REVIEW-BERICHT|GITHUB-ANLEITUNG|MIGRATION_CLAUDE_CODE|OLLAMA-UPDATE-ANLEITUNG)[^/]*$', 'private Notizen', 'private notes'),
    (r'(projektstand|projektdokumentation)', 'private Notizen', 'private notes'),
    (r'(^|/)(A_docs|Wiki|_backup[^/]*|_to_delete|_ollama-test|fonts|build|dist|node_modules|\.venv|venv)/',
     'privater/erzeugter Ordner', 'private/generated folder'),
    (r'(^|/)(\.vscode|\.idea)/', 'Editor-Einstellungen (Pfade)', 'editor settings (paths)'),
    (r'(^|/)data/(sources|tmp)/', 'Roh-/Zwischendaten', 'raw/intermediate data'),
    (r'(^|/)data/(warnzonen|verwaltungsgebiete)\.geojson$', 'veralteter Reisewarnungs-Schnappschuss/ungeprüfte Grenzen',
     'stale travel-advice snapshot/unverified boundaries'),
    (RX_DOCS_UPLOADS, 'hochgeladene Dokumente (docs/<Modul>/)', 'uploaded documents (docs/<module>/)'),
    (r'(^|/)\.safari-assistant-', 'App-Laufzeitdatei aus $HOME', 'app runtime file copied from $HOME'),
    (r'denylist', 'Term-Liste (denylist) nie committen', 'never commit the term list (denylist)'),
    (r'(^|/)private-terms(?!\.example\.txt$)[^/]*$', 'Term-Liste nie committen', 'never commit the term list'),
    (r'(^|/)(CLAUDE(\.local)?\.md|\.claude/|\.mcp\.json|\.cursor/|\.aider[^/]*|\.continue/)',
     'KI-Assistent-Speicher/-Einstellungen', 'AI assistant memory/settings'),
    (r'\.(bak|orig|rej|swp|swo)$|~$', 'Editor-/Merge-Backup', 'editor/merge backup'),
]]


# ================================================================== A: content rules
def luhn_ok(d):
    s, alt = 0, False
    for ch in reversed(d):
        n = int(ch)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        s += n
        alt = not alt
    return s % 10 == 0


def v_card(m):
    d = re.sub(r'\D', '', m.group(0))
    if not (13 <= len(d) <= 19) or not luhn_ok(d):
        return False
    return bool(re.match(r'4|5[1-5]|2(2[2-9]|[3-6]\d|7[01]|720)|3[47]|6(011|5|4[4-9])|35(2[89]|[3-8])', d))


def v_iban(m):
    s = re.sub(r'\s', '', m.group(0)).upper()
    if not 15 <= len(s) <= 34:
        return False
    num = ''.join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(num) % 97 == 1


PRIVATE_V4 = [('10.0.0.0', 8), ('172.16.0.0', 12), ('192.168.0.0', 16), ('127.0.0.0', 8), ('0.0.0.0', 8),
              ('169.254.0.0', 16), ('100.64.0.0', 10), ('192.0.2.0', 24), ('198.51.100.0', 24),
              ('203.0.113.0', 24), ('224.0.0.0', 4), ('240.0.0.0', 4), ('255.0.0.0', 8)]
WELL_KNOWN_V4 = {'8.8.8.8', '8.8.4.4', '1.1.1.1', '1.0.0.1', '9.9.9.9'}


def _v4int(ip):
    a = [int(x) for x in ip.split('.')]
    return (a[0] << 24) | (a[1] << 16) | (a[2] << 8) | a[3]


def v_public_ipv4(m):
    ip = m.group(0)
    try:
        if any(int(x) > 255 for x in ip.split('.')):
            return False
        v = _v4int(ip)
    except ValueError:
        return False
    if ip in WELL_KNOWN_V4:
        return False
    for net, bits in PRIVATE_V4:
        if (v >> (32 - bits)) == (_v4int(net) >> (32 - bits)):
            return False
    return True


def in_europe(la, lo):
    return 34.0 <= la <= 72.0 and -25.0 <= lo <= 45.0


def v_europe(m):
    try:
        return in_europe(float(m.group(1)), float(m.group(2)))
    except ValueError:
        return False


def v_europe_rev(m):          # regex captured (lon, lat)
    try:
        return in_europe(float(m.group(2)), float(m.group(1)))
    except ValueError:
        return False


def v_mac(m):
    s = re.sub(r'[:-]', '', m.group(0)).lower()
    return s not in ('000000000000', 'ffffffffffff', '001122334455', '0123456789ab', 'aabbccddeeff')


def v_vin(m):
    s = m.group(0)
    return sum(c.isdigit() for c in s) >= 3 and sum(c.isalpha() for c in s) >= 3 and not re.fullmatch(r'[0-9A-F]+', s)


# Addresses that may appear in files and messages (Co-Authored-By trailers, examples, ssh remotes).
EMAIL_ALLOW = re.compile(r'(?i)(?:@users\.noreply\.github\.com$|^noreply@github\.com$|^noreply@anthropic\.com$'
                         r'|@(?:[a-z0-9-]+\.)*example\.(?:com|org|net)$|@[a-z0-9.-]+\.(?:example|invalid|test|localhost)$'
                         r'|^git@[a-z0-9.-]+$)')
EMAIL_NOT_AN_EMAIL = re.compile(r'(?i)@\d+x\.(?:png|jpe?g|gif|webp|svg)$')      # icon_32x32@2x.png


def v_email(m):
    s = m.group(0)
    return not (EMAIL_ALLOW.search(s) or EMAIL_NOT_AN_EMAIL.search(s))


class Rule(object):
    __slots__ = ('rid', 'rx', 'val', 'de', 'en', 'quick', 'multiline')

    def __init__(self, rid, rx, val, de, en, quick=None, multiline=False):
        self.rid, self.rx, self.val, self.de, self.en = rid, re.compile(rx), val, de, en
        self.quick = None
        if quick:
            self.quick = [tuple((q, q != q.lower()) for q in (alt if isinstance(alt, tuple) else (alt,))) for alt in quick]
        self.multiline = multiline

    def may_match(self, text, low):
        """Cheap necessary condition (speed only): one alternative whose literals all occur.
        Literals with upper-case letters are looked up case-sensitively, the others in the lower-cased text."""
        if not self.quick:
            return True
        for alt in self.quick:
            if all((q in text) if cs else (q in low) for q, cs in alt):
                return True
        return False


# quick = literals of which at least one alternative must occur for the regex to be able to match (speed only)
A_RULES = [
    Rule('A-S01', r'-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|PuTTY-User-Key-File[-]', None,
         'privater Schlüssel', 'private key', ('-----BEGIN', 'PuTTY-User-Key-File\x2d')),       # escaped: this file must pass itself
    Rule('A-S02', r'-----BEGIN (?:CERTIFICATE|CERTIFICATE REQUEST|TRUSTED CERTIFICATE|X509 CRL)-----', None,
         'Zertifikat', 'certificate', ('-----BEGIN',)),
    Rule('A-S03', r'\bsk-ant-[A-Za-z0-9_-]{20,}', None, 'Anthropic-API-Schlüssel', 'Anthropic API key', ('sk-ant-',)),
    Rule('A-S04', r'\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}|\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b|\bsk-[A-Za-z0-9]{48}\b',
         None, 'OpenAI-API-Schlüssel', 'OpenAI API key', ('sk-',)),
    Rule('A-S05', r'\bgh[pousr]_[A-Za-z0-9]{36,255}\b|\bgithub_pat_[A-Za-z0-9_]{22,255}\b', None,
         'GitHub-Token', 'GitHub token', ('ghp_', 'gho_', 'ghu_', 'ghs_', 'ghr_', 'github_pat_')),
    Rule('A-S06', r'\b(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|APKA)[A-Z0-9]{16}\b', None,
         'AWS-Schlüssel', 'AWS key', ('AKIA', 'ASIA', 'ABIA', 'ACCA', 'AGPA', 'AIDA', 'AROA', 'AIPA', 'ANPA', 'ANVA', 'APKA')),
    Rule('A-S06', r'(?i)aws.{0,20}(?:secret|private).{0,20}[=:]\s*["\']?[A-Za-z0-9/+=]{40}\b', None,
         'AWS-Schlüssel', 'AWS key', (('aws', 'secret'), ('aws', 'private'))),
    Rule('A-S07', r'\bAIza[0-9A-Za-z_-]{35}\b|\bGOCSPX-[A-Za-z0-9_-]{28}\b|\bya29\.[0-9A-Za-z_-]{20,}|"type"\s*:\s*"service_account"',
         None, 'Google-Zugangsdaten', 'Google credential', ('AIza', 'GOCSPX-', 'ya29.', 'service_account')),
    Rule('A-S08', r'\bxox[abposr]-[A-Za-z0-9-]{10,}|hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+|'
                  r'\bxapp-\d-[A-Z0-9]+-\d+-[a-f0-9]+', None, 'Slack-Token/Webhook', 'Slack token/webhook',
         ('xoxa-', 'xoxb-', 'xoxo-', 'xoxp-', 'xoxr-', 'xoxs-', 'hooks.slack.com', 'xapp-')),
    Rule('A-S09', r'\bhf_[A-Za-z0-9]{34,}\b|\bglpat-[A-Za-z0-9_-]{20,}\b|\bnpm_[A-Za-z0-9]{36}\b|\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}|'
                  r'\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b|\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b|'
                  r'discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+|'
                  r'\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b|\b(?:pk|sk)\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|'
                  r'\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}', None,
         'Token (HF/GitLab/npm/PyPI/Stripe/Telegram/Discord/SendGrid/Mapbox/JWT)',
         'token (HF/GitLab/npm/PyPI/Stripe/Telegram/Discord/SendGrid/Mapbox/JWT)',
         ('hf_', 'glpat-', 'npm_', 'pypi-AgEIcHlwaS5vcmc', '_live_', '_test_', ':AA', 'discord', 'SG.', 'eyJ')),
    Rule('A-S10', r'\b[a-z][a-z0-9+.-]{1,20}://[^/\s:@\'"<>]{1,64}:[^/\s@\'"<>]{3,}@[^/\s\'"<>]+', None,
         'Zugangsdaten in URL', 'credentials in URL', ('://',)),
    Rule('A-S11', r'(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|bearer|password|'
                  r'passwort|passwd|pwd|wlan[_-]?(?:key|passwort))\b["\']?\s*[:=]\s*["\']'
                  r'(?!(?:sk-ant-\.\.\.|YOUR_|<|\$\{|\{\{|x+["\']|\*+["\']))[^"\'\s]{8,}["\']', None,
         'fest eingetragenes Geheimnis', 'hard-coded secret', ('key', 'secret', 'token', 'bearer', 'passw', 'pwd')),
    Rule('A-P01', r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', v_email, 'E-Mail-Adresse', 'e-mail address', ('@',)),
    Rule('A-P02', r'(?i)@privaterelay\.appleid\.com|@(?:icloud|me|mac)\.com\b', None,
         'Apple-Relay-/iCloud-Adresse', 'Apple relay or iCloud address', ('@',)),
    Rule('A-P03', r'/Users/(?!(?:Shared|x|…|\.\.\.|USERNAME|username|you|YOU|<[^>]+>|\$USER|\$\{USER\})/)[^/\s"\'`)\]]+/|'
                  r'/home/(?!(?:runner|user|username|you|<[^>]+>|\$USER)/)[a-z_][a-z0-9_.-]*(?=/|\b)|'
                  r'(?i:[a-z]:\\\\?users\\\\?[^\\\s"\']+)|/private/var/folders[/]|/var/folders[/][A-Za-z0-9_+-]{2}/|'
                  r'Mobile Documents[/]|com[~]apple[~]CloudDocs|file:///Users[/]', None,
         'absoluter Benutzerpfad', 'absolute user path',
         ('/Users/', '/home/', 'users\\', '/var/folders/', 'Mobile Documents\x2f', 'com\x7eapple\x7eCloudDocs')),
    Rule('A-P04', r'/Volumes[/](?!(?:YourSSD|Macintosh HD|<[^>]+>)\b)[^/\s"\'`)]+', None,
         'benanntes externes Laufwerk', 'named external volume', ('/Volumes/',)),
    # A-P05 is split into its alternatives so that each gets a precise prefilter
    Rule('A-P05', r'(?i)\b(?:macbook(?:-?(?:pro|air))?|imac|mac-?mini|mac-?studio|iphone|ipad)-von-[a-z0-9-]+', None,
         'persönlicher Geräte-/Hostname', 'personal device/host name', ('-von-',)),
    Rule('A-P05', r'(?i)\b[a-z0-9]+s-(?:macbook(?:-(?:pro|air))?|imac|mac-mini|mac-studio|iphone|ipad)(?:-\d+)?\b', None,
         'persönlicher Geräte-/Hostname', 'personal device/host name',
         ('s-macbook', 's-imac', 's-mac-mini', 's-mac-studio', 's-iphone', 's-ipad')),
    Rule('A-P05', r'(?i)\b(?:iphone|ipad|macbook(?: pro| air)?|imac|mac mini|apple watch) von [a-zäöüß]+', None,
         'persönlicher Geräte-/Hostname', 'personal device/host name',
         (('iphone von',), ('ipad von',), ('macbook von',), ('pro von',), ('air von',), ('imac von',), ('mini von',),
          ('watch von',))),
    Rule('A-P05', r'\b[A-Z][a-zäöüß]+[\'’]s (?:iPhone|iPad|MacBook(?: Pro| Air)?|iMac|Mac mini|Apple Watch|AirPods)\b', None,
         'persönlicher Geräte-/Hostname', 'personal device/host name',
         ("s iPhone", "s iPad", "s MacBook", "s iMac", "s Mac mini", "s Apple Watch", "s AirPods")),
    Rule('A-P06', r'(?i)(?<![a-z0-9.-])(?!(?:macbook|mein-mac|mac-name|example|shop|pruef|vm|fremder-name|safari-assistant|localhost)\.local\b)'
                  r'[a-z0-9][a-z0-9-]{1,62}\.local\b(?!\.[a-z0-9])', None,
         'Bonjour-Hostname (.local)', 'Bonjour host name (.local)', ('.local',)),
    # Several patterns below start with a character class and check the preceding character with a lookbehind
    # placed after it (e.g. \d(?<![\d.]\d) == (?<![\d.])\d): same matches, but much faster to search.
    Rule('A-P07', r'\d(?<![\d.]\d)\d{0,2}\.(?:\d{1,3}\.){2}\d{1,3}(?![\d.])', v_public_ipv4, 'öffentliche IPv4-Adresse', 'public IPv4 address'),
    Rule('A-P08', r'(?i)\b(?!2001:0?db8:)(?:2[0-9a-f]{3}|3fff):[0-9a-f]{1,4}:[0-9a-f:]{3,}', None,
         'globale IPv6-Adresse', 'global IPv6 address', (':',)),
    Rule('A-P09', r'[0-9A-Fa-f](?<!\w[0-9A-Fa-f])[0-9A-Fa-f][:-](?:[0-9A-Fa-f]{2}[:-]){4}[0-9A-Fa-f]{2}\b', v_mac, 'MAC-Adresse', 'MAC address'),
    Rule('A-P10', r'[A-Z](?<!\w[A-Z])[A-Z]\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b', v_iban, 'IBAN', 'IBAN'),
    # A-P11: an international phone number ("+244 925 …") is not a card number — a leading "+" excludes it.
    Rule('A-P11', r'\d(?<![\d.+]\d)[ -]?(?:\d[ -]?){11,17}\d(?![\d.])', v_card, 'Kartennummer (Luhn)', 'payment card number (Luhn)'),
    # A-P12: the international forms must not start inside a longer number (OSM ids such as 10004999555).
    Rule('A-P12', r'(?<![\w+])(?:\+49|0049)[\s/-]?\(?0?\)?\s?1[5-7]\d[\s/-]?\d{3,4}[\s/-]?\d{3,5}|'
                  r'0(?<![\d+]0)1[5-7]\d[\s/-]?\d{3,4}[\s/-]?\d{3,5}(?!\d)|'
                  r'(?<![\w+])(?:\+49|0049)[\s/-]?\(?0?\)?\s?[2-9]\d{1,4}[\s/-]?\d{3,}(?:[\s-]\d{1,5})?', None,
         'deutsche Telefonnummer', 'German phone number', ('+49', '0049', '015', '016', '017')),
    Rule('A-P13', r'(-(?<![\d.]-)\d{1,2}\.\d{3,}|\d(?<![\d.]\d)\d?\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})(?![\d])', v_europe,
         'Koordinatenpaar in Europa', 'coordinate pair in Europe'),
    Rule('A-P13', r'(?i)\blat(?:itude)?["\']?\s*[:=]\s*(-?\d{1,2}\.\d{2,})\s*[,;&]?\s*["\']?(?:lon|lng|long|longitude)["\']?\s*[:=]\s*'
                  r'(-?\d{1,3}\.\d{2,})', v_europe, 'lat/lon in Europa', 'lat/lon in Europe', ('lat',), True),
    Rule('A-P13', r'(?i)\b(?:lon|lng|long|longitude)["\']?\s*[:=]\s*(-?\d{1,3}\.\d{2,})\s*[,;&]?\s*["\']?lat(?:itude)?["\']?\s*[:=]\s*'
                  r'(-?\d{1,2}\.\d{2,})', v_europe_rev, 'lon/lat in Europa', 'lon/lat in Europe', ('lat',), True),
    Rule('A-P13', r'\b(?:[3-6]\d|7[0-2])°\s?\d{1,2}[\'′]\s?(?:\d{1,2}(?:[.,]\d+)?["″]\s?)?N\b[\s,]*\d{1,2}°\s?\d{1,2}[\'′]', None,
         'DMS-Position in Europa', 'DMS position in Europe', ('°',)),
    Rule('A-P13', r'\b[89][CFGH][2-9CFGHJMPQRVWX]{6}\+[2-9CFGHJMPQRVWX]{2,3}\b', None,
         'Plus Code in Europa', 'Plus Code in Europe', ('+',)),
    Rule('A-P14', r'[A-HJ-NPR-Z0-9](?<!\w[A-HJ-NPR-Z0-9])[A-HJ-NPR-Z0-9]{16}\b', v_vin, 'VIN-artige Kennung', 'VIN-like identifier'),
    Rule('A-P15', r'\b(?:HZJ|FZJ|HDJ|GRJ|VDJ|KZJ|PZJ|BJ|FJ|LJ)\d{2,3}-\d{5,7}\b', None, 'Toyota-Rahmennummer', 'Toyota frame number',
         ('HZJ', 'FZJ', 'HDJ', 'GRJ', 'VDJ', 'KZJ', 'PZJ', 'BJ', 'FJ', 'LJ')),
    Rule('A-P16', r'(?:276|040|056|250|380|528|724|756|826|9\d\d)(?<![\d.]\d\d\d)\d{12}(?![\d.])', None,
         'Tier-Chipnummer (ISO)', 'ISO pet microchip number'),
    Rule('A-P17', r'[A-ZÄÖÜ](?<!\w[A-ZÄÖÜ])[A-ZÄÖÜ]{0,2}-[A-Z]{1,2} \d{1,4}[EH]?\b', None, 'deutsches Kennzeichen', 'German licence plate'),
    Rule('A-P18', r'(?i)\b(?:abreise|abfahrt|abflug|rückkehr|rueckkehr|heimreise|reisebeginn|reisejahr|departure|leaving|we leave|'
                  r'return(?:ing)? home)\b\D{0,25}'
                  r'(?:\d{1,2}\.\s?\d{1,2}\.(?:\s?\d{2,4})?|\d{4}-\d{2}-\d{2}|\d{1,2}\.? (?:jan|feb|mär|mar|apr|mai|may|jun|jul|aug|sep|okt|oct|nov|dez|dec)[a-zä]*)',
         None, 'persönliches Reisedatum', 'personal travel date',
         ('abreise', 'abfahrt', 'abflug', 'rückkehr', 'rueckkehr', 'heimreise', 'reisebeginn', 'reisejahr',
          'departure', 'leaving', 'we leave', 'return')),
    Rule('A-P19', r'(?i)(?:kilometerstand|km-stand|tachostand|odometer|laufleistung)\D{0,20}\d{2,3}[.,\' ]?\d{3}\b', None,
         'Kilometerstand', 'odometer reading', ('kilometerstand', 'km-stand', 'tachostand', 'odometer', 'laufleistung')),
    Rule('A-P19', r'(?i)\d(?<!\w\d)\d{1,2}[.,\']\d{3}\s?km\b(?=.{0,40}(?:stand|tacho|odometer|gelaufen))', None,
         'Kilometerstand', 'odometer reading', (('km', 'stand'), ('km', 'tacho'), ('km', 'odometer'), ('km', 'gelaufen'))),
    Rule('A-P20', r'(?i)\b(?:mein(?:e[mnrs]?)?|unser(?:e[mnrs]?)?|my|our)\s+(?:hund|auto|wagen|mac|macbook|iphone|partner(?:in)?|'
                  r'freundin|frau|mann|wohnung|adresse|tierarzt|hausarzt|versicherung|konto|kreditkarte|pass|reisepass|kennzeichen|'
                  r'dog|car|wife|husband|girlfriend|boyfriend|flat|apartment|address|vet|insurance|account|passport|plate)\b', None,
         'persönliche Ich-Notiz', 'first-person personal note', ('mein', 'unser', 'my', 'our')),
]
P13_RULES = [r for r in A_RULES if r.rid == 'A-P13']
# .privacy-allowlist itself is only checked for rules that can never be allowlisted (plus B rules)
NEVER_ALLOWLIST = re.compile(r'^(A-S\d\d|A-P02|A-G\d\d|A-F06|B-.*)$')
ALLOWLIST_FILE_RULES = [r for r in A_RULES if NEVER_ALLOWLIST.match(r.rid)]
_NL = re.compile('\n')


def newline_positions(text):
    return [m.start() for m in _NL.finditer(text)] if '\n' in text else []


def line_of(nls, off):
    return bisect.bisect_left(nls, off) + 1


def iter_matches(rx, text, nls, multiline=False):
    """Return [(line, match)]. Per-line semantics (like scanning line by line) unless multiline.

    The whole text is scanned once; only lines touched by a match that spans a newline are
    rescanned on their own, which gives exactly the per-line result for these rules."""
    good, spanning = [], None
    for m in rx.finditer(text):
        s, e = m.span()
        if not multiline and text.find('\n', s, e) != -1:
            if spanning is None:
                spanning = set()
            spanning.update(range(line_of(nls, s), line_of(nls, e - 1) + 1))
            continue
        good.append((line_of(nls, s), m))
    if spanning:
        good = [(ln, m) for ln, m in good if ln not in spanning]
        for ln in sorted(spanning):
            ls = nls[ln - 2] + 1 if ln >= 2 else 0
            le = nls[ln - 1] if ln - 1 < len(nls) else len(text)
            for m in rx.finditer(text[ls:le]):
                good.append((ln, m))
        good.sort(key=lambda t: t[0])
    return good


# ================================================================== image metadata (A-F04)
EXIF_OK_TAGS = {0x8769, 0xA001, 0xA002, 0xA003, 0x0112, 0x011A, 0x011B, 0x0128, 0x0213, 0x9000, 0xA000,
                0x0100, 0x0101, 0x0102, 0x0103, 0x0106, 0x0115, 0x011C, 0x0211, 0x0212, 0x0214, 0x9101, 0xA005}
EXIF_NAMES = {0x010E: 'ImageDescription', 0x010F: 'Make', 0x0110: 'Model', 0x0131: 'Software', 0x0132: 'DateTime',
              0x013B: 'Artist', 0x8298: 'Copyright', 0x8825: 'GPS', 0x9003: 'DateTimeOriginal', 0x9004: 'DateTimeDigitized',
              0x9286: 'UserComment', 0x927C: 'MakerNote', 0xA420: 'ImageUniqueID', 0xA430: 'CameraOwnerName',
              0xA431: 'BodySerialNumber', 0xA435: 'LensSerialNumber', 0x9C9B: 'XPTitle', 0x9C9C: 'XPComment',
              0x9C9D: 'XPAuthor', 0x9C9E: 'XPKeywords', 0x83BB: 'IPTC', 0x02BC: 'XMP', 0x8773: 'ICC'}
PNG_TEXT_KEYS = {b'Title', b'Author', b'Description', b'Copyright', b'Creation Time', b'Software', b'Disclaimer',
                 b'Warning', b'Source', b'Comment', b'XML:com.adobe.xmp', b'Raw profile type exif',
                 b'Raw profile type iptc', b'Raw profile type xmp', b'date:create', b'date:modify', b'date:timestamp'}


def exif_findings(t):
    out = []
    if len(t) < 8 or t[:2] not in (b'II', b'MM'):
        return ['EXIF (unlesbar / unreadable)']
    end = '<' if t[:2] == b'II' else '>'
    seen = set()

    def ifd(off, depth):
        if off in seen or off + 2 > len(t) or depth > 4:
            return
        seen.add(off)
        n = struct.unpack(end + 'H', t[off:off + 2])[0]
        for k in range(n):
            e = t[off + 2 + 12 * k: off + 14 + 12 * k]
            if len(e) < 12:
                return
            tag = struct.unpack(end + 'H', e[:2])[0]
            if tag == 0x8769:
                ifd(struct.unpack(end + 'I', e[8:12])[0], depth + 1)
            elif tag not in EXIF_OK_TAGS:
                out.append('EXIF ' + EXIF_NAMES.get(tag, 'tag 0x%04X' % tag))
        nx = off + 2 + 12 * n
        if depth == 0 and nx + 4 <= len(t) and struct.unpack(end + 'I', t[nx:nx + 4])[0]:
            out.append('EXIF-Vorschaubild / EXIF thumbnail (IFD1)')
    ifd(struct.unpack(end + 'I', t[4:8])[0], 0)
    return out


def _ident(data):
    s = data[:12].split(b'\0', 1)[0]
    return s.decode('ascii') if s and all(32 <= c < 127 for c in s) else s.hex()[:16]


def jpeg_findings(b):
    out, i, n = [], 2, len(b)
    while i < n:
        if b[i] != 0xFF:
            out.append('JPEG-Struktur unlesbar / unreadable JPEG structure')
            return out
        while i < n and b[i] == 0xFF:          # fill bytes
            i += 1
        if i >= n:
            break
        m = b[i]
        i += 1
        if m == 0xD9:                            # EOI
            rest = b[i:]
            if rest.strip(b'\0'):
                out.append('%d Bytes nach EOI / bytes after EOI' % len(rest))
            return out
        if m == 0x01 or 0xD0 <= m <= 0xD7:
            continue
        if i + 2 > n:
            out.append('JPEG abgeschnitten / truncated JPEG')
            return out
        ln = struct.unpack('>H', b[i:i + 2])[0]
        if ln < 2 or i + ln > n:
            out.append('JPEG abgeschnitten / truncated JPEG')
            return out
        data = b[i + 2:i + ln]
        i += ln
        if m == 0xE1:
            if data.startswith(b'Exif\0\0'):
                out += exif_findings(data[6:])
            elif data.startswith(b'http://ns.adobe.com/xap/1.0/'):
                out.append('XMP (APP1)')
            elif data.startswith(b'http://ns.adobe.com/xmp/extension/'):
                out.append('XMP erweitert / extended XMP (APP1)')
            else:
                out.append('APP1 %s' % _ident(data))
        elif m == 0xE0:
            if data.startswith(b'JFXX'):
                out.append('JFXX-Vorschaubild / JFXX thumbnail (APP0)')
            elif data.startswith(b'JFIF\0') and len(data) >= 14 and data[12] and data[13]:
                out.append('JFIF-Vorschaubild / JFIF thumbnail (APP0)')
        elif m == 0xE2:
            if not data.startswith(b'ICC_PROFILE'):
                out.append('APP2 %s (MPF/FlashPix: Zusatzbilder? / extra images?)' % _ident(data))
        elif m == 0xED:
            out.append('IPTC/Photoshop (APP13)')
        elif m == 0xEB:
            out.append('JUMBF/C2PA Content Credentials (APP11)')
        elif m == 0xFE:
            out.append('JPEG-Kommentar / JPEG comment (%d Bytes)' % len(data))
        elif 0xE3 <= m <= 0xEF and m != 0xEE:
            out.append('APP%d %s' % (m - 0xE0, _ident(data)))
        if m == 0xDA:                            # start of scan: skip entropy-coded data up to the next marker
            while i < n:
                j = b.find(b'\xff', i)
                if j < 0 or j + 1 >= n:
                    i = n
                    break
                nxt = b[j + 1]
                if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                    i = j + 2
                elif nxt == 0xFF:
                    i = j + 1
                else:
                    i = j
                    break
    return out


def png_findings(b):
    out, i, n = [], 8, len(b)
    while i + 8 <= n:
        ln = struct.unpack('>I', b[i:i + 4])[0]
        typ = b[i + 4:i + 8]
        if i + 12 + ln > n:
            out.append('PNG abgeschnitten / truncated PNG')
            return out
        data = b[i + 8:i + 8 + ln]
        if typ in (b'tEXt', b'zTXt', b'iTXt'):
            key = data.split(b'\0', 1)[0]
            label = key.decode('latin-1') if key in PNG_TEXT_KEYS else 'eigener Schlüssel / custom key'
            out.append('PNG %s "%s"' % (typ.decode('ascii'), label))
        elif typ == b'tIME':
            out.append('PNG tIME (Zeitstempel / timestamp)')
        elif typ == b'eXIf':
            out += ['PNG ' + f for f in exif_findings(data)]
        elif typ == b'caBX':
            out.append('PNG caBX (C2PA/JUMBF)')
        i += 12 + ln
        if typ == b'IEND':
            break
    if i < n and b[i:].strip(b'\0'):
        out.append('%d Bytes nach IEND / bytes after IEND' % (n - i))
    return out


def icns_findings(b):
    out, i = [], 8
    total = struct.unpack('>I', b[4:8])[0] if len(b) >= 8 else 0
    while i + 8 <= min(total, len(b)):
        ln = struct.unpack('>I', b[i + 4:i + 8])[0]
        data = b[i + 8:i + ln]
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            out += ['ICNS ' + f for f in png_findings(data)]
        elif data[:3] == b'\xff\xd8\xff':
            out += ['ICNS ' + f for f in jpeg_findings(data)]
        if ln < 8:
            break
        i += ln
    return out


def webp_findings(b):
    out, i, n = [], 12, len(b)
    while i + 8 <= n:
        fourcc = b[i:i + 4]
        size = struct.unpack('<I', b[i + 4:i + 8])[0]
        if fourcc == b'EXIF':
            out.append('WebP EXIF')
        elif fourcc == b'XMP ':
            out.append('WebP XMP')
        i += 8 + size + (size & 1)
    return out


def gif_findings(b):
    out, n = [], len(b)
    if n < 13:
        return out
    flags, i = b[10], 13
    if flags & 0x80:
        i += 3 * (2 << (flags & 7))

    def skip_blocks(i, want_first=False):
        first = None
        while i < n:
            sz = b[i]
            i += 1
            if sz == 0:
                break
            if want_first and first is None:
                first = b[i:i + sz]
            i += sz
        return i, first
    while i < n:
        c = b[i]
        if c == 0x3B:
            if b[i + 1:].strip(b'\0'):
                out.append('%d Bytes nach GIF-Ende / bytes after GIF trailer' % (n - i - 1))
            return out
        if c == 0x21 and i + 1 < n:
            label = b[i + 1]
            i, first = skip_blocks(i + 2, True)
            if label == 0xFE:
                out.append('GIF-Kommentar / GIF comment')
            elif label == 0xFF and (first or b'')[:11] not in (b'NETSCAPE2.0', b'ANIMEXTS1.0'):
                out.append('GIF-Anwendungsblock / GIF application block %s' % _ident(first or b''))
        elif c == 0x2C and i + 10 <= n:
            fl = b[i + 9]
            i += 10
            if fl & 0x80:
                i += 3 * (2 << (fl & 7))
            i, _ = skip_blocks(i + 1)
        else:
            out.append('GIF-Struktur unlesbar / unreadable GIF structure')
            return out
    return out


def image_findings(b):
    try:
        if b[:8] == b'\x89PNG\r\n\x1a\n':
            return png_findings(b)
        if b[:3] == b'\xff\xd8\xff':
            return jpeg_findings(b)
        if b[:4] == b'icns':
            return icns_findings(b)
        if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
            return webp_findings(b)
        if b[:6] in (b'GIF87a', b'GIF89a'):
            return gif_findings(b)
    except (struct.error, IndexError, ValueError):
        return ['Bildstruktur unlesbar / unreadable image structure']
    return []


DATA_URI = re.compile(r'data:image/(?:png|jpe?g|gif|webp);base64,([A-Za-z0-9+/]{40,}={0,2})')


# ================================================================== promo video (A-F06): a coded, narrow exception
# For promo videos on the GitHub Pages site, rendered by ffmpeg from generated frames (no camera, no phone): the
# phone promo (safari-assistant-promo-<xx>) and the desktop video (safari-assistant-desktop-<xx>), each with a poster.
# Exactly these names - case-sensitive, at the top of the tree - are exempt from the media and docs/<module>/ path
# rules. Not via .privacy-allowlist (A-F06 can never be allowlisted): the content is still checked, the video by
# mp4_inspect() plus the text rules on its readable metadata, the poster by the image rules like every image.
# 2026-10-05: English spelling safari-assistant-* (2026-10-04: safari-assistent-*, before that dark-promo-<xx>);
# the old names are no longer exempt.
PROMO_VIDEO = re.compile(r'docs/video/safari-assistant-(?:promo|desktop)-[a-z]{2}\.mp4')                  # fullmatch
PROMO_POSTER = re.compile(r'docs/video/safari-assistant-(?:promo|desktop)-[a-z]{2}-poster\.(?:jpg|png)')  # fullmatch
PROMO_EXEMPT = (RX_MEDIA, RX_DOCS_UPLOADS)
MP4_BRANDS = (b'isom', b'iso2', b'iso4', b'iso5', b'iso6', b'mp41', b'mp42', b'avc1')   # ffmpeg's mp4 muxer: isom
MP4_TOP = (b'ftyp', b'moov', b'mdat', b'free', b'skip', b'wide')
# boxes that hold a place, a device or an editing history; searched in every byte outside the media data (mdat)
MP4_ATOMS = ((b'\xa9xyz', '\xa9xyz (GPS-Position / GPS position)'), (b'loci', 'loci (3GPP-Ort / 3GPP location)'),
             (b'\xa9mak', '\xa9mak (Kamerahersteller / camera make)'), (b'\xa9mod', '\xa9mod (Kameramodell / camera model)'),
             (b'XMP_', 'XMP_ (QuickTime-XMP)'), (b'gpmd', 'gpmd (GoPro-Telemetrie / GoPro telemetry)'),
             (b'GPMF', 'GPMF (GoPro-Telemetrie / GoPro telemetry)'), (b'camm', 'camm (Kamerabewegung / camera motion)'),
             (b'jumb', 'JUMBF/C2PA Content Credentials'), (b'c2pa', 'JUMBF/C2PA Content Credentials'))
# long markers: searched in the whole file (too long to occur by chance in compressed media data)
MP4_KEYS = re.compile(rb'(?:com\.apple\.quicktime|com\.android)\.[A-Za-z0-9._-]{1,64}')
MP4_XMP = (b'<x:xmpmeta', b'<?xpacket', b'http://ns.adobe.com/xap/1.0/', b'adobe:ns:meta',
           bytes.fromhex('be7acfcb97a942e89c71999491e3afac'))                          # XMP uuid box
MP4_ISO6709 = re.compile(rb'[+-]\d{2}[\d.]*[+-]\d{3}[\d.]*(?:[+-][\d.]+)?/')           # "+12.3456+045.6789/"
MP4_STRINGS = re.compile(rb'(?:[\x20-\x7e]|[\xc2-\xf4][\x80-\xbf]{1,3}){4,}')


def mp4_inspect(b):
    """-> (findings, text). Findings: wrong format/structure or location/device metadata. Text: the readable strings
    outside the media data (tags, handler names, encoder) for the A and B text rules. ffmpeg's own tags (©too
    encoder, handler names) are fine."""
    out, n = [], len(b)
    if n < 16 or b[4:8] != b'ftyp':
        return ['kein MP4 (ftyp fehlt) / not an MP4 (no ftyp box)'], ''
    if b[8:12] not in MP4_BRANDS:
        out.append('Marke / brand "%s": kein ffmpeg-MP4 (z. B. QuickTime/Kamera) / not an ffmpeg MP4 (e.g. QuickTime/camera)'
                   % printable(b[8:12].decode('latin-1')))
    meta, i, ok, moov = [], 0, True, False
    while i < n:
        if i + 8 > n:
            out.append('%d Bytes nach der letzten Box / bytes after the last box' % (n - i))
            ok = False
            break
        size, typ, hdr = struct.unpack('>I', b[i:i + 4])[0], b[i + 4:i + 8], 8
        if size == 1 and i + 16 <= n:
            size, hdr = struct.unpack('>Q', b[i + 8:i + 16])[0], 16
        elif size == 0:
            size = n - i
        if size < hdr or i + size > n:
            out.append('MP4-Struktur unlesbar / unreadable MP4 structure')
            ok = False
            break
        if typ not in MP4_TOP:
            out.append('unerwartete Box / unexpected box "%s"' % printable(typ.decode('latin-1')))
        moov = moov or typ == b'moov'
        meta.append(b[i:i + hdr] if typ == b'mdat' else b[i:i + size])
        i += size
    if ok and not moov:
        out.append('moov fehlt / no moov box')
    region = b'\0'.join(meta) if ok else b
    for marker, label in MP4_ATOMS:
        if marker in region and label not in out:
            out.append(label)
    for key in sorted(set(MP4_KEYS.findall(b))):
        out.append('%s (Geräte-/Ortsmetadaten / device/location metadata)' % printable(key.decode('ascii')))
    if any(x in b for x in MP4_XMP):
        out.append('XMP-Paket / XMP packet')
    if MP4_ISO6709.search(region):
        out.append('ISO-6709-Position / ISO 6709 position')
    return out, '\n'.join(s.decode('utf-8', 'replace') for s in MP4_STRINGS.findall(region))


# ================================================================== B: local term list
_COMBINING = re.compile('[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]')
_UESC = re.compile(r'\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})')


def fold(s):
    """Lower-case, accent-free form used for B rules."""
    if s.isascii():
        return s.lower()
    return _COMBINING.sub('', unicodedata.normalize('NFKD', s)).lower()


def _unesc(m):
    c = int(m.group(1) or m.group(2), 16)
    return m.group(0) if c < 0x20 or 0xD800 <= c <= 0xDFFF else chr(c)


def b_prepare(text):
    """Decode \\uXXXX / \\xXX escapes and HTML entities so that 'M\\u00fcller' or 'M&uuml;ller' still match."""
    if '\\u' in text or '\\x' in text:
        text = _UESC.sub(_unesc, text)
    if '&' in text:
        text = html.unescape(text)
    return text


PAIR_ANY = re.compile(r'(?<![\d.])(-?\d{1,3}\.\d+)\s*[,;/ ]\s*(-?\d{1,3}\.\d+)(?![\d])')
PAIR_KEYED = re.compile(r'(?i)\blat(?:itude)?["\']?\s*[:=]\s*["\']?(-?\d{1,3}(?:\.\d+)?)[^\d]{1,30}?\b(?:lon|lng|long|longitude)["\']?\s*[:=]\s*["\']?(-?\d{1,3}(?:\.\d+)?)')
PAIR_KEYED_REV = re.compile(r'(?i)\b(?:lon|lng|long|longitude)["\']?\s*[:=]\s*["\']?(-?\d{1,3}(?:\.\d+)?)[^\d]{1,30}?\blat(?:itude)?["\']?\s*[:=]\s*["\']?(-?\d{1,3}(?:\.\d+)?)')


def km(la1, lo1, la2, lo2):
    p = math.pi / 180
    a = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 12742 * math.asin(min(1.0, math.sqrt(a)))


class Fence(object):
    __slots__ = ('lat', 'lon', 'r')

    def __init__(self, lat, lon, r):
        self.lat, self.lon, self.r = lat, lon, r

    def hit(self, a, b):        # either axis order
        for x, y in ((a, b), (b, a)):
            if -90 <= x <= 90 and -180 <= y <= 180 and km(self.lat, self.lon, x, y) <= self.r:
                return True
        return False


class Terms(object):
    def __init__(self):
        self.path, self.source = None, None
        self.rules = []        # (rid, compiled regex)
        self.fences = []       # (rid, Fence)
        self.allow = []        # (rid, glob, max count)

    @property
    def count(self):
        return len(self.rules) + len(self.fences)

    def text_hits(self, folded):
        """Yield rule ids whose term occurs in an already folded string."""
        for rid, rx in self.rules:
            if rx.search(folded):
                yield rid


def env_value(name):
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None


def parse_bool(v, what):
    if v is None:
        return True                       # "[privacy] requireUTC" without value means true (git semantics)
    s = v.strip().lower()
    if s in ('true', 'yes', 'on', '1'):
        return True
    if s in ('false', 'no', 'off', '0', ''):
        return False
    try:
        return int(s) != 0
    except ValueError:
        raise ConfigError('ungültiger Wahrheitswert für %s' % what, 'invalid boolean value for %s' % what)


def short_home(p):
    home = os.path.expanduser('~')
    return '~' + p[len(home):] if home and home != '~' and p.startswith(home + os.sep) else p


def parse_terms(path):
    terms = Terms()
    try:
        with open(path, encoding='utf-8-sig') as fh:
            lines = fh.read().splitlines()
    except (OSError, UnicodeDecodeError):
        raise ConfigError('Term-Liste nicht lesbar (UTF-8?)', 'term list not readable (UTF-8?)')
    rule_lines = set()
    pending_allow = []
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        kind, sep, val = line.partition(':')
        kind, val = kind.strip().lower(), val.strip()

        def bad(de, en):
            # never echo the line itself: it is private
            raise ConfigError('Term-Liste Zeile %d: %s' % (n, de), 'term list line %d: %s' % (n, en))
        if not sep or kind not in ('word', 'text', 'regex', 'geo', 'allow'):
            bad('unbekannte Art (erlaubt: word, text, regex, geo, allow)', 'unknown kind (allowed: word, text, regex, geo, allow)')
        if not val:
            bad('leerer Wert', 'empty value')
        rid = 'B-%02d' % n
        if kind in ('word', 'text'):
            body = r'\s+'.join(re.escape(p) for p in fold(val).split())
            if kind == 'word':
                body = r'(?<![0-9a-z])' + body + r'(?![0-9a-z])'
            terms.rules.append((rid, re.compile(body)))
            rule_lines.add(n)
        elif kind == 'regex':
            try:
                terms.rules.append((rid, re.compile(val, re.I)))
            except re.error:
                bad('ungültige Regex', 'invalid regex')
            rule_lines.add(n)
        elif kind == 'geo':
            try:
                la, lo, r = (float(x) for x in val.split(','))
            except ValueError:
                bad('geo erwartet "lat,lon,km"', 'geo expects "lat,lon,km"')
            if not (-90 <= la <= 90 and -180 <= lo <= 180 and 0 < r <= 500):
                bad('geo außerhalb des Wertebereichs', 'geo value out of range')
            terms.fences.append((rid, Fence(la, lo, r)))
            rule_lines.add(n)
        else:
            parts = val.split()
            if len(parts) != 3 or not parts[0].isdigit() or not parts[2].isdigit():
                bad('allow erwartet "<Zeile> <Pfad-Glob> <Anzahl>"', 'allow expects "<line> <path-glob> <count>"')
            pending_allow.append((n, int(parts[0]), parts[1], int(parts[2])))
    for n, target, glob_, cnt in pending_allow:
        if target not in rule_lines:
            raise ConfigError('Term-Liste Zeile %d: allow verweist auf Zeile %d ohne Regel' % (n, target),
                              'term list line %d: allow refers to line %d, which holds no rule' % (n, target))
        terms.allow.append(('B-%02d' % target, glob_, cnt))
    return terms


def load_terms(gitcfg, top, required, notes):
    cands = []
    ev = env_value('PRIVACY_DENYLIST')
    if ev:
        cands.append(('PRIVACY_DENYLIST', os.path.abspath(os.path.expanduser(ev))))
    gv = gitcfg.get('privacy.denylist')
    if gv:
        p = os.path.expanduser(gv.strip())
        if not os.path.isabs(p):
            p = os.path.join(top or os.getcwd(), p)
        cands.append(('git config privacy.denylist', os.path.normpath(p)))
    cands.append(('default', os.path.expanduser(DEFAULT_TERMS)))
    chosen = None
    for src, p in cands:
        if os.path.isfile(p):
            chosen = (src, p)
            break
        if src != 'default':
            notes.append('WARNUNG / WARNING: %s zeigt auf eine fehlende Datei / points to a missing file (%s)' % (src, short_home(p)))
    if chosen is None:
        if required:
            raise ConfigError(
                'lokale Term-Liste ist Pflicht (--require-denylist / privacy.requireDenylist), fehlt aber. Anlegen: '
                '~/.config/privacy-gate/denylist.txt (chmod 600) oder git config privacy.denylist <Pfad>',
                'local term list is required but missing. Create ~/.config/privacy-gate/denylist.txt (chmod 600) '
                'or set git config privacy.denylist <path>')
        notes.append('Hinweis / Note: keine lokale Term-Liste - B-Regeln aus / no local term list - B rules off '
                     '(docs/PRIVACY-GATE.md)')
        return Terms()
    terms = parse_terms(chosen[1])
    terms.path, terms.source = chosen[1], chosen[0]
    if required and not terms.count:
        raise ConfigError('Term-Liste ist leer, aber Pflicht', 'term list is empty but required')
    if not terms.count:
        notes.append('Hinweis / Note: Term-Liste enthält keine Regeln / term list contains no rules')
    try:
        mode = os.stat(chosen[1]).st_mode
        if os.name != 'nt' and mode & 0o044:
            notes.append('WARNUNG / WARNING: Term-Liste ist für andere lesbar / term list is readable by others -> '
                         'chmod 600 %s' % short_home(chosen[1]))
    except OSError:
        pass
    if top:
        rp, rt = os.path.realpath(chosen[1]), os.path.realpath(top)
        if rp.startswith(rt + os.sep):
            notes.append('WARNUNG / WARNING: Term-Liste liegt im Repository - nach außerhalb verschieben / '
                         'term list is inside the repository - move it outside')
    return terms


# ================================================================== configuration
def read_git_config(cwd):
    try:
        p = subprocess.run(['git', 'config', '-z', '--get-regexp', r'^privacy\.'], cwd=cwd,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return {}
    if p.returncode not in (0, 1):
        raise ConfigError('git config nicht lesbar: %s' % p.stderr.decode('utf-8', 'replace').strip()[:200],
                          'cannot read git config')
    out = {}
    for rec in p.stdout.decode('utf-8', 'replace').split('\0'):
        if rec:
            key, sep, val = rec.partition('\n')
            out[key.strip().lower()] = val if sep else None
    return out


class Config(object):
    def __init__(self, gitcfg, require_flag):
        self.git = gitcfg
        names = env_value('PRIVACY_ALLOWED_NAMES')
        if names is None:
            names = gitcfg.get('privacy.allowednames')
        self.names = None
        if names and names.strip():
            self.names = set(x.strip() for x in names.split(',') if x.strip())
        rx = env_value('PRIVACY_ALLOWED_EMAIL_REGEX')
        if rx is None:
            rx = gitcfg.get('privacy.allowedemailregex')
        self.email_rx = None
        if rx and rx.strip():
            try:
                self.email_rx = re.compile(rx.strip(), re.I)
            except re.error:
                raise ConfigError('privacy.allowedEmailRegex ist keine gültige Regex', 'privacy.allowedEmailRegex is not a valid regex')
        self.require_denylist = bool(require_flag) or self._flag('PRIVACY_REQUIRE_DENYLIST', 'privacy.requiredenylist')
        self.require_utc = self._flag('PRIVACY_REQUIRE_UTC', 'privacy.requireutc')

    def _flag(self, env, key):
        ev = env_value(env)
        on = parse_bool(ev, env) if ev is not None else False
        if key in self.git:
            on = parse_bool(self.git[key], key) or on
        return on


# ================================================================== identity rules (A-G)
BOT_IDENTS = (
    ('GitHub', re.compile(r'noreply@github\.com', re.I)),
    ('dependabot[bot]', re.compile(r'(?:\d+\+)?dependabot\[bot\]@users\.noreply\.github\.com', re.I)),
    ('github-actions[bot]', re.compile(r'(?:\d+\+)?github-actions\[bot\]@users\.noreply\.github\.com', re.I)),
)
NOREPLY_EMAIL = re.compile(r'(?:\d+\+)?[A-Za-z0-9][A-Za-z0-9-]*(?:\[bot\])?@users\.noreply\.github\.com|noreply@github\.com', re.I)
APPLE_EMAIL = re.compile(r'@(?:privaterelay\.appleid|icloud|me|mac)\.com$', re.I)
LOCAL_DOMAIN = re.compile(r'(?:^|\.)(?:local|lan|home|localdomain|fritz\.box|internal|intranet|home\.arpa)$', re.I)
PLAIN_EMAIL = re.compile(r'[^@\s<>]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{1,59})')
IDENT_RX = re.compile(r'^(.*?) ?<([^<>]*)> (\d+) ([+-]\d{4})\s*$')


def parse_ident(s):
    m = IDENT_RX.match(s.strip())
    if not m:
        return s.strip(), '', ''
    return m.group(1).strip(), m.group(2).strip(), m.group(4)


# ================================================================== the gate
class Finding(object):
    __slots__ = ('rid', 'block', 'where', 'excerpt', 'de', 'en', 'hint', 'group')

    def __init__(self, rid, block, where, excerpt, de, en, hint, group):
        self.rid, self.block, self.where, self.excerpt = rid, block, where, excerpt
        self.de, self.en, self.hint, self.group = de, en, hint, group


def printable(s):
    out = []
    for c in s:
        if c.isprintable() and c not in '\u2028\u2029':
            out.append(c)
        else:
            out.append('\\x%02x' % ord(c) if ord(c) < 256 else '\\u%04x' % ord(c))
    return ''.join(out)


def mask(s):
    s = printable(' '.join(s.split()))
    return '"%s…"' % s[:4]


def size_limit(path):
    limit = MAX_BYTES_DEFAULT
    for glob_, mib in SIZE_ALLOW:
        if fnmatch.fnmatchcase(path, glob_):
            limit = mib * MIB
    return limit


class Gate(object):
    def __init__(self, cfg, terms, history=False):
        self.cfg, self.terms, self.history = cfg, terms, history
        self.findings = []
        self.allow = {}
        self.units = []                 # unit id -> path (for B allow)
        self.b_count = {}               # (rid, unit) -> hits
        self.files = self.commits = 0

    # ------------------------------------------------------------- allowlist
    def set_allowlist(self, text, origin):
        self.allow = {}
        for n, line in enumerate(text.splitlines(), 1):
            line = line.rstrip('\r')
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            parts = line.split(' ', 2)
            if NEVER_ALLOWLIST.match(parts[0]):
                raise ConfigError('%s Zeile %d: %s kann nicht freigegeben werden' % (origin, n, printable(parts[0])),
                                  '%s line %d: %s cannot be allowlisted' % (origin, n, printable(parts[0])))
            if len(parts) < 3 or not re.match(r'^A-[A-Z]\d\d$', parts[0]) or not parts[2]:
                raise ConfigError('%s Zeile %d: erwartet "<Regel> <Pfad-Glob> <exakter Text>"' % (origin, n),
                                  '%s line %d: expected "<rule> <path-glob> <exact text>"' % (origin, n))
            self.allow.setdefault(parts[0], []).append((parts[1], parts[2]))

    def allowed(self, rid, path, text):
        for glob_, t in self.allow.get(rid, ()):
            if t == text and fnmatch.fnmatchcase(path, glob_):
                return True
        return False

    # ------------------------------------------------------------- findings
    def new_unit(self, path):
        self.units.append(path)
        return len(self.units) - 1

    def add(self, rid, where, excerpt, de, en, hint, group, block=True):
        self.findings.append(Finding(rid, block, where, excerpt, de, en, hint, group))

    def add_b(self, rid, where, unit):
        key = (rid, unit)
        self.b_count[key] = self.b_count.get(key, 0) + 1
        self.add(rid, where, '[redacted]', 'private Term-Liste', 'private term list', 'B', unit)

    def excerpt(self, s):
        if self.terms.rules and any(True for _ in self.terms.text_hits(fold(s))):
            return '[redacted]'
        return mask(s)

    def hint_a(self, rid, path):
        if rid.startswith('A-S'):
            return 'entfernen UND Schlüssel widerrufen/rotieren / remove it AND revoke/rotate the secret'
        if rid == 'A-P02':
            return 'entfernen (nicht freigebbar) / remove it (cannot be allowlisted)'
        return ('entfernen; öffentlicher Fehlalarm / remove it; public false positive: .privacy-allowlist += "%s %s <exakter Text / exact text>"'
                % (rid, path))

    # ------------------------------------------------------------- paths and blobs
    def check_path(self, path, size, unit, sfx=''):
        loc = printable(path) + sfx
        promo = PROMO_VIDEO.fullmatch(path) or PROMO_POSTER.fullmatch(path)
        for rx, de, en in FORBIDDEN_PATHS:
            if rx.search(path):
                if promo and rx.pattern in PROMO_EXEMPT:
                    continue                     # content is checked in check_blob (A-F06, A-F04)
                if not self.allowed('A-F01', path, path):
                    self.add('A-F01', loc, '', 'verbotene Datei: ' + de, 'forbidden file: ' + en,
                             'Datei entfernen (git rm --cached <Datei>) + .gitignore / remove the file (git rm --cached <file>) + .gitignore',
                             unit)
                break
        if size is not None and size > size_limit(path):
            self.add('A-F02', loc, '%d > %d Bytes' % (size, size_limit(path)), 'Datei zu groß', 'file too large',
                     'verkleinern oder weglassen / shrink it or leave it out', unit)
        # the path itself is public too
        self.scan_a(path, path, unit, printable(path) + ' (Dateiname / file name)' + sfx, A_RULES, False, one_line=True)
        self.scan_b(path, path, unit, printable(path) + ' (Dateiname / file name)' + sfx, geo_text=False, one_line=True)

    def check_blob(self, path, data, size, sfx=''):
        self.files += 1
        unit = self.new_unit(path)
        self.check_path(path, size, unit, sfx)
        if data is None:
            return
        loc = printable(path) + sfx
        for f in image_findings(data):
            if not self.allowed('A-F04', path, f):
                self.add('A-F04', loc, f, 'Bild-Metadaten', 'image metadata',
                         'Metadaten entfernen, z. B. exiftool -all= <Datei> / strip metadata, e.g. exiftool -all= <file>', unit)
        if PROMO_VIDEO.fullmatch(path):
            found, text = mp4_inspect(data)
            for f in found:
                self.add('A-F06', loc, f, 'Promo-Video: Format/Metadaten nicht erlaubt', 'promo video: format/metadata not allowed',
                         'mit ffmpeg ohne Metadaten neu erzeugen (-map_metadata -1 -f mp4) / re-render with ffmpeg without '
                         'metadata (-map_metadata -1 -f mp4)', unit)
            base = printable(path) + ' (MP4-Metadaten / MP4 metadata)'
            self.scan_a(text, path, unit, base, A_RULES, False, sfx=sfx)
            self.scan_b(text, path, unit, base, sfx=sfx)
            return
        if PROMO_POSTER.fullmatch(path) and not data.startswith(b'\x89PNG\r\n\x1a\n' if path.endswith('.png') else b'\xff\xd8\xff'):
            self.add('A-F06', loc, 'kein %s / not a %s' % ((path[-3:].upper(),) * 2), 'Promo-Poster: kein Bild',
                     'promo poster: not an image', 'als echtes JPEG/PNG speichern / save it as a real JPEG/PNG', unit)
        if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
            text = data.decode('utf-16', 'replace')
        elif b'\0' in data[:8192]:
            return
        else:
            text = data.decode('utf-8', 'replace')
        self.scan_file_text(path, text, unit, sfx)

    def scan_file_text(self, path, text, unit, sfx):
        if path == ALLOWLIST_FILE:
            self.scan_a(text, path, unit, printable(path), ALLOWLIST_FILE_RULES, False, sfx=sfx)
            self.scan_b(text, path, unit, printable(path), geo_text=True, sfx=sfx)
            return
        json_ok = False
        if path.lower().endswith(JSON_EXT):
            if re.search(r'"safari-(?:notfallkarte|history|logbuch|notes|settings)"\s*:', text):
                self.add('A-F05', printable(path) + sfx, '', 'sieht nach App-Backup/localStorage-Export aus',
                         'looks like an app backup/localStorage export', 'App-Backups nie committen / never commit app backups', unit)
            json_ok = self.scan_json(path, text, unit, sfx)
        # floats inside JSON arrays were checked structurally; blank them (same length) to keep the text rules fast
        self.scan_a(blank_json_floats(text) if json_ok else text, path, unit, printable(path), A_RULES, json_ok, sfx=sfx)
        if 'data:image/' in text:
            self.scan_data_uris(path, text, unit, sfx)
        self.scan_b(text, path, unit, printable(path), geo_text=not json_ok, sfx=sfx)

    def scan_a(self, text, path, unit, base, rules, skip_p13, sfx='', one_line=False):
        low = text.lower()
        nls = [] if one_line else newline_positions(text)
        for r in rules:
            if skip_p13 and r.rid == 'A-P13':
                continue
            if not r.may_match(text, low):
                continue
            for ln, m in iter_matches(r.rx, text, nls, r.multiline):
                if r.val is not None and not r.val(m):
                    continue
                s = m.group(0)
                if self.allowed(r.rid, path, s) or ('\n' in s and self.allowed(r.rid, path, ' '.join(s.split()))):
                    continue
                where = base + sfx if one_line else '%s:%d%s' % (base, ln, sfx)
                self.add(r.rid, where, self.excerpt(s), r.de, r.en, self.hint_a(r.rid, path), unit)

    def scan_b(self, text, path, unit, base, geo_text=True, sfx='', one_line=False):
        t = self.terms
        if not t.count:
            return
        prepared = b_prepare(text)
        if t.rules:
            folded = fold(prepared)
            nls = [] if one_line else newline_positions(folded)
            for rid, rx in t.rules:
                for m in rx.finditer(folded):
                    self.add_b(rid, base + sfx if one_line else '%s:%d%s' % (base, line_of(nls, m.start()), sfx), unit)
        if t.fences and geo_text:
            nls = [] if one_line else newline_positions(prepared)
            for la, lo, off in text_pairs(prepared):
                for rid, fence in t.fences:
                    if fence.hit(la, lo):
                        self.add_b(rid, base + sfx if one_line else '%s:%d%s' % (base, line_of(nls, off), sfx), unit)

    def scan_data_uris(self, path, text, unit, sfx):
        nls = newline_positions(text)
        for m in DATA_URI.finditer(text):
            b64 = m.group(1)
            try:
                raw = base64.b64decode(b64 + '=' * (-len(b64) % 4))
            except (ValueError, TypeError):
                continue
            for f in image_findings(raw):
                if not self.allowed('A-F04', path, f):
                    self.add('A-F04', '%s:%d%s' % (printable(path), line_of(nls, m.start()), sfx), f,
                             'Bild-Metadaten (data:-URI)', 'image metadata (data: URI)',
                             'Metadaten entfernen / strip metadata', unit)

    def scan_json(self, path, text, unit, sfx):
        """Structural coordinate check: lat/lon keys, GeoJSON 'coordinates' ([lon, lat]) and [name, lat, lon, ...] rows
        with >= 2 decimals, plain [lat, lon] pairs with >= 3 decimals (like the text rules). String values are checked
        with the text rules. Returns False if the file is not valid JSON (the caller then uses the text rules)."""
        try:
            doc = json.loads(text.lstrip('\ufeff'), parse_float=Decimal)
        except (ValueError, RecursionError):
            return False

        def num(v):
            t = type(v)
            return t is Decimal or t is int

        def decimals(v):
            if isinstance(v, Decimal):
                e = v.as_tuple().exponent
                return -e if isinstance(e, int) and e < 0 else 0
            return 0
        pairs, strings = [], []
        stack = [(doc, False)] if type(doc) in (dict, list) else []
        if type(doc) is str:
            strings.append(doc)
        while stack:
            o, geo = stack.pop()
            if type(o) is dict:
                la = next((o[k] for k in ('lat', 'latitude') if k in o and num(o[k])), None)
                lo = next((o[k] for k in ('lon', 'lng', 'long', 'longitude') if k in o and num(o[k])), None)
                if la is not None and lo is not None:
                    pairs.append((la, lo, decimals(la) >= 2 and decimals(lo) >= 2))
                for k, v in o.items():
                    t = type(v)
                    if t is str:
                        strings.append(v)
                    elif t is dict or t is list:
                        stack.append((v, geo or k == 'coordinates'))
                continue
            n = len(o)
            if geo:
                if n >= 2 and num(o[0]) and num(o[1]):
                    pairs.append((o[1], o[0], decimals(o[0]) >= 2 and decimals(o[1]) >= 2))
                    continue
            elif n >= 3 and type(o[0]) is str and num(o[1]) and num(o[2]):
                pairs.append((o[1], o[2], decimals(o[1]) >= 2 and decimals(o[2]) >= 2))
            elif (n == 2 or n == 3) and all(num(x) for x in o):
                pairs.append((o[0], o[1], decimals(o[0]) >= 3 and decimals(o[1]) >= 3))
            for v in o:
                t = type(v)
                if t is str:
                    strings.append(v)
                elif t is dict or t is list:
                    stack.append((v, geo))
        loc = printable(path) + ' (JSON)' + sfx
        fences = self.terms.fences
        for la, lo, strong in pairs:
            fla, flo = float(la), float(lo)
            if strong and in_europe(fla, flo) and not self.allowed('A-P13', path, '%s,%s' % (la, lo)):
                self.add('A-P13', loc, self.excerpt('%s,%s' % (la, lo)), 'Koordinate in Europa', 'coordinate in Europe',
                         self.hint_a('A-P13', path), unit)
            if fences and (isinstance(la, Decimal) or isinstance(lo, Decimal)):
                for rid, fence in fences:
                    if fence.hit(fla, flo):
                        self.add_b(rid, loc, unit)
        if strings:
            joined = '\n'.join(s.replace('\n', ' ') for s in strings)
            if re.search(r'\d', joined):
                nls = newline_positions(joined)
                jlow = joined.lower()
                for r in P13_RULES:
                    if not r.may_match(joined, jlow):
                        continue
                    for _ln, m in iter_matches(r.rx, joined, nls, False):
                        s = m.group(0)
                        if (r.val is None or r.val(m)) and not self.allowed('A-P13', path, s):
                            k = text.find(s)
                            where = '%s:%d%s' % (printable(path), text.count('\n', 0, k) + 1, sfx) if k >= 0 else loc
                            self.add('A-P13', where, self.excerpt(s), r.de, r.en, self.hint_a('A-P13', path), unit)
                if fences:
                    for la, lo, _off in text_pairs(b_prepare(joined)):
                        for rid, fence in fences:
                            if fence.hit(la, lo):
                                self.add_b(rid, loc, unit)
        return True

    # ------------------------------------------------------------- messages, refs, identities
    def scan_message(self, where, text):
        unit = self.new_unit('<commit-message>')
        self.scan_a(text, '<commit-message>', unit, where, A_RULES, False)
        self.scan_b(text, '<commit-message>', unit, where)

    def scan_refname(self, name):
        unit = self.new_unit('<ref>')
        where = 'ref ' + printable(name)
        self.scan_a(name, '<ref>', unit, where, A_RULES, False, one_line=True)
        self.scan_b(name, '<ref>', unit, where, one_line=True)

    def ident_hint(self):
        if self.history:
            return ('Commits neu schreiben (git rebase -i … --reset-author) / rewrite those commits '
                    '(git commit --amend --reset-author)')
        return ('git config user.name/user.email setzen (GitHub-noreply) / set git config user.name/user.email '
                '(GitHub noreply address)')

    def check_ident(self, where, name, email, tz):
        group = 'ident:' + where
        cfg = self.cfg
        if any(name == bn and brx.fullmatch(email) for bn, brx in BOT_IDENTS):
            return
        if cfg.names is not None and name not in cfg.names:
            self.add('A-G01', where, mask(name), 'Name nicht in privacy.allowedNames', 'name not in privacy.allowedNames',
                     self.ident_hint(), group)
        if cfg.email_rx is not None and not cfg.email_rx.fullmatch(email):
            self.add('A-G02', where, mask(email or '-'), 'E-Mail passt nicht zu privacy.allowedEmailRegex',
                     'e-mail does not match privacy.allowedEmailRegex', self.ident_hint(), group)
        domain = email.rsplit('@', 1)[1] if '@' in email else ''
        if not email:
            self.add('A-G05', where, '-', 'leere E-Mail', 'empty e-mail', self.ident_hint(), group)
        elif APPLE_EMAIL.search(email):
            self.add('A-G05', where, mask(email), 'Apple-Relay-/iCloud-Adresse', 'Apple relay or iCloud address',
                     self.ident_hint(), group)
        elif '.' not in domain or LOCAL_DOMAIN.search(domain) or not PLAIN_EMAIL.fullmatch(email):
            self.add('A-G05', where, mask(email), 'Rechner-/LAN-Adresse (z. B. <user>@<host>.local)',
                     'machine or LAN address (e.g. <user>@<host>.local)', self.ident_hint(), group)
        if self.terms.rules:
            for rid in sorted(set(self.terms.text_hits(fold(name + '\n' + email)))):
                self.add(rid, where, '[redacted]', 'Name/E-Mail enthält privaten Term', 'name/e-mail contains a private term',
                         self.ident_hint(), group)
        if cfg.email_rx is None and email and not NOREPLY_EMAIL.fullmatch(email):
            self.add('A-G06', where, mask(email), 'keine GitHub-noreply-Adresse', 'not a GitHub noreply address',
                     'GitHub-noreply-Adresse nutzen (Settings > Emails) / use your GitHub noreply address (Settings > Emails)',
                     group, block=False)
        self.check_tz(where, tz)

    def check_tz(self, where, tz):
        if tz and tz not in ('+0000', '-0000'):
            self.add('A-G03', where, mask(tz), 'Zeitzone verrät den Aufenthaltsort', 'timezone reveals your location',
                     "mit TZ=UTC committen: TZ=UTC git commit … oder alias git='TZ=UTC git' / commit with TZ=UTC git commit … or an alias",
                     'tz:' + where, block=self.cfg.require_utc)

    def ident_line(self, where, value):
        name, email, tz = parse_ident(value)
        self.check_ident(where, name, email, tz)

    # ------------------------------------------------------------- result
    def finish(self):
        """Drop B hits covered by local 'allow:' lines (per file: at most <count> hits)."""
        if not self.terms.allow:
            return
        keep = []
        for f in self.findings:
            if f.rid.startswith('B-') and isinstance(f.group, int):
                path = self.units[f.group]
                cnt = self.b_count.get((f.rid, f.group), 0)
                if any(r == f.rid and fnmatch.fnmatchcase(path, g) and cnt <= mx for r, g, mx in self.terms.allow):
                    continue
            keep.append(f)
        self.findings = keep

    def b_hint(self, f):
        if isinstance(f.group, int):
            path = self.units[f.group]
            line = f.rid[2:].lstrip('0') or '0'
            return ('entfernen; Fehlalarm / remove it; false positive: LOKALE Liste / LOCAL list += "allow: %s %s %d"'
                    % (line, path, self.b_count.get((f.rid, f.group), 0)))
        return f.hint

    def report(self):
        shown, hidden, order, total = {}, {}, [], 0
        for f in self.findings:
            g = (f.rid, f.group)
            if shown.get(g, 0) >= PRINT_PER_GROUP or total >= PRINT_MAX:
                if g not in hidden:
                    order.append((g, f))
                hidden[g] = hidden.get(g, 0) + 1
                continue
            shown[g] = shown.get(g, 0) + 1
            total += 1
            level = 'BLOCKIERT / BLOCKED' if f.block else 'WARNUNG / WARNING'
            hint = self.b_hint(f) if f.hint == 'B' else f.hint
            print('%s  %s  %s  %s  %s / %s' % (level, f.rid, f.where, f.excerpt or '-', f.de, f.en))
            print('    -> %s' % hint)
        for i, (g, f) in enumerate(order):
            if i == 40:
                print('    … %d weitere Gruppen / more groups' % (len(order) - 40))
                break
            where = printable(self.units[f.group]) if isinstance(f.group, int) else f.where
            print('    … +%d %s  %s  (weitere Funde / more findings)' % (hidden[g], f.rid, where))
        blocking = sum(1 for f in self.findings if f.block)
        warnings = len(self.findings) - blocking
        scope = 'geprüft / checked: %d Dateien / files, %d Commits' % (self.files, self.commits)
        if blocking:
            print('privacy-gate: BLOCKIERT / BLOCKED - %d blockierend / blocking, %d Warnung(en) / warning(s) (%s)'
                  % (blocking, warnings, scope))
            return EXIT_BLOCKED
        print('privacy-gate: OK - %d Warnung(en) / warning(s) (%s)' % (warnings, scope))
        return EXIT_OK


_JSON_ARRAY_FLOAT = re.compile(r'([\[,]\s*)(-?\d+\.\d+(?:[eE][+-]?\d+)?)(?=\s*[,\]])')


def blank_json_floats(text):
    return _JSON_ARRAY_FLOAT.sub(lambda m: m.group(1) + ' ' * len(m.group(2)), text)


def text_pairs(text):
    """(lat, lon, offset) candidates for B geofences: plain pairs and lat/lon keyed pairs."""
    out = []
    has_lat = 'lat' in text.lower()
    for rx, rev in ((PAIR_ANY, False), (PAIR_KEYED, False), (PAIR_KEYED_REV, True)):
        if rx is not PAIR_ANY and not has_lat:
            continue
        for m in rx.finditer(text):
            try:
                a, b = float(m.group(1)), float(m.group(2))
            except ValueError:
                continue
            out.append((b, a, m.start()) if rev else (a, b, m.start()))
    return out


# ================================================================== git helpers
def git(args, cwd=None, inp=None, check=True):
    try:
        p = subprocess.run(['git'] + list(args), cwd=cwd, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        raise GitError('git nicht gefunden / git not found')
    if check and p.returncode != 0:
        raise GitError('git %s: %s' % (' '.join(args[:3]), p.stderr.decode('utf-8', 'replace').strip()[:300]))
    return p


def repo_top(cwd):
    try:
        p = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return None
    return p.stdout.decode('utf-8', 'replace').strip() if p.returncode == 0 else None


def batch_check(shas, top):
    info = {}
    if not shas:
        return info
    out = git(['cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)'], top,
              inp=('\n'.join(shas) + '\n').encode()).stdout.decode()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3:
            info[parts[0]] = (parts[1], int(parts[2]))
    return info


def cat_objects(shas, sizes, top, chunk=64 * MIB):
    """Yield (sha, bytes) for the given objects, reading at most ~chunk bytes per git call."""
    batch, total = [], 0
    for sha in list(shas) + [None]:
        if sha is not None:
            batch.append(sha)
            total += sizes.get(sha, 0)
            if total < chunk:
                continue
        if not batch:
            break
        out = git(['cat-file', '--batch'], top, inp=('\n'.join(batch) + '\n').encode()).stdout
        i = 0
        for s in batch:
            j = out.index(b'\n', i)
            hdr = out[i:j].split()
            if len(hdr) < 3:
                raise GitError('git cat-file: %s fehlt / missing' % s)
            size = int(hdr[2])
            yield s, out[j + 1:j + 1 + size]
            i = j + 1 + size + 1
        batch, total = [], 0


def parse_raw_diff(out, with_commits):
    """Parse -z --raw output (optionally with commit ids from diff-tree --stdin) -> [(commit, newmode, newsha, path)]."""
    toks = out.split(b'\0')
    res, cur, i = [], None, 0
    while i < len(toks):
        t = toks[i]
        if not t:
            i += 1
            continue
        if t.startswith(b':'):
            meta = t[1:].decode('ascii', 'replace').split()
            path = toks[i + 1].decode('utf-8', 'replace') if i + 1 < len(toks) else ''
            i += 2
            if len(meta) >= 5 and not meta[4].startswith('D'):
                res.append((cur, meta[1], meta[3], path))
        else:
            if with_commits:
                cur = t.decode('ascii', 'replace').strip()
            i += 1
    return res


def scan_blob_list(gate, entries, top):
    """entries: [(sha, path, sfx)] -> size check, read small enough blobs (streamed in chunks), scan them."""
    info = batch_check(sorted(set(sha for sha, _, _ in entries)), top)
    by_sha, order, sizes = {}, [], {}
    for sha, path, sfx in entries:
        typ, size = info.get(sha, ('missing', None))
        if typ == 'blob' and size <= size_limit(path):
            if sha not in by_sha:
                by_sha[sha] = []
                order.append(sha)
                sizes[sha] = size
            by_sha[sha].append((path, sfx))
        else:                                  # too large, missing or not a blob: path and size rules only
            gate.check_blob(path, None, size, sfx)
    for sha, data in cat_objects(order, sizes, top):
        for path, sfx in by_sha.pop(sha):
            gate.check_blob(path, data, len(data), sfx)


def scan_object_meta(gate, sha, typ, raw):
    text = raw.decode('utf-8', 'replace')
    head, _, msg = text.partition('\n\n')
    label = sha[:10]
    cur, tagname = None, None
    for line in head.split('\n'):
        if line.startswith(' '):
            if cur == 'mergetag' and line[1:].startswith('tagger '):
                gate.ident_line('%s mergetag tagger' % label, line[8:])
            continue
        key, _, val = line.partition(' ')
        cur = key
        if key in ('author', 'committer', 'tagger'):
            gate.ident_line('%s %s' % (label, key), val)
        elif key in ('gpgsig', 'gpgsig-sha256'):
            gate.add('A-G04', label, '-', 'signiertes Objekt', 'signed object',
                     'Signatur-UID prüfen (kein Klarname) / check the signing key UID (no real name)', 'sig:' + label, block=False)
        elif key == 'tag':
            tagname = val
    where = '%s message' % label
    if typ == 'tag':
        for marker in ('-----BEGIN PGP SIGNATURE-----', '-----BEGIN SSH SIGNATURE-----', '-----BEGIN SIGNED MESSAGE-----'):
            k = msg.find(marker)
            if k >= 0:
                msg = msg[:k]
                gate.add('A-G04', 'tag ' + printable(tagname or label), '-', 'signierter Tag', 'signed tag',
                         'Signatur-UID prüfen (kein Klarname) / check the signing key UID (no real name)', 'sig:' + label, block=False)
                break
        if tagname:
            gate.scan_refname('tag-object ' + tagname)
        where = 'tag %s message' % printable(tagname or label)
    gate.scan_message(where, msg)


def scan_history(gate, top, rng):
    """Scan everything reachable from rng (rev-list syntax): commit/tag metadata, messages, every path
    added or changed by those commits (including files added and deleted again) and every new blob."""
    listing = git(['rev-list', '--objects'] + rng, top).stdout.decode('utf-8', 'replace').splitlines()
    names = {}
    for line in listing:
        sha, _, name = line.partition(' ')
        if sha and sha not in names:
            names[sha] = name
    info = batch_check(list(names), top)
    commits = [s for s in names if info.get(s, ('',))[0] == 'commit']
    tags = [s for s in names if info.get(s, ('',))[0] == 'tag']
    new_blobs = set(s for s in names if info.get(s, ('',))[0] == 'blob')
    sizes = dict((s, info[s][1]) for s in commits + tags)
    types = dict((s, info[s][0]) for s in commits + tags)
    for sha, raw in cat_objects(commits + tags, sizes, top):
        scan_object_meta(gate, sha, types[sha], raw)
    gate.commits += len(commits)
    entries, seen, covered = [], set(), set()
    if commits:
        out = git(['diff-tree', '--stdin', '-r', '-z', '--root', '-m', '--no-renames', '--no-abbrev'], top,
                  inp=('\n'.join(commits) + '\n').encode()).stdout
        for commit, mode, sha, path in parse_raw_diff(out, True):
            if (sha, path) in seen:
                continue
            seen.add((sha, path))
            sfx = ' [%s]' % (commit or '')[:10]
            if mode == '160000' or sha not in new_blobs:
                unit = gate.new_unit(path)       # already public content or submodule: path rules only
                gate.check_path(path, None, unit, sfx)
                continue
            covered.add(sha)
            entries.append((sha, path, sfx))
    for sha in sorted(new_blobs - covered):     # e.g. blobs referenced directly by a tag
        entries.append((sha, names.get(sha) or '<blob %s>' % sha[:10], ''))
    scan_blob_list(gate, entries, top)


# ================================================================== modes
def load_allowlist_file(gate, root):
    p = os.path.join(root, ALLOWLIST_FILE)
    if os.path.isfile(p):
        with open(p, encoding='utf-8', errors='replace') as fh:
            gate.set_allowlist(fh.read(), ALLOWLIST_FILE)
    else:
        gate.allow = {}


def mode_staged(gate, top):
    p = git(['show', ':' + ALLOWLIST_FILE], top, check=False)
    if p.returncode == 0:
        gate.set_allowlist(p.stdout.decode('utf-8', 'replace'), ALLOWLIST_FILE + ' (Index/index)')
    else:
        load_allowlist_file(gate, top)
    for who, label in (('AUTHOR', 'author'), ('COMMITTER', 'committer')):
        p = git(['var', 'GIT_%s_IDENT' % who], top, check=False)
        if p.returncode != 0:
            gate.add('A-G05', '%s (git var)' % label, '-', 'Identität nicht ermittelbar', 'identity not available',
                     gate.ident_hint(), 'ident:' + label)
            continue
        gate.ident_line('%s (git var)' % label, p.stdout.decode('utf-8', 'replace'))
    out = git(['diff', '--cached', '--raw', '-z', '--no-renames', '--no-abbrev', '--diff-filter=ACMRT'], top).stdout
    entries = []
    for _c, mode, sha, path in parse_raw_diff(out, False):
        if mode == '160000':
            gate.check_path(path, None, gate.new_unit(path))
        else:
            entries.append((sha, path, ''))
    scan_blob_list(gate, entries, top)


def mode_commit_msg(gate, top, msgfile):
    try:
        with open(msgfile, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError:
        raise ConfigError('Nachrichtendatei nicht lesbar: %s' % msgfile, 'cannot read message file: %s' % msgfile)
    cc = '#'
    p = git(['config', '--get', 'core.commentChar'], top, check=False) if top else None
    if p is not None and p.returncode == 0:
        v = p.stdout.decode('utf-8', 'replace').strip()
        if v and v != 'auto':
            cc = v
    lines = []
    scissors = re.compile(r'^%s -+ >8 -+$' % re.escape(cc))
    for line in text.split('\n'):
        if scissors.match(line.rstrip()):
            break
        lines.append('' if line.startswith(cc) else line)
    gate.scan_message('commit message', '\n'.join(lines))


ZERO = re.compile(r'^0+$')


def mode_push(gate, top, remote):
    if sys.stdin.isatty():
        raise ConfigError('--push erwartet die pre-push-Eingabe von git auf stdin', '--push expects git pre-push input on stdin')
    load_allowlist_file(gate, top)
    tips, excl = [], []
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 4:
            raise ConfigError('unerwartete pre-push-Zeile', 'unexpected pre-push input line')
        lref, lsha, rref, rsha = parts
        gate.scan_refname(rref)
        if lref != rref:
            gate.scan_refname(lref)
        if ZERO.match(lsha):
            continue                              # deleting a remote ref publishes nothing
        tips.append(lsha)
        if not ZERO.match(rsha) and git(['cat-file', '-e', rsha], top, check=False).returncode == 0:
            excl.append('^' + rsha)
    if not tips:
        return
    rng = tips + excl + ['--not', '--remotes=%s' % remote if remote else '--remotes']
    scan_history(gate, top, rng)


def mode_all(gate, top):
    load_allowlist_file(gate, top)
    refs = git(['for-each-ref', '--format=%(refname)'], top).stdout.decode('utf-8', 'replace').splitlines()
    for r in refs:
        if r != 'refs/stash':
            gate.scan_refname(r)
    scan_history(gate, top, ['--exclude=refs/stash', '--all'])


def read_path_file(full):
    """-> (size, bytes or None). Symlinks yield their target (that is what git stores)."""
    st = os.lstat(full)
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(full).encode('utf-8', 'surrogateescape')
        return len(target), target
    if not stat.S_ISREG(st.st_mode):
        return None, None
    return st.st_size, None


def mode_paths(gate, paths, top):
    """Files and folders on disk, git not required. Paths are reported relative to the repository root (or the
    current folder). A folder that has its own .privacy-allowlist or .git, or lies outside that root, is scanned
    as a tree of its own: paths relative to it, its allowlist applies, its top-level .git is skipped."""
    default_root = os.path.abspath(top or os.getcwd())
    for arg in paths:
        if not os.path.lexists(arg):
            raise ConfigError('Pfad nicht gefunden: %s' % arg, 'path not found: %s' % arg)
        full = os.path.abspath(arg)
        inside = full == default_root or full.startswith(default_root.rstrip(os.sep) + os.sep)
        is_dir = os.path.isdir(full) and not os.path.islink(full)
        if is_dir and (not inside or full == default_root or os.path.lexists(os.path.join(full, ALLOWLIST_FILE))
                       or os.path.lexists(os.path.join(full, '.git'))):
            base = full
        elif inside:
            base = default_root
        else:
            base = os.path.dirname(full)
        load_allowlist_file(gate, base if os.path.isfile(os.path.join(base, ALLOWLIST_FILE)) else default_root)
        items = []
        if is_dir:
            for dirpath, dirs, fnames in os.walk(full):
                if os.path.relpath(dirpath, base) == '.':      # only the tree's own top-level .git is skipped
                    dirs[:] = [d for d in dirs if d != '.git']
                    fnames = [f for f in fnames if f != '.git']
                for d in list(dirs):
                    if os.path.islink(os.path.join(dirpath, d)):
                        dirs.remove(d)
                        fnames.append(d)
                dirs.sort()
                for fn in sorted(fnames):
                    f = os.path.join(dirpath, fn)
                    items.append((f, os.path.relpath(f, base).replace(os.sep, '/')))
        else:
            items.append((full, os.path.relpath(full, base).replace(os.sep, '/')))
        for f, rel in items:
            try:
                size, data = read_path_file(f)
                if size is None:
                    gate.files += 1
                    gate.add('A-F03', printable(rel), '', 'Sonderdatei (kein normaler Inhalt)', 'special file (not regular)',
                             'entfernen / remove it', gate.new_unit(rel))
                    continue
                if data is None and size <= size_limit(rel):
                    with open(f, 'rb') as fh:
                        data = fh.read()
                gate.check_blob(rel, data, size)
            except OSError:
                gate.files += 1
                gate.add('A-F03', printable(rel), '', 'Datei nicht lesbar', 'file not readable',
                         'Rechte prüfen oder entfernen / fix permissions or remove it', gate.new_unit(rel))


# ================================================================== main
def parse_args(argv):
    opts = {'mode': None, 'require': False, 'msgfile': None, 'remote': None, 'paths': []}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('-h', '--help'):
            print(HELP)
            raise SystemExit(EXIT_OK)
        if a == '--version':
            print('privacy_gate.py %s' % VERSION)
            raise SystemExit(EXIT_OK)
        if a == '--require-denylist':
            opts['require'] = True
        elif a in ('--staged', '--all', '--push', '--commit-msg', '--paths'):
            if opts['mode']:
                raise ConfigError('nur ein Modus erlaubt', 'only one mode allowed')
            opts['mode'] = a
            if a == '--commit-msg':
                if i + 1 >= len(argv):
                    raise ConfigError('--commit-msg braucht eine Datei', '--commit-msg needs a file')
                opts['msgfile'] = argv[i + 1]
                i += 1
            elif a == '--push' and i + 1 < len(argv) and not argv[i + 1].startswith('-'):
                opts['remote'] = argv[i + 1]
                i += 1
            elif a == '--paths':
                while i + 1 < len(argv) and argv[i + 1] != '--require-denylist':
                    opts['paths'].append(argv[i + 1])
                    i += 1
                if not opts['paths']:
                    raise ConfigError('--paths braucht mindestens einen Pfad', '--paths needs at least one path')
        else:
            raise ConfigError('unbekannte Option %s (siehe --help)' % printable(a), 'unknown option %s (see --help)' % printable(a))
        i += 1
    if not opts['mode']:
        raise ConfigError('kein Modus angegeben (siehe --help)', 'no mode given (see --help)')
    return opts


def run(argv):
    opts = parse_args(argv)
    mode = opts['mode']
    top = repo_top(os.getcwd())
    if mode != '--paths' and not top:
        raise ConfigError('kein Git-Repository', 'not a git repository')
    gitcfg = read_git_config(top or os.getcwd())
    cfg = Config(gitcfg, opts['require'])
    notes = []
    terms = load_terms(gitcfg, top, cfg.require_denylist, notes)
    for n in notes:
        print('privacy-gate: ' + n)
    if terms.count:
        print('privacy-gate: Term-Liste / term list: %d Regeln / rules (%s)' % (terms.count, short_home(terms.path)))
    gate = Gate(cfg, terms, history=mode in ('--push', '--all'))
    if mode == '--staged':
        mode_staged(gate, top)
    elif mode == '--commit-msg':
        mode_commit_msg(gate, top, opts['msgfile'])
    elif mode == '--push':
        mode_push(gate, top, opts['remote'])
    elif mode == '--all':
        mode_all(gate, top)
    else:
        mode_paths(gate, opts['paths'], top)
    gate.finish()
    return gate.report()


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors='backslashreplace')
        except (AttributeError, ValueError):
            pass
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except ConfigError as e:
        print('privacy-gate: FEHLER / ERROR: %s' % e, file=sys.stderr)
        return EXIT_CONFIG
    except GitError as e:
        print('privacy-gate: FEHLER / ERROR: git: %s' % e, file=sys.stderr)
        return EXIT_CONFIG


if __name__ == '__main__':
    sys.exit(main())
