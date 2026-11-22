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

    # 8. Review 13.11.2026, S2: Der Ollama-Durchgriff und die Dokumentensuche nehmen nichts von fremden Webseiten an.
    #    Vorher lief POST /api/ollama/api/chat mit „Origin: https://evil.example" bis zu Ollama durch.
    import json as _json
    gesehen = []
    echt_proxy, echt_basis = m.SafariHandler._proxy_ollama, m.OLLAMA_BASE
    m.OLLAMA_BASE = 'http://127.0.0.1:1'      # falls doch etwas durchkäme: nie ein echtes Ollama

    def proxy_attrappe(self, methode, ziel, body):
        gesehen.append((methode, ziel, body))
        self._json({'attrappe': True})
    m.SafariHandler._proxy_ollama = proxy_attrappe

    def post(pfad, kopf, daten, ziel=None):
        k = http.client.HTTPConnection('127.0.0.1', ziel or port, timeout=6)
        roh = _json.dumps(daten).encode('utf-8')
        kk = {'Content-Length': str(len(roh))}
        kk.update(kopf or {})
        k.request('POST', pfad, body=roh, headers=kk)
        r = k.getresponse()
        r.read()
        k.close()
        return r.status
    chat = {'model': 'x', 'messages': [{'role': 'user', 'content': 'hi'}], 'keep_alive': -1, 'options': {'num_ctx': 10 ** 7}}
    eigen = 'http://localhost:%d' % port
    for kopf, soll, was in [({'Origin': 'https://evil.example', 'Content-Type': 'text/plain'}, 403, 'fremder Origin'),
                            ({'Origin': 'null'}, 403, 'Origin null'),
                            ({'Origin': 'http://localhost:%d' % (port + 1)}, 403, 'anderer lokaler Port'),
                            ({'Sec-Fetch-Site': 'cross-site'}, 403, 'Sec-Fetch-Site cross-site ohne Origin'),
                            ({'Origin': eigen, 'Sec-Fetch-Site': 'same-origin'}, 200, 'eigene Seite'),
                            ({}, 200, 'ohne Browser-Kopfzeilen (curl)')]:
        vorher = len(gesehen)
        st = post('/api/ollama/api/chat', kopf, chat)
        if st != soll or (soll == 403) != (len(gesehen) == vorher):
            f.append('S2: Ollama-Durchgriff, %s → %s, durchgereicht: %s' % (was, st, len(gesehen) > vorher))
    if gesehen:
        d = _json.loads(gesehen[-1][2].decode('utf-8'))
        if 'keep_alive' in d or (d.get('options') or {}).get('num_ctx') != 32768:
            f.append('S2: Deckel gelten nicht für Anfragen vom Mac selbst: %r' % d)
    else:
        f.append('S2: die eigene Seite kommt nicht mehr durch')
    vorher = len(gesehen)
    st, _, _ = anfrage('GET', '/api/ollama/api/tags', {'Origin': 'https://evil.example'})
    if st != 403 or len(gesehen) != vorher:
        f.append('S2: /api/ollama/api/tags von fremder Seite → %s' % st)
    st, _, _ = anfrage('GET', '/api/ollama/api/tags', {'Origin': eigen})
    if st != 200:
        f.append('S2: /api/ollama/api/tags von der eigenen Seite → %s' % st)
    if post('/api/rag/search', {'Origin': 'https://evil.example'}, {'query': 'x', 'module': 'y'}) != 403:
        f.append('S2: /api/rag/search nimmt eine fremde Seite an')
    if post('/api/rag/search', {'Origin': eigen}, {'query': 'x', 'module': 'y'}) != 200:
        f.append('S2: /api/rag/search lehnt die eigene Seite ab')
    # iPhone (WLAN, mit Code): eigene Seite ja, fremde Seite nein
    m.LAN_STATE['an'] = True
    wlan_eigen = dict(mit_code, Origin='http://127.0.0.1:%d' % port_wlan)
    if post('/api/ollama/api/chat', wlan_eigen, chat, ziel=port_wlan) != 200:
        f.append('S2: das iPhone kommt mit Code und eigener Seite nicht mehr an den Durchgriff')
    if post('/api/ollama/api/chat', dict(mit_code, Origin='https://evil.example'), chat, ziel=port_wlan) != 403:
        f.append('S2: fremde Seite mit gültigem Cookie kommt aus dem WLAN durch')
    m.SafariHandler._proxy_ollama, m.OLLAMA_BASE = echt_proxy, echt_basis

    # 9. Review 13.11.2026, S3: Die Wikipedia hat einen eigenen Port (eigene Herkunft im Browser). Der App-Port
    #    leitet /wiki nur um; der Wikipedia-Port liefert nichts außer /wiki; von dort gibt es weder CORS noch Mutationen.
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class KiwixAttrappe(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<html><script>window.wiki=1</script>kiwix-attrappe ' + self.path.encode('ascii', 'replace') + b'</html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    kiwix = HTTPServer(('127.0.0.1', 0), KiwixAttrappe)
    threading.Thread(target=kiwix.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    alt_kiwix = (m.KIWIX_PORT, m.KIWIX_ROOT, dict(m.WIKI_STATE))
    m.KIWIX_PORT, m.KIWIX_ROOT = kiwix.server_address[1], '/wiki'
    wport = 0
    try:
        wport = m.wiki_server_oeffnen(port)
        if not wport or wport == port or not (port + m.WIKI_PORT_ABSTAND <= wport < port + m.WIKI_PORT_ABSTAND + 10):
            f.append('S3: kein eigener Wikipedia-Port (%r)' % wport)
        else:
            if not getattr(m.WIKI_STATE['server'], 'nur_wiki', False):
                f.append('S3: der Wikipedia-Listener ist nicht auf /wiki beschränkt')
            st, hdr, body = anfrage('GET', '/wiki/content/buch/A?x=1')
            if st != 302 or hdr.get('location') != 'http://127.0.0.1:%d/wiki/content/buch/A?x=1' % wport or b'kiwix-attrappe' in body:
                f.append('S3: App-Port leitet /wiki nicht um: %s %r' % (st, hdr.get('location')))
            st, hdr, _ = anfrage('GET', '/wiki/', {'Host': 'localhost:%d' % port})
            if st != 302 or hdr.get('location') != 'http://localhost:%d/wiki/' % wport:
                f.append('S3: Umleitung behält den Namen aus der Adresse nicht: %r' % hdr.get('location'))
            st, _, body = anfrage('GET', '/wiki/content/buch/A?x=1', ziel=wport)
            if st != 200 or b'kiwix-attrappe /wiki/content/buch/A?x=1' not in body:
                f.append('S3: Wikipedia-Port reicht nicht durch (%s)' % st)
            for pfad in ('/', '/index.html', '/mobile.html', '/api/ping', '/api/docs/list', '/api/kiwix/status', '/i18n.js',
                         '/vendor/leaflet.js', '/hilfe', '/sw.js', '/api/ollama/api/tags', '/wikix', '/server.py'):
                st, _, body = anfrage('GET', pfad, ziel=wport)
                if st != 404:
                    f.append('S3: Wikipedia-Port liefert %s → %s' % (pfad, st))
            for methode, pfad in (('POST', '/api/netz/an'), ('POST', '/api/rag/search'), ('POST', '/wiki/'),
                                  ('DELETE', '/api/docs/delete?module=a&file=b.txt'), ('OPTIONS', '/api/ping')):
                st, _, _ = anfrage(methode, pfad, {'Content-Length': '0'}, ziel=wport)
                if st != 404:
                    f.append('S3: Wikipedia-Port nimmt %s %s an (%s)' % (methode, pfad, st))
            st, _, _ = anfrage('GET', '/wiki/', {'Host': 'evil.example'}, ziel=wport)
            if st != 421:
                f.append('S3: Wikipedia-Port ohne Host-Prüfung (%s)' % st)
            st, _, body = anfrage('GET', '/wiki/../server.py', ziel=wport)
            if st == 200 and b'kiwix-attrappe' not in body:
                f.append('S3: Wikipedia-Port liefert Dateien')
            # Von der Wikipedia-Herkunft aus: kein CORS auf der App, keine Mutation, kein Durchgriff
            wiki_origin = 'http://127.0.0.1:%d' % wport
            _, hdr, _ = anfrage('GET', '/api/docs/list', {'Origin': wiki_origin})
            if 'access-control-allow-origin' in hdr:
                f.append('S3: die Wikipedia-Herkunft bekommt CORS-Freigabe auf der App')
            st, _, _ = anfrage('POST', '/api/netz/aus', {'Origin': wiki_origin})
            if st != 403:
                f.append('S3: Mutation von der Wikipedia-Herkunft → %s statt 403' % st)
            if post('/api/rag/search', {'Origin': wiki_origin}, {'query': 'x', 'module': 'y'}) != 403:
                f.append('S3: Dokumentensuche von der Wikipedia-Herkunft möglich')
            # Status nennt den Port (Mac). iPhone: nur wenn dort der zweite Listener offen ist — sonst wie bisher durchreichen.
            st, _, body = anfrage('GET', '/api/kiwix/status')
            d = _json.loads(body.decode('utf-8'))
            if d.get('wiki_port') != wport or d.get('proxy') != '/wiki/' or 'offen_im_netz' not in d:
                f.append('S3: /api/kiwix/status ohne Wikipedia-Port: %r' % d)
            m.WIKI_STATE['lan'] = None
            st, _, body = anfrage('GET', '/api/kiwix/status', mit_code, ziel=port_wlan)
            if _json.loads(body.decode('utf-8')).get('wiki_port') != 0:
                f.append('S3: iPhone bekommt einen Wikipedia-Port genannt, der im WLAN nicht offen ist')
            st, _, body = anfrage('GET', '/wiki/A', mit_code, ziel=port_wlan)
            if st != 200 or b'kiwix-attrappe' not in body:
                f.append('S3: ohne zweiten WLAN-Listener fällt die Wikipedia am iPhone aus (%s)' % st)
            alt_ip = m.LAN_STATE.get('ip')
            m.WIKI_STATE['lan'], m.LAN_STATE['ip'] = object(), '192.168.178.23'
            st, hdr, _ = anfrage('GET', '/wiki/A', dict(mit_code, Host='192.168.178.23:%d' % port_wlan), ziel=port_wlan)
            m.WIKI_STATE['lan'], m.LAN_STATE['ip'] = None, alt_ip
            if st != 302 or hdr.get('location') != 'http://192.168.178.23:%d/wiki/A' % wport:
                f.append('S3: iPhone wird nicht auf den Wikipedia-Port geleitet (%s %r)' % (st, hdr.get('location')))
            st, _, _ = anfrage('GET', '/wiki/A', ziel=port_wlan)
            if st != 403:
                f.append('S3: Wikipedia aus dem WLAN ohne Zugangscode → %s' % st)
    finally:
        ws = m.WIKI_STATE.get('server')
        if ws is not None and ws is not alt_kiwix[2].get('server'):
            try:
                ws.shutdown(); ws.server_close()
            except Exception:
                pass
        m.KIWIX_PORT, m.KIWIX_ROOT = alt_kiwix[0], alt_kiwix[1]
        m.WIKI_STATE.clear(); m.WIKI_STATE.update(alt_kiwix[2])
        try:
            kiwix.shutdown(); kiwix.server_close()
        except Exception:
            pass

    # 10. Review 13.11.2026, U2/U1: Sicherung der Browser-Daten auf die Platte — nur vom Mac, nur aus der eigenen Seite,
    #     ohne Claude-Key und Position; Notfallkarte fürs iPhone nur auf Wunsch, mit Code und nur verschlüsselt.
    import os as _os, stat as _stat
    import re as _re_k
    alt_dir = m.SICHERUNG_DIR
    m.SICHERUNG_DIR = tmp / 'sicherung'
    try:
        def post_roh(pfad, kopf, daten, ziel=None):
            k = http.client.HTTPConnection('127.0.0.1', ziel or port, timeout=6)
            roh = _json.dumps(daten).encode('utf-8')
            kk = {'Content-Length': str(len(roh))}
            kk.update(kopf or {})
            k.request('POST', pfad, body=roh, headers=kk)
            r = k.getresponse()
            body = r.read()
            k.close()
            return r.status, body
        karte = {'personen': [{'label': 'Person 1', 'fields': {'Blutgruppe': '0+'}}], 'fahrzeug': {'Kennzeichen': 'X', 'Schlüssel-Versteck': 'hinten links'}}
        stand = {'herkunft': eigen, 'kennung': 'abc123', 'daten': {
            'safari-settings': _json.dumps({'anthropicKey': 'sk-ant-geheim', 'userLat': -22.5, 'userLng': 17.1, 'ollamaUrl': 'http://localhost:11434'}),
            'safari-notfallkarte': _json.dumps(karte), 'safari-logbuch': '[]',
            'evil': 'x', '__proto__': 'x', 'safari-zahl': 5, 'safari-' + 'x' * 60: 'zu lang'}}
        st, _ = anfrage('GET', '/api/sicherung/status')[0], None
        if _json.loads(anfrage('GET', '/api/sicherung/status')[2].decode('utf-8')).get('vorhanden') is not False:
            f.append('U2: Status meldet eine Sicherung, bevor es eine gibt')
        if anfrage('GET', '/api/sicherung')[0] != 404:
            f.append('U2: GET /api/sicherung ohne Sicherung nicht 404')
        for kopf, was in [({'Origin': 'https://evil.example'}, 'fremde Seite'), ({'Origin': 'http://localhost:%d' % (port + 1)}, 'anderer Port')]:
            if post_roh('/api/sicherung', kopf, stand)[0] != 403 or (m.SICHERUNG_DIR / 'daten.json').exists():
                f.append('U2: Sicherung von %s angenommen' % was)
        if post_roh('/api/sicherung', dict(mit_code, Origin='http://127.0.0.1:%d' % port_wlan), stand, ziel=port_wlan)[0] != 403:
            f.append('U2: Sicherung aus dem WLAN angenommen')
        st, body = post_roh('/api/sicherung', {'Origin': eigen}, stand)
        datei = m.SICHERUNG_DIR / 'daten.json'
        if st != 200 or not datei.exists():
            f.append('U2: Sicherung von der eigenen Seite → %s' % st)
        else:
            text = datei.read_text(encoding='utf-8')
            d = _json.loads(text)
            if 'sk-ant-geheim' in text or 'userLat' in text or '-22.5' in text:
                f.append('U2: Claude-Key oder Position stehen in der Sicherung')
            if sorted(d['daten']) != ['safari-logbuch', 'safari-notfallkarte', 'safari-settings'] or d.get('kennung') != 'abc123':
                f.append('U2: unerwartete Schlüssel in der Sicherung: %r' % sorted(d['daten']))
            if _stat.S_IMODE(datei.stat().st_mode) != 0o600 or _stat.S_IMODE(m.SICHERUNG_DIR.stat().st_mode) != 0o700:
                f.append('U2: Rechte der Sicherung nicht 0600/0700')
            sta = _json.loads(anfrage('GET', '/api/sicherung/status')[2].decode('utf-8'))
            if not sta.get('vorhanden') or sta.get('eintraege') != 3 or sta.get('kennung') != 'abc123' or 'ordner' in sta:
                f.append('U2: Status falsch: %r' % sta)
            st, _, body = anfrage('GET', '/api/sicherung')
            if st != 200 or _json.loads(body.decode('utf-8')).get('daten', {}).get('safari-logbuch') != '[]':
                f.append('U2: GET /api/sicherung liefert die Daten nicht')
            if anfrage('GET', '/api/sicherung', {'Origin': 'https://evil.example'})[0] != 403:
                f.append('U2: fremde Seite darf die Sicherung abrufen')
            _, hdr, _ = anfrage('GET', '/api/sicherung', {'Origin': 'http://localhost:%d' % (port + 1)})
            if 'access-control-allow-origin' in hdr:
                f.append('U2: CORS-Freigabe der Sicherung für einen anderen Port')
            for pfad in ('/api/sicherung', '/api/sicherung/status'):
                if anfrage('GET', pfad, mit_code, ziel=port_wlan)[0] != 403:
                    f.append('U2: %s aus dem WLAN abrufbar' % pfad)
            # Vortag aufheben; starkes Schrumpfen aufheben
            gestern = time.time() - 86400
            _os.utime(str(datei), (gestern, gestern))
            post_roh('/api/sicherung', {'Origin': eigen}, stand)
            tag = 'tag-%s.json' % time.strftime('%Y-%m-%d', time.localtime(gestern))
            if not (m.SICHERUNG_DIR / tag).exists():
                f.append('U2: der Stand des Vortags wird nicht aufgehoben')
            gross = dict(stand, daten=dict(stand['daten'], **{'safari-history': 'x' * 80000}))
            post_roh('/api/sicherung', {'Origin': eigen}, gross)
            post_roh('/api/sicherung', {'Origin': eigen}, stand)
            if not list(m.SICHERUNG_DIR.glob('vor-schrumpfen-*.json')):
                f.append('U2: ein plötzlich viel kleinerer Stand überschreibt die Sicherung ohne Kopie')
            # Ein anderer Browser-Speicher (andere Kennung) überschreibt nie ohne Kopie des bisherigen Stands
            post_roh('/api/sicherung', {'Origin': eigen}, dict(stand, kennung='anderer99'))
            if not list(m.SICHERUNG_DIR.glob('vor-wechsel-*.json')):
                f.append('U2: Wechsel des Browser-Speichers überschreibt die Sicherung ohne Kopie')
            m._SICHERUNG_LETZTE['kennung'] = None          # wie nach einem Neustart des Servers: Kennung aus der Datei
            post_roh('/api/sicherung', {'Origin': eigen}, dict(stand, kennung='anderer99'))
            if len(list(m.SICHERUNG_DIR.glob('vor-wechsel-*.json'))) != 1:
                f.append('U2: gleiche Kennung nach Neustart legt eine Wechsel-Kopie an')
            if post_roh('/api/sicherung', {'Origin': eigen}, {'daten': {'evil': 'x'}})[0] != 400:
                f.append('U2: leere/ungültige Sicherung wird angenommen')
            # Notfallkarte fürs iPhone: erst nach dem Schalter, aus dem WLAN nie über http
            if _json.loads(anfrage('GET', '/api/notfallkarte')[2].decode('utf-8')) != {'freigegeben': False}:
                f.append('U1: Notfallkarte ohne Freigabe abrufbar')
            if post_roh('/api/sicherung/einstellungen', dict(mit_code), {'notfallkarte_iphone': True}, ziel=port_wlan)[0] != 403:
                f.append('U1: der Schalter lässt sich aus dem WLAN umlegen')
            for wert in ('ja', 1, None):
                post_roh('/api/sicherung/einstellungen', {'Origin': eigen}, {'notfallkarte_iphone': wert})
                if m.sicherung_einstellungen()['notfallkarte_iphone']:
                    f.append('U1: Schalter geht mit %r an (nur echtes true)' % (wert,))
            st, _ = post_roh('/api/sicherung/einstellungen', {'Origin': eigen}, {'notfallkarte_iphone': True})
            d = _json.loads(anfrage('GET', '/api/notfallkarte')[2].decode('utf-8'))
            ohne = {'personen': karte['personen'], 'fahrzeug': {'Kennzeichen': 'X'}}
            if st != 200 or d.get('freigegeben') is not True or d.get('karte') != ohne or 'hinten links' in _json.dumps(d, ensure_ascii=False):
                f.append('U1: Notfallkarte nach Freigabe nicht abrufbar oder mit Schlüssel-Versteck: %r' % d)
            if anfrage('GET', '/api/notfallkarte', ziel=port_wlan)[0] != 403:
                f.append('U1: Notfallkarte aus dem WLAN ohne Zugangscode')
            d = _json.loads(anfrage('GET', '/api/notfallkarte', mit_code, ziel=port_wlan)[2].decode('utf-8'))
            if d != {'freigegeben': False, 'grund': 'nur_https'}:
                f.append('U1: Notfallkarte geht über http ins WLAN: %r' % d)
            if anfrage('GET', '/api/notfallkarte', {'Origin': 'https://evil.example'})[0] != 403:
                f.append('U1: fremde Seite darf die Notfallkarte abrufen')
            # Reiseprofil fürs iPhone (2026-11-15-4): kommt aus safari-settings der Sicherung; Code, https und eigene Seite wie die Notfallkarte
            einst = {'reiseprofil': 'Wir reisen zu zweit mit Hund. ' + 'x' * 9000, 'reiseprofilClaude': True, 'country': 'Namibia'}
            post_roh('/api/sicherung', {'Origin': eigen}, dict(stand, daten=dict(stand['daten'], **{'safari-settings': _json.dumps(einst)})))
            d = _json.loads(anfrage('GET', '/api/reiseprofil')[2].decode('utf-8'))
            if not d.get('text', '').startswith('Wir reisen zu zweit mit Hund.') or len(d['text']) != 8000 or d.get('claude') is not True:
                f.append('RP: Reiseprofil nicht wie gespeichert (gekürzt auf 8000, Claude-Haken): %r' % {k: (v[:40] if isinstance(v, str) else v) for k, v in d.items()})
            if anfrage('GET', '/api/reiseprofil', ziel=port_wlan)[0] != 403:
                f.append('RP: Reiseprofil aus dem WLAN ohne Zugangscode')
            d = _json.loads(anfrage('GET', '/api/reiseprofil', mit_code, ziel=port_wlan)[2].decode('utf-8'))
            if d.get('text') or d.get('grund') != 'nur_https':
                f.append('RP: Reiseprofil geht über http ins WLAN')
            if anfrage('GET', '/api/reiseprofil', {'Origin': 'https://evil.example'})[0] != 403:
                f.append('RP: fremde Seite darf das Reiseprofil abrufen')
            post_roh('/api/sicherung', {'Origin': eigen}, dict(stand, daten=dict(stand['daten'], **{'safari-settings': _json.dumps({'reiseprofil': ['kein', 'text'], 'reiseprofilClaude': 'ja'})})))
            if _json.loads(anfrage('GET', '/api/reiseprofil')[2].decode('utf-8')) != {'text': '', 'claude': False}:
                f.append('RP: ungültiges Reiseprofil (kein Text, Haken nicht true) wird weitergegeben')
    finally:
        m.SICHERUNG_DIR = alt_dir

    # 11. 2026-11-14-4: Claude-Key vom Mac aufs iPhone — anfragen darf das Gerät, erlauben nur der Mac aus der eigenen
    #     Seite; aus dem WLAN nur über https; der Key geht genau einmal und nur an die anfragende Adresse.
    def post_k(pfad, kopf=None, daten=None, ziel=None):
        k = http.client.HTTPConnection('127.0.0.1', ziel or port, timeout=6)
        roh = _json.dumps(daten).encode('utf-8') if daten is not None else b''
        kk = {'Content-Length': str(len(roh))}
        if daten is not None:
            kk['Content-Type'] = 'application/json'
        kk.update(kopf or {})
        k.request('POST', pfad, body=roh, headers=kk)
        r = k.getresponse(); body = r.read(); k.close()
        return r.status, (_json.loads(body.decode('utf-8')) if body else {})
    def get_k(pfad, kopf=None, ziel=None):
        st, _, body = anfrage('GET', pfad, kopf, ziel=ziel)
        return st, (_json.loads(body.decode('utf-8')) if body else {})
    KEY = 'sk-ant-api03-' + 'T' * 30
    ua = {'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15'}
    st, a = post_k('/api/schluessel/anfrage', dict(ua, Origin=eigen))
    if st != 200 or not _re_k.match(r'^\d{4}$', str(a.get('code'))) or len(str(a.get('id', ''))) < 30:
        f.append('K: Anfrage vom Mac: %s %r' % (st, a))
    st, o = get_k('/api/schluessel/offen')
    oa = o.get('anfrage') or {}
    if st != 200 or oa.get('code') != a.get('code') or oa.get('geraet') != 'iPhone · iOS 18.1' or 'key' in oa or oa.get('id') != a.get('id'):
        f.append('K: offene Anfrage am Mac falsch: %s %r' % (st, o))
    if get_k('/api/schluessel/offen', ziel=port_wlan)[0] != 403 or get_k('/api/schluessel/offen', mit_code, ziel=port_wlan)[0] != 403:
        f.append('K: offene Anfrage (mit Code) aus dem WLAN lesbar')
    if get_k('/api/schluessel/offen', {'Origin': 'https://evil.example'})[0] != 403:
        f.append('K: fremde Seite liest die offene Anfrage')
    # Antworten: nur Mac, nur eigene Seite, nur gültiger Key
    if post_k('/api/schluessel/antwort', {'Origin': 'https://evil.example'}, {'id': a['id'], 'erlauben': True, 'key': KEY})[0] != 403:
        f.append('K: fremde Seite darf erlauben')
    if post_k('/api/schluessel/antwort', mit_code, {'id': a['id'], 'erlauben': True, 'key': KEY}, ziel=port_wlan)[0] != 403:
        f.append('K: WLAN-Gerät darf sich selbst erlauben')
    if post_k('/api/schluessel/antwort', {'Origin': eigen}, {'id': a['id'], 'erlauben': True, 'key': 'kein-key'})[0] != 400:
        f.append('K: ungültiger Key angenommen')
    if post_k('/api/schluessel/antwort', {'Origin': eigen}, {'id': 'falsch', 'erlauben': True, 'key': KEY})[0] != 400:
        f.append('K: falsche Kennung angenommen')
    if get_k('/api/schluessel/anfrage?id=' + a['id'])[1].get('status') != 'wartet':
        f.append('K: Stand vor dem Erlauben nicht „wartet"')
    if m.schluessel_abholen(a['id'], '192.168.178.23').get('status') != 'unbekannt':
        f.append('K: andere Adresse sieht die Anfrage')
    st, r = post_k('/api/schluessel/antwort', {'Origin': eigen}, {'id': a['id'], 'erlauben': True, 'key': KEY})
    if st != 200 or r.get('status') != 'erlaubt':
        f.append('K: Erlauben vom Mac: %s %r' % (st, r))
    if m.schluessel_abholen(a['id'], '192.168.178.23').get('status') != 'unbekannt':
        f.append('K: andere Adresse holt den erlaubten Key')
    st, h, body = anfrage('GET', '/api/schluessel/anfrage?id=' + a['id'])
    d = _json.loads(body.decode('utf-8'))
    if st != 200 or d != {'status': 'erlaubt', 'key': KEY} or 'no-store' not in h.get('cache-control', ''):
        f.append('K: Abholen: %s %r %r' % (st, d, h.get('cache-control')))
    if get_k('/api/schluessel/anfrage?id=' + a['id'])[1].get('status') != 'unbekannt' or m._SCHLUESSEL['anfrage'] is not None:
        f.append('K: Key ein zweites Mal abholbar oder nicht vergessen')
    # Ablehnen, Ersetzen, Ablaufen
    a1 = post_k('/api/schluessel/anfrage')[1]; a2 = post_k('/api/schluessel/anfrage')[1]
    if m.schluessel_abholen(a1['id'], '127.0.0.1').get('status') != 'unbekannt':
        f.append('K: ersetzte Anfrage lebt weiter')
    post_k('/api/schluessel/antwort', {'Origin': eigen}, {'id': a2['id'], 'erlauben': False})
    if get_k('/api/schluessel/anfrage?id=' + a2['id'])[1] != {'status': 'abgelehnt'}:
        f.append('K: Ablehnen kommt nicht an')
    a3 = post_k('/api/schluessel/anfrage')[1]
    m._SCHLUESSEL['anfrage']['zeit'] -= m.SCHLUESSEL_FRIST_S + 1
    if get_k('/api/schluessel/offen')[1].get('anfrage') is not None:
        f.append('K: abgelaufene Anfrage wird am Mac noch gezeigt')
    a4 = post_k('/api/schluessel/anfrage')[1]
    post_k('/api/schluessel/antwort', {'Origin': eigen}, {'id': a4['id'], 'erlauben': True, 'key': KEY})
    m._SCHLUESSEL['anfrage']['zeit'] -= m.SCHLUESSEL_FRIST_S + 1
    if get_k('/api/schluessel/anfrage?id=' + a4['id'])[1] != {'status': 'abgelaufen'} or m._SCHLUESSEL['anfrage'] is not None:
        f.append('K: erlaubter, aber abgelaufener Key ist noch abholbar')
    # WLAN über http: weder anfragen noch abholen
    st, d = post_k('/api/schluessel/anfrage', mit_code, ziel=port_wlan)
    if st != 403 or 'https' not in str(d.get('error', '')):
        f.append('K: Anfrage aus dem WLAN über http: %s %r' % (st, d))
    if get_k('/api/schluessel/anfrage?id=x', mit_code, ziel=port_wlan)[0] != 403:
        f.append('K: Abholen aus dem WLAN über http')
    if post_k('/api/schluessel/anfrage', {'Origin': 'https://evil.example'})[0] != 403:
        f.append('K: fremde Seite stößt eine Anfrage an')
    for ua_, soll in (('Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X)', 'iPad · iPadOS 17.2'), ('', 'unbekanntes Gerät'), ('<script>', 'unbekanntes Gerät')):
        if m.geraet_aus_ua(ua_) != soll:
            f.append('K: Gerät aus %r → %r' % (ua_, m.geraet_aus_ua(ua_)))
    # nie auf die Platte: weder Sicherung noch irgendeine Datei im Arbeitsordner kennt den Key
    if 'iphoneAnthropicKey' not in m._SICHERUNG_GEHEIM:
        f.append('K: Key fürs iPhone ginge in die Sicherung')
    # ── 12. kiwix nur auf diesem Mac (2026-11-15-2) ─────────────────────────────────────────
    # kiwix-serve 3.8.2 / libkiwix 14.2 lehnt „--address=127.0.0.1" ab („IP address is not available on this system"),
    # nimmt aber ::1. Ein nachgebautes kiwix verhält sich genau so; geprüft wird der ECHTE start_kiwix().
    if m.kiwix_url('/wiki/') != 'http://127.0.0.1:%d/wiki/' % m.KIWIX_PORT:
        f.append('W: kiwix_url mit 127.0.0.1')
    alt12 = (m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_ROOT, m.KIWIX_NUR_LOKAL, m.KIWIX_PROC, m.find_kiwix_bin, m.find_kiwix_zims, m.lan_ip, m.LOG_DIR)
    try:
        m.KIWIX_HOST = '::1'
        if m.kiwix_url('/wiki/x?y=1') != 'http://[::1]:%d/wiki/x?y=1' % m.KIWIX_PORT:
            f.append('W: kiwix_url mit ::1 ohne eckige Klammern: ' + m.kiwix_url('/wiki/x?y=1'))
        ipv6 = True
        try:
            t6 = socket.socket(socket.AF_INET6); t6.bind(('::1', 0)); t6.close()
        except OSError:
            ipv6 = False
        if ipv6:
            s0 = socket.socket(); s0.bind(('127.0.0.1', 0)); frei = s0.getsockname()[1]; s0.close()
            attrappe = tmp / 'kiwix-serve'
            attrappe.write_text(
                '#!' + sys.executable + '\n'
                'import sys, socket\n'
                'from http.server import HTTPServer, BaseHTTPRequestHandler\n'
                'a = sys.argv[1:]\n'
                'if "--address=127.0.0.1" in a:\n'
                '    print("ERROR: IP address is not available on this system: 127.0.0.1"); sys.exit(1)\n'
                'port = int(a[a.index("--port") + 1])\n'
                'class H(BaseHTTPRequestHandler):\n'
                '    def do_GET(self):\n'
                '        ok = self.path.startswith("/wiki/") or "--urlRootLocation" not in a\n'
                '        self.send_response(200 if ok else 404); self.end_headers(); self.wfile.write(b"kiwix-6")\n'
                '    def log_message(self, *x): pass\n'
                'class S(HTTPServer):\n'
                '    address_family = socket.AF_INET6 if "--address=::1" in a else socket.AF_INET\n'
                'S(("::1" if "--address=::1" in a else "0.0.0.0", port), H).serve_forever()\n')
            attrappe.chmod(0o755)
            (tmp / 'test.zim').write_bytes(b'zim')
            m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_PROC = '127.0.0.1', frei, None
            m.find_kiwix_bin = lambda: str(attrappe)
            m.find_kiwix_zims = lambda: [tmp / 'test.zim']
            m.lan_ip = lambda: '127.0.0.1'   # „WLAN-Adresse" für die Gegenprobe: kiwix auf ::1 darf dort NICHT annehmen
            m.LOG_DIR = tmp
            m.start_kiwix()
            if not m.kiwix_laeuft():
                f.append('W: start_kiwix startet das nachgebaute kiwix nicht')
            elif (m.KIWIX_HOST, m.KIWIX_ROOT, m.KIWIX_NUR_LOKAL) != ('::1', '/wiki', True):
                f.append('W: nach dem Start %r statt (::1, /wiki, True)' % ((m.KIWIX_HOST, m.KIWIX_ROOT, m.KIWIX_NUR_LOKAL),))
            elif not m.kiwix_antwortet('/wiki/'):
                f.append('W: kiwix auf ::1 antwortet über kiwix_url nicht')
            if m.kiwix_im_wlan_erreichbar():
                f.append('W: Gegenprobe meldet kiwix auf ::1 als im WLAN erreichbar')
            if 'IP address is not available' not in (tmp / 'kiwix.log').read_text(errors='replace'):
                f.append('W: der erste Versuch (127.0.0.1) wurde gar nicht unternommen')
            m.stoppe_kiwix(); time.sleep(0.5)
            # Rückfall auf alle Schnittstellen: die Gegenprobe muss „im WLAN erreichbar" erkennen, auch wenn der Aufruf anderes behauptet
            m.find_kiwix_bin = lambda: str(attrappe)
            attrappe.write_text(attrappe.read_text().replace('if "--address=127.0.0.1" in a:', 'if any(x.startswith("--address") for x in a):'))
            m.KIWIX_HOST = '127.0.0.1'
            m.start_kiwix()
            if m.KIWIX_NUR_LOKAL or not m.kiwix_im_wlan_erreichbar():
                f.append('W: kiwix auf allen Schnittstellen nicht als offen erkannt (NUR_LOKAL=%r)' % m.KIWIX_NUR_LOKAL)
            m.stoppe_kiwix(); time.sleep(0.3)
        else:
            print('    (Hinweis: keine IPv6-Loopback in dieser Umgebung — Abschnitt 12 nur teilweise)')
    finally:
        try:
            m.stoppe_kiwix()
        except Exception:
            pass
        (m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_ROOT, m.KIWIX_NUR_LOKAL, m.KIWIX_PROC, m.find_kiwix_bin, m.find_kiwix_zims, m.lan_ip, m.LOG_DIR) = alt12
    # ── 13. Wiki-Suche: Artikeltext, Akzente, Nachfragen, Pfade (2026-11-15-3) ──────────────
    html13 = ('<html><h1>Guillain–Barré syndrome</h1><table><tr><td>Other names Landry paralysis</td></tr></table>'
              '<p>Short.</p><p>Guillain–Barré syndrome is a rapid-onset muscle weakness caused by the immune system damaging '
              'the peripheral nervous system. Typically, both sides of the body are involved.</p>'
              '<p>' + 'The initial symptoms are changes in sensation or pain often in the back along with muscle weakness. ' * 3 + '</p></html>')
    t13 = m.wiki_artikeltext(html13)
    if not t13.startswith('Guillain–Barré syndrome is a rapid-onset') or 'Other names' in t13 or 'Short.' in t13:
        f.append('WS: Auszug beginnt nicht mit dem Artikeltext: %r' % t13[:80])
    if m.wiki_artikeltext('<ul><li>Liste A</li><li>Liste B</li></ul>') != 'Liste A Liste B':
        f.append('WS: ohne Absätze kein Rückfall auf die ganze Seite')
    gesehen13 = {}
    class _Antwort:
        def __init__(self, txt): self.txt = txt
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.txt.encode()
    alt_urlopen13 = m.urllib.request.urlopen
    try:
        import json as _j13
        def _fake(req, timeout=None):
            gesehen13['prompt'] = _j13.loads(req.data.decode())['prompt']
            return _Antwort(_j13.dumps({'response': 'Guillain-Barré syndrome'}))
        m.urllib.request.urlopen = _fake
        r13 = m.wiki_suchbegriffe('was ist die zugehörige wikipediaquelle?', 'Was versteht man unter guillaume-barre Syndrom?')
        if r13 != 'Guillain-Barré syndrome':
            f.append('WS: Akzent geht verloren: %r' % r13)
        pr = gesehen13.get('prompt', '')
        if 'Previous question: Was versteht man unter guillaume-barre Syndrom?' not in pr or 'Correct misspelled names' not in pr:
            f.append('WS: vorige Frage oder Schreibkorrektur fehlt im Prompt')
        m.wiki_suchbegriffe('Malaria Symptome')
        if 'Previous question' in gesehen13.get('prompt', ''):
            f.append('WS: ohne vorige Frage trotzdem „Previous question" im Prompt')
    finally:
        m.urllib.request.urlopen = alt_urlopen13
    # Pfade aus kiwix-Treffern: nur unverdächtige gehen als Link an die App
    from http.server import HTTPServer as _HS13, BaseHTTPRequestHandler as _BH13
    class _Kiwix13(_BH13):
        def do_GET(self):
            if '/search' in self.path:
                body = ('<a href="/wiki/content/buch/A/Guillain%E2%80%93Barr%C3%A9_syndrome">GBS</a>'
                        '<a href="/wiki/content/buch/A/x&quot;onmouseover=alert(1)">Böse</a>').encode()
            else:
                body = ('<p>' + 'Artikeltext über Nerven und Muskeln. ' * 12 + '</p>').encode()
            self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *a): pass
    k13 = _HS13(('127.0.0.1', 0), _Kiwix13)
    threading.Thread(target=k13.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    alt13 = (m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_ROOT, m.wiki_buecher)
    try:
        m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_ROOT = '127.0.0.1', k13.server_address[1], '/wiki'
        m.wiki_buecher = lambda: ['buch']
        q13 = m.wiki_suche('Guillain-Barré syndrome', 3)
        pf = [q.get('pfad') for q in q13]
        if not q13 or pf[0] != 'buch/A/Guillain%E2%80%93Barr%C3%A9_syndrome':
            f.append('WS: Pfad des echten Treffers fehlt: %r' % pf)
        if any(('"' in (p_ or '') or '<' in (p_ or '') or ' ' in (p_ or '')) for p_ in pf):
            f.append('WS: verdächtiger Pfad geht an die App: %r' % pf)
    finally:
        (m.KIWIX_HOST, m.KIWIX_PORT, m.KIWIX_ROOT, m.wiki_buecher) = alt13
        k13.shutdown(); k13.server_close()
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
