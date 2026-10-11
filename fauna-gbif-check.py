#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fauna-gbif-check.py — Quellen-Abgleich für die kuratierte Tier-Grundlage (FAUNA_LAENDER)

Zweck
-----
Zieht aus GBIF (Global Biodiversity Information Facility, offene Fundmelde-Datenbank) pro
Reiseland die belastbaren Vorkommen der sicherheitsrelevanten Zielarten (Raubtiere, Flusspferd,
Krokodil, Nashorn, Kaffernbüffel, Giftschlangen ...) und gleicht sie gegen die FAUNA_LAENDER-
Daten in index.html ab. So kannst du die kuratierten Angaben QUELLENBASIERT gegenprüfen und
Lücken finden — genau der Weg, um „klingt plausibel" durch „steht in den Daten" zu ersetzen.

Ergebnis
--------
1) fauna-gbif-matrix.csv  — Art × Land, Zelle = Zahl der GBIF-Fundmeldungen
2) Konsolen-Report        — pro Land die GBIF-bestätigten Arten + Abgleich gegen FAUNA_LAENDER
                            (Kandidaten, die bestätigt sind, aber im Profil fehlen)

WICHTIGE CAVEATS (bitte lesen)
------------------------------
* GBIF BESTÄTIGT Vorkommen (viele Fundmeldungen = Art ist dort belegt).
* GBIF WIDERLEGT NICHTS: wenige/keine Meldungen heißen NICHT „Art fehlt" — es gibt starke
  Erfassungslücken (v. a. Angola, Burundi, Mosambik, Teile Äthiopiens). Null also nie als
  „nicht vorhanden" werten.
* Fundmeldungen können Zoo-/Gehege-/Fehlbestimmungen enthalten; darum eine Mindestschwelle
  (--min, Standard 5). Für die medizinische Seite (Malaria/Tsetse-Zonen) bleiben WHO/CDC/
  Tropenmediziner die Primärquelle, nicht GBIF.

Nutzung
-------
    python3 fauna-gbif-check.py                 # alle 16 Länder, liest ./index.html mit
    python3 fauna-gbif-check.py --min 8         # strengere Präsenz-Schwelle
    python3 fauna-gbif-check.py --index /pfad/index.html --out matrix.csv
    python3 fauna-gbif-check.py --only Namibia,Lesotho

Nur Python-Standardbibliothek — kein pip nötig. Braucht Internet (läuft zuhause am Mac).
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

GBIF_API = "https://api.gbif.org/v1"
UA = "SafariAssistant/2026.10 (+https://github.com/DarkPirateGo/safari-assistant) fauna-check"

# ISO-3166-1 alpha-2 der 16 Reiseländer (Schlüssel = Name wie in LAENDER_GEO/FAUNA_LAENDER)
COUNTRIES = {
    "Lesotho": "LS", "Eswatini": "SZ", "Ruanda": "RW", "Burundi": "BI",
    "Namibia": "NA", "Botswana": "BW", "Sambia": "ZM", "Zimbabwe": "ZW",
    "Mosambik": "MZ", "Malawi": "MW", "Tansania": "TZ", "Kenia": "KE",
    "Uganda": "UG", "Äthiopien": "ET", "Angola": "AO", "Südafrika": "ZA",
}

# Zielarten: sicherheitsrelevant zuerst. 'kw' = ASCII-Schlüsselwort, wie es im FAUNA_LAENDER-Text
# vorkommt (Umlaute sind dort als ae/oe/ue geschrieben). 'check' = im Profil-Abgleich prüfen?
# (bei Nebenarten wie Hyäne/ikonischem Wild False, um Rauschen zu vermeiden — stehen trotzdem in der CSV).
TARGETS = [
    # Raubtiere
    {"de": "Löwe",              "sci": "Panthera leo",            "grp": "Raubtier",     "kw": "loewe",         "check": True},
    {"de": "Leopard",           "sci": "Panthera pardus",         "grp": "Raubtier",     "kw": "leopard",       "check": True},
    {"de": "Gepard",            "sci": "Acinonyx jubatus",        "grp": "Raubtier",     "kw": "gepard",        "check": False},
    {"de": "Tüpfelhyäne",       "sci": "Crocuta crocuta",         "grp": "Raubtier",     "kw": "hyaene",        "check": False},
    {"de": "Afrik. Wildhund",   "sci": "Lycaon pictus",           "grp": "Raubtier",     "kw": "wildhund",      "check": False},
    # Großtiere / Dickhäuter
    {"de": "Elefant",           "sci": "Loxodonta africana",      "grp": "Grosstier",    "kw": "elefant",       "check": True},
    {"de": "Flusspferd",        "sci": "Hippopotamus amphibius",  "grp": "Grosstier",    "kw": "flusspferd",    "check": True},
    {"de": "Kaffernbüffel",     "sci": "Syncerus caffer",         "grp": "Grosstier",    "kw": "kaffernbueffel","check": True},
    {"de": "Spitzmaulnashorn",  "sci": "Diceros bicornis",        "grp": "Grosstier",    "kw": "nashorn",       "check": False},
    {"de": "Breitmaulnashorn",  "sci": "Ceratotherium simum",     "grp": "Grosstier",    "kw": "nashorn",       "check": False},
    # Krokodil
    {"de": "Nilkrokodil",       "sci": "Crocodylus niloticus",    "grp": "Reptil",       "kw": "krokodil",      "check": True},
    # Giftschlangen
    {"de": "Schwarze Mamba",    "sci": "Dendroaspis polylepis",   "grp": "Giftschlange", "kw": "mamba",         "check": True},
    {"de": "Grüne Mamba",       "sci": "Dendroaspis angusticeps", "grp": "Giftschlange", "kw": "mamba",         "check": False},
    {"de": "Puffotter",         "sci": "Bitis arietans",          "grp": "Giftschlange", "kw": "puffotter",     "check": True},
    {"de": "Gabunviper",        "sci": "Bitis gabonica",          "grp": "Giftschlange", "kw": "gabunviper",    "check": False},
    {"de": "Mosambik-Speikobra","sci": "Naja mossambica",         "grp": "Giftschlange", "kw": "speikobra",     "check": False},
    {"de": "Kap-Kobra",         "sci": "Naja nivea",              "grp": "Giftschlange", "kw": "kap-kobra",     "check": False},
    {"de": "Boomslang",         "sci": "Dispholidus typus",       "grp": "Giftschlange", "kw": "boomslang",     "check": True},
    # Krankheitsüberträger (GBIF hat Fundpunkte; Zonen aber über WHO/CDC absichern!)
    {"de": "Tsetsefliege",      "sci": "Glossina",                "grp": "Uebertraeger", "kw": "tsetse",        "check": False},
    {"de": "Malaria-Mücke",     "sci": "Anopheles gambiae",       "grp": "Uebertraeger", "kw": "malaria",       "check": False},
    # Ikonisch (Kontext, nicht sicherheitskritisch)
    {"de": "Giraffe",           "sci": "Giraffa",                 "grp": "Ikonisch",     "kw": "giraffe",       "check": False},
    {"de": "Steppenzebra",      "sci": "Equus quagga",            "grp": "Ikonisch",     "kw": "zebra",         "check": False},
    {"de": "Streifengnu",       "sci": "Connochaetes taurinus",   "grp": "Ikonisch",     "kw": "gnu",           "check": False},
]


def http_json(url, tries=4):
    """GET -> JSON, mit einfachem Retry/Backoff. Gibt None bei dauerhaftem Fehler."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 (Netz-/JSON-Fehler bewusst breit)
            if i == tries - 1:
                sys.stderr.write(f"  ! Fehler bei {url}\n    {e}\n")
                return None
            time.sleep(1.5 * (i + 1))
    return None


_match_cache = {}


def taxon_key(sci):
    """GBIF-Taxon-Key für einen wissenschaftlichen Namen (Art oder Gattung)."""
    if sci in _match_cache:
        return _match_cache[sci]
    url = f"{GBIF_API}/species/match?name={urllib.parse.quote(sci)}"
    d = http_json(url) or {}
    key = d.get("usageKey")
    if not key or d.get("matchType") == "NONE":
        sys.stderr.write(f"  ! Kein GBIF-Treffer für '{sci}' (matchType={d.get('matchType')})\n")
        key = None
    _match_cache[sci] = key
    return key


def occ_count(taxon, cc):
    """Zahl der GBIF-Fundmeldungen eines Taxons in einem Land (ISO2)."""
    url = f"{GBIF_API}/occurrence/search?taxonKey={taxon}&country={cc}&limit=0"
    d = http_json(url) or {}
    return int(d.get("count", 0))


# ---- FAUNA_LAENDER aus index.html lesen (für den Abgleich) -------------------

def normalize(s):
    """Umlaute -> ae/oe/ue, lower — damit ASCII-Schlüsselwörter zuverlässig matchen."""
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def load_fauna(index_path):
    """Zieht das FAUNA_LAENDER-Objekt aus index.html und gibt {Land: normalisierter Text}."""
    if not index_path or not os.path.isfile(index_path):
        return None
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"const FAUNA_LAENDER = \{(.*?)\n\};", html, re.S)
    if not m:
        return None
    body = m.group(1)
    out = {}
    # Zeilen der Form:  'Land': 'Text ...',
    for line in body.splitlines():
        lm = re.match(r"\s*'([^']+)':\s*'(.*)'\s*,?\s*$", line)
        if lm:
            out[lm.group(1)] = normalize(lm.group(2))
    return out


# ---- Hauptlauf --------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="GBIF-Abgleich für FAUNA_LAENDER")
    ap.add_argument("--min", type=int, default=5, help="Mindest-Fundmeldungen für 'präsent' (Standard 5)")
    ap.add_argument("--index", default="index.html", help="Pfad zu index.html (für den Profil-Abgleich)")
    ap.add_argument("--out", default="fauna-gbif-matrix.csv", help="Ausgabe-CSV")
    ap.add_argument("--only", default="", help="Nur diese Länder (kommagetrennt, z. B. Namibia,Lesotho)")
    ap.add_argument("--sleep", type=float, default=0.05, help="Pause zwischen Requests (Sekunden)")
    args = ap.parse_args()

    countries = dict(COUNTRIES)
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        countries = {k: v for k, v in COUNTRIES.items() if k in want}
        if not countries:
            sys.exit(f"Keine gültigen Länder in --only. Erlaubt: {', '.join(COUNTRIES)}")

    fauna = load_fauna(args.index)
    print(f"GBIF-Abgleich · {len(TARGETS)} Zielarten × {len(countries)} Länder · Schwelle ≥ {args.min}")
    print(f"FAUNA_LAENDER aus {args.index}: {'gefunden' if fauna else 'NICHT gefunden (Abgleich übersprungen)'}\n")

    # 1) Taxon-Keys auflösen
    print("Taxon-Keys auflösen ...")
    for t in TARGETS:
        t["key"] = taxon_key(t["sci"])
        time.sleep(args.sleep)

    # 2) Occurrence-Counts (Matrix)
    print("Fundmeldungen zählen (das dauert kurz) ...\n")
    counts = {}  # counts[de][Land] = int
    for t in TARGETS:
        counts[t["de"]] = {}
        for land, cc in countries.items():
            n = occ_count(t["key"], cc) if t["key"] else 0
            counts[t["de"]][land] = n
            time.sleep(args.sleep)

    # 3) CSV schreiben
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Art", "Wissenschaftlich", "Gruppe"] + list(countries.keys()))
        for t in TARGETS:
            w.writerow([t["de"], t["sci"], t["grp"]] + [counts[t["de"]][l] for l in countries])
    print(f"✅ Matrix geschrieben: {args.out}\n")

    # 4) Per-Land-Report + Abgleich gegen FAUNA_LAENDER
    print("=" * 64)
    for land in countries:
        present = [t for t in TARGETS if counts[t["de"]][land] >= args.min]
        print(f"\n### {land} — GBIF-bestätigt (≥{args.min}): {len(present)} Arten")
        by_grp = {}
        for t in present:
            by_grp.setdefault(t["grp"], []).append(f'{t["de"]} ({counts[t["de"]][land]})')
        for grp in ["Raubtier", "Grosstier", "Reptil", "Giftschlange", "Uebertraeger", "Ikonisch"]:
            if by_grp.get(grp):
                print(f"  {grp:13s}: " + ", ".join(by_grp[grp]))

        if fauna and land in fauna:
            txt = fauna[land]
            missing = [t["de"] for t in present if t["check"] and normalize(t["kw"]) not in txt]
            if missing:
                print(f"  ⚠️ im Profil evtl. NICHT erwähnt (GBIF-bestätigt): {', '.join(sorted(set(missing)))}")
            else:
                print("  ✓ Kern-Gefahrenarten im Profil abgedeckt")
        elif fauna is not None:
            print("  (kein FAUNA_LAENDER-Eintrag für dieses Land gefunden)")

    print("\n" + "=" * 64)
    print("HINWEIS: GBIF bestätigt Vorkommen. Wenige/keine Meldungen heißen NICHT 'Art fehlt'")
    print("(Erfassungslücken v. a. Angola/Burundi/Mosambik). Malaria/Tsetse-ZONEN über WHO/CDC absichern.")


if __name__ == "__main__":
    main()
