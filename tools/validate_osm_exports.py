#!/usr/bin/env python3
"""Structural check of POIs/*-osm.json: only genuine Overpass objects, whitelisted tags, inside the country bbox.

Paths are resolved against the repository root (the parent of tools/), so it can be run from anywhere.
No POIs/*-osm.json files -> nothing to check, exit 0.  Stdlib only, Python 3.9+.
"""
import glob
import json
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WL = {'name', 'name:en', 'operator', 'opening_hours', 'phone', 'amenity', 'shop', 'tourism', 'man_made',
      'healthcare', 'emergency', 'barrier'}
BBOX = {'Südafrika': (-47.5, -22.0, 16.0, 38.5), 'Namibia': (-29.5, -16.9, 11.5, 25.5), 'Botswana': (-27.0, -17.7, 19.8, 29.5),
        'Sambia': (-18.2, -8.1, 21.9, 33.8), 'Zimbabwe': (-22.5, -15.5, 25.2, 33.2), 'Mosambik': (-27.0, -10.3, 30.1, 41.0),
        'Malawi': (-17.2, -9.3, 32.6, 36.0), 'Tansania': (-11.8, -0.9, 29.2, 40.6), 'Kenia': (-4.8, 5.1, 33.8, 42.0),
        'Uganda': (-1.6, 4.3, 29.5, 35.1), 'Ruanda': (-2.9, -1.0, 28.8, 31.0), 'Burundi': (-4.5, -2.3, 28.9, 30.9),
        'Äthiopien': (3.3, 15.0, 32.9, 48.1), 'Angola': (-18.1, -4.3, 11.6, 24.2), 'Eswatini': (-27.4, -25.7, 30.7, 32.2),
        'Lesotho': (-30.7, -28.5, 26.9, 29.5)}

files = sorted(glob.glob(os.path.join(ROOT, 'POIs', '*-osm.json')))
if not files:
    print('validate_osm_exports: keine POIs/*-osm.json - nichts zu prüfen / no POIs/*-osm.json - nothing to check')
    sys.exit(0)
bad = 0
for f in files:
    rel = os.path.relpath(f, ROOT).replace(os.sep, '/')
    land = unicodedata.normalize('NFC', os.path.basename(f)[:-len('-osm.json')])   # macOS may store names decomposed
    try:
        with open(f, encoding='utf-8') as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        print('%-28s  not readable as JSON: %s' % (rel, e))
        bad += 1
        continue
    errs = []
    if not isinstance(d, dict) or set(d) != {'hinweis', 'elements'} or 'OpenStreetMap' not in str(d.get('hinweis', '')):
        errs.append('top-level keys/attribution unexpected: %s' % (sorted(d) if isinstance(d, dict) else type(d).__name__))
        d = d if isinstance(d, dict) else {}
    s, n, w, e = BBOX.get(land, (-90, 90, -180, 180))
    seen = set()
    elements = d.get('elements', [])
    for el in elements if isinstance(elements, list) else []:
        if not isinstance(el, dict):
            errs.append('element is not an object')
            continue
        k = (el.get('type'), el.get('id'))
        if set(el) != {'type', 'id', 'lat', 'lon', 'tags'}:
            errs.append('keys %s' % sorted(el))
        elif el['type'] not in ('node', 'way', 'relation') or not isinstance(el['id'], int) or el['id'] <= 0:
            errs.append('not an OSM object %s' % (k,))
        elif not isinstance(el['tags'], dict) or set(el['tags']) - WL:
            errs.append('%s extra tags %s' % (k, sorted(set(el['tags']) - WL) if isinstance(el['tags'], dict) else '?'))
        elif not (s - 1 <= el['lat'] <= n + 1 and w - 1 <= el['lon'] <= e + 1):
            errs.append('%s outside %s bbox %.4f,%.4f' % (k, land, el['lat'], el['lon']))
        elif k in seen:
            errs.append('duplicate %s' % (k,))
        seen.add(k)
    print('%-28s %6d elements  %s' % (rel, len(elements) if isinstance(elements, list) else 0,
                                      'OK' if not errs else '%d problems, e.g. %s' % (len(errs), errs[:3])))
    bad += bool(errs)
sys.exit(1 if bad else 0)
