#!/usr/bin/env python3
"""
Safari Assistant — lokaler Server (Stand 2026-10-06-1)
(Creator: DARK; Name seit 2026-10-05 in englischer Schreibweise, kurz davor „DARK", in der Entwicklung „Safari Assistent")
Port 8765
- Statische Dateien (HTML/JS)
- Klimatologie für die Regenzeit-Ebene (/data/klima.json — Datei aus fetch-klima.py, NASA POWER)
- Dokument-API (/api/docs/...)
- MBTiles Karten-API (/api/tiles/...)
- Kiwix Offline-Wikipedia (/api/kiwix/status + Autostart kiwix-serve :8090)
- Wiki-RAG (/api/wiki/search — Kiwix-Volltextsuche + Artikel-Auszüge für die Chat-Module)
- Offline-Ortssuche (/api/orte/search — GeoNames-Index aus data/orte.json, fetch-orte.py)
- Hilfe (/hilfe?lang=de|en|fr|es — die Anleitung README*.md als Seite, offline; hilfe.py, 2026-10-04-1)
- Sicherheit (2026-09-05-1): Pfad-Härtung der Dokument-API (kein ../ mehr), Größenlimits für alle
  POST-Bodies, schreibende Endpunkte nur noch vom Mac selbst (Loopback + eigener Origin),
  CORS nur für lokale Origins.
- iPhone-Modus (2026-09-12-1): der Server lauscht IMMER nur auf 127.0.0.1. Der WLAN-Zugang wird zur
  Laufzeit per Knopf in der App geöffnet (zweiter Listener auf der Mac-IP, /api/netz/an) und wieder
  geschlossen (/api/netz/aus); mit dem Server endet er automatisch, beim Start ist er nie an.
  Anfragen aus dem WLAN brauchen einen Zugangscode (Cookie/URL), Ollama bleibt auf 127.0.0.1 und
  wird für das iPhone durch den Server geproxyt (/api/ollama/api/chat, /api/ollama/api/tags).
- 2026-09-13-1: iPhone-Modus schaltet nach 12 h ohne Anfrage automatisch ab (einschalten bleibt
  eine bewusste Entscheidung); Reisewarn-Pipeline (Auswärtiges Amt, UK FCDO, US State Department)
  holt die amtlichen Warnungen, sobald Netz da ist, und hält sie offline bereit.
- Re-Audit 2026-09-12: Host-Header-Prüfung (DNS-Rebinding), Mutationen nur same-origin, statische
  Auslieferung nur für die App-Dateien (kein .git/rag-store/Verzeichnislisting), Verbindungs-Timeout
  und Thread-Obergrenze (Slowloris), Seitenlimit im PDF-Extraktor, keine internen Fehlertexte nach außen.
"""

import errno
import os
import sys
import time
import urllib.error
import urllib.request
import json
import shutil
import signal
import socket
import sqlite3
import ssl
import struct
import subprocess
import zlib
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import threading

import platform
import re as _re
import html as _html
import secrets

# Basis-Verzeichnis = Ordner dieser Datei
BASE_DIR = Path(__file__).parent.resolve()
DOCS_DIR = BASE_DIR / 'docs'
DOCS_DIR.mkdir(exist_ok=True)

# ── INSTANZ-VERWALTUNG (2026-09-11-1) ─────────────────────────
# Problem aus der Praxis: Wird die App hart beendet (Force-Quit, Absturz, Ruhezustand), überlebt
# der Python-Server als Waise. Beim nächsten Start war Port 8765 belegt; der Launcher wich still
# auf 8766 aus, und der Browser landete auf einer Adresse, unter der nichts antwortete — ein
# Fehlerbild, das sich nur mit `lsof` im Terminal auflösen ließ. Drei Maßnahmen dagegen:
#   1. Laufzeitdatei: jede Instanz hinterlegt PID, Port und Bindung — so ist eine Altinstanz
#      auch dann identifizierbar, wenn sie nicht mehr auf HTTP antwortet.
#   2. /api/ping: eindeutige Kennung des Servers, damit fremde Software auf demselben Port
#      niemals versehentlich abgeschossen wird.
#   3. Eltern-Wache (nur aus der .app): stirbt der Launcher, beendet sich der Server mit.
APP_SIGNATUR = 'safari-assistent'
SERVER_VERSION = '2026-10-06-1'
# Kennung gegenüber fremden Diensten (Reisewarnungen, Overpass, …) — mit Projektadresse, wie es deren
# Nutzungsregeln verlangen; viele Installationen teilen sie sich (2026-09-27).
PROJEKT_UA = 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant)'
RUNTIME_DATEI = Path.home() / '.safari-assistant-runtime.json'
# 2026-09-27 (Audit M1): Logs nicht mehr unter /tmp (für alle Konten lesbar, feste Namen → Symlink-
# Falle), sondern in ~/Library/Logs/Safari Assistant mit Rechten nur für den Nutzer. Der Launcher schreibt dorthin.
# 2026-10-04-2: Ordner heißt wie die App (vorher ~/Library/Logs/DARK); die Umgebungsvariable DARK_LOG_DIR bleibt.
LOG_DIR = Path(os.environ.get('DARK_LOG_DIR') or (Path.home() / 'Library' / 'Logs' / 'Safari Assistant'))

def log_datei(name):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        pass
    return LOG_DIR / name

def _log_oeffnen(name):
    """Logdatei zum Anhängen öffnen: 0600, folgt keinem Symlink."""
    fd = os.open(str(log_datei(name)), os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    return os.fdopen(fd, 'ab')
SERVER_INFO = {}          # wird in main() gefüllt, /api/ping liefert es aus
START_ZEIT = time.time()

def schreibe_privat(pfad, text):
    """Datei mit Rechten 0600 anlegen/überschreiben — andere Konten auf demselben Mac lesen sie nicht."""
    fd = os.open(str(pfad), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    try:
        os.chmod(str(pfad), 0o600)
    except OSError:
        pass

def runtime_schreiben(port, bind):
    try:
        schreibe_privat(RUNTIME_DATEI, json.dumps({
            'app': APP_SIGNATUR, 'pid': os.getpid(), 'port': port, 'bind': bind,
            'basis': str(BASE_DIR), 'seit': time.strftime('%Y-%m-%d %H:%M:%S')}))
    except OSError:
        pass  # nur eine Hilfe, kein Muss — ein nicht schreibbares Home darf den Start nicht verhindern

def runtime_lesen():
    try:
        return json.loads(RUNTIME_DATEI.read_text(encoding='utf-8'))
    except Exception:
        return None

def runtime_entfernen():
    d = runtime_lesen()
    if d and d.get('pid') == os.getpid():
        try:
            RUNTIME_DATEI.unlink()
        except OSError:
            pass

def lan_ip():
    """Beste Vermutung für die IP dieses Macs im lokalen Netz — für die iPhone-Adresse.
    Der UDP-„connect" SENDET nichts, er lässt nur den Kernel die Route wählen; das funktioniert
    darum auch am Travel-Router ohne Internet. Ohne Default-Route bleibt es leer."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(0.5)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith('127.'):
            return ip
    except OSError:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return '' if ip.startswith('127.') else ip
    except OSError:
        return ''


def port_belegt_von(port, timeout=1.5):
    """Wer hält den Port? dict = unsere eigene Instanz (Antwort von /api/ping),
    'fremd' = spricht HTTP, ist aber nicht unsere App, None = keine Antwort (hängend/kein HTTP)."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=timeout) as r:
            daten = json.loads(r.read().decode('utf-8'))
            return daten if daten.get('app') == APP_SIGNATUR else 'fremd'
    except urllib.error.HTTPError:
        return 'fremd'          # antwortet, kennt aber /api/ping nicht → andere Software
    except Exception:
        return None             # Zeitüberschreitung/Verbindung zu: hängender Prozess oder kein HTTP

def ist_eigener_server_alt(port, timeout=1.5):
    """Ältere Versionen (vor 2026-09-11-1) kennen /api/ping nicht und gälten damit als „fremd" —
    beim Umstieg würde der neue Server also unnötig auf einen Ausweichport gehen. Sie haben aber
    /api/tiles/status, und diesen Endpunkt bedient sonst keine Software."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/tiles/status', timeout=timeout) as r:
            d = json.loads(r.read().decode('utf-8'))
        return isinstance(d, dict) and 'available' in d
    except Exception:
        return False

def pid_auf_port(port):
    """PID des lauschenden Prozesses über lsof — nötig für Altversionen, die keine PID melden."""
    try:
        aus = subprocess.run(['lsof', '-ti', f'tcp:{port}', '-sTCP:LISTEN'],
                             capture_output=True, text=True, timeout=5).stdout.split()
        return int(aus[0]) if aus else None
    except Exception:
        return None

_UNSER_PROZESS = _re.compile(r'(^|/)python[0-9.]*\s+(?!-)([^\n]*?/)?server\.py(\s|$)')   # Interpreter, dann (Pfad, auch mit Leerzeichen)/server.py — kein -c

def ist_unser_prozess(pid):
    """Schutz vor wiederverwendeten PIDs: nur beenden, wenn dort wirklich ein Python mit server.py
    läuft — nicht `vim server.py`, nicht `tail server.py.log`, nicht `python3 anderer_server.py`
    (Re-Audit 2026-09-12: der frühere Substring-Test 'server.py' war zu lose)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 1:
        return False
    try:
        aus = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                             capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return False
    return bool(_UNSER_PROZESS.search(aus))

def alte_instanz_beenden(port):
    """Räumt eine eigene Altinstanz auf diesem Port ab. True, wenn der Port danach frei sein sollte."""
    info = port_belegt_von(port)
    alt = False
    if info == 'fremd':
        # Zweite Chance für Altversionen: /api/ping gibt es erst ab 2026-09-11-1.
        if not ist_eigener_server_alt(port):
            return False        # wirklich fremde Software — niemals abschießen
        alt = True
        info = None
    pid = info.get('pid') if isinstance(info, dict) else None
    if pid is None and alt:     # Altversion meldet keine PID → über den Port ermitteln
        pid = pid_auf_port(port)
    if pid is None:             # keine Antwort → Laufzeitdatei befragen
        rt = runtime_lesen()
        if rt and rt.get('port') == port and rt.get('app') == APP_SIGNATUR:
            pid = rt.get('pid')
    if not pid or pid == os.getpid() or not ist_unser_prozess(pid):
        return False
    print(f'♻️  Port {port} wird noch von einer älteren Instanz dieses Servers gehalten (PID {pid}) —')
    print( '   vermutlich ein Rest eines hart beendeten App-Starts' + (' oder eine Version vor 2026-09-11-1' if alt else '') + '. Wird beendet und übernommen.')
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(20):         # bis zu 5 s auf sauberes Beenden warten
        time.sleep(0.25)
        try:
            os.kill(pid, 0)
        except OSError:
            return True
    try:                        # reagiert nicht → hart beenden
        print(f'   PID {pid} reagiert nicht auf SIGTERM — wird hart beendet.')
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.5)
    except OSError:
        pass
    return True

def starte_eltern_wache():
    """Nur aus der .app (SAFARI_PARENT_WATCH=1): stirbt der Launcher, beendet sich der Server mit.
    Das ist die eigentliche Wurzel — ohne sie entstehen bei jedem Force-Quit neue Waisen."""
    if os.environ.get('SAFARI_PARENT_WATCH') != '1':
        return
    eltern = os.getppid()
    if eltern <= 1:
        return
    def wache():
        while True:
            time.sleep(2)
            if os.getppid() != eltern:
                print('🛑 App-Launcher ist beendet — Server beendet sich mit (keine Waise).')
                stoppe_kiwix()
                runtime_entfernen()
                os._exit(0)
    threading.Thread(target=wache, daemon=True).start()


# ── LOKALES HTTPS FÜR DAS iPHONE (2026-09-14-1) ───────────────
# Warum: Safari am iPhone blockt reine http://-Adressen, sobald der HTTPS-Only-Modus an ist —
# der Zugang scheiterte, bevor überhaupt eine Verbindung zustande kam. Ohne sicheren Kontext gibt
# iOS außerdem kein GPS an mobile.html frei. Beides löst ein eigenes Zertifikat.
#
# Aufbau: eine lokale CA (bleibt, wird EINMAL aufs iPhone geladen) signiert ein Serverzertifikat,
# das automatisch neu ausgestellt wird, sobald sich die Adressen des Macs ändern (Starlink ↔
# iPhone-Hotspot). Dadurch muss am iPhone nie wieder etwas installiert werden.
# Die Hauptadresse ist der Bonjour-Name (`<mac>.local`) — der bleibt in jedem Netz gleich, anders
# als die IP; damit überlebt auch das Home-Bildschirm-Icon den Netzwechsel.
# Loopback bleibt bewusst http://localhost:8765: localhost gilt im Browser ohnehin als sicherer
# Kontext, und Launcher, Instanz-Übernahme und Lesezeichen bleiben unverändert.
#
# Anforderungen von Apple an Serverzertifikate (iOS 13+), hier alle erfüllt: SAN vorhanden (ein
# Common Name allein genügt nicht), Laufzeit höchstens 825 Tage, SHA-256, RSA ≥ 2048,
# ExtendedKeyUsage serverAuth. Die CA trägt zusätzlich Namensbeschränkungen: sie kann nur für
# `.local` und private IP-Bereiche gültige Zertifikate ausstellen — wird ihr Schlüssel gestohlen,
# taugt er nicht, um dem iPhone eine beliebige Webseite vorzuspielen. Stufen siehe TLS_STUFEN;
# ganz ohne Beschränkung nur auf ausdrücklichen Wunsch: SAFARI_TLS_OHNE_CONSTRAINTS=1.
TLS_DIR = Path.home() / '.safari-assistant-tls'
TLS_CA_KEY = TLS_DIR / 'ca.key'
TLS_CA_CRT = TLS_DIR / 'safari-assistent-ca.crt'      # diese Datei kommt aufs iPhone
TLS_SRV_KEY = TLS_DIR / 'server.key'
TLS_SRV_CRT = TLS_DIR / 'server.crt'
TLS_MERKMALE = TLS_DIR / 'adressen.json'              # wofür das aktuelle Zertifikat ausgestellt ist
TLS_CA_TAGE = 825                                      # 2026-09-27 (Audit H3): vorher 3650 — ein gestohlener
                                                       # CA-Schlüssel taugte zehn Jahre; gilt nur für NEUE CAs
TLS_SRV_TAGE = 820                                     # unter Apples Grenze von 825
TLS_STATE = {'aktiv': False, 'grund': '', 'namen': [], 'ips': [], 'fingerabdruck': '', 'gueltig_bis': '',
             'constraints': True, 'stufe': '', 'ca_name': '', 'ca_neu': False, 'selbsttest': ''}
# Stufen der Namensbeschränkung der CA (2026-09-27, Audit H3):
#   'voll' — nur .local/localhost UND die privaten Netze aus TLS_NETZE
#   'dns'  — nur .local/localhost; IP-Adressen bleiben unbeschränkt. Ältere Krypto-Bibliotheken
#            (LibreSSL im Python von macOS) kennen keine IP-Beschränkung und melden „unsupported
#            name constraint type" — das war der Fehler vom 15.09.2026.
#   'aus'  — keine Beschränkung. Nur per SAFARI_TLS_OHNE_CONSTRAINTS=1, NIE automatisch: vorher
#            wurde bei jedem Fehlschlag des Selbsttests still eine unbeschränkte CA erzeugt.
TLS_STUFEN = ('voll', 'dns', 'aus')


def openssl_pfad():
    return shutil.which('openssl') or ('/usr/bin/openssl' if Path('/usr/bin/openssl').exists() else '')


def _openssl(args, timeout=60):
    exe = openssl_pfad()
    if not exe:
        raise OSError('openssl nicht gefunden')
    p = subprocess.run([exe] + args, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise OSError(f'openssl {args[0]}: {(p.stderr or p.stdout).strip()[:300]}')
    return p.stdout


_BONJOUR = {'wert': None, 'zeit': 0.0}     # Zwischenspeicher: eigene_hosts() fragt bei jeder Anfrage


def _local_hostname_macos():
    """Bonjour-Name aus den Systemeinstellungen (Allgemein → Freigaben → Lokaler Hostname), ohne „.local".
    '' wenn nicht macOS oder nicht ermittelbar."""
    exe = shutil.which('scutil') or ('/usr/sbin/scutil' if Path('/usr/sbin/scutil').exists() else '')
    if not exe:
        return ''
    try:
        p = subprocess.run([exe, '--get', 'LocalHostName'], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ''
    name = (p.stdout or '').strip() if p.returncode == 0 else ''
    return name if _re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', name) else ''


def _bonjour_name_ermitteln():
    lokal = _local_hostname_macos()
    if lokal:
        return lokal.lower() + '.local'
    try:
        name = socket.gethostname().strip().rstrip('.').lower()
    except OSError:
        return ''
    if not name or name.startswith('localhost'):
        return ''
    if '.' not in name:
        return name + '.local'
    if name.endswith('.local'):
        return name
    # Ein Name aus dem DNS des Routers (z. B. „…fritz.box") gilt nur in diesem einen Netz und liegt
    # außerhalb dessen, wofür die lokale CA ausstellen darf — dann lieber kein Name (Adresse per IP).
    return ''


def bonjour_name():
    """Der Name, unter dem der Mac im lokalen Netz per Bonjour erreichbar ist (<Lokaler Hostname>.local) —
    bleibt beim Netzwechsel gleich.
    2026-10-06-1: nicht mehr einfach socket.gethostname(). Das liefert unter macOS den Namen, den der
    Router per DHCP/DNS vergibt, sobald es einen gibt (z. B. „<uuid>.fritz.box"). Der landete im
    Serverzertifikat, verletzte die Namensbeschränkung der CA (.local) — „permitted subtree violation",
    das iPhone hätte die Verbindung abgelehnt — und wäre in einem anderen Netz ohnehin nicht erreichbar
    gewesen."""
    jetzt = time.time()
    if _BONJOUR['wert'] is not None and jetzt - _BONJOUR['zeit'] < 300:
        return _BONJOUR['wert']
    wert = _bonjour_name_ermitteln()
    _BONJOUR.update(wert=wert, zeit=jetzt)
    return wert


def tls_name_erlaubt(name):
    """Darf dieser Name ins Serverzertifikat? Nur was die Namensbeschränkung der CA abdeckt
    (.local und localhost) — das Gegenstück zu tls_ip_erlaubt für Namen (2026-10-06-1)."""
    name = (name or '').strip().lower()
    return name == 'localhost' or (name.endswith('.local') and len(name) > len('.local')
                                   and not name.startswith('.'))


# Netze, für die die lokale CA Zertifikate ausstellen darf. Dieselbe Liste erzeugt die
# Namensbeschränkung IM CA-Zertifikat und filtert die Adressen im Serverzertifikat — sonst stünde
# im Zertifikat eine Adresse, die die eigene CA laut ihrer Beschränkung gar nicht abdecken darf,
# und das iPhone lehnte die Verbindung ab. 100.64/10 ist bewusst dabei (Mobilfunk/Starlink-CGNAT).
TLS_NETZE = [('127.0.0.0', '255.0.0.0'), ('10.0.0.0', '255.0.0.0'), ('172.16.0.0', '255.240.0.0'),
             ('192.168.0.0', '255.255.0.0'), ('100.64.0.0', '255.192.0.0')]


def _als_zahl(ip):
    try:
        teile = [int(t) for t in ip.split('.')]
    except ValueError:
        return None
    if len(teile) != 4 or any(t < 0 or t > 255 for t in teile):
        return None
    return (teile[0] << 24) | (teile[1] << 16) | (teile[2] << 8) | teile[3]


def tls_ip_erlaubt(ip):
    """Darf diese Adresse ins Zertifikat? Nur was die Namensbeschränkung der CA auch zulässt."""
    wert = _als_zahl(ip)
    if wert is None:
        return False
    for netz, maske in TLS_NETZE:
        n, mk = _als_zahl(netz), _als_zahl(maske)
        if n is not None and mk is not None and (wert & mk) == n:
            return True
    return False


def lokale_ips():
    """Alle lokalen IPv4-Adressen dieses Rechners — nicht nur die der Standardroute. Am Hotspot
    (172.20.10.x) und am Starlink-WLAN gleichzeitig hat der Mac zwei; das Zertifikat deckt beide ab.
    Adressen außerhalb der erlaubten Netze bleiben draußen (siehe TLS_NETZE)."""
    gefunden = []
    for befehl in (['ifconfig'], ['ip', '-4', '-o', 'addr']):
        try:
            p = subprocess.run(befehl, capture_output=True, text=True, timeout=8)
        except (OSError, subprocess.SubprocessError):
            continue
        if p.returncode != 0:
            continue
        for treffer in _re.finditer(r'inet\s+(\d+\.\d+\.\d+\.\d+)', p.stdout):
            ip = treffer.group(1)
            if ip.startswith('127.') or ip.startswith('169.254.') or ip in gefunden:
                continue
            if tls_ip_erlaubt(ip):
                gefunden.append(ip)
        if gefunden:
            break
    aktuell = lan_ip()
    if aktuell and aktuell not in gefunden and tls_ip_erlaubt(aktuell):
        gefunden.insert(0, aktuell)
    return gefunden


def _config(namen, ips, stufe=None):
    """openssl-Konfiguration als Text — als Datei übergeben, damit es auch mit dem LibreSSL von
    macOS funktioniert (dort fehlt -addext in älteren Versionen). `stufe` siehe TLS_STUFEN."""
    if stufe is None:
        stufe = 'aus' if os.environ.get('SAFARI_TLS_OHNE_CONSTRAINTS') == '1' else 'voll'
    alt = '\n'.join([f'DNS.{i + 1} = {n}' for i, n in enumerate(namen)]
                    + [f'IP.{i + 1} = {p}' for i, p in enumerate(ips)])
    netze = ','.join(f'permitted;IP:{n}/{m}' for n, m in TLS_NETZE)
    if stufe == 'voll':
        nc = 'nameConstraints = critical,permitted;DNS:.local,permitted;DNS:localhost,' + netze + '\n'
    elif stufe == 'dns':
        nc = 'nameConstraints = critical,permitted;DNS:.local,permitted;DNS:localhost\n'
    else:
        nc = ''
    return f"""[req]
distinguished_name = dn
prompt = no
[dn]
CN = {namen[0] if namen else 'localhost'}
O = Safari Assistant
[ca_ext]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
{nc}[srv_ext]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = @alt
[alt]
{alt}
"""


def _privat_machen(*pfade):
    for p in pfade:
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass


def ca_erzeugen(cfg_pfad):
    """Die lokale CA — einmalig. Sie wird aufs iPhone geladen und bleibt dort; nur sie muss
    vertraut werden, das Serverzertifikat darunter darf sich beliebig oft ändern."""
    if TLS_CA_KEY.exists() and TLS_CA_CRT.exists():
        return False
    TLS_DIR.mkdir(mode=0o700, exist_ok=True)
    _openssl(['req', '-x509', '-new', '-nodes', '-newkey', 'rsa:2048', '-sha256',
              '-days', str(TLS_CA_TAGE), '-keyout', str(TLS_CA_KEY), '-out', str(TLS_CA_CRT),
              '-subj', '/CN=Safari Assistant lokale CA/O=Safari Assistant',
              '-config', cfg_pfad, '-extensions', 'ca_ext'])
    _privat_machen(TLS_CA_KEY)
    try:
        os.chmod(TLS_CA_CRT, 0o644)     # das Zertifikat ist öffentlich — es soll aufs iPhone
    except OSError:
        pass
    print(f'🔐 Lokale CA angelegt: {TLS_CA_CRT}')
    return True


def leaf_erzeugen(namen, ips, cfg_pfad):
    """Serverzertifikat für die aktuellen Adressen, signiert von der lokalen CA."""
    csr = TLS_DIR / 'server.csr'
    _openssl(['req', '-new', '-nodes', '-newkey', 'rsa:2048', '-sha256',
              '-keyout', str(TLS_SRV_KEY), '-out', str(csr),
              '-subj', f'/CN={namen[0]}/O=Safari Assistant', '-config', cfg_pfad])
    _openssl(['x509', '-req', '-in', str(csr), '-CA', str(TLS_CA_CRT), '-CAkey', str(TLS_CA_KEY),
              '-CAcreateserial', '-out', str(TLS_SRV_CRT), '-days', str(TLS_SRV_TAGE),
              '-sha256', '-extfile', cfg_pfad, '-extensions', 'srv_ext'])
    _privat_machen(TLS_SRV_KEY, TLS_DIR / 'ca.srl', TLS_CA_CRT.with_suffix('.srl'))
    try:
        csr.unlink()
    except OSError:
        pass
    print(f'🔐 Serverzertifikat ausgestellt für: {", ".join(namen + ips)}')


def tls_merkmale_gespeichert():
    try:
        d = json.loads(TLS_MERKMALE.read_text(encoding='utf-8'))
        return list(d.get('namen') or []), list(d.get('ips') or [])
    except (OSError, ValueError):
        return [], []


def _tls_dateien(mit_ca=True):
    # openssl -CAcreateserial legt die Seriennummern-Datei neben die CA: <CA-Name>.srl
    dateien = [TLS_SRV_CRT, TLS_SRV_KEY, TLS_DIR / 'ca.srl', TLS_CA_CRT.with_suffix('.srl'), TLS_MERKMALE]
    return ([TLS_CA_KEY, TLS_CA_CRT] if mit_ca else []) + dateien


def _ca_beiseitelegen(grund):
    """Alte CA nicht löschen, sondern umbenennen (…-<grund>-<Datum>) — sie könnte noch gebraucht werden."""
    stempel = time.strftime('%Y%m%d-%H%M%S')
    for datei in (TLS_CA_KEY, TLS_CA_CRT):
        try:
            datei.rename(datei.with_name(f'{datei.name}.{grund}-{stempel}'))
        except OSError:
            pass
    for datei in _tls_dateien(mit_ca=False):
        try:
            datei.unlink()
        except OSError:
            pass


def tls_ca_merkmale():
    """Liest aus dem CA-Zertifikat, was wirklich drinsteht: Stufe der Namensbeschränkung und Name.
    Ein Merker im Speicher zeigte nach einem Neustart das Falsche an (Audit H3)."""
    try:
        text = _openssl(['x509', '-noout', '-text', '-in', str(TLS_CA_CRT)])
    except (OSError, subprocess.SubprocessError):
        return '', ''
    stufe = 'aus'
    if 'Name Constraints' in text:
        teil = text.split('Name Constraints', 1)[1]
        teil = _re.split(r'\n\s*(?:X509v3 [A-Z]|Signature Algorithm|Signature Value)', teil, maxsplit=1)[0]
        stufe = 'voll' if 'IP:' in teil else 'dns'
    m = _re.search(r'Subject:[^\n]*?CN\s*=\s*([^,\n/]+)', text)
    return stufe, (m.group(1).strip() if m else '')


def tls_vorbereiten():
    """Stellt sicher, dass CA und passendes Serverzertifikat vorliegen. Liefert (kontext, grund).
    kontext=None heißt: HTTPS geht nicht — der Grund wird dem Nutzer angezeigt, nie verschwiegen."""
    if os.environ.get('SAFARI_OHNE_TLS') == '1':
        return None, 'Per SAFARI_OHNE_TLS=1 abgeschaltet — der iPhone-Zugang läuft unverschlüsselt.'
    if not openssl_pfad():
        return None, 'openssl nicht gefunden — der iPhone-Zugang läuft unverschlüsselt (http).'
    name = bonjour_name()
    namen = [n for n in [name, 'localhost'] if n and tls_name_erlaubt(n)]
    ips = lokale_ips()
    if not namen:
        return None, 'Kein Netzwerkname für diesen Mac ermittelbar.'
    try:
        TLS_DIR.mkdir(mode=0o700, exist_ok=True)
        # Läuft die CA in weniger als 30 Tagen ab, wird sie ersetzt (die alte bleibt umbenannt
        # liegen) — ein still abgelaufenes Zertifikat wäre unterwegs ein Ausfall ohne Grund.
        # Das iPhone braucht danach einmal das neue Profil; die Einstellungen sagen es.
        if TLS_CA_CRT.exists() and TLS_CA_KEY.exists() and tls_laeuft_bald_ab(datei=TLS_CA_CRT):
            print('🔐 Die lokale CA läuft bald ab — neue CA wird erzeugt (iPhone: Profil einmal neu installieren).')
            _ca_beiseitelegen('abgelaufen')

        def bauen(stufe, erzwingen=False):
            cfg = TLS_DIR / 'openssl.cnf'
            cfg.write_text(_config(namen, ips + ['127.0.0.1'], stufe), encoding='utf-8')
            neu_ca = ca_erzeugen(str(cfg))
            alt_namen, alt_ips = tls_merkmale_gespeichert()
            fehlt = not (TLS_SRV_CRT.exists() and TLS_SRV_KEY.exists())
            if erzwingen or neu_ca or fehlt or alt_namen != namen or alt_ips != ips or tls_laeuft_bald_ab():
                leaf_erzeugen(namen, ips, str(cfg))
                TLS_MERKMALE.write_text(json.dumps({'namen': namen, 'ips': ips}), encoding='utf-8')
            k = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            k.load_cert_chain(certfile=str(TLS_SRV_CRT), keyfile=str(TLS_SRV_KEY))
            k.minimum_version = ssl.TLSVersion.TLSv1_2
            return k, neu_ca

        wunsch = 'aus' if os.environ.get('SAFARI_TLS_OHNE_CONSTRAINTS') == '1' else 'voll'
        ctx, neu_ca = bauen(wunsch)
        probe = tls_selbsttest(ctx, namen[0])
        # Nur „unsupported … constraint" heißt: die Krypto hier kennt die IP-Beschränkung nicht. Eine
        # „permitted subtree violation" heißt dagegen: im Zertifikat steht etwas außerhalb der
        # Beschränkung — das behebt eine Herabstufung nicht, sie schwächte nur die CA (2026-10-06-1).
        if probe and neu_ca and wunsch == 'voll' and _re.search(r'unsupported[^|]*constraint', probe, _re.I):
            # Nur eine GERADE erzeugte CA darf ersetzt werden — sie war noch auf keinem iPhone.
            # Eine vorhandene CA bleibt immer (sonst müsste jedes iPhone das Profil neu installieren);
            # ihr Fehler wird angezeigt, statt die Sicherheit still herabzustufen. Und herabgestuft
            # wird höchstens auf 'dns' (nur Namen beschränkt), nie automatisch auf 'aus'.
            print(f'⚠️  Die Krypto dieses Rechners prüft die IP-Beschränkung der CA nicht ({probe}) — '
                  f'neue CA wird mit Beschränkung nur auf .local-Namen ausgestellt.')
            for datei in _tls_dateien():
                try:
                    datei.unlink()
                except OSError:
                    pass
            ctx, neu_ca = bauen('dns', erzwingen=True)
            probe = tls_selbsttest(ctx, namen[0])
        if probe:
            print(f'⚠️  Die eigene Zertifikatskette ließ sich hier nicht prüfen: {probe} — '
                  f'HTTPS bleibt an, aber das iPhone könnte das Zertifikat ablehnen.')
        stufe, ca_name = tls_ca_merkmale()
        if stufe == 'aus':
            print('⚠️  Die lokale CA ist NICHT namensbeschränkt: Wer ihren Schlüssel vom Mac stiehlt, kann dem '
                  'iPhone beliebige Webseiten vorspielen. Neu erzeugen: siehe Einstellungen → iPhone-Modus.')
        TLS_STATE.update({'aktiv': True, 'grund': '', 'namen': namen, 'ips': ips,
                          'fingerabdruck': tls_fingerabdruck(), 'gueltig_bis': tls_gueltig_bis(),
                          'ca_gueltig_bis': tls_gueltig_bis(TLS_CA_CRT),
                          'stufe': stufe, 'constraints': stufe != 'aus', 'ca_name': ca_name,
                          'ca_neu': bool(neu_ca), 'selbsttest': probe})
        return ctx, ''
    except Exception as e:
        grund = f'Zertifikat konnte nicht erzeugt werden ({e.__class__.__name__}: {e}).'
        TLS_STATE.update({'aktiv': False, 'grund': grund})
        return None, grund


def tls_selbsttest(kontext, name):
    """Prüft die frisch erzeugte Kette mit einem echten Handshake gegen sich selbst — mit einem
    ANDEREN Prüfer als dem Erzeuger (Pythons ssl gegen openssl). Nur so fällt auf, wenn openssl
    etwas schreibt, das ein Standard-Prüfer nicht akzeptiert. Genau das passierte am 15.09.2026 auf
    macOS: „unsupported name constraint type" — die Kette war lokal erzeugt und lokal unbrauchbar.
    Liefert '' bei Erfolg, sonst den Fehlertext."""
    fehler = []
    try:
        pruefer = ssl.create_default_context(cafile=str(TLS_CA_CRT))
        a, b = socket.socketpair()
        a.settimeout(5)
        b.settimeout(5)

        def serverseite():
            try:
                with kontext.wrap_socket(a, server_side=True) as t:
                    t.recv(1)
            except Exception as e:
                fehler.append(f'{e.__class__.__name__}: {e}')

        t = threading.Thread(target=serverseite, daemon=True)
        t.start()
        try:
            with pruefer.wrap_socket(b, server_hostname=name) as s:
                s.send(b'x')
        except Exception as e:
            fehler.append(f'{e.__class__.__name__}: {e}')
        t.join(timeout=5)
        for sock in (a, b):
            try:
                sock.close()
            except OSError:
                pass
    except Exception as e:
        return f'Selbsttest nicht durchführbar ({e.__class__.__name__}: {e})'
    return fehler[0] if fehler else ''


def tls_laeuft_bald_ab(tage=30, datei=None):
    """Läuft das Serverzertifikat (bzw. `datei`) demnächst ab? Dann rechtzeitig neu ausstellen —
    ein still abgelaufenes Zertifikat wäre unterwegs ein Ausfall ohne erkennbaren Grund."""
    datei = datei or TLS_SRV_CRT
    if not datei.exists():
        return True
    try:
        exe = openssl_pfad()
        p = subprocess.run([exe, 'x509', '-noout', '-checkend', str(tage * 86400), '-in', str(datei)],
                           capture_output=True, text=True, timeout=20)
        return p.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return False


def tls_fingerabdruck():
    try:
        aus = _openssl(['x509', '-noout', '-fingerprint', '-sha256', '-in', str(TLS_CA_CRT)])
        return aus.split('=', 1)[1].strip() if '=' in aus else ''
    except OSError:
        return ''


def tls_gueltig_bis(datei=None):
    try:
        aus = _openssl(['x509', '-noout', '-enddate', '-in', str(datei or TLS_SRV_CRT)])
        return aus.split('=', 1)[1].strip() if '=' in aus else ''
    except OSError:
        return ''


def tls_status():
    return {'aktiv': bool(TLS_STATE['aktiv']), 'grund': TLS_STATE['grund'],
            'namen': TLS_STATE['namen'], 'ips': TLS_STATE['ips'],
            'ca_datei': str(TLS_CA_CRT), 'fingerabdruck': TLS_STATE['fingerabdruck'],
            'gueltig_bis': TLS_STATE['gueltig_bis'],
            'constraints': bool(TLS_STATE.get('constraints', True)),
            'stufe': TLS_STATE.get('stufe') or '', 'ca_name': TLS_STATE.get('ca_name') or '',
            'ca_neu': bool(TLS_STATE.get('ca_neu')), 'ca_gueltig_bis': TLS_STATE.get('ca_gueltig_bis') or '',
            'tls_ordner': str(TLS_DIR),
            'selbsttest': TLS_STATE.get('selbsttest') or '',
            'ca_da': TLS_CA_CRT.exists()}


# ── iPHONE-MODUS (2026-09-12-1) ───────────────────────────────
# Anforderung: per Knopf ein- und ausschalten, beim Beenden automatisch aus, beim Start NIE
# automatisch an. Umsetzung: Der Hauptserver bindet immer nur 127.0.0.1. Der Knopf öffnet einen
# zweiten Listener auf der aktuellen Mac-IP (gleicher Port) und schließt ihn wieder. Da der
# Listener im Prozess lebt, endet er mit dem Server — es gibt keinen persistenten Zustand.
# Zugang aus dem WLAN nur mit Zugangscode (Cookie, gesetzt über http://<Mac-IP>:8765/go/<code>);
# der Code liegt mit 0600 im Home und überlebt Neustarts, damit das iPhone ihn nur einmal braucht.
# Ollama bleibt dabei auf 127.0.0.1 — das iPhone spricht es über /api/ollama/* durch den Server.
LAN_STATE = {'an': False, 'ip': '', 'server': None, 'seit': 0.0, 'anfragen': 0, 'letzte': 0.0,
             'hinweis': '', 'tls': False, 'tls_grund': ''}
# 2026-09-13-1: Vergessen-Schutz. Bleibt der Modus an, obwohl das iPhone längst nicht mehr anfragt
# (Lodge-WLAN, Grenze), schließt der Server ihn nach LAN_INAKTIV_H Stunden ohne Anfrage von selbst.
# Jede Anfrage mit gültigem Zugangscode setzt die Uhr zurück; Einschalten bleibt eine bewusste Entscheidung.
try:
    LAN_INAKTIV_H = max(1, int(os.environ.get('SAFARI_LAN_INAKTIV_H', '12')))
except ValueError:
    LAN_INAKTIV_H = 12
LAN_LOCK = threading.Lock()
TOKEN_DATEI = Path.home() / '.safari-assistant-zugang'
TOKEN_ALPHABET = '23456789abcdefghjkmnpqrstuvwxyz'   # ohne 0/1/o/i/l — am iPhone eindeutig tippbar
TOKEN_LAENGE = 10
_TOKEN_RE = _re.compile(r'^[a-z0-9]{6,64}$')
_TOKEN_CACHE = {'wert': ''}

def zugangs_token(neu=False):
    """Zugangscode für das WLAN lesen bzw. anlegen. neu=True erzeugt einen frischen Code
    (alle iPhones müssen dann die Adresse neu öffnen)."""
    if not neu:
        if _TOKEN_CACHE['wert']:
            return _TOKEN_CACHE['wert']
        try:
            t = TOKEN_DATEI.read_text(encoding='utf-8').strip()
            if _TOKEN_RE.match(t):
                _TOKEN_CACHE['wert'] = t
                return t
        except OSError:
            pass
    t = ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LAENGE))
    try:
        schreibe_privat(TOKEN_DATEI, t + '\n')
    except OSError:
        pass   # dann gilt der Code nur für diesen Lauf — besser als gar keiner
    _TOKEN_CACHE['wert'] = t
    return t

def token_gueltig(wert):
    if not wert or not _TOKEN_RE.match(wert):
        return False
    return secrets.compare_digest(wert, zugangs_token())

def url_fuers_log(url):
    """Zugangscode nur im Terminal voll zeigen. Startet die App den Server, landet stdout in einer
    Logdatei — dort steht der Code nicht (2026-09-27, Audit M1). Die volle Adresse steht in der App
    unter ⚙️ Einstellungen → iPhone-Modus."""
    try:
        if sys.stdout.isatty():
            return url
    except (AttributeError, ValueError):
        pass
    return _re.sub(r'/go/[^/?#\s]+', '/go/<Code: App → Einstellungen → iPhone-Modus>', url)

def lan_status():
    st = LAN_STATE
    port = SERVER_INFO.get('port') or 8765
    ip = st['ip'] if st['an'] else lan_ip()
    schema = 'https' if st['tls'] else 'http'
    # Hauptadresse ist der Bonjour-Name: der bleibt beim Wechsel Starlink ↔ iPhone-Hotspot gleich,
    # die IP nicht. Damit überlebt auch das Home-Bildschirm-Icon am iPhone den Netzwechsel.
    name = bonjour_name()
    token = zugangs_token()
    url_name = f'{schema}://{name}:{port}/go/{token}' if name else ''
    # Die IP-Adresse nur anbieten, wenn das Zertifikat sie auch abdeckt — sonst schickt man das
    # iPhone auf eine Adresse, die vorhersehbar an der Zertifikatsprüfung scheitert.
    ip_gedeckt = (not st['tls']) or (ip and ip in (TLS_STATE.get('ips') or []))
    url_ip = f'{schema}://{ip}:{port}/go/{token}' if (ip and ip_gedeckt) else ''
    return {'an': st['an'], 'ip': ip, 'port': port,
            'url': url_name or url_ip,
            'url_ip': url_ip, 'name': name, 'schema': schema,
            'tls': st['tls'], 'tls_grund': st['tls_grund'], 'tls_info': tls_status(),
            'code': token,
            'seit_s': int(time.time() - st['seit']) if st['an'] else 0,
            'inaktiv_s': lan_inaktiv_s(), 'auto_aus_h': LAN_INAKTIV_H,
            'anfragen': st['anfragen'], 'hinweis': st['hinweis']}

def lan_inaktiv_s():
    """Sekunden seit der letzten Anfrage mit gültigem Zugangscode — vor der ersten Anfrage seit dem Einschalten."""
    if not LAN_STATE['an']:
        return 0
    return int(time.time() - max(LAN_STATE['letzte'], LAN_STATE['seit']))

def _lan_listener_schliessen():
    srv = LAN_STATE['server']
    LAN_STATE['server'] = None
    if srv is not None:
        try:
            srv.shutdown()      # serve_forever-Schleife beenden (läuft im eigenen Thread)
            srv.server_close()
        except Exception:
            pass

def lan_an():
    """Öffnet den WLAN-Zugang. Liefert (ok, status)."""
    with LAN_LOCK:
        ip = lan_ip()
        if not ip:
            LAN_STATE['hinweis'] = 'Keine Netzwerk-IP gefunden — ist der Mac im WLAN (Starlink/Hotspot)?'
            return False, lan_status()
        port = SERVER_INFO.get('port') or 8765
        if LAN_STATE['an'] and LAN_STATE['ip'] == ip and (LAN_STATE['server'] is not None or SERVER_INFO.get('offen')):
            return True, lan_status()
        _lan_listener_schliessen()
        if SERVER_INFO.get('offen'):
            # Ausweichlösung nach defektem lo0: der Hauptserver lauscht bereits auf 0.0.0.0,
            # ein zweiter Listener wäre EADDRINUSE. Dann öffnet nur das Tor (Anfragen-Gate) —
            # und zwar unverschlüsselt, weil der bestehende Listener kein TLS spricht.
            LAN_STATE.update({'an': True, 'ip': ip, 'seit': time.time(), 'anfragen': 0, 'hinweis': '',
                              'tls': False, 'tls_grund': 'Ausweichbindung 0.0.0.0 (defektes lo0) — ohne Verschlüsselung.'})
            print(f'📱 iPhone-Modus: AN (ohne TLS) — ' + url_fuers_log(f'http://{ip}:{port}/go/{zugangs_token()}'))
            return True, lan_status()
        ctx, tls_grund = tls_vorbereiten()
        try:
            srv = SafariServer((ip, port), SafariHandler, ssl_kontext=ctx)
        except OSError as e:
            LAN_STATE['hinweis'] = f'WLAN-Adresse {ip}:{port} lässt sich nicht öffnen ({e.strerror or e}).'
            LAN_STATE['an'] = False
            return False, lan_status()
        threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.5}, daemon=True).start()
        LAN_STATE.update({'an': True, 'ip': ip, 'server': srv, 'seit': time.time(), 'anfragen': 0,
                          'hinweis': '', 'tls': bool(ctx), 'tls_grund': tls_grund})
        st = lan_status()
        print(f'📱 iPhone-Modus: AN — {url_fuers_log(st["url"])}' + ('' if ctx else f'  ⚠️  ohne Verschlüsselung: {tls_grund}'))
        if ctx:
            print(f'🔐 Zertifikat der lokalen CA fürs iPhone: {TLS_CA_CRT}')
        return True, lan_status()

def lan_aus(grund=''):
    with LAN_LOCK:
        war_an = LAN_STATE['an']
        _lan_listener_schliessen()
        LAN_STATE.update({'an': False, 'ip': '', 'hinweis': grund, 'tls': False})
        if war_an:
            print('📱 iPhone-Modus: AUS' + (f' ({grund})' if grund else ''))
        return lan_status()

def starte_lan_wache():
    """Wechselt der Mac das Netz (Starlink → Hotspot), stimmt die gebundene IP nicht mehr:
    dann neu binden — oder schließen, wenn gar kein Netz mehr da ist. Außerdem: nach LAN_INAKTIV_H
    Stunden ohne Anfrage vom iPhone schließt der Zugang von selbst (Vergessen-Schutz)."""
    def wache():
        while True:
            time.sleep(10)
            if not LAN_STATE['an']:
                continue
            if lan_inaktiv_s() >= LAN_INAKTIV_H * 3600:
                lan_aus(f'Nach {LAN_INAKTIV_H} Stunden ohne Anfrage vom iPhone automatisch abgeschaltet. Bei Bedarf neu einschalten.')
                continue
            if SERVER_INFO.get('offen'):
                continue
            ip = lan_ip()
            if ip == LAN_STATE['ip']:
                continue
            if not ip:
                lan_aus('Netzwerk verloren — iPhone-Modus geschlossen. Bei Bedarf neu einschalten.')
            else:
                alt = LAN_STATE['ip']
                ok, st = lan_an()
                print(f'📱 iPhone-Modus: Netzwerk gewechselt {alt} → {ip}' + ('' if ok else ' — Neubinden fehlgeschlagen'))
    threading.Thread(target=wache, daemon=True).start()


# ── REISEWARNUNGEN (2026-09-13-1) ─────────────────────────────
# „Sobald ich online bin, die wichtigen Reisewarnungen holen." Drei amtliche Quellen — keine Blogs,
# keine Nachrichtenportale, keine KI-Zusammenfassung des Warntextes:
#   1. Auswärtiges Amt, Open-Data-Schnittstelle: Liste /opendata/travelwarning (je Land die amtlichen
#      Kennzeichen warning/partialWarning/situationWarning/situationPartWarning, Stand als Zeitstempel),
#      Detail /opendata/travelwarning/<id> (HTML-Text). Maßgeblich für deutsche Reisende.
#   2. UK FCDO über die GOV.UK-Content-API: details.alert_status ist maschinenlesbar, dazu der
#      Abschnitt „Areas where FCDO advises against travel".
#   3. US State Department, RSS der Travel Advisories: enthält NUR zuletzt geänderte Länder —
#      deshalb ergänzend, nie allein.
# Der Warntext wird WÖRTLICH übernommen (Nutzungsbedingungen des AA: vollständige Übernahme, klar
# erkennbare Herkunft, Hinweis auf den Originaltext) — die App kürzt, deutet und formuliert ihn nicht um.
# Abruf läuft im Hintergrund: ist der Cache älter als REISEWARN_MAX_ALTER_H, versucht die Wache es
# alle REISEWARN_WIEDERHOLUNG_MIN Minuten erneut — sobald Netz da ist, klappt es und der Cache gilt
# wieder offline. Nichts davon blockiert je eine Anfrage.
REISEWARN_DATEI = Path.home() / '.safari-assistant-reisewarnungen.json'
try:
    REISEWARN_MAX_ALTER_H = max(1, int(os.environ.get('SAFARI_REISEWARN_ALTER_H', '12')))
except ValueError:
    REISEWARN_MAX_ALTER_H = 12
REISEWARN_WIEDERHOLUNG_MIN = 15
REISEWARN_UA = PROJEKT_UA   # 2026-09-27: Kennung des öffentlichen Projekts
AA_LISTE_URL = 'https://www.auswaertiges-amt.de/opendata/travelwarning'
AA_DETAIL_URL = 'https://www.auswaertiges-amt.de/opendata/travelwarning/{id}'
AA_SEITE_URL = 'https://www.auswaertiges-amt.de/de/service/laender/{slug}-node/{slug}sicherheit/{id}'
FCDO_URL = 'https://www.gov.uk/api/content/foreign-travel-advice/{slug}'
FCDO_SEITE_URL = 'https://www.gov.uk/foreign-travel-advice/{slug}'
USA_RSS_URL = 'https://travel.state.gov/_res/rss/TAsTWs.xml'

# Die 16 Länder der Route. aa = ISO-3166-1-alpha-2 (Abgleich über countryCode der AA-Liste, nicht über
# die AA-internen IDs — die können sich ändern). slug = Namensteil der öffentlichen AA-Seite; er wird
# beim Abruf geprüft und nur übernommen, wenn die Seite wirklich antwortet (sonst kein Link statt
# eines falschen). fcdo/usa = Länderkennung der jeweiligen Quelle.
REISEWARN_LAENDER = [
    {'name': 'Namibia',    'aa': 'NA', 'slug': 'namibia',    'fcdo': 'namibia',       'usa': 'Namibia'},
    {'name': 'Botswana',   'aa': 'BW', 'slug': 'botsuana',   'fcdo': 'botswana',      'usa': 'Botswana'},
    {'name': 'Südafrika',  'aa': 'ZA', 'slug': 'suedafrika', 'fcdo': 'south-africa',  'usa': 'South Africa'},
    {'name': 'Sambia',     'aa': 'ZM', 'slug': 'sambia',     'fcdo': 'zambia',        'usa': 'Zambia'},
    {'name': 'Zimbabwe',   'aa': 'ZW', 'slug': 'simbabwe',   'fcdo': 'zimbabwe',      'usa': 'Zimbabwe'},
    {'name': 'Mosambik',   'aa': 'MZ', 'slug': 'mosambik',   'fcdo': 'mozambique',    'usa': 'Mozambique'},
    {'name': 'Malawi',     'aa': 'MW', 'slug': 'malawi',     'fcdo': 'malawi',        'usa': 'Malawi'},
    {'name': 'Tansania',   'aa': 'TZ', 'slug': 'tansania',   'fcdo': 'tanzania',      'usa': 'Tanzania'},
    {'name': 'Kenia',      'aa': 'KE', 'slug': 'kenia',      'fcdo': 'kenya',         'usa': 'Kenya'},
    {'name': 'Uganda',     'aa': 'UG', 'slug': 'uganda',     'fcdo': 'uganda',        'usa': 'Uganda'},
    {'name': 'Ruanda',     'aa': 'RW', 'slug': 'ruanda',     'fcdo': 'rwanda',        'usa': 'Rwanda'},
    {'name': 'Burundi',    'aa': 'BI', 'slug': 'burundi',    'fcdo': 'burundi',       'usa': 'Burundi'},
    {'name': 'Äthiopien',  'aa': 'ET', 'slug': 'aethiopien', 'fcdo': 'ethiopia',      'usa': 'Ethiopia'},
    {'name': 'Angola',     'aa': 'AO', 'slug': 'angola',     'fcdo': 'angola',        'usa': 'Angola'},
    {'name': 'Lesotho',    'aa': 'LS', 'slug': 'lesotho',    'fcdo': 'lesotho',       'usa': 'Lesotho'},
    {'name': 'Eswatini',   'aa': 'SZ', 'slug': 'eswatini',   'fcdo': 'eswatini',      'usa': 'Eswatini'},
]
# Maschinenlesbare Warnstufen des FCDO. Unbekannte Codes werden UNVERÄNDERT durchgereicht, damit eine
# neue Stufe sichtbar wird, statt still zu verschwinden.
FCDO_STUFEN = {
    'avoid_all_travel_to_parts': 'Von allen Reisen in Teile des Landes wird abgeraten',
    'avoid_all_but_essential_travel_to_parts': 'Von nicht notwendigen Reisen in Teile des Landes wird abgeraten',
    'avoid_all_travel_to_whole_country': 'Von allen Reisen in das ganze Land wird abgeraten',
    'avoid_all_but_essential_travel_to_whole_country': 'Von nicht notwendigen Reisen in das ganze Land wird abgeraten',
}
REISEWARN_STATE = {'laeuft': False, 'letzter_versuch': 0.0, 'meldung': ''}
REISEWARN_LOCK = threading.Lock()


def _hole(url, timeout=20, max_bytes=4 * 1024 * 1024, roh=False):
    """Ein GET mit Zeitlimit und Größendeckel. Liefert Text (oder Bytes bei roh=True)."""
    req = urllib.request.Request(url, headers={'User-Agent': REISEWARN_UA,
                                               'Accept': 'application/json, application/rss+xml, text/html'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        daten = r.read(max_bytes + 1)
    if len(daten) > max_bytes:
        raise ValueError(f'Antwort größer als {max_bytes // 1024} KB')
    return daten if roh else daten.decode('utf-8', 'replace')


def _erreichbar(url, timeout=8):
    """Prüft eine öffentliche Seite, bevor ihr Link gespeichert wird (kein Link ist besser als ein falscher)."""
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': REISEWARN_UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


_TAG_RE = _re.compile(r'<[^>]+>')
_LEER_RE = _re.compile(r'[ \t ]+')


def html_zu_text(roh):
    """HTML → lesbarer Text. Blockenden werden zu Zeilenumbrüchen, Listenpunkte zu „• ",
    der Rest bleibt Wort für Wort erhalten (keine Kürzung, keine Umformulierung)."""
    t = _re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', str(roh or ''))
    t = _re.sub(r'(?i)<li[^>]*>', '\n• ', t)
    t = _re.sub(r'(?i)<br\s*/?>', '\n', t)
    t = _re.sub(r'(?i)</(p|div|h[1-6]|li|ul|ol|tr)>', '\n', t)
    t = _TAG_RE.sub('', t)
    t = _html.unescape(t)
    t = _LEER_RE.sub(' ', t)
    t = _re.sub(r' *\n *', '\n', t)
    return _re.sub(r'\n{2,}', '\n', t).strip()      # Absätze/Listenpunkte je eine Zeile


def aa_abschnitt(content, start_muster, stop_muster):
    """Schneidet einen Abschnitt aus dem AA-HTML heraus (Überschrift bis zur nächsten Überschrift)."""
    m = _re.search(start_muster, content or '', _re.I)
    if not m:
        return ''
    rest = content[m.end():]
    e = _re.search(stop_muster, rest, _re.I)
    return html_zu_text(rest[:e.start()] if e else rest)


def aa_stufe(e):
    """Amtliche Einstufung aus den Kennzeichen der AA-Liste — nicht aus dem Text geraten."""
    if e.get('warning'):
        return 'Reisewarnung'
    if e.get('situationWarning'):
        return 'Situationsbedingte Reisewarnung'
    if e.get('partialWarning'):
        return 'Teilreisewarnung'
    if e.get('situationPartWarning'):
        return 'Situationsbedingte Teilreisewarnung'
    return 'Reise- und Sicherheitshinweise (keine Warnung)'


def _datum(epoch):
    try:
        return time.strftime('%Y-%m-%d', time.localtime(int(epoch))) if epoch else ''
    except (ValueError, OSError, OverflowError):
        return ''


def aa_eintrag(land, listen_eintrag, eid, detail):
    """Ein Landeseintrag aus AA-Liste + Detail. Der Warntext bleibt wörtlich."""
    d = detail or {}
    inhalt = d.get('content') or ''
    warn = aa_abschnitt(inhalt, r'<h2[^>]*>\s*Sicherheit[^<]*</h2>', r'<h[23][^>]*>')
    aktuell = aa_abschnitt(inhalt, r'<h2[^>]*>\s*Aktuelles\s*</h2>', r'<h2[^>]*>')
    seite = AA_SEITE_URL.format(slug=land['slug'], id=eid)
    return {
        'stufe': aa_stufe(listen_eintrag),
        'kennzeichen': {k: bool(listen_eintrag.get(k)) for k in
                        ('warning', 'partialWarning', 'situationWarning', 'situationPartWarning')},
        'titel': str(d.get('title') or listen_eintrag.get('title') or ''),
        'landname': str(listen_eintrag.get('countryName') or land['name']),
        'stand': _datum(listen_eintrag.get('effective')),
        'geaendert': _datum(listen_eintrag.get('lastModified')),
        'letzte_aenderung': html_zu_text(d.get('lastChanges') or ''),
        'warntext': warn,
        'aktuelles': aktuell,
        'url': seite if _erreichbar(seite) else '',
        'abgerufen': int(time.time()),
    }


def aa_abrufen(laender, alt_laender=None):
    """AA-Liste einmal holen (~75 KB), dann je Land das Detail (~60 KB) — aber nur, wenn sich der
    Zeitstempel lastModified seit dem letzten Abruf geändert hat. Das hält den Datenverbrauch über
    Satellit/Hotspot klein. Liefert (dict land→eintrag, fehler-text)."""
    roh = json.loads(_hole(AA_LISTE_URL, max_bytes=8 * 1024 * 1024))
    antwort = roh.get('response') if isinstance(roh, dict) else None
    if not isinstance(antwort, dict):
        raise ValueError('Unerwartete Struktur der AA-Liste (kein response-Objekt)')
    nach_code = {}
    for eid, e in antwort.items():
        if isinstance(e, dict) and e.get('countryCode'):
            nach_code[str(e['countryCode']).upper()] = (eid, e)
    ergebnis, fehlend = {}, []
    for land in laender:
        treffer = nach_code.get(land['aa'])
        if not treffer:
            fehlend.append(land['name'])
            continue
        eid, e = treffer
        frueher = ((alt_laender or {}).get(land['name']) or {}).get('aa') or {}
        if frueher.get('warntext') and frueher.get('geaendert') == _datum(e.get('lastModified')):
            ergebnis[land['name']] = dict(frueher, stufe=aa_stufe(e), geprueft=int(time.time()))
            continue
        try:
            detail = json.loads(_hole(AA_DETAIL_URL.format(id=eid))).get('response', {}).get(eid, {})
        except Exception as ex:
            detail = {}
            fehlend.append(f'{land["name"]} (Detail: {ex.__class__.__name__})')
        ergebnis[land['name']] = aa_eintrag(land, e, eid, detail)
    return ergebnis, ('; '.join(fehlend) if fehlend else '')


def fcdo_eintrag(land, roh):
    d = (roh or {}).get('details') or {}
    codes = [str(c) for c in (d.get('alert_status') or []) if isinstance(c, str)]
    teile = d.get('parts') if isinstance(d.get('parts'), list) else []
    gebiete = ''
    for t in teile:
        if isinstance(t, dict) and t.get('slug') == 'warnings-and-insurance':
            gebiete = aa_abschnitt(t.get('body') or '',
                                   r'<h2[^>]*id="areas-where-[^"]*"[^>]*>.*?</h2>', r'<h2[^>]*>')
            break
    return {
        'stufe': ' · '.join(FCDO_STUFEN.get(c, c) for c in codes) if codes
                 else 'Keine Reisewarnung für Landesteile (FCDO)',
        'codes': codes,
        'gebiete': gebiete,
        'stand': str(roh.get('public_updated_at') or '')[:10],
        'aenderung': str(d.get('change_description') or ''),
        'url': FCDO_SEITE_URL.format(slug=land['fcdo']),
        'abgerufen': int(time.time()),
    }


def fcdo_abrufen(laender):
    ergebnis, fehlend = {}, []
    for land in laender:
        try:
            ergebnis[land['name']] = fcdo_eintrag(land, json.loads(_hole(FCDO_URL.format(slug=land['fcdo']))))
        except Exception as ex:
            fehlend.append(f'{land["name"]} ({ex.__class__.__name__})')
    if not ergebnis:
        # Kein einziges Land erreichbar: als Fehler melden, nicht als „erfolgreich, 0 Länder"
        raise OSError('kein Land abrufbar — ' + '; '.join(fehlend[:3]))
    return ergebnis, ('; '.join(fehlend) if fehlend else '')


_ITEM_RE = _re.compile(r'(?is)<item>(.*?)</item>')


def _xml_feld(block, tag, attr=''):
    muster = rf'(?is)<{tag}{attr}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>'
    m = _re.search(muster, block)
    return _html.unescape(_TAG_RE.sub('', m.group(1))).strip() if m else ''


def usa_abrufen(laender):
    """RSS des State Department. Achtung: nur zuletzt geänderte Länder — fehlende sind kein Fehler."""
    feed = _hole(USA_RSS_URL, max_bytes=2 * 1024 * 1024)
    nach_land = {}
    for block in _ITEM_RE.findall(feed):
        titel = _xml_feld(block, 'title')
        if not titel:
            continue
        name = _re.split(r'\s+-\s+(?:Level|See)\b', titel)[0].strip()
        stufe = _xml_feld(block, 'category', r'\s+domain="Threat-Level"') or \
                (titel.split(' - ', 1)[1] if ' - ' in titel else '')
        eintrag = {'stufe': stufe, 'titel': titel, 'stand': _xml_feld(block, 'pubDate'),
                   'url': _xml_feld(block, 'link'), 'abgerufen': int(time.time())}
        nach_land.setdefault(name, eintrag)
    ergebnis = {land['name']: nach_land[land['usa']] for land in laender if land['usa'] in nach_land}
    return ergebnis, (f'{len(ergebnis)} von {len(laender)} Ländern im Feed '
                      f'(der Feed führt nur zuletzt geänderte Länder)')


# ── WARNGEBIETE: aus dem amtlichen Text die konkreten Gebiete lesen (2026-09-15-1) ──
# Ziel: nicht mehr nur „Land X hat eine Teilreisewarnung", sondern welche Gebiete gemeint sind —
# als Fläche auf der Karte und als Antwort auf „bin ich gerade drin?".
# Regel dabei: NICHTS raten. Der Text wird nur zerlegt, die Namen kommen aus einem Verzeichnis
# echter Verwaltungsgebiete (OpenStreetMap, fetch-warnzonen.py). Was nicht zugeordnet werden kann,
# wird gemeldet und bleibt Text — eine falsche Fläche auf einer Sicherheitskarte wäre schlimmer
# als gar keine.
WARN_STUFEN = [
    (3, _re.compile(r'wird\s+gewarnt', _re.I), 'Reisewarnung'),
    (2, _re.compile(r'wird\s+dringend\s+abgeraten', _re.I), 'Dringend abgeraten'),
    (1, _re.compile(r'wird\s+abgeraten', _re.I), 'Von nicht notwendigen Reisen abgeraten'),
]
# „außer Pemba", „mit Ausnahme der Hauptstadt" — was NUR nach diesen Wörtern steht, ist ausgenommen.
# Ohne diese Prüfung würde die Karte genau die Orte einfärben, die der Text ausnimmt.
AUSNAHME_RE = _re.compile(r'\b(außer|ausser|mit\s+Ausnahme|ausgenommen|außerhalb)\b', _re.I)
# ── Einschränkungs-Markierung ⚑ (überarbeitet 2026-09-19) ──
# Die Markierung bedeutet: „Die gezeichnete Fläche ist größer als das, wovor der Satz warnt." Sie
# muss AM GEBIET hängen, nicht am Satz. Der Lauf vom 18.09. trug sie auf allen 19 Flächen, bei 13
# zu Unrecht — weil der Satz als Ganzes geprüft wurde: In „die Countys Mandera, Wajir, Garissa und
# Lamu …, mit Ausnahme von Lamu Island" standen „Countys" und „mit Ausnahme", also bekamen alle
# vier die Markierung. Richtig war sie nur für Lamu. Drei Regeln (Prüfsätze in test-warngebiete.py):
#  1. Verwaltungsebene: Ein Einheitswort („Distrikte", „Zonen") schränkt ein Gebiet nur ein, wenn
#     es eine Ebene UNTER dem Gebiet meint. „die Countys Mandera, Wajir" beschreibt die Countys
#     selbst; „Provinz Nampula, in die Distrikte Memba und Erati" meint nur zwei Distrikte.
#  2. Teilsätze: Der Satz wird an „;", „sowie", „und in" zerlegt; Einschübe („einschließlich …",
#     Klammern) und Ausnahmen („außer …") werden abgetrennt. Markierungen binden nur im eigenen
#     Teilsatz. Steht ein Gebiet in irgendeinem Teilsatz ohne Einschränkung, ist es ganz gewarnt.
#  3. Ausnahmen binden über den Namen: „mit Ausnahme von Lamu Island" trifft Lamu, weil der
#     Ausnahme-Text den Gebietsnamen enthält — nicht Mandera im selben Satz. Enthält der
#     Ausnahme-Text keinen Gebietsnamen („Provinz Cabo Delgado, in alle Distrikte, außer Pemba"),
#     gilt er für alle Gebiete des Teilsatzes.
# Himmelsrichtungen schränken nur ein, wenn sie VOR dem Gebiet stehen: „den Norden des Countys
# Tana River" ja, „die Countys … im Osten Kenias" nein. „westlich von Addis Abeba" macht Addis
# Abeba zum Bezugspunkt, nicht zum Warngebiet — ebenso „an den Regionalstaat Tigray angrenzenden".
EINHEITEN_EBENE = (
    (4, r'County|Countys|Counties|Provinz|Provinzen|Region|Regionen|Regionalstaat|Regionalstaaten|'
        r'Regionalstaates|Bundesstaat|Bundesstaaten|Bundesstaates'),
    (6, r'Distrikt|Distrikte|Distrikten|Distrikts|Zone|Zonen|Bezirk|Bezirke|Bezirken|Bezirks|Kreis|Kreise|'
        r'Kreisen|Landkreis|Landkreise|Sub-County|Sub-Countys|Subcounty|Subcountys'),
    (8, r'Woreda|Woredas|Gemeinde|Gemeinden|Stadt|Städte|Ort|Orte|Insel|Inseln|Dorf|Dörfer'),
)
# (?<![\w-]): „Region" in „North-Rift-Region" und „County" in „Sub-County" sind keine eigenen Wörter.
EINHEIT_RES = [(ebene, _re.compile(r'(?<![\w-])(?:' + woerter + r')(?![\w-])', _re.I))
               for ebene, woerter in EINHEITEN_EBENE]
_EINHEIT_ALLE = '|'.join(woerter for _, woerter in EINHEITEN_EBENE)
# „in alle Distrikte", „sämtliche Zonen" meinen das Ganze, nicht einen Teil.
GANZ_RE = _re.compile(r'\b(alle|allen|sämtliche|sämtlichen|saemtliche)\s*$', _re.I)
_RICHTUNG_W = (r'nördlich|noerdlich|südlich|suedlich|östlich|oestlich|westlich|nordöstlich|nordwestlich|'
               r'südöstlich|südwestlich|Norden|Süden|Sueden|Osten|Westen|Nordosten|Nordwesten|Südosten|Südwesten')
RICHTUNG_RE = _re.compile(r'(?<![\w-])(?:' + _RICHTUNG_W + r')(?![\w-])', _re.I)
# Wörter, die in jedem Fall nur einen TEIL des Gebiets meinen — egal, wo im Teilsatz sie stehen:
# „innerhalb 60 km zur Grenze", „entlang der Küste", „die Fernstraße A3 im County Tana River".
TEILGEBIET_RE = _re.compile(r'\b(innerhalb|Umkreis|Grenzgebiet|Grenzgebiete|Grenzstreifen|Grenzregion|entlang|'
                            r'Umgebung|Teile\s+de[rs]|Teilen\s+de[rs]|Teil\s+de[rs]|Küstenstreifen|Küstengebiet|'
                            r'Küstengebiete|Straße|Straßen|Fernstraße|Fernstraßen|Route|Routen|Strecke|Korridor|'
                            r'\d+\s*km)\b', _re.I)
# Einschübe verfeinern einen Teilsatz, sie erweitern ihn nicht: „einschließlich der Fernstraße A3 im
# County Tana River" macht aus dem Norden des Countys nicht das ganze County.
EINSCHUB_RE = _re.compile(r'\b(einschließlich|einschliesslich|inklusive|insbesondere|darunter|vor\s+allem)\b', _re.I)
TEILSATZ_RE = _re.compile(r';|,?\s+sowie\s+|,?\s+und\s+i[nm]\s+|,?\s+und\s+vor\s+|\.\s+(?=[A-ZÄÖÜ])')
_NAME_RAND = (r'(?<![\wÄÖÜäöüß])', r'(?![\wÄÖÜäöüß])')
# Bezugspunkte: „westlich von Addis Abeba", „an den Regionalstaat Tigray angrenzenden"
BEZUG_VON_RE = _re.compile(r'(?:' + _RICHTUNG_W + r')\s+von\s+(?:(?:der|dem|des)\s+)?(?:(?:' + _EINHEIT_ALLE + r')\s+)?$', _re.I)
BEZUG_AN_RE = _re.compile(r'\ban\s+(?:den|die|das|der|dem)\s+(?:(?:' + _EINHEIT_ALLE + r')\s+)?$', _re.I)
BEZUG_ANGRENZEND_RE = _re.compile(r'^\s+angrenzend', _re.I)


def warnstufe_der_zeile(zeile):
    """Stufe einer Zeile: 3 = „wird gewarnt", 2 = „dringend abgeraten", 1 = „abgeraten"; 0 = keine.
    Die Reihenfolge ist wichtig — „dringend abgeraten" darf nicht als bloßes „abgeraten" zählen."""
    for stufe, muster, _ in WARN_STUFEN:
        if muster.search(zeile or ''):
            return stufe
    return 0


def warnstufe_name(stufe):
    for s, _, name in WARN_STUFEN:
        if s == stufe:
            return name
    return ''


def warnbloecke(warntext):
    """Zerlegt den amtlichen Warnblock in Abschnitte mit je einer Stufe.
    Drei Bauformen kommen in den AA-Texten vor und werden alle abgedeckt:
      • ein Satz enthält Gebiete und Stufe (Kenia),
      • die Aufzählung steht VOR dem Satz mit der Stufe (Mosambik),
      • die Aufzählung steht DANACH, der Stufensatz endet mit Doppelpunkt (Äthiopien).
    Liefert [{'stufe': int, 'zeilen': [...], 'text': '...'}] — Zeilen ohne Stufe gehen nicht verloren,
    sie hängen am nächsten Stufensatz."""
    zeilen = [z.strip() for z in str(warntext or '').split('\n') if z.strip()]
    bloecke, puffer = [], []
    i = 0
    while i < len(zeilen):
        zeile = zeilen[i]
        stufe = warnstufe_der_zeile(zeile)
        if not stufe:
            puffer.append(zeile)
            i += 1
            continue
        block = puffer + [zeile]
        puffer = []
        i += 1
        # Aufzählung, die dem Stufensatz folgt (Äthiopien-Form), gehört noch dazu
        while i < len(zeilen) and zeilen[i].startswith('•') and not warnstufe_der_zeile(zeilen[i]):
            block.append(zeilen[i])
            i += 1
        bloecke.append({'stufe': stufe, 'zeilen': block, 'text': '\n'.join(block)})
    # Zeilen NACH dem letzten Stufensatz gehören zu keiner Warnung — im Äthiopien-Text folgt dort
    # etwa ein Satz über die Botschaft in Addis Abeba. Hängte man sie an den letzten Block, würde
    # Addis Abeba als gewarntes Gebiet eingefärbt. Sie bleiben im vollständigen Text sichtbar.
    return bloecke


def _namen_finden(text, vokabular):
    """[(Name, Anfang, Ende)] in Textreihenfolge. Längere Namen gewinnen („West Pokot" vor „Pokot"),
    Treffer überlappen nicht."""
    belegt, treffer = [], []
    for name in sorted(vokabular, key=len, reverse=True):
        for m in _re.finditer(_NAME_RAND[0] + _re.escape(name) + _NAME_RAND[1], text, _re.I):
            if any(m.start() < e and m.end() > s for s, e in belegt):
                continue    # überlappt einen längeren Treffer
            belegt.append((m.start(), m.end()))
            treffer.append((name, m.start(), m.end()))
    return sorted(treffer, key=lambda t: t[1])


def _maskiert(text, spannen):
    """Der Text mit ausgeblendeten Namen — sonst zählte „Provinz" in „Provinz Nampula" oder „County"
    in „Tana River County" als Einheitswort des Satzes."""
    zeichen = list(text)
    for s, e in spannen:
        for i in range(s, e):
            zeichen[i] = ' '
    return ''.join(zeichen)


def _ist_bezugspunkt(text, s, e):
    """Genannt, aber nicht gemeint: „westlich von Addis Abeba", „an den Regionalstaat Tigray angrenzenden"."""
    davor, danach = text[max(0, s - 80):s], text[e:e + 24]
    if BEZUG_VON_RE.search(davor):
        return True
    return bool(BEZUG_AN_RE.search(davor) and BEZUG_ANGRENZEND_RE.match(danach))


def _zeile_zerlegen(zeile):
    """Segmente einer Zeile: [(art, text, teilsatz_nr)], art ∈ {'kern', 'einschub', 'ausnahme'}.
    Klammern werden zuerst herausgelöst, dann der Rest an Teilsatzgrenzen geteilt; in jedem Teilsatz
    werden Ausnahme („außer …") und Einschub („einschließlich …") vom Kern getrennt."""
    text = zeile or ''
    klammern, arbeit = [], text
    for m in _re.finditer(r'\([^)]*\)', text):
        klammern.append((m.start(), m.group(0)[1:-1]))
        arbeit = arbeit[:m.start()] + ' ' * (m.end() - m.start()) + arbeit[m.end():]
    spannen, pos = [], 0
    for m in TEILSATZ_RE.finditer(arbeit):
        spannen.append((pos, m.start()))
        pos = m.end()
    spannen.append((pos, len(arbeit)))
    segmente = []
    for nr, (a, b) in enumerate(spannen):
        for k_pos, k_text in klammern:
            if a <= k_pos < b:
                segmente.append(('ausnahme' if AUSNAHME_RE.match(k_text.strip()) else 'einschub', k_text, nr))
        t = arbeit[a:b]
        aus = AUSNAHME_RE.search(t)
        if aus:
            segmente.append(('ausnahme', t[aus.start():], nr))
            t = t[:aus.start()]
        ein = EINSCHUB_RE.search(t)
        if ein:
            segmente.append(('einschub', t[ein.end():], nr))
            t = t[:ein.start()]
        segmente.append(('kern', t, nr))
    return segmente


def zeile_analysieren(zeile, vokabular):
    """Eine Zeile des Warntexts → ({Name: {'einschraenkung': bool}}, [ausgenommene Namen]).
    `vokabular` ist eine Liste von Namen oder ein dict {Name: Verwaltungsebene} (4 = Provinz/Region/
    County, 6 = Distrikt/Zone). Ohne Ebenen greift Regel 1 nicht, Regeln 2 und 3 schon.
    Ausgenommen ist ein Name nur, wenn er AUSSCHLIESSLICH in Ausnahme-Segmenten steht — „die Countys
    … und Lamu …, mit Ausnahme von Lamu Island" warnt weiterhin vor Lamu County."""
    ebenen = vokabular if isinstance(vokabular, dict) else {}

    def ebene(name):
        try:
            return int(ebenen.get(name) or 0)
        except (TypeError, ValueError):
            return 0

    objekte, ausnahmen, ausnahme_namen = {}, {}, set()
    for art, t, nr in _zeile_zerlegen(zeile):
        treffer = _namen_finden(t, vokabular)
        if art == 'ausnahme':
            ausnahmen[nr] = ausnahmen.get(nr, '') + ' ' + t
            ausnahme_namen.update(n for n, _, _ in treffer)
            continue
        maske = _maskiert(t, [(s, e) for _, s, e in treffer])
        einheiten = []
        for eb, muster in EINHEIT_RES:
            for m in muster.finditer(maske):
                if GANZ_RE.search(maske[:m.start()]):
                    continue        # „alle Distrikte" = das Ganze
                einheiten.append(eb)
        richtungen = [m.end() for m in RICHTUNG_RE.finditer(maske)]
        teilwort = bool(TEILGEBIET_RE.search(maske))
        gemeint = [(n, s, e) for n, s, e in treffer if not _ist_bezugspunkt(t, s, e)]
        # Feinere Ebene schlägt gröbere — im selben Kern-Teilsatz: „Provinz Nampula, in die Distrikte
        # Memba und Erati" meint die Distrikte, die Provinz ist Ortsangabe. „Provinz Cabo Delgado, in
        # alle Distrikte, außer Pemba" behält die Provinz, weil dort kein Distrikt übrig bleibt.
        if art == 'kern':
            eb_liste = [ebene(n) for n, _, _ in gemeint]
            if any(x >= 6 for x in eb_liste) and any(0 < x < 6 for x in eb_liste):
                gemeint = [(n, s, e) for n, s, e in gemeint if ebene(n) >= 6]
        for n, s, _ in gemeint:
            eb = ebene(n)
            feiner = eb > 0 and any(x > eb for x in einheiten)          # Regel 1
            richtung_davor = any(r <= s for r in richtungen)           # „den Norden des Countys …"
            objekte.setdefault(n, []).append([art, nr, feiner or richtung_davor or teilwort])
    # Regel 3: Ausnahmen binden über den Namen, sonst an alle Gebiete des Teilsatzes
    for nr, atext in ausnahmen.items():
        im_teilsatz = [n for n, liste in objekte.items() if any(a == 'kern' and t_nr == nr for a, t_nr, _ in liste)]
        gebunden = [n for n in im_teilsatz
                    if _re.search(_NAME_RAND[0] + _re.escape(n) + _NAME_RAND[1], atext, _re.I)]
        for n in (gebunden or im_teilsatz):
            for eintrag in objekte[n]:
                if eintrag[0] == 'kern' and eintrag[1] == nr:
                    eintrag[2] = True
    gebiete = {}
    for n, liste in objekte.items():
        kern = [x for a, _, x in liste if a == 'kern']
        # Regel 2: ein Kern-Teilsatz ohne Einschränkung → ganz gewarnt. Einschübe zählen nur, wenn
        # das Gebiet in keinem Kern steht.
        gebiete[n] = {'einschraenkung': all(kern) if kern else all(x for _, _, x in liste)}
    return gebiete, sorted(n for n in ausnahme_namen if n not in objekte)


def namen_in_zeile(zeile, vokabular):
    """Gebietsnamen einer Zeile (ohne Bezugspunkte und ohne rein Ausgenommenes) und die Ausnahmen —
    die Kurzform von zeile_analysieren()."""
    gebiete, ausgenommen = zeile_analysieren(zeile, vokabular)
    return list(gebiete), ausgenommen


def satzrest(zeile):
    """Was von einer Zeile übrig bleibt, wenn Stufenformel und Einleitung weg sind — daran erkennt
    man, ob die Zeile überhaupt ein Gebiet nennt oder nur Satzklammer ist."""
    rest = zeile or ''
    for _, muster, _ in WARN_STUFEN:
        rest = muster.sub(' ', rest)
    rest = _re.sub(r'(?i)\b(vor|von)\s+(nicht\s+notwendigen\s+)?reisen\b', ' ', rest)
    rest = _re.sub(r'(?i)\b(in|nach|die|den|das|der|folgenden|Regionen|Gebiete|und|sowie)\b', ' ', rest)
    return _re.sub(r'[\s•,.;:()-]+', ' ', rest).strip()


def warngebiete_aus_text(warntext, vokabular):
    """Amtlicher Warnblock + Verzeichnis echter Verwaltungsgebiete → konkrete Gebiete.
    Liefert (gebiete, ausgenommen, unaufgeloest). „unaufgeloest" sind Sätze, die vor etwas warnen,
    dem sich kein Verwaltungsgebiet zuordnen ließ (z. B. „das Grenzgebiet zu Eritrea (ca. 10 km)").
    Die müssen sichtbar bleiben, sonst suggeriert eine Karte Vollständigkeit, die sie nicht hat.
    `einschraenkung` gilt je Gebiet (siehe die drei Regeln oben), nicht je Satz."""
    gebiete, ausgenommen_gesamt, unaufgeloest = {}, set(), []
    for block in warnbloecke(warntext):
        for zeile in block['zeilen']:
            gefunden, ausgenommen = zeile_analysieren(zeile, vokabular)
            ausgenommen_gesamt.update(ausgenommen)
            # Einleitungen und Satzreste („Vor Reisen in die", „wird gewarnt.") sind keine
            # ungelösten Gebiete — sonst stünde in der App eine Warnliste voller Bruchstücke.
            querverweis = _re.match(r'^[•\s]*(siehe|s\.)\b', zeile or '', _re.I)
            if not gefunden and not querverweis and not zeile.rstrip().endswith(':') and len(satzrest(zeile)) >= 15:
                unaufgeloest.append({'satz': zeile, 'stufe': block['stufe'],
                                     'stufe_text': warnstufe_name(block['stufe'])})
            for name, info in gefunden.items():
                vorher = gebiete.get(name)
                if vorher and vorher['stufe'] >= block['stufe']:
                    continue      # die schärfere Stufe gewinnt
                gebiete[name] = {'name': name, 'stufe': block['stufe'],
                                 'stufe_text': warnstufe_name(block['stufe']), 'satz': zeile,
                                 'einschraenkung': bool(info['einschraenkung'])}
    for name in ausgenommen_gesamt:
        gebiete.pop(name, None)   # was der Text ausnimmt, wird nicht eingefärbt
    return (sorted(gebiete.values(), key=lambda g: (-g['stufe'], g['name'])),
            sorted(ausgenommen_gesamt), unaufgeloest)


# ── WARNGEBIETE NACHZIEHEN (2026-09-15-2) ─────────────────────
# Die Flächen in data/warnzonen.geojson gehören zu einem bestimmten Stand des amtlichen Textes.
# Ändert das Auswärtige Amt eine Warnung — ein County kommt dazu, eines fällt weg —, holt der
# Assistent den neuen TEXT von allein, die Flächen blieben aber alt. Genau das wäre gefährlich:
# Die Karte zeigte dann eine Warnung, die es so nicht mehr gibt, oder eine neue eben nicht.
# Deshalb merkt sich die Datei, aus welchem Stand je Land sie gebaut wurde, und nach jedem
# erfolgreichen Warnungs-Abruf zieht der Assistent die betroffenen Länder selbst nach —
# im Hintergrund, nur online, nur für das, was sich geändert hat.
# Abschalten: SAFARI_OHNE_WARNZONEN_AUTO=1.
WARNZONEN_DATEI = BASE_DIR / 'data' / 'warnzonen.geojson'
WARNZONEN_SKRIPT = BASE_DIR / 'fetch-warnzonen.py'
WARNZONEN_MIN_ABSTAND_H = 6          # nicht öfter als alle 6 Stunden automatisch nachziehen
WARNZONEN_STATE = {'laeuft': False, 'letzter_lauf': 0.0, 'meldung': '', 'letzte_laender': []}


def warnzonen_lesen():
    try:
        d = json.loads(WARNZONEN_DATEI.read_text(encoding='utf-8'))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def warnzonen_veraltet(laender_daten=None):
    """Länder, deren Flächen nicht zum aktuellen Warntext passen — inklusive solcher, für die es
    noch gar keine Flächen gibt. Verglichen wird das Stand-Datum, das beim Bauen vermerkt wurde."""
    daten = warnzonen_lesen()
    staende = daten.get('staende') or {}
    if laender_daten is None:
        laender_daten = (reisewarnungen_lesen().get('laender') or {})
    veraltet = []
    for land in REISEWARN_LAENDER:
        aa = (laender_daten.get(land['name']) or {}).get('aa') or {}
        if not aa:
            continue
        jetzt = aa.get('stand') or aa.get('geaendert') or ''
        if not jetzt:
            continue
        if staende.get(land['name']) != jetzt:
            veraltet.append(land['name'])
    return veraltet


def warnzonen_status():
    daten = warnzonen_lesen()
    return {'da': bool(daten.get('features')), 'erzeugt': daten.get('erzeugt') or '',
            'flaechen': len(daten.get('features') or []),
            'veraltet': warnzonen_veraltet(), 'laeuft': WARNZONEN_STATE['laeuft'],
            'meldung': WARNZONEN_STATE['meldung'],
            'unaufgeloest': daten.get('unaufgeloest') or {},
            'nicht_gefunden': daten.get('nicht_gefunden') or {}}


def warnzonen_nachziehen(laender, grund='automatisch'):
    """Startet fetch-warnzonen.py für die genannten Länder im Hintergrund. Blockiert nie eine
    Anfrage; Fehler landen sichtbar im Log und in der Meldung, nicht im Nirgendwo."""
    if os.environ.get('SAFARI_OHNE_WARNZONEN_AUTO') == '1':
        return False
    if not laender or WARNZONEN_STATE['laeuft']:
        return False
    if not WARNZONEN_SKRIPT.exists():
        WARNZONEN_STATE['meldung'] = f'fetch-warnzonen.py fehlt neben dem Server ({WARNZONEN_SKRIPT}).'
        return False

    def lauf():
        WARNZONEN_STATE.update({'laeuft': True, 'letzter_lauf': time.time(), 'letzte_laender': list(laender),
                                'meldung': f'Gebietsgrenzen werden nachgeholt ({", ".join(laender)}) …'})
        print(f'🗺  Warngebiete nachziehen ({grund}): {", ".join(laender)}')
        try:
            p = subprocess.run([sys.executable, str(WARNZONEN_SKRIPT)] + list(laender),
                               cwd=str(BASE_DIR), capture_output=True, text=True, timeout=900)
            ausgabe = (p.stdout or '')[-1500:]
            print(ausgabe.strip())
            if p.returncode == 0:
                offen = warnzonen_veraltet()
                WARNZONEN_STATE['meldung'] = ('Gebietsgrenzen aktualisiert: ' + ', '.join(laender)
                                              + (f' · weiter offen: {", ".join(offen)}' if offen else ''))
            else:
                WARNZONEN_STATE['meldung'] = ('Gebietsgrenzen konnten nicht geholt werden — '
                                              + ((p.stderr or ausgabe).strip().splitlines() or ['unbekannt'])[-1][:200])
                print('⚠️  ' + WARNZONEN_STATE['meldung'])
        except subprocess.TimeoutExpired:
            WARNZONEN_STATE['meldung'] = 'Abruf der Gebietsgrenzen hat zu lange gedauert (Overpass überlastet?).'
            print('⚠️  ' + WARNZONEN_STATE['meldung'])
        except Exception as e:
            WARNZONEN_STATE['meldung'] = f'Gebietsgrenzen: {e.__class__.__name__}: {e}'
            print('⚠️  ' + WARNZONEN_STATE['meldung'])
        finally:
            WARNZONEN_STATE['laeuft'] = False

    threading.Thread(target=lauf, daemon=True).start()
    return True


def warnzonen_pruefen_und_nachziehen():
    """Nach einem geglückten Warnungs-Abruf: passen die Flächen noch zum Text? Wenn nicht und der
    letzte Versuch ist lange genug her, wird nachgezogen — wir sind in diesem Moment nachweislich
    online, das ist die beste Gelegenheit."""
    if os.environ.get('SAFARI_OHNE_WARNZONEN_AUTO') == '1':
        return
    veraltet = warnzonen_veraltet()
    if not veraltet:
        return
    seit = time.time() - WARNZONEN_STATE['letzter_lauf']
    if seit < WARNZONEN_MIN_ABSTAND_H * 3600:
        WARNZONEN_STATE['meldung'] = (f'Flächen für {", ".join(veraltet)} sind älter als der Warntext — '
                                      f'nächster Versuch in {int((WARNZONEN_MIN_ABSTAND_H * 3600 - seit) / 60)} Min.')
        return
    warnzonen_nachziehen(veraltet)


def reisewarnungen_lesen():
    try:
        d = json.loads(REISEWARN_DATEI.read_text(encoding='utf-8'))
        return d if isinstance(d, dict) and isinstance(d.get('laender'), dict) else {}
    except (OSError, ValueError):
        return {}


def reisewarnungen_status():
    d = reisewarnungen_lesen()
    geholt = int(d.get('geholt') or 0)
    return {'geholt': geholt, 'alter_h': round((time.time() - geholt) / 3600, 1) if geholt else None,
            'laender': len(d.get('laender') or {}), 'quellen': d.get('quellen') or {},
            'laeuft': REISEWARN_STATE['laeuft'], 'meldung': REISEWARN_STATE['meldung'],
            'max_alter_h': REISEWARN_MAX_ALTER_H}


def reisewarnungen_aktualisieren():
    """Holt alle drei Quellen. Jede Quelle kann einzeln scheitern — was da ist, wird gespeichert,
    was fehlt, bleibt aus dem letzten Abruf erhalten und wird als solches ausgewiesen."""
    with REISEWARN_LOCK:
        if REISEWARN_STATE['laeuft']:
            return reisewarnungen_status()
        REISEWARN_STATE.update({'laeuft': True, 'letzter_versuch': time.time(), 'meldung': 'Abruf läuft …'})
    alt = reisewarnungen_lesen()
    laender = {k: dict(v) for k, v in (alt.get('laender') or {}).items() if isinstance(v, dict)}
    quellen = dict(alt.get('quellen') or {})
    irgendwas = False
    try:
        for schluessel, name, funktion in (
                ('aa', 'Auswärtiges Amt', aa_abrufen),
                ('fcdo', 'UK FCDO', fcdo_abrufen),
                ('usa', 'US State Department', usa_abrufen)):
            try:
                daten, hinweis = (funktion(REISEWARN_LAENDER, laender) if schluessel == 'aa'
                                  else funktion(REISEWARN_LAENDER))
                for land, eintrag in daten.items():
                    laender.setdefault(land, {})[schluessel] = eintrag
                quellen[schluessel] = {'name': name, 'ok': True, 'zeit': int(time.time()),
                                       'laender': len(daten), 'hinweis': hinweis, 'fehler': ''}
                irgendwas = irgendwas or bool(daten)
                print(f'🌐 Reisewarnungen {name}: {len(daten)} Länder' + (f' — {hinweis}' if hinweis else ''))
            except Exception as ex:
                quellen[schluessel] = {'name': name, 'ok': False, 'zeit': int(time.time()), 'laender': 0,
                                       'hinweis': '', 'fehler': f'{ex.__class__.__name__}: {ex}'}
                print(f'⚠️  Reisewarnungen {name}: {ex.__class__.__name__}: {ex}')
        if irgendwas:
            schreibe_privat(REISEWARN_DATEI, json.dumps(
                {'version': 1, 'geholt': int(time.time()), 'laender': laender, 'quellen': quellen},
                ensure_ascii=False))
            REISEWARN_STATE['meldung'] = 'Abruf abgeschlossen: ' + ', '.join(
                f'{q["name"]} {"ok" if q.get("ok") else "Fehler"}' for q in quellen.values())
            # Wir sind gerade nachweislich online — die beste Gelegenheit, veraltete Flächen nachzuziehen
            try:
                warnzonen_pruefen_und_nachziehen()
            except Exception as e:
                print(f'⚠️  Warngebiete-Prüfung: {e.__class__.__name__}: {e}')
        else:
            REISEWARN_STATE['meldung'] = ('Keine Quelle erreichbar — vermutlich offline. '
                                          'Der letzte Stand bleibt gespeichert.')
    finally:
        REISEWARN_STATE['laeuft'] = False
    return reisewarnungen_status()


def reisewarnungen_anstossen():
    """Abruf im Hintergrund starten (blockiert nie eine Anfrage)."""
    if REISEWARN_STATE['laeuft']:
        return False
    threading.Thread(target=reisewarnungen_aktualisieren, daemon=True).start()
    return True


def starte_reisewarn_wache():
    """Hält den Cache aktuell, sobald Netz da ist: ist er älter als REISEWARN_MAX_ALTER_H, wird es alle
    REISEWARN_WIEDERHOLUNG_MIN Minuten erneut versucht. Ohne Netz kostet ein Versuch nur einen Timeout."""
    def wache():
        time.sleep(20)   # Start nicht ausbremsen
        while True:
            try:
                st = reisewarnungen_status()
                veraltet = st['alter_h'] is None or st['alter_h'] >= REISEWARN_MAX_ALTER_H
                zuletzt = time.time() - REISEWARN_STATE['letzter_versuch']
                if veraltet and not REISEWARN_STATE['laeuft'] and zuletzt >= REISEWARN_WIEDERHOLUNG_MIN * 60:
                    reisewarnungen_aktualisieren()
            except Exception as e:
                print(f'⚠️  Reisewarn-Wache: {e.__class__.__name__}: {e}')
            time.sleep(60)
    threading.Thread(target=wache, daemon=True).start()


# ── SICHERHEIT (2026-09-05-1) ─────────────────────────────────
# Der Server ist ein Werkzeug für localhost + Fahrzeug-WLAN. Trotzdem gilt: Was aus dem
# Netz kommt, ist nicht vertrauenswürdig. Drei Regeln:
#  1. Dateinamen/Modulnamen aus Requests dürfen NIE Pfadbestandteile enthalten (kein ../).
#  2. Jeder Request-Body hat eine Obergrenze (sonst reicht ein Content-Length: 10 GB als DoS).
#  3. Alles, was schreibt/löscht/beendet, darf nur der Mac selbst (Loopback) aus einer
#     Seite dieses Servers auslösen — nicht das iPhone, nicht eine fremde Webseite im Browser.
MAX_JSON_BODY   = 32 * 1024 * 1024    # rag/sync, rag/search
MAX_UPLOAD_BODY = 64 * 1024 * 1024    # docs/upload
MAX_PDF_BODY    = 64 * 1024 * 1024    # extract-pdf
DOC_SUFFIXES    = ('.pdf', '.txt', '.md')
_SAFE_NAME = _re.compile(r'^[^/\\\x00-\x1f\x7f]{1,200}$')   # kein Slash/Backslash, keine Steuerzeichen, max 200 Zeichen

def safe_docs_path(module, filename, must_exist=False):
    """Liefert DOCS_DIR/<module>/<filename> — oder None, wenn einer der Teile aus dem
    Dokument-Ordner ausbrechen könnte. Prüft Syntax UND den aufgelösten Pfad (Symlinks)."""
    for teil in (module, filename):
        if not teil or teil in ('.', '..') or not _SAFE_NAME.match(teil) or teil.startswith('.'):
            return None
    if not filename.lower().endswith(DOC_SUFFIXES):
        return None
    pfad = (DOCS_DIR / module / filename)
    try:
        aufgeloest = pfad.resolve()
        wurzel = DOCS_DIR.resolve()
        if wurzel not in aufgeloest.parents:
            return None
    except (OSError, RuntimeError):
        return None
    if must_exist and not pfad.is_file():
        return None
    return pfad

def ist_loopback(ip):
    return ip in ('127.0.0.1', '::1', '::ffff:127.0.0.1') or ip.startswith('127.')

def ist_private_ip(host):
    """Loopback, RFC1918 (10/8, 172.16/12, 192.168/16), Link-local, .local — alles, was im
    Fahrzeug-WLAN oder Hotspot vorkommt. Öffentliche Hostnames (evil.example) → False."""
    h = host.lower().strip('[]')
    if h in ('localhost', '0.0.0.0') or h.endswith('.local') or ist_loopback(h):
        return True
    m = _re.match(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$', h)
    if not m:
        # Nur echte IPv6-Adressen (mit Doppelpunkt) — vorher galten auch Hostnamen wie
        # fdroid.org oder fcbarcelona.com als „privat" (Re-Audit 2026-09-12).
        return ':' in h and (h.startswith('fe80:') or h.startswith('fd') or h.startswith('fc'))
    a, b = int(m.group(1)), int(m.group(2))
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254)

def origin_host(origin):
    """'http://192.168.1.23:8765' → '192.168.1.23'; None/kaputt → ''"""
    if not origin or origin == 'null':
        return ''
    try:
        return urlparse(origin).hostname or ''
    except Exception:
        return ''

class SafariServer(ThreadingHTTPServer):
    """ThreadingHTTPServer mit Obergrenze für gleichzeitige Verbindungen (Re-Audit 2026-09-12:
    ohne Limit hält jede halboffene Verbindung aus dem WLAN einen Thread — Slowloris).
    2026-09-14-1: optional mit TLS — der WLAN-Listener fürs iPhone läuft verschlüsselt,
    Loopback bleibt unverschlüsselt (localhost gilt im Browser ohnehin als sicherer Kontext)."""
    daemon_threads = True
    allow_reuse_address = True
    MAX_VERBINDUNGEN = 64
    MAX_JE_ADRESSE = 16       # ein einzelnes Gerät im WLAN darf nicht alle Plätze belegen (Loopback: frei)

    def __init__(self, adresse, handler, ssl_kontext=None):
        self.ssl_kontext = ssl_kontext
        self._je_adresse = {}
        self._je_adresse_lock = threading.Lock()
        super().__init__(adresse, handler)

    # 2026-09-27 (Audit H2): Der TLS-Handshake lief im Accept-Thread. Sieben stumme Verbindungen
    # aus dem WLAN — ohne Zugangscode — legten damit den iPhone-Zugang lahm. Jetzt nimmt der
    # Accept-Thread nur die TCP-Verbindung an; der Handshake läuft im Arbeits-Thread, mit Zeitlimit.
    def _platz_nehmen(self, ip):
        if ist_loopback(ip):
            return True
        with self._je_adresse_lock:
            n = self._je_adresse.get(ip, 0)
            if n >= self.MAX_JE_ADRESSE:
                return False
            self._je_adresse[ip] = n + 1
            return True

    def _platz_freigeben(self, ip):
        if ist_loopback(ip):
            return
        with self._je_adresse_lock:
            n = self._je_adresse.get(ip, 0) - 1
            if n > 0:
                self._je_adresse[ip] = n
            else:
                self._je_adresse.pop(ip, None)

    def process_request(self, request, client_address):
        ip = client_address[0] if client_address else ''
        if threading.active_count() > self.MAX_VERBINDUNGEN + 6 or not self._platz_nehmen(ip):   # + Wächter-/Hintergrund-Threads
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._platz_freigeben(ip)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._platz_freigeben(client_address[0] if client_address else '')

    def finish_request(self, request, client_address):
        if self.ssl_kontext is None:
            self.RequestHandlerClass(request, client_address, self)
            return
        try:
            request.settimeout(10)
            tls = self.ssl_kontext.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError, ValueError):
            # Ein abgelehnter Handshake (z. B. Zertifikat am iPhone noch nicht vertraut) ist kein Serverfehler.
            try:
                request.close()
            except OSError:
                pass
            return
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            self.shutdown_request(tls)


def oeffne_server(port):
    """Bindet den Server und liefert (server, adresse, lan). Standard ist 127.0.0.1 — nur dieser Mac;
    --lan/SAFARI_LAN=1 (nur für Entwicklung) bindet 0.0.0.0. Den Zugang fürs iPhone öffnet man
    zur Laufzeit per Knopf (lan_an), nicht beim Start.

    Wichtig: Ein explizites 127.0.0.1 kann scheitern, wenn das Loopback-Interface kaputt ist
    (macOS, nach Netzwerk-Tools/VPNs: 'lo0' ohne 'inet 127.0.0.1' → Errno 49 EADDRNOTAVAIL).
    Mit dem alten 0.0.0.0 fiel das nie auf. Statt wortlos zu sterben: Grund nennen, den Fix
    ausgeben und auf 0.0.0.0 ausweichen — im Busch ist ein laufender Assistent wichtiger als
    die feinere Bindung. Belegter Port wird ebenfalls benannt statt als Stacktrace geworfen."""
    lan = lan_modus_gewuenscht()
    wunsch = '0.0.0.0' if lan else '127.0.0.1'
    try:
        return SafariServer((wunsch, port), SafariHandler), wunsch, lan
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            # Erst aufräumen statt ausweichen: eine eigene Altinstanz wird beendet und der
            # gewohnte Port übernommen. Nur wenn dort FREMDE Software sitzt, weichen wir aus —
            # und sagen dann laut, auf welchem Port die App wirklich läuft.
            if alte_instanz_beenden(port):
                for _ in range(8):
                    try:
                        srv = SafariServer((wunsch, port), SafariHandler)
                        print(f'✅ Port {port} übernommen.')
                        return srv, wunsch, lan
                    except OSError:
                        time.sleep(0.25)
            info = port_belegt_von(port)
            print(f'🟡 Port {port} ist belegt' + (' — von anderer Software (nicht diesem Projekt).' if info == 'fremd'
                  else ' und lässt sich nicht übernehmen.'))
            print(f'   Wer es ist:  lsof -iTCP:{port} -sTCP:LISTEN -n -P')
            print(f'   Ist es doch dieses Projekt, half nichts: pkill -f server.py, dann neu starten.')
            for alt in range(port + 1, port + 4):
                try:
                    srv = SafariServer((wunsch, alt), SafariHandler)
                    print(f'   → Server läuft stattdessen auf Port {alt}: http://localhost:{alt}/index.html')
                    print(f'   Achtung: Lesezeichen und die iPhone-Adresse zeigen auf {port} — dort antwortet er nicht.')
                    return srv, wunsch, lan
                except OSError:
                    continue
            print(f'🔴 Auch {port + 1}–{port + 3} sind belegt. Server startet nicht.')
            raise SystemExit(1)
        if e.errno == errno.EADDRNOTAVAIL and wunsch == '127.0.0.1':
            print(f'🟡 127.0.0.1 lässt sich nicht binden ({e.strerror}) — das Loopback-Interface dieses Macs')
            print( '   hat keine 127.0.0.1. Das passiert nach Netzwerk-Tools/VPNs. Prüfen und reparieren:')
            print( '     ifconfig lo0                                    # "inet 127.0.0.1" muss dastehen')
            print( '     sudo ifconfig lo0 alias 127.0.0.1 netmask 255.0.0.0')
            print( '   (NIEMALS networksetup auf lo0 anwenden.)')
            print( '   Ausweichlösung für JETZT: Server bindet 0.0.0.0 — er ist damit im gesamten WLAN')
            print( '   erreichbar, obwohl der Netzwerk-Modus aus ist. In fremden WLANs lo0 reparieren.')
            server = SafariServer(('0.0.0.0', port), SafariHandler)
            return server, '0.0.0.0 (Ausweichlösung — lo0 defekt)', lan
        print(f'🔴 Server kann nicht auf {wunsch}:{port} starten: {e}')
        raise SystemExit(1)


def lan_modus_gewuenscht():
    """0.0.0.0 beim Start nur noch mit --lan oder SAFARI_LAN=1 (Entwicklung/Tests). Die frühere
    Marker-Datei ~/.safari-assistant-network zählt seit 2026-09-12-1 NICHT mehr: Der iPhone-Modus
    soll beim Start nie von allein an sein, sondern nur per Knopf in der App."""
    if '--localhost' in sys.argv:
        return False
    if '--lan' in sys.argv or os.environ.get('SAFARI_LAN') == '1':
        return True
    if (Path.home() / '.safari-assistant-network').exists():
        print('ℹ️  ~/.safari-assistant-network wird nicht mehr beachtet — den iPhone-Modus schaltest du')
        print('   jetzt in der App ein (⚙️ Einstellungen → iPhone-Modus). Die Datei kann weg: rm ~/.safari-assistant-network')
    return False

_SYS_PATH_START = list(sys.path)   # für die Startmeldung: was war von Haus aus da?


def benutzer_site_pfade():
    """Das Benutzer-site-packages DIESES Interpreters — dorthin installiert pip, sobald das
    systemweite Verzeichnis schreibgeschützt ist („Defaulting to user installation").
    getusersitepackages() liefert den Pfad auch dann, wenn site ihn nicht in sys.path aufgenommen
    hat; die beiden Standardorte werden zusätzlich selbst gebildet, falls site gar nichts hergibt."""
    pfade = []
    try:
        import site
        p = site.getusersitepackages()
        pfade.extend([p] if isinstance(p, str) else list(p))
    except Exception:
        pass
    v = f'{sys.version_info.major}.{sys.version_info.minor}'
    pfade.append(os.path.expanduser(f'~/Library/Python/{v}/lib/python/site-packages'))  # Apples Python
    pfade.append(os.path.expanduser(f'~/.local/lib/python{v}/site-packages'))
    einmalig = []                       # Reihenfolge behalten, Dubletten raus
    for x in pfade:
        if x and x not in einmalig:
            einmalig.append(x)
    return einmalig


def benutzer_site_ergaenzen():
    """Hängt fehlende Benutzer-site-packages an sys.path. Liefert die ergänzten Pfade.

    Warum das nötig ist (Fall vom 14.09.2026): pip meldete „Requirement already satisfied:
    pymupdf in /Users/…/Library/Python/3.9/lib/python/site-packages" für GENAU den Interpreter,
    unter dem der Server läuft — und der Server fand die Bibliothek trotzdem nicht. Aus einer
    .app heraus gestartet steht dieses Verzeichnis nicht zwangsläufig in sys.path. Statt die
    Ursache zu erraten, wird der Pfad hier gezielt nachgetragen: nur das Benutzerverzeichnis
    dieses Interpreters, nur wenn es existiert, und nur wenn der Import sonst scheitern würde."""
    ergaenzt = []
    for p in benutzer_site_pfade():
        if p and p not in sys.path and os.path.isdir(p):
            sys.path.append(p)
            ergaenzt.append(p)
    return ergaenzt


def pymupdf_gefunden():
    """Welcher Importname von PyMuPDF auffindbar ist — ohne die Bibliothek zu laden (find_spec
    sucht nur). Für die Startmeldung: Ein „PyMuPDF nicht installiert" ist praktisch immer die
    Frage, WELCHER Python gerade läuft. Steht beides im Log, ist die Diagnose eine Zeile lang."""
    import importlib.util
    def suche():
        for name in ('pymupdf', 'fitz'):
            try:
                if importlib.util.find_spec(name):
                    return name
            except (ImportError, ValueError):
                continue
        return None
    return suche() or (benutzer_site_ergaenzen() and suche()) or None


# PyMuPDF hat zwei Importnamen: „pymupdf" ist der heutige, „fitz" der historische. Je nach
# Fassung ist der eine oder andere vorhanden — wer nur „fitz" versucht, hält die Bibliothek für
# nicht installiert, obwohl sie daliegt (Fall vom 15.09.2026: pymupdf 1.26.5 installiert, die App
# meldete trotzdem „nicht installiert"). Deshalb IMMER über diesen Helfer importieren.
def pymupdf_arch_konflikt(fehler):
    """Erkennt den Fall, in dem PyMuPDF zwar daliegt, aber für eine andere Prozessorarchitektur
    gebaut ist. Das ist KEIN Installationsproblem — pip meldet dann stur „already satisfied" —,
    sondern ein Rosetta-Problem: Die App startet ein universelles python3 als x86_64."""
    return fehler is not None and 'incompatible architecture' in str(fehler)


def pymupdf_fehlertext(fehler=None):
    """Die Meldung trägt die Belege mit: Welcher Python, welche Verzeichnisse wurden abgesucht,
    existieren sie, welches HOME gilt und wie lautete der Importfehler wörtlich. Ohne das bleibt
    nur Raten — genau daran sind am 14.09.2026 mehrere Anläufe hintereinander gescheitert."""
    if pymupdf_arch_konflikt(fehler):
        return (f'PyMuPDF ist installiert, passt aber nicht zur Architektur dieses Prozesses: Der Server '
                f'läuft als {platform.machine()}, die Bibliothek ist für eine andere Architektur gebaut. '
                f'Ein erneutes „pip install" hilft hier NICHT — pip meldet „already satisfied". Ursache ist '
                f'fast immer Rosetta: Die App startet ein universelles python3 übersetzt. Abhilfe: im Finder '
                f'„Safari Assistant.app" (bzw. „DARK.app" oder „Safari Assistent.app") → Informationen → „Mit Rosetta öffnen" ausschalten und die App neu '
                f'starten (der Launcher erzwingt ab 2026-09-16 zusätzlich „arch -arm64"). '
                f'· Python: {sys.executable} · Importfehler: {fehler}')
    pfade = '; '.join(f'{p} ({"vorhanden" if os.path.isdir(p) else "fehlt"})'
                      for p in benutzer_site_pfade()) or 'keine'
    teile = [f'PyMuPDF ist für DIESEN Python nicht importierbar (weder als „pymupdf" noch als '
             f'„fitz"): {sys.executable}']
    if fehler is not None:
        teile.append(f'Importfehler: {fehler.__class__.__name__}: {fehler}')
    teile.append(f'Abgesuchte Benutzerverzeichnisse: {pfade}')
    teile.append(f'HOME: {os.path.expanduser("~")}')
    teile.append(f'Im Terminal ausführen und den Assistenten danach neu starten:  '
                 f'"{sys.executable}" -m pip install pymupdf   '
                 f'(antwortet pip mit „externally-managed-environment", --break-system-packages anhängen)')
    return ' · '.join(teile)


def _pymupdf_importieren():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def lade_fitz():
    """Liefert das PyMuPDF-Modul unter welchem Namen auch immer — oder wirft ImportError.
    Scheitert der Import, wird einmal das Benutzer-site-packages nachgetragen und erneut
    versucht (siehe benutzer_site_ergaenzen)."""
    try:
        return _pymupdf_importieren()
    except ImportError:
        if not benutzer_site_ergaenzen():
            raise
        return _pymupdf_importieren()


# ── RAG: PDF-Chunking ─────────────────────────────────────────
# Zerlegt PDF in überlappende Abschnitte mit Kapitel- und Seitenangabe.
# Wird vom /api/extract-pdf Endpunkt genutzt (IndexedDB-Speicherung im Browser).
RAG_CHUNK_WORDS = 450
RAG_CHUNK_OVERLAP = 60
RAG_MIN_CHUNK = 30
MAX_PDF_SEITEN = 2500          # Re-Audit 2026-09-12: ein präpariertes PDF darf den Mac nicht lahmlegen
MAX_PDF_ZEICHEN = 12_000_000   # ~ ein sehr dickes Werkstatthandbuch; darüber wird abgebrochen

def extract_pdf_chunks(pdf_bytes):
    """Rückgabe: (chunks, total_pages). chunks = [{text, chapter, page}]"""
    fitz = lade_fitz()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    if total_pages > MAX_PDF_SEITEN:
        doc.close()
        raise ValueError(f'PDF hat {total_pages} Seiten — Limit {MAX_PDF_SEITEN}. Bitte aufteilen.')
    zeichen = 0
    chunks = []
    current_chapter = "Einleitung"
    word_buffer = []  # Liste von (wort, seite)

    def flush(chapter):
        nonlocal word_buffer
        if not word_buffer:
            return
        i = 0
        while i < len(word_buffer):
            window = word_buffer[i:i + RAG_CHUNK_WORDS]
            if len(window) < RAG_MIN_CHUNK and chunks:
                break
            text = " ".join(w for w, _ in window).strip()
            start_page = window[0][1] if window else 1
            if text:
                chunks.append({"text": text, "chapter": chapter, "page": start_page})
            i += max(1, RAG_CHUNK_WORDS - RAG_CHUNK_OVERLAP)
        word_buffer = []

    for page_num in range(total_pages):
        page = doc[page_num]
        page_label = page_num + 1
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                line_text = "".join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue
                max_size = max((s.get("size", 0) for s in spans), default=0)
                is_bold = any("bold" in s.get("font", "").lower() for s in spans)
                is_heading = (
                    len(line_text) < 80
                    and (max_size >= 13 or is_bold)
                    and len(line_text.split()) <= 10
                    and not line_text.endswith(('.', ',', ';', ':'))
                    and (max_size >= 13 or _re.match(r'^\s*(\d+[\.\)]|[A-ZÄÖÜ][A-ZÄÖÜ\s]{3,})', line_text))
                )
                if is_heading and len(line_text) > 3:
                    flush(current_chapter)
                    current_chapter = line_text[:80]
                else:
                    zeichen += len(line_text)
                    if zeichen > MAX_PDF_ZEICHEN:
                        doc.close()
                        raise ValueError(f'PDF enthält mehr als {MAX_PDF_ZEICHEN // 1_000_000} Mio. Zeichen Text — Limit erreicht. Bitte aufteilen.')
                    for word in line_text.split():
                        word_buffer.append((word, page_label))
                    if len(word_buffer) >= RAG_CHUNK_WORDS * 2:
                        flush(current_chapter)
    flush(current_chapter)
    doc.close()
    return chunks, total_pages

# MBTiles Datei suchen
def find_mbtiles():
    for f in BASE_DIR.glob('*.mbtiles'):
        return f
    return None

# MBTiles Kachel lesen (SQLite)
def get_tile(mbtiles_path, z, x, y):
    """Liest eine Kachel aus einer .mbtiles Datei.
    MBTiles verwendet TMS-Schema (Y ist invertiert)."""
    try:
        y_tms = (2 ** z - 1) - y  # TMS → XYZ konvertieren
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        cur.execute(
            'SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
            (z, x, y_tms)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
        return None
    except Exception as e:
        return None

def get_mbtiles_metadata(mbtiles_path):
    try:
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        cur.execute('SELECT name, value FROM metadata')
        meta = dict(cur.fetchall())
        conn.close()
        return meta
    except:
        return {}

def is_vector_mbtiles(mbtiles_path):
    """Prüft ob MBTiles Vektor- oder Raster-Kacheln enthält."""
    try:
        meta = get_mbtiles_metadata(mbtiles_path)
        fmt = meta.get('format', '')
        if fmt == 'pbf':
            return True
        if fmt in ['png', 'jpg', 'jpeg']:
            return False
        # Format nicht in Metadata — erste Kachel prüfen
        conn = sqlite3.connect(str(mbtiles_path))
        cur = conn.cursor()
        cur.execute('SELECT tile_data FROM tiles LIMIT 1')
        row = cur.fetchone()
        conn.close()
        if row:
            data = row[0]
            # Gzip-Header = wahrscheinlich PBF (Vektor)
            if data[:2] == b'\x1f\x8b':
                return True
            # PNG-Header
            if data[:4] == b'\x89PNG':
                return False
        return False
    except:
        return False


# ── KIWIX: Offline-Wikipedia (kiwix-serve als Kind-Prozess) ───
# ZIM-Dateien (z. B. wikipedia_en_medicine_maxi) liegen NICHT im App-Bundle (zu groß) —
# gesucht wird in BASE_DIR und im Projektordner auf dem Desktop (A_docs/Wiki bzw. Wiki).
# kiwix-serve bindet nach Möglichkeit nur 127.0.0.1:8090 — das iPhone liest Wikipedia über den
# Assistenten (/wiki, mit Zugangscode und TLS), nicht direkt (2026-09-27, Review).
# Fehlt Binary oder ZIM, startet nichts still — /api/kiwix/status nennt den Grund.
KIWIX_PORT = 8090
KIWIX_PROC = None
# 2026-09-14-1: Seit der iPhone-Zugang über https läuft, kann das iPhone den direkten Link auf
# http://<Mac>:8090 nicht mehr öffnen (Safaris HTTPS-Only-Modus blockt ihn). Deshalb startet
# kiwix-serve nach Möglichkeit unter dem Pfad /wiki und wird vom Assistenten durchgereicht —
# dann läuft Wikipedia am iPhone über dieselbe verschlüsselte Adresse.
# Ob die installierte kiwix-Version --urlRootLocation kennt, wird beim Start GEPRÜFT: antwortet sie
# unter /wiki nicht, startet der Server sie wie bisher ohne den Schalter (KIWIX_ROOT bleibt leer)
# und die App sagt dem Nutzer, warum das Öffnen am iPhone nicht geht.
KIWIX_ROOT = ''
# Wiki-RAG-Suchbegriffe: die ZIMs sind englisch → deutsche Frage vor der Suche in englische
# Stichwörter übersetzen (schnelles lokales Modell). Fällt bei Ollama-Problemen auf die Rohfrage
# zurück (englische Fragen funktionieren dann weiterhin).
WIKI_TRANSLATE_MODEL = 'gemma4:e4b'
OLLAMA_BASE = 'http://127.0.0.1:11434'

# 2026-09-27 (Audit L3): Anfragen aus dem WLAN (iPhone) dürfen das Modell nicht dauerhaft im
# Speicher festnageln (keep_alive) oder unbegrenzt generieren lassen. Erlaubt sind nur übliche
# Sampling-Optionen, Kontext und Antwortlänge werden gedeckelt.
OLLAMA_LAN_OPTIONEN = {'temperature', 'top_p', 'top_k', 'min_p', 'repeat_penalty', 'seed', 'stop', 'num_ctx', 'num_predict'}

def ollama_optionen_begrenzen(daten):
    daten = dict(daten)
    daten.pop('keep_alive', None)
    opt = daten.get('options')
    if not isinstance(opt, dict):
        daten.pop('options', None)
        return daten
    sauber = {}
    for k, v in opt.items():
        if k not in OLLAMA_LAN_OPTIONEN:
            continue
        if k == 'stop':
            if isinstance(v, list) and len(v) <= 8 and all(isinstance(x, str) and len(x) <= 40 for x in v):
                sauber[k] = v
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if k == 'num_ctx':
            v = int(max(512, min(v, 32768)))
        elif k == 'num_predict':
            v = 8192 if v < 0 else int(max(1, min(v, 8192)))
        sauber[k] = v
    daten['options'] = sauber
    return daten

def kiwix_zim_dirs():
    heim = Path.home() / 'Desktop' / 'safari-assistant'
    # ~/safari-zim = TCC-freier Ausweichpfad: liegt NICHT unter Desktop/Dokumente → macOS
    # blockt ihn nie. Falls Festplattenvollzugriff für die .app nicht greift: ZIMs dorthin
    # verschieben (mv ist auf demselben Volume sofort fertig, auch bei 50 GB).
    return [BASE_DIR / 'A_docs' / 'Wiki', BASE_DIR / 'Wiki',
            heim / 'A_docs' / 'Wiki', heim / 'Wiki', Path.home() / 'safari-zim']

def find_kiwix_zims():
    for d in kiwix_zim_dirs():
        if d.is_dir():
            zims = sorted(d.glob('*.zim'))
            if zims:
                return zims
    return []

def find_kiwix_bin():
    # Auch neben den ZIMs (~/safari-zim) und im Bundle suchen — Binary dort ablegen braucht kein sudo
    kandidaten = (shutil.which('kiwix-serve'), '/opt/homebrew/bin/kiwix-serve', '/usr/local/bin/kiwix-serve',
                  str(Path.home() / 'safari-zim' / 'kiwix-serve'), str(BASE_DIR / 'kiwix-serve'))
    for k in kandidaten:
        if k and Path(k).is_file() and os.access(k, os.X_OK):
            return k
    return None

def kiwix_antwortet(pfad):
    """Liefert kiwix unter diesem Pfad wirklich eine Seite? (Prüfung für --urlRootLocation)"""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{KIWIX_PORT}{pfad}', timeout=3) as r:
            return 200 <= r.status < 400
    except urllib.error.HTTPError as e:
        return e.code < 400
    except Exception:
        return False


def kiwix_laeuft():
    try:
        with socket.create_connection(('127.0.0.1', KIWIX_PORT), timeout=0.5):
            return True
    except OSError:
        return False

def kiwix_zugriffsproblem():
    """macOS-TCC erkennen: blockt das System den Desktop-Zugriff der App, liefert stat()
    EPERM — Path.is_dir() schluckt das still und sieht aus wie 'Ordner fehlt'. Hier
    explizit prüfen, damit die Fehlermeldung die WAHRE Ursache nennt (nie still scheitern)."""
    for d in kiwix_zim_dirs():
        try:
            d.stat()
        except PermissionError:
            return str(d)
        except OSError:
            pass  # existiert nicht o. ä. — kein Rechteproblem
    return None

def kiwix_proxy_pfad():
    """Pfad, unter dem die App die Wikipedia durchreicht — leer, wenn das nicht geht."""
    return (KIWIX_ROOT + '/') if KIWIX_ROOT else ''


def kiwix_grund():
    if kiwix_laeuft():
        return ''
    blockiert = kiwix_zugriffsproblem()
    if blockiert:
        return ('macOS blockiert den Zugriff der App auf ' + blockiert + ' — Systemeinstellungen → '
                'Datenschutz & Sicherheit → Dateien und Ordner → der App den Schreibtisch erlauben '
                '(oder Festplattenvollzugriff), danach App neu starten.')
    if not find_kiwix_zims():
        return 'Keine ZIM-Dateien gefunden (A_docs/Wiki/ bzw. Wiki/ im Projektordner oder ~/safari-zim).'
    if not find_kiwix_bin():
        return 'kiwix-serve nicht installiert — kiwix-tools von download.kiwix.org laden und kiwix-serve nach ~/safari-zim/ legen'
    return 'kiwix-serve nicht gestartet (Server/App neu starten).'

def start_kiwix():
    global KIWIX_PROC
    if kiwix_laeuft():
        print(f'📚 Offline-Wikipedia: kiwix-serve läuft schon auf :{KIWIX_PORT}')
        return
    zims, kbin = find_kiwix_zims(), find_kiwix_bin()
    if not zims or not kbin:
        print('📚 Offline-Wikipedia: aus — ' + kiwix_grund())
        return
    # Aufrufe in absteigender Wunschreihenfolge. Zuerst nur auf 127.0.0.1 (2026-09-27, Review:
    # vorher lauschte kiwix auf allen Schnittstellen — Wikipedia war im WLAN ohne Zugangscode
    # lesbar). Achtung: kiwix-serve 3.8.2 lehnte „--address 0.0.0.0" mit „Arguments did not match
    # expected patterns" ab und beendete sich; deshalb wird jeder Aufruf geprüft und notfalls der
    # nächste versucht — zuletzt exakt der von Hand funktionierende: kiwix-serve --port 8090 <zims>.
    global KIWIX_ROOT
    KIWIX_ROOT = ''
    versuche = ((['--address=127.0.0.1', '--urlRootLocation', '/wiki'], True, True),
                (['--urlRootLocation', '/wiki'], True, False),
                ([], False, False))
    nur_lokal = False
    import time as _t
    for zusatz, mit_pfad, lokal in versuche:
        with _log_oeffnen('kiwix.log') as logf:
            KIWIX_PROC = subprocess.Popen(
                [kbin, '--port', str(KIWIX_PORT)] + zusatz + [str(z) for z in zims],
                stdout=logf, stderr=subprocess.STDOUT)
        # Nicht blind "gestartet" melden — nachprüfen, ob der Prozess lebt und der Port antwortet.
        # Große ZIM-Archive brauchen Sekunden bis zum ersten Lauschen: solange der Prozess lebt, wird
        # gewartet (bis 30 s). Zum nächsten Aufruf geht es NUR, wenn kiwix sich beendet hat — also den
        # Aufruf abgelehnt hat. Vorher löste schon ein langsamer Start den Rückfall ohne --address aus
        # (Final-Audit 2026-09-27): dann lauschte Wikipedia auf allen Schnittstellen.
        ende = _t.time() + 30
        while _t.time() < ende:
            if KIWIX_PROC.poll() is not None or kiwix_laeuft():
                break
            _t.sleep(0.3)
        if KIWIX_PROC.poll() is None and not kiwix_laeuft():
            print('⚠️  kiwix-serve antwortet nach 30 s noch nicht — läuft weiter; Status: /api/kiwix/status')
            KIWIX_ROOT = '/wiki' if mit_pfad else ''
            nur_lokal = lokal
            break
        if kiwix_laeuft() and (not mit_pfad or kiwix_antwortet('/wiki/')):
            KIWIX_ROOT = '/wiki' if mit_pfad else ''
            nur_lokal = lokal
            break
        stoppe_kiwix()
    if kiwix_laeuft():
        print(f'📚 Offline-Wikipedia: kiwix-serve auf :{KIWIX_PORT} — {len(zims)} ZIM ({", ".join(z.name for z in zims)})')
        if not nur_lokal:
            print('⚠️  Diese kiwix-Version kennt --address nicht: Wikipedia lauscht auf allen Schnittstellen '
                  f'(Port {KIWIX_PORT}) und ist im WLAN ohne Zugangscode lesbar. Abhilfe: kiwix-tools aktualisieren.')
        if not KIWIX_ROOT:
            print('📚 kiwix-serve kennt --urlRootLocation nicht — Wikipedia lässt sich dann nur am Mac öffnen, nicht am iPhone.')
    else:
        log = ''
        try:
            log = log_datei('kiwix.log').read_text(errors='replace')[-400:].strip()
        except Exception:
            pass
        print(f'🔴 kiwix-serve startet nicht (Exit-Code {KIWIX_PROC.poll()}) — {log_datei("kiwix.log")}: {log or "leer"}')
        print(f'   Häufigste Ursache: macOS-Quarantäne → xattr -d com.apple.quarantine {kbin}')

def stoppe_kiwix():
    global KIWIX_PROC
    if KIWIX_PROC:
        try:
            KIWIX_PROC.terminate()
        except Exception:
            pass
        KIWIX_PROC = None


# ── WIKI-RAG: Kiwix-Volltextsuche für die Chat-Module ─────────
# /api/wiki/search?query=...&k=3 → Artikel-Auszüge als Faktenbasis (zuschaltbar pro Modul
# im Frontend). Bücher aus dem Kiwix-OPDS-Katalog, Medizin-ZIM zuerst (beste Quelle).
# Kiwix aus → available:false + Grund (nie still scheitern).
_WIKI_BUECHER = None

def wiki_buecher():
    global _WIKI_BUECHER
    if _WIKI_BUECHER is not None:
        return _WIKI_BUECHER
    # books.name = ZIM-Dateiname OHNE .zim — genau das erwartet kiwix-serve (per Handstart-curl
    # bestätigt: books.name=wikipedia_en_medicine_maxi_2026-04 liefert Treffer). Der frühere Weg
    # über den OPDS-Katalog lieferte abweichende/zusätzliche <name>-Werte → Suche fand nichts.
    # Vorteil: funktioniert direkt aus den Dateinamen, unabhängig davon, ob Kiwix schon HTTP kann.
    stems = [z.stem for z in find_kiwix_zims()]
    if not stems:
        return []
    # Medizin zuerst — kuratierteste Quelle für die Kern-Module (medizin/hund/natur)
    _WIKI_BUECHER = sorted(set(stems), key=lambda b: (0 if 'medicine' in b else 1, b))
    return _WIKI_BUECHER

def wiki_html_zu_text(html):
    html = _re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    html = _re.sub(r'(?is)<[^>]+>', ' ', html)
    for a, b in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&#39;', "'"), ('&quot;', '"'), ('&nbsp;', ' ')):
        html = html.replace(a, b)
    return _re.sub(r'\s+', ' ', html).strip()

def wiki_suchbegriffe(query):
    """Frage (meist Deutsch) → 2-4 englische Suchbegriffe fürs englische ZIM.
    Bei Ollama-Fehler/Timeout: Rohfrage zurück (englische Fragen bleiben nutzbar)."""
    q = query.strip()
    if len(q) < 2:
        return q
    prompt = ('Extract 2 to 4 English search keywords for an offline Wikipedia full-text search '
              'from this question. Reply with ONLY the keywords separated by spaces, no other text, '
              'no punctuation, no explanation.\n\nQuestion: ' + q + '\nKeywords:')
    try:
        import urllib.request
        body = json.dumps({'model': WIKI_TRANSLATE_MODEL, 'prompt': prompt, 'stream': False,
                           'options': {'temperature': 0, 'num_predict': 24}}).encode()
        req = urllib.request.Request(OLLAMA_BASE + '/api/generate', data=body,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as r:
            out = (json.load(r).get('response') or '').strip()
        out = out.splitlines()[0] if out else ''
        out = _re.sub(r'[^A-Za-z0-9 -]', ' ', out)      # nur Wörter, kein Modell-Geschwätz
        out = _re.sub(r'\s+', ' ', out).strip()
        return out or q
    except Exception:
        return q  # Ollama weg → Rohfrage (englische Eingaben funktionieren weiter)


def wiki_suche(query, k=3, max_chars=1600):
    """Volltextsuche über alle ZIMs → [{titel, buch, auszug, url}] (url = /viewer#-Pfad für den Browser)."""
    import urllib.request
    from urllib.parse import quote
    quellen, gesehen = [], set()
    for buch in wiki_buecher():
        if len(quellen) >= k:
            break
        try:
            such_url = (f'http://127.0.0.1:{KIWIX_PORT}/search?books.name={quote(buch)}'
                        f'&pattern={quote(query)}&pageLength=4')
            with urllib.request.urlopen(such_url, timeout=5) as r:
                seite = r.read().decode('utf-8', 'ignore')
            # Tolerant: jeden Artikel-Link (Viewer ODER Content, mit/ohne ROOT-Präfix) einsammeln.
            # kiwix-serve-HTML variiert je Version — daher breit fangen statt auf ein Format wetten.
            for m in _re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', seite, _re.S):
                if len(quellen) >= k:
                    break
                href, titel_html = m.group(1), m.group(2)
                mm = _re.search(r'(?:/viewer#|/content/)([^"?#]+)', href)
                if not mm:
                    continue
                pfad = mm.group(1)
                if pfad in gesehen:
                    continue
                gesehen.add(pfad)
                titel = wiki_html_zu_text(titel_html) or pfad.rsplit('/', 1)[-1]
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{KIWIX_PORT}/content/{pfad}', timeout=5) as ar:
                        auszug = wiki_html_zu_text(ar.read().decode('utf-8', 'ignore'))[:max_chars]
                except Exception:
                    continue
                if len(auszug) < 200:
                    continue  # Redirect-/Stub-Seiten überspringen
                quellen.append({'titel': titel, 'buch': buch, 'auszug': auszug, 'url': '/viewer#' + pfad})
        except Exception:
            continue
    return quellen


# ── OFFLINE-ORTSSUCHE: GeoNames-Index (data/orte.json, fetch-orte.py) ──
# Für das Suchfeld der POI-Karte. Index ist nach Population vorsortiert → einfache
# lineare Suche mit Scoring (exakt > Präfix > Substring) reicht auch bei 100k+ Einträgen.
_ORTE_CACHE = None  # {'laender': [...], 'orte': [[name, lat, lng, landIdx, typ, pop], ...]}

def orte_index():
    global _ORTE_CACHE
    if _ORTE_CACHE is not None:
        return _ORTE_CACHE
    f = BASE_DIR / 'data' / 'orte.json'
    if not f.is_file():
        return None
    try:
        j = json.loads(f.read_text())
        # Suchnamen einmalig vorberechnen (lowercase) — spart es pro Anfrage
        j['_such'] = [o[0].lower() for o in j.get('orte', [])]
        _ORTE_CACHE = j
    except Exception:
        return None
    return _ORTE_CACHE

def orte_suche(query, k=8):
    idx = orte_index()
    if not idx:
        return None
    q = query.lower().strip()
    treffer = []
    for i, name_l in enumerate(idx['_such']):
        pos = name_l.find(q)
        if pos < 0:
            continue
        score = 3 if name_l == q else (2 if pos == 0 else 1)
        o = idx['orte'][i]
        treffer.append((score, o[5], o))
        if len(treffer) >= 400:  # Index ist pop-sortiert — reicht für die Top-k locker
            break
    treffer.sort(key=lambda t: (-t[0], -t[1]))
    typ_label = {'o': 'Ort', 'b': 'Berg/Pass', 'w': 'See/Wasserfall', 'f': 'Flughafen'}
    return [{'name': o[0], 'lat': o[1], 'lng': o[2], 'land': idx['laender'][o[3]],
             'typ': typ_label.get(o[4], 'Ort'), 'pop': o[5]} for _, _, o in treffer[:k]]


# ── RAG-MOBILE: Chunk-Store + Suche (v2026-07-14-1) ──────────
# (server.py Stand 2026-07-16-1: CORS auf JEDER Antwort (end_headers-Override) — Fix für cross-origin
#  Glyph-Fetches (Seite :8766 → API :8765), die vorher "Load failed"/schwarze Vektor-Karte verursachten;
#  14-5: + Info-Layer (Flughäfen, POIs, Parks, Gewässer, Bahn, Gipfel); 14-4: Straßennamen; 14-3: ThreadingHTTPServer, Label-minzoom; 14-2: /fonts/-Fallback, lokale Glyphs)
# index.html spiegelt die IndexedDB-Chunks hierher (POST /api/rag/sync → rag-store.json).
# mobile.html sucht dann via POST /api/rag/search — das iPhone hat keinen Zugriff auf die
# IndexedDB des Mac-Browsers. Das Scoring MUSS der searchDocs()-Logik in index.html
# entsprechen: Stoppwörter, Terme >= 3 Zeichen, Vorkommen zählen, Kapitel-Bonus +3, Top-K.
RAG_STORE_FILE = BASE_DIR / 'rag-store.json'
RAG_STOPWORDS = {'der','die','das','und','ist','ich','wie','was','ein','eine','mit','für','den','dem','auf','von','sich','nicht','auch','bei','aus','hat','wird','kann','muss','soll','beim','oder','aber','wenn','dann','noch','nur','des','zur','zum'}
_rag_cache = {'mtime': None, 'data': None}
_rag_lock = threading.Lock()

def load_rag_store():
    """Store mit mtime-Cache laden. Rückgabe: {'docs': [...], 'chunks': [...]} oder None."""
    with _rag_lock:
        if not RAG_STORE_FILE.exists():
            return None
        mtime = RAG_STORE_FILE.stat().st_mtime
        if _rag_cache['mtime'] != mtime:
            try:
                _rag_cache['data'] = json.loads(RAG_STORE_FILE.read_text(encoding='utf-8'))
                _rag_cache['mtime'] = mtime
            except Exception:
                return None
        return _rag_cache['data']

def save_rag_store(data):
    with _rag_lock:
        tmp = RAG_STORE_FILE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(RAG_STORE_FILE)
        _rag_cache['mtime'] = None  # Cache invalidieren

def rag_terms(query):
    """Suchterme wie in index.html searchDocs(): lowercase, Sonderzeichen raus, >=3 Zeichen, keine Stoppwörter."""
    cleaned = _re.sub(r'[^a-z0-9_äöüß\s]', ' ', query.lower())
    return [t for t in cleaned.split() if len(t) >= 3 and t not in RAG_STOPWORDS]

def rag_search(query, module, k=4):
    """Port von searchDocs() aus index.html. Rückgabe: Liste Treffer-Chunks mit score, absteigend."""
    store = load_rag_store()
    if not store:
        return None  # None = noch nie gesynct (unterscheidbar von 0 Treffern)
    doc_ids = {d['id'] for d in store.get('docs', []) if module in d.get('modules', [])}
    if not doc_ids:
        return []
    terms = rag_terms(query)
    if not terms:
        return []
    scored = []
    for chunk in store.get('chunks', []):
        if chunk.get('docId') not in doc_ids:
            continue
        lower = chunk.get('text', '').lower()
        chapter = chunk.get('chapter', '').lower()
        score = 0
        for term in terms:
            score += lower.count(term)
            if term in chapter:
                score += 3
        if score > 0:
            scored.append({**chunk, 'score': score})
    scored.sort(key=lambda c: -c['score'])
    return scored[:k]


# ── HILFE (2026-10-04-1): die Anleitung (README) als Seite /hilfe, offline, vier Sprachen ──
# hilfe.py (Markdown-Renderer + Seite) liegt neben server.py. Geladen wird über den Pfad, nicht über
# sys.path — die Tests laden server.py selbst über importlib, dann steht sein Ordner nicht in
# sys.path —, und ohne __pycache__: .pyc-Dateien enthalten absolute Pfade (Datenschutz, Git-Repo).
# Fehlt hilfe.py (älteres Bundle), läuft der Rest der App weiter; /hilfe sagt dann, was fehlt.
def _hilfe_laden():
    import importlib.util
    alt = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location('dark_hilfe', str(BASE_DIR / 'hilfe.py'))
        modul = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modul
        spec.loader.exec_module(modul)
        return modul, ''
    except Exception as e:
        sys.modules.pop('dark_hilfe', None)
        return None, f'{e.__class__.__name__}: {e}'
    finally:
        sys.dont_write_bytecode = alt

HILFE, HILFE_FEHLER = _hilfe_laden()


# Statische Auslieferung: NUR die App-Dateien (Re-Audit 2026-09-12 — vorher lieferte der Server den
# ganzen Projektordner aus, inkl. .git, rag-store.json, server.py und Verzeichnislisten ins WLAN).
STATIK_DATEIEN = {'/': '/index.html', '/index.html': '/index.html', '/mobile.html': '/mobile.html', '/pois.html': '/pois.html',
                  '/data/parks.geojson': '/data/parks.geojson', '/data/warnzonen.geojson': '/data/warnzonen.geojson', '/data/orte.json': '/data/orte.json',
                  '/data/klima.json': '/data/klima.json',   # 2026-09-24-1: Klimatologie der Regenzeit-Ebene (fetch-klima.py)
                  '/dark-logo.jpg': '/dark-logo.jpg',       # 2026-09-25-1: Creator-Logo (Einstellungen → App, ⚙️-Sheet)
                  '/icon.png': '/icon.png',
                  # 2026-10-04-1: Oberflächensprache — i18n.js und ihre Wörterbücher (i18n/<sprache>.js)
                  '/i18n.js': '/i18n.js', '/i18n/en.js': '/i18n/en.js', '/i18n/fr.js': '/i18n/fr.js',
                  '/i18n/es.js': '/i18n/es.js'}
STATIK_PRAEFIXE = ('/vendor/', '/fonts/')
_FONT_PFAD = _re.compile(r'^/fonts/[A-Za-z0-9 ,%_.-]{1,80}/\d{1,6}-\d{1,6}\.pbf$')
LOKALE_HOSTS = ('localhost', '127.0.0.1', '::1', '0.0.0.0')

def eigene_hosts():
    """Hosts, unter denen dieser Server legitim angesprochen wird — Loopback, die aktuelle Mac-IP
    und der Bonjour-Name des Macs. Alles andere im Host-Header ist DNS-Rebinding (Re-Audit K1)."""
    h = set(LOKALE_HOSTS)
    for ip in (LAN_STATE.get('ip'), SERVER_INFO.get('mac_ip')):
        if ip:
            h.add(ip.lower())
    try:
        name = socket.gethostname().lower()
        if name:
            h.add(name)
            h.add(name.split('.')[0])
            h.add(name.split('.')[0] + '.local')
    except OSError:
        pass
    b = bonjour_name()      # 2026-10-06-1: die Adresse fürs iPhone (Lokaler Hostname), siehe bonjour_name()
    if b:
        h.add(b)
    return h

def host_ohne_port(host):
    """'192.168.1.5:8765' → '192.168.1.5'; '[::1]:8765' → '::1'; None → ''"""
    h = (host or '').strip().lower()
    if h.startswith('['):
        return h[1:h.find(']')] if ']' in h else h
    return h.rsplit(':', 1)[0] if h.count(':') == 1 else h


class SafariHandler(SimpleHTTPRequestHandler):
    server_version = 'SafariAssistant'   # kein Python-/Bibliotheksstempel im Server-Header
    sys_version = ''
    timeout = 30   # pro Verbindung — halboffene Verbindungen (Slowloris) halten keinen Thread mehr ewig

    def __init__(self, *args, **kwargs):
        self._cookie_setzen = None
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Kein Log-Spam

    def end_headers(self):
        # CORS auf JEDER Antwort — auch bei statischen Dateien/Fonts, die über super().do_GET()
        # laufen. Reflektiert wird NUR ein Origin, dessen Host dieser Server selbst ist
        # (localhost/127.0.0.1/Mac-IP/Bonjour-Name, beliebiger Port — z. B. Seite :8766 → API :8765).
        # Re-Audit 2026-09-12: vorher galt jedes RFC1918-Netz, jede *.local-Domain und jeder
        # Hostname mit „fd"/„fc" als vertrauenswürdig — damit konnte eine fremde Webseite Antworten lesen.
        # 2026-09-27 (Audit L2): nur noch derselbe Port — vorher las jede Seite eines anderen lokalen
        # Programms (http://localhost:3000) die Antworten mit. Die Seiten nutzen location.origin.
        origin = self.headers.get('Origin') if hasattr(self, 'headers') else None
        if origin and self.origin_passt(origin, eigene_hosts()):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        if self._cookie_setzen:
            sicher = '; Secure' if isinstance(self.connection, ssl.SSLSocket) else ''
            self.send_header('Set-Cookie', f'safari_zugang={self._cookie_setzen}; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly{sicher}')
            self._cookie_setzen = None
        # 2026-09-27 (Audit L1): Grundschutz auf jeder Antwort. Kein Einbetten in fremde Seiten
        # (Klick-Hijacking von „Beenden"/„iPhone-Modus"), kein MIME-Raten, Referer nur als Origin.
        # Eine volle CSP scheitert an den Inline-Handlern der Seiten (siehe docs/ROADMAP.md).
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        if not getattr(self, '_ohne_csp', False):
            # /hilfe bringt eine eigene, strengere Richtlinie mit (self._csp = hilfe.CSP: kein Skript, nichts von außen)
            self.send_header('Content-Security-Policy',
                             getattr(self, '_csp', None) or "frame-ancestors 'self'; object-src 'none'; base-uri 'self'")
        super().end_headers()

    def origin_passt(self, origin, hosts):
        """Origin-Kopf gehört zu DIESEM Server: Host in `hosts` und derselbe Port."""
        try:
            u = urlparse(origin)
            port = u.port or (443 if u.scheme == 'https' else 80)
        except (ValueError, TypeError):
            return False
        return (u.hostname or '').lower() in hosts and port == self.server.server_port

    def list_directory(self, path):
        self._error(403, 'Verzeichnislisten sind abgeschaltet')
        return None

    def client_ip(self):
        try:
            return self.client_address[0]
        except Exception:
            return ''

    def host_ok(self):
        """DNS-Rebinding-Schutz: Der Host-Header muss dieser Server selbst sein. Ohne Host-Header
        (HTTP/1.0-Werkzeuge) gibt es keinen Browser und damit kein Rebinding → erlaubt."""
        host = self.headers.get('Host')
        if not host:
            return True
        return host_ohne_port(host) in eigene_hosts()

    def _cookie(self, name):
        for teil in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = teil.strip().partition('=')
            if k == name:
                return v.strip()
        return ''

    def zugang_pruefen(self, path, params):
        """Vor JEDER Anfrage: Host-Header prüfen; vom Mac selbst (Loopback) ist alles Weitere frei.
        Aus dem WLAN: nur im iPhone-Modus und nur mit Zugangscode (Cookie, ?t=, X-Safari-Zugang).
        /go/<code> setzt das Cookie; /api/ping bleibt frei (liefert dem WLAN aber nur app+version).
        Liefert True, wenn die Anfrage bearbeitet werden darf (sonst ist die Antwort schon gesendet)."""
        if not self.host_ok():
            self._error(421, f'Ungültiger Host-Header „{self.headers.get("Host")}" — der Server antwortet nur unter '
                             f'localhost, 127.0.0.1 oder seiner WLAN-Adresse (Schutz vor DNS-Rebinding).')
            return False
        ip = self.client_ip()
        if ist_loopback(ip):
            return True
        if not LAN_STATE['an']:
            self._error(403, 'iPhone-Modus ist aus. Am Mac einschalten: ⚙️ Einstellungen → iPhone-Modus.')
            return False
        if path == '/api/ping':
            return True
        if path.startswith('/go/'):
            return True
        wert = self._cookie('safari_zugang') or params.get('t', [''])[0] or self.headers.get('X-Safari-Zugang', '')
        if token_gueltig(wert):
            if params.get('t') and not self._cookie('safari_zugang'):
                self._cookie_setzen = wert
            LAN_STATE['anfragen'] += 1
            LAN_STATE['letzte'] = time.time()
            return True
        self._error(403, 'Zugangscode fehlt oder ist falsch. Am Mac unter ⚙️ Einstellungen → iPhone-Modus steht die '
                         'vollständige Adresse (http://<Mac-IP>:8765/go/<Code>) — diese einmal am iPhone öffnen.')
        return False

    def mutation_erlaubt(self):
        """Schreibende/löschende/beendende Endpunkte: nur vom Mac selbst (Loopback) UND — falls
        ein Browser den Origin mitschickt — nur aus einer Seite DIESES Servers (localhost/127.0.0.1).
        Re-Audit 2026-09-12: vorher genügte ein „privater" Origin (jedes RFC1918-Netz, *.local,
        fd*/fc*-Hostnamen) — eine per DNS-Rebinding oder im WLAN gehostete Seite konnte damit
        Dokumente schreiben/löschen, den RAG-Store vergiften und den Server beenden.
        Liefert (ok, grund)."""
        ip = self.client_ip()
        if not ist_loopback(ip):
            return False, (f'Diese Aktion ist nur vom Mac selbst möglich (Anfrage kam von {ip}). '
                           f'Öffne die App am Mac über http://localhost:{self.server.server_port}/index.html.')
        origin = self.headers.get('Origin')
        if origin and not self.origin_passt(origin, LOKALE_HOSTS):
            return False, f'Anfrage von fremder Webseite ({origin}) abgelehnt.'
        return True, ''

    def _body_length(self, limit):
        """Content-Length prüfen und begrenzen. Liefert Länge oder None (Fehler bereits gesendet)."""
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            self._error(400, 'Content-Length ungültig')
            return None
        if length <= 0:
            self._error(400, 'Leerer Request-Body')
            return None
        if length > limit:
            self._error(413, f'Request zu groß ({length // (1024*1024)} MB) — Limit {limit // (1024*1024)} MB')
            return None
        return length

    def _int_param(self, params, name, default, maximum):
        try:
            return max(0, min(int(params.get(name, [str(default)])[0]), maximum))
        except (TypeError, ValueError):
            return default

    def send_cors(self):
        # ACAO kommt zentral aus end_headers(); hier nur Methods/Headers.
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Doc-Name, X-Safari-Zugang')

    def do_OPTIONS(self):
        parsed = urlparse(self.path)
        if not self.zugang_pruefen(parsed.path, parse_qs(parsed.query)):
            return
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def do_HEAD(self):
        """HEAD gibt es nicht (2026-10-04, Sicherheitsfix). Ohne eigene Methode lief HEAD in
        SimpleHTTPRequestHandler.do_HEAD — vorbei an zugang_pruefen (Host-Prüfung 421, iPhone-Modus,
        Zugangscode) und an STATIK_DATEIEN/_statik_pfad_ok: HEAD /server.py oder /.git/config
        lieferte 200 mit Größe und Datum, auch aus dem WLAN ohne Code. Die App braucht HEAD nicht →
        immer 405, ohne Body und ohne Dateizugriff. Alle anderen Methoden ohne do_* (PUT, PATCH,
        TRACE …) beantwortet die Standardbibliothek mit 501, ebenfalls ohne Dateizugriff."""
        self.send_response(405)
        self.send_header('Allow', 'GET, POST')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if not self.zugang_pruefen(path, params):
            return

        # ── PING: eindeutige Kennung dieses Servers ───────────────
        # Beantwortet „läuft da unser Server, auf welchem Port, mit welcher PID?" — für den
        # Launcher (wartet darauf, bevor er den Browser öffnet), für die Einstellungen im
        # Frontend und für einen Neustart, der eine Altinstanz erkennen muss.
        # Ins WLAN gehen nur Kennung und Version — PID, Pfad (= Benutzername) und Bindung nicht (N1).
        if path == '/api/ping':
            if ist_loopback(self.client_ip()):
                self._json(dict(SERVER_INFO, app=APP_SIGNATUR, version=SERVER_VERSION,
                                pid=os.getpid(), laeuft_seit_s=int(time.time() - START_ZEIT),
                                mac_ip=lan_ip(), lan=LAN_STATE['an'], iphone=lan_status()))
            else:
                self._json({'app': APP_SIGNATUR, 'version': SERVER_VERSION, 'port': SERVER_INFO.get('port'), 'lan': True})
            return

        # ── REISEWARNUNGEN: gespeicherter Stand (offline lesbar, auch vom iPhone) ──
        if path == '/api/reisewarnungen':
            d = reisewarnungen_lesen()
            self._json({'laender': d.get('laender') or {}, 'status': reisewarnungen_status(),
                        'warnzonen': warnzonen_status(),
                        'hinweis': ('Amtliche Texte, wörtlich übernommen: Auswärtiges Amt (maßgeblich), '
                                    'UK FCDO, US State Department. Vor Reiseentscheidungen den Originaltext '
                                    'der Quelle lesen — Stand und Link stehen bei jedem Eintrag.')})
            return

        # ── iPHONE-MODUS: Status (nur vom Mac) ────────────────────
        if path == '/api/netz/status':
            if not ist_loopback(self.client_ip()):
                self._error(403, 'Nur vom Mac selbst abrufbar.')
                return
            self._json(lan_status())
            return

        # ── /go/<code>: Zugangscode als Cookie setzen, dann zur iPhone-Seite ──
        if path.startswith('/go/'):
            code = path[len('/go/'):].strip('/').lower()
            if not token_gueltig(code):
                self._error(403, 'Dieser Zugangscode ist ungültig. Aktuelle Adresse am Mac: ⚙️ Einstellungen → iPhone-Modus.')
                return
            self._cookie_setzen = code
            self.send_response(302)
            self.send_header('Location', '/mobile.html?t=' + code)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return

        # ── WIKIPEDIA-PROXY: /wiki/... → kiwix-serve auf 127.0.0.1:8090 ──
        # Damit läuft die Offline-Wikipedia am iPhone über dieselbe verschlüsselte Adresse wie der
        # Rest der App. Gegenstelle ist fest verdrahtet (kein SSRF), der Pfad bleibt unterhalb von
        # /wiki, und der Zugangscode gilt wie überall (zugang_pruefen lief schon).
        if KIWIX_ROOT and (path == '/wiki' or path.startswith('/wiki/')):
            self._proxy_kiwix(path, parsed.query)
            return

        # ── OLLAMA-PROXY für das iPhone (GET /api/ollama/api/tags — mobile.html nutzt SERVER_URL + '/api/ollama' als Ollama-Basis) ──
        if path == '/api/ollama/api/tags':
            self._proxy_ollama('GET', '/api/tags', None)
            return

        # ── TILE API ──────────────────────────────────────────────
        # ── KIWIX-STATUS (Offline-Wikipedia — Frontend fragt vor dem Öffnen) ──
        if path == '/api/kiwix/status':
            self._json({'running': kiwix_laeuft(), 'port': KIWIX_PORT, 'proxy': kiwix_proxy_pfad(),
                        'zims': [z.name for z in find_kiwix_zims()], 'grund': kiwix_grund()})
            return

        # ── OFFLINE-ORTSSUCHE (Suchfeld der POI-Karte) ────────────
        if path == '/api/orte/search':
            query = params.get('query', [''])[0].strip()
            k = self._int_param(params, 'k', 8, 20)
            if len(query) < 2:
                self._json({'available': True, 'treffer': []})
                return
            treffer = orte_suche(query, k)
            if treffer is None:
                self._json({'available': False, 'treffer': [],
                            'grund': 'Ortsindex fehlt — einmalig: python3 fetch-orte.py, dann Server neu starten'})
                return
            self._json({'available': True, 'treffer': treffer})
            return

        # ── WIKI-RAG-SUCHE (Kiwix-Volltext → Auszüge für die Chat-Module) ──
        if path == '/api/wiki/search':
            query = params.get('query', [''])[0].strip()
            k = self._int_param(params, 'k', 3, 5)
            if not query:
                self._error(400, 'query erforderlich')
                return
            if not kiwix_laeuft():
                self._json({'available': False, 'grund': kiwix_grund(), 'quellen': []})
                return
            # DE→EN-Übersetzung, außer der Aufrufer schaltet sie ab (&translate=0)
            begriffe = query
            if params.get('translate', ['1'])[0] != '0':
                begriffe = wiki_suchbegriffe(query)
            quellen = wiki_suche(begriffe, k)
            self._json({'available': True, 'grund': '', 'suchbegriffe': begriffe, 'quellen': quellen})
            return

        if path == '/api/tiles/status':
            mbtiles = find_mbtiles()
            if mbtiles:
                meta = get_mbtiles_metadata(mbtiles)
                is_vector = is_vector_mbtiles(mbtiles)
                data = {
                    'available': True,
                    'file': mbtiles.name,
                    'format': 'pbf' if is_vector else 'png',
                    'is_vector': is_vector,
                    'name': meta.get('name', mbtiles.stem),
                    'description': meta.get('description', ''),
                    'minzoom': int(meta.get('minzoom', 0)),
                    'maxzoom': int(meta.get('maxzoom', 14)),
                    'bounds': meta.get('bounds', '')
                }
            else:
                data = {'available': False}
            self._json(data)
            return

        # /api/tiles/style.json — MapLibre GL Style für Vektor-Tiles
        if path == '/api/tiles/style.json':
            mbtiles = find_mbtiles()
            if not mbtiles:
                self._error(404, 'Keine MBTiles-Datei')
                return
            meta = get_mbtiles_metadata(mbtiles)
            bounds = meta.get('bounds', '-180,-85,180,85').split(',')
            center = [(float(bounds[0])+float(bounds[2]))/2,
                      (float(bounds[1])+float(bounds[3]))/2] if len(bounds)==4 else [25,-20]
            style = {
                "version": 8,
                "name": meta.get('name', 'Offline Karte'),
                "glyphs": f"http://localhost:{self.server.server_port}/fonts/{{fontstack}}/{{range}}.pbf",
                "sources": {
                    "openmaptiles": {
                        "type": "vector",
                        "tiles": [f"http://localhost:{self.server.server_port}/api/tiles/{{z}}/{{x}}/{{y}}"],
                        "minzoom": int(meta.get('minzoom', 0)),
                        "maxzoom": int(meta.get('maxzoom', 14)),
                        # 2026-09-27 (Review S7): OpenMapTiles-Schema (CC BY) + OSM-Daten (ODbL) nennen
                        "attribution": '© <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> '
                                       '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>-Mitwirkende'
                    }
                },
                "layers": [
                    {"id":"background","type":"background","paint":{"background-color":"#1a1916"}},
                    {"id":"water","type":"fill","source":"openmaptiles","source-layer":"water","paint":{"fill-color":"#1a2a3a"}},
                    {"id":"waterway","type":"line","source":"openmaptiles","source-layer":"waterway","paint":{"line-color":"#2a4a6a","line-width":1}},
                    {"id":"landcover-grass","type":"fill","source":"openmaptiles","source-layer":"landcover","filter":["in","class","grass","farmland","meadow"],"paint":{"fill-color":"#1a2318","fill-opacity":0.6}},
                    {"id":"landcover-wood","type":"fill","source":"openmaptiles","source-layer":"landcover","filter":["in","class","wood","forest"],"paint":{"fill-color":"#162018","fill-opacity":0.8}},
                    {"id":"landuse","type":"fill","source":"openmaptiles","source-layer":"landuse","filter":["in","class","residential","commercial","industrial"],"paint":{"fill-color":"#232220","fill-opacity":0.5}},
                    {"id":"national-park","type":"fill","source":"openmaptiles","source-layer":"landuse_overlay","filter":["==","class","national_park"],"paint":{"fill-color":"#1a2a18","fill-opacity":0.7}},
                    {"id":"road-minor","type":"line","source":"openmaptiles","source-layer":"transportation","filter":["in","class","minor","service","track"],"paint":{"line-color":"#2e2c29","line-width":["interpolate",["linear"],["zoom"],10,0.5,14,2]}},
                    {"id":"road-secondary","type":"line","source":"openmaptiles","source-layer":"transportation","filter":["in","class","secondary","tertiary"],"paint":{"line-color":"#3d3b37","line-width":["interpolate",["linear"],["zoom"],8,1,14,4]}},
                    {"id":"road-primary","type":"line","source":"openmaptiles","source-layer":"transportation","filter":["in","class","primary","trunk"],"paint":{"line-color":"#5a5750","line-width":["interpolate",["linear"],["zoom"],6,1,14,6]}},
                    {"id":"road-motorway","type":"line","source":"openmaptiles","source-layer":"transportation","filter":["==","class","motorway"],"paint":{"line-color":"#c8a95a","line-width":["interpolate",["linear"],["zoom"],6,1,14,8]}},
                    {"id":"rail","type":"line","source":"openmaptiles","source-layer":"transportation","filter":["==","class","rail"],"minzoom":7,"paint":{"line-color":"#4a4640","line-width":1.2,"line-dasharray":[3,3]}},
                    {"id":"aeroway","type":"line","source":"openmaptiles","source-layer":"aeroway","minzoom":10,"paint":{"line-color":"#6a675f","line-width":["interpolate",["linear"],["zoom"],10,1,14,4]}},
                    {"id":"boundary","type":"line","source":"openmaptiles","source-layer":"boundary","filter":["==","admin_level",2],"paint":{"line-color":"#5a5750","line-width":1.5,"line-dasharray":[4,2]}},
                    {"id":"park-name","type":"symbol","source":"openmaptiles","source-layer":"park","minzoom":7,"filter":["has","name"],"layout":{"text-field":["get","name"],"text-size":10,"text-font":["Noto Sans Regular"],"text-transform":"uppercase","text-letter-spacing":0.1},"paint":{"text-color":"#6f9a5c","text-halo-color":"#0f0e0c","text-halo-width":1.5}},
                    {"id":"water-name","type":"symbol","source":"openmaptiles","source-layer":"water_name","minzoom":9,"layout":{"text-field":["get","name"],"text-size":10,"text-font":["Noto Sans Regular"]},"paint":{"text-color":"#7eb8c9","text-halo-color":"#0f0e0c","text-halo-width":1.2}},
                    {"id":"waterway-name","type":"symbol","source":"openmaptiles","source-layer":"waterway","minzoom":11,"filter":["has","name"],"layout":{"symbol-placement":"line","text-field":["get","name"],"text-size":9,"text-font":["Noto Sans Regular"]},"paint":{"text-color":"#7eb8c9","text-halo-color":"#0f0e0c","text-halo-width":1.2}},
                    {"id":"mountain-peak","type":"symbol","source":"openmaptiles","source-layer":"mountain_peak","minzoom":10,"filter":["has","name"],"layout":{"text-field":["concat",["get","name"]," (",["get","ele"]," m)"],"text-size":9,"text-font":["Noto Sans Regular"]},"paint":{"text-color":"#a89a7e","text-halo-color":"#0f0e0c","text-halo-width":1.2}},
                    {"id":"airport-dot","type":"circle","source":"openmaptiles","source-layer":"aerodrome_label","minzoom":8,"paint":{"circle-radius":4,"circle-color":"#9a7ec9","circle-stroke-color":"#0f0e0c","circle-stroke-width":1.5}},
                    {"id":"airport-label","type":"symbol","source":"openmaptiles","source-layer":"aerodrome_label","minzoom":8,"layout":{"text-field":["get","name"],"text-size":10,"text-font":["Noto Sans Bold"],"text-offset":[0,1],"text-anchor":"top"},"paint":{"text-color":"#b49ad6","text-halo-color":"#0f0e0c","text-halo-width":1.5}},
                    {"id":"poi-dot","type":"circle","source":"openmaptiles","source-layer":"poi","minzoom":11,"filter":["in","class","hospital","doctors","dentist","clinic","pharmacy","fuel","campsite","lodging","grocery","supermarket","marketplace","shop","department_store","mall","police","car","car_repair","garage","drinking_water","bank","atm","border_control"],"paint":{"circle-radius":["interpolate",["linear"],["zoom"],11,2.5,16,5],"circle-color":["match",["get","class"],"hospital","#e07a5f","doctors","#e07a5f","dentist","#e07a5f","clinic","#e07a5f","pharmacy","#e08baa","fuel","#c8a95a","campsite","#8fb87a","lodging","#8fb87a","grocery","#c9b47e","supermarket","#c9b47e","marketplace","#c9b47e","shop","#c9b47e","department_store","#c9b47e","mall","#c9b47e","police","#7e9ac9","car","#b8874a","car_repair","#b8874a","garage","#b8874a","drinking_water","#7eb8c9","bank","#9a9589","atm","#9a9589","border_control","#c47eb5","#c47eb5"],"circle-stroke-color":"#0f0e0c","circle-stroke-width":1}},
                    {"id":"poi-name","type":"symbol","source":"openmaptiles","source-layer":"poi","minzoom":13,"filter":["all",["in","class","hospital","doctors","dentist","clinic","pharmacy","fuel","campsite","lodging","grocery","supermarket","marketplace","shop","department_store","mall","police","car","car_repair","garage","drinking_water","bank","atm","border_control"],["has","name"]],"layout":{"text-field":["get","name"],"text-size":9,"text-font":["Noto Sans Regular"],"text-offset":[0,0.8],"text-anchor":"top"},"paint":{"text-color":["match",["get","class"],"hospital","#e07a5f","doctors","#e07a5f","dentist","#e07a5f","clinic","#e07a5f","pharmacy","#e08baa","fuel","#c8a95a","campsite","#8fb87a","lodging","#8fb87a","grocery","#c9b47e","supermarket","#c9b47e","marketplace","#c9b47e","shop","#c9b47e","department_store","#c9b47e","mall","#c9b47e","police","#7e9ac9","car","#b8874a","car_repair","#b8874a","garage","#b8874a","drinking_water","#7eb8c9","bank","#9a9589","atm","#9a9589","border_control","#c47eb5","#c47eb5"],"text-halo-color":"#0f0e0c","text-halo-width":1.2}},
                    {"id":"road-name","type":"symbol","source":"openmaptiles","source-layer":"transportation_name","minzoom":11,"layout":{"symbol-placement":"line","text-field":["get","name"],"text-size":["interpolate",["linear"],["zoom"],11,9,16,12],"text-font":["Noto Sans Regular"],"text-rotation-alignment":"map","symbol-spacing":350},"paint":{"text-color":"#b8b2a5","text-halo-color":"#0f0e0c","text-halo-width":1.5}},
                    {"id":"place-village","type":"symbol","source":"openmaptiles","source-layer":"place","minzoom":10,"filter":["in","class","village","hamlet","suburb"],"layout":{"text-field":["get","name"],"text-size":10,"text-font":["Noto Sans Regular"]},"paint":{"text-color":"#9a9589","text-halo-color":"#0f0e0c","text-halo-width":1}},
                    {"id":"place-town","type":"symbol","source":"openmaptiles","source-layer":"place","minzoom":6,"filter":["in","class","town","city"],"layout":{"text-field":["get","name"],"text-size":13,"text-font":["Noto Sans Bold"]},"paint":{"text-color":"#e8e4dc","text-halo-color":"#0f0e0c","text-halo-width":2}},
                    {"id":"place-country","type":"symbol","source":"openmaptiles","source-layer":"place","filter":["==","class","country"],"layout":{"text-field":["get","name"],"text-size":14,"text-font":["Noto Sans Bold"],"text-transform":"uppercase"},"paint":{"text-color":"#c8a95a","text-halo-color":"#0f0e0c","text-halo-width":2}}
                ]
            }
            body = json.dumps(style, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(body))
            self.send_cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # /api/tiles/{z}/{x}/{y}
        if path.startswith('/api/tiles/'):
            parts = path.split('/')
            # Erwartet: ['', 'api', 'tiles', z, x, y]
            if len(parts) == 6:
                try:
                    z, x, y = int(parts[3]), int(parts[4]), int(parts[5])
                except ValueError:
                    self._error(400, 'Ungültige Kachel-Koordinaten')
                    return
                # 2026-09-27 (Audit M2): ohne Grenze rechnete get_tile() 2**z — ein einziges
                # /api/tiles/700000000/0/0 kostete Sekunden CPU, auch per <img> aus fremden Seiten.
                if not (0 <= z <= 22 and 0 <= x < (1 << z) and 0 <= y < (1 << z)):
                    self._empty_tile()
                    return
                mbtiles = find_mbtiles()
                if not mbtiles:
                    self._error(404, 'Keine MBTiles-Datei gefunden')
                    return
                tile_data = get_tile(mbtiles, z, x, y)
                if tile_data is None:
                    self._empty_tile()
                    return
                # Format bestimmen
                is_vector = is_vector_mbtiles(mbtiles)
                if is_vector:
                    # Vektor-Tile: gzip-komprimiertes PBF
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/x-protobuf')
                    self.send_header('Content-Encoding', 'gzip')
                    self.send_header('Content-Length', len(tile_data))
                    self.send_header('Cache-Control', 'max-age=86400')
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(tile_data)
                else:
                    # Raster-Tile: PNG (ggf. entpacken)
                    if tile_data[:2] == b'\x1f\x8b':
                        tile_data = zlib.decompress(tile_data, 16 + zlib.MAX_WBITS)
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', len(tile_data))
                    self.send_header('Cache-Control', 'max-age=86400')
                    self.send_cors()
                    self.end_headers()
                    self.wfile.write(tile_data)
                return
            self._error(400, 'Ungültiger Tile-Pfad')
            return

        # ── RAG-MOBILE API ────────────────────────────────────────
        if path == '/api/rag/status':
            store = load_rag_store()
            self._json({
                'synced': store is not None,
                'docs': len(store.get('docs', [])) if store else 0,
                'chunks': len(store.get('chunks', [])) if store else 0,
                'synced_at': store.get('synced_at', '') if store else ''
            })
            return

        # ── FONTS (Vektor-Karten-Labels) ──────────────────────────
        # Lokal aus BASE_DIR/fonts/ (setup-offline-karte.sh legt sie an). Fehlt die Datei,
        # Redirect zum Online-Font-Server — so funktionieren Labels online auch ohne Setup.
        if path.startswith('/fonts/'):
            if not _FONT_PFAD.match(path):
                self._error(404, 'Nicht gefunden')
                return
            local = BASE_DIR / unquote(path.lstrip('/'))
            if local.is_file() and self._statik_pfad_ok(path):
                super().do_GET()  # statisch ausliefern
                return
            self.send_response(302)
            self.send_header('Location', 'https://fonts.openmaptiles.org/' + path[len('/fonts/'):])  # kodiert lassen
            self.send_cors()
            self.end_headers()
            return

        # ── DOKUMENT API ──────────────────────────────────────────
        if path == '/api/docs/list':
            result = {}
            if DOCS_DIR.exists():
                for module_dir in sorted(DOCS_DIR.iterdir()):
                    if module_dir.is_dir():
                        files = []
                        for f in sorted(module_dir.iterdir()):
                            if f.suffix.lower() in ['.pdf', '.txt', '.md']:
                                files.append({
                                    'name': f.name,
                                    'size': f.stat().st_size,
                                    'size_human': self._fmt_size(f.stat().st_size),
                                    'module': module_dir.name
                                })
                        if files:
                            result[module_dir.name] = files
            self._json(result)
            return

        if path == '/api/docs/text':
            module = params.get('module', [''])[0]
            filename = unquote(params.get('file', [''])[0])
            if not module or not filename:
                self._error(400, 'module und file erforderlich')
                return
            filepath = safe_docs_path(module, filename, must_exist=True)
            if not filepath:
                self._error(404, 'Datei nicht gefunden (oder unzulässiger Name)')
                return
            text = self._read_file(filepath)
            self._json({'text': text[:50000], 'chars': len(text)})
            return

        if path == '/api/docs/search':
            module = params.get('module', [''])[0]
            filename = unquote(params.get('file', [''])[0])
            query = params.get('query', [''])[0].lower()
            max_chars = self._int_param(params, 'max_chars', 6000, 60000)
            if not module or not filename:
                self._error(400, 'module und file erforderlich')
                return
            filepath = safe_docs_path(module, filename, must_exist=True)
            if not filepath:
                self._error(404, 'Datei nicht gefunden (oder unzulässiger Name)')
                return
            text = self._read_file(filepath)
            relevant = self._search_text(text, query, max_chars)
            self._json({'text': relevant, 'chars': len(relevant)})
            return

        # ── HILFE: die Anleitung (README) als Seite, offline (2026-10-04-1) ──
        # /hilfe?lang=de|en|fr|es&from=/index.html|/mobile.html|/pois.html. zugang_pruefen lief schon:
        # vom iPhone nur im iPhone-Modus und mit Zugangscode — genau wie mobile.html. Kein Dateipfad
        # aus der Anfrage: die Sprache wählt eine von vier festen README-Dateien.
        if path == '/hilfe':
            self._hilfe_seite(params)
            return

        # ── STATISCHE DATEIEN: nur die App-Dateien, kein Ordner-Browsing ──
        if path in STATIK_DATEIEN:
            self.path = STATIK_DATEIEN[path] + (('?' + parsed.query) if parsed.query else '')
            super().do_GET()
            return
        if path.startswith(STATIK_PRAEFIXE) and self._statik_pfad_ok(path):
            super().do_GET()
            return
        self._error(404, 'Nicht gefunden')

    def _statik_pfad_ok(self, path):
        """Darf dieser Pfad unter /vendor/ bzw. /fonts/ ausgeliefert werden? (2026-09-27, Audit H1)
        Geprüft wird, was translate_path() tatsächlich öffnen würde: vorher sah die Prüfung nur den
        kodierten Pfad — /vendor/%2e%2e/server.py kam durch und lieferte Quelltext und rag-store.json."""
        dekodiert = unquote(path)
        if '..' in dekodiert or '/.' in dekodiert or '\\' in dekodiert or '\0' in dekodiert:
            return False
        try:
            ziel = Path(self.translate_path(path)).resolve()
        except (OSError, ValueError, RuntimeError):
            return False
        for praefix in STATIK_PRAEFIXE:
            wurzel = (BASE_DIR / praefix.strip('/')).resolve()
            if wurzel in ziel.parents:
                return True
        return False

    def _proxy_kiwix(self, path, query):
        """Reicht die Offline-Wikipedia durch. Kein Umschreiben nötig: kiwix erzeugt seine Links
        bereits unter /wiki, weil es mit --urlRootLocation gestartet wurde."""
        if '..' in path:
            self._error(400, 'Ungültiger Pfad.')
            return
        ziel = f'http://127.0.0.1:{KIWIX_PORT}{path}' + (f'?{query}' if query else '')
        try:
            upstream = urllib.request.urlopen(ziel, timeout=30)
        except urllib.error.HTTPError as e:
            upstream = e
        except Exception as e:
            self._error(502, f'Offline-Wikipedia antwortet nicht ({e.__class__.__name__}). '
                             f'Läuft kiwix-serve? Status: /api/kiwix/status')
            return
        with upstream:
            self.send_response(upstream.status)
            for kopf in ('Content-Type', 'Content-Length', 'Cache-Control', 'Content-Encoding', 'Location', 'ETag'):
                wert = upstream.headers.get(kopf)
                if wert:
                    self.send_header(kopf, wert)
            self.send_cors()
            self._ohne_csp = True          # Wikipedia-Seiten bringen eigene Einbettungen mit
            try:
                self.end_headers()
            finally:
                self._ohne_csp = False
            try:
                while True:
                    stueck = upstream.read(65536)
                    if not stueck:
                        break
                    self.wfile.write(stueck)
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass

    def _proxy_ollama(self, methode, ziel_pfad, body):
        """Feste Ollama-Pfade an 127.0.0.1:11434 durchreichen — für das iPhone, damit Ollama selbst
        nie ins WLAN muss (Ollama hat keine Authentifizierung; OLLAMA_ORIGINS schützt nur Browser).
        Kein Host/Port/Pfad aus der Anfrage (kein SSRF), Antwort wird gestreamt (NDJSON)."""
        req = urllib.request.Request(OLLAMA_BASE + ziel_pfad, data=body, method=methode,
                                     headers={'Content-Type': 'application/json'} if body else {})
        try:
            upstream = urllib.request.urlopen(req, timeout=600)
        except urllib.error.HTTPError as e:
            # z. B. 404 „model not found" — Statuscode und Text unverändert weitergeben
            daten = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', e.headers.get('Content-Type', 'application/json'))
            self.send_header('Content-Length', str(len(daten)))
            self.send_cors()
            self.end_headers()
            self.wfile.write(daten)
            return
        except Exception as e:
            self._error(502, f'Ollama am Mac nicht erreichbar ({e.__class__.__name__}). Läuft `ollama serve`?')
            return
        with upstream:
            self.send_response(upstream.status)
            self.send_header('Content-Type', upstream.headers.get('Content-Type', 'application/x-ndjson'))
            self.send_header('Cache-Control', 'no-store')
            self.send_cors()
            self.end_headers()   # ohne Content-Length: Antwort endet mit der Verbindung (HTTP/1.0)
            try:
                while True:
                    stueck = upstream.read1(16384) if hasattr(upstream, 'read1') else upstream.read(16384)
                    if not stueck:
                        break
                    self.wfile.write(stueck)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass   # iPhone hat abgebrochen — Upstream wird über `with` geschlossen

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if not self.zugang_pruefen(path, parse_qs(parsed.query)):
            return

        # Schreibende/beendende Endpunkte: nur vom Mac selbst (siehe mutation_erlaubt)
        if path in ('/api/shutdown', '/api/docs/upload', '/api/extract-pdf', '/api/rag/sync',
                    '/api/netz/an', '/api/netz/aus', '/api/netz/neuer-code',
                    '/api/reisewarnungen/aktualisieren', '/api/tls/zeigen'):
            ok, grund = self.mutation_erlaubt()
            if not ok:
                self._error(403, grund)
                return

        # ── iPHONE-MODUS schalten (nur vom Mac, nur aus der eigenen Seite) ──
        if path == '/api/netz/an':
            ok, st = lan_an()
            self._json(dict(st, ok=ok))
            return
        if path == '/api/netz/aus':
            self._json(dict(lan_aus(), ok=True))
            return
        if path == '/api/netz/neuer-code':
            zugangs_token(neu=True)
            self._json(dict(lan_status(), ok=True))
            return

        # ── CA-Zertifikat im Finder zeigen, damit es per AirDrop aufs iPhone kann ──
        if path == '/api/tls/zeigen':
            if not TLS_CA_CRT.exists():
                self._error(404, 'Es gibt noch kein Zertifikat — den iPhone-Modus einmal einschalten.')
                return
            try:
                subprocess.run(['open', '-R', str(TLS_CA_CRT)], timeout=8, check=True,
                               capture_output=True)
                self._json({'ok': True, 'datei': str(TLS_CA_CRT)})
            except Exception as e:
                self._error(500, f'Finder ließ sich nicht öffnen ({e.__class__.__name__}). '
                                 f'Die Datei liegt hier: {TLS_CA_CRT}')
            return

        # ── REISEWARNUNGEN jetzt holen (nur vom Mac; läuft im Hintergrund weiter) ──
        if path == '/api/reisewarnungen/aktualisieren':
            gestartet = reisewarnungen_anstossen()
            self._json(dict(reisewarnungen_status(), gestartet=gestartet))
            return

        # ── OLLAMA-PROXY (iPhone): POST /api/ollama/api/chat ──────
        if path == '/api/ollama/api/chat':
            try:
                length = self._body_length(MAX_JSON_BODY)
                if length is None:
                    return
                daten = json.loads(self.rfile.read(length).decode('utf-8'))
                if not isinstance(daten, dict) or not isinstance(daten.get('messages'), list):
                    self._error(400, 'model und messages erforderlich')
                    return
            except Exception:
                self._error(400, 'Ungültiger JSON-Body')
                return
            erlaubt = {k: daten[k] for k in ('model', 'messages', 'stream', 'options', 'think', 'format', 'keep_alive') if k in daten}
            if not ist_loopback(self.client_ip()):
                erlaubt = ollama_optionen_begrenzen(erlaubt)
            self._proxy_ollama('POST', '/api/chat', json.dumps(erlaubt).encode('utf-8'))
            return

        if path == '/api/shutdown':
            self._json({'ok': True})
            import threading, subprocess
            def stop():
                import time
                time.sleep(0.3)
                stoppe_kiwix()  # Kind-Prozess mitnehmen — sonst Kiwix-Waise nach App-Ende
                # Ollama NICHT beenden — LaunchAgent verwaltet Ollama
                lan_aus('Server beendet')
                runtime_entfernen()
                # Parent-Prozess (Launcher-Script) beenden → App verschwindet aus dem Dock.
                # Nur unter dem App-Launcher (SAFARI_PARENT_WATCH=1) — aus einem Terminal gestartet
                # wäre der Elternprozess die Shell des Nutzers (Re-Audit N4).
                if os.environ.get('SAFARI_PARENT_WATCH') == '1':
                    try:
                        os.kill(os.getppid(), 15)  # SIGTERM an Launcher
                    except OSError:
                        pass
                time.sleep(0.3)
                os.kill(os.getpid(), 9)
            threading.Thread(target=stop, daemon=True).start()
            return

        if path == '/api/docs/upload':
            self._handle_upload()
            return

        # ── RAG: PDF extrahieren + chunken (für IndexedDB im Browser) ──
        if path == '/api/extract-pdf':
            self._handle_extract_pdf()
            return

        # ── RAG-MOBILE: Chunks vom Mac-Browser empfangen / für das iPhone durchsuchen ──
        if path == '/api/rag/sync':
            self._handle_rag_sync()
            return

        if path == '/api/rag/search':
            self._handle_rag_search()
            return

        self._error(404, 'Nicht gefunden')

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        if not self.zugang_pruefen(path, params):
            return

        if path == '/api/docs/delete':
            ok, grund = self.mutation_erlaubt()
            if not ok:
                self._error(403, grund)
                return
            module = params.get('module', [''])[0]
            filename = unquote(params.get('file', [''])[0])
            filepath = safe_docs_path(module, filename, must_exist=True)
            if filepath:
                filepath.unlink()
                self._json({'success': True})
            else:
                self._error(404, 'Datei nicht gefunden (oder unzulässiger Name)')
            return

        self._error(404, 'Nicht gefunden')

    def _read_json_body(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            return None
        if length <= 0:
            return None
        if length > MAX_JSON_BODY:
            raise ValueError(f'Request zu groß ({length // (1024*1024)} MB) — Limit {MAX_JSON_BODY // (1024*1024)} MB')
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _handle_rag_sync(self):
        """POST /api/rag/sync — {docs:[{id,name,modules}], chunks:[{docId,doc,chapter,page,text}]}"""
        try:
            data = self._read_json_body()
            if not data or 'docs' not in data or 'chunks' not in data:
                self._error(400, 'docs und chunks erforderlich')
                return
            from datetime import datetime
            store = {
                'synced_at': datetime.now().isoformat(timespec='seconds'),
                'docs': data['docs'],
                'chunks': data['chunks']
            }
            save_rag_store(store)
            self._json({'ok': True, 'docs': len(store['docs']), 'chunks': len(store['chunks'])})
        except ValueError as e:
            self._error(400, str(e))
        except Exception as e:
            self._fehler_intern('rag/sync', e)

    def _handle_rag_search(self):
        """POST /api/rag/search — {query, module, k?} → {hits:[{doc,chapter,page,text,score}], synced}"""
        try:
            data = self._read_json_body()
            if not data or not data.get('query') or not data.get('module'):
                self._error(400, 'query und module erforderlich')
                return
            k = int(data.get('k', 4))
            hits = rag_search(data['query'], data['module'], k)
            if hits is None:
                self._json({'hits': [], 'synced': False, 'hinweis': 'Noch kein Sync — am Mac das Dokumente-Panel öffnen (index.html synct automatisch).'})
                return
            self._json({'hits': [{'doc': h.get('doc', 'Dokument'), 'chapter': h.get('chapter', ''),
                                   'page': h.get('page', 1), 'text': h.get('text', ''), 'score': h['score']}
                                  for h in hits], 'synced': True})
        except Exception as e:
            self._fehler_intern('rag/search', e)

    def _handle_extract_pdf(self):
        """POST /api/extract-pdf — raw PDF im Body, X-Doc-Name Header.
        Antwort: {doc, total_pages, total_chunks, chunks:[{text,chapter,page}]}"""
        try:
            length = self._body_length(MAX_PDF_BODY)
            if length is None:
                return
            pdf_bytes = self.rfile.read(length)
            doc_name = self.headers.get('X-Doc-Name', 'dokument.pdf')
            try:
                doc_name = unquote(doc_name)
            except Exception:
                pass
            try:
                lade_fitz()
            except ImportError as e:
                self._error(500, pymupdf_fehlertext(e))
                return
            chunks, total_pages = extract_pdf_chunks(pdf_bytes)
            self._json({
                'doc': doc_name,
                'total_pages': total_pages,
                'total_chunks': len(chunks),
                'chunks': chunks
            })
        except ValueError as e:
            self._error(400, str(e))      # eigene, verständliche Limits (Seiten/Zeichen)
        except Exception as e:
            self._fehler_intern('extract-pdf', e)

    def _handle_upload(self):
        import cgi
        ctype = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in ctype:
            self._error(400, 'multipart/form-data erwartet')
            return
        length = self._body_length(MAX_UPLOAD_BODY)
        if length is None:
            return
        data = self.rfile.read(length)
        # Einfacher multipart Parser
        boundary = ctype.split('boundary=')[-1].encode()
        parts = data.split(b'--' + boundary)
        module_name = 'allgemein'
        file_data = None
        file_name = 'upload.txt'
        for part in parts:
            if b'Content-Disposition' not in part:
                continue
            header, _, body = part.partition(b'\r\n\r\n')
            body = body.rstrip(b'\r\n')
            header_str = header.decode('utf-8', errors='ignore')
            if 'name="module"' in header_str:
                module_name = body.decode('utf-8', errors='ignore').strip()
            elif 'name="file"' in header_str:
                fn_match = [x for x in header_str.split(';') if 'filename=' in x]
                if fn_match:
                    file_name = fn_match[0].split('filename=')[-1].strip().strip('"')
                file_data = body
        if file_data is None:
            self._error(400, 'Keine Datei empfangen')
            return
        # Dateiname aus dem Header kann alles sein ("../../.zshrc") — nur der letzte Pfadteil zählt,
        # und der muss den Regeln von safe_docs_path genügen (Modulname ebenso).
        file_name = file_name.replace('\\', '/').rsplit('/', 1)[-1]
        dest = safe_docs_path(module_name, file_name)
        if not dest:
            self._error(400, f'Unzulässiger Modul- oder Dateiname ("{module_name}", "{file_name}") — erlaubt: .pdf/.txt/.md ohne Pfadzeichen')
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(file_data)
        text = self._read_file(dest)
        self._json({
            'success': True,
            'doc': {
                'name': file_name,
                'module': module_name,
                'size': len(file_data),
                'size_human': self._fmt_size(len(file_data)),
                'chars': len(text)
            }
        })

    def _read_file(self, path):
        suffix = path.suffix.lower()
        if suffix == '.pdf':
            try:
                doc = lade_fitz().open(str(path))
                return '\n'.join(page.get_text() for page in doc)
            except ImportError as e:
                return '[' + pymupdf_fehlertext(e) + ']'
        elif suffix in ['.txt', '.md']:
            try:
                return path.read_text(encoding='utf-8')
            except:
                return path.read_text(encoding='latin-1', errors='ignore')
        return ''

    def _search_text(self, text, query, max_chars):
        if not query:
            return text[:max_chars]
        paragraphs = text.split('\n')
        scored = []
        for i, para in enumerate(paragraphs):
            if query in para.lower():
                scored.append((i, 3))
            elif any(w in para.lower() for w in query.split()):
                scored.append((i, 1))
        if not scored:
            return text[:max_chars]
        result_parts = []
        used_chars = 0
        seen = set()
        for idx, _ in sorted(scored, key=lambda x: -x[1]):
            for j in range(max(0, idx-2), min(len(paragraphs), idx+5)):
                if j not in seen:
                    seen.add(j)
                    chunk = paragraphs[j]
                    if used_chars + len(chunk) > max_chars:
                        break
                    result_parts.append(chunk)
                    used_chars += len(chunk)
        return '\n'.join(result_parts)

    def _empty_tile(self):
        # 1x1 transparente PNG
        empty = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00'
            b'\x00\x00\x01\x00\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
            b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01'
            b'\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _fehler_intern(self, wo, e):
        """Interne Ausnahmen: Details nur ins Server-Log, nach außen ein allgemeiner Text (N6)."""
        print(f'⚠️  Fehler in {wo}: {e.__class__.__name__}: {e}')
        self._error(500, f'Interner Fehler bei {wo} — Details stehen im Server-Log (~/Library/Logs/Safari Assistant/server.log).')

    def _error(self, code, msg):
        body = json.dumps({'error': msg}).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def _hilfe_seite(self, params):
        """GET /hilfe — die Anleitung als HTML-Seite (hilfe.seite) mit eigener, strenger Richtlinie
        (hilfe.CSP). Übersetzung fehlt → englische Fassung mit Hinweis; README.md fehlt → 404-Seite."""
        if HILFE is None:
            print(f'⚠️  hilfe.py nicht geladen: {HILFE_FEHLER}')
            self._error(503, 'Die Hilfe fehlt in dieser Installation (hilfe.py) — ./deploy.sh kopiert sie ins App-Bundle.')
            return
        try:
            status, seite = HILFE.seite(params.get('lang', [''])[0], params.get('from', [''])[0], BASE_DIR)
        except Exception as e:
            self._fehler_intern('hilfe', e)
            return
        body = seite.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self._csp = HILFE.CSP
        try:
            self.end_headers()
        finally:
            self._csp = None
        self.wfile.write(body)

    def _fmt_size(self, size):
        if size < 1024: return f'{size} B'
        if size < 1024**2: return f'{size//1024} KB'
        return f'{size/1024**2:.1f} MB'


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8765
    server, bind, lan = oeffne_server(port)  # parallel: Karte + RAG + Statik gleichzeitig
    port = server.server_port                # kann abgewichen sein (belegter Port, siehe oben)
    SERVER_INFO.update({'port': port, 'bind': bind, 'lan': lan, 'basis': str(BASE_DIR),
                        'offen': bind.startswith('0.0.0.0'), 'mac_ip': lan_ip()})
    runtime_schreiben(port, bind)
    starte_eltern_wache()
    starte_lan_wache()
    starte_reisewarn_wache()
    if lan:   # --lan/SAFARI_LAN=1: Tor sofort offen (nur Entwicklung/Tests)
        LAN_STATE.update({'an': True, 'ip': lan_ip(), 'seit': time.time()})
    mbtiles = find_mbtiles()
    print(f'🌍 Safari Assistant läuft auf Port {port} (gebunden an {bind})')
    if lan:
        ip = lan_ip()
        print('📡 --lan: iPhone-Modus sofort AN — ' + url_fuers_log(f'http://{ip or "<Mac-IP>"}:{port}/go/{zugangs_token()}'))
    elif bind.startswith('0.0.0.0'):
        # Ausweichlösung nach defektem Loopback: gebunden ist 0.0.0.0, aber das Tor bleibt zu —
        # Anfragen aus dem WLAN werden abgewiesen, bis der iPhone-Modus eingeschaltet wird.
        print(f'⚠️  Bindung 0.0.0.0 (lo0 defekt) — Anfragen aus dem WLAN werden abgewiesen, solange der iPhone-Modus aus ist.')
    else:
        print(f'🔒 iPhone-Modus: AUS — nur dieser Mac (127.0.0.1). Einschalten in der App: ⚙️ Einstellungen → iPhone-Modus '
              f'(oder Server mit --lan starten).')
    print(f'📂 Verzeichnis: {BASE_DIR}')
    # Diese Zeile beantwortet die häufigste Rückfrage („PyMuPDF ist doch installiert!") ohne
    # Nachforschen: Sie nennt den Python, unter dem der Server WIRKLICH läuft, und was er findet.
    _pm = pymupdf_gefunden()
    print(f'🐍 Python: {sys.executable} ({sys.version.split()[0]}, {platform.machine()}) · '
          f'PyMuPDF: {"gefunden als " + _pm if _pm else "NICHT gefunden — PDF-Ablage aus"}')
    _nach = [p for p in benutzer_site_pfade() if p in sys.path and p not in _SYS_PATH_START]
    if _nach:
        print(f'   ↳ Benutzer-site-packages nachgetragen: {_nach[0]}')
    if mbtiles:
        print(f'🗺️  Offline-Karte: {mbtiles.name}')
    else:
        print(f'🗺️  Offline-Karte: keine (karte.mbtiles in {BASE_DIR} legen)')
    # Kiwix mitstarten + bei SIGTERM (Launcher-cleanup) sauber mitbeenden
    def _sigterm(signum, frame):
        stoppe_kiwix()
        lan_aus('Server beendet')
        runtime_entfernen()
        os._exit(0)
    signal.signal(signal.SIGTERM, _sigterm)
    start_kiwix()
    print(f'📡 http://localhost:{port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stoppe_kiwix()
        lan_aus('Server beendet')
        runtime_entfernen()
        print('\nServer gestoppt.')
