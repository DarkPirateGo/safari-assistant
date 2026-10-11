#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-pois.py v2026-07-20-1
#
# Holt Reise-POIs für die 16 Länder aus OpenStreetMap (Overpass) und
# schreibt pro Land eine importfertige Datei nach POIs/<Land>-osm.json
# (Format = Overpass-Rohdaten, exakt was parseOverpass() in pois.html
# erwartet; eine Datei = ein Layer pro Land — TODO §3).
#
# Kategorien (deckungsgleich mit osmType() in pois.html):
#   🏥 hospital/clinic/doctors/pharmacy   🐾 veterinary (auch healthcare=)
#   ⛽ fuel      💧 drinking_water/water_point + Brunnen/Bohrloch
#   🏕️ camp_site/caravan_site            🔧 car_repair/car_parts
#   🛂 border_control
#
# Daten: © OpenStreetMap contributors (ODbL). Tags werden auf das vom
# Import genutzte Minimum verschlankt (Name/Betreiber/Zeiten/Telefon +
# Kategorie-Tags) — hält die Dateien und IndexedDB klein.
#
# Nutzung:  im Projektordner: python3 fetch-pois.py
#           Einzelne Länder:  python3 fetch-pois.py NA BW
# Danach:   Dateien in der POI-Karte über den Import-Tab laden
#           (jede Datei wird ein eigener, togglebarer Layer)
# ═══════════════════════════════════════════════════════════════════
import json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUTDIR = BASE / 'POIs'

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

# Nur diese Tags überleben die Verschlankung — alles, was parseOverpass()/osmType() liest
TAG_WHITELIST = ('name', 'name:en', 'operator', 'opening_hours', 'phone',
                 'amenity', 'shop', 'tourism', 'man_made', 'healthcare',
                 'emergency', 'barrier')

WARN_PUNKTE = 30000  # darüber: Hinweis, dass der iPhone-Import träge werden kann


def overpass_query(cc):
    return f'''[out:json][timeout:300];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
(
  nwr(area.a)[amenity~"^(hospital|clinic|doctors|pharmacy|veterinary|fuel|drinking_water|water_point|border_control)$"];
  nwr(area.a)[healthcare=veterinary];
  nwr(area.a)[shop~"^(car_repair|car_parts)$"];
  nwr(area.a)[tourism~"^(camp_site|caravan_site)$"];
  nwr(area.a)[man_made~"^(water_well|borehole)$"];
  nwr(area.a)[barrier=border_control];
);
out center;'''


def fetch(cc):
    body = urllib.parse.urlencode({'data': overpass_query(cc)}).encode()
    letzte = None
    for versuch in range(4):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=body, headers={
                    'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-pois'})
                with urllib.request.urlopen(req, timeout=360) as r:
                    return json.load(r)
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
        pause = 60 * (versuch + 1)
        print(f'   ⏳ Runde {versuch + 1} erfolglos — {pause}s Pause...')
        time.sleep(pause)
    raise RuntimeError(f'Overpass nicht erreichbar: {letzte}')


def kategorie(tags):
    """Spiegel von osmType() in pois.html — nur für die Zusammenfassung."""
    a, s, t = tags.get('amenity', ''), tags.get('shop', ''), tags.get('tourism', '')
    m, h = tags.get('man_made', ''), tags.get('healthcare', '')
    if a == 'veterinary' or h == 'veterinary': return '🐾 Tierarzt'
    if a in ('hospital', 'clinic', 'doctors', 'pharmacy') or h: return '🏥 Medizin'
    if a == 'fuel': return '⛽ Tanken'
    if a in ('drinking_water', 'water_point') or m in ('water_well', 'borehole') \
       or tags.get('emergency') == 'drinking_water': return '💧 Wasser'
    if t in ('camp_site', 'caravan_site'): return '🏕️ Camp'
    if s in ('car_repair', 'car_parts'): return '🔧 Werkstatt'
    if a == 'border_control' or tags.get('barrier') == 'border_control': return '🛂 Grenze'
    return '❓ Sonstige'


def verschlanken(daten):
    """Elemente aufs Import-Minimum reduzieren (Koordinate + Whitelist-Tags)."""
    elems, stats = [], {}
    for el in daten.get('elements', []):
        lat = el.get('lat', (el.get('center') or {}).get('lat'))
        lon = el.get('lon', (el.get('center') or {}).get('lon'))
        if lat is None or lon is None:
            continue
        tags = {k: v for k, v in (el.get('tags') or {}).items() if k in TAG_WHITELIST}
        if not tags:
            continue
        elems.append({'type': el.get('type', 'node'), 'id': el.get('id', 0),
                      'lat': lat, 'lon': lon, 'tags': tags})
        k = kategorie(tags)
        stats[k] = stats.get(k, 0) + 1
    return elems, stats


def main():
    nur = {a.upper() for a in sys.argv[1:]}
    laender = [(cc, n) for cc, n in LAENDER if not nur or cc in nur]
    OUTDIR.mkdir(exist_ok=True)
    fehler = []
    for cc, land in laender:
        print(f'⬇️  {land} ({cc}) — Overpass...')
        try:
            daten = fetch(cc)
        except RuntimeError as e:
            print(f'   ❌ {e}'); fehler.append(cc); continue
        elems, stats = verschlanken(daten)
        out = OUTDIR / f'{land}-osm.json'
        out.write_text(json.dumps(
            {'hinweis': '© OpenStreetMap contributors (ODbL) 1.0 https://opendatacommons.org/licenses/odbl/1-0/ — erzeugt von fetch-pois.py, Stand ' +
                        time.strftime('%Y-%m'), 'elements': elems},
            ensure_ascii=False, separators=(',', ':')))
        kb = out.stat().st_size // 1024
        zusammenfassung = ' · '.join(f'{k} {n}' for k, n in sorted(stats.items())) or 'nichts'
        print(f'   ✅ {out.name}: {len(elems)} POIs, {kb} KB — {zusammenfassung}')
        if not elems:
            print(f'   ⚠️  0 POIs für {land} — Query/Datenlage prüfen (nie still scheitern)')
        if len(elems) > WARN_PUNKTE:
            print(f'   ⚠️  > {WARN_PUNKTE} POIs — Import am iPhone kann träge werden (Layer einzeln togglen hilft)')
        time.sleep(10)  # Overpass-Höflichkeit

    print('\n🟢 Fertig. Import: POI-Karte → Import-Tab → Datei(en) aus POIs/ laden')
    print('   (jede Datei wird ein eigener, togglebarer Layer; Distanzsuche über 🧭)')
    if fehler:
        print(f'🔴 Fehlgeschlagen: {" ".join(fehler)} — später erneut: python3 fetch-pois.py {" ".join(fehler)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
