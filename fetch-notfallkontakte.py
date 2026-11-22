#!/usr/bin/env python3
# ══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-notfallkontakte.py v2026-11-21-2
#
# Holt Notfall-Stellen mit Telefonnummer für die 16 Reiseländer aus OpenStreetMap
# (Overpass) und schreibt sie kompakt nach data/notfallkontakte.json. Das 🚨-Blatt am
# iPhone zeigt daraus die nächsten Stellen zur GPS-Position — offline.
#
# Arten (Kürzel in der Datei):
#   p 🚓 Polizei            amenity=police
#   f 🚒 Feuerwehr          amenity=fire_station
#   r 🦏 Ranger-Posten      amenity=ranger_station
#   s 🛡 Sicherheitsfirma    office=security
#   a 🚑 Rettungswache      emergency=ambulance_station
#   w ⚓ Seenotrettung      emergency=water_rescue / lifeguard_base
#
# Wichtig: OSM-Daten sind von Freiwilligen eingetragen und UNGEPRÜFT. Nummern können
# veraltet sein; Wachen-Nummern sind oft nicht besetzt. Im Notfall zuerst die Landes-
# nummer. Das Skript zählt je Land, wie viele Einträge eine Nummer haben.
#
# Daten: © OpenStreetMap contributors (ODbL).
#
# Nutzung:  python3 fetch-notfallkontakte.py            alle 16 Länder
#           python3 fetch-notfallkontakte.py ZA NA       nur diese (andere bleiben erhalten)
#           python3 fetch-notfallkontakte.py --amtlich   zusätzlich amtliche Wachen-Listen
#                     (ZA, BW, MW) als Rohdateien nach data/sources/notfall-amtlich/ —
#                     noch ohne Auswertung; die kommt, sobald ihr Aufbau bekannt ist.
# Danach:   ./deploy.sh
# ══════════════════════════════════════════════════════════════════
import json, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
ZIEL = BASE / 'data' / 'notfallkontakte.json'
AMTLICH_DIR = BASE / 'data' / 'sources' / 'notfall-amtlich'

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
# Amtliche Verzeichnisse (Recherche 21.11.2026). Nur Rohabruf — siehe Kopf.
AMTLICH = {
    'ZA': 'https://www.saps.gov.za/contacts/stationlist.php',
    'BW': 'https://www.police.gov.bw/index.php/page/28',
    'MW': 'https://police.gov.mw/structure/police-stations/contacts',
}
AGENT = 'SafariAssistant/2026.11 (+https://github.com/DarkPirateGo/safari-assistant) fetch-notfallkontakte'
TELEFON_TAGS = ('phone', 'contact:phone', 'contact:mobile', 'emergency:phone', 'phone:mobile')
ARTEN = ('p', 'f', 'r', 's', 'a', 'w')


def overpass_query(cc):
    return f'''[out:json][timeout:300];
area["ISO3166-1"="{cc}"][admin_level=2]->.a;
(
  nwr(area.a)[amenity~"^(police|fire_station|ranger_station)$"];
  nwr(area.a)[office=security];
  nwr(area.a)[emergency~"^(ambulance_station|water_rescue|lifeguard_base)$"];
);
out center tags;'''


def art(tags):
    a, e = tags.get('amenity', ''), tags.get('emergency', '')
    if a == 'police': return 'p'
    if a == 'fire_station': return 'f'
    if a == 'ranger_station': return 'r'
    if tags.get('office') == 'security': return 's'
    if e == 'ambulance_station': return 'a'
    if e in ('water_rescue', 'lifeguard_base'): return 'w'
    return ''


def nummer(tags):
    """Erste vorhandene Telefon-Angabe; mehrere Nummern („a; b") bleiben als Text zusammen (das iPhone
    macht jede einzeln wählbar). Nur Ziffern, +, Leerzeichen, Trenner — alles andere fliegt raus."""
    for k in TELEFON_TAGS:
        v = str(tags.get(k) or '').strip()
        if v:
            v = re.sub(r'[^0-9+;,/ ()\-.]', '', v)
            v = re.sub(r'\s+', ' ', v).strip(' ;,/')
            if re.search(r'\d{3}', v):
                return v[:60]
    return ''


def name(tags, a):
    for k in ('name', 'name:en', 'official_name', 'operator'):
        v = str(tags.get(k) or '').strip()
        if v:
            return re.sub(r'\s+', ' ', v)[:80]
    return ''


def verdichten(daten, cc):
    """Overpass-Antwort → Liste [lat, lng, art, name, nummer, cc] (5 Nachkommastellen ≈ 1 m)."""
    aus, gesehen = [], set()
    for el in (daten or {}).get('elements', []) or []:
        if not isinstance(el, dict):
            continue
        lat = el.get('lat', (el.get('center') or {}).get('lat'))
        lon = el.get('lon', (el.get('center') or {}).get('lon'))
        tags = el.get('tags') or {}
        a = art(tags)
        if lat is None or lon is None or not a:
            continue
        try:
            lat, lon = round(float(lat), 5), round(float(lon), 5)
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        n, nr = name(tags, a), nummer(tags)
        schluessel = (a, n.lower(), nr, round(lat, 3), round(lon, 3))   # Knoten + Fläche derselben Wache
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        aus.append([lat, lon, a, n, nr, cc])
    return aus


def statistik(eintraege):
    st = {'gesamt': len(eintraege), 'mit_nummer': sum(1 for e in eintraege if e[4])}
    for a in ARTEN:
        teil = [e for e in eintraege if e[2] == a]
        if teil:
            st[a] = [len(teil), sum(1 for e in teil if e[4])]
    return st


def zusammenfuehren(alt, neu_je_land, stand):
    """Neue Länder ersetzen ihre alten Einträge; alle übrigen Länder bleiben, wie sie waren."""
    alt = alt if isinstance(alt, dict) else {}
    laender = dict(alt['laender']) if isinstance(alt.get('laender'), dict) else {}
    k = [e for e in (alt.get('k') or []) if isinstance(e, list) and len(e) == 6 and e[5] not in neu_je_land]
    for cc, eintraege in neu_je_land.items():
        k.extend(eintraege)
        laender[cc] = dict(statistik(eintraege), stand=stand)
    k.sort(key=lambda e: (e[5], e[2], e[0], e[1]))
    return {
        'attribution': '© OpenStreetMap contributors (ODbL) https://opendatacommons.org/licenses/odbl/1-0/ — ungeprüft, erzeugt von fetch-notfallkontakte.py',
        'felder': ['lat', 'lng', 'art', 'name', 'nummer', 'land'],
        'arten': {'p': 'Polizei', 'f': 'Feuerwehr', 'r': 'Ranger', 's': 'Sicherheitsfirma', 'a': 'Rettungswache', 'w': 'Seenotrettung'},
        'stand': stand, 'laender': laender, 'k': k,
    }


def holen(url, daten=None, timeout=360):
    req = urllib.request.Request(url, data=daten, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def overpass(cc):
    body = urllib.parse.urlencode({'data': overpass_query(cc)}).encode()
    letzte = None
    for versuch in range(4):
        for url in MIRRORS:
            try:
                return json.loads(holen(url, body))
            except urllib.error.HTTPError as e:
                letzte = e
                if e.code in (429, 504):
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


def amtlich_holen():
    AMTLICH_DIR.mkdir(parents=True, exist_ok=True)
    for cc, url in AMTLICH.items():
        try:
            roh = holen(url, timeout=60)
            ziel = AMTLICH_DIR / f'{cc}.html'
            ziel.write_bytes(roh)
            print(f'   ✅ amtlich {cc}: {len(roh) // 1024} KB → {ziel.relative_to(BASE)}')
        except Exception as e:
            print(f'   ⚠️  amtlich {cc}: {e}')


def main(argv):
    amtlich = '--amtlich' in argv
    nur = {a.upper() for a in argv if not a.startswith('--')}
    unbekannt = nur - {cc for cc, _ in LAENDER}
    if unbekannt:
        print('❌ Unbekannte Länderkürzel: ' + ' '.join(sorted(unbekannt)))
        return 2
    laender = [(cc, n) for cc, n in LAENDER if not nur or cc in nur]
    stand = time.strftime('%Y-%m-%d')
    try:
        alt = json.loads(ZIEL.read_text(encoding='utf-8')) if ZIEL.exists() else {}
    except Exception:
        alt = {}
    neu, fehler = {}, []
    for cc, land in laender:
        print(f'⬇️  {land} ({cc}) — Overpass...')
        try:
            e = verdichten(overpass(cc), cc)
        except RuntimeError as ex:
            print(f'   ❌ {ex}'); fehler.append(cc); continue
        st = statistik(e)
        teile = ' · '.join(f'{a} {st[a][0]} ({st[a][1]} mit Nr.)' for a in ARTEN if a in st) or 'nichts'
        print(f'   ✅ {st["gesamt"]} Stellen, davon {st["mit_nummer"]} mit Nummer — {teile}')
        if not e:
            print(f'   ⚠️  0 Stellen für {land} — Query/Datenlage prüfen')
        neu[cc] = e
        time.sleep(10)   # Overpass-Höflichkeit
    if neu:
        ZIEL.parent.mkdir(exist_ok=True)
        daten = zusammenfuehren(alt, neu, stand)
        ZIEL.write_text(json.dumps(daten, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(f'\n💾 {ZIEL.relative_to(BASE)}: {len(daten["k"])} Stellen, {ZIEL.stat().st_size // 1024} KB')
    if amtlich:
        print('\n⬇️  Amtliche Wachen-Listen (Rohabruf)...')
        amtlich_holen()
    print('\n🟢 Fertig. Danach ./deploy.sh — das iPhone holt die Datei beim nächsten Öffnen von 🚨.')
    if fehler:
        print(f'🔴 Fehlgeschlagen: {" ".join(fehler)} — später erneut: python3 fetch-notfallkontakte.py {" ".join(fehler)}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
