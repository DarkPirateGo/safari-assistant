# Ausgeführter Sicherheitstest des Servers (Release-Härtung 2026-09-27, Safari Assistant). Startet einen echten
# SafariServer auf 127.0.0.1 (Zufallsport) und schickt echte HTTP-Anfragen. Wird von test-app.js
# (Sektion 62) ausgeführt; läuft mit Python 3.9+ ohne Internet. Abschnitt 7 (2026-10-04): HEAD und
# andere Methoden ohne eigenes do_* erreichen keine Dateien mehr (vom Mac und aus dem WLAN).
import sys, importlib.util, threading, tempfile, shutil, sqlite3, time, http.client, socket
sys.dont_write_bytecode = True   # kein __pycache__ neben server.py (enthielte absolute Pfade)
from pathlib import Path
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location("srv", SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []
tmp = Path(tempfile.mkdtemp(prefix='dark-sec-test-'))
srv = None
srv_wlan = None
alt_token, alt_an = m._TOKEN_CACHE['wert'], m.LAN_STATE['an']
try:
    # Kleine Karten-Datei für den Kachel-Test (find_mbtiles zeigt darauf)
    mb = tmp / 'karte.mbtiles'
    c = sqlite3.connect(str(mb))
    c.execute('create table metadata(name text, value text)')
    c.execute('create table tiles(zoom_level int, tile_column int, tile_row int, tile_data blob)')
    c.execute("insert into metadata values('format','png')")
    c.execute("insert into tiles values(0,0,0,?)", (b'\x89PNG\r\n\x1a\n' + b'0' * 16,))
    c.commit(); c.close()
    m.find_mbtiles = lambda: mb

    m.SERVER_INFO.update({'port': 0, 'bind': '127.0.0.1', 'lan': False, 'basis': str(m.BASE_DIR), 'offen': False})
    srv = m.SafariServer(('127.0.0.1', 0), m.SafariHandler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()

    def anfrage(methode, pfad, kopf=None, timeout=6, ziel=None):
        k = http.client.HTTPConnection('127.0.0.1', ziel or port, timeout=timeout)
        k.request(methode, pfad, headers=kopf or {})
        r = k.getresponse()
        body = r.read()
        hdr = {a.lower(): b for a, b in r.getheaders()}
        k.close()
        return r.status, hdr, body

    # 1. Audit H1: kein Weg aus /vendor/ bzw. /fonts/ heraus — auch nicht kodiert
    for pfad in ('/vendor/%2e%2e/server.py', '/vendor/%2E%2E/server.py', '/vendor/..%2fserver.py',
                 '/vendor/%2e%2e%2fserver.py', '/vendor/.%2e/server.py', '/vendor/%2e%2e/%2e%2e/etc/passwd',
                 '/vendor/%252e%252e/server.py', '/vendor/..%5cserver.py', '/fonts/%2e%2e/server.py',
                 '/vendor/%2e%2e/rag-store.json'):
        st, _, body = anfrage('GET', pfad)
        if st == 200 or b'def tls_vorbereiten' in body:
            f.append('H1: %s liefert %s' % (pfad, st))
    if (m.BASE_DIR / 'vendor' / 'leaflet.js').exists():
        st, _, _ = anfrage('GET', '/vendor/leaflet.js')
        if st != 200:
            f.append('H1: /vendor/leaflet.js liefert %s statt 200' % st)

    # 2. Audit M2: Kachel-Koordinaten begrenzt — kein 2**z mit riesigem z
    t0 = time.time()
    st, _, _ = anfrage('GET', '/api/tiles/700000000/0/0')
    if time.time() - t0 > 1.5 or st >= 500:
        f.append('M2: riesiges z dauert %.1f s / Status %s' % (time.time() - t0, st))
    for pfad in ('/api/tiles/3/9/0', '/api/tiles/-1/0/0', '/api/tiles/23/0/0'):
        st, _, body = anfrage('GET', pfad)
        if st >= 500 or (st == 200 and body):
            f.append('M2: %s → %s' % (pfad, st))
    st, _, body = anfrage('GET', '/api/tiles/0/0/0')
    if st != 200 or not body:
        f.append('M2: gültige Kachel 0/0/0 → %s' % st)

    # 3. Audit L1: Sicherheits-Header auf jeder Antwort
    st, hdr, _ = anfrage('GET', '/index.html')
    soll = {'x-content-type-options': 'nosniff', 'x-frame-options': 'SAMEORIGIN',
            'referrer-policy': 'strict-origin-when-cross-origin'}
    for k, v in soll.items():
        if hdr.get(k) != v:
            f.append('L1: Header %s = %r' % (k, hdr.get(k)))
    if "frame-ancestors 'self'" not in hdr.get('content-security-policy', ''):
        f.append('L1: CSP frame-ancestors fehlt')

    # 4. Audit L2: CORS und Mutationen nur für DIESEN Server (Host UND Port)
    _, hdr, _ = anfrage('GET', '/api/ping', {'Origin': 'http://localhost:3000'})
    if 'access-control-allow-origin' in hdr:
        f.append('L2: fremder Port bekommt CORS-Freigabe')
    _, hdr, _ = anfrage('GET', '/api/ping', {'Origin': 'http://localhost:%d' % port})
    if hdr.get('access-control-allow-origin') != 'http://localhost:%d' % port:
        f.append('L2: eigener Origin bekommt keine CORS-Freigabe')
    st, _, _ = anfrage('POST', '/api/netz/aus', {'Origin': 'http://localhost:3000'})
    if st != 403:
        f.append('L2: Mutation von fremdem Port → %s statt 403' % st)
    st, _, _ = anfrage('POST', '/api/netz/aus', {'Origin': 'http://127.0.0.1:%d' % port})
    if st != 200:
        f.append('L2: Mutation vom eigenen Origin → %s statt 200' % st)
    st, _, _ = anfrage('GET', '/index.html', {'Host': 'evil.example'})
    if st != 421:
        f.append('DNS-Rebinding-Schutz: fremder Host → %s statt 421' % st)

    # 5. Audit M1: Zugangscode nicht im Log (stdout ist hier keine Konsole)
    if 'abcdefghij' in m.url_fuers_log('https://x.local:8765/go/abcdefghij'):
        f.append('M1: Zugangscode steht im Log')

    # 6. Audit L3: Ollama-Optionen aus dem WLAN begrenzt
    d = m.ollama_optionen_begrenzen({'model': 'x', 'messages': [], 'keep_alive': -1,
                                     'options': {'num_ctx': 10 ** 7, 'num_predict': -1, 'temperature': 0.3, 'fremd': 1}})
    o = d.get('options', {})
    if 'keep_alive' in d or o.get('num_ctx') != 32768 or o.get('num_predict') != 8192 or o.get('temperature') != 0.3 or 'fremd' in o:
        f.append('L3: Optionen nicht begrenzt: %r' % d)

    # 7. HEAD-Lücke (2026-10-04): HEAD lief in SimpleHTTPRequestHandler.do_HEAD — ohne Zugangscode,
    #    ohne Host-Prüfung, ohne STATIK_DATEIEN. HEAD /server.py lieferte 200 mit Größe und Datum.
    #    Jetzt: HEAD immer 405 ohne Body; keine andere Methode erreicht Dateien.
    geerbt = sorted(n for n in dir(m.SafariHandler) if n.startswith('do_') and n not in vars(m.SafariHandler))
    if geerbt:
        f.append('HEAD: geerbte Methoden der Standardbibliothek antworten ungeprüft: %s' % ', '.join(geerbt))

    def head_dicht(st, hdr, wo):
        """HEAD-Antwort darf nichts über Dateien verraten: 405, Allow, Länge 0, kein Datum."""
        if st != 405 or hdr.get('allow') != 'GET, POST' or hdr.get('content-length') != '0' or 'last-modified' in hdr:
            f.append('HEAD %s → %s, Allow %r, Länge %r, Last-Modified %r' % (
                wo, st, hdr.get('allow'), hdr.get('content-length'), hdr.get('last-modified')))

    for pfad in ('/server.py', '/.git/config', '/index.html', '/', '/rag-store.json', '/vendor/%2e%2e/server.py'):
        st, hdr, _ = anfrage('HEAD', pfad)
        head_dicht(st, hdr, pfad + ' (Mac)')
    st, hdr, _ = anfrage('HEAD', '/server.py', {'Host': 'evil.example'})
    if st == 200 or 'last-modified' in hdr:
        f.append('HEAD mit fremdem Host → %s' % st)

    # Roh über den Socket: nach den Kopfzeilen kommt kein Byte (http.client würde einen Body bei HEAD verschlucken)
    s = socket.create_connection(('127.0.0.1', port), timeout=6)
    s.sendall(b'HEAD /server.py HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n')
    roh = b''
    while True:
        stueck = s.recv(65536)
        if not stueck:
            break
        roh += stueck
    s.close()
    kopf_roh, _, rest = roh.partition(b'\r\n\r\n')
    if not kopf_roh.startswith(b'HTTP/1.0 405') or rest:
        f.append('HEAD roh: %r … %d Byte Body' % (kopf_roh[:40], len(rest)))

    # Andere Methoden ohne eigenes do_*: Standardbibliothek → 501, nichts aus Dateien
    for methode in ('PUT', 'PATCH', 'TRACE', 'PROPFIND', 'head'):
        for pfad in ('/server.py', '/.git/config'):
            st, hdr, body = anfrage(methode, pfad)
            if st < 400 or 'last-modified' in hdr or b'def tls_vorbereiten' in body or b'[core]' in body:
                f.append('%s %s → %s (verrät Dateiinhalt/-daten)' % (methode, pfad, st))
    st, hdr, body = anfrage('OPTIONS', '/server.py')
    if 'last-modified' in hdr or body:
        f.append('OPTIONS /server.py verrät etwas: %s, %d Byte' % (st, len(body)))

    # GET unverändert: App-Dateien ja, Quelltext/.git nein
    st, hdr, body = anfrage('GET', '/index.html')
    if st != 200 or 'last-modified' not in hdr or not body:
        f.append('GET /index.html → %s (sollte ausgeliefert werden)' % st)
    for pfad in ('/server.py', '/.git/config', '/rag-store.json'):
        st, _, body = anfrage('GET', pfad)
        if st != 404 or b'def tls_vorbereiten' in body or b'[core]' in body:
            f.append('GET %s → %s statt 404' % (pfad, st))

    # Aus dem WLAN (iPhone): HEAD nie 200 — weder ohne noch mit Zugangscode, iPhone-Modus an oder aus
    class AusDemWlan(m.SafariHandler):
        def client_ip(self):
            return '192.168.178.9'

    code = 'testcode2345'
    m._TOKEN_CACHE['wert'] = code          # kein Lesen/Schreiben von ~/.safari-assistant-zugang
    srv_wlan = m.SafariServer(('127.0.0.1', 0), AusDemWlan)
    port_wlan = srv_wlan.server_address[1]
    threading.Thread(target=srv_wlan.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    mit_code = {'Cookie': 'safari_zugang=' + code}
    for an in (True, False):
        m.LAN_STATE['an'] = an
        modus = 'an' if an else 'aus'
        for pfad in ('/server.py', '/.git/config', '/index.html', '/mobile.html'):
            st, hdr, _ = anfrage('HEAD', pfad, ziel=port_wlan)
            head_dicht(st, hdr, '%s (WLAN, iPhone-Modus %s, ohne Code)' % (pfad, modus))
            st, hdr, _ = anfrage('HEAD', pfad, mit_code, ziel=port_wlan)
            head_dicht(st, hdr, '%s (WLAN, iPhone-Modus %s, mit Code)' % (pfad, modus))
        # GET unverändert: ohne Code 403, mit Code nur im iPhone-Modus 200; Quelltext nie
        ohne = anfrage('GET', '/mobile.html', ziel=port_wlan)[0]
        mit = anfrage('GET', '/mobile.html', mit_code, ziel=port_wlan)[0]
        if (ohne, mit) != (403, 200 if an else 403):
            f.append('GET /mobile.html aus dem WLAN (iPhone-Modus %s): ohne/mit Code → %s' % (modus, (ohne, mit)))
        st, _, body = anfrage('GET', '/server.py', mit_code, ziel=port_wlan)
        if st == 200 or b'def tls_vorbereiten' in body:
            f.append('GET /server.py aus dem WLAN mit Code → %s' % st)
        st, _, _ = anfrage('OPTIONS', '/server.py', ziel=port_wlan)
        if st != 403:
            f.append('OPTIONS aus dem WLAN ohne Code → %s statt 403' % st)
except Exception as e:
    f.append('Ausnahme: %s: %s' % (e.__class__.__name__, e))
finally:
    m._TOKEN_CACHE['wert'], m.LAN_STATE['an'] = alt_token, alt_an
    for s_ in (srv, srv_wlan):
        if s_ is not None:
            try:
                s_.shutdown(); s_.server_close()
            except Exception:
                pass
    shutil.rmtree(tmp, ignore_errors=True)

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
