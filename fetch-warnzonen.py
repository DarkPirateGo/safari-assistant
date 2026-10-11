#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-warnzonen.py v2026-09-15-1
#
# Holt die Grenzen der Gebiete, vor denen das Auswärtige Amt warnt, aus
# OpenStreetMap und schreibt data/warnzonen.geojson. Damit zeigt die Karte
# nicht mehr nur „Land X hat eine Teilreisewarnung", sondern die konkreten
# Gebiete — und der Assistent kann sagen, ob die eigene Position darin liegt.
#
# Zwei Durchgänge, damit Overpass nicht unnötig belastet wird:
#   1. Nur die NAMEN aller Verwaltungsgebiete (admin_level 4 und 6) je Land.
#   2. Die GEOMETRIE ausschließlich für die Gebiete, die im amtlichen Warntext
#      tatsächlich vorkommen.
#
# Kein Raten: Welche Gebiete gemeint sind, entscheidet der Abgleich des
# amtlichen Textes mit diesem Namensverzeichnis (Logik in server.py, dadurch
# identisch zu dem, was die App anzeigt). Was sich nicht zuordnen lässt —
# „das Grenzgebiet zu Eritrea (ca. 10 km)" — wird als ungelöst AUSGEWIESEN und
# bleibt Text. Eine Karte, die Vollständigkeit vortäuscht, wäre gefährlich.
#
# Datenlizenz Flächen: © OpenStreetMap contributors, ODbL.
# Warntexte: Auswärtiges Amt — maßgeblich ist immer der Originaltext.
#
# Nutzung:  im Projektordner: python3 fetch-warnzonen.py
#           (einmalig MIT Internet, nachdem die Reisewarnungen geholt wurden;
#            danach ist die Ebene offline nutzbar)
#           Einzelne Länder:  python3 fetch-warnzonen.py Kenia Mosambik
#
#           python3 fetch-warnzonen.py --vorrat
#           Holt EINMALIG die Verwaltungsgrenzen aller 16 Länder auf Vorrat nach
#           data/verwaltungsgebiete.geojson (beide Ebenen: Provinz/County und
#           Distrikt/Kreis). Danach entstehen Flächen zu NEUEN Warnungen ohne
#           Internet — unterwegs kommt der Warntext über wenige Kilobyte, die
#           Geometrie liegt dann schon da. Läuft lange und ist gegen Abbrüche
#           unempfindlich: bereits geholte Länder werden übersprungen
#           (erzwingen mit --neu). Diese Datei geht NIE ans iPhone — sie wird nur
#           auf dem Mac gelesen; ausgeliefert wird weiterhin nur die kleine
#           warnzonen.geojson mit den tatsächlich gewarnten Gebieten.
#
# Danach:   ./deploy.sh  (kopiert data/warnzonen.geojson ins Bundle)
# ═══════════════════════════════════════════════════════════════════
import json, sys, time, importlib.util, urllib.request, urllib.parse, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'data' / 'warnzonen.geojson'
VORRAT_DATEI = BASE / 'data' / 'verwaltungsgebiete.geojson'
WARNUNGEN = Path.home() / '.safari-assistant-reisewarnungen.json'
MIRRORS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
KOPF = {'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-warnzonen'}
EBENEN = (4, 6)
# Verwaltungs-Zusätze, die das Auswärtige Amt weglässt: OSM schreibt „Mandera County",
# der Warntext „die Countys Mandera". Beide Schreibweisen kommen ins Verzeichnis.
ZUSAETZE = ['County', 'Province', 'Região', 'Regiao', 'Region', 'Provincia', 'Província', 'Distrito',
            'District', 'Zone', 'Prefecture', 'Governorate', 'Sub-County', 'Municipality',
            'Provinz', 'Regionalstaat', 'Bundesstaat', 'Distrikt', 'Bezirk', 'Verwaltungszone']


# Die Aufrufparameter MÜSSEN hier gesichert werden: lade_modul setzt sys.argv gleich um, damit die
# geladenen Module unsere Argumente nicht für ihre eigenen halten. Ohne diese Kopie kam „--vorrat"
# nie in main() an — das Skript lief dann stumm im Normalmodus weiter (Fehler vom 15.09.2026).
ARGUMENTE = list(sys.argv[1:])


def lade_modul(pfad, name):
    spec = importlib.util.spec_from_file_location(name, pfad)
    m = importlib.util.module_from_spec(spec)
    merk = sys.argv
    sys.argv = [name]
    try:
        spec.loader.exec_module(m)
    finally:
        sys.argv = merk
    return m


SRV = lade_modul(BASE / 'server.py', 'srv')          # Textlogik: identisch mit der App
PARKS = lade_modul(BASE / 'fetch-parks.py', 'parks')  # Geometrie-Helfer: bewährt, nicht doppeln


def overpass(abfrage, timeout=360):
    body = urllib.parse.urlencode({'data': abfrage}).encode()
    letzte = None
    for versuch in range(4):
        for url in MIRRORS:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=KOPF), timeout=timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                letzte = e
                if e.code in (429, 504):
                    warte = int(e.headers.get('Retry-After') or 0) or 30
                    print(f'   ⚠️  {url.split("/")[2]}: HTTP {e.code} — warte {warte}s …')
                    time.sleep(warte)
                else:
                    print(f'   ⚠️  {url.split("/")[2]}: {e} — nächster Mirror …')
            except Exception as e:
                letzte = e
                print(f'   ⚠️  {url.split("/")[2]}: {e.__class__.__name__} — nächster Mirror …')
        time.sleep(10 * (versuch + 1))
    raise SystemExit(f'❌ Overpass nicht erreichbar: {letzte}')


def namen_abfrage(cc):
    ebenen = '|'.join(str(e) for e in EBENEN)
    return f'''[out:json][timeout:180];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
relation["boundary"="administrative"]["admin_level"~"^({ebenen})$"](area.a);
out tags;'''


def geometrie_abfrage(ids):
    # „out geom;" (Vorgabe: body) liefert Mitglieder MIT Geometrie. Mit „out geom tags;" kämen die
    # Relationen ohne Mitglieder zurück — und damit ohne jede Fläche. Genau daran scheiterte der
    # erste Lauf am 15.09.2026: 12 Gebiete erkannt, 0 Flächen gebaut.
    return f'''[out:json][timeout:300];
relation(id:{",".join(str(i) for i in ids)});
out geom;'''


def suchnamen(tags):
    """Alle Schreibweisen, unter denen ein Gebiet im deutschen Warntext stehen kann."""
    namen = []
    for schluessel in ('name:de', 'name', 'name:en', 'int_name', 'alt_name'):
        wert = (tags.get(schluessel) or '').strip()
        if not wert or wert in namen:
            continue
        namen.append(wert)
        for zusatz in ZUSAETZE:                      # „Mandera County" → auch „Mandera"
            for form in (f' {zusatz}', f'{zusatz} '):
                if wert.lower().startswith(form.strip().lower() + ' ') or wert.lower().endswith(form.rstrip().lower()):
                    kurz = wert[:-len(zusatz)].strip(' -') if wert.lower().endswith(zusatz.lower()) else wert[len(zusatz):].strip(' -')
                    if len(kurz) >= 3 and kurz not in namen:
                        namen.append(kurz)
    return namen


def verzeichnis(cc):
    """{Suchname: {'id':…, 'ebene':…, 'osm_name':…}} für ein Land."""
    daten = overpass(namen_abfrage(cc), timeout=200)
    eintraege = {}
    for el in daten.get('elements', []):
        tags = el.get('tags') or {}
        try:
            ebene = int(tags.get('admin_level') or 0)
        except ValueError:
            continue
        if ebene not in EBENEN:
            continue
        for name in suchnamen(tags):
            vorher = eintraege.get(name)
            # Bei gleichem Namen gewinnt die gröbere Ebene (Provinz vor gleichnamigem Distrikt);
            # die feinere bleibt über ihren vollen OSM-Namen erreichbar.
            if vorher is None or ebene < vorher['ebene']:
                eintraege[name] = {'id': el['id'], 'ebene': ebene,
                                   'osm_name': tags.get('name') or name}
    return eintraege


def vorrat_lesen():
    """{Land: {Suchname: {id, ebene, osm_name, ringe}}} — die lokal vorliegenden Verwaltungsgrenzen."""
    try:
        d = json.loads(VORRAT_DATEI.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    nach_land = {}
    for f in d.get('features') or []:
        p = f.get('properties') or {}
        land = p.get('land')
        if not land:
            continue
        eintrag = {'id': p.get('osm_id'), 'ebene': int(p.get('ebene') or 0),
                   'osm_name': p.get('osm_name') or '', 'geometry': f.get('geometry')}
        ziel = nach_land.setdefault(land, {})
        for name in (p.get('suchnamen') or []):
            vorher = ziel.get(name)
            if vorher is None or eintrag['ebene'] < vorher['ebene']:
                ziel[name] = eintrag
    return nach_land


def vorrat_abfrage(cc, ebene):
    return f"""[out:json][timeout:600];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
relation["boundary"="administrative"]["admin_level"="{ebene}"](area.a);
out geom;"""


def vorrat_holen(laender, neu_holen=False):
    """Verwaltungsgrenzen aller Länder auf Vorrat. Schreibt nach jedem Land, damit ein Abbruch
    (Overpass drosselt gern) nichts von der bisherigen Arbeit kostet."""
    vorhanden = {}
    if VORRAT_DATEI.exists():
        try:
            vorhanden = json.loads(VORRAT_DATEI.read_text(encoding='utf-8'))
        except ValueError:
            vorhanden = {}
    features = list(vorhanden.get('features') or [])
    fertig = set(vorhanden.get('fertig') or [])
    for land in laender:
        if land['name'] in fertig and not neu_holen:
            print(f'· {land["name"]}: schon im Vorrat — übersprungen (--neu erzwingt)')
            continue
        features = [f for f in features if (f.get('properties') or {}).get('land') != land['name']]
        gesamt = 0
        for ebene in EBENEN:
            print(f'▶ {land["name"]} ({land["aa"]}) — Ebene {ebene} …')
            try:
                daten = overpass(vorrat_abfrage(land['aa'], ebene), timeout=600)
            except SystemExit:
                print(f'   ⚠️  Ebene {ebene} nicht abrufbar — Land bleibt unvollständig, später erneut versuchen')
                break
            neu_f = 0
            for el in daten.get('elements', []):
                if el.get('type') != 'relation':
                    continue
                tags = el.get('tags') or {}
                namen = suchnamen(tags)
                if not namen:
                    continue
                segmente = [[(g['lon'], g['lat']) for g in glied.get('geometry', [])]
                            for glied in el.get('members', [])
                            if glied.get('type') == 'way' and glied.get('role') in ('outer', '') and glied.get('geometry')]
                ringe = PARKS.ringe_zusammensetzen(segmente)
                polygone = PARKS.gebiet_vereinfachen(ringe) if ringe else []
                if not polygone:
                    continue
                features.append({
                    'type': 'Feature',
                    'properties': {'land': land['name'], 'osm_name': tags.get('name') or namen[0],
                                   'ebene': ebene, 'osm_id': el['id'], 'suchnamen': namen},
                    'geometry': {'type': 'MultiPolygon', 'coordinates': [[r] for r in polygone]},
                })
                neu_f += 1
            gesamt += neu_f
            print(f'   ✅ Ebene {ebene}: {neu_f} Gebiete')
            time.sleep(5)     # Overpass ist ein ehrenamtlicher Dienst — nicht hetzen
        else:
            fertig.add(land['name'])
        VORRAT_DATEI.parent.mkdir(exist_ok=True)
        VORRAT_DATEI.write_text(json.dumps({
            'type': 'FeatureCollection', 'erzeugt': time.strftime('%Y-%m-%d %H:%M'),
            'quelle': '© OpenStreetMap contributors, ODbL 1.0 https://opendatacommons.org/licenses/odbl/1-0/',
            'hinweis': 'Verwaltungsgrenzen auf Vorrat — nur lokal genutzt, wird nicht ans iPhone ausgeliefert.',
            'fertig': sorted(fertig), 'features': features}, ensure_ascii=False), encoding='utf-8')
        print(f'   📁 Zwischenstand gesichert: {len(features)} Gebiete, {VORRAT_DATEI.stat().st_size // 1024} KB')
    print(f'\n📁 {VORRAT_DATEI} — {len(features)} Gebiete aus {len(fertig)} Ländern, '
          f'{VORRAT_DATEI.stat().st_size // 1024} KB')
    offen = [l['name'] for l in laender if l['name'] not in fertig]
    if offen:
        print('⚠️  Unvollständig geblieben (später erneut aufrufen): ' + ', '.join(offen))


def features_bauen(daten, land, zuordnung, stand):
    features = []
    for el in daten.get('elements', []):
        if el.get('type') != 'relation':
            continue
        info = zuordnung.get(el['id'])
        if not info:
            continue
        segmente = [[(g['lon'], g['lat']) for g in glied.get('geometry', [])]
                    for glied in el.get('members', [])
                    if glied.get('type') == 'way' and glied.get('role') in ('outer', '') and glied.get('geometry')]
        ringe = PARKS.ringe_zusammensetzen(segmente)
        if not ringe:
            grund = ('Antwort enthält keine Mitglieder — Abfrage liefert keine Geometrie'
                     if not el.get('members') else 'keine geschlossene Fläche in OSM')
            print(f'   ⚠️  {land}/{info["name"]}: {grund} — bleibt Text')
            continue
        polygone = PARKS.gebiet_vereinfachen(ringe)
        if not polygone:
            continue
        features.append({
            'type': 'Feature',
            'properties': {
                'land': land, 'name': info['name'], 'osm_name': info['osm_name'], 'ebene': info['ebene'],
                'stufe': info['stufe'], 'stufe_text': info['stufe_text'], 'satz': info['satz'],
                'einschraenkung': bool(info['einschraenkung']), 'stand': stand, 'osm_id': el['id'],
            },
            'geometry': {'type': 'MultiPolygon', 'coordinates': [[r] for r in polygone]},
        })
    return features


def main():
    nur_alle = [a for a in ARGUMENTE if not a.startswith('-')]
    unbekannt = [a for a in ARGUMENTE if a.startswith('-') and a not in ('--vorrat', '--neu')]
    if unbekannt:
        raise SystemExit(f'❌ Unbekannte Option: {" ".join(unbekannt)}\n'
                         f'   Bekannt sind: --vorrat (Verwaltungsgrenzen auf Vorrat holen) und '
                         f'--neu (bereits geholte Länder erneut holen).')
    if '--vorrat' in ARGUMENTE:
        laender = [l for l in SRV.REISEWARN_LAENDER if not nur_alle or l['name'] in nur_alle]
        print(f'📦 Vorrat: Verwaltungsgrenzen für {len(laender)} Länder (beide Ebenen). '
              f'Das dauert; ein Abbruch ist unkritisch, bereits geholte Länder werden übersprungen.')
        vorrat_holen(laender, neu_holen='--neu' in ARGUMENTE)
        return
    if not WARNUNGEN.exists():
        raise SystemExit('❌ Noch keine Reisewarnungen geholt. Erst den Assistenten starten und im '
                         'Panel „Reisewarnungen" → „Jetzt holen" (oder kurz warten, er holt sie selbst).')
    daten = json.loads(WARNUNGEN.read_text(encoding='utf-8'))
    laender_daten = daten.get('laender') or {}
    nur = nur_alle
    laender = [l for l in SRV.REISEWARN_LAENDER if not nur or l['name'] in nur]

    # Ein Lauf für einzelne Länder darf die übrigen NICHT löschen — bisher hätte
    # „fetch-warnzonen.py Kenia" alle anderen Flächen aus der Datei geworfen.
    vorrat = vorrat_lesen()
    if vorrat:
        print(f'· Vorrat: {sum(len(v) for v in vorrat.values())} Namen aus {len(vorrat)} Ländern '
              f'({VORRAT_DATEI.name}) — Flächen kommen wenn möglich von dort')
    alt_daten = {}
    if OUT.exists():
        try:
            alt_daten = json.loads(OUT.read_text(encoding='utf-8'))
        except ValueError:
            alt_daten = {}
    behalten = [f for f in (alt_daten.get('features') or [])
                if nur and (f.get('properties') or {}).get('land') not in nur]
    features = list(behalten)
    meta_unaufgeloest = {k: v for k, v in (alt_daten.get('unaufgeloest') or {}).items() if not nur or k not in nur}
    meta_nicht_gefunden = {k: v for k, v in (alt_daten.get('nicht_gefunden') or {}).items() if not nur or k not in nur}
    staende = {k: v for k, v in (alt_daten.get('staende') or {}).items() if not nur or k not in nur}
    if behalten:
        print(f'· {len(behalten)} Flächen anderer Länder aus der bestehenden Datei übernommen')
    for land in laender:
        eintrag = (laender_daten.get(land['name']) or {}).get('aa') or {}
        text = eintrag.get('warntext') or ''
        kennzeichen = eintrag.get('kennzeichen') or {}
        stand = eintrag.get('stand') or eintrag.get('geaendert') or ''
        if not text or not any(kennzeichen.values()):
            # Ohne Warnung gibt es nichts zu holen — das gilt als erledigt.
            staende[land['name']] = stand
            print(f'· {land["name"]}: keine Warnung im gespeicherten Stand — übersprungen')
            continue
        print(f'▶ {land["name"]} ({land["aa"]}) — Verwaltungsgebiete …')
        # Erst den lokalen Vorrat: dann braucht dieser Lauf gar kein Internet. Nur wenn dort für
        # dieses Land nichts liegt, wird Overpass gefragt.
        aus_vorrat = vorrat.get(land['name']) or {}
        if aus_vorrat:
            verz = aus_vorrat
            print(f'   {len(verz)} Namen aus dem lokalen Vorrat (kein Internet nötig)')
        else:
            verz = verzeichnis(land['aa'])
            print(f'   {len(verz)} Namen über Overpass')
        gebiete, ausgenommen, offen = SRV.warngebiete_aus_text(
            text, {name: info['ebene'] for name, info in verz.items()})
        if offen:
            meta_unaufgeloest[land['name']] = offen
        if not gebiete:
            staende[land['name']] = stand   # nichts zuzuordnen: erledigt, kein ewiges Nachziehen
            print(f'   ⚠️  kein Gebiet zugeordnet — der Warntext bleibt vollständig als Text sichtbar')
            continue
        zuordnung, fehlt = {}, []
        for g in gebiete:
            info = verz.get(g['name'])
            if not info:
                fehlt.append(g['name'])
                continue
            zuordnung[info['id']] = dict(g, osm_name=info['osm_name'], ebene=info['ebene'])
        if fehlt:
            meta_nicht_gefunden[land['name']] = fehlt
        print(f'   {len(zuordnung)} Gebiete: ' + ', '.join(f'{g["name"]}({g["stufe"]})' for g in gebiete))
        if ausgenommen:
            print(f'   ausgenommen laut Text: {", ".join(ausgenommen)}')
        if offen:
            print(f'   ⚠️  ohne Fläche (bleibt Text): ' + ' | '.join(u['satz'][:60] for u in offen))
        if not zuordnung:
            continue
        gebaut, offen_ids = [], {}
        for osm_id, info in zuordnung.items():
            lager = aus_vorrat.get(info['name'])
            if lager and lager.get('geometry') and lager.get('id') == osm_id:
                gebaut.append({'type': 'Feature',
                               'properties': {'land': land['name'], 'name': info['name'],
                                              'osm_name': info['osm_name'], 'ebene': info['ebene'],
                                              'stufe': info['stufe'], 'stufe_text': info['stufe_text'],
                                              'satz': info['satz'], 'einschraenkung': bool(info['einschraenkung']),
                                              'stand': stand, 'osm_id': osm_id, 'quelle': 'vorrat'},
                               'geometry': lager['geometry']})
            else:
                offen_ids[osm_id] = info
        if gebaut:
            print(f'   {len(gebaut)} Flächen aus dem Vorrat')
        if offen_ids:
            geo = overpass(geometrie_abfrage(list(offen_ids)))
            gebaut += features_bauen(geo, land['name'], offen_ids, stand)
        features += gebaut
        if gebaut:
            staende[land['name']] = stand   # nur ein geglückter Lauf zählt als erledigt
            print(f'   ✅ {len(gebaut)} Flächen')
        else:
            print(f'   ❌ 0 Flächen — Stand NICHT vermerkt, der nächste Lauf versucht es erneut')
        time.sleep(2)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        'type': 'FeatureCollection',
        'erzeugt': time.strftime('%Y-%m-%d %H:%M'),
        'quelle_flaechen': '© OpenStreetMap contributors, ODbL 1.0 https://opendatacommons.org/licenses/odbl/1-0/',
        'quelle_warnung': 'Auswärtiges Amt — maßgeblich ist der Originaltext',
        'unaufgeloest': meta_unaufgeloest,
        'nicht_gefunden': meta_nicht_gefunden,
        'staende': staende,
        'features': features,
    }, ensure_ascii=False), encoding='utf-8')
    print(f'\n📁 {OUT} — {len(features)} Flächen, {OUT.stat().st_size // 1024} KB')
    if meta_unaufgeloest:
        print('ℹ️  Ohne Fläche geblieben (in der App als Text sichtbar): '
              + ', '.join(f'{l} ({len(v)})' for l, v in meta_unaufgeloest.items()))
    if meta_nicht_gefunden:
        print('⚠️  Im OSM-Verzeichnis nicht gefunden: '
              + '; '.join(f'{l}: {", ".join(v)}' for l, v in meta_nicht_gefunden.items()))
    print('Danach: ./deploy.sh')


if __name__ == '__main__':
    main()
