# Fixture-Test der Reisewarnungs-Pipeline. Die Antworten sind den WÖRTLICH geprüften Antworten der
# drei amtlichen Quellen nachgebaut (13.09.2026) — echte Abrufe gehören nicht in eine Testsuite.
# Wird von test-app.js (Sektion 57) mit python3 ausgeführt.
import sys, json, importlib.util, time
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location('srv', SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []

# Fixtures: nachgebaut aus den WÖRTLICH geprüften Antworten der drei Quellen (13.09.2026).
AA_LISTE = {"response": {
    "lastModified": 1757063288,
    "208058": {"lastModified": 1787659756, "effective": 1787659200, "title": "Kenia: Reise- und Sicherheitshinweise",
               "countryCode": "KE", "iso3CountryCode": "KEN", "countryName": "Kenia",
               "warning": False, "partialWarning": True, "situationWarning": False, "situationPartWarning": False},
    "221782": {"lastModified": 1776425407, "effective": 1776416400, "title": "Mosambik: Reise- und Sicherheitshinweise",
               "countryCode": "MZ", "iso3CountryCode": "MOZ", "countryName": "Mosambik",
               "warning": False, "partialWarning": True, "situationWarning": False, "situationPartWarning": False},
    "208314": {"lastModified": 1770000000, "effective": 1769990000, "title": "Namibia: Reise- und Sicherheitshinweise",
               "countryCode": "NA", "iso3CountryCode": "NAM", "countryName": "Namibia",
               "warning": False, "partialWarning": False, "situationWarning": False, "situationPartWarning": False},
    "999999": {"lastModified": 1, "effective": 1, "title": "Irgendwo", "countryCode": "XX", "iso3CountryCode": "XXX",
               "countryName": "Irgendwo", "warning": True, "partialWarning": False,
               "situationWarning": False, "situationPartWarning": False},
    "contentList": ["208058", "221782", "208314", "999999"]}}
AA_KENIA = {"response": {"208058": {
    "countryName": "Kenia", "title": "Kenia: Reise- und Sicherheitshinweise",
    "lastChanges": "Letzte Änderungen: <br><span>Redaktionelle Änderungen</span>",
    "content": ('<div><blockquote class="info-box"><p><strong>Lagen können sich schnell verändern'
                '</strong></p></blockquote><h2>Sicherheit</h2>'
                '<p><strong>Vor Reisen in die Countys Mandera, Wajir, Garissa und Lamu im Osten Kenias wird gewarnt.</strong></p>'
                '<p><strong>Von Reisen in die Countys Baringo, West Pokot und Turkana wird dringend abgeraten.</strong></p>'
                '<p><strong>Von nicht notwendigen Reisen nach Lamu Island und Manda Island wird abgeraten.</strong></p>'
                '<h3>Terrorismus</h3><p>Text zum Terrorismus, gehört nicht in den Warnblock.</p>'),
    "disclaimer": "<div>Haftungsausschluss</div>"}}}
AA_MOSAMBIK = {"response": {"221782": {
    "countryName": "Mosambik", "title": "Mosambik: Reise- und Sicherheitshinweise",
    "lastChanges": "Letzte Änderungen: <br><span>Aktuelles</span>",
    "content": ('<div><blockquote class="info-box"><p>Vorspann</p></blockquote>'
                '<h2>Aktuelles</h2><p>In Mosambik ist die Lage nach den Überschwemmungen kritisch.</p>'
                '<h2>Sicherheit - Teilreisewarnung</h2><p>Siehe <em>Aktuelles</em></p>'
                '<p><strong>Vor Reisen in die</strong></p>'
                '<ul class="rte__unordered-list--bullet-hyphen rte--list">'
                '<li><strong>Provinz Cabo Delgado, in alle Distrikte, </strong>außer Pemba,</li>'
                '<li><strong>Provinz Nampula, in die Distrikte Memba und Erati,</strong></li></ul>'
                '<p><strong>wird gewarnt.</strong></p><h3>Terrorismus</h3><p>Nicht im Warnblock.</p>')}}}
AA_NAMIBIA = {"response": {"208314": {"countryName": "Namibia", "title": "Namibia: Reise- und Sicherheitshinweise",
    "content": '<div><h2>Sicherheit</h2><p>Landesweit besteht ein erhöhtes Risiko der Kriminalität.</p><h3>Kriminalität</h3><p>X</p>'}}}
FCDO_KENIA = {"base_path": "/foreign-travel-advice/kenya", "public_updated_at": "2026-09-04T14:12:11Z",
    "details": {"alert_status": ["avoid_all_travel_to_parts", "avoid_all_but_essential_travel_to_parts"],
                "change_description": "Removed information about industrial action.",
                "parts": [{"slug": "warnings-and-insurance", "title": "Warnings and insurance  ",
                           "body": ('<div role="note"><p>Insurance note</p></div>\n'
                                    '<h2 id="areas-where-fcdo-advises-against-travel">Areas where '
                                    '<abbr title="Foreign, Commonwealth &amp; Development Office">FCDO</abbr> advises against travel</h2>\n'
                                    '<p>FCDO advises against all travel to:</p>\n<ul>\n<li>Mandera County</li>\n'
                                    '<li>Lamu County, except for Lamu Island and Manda Island</li>\n</ul>\n'
                                    '<h2 id="before-you-travel">Before you travel</h2>\n<p>Nicht mehr im Gebietsblock.</p>')},
                          {"slug": "safety-and-security", "title": "Safety and security", "body": "<p>egal</p>"}]}}
FCDO_LESOTHO = {"public_updated_at": "2025-12-10T13:12:05+00:00",
    "details": {"alert_status": [], "change_description": "New information about dual nationals.",
                "parts": [{"slug": "warnings-and-insurance", "title": "Warnings and insurance  ",
                           "body": '\n<h2 id="before-you-travel">Before you travel</h2>\n<p>No travel can be guaranteed safe.</p>'}]}}
FCDO_NEU = {"public_updated_at": "2026-01-01T00:00:00Z",
            "details": {"alert_status": ["brandneue_stufe_2027"], "parts": []}}
USA_RSS = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
           '<title>travel.state.gov: Travel Advisories</title>'
           '<item><title>Ethiopia - Level 3: Reconsider Travel</title>'
           '<link>https://travel.state.gov/ethiopia.html</link><pubDate>Thu, 27 Aug 2026</pubDate>'
           '<description><![CDATA[Reconsider travel to <b>Ethiopia</b>.]]></description>'
           '<category domain="Threat-Level">Level 3: Reconsider Travel</category>'
           '<category domain="Country-Tag">ET</category></item>'
           '<item><title>Mainland China, Hong Kong &amp; Macau - See Summaries - Level 3: Reconsider Travel</title>'
           '<link>https://travel.state.gov/china.html</link><pubDate>Wed, 09 Sep 2026</pubDate>'
           '<category domain="Threat-Level">Level 3: Reconsider Travel</category></item>'
           '</channel></rss>')

ANTWORTEN = {m.AA_LISTE_URL: json.dumps(AA_LISTE),
             m.AA_DETAIL_URL.format(id='208058'): json.dumps(AA_KENIA),
             m.AA_DETAIL_URL.format(id='221782'): json.dumps(AA_MOSAMBIK),
             m.AA_DETAIL_URL.format(id='208314'): json.dumps(AA_NAMIBIA),
             m.FCDO_URL.format(slug='kenya'): json.dumps(FCDO_KENIA),
             m.FCDO_URL.format(slug='lesotho'): json.dumps(FCDO_LESOTHO),
             m.FCDO_URL.format(slug='botswana'): json.dumps(FCDO_NEU),
             m.USA_RSS_URL: USA_RSS}

def hole(url, timeout=20, max_bytes=0, roh=False):
    if url not in ANTWORTEN:
        raise OSError('kein Netz für ' + url)
    return ANTWORTEN[url]
m._hole = hole
m._erreichbar = lambda url, timeout=8: '/kenia-node/' in url   # nur Kenia hat eine geprüfte Seite

LAENDER = [l for l in m.REISEWARN_LAENDER if l['name'] in ('Kenia', 'Mosambik', 'Namibia', 'Lesotho', 'Botswana')]

# 1. AA: Stufen aus den Kennzeichen, nicht aus dem Text
aa, fehlend = m.aa_abrufen(LAENDER)
if aa['Kenia']['stufe'] != 'Teilreisewarnung': f.append('AA Stufe Kenia: ' + aa['Kenia']['stufe'])
if aa['Namibia']['stufe'] != 'Reise- und Sicherheitshinweise (keine Warnung)': f.append('AA Stufe Namibia')
if m.aa_stufe({'warning': True, 'partialWarning': True}) != 'Reisewarnung': f.append('AA Stufe Vorrang')
if m.aa_stufe({'situationPartWarning': True}) != 'Situationsbedingte Teilreisewarnung': f.append('AA Stufe situativ')
# 2. Warnblock endet vor <h3>, Text bleibt wörtlich
k = aa['Kenia']['warntext']
if 'Mandera, Wajir, Garissa und Lamu' not in k: f.append('Kenia Warntext fehlt: ' + k[:80])
if 'Terrorismus' in k: f.append('Kenia Warnblock reicht über <h3> hinaus')
if 'Manda Island wird abgeraten.' not in k: f.append('Kenia dritter Satz fehlt')
# 3. Überschriftenvariante "Sicherheit - Teilreisewarnung" + Liste + getrennter Satz
mo = aa['Mosambik']['warntext']
if 'Vor Reisen in die' not in mo or 'wird gewarnt.' not in mo: f.append('Mosambik Warnblock: ' + mo[:120])
if '• Provinz Cabo Delgado' not in mo: f.append('Mosambik Liste nicht als Punkte: ' + mo[:160])
if 'Nicht im Warnblock' in mo: f.append('Mosambik Warnblock zu lang')
if 'Überschwemmungen' not in aa['Mosambik']['aktuelles']: f.append('Mosambik Aktuelles fehlt')
if 'Überschwemmungen' in mo: f.append('Aktuelles ist in den Warnblock gerutscht')
# 4. Stand-Datum aus den Zeitstempeln, Link nur wenn geprüft
if aa['Kenia']['stand'] != m._datum(1787659200): f.append('Kenia Stand: ' + aa['Kenia']['stand'])
if not aa['Kenia']['url'].endswith('/kenia-node/keniasicherheit/208058'): f.append('Kenia URL: ' + aa['Kenia']['url'])
if aa['Mosambik']['url'] != '': f.append('ungeprüfte URL gespeichert: ' + aa['Mosambik']['url'])
# 5. Länder ohne Detail/ohne Eintrag werden gemeldet, nicht erfunden
if 'Lesotho' in aa or 'Botswana' in aa: f.append('Land ohne AA-Eintrag erfunden')
if 'Lesotho' not in fehlend or 'Botswana' not in fehlend: f.append('fehlende Länder nicht gemeldet: ' + fehlend)
# 5b. Zweiter Abruf ohne Änderung am Zeitstempel holt KEIN Detail mehr (Datenvolumen unterwegs)
geholt = []
orig_hole = m._hole
def zaehle(url, timeout=20, max_bytes=0, roh=False):
    geholt.append(url)
    return orig_hole(url, timeout, max_bytes, roh)
m._hole = zaehle
aa2, _ = m.aa_abrufen(LAENDER, {k: {'aa': v} for k, v in aa.items()})
if any('/travelwarning/' in u for u in geholt): f.append('Detail trotz unveränderter lastModified geholt')
if aa2['Kenia']['warntext'] != aa['Kenia']['warntext']: f.append('zwischengespeicherter Warntext ging verloren')
if not aa2['Kenia'].get('geprueft'): f.append('Prüfzeitpunkt fehlt beim Wiederverwenden')
geholt.clear()
veraltet = {k: {'aa': dict(v, geaendert='2000-01-01')} for k, v in aa.items()}
m.aa_abrufen(LAENDER, veraltet)
if not any('/travelwarning/208058' in u for u in geholt): f.append('geänderter Stand holt kein Detail nach')
m._hole = orig_hole

# 6. FCDO: bekannte Codes übersetzt, unbekannte unverändert, Gebietsblock endet vor dem nächsten <h2>
fc, fcf = m.fcdo_abrufen(LAENDER)
if 'Von allen Reisen in Teile' not in fc['Kenia']['stufe']: f.append('FCDO Stufe: ' + fc['Kenia']['stufe'])
if 'Mandera County' not in fc['Kenia']['gebiete']: f.append('FCDO Gebiete: ' + fc['Kenia']['gebiete'][:100])
if 'Nicht mehr im Gebietsblock' in fc['Kenia']['gebiete']: f.append('FCDO Gebietsblock zu lang')
if 'FCDO advises against all travel to' not in fc['Kenia']['gebiete']: f.append('FCDO abbr nicht aufgelöst')
if fc['Lesotho']['codes'] != [] or 'Keine Reisewarnung' not in fc['Lesotho']['stufe']: f.append('FCDO leer')
if fc['Botswana']['stufe'] != 'brandneue_stufe_2027': f.append('FCDO unbekannte Stufe verschluckt: ' + fc['Botswana']['stufe'])
if fc['Kenia']['stand'] != '2026-09-04': f.append('FCDO Stand: ' + fc['Kenia']['stand'])
if 'Mosambik' in fc or 'Namibia' not in fcf: f.append('FCDO Fehlerliste: ' + fcf)
try:
    m.fcdo_abrufen([l for l in m.REISEWARN_LAENDER if l['name'] == 'Mosambik'])
    f.append('FCDO ohne jedes Land meldet keinen Fehler')
except OSError:
    pass
# 7. USA: RSS-Auswertung, Länder ohne Eintrag fehlen einfach
us, ush = m.usa_abrufen([l for l in m.REISEWARN_LAENDER if l['name'] in ('Äthiopien', 'Kenia')])
if us.get('Äthiopien', {}).get('stufe') != 'Level 3: Reconsider Travel': f.append('USA Stufe: ' + str(us))
if us['Äthiopien']['stand'] != 'Thu, 27 Aug 2026': f.append('USA Datum')
if 'Kenia' in us: f.append('USA Land erfunden, das nicht im Feed steht')
if '1 von 2' not in ush: f.append('USA Hinweis: ' + ush)
# 8. html_zu_text kürzt nicht und lässt keine Tags stehen
t = m.html_zu_text('<p>Erste Zeile</p><ul><li>A &amp; B</li><li>C</li></ul><p>Ende</p>')
if t != 'Erste Zeile\n• A & B\n• C\nEnde': f.append('html_zu_text: ' + repr(t))
if '<' in m.html_zu_text('<script>alert(1)</script><p>ok</p>'): f.append('script nicht entfernt')

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
