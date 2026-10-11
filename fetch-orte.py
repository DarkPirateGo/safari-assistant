#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
# Safari Assistant — fetch-orte.py v2026-07-20-1
#
# Baut den OFFLINE-Ortsindex für die Kartensuche der POI-Karte:
# lädt die GeoNames-Länderdumps der 16 Reiseländer und schreibt
# data/orte.json (Orte, Berge/Pässe, Seen/Wasserfälle, Flughäfen).
#
# Daten: GeoNames (geonames.org), Lizenz CC BY 4.0 — Attribution steht
# in der Ausgabedatei. Straßennamen sind bewusst NICHT enthalten
# (dafür nutzt die Suche online Nominatim).
#
# Nutzung:  im Projektordner: python3 fetch-orte.py
#           Einzelne Länder:  python3 fetch-orte.py NA BW
# Danach:   ./deploy.sh (kopiert data/ ins Bundle), Server neu starten
# ═══════════════════════════════════════════════════════════════════
import io, json, sys, time, urllib.request, zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = BASE / 'data' / 'orte.json'

LAENDER = [
    ('ZA', 'Südafrika'), ('NA', 'Namibia'), ('BW', 'Botswana'), ('ZM', 'Sambia'),
    ('ZW', 'Zimbabwe'), ('MZ', 'Mosambik'), ('MW', 'Malawi'), ('TZ', 'Tansania'),
    ('KE', 'Kenia'), ('UG', 'Uganda'), ('RW', 'Ruanda'), ('BI', 'Burundi'),
    ('ET', 'Äthiopien'), ('AO', 'Angola'), ('SZ', 'Eswatini'), ('LS', 'Lesotho'),
]

DUMP_URL = 'https://download.geonames.org/export/dump/{cc}.zip'

# GeoNames feature class/code → Kategorie (typ-Kürzel spart Platz: 100k+ Einträge)
#   o = Ort  ·  b = Berg/Pass  ·  w = See/Wasserfall  ·  f = Flughafen
T_CODES = {'MT', 'MTS', 'PK', 'PASS', 'VLC', 'DUNE', 'GRGE'}
H_CODES = {'LK', 'LKS', 'FLLS', 'RSV'}
S_CODES = {'AIRP'}


def kategorie(fclass, fcode):
    if fclass == 'P':
        return 'o'
    if fclass == 'T' and fcode in T_CODES:
        return 'b'
    if fclass == 'H' and fcode in H_CODES:
        return 'w'
    if fclass == 'S' and fcode in S_CODES:
        return 'f'
    return None


def lade_land(cc):
    for versuch in range(3):
        try:
            req = urllib.request.Request(DUMP_URL.format(cc=cc), headers={
                'User-Agent': 'SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fetch-orte'})
            with urllib.request.urlopen(req, timeout=180) as r:
                daten = r.read()
            with zipfile.ZipFile(io.BytesIO(daten)) as z:
                return z.read(f'{cc}.txt').decode('utf-8', 'ignore')
        except Exception as e:
            print(f'   ⚠️  Versuch {versuch + 1}: {e}')
            time.sleep(15)
    raise RuntimeError(f'GeoNames-Download für {cc} fehlgeschlagen')


def parse_land(txt, land_idx):
    orte = []
    for zeile in txt.split('\n'):
        f = zeile.split('\t')
        if len(f) < 15:
            continue
        typ = kategorie(f[6], f[7])
        if not typ:
            continue
        name = f[1].strip()
        if not name:
            continue
        try:
            lat, lng = round(float(f[4]), 4), round(float(f[5]), 4)
            pop = int(f[14] or 0)
        except ValueError:
            continue
        orte.append([name, lat, lng, land_idx, typ, pop])
    return orte


def main():
    nur = {a.upper() for a in sys.argv[1:]}
    ziel = [(i, cc, n) for i, (cc, n) in enumerate(LAENDER) if not nur or cc in nur]
    alt = []
    if nur and OUT.exists():  # Teil-Lauf: andere Länder aus Bestand übernehmen
        try:
            j = json.load(open(OUT))
            behalten = {i for i, (cc, n) in enumerate(LAENDER) if cc not in nur}
            alt = [o for o in j.get('orte', []) if o[3] in behalten]
        except Exception:
            print('⚠️  Bestehende orte.json unlesbar — wird komplett neu geschrieben')

    orte, fehler = list(alt), []
    for idx, cc, land in ziel:
        print(f'⬇️  {land} ({cc}) — GeoNames...')
        try:
            txt = lade_land(cc)
        except RuntimeError as e:
            print(f'   ❌ {e}'); fehler.append(cc); continue
        neu = parse_land(txt, idx)
        stats = {}
        for o in neu:
            stats[o[4]] = stats.get(o[4], 0) + 1
        print(f'   ✅ {len(neu)} Einträge — 🏘 {stats.get("o", 0)} · ⛰ {stats.get("b", 0)}'
              f' · 💧 {stats.get("w", 0)} · ✈ {stats.get("f", 0)}')
        if not neu:
            print(f'   ⚠️  0 Einträge für {land} — Dump/Filter prüfen (nie still scheitern)')
        orte += neu

    # Ranking-Vorarbeit: bevölkerungsreichste zuerst → Server-Suche darf früh abbrechen
    orte.sort(key=lambda o: -o[5])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({
        'attribution': 'Ortsdaten: GeoNames (geonames.org), CC BY 4.0 — Stand ' + time.strftime('%Y-%m'),
        'laender': [n for cc, n in LAENDER],
        'orte': orte,
    }, ensure_ascii=False, separators=(',', ':')))
    mb = OUT.stat().st_size / 1024 / 1024
    print(f'\n🟢 {OUT.name}: {len(orte)} Einträge, {mb:.1f} MB → {OUT}')
    print('Danach: ./deploy.sh + Server neu starten (Suche lädt den Index beim ersten Zugriff)')
    if fehler:
        print(f'🔴 Fehlgeschlagen: {" ".join(fehler)} — später erneut: python3 fetch-orte.py {" ".join(fehler)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
