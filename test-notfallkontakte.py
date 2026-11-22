# Ausgeführter Test von fetch-notfallkontakte.py ohne Netz: Overpass-Antworten werden nachgebaut.
# Nummern aus dem britischen Bereich für Film/Fernsehen (Ofcom 020 7946 0xxx) — keine echten Anschlüsse.
# Wird von test-app.js (Abschnitt 85) ausgeführt.
import sys, importlib.util
spec = importlib.util.spec_from_file_location('fnk', SKRIPT_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []

DATEN = {'elements': [
    {'type': 'node', 'id': 1, 'lat': -26.2040612, 'lon': 28.0473049,
     'tags': {'amenity': 'police', 'name': 'Testwache Nord', 'phone': '+44 20 7946 0001'}},
    {'type': 'way', 'id': 2, 'center': {'lat': -26.2040, 'lon': 28.0473},          # dieselbe Wache als Fläche
     'tags': {'amenity': 'police', 'name': 'Testwache Nord', 'phone': '+44 20 7946 0001'}},
    {'type': 'node', 'id': 3, 'lat': -33.5, 'lon': 18.5,
     'tags': {'amenity': 'fire_station', 'operator': 'Testfeuerwehr', 'contact:phone': '020 7946 0002; 020 7946 0003'}},
    {'type': 'node', 'id': 4, 'lat': -34.0, 'lon': 18.9, 'tags': {'office': 'security', 'name': 'Test Security'}},
    {'type': 'node', 'id': 5, 'lat': -34.1, 'lon': 19.0, 'tags': {'emergency': 'water_rescue', 'name': 'Seenot Test', 'phone': 'tel:<script>+44 20 7946 0004'}},
    {'type': 'node', 'id': 6, 'lat': -34.2, 'lon': 19.1, 'tags': {'amenity': 'cafe', 'name': 'kein Notfall'}},
    {'type': 'node', 'id': 7, 'tags': {'amenity': 'police', 'name': 'ohne Koordinaten'}},
    {'type': 'node', 'id': 8, 'lat': 95, 'lon': 18, 'tags': {'amenity': 'police', 'name': 'kaputt'}},
    {'type': 'node', 'id': 9, 'lat': -22.5, 'lon': 17.0, 'tags': {'amenity': 'ranger_station', 'phone': 'ask at gate'}},
    'kein dict',
]}
e = m.verdichten(DATEN, 'ZA')
if len(e) != 5: f.append(f'{len(e)} statt 5 Einträge: {e}')
p = [x for x in e if x[2] == 'p']
if len(p) != 1 or p[0] != [-26.20406, 28.0473, 'p', 'Testwache Nord', '+44 20 7946 0001', 'ZA']: f.append('Polizei: ' + str(p))
fw = [x for x in e if x[2] == 'f']
if not fw or fw[0][3] != 'Testfeuerwehr' or fw[0][4] != '020 7946 0002; 020 7946 0003': f.append('Feuerwehr: ' + str(fw))
s = [x for x in e if x[2] == 's']
if not s or s[0][4] != '': f.append('Sicherheitsfirma ohne Nummer: ' + str(s))
w = [x for x in e if x[2] == 'w']
if not w or '<' in w[0][4] or 'script' in w[0][4] or not w[0][4].endswith('7946 0004'): f.append('Nummer nicht gesäubert: ' + str(w))
r = [x for x in e if x[2] == 'r']
if not r or r[0][4] != '' or r[0][3] != '': f.append('Ranger: ' + str(r))

st = m.statistik(e)
if st['gesamt'] != 5 or st['mit_nummer'] != 3 or st['p'] != [1, 1] or st['s'] != [1, 0]: f.append('Statistik: ' + str(st))

alt = m.zusammenfuehren({}, {'ZA': e, 'NA': [[-22.0, 17.0, 'p', 'Alt NA', '+44 20 7946 0009', 'NA']]}, '2026-10-15')
neu = m.zusammenfuehren(alt, {'ZA': e[:1]}, '2026-11-21')
if [x for x in neu['k'] if x[5] == 'NA'] != [[-22.0, 17.0, 'p', 'Alt NA', '+44 20 7946 0009', 'NA']]: f.append('NA beim Teil-Abruf verloren')
if len([x for x in neu['k'] if x[5] == 'ZA']) != 1: f.append('ZA nicht ersetzt')
if neu['laender']['NA']['stand'] != '2026-10-15' or neu['laender']['ZA']['stand'] != '2026-11-21': f.append('Stand je Land: ' + str(neu['laender']))
if 'OpenStreetMap' not in neu['attribution'] or neu['felder'] != ['lat', 'lng', 'art', 'name', 'nummer', 'land']: f.append('Kopf der Datei')
kaputt = m.zusammenfuehren({'k': [None, [1, 2], 'x'], 'laender': 5}, {}, '2026-11-21')
if kaputt['k'] != []: f.append('kaputte Altdatei übernommen')

q = m.overpass_query('ZA')
for teil in ('"ISO3166-1"="ZA"', 'police|fire_station|ranger_station', 'office=security', 'ambulance_station|water_rescue|lifeguard_base', 'out center tags'):
    if teil not in q: f.append('Query ohne ' + teil)
if m.main(['XX']) != 2: f.append('unbekanntes Land nicht abgelehnt')
if set(m.AMTLICH) != {'ZA', 'BW', 'MW'} or not all(u.startswith('https://') for u in m.AMTLICH.values()): f.append('amtliche Quellen')
if 'data/sources' not in str(m.AMTLICH_DIR).replace('\\', '/'): f.append('Rohdateien nicht unter data/sources (gitignore)')

print('OK' if not f else 'FEHLER: ' + ' | '.join(f))
