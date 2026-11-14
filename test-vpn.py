# Ausgeführter Test der VPN-Prüfung (2026-10-30-1, Anbieter-Erkennung 2026-11-02-1): Bewertung der Messung (grün nur mit Beleg, Leck, Starlink nie VPN),
# Frische (alte Messung oder Netzwechsel → „pruefe"), Einstellungsdatei (0600, manipulierte Felder, keine Adressen),
# Merken/Vergessen, echte https-Messung gegen einen lokalen TLS-Server (erzwungene Familie, Zertifikat, private oder
# falsche Adresse, Größe, Weiterleitung, Ersatzdienst, IPv6), Anmeldeseiten-Erkennung, RIPEstat-Auswertung mit
# Zwischenspeicher, Gesamtmessung ohne Netz und die Trennung lesen (iPhone) / prüfen und verwalten (nur Mac).
# Anbieter-Erkennung (Mullvad): ein vom Anbieter bestätigter Ausgang zählt als VPN — nur dort, nur eingeschaltet, nur bei
# eindeutigem „ja" mit derselben Adresse über https mit Zertifikatsprüfung; alles Unklare ist „nein".
# Wird von test-app.js (Sektion 70) ausgeführt; den Pfad zu server.py setzt test-app.js ein. Schreibt nichts ins Home.
import sys, importlib.util, socket, ssl, threading, tempfile, shutil, json, time, os, subprocess, io, contextlib
sys.dont_write_bytecode = True
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location("srv", SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []
tmp = Path(tempfile.mkdtemp(prefix='safari-vpn-test-'))
m.VPN_DATEI = tmp / 'vpn.json'
m._VPN_CFG['wert'] = None
m.TOKEN_DATEI = tmp / 'zugang'
m._TOKEN_CACHE['wert'] = ''
m.ZUSTAND_DATEI = tmp / 'iphone.json'
m._ZUSTAND_CACHE['wert'] = None
ECHT_ANSTOSSEN = m.vpn_anstossen
m.vpn_anstossen = lambda: False          # nie echtes Netz im Test


def A(fam, asns, name='', land='DE', ip=None):
    return {'familie': fam, 'ip': ip or ('9.9.9.9' if fam == 'IPv4' else '2a00::1'), 'land': land,
            'quelle': 'trace', 'asns': asns, 'prefix': '', 'name': name}


def messung(ausgaenge, alter=0, captive=None, fehler=None):
    m.VPN_STATE['messung'] = {'zeit': time.time() - alter, 'dauer_s': 0.1, 'ausgaenge': ausgaenge,
                              'fehler': fehler or {}, 'captive': captive}


try:
    # 1. Bewertung: grün nur, wenn JEDER Weg im gemerkten Netz liegt; Starlink ist nie das VPN
    B = m.vpn_bewerten
    erwartet = [
        (([], set(), None), ('offline', '')),
        (([], set(), True), ('anmeldung', '')),
        (([], set(), False), ('unklar', '')),
        (([A('IPv4', ['9009'], 'M247')], {'9009'}), ('vpn', '')),
        (([A('IPv4', ['9009']), A('IPv6', ['9009'])], {'9009'}), ('vpn', '')),
        (([A('IPv4', ['9009']), A('IPv6', ['36996'], 'TN', 'NA')], {'9009'}), ('leck', 'IPv6')),
        (([A('IPv4', ['36996'], 'TN', 'NA'), A('IPv6', ['9009'])], {'9009'}), ('leck', 'IPv4')),
        (([A('IPv4', ['36996'], 'Telecom Namibia', 'NA')], set()), ('einrichten', '')),
        (([A('IPv4', ['36996'], 'Telecom Namibia', 'NA')], {'9009'}), ('kein_vpn', '')),
        (([A('IPv4', ['14593'], 'SPACEX-STARLINK - Space Exploration Technologies Corporation', 'NA')], set()), ('kein_vpn', '')),
        (([A('IPv4', ['14593'], 'x')], {'14593'}), ('kein_vpn', '')),
        (([A('IPv4', ['399999'], 'STARLINK-EXAMPLE - Starlink Roam')], {'399999'}), ('kein_vpn', '')),
        (([A('IPv4', None)], {'9009'}), ('unklar', '')),
        (([A('IPv4', [])], {'9009'}), ('unklar', '')),
        (([A('IPv4', ['9009']), A('IPv6', None)], {'9009'}), ('unklar', '')),
        (([A('IPv4', ['36996']), A('IPv6', None)], {'9009'}), ('kein_vpn', '')),
        (([A('IPv4', ['9009', '1234'])], {'1234'}), ('vpn', '')),
    ]
    for args, soll in erwartet:
        ist = B([dict(a) for a in args[0]], *args[1:])
        if ist != soll:
            f.append('Bewertung %r → %r statt %r' % ([(a['familie'], a['asns']) for a in args[0]] + list(args[1:]), ist, soll))

    # 2. Frische: eine alte Messung oder eine von vor einem Netzwechsel zeigt „pruefe", nie die alte Farbe
    m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [{'asn': '9009', 'name': 'M247', 'land': 'DE', 'seit': 1}]})
    messung([A('IPv4', ['9009'], 'M247 Europe SRL')])
    st = m.vpn_status()
    if st['stufe'] != 'vpn' or st['ausgaenge'][0]['vpn'] is not True:
        f.append('frische Messung nicht grün: %r' % st['stufe'])
    messung([A('IPv4', ['9009'])], alter=60 + m.VPN_TOLERANZ_S + 5)
    st = m.vpn_status()
    if st['stufe'] != 'pruefe' or st['zuletzt'] != 'vpn':
        f.append('alte Messung zeigt %r (zuletzt %r) statt „pruefe"' % (st['stufe'], st['zuletzt']))
    messung([A('IPv4', ['9009'])], alter=5)
    m.VPN_STATE['netzwechsel'] = time.time()
    if m.vpn_status()['stufe'] != 'pruefe':
        f.append('nach einem Netzwechsel gilt die alte Messung weiter')
    m.VPN_STATE['netzwechsel'] = 0.0
    m.vpn_speichern({'aktiv': False, 'intervall_s': 60, 'gemerkt': []})
    st = m.vpn_status()
    if st['stufe'] != 'aus' or st['ausgaenge']:
        f.append('abgeschaltet: %r / %r' % (st['stufe'], st['ausgaenge']))
    m.VPN_STATE['nachfrage'] = 0.0
    m.vpn_status(nachfrage=False)
    if m.VPN_STATE['nachfrage'] != 0.0:
        f.append('interne Abfrage zählt als Bedarf')
    m.vpn_status()
    if time.time() - m.VPN_STATE['nachfrage'] > 2:
        f.append('Abfrage einer Seite zählt nicht als Bedarf')

    # 3. Einstellungsdatei: 0600, nur gültige Felder, kein Zugangsnetz, keine Adressen
    m.VPN_DATEI.write_text(json.dumps({'aktiv': 'ja', 'intervall_s': 7, 'gemerkt': [
        {'asn': '9009', 'name': 'M247\u0000<b>x</b>\n' + 'y' * 300, 'land': 'de', 'seit': 'gestern'},
        {'asn': '9009', 'name': 'doppelt'}, {'asn': '14593', 'name': 'Starlink'}, {'asn': 'AS1; rm', 'name': 'x'},
        'kaputt', {'asn': 60068, 'name': 'Zahl statt Text'}]}), encoding='utf-8')
    m._VPN_CFG['wert'] = None
    c = m.vpn_einstellungen()
    if c['aktiv'] is not True or c['intervall_s'] != 60:
        f.append('ungültige Einstellungen übernommen: %r' % {k: c[k] for k in ('aktiv', 'intervall_s')})
    if [g['asn'] for g in c['gemerkt']] != ['9009', '60068']:
        f.append('gemerkte Netze aus manipulierter Datei: %r' % [g['asn'] for g in c['gemerkt']])
    g0 = c['gemerkt'][0]
    if '\u0000' in g0['name'] or '\n' in g0['name'] or len(g0['name']) > 120 or g0['land'] != '' or g0['seit'] != 0:
        f.append('Feld nicht bereinigt: %r' % g0)
    c['gemerkt'].append({'asn': '1'})
    if any(g['asn'] == '1' for g in m.vpn_einstellungen()['gemerkt']):
        f.append('vpn_einstellungen gibt den Zwischenspeicher selbst heraus')
    for n in range(40):
        c['gemerkt'].append({'asn': str(1000 + n), 'name': 'x'})
    m.vpn_speichern(c)
    if len(m.vpn_einstellungen()['gemerkt']) != m.VPN_MAX_GEMERKT:
        f.append('mehr als %d gemerkte Netze' % m.VPN_MAX_GEMERKT)
    if os.name == 'posix' and (m.VPN_DATEI.stat().st_mode & 0o777) != 0o600:
        f.append('vpn.json nicht 0600: %o' % (m.VPN_DATEI.stat().st_mode & 0o777))

    # 4. Merken/Vergessen: nur ein Netz, über das der Mac gerade ins Internet geht; nie Starlink
    m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': []})
    messung([A('IPv4', ['9009'], 'M247 Europe SRL', ip='8.8.4.4'), A('IPv6', ['14593'], 'SPACEX-STARLINK')])
    def fehler_bei(fn, *a):
        try:
            fn(*a)
        except ValueError as e:
            return str(e)
        return ''
    if 'nicht ins Internet' not in fehler_bei(m.vpn_merken, '3320'):
        f.append('fremdes Netz ließ sich merken')
    if 'Starlink' not in fehler_bei(m.vpn_merken, '14593'):
        f.append('Starlink ließ sich als VPN merken')
    if 'Ungültige' not in fehler_bei(m.vpn_merken, '9009; x'):
        f.append('ungültige Netznummer angenommen')
    with contextlib.redirect_stdout(io.StringIO()) as log:
        m.vpn_merken('AS9009')
        m.vpn_merken('9009')               # zweimal = einmal
    gem = m.vpn_einstellungen()['gemerkt']
    if [g['asn'] for g in gem] != ['9009'] or gem[0]['name'] != 'M247 Europe SRL' or gem[0]['land'] != 'DE':
        f.append('gemerkt: %r' % gem)
    roh = m.VPN_DATEI.read_text(encoding='utf-8')
    if '8.8.4.4' in roh or '2a00:' in roh or '8.8.4.4' in log.getvalue():
        f.append('Adresse landet in der Datei oder im Log')
    st = m.vpn_status()
    if st['stufe'] != 'leck' or st['leck'] != 'IPv6':
        f.append('IPv4 übers VPN, IPv6 direkt über Starlink → %r/%r statt leck/IPv6' % (st['stufe'], st['leck']))
    messung([A('IPv4', ['9009'])], alter=16 * 60)
    if 'aktuelle Messung' not in fehler_bei(m.vpn_merken, '9009'):
        f.append('Merken mit alter Messung möglich')
    if 'nicht gemerkt' not in fehler_bei(m.vpn_vergessen, '3320'):
        f.append('Vergessen eines unbekannten Netzes ohne Fehler')
    m.vpn_vergessen('AS9009')
    if m.vpn_einstellungen()['gemerkt']:
        f.append('Vergessen wirkt nicht')
    if 'Takt' not in fehler_bei(m.vpn_einstellen, {'intervall_s': 61}) or 'Takt' not in fehler_bei(m.vpn_einstellen, {'intervall_s': True}):
        f.append('ungültiger Takt angenommen')
    m.vpn_einstellen({'aktiv': 1})
    if m.vpn_einstellungen()['aktiv'] is not False:
        f.append('aktiv nur bei true (1 zählt nicht)')
    m.vpn_einstellen({'aktiv': True, 'intervall_s': 300})
    if m.vpn_einstellungen() ['intervall_s'] != 300 or m.vpn_einstellungen()['aktiv'] is not True:
        f.append('Einstellungen nicht übernommen')

    # 5. Echte https-Messung gegen einen lokalen TLS-Server (eigene Test-CA, Zertifikat für 127.0.0.1 und ::1)
    ossl = m.openssl_pfad()
    if not ossl:
        print('    (openssl fehlt — TLS-Teil übersprungen)')
    else:
        cfg = tmp / 'tls.cnf'
        cfg.write_text('[req]\ndistinguished_name = dn\nprompt = no\n[dn]\nCN = Test\n[ca_ext]\n'
                       'basicConstraints = critical,CA:TRUE\nkeyUsage = critical,keyCertSign,cRLSign\n'
                       'subjectKeyIdentifier = hash\n[srv_ext]\nbasicConstraints = critical,CA:FALSE\n'
                       'keyUsage = critical,digitalSignature,keyEncipherment\nextendedKeyUsage = serverAuth\n'
                       'subjectKeyIdentifier = hash\nauthorityKeyIdentifier = keyid,issuer\n'
                       'subjectAltName = IP:127.0.0.1, IP:::1\n', encoding='utf-8')
        def o(*a):
            p = subprocess.run([ossl] + list(a), capture_output=True, text=True, timeout=60)
            if p.returncode:
                raise RuntimeError('openssl %s: %s' % (a[0], (p.stderr or p.stdout).strip()[-200:]))
        o('req', '-x509', '-new', '-nodes', '-newkey', 'rsa:2048', '-sha256', '-days', '2', '-keyout', str(tmp / 'ca.key'),
          '-out', str(tmp / 'ca.crt'), '-subj', '/CN=VPN-Test-CA', '-config', str(cfg), '-extensions', 'ca_ext')
        o('req', '-new', '-nodes', '-newkey', 'rsa:2048', '-sha256', '-keyout', str(tmp / 'srv.key'), '-out', str(tmp / 'srv.csr'),
          '-subj', '/CN=127.0.0.1', '-config', str(cfg))
        o('x509', '-req', '-in', str(tmp / 'srv.csr'), '-CA', str(tmp / 'ca.crt'), '-CAkey', str(tmp / 'ca.key'),
          '-CAcreateserial', '-days', '2', '-sha256', '-out', str(tmp / 'srv.crt'), '-extfile', str(cfg), '-extensions', 'srv_ext')
        srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        srv_ctx.load_cert_chain(str(tmp / 'srv.crt'), str(tmp / 'srv.key'))
        test_ctx = ssl.create_default_context(cafile=str(tmp / 'ca.crt'))
        ANTWORT = {
            '/cdn-cgi/trace': (200, b'fl=1\nh=x\nip=9.9.9.9\nts=1\nloc=de\nwarp=off\n'),
            '/v6/cdn-cgi/trace': (200, b'ip=2a00::1\nloc=NA\n'),
            '/privat/cdn-cgi/trace': (200, b'ip=192.168.1.5\nloc=DE\n'),
            '/falsch/cdn-cgi/trace': (200, b'ip=2a00::1\nloc=DE\n'),
            '/tor/cdn-cgi/trace': (200, b'ip=8.8.8.8\nloc=T1\n'),
            '/gross/cdn-cgi/trace': (200, b'ip=9.9.9.9\n' + b'x' * 20000),
            '/weiter/cdn-cgi/trace': (302, b''),
            '/fehler/cdn-cgi/trace': (500, b'nein'),
            '/?format=json': (200, b'{"ip":"1.0.0.1"}'),
            '/mv/ja': (200, b'{"ip":"9.9.9.9","mullvad_exit_ip":true,"country":"Germany"}'),
            '/mv/nein': (200, b'{"ip":"9.9.9.9","mullvad_exit_ip":false}'),
            '/mv/text': (200, b'{"ip":"9.9.9.9","mullvad_exit_ip":"true"}'),
            '/mv/eins': (200, b'{"ip":"9.9.9.9","mullvad_exit_ip":1}'),
            '/mv/andere': (200, b'{"ip":"8.8.8.8","mullvad_exit_ip":true}'),
            '/mv/privat': (200, b'{"ip":"192.168.1.5","mullvad_exit_ip":true}'),
            '/mv/ohnefeld': (200, b'{"ip":"9.9.9.9"}'),
            '/mv/html': (200, b'<html>Willkommen</html>'),
            '/mv/liste': (200, b'[true]'),
            '/mv/v6ja': (200, b'{"ip":"2a00::1","mullvad_exit_ip":true}'),
        }
        AUFRUFE = []
        class Dienst(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_GET(self):
                AUFRUFE.append((self.path, self.headers.get('Host'), self.headers.get('User-Agent')))
                code, body = ANTWORT.get(self.path, (404, b''))
                self.send_response(code)
                if code == 302:
                    self.send_header('Location', 'https://127.0.0.1/cdn-cgi/trace')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        class TlsServer(ThreadingHTTPServer):
            daemon_threads = True
            def get_request(self):
                s, a = self.socket.accept()
                return srv_ctx.wrap_socket(s, server_side=True), a
        s4 = TlsServer(('127.0.0.1', 0), Dienst)
        threading.Thread(target=s4.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
        port = s4.server_address[1]
        s6 = None
        try:
            class TlsServer6(TlsServer):
                address_family = socket.AF_INET6
            s6 = TlsServer6(('::1', port), Dienst)
            threading.Thread(target=s6.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
        except OSError:
            s6 = None
            print('    (kein IPv6 auf ::1 — IPv6-Teil übersprungen)')
        m.VPN_PORT = port
        m.vpn_ssl_kontext = lambda: test_ctx
        Q = lambda pfad: (('127.0.0.1', pfad, 'trace'),)
        try:
            m.VPN_QUELLEN = Q('/cdn-cgi/trace')
            a = m.vpn_ausgang(socket.AF_INET)
            if a != {'ip': '9.9.9.9', 'land': 'DE', 'quelle': 'trace'}:
                f.append('Trace-Antwort falsch gelesen: %r' % a)
            if not AUFRUFE or AUFRUFE[-1][1] != '127.0.0.1:%d' % port or 'SafariAssistant' not in (AUFRUFE[-1][2] or ''):
                f.append('Anfrage ohne passenden Host/User-Agent: %r' % AUFRUFE[-1:])
            # erzwungene Familie: über IPv6 zu einer IPv4-Adresse gibt es keinen Weg
            # Entscheidend ist: kein Ergebnis. Wie ein System eine IPv4-Adresse für IPv6 ablehnt, ist verschieden
            # (Linux: Adressfehler = kein_netz; macOS meldet es anders) — nur die Anzeige-Art darf abweichen.
            try:
                m.vpn_ausgang(socket.AF_INET6)
                f.append('IPv6-Messung lief über IPv4')
            except Exception as e:
                if m._vpn_fehlerart(e) not in ('kein_netz', 'verbindung'):
                    f.append('IPv6 ohne Weg → %s statt kein_netz/verbindung' % m._vpn_fehlerart(e))
            # Systemunabhängig: liefert das System für IPv6 nur ::ffff:-Adressen (= IPv4), gibt es keinen IPv6-Weg
            # → kein_netz, und es wird nichts versucht.
            echt_gai = socket.getaddrinfo
            socket.getaddrinfo = lambda host, port, fam=0, typ=0, proto=0, flags=0: [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::ffff:127.0.0.1', port, 0, 0))]
            try:
                m._VpnVerbindung('127.0.0.1', socket.AF_INET6, 2, test_ctx, port=port).connect()
                f.append('IPv4-gemappte Adresse als IPv6-Weg genommen')
            except Exception as e:
                if m._vpn_fehlerart(e) != 'kein_netz':
                    f.append('nur ::ffff:-Adressen → %s statt kein_netz' % m._vpn_fehlerart(e))
            finally:
                socket.getaddrinfo = echt_gai
            # fremdes Zertifikat → kein Ergebnis (und Fehlerart tls)
            m.vpn_ssl_kontext = ssl.create_default_context
            try:
                m.vpn_ausgang(socket.AF_INET)
                f.append('Zertifikat einer fremden CA angenommen')
            except Exception as e:
                if m._vpn_fehlerart(e) != 'tls':
                    f.append('fremdes Zertifikat → %s statt tls' % m._vpn_fehlerart(e))
            m.vpn_ssl_kontext = lambda: test_ctx
            for pfad, grund in (('/privat/cdn-cgi/trace', 'private Adresse angenommen'),
                                ('/falsch/cdn-cgi/trace', 'IPv6-Adresse auf dem IPv4-Weg angenommen'),
                                ('/gross/cdn-cgi/trace', 'zu große Antwort angenommen'),
                                ('/weiter/cdn-cgi/trace', 'Weiterleitung verfolgt'),
                                ('/fehler/cdn-cgi/trace', 'HTTP 500 als Ergebnis genommen')):
                m.VPN_QUELLEN = Q(pfad)
                try:
                    m.vpn_ausgang(socket.AF_INET)
                    f.append(grund)
                except Exception:
                    pass
            m.VPN_QUELLEN = Q('/tor/cdn-cgi/trace')
            if m.vpn_ausgang(socket.AF_INET)['land'] != '':
                f.append('Ländercode T1 (Tor) als Land übernommen')
            # Ersatzdienst, wenn der erste nicht antwortet
            m.VPN_QUELLEN = (('127.0.0.1', '/fehler/cdn-cgi/trace', 'trace'), ('', '/?format=json', 'ipify'))
            m.VPN_IPIFY = {socket.AF_INET: '127.0.0.1', socket.AF_INET6: '::1'}
            a = m.vpn_ausgang(socket.AF_INET)
            if a != {'ip': '1.0.0.1', 'land': '', 'quelle': 'ipify'}:
                f.append('Ersatzdienst nicht genutzt: %r' % a)
            if s6:
                m.VPN_QUELLEN = (('::1', '/v6/cdn-cgi/trace', 'trace'),)
                a = m.vpn_ausgang(socket.AF_INET6)
                if a.get('ip') != '2a00::1' or a.get('land') != 'NA':
                    f.append('IPv6-Weg falsch gemessen: %r' % a)
                try:
                    m.vpn_ausgang(socket.AF_INET)
                    f.append('IPv4-Messung lief über IPv6')
                except Exception:
                    pass
            # Anbieter-Erkennung (2026-11-02-1): echte https-Abfrage; nur ein eindeutiges „ja" mit derselben Adresse zählt
            anb_alt = m.VPN_ANBIETER['mullvad']
            def anb(pfad, ip='9.9.9.9', fam=socket.AF_INET):
                m.VPN_ANBIETER['mullvad'] = dict(anb_alt, pfad=pfad, hosts={socket.AF_INET: '127.0.0.1', socket.AF_INET6: '::1'})
                return m.vpn_anbieter_pruefen('mullvad', ip, fam)
            try:
                if anb('/mv/ja') is not True:
                    f.append('Anbieter: eindeutiges „ja" mit derselben Adresse nicht bestätigt')
                if not AUFRUFE or AUFRUFE[-1][0] != '/mv/ja' or AUFRUFE[-1][1] != '127.0.0.1:%d' % port or 'SafariAssistant' not in (AUFRUFE[-1][2] or ''):
                    f.append('Anbieter-Anfrage ohne passenden Pfad/Host/User-Agent: %r' % AUFRUFE[-1:])
                for pfad, grund in (('/mv/nein', 'false als „ja"'), ('/mv/text', 'Text „true" als „ja"'), ('/mv/eins', 'Zahl 1 als „ja"'),
                                    ('/mv/andere', 'Antwort für eine andere Adresse als „ja"'), ('/mv/privat', 'private Adresse als „ja"'),
                                    ('/mv/ohnefeld', 'fehlendes Feld als „ja"'), ('/mv/html', 'HTML als „ja"'), ('/mv/liste', 'Liste als „ja"'),
                                    ('/gross/cdn-cgi/trace', 'zu große Antwort'), ('/fehler/cdn-cgi/trace', 'HTTP 500'),
                                    ('/weiter/cdn-cgi/trace', 'Weiterleitung'), ('/gibt/es/nicht', 'HTTP 404')):
                    if anb(pfad) is not False:
                        f.append('Anbieter-Antwort zählt als „ja": ' + grund)
                if anb('/mv/ja', ip='8.8.4.4') is not False:
                    f.append('Anbieter: „ja" für eine andere Adresse als die gemessene zählt')
                if s6:
                    if anb('/mv/v6ja', '2a00::1', socket.AF_INET6) is not True:
                        f.append('Anbieter: IPv6-Bestätigung nicht erkannt')
                    if anb('/mv/ja', '2a00::1', socket.AF_INET6) is not False:
                        f.append('Anbieter: IPv4-Antwort auf dem IPv6-Weg zählt')
                m.vpn_ssl_kontext = ssl.create_default_context
                if anb('/mv/ja') is not False:
                    f.append('Anbieter mit Zertifikat einer fremden CA bestätigt')
                m.vpn_ssl_kontext = lambda: test_ctx
                if m.vpn_anbieter_pruefen('gibtsnicht', '9.9.9.9', socket.AF_INET) is not False:
                    f.append('unbekannter Anbieter bestätigt')
                m.VPN_ANBIETER['mullvad'] = dict(anb_alt, pfad='/mv/ja', hosts={socket.AF_INET: '127.0.0.1'})
                if m.vpn_anbieter_pruefen('mullvad', '2a00::1', socket.AF_INET6) is not False:
                    f.append('Familie ohne Anbieter-Adresse bestätigt')
            finally:
                m.VPN_ANBIETER['mullvad'] = anb_alt
        finally:
            s4.shutdown(); s4.server_close()
            if s6:
                s6.shutdown(); s6.server_close()
        # Fehlerarten
        for e, soll in ((socket.gaierror(8, 'x'), 'kein_netz'), (socket.timeout('x'), 'zeit'),
                        (OSError(m.errno.ENETUNREACH, 'x'), 'kein_netz'), (OSError(m.errno.ECONNREFUSED, 'x'), 'verbindung'),
                        (ValueError('x'), 'antwort'), (ssl.SSLError('x'), 'tls')):
            if m._vpn_fehlerart(e) != soll:
                f.append('Fehlerart %r → %s statt %s' % (e, m._vpn_fehlerart(e), soll))

    # 6. Anmeldeseite (Captive Portal): „Success" = frei, alles andere = Anmeldung, keine Antwort = None
    class Portal(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_GET(self):
            if self.path == '/frei':
                body = b'<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>'
                self.send_response(200)
            else:
                body = b'<html>Login</html>'
                self.send_response(302)
                self.send_header('Location', 'http://10.0.0.1/login')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    sp = ThreadingHTTPServer(('127.0.0.1', 0), Portal)
    threading.Thread(target=sp.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    try:
        m.VPN_CAPTIVE = ('127.0.0.1', '/frei', sp.server_address[1])
        if m.vpn_anmeldung_noetig() is not False:
            f.append('freies Netz als Anmeldeseite erkannt')
        m.VPN_CAPTIVE = ('127.0.0.1', '/portal', sp.server_address[1])
        if m.vpn_anmeldung_noetig() is not True:
            f.append('Anmeldeseite nicht erkannt')
    finally:
        sp.shutdown(); sp.server_close()
    frei = socket.socket(); frei.bind(('127.0.0.1', 0)); leer_port = frei.getsockname()[1]; frei.close()
    m.VPN_CAPTIVE = ('127.0.0.1', '/frei', leer_port)
    if m.vpn_anmeldung_noetig(timeout=2) is not None:
        f.append('ohne Verbindung keine None-Antwort')

    # 7. RIPEstat: Adresse → Netz, Netz → Name; Zwischenspeicher, Weitergelten bei Ausfall, fremde Felder bereinigt
    echt_hole = m._hole
    ABRUFE = []
    def hole_ripe(url, timeout=20, max_bytes=0, roh=False):
        ABRUFE.append(url)
        if 'network-info' in url:
            return json.dumps({'status': 'ok', 'data': {'asns': ['9009', 'x1', 12], 'prefix': '9.9.9.9/32'}})
        return json.dumps({'status': 'ok', 'data': {'holder': 'M247 - M247 Europe SRL\u0007\n'}})
    m._hole = hole_ripe
    m._VPN_NETZ_CACHE.clear(); m._VPN_NAMEN_CACHE.clear()
    if m.vpn_netz('9.9.9.9') != (['9009', '12'], '9.9.9.9/32'):
        f.append('network-info falsch gelesen: %r' % (m.vpn_netz('9.9.9.9'),))
    if not ABRUFE or 'resource=9.9.9.9' not in ABRUFE[0] or 'sourceapp=safari-assistant' not in ABRUFE[0]:
        f.append('RIPEstat-Adresse falsch: %r' % ABRUFE[:1])
    n = len(ABRUFE)
    m.vpn_netz('9.9.9.9')
    if len(ABRUFE) != n:
        f.append('zweite Abfrage derselben Adresse ging wieder ins Netz')
    if m.vpn_netzname('9009') != 'M247 - M247 Europe SRL':
        f.append('Netzname falsch/unbereinigt: %r' % m.vpn_netzname('9009'))
    def hole_kaputt(*a, **k):
        raise OSError('offline')
    m._hole = hole_kaputt
    m._VPN_NETZ_CACHE['9.9.9.9'] = (time.time() - 7 * 3600, ['9009'], 'p')
    if m.vpn_netz('9.9.9.9') != (['9009'], 'p'):
        f.append('bei Ausfall gilt der bis zu 24 h alte Eintrag nicht weiter')
    m._VPN_NETZ_CACHE['9.9.9.9'] = (time.time() - 25 * 3600, ['9009'], 'p')
    if m.vpn_netz('9.9.9.9') != (None, ''):
        f.append('ein über 24 h alter Eintrag gilt noch')
    m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [{'asn': '60068', 'name': 'Datacamp Limited', 'land': 'DE', 'seit': 1}]})
    m._VPN_NAMEN_CACHE.clear()
    if m.vpn_netzname('60068') != 'Datacamp Limited' or m.vpn_netzname('1') != '':
        f.append('offline kein gemerkter Name als Ersatz')
    m._hole = lambda *a, **k: json.dumps({'status': 'error', 'data': {'asns': ['1']}})
    m._VPN_NETZ_CACHE.clear()
    if m.vpn_netz('1.1.1.1') != (None, ''):
        f.append('Antwort mit status != ok übernommen')
    m._hole = echt_hole

    # 8. Gesamtmessung ohne Netz: beide Wege gleichzeitig, Leck erkannt, Anmeldeseite nur wenn nichts ging, kein Log mit Adresse
    echt = (m.vpn_ausgang, m.vpn_netz, m.vpn_netzname, m.vpn_anmeldung_noetig)
    try:
        m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [{'asn': '9009', 'name': 'M247', 'land': 'DE', 'seit': 1}]})
        def ausgang(fam):
            time.sleep(0.5)
            if fam == socket.AF_INET:
                return {'ip': '9.9.9.9', 'land': 'DE', 'quelle': 'trace'}
            return {'ip': '2c0f::1', 'land': 'NA', 'quelle': 'trace'}
        m.vpn_ausgang = ausgang
        m.vpn_netz = lambda ip: (['9009'], 'p4') if ':' not in ip else (['36996'], 'p6')
        m.vpn_netzname = lambda asn: {'9009': 'M247 Europe SRL', '36996': 'Telecom Namibia'}.get(asn, '')
        captive_gefragt = []
        m.vpn_anmeldung_noetig = lambda timeout=5.0: captive_gefragt.append(1) or True
        t0 = time.time()
        with contextlib.redirect_stdout(io.StringIO()) as log:
            m.VPN_STATE['letzte_stufe'] = ''
            m.vpn_messen()
        if time.time() - t0 > 0.95:
            f.append('Wege nicht gleichzeitig gemessen (%.1f s)' % (time.time() - t0))
        st = m.vpn_status()
        if st['stufe'] != 'leck' or st['leck'] != 'IPv6' or captive_gefragt:
            f.append('Gesamtmessung: %r/%r, Anmeldeseite gefragt: %r' % (st['stufe'], st['leck'], captive_gefragt))
        if '9.9.9.9' in log.getvalue() or '2c0f' in log.getvalue() or 'VPN-LECK' not in log.getvalue():
            f.append('Log: %r' % log.getvalue())
        if m.VPN_STATE['laeuft']:
            f.append('Messung bleibt als laufend markiert')
        def ohne_netz(fam):
            raise socket.gaierror(8, 'nodename nor servname provided')
        m.vpn_ausgang = ohne_netz
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_messen()
        st = m.vpn_status()
        if st['stufe'] != 'anmeldung' or st['fehler'] != {'IPv4': 'kein_netz', 'IPv6': 'kein_netz'} or not captive_gefragt:
            f.append('ohne Weg + Anmeldeseite: %r %r' % (st['stufe'], st['fehler']))
        m.vpn_anmeldung_noetig = lambda timeout=5.0: None
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_messen()
        if m.vpn_status()['stufe'] != 'offline':
            f.append('ohne jede Verbindung nicht „offline"')
        m.VPN_STATE['laeuft'] = True
        if m.vpn_messen() is not False:
            f.append('zweite Messung startet, während eine läuft')
        m.VPN_STATE['laeuft'] = False
    finally:
        m.vpn_ausgang, m.vpn_netz, m.vpn_netzname, m.vpn_anmeldung_noetig = echt

    # 8b. Anbieter-Erkennung (2026-11-02-1): ein vom Anbieter bestätigter Ausgang zählt als VPN — nur für diesen Anbieter,
    #     nur eingeschaltet, nie bei unklarer Antwort; Zugangsnetze (Starlink) bleiben Zugang
    mv = m.VPN_ANBIETER.get('mullvad') or {}
    if (mv.get('name'), mv.get('feld'), mv.get('pfad')) != ('Mullvad', 'mullvad_exit_ip', '/json') \
            or mv.get('hosts') != {socket.AF_INET: 'ipv4.am.i.mullvad.net', socket.AF_INET6: 'ipv6.am.i.mullvad.net'}:
        f.append('Mullvad-Eintrag verändert: %r' % mv)
    if set(m.VPN_ANBIETER) != {'mullvad'}:
        f.append('Anbieterliste enthält mehr als Mullvad: %r' % sorted(m.VPN_ANBIETER))

    def AB(fam, asns, anbieter='', **kw):
        a = A(fam, asns, **kw)
        a['anbieter'] = anbieter
        return a
    erw_anb = [
        ([AB('IPv4', ['31173'], 'mullvad')], set(), ('mullvad',), ('vpn', '')),
        ([AB('IPv4', ['31173'], 'mullvad')], set(), (), ('einrichten', '')),               # ausgeschaltet → zählt nicht
        ([AB('IPv4', ['31173'], 'mullvad')], {'9009'}, (), ('kein_vpn', '')),
        ([AB('IPv4', ['31173'], '')], set(), ('mullvad',), ('kein_vpn', '')),              # an, aber nicht bestätigt → rot
        ([AB('IPv4', ['31173'], 'mullvad'), AB('IPv6', ['31173'], '')], set(), ('mullvad',), ('leck', 'IPv6')),
        ([AB('IPv4', ['31173'], 'mullvad'), AB('IPv6', ['31173'], 'mullvad')], set(), ('mullvad',), ('vpn', '')),
        ([AB('IPv4', ['14593'], 'mullvad', name='SPACEX-STARLINK')], set(), ('mullvad',), ('kein_vpn', '')),   # Zugang nie VPN
        ([AB('IPv4', ['31173'], 'unbekannt')], set(), ('unbekannt',), ('kein_vpn', '')),   # nicht in der Anbieterliste
        ([AB('IPv4', None, 'mullvad')], set(), ('mullvad',), ('vpn', '')),                 # bestätigt auch ohne Netzzuordnung
        ([AB('IPv4', ['36996'], '')], {'36996'}, ('mullvad',), ('vpn', '')),               # gemerktes Netz gilt weiter
        ([AB('IPv4', ['31173'], 'mullvad')], set(), ('anderer',), ('kein_vpn', '')),       # nur der eingeschaltete Anbieter
    ]
    for ausg, gem, anb_an, soll in erw_anb:
        ist = m.vpn_bewerten(ausg, gem, None, anb_an)
        if ist != soll:
            f.append('Anbieter-Bewertung %r → %r statt %r' % ([(a['familie'], a['asns'], a['anbieter']) for a in ausg] + [sorted(gem), anb_an], ist, soll))
    a0 = AB('IPv4', ['31173'], 'mullvad', name='ESAB-AS 31173 Services AB')
    m.vpn_bewerten([a0], set(), None, ('mullvad',))
    if a0['vpn'] is not True or a0['anbieter_name'] != 'Mullvad':
        f.append('bestätigter Ausgang: vpn=%r anbieter_name=%r' % (a0['vpn'], a0['anbieter_name']))
    a1 = AB('IPv4', ['31173'], 'mullvad')
    m.vpn_bewerten([a1], set(), None, ())
    if a1['vpn'] is not False or a1['anbieter_name'] != '':
        f.append('Anbieter zählt, obwohl ausgeschaltet: %r' % a1)

    echt = (m.vpn_ausgang, m.vpn_netz, m.vpn_netzname, m.vpn_anmeldung_noetig, m.vpn_anbieter_pruefen)
    try:
        m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [], 'anbieter': ['mullvad']})
        m.VPN_STATE['netzwechsel'] = 0.0

        def ausgang_v4(fam):
            if fam == socket.AF_INET:
                return {'ip': '9.9.9.9', 'land': 'DE', 'quelle': 'trace'}
            raise socket.gaierror(8, 'x')
        m.vpn_ausgang = ausgang_v4
        m.vpn_netz = lambda ip: (['31173'], 'p4')
        m.vpn_netzname = lambda asn: 'ESAB-AS 31173 Services AB'
        m.vpn_anmeldung_noetig = lambda timeout=5.0: None
        gefragt, antwort = [], [True]
        m.vpn_anbieter_pruefen = lambda n, ip, fam: gefragt.append((n, ip, fam)) or antwort[0]
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_messen()
        st = m.vpn_status()
        w = (st['ausgaenge'] or [{}])[0]
        if st['stufe'] != 'vpn' or w.get('anbieter') != 'Mullvad' or w.get('vpn') is not True:
            f.append('Gesamtmessung mit Anbieter: %r %r' % (st['stufe'], w))
        if gefragt != [('mullvad', '9.9.9.9', socket.AF_INET)]:
            f.append('Anbieter gefragt: %r' % gefragt)
        if st['anbieter'] != [{'id': 'mullvad', 'name': 'Mullvad', 'an': True}] or st['eingerichtet'] is not True:
            f.append('Status am Mac: anbieter=%r eingerichtet=%r' % (st.get('anbieter'), st.get('eingerichtet')))
        sp = m.vpn_status(fuer_mac=False)
        if 'anbieter' in sp or sp['ausgaenge'][0].get('anbieter') != 'Mullvad' or 'ip' in sp['ausgaenge'][0]:
            f.append('Status am iPhone: %r' % sp)
        antwort[0] = False                                      # Anbieter sagt „nein" → rot, nie grün
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_messen()
        st = m.vpn_status()
        if st['stufe'] != 'kein_vpn' or st['ausgaenge'][0]['anbieter'] != '' or st['ausgaenge'][0]['vpn'] is not False:
            f.append('Anbieter sagt „nein": %r' % st['stufe'])
        for schlecht in (None, 5, ['mullvad'], {'x': 1}, '', 'gibtsnicht', 'MULLVAD', 'mullvad '):
            try:
                m.vpn_anbieter_einstellen(schlecht, True)
                f.append('Anbieter %r angenommen' % (schlecht,))
            except ValueError as e:
                if str(e) != 'Unbekannter Anbieter.':
                    f.append('Fehlertext für %r: %s' % (schlecht, e))
        if m.vpn_einstellungen()['anbieter'] != ['mullvad']:
            f.append('ungültiger Anbieter hat die Einstellungen verändert')
        antwort[0] = True
        messung([AB('IPv4', ['31173'], 'mullvad')], alter=5)
        time.sleep(0.02)
        with contextlib.redirect_stdout(io.StringIO()) as log:
            m.vpn_anbieter_einstellen('mullvad', False)         # ausschalten → alte Messung gilt nicht mehr
        if m.vpn_status()['stufe'] != 'pruefe':
            f.append('nach dem Umschalten gilt die alte Messung weiter')
        if m.vpn_einstellungen()['anbieter'] != [] or '9.9.9.9' in log.getvalue():
            f.append('ausschalten: %r / Log %r' % (m.vpn_einstellungen()['anbieter'], log.getvalue()))
        gefragt.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_messen()
        st = m.vpn_status()
        if gefragt or st['stufe'] != 'einrichten' or st['eingerichtet'] is not False or st['anbieter'] != [{'id': 'mullvad', 'name': 'Mullvad', 'an': False}]:
            f.append('ausgeschaltet: gefragt=%r stufe=%r eingerichtet=%r anbieter=%r' % (gefragt, st['stufe'], st['eingerichtet'], st['anbieter']))
        # Datei: nur der Name, keine Adresse; doppelt einschalten = einmal; manipulierte Einträge fallen weg
        with contextlib.redirect_stdout(io.StringIO()):
            m.vpn_anbieter_einstellen('mullvad', True)
            m.vpn_anbieter_einstellen('mullvad', True)
        text = m.VPN_DATEI.read_text(encoding='utf-8')
        roh = json.loads(text)
        if roh.get('anbieter') != ['mullvad'] or '9.9.9.9' in text:
            f.append('Datei: %r' % roh.get('anbieter'))
        if os.name == 'posix' and (m.VPN_DATEI.stat().st_mode & 0o777) != 0o600:
            f.append('vpn.json nach dem Umschalten nicht 0600')
        for manip, soll in ((['mullvad', 'evil', 'mullvad', 5, '../x', None], ['mullvad']), ('mullvad', []), ({'mullvad': True}, []), (['evil'], [])):
            roh['anbieter'] = manip
            m.VPN_DATEI.write_text(json.dumps(roh), encoding='utf-8')
            m._VPN_CFG['wert'] = None
            if m.vpn_einstellungen()['anbieter'] != soll:
                f.append('manipulierte Anbieterliste %r → %r' % (manip, m.vpn_einstellungen()['anbieter']))
        del roh['anbieter']
        m.VPN_DATEI.write_text(json.dumps(roh), encoding='utf-8')
        m._VPN_CFG['wert'] = None
        if m.vpn_einstellungen()['anbieter'] != []:
            f.append('ältere Datei ohne Anbieterfeld')
    finally:
        m.vpn_ausgang, m.vpn_netz, m.vpn_netzname, m.vpn_anmeldung_noetig, m.vpn_anbieter_pruefen = echt
        m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [], 'anbieter': []})
        m.VPN_STATE['netzwechsel'] = 0.0

    # 9. Lesen darf das iPhone (ohne Adressen und ohne die gemerkte Liste), prüfen und verwalten nur der Mac
    m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [{'asn': '9009', 'name': 'M247', 'land': 'DE', 'seit': 1}]})
    messung([A('IPv4', ['9009'], 'M247 Europe SRL', ip='8.8.4.4')])
    class AusDemWlan(m.SafariHandler):
        def client_ip(self):
            return '192.168.1.50'
    code = m.zugangs_token()
    m.LAN_STATE.update({'an': True, 'weg': 'schnell', 'tls': False, 'ip': '192.168.1.50', 'seit': time.time()})
    wlan = m.SafariServer(('127.0.0.1', 0), AusDemWlan, lan=True)
    mac = m.SafariServer(('127.0.0.1', 0), m.SafariHandler, lan=False)
    for s in (wlan, mac):
        threading.Thread(target=s.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()

    def anfrage(srv, methode, pfad, body=b'', kopf=''):
        port = srv.server_address[1]
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
        s.sendall(f'{methode} {pfad} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nX-Safari-Zugang: {code}\r\n{kopf}'
                  f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n'.encode() + body)
        d = b''
        while True:
            t = s.recv(8192)
            if not t:
                break
            d += t
        s.close()
        kopf_teil, _, rumpf = d.decode('utf-8', 'replace').partition('\r\n\r\n')
        return kopf_teil.split('\r\n', 1)[0], rumpf
    try:
        zeile, rumpf = anfrage(wlan, 'GET', '/api/vpn/status')
        if ' 200 ' not in zeile:
            f.append('iPhone kann den VPN-Stand nicht lesen: %s' % zeile)
        else:
            d = json.loads(rumpf)
            if d.get('stufe') != 'vpn' or '8.8.4.4' in rumpf or 'gemerkt' in d or 'ip' in d['ausgaenge'][0]:
                f.append('iPhone bekommt Adressen oder die gemerkte Liste: %s' % rumpf[:200])
        for pfad, body in (('/api/vpn/pruefen', b''), ('/api/vpn/merken', b'{"asn":"9009"}'),
                           ('/api/vpn/vergessen', b'{"asn":"9009"}'), ('/api/vpn/einstellungen', b'{"aktiv":false}'),
                           ('/api/vpn/anbieter', b'{"anbieter":"mullvad","an":true}')):
            if ' 403 ' not in anfrage(wlan, 'POST', pfad, body)[0]:
                f.append('iPhone darf %s (nur Mac)' % pfad)
        if m.vpn_einstellungen()['anbieter']:
            f.append('iPhone konnte die Anbieter-Erkennung einschalten')
        zeile, rumpf = anfrage(mac, 'GET', '/api/vpn/status')
        d = json.loads(rumpf) if ' 200 ' in zeile else {}
        if d.get('ausgaenge', [{}])[0].get('ip') != '8.8.4.4' or [g['asn'] for g in d.get('gemerkt', [])] != ['9009']:
            f.append('Mac sieht Adresse oder gemerkte Netze nicht: %s' % rumpf[:200])
        zeile, rumpf = anfrage(mac, 'POST', '/api/vpn/einstellungen', b'{"intervall_s":120}')
        if ' 200 ' not in zeile or m.vpn_einstellungen()['intervall_s'] != 120:
            f.append('Mac kann den Takt nicht ändern: %s %s' % (zeile, rumpf[:120]))
        zeile, rumpf = anfrage(mac, 'POST', '/api/vpn/merken', b'{"asn":"14593"}')
        if ' 400 ' not in zeile or 'Über dieses Netz' not in json.loads(rumpf).get('error', ''):
            f.append('Merken eines fremden Netzes: %s %s' % (zeile, rumpf[:120]))
        if ' 403 ' not in anfrage(mac, 'POST', '/api/vpn/einstellungen', b'{"aktiv":false}', 'Origin: https://boese.example\r\n')[0]:
            f.append('fremde Webseite darf die VPN-Prüfung abschalten')
        if m.vpn_einstellungen()['aktiv'] is not True:
            f.append('VPN-Prüfung wurde von außen abgeschaltet')
        zeile, rumpf = anfrage(mac, 'POST', '/api/vpn/pruefen')
        if ' 200 ' not in zeile or 'gestartet' not in json.loads(rumpf):
            f.append('Jetzt prüfen am Mac: %s' % zeile)
        # Anbieter-Erkennung: nur am Mac, nur bekannte Anbieter, „an" nur bei echtem true, fremde Webseiten nie
        with contextlib.redirect_stdout(io.StringIO()):
            zeile, rumpf = anfrage(mac, 'POST', '/api/vpn/anbieter', b'{"anbieter":"mullvad","an":true}')
        d = json.loads(rumpf) if ' 200 ' in zeile else {}
        if d.get('anbieter') != [{'id': 'mullvad', 'name': 'Mullvad', 'an': True}] or m.vpn_einstellungen()['anbieter'] != ['mullvad']:
            f.append('Mac kann die Anbieter-Erkennung nicht einschalten: %s %s' % (zeile, rumpf[:160]))
        zeile, rumpf = anfrage(mac, 'POST', '/api/vpn/anbieter', b'{"anbieter":"gibtsnicht","an":true}')
        if ' 400 ' not in zeile or json.loads(rumpf).get('error') != 'Unbekannter Anbieter.':
            f.append('unbekannter Anbieter über die Route: %s %s' % (zeile, rumpf[:120]))
        if ' 403 ' not in anfrage(mac, 'POST', '/api/vpn/anbieter', b'{"anbieter":"mullvad","an":false}', 'Origin: https://boese.example\r\n')[0] \
                or m.vpn_einstellungen()['anbieter'] != ['mullvad']:
            f.append('fremde Webseite darf die Anbieter-Erkennung abschalten')
        with contextlib.redirect_stdout(io.StringIO()):
            anfrage(mac, 'POST', '/api/vpn/anbieter', b'{"anbieter":"mullvad","an":"true"}')
        if m.vpn_einstellungen()['anbieter'] != []:
            f.append('„an" als Text „true" schaltet ein')
    finally:
        for s in (wlan, mac):
            s.shutdown(); s.server_close()

    # 9b. iPhone-Zugang bei laufendem VPN am Mac (2026-11-02-2): lan_ip() nimmt die Adresse des WLANs, nicht die des Tunnels
    def ifc(en0='192.168.178.23', status='active', extra=''):
        return ('lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n\tinet 127.0.0.1 netmask 0xff000000\n\tinet6 ::1 prefixlen 128\n'
                'en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n\tether aa:bb:cc:dd:ee:ff\n'
                '\tinet6 fe80::1c5e:1%en0 prefixlen 64 secured scopeid 0xb\n'
                + ('\tinet %s netmask 0xffffff00 broadcast 192.168.178.255\n' % en0 if en0 else '')
                + '\tmedia: autoselect\n\tstatus: ' + status + '\n' + extra
                + 'bridge100: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n\tinet 192.168.64.1 netmask 0xffffff00\n\tstatus: active\n'
                'utun4: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380\n\tinet 10.66.12.5 --> 10.66.12.5 netmask 0xffffffff\n')
    def netstat(*namen):
        zeilen = ''.join('default            192.168.178.1      UGScg                 %s\n' % n for n in namen)
        return ('Routing tables\n\nInternet:\nDestination        Gateway            Flags               Netif Expire\n' + zeilen
                + '0/1                10.66.0.1          UGSc                utun4\n128.0/1            10.66.0.1          UGSc                utun4\n')
    echt_route, echt_befehl = m.lan_ip_route, m._befehl_text
    def lauf(route, ifconfig, ns=''):
        aufrufe = []
        def befehl(b, timeout=4):
            aufrufe.append(b[0])
            return {'ifconfig': ifconfig, 'netstat': ns}.get(b[0], '')
        m.lan_ip_route = lambda: route
        m._befehl_text = befehl
        m._LAN_IP_CACHE.update({'route': None, 'ip': '', 'zeit': 0.0})
        return m.lan_ip(), aufrufe
    try:
        TUN = '10.66.12.5'
        fall = [
            ('VPN am Mac, Standardroute en0', lauf(TUN, ifc(), netstat('en0'))[0], '192.168.178.23'),
            ('VPN am Mac, netstat fehlt → aktives en0', lauf(TUN, ifc(), '')[0], '192.168.178.23'),
            ('VPN am Mac, en0 inaktiv → Adresse der Route (unverändert)', lauf(TUN, ifc(status='inactive'), netstat('en0'))[0], TUN),
            ('VPN am Mac, en0 ohne Adresse → unverändert', lauf(TUN, ifc(en0=None), netstat('en0'))[0], TUN),
            ('VPN am Mac, öffentliche Adresse an en0 → unverändert', lauf(TUN, ifc(en0='8.8.4.4'), netstat('en0'))[0], TUN),
            ('VPN am Mac, Hotspot 172.20.10.2', lauf(TUN, ifc(en0='172.20.10.2'), netstat('en0'))[0], '172.20.10.2'),
            ('ifconfig liefert nichts → unverändert', lauf(TUN, '', netstat('en0'))[0], TUN),
            ('kein Netz (leere Route)', lauf('', ifc(), netstat('en0'))[0], ''),
        ]
        for name, ist, soll in fall:
            if ist != soll:
                f.append('lan_ip: %s → %r statt %r' % (name, ist, soll))
        ip, aufrufe = lauf('192.168.178.23', ifc(), netstat('en0'))
        if ip != '192.168.178.23' or 'netstat' in aufrufe:
            f.append('ohne VPN: %r, Befehle %r (Route über en0 → unverändert, kein netstat)' % (ip, aufrufe))
        ip, aufrufe = lauf(TUN, ifc(en0='192.168.178.23'), netstat('utun4', 'en1', 'en0'))
        if ip != '192.168.178.23':
            f.append('Standardroute: Tunnel übersprungen, en1 hat keine Adresse → en0 erwartet, %r' % ip)
        # Zwischenspeicher: gleiche Route innerhalb von LAN_IP_CACHE_S → keine neuen Befehle; andere Route → neu
        ip, aufrufe = lauf(TUN, ifc(), netstat('en0'))
        n0 = len(aufrufe)
        m.lan_ip(); m.lan_ip()
        if len(aufrufe) != n0:
            f.append('lan_ip fragt bei jeder Anfrage das System (%d → %d Befehle)' % (n0, len(aufrufe)))
        m.lan_ip_route = lambda: '192.168.178.23'
        m.lan_ip()
        if len(aufrufe) == n0:
            f.append('lan_ip bemerkt eine andere Route nicht')
        # Parser: ifconfig (macOS) und ip -4 -o addr (Linux), Tunnel-Namen
        ifs = m._schnittstellen_aus_text(ifc())
        if ifs.get('en0') != {'ips': ['192.168.178.23'], 'aktiv': True} or ifs.get('utun4', {}).get('ips') != ['10.66.12.5'] or ifs.get('lo0', {}).get('ips') != ['127.0.0.1']:
            f.append('ifconfig falsch gelesen: %r' % ifs)
        lx = m._schnittstellen_aus_text('2: eth0    inet 192.168.1.5/24 brd 192.168.1.255 scope global dynamic eth0\n3: wg0    inet 10.66.12.5/32 scope global wg0\n')
        if lx != {'eth0': {'ips': ['192.168.1.5'], 'aktiv': None}, 'wg0': {'ips': ['10.66.12.5'], 'aktiv': None}}:
            f.append('ip -o falsch gelesen: %r' % lx)
        for n in ('utun4', 'tun0', 'tap1', 'wg0', 'ppp0', 'ipsec0', 'nordlynx', 'tailscale0'):
            if not m.TUNNEL_SCHNITTSTELLEN.match(n):
                f.append('Tunnel nicht erkannt: ' + n)
        for n in ('en0', 'en5', 'bridge100', 'lo0', 'awdl0', 'eth0'):
            if m.TUNNEL_SCHNITTSTELLEN.match(n):
                f.append('Kein Tunnel, aber erkannt: ' + n)
    finally:
        m.lan_ip_route, m._befehl_text = echt_route, echt_befehl
        m._LAN_IP_CACHE.update({'route': None, 'ip': '', 'zeit': 0.0})

    # 10. Wache: misst nur bei Bedarf, im Takt, und nach einem Netzwechsel sofort
    gemessen = []
    netze = ['192.168.178.50']
    def messen_stub():
        gemessen.append(time.time())
        m.VPN_STATE['messung'] = {'zeit': time.time(), 'dauer_s': 0, 'ausgaenge': [A('IPv4', ['9009'])], 'fehler': {}, 'captive': None}
        return True
    m.vpn_messen = messen_stub
    m.lan_ip_route = lambda: netze[0]       # die Wache achtet auf die Adresse der Route (auch VPN an/aus am Mac)
    m._lan_ip_ohne_tunnel = lambda route: '192.168.1.99'   # lan_ip() bliebe bei VPN an/aus gleich — die Wache muss die Route beachten
    m.VPN_TAKT_S = 0.05
    m.vpn_speichern({'aktiv': True, 'intervall_s': 60, 'gemerkt': [{'asn': '9009', 'name': 'M247', 'land': 'DE', 'seit': 1}]})
    m.VPN_STATE.update({'messung': None, 'nachfrage': 0.0, 'netzwechsel': 0.0, 'laeuft': False})
    m.starte_vpn_wache()
    time.sleep(0.4)
    if gemessen:
        f.append('Wache misst ohne Bedarf (keine Seite offen)')
    m.vpn_status()                      # eine Seite fragt
    time.sleep(0.4)
    if len(gemessen) != 1:
        f.append('Wache misst bei Bedarf nicht genau einmal: %d' % len(gemessen))
    time.sleep(0.3)
    if len(gemessen) != 1:
        f.append('Wache misst vor Ablauf des Takts erneut')
    netze[0] = '192.168.1.23'           # Netzwechsel (anderes WLAN)
    time.sleep(0.02)
    for _ in range(40):
        if len(gemessen) >= 2:
            break
        time.sleep(0.05)
    if len(gemessen) < 2:
        f.append('nach einem Netzwechsel keine neue Messung')
    if m.vpn_status()['stufe'] != 'vpn':
        f.append('nach der neuen Messung nicht wieder grün')
    m.VPN_STATE['nachfrage'] = 0.0
    m.vpn_speichern({'aktiv': False, 'intervall_s': 60, 'gemerkt': []})
except Exception as e:
    import traceback
    f.append('Abbruch: %s: %s | %s' % (e.__class__.__name__, e, traceback.format_exc().strip().splitlines()[-3:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
