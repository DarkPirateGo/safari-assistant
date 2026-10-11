#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-parks.py v2026-09-16-1
#   (Schutzklassen IV und VI dazu: Masai Mara und Ngorongoro fehlten sonst)
#
# Holt echte Park-/Schutzgebietsgrenzen (Nationalparks + protect_class 1/2)
# für die 16 Reiseländer aus OpenStreetMap (Overpass-API), vereinfacht die
# Polygone (Bug-11-Lektion: NIE tausende Roh-Punkte in die Karte) und
# schreibt data/parks.geojson für das Gefahren-Overlay der POI-Karte.
#
# Lizenz der Daten: © OpenStreetMap contributors, ODbL — Attribution steht
# in der Ausgabedatei und im Karten-Popup. (IUCN/WDPA bewusst NICHT genutzt:
# keine Weiterverbreitung erlaubt — siehe TODO/Recherche 16.07.)
#
# FEHLER VOM 15.09.2026 (hier behoben): Die Abfrage endete auf „out geom tags;".
# „tags" ist eine Ausführlichkeitsstufe und liefert Relationen OHNE Mitglieder, also
# ohne Geometrie. Weil große Schutzgebiete in OSM fast immer Relationen sind, fielen
# sie stillschweigend heraus: Die Datei enthielt 132 Gebiete, davon 132 aus Wegen und
# kein einziges aus einer Relation — es fehlten u. a. Serengeti, Ngorongoro, Etosha,
# Kruger, Okavango/Moremi, Hwange, Masai Mara, Amboseli, Tsavo, Kafue, South Luangwa,
# Namib, Bwindi, Murchison, Simien, Gorongosa, Nyerere/Selous, Ruaha, Mana Pools.
# Richtig ist „out geom;" (Vorgabestufe „body" + Geometrie): Tags UND Mitglieder.
# Damit so etwas nie wieder unbemerkt bleibt, meldet der Lauf jetzt ausdrücklich,
# wie viele Gebiete aus Relationen stammen und welche ohne Mitglieder ankamen.
#
# Nutzung:  im Projektordner: python3 fetch-parks.py
#           (einmalig MIT Internet; danach ist der Layer offline nutzbar)
#           Einzelne Länder erneut:  python3 fetch-parks.py NA BW
#
#           python3 fetch-parks.py --tags Ngorongoro
#           Fragt Overpass nach allen Gebieten, deren Name das Muster enthält, und zeigt ihre
#           Tags — samt Urteil, ob die Abfrage oben sie erfassen würde und warum nicht. Damit ist
#           „warum fehlt X auf der Karte?" eine Frage von zehn Sekunden statt von Mutmaßungen.
#           Der Lauf sichert nach JEDEM Land — ein Abbruch ist unkritisch, und ein
#           fehlgeschlagenes Land behält seinen bisherigen Stand (nie Daten löschen).
#
# Danach:   ./deploy.sh  (kopiert data/parks.geojson ins Bundle)
# ═══════════════════════════════════════════════════════════════════
import json, math, sys, time, urllib.request, urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'data' / 'parks.geojson'
# Wie in fetch-warnzonen.py: die Aufrufparameter sichern, bevor irgendein Modul sys.argv umsetzt.
ARGUMENTE = list(sys.argv[1:])

# Ländernamen EXAKT wie in GEFAHREN_REGIONAL/LAENDER_GEO (Single Source of Truth der Texte)
LAENDER = [
    ('ZA', 'Südafrika'), ('NA', 'Namibia'), ('BW', 'Botswana'), ('ZM', 'Sambia'),
    ('ZW', 'Zimbabwe'), ('MZ', 'Mosambik'), ('MW', 'Malawi'), ('TZ', 'Tansania'),
    ('KE', 'Kenia'), ('UG', 'Uganda'), ('RW', 'Ruanda'), ('BI', 'Burundi'),
    ('ET', 'Äthiopien'), ('AO', 'Angola'), ('SZ', 'Eswatini'), ('LS', 'Lesotho'),
]

MIRRORS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
]

# Vereinfachung: Start-Toleranz ~440 m; wird pro Gebiet verdoppelt, bis es kompakt ist
EPS_START = 0.004
MAX_PUNKTE_PRO_GEBIET = 600
MIN_RING_FLAECHE = 5e-5  # ~0.6 km² — Splitter raus, kleine echte Reservate (z. B. Mkhaya) bleiben

# Für die 2026-09-16 hinzugekommenen Klassen IV und VI gilt eine höhere Mindestgröße. Grund: Unter
# ihnen stehen in Kenia 163 Gebiete, von der 10 555 km² großen Shurr Community Conservancy bis zur
# 0,8 km² kleinen Silole Conservancy. Auf einer Überlandkarte ist Letzteres ein Punkt und macht die
# Ebene unlesbar. Nationalparks und strenge Reservate behalten die niedrige Schwelle oben — dort
# soll nichts verschwinden, was bisher da war. Tansania verliert durch die Regel nichts (kleinste
# Fläche dort: 69 km²), Kenia 42 Kleinstflächen.
WEITE_KLASSEN = ('4', '6')
MIN_KM2_WEITE_KLASSEN = 50.0


def ring_km2(ring):
    """Näherungsfläche in km²: Gradmaß, in der Länge mit dem Kosinus der mittleren Breite
    entzerrt. Für eine Mindestgröße völlig ausreichend — es geht nicht um Katasterwerte."""
    if len(ring) < 4:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += (x1 * k) * y2 - (x2 * k) * y1
    return abs(s) / 2 * (111.32 ** 2)


# „protect_class" ist die IUCN-Kategorie des Schutzgebiets (Quelle: OSM-Wiki, Key:protect_class,
# geprüft 16.09.2026). Relevant für diese Ebene:
#   1a Strenges Naturreservat · 1b Wildnisgebiet · 1 (OSM-eigener Sammelwert für 1a/1b)
#   2  Nationalpark            · 3  Naturdenkmal (klein, kein Wild)
#   4  Wildtier-/Habitatschutz · 5  Schutzlandschaft (meist Kulturlandschaft)
#   6  Schutzgebiet mit nachhaltiger Nutzung (Menschen leben darin)
# Bis 15.09.2026 wurden nur 1/1a/1b/2 geholt. Damit fehlten genau die Gebiete, die formal KEIN
# Nationalpark sind, aber für diese Ebene die wichtigsten: das Masai-Mara-„National Reserve" und
# die Ngorongoro-„Conservation Area". Deshalb jetzt zusätzlich 4 und 6 — dort sitzen die Reservate
# und Schutzgebiete mit Großwild. 3 und 5 bleiben draußen: Naturdenkmäler sind klein und ohne
# Wild, Schutzlandschaften sind überwiegend Kulturlandschaft und würden die Datei aufblähen.
# Achtung: Kategorie II wird in OSM häufiger als boundary=national_park getaggt als über
# protect_class=2 — beide Wege stehen deshalb in der Abfrage.
#
# UND: Das OSM-Wiki schreibt arabische Werte vor („6"), in der Praxis wird aber auch die römische
# IUCN-Ziffer eingetragen. Genau daran ist Ngorongoro gescheitert — das Schutzgebiet trägt
# protect_class=VI (relation/21319325, geprüft 16.09.2026). Beide Schreibweisen meinen dasselbe;
# sie werden in der Abfrage gesucht und intern auf die arabische Form normalisiert.
IUCN_RN = {'1a': 'Ia', '1b': 'Ib', '1': 'Ia/Ib', '2': 'II', '3': 'III', '4': 'IV', '5': 'V', '6': 'VI'}
SCHREIBWEISEN = {'1': ('1', 'I'), '1a': ('1a', 'Ia'), '1b': ('1b', 'Ib'),
                 '2': ('2', 'II'), '3': ('3', 'III'), '4': ('4', 'IV'),
                 '5': ('5', 'V'), '6': ('6', 'VI')}
KLASSE_NORM = {s.lower(): k for k, ss in SCHREIBWEISEN.items() for s in ss}


def klasse_norm(wert):
    """„VI" und „6" sind dasselbe. Liefert die arabische Form; Unbekanntes bleibt unverändert
    (klein geschrieben), damit es in der Diagnose sichtbar wird statt still zu verschwinden."""
    k = str(wert or '').strip().lower()
    return KLASSE_NORM.get(k, k)
KLASSEN_TEXT = {
    '1a': 'Strenges Naturreservat (IUCN Ia)',
    '1b': 'Wildnisgebiet (IUCN Ib)',
    '1': 'Naturreservat/Wildnis (IUCN Ia/Ib)',
    '2': 'Nationalpark (IUCN II)',
    '4': 'Wildtier-/Habitatschutzgebiet (IUCN IV)',
    '6': 'Schutzgebiet mit nachhaltiger Nutzung (IUCN VI)',
}


def gebiets_typ(tags):
    """Was das Gebiet AMTLICH ist — steht im Popup. Der amtliche Titel (protection_title) hat
    Vorrang vor der IUCN-Nummer: „National Reserve" sagt mehr als „Kategorie IV". Wichtig, weil
    ein Conservation Area, in dem Menschen wohnen, etwas anderes ist als ein Nationalpark."""
    if tags.get('boundary') == 'national_park':
        return 'Nationalpark'
    klasse = klasse_norm(tags.get('protect_class'))
    titel = (tags.get('protection_title:de') or tags.get('protection_title') or '').strip()
    if titel:
        return titel + (f' (IUCN {IUCN_RN[klasse]})' if klasse in IUCN_RN else '')
    return KLASSEN_TEXT.get(klasse, 'Schutzgebiet')


KLASSEN_ABFRAGE = ('1', '1a', '1b', '2', '4', '6')   # normalisierte Klassen, die wir holen
# Die Regex sucht BEIDE Schreibweisen; „,i" in der Abfrage macht sie unabhängig von Groß-/
# Kleinschreibung. Aus einer Liste erzeugt, damit Abfrage und Urteilslogik nicht auseinanderlaufen.
KLASSEN_REGEX = '^(' + '|'.join(s for k in KLASSEN_ABFRAGE for s in SCHREIBWEISEN[k]) + ')$'


def overpass_query(cc):
    # boundary=national_park + Schutzklassen 1/1a/1b/2 (Wildnis/Nationalpark) sowie 4 und 6
    # (Reservate, Conservation Areas) — Begründung siehe oben
    # Abschluss MUSS „out geom;" sein, nicht „out geom tags;" — siehe Kopfkommentar:
    # „tags" unterdrückt die Mitglieder der Relationen und damit deren Geometrie.
    return f'''[out:json][timeout:300];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
(
  relation["boundary"="national_park"](area.a);
  relation["boundary"="protected_area"]["protect_class"~"{KLASSEN_REGEX}",i](area.a);
  way["boundary"="national_park"](area.a);
  way["boundary"="protected_area"]["protect_class"~"{KLASSEN_REGEX}",i](area.a);
);
out geom;'''


def fetch(cc):
    body = urllib.parse.urlencode({'data': overpass_query(cc)}).encode()
    letzte = None
    for versuch in range(4):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=body, headers={
                    'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-parks'})
                with urllib.request.urlopen(req, timeout=360) as r:
                    roh = r.read()
                try:
                    return json.loads(roh)
                except ValueError:
                    # Overpass meldet Überlast/Abbruch teils als Text oder XML MIT HTTP 200.
                    # Das darf nicht als „kaputtes JSON" durchgehen — sonst sucht man den
                    # Fehler an der falschen Stelle.
                    grund = ' '.join(roh.decode('utf-8', 'replace').split())[:200]
                    letzte = RuntimeError(grund)
                    print(f'   ⚠️  {url.split("/")[2]}: keine JSON-Antwort — {grund}')
            except urllib.error.HTTPError as e:
                letzte = e
                if e.code in (429, 504):  # gedrosselt/überlastet: Server-Wunsch respektieren
                    warte = int(e.headers.get('Retry-After') or 0) or 30
                    print(f'   ⚠️  {url.split("/")[2]}: HTTP {e.code} — warte {warte}s...')
                    time.sleep(warte)
                else:
                    print(f'   ⚠️  {url.split("/")[2]}: {e} — nächster Mirror...')
            except Exception as e:
                letzte = e
                print(f'   ⚠️  {url.split("/")[2]}: {e} — nächster Mirror...')
        pause = 60 * (versuch + 1)  # Backoff zwischen den Runden: 60/120/180 s
        print(f'   ⏳ Runde {versuch + 1} erfolglos — {pause}s Pause...')
        time.sleep(pause)
    raise RuntimeError(f'Overpass nicht erreichbar: {letzte}')


# ── Geometrie-Helfer (bewusst stdlib-only, keine shapely-Abhängigkeit) ──

def dp_vereinfachen(pts, eps):
    """Douglas-Peucker, iterativ (kein Rekursionslimit)."""
    if len(pts) < 3:
        return pts[:]
    behalten = [False] * len(pts)
    behalten[0] = behalten[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        norm2 = dx * dx + dy * dy
        dmax, imax = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            if norm2 < 1e-18:  # geschlossener Ring: Sehne degeneriert → Abstand zum Ankerpunkt
                d = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / norm2 ** 0.5
            if d > dmax:
                dmax, imax = d, i
        if dmax > eps:
            behalten[imax] = True
            stack.append((a, imax)); stack.append((imax, b))
    return [p for p, k in zip(pts, behalten) if k]


def ring_flaeche(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def ringe_zusammensetzen(segmente):
    """Wege einer Relation (role=outer) an den Endpunkten zu geschlossenen Ringen verketten."""
    segs = [list(s) for s in segmente if len(s) >= 2]
    ringe = []
    while segs:
        cur = segs.pop(0)
        gewachsen = True
        while gewachsen and cur[0] != cur[-1]:
            gewachsen = False
            for i, s in enumerate(segs):
                if s[0] == cur[-1]:
                    cur += s[1:]
                elif s[-1] == cur[-1]:
                    cur += s[-2::-1]
                elif s[-1] == cur[0]:
                    cur = s[:-1] + cur
                elif s[0] == cur[0]:
                    cur = s[:0:-1] + cur
                else:
                    continue
                segs.pop(i); gewachsen = True
                break
        if cur[0] != cur[-1]:
            cur.append(cur[0])  # kleine Lücke: erzwungen schließen
        if len(cur) >= 4:
            ringe.append(cur)
    return ringe


def gebiet_vereinfachen(ringe):
    """Alle Ringe eines Gebiets vereinfachen; Toleranz erhöhen bis Punktbudget passt."""
    eps = EPS_START
    for _ in range(5):
        fertig = []
        for r in ringe:
            v = dp_vereinfachen(r, eps)
            if v[0] != v[-1]:
                v.append(v[0])
            v = [(round(x, 4), round(y, 4)) for x, y in v]
            v = [p for i, p in enumerate(v) if i == 0 or p != v[i - 1]]
            if len(v) >= 4 and ring_flaeche(v) >= MIN_RING_FLAECHE:
                fertig.append(v)
        if sum(len(r) for r in fertig) <= MAX_PUNKTE_PRO_GEBIET or not fertig:
            return fertig
        eps *= 2
    return fertig


def elemente_zu_features(daten, land):
    """Liefert (features, rohpunkte, diagnose). Die Diagnose unterscheidet zwei sehr
    verschiedene Ausfälle: „Antwort enthält keine Mitglieder" ist ein Fehler UNSERER
    Abfrage, „keine geschlossene Fläche" ist die Datenlage in OSM."""
    feats, namen, roh_punkte = [], set(), 0
    ohne_mitglieder, ohne_flaeche, zu_klein, aus_relation = [], [], [], 0
    elems = daten.get('elements', [])
    # Relationen zuerst (vollständige Multipolygone) — Wege mit gleichem Namen sind Duplikate
    for el in sorted(elems, key=lambda e: 0 if e['type'] == 'relation' else 1):
        tags = el.get('tags', {})
        name = tags.get('name:de') or tags.get('name')
        if not name or name in namen:
            continue
        if el['type'] == 'relation':
            segs = [[(g['lon'], g['lat']) for g in m.get('geometry', [])]
                    for m in el.get('members', [])
                    if m.get('type') == 'way' and m.get('role') in ('outer', '') and m.get('geometry')]
            if not segs:
                # Signatur des „out geom tags"-Fehlers. Der Name wird bewusst NICHT belegt:
                # ein gleichnamiger Weg darf die Fläche danach noch liefern.
                ohne_mitglieder.append(name)
                continue
            ringe = ringe_zusammensetzen(segs)
        else:
            ringe = [[(g['lon'], g['lat']) for g in el.get('geometry', [])]]
            ringe = [r + [r[0]] if r and r[0] != r[-1] else r for r in ringe]
            ringe = [r for r in ringe if len(r) >= 4]
        roh_punkte += sum(len(r) for r in ringe)
        ringe = gebiet_vereinfachen(ringe)
        if not ringe:
            ohne_flaeche.append(name)
            continue
        klasse = klasse_norm(tags.get('protect_class'))
        if klasse in WEITE_KLASSEN and tags.get('boundary') != 'national_park':
            km2 = sum(ring_km2(r) for r in ringe)
            if km2 < MIN_KM2_WEITE_KLASSEN:
                zu_klein.append(f'{name} ({km2:.0f} km²)')
                continue
        namen.add(name)
        if el['type'] == 'relation':
            aus_relation += 1
        typ = gebiets_typ(tags)
        feats.append({
            'type': 'Feature',
            'properties': {'name': name, 'land': land, 'typ': typ, 'klasse': klasse,
                           'osm': ('r' if el['type'] == 'relation' else 'w') + str(el['id'])},
            'geometry': {'type': 'MultiPolygon', 'coordinates': [[r] for r in ringe]},
        })
    return feats, roh_punkte, {'ohne_mitglieder': ohne_mitglieder, 'ohne_flaeche': ohne_flaeche,
                               'zu_klein': zu_klein, 'aus_relation': aus_relation}


def kurzliste(namen, n=5):
    return ', '.join(namen[:n]) + (' …' if len(namen) > n else '')


def tags_diagnose(muster):
    """„Warum fehlt dieses Gebiet?" — beantwortet aus der Quelle statt aus Vermutungen."""
    sicher = muster.replace('\\', '').replace('"', '')
    frage = f"""[out:json][timeout:120];
(
  relation["name"~"{sicher}",i];
  way["name"~"{sicher}",i];
);
out tags;"""
    print(f'🔎 Overpass nach Namen „{sicher}" …')
    body = urllib.parse.urlencode({'data': frage}).encode()
    letzte = None
    for url in MIRRORS:
        try:
            req = urllib.request.Request(url, data=body, headers={
                'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-parks'})
            with urllib.request.urlopen(req, timeout=180) as r:
                daten = json.loads(r.read())
            break
        except Exception as e:
            letzte = e
            print(f'   ⚠️  {url.split("/")[2]}: {e}')
    else:
        sys.exit(f'Overpass nicht erreichbar: {letzte}')

    elemente = daten.get('elements', [])
    if not elemente:
        print('   Nichts gefunden — anderes Namensmuster versuchen (die Suche ist ein Regex, '
              'Groß-/Kleinschreibung egal).')
        return
    for el in elemente:
        t = el.get('tags', {})
        name = t.get('name:de') or t.get('name') or '(ohne Namen)'
        grenze, klasse = t.get('boundary', '—'), klasse_norm(t.get('protect_class'))
        if grenze == 'national_park':
            urteil = '✅ wird erfasst (boundary=national_park)'
        elif grenze == 'protected_area' and klasse in KLASSEN_ABFRAGE:
            urteil = f'✅ wird erfasst (protect_class={klasse})'
            if klasse in WEITE_KLASSEN:
                urteil += f' — sofern die Fläche mindestens {MIN_KM2_WEITE_KLASSEN:.0f} km² beträgt'
        elif grenze == 'protected_area':
            urteil = (f'❌ NICHT erfasst: protect_class={t.get("protect_class") or "fehlt"}'
                      + (f' (entspricht {klasse})' if klasse and klasse != str(t.get('protect_class') or '').lower() else '')
                      + f' — die Abfrage nimmt nur {", ".join(KLASSEN_ABFRAGE)} '
                        f'(arabisch oder römisch geschrieben)')
        else:
            urteil = f'❌ NICHT erfasst: boundary={grenze} (gesucht: national_park oder protected_area)'
        print(f'\n  {el["type"]}/{el["id"]}  {name}')
        print(f'    {urteil}')
        for schluessel in ('boundary', 'protect_class', 'protection_title', 'leisure', 'landuse',
                           'type', 'admin_level', 'ref:whc', 'iucn_level'):
            if t.get(schluessel):
                print(f'    {schluessel} = {t[schluessel]}')
    print('\nDie Tags stammen unverändert aus OpenStreetMap (ODbL).')


def main():
    if ARGUMENTE[:1] == ['--tags']:
        if len(ARGUMENTE) < 2:
            sys.exit('Aufruf: python3 fetch-parks.py --tags <Namensmuster>')
        tags_diagnose(' '.join(ARGUMENTE[1:]))
        return
    nur = {a.upper() for a in sys.argv[1:] if not a.startswith('-')}
    optionen = [a for a in sys.argv[1:] if a.startswith('-')]   # --tags ist oben schon raus
    if optionen:
        sys.exit(f'Unbekannte Option: {" ".join(optionen)} — Aufruf: '
                 f'python3 fetch-parks.py [LÄNDERCODE ...]')
    unbekannt = nur - {cc for cc, _ in LAENDER}
    if unbekannt:
        sys.exit(f'Unbekannter Ländercode: {", ".join(sorted(unbekannt))} — bekannt sind: '
                 + ' '.join(cc for cc, _ in LAENDER))
    laender = [(cc, n) for cc, n in LAENDER if not nur or cc in nur]

    # Bestand einlesen. Ein Land, das jetzt nicht geholt wird ODER dessen Abruf scheitert,
    # behält seine bisherigen Flächen — ein Fehlversuch darf niemals Daten löschen.
    bestand, staende = {}, {}
    if OUT.exists():
        try:
            vorher = json.load(open(OUT, encoding='utf-8'))
            for f in vorher['features']:
                bestand.setdefault(f['properties']['land'], []).append(f)
            staende = dict(vorher.get('staende') or {})
        except Exception:
            print('⚠️  Bestehende parks.geojson unlesbar — wird komplett neu geschrieben')

    def schreiben():
        feats = [f for land in bestand for f in bestand[land]]
        feats.sort(key=lambda f: (f['properties']['land'], f['properties']['name']))
        OUT.parent.mkdir(exist_ok=True)
        fc = {
            'type': 'FeatureCollection',
            'attribution': '© OpenStreetMap contributors (ODbL) 1.0 https://opendatacommons.org/licenses/odbl/1-0/ — Grenzen vereinfacht, Stand '
                           + time.strftime('%Y-%m'),
            'hinweis': 'Erzeugt von fetch-parks.py. Nur Orientierung, keine Rechtsgrenzen.',
            'staende': staende,
            'features': feats,
        }
        OUT.write_text(json.dumps(fc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        return len(feats), OUT.stat().st_size // 1024

    fehler = []
    for i, (cc, land) in enumerate(laender):
        print(f'⬇️  {land} ({cc}) — Overpass...')
        try:
            daten = fetch(cc)
        except RuntimeError as e:
            print(f'   ❌ {e}')
            if bestand.get(land):
                print(f'   ↩︎  bisheriger Stand für {land} bleibt erhalten '
                      f'({len(bestand[land])} Gebiete, Stand {staende.get(land, "unbekannt")})')
            fehler.append((cc, land))
            continue
        neu, roh, d = elemente_zu_features(daten, land)
        pkt = sum(len(r[0]) for f in neu for r in f['geometry']['coordinates'])
        print(f'   ✅ {len(neu)} Gebiete ({d["aus_relation"]} aus Relationen, '
              f'{len(neu) - d["aus_relation"]} aus Wegen) · {roh} Rohpunkte → {pkt} vereinfacht')
        if d['ohne_mitglieder']:
            # Das ist KEINE Datenlage, sondern ein Abfragefehler — entsprechend laut.
            print(f'   🔴 {len(d["ohne_mitglieder"])} Relationen kamen OHNE Mitglieder an — die '
                  f'Abfrage liefert dann keine Geometrie (out geom tags?): '
                  f'{kurzliste(d["ohne_mitglieder"])}')
        if d['ohne_flaeche']:
            print(f'   ⚠️  {len(d["ohne_flaeche"])} ohne geschlossene Fläche in OSM — bleiben weg: '
                  f'{kurzliste(d["ohne_flaeche"])}')
        if d['zu_klein']:
            print(f'   ℹ️  {len(d["zu_klein"])} Gebiete der Klassen IV/VI unter '
                  f'{MIN_KM2_WEITE_KLASSEN:.0f} km² übersprungen: {kurzliste(d["zu_klein"])}')
        if not neu:
            print(f'   ⚠️  0 Gebiete für {land} — Query/Datenlage prüfen (nie still scheitern)')
            fehler.append((cc, land))
            continue
        bestand[land] = neu
        staende[land] = time.strftime('%Y-%m-%d')
        anz, kb = schreiben()
        print(f'   💾 Zwischenstand gesichert: {anz} Gebiete, {kb} KB')
        if i < len(laender) - 1:
            time.sleep(10)  # Overpass-Höflichkeit (429-Lektion: 3 s waren zu forsch)

    anz, kb = schreiben()
    print(f'\n🟢 {OUT.name}: {anz} Gebiete, {kb} KB → {OUT}')
    aus_rel = sum(1 for fs in bestand.values() for f in fs
                  if str(f['properties'].get('osm', '')).startswith('r'))
    print(f'   davon {aus_rel} aus Relationen, {anz - aus_rel} aus Wegen')
    # Aufteilung nach Schutzklasse — damit sichtbar wird, was die Erweiterung auf 4 und 6
    # tatsächlich beigetragen hat und ob die Datei dadurch aus dem Ruder läuft.
    nach_klasse = {}
    for fs in bestand.values():
        for f in fs:
            k = f['properties'].get('klasse') or ('national_park' if f['properties'].get('typ') == 'Nationalpark' else '—')
            nach_klasse[k] = nach_klasse.get(k, 0) + 1
    if nach_klasse:
        print('   nach Schutzklasse: ' + ', '.join(f'{k}: {n}' for k, n in sorted(nach_klasse.items())))
    if anz and not aus_rel:
        print('🔴 KEIN einziges Gebiet aus einer Relation — das war die Signatur des Fehlers vom '
              '15.09.2026. Abfrage prüfen: sie muss auf „out geom;" enden.')
    if kb > 4000:
        print('⚠️  Datei > 4 MB — EPS_START/MAX_PUNKTE_PRO_GEBIET straffen (Bug-11-Lektion)')
    if fehler:
        print(f'🔴 Fehlgeschlagen: {", ".join(n for _, n in fehler)} — später erneut: '
              f'python3 fetch-parks.py ' + ' '.join(cc for cc, _ in fehler))
        sys.exit(1)
    print('Danach: ./deploy.sh  (kopiert die Datei ins Bundle)')


if __name__ == '__main__':
    main()
