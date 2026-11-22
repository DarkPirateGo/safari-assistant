# Ausgeführter Test der Nachrichten aus RSS-Feeds (2026-10-18-2): Adressprüfung (kein Abruf ins eigene Netz),
# Abruf (bedingt, gzip, Größendeckel, Zip-Bombe), Lesen von RSS 2.0 / RDF / Atom / GDACS, Datumsformate, Zuordnung
# zu Themen, Ländern und „wichtig", eigene Quellen (anlegen, prüfen, schalten, entfernen, manipulierte Datei),
# Gesamtabruf mit Doppelten, ETag und Offline-Abbruch, und die Trennung lesen (iPhone) / verwalten (nur Mac).
# Wird von test-app.js (Sektion 69) ausgeführt; den Pfad zu server.py setzt test-app.js ein. Schreibt nichts ins Home.
import sys, importlib.util, socket, threading, tempfile, shutil, json, gzip, time, os
sys.dont_write_bytecode = True
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location("srv", SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []
tmp = Path(tempfile.mkdtemp(prefix='safari-nachrichten-test-'))
m.NACHRICHTEN_DATEI = tmp / 'nachrichten.json'
m.FEEDS_DATEI = tmp / 'feeds.json'
m.TOKEN_DATEI = tmp / 'zugang'
m._TOKEN_CACHE['wert'] = ''
m.ZUSTAND_DATEI = tmp / 'iphone.json'
m._ZUSTAND_CACHE['wert'] = None
JETZT = int(time.time())


def rfc(sek):
    return time.strftime('%a, %d %b %Y %H:%M:%S +0000', time.gmtime(sek))


RSS = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Nyasa Times</title><link>https://www.nyasatimes.com</link><description>x</description>
<item><title>Fuel queues return in Lilongwe as shortage bites</title><link>https://www.nyasatimes.com/fuel-queues/</link>
<pubDate>{rfc(JETZT - 3600)}</pubDate><guid isPermaLink="false">https://www.nyasatimes.com/?p=1</guid>
<category>Business</category>
<description><![CDATA[<p>Motorists spent the night at <b>filling stations</b> in Lilongwe.</p><p>The post Fuel queues appeared first on Malawi Nyasa Times.</p>]]></description></item>
<item><title>Government closes border with Mozambique after clashes</title><link>https://www.nyasatimes.com/border/</link>
<pubDate>{rfc(JETZT - 7200)}</pubDate><description>Security forces were deployed.</description></item>
<item><title>Flames beat Zambia 2-1 in friendly</title><link>https://www.nyasatimes.com/flames/</link><pubDate>{rfc(JETZT - 7300)}</pubDate></item>
<item><title>Old cholera story</title><link>https://www.nyasatimes.com/old/</link><pubDate>{rfc(JETZT - 40 * 86400)}</pubDate></item>
<item><title>Bad link cholera outbreak</title><link>javascript:alert(1)</link><pubDate>{rfc(JETZT + 5 * 86400)}</pubDate></item>
</channel></rss>'''.encode('utf-8')

ATOM = b'''<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Travel Advice Summary</title><id>x</id><updated>2026-10-10T10:00:00+01:00</updated>
<entry><title>Malawi travel advice</title><link rel="self" href="https://www.gov.uk/x.atom"/><link rel="alternate" type="text/html" href="https://www.gov.uk/foreign-travel-advice/malawi"/>
<id>https://www.gov.uk/foreign-travel-advice/malawi#2026-10-10 10:00:00 +0100</id><updated>2026-10-10T10:00:00+01:00</updated>
<summary type="html">New information about Traveller Health Check form ('Entry requirements' page).</summary></entry></feed>'''

RDF = f'''<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel rdf:about="https://allafrica.com"><title>AllAfrica News: Ethiopia</title><items><rdf:Seq><rdf:li rdf:resource="https://allafrica.com/a1"/></rdf:Seq></items></channel>
<item rdf:about="https://allafrica.com/a1"><title>Renewed Conflict in Tigray Raises Fears of a New Humanitarian Emergency</title>
<description>Fighting and attacks were reported near Mekelle &amp;#xE3;</description><dc:date>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(JETZT - 5000))}</dc:date></item>
</rdf:RDF>'''.encode('utf-8')

GDACS = f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:gdacs="http://www.gdacs.org" xmlns:georss="http://www.georss.org/georss"><channel><title>GDACS</title>
<item><title>Orange alert for tropical cyclone DINEO-26</title><link>https://www.gdacs.org/report.aspx?eventid=1</link><pubDate>{rfc(JETZT - 600)}</pubDate>
<gdacs:alertlevel>Orange</gdacs:alertlevel><gdacs:iso3>MOZ</gdacs:iso3><gdacs:country>Mozambique</gdacs:country><gdacs:eventtype>TC</gdacs:eventtype></item>
<item><title>Green earthquake (Magnitude 4.8M) in Papua New Guinea</title><link>https://www.gdacs.org/x</link><pubDate>{rfc(JETZT - 600)}</pubDate>
<gdacs:alertlevel>Green</gdacs:alertlevel><gdacs:iso3>PNG</gdacs:iso3><gdacs:country>Papua New Guinea</gdacs:country></item>
<item><title>Green earthquake (Magnitude 4.5M) in Malawi</title><link>https://www.gdacs.org/y</link><pubDate>{rfc(JETZT - 600)}</pubDate>
<gdacs:alertlevel>Green</gdacs:alertlevel><gdacs:iso3>MWI</gdacs:iso3></item>
</channel></rss>'''.encode('utf-8')

try:
    # 1. Adressen: nur öffentliche http(s)-Adressen
    for url, soll in [('https://www.namibian.com.na/feed/', True), ('http://example.com/rss', True), ('https://1.1.1.1/feed', True),
                      ('', False), ('ftp://example.com/f', False), ('javascript:alert(1)', False), ('file:///etc/passwd', False),
                      ('http://localhost:11434/api/tags', False), ('http://127.0.0.1/', False), ('http://10.0.0.1/', False),
                      ('http://192.168.178.1/', False), ('http://169.254.1.1/', False), ('http://[::1]/', False),
                      ('http://100.64.0.1/', False), ('http://0.0.0.0/', False), ('http://macbook.local/feed', False),
                      ('http://router/', False), ('https://user:pw@example.com/feed', False), ('http://example.com:99999/', False),
                      ('https://example.com/ feed', False), ('http://fritz.box.home/', False)]:
        if (m.feed_url_pruefen(url) == '') != soll:
            f.append('feed_url_pruefen(%r) %s' % (url, 'abgelehnt' if soll else 'angenommen'))
    echt_gai = m.socket.getaddrinfo
    for adressen, soll in [(['1.1.1.1'], True), (['127.0.0.1'], False), (['1.1.1.1', '192.168.1.1'], False),
                           (['fe80::1%en0'], False), (['2606:4700:4700::1111'], True)]:
        m.socket.getaddrinfo = lambda *a, adr=adressen, **k: [(2, 1, 6, '', (x, 0)) for x in adr]
        if m.feed_host_oeffentlich('beispiel.org') != soll:
            f.append('feed_host_oeffentlich bei %r' % adressen)
    # Weiterleitung ins eigene Netz wird abgelehnt
    import urllib.request
    m.socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, '', ('1.1.1.1', 0))]
    h = m._FeedWeiterleitung()
    req = urllib.request.Request('https://beispiel.org/feed')
    for ziel in ('http://127.0.0.1:11434/api/tags', 'http://macbook.local/', 'file:///etc/passwd'):
        try:
            h.redirect_request(req, None, 302, 'Found', {}, ziel)
            f.append('Weiterleitung nach %s nicht abgelehnt' % ziel)
        except ValueError:
            pass
    if h.redirect_request(req, None, 302, 'Found', {}, 'https://beispiel.org/neu') is None:
        f.append('Weiterleitung auf eine öffentliche Adresse abgelehnt')
    m.socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, '', ('192.168.1.1', 0))]
    try:
        h.redirect_request(req, None, 302, 'Found', {}, 'https://boese.example/feed')
        f.append('Weiterleitung auf einen Namen, der ins WLAN zeigt, nicht abgelehnt')
    except ValueError:
        pass
    m.socket.getaddrinfo = echt_gai

    # 2. Lesen: RSS 2.0, Atom, RDF, GDACS; Webseiten, Entities und kaputtes XML werden abgelehnt
    titel, roh = m.feed_parsen(RSS)
    if titel != 'Nyasa Times' or len(roh) != 5 or roh[0]['link'] != 'https://www.nyasatimes.com/fuel-queues/' or roh[0]['kategorien'] != ['Business']:
        f.append('RSS 2.0 falsch gelesen: %r / %r' % (titel, roh[:1]))
    titel, roh = m.feed_parsen(ATOM)
    if len(roh) != 1 or roh[0]['link'] != 'https://www.gov.uk/foreign-travel-advice/malawi' or 'Traveller Health' not in roh[0]['text']:
        f.append('Atom falsch gelesen (Link rel=alternate, summary): %r' % roh)
    titel, roh = m.feed_parsen(RDF)
    if titel != 'AllAfrica News: Ethiopia' or len(roh) != 1 or roh[0]['link'] != 'https://allafrica.com/a1' or not roh[0]['datum']:
        f.append('RDF (RSS 1.0) falsch gelesen: %r %r' % (titel, roh))
    titel, roh = m.feed_parsen(GDACS)
    if roh[0]['extra'].get('iso3') != 'MOZ' or roh[0]['extra'].get('alertlevel') != 'Orange':
        f.append('GDACS-Felder nicht gelesen: %r' % roh[0].get('extra'))
    for schlecht, wort in [(b'<!DOCTYPE html><html><body>Hallo</body></html>', 'Webseite'),
                           (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]><rss><channel><title>&lol2;</title></channel></rss>', 'Entity'),
                           (b'<rss><channel><item><title>kaputt</channel>', 'XML'), (b'<html><body>x</body></html>', ''),
                           (b'<?xml version="1.0"?><kml><Document/></kml>', 'Feed'), (b'', 'Leer')]:
        try:
            m.feed_parsen(schlecht)
            f.append('kein Feed angenommen: %r' % schlecht[:40])
        except ValueError as e:
            if wort and wort not in str(e):
                f.append('Fehlertext ohne %r: %s' % (wort, e))

    # 3. Datumsformate
    import calendar
    t1 = calendar.timegm((2026, 10, 18, 6, 38, 50))
    t0 = calendar.timegm((2026, 10, 18, 0, 0, 0))
    for s, soll in [('Sun, 18 Oct 2026 06:38:50 +0000', t1), ('2026-10-18T06:38:50Z', t1),
                    ('2026-10-18T08:38:50+02:00', t1), ('2026-10-18T08:38:50.123+0200', t1),
                    ('2026-10-18', t0), ('Sun, 18 Oct 2026 08:38:50 +0200', t1), ('Sun, 18 Oct 2026 06:38:50 GMT', t1),
                    ('gestern', 0), ('', 0)]:
        if m.feed_zeit(s) != soll:
            f.append('feed_zeit(%r) = %r statt %r' % (s, m.feed_zeit(s), soll))

    # 4. Zuordnung: Themen, Länder, wichtig
    zeitung = {'id': 'zeitung-mw', 'name': 'Nyasa Times', 'url': 'https://www.nyasatimes.com/feed/', 'land': 'MW',
               'thema': '', 'filter': True, 'nur_route': False, 'art': 'zeitung'}
    _, roh = m.feed_parsen(RSS)
    n = [m.nachricht_aus_roh(r, zeitung, JETZT) for r in roh]
    if not n[0] or n[0]['themen'][0] != 'treibstoff' or n[0]['laender'] != ['MW'] or n[0]['kritisch']:
        f.append('Treibstoff-Meldung falsch zugeordnet: %r' % n[0])
    if n[0] and ('appeared first' in n[0]['text'] or '<' in n[0]['text'] or 'filling stations' not in n[0]['text']):
        f.append('Anriss nicht bereinigt: %r' % (n[0] or {}).get('text'))
    if not n[1] or not {'einreise', 'sicherheit'} <= set(n[1]['themen']) or not n[1]['kritisch'] or n[1]['laender'] != ['MW', 'MZ']:
        f.append('Grenzschließung falsch zugeordnet: %r' % n[1])
    if n[2] is not None:
        f.append('Fußballmeldung ohne Thema trotz Filter übernommen')
    if n[3] is not None:
        f.append('Meldung älter als %d Tage übernommen' % m.NACHRICHTEN_TAGE)
    if not n[4] or n[4]['link'] != '' or n[4]['zeit'] != JETZT:
        f.append('javascript:-Link oder Zukunftsdatum nicht abgefangen: %r' % n[4])
    if n[0]['id'] == n[1]['id'] or n[0]['id'] != m.nachricht_aus_roh(roh[0], zeitung, JETZT)['id']:
        f.append('Kennungen nicht eindeutig oder nicht stabil')
    for text, land, themen_soll, laender_soll in [
            ('Cheias em Moçambique: estrada N1 intransitável', 'MZ', {'natur', 'strassen'}, ['MZ']),
            ('Pénurie de carburant à Bujumbura', 'BI', {'treibstoff'}, ['BI']),
            ('Malawians queue for forex as kwacha slides', 'MW', {'geld'}, ['MW']),
            ('Cholera outbreak declared in Kenyan coastal county', 'KE', {'gesundheit'}, ['KE'])]:
        q = dict(zeitung, land=land)
        r = m.nachricht_aus_roh({'titel': text}, q, JETZT)
        if not r or not themen_soll <= set(r['themen']) or r['laender'][:1] != laender_soll:
            f.append('Zuordnung von %r: %r' % (text, r))
    if m.themen_zuordnen('flood flood bridge')[:2] != ['natur', 'strassen']:
        f.append('Reihenfolge der Themen nicht nach Trefferzahl: %r' % m.themen_zuordnen('flood flood bridge'))
    for wort in ('Tanzanite prices rise', 'The hospitality sector grows', 'Bachelor students'):
        if m.laender_erkennen(wort) or 'gesundheit' in m.themen_zuordnen(wort) or m.themen_zuordnen(wort) == ['strassen']:
            f.append('Wortanfang/ganzes Wort greift nicht bei %r: %r %r' % (wort, m.laender_erkennen(wort), m.themen_zuordnen(wort)))
    # weltweite Quellen: nur die 16 Länder
    cdc = next(q for q in m.NACHRICHTEN_QUELLEN if q['id'] == 'cdc')
    if m.nachricht_aus_roh({'titel': 'Level 1 - Rift Valley Fever in Mauritania and Senegal'}, cdc, JETZT) is not None:
        f.append('CDC-Meldung ohne Routenland übernommen')
    r = m.nachricht_aus_roh({'titel': 'Level 1 - East African Sleeping Sickness in Zambia and Zimbabwe'}, cdc, JETZT)
    if not r or r['laender'] != ['ZM', 'ZW'] or r['themen'][0] != 'gesundheit':
        f.append('CDC-Meldung zu Sambia/Zimbabwe: %r' % r)
    gdacs = next(q for q in m.NACHRICHTEN_QUELLEN if q['id'] == 'gdacs')
    _, roh = m.feed_parsen(GDACS)
    g = [m.nachricht_aus_roh(x, gdacs, JETZT) for x in roh]
    if not g[0] or not g[0]['kritisch'] or g[0]['laender'] != ['MZ'] or g[0]['themen'][0] != 'natur':
        f.append('GDACS Orange/Mosambik: %r' % g[0])
    if g[1] is not None:
        f.append('GDACS Papua-Neuguinea übernommen')
    if not g[2] or g[2]['kritisch'] or g[2]['laender'] != ['MW']:
        f.append('GDACS Grün/Malawi: %r' % g[2])
    fcdo = next(q for q in m.NACHRICHTEN_QUELLEN if q['id'] == 'fcdo-mw')
    _, roh = m.feed_parsen(ATOM)
    r = m.nachricht_aus_roh(dict(roh[0], datum=rfc(JETZT - 100)), fcdo, JETZT)
    if not r or 'einreise' not in r['themen'] or r['laender'] != ['MW']:
        f.append('FCDO-Atom-Meldung: %r' % r)
    gnews = next(q for q in m.NACHRICHTEN_QUELLEN if q['id'] == 'gnews-mw')
    r = m.nachricht_aus_roh({'titel': 'Malawi fuel crisis deepens - Nyasa Times', 'text': '<a href="x">Malawi fuel crisis deepens</a>&nbsp;Nyasa Times'}, gnews, JETZT)
    if not r or r['text'] != '' or not r['kritisch']:
        f.append('Google-News-Meldung (kein Anriss, „fuel crisis" wichtig): %r' % r)
    eigen = {'id': 'eigen-00000001', 'name': 'Blog', 'url': 'https://blog.example/feed', 'land': '', 'thema': 'parks', 'filter': True, 'nur_route': False}
    r = m.nachricht_aus_roh({'titel': 'Our week in the desert'}, eigen, JETZT)
    if not r or r['themen'] != ['parks'] or r['laender'] != []:
        f.append('Eigene Quelle mit festem Thema: %r' % r)
    r = m.nachricht_aus_roh({'titel': 'Our week in the desert'}, dict(eigen, thema='', filter=False), JETZT)
    if not r or r['themen'] != ['sonstiges']:
        f.append('Eigene Quelle ohne Filter, ohne Thema → „Weitere Meldungen": %r' % r)
    if m.nachricht_aus_roh({'titel': 'Our week in the desert'}, dict(eigen, thema=''), JETZT) is not None:
        f.append('Eigene Quelle mit Filter übernimmt Meldung ohne Thema')
    lang = m.nachricht_aus_roh({'titel': 'Fuel ' + 'x' * 600, 'text': 'fuel ' * 300}, zeitung, JETZT)
    if len(lang['titel']) > m.NACHRICHT_TITEL_MAX + 2 or len(lang['text']) > m.NACHRICHT_TEXT_MAX + 2:
        f.append('Titel/Anriss nicht gekürzt')
    # 2026-11-15-6: US-Botschaft — nur Warnungen, keine Routinemeldungen; Orte je Meldung für „In deiner Nähe"
    bot = [q for q in m.NACHRICHTEN_QUELLEN if q['id'] == 'botschaft-za'][0]
    for t in ('Security Alert: U.S. Consulate General Durban, South Africa (October 13, 2026)', 'Demonstration Alert: Unrest ahead of elections',
              'Health Alert: Updates for Travelers Impacted by the Ebola-Related Travel Restrictions', 'Worldwide Caution: Public Health Arrival Restrictions'):
        r = m.nachricht_aus_roh({'titel': t}, bot, JETZT)
        if not r or r['laender'] != ['ZA'] or r['themen'][0] not in ('sicherheit', 'gesundheit', 'natur'):
            f.append('Botschaftswarnung nicht übernommen: %s → %r' % (t, r))
    for t in ('Consular Services in George and Plettenberg Bay November 17', 'Routine Message: Consular Services in Pietermaritzburg',
              'Voting in U.S. Elections from Overseas', 'RFQ: Procurement and Delivery of Slide Gate Motor Systems'):
        if m.nachricht_aus_roh({'titel': t}, bot, JETZT) is not None:
            f.append('Routinemeldung der Botschaft übernommen: ' + t)
    merk = m._ORTE_NAMEN
    m._ORTE_NAMEN = {'Südafrika': {'cape town': ('Cape Town', -33.926, 18.423, 4772846), 'durban': ('Durban', -29.858, 31.029, 3338026),
                                   'bethlehem': ('Bethlehem', -28.231, 28.307, 91075)},
                     'Kenia': {'nairobi': ('Nairobi', -1.283, 36.817, 2750547)}}
    o = m.orte_in_meldung('Protests near Cape Town airport; also in durban (klein) and Bethlehem. Nairobi quiet.', ['ZA'])
    if o != [['Cape Town', -33.926, 18.423], ['Bethlehem', -28.231, 28.307]]:
        f.append('Orte je Meldung (nur groß geschrieben, nur Länder der Meldung, größte zuerst): %r' % o)
    if m.orte_in_meldung('Lage in Kapstadt angespannt', ['ZA']) != [['Cape Town', -33.926, 18.423]]:
        f.append('deutscher Ortsname Kapstadt nicht erkannt')
    if m.orte_in_meldung('Cape Town', []) != []:
        f.append('Orte ohne Land der Meldung gesucht')
    m._ORTE_NAMEN = merk
    if len(m.NACHRICHTEN_QUELLEN) != 2 + 4 * 16 or len({q['id'] for q in m.NACHRICHTEN_QUELLEN}) != len(m.NACHRICHTEN_QUELLEN):
        f.append('eingebaute Quellen: %d (doppelte Kennungen?)' % len(m.NACHRICHTEN_QUELLEN))
    for q in m.NACHRICHTEN_QUELLEN:
        if m.feed_url_pruefen(q['url']):
            f.append('eingebaute Quelle mit unzulässiger Adresse: ' + q['id'])

    # 5. Eigene Quellen: anlegen, prüfen, schalten, entfernen — und eine manipulierte Datei
    q1 = m.eigene_quelle_anlegen({'name': 'Overland-Blog', 'url': 'https://blog.example/feed/', 'land': 'na', 'thema': '', 'filter': True})
    if not q1['id'].startswith('eigen-') or q1['land'] != 'NA' or (m.FEEDS_DATEI.stat().st_mode & 0o777) != 0o600:
        f.append('eigene Quelle falsch angelegt: %r' % q1)
    for d, wort in [({'name': 'X', 'url': 'https://blog.example/feed'}, 'schon'),
                    ({'name': 'X', 'url': 'https://www.namibian.com.na/feed/'}, 'schon'),
                    ({'name': 'X', 'url': 'http://localhost:11434/'}, 'eigenen Netz'),
                    ({'name': '<script>', 'url': 'https://a.example/f'}, 'Namen'),
                    ({'name': 'X', 'url': 'https://a.example/f', 'land': 'XX'}, 'Land'),
                    ({'name': 'X', 'url': 'https://a.example/f', 'thema': 'foo'}, 'Thema')]:
        try:
            m.eigene_quelle_anlegen(d)
            f.append('unzulässige eigene Quelle angenommen: %r' % d)
        except ValueError as e:
            if wort not in str(e):
                f.append('Begründung ohne %r: %s' % (wort, e))
    alt_max = m.EIGENE_QUELLEN_MAX
    m.EIGENE_QUELLEN_MAX = 1
    try:
        m.eigene_quelle_anlegen({'name': 'Zwei', 'url': 'https://zwei.example/feed'})
        f.append('Obergrenze eigener Quellen greift nicht')
    except ValueError:
        pass
    m.EIGENE_QUELLEN_MAX = alt_max
    m.quelle_schalten('gdacs', False)
    if any(q['id'] == 'gdacs' for q in m.nachrichten_quellen_aktiv()):
        f.append('abgeschaltete eingebaute Quelle bleibt aktiv')
    m.quelle_schalten('gdacs', True)
    m.quelle_schalten(q1['id'], False)
    if any(q['id'] == q1['id'] for q in m.nachrichten_quellen_aktiv()) or not any(q['id'] == 'gdacs' for q in m.nachrichten_quellen_aktiv()):
        f.append('Schalten wirkt nicht')
    try:
        m.eigene_quelle_loeschen('gdacs')
        f.append('eingebaute Quelle ließ sich löschen')
    except ValueError:
        pass
    m.eigene_quelle_loeschen(q1['id'])
    if m.feeds_lesen()['eigene']:
        f.append('eigene Quelle nicht entfernt')
    m.FEEDS_DATEI.write_text(json.dumps({'eigene': [
        {'id': 'eigen-zzzz', 'name': 'a', 'url': 'https://a.example/'}, {'id': 'eigen-0000000a', 'name': 'b', 'url': 'http://127.0.0.1/'},
        {'id': 'eigen-0000000b', 'name': 'ok', 'url': 'https://ok.example/feed', 'boese': 1, 'nur_route': True}, 'kein dict'],
        'aus': ['gdacs', 'erfunden', 7]}))
    cfg = m.feeds_lesen()
    if [q['id'] for q in cfg['eigene']] != ['eigen-0000000b'] or cfg['aus'] != ['gdacs'] or 'boese' in cfg['eigene'][0] or cfg['eigene'][0]['nur_route']:
        f.append('manipulierte Quellen-Datei nicht bereinigt: %r' % cfg)
    m.FEEDS_DATEI.unlink()

    # 6. Abruf gegen einen lokalen Server — Prüfung der Adresse für den Test überbrückt (sonst ist 127.0.0.1 gesperrt)
    zaehler = {'304': 0}

    class Feeds(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == '/a.xml':
                if self.headers.get('If-None-Match') == '"v1"':
                    zaehler['304'] += 1
                    self.send_response(304); self.end_headers(); return
                body = gzip.compress(RSS)
                self.send_response(200); self.send_header('ETag', '"v1"'); self.send_header('Content-Encoding', 'gzip')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path == '/b.xml':   # dieselbe Grenzmeldung wie in a.xml — als Doppelte zu erkennen
                body = RSS.replace(b'Nyasa Times', b'Andere Zeitung').replace(b'nyasatimes.com/', b'andere.example/')
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path == '/bombe':
                body = gzip.compress(b'<rss>' + b' ' * (m.FEED_MAX_BYTES + 10) + b'</rss>')
                self.send_response(200); self.send_header('Content-Encoding', 'gzip'); self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if self.path == '/gross':
                body = b'<rss>' + b' ' * (m.FEED_MAX_BYTES + 10) + b'</rss>'
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path == '/umleitung':
                self.send_response(302); self.send_header('Location', 'http://127.0.0.1:11434/api/tags'); self.end_headers(); return
            self.send_response(404); self.end_headers()

    fsrv = ThreadingHTTPServer(('127.0.0.1', 0), Feeds)
    fport = fsrv.server_address[1]
    threading.Thread(target=fsrv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
    basis = f'http://127.0.0.1:{fport}'
    echt_pruefen, echt_oeffentlich, echt_adresse = m.feed_url_pruefen, m.feed_host_oeffentlich, m.feed_adresse_erlaubt
    m.feed_url_pruefen = lambda u: '' if str(u).startswith(basis) else echt_pruefen(u)
    m.feed_host_oeffentlich = lambda h: True
    m.feed_adresse_erlaubt = lambda a: True      # 2026-11-14-1: auch die Prüfung beim Verbinden (der Testserver ist 127.0.0.1)
    try:
        # 5a. 2026-11-14-1 (Review S6): DNS-Rebinding. Der Name löst beim Prüfen öffentlich auf, beim Verbinden
        # auf 127.0.0.1 — der Abruf darf den lokalen Server nicht erreichen (vorher: zwei getrennte Auflösungen).
        m.feed_host_oeffentlich, m.feed_adresse_erlaubt = echt_oeffentlich, echt_adresse
        m.feed_url_pruefen = echt_pruefen
        gai_vorher, rufe, treffer_vorher = m.socket.getaddrinfo, {'n': 0}, zaehler.get('alle', 0)
        def gai_wechsel(host, port=None, *a, **k):
            if host == 'beispiel.org':
                rufe['n'] += 1
                return [(2, 1, 6, '', ('1.1.1.1' if rufe['n'] == 1 else '127.0.0.1', port or 0))]
            return gai_vorher(host, port, *a, **k)
        m.socket.getaddrinfo = gai_wechsel
        # Der echte Öffner muss die drei Bausteine enthalten. Für den Abruf selbst wird er ohne Proxy nachgebaut:
        # steht in der Umgebung ein Proxy (http_proxy, am Mac auch die Systemeinstellung), geht die Anfrage dorthin
        # und der Test mäße den Proxy statt der Verbindung (so gesehen am 14.11. in der Prüfumgebung).
        oeffner_vorher = m._FEED_OPENER
        for baustein in (m._FeedWeiterleitung, m._FeedHTTP, m._FeedHTTPS):
            if not any(isinstance(h, baustein) for h in oeffner_vorher.handlers):
                f.append('S6: _FEED_OPENER enthält %s nicht' % baustein.__name__)
        m._FEED_OPENER = m.urllib.request.build_opener(m._FeedWeiterleitung, m._FeedHTTP, m._FeedHTTPS, m.urllib.request.ProxyHandler({}))
        try:
            m.feed_holen(f'http://beispiel.org:{fport}/a.xml', timeout=3)
            f.append('S6: Feed-Abruf folgt einem Namen, der beim Verbinden auf 127.0.0.1 zeigt (DNS-Rebinding)')
        except ValueError as e:
            if 'eigene Netz' not in str(e):
                f.append('S6: falscher Grund bei DNS-Rebinding: %r' % str(e))
        except Exception as e:
            f.append('S6: DNS-Rebinding endet mit %s statt mit der Ablehnung' % e.__class__.__name__)
        finally:
            m.socket.getaddrinfo = gai_vorher
            m._FEED_OPENER = oeffner_vorher
        if rufe['n'] < 2:
            f.append('S6: der Test hat die zweite Auflösung nie erreicht (%d)' % rufe['n'])
        # … und eine Adresse, die schon beim Verbinden gemischt ist (öffentlich + WLAN), wird ganz abgelehnt
        m.socket.getaddrinfo = lambda host, port=None, *a, **k: [(2, 1, 6, '', ('1.1.1.1', port or 0)), (2, 1, 6, '', ('192.168.1.1', port or 0))]
        try:
            m._feed_socket('beispiel.org', 80, 2)
            f.append('S6: gemischte Auflösung (öffentlich + eigenes Netz) wird verbunden')
        except ValueError:
            pass
        except Exception as e:
            f.append('S6: gemischte Auflösung endet mit %s' % e.__class__.__name__)
        finally:
            m.socket.getaddrinfo = gai_vorher
        m.feed_url_pruefen = lambda u: '' if str(u).startswith(basis) else echt_pruefen(u)
        m.feed_host_oeffentlich = lambda h: True
        m.feed_adresse_erlaubt = lambda a: True
        daten, etag, _ = m.feed_holen(basis + '/a.xml')
        if daten != RSS or etag != '"v1"':
            f.append('gzip-Feed nicht entpackt oder ETag fehlt')
        if m.feed_holen(basis + '/a.xml', etag='"v1"')[0] is not None or zaehler['304'] != 1:
            f.append('bedingte Anfrage (304) wird nicht genutzt')
        for pfad, wort in [('/bombe', 'entpackt'), ('/gross', 'MB'), ('/fehlt', '404'), ('/umleitung', 'Weiterleitung')]:
            try:
                m.feed_holen(basis + pfad)
                f.append('Abruf %s nicht abgelehnt' % pfad)
            except Exception as e:
                if wort not in m._feed_fehlertext(e):
                    f.append('%s: Fehlertext %r ohne %r' % (pfad, m._feed_fehlertext(e), wort))
        # Gesamtabruf: nur zwei eigene Quellen (eingebaute aus), Doppelte, ETag, Antwort, abgeschaltete Quelle
        m.NACHRICHTEN_QUELLEN[:] = []
        m._QUELLEN_IDS.clear()
        qa = m.eigene_quelle_anlegen({'name': 'A', 'url': basis + '/a.xml', 'land': 'MW'})
        qb = m.eigene_quelle_anlegen({'name': 'B', 'url': basis + '/b.xml', 'land': 'MW'})
        qc = m.eigene_quelle_anlegen({'name': 'C', 'url': basis + '/fehlt', 'land': 'MW'})
        m.nachrichten_aktualisieren()
        d = m.nachrichten_lesen()
        titel = [e['titel'] for e in d['eintraege']]
        if titel.count('Government closes border with Mozambique after clashes') != 1:
            f.append('Doppelte Meldung aus zwei Quellen nicht zusammengefasst: %r' % titel)
        if d['quellen'].get(qc['id'], {}).get('ok') is not False or '404' not in d['quellen'][qc['id']].get('fehler', ''):
            f.append('Fehler einer Quelle nicht vermerkt: %r' % d['quellen'].get(qc['id']))
        if not d['geholt'] or (m.NACHRICHTEN_DATEI.stat().st_mode & 0o777) != 0o600:
            f.append('Speicher ohne Zeitstempel oder nicht 0600')
        gesehen = {e['id']: e['gesehen'] for e in d['eintraege']}
        time.sleep(1.1)
        m.nachrichten_aktualisieren()
        d2 = m.nachrichten_lesen()
        if d2['quellen'][qa['id']].get('unveraendert') is not True:
            f.append('zweiter Abruf nutzt den ETag nicht')
        if any(gesehen.get(e['id']) not in (None, e['gesehen']) for e in d2['eintraege']):
            f.append('„gesehen" ändert sich beim erneuten Abruf (dann wäre alles wieder „neu")')
        a = m.nachrichten_antwort()
        if [t['id'] for t in a['themen']] != m.THEMEN_IDS or a['laender'].get('MW') != 'Malawi' or not a['eintraege']:
            f.append('Antwort ohne Themen/Länder/Meldungen')
        if any(e['link'] and not e['link'].startswith('http') for e in a['eintraege']):
            f.append('Antwort mit nicht-http-Link')
        m.quelle_schalten(qb['id'], False)
        m.quelle_schalten(qa['id'], False)
        if m.nachrichten_antwort()['eintraege']:
            f.append('Meldungen abgeschalteter Quellen werden weiter angezeigt')
        m.quelle_schalten(qa['id'], True)
        # Prüfen ohne Speichern
        p = m.feed_probe({'url': basis + '/a.xml', 'land': 'MW'})
        if not p.get('ok') or p['roh'] != 5 or p['passend'] < 2 or not p['beispiele'] or not p['neuester']:
            f.append('Prüfen liefert %r' % p)
        if m.feed_probe({'url': 'http://192.168.1.1/feed'}).get('ok') is not False:
            f.append('Prüfen holt eine Adresse im eigenen Netz')
        if m.feed_probe({'id': qa['id']}).get('ok') is not True:
            f.append('Prüfen einer vorhandenen Quelle über die Kennung')
        # Offline: drei Verbindungsfehler ohne Erfolg → Abbruch, Speicher bleibt unverändert
        fsrv.shutdown(); fsrv.server_close()
        vorher = m.NACHRICHTEN_DATEI.read_bytes()
        m.FEEDS_DATEI.unlink()
        for i in range(5):
            m.eigene_quelle_anlegen({'name': f'tot{i}', 'url': f'{basis}/tot{i}.xml'})
        t0 = time.time()
        m.nachrichten_aktualisieren()
        if 'offline' not in m.NACHRICHTEN_STATE['meldung'] or m.NACHRICHTEN_DATEI.read_bytes() != vorher:
            f.append('ohne Netz: kein Abbruch oder Speicher verändert (%r)' % m.NACHRICHTEN_STATE['meldung'])
        if time.time() - t0 > 20:
            f.append('Offline-Abbruch dauert zu lange')
    finally:
        m.feed_url_pruefen, m.feed_host_oeffentlich, m.feed_adresse_erlaubt = echt_pruefen, echt_oeffentlich, echt_adresse
        try:
            fsrv.shutdown(); fsrv.server_close()
        except Exception:
            pass

    # 6b. Eine Quelle, die während eines laufenden Abrufs dazukommt, wird gleich danach geholt
    m.NACHRICHTEN_STATE['laeuft'] = True
    if m.nachrichten_anstossen(nur={'eigen-0000000a'}) is not False or 'eigen-0000000a' not in m.NACHRICHTEN_NACHHOLEN:
        f.append('neue Quelle während eines Abrufs nicht vorgemerkt')
    m.nachrichten_aktualisieren(nur={'eigen-0000000b'})
    if m.NACHRICHTEN_NACHHOLEN != {'eigen-0000000a', 'eigen-0000000b'}:
        f.append('Einzelabruf während eines Abrufs nicht vorgemerkt: %r' % m.NACHRICHTEN_NACHHOLEN)
    m.NACHRICHTEN_STATE['laeuft'] = False
    gestartet = []

    class Merker:
        def __init__(self, target=None, kwargs=None, daemon=None):
            gestartet.append((getattr(target, '__name__', ''), kwargs))

        def start(self):
            pass
    echt_thread = m.threading.Thread
    m.threading.Thread = Merker
    try:
        m.nachrichten_aktualisieren(nur={'gibt-es-nicht'})
    finally:
        m.threading.Thread = echt_thread
    if gestartet != [('nachrichten_aktualisieren', {'nur': {'eigen-0000000a', 'eigen-0000000b'}})] or m.NACHRICHTEN_NACHHOLEN:
        f.append('vorgemerkte Quellen werden danach nicht geholt: %r' % gestartet)
    if m.NACHRICHTEN_STATE['laeuft']:
        f.append('Abruf bleibt als laufend markiert')

    # 7. Lesen darf das iPhone, verwalten nur der Mac
    class AusDemWlan(m.SafariHandler):
        def client_ip(self):
            return '192.168.1.50'
    code = m.zugangs_token()
    m.LAN_STATE.update({'an': True, 'weg': 'schnell', 'tls': False, 'ip': '192.168.1.50', 'seit': time.time()})
    srv = m.SafariServer(('127.0.0.1', 0), AusDemWlan, lan=True)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()

    def anfrage(methode, pfad, body=b''):
        s = socket.create_connection(('127.0.0.1', port), timeout=6)
        s.sendall(f'{methode} {pfad} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nX-Safari-Zugang: {code}\r\n'
                  f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n'.encode() + body)
        d = b''
        while True:
            t = s.recv(8192)
            if not t:
                break
            d += t
        s.close()
        return d.decode('utf-8', 'replace').split('\r\n', 1)[0]
    try:
        if ' 200 ' not in anfrage('GET', '/api/nachrichten'):
            f.append('iPhone kann die Nachrichten nicht lesen')
        if ' 403 ' not in anfrage('GET', '/api/nachrichten/quellen'):
            f.append('iPhone sieht die Quellenliste (nur Mac)')
        for pfad in ('/api/nachrichten/aktualisieren', '/api/nachrichten/quelle', '/api/nachrichten/pruefen',
                     '/api/nachrichten/quelle/schalten', '/api/nachrichten/quelle/loeschen'):
            if ' 403 ' not in anfrage('POST', pfad, b'{"name":"x","url":"https://x.example/feed","id":"gdacs"}'):
                f.append('iPhone darf %s (nur Mac)' % pfad)
    finally:
        srv.shutdown(); srv.server_close()
except Exception as e:
    import traceback
    f.append('Abbruch: %s: %s | %s' % (e.__class__.__name__, e, traceback.format_exc().strip().splitlines()[-3:]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
