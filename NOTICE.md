# Third-party licences and attribution

## Safari Assistant's own code

The source code of Safari Assistant is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE) (<https://polyformproject.org/licenses/noncommercial/1.0.0>). Its required notice:

```
Required Notice: Copyright 2026 DARK (https://github.com/DarkPirateGo)
```

**Source-available, not open source.** PolyForm Noncommercial is a source-available licence. It is not an open-source licence approved by the Open Source Initiative (OSI). It grants rights only for the purposes it permits. In the words of the licence:

- "Any noncommercial purpose is a permitted purpose."
- "Personal use for research, experiment, and testing for the benefit of public knowledge, personal study, private entertainment, hobby projects, amateur pursuits, or religious observance, without any anticipated commercial application, is use for a permitted purpose."
- "Use by any charitable organization, educational institution, public research organization, public safety or health organization, environmental protection organization, or government institution is use for a permitted purpose regardless of the source of funding or obligations resulting from the funding."

For these purposes you may also "make changes and new works based on the software" and "distribute copies of the software", including "with changes and new works". Anyone who gets a copy of any part of the software from you must also get "a copy of these terms or the URL for them above" and the `Required Notice:` line. The software "comes as is, without any warranty or condition".

Anything else, including commercial use, is not covered: "These terms do not imply any other licenses." Commercial use needs a separate licence from DARK; ask in an [issue](https://github.com/DarkPirateGo/safari-assistant/issues). The binding text is [`LICENSE`](LICENSE), not this summary.

PolyForm Noncommercial does **not** cover the names and logos, the data files, the vendored libraries or the adapted code listed below. Each keeps its own licence or terms.

---

## Names and logos

"Safari Assistant" is the name of the app; its logo and icon are the files in `docs/img/logo/` (also shown in `docs/img/social-preview.png`). "DARK" and `dark-logo.jpg` identify the creator. None of them is licensed under PolyForm Noncommercial; all rights reserved. Forks must remove or replace them as the name and logo of their version. The `Required Notice:` line, which names DARK as the copyright holder, stays.

---

## Data in this repository

### OpenStreetMap — ODbL 1.0

- `POIs/<Country>-osm.json` (one file per country), created by `fetch-pois.py` through the Overpass API
- `data/parks.geojson` (simplified park and protected-area boundaries), created by `fetch-parks.py`

> Contains information from OpenStreetMap (© OpenStreetMap contributors), made available here under the Open Database License (ODbL) 1.0: https://opendatacommons.org/licenses/odbl/1-0/ . Individual contents: Database Contents License (DbCL) 1.0: https://opendatacommons.org/licenses/dbcl/1-0/ . https://www.openstreetmap.org/copyright

These files are Derivative Databases. They are licensed to you under the ODbL 1.0, not under PolyForm Noncommercial. If you publicly use or redistribute them, modified or not, keep this notice, license your version under the ODbL and make the database (or the means to recreate it) available. `fetch-pois.py` and `fetch-parks.py` are the complete recipe.

### GeoNames — CC BY 4.0

- `data/orte.json` (offline place search), created by `fetch-orte.py`

> Place data © GeoNames (https://www.geonames.org), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).
> Changes: filtered to 16 countries and selected feature classes; reduced to name, coordinates, country, category and population.

### NASA POWER

- `data/klima.json` (rain-season layer), created by `fetch-klima.py`

> The data was obtained from National Aeronautics and Space Administration (NASA) Langley Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA Earth Science Division.

Service: POWER API, climatology point endpoint, "20-year Meteorological and Solar Monthly & Annual Climatologies (January 2001 – December 2020)". Accessed 2026-09-25; the date is recorded in the file (`erzeugt`).

### Test fixtures

`test-reisewarnungen.py` and `test-warngebiete.py` contain short, abridged excerpts modelled on travel advice of the German Federal Foreign Office (Auswärtiges Amt), the UK FCDO and the US Department of State. They are used only to test the parser and are not current travel advice. FCDO: contains public sector information licensed under the Open Government Licence v3.0. US Department of State material is a work of the U.S. Government.

---

## Libraries in `vendor/`

Release builds of these versions, pinned by SHA-256. The licence file for each library sits next to it.

| Library | Version | Licence | Copyright | Licence file |
|---|---|---|---|---|
| [Leaflet](https://leafletjs.com) | 1.9.4 | BSD-2-Clause | © 2010-2023 Vladimir Agafonkin, © 2010-2011 CloudMade | `vendor/LICENSE-leaflet.txt` |
| [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster) | 1.5.3 | MIT | © 2012 David Leaver | `vendor/LICENSE-leaflet.markercluster.txt` |
| [MapLibre GL JS](https://maplibre.org) | 4.7.1 | BSD-3-Clause, including notices for code from Mapbox GL JS v1.13 and earlier (BSD-3-Clause, © 2020 Mapbox), glfx.js (MIT, © 2011 Evan Wallace) and d3-color (BSD-3-Clause, © 2010-2016 Mike Bostock) | © 2023 MapLibre contributors | `vendor/LICENSE-maplibre-gl.txt` |

A licence file whose short header ends with the line `STANDARD-TEXT-MARKER` holds the standard SPDX text with the upstream copyright notices. In the maintainer's working folder (marker file `.deploy-commit`) or with `DEPLOY_LIZENZEN=1`, `deploy.sh` replaces such a file with the verbatim upstream file from the project's GitHub tag when it runs online.

---

## Code adapted from third parties

### QR code encoder — Project Nayuki, MIT

The QR code encoder in `index.html` (section "QR-CODE") and the read-back helper in `test-app.js` (section 55) are adapted from the QR Code generator library by Project Nayuki: https://www.nayuki.io/page/qr-code-generator-library

Copyright (c) Project Nayuki. Licensed under the MIT License (standard text):

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Plus Codes — Open Location Code

`plusCode()` implements the Open Location Code specification (https://github.com/google/open-location-code). The test vectors in `test-app.js` come from its `test_data/encoding.csv`, Copyright Google LLC, Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0).

### Sun times

The sunrise and sunset calculation follows the public-domain *Almanac for Computers* algorithm (U.S. Naval Observatory, 1990).

---

## Fonts

The pages use the system font stacks of your device. No web fonts are loaded or shipped.

Map glyphs (Noto Sans, SIL Open Font License 1.1) are downloaded by `setup-offline-karte.sh` from the [OpenMapTiles fonts release](https://github.com/openmaptiles/fonts) and are not stored in this repository.

---

## Fetched or generated at runtime, never stored in this repository

- **Travel advice:** Auswärtiges Amt open data (shown complete, with date and link, refreshed whenever online); UK FCDO (contains public sector information licensed under the Open Government Licence v3.0); US Department of State (a work of the U.S. Government). No travel-advice snapshot is shipped: the Foreign Office terms require complete, current text.
- **`data/warnzonen.geojson` and `data/verwaltungsgebiete.geojson`:** not shipped. Safari Assistant generates them locally from OpenStreetMap (ODbL 1.0) with `fetch-warnzonen.py`. The warn-zone file also stores sentences from the official warning text.
- **Map tiles:** tile.openstreetmap.org, © OpenStreetMap contributors, under the OSMF Tile Usage Policy.
- **Place search:** Nominatim (nominatim.openstreetmap.org), under the Nominatim Usage Policy.
- **Weather forecast:** Open-Meteo.com, CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The free Open-Meteo API is for non-commercial use only.
- **Exchange rates:** open.er-api.com (ExchangeRate-API). The app names the source next to the rates.
- **Your own `karte.mbtiles`:** © OpenMapTiles © OpenStreetMap contributors (ODbL); the OpenMapTiles schema is CC BY 4.0. The map build also uses Natural Earth data (public domain) and OpenStreetMap-derived ocean polygons.

---

## Tools Safari Assistant drives but does not include

| Tool | Role | Licence |
|---|---|---|
| [Ollama](https://ollama.com) | local model runtime | MIT |
| [Kiwix / kiwix-tools](https://kiwix.org) | offline Wikipedia server | GPL-3.0 |
| [Planetiler](https://github.com/onthegomap/planetiler) | builds the offline vector map | Apache-2.0 |
| [PyMuPDF](https://pymupdf.readthedocs.io) | PDF text extraction | AGPL-3.0 or commercial |
| [Pillow](https://python-pillow.org) | icon generation (`generate_icon.py`) | MIT-CMU |

**PyMuPDF is AGPL-3.0.** It is an optional runtime dependency that users install themselves. Safari Assistant does not distribute it or link it at build time. If you distribute a product built on this code, review that licence; you may need a commercial PyMuPDF licence or a different PDF library. (Commercial use of Safari Assistant's own code needs a separate licence from DARK as well; see [Safari Assistant's own code](#safari-assistants-own-code).)

Models pulled through Ollama carry their own licences (Qwen, Gemma and others each have their own terms). Check them before commercial use.

---

## Data deliberately not included

**iOverlander exports.** The app imports them, but the [iOverlander terms](https://ioverlander.com/terms_2023) grant users a licence "solely for personal, non-commercial use" and state that "Use, reproduction, modification, distribution or storage of any Content for other than personal, non-commercial use is expressly prohibited without prior written permission from iOverlander." So no iOverlander data is distributed here. Export your own and import it locally.

**Manufacturer manuals and your own documents.** Workshop and owner manuals are copyrighted. The document feature is built for you to add your own copies locally. Uploaded documents (`docs/<module>/`), `rag-store.json` and PDFs are ignored by git and blocked by the privacy gate. Please keep them out of forks too.

**Travel-advice snapshots.** See above: the official texts are fetched at runtime and never committed.
