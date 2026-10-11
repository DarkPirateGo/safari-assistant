#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-klima.py v2026-09-25-1
#
# Holt die Klimatologie (langjährige Monatsmittel) für ein 1°-Raster über die
# 16 Reiseländer und schreibt data/klima.json — die Datengrundlage der
# Regenzeit-Ebene mit Zeitleiste auf der POI-Karte (pois.html, 🌧️-Knopf).
#
# Quelle: NASA POWER (power.larc.nasa.gov), Dienst „temporal/climatology/point".
#   Meteorologie aus MERRA-2 (½° × ⅝°), Solarstrahlung aus dem POWER-Strahlungsdatensatz (1°).
#   Die Daten der NASA sind frei nutzbar; die Quelle steht in der Ausgabedatei und im
#   Karten-Popup. Je Rasterzelle EINE Anfrage (alle Parameter zusammen), Antwort sind
#   zwölf Monatswerte je Parameter — kein Tagesmaterial, keine Nachverdichtung nötig.
#
# Was drin ist (je Zelle, 12 Monate):
#   p  Niederschlag in mm/Monat (aus mm/Tag × Tage des Monats)
#   t  Ø Temperatur (°C) · tx / tn  EXTREMWERTE des Monats im Bezugszeitraum (höchster/tiefster Wert,
#      °C) — so liefert POWER T2M_MAX/T2M_MIN in der Klimatologie (echter Lauf 25.09.2026: Lüderitz
#      Jan 43 °C, Windhoek Jul −4 °C); es sind KEINE Tagesmittel der Höchst-/Tiefstwerte
#   rh  relative Feuchte (%) · ws  Ø Wind in 10 m (m/s) · sr  Globalstrahlung (kWh/m²/Tag — Solar-Ertrag)
#
# WICHTIG: Das ist eine KLIMATOLOGIE (Mittel über viele Jahre), keine Vorhersage. Die App sagt
# das an jeder Stelle dazu. Regenzeiten verschieben sich von Jahr zu Jahr um Wochen.
#
# Nutzung:  im Projektordner: python3 fetch-klima.py
#           (einmalig MIT Internet; rund 1000 Anfragen, dauert 15–40 Minuten. Der Lauf sichert
#           alle 20 Zellen einen Zwischenstand in data/tmp/ — ein Abbruch ist unkritisch, der
#           nächste Aufruf macht dort weiter, wo er aufgehört hat.)
#           Einzelne Länder:        python3 fetch-klima.py NA BW
#           Antwortformat ansehen:  python3 fetch-klima.py --probe    (eine Anfrage, Rohantwort)
#           Alles neu holen:        python3 fetch-klima.py --neu
#           Gröberes Raster:        python3 fetch-klima.py --raster 2
#
# Danach:   ./deploy.sh  (kopiert data/klima.json ins Bundle)
#
# Hinweis zur Entstehung (24.09.2026): Dieses Skript wurde in einer Umgebung OHNE Zugang zu
# power.larc.nasa.gov geschrieben. Die Antwortstruktur (properties.parameter.<PARAM>.JAN…DEC,
# header.fill_value, parameters.<PARAM>.units) entspricht der POWER-API v2 nach bestem Wissen,
# ist aber hier nicht gegen den Dienst geprüft. Deshalb: Der erste Lauf prüft die Struktur der
# ersten Antwort ausdrücklich und bricht mit dem WÖRTLICHEN Anfang der Antwort ab, wenn sie
# anders aussieht — „--probe" zeigt die Rohantwort. Projektregel: Eine Fehlermeldung nennt den
# Beleg.
# ═══════════════════════════════════════════════════════════════════
import json, math, re, sys, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'data' / 'klima.json'
FORTSCHRITT = BASE / 'data' / 'tmp' / 'klima-fortschritt.json'
ARGUMENTE = list(sys.argv[1:])

API = 'https://power.larc.nasa.gov/api/temporal/climatology/point'
COMMUNITY = 'RE'   # Renewable Energy: Globalstrahlung kommt in kWh/m²/Tag (Solar-Ertrag)
# Parametername bei POWER → Kurzname in klima.json
PARAMETER = [
    ('PRECTOTCORR', 'p'),          # Niederschlag, biaskorrigiert, mm/Tag
    ('T2M', 't'),                  # Ø Temperatur 2 m
    ('T2M_MAX', 'tx'),             # Extremwert: höchste Temperatur des Monats im Zeitraum
    ('T2M_MIN', 'tn'),             # Extremwert: tiefste Temperatur des Monats im Zeitraum
    ('RH2M', 'rh'),                # relative Feuchte 2 m
    ('WS10M', 'ws'),               # Ø Windgeschwindigkeit 10 m
    ('ALLSKY_SFC_SW_DWN', 'sr'),   # Globalstrahlung auf die Horizontale
]
MONATE = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
TAGE = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
PAUSE_S = 0.7            # Höflichkeit — POWER nennt kein hartes Limit, wir drängeln trotzdem nicht
SICHERN_ALLE = 20        # Zwischenstand alle N Zellen

# Ländercodes wie in fetch-parks.py; Namen EXAKT wie in LAENDER_GEO (Single Source of Truth)
LAENDER = [
    ('ZA', 'Südafrika'), ('NA', 'Namibia'), ('BW', 'Botswana'), ('ZM', 'Sambia'),
    ('ZW', 'Zimbabwe'), ('MZ', 'Mosambik'), ('MW', 'Malawi'), ('TZ', 'Tansania'),
    ('KE', 'Kenia'), ('UG', 'Uganda'), ('RW', 'Ruanda'), ('BI', 'Burundi'),
    ('ET', 'Äthiopien'), ('AO', 'Angola'), ('SZ', 'Eswatini'), ('LS', 'Lesotho'),
]
CODE_VON_LAND = {name: cc for cc, name in LAENDER}

# Plausible Spannen — alles außerhalb ist ein Zeichen für ein falsch gelesenes Feld (nie still übernehmen)
PLAUSIBEL = {'p': (0, 60), 't': (-15, 45), 'tx': (-10, 55), 'tn': (-30, 40), 'rh': (0, 100), 'ws': (0, 30), 'sr': (0, 12)}


def laender_polygone(quelle=None):
    """LAENDER_GEO aus pois.html lesen — die 16 Länderumrisse, die die App selbst benutzt
    (byteidentisch in index/mobile/pois, durch Tests gesichert). Kein zweiter Datensatz."""
    quelle = quelle or (BASE / 'pois.html')
    text = Path(quelle).read_text(encoding='utf-8')
    block = re.search(r'const LAENDER_GEO = \[(.*?)\n\];', text, re.S)
    if not block:
        sys.exit(f'LAENDER_GEO nicht in {quelle} gefunden — Datei oder Format geändert?')
    polys = []
    for m in re.finditer(r"\{\s*name:\s*'([^']+)',\s*poly:\s*(\[\[.*?\]\])\s*\}", block.group(1), re.S):
        polys.append({'name': m.group(1), 'poly': json.loads(m.group(2))})
    if len(polys) != 16:
        sys.exit(f'LAENDER_GEO: {len(polys)} statt 16 Länder gelesen — Format geändert?')
    return polys


def punkt_in_ring(lng, lat, ring):
    """Strahlenverfahren — dieselbe Logik wie punktInRing() in der App."""
    drin = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            drin = not drin
        j = i
    return drin


def land_von(lng, lat, polys):
    for p in polys:            # Reihenfolge = Priorität (Enklaven zuerst), wie in der App
        if punkt_in_ring(lng, lat, p['poly']):
            return p['name']
    return None


def raster_zellen(polys, schritt=1.0):
    """Alle Zellen (SW-Ecke lon/lat), die eines der 16 Länder berühren. Geprüft werden neun
    Punkte je Zelle (Mitte, Ecken, Kantenmitten) — sonst fielen Küstenzellen weg, deren Mitte im
    Meer liegt. 'pt' ist der Abfragepunkt: die Mitte, wenn sie im Land liegt, sonst der erste
    Prüfpunkt im Land (Küste: lieber die Landseite messen als das Meer davor)."""
    minx = min(pt[0] for p in polys for pt in p['poly']); maxx = max(pt[0] for p in polys for pt in p['poly'])
    miny = min(pt[1] for p in polys for pt in p['poly']); maxy = max(pt[1] for p in polys for pt in p['poly'])
    zellen = []
    x = math.floor(minx / schritt) * schritt
    while x < maxx:
        y = math.floor(miny / schritt) * schritt
        while y < maxy:
            h = schritt / 2
            pruef = [(x + h, y + h), (x, y), (x + schritt, y), (x, y + schritt), (x + schritt, y + schritt),
                     (x + h, y), (x + h, y + schritt), (x, y + h), (x + schritt, y + h)]
            land, pt = None, None
            for (px, py) in pruef:
                l = land_von(px, py, polys)
                if l:
                    land, pt = l, (px, py)
                    break
            if land:
                zellen.append({'lon': round(x, 4), 'lat': round(y, 4), 'land': land,
                               'pt': [round(pt[0], 4), round(pt[1], 4)]})
            y = round(y + schritt, 6)
        x = round(x + schritt, 6)
    return zellen


def anfrage_url(lng, lat):
    q = {'parameters': ','.join(p for p, _ in PARAMETER), 'community': COMMUNITY,
         'longitude': f'{lng:.4f}', 'latitude': f'{lat:.4f}', 'format': 'JSON'}
    return API + '?' + urllib.parse.urlencode(q)


def hole(url, timeout=90):
    """Eine HTTP-Anfrage → Text. Bewusst eigenständig, damit Tests sie durch eine Attrappe
    ersetzen können, ohne ins Netz zu gehen."""
    req = urllib.request.Request(url, headers={'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-klima'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def hole_mit_wiederholung(url, versuche=6):
    """429/5xx/Netzfehler → warten und erneut; 4xx sonst → sofort Fehler mit Wortlaut."""
    letzter = None
    for v in range(versuche):
        try:
            return hole(url)
        except urllib.error.HTTPError as e:
            koerper = ''
            try:
                koerper = e.read().decode('utf-8', 'replace')[:400]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 504):
                ra = (e.headers.get('Retry-After') or '').strip()     # Sekunden ODER HTTP-Datum (RFC 7231)
                warte = int(ra) if ra.isdigit() else 20 * (v + 1)
                print(f'   ⚠️  HTTP {e.code} — warte {warte}s … {koerper[:120]}')
                time.sleep(warte)
                letzter = f'HTTP {e.code}: {koerper}'
                continue
            raise RuntimeError(f'HTTP {e.code} von POWER — Wortlaut: {koerper or "(leer)"}')
        except Exception as e:
            letzter = str(e)
            warte = 10 * (v + 1)
            print(f'   ⚠️  {e} — warte {warte}s …')
            time.sleep(warte)
    raise RuntimeError(f'nach {versuche} Versuchen aufgegeben — zuletzt: {letzter}')


def monatswerte(antwort, param):
    """Zwölf Monatswerte eines Parameters aus der POWER-Antwort. Sucht das Monats-Wörterbuch
    (JAN…DEC) unter properties.parameter.<PARAM>; ist die Struktur anders, wird der Fehler mit
    dem Fundort benannt statt still 0 zu liefern."""
    try:
        d = antwort['properties']['parameter'][param]
    except (KeyError, TypeError):
        raise ValueError(f'properties.parameter.{param} fehlt in der Antwort')
    if not isinstance(d, dict) or any(m not in d for m in MONATE):
        raise ValueError(f'{param}: kein Monats-Wörterbuch JAN…DEC, sondern {type(d).__name__} mit Schlüsseln {list(d)[:6] if isinstance(d, dict) else "?"}')
    fill = -999.0
    try:
        fill = float(antwort.get('header', {}).get('fill_value', -999.0))
    except (TypeError, ValueError):
        pass
    werte = []
    for m in MONATE:
        try:
            w = float(d[m])
        except (TypeError, ValueError):
            w = None
        if w is None or abs(w - fill) < 1e-6 or w <= -900:
            werte.append(None)
        else:
            werte.append(w)
    return werte


def einheit(antwort, param):
    try:
        return str(antwort['parameters'][param]['units'])
    except (KeyError, TypeError):
        return ''


def antwort_zu_zelle(antwort):
    """POWER-Antwort → Kurzform für klima.json. Prüft Einheiten und Plausibilität."""
    erg, einheiten = {}, {}
    for param, kurz in PARAMETER:
        werte = monatswerte(antwort, param)
        u = einheit(antwort, param)
        einheiten[kurz] = u
        if kurz == 'sr' and u and 'mj' in u.lower():
            werte = [None if w is None else w / 3.6 for w in werte]   # MJ/m²/Tag → kWh/m²/Tag
            einheiten[kurz] = 'kWh/m^2/day (aus MJ umgerechnet)'
        lo, hi = PLAUSIBEL[kurz]   # Spannen gelten für die Rohwerte der Quelle (p in mm/Tag)
        for w in werte:
            if w is not None and not (lo <= w <= hi):
                raise ValueError(f'{param}: Wert {w} außerhalb der plausiblen Spanne {lo}…{hi} ({u})')
        if kurz == 'p':
            # mm/Tag → mm/Monat. Meldet POWER eine andere Einheit als mm/Tag, wird NICHT geraten.
            if u and 'day' not in u.lower() and 'tag' not in u.lower():
                raise ValueError(f'{param}: Einheit „{u}" — erwartet mm/day')
            werte = [None if w is None else w * TAGE[i] for i, w in enumerate(werte)]
        nk = 0 if kurz in ('p', 'rh') else (2 if kurz == 'sr' else 1)
        erg[kurz] = [None if w is None else (round(w) if nk == 0 else round(w, nk)) for w in werte]
    return erg, einheiten


def zeitraum_aus(antwort):
    """Der Bezugszeitraum der Klimatologie steht im Kopf der Antwort — welches Feld genau, ist
    nicht garantiert; wir nehmen, was da ist, und zeigen es unverändert."""
    h = antwort.get('header') or {}
    for k in ('range', 'period', 'start', 'time_standard'):
        if k in h:
            if k == 'start' and 'end' in h:
                return f'{h["start"]}–{h["end"]}'
            return str(h[k])
    return ''


def struktur_pruefen(text):
    """Erste Antwort: JSON? Erwartete Felder? Bricht mit dem Rohanfang ab, wenn nicht."""
    try:
        antwort = json.loads(text)
    except ValueError:
        sys.exit('🔴 POWER liefert kein JSON. Anfang der Antwort:\n' + text[:600])
    try:
        zelle, einheiten = antwort_zu_zelle(antwort)
    except ValueError as e:
        sys.exit('🔴 Antwortstruktur anders als erwartet: ' + str(e) + '\nAnfang der Antwort:\n' + text[:1200]
                 + '\n\nZum Ansehen: python3 fetch-klima.py --probe')
    return antwort, zelle, einheiten


def fortschritt_lesen():
    if FORTSCHRITT.exists():
        try:
            return json.loads(FORTSCHRITT.read_text(encoding='utf-8'))
        except Exception:
            print('⚠️  Zwischenstand unlesbar — wird verworfen')
    return {'zellen': {}, 'einheiten': {}, 'zeitraum': '', 'raster': None}


def fortschritt_schreiben(f):
    FORTSCHRITT.parent.mkdir(parents=True, exist_ok=True)
    FORTSCHRITT.write_text(json.dumps(f, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def ausgabe_schreiben(zellen, einheiten, zeitraum, raster):
    zellen = sorted(zellen, key=lambda z: (z['land'], z['lat'], z['lon']))
    OUT.parent.mkdir(exist_ok=True)
    daten = {
        'quelle': 'NASA POWER (power.larc.nasa.gov) — Klimatologie: Meteorologie MERRA-2, Strahlung POWER; '
                  'Daten der NASA, frei nutzbar',
        'zeitraum': zeitraum,
        'erzeugt': time.strftime('%Y-%m-%d'),
        'raster': raster,
        'hinweis': 'Langjährige Monatsmittel je Rasterzelle (Abfragepunkt „pt"). KEINE Vorhersage — '
                   'Regenzeiten verschieben sich von Jahr zu Jahr um Wochen. p = mm/Monat, t = Ø °C, '
                   'tx/tn = Extremwerte des Monats im Zeitraum (°C, keine Tagesmittel), rh = %, ws = m/s, '
                   'sr = kWh/m²/Tag. Reanalyse ~50 km: an Wüstenküsten zu nass, im Gebirge grob.',
        'einheiten_quelle': einheiten,
        'zellen': zellen,
    }
    OUT.write_text(json.dumps(daten, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return OUT.stat().st_size // 1024


def zusammenfassung(zellen):
    """Sichtprüfung am Ende: Anzahl je Land und ein paar Kennwerte, an denen man Unsinn erkennt."""
    je_land = {}
    for z in zellen:
        je_land[z['land']] = je_land.get(z['land'], 0) + 1
    print('   Zellen je Land: ' + ', '.join(f'{l}: {n}' for l, n in sorted(je_land.items())))
    mit_p = [z for z in zellen if any(w is not None for w in z['p'])]
    if not mit_p:
        print('🔴 Keine Zelle hat Niederschlagswerte — Antwortfelder prüfen (--probe)')
        return
    nass = max(mit_p, key=lambda z: max(w or 0 for w in z['p']))
    trocken = min(mit_p, key=lambda z: sum(w or 0 for w in z['p']))
    mon = lambda z: MONATE[max(range(12), key=lambda i: z['p'][i] or 0)]
    print(f'   Nassester Monat: {max(w or 0 for w in nass["p"])} mm in {nass["land"]} ({nass["pt"][0]}/{nass["pt"][1]}, {mon(nass)})')
    print(f'   Trockenste Zelle: {round(sum(w or 0 for w in trocken["p"]))} mm/Jahr in {trocken["land"]} ({trocken["pt"][0]}/{trocken["pt"][1]})')
    luecken = sum(1 for z in zellen for k in ('p', 'tx', 'tn') for w in z[k] if w is None)
    if luecken:
        print(f'   ⚠️  {luecken} fehlende Monatswerte (Füllwert der Quelle) — bleiben in der Karte leer')
    # Einordnung statt Alarm: Die Reanalyse (~50 km) ist an der Namib-Küste bekanntermaßen zu nass
    # (Lauf 25.09.2026: Walvis Bay 113, Lüderitz 56 mm/Jahr — Stationen melden 10–20 mm). Für die Karte
    # bleibt das „trocken" (< 20 mm/Monat). Ein früherer Anker warnte bei lon ≤ 15 und > 200 mm — das traf
    # die Escarpment-Zelle bei Uis/Omaruru (259 mm, plausibel), also Fehlalarm.
    kueste = [z for z in zellen if z['land'] == 'Namibia' and z['lon'] <= 15 and -27 <= z['lat'] <= -22]
    if kueste:
        print('   Namib-Küste (Reanalyse, erwartet zu nass — Stationen 10–20 mm): '
              + ', '.join(f'{z["lon"]}/{z["lat"]}: {round(sum(w or 0 for w in z["p"]))} mm/Jahr' for z in sorted(kueste, key=lambda z: z['lat'])[:6]))


def probe():
    polys = laender_polygone()
    url = anfrage_url(17.08, -22.56)   # Windhoek
    print('Anfrage: ' + url)
    text = hole_mit_wiederholung(url)
    print('\nRohantwort (erste 3000 Zeichen):\n' + text[:3000])
    antwort, zelle, einheiten = struktur_pruefen(text)
    print('\n✅ Struktur wie erwartet. Einheiten: ' + json.dumps(einheiten))
    print('   Zeitraum laut Kopf: ' + (zeitraum_aus(antwort) or '(nicht gefunden)'))
    print('   Windhoek, Niederschlag mm/Monat: ' + json.dumps(zelle['p']))
    print('   (Erwartung Windhoek: Regen v. a. Jan–Mär, Jun–Sep praktisch null — Klimatologie, ungefähr)')
    print(f'   Land laut LAENDER_GEO: {land_von(17.08, -22.56, polys)}')


def main():
    optionen = [a for a in ARGUMENTE if a.startswith('-')]
    if '--probe' in optionen:
        probe()
        return
    neu = '--neu' in optionen
    raster = 1.0
    if '--raster' in ARGUMENTE:
        i = ARGUMENTE.index('--raster')
        try:
            raster = float(ARGUMENTE[i + 1])
        except (IndexError, ValueError):
            sys.exit('Aufruf: python3 fetch-klima.py --raster <Grad, z. B. 1 oder 2>')
        if not (0.25 <= raster <= 5):
            sys.exit('--raster zwischen 0.25 und 5 Grad wählen')
    unbekannt = [o for o in optionen if o not in ('--neu', '--raster')]
    if unbekannt:
        sys.exit(f'Unbekannte Option: {" ".join(unbekannt)} — Aufruf: python3 fetch-klima.py [--neu] [--raster N] [--probe] [LÄNDERCODE …]')
    nur = {a.upper() for a in ARGUMENTE if not a.startswith('-') and not re.fullmatch(r'[\d.]+', a)}
    falsch = nur - {cc for cc, _ in LAENDER}
    if falsch:
        sys.exit(f'Unbekannter Ländercode: {", ".join(sorted(falsch))} — bekannt sind: ' + ' '.join(cc for cc, _ in LAENDER))

    polys = laender_polygone()
    zellen = raster_zellen(polys, raster)
    if nur:
        zellen = [z for z in zellen if CODE_VON_LAND[z['land']] in nur]
    print(f'🗺  {len(zellen)} Rasterzellen ({raster}°) über {len({z["land"] for z in zellen})} Länder')

    f = fortschritt_lesen()
    if neu or f.get('raster') not in (None, raster):
        if f.get('zellen') and f.get('raster') != raster:
            print(f'ℹ️  Zwischenstand stammt von einem {f.get("raster")}°-Raster — wird verworfen')
        f = {'zellen': {}, 'einheiten': {}, 'zeitraum': '', 'raster': raster}
    f['raster'] = raster
    fertig = f['zellen']
    offen = [z for z in zellen if f'{z["lon"]},{z["lat"]}' not in fertig]
    print(f'   {len(zellen) - len(offen)} schon geholt, {len(offen)} offen'
          + (f' — weiter aus {FORTSCHRITT}' if len(zellen) - len(offen) else ''))

    fehler = []
    start = time.time()
    for i, z in enumerate(offen):
        key = f'{z["lon"]},{z["lat"]}'
        url = anfrage_url(z['pt'][0], z['pt'][1])
        try:
            text = hole_mit_wiederholung(url)
        except RuntimeError as e:
            print(f'   ❌ {z["land"]} {key}: {e}')
            fehler.append(key)
            if len(fehler) >= 8 and len(fehler) > i * 0.5:
                print('🔴 Zu viele Fehler hintereinander — Abbruch. Netz? Dienst? Erst --probe versuchen.')
                break
            continue
        if not fertig and not f.get('einheiten'):
            antwort, werte, einheiten = struktur_pruefen(text)   # erste Antwort: hart prüfen
            f['einheiten'] = einheiten
            f['zeitraum'] = zeitraum_aus(antwort)
            print(f'   ✅ Antwortstruktur geprüft · Einheiten {json.dumps(einheiten)} · Zeitraum „{f["zeitraum"] or "?"}"')
        else:
            try:
                werte, _ = antwort_zu_zelle(json.loads(text))
            except (ValueError, TypeError) as e:
                print(f'   ❌ {z["land"]} {key}: {e} — Anfang: {text[:160]!r}')
                fehler.append(key)
                continue
        eintrag = dict(z); eintrag.update(werte)
        fertig[key] = eintrag
        n = len(zellen) - len(offen) + i + 1
        if (i + 1) % SICHERN_ALLE == 0 or i == len(offen) - 1:
            fortschritt_schreiben(f)
            je = (time.time() - start) / (i + 1)
            rest = int(je * (len(offen) - i - 1))
            print(f'   💾 {n}/{len(zellen)} Zellen · zuletzt {z["land"]} · noch ca. {rest // 60} min')
        if i < len(offen) - 1:
            time.sleep(PAUSE_S)

    # Ausgabe: ALLE bisher geholten Zellen — ein Teil-Lauf (Ländercodes) lässt die übrigen Länder
    # in der Datei stehen, ein Fehlversuch löscht nie Daten.
    alle = [fertig[k] for k in fertig]
    if not alle:
        sys.exit('🔴 Keine einzige Zelle geholt — nichts geschrieben.')
    kb = ausgabe_schreiben(alle, f.get('einheiten', {}), f.get('zeitraum', ''), raster)
    print(f'\n🟢 {OUT.name}: {len(alle)} Zellen, {kb} KB → {OUT}')
    zusammenfassung(alle)
    if kb > 4000:
        print('⚠️  Datei > 4 MB — sie geht ans iPhone; --raster 2 wählen')
    if fehler:
        print(f'🔴 {len(fehler)} Zellen fehlgeschlagen — später erneut: python3 fetch-klima.py (macht weiter)')
        sys.exit(1)
    fehlend = [z for z in zellen if f'{z["lon"]},{z["lat"]}' not in fertig]
    if fehlend:
        print(f'ℹ️  {len(fehlend)} Zellen fehlen noch — python3 fetch-klima.py erneut ausführen')
    print('Danach: ./deploy.sh  (kopiert die Datei ins Bundle)')


if __name__ == '__main__':
    main()
