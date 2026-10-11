# Ausgeführter Test des lokalen HTTPS. Erzeugt Zertifikate in einem Wegwerf-Verzeichnis, prüft die
# Kette mit openssl, macht einen echten TLS-Handshake gegen den echten SafariHandler und kontrolliert,
# dass die Namensbeschränkung der CA wirklich greift (Stufen voll/dns/aus, 2026-09-27). Wird von
# test-app.js (Sektion 58) ausgeführt.
import sys, importlib.util, ssl, socket, threading, subprocess, tempfile, shutil, os, json
sys.dont_write_bytecode = True   # kein __pycache__ neben server.py (enthielte absolute Pfade)
from pathlib import Path
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location("srv", SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []
if not m.openssl_pfad():
    print('OK (openssl nicht vorhanden — Test übersprungen)')
    sys.exit(0)

tmp = Path(tempfile.mkdtemp(prefix='safari-tls-test-'))
m.TLS_DIR = tmp
m.TLS_CA_KEY, m.TLS_CA_CRT = tmp / 'ca.key', tmp / 'safari-assistent-ca.crt'
m.TLS_SRV_KEY, m.TLS_SRV_CRT = tmp / 'server.key', tmp / 'server.crt'
m.TLS_MERKMALE = tmp / 'adressen.json'
try:
    # 1. Adressfilter: nur was die CA laut Namensbeschränkung abdecken darf
    erlaubt = {'192.168.1.23': True, '172.20.10.2': True, '10.0.0.5': True, '100.70.1.2': True,
               '127.0.0.1': True, '8.8.8.8': False, '192.0.2.2': False, 'kein.ip': False}
    for ip, soll in erlaubt.items():
        if m.tls_ip_erlaubt(ip) != soll:
            f.append('tls_ip_erlaubt(%s)=%s' % (ip, not soll))

    # 1b. Namen (2026-10-06-1): nur .local und localhost dürfen ins Zertifikat. Der Rechnername kommt
    # aus dem Lokalen Hostnamen von macOS, nicht aus dem DNS des Routers — in einem WLAN, dessen Router
    # Namen vergibt, lieferte socket.gethostname() z. B. „<uuid>.fritz.box", und alle TLS-Prüfungen
    # scheiterten mit „permitted subtree violation".
    for n, soll in {'macbook.local': True, 'localhost': True, 'LOCALHOST': True, 'x.fritz.box': False,
                    'www.example.com': False, '.local': False, 'local': False, '': False}.items():
        if m.tls_name_erlaubt(n) != soll:
            f.append('tls_name_erlaubt(%r)=%s' % (n, not soll))
    echt_gh, echt_lh = m.socket.gethostname, m._local_hostname_macos
    try:
        m._local_hostname_macos = lambda: ''
        for gh, soll in [('0a1b2c3d-0000-4000-8000-00000000abcd.fritz.box', ''), ('Mein-Mac.local', 'mein-mac.local'),
                         ('macbook', 'macbook.local'), ('localhost', '')]:
            m.socket.gethostname = lambda gh=gh: gh
            m._BONJOUR['zeit'] = 0
            if m.bonjour_name() != soll:
                f.append('bonjour_name() bei Rechnername %r: %r statt %r' % (gh, m.bonjour_name(), soll))
        m._local_hostname_macos = lambda: 'Mac-Name'
        m.socket.gethostname = lambda: '0a1b2c3d-0000-4000-8000-00000000abcd.fritz.box'
        m._BONJOUR['zeit'] = 0
        if m.bonjour_name() != 'mac-name.local':
            f.append('Lokaler Hostname von macOS wird nicht benutzt: %r' % m.bonjour_name())
        if 'mac-name.local' not in m.eigene_hosts():
            f.append('die iPhone-Adresse (Lokaler Hostname) fehlt in eigene_hosts() — Host-Prüfung lehnte sie ab')
    finally:
        m.socket.gethostname, m._local_hostname_macos = echt_gh, echt_lh
        m._BONJOUR['zeit'] = 0

    # 2. Zertifikate erzeugen (Hotspot- und WLAN-Adresse gleichzeitig, wie am Mac unterwegs)
    m.lokale_ips = lambda: ['192.168.1.23', '172.20.10.2']
    ctx, grund = m.tls_vorbereiten()
    if ctx is None:
        f.append('kein Kontext: ' + grund)
        raise SystemExit
    p = subprocess.run([m.openssl_pfad(), 'verify', '-CAfile', str(m.TLS_CA_CRT), str(m.TLS_SRV_CRT)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        f.append('Kette prüft nicht: ' + (p.stdout + p.stderr).strip()[:120])
    text = subprocess.run([m.openssl_pfad(), 'x509', '-noout', '-text', '-in', str(m.TLS_SRV_CRT)],
                          capture_output=True, text=True).stdout
    for muss in ('192.168.1.23', '172.20.10.2', 'TLS Web Server Authentication', 'sha256'):
        if muss not in text:
            f.append('im Zertifikat fehlt: ' + muss)
    if 'Subject Alternative Name' not in text:
        f.append('kein SAN — iOS lehnt solche Zertifikate ab')
    ca_text = subprocess.run([m.openssl_pfad(), 'x509', '-noout', '-text', '-in', str(m.TLS_CA_CRT)],
                             capture_output=True, text=True).stdout
    if 'CA:TRUE' not in ca_text:
        f.append('CA ist keine CA')
    # Stufe der Namensbeschränkung (2026-09-27): 'voll' (Namen + private Netze) oder — wenn die
    # Krypto dieses Rechners keine IP-Beschränkung prüft — 'dns'. Nie automatisch 'aus'.
    stufe = m.TLS_STATE.get('stufe')
    if os.environ.get('SAFARI_TLS_OHNE_CONSTRAINTS') == '1':
        f.append('Test bitte ohne SAFARI_TLS_OHNE_CONSTRAINTS=1 starten')
    if stufe not in ('voll', 'dns'):
        f.append('CA-Stufe %r — erwartet voll oder dns' % stufe)
    if 'Name Constraints' not in ca_text:
        f.append('CA ohne Namensbeschränkung')
    # 2026-10-04-2: neue CAs heißen wie die App; bestehende CAs (DARK / Safari Assistent) behalten ihren Namen
    if 'CN = Safari Assistant lokale CA' not in ca_text and 'CN=Safari Assistant lokale CA' not in ca_text:
        f.append('neue CA heißt nicht „Safari Assistant lokale CA"')
    if 'O = Safari Assistant' not in ca_text and 'O=Safari Assistant' not in ca_text:
        f.append('neue CA: Organisation ist nicht „Safari Assistant"')
    if m.TLS_STATE.get('ca_name') != 'Safari Assistant lokale CA':
        f.append('CA-Name nicht aus dem Zertifikat gelesen: %r' % m.TLS_STATE.get('ca_name'))
    if m.TLS_CA_TAGE > 825 or not m.tls_laeuft_bald_ab(tage=826, datei=m.TLS_CA_CRT):
        f.append('neue CA gilt länger als 825 Tage')
    if m.TLS_STATE.get('selbsttest'):
        f.append('Selbsttest der eigenen Kette schlug fehl: %s' % m.TLS_STATE['selbsttest'])

    # 3. Laufzeit höchstens 825 Tage (Vorgabe von Apple, sonst lehnt iOS ab)
    tage = int(subprocess.run([m.openssl_pfad(), 'x509', '-noout', '-checkend', str(825 * 86400),
                               '-in', str(m.TLS_SRV_CRT)], capture_output=True, text=True).returncode != 0)
    if tage != 1:
        f.append('Serverzertifikat läuft länger als 825 Tage — iOS akzeptiert das nicht')

    # 4. Echter Handshake gegen den echten Handler
    m.SERVER_INFO.update({'port': 0, 'bind': '127.0.0.1', 'lan': False, 'basis': str(m.BASE_DIR), 'offen': False})
    srv = m.SafariServer(('127.0.0.1', 0), m.SafariHandler, ssl_kontext=ctx)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    cctx = ssl.create_default_context(cafile=str(m.TLS_CA_CRT))
    def anfrage(name, pfad='/api/ping', kopf=''):
        roh = socket.create_connection(('127.0.0.1', port), timeout=6)
        with cctx.wrap_socket(roh, server_hostname=name) as s:
            s.sendall(f'GET {pfad} HTTP/1.0\r\nHost: {name}:{port}\r\n{kopf}\r\n'.encode())
            daten = b''
            while True:
                teil = s.recv(8192)
                if not teil:
                    break
                daten += teil
        return daten.decode('utf-8', 'replace')
    name = m.bonjour_name() or 'localhost'
    try:
        if '200' not in anfrage(name).splitlines()[0]:
            f.append('Handshake über den Namen liefert kein 200')
    except Exception as e:
        f.append('Handshake über den Namen: %s: %s' % (e.__class__.__name__, e))
    try:
        anfrage('fremder-name.local')
        f.append('fremder Name wurde akzeptiert — Zertifikat deckt zu viel ab')
    except ssl.SSLCertVerificationError:
        pass
    except Exception as e:
        f.append('unerwarteter Fehler bei fremdem Namen: %s' % e.__class__.__name__)
    # 2026-09-27 (Audit H2): stumme Verbindungen blockieren den Listener nicht mehr — der Handshake
    # läuft im Arbeits-Thread. Vorher froren sieben halboffene Handshakes den iPhone-Zugang ein.
    stumm = []
    try:
        for _ in range(8):
            s0 = socket.create_connection(('127.0.0.1', port), timeout=4)
            s0.sendall(b'\x16')
            stumm.append(s0)
        t0 = __import__('time').time()
        try:
            if '200' not in anfrage(name).splitlines()[0] or __import__('time').time() - t0 > 3:
                f.append('H2: mit 8 stummen Verbindungen antwortet der TLS-Listener nicht zügig')
        except Exception as e:
            f.append('H2: TLS-Listener blockiert durch stumme Verbindungen (%s)' % e.__class__.__name__)
    finally:
        for s0 in stumm:
            s0.close()
    # unverschlüsselt gegen den TLS-Port darf nicht funktionieren
    try:
        roh = socket.create_connection(('127.0.0.1', port), timeout=4)
        roh.sendall(b'GET /api/ping HTTP/1.0\r\nHost: x\r\n\r\n')
        if b'200' in roh.recv(200):
            f.append('der TLS-Port antwortet auch unverschlüsselt')
    except OSError:
        pass
    srv.shutdown(); srv.server_close()

    # 5. Namensbeschränkung greift: fremder Name immer abgelehnt, fremde IP bei Stufe 'voll'
    cfg = tmp / 'test.cnf'
    faelle = [(['www.example.com'], [])] + ([(['pruef.local'], ['8.8.8.8'])] if stufe == 'voll' else [])
    for fnamen, fips in faelle:
        cfg.write_text(m._config(fnamen, fips), encoding='utf-8')
        m.leaf_erzeugen(fnamen, fips, str(cfg))
        p = subprocess.run([m.openssl_pfad(), 'verify', '-CAfile', str(m.TLS_CA_CRT), str(m.TLS_SRV_CRT)],
                           capture_output=True, text=True)
        if p.returncode == 0:
            f.append('CA stellt Zertifikate für %s aus — Namensbeschränkung wirkungslos' % (fnamen + fips))

    # 6. Neuausstellung nur bei geänderten Adressen; die CA bleibt (iPhone-Profil bleibt gültig)
    m.lokale_ips = lambda: ['192.168.1.23', '172.20.10.2']
    m.tls_vorbereiten()
    ca_vorher, crt_vorher = m.TLS_CA_CRT.read_bytes(), m.TLS_SRV_CRT.read_bytes()
    m.tls_vorbereiten()
    if m.TLS_SRV_CRT.read_bytes() != crt_vorher:
        f.append('Zertifikat wird ohne Adressänderung neu ausgestellt')
    m.lokale_ips = lambda: ['10.5.5.5']
    m.tls_vorbereiten()
    if m.TLS_SRV_CRT.read_bytes() == crt_vorher:
        f.append('Adresswechsel führt zu keinem neuen Zertifikat')
    if m.TLS_CA_CRT.read_bytes() != ca_vorher:
        f.append('die CA wurde ersetzt — dann müsste am iPhone neu installiert werden')

    # 6b. Ablauf: ein Zertifikat, das in weniger als 30 Tagen abläuft, wird erneuert
    cfg = tmp / 'kurz.cnf'
    cfg.write_text(m._config(['vm.local'], ['10.5.5.5']), encoding='utf-8')
    echte_tage = m.TLS_SRV_TAGE
    m.TLS_SRV_TAGE = 10
    m.leaf_erzeugen(['vm.local'], ['10.5.5.5'], str(cfg))
    m.TLS_SRV_TAGE = echte_tage
    kurz = m.TLS_SRV_CRT.read_bytes()
    if not m.tls_laeuft_bald_ab():
        f.append('bald ablaufendes Zertifikat wird nicht erkannt')
    m.lokale_ips = lambda: ['10.5.5.5']
    m.tls_vorbereiten()
    if m.TLS_SRV_CRT.read_bytes() == kurz:
        f.append('bald ablaufendes Zertifikat wird nicht erneuert')

    # 7. Schlüssel sind privat, das CA-Zertifikat ist lesbar (es soll aufs iPhone)
    if oct(os.stat(m.TLS_CA_KEY).st_mode)[-3:] != '600' or oct(os.stat(m.TLS_SRV_KEY).st_mode)[-3:] != '600':
        f.append('Schlüsseldateien sind nicht 0600')

    def ca_text_jetzt():
        return subprocess.run([m.openssl_pfad(), 'x509', '-noout', '-text', '-in', str(m.TLS_CA_CRT)],
                              capture_output=True, text=True).stdout
    def alles_weg():
        for datei in tmp.iterdir():
            if datei.is_file():
                datei.unlink()
    echt_selbsttest = m.tls_selbsttest

    # 7b. Eine NEUE CA, deren IP-Beschränkung die Krypto hier nicht prüfen kann (macOS-LibreSSL:
    # „unsupported name constraint type"), wird mit Beschränkung nur auf Namen neu ausgestellt —
    # nie ganz ohne (Audit H3, 2026-09-27).
    alles_weg()
    rufe = {'n': 0}
    def einmal_scheitern(ctx, name):
        rufe['n'] += 1
        return 'SSLCertVerificationError: unsupported name constraint type' if rufe['n'] == 1 else echt_selbsttest(ctx, name)
    m.tls_selbsttest = einmal_scheitern
    ctx3, _ = m.tls_vorbereiten()
    m.tls_selbsttest = echt_selbsttest
    ca_text3 = ca_text_jetzt()
    nc3 = ca_text3.split('Name Constraints', 1)[1].split('Signature', 1)[0] if 'Name Constraints' in ca_text3 else ''
    if ctx3 is None:
        f.append('nach abgelehnter IP-Beschränkung gibt es gar kein Zertifikat mehr')
    if not nc3 or 'DNS:.local' not in nc3:
        f.append('Stufe dns: CA ohne Namensbeschränkung — nie still ganz ohne')
    if 'IP:' in nc3:
        f.append('Stufe dns: IP-Beschränkung trotz Ablehnung beibehalten')
    if m.TLS_STATE.get('stufe') != 'dns' or m.TLS_STATE.get('constraints') is not True or m.TLS_STATE.get('selbsttest'):
        f.append('Herabstufung nicht korrekt im Status: %s' % m.tls_status())
    if rufe['n'] < 2:
        f.append('nach der Neuausstellung wurde nicht erneut geprüft')

    # 7c. Eine VORHANDENE CA wird nie ersetzt, auch wenn der Selbsttest scheitert — das iPhone
    # vertraut ihr schon. Der Fehler steht im Status statt still herabzustufen.
    ca_vorher = m.TLS_CA_CRT.read_bytes()
    m.tls_selbsttest = lambda ctx, name: 'SSLCertVerificationError: unsupported name constraint type'
    ctx4, _ = m.tls_vorbereiten()
    m.tls_selbsttest = echt_selbsttest
    if m.TLS_CA_CRT.read_bytes() != ca_vorher:
        f.append('vorhandene CA wurde nach Selbsttest-Fehler ersetzt — iPhone-Profil wäre ungültig')
    if ctx4 is None or not m.TLS_STATE.get('selbsttest'):
        f.append('Selbsttest-Fehler einer vorhandenen CA wird nicht gemeldet')
    if m.TLS_STATE.get('stufe') != 'dns':
        f.append('Stufe der vorhandenen CA nicht aus dem Zertifikat gelesen: %r' % m.TLS_STATE.get('stufe'))

    # 7d. Ganz ohne Beschränkung nur auf ausdrücklichen Wunsch — und dann sichtbar
    alles_weg()
    os.environ['SAFARI_TLS_OHNE_CONSTRAINTS'] = '1'
    try:
        m.tls_vorbereiten()
    finally:
        del os.environ['SAFARI_TLS_OHNE_CONSTRAINTS']
    if 'Name Constraints' in ca_text_jetzt() or m.tls_status().get('stufe') != 'aus' or m.tls_status().get('constraints') is not False:
        f.append('SAFARI_TLS_OHNE_CONSTRAINTS=1 wird nicht korrekt umgesetzt/angezeigt: %s' % m.tls_status())
    # … und ohne den Schalter bleibt diese vorhandene (unbeschränkte) CA, wird aber als 'aus' gemeldet
    m.tls_vorbereiten()
    if m.tls_status().get('stufe') != 'aus':
        f.append('unbeschränkte CA wird nach Neustart als beschränkt gemeldet')

    # 7e. CA kurz vor Ablauf: wird ersetzt, die alte bleibt umbenannt liegen, Status sagt es
    alles_weg()
    echte_ca_tage = m.TLS_CA_TAGE
    m.TLS_CA_TAGE = 10
    m.tls_vorbereiten()
    m.TLS_CA_TAGE = echte_ca_tage
    alt = m.TLS_CA_CRT.read_bytes()
    m.tls_vorbereiten()
    if m.TLS_CA_CRT.read_bytes() == alt or not m.tls_status().get('ca_neu'):
        f.append('bald ablaufende CA wird nicht erneuert/gemeldet')
    if not any(d.name.startswith(m.TLS_CA_CRT.name + '.abgelaufen-') for d in tmp.iterdir()):
        f.append('abgelaufene CA wurde gelöscht statt umbenannt')

    # 7f. Ein Name außerhalb der Beschränkung (Router-DNS) kommt nie ins Zertifikat (2026-10-06-1)
    alles_weg()
    echt_bn = m.bonjour_name
    m.bonjour_name = lambda: '0a1b2c3d-0000-4000-8000-00000000abcd.fritz.box'
    try:
        ctx5, _ = m.tls_vorbereiten()
    finally:
        m.bonjour_name = echt_bn
    if ctx5 is None or m.TLS_STATE.get('selbsttest') or any('fritz.box' in n for n in (m.TLS_STATE.get('namen') or [])):
        f.append('fremder Rechnername landet im Zertifikat oder bricht die Kette: %s' % m.tls_status())
    if m.TLS_STATE.get('stufe') != stufe:
        f.append('Stufe %r statt %r nach fremdem Rechnernamen' % (m.TLS_STATE.get('stufe'), stufe))

    # 7g. „permitted subtree violation" stuft eine neue CA NICHT herab — das behebt den Fehler nicht,
    # es schwächte nur die Beschränkung. Herabgestuft wird nur bei „unsupported … constraint" (7b).
    alles_weg()
    rufe2 = {'n': 0}
    def einmal_subtree(ctx, name):
        rufe2['n'] += 1
        return ('SSLCertVerificationError: certificate verify failed: permitted subtree violation'
                if rufe2['n'] == 1 else echt_selbsttest(ctx, name))
    m.tls_selbsttest = einmal_subtree
    m.tls_vorbereiten()
    m.tls_selbsttest = echt_selbsttest
    if m.TLS_STATE.get('stufe') != stufe:
        f.append('„permitted subtree violation" stufte die neue CA herab (%r statt %r)' % (m.TLS_STATE.get('stufe'), stufe))
    if 'subtree' not in (m.TLS_STATE.get('selbsttest') or ''):
        f.append('„permitted subtree violation" wird nicht im Status gemeldet')

    # 8. Ohne openssl: kein stiller Ausfall, sondern ein Grund
    echt = m.openssl_pfad
    m.openssl_pfad = lambda: ''
    ctx2, grund2 = m.tls_vorbereiten()
    if ctx2 is not None or 'openssl' not in grund2:
        f.append('fehlendes openssl wird nicht sauber gemeldet: %r' % grund2)
    m.openssl_pfad = echt
except SystemExit:
    pass
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
