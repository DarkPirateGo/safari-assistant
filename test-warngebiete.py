# Ausgeführter Test der Gebietserkennung aus den amtlichen Warntexten. Die drei Textformen sind den
# am 13.09.2026 WÖRTLICH geprüften Antworten des Auswärtigen Amts nachgebaut (Kenia, Mosambik,
# Äthiopien) — sie unterscheiden sich im Aufbau, und genau daran scheitert naives Zerlegen.
# Wird von test-app.js (Sektion 59) ausgeführt.
import sys, importlib.util
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location('srv', SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []

KENIA = m.html_zu_text(
    '<p><strong>Vor Reisen in die Countys Mandera, Wajir, Garissa und Lamu im Osten Kenias, mit Ausnahme '
    'von Lamu Island und Manda Island, wird gewarnt.</strong></p>'
    '<p><strong>Von Reisen in die Countys Baringo, West Pokot und Turkana sowie in die Gebiete nördlich '
    'des Tana River County wird dringend abgeraten.</strong></p>'
    '<p><strong>Von nicht notwendigen Reisen nach Lamu Island wird abgeraten.</strong></p>'
    '<h3>Terrorismus</h3><p>Gehört nicht mehr zum Warnblock: Nairobi, Mombasa.</p>')
MOSAMBIK = m.html_zu_text(
    '<p><strong>Vor Reisen in die</strong></p><ul>'
    '<li><strong>Provinz Cabo Delgado, in alle Distrikte, </strong>außer Pemba,</li>'
    '<li><strong>Provinz Nampula, in die Distrikte Memba und Erati,</strong></li></ul>'
    '<p><strong>wird gewarnt.</strong></p>')
AETHIOPIEN = m.html_zu_text(
    '<p><strong>Vor Reisen in die folgenden Regionen und Gebiete wird gewarnt:</strong></p><ul>'
    '<li><strong>die Regionalstaaten Amhara, Gambela, Oromia, (mit Ausnahme der Route von Addis Abeba '
    'nach Hawassa)</strong></li>'
    '<li><strong>das Grenzgebiet zu Eritrea (ca. 10 km).</strong></li></ul>'
    '<p><strong>Von nicht notwendigen Reisen in alle übrigen Gebiete wird abgeraten.</strong></p>')
VOK_KE = {'Mandera': 4, 'Wajir': 4, 'Garissa': 4, 'Lamu': 4, 'Baringo': 4, 'West Pokot': 4, 'Pokot': 6,
          'Turkana': 4, 'Tana River': 4, 'Nairobi': 4, 'Mombasa': 4}
VOK_MZ = {'Cabo Delgado': 4, 'Nampula': 4, 'Niassa': 4, 'Pemba': 6, 'Memba': 6, 'Erati': 6}
VOK_ET = {'Amhara': 4, 'Gambela': 4, 'Oromia': 4, 'Tigray': 4, 'Addis Abeba': 4, 'Hawassa': 6}

# 1. Stufen: die schärfere Formel darf nicht als die mildere zählen
for satz, erwartet in (('… wird gewarnt.', 3), ('… wird dringend abgeraten.', 2),
                       ('… wird abgeraten.', 1), ('Beachten Sie die Lage.', 0)):
    if m.warnstufe_der_zeile(satz) != erwartet:
        f.append('Stufe von %r = %s' % (satz, m.warnstufe_der_zeile(satz)))

# 2. Kenia: ein Satz je Stufe, Lamu bleibt gewarnt (nur die Inseln sind ausgenommen)
ke, ke_aus, ke_offen = m.warngebiete_aus_text(KENIA, VOK_KE)
stufen = {g['name']: g['stufe'] for g in ke}
for name in ('Mandera', 'Wajir', 'Garissa', 'Lamu'):
    if stufen.get(name) != 3:
        f.append('Kenia: %s sollte Stufe 3 haben, hat %s' % (name, stufen.get(name)))
for name in ('Baringo', 'West Pokot', 'Turkana', 'Tana River'):
    if stufen.get(name) != 2:
        f.append('Kenia: %s sollte Stufe 2 haben, hat %s' % (name, stufen.get(name)))
if 'Nairobi' in stufen or 'Mombasa' in stufen:
    f.append('Kenia: Ortsnamen aus dem Fließtext hinter dem Warnblock wurden mitgenommen')
if 'Pokot' in stufen:
    f.append('Kenia: „Pokot" statt „West Pokot" — der längere Name muss gewinnen')
tana = next((g for g in ke if g['name'] == 'Tana River'), None)
if not tana or not tana['einschraenkung']:
    f.append('Kenia: „nördlich des Tana River County" nicht als Teilgebiet markiert')

# 3. Mosambik: Aufzählung VOR der Stufenformel; Distrikte schlagen die Provinz, Pemba ist ausgenommen
mz, mz_aus, mz_offen = m.warngebiete_aus_text(MOSAMBIK, VOK_MZ)
namen_mz = {g['name'] for g in mz}
if namen_mz != {'Cabo Delgado', 'Memba', 'Erati'}:
    f.append('Mosambik: %s (erwartet Cabo Delgado, Memba, Erati)' % sorted(namen_mz))
if 'Pemba' not in mz_aus:
    f.append('Mosambik: „außer Pemba" wurde nicht als Ausnahme erkannt')
if mz_offen:
    f.append('Mosambik: Satzklammern als ungelöste Gebiete gemeldet: %s' % [u['satz'] for u in mz_offen])

# 4. Äthiopien: Aufzählung NACH der Stufenformel; Grenzgebiet bleibt ungelöst und wird gemeldet
et, et_aus, et_offen = m.warngebiete_aus_text(AETHIOPIEN, VOK_ET)
namen_et = {g['name'] for g in et}
if namen_et != {'Amhara', 'Gambela', 'Oromia'}:
    f.append('Äthiopien: %s (erwartet Amhara, Gambela, Oromia)' % sorted(namen_et))
if 'Addis Abeba' not in et_aus or 'Hawassa' not in et_aus:
    f.append('Äthiopien: Ausnahmen nicht erkannt: %s' % et_aus)
if not any('Eritrea' in u['satz'] for u in et_offen):
    f.append('Äthiopien: „Grenzgebiet zu Eritrea" muss als ungelöst gemeldet werden, nicht verschwinden')
if any(u['satz'].rstrip().endswith(':') for u in et_offen):
    f.append('Äthiopien: Einleitungszeile als ungelöstes Gebiet gezählt')

# 4b. Echte Sätze aus dem Lauf vom 15.09.2026: Nennt der Satz Untereinheiten (Distrikte, Zonen)
# oder eine Himmelsrichtung, darf die übergeordnete Fläche nicht ohne Markierung gezeichnet werden.
ECHT = [
    ('Mosambik', '• Provinz Nampula, in die Distrikte Memba und Erati,', {'Provinz Nampula': 4}, 'Provinz Nampula'),
    ('Äthiopien', '• die Regionalstaaten Tigray, Amhara und Somali sowie die an den Regionalstaat Tigray '
                  'angrenzenden Zonen Kilbet Rasu und Fanti Rasu des Regionalstaates Afar;', {'Afar': 4, 'Tigray': 4}, 'Afar'),
    ('Kenia', 'Von Reisen in die Countys Baringo und Turkana und in den Norden des Countys Tana River '
              'wird dringend abgeraten', {'Tana River': 4, 'Baringo': 4}, 'Tana River'),
]
for land, satz, vok, pruef in ECHT:
    text = satz if m.warnstufe_der_zeile(satz) else ('Vor Reisen in die\n' + satz + '\nwird gewarnt.')
    g, _, _ = m.warngebiete_aus_text(text, vok)
    treffer = next((x for x in g if x['name'] == pruef), None)
    if not treffer:
        f.append('%s: %s nicht erkannt' % (land, pruef))
    elif not treffer['einschraenkung']:
        f.append('%s: %s wird ohne Markierung als ganze Fläche gezeichnet, obwohl der Satz nur '
                 'einen Teil meint' % (land, pruef))

# 4c. Die Markierung ⚑ hängt am GEBIET, nicht am Satz (Befund 18.09.2026: 19 von 19 markiert, 13 zu
# Unrecht). Die drei echten Warnblöcke vom 18.09. gegen ein Verzeichnis mit den Ebenen des OSM-Vorrats
# (auch die Nebentreffer, die dort wirklich vorkommen: „Tana River County", „Pokot North", „Addis Abeba").
VOK_KE2 = {'Mandera': 4, 'Wajir': 4, 'Garissa': 4, 'Lamu': 4, 'Lamu East': 6, 'Baringo': 4, 'West Pokot': 4,
           'Pokot North': 6, 'Turkana': 4, 'Tana River': 4, 'Tana River County': 4, 'Nairobi': 4}
VOK_MZ2 = {'Provinz Cabo Delgado': 4, 'Cabo Delgado': 4, 'Provinz Nampula': 4, 'Nampula': 4,
           'Provinz Niassa': 4, 'Niassa': 4, 'Mecula': 6, 'Marrupa': 6}
VOK_ET2 = {'Tigray': 4, 'Amhara': 4, 'Benishangul-Gumuz': 4, 'Gambela': 4, 'Somali': 4, 'Afar': 4, 'Oromia': 4,
           'Addis Abeba': 4, 'Arsi Negele': 6}
KENIA2 = ('Vor Reisen in die Countys Mandera, Wajir, Garissa und Lamu im Osten Kenias, mit Ausnahme von Lamu '
          'Island und Manda Island, wird gewarnt.\n'
          'Von Reisen in die Countys Baringo, West Pokot und Turkana der North-Rift-Region und in den Norden des '
          'Countys Tana River, einschließlich der Fernstraße A3 im County Tana River, wird dringend abgeraten.')
MOSAMBIK2 = ('Vor Reisen in die\n• Provinz Cabo Delgado, in alle Distrikte, außer Pemba,\n'
             '• Provinz Nampula, in die Distrikte Memba und Erati,\n'
             '• Provinz Niassa, in die Distrikte Mecula und Marrupa,\nwird gewarnt.')
AETHIOPIEN2 = ('Vor Reisen in die folgenden Regionen und Gebiete wird gewarnt:\n'
               '• die Regionalstaaten Tigray, Amhara, Benishangul-Gumuz, Gambela und Somali sowie die an den '
               'Regionalstaat Tigray angrenzenden Zonen Kilbet Rasu und Fanti Rasu des Regionalstaates Afar;\n'
               '• alle Zonen westlich von Addis Abeba des Regionalstaates Oromia (einschließlich der Zonen West '
               'Shewa, South West Shewa und North Shewa), sowie die Zone Arsi des Regionalstaates Oromia;\n'
               '• das Grenzgebiet zu Eritrea, Südsudan, Sudan und Kenia (ca. 10 km zum Grenzverlauf).')
MARKIERT = {'Lamu', 'Tana River', 'Provinz Cabo Delgado', 'Provinz Nampula', 'Afar', 'Oromia'}
FREI = {'Mandera', 'Wajir', 'Garissa', 'Baringo', 'West Pokot', 'Turkana', 'Mecula', 'Marrupa',
        'Tigray', 'Amhara', 'Benishangul-Gumuz', 'Gambela', 'Somali'}
flags = {}
for text, vok in ((KENIA2, VOK_KE2), (MOSAMBIK2, VOK_MZ2), (AETHIOPIEN2, VOK_ET2)):
    for g in m.warngebiete_aus_text(text, vok)[0]:
        flags[g['name']] = g['einschraenkung']
for name in sorted(MARKIERT):
    if flags.get(name) is not True:
        f.append('⚑ fehlt bei %s (%s)' % (name, flags.get(name)))
for name in sorted(FREI):
    if flags.get(name) is not False:
        f.append('⚑ zu Unrecht bei %s (%s)' % (name, flags.get(name)))
if 'Addis Abeba' in flags:
    f.append('„westlich von Addis Abeba" macht Addis Abeba zum Warngebiet — es ist der Bezugspunkt')
if len(flags) != 19:
    f.append('19 Gebiete erwartet, %d gefunden: %s' % (len(flags), sorted(flags)))

def _flags(text, vok):
    return {x['name']: x['einschraenkung'] for x in m.warngebiete_aus_text(text, vok)[0]}

# Regel 2: Tigray steht im zweiten Teilsatz nur als Bezug („an den Regionalstaat Tigray angrenzenden")
g2 = _flags('Vor Reisen in die folgenden Gebiete wird gewarnt:\n• die an den Regionalstaat Tigray angrenzenden '
            'Zonen Kilbet Rasu und Fanti Rasu des Regionalstaates Afar;', VOK_ET2)
if 'Tigray' in g2:
    f.append('„an den Regionalstaat Tigray angrenzenden" macht Tigray zum Warngebiet')
if g2.get('Afar') is not True:
    f.append('Zonen des Regionalstaates Afar: Afar muss markiert sein (%s)' % g2)
# Regel 1: dasselbe Einheitswort, andere Ebene — die Distrikte sind selbst gemeint
g3 = _flags('Vor Reisen in die\n• Provinz Niassa, in die Distrikte Mecula und Marrupa,\nwird gewarnt.', VOK_MZ2)
if g3 != {'Mecula': False, 'Marrupa': False}:
    f.append('Distrikte Mecula und Marrupa: keine Markierung, keine Provinz — %s' % g3)
# Regel 3: Ausnahme ohne Gebietsnamen bindet an alle Gebiete des Teilsatzes
g4 = _flags('Vor Reisen in die Countys Mandera und Wajir, mit Ausnahme der Grenzorte, wird gewarnt.', VOK_KE2)
if g4 != {'Mandera': True, 'Wajir': True}:
    f.append('Ausnahme ohne Gebietsnamen muss alle Gebiete des Teilsatzes markieren: %s' % g4)
# Himmelsrichtung NACH dem Namen ist Ortsangabe, DAVOR Einschränkung
g5 = _flags('Vor Reisen in das County Garissa im Osten Kenias und in den Süden des Countys Wajir wird gewarnt.', VOK_KE2)
if g5 != {'Garissa': False, 'Wajir': True}:
    f.append('„im Osten Kenias" ist Ortsangabe, „den Süden des Countys Wajir" Einschränkung: %s' % g5)
# Ein Einschub erweitert nicht: Tana River bleibt markiert, obwohl es im Einschub ohne Richtung steht
g6 = _flags('Von Reisen in den Norden des Countys Tana River, einschließlich der Fernstraße A3 im County Tana '
            'River, wird dringend abgeraten.', VOK_KE2)
if g6 != {'Tana River': True}:
    f.append('Einschub „einschließlich …" darf die Markierung nicht aufheben: %s' % g6)
# … und er erbt die Einschränkung des Kerns nicht: ein im Einschub ganz genanntes County bleibt ganz
g7 = _flags('Von Reisen in den Norden des Countys Tana River, insbesondere in das County Garissa, wird abgeraten.', VOK_KE2)
if g7 != {'Tana River': True, 'Garissa': False}:
    f.append('Einschub „insbesondere …" erbt die Himmelsrichtung des Kerns nicht: %s' % g7)

# 5. Ohne Verzeichnis wird nichts erfunden
leer, leer_aus, leer_offen = m.warngebiete_aus_text(KENIA, {})
if leer:
    f.append('ohne Verzeichnis werden Gebiete erfunden: %s' % [g['name'] for g in leer])
if not leer_offen:
    f.append('ohne Verzeichnis müssen die Warnsätze als ungelöst gemeldet werden')

# 6. Leerer Text bringt weder Absturz noch Inhalt
for wert in ('', None, '   '):
    g, a, o = m.warngebiete_aus_text(wert, VOK_KE)
    if g or a or o:
        f.append('leerer Text liefert Inhalt: %r' % wert)

print('FEHLER: ' + ' | '.join(f) if f else 'OK')
sys.exit(1 if f else 0)
