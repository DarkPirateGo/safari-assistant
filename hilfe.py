"""Safari Assistant — Hilfe in der App: die Anleitung (README) als Seite, offline, in vier Sprachen.
Safari Assistant hilfe.py v2026-10-05-1

Das „?“ in index.html, mobile.html und pois.html öffnet `/hilfe?lang=<de|en|fr|es>&from=<Seite>`.
server.py ruft dafür `seite()` auf und schickt die Seite mit der strengen Richtlinie `CSP` —
ohne Skripte, ohne etwas von außen; der Stil ist per Prüfsumme freigegeben.

Die Anleitung ist Markdown. `rendern()` ist ein kleiner Renderer dafür, ohne fremdes Paket
(übernommen aus Wingfoilscout, gleicher Autor, gleiche Lizenz): Überschriften mit Ankern wie auf
GitHub (`slug()`), Absätze, verschachtelte Listen, Code, Tabellen, Zitate samt GitHub-Hinweis-
kästen (`> [!IMPORTANT]`), Trennlinien, harte Zeilenumbrüche, fett/kursiv, Links. Jeder Text wird
escaped. Rohes HTML im Markdown wird nicht gezeigt, sondern weggelassen; ein Bild wird zu seinem
Alternativtext. Links (`link_ziel()`): http(s) und mailto öffnen in einem neuen Tab, ein Verweis
auf ein README bleibt in der Hilfe (`/hilfe?lang=xx`), jede andere Datei des Repositorys führt
auf GitHub, `#anker` bleibt auf der Seite; alles andere (`javascript:`, `data:` …) steht als
bloßer Text da.

Die Dateien: README.md (Englisch, das Original), README.de.md, README.fr.md, README.es.md. Im
öffentlichen Repository liegen sie im Hauptordner, im Arbeitsordner, aus dem der Release entsteht,
in release-docs/ — gesucht wird erst neben server.py, dann in release-docs/. Fehlt eine Übersetzung,
kommt die englische Fassung mit einem Satz dazu. Gerendert wird einmal je Datei und Stand (Änderungszeit,
Größe) — `_gemerkt()`.

Python 3.9 (macOS /usr/bin/python3), nur Standardbibliothek.
"""
from __future__ import annotations

import base64
import hashlib
import html
import posixpath
import re
import threading
import unicodedata
import urllib.parse
from pathlib import Path
from typing import NamedTuple

WURZEL = Path(__file__).resolve().parent     # der Ordner von server.py (Arbeitsordner bzw. App-Bundle)
UNTERORDNER = ("", "release-docs")           # wo die README-Dateien liegen können, in dieser Reihenfolge
ORIGINAL = "en"                              # die Sprache von README.md
SPRACHEN = ("de", "en", "fr", "es")

REPO = "https://github.com/DarkPirateGo/safari-assistant"
DATEI_AUF_GITHUB = REPO + "/blob/main/"
ANLEITUNG_PFAD = "/hilfe"


def readme_name(sprache: str) -> str:
    return "README.md" if sprache == ORIGINAL else f"README.{sprache}.md"


def readme_datei(sprache: str, wurzel: Path = WURZEL) -> Path | None:
    """Die README-Datei einer Sprache: erst neben server.py, dann in release-docs/ — oder None."""
    for ordner in UNTERORDNER:
        pfad = (wurzel / ordner / readme_name(sprache)) if ordner else (wurzel / readme_name(sprache))
        if pfad.is_file():
            return pfad
    return None


def sprache_waehlen(wert) -> str:
    """Die Sprache aus `?lang=`: de, en, fr oder es — alles andere (auch „../x“) ist Englisch.
    „de-DE“ und „DE“ gelten als de."""
    s = str(wert or "").strip().lower().replace("_", "-").split("-")[0]
    return s if s in SPRACHEN else ORIGINAL


# ── Anker wie auf GitHub ────────────────────────────────────────────────────
# Wie github-slugger: klein geschrieben; weg fällt, was nicht Buchstabe,
# Zeichen (Mark), Ziffer, Verbindungsstrich (_), Bindestrich oder Leerzeichen
# ist — Satzzeichen, Gedankenstriche, Symbole, Emoji, geschützte Leerzeichen;
# jedes Leerzeichen wird ein Bindestrich. „The benchmark — is it still
# right?“ → `the-benchmark--is-it-still-right`, „Über uns“ → `über-uns`.

_SLUG_WEG = {"Cc", "Cf", "Co", "Cn", "Cs", "Zs", "Zl", "Zp", "Pd", "Ps", "Pe", "Pi", "Pf", "Po",
             "Sm", "Sc", "Sk", "So", "No"}


def slug(text: str) -> str:
    aus = []
    for zeichen in text.lower():
        if zeichen in " -":
            aus.append(zeichen)
        elif unicodedata.category(zeichen) not in _SLUG_WEG or zeichen.isalpha():
            aus.append(zeichen)
    return "".join(aus).replace(" ", "-")


class Slugs:
    """Anker eines Dokuments: derselbe Text ein zweites Mal bekommt `-1`,
    dann `-2` … (wie GitHub)."""

    def __init__(self):
        self.vorkommen: dict[str, int] = {}

    def __call__(self, text: str) -> str:
        basis = slug(text)
        ergebnis = basis
        while ergebnis in self.vorkommen:
            self.vorkommen[basis] += 1
            ergebnis = f"{basis}-{self.vorkommen[basis]}"
        self.vorkommen[ergebnis] = 0
        return ergebnis


# ── Links ───────────────────────────────────────────────────────────────────

def _kodieren(adresse: str) -> str:
    """Leerzeichen, Umlaute und Ähnliches als %-Escape; was schon escaped
    ist, bleibt."""
    return urllib.parse.quote(adresse, safe="%/:=&?~#+!$,;'@()*[]-._")


def link_ziel(adresse: str) -> tuple[str, bool] | None:
    """Wohin ein Link der Anleitung in der App führt: (href, extern) — oder
    None, dann steht nur sein Text da.

    http(s) und mailto bleiben (extern: neuer Tab); `#anker` bleibt auf der
    Seite. Ein relativer Pfad im Repository: README.md → `/hilfe?lang=en`,
    README.xx.md → `/hilfe?lang=xx` (xx eine der vier Sprachen), jede andere
    Datei → auf GitHub. Jedes andere Schema (`javascript:`, `data:`,
    `file:` …), `//host/…` und ein Pfad, der aus dem Repository hinausführt,
    ist kein Link."""
    # Wie der Browser: Tab und Zeilenende zählen nirgends, Leerraum und
    # Steuerzeichen an den Rändern nicht. Ob ein Schema dasteht, entscheidet
    # die Fassung ganz ohne Leerraum und Steuerzeichen — „java script:“ ist
    # dann auch keins, das durchkommt.
    kompakt = re.sub(r"[\t\n\r]+", "", adresse or "").strip("".join(map(chr, range(0x21))) + "\x7f")
    pruef = re.sub(r"[\x00-\x20\x7f]+", "", kompakt)
    if not kompakt:
        return None
    if kompakt.startswith("#"):
        return kompakt, False
    schema = re.match(r"([A-Za-z][A-Za-z0-9+.\-]*):", pruef)
    if schema:
        art = schema.group(1).lower()
        if not kompakt.lower().startswith(art + ":"):
            return None                         # „ht tp://…“: kein Schema, aber auch kein Pfad
        if art in ("http", "https", "mailto"):
            return _kodieren(kompakt), True
        return None
    if pruef.startswith(("//", "\\", "/\\")):
        return None
    pfad, raute, anker = kompakt.partition("#")
    pfad, frage, abfrage = pfad.partition("?")
    anker = raute + anker
    voll = posixpath.normpath(pfad.lstrip("/"))
    if voll == ".." or voll.startswith("../") or "\\" in voll:
        return None
    m = re.fullmatch(r"README(?:\.([A-Za-z]{2}))?\.md", voll)
    if m and (m.group(1) or ORIGINAL).lower() in SPRACHEN:
        return f"{ANLEITUNG_PFAD}?lang={(m.group(1) or ORIGINAL).lower()}" + anker, False
    if voll == ".":
        return _kodieren(REPO + anker), True
    return _kodieren(DATEI_AUF_GITHUB + voll + frage + abfrage + anker), True


# ── Markdown: Blöcke ────────────────────────────────────────────────────────

MAX_TIEFE = 24                 # Zitate und Listen ineinander; tiefer wird es Text
MAX_TRENNER = 1000             # Sternchen-Läufe je Absatz; darüber bleibt der Rest wörtlich
MAX_KLAMMERN = 1000            # offene [ je Absatz; darüber ist [ nur noch ein Zeichen

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_HR = re.compile(r"^ {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")
_ZAUN = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_ZITAT = re.compile(r"^ {0,3}>")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_PUNKT = re.compile(r"^( {0,3})([-+*]|\d{1,9}[.)])(?=[ \t]|$)")
_LINKDEF = re.compile(r"^ {0,3}\[((?:[^\[\]\\]|\\.){1,999})\]:[ \t]*(<[^<>\n]*>|\S+)"
                      r"(?:[ \t]+(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|\((?:[^()\\]|\\.)*\)))?[ \t]*$")
_HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|"
    "dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|"
    "iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|section|"
    "summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul")
_HTML_ANFANG = [                 # (Anfang, Ende) der HTML-Blöcke 1–6 nach CommonMark
    (re.compile(r"^ {0,3}<(?:script|pre|style|textarea)(?:[\s>]|$)", re.I),
     re.compile(r"</(?:script|pre|style|textarea)>", re.I)),
    (re.compile(r"^ {0,3}<!--"), re.compile(r"-->")),
    (re.compile(r"^ {0,3}<\?"), re.compile(r"\?>")),
    (re.compile(r"^ {0,3}<![A-Za-z]"), re.compile(r">")),
    (re.compile(r"^ {0,3}<!\[CDATA\["), re.compile(r"\]\]>")),
    (re.compile(r"^ {0,3}</?(?:" + _HTML_BLOCK_TAGS + r")(?:[\s/>]|$)", re.I), None),
]
_ATTRIBUT = r"""(?:\s+[A-Za-z_:][\w.:-]*(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)"""
_HTML_TAG7 = re.compile(r"^ {0,3}(?:<[A-Za-z][A-Za-z0-9-]*" + _ATTRIBUT + r"*\s*/?>|</[A-Za-z][A-Za-z0-9-]*\s*>)\s*$")


def _leer(zeile: str) -> bool:
    return not zeile.strip()


def _einrueckung(zeile: str) -> int:
    return len(zeile) - len(zeile.lstrip(" "))


def _tabs(zeile: str) -> str:
    """Tabulatoren am Zeilenanfang als Leerzeichen (Stopps alle vier)."""
    m = re.match(r"[ \t]+", zeile)
    return zeile if not m or "\t" not in m.group(0) else m.group(0).expandtabs(4) + zeile[m.end():]


def _listenpunkt(zeile: str) -> dict | None:
    m = _PUNKT.match(zeile)
    if not m:
        return None
    marke = m.group(2)
    rest = zeile[m.end():]
    abstand = len(rest) - len(rest.lstrip(" "))
    if not rest.strip():
        inhalt, text = m.end() + 1, ""
    elif abstand > 4:                       # eingerückter Code im Punkt: nur ein Leerzeichen zählt
        inhalt, text = m.end() + 1, rest[1:]
    else:
        inhalt, text = m.end() + abstand, rest[abstand:]
    nummer = marke[:-1] if marke[-1] in ".)" else ""
    return {"art": "ol" if nummer else "ul", "zeichen": marke[-1], "start": int(nummer) if nummer else 1,
            "inhalt": inhalt, "text": text}


def _html_block(zeile: str, mit_typ7: bool) -> int | None:
    """Nummer des HTML-Blocks (0–6), der mit dieser Zeile beginnt — oder None."""
    for nr, (anfang, _) in enumerate(_HTML_ANFANG):
        if anfang.match(zeile):
            return nr
    if mit_typ7 and _HTML_TAG7.match(zeile) and not re.match(r"^ {0,3}</?(?:script|style|pre)\b", zeile, re.I):
        return 6
    return None


def _unterbricht(zeile: str) -> bool:
    """Beginnt diese Zeile einen neuen Block, auch mitten in einem Absatz?"""
    if _leer(zeile) or _ATX.match(zeile) or _ZAUN.match(zeile) or _ZITAT.match(zeile) or _HR.match(zeile):
        return True
    p = _listenpunkt(zeile)
    if p and p["text"].strip() and (p["art"] == "ul" or p["start"] == 1):
        return True
    return _html_block(zeile, mit_typ7=False) is not None


def _zellen(zeile: str) -> list[str]:
    """Die Zellen einer Tabellenzeile: geteilt an jedem `|`, das nicht
    escaped ist — auch in `Code` (wie GitHub); `\\|` wird dann zu `|`."""
    z = zeile.strip()
    if z.startswith("|"):
        z = z[1:]
    if z.endswith("|") and not z.endswith("\\|"):
        z = z[:-1]
    zellen, aktuell, i = [], [], 0
    while i < len(z):
        if z[i] == "\\" and i + 1 < len(z) and z[i + 1] == "|":
            aktuell.append("|")
            i += 2
            continue
        if z[i] == "|":
            zellen.append("".join(aktuell).strip())
            aktuell = []
        else:
            aktuell.append(z[i])
        i += 1
    zellen.append("".join(aktuell).strip())
    return zellen


def _ausrichtung(trennzeile: str) -> list[str] | None:
    zellen = _zellen(trennzeile)
    if "|" not in trennzeile and len(zellen) < 2:
        return None
    aus = []
    for zelle in zellen:
        if not re.fullmatch(r":?-+:?", zelle):
            return None
        links, rechts = zelle.startswith(":"), zelle.endswith(":")
        aus.append("center" if links and rechts else "right" if rechts else "left" if links else "")
    return aus


class _Blockleser:
    """Zerlegt Markdown in Blöcke: (art, …)-Tupel, Container mit Kindern."""

    def __init__(self):
        self.verweise: dict[str, tuple[str, str]] = {}      # [label]: ziel "titel"
        self.zaeune = 0                                      # Codeblöcke mit ``` oder ~~~

    def bloecke(self, zeilen: list[str], tiefe: int = 0) -> tuple[list, bool]:
        """(Blöcke, lose) — lose heißt: zwischen zwei Blöcken lag eine Leerzeile."""
        aus: list = []
        absatz: list[str] = []
        leer_dazwischen = lose = False
        i, n = 0, len(zeilen)

        def absatz_ende():
            nonlocal absatz
            if absatz:
                text = "\n".join(absatz)
                # Verweisdefinitionen am Anfang eines Absatzes: merken, nicht zeigen
                while True:
                    m = _LINKDEF.match(text.split("\n", 1)[0])
                    if not m:
                        break
                    label = _label(m.group(1))
                    ziel = m.group(2)[1:-1] if m.group(2).startswith("<") else m.group(2)
                    titel = m.group(3)[1:-1] if m.group(3) else ""
                    if label and label not in self.verweise:
                        self.verweise[label] = (_entescape(ziel), _entescape(titel))
                    text = text.split("\n", 1)[1] if "\n" in text else ""
                if text.strip():
                    hinzu(("p", text))
                absatz = []

        def hinzu(block):
            nonlocal leer_dazwischen, lose
            if aus and leer_dazwischen:
                lose = True
            leer_dazwischen = False
            aus.append(block)

        while i < n:
            z = zeilen[i]
            if _leer(z):
                absatz_ende()
                if aus:
                    leer_dazwischen = True
                i += 1
                continue
            if absatz:
                m = _SETEXT.match(z)
                if m:
                    text = "\n".join(absatz)
                    absatz = []
                    hinzu(("h", 1 if m.group(1)[0] == "=" else 2, text.strip()))
                    i += 1
                    continue
                kopf = absatz[-1]
                ausr = _ausrichtung(z) if "|" in kopf else None
                if ausr is not None and len(_zellen(kopf)) == len(ausr):
                    absatz.pop()
                    absatz_ende()
                    i = self._tabelle(zeilen, i + 1, kopf, ausr, hinzu)
                    continue
                if not _unterbricht(z):
                    absatz.append(z)
                    i += 1
                    continue
                absatz_ende()
            # Ein Block beginnt
            if _einrueckung(z) >= 4:
                code = []
                while i < n and (_leer(zeilen[i]) or _einrueckung(zeilen[i]) >= 4):
                    code.append(zeilen[i][4:] if len(zeilen[i]) >= 4 else "")
                    i += 1
                while code and not code[-1].strip():
                    code.pop()
                hinzu(("code", "", "\n".join(code)))
                continue
            m = _ATX.match(z)
            if m:
                text = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", m.group(2) or "")
                hinzu(("h", len(m.group(1)), text.strip()))
                i += 1
                continue
            if _HR.match(z):
                hinzu(("hr",))
                i += 1
                continue
            m = _ZAUN.match(z)
            if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
                einr, zaun, info = len(m.group(1)), m.group(2), m.group(3).strip()
                code = []
                i += 1
                while i < n:
                    ende = re.match(r"^ {0,3}(" + re.escape(zaun[0]) + r"{" + str(len(zaun)) + r",})[ \t]*$", zeilen[i])
                    if ende:
                        i += 1
                        break
                    zeile = zeilen[i]
                    code.append(zeile[min(einr, _einrueckung(zeile)):])
                    i += 1
                self.zaeune += 1
                hinzu(("code", _entescape(info.split()[0]) if info else "", "\n".join(code)))
                continue
            if _ZITAT.match(z):
                innen, i = self._zitat(zeilen, i)
                if tiefe >= MAX_TIEFE:
                    hinzu(("p", "\n".join(innen)))
                else:
                    kinder, _ = self.bloecke(innen, tiefe + 1)
                    hinzu(("zitat", kinder))
                continue
            p = _listenpunkt(z)
            if p:
                if tiefe >= MAX_TIEFE:
                    absatz.append(z)
                    i += 1
                    continue
                liste, i = self._liste(zeilen, i, tiefe)
                hinzu(liste)
                continue
            typ = _html_block(z, mit_typ7=True)
            if typ is not None:
                i = self._html_weg(zeilen, i, typ)
                continue
            if "|" in z and i + 1 < n:
                ausr = _ausrichtung(zeilen[i + 1])
                if ausr is not None and len(_zellen(z)) == len(ausr):
                    i = self._tabelle(zeilen, i + 2, z, ausr, hinzu)
                    continue
            absatz.append(z)
            i += 1
        absatz_ende()
        return aus, lose

    def _tabelle(self, zeilen, i, kopf, ausr, hinzu) -> int:
        reihen = []
        while i < len(zeilen) and not _unterbricht(zeilen[i]):
            zellen = _zellen(zeilen[i])
            reihen.append((zellen + [""] * len(ausr))[:len(ausr)])
            i += 1
        hinzu(("tabelle", ausr, _zellen(kopf), reihen))
        return i

    @staticmethod
    def _zitat(zeilen, i) -> tuple[list[str], int]:
        """Die Zeilen eines Zitats ohne `>` — mit faulen Fortsetzungszeilen:
        eine Zeile ohne `>` gehört noch zum Absatz davor, wenn sie keinen
        neuen Block beginnt."""
        innen: list[str] = []
        while i < len(zeilen):
            z = zeilen[i]
            m = _ZITAT.match(z)
            if m:
                rest = z[m.end():]
                innen.append(rest[1:] if rest.startswith(" ") else rest)
            elif innen and not _leer(innen[-1]) and not _unterbricht(z) and not _ZAUN.match(innen[-1]):
                innen.append(z)
            else:
                break
            i += 1
        return innen, i

    def _liste(self, zeilen, i, tiefe) -> tuple[tuple, int]:
        erster = _listenpunkt(zeilen[i])
        punkte, lose, n = [], False, len(zeilen)
        while i < n:
            p = _listenpunkt(zeilen[i])
            if (not p or p["art"] != erster["art"] or p["zeichen"] != erster["zeichen"]
                    or _HR.match(zeilen[i])):
                break
            inhalt, ein = [p["text"]], p["inhalt"]
            i += 1
            while i < n:
                z = zeilen[i]
                if _leer(z):
                    inhalt.append("")
                    i += 1
                    continue
                if _einrueckung(z) >= ein:
                    inhalt.append(z[ein:])
                    i += 1
                    continue
                # weniger eingerückt: neuer Punkt, Ende — oder eine faule Fortsetzung
                if _leer(inhalt[-1]) or _listenpunkt(z) or _unterbricht(z):
                    break
                inhalt.append(z.lstrip(" "))
                i += 1
            # Leerzeilen am Ende gehören zwischen die Punkte
            naechster = _listenpunkt(zeilen[i]) if i < n else None
            folgt = bool(naechster and naechster["art"] == erster["art"]
                         and naechster["zeichen"] == erster["zeichen"])
            while inhalt and _leer(inhalt[-1]):
                inhalt.pop()
                if folgt:
                    lose = True
            kinder, innen_lose = self.bloecke(inhalt, tiefe + 1)
            lose = lose or innen_lose
            punkte.append(kinder)
        # Eine Leerzeile nach dem letzten Punkt macht die Liste nicht lose
        return ("liste", erster["art"], erster["start"], lose, punkte), i

    @staticmethod
    def _html_weg(zeilen, i, typ) -> int:
        """Rohes HTML wird nicht gezeigt: der Block fällt weg, ganz."""
        ende = _HTML_ANFANG[typ][1] if typ < 6 else None
        if ende is None:                       # Typ 6 und 7: bis zur nächsten Leerzeile
            while i < len(zeilen) and not _leer(zeilen[i]):
                i += 1
            return i
        while i < len(zeilen):
            gefunden = ende.search(zeilen[i])
            i += 1
            if gefunden:
                break
        return i


def _label(text: str) -> str:
    return " ".join(text.split()).casefold()


_ESCAPEBAR = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_ENTITAET = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});")


def _entitaet(m: re.Match) -> str:
    aus = html.unescape(m.group(0))
    return aus if aus != m.group(0) else m.group(0)


def _entescape(text: str) -> str:
    """Backslash-Escapes und Entitäten aufgelöst — für Ziele und Titel."""
    text = re.sub(r"\\([!-/:-@\[-`{-~])", r"\1", text)
    return _ENTITAET.sub(_entitaet, text)


# ── Markdown: im Absatz ─────────────────────────────────────────────────────

class _K:
    """Ein Knoten im Absatz: Text, Code, Umbruch, Betonung, Link …"""
    __slots__ = ("art", "text", "kinder", "href", "titel", "extern")

    def __init__(self, art, text="", kinder=None, href="", titel="", extern=False):
        self.art, self.text, self.kinder = art, text, kinder if kinder is not None else []
        self.href, self.titel, self.extern = href, titel, extern


class _Trenner:
    """Ein Lauf aus `*`, `_` oder `~~` — vielleicht der Anfang oder das Ende
    einer Betonung."""
    __slots__ = ("zeichen", "anzahl", "orig", "oeffnet", "schliesst", "knoten")


def _ist_punkt(z: str) -> bool:
    return bool(z) and (z in _ESCAPEBAR or unicodedata.category(z)[0] in "PS")


def _ist_leerraum(z: str) -> bool:
    return not z or z.isspace()


_AUTOLINK = re.compile(r"<([A-Za-z][A-Za-z0-9+.\-]{1,31}:[^\s<>]*)>")
_MAIL = re.compile(r"<([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                   r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*)>")
_ROH_TAG = re.compile(r"<[A-Za-z][A-Za-z0-9-]*" + _ATTRIBUT + r"*\s*/?>|</[A-Za-z][A-Za-z0-9-]*\s*>")
_ROH_BIS = (("<!-->", ""), ("<!--->", ""), ("<!--", "-->"), ("<?", "?>"), ("<![CDATA[", "]]>"))
_BR = re.compile(r"<br\s*/?>", re.I)
_VERWEIS = re.compile(r"\[((?:[^\[\]\\]|\\.){0,999})\]")
MAX_TAG = 4000                 # so lang darf ein rohes Tag im Absatz höchstens sein
_NACKT = re.compile(r"(?:https?://|www\.)[^\s<]+", re.I)


class _Absatz:
    """Der Inhalt eines Absatzes, einer Überschrift oder einer Zelle als
    Knoten — nach CommonMark: Code vor allem anderen, Links über die
    Klammern, Betonung über die Liste der Trenner."""

    def __init__(self, verweise: dict, ziel=link_ziel):
        self.verweise = verweise
        self.ziel = ziel

    def lesen(self, text: str) -> list[_K]:
        text = text.replace("\x00", "\ufffd")
        knoten: list[_K] = []
        trenner: list[_Trenner] = []
        klammern: list[dict] = []
        n, i = len(text), 0
        puffer: list[str] = []
        # Was ab einer Stelle nicht mehr vorkommt, kommt auch dahinter nicht
        # vor: ohne dieses Gedächtnis suchte jedes offene `<!--` (oder ein
        # Lauf aus Backticks) bis zum Ende — quadratisch, 9 s für 90 kB.
        fehlt: dict = {}

        def finde(was: str, ab: int) -> int:
            if ab >= fehlt.get(was, n + 1):
                return -1
            stelle = text.find(was, ab)
            if stelle < 0:
                fehlt[was] = ab
            return stelle

        def text_hinzu(s: str):
            puffer.append(s)

        def puffer_leeren():
            if puffer:
                knoten.append(_K("text", "".join(puffer)))
                puffer.clear()

        while i < n:
            c = text[i]
            if c == "\\":
                if i + 1 < n and text[i + 1] in _ESCAPEBAR:
                    text_hinzu(text[i + 1])
                    i += 2
                    continue
                if i + 1 < n and text[i + 1] == "\n":
                    puffer_leeren()
                    knoten.append(_K("br"))
                    i += 2
                    while i < n and text[i] == " ":
                        i += 1
                    continue
                text_hinzu("\\")
                i += 1
                continue
            if c == "`":
                j = i
                while j < n and text[j] == "`":
                    j += 1
                lauf = j - i
                ende = None
                if j < fehlt.get(("`", lauf), n + 1):
                    ende = re.compile(r"(?<!`)`{" + str(lauf) + r"}(?!`)").search(text, j)
                    if not ende:
                        fehlt[("`", lauf)] = j
                if ende:
                    inhalt = text[j:ende.start()].replace("\n", " ")
                    if len(inhalt) >= 2 and inhalt[0] == " " and inhalt[-1] == " " and inhalt.strip():
                        inhalt = inhalt[1:-1]
                    puffer_leeren()
                    knoten.append(_K("code", inhalt))
                    i = ende.end()
                else:
                    text_hinzu("`" * lauf)
                    i = j
                continue
            if c in "*_~":
                j = i
                while j < n and text[j] == c:
                    j += 1
                lauf = j - i
                if c == "~" and lauf != 2:
                    text_hinzu(c * lauf)
                    i = j
                    continue
                vor = text[i - 1] if i > 0 else ""
                nach = text[j] if j < n else ""
                links = not _ist_leerraum(nach) and (not _ist_punkt(nach) or _ist_leerraum(vor) or _ist_punkt(vor))
                rechts = not _ist_leerraum(vor) and (not _ist_punkt(vor) or _ist_leerraum(nach) or _ist_punkt(nach))
                if c == "_":
                    oeffnet = links and (not rechts or _ist_punkt(vor))
                    schliesst = rechts and (not links or _ist_punkt(nach))
                else:
                    oeffnet, schliesst = links, rechts
                puffer_leeren()
                k = _K("trenner", c * lauf)
                knoten.append(k)
                if (oeffnet or schliesst) and len(trenner) < MAX_TRENNER:
                    t = _Trenner()
                    t.zeichen, t.anzahl, t.orig, t.oeffnet, t.schliesst, t.knoten = c, lauf, lauf, oeffnet, schliesst, k
                    trenner.append(t)
                i = j
                continue
            if c in "hHwW" and (i == 0 or text[i - 1] in " \t\n*_~("):
                gefunden = _nackte_adresse(text, i)
                if gefunden:
                    adresse, ende = gefunden
                    wohin = self.ziel(adresse if re.match(r"(?i)https?://", adresse) else "http://" + adresse)
                    if wohin:
                        puffer_leeren()
                        knoten.append(_K("link", kinder=[_K("text", text[i:ende])], href=wohin[0], extern=wohin[1]))
                        i = ende
                        continue
            if c == "!" and i + 1 < n and text[i + 1] == "[" and len(klammern) < MAX_KLAMMERN:
                puffer_leeren()
                k = _K("text", "![")
                knoten.append(k)
                klammern.append({"knoten": k, "bild": True, "aktiv": True, "stand": len(trenner), "ab": i + 2})
                i += 2
                continue
            if c == "[" and len(klammern) < MAX_KLAMMERN:
                puffer_leeren()
                k = _K("text", "[")
                knoten.append(k)
                klammern.append({"knoten": k, "bild": False, "aktiv": True, "stand": len(trenner), "ab": i + 1})
                i += 1
                continue
            if c == "]":
                puffer_leeren()
                i = self._klammer_zu(text, i, knoten, trenner, klammern)
                continue
            if c == "<":
                m = _AUTOLINK.match(text, i) or _MAIL.match(text, i)
                if m:
                    adresse = m.group(1)
                    if m.re is _MAIL:
                        adresse = "mailto:" + adresse
                    puffer_leeren()
                    ziel = self.ziel(adresse)
                    kinder = [_K("text", m.group(1))]
                    knoten.append(_K("link", kinder=kinder, href=ziel[0], extern=ziel[1]) if ziel
                                  else _K("gruppe", kinder=kinder))
                    i = m.end()
                    continue
                ende = _roh_html(text, i, finde)
                if ende:
                    # Rohes HTML wird nicht gezeigt — nur <br> wird ein Umbruch
                    if _BR.fullmatch(text, i, ende):
                        puffer_leeren()
                        knoten.append(_K("br"))
                    i = ende
                    continue
                text_hinzu("<")
                i += 1
                continue
            if c == "&":
                m = _ENTITAET.match(text, i)
                if m:
                    text_hinzu(_entitaet(m))
                    i = m.end()
                    continue
                text_hinzu("&")
                i += 1
                continue
            if c == "\n":
                # Zwei Leerzeichen vor dem Zeilenende: harter Umbruch
                hart = puffer and "".join(puffer).endswith("  ")
                if puffer:
                    rest = "".join(puffer).rstrip(" ")
                    puffer.clear()
                    if rest:
                        puffer.append(rest)
                puffer_leeren()
                knoten.append(_K("br" if hart else "weich"))
                i += 1
                while i < n and text[i] == " ":
                    i += 1
                continue
            text_hinzu(c)
            i += 1
        puffer_leeren()
        self._betonung(knoten, trenner, 0)
        return knoten

    def _klammer_zu(self, text, i, knoten, trenner, klammern) -> int:
        if not klammern:
            knoten.append(_K("text", "]"))
            return i + 1
        k = klammern[-1]
        if not k["aktiv"]:
            klammern.pop()
            knoten.append(_K("text", "]"))
            return i + 1
        ziel = None
        weiter = i + 1
        if i + 1 < len(text) and text[i + 1] == "(":
            gelesen = _linkziel_lesen(text, i + 1)
            if gelesen:
                adresse, titel, weiter = gelesen
                ziel = (adresse, titel)
        if ziel is None:
            # [text][label], [label][] oder nur [label]
            label = text[k["ab"]:i]
            m = _VERWEIS.match(text, i + 1)
            if m:
                eigen = m.group(1)
                schluessel = _label(eigen if eigen.strip() else label)
                if schluessel in self.verweise:
                    ziel = self.verweise[schluessel]
                    weiter = m.end()
            elif _label(label) in self.verweise:
                ziel = self.verweise[_label(label)]
                weiter = i + 1
        if ziel is None:
            klammern.pop()
            knoten.append(_K("text", "]"))
            return i + 1
        a = _stelle(knoten, k["knoten"])
        kinder = knoten[a + 1:]
        del knoten[a:]
        self._betonung(kinder, trenner, k["stand"])
        klammern.pop()
        if k["bild"]:
            knoten.append(_K("bild", text=_klartext(kinder)))
        else:
            for frueher in klammern:            # kein Link im Link
                if not frueher["bild"]:
                    frueher["aktiv"] = False
            wohin = self.ziel(ziel[0])
            knoten.append(_K("link", kinder=kinder, href=wohin[0], titel=ziel[1], extern=wohin[1]) if wohin
                          else _K("gruppe", kinder=kinder))
        return weiter

    @staticmethod
    def _betonung(knoten: list[_K], trenner: list[_Trenner], unten: int) -> None:
        """Betonung nach CommonMark („process emphasis“): zu jedem Trenner, der
        schließen kann, der nächste passende davor, der öffnen kann."""
        boeden: dict = {}
        aktuell = unten
        while aktuell < len(trenner):
            t = trenner[aktuell]
            if not t.schliesst:
                aktuell += 1
                continue
            schluessel = (t.zeichen, t.oeffnet, t.orig % 3)
            boden = max(unten - 1, boeden.get(schluessel, unten - 1))
            gefunden, j = None, aktuell - 1
            while j > boden:
                o = trenner[j]
                if o.zeichen == t.zeichen and o.oeffnet:
                    if t.zeichen == "~":
                        passt = o.anzahl == t.anzahl
                    else:
                        passt = not ((o.schliesst or t.oeffnet) and (o.orig + t.orig) % 3 == 0
                                     and not (o.orig % 3 == 0 and t.orig % 3 == 0))
                    if passt:
                        gefunden = j
                        break
                j -= 1
            if gefunden is None:
                boeden[schluessel] = aktuell - 1
                if not t.oeffnet:
                    del trenner[aktuell]
                else:
                    aktuell += 1
                continue
            o = trenner[gefunden]
            if t.zeichen == "~":
                breite, art = 2, "del"
            else:
                breite = 2 if (o.anzahl >= 2 and t.anzahl >= 2) else 1
                art = "strong" if breite == 2 else "em"
            b = _stelle(knoten, t.knoten)
            a = _stelle(knoten, o.knoten, b)
            knoten[a + 1:b] = [_K(art, kinder=knoten[a + 1:b])]
            del trenner[gefunden + 1:aktuell]
            aktuell = gefunden + 1
            o.anzahl -= breite
            o.knoten.text = o.knoten.text[breite:]
            t.anzahl -= breite
            t.knoten.text = t.knoten.text[breite:]
            if o.anzahl == 0:
                del knoten[a]
                del trenner[gefunden]
                aktuell -= 1
            if t.anzahl == 0:
                del knoten[_stelle(knoten, t.knoten, a + 3)]
                del trenner[aktuell]
        del trenner[unten:]


def _roh_html(text: str, i: int, finde) -> int | None:
    """Wo rohes HTML ab `text[i] == "<"` endet — Kommentar, Anweisung,
    CDATA, Deklaration oder ein Tag (höchstens MAX_TAG Zeichen) — oder None."""
    for anfang, bis in _ROH_BIS:
        if text.startswith(anfang, i):
            if not bis:
                return i + len(anfang)
            ende = finde(bis, i + len(anfang))
            return ende + len(bis) if ende >= 0 else None
    if text.startswith("<!", i) and text[i + 2:i + 3].isascii() and text[i + 2:i + 3].isalpha():
        ende = finde(">", i + 2)
        return ende + 1 if ende >= 0 else None
    m = _ROH_TAG.match(text, i, min(len(text), i + MAX_TAG))
    return m.end() if m else None


def _stelle(knoten: list[_K], gesucht: _K, bis: int | None = None) -> int:
    """Wo `gesucht` in `knoten` steht — von hinten gesucht (ab `bis`), denn
    was gerade geschlossen wird, steht fast immer am Ende."""
    for nr in range(min(len(knoten), bis if bis is not None else len(knoten)) - 1, -1, -1):
        if knoten[nr] is gesucht:
            return nr
    raise ValueError("Knoten nicht gefunden")


def _linkziel_lesen(text: str, i: int) -> tuple[str, str, int] | None:
    """`(ziel "titel")` ab `text[i] == "("` → (Ziel, Titel, Position danach)."""
    n = len(text)
    j = i + 1

    def leerraum(j):
        zeilen = 0
        while j < n and text[j] in " \t\n":
            if text[j] == "\n":
                zeilen += 1
                if zeilen > 1:
                    return None
            j += 1
        return j

    j = leerraum(j)
    if j is None:
        return None
    ziel = ""
    if j < n and text[j] == "<":
        k = j + 1
        while k < n and text[k] not in "<>\n":
            k += 2 if text[k] == "\\" else 1
        if k >= n or text[k] != ">":
            return None
        ziel, j = text[j + 1:k], k + 1
    else:
        tiefe, k = 0, j
        while k < n:
            c = text[k]
            if c == "\\" and k + 1 < n:
                k += 2
                continue
            if c.isspace() or ord(c) < 0x20:
                break
            if c == "(":
                tiefe += 1
                if tiefe > 32:
                    return None
            elif c == ")":
                if tiefe == 0:
                    break
                tiefe -= 1
            k += 1
        if tiefe:
            return None
        ziel, j = text[j:k], k
    vorher = j
    j = leerraum(j)
    if j is None:
        return None
    titel = ""
    if j < n and text[j] in "\"'(" and j > vorher:
        schluss = ")" if text[j] == "(" else text[j]
        k = j + 1
        while k < n and text[k] != schluss:
            if text[k] == "\\":
                k += 1
            k += 1
        if k >= n:
            return None
        titel, j = text[j + 1:k], k + 1
        j = leerraum(j)
        if j is None:
            return None
    if j >= n or text[j] != ")":
        return None
    return _entescape(ziel), _entescape(titel), j + 1


def _klartext(knoten: list[_K]) -> str:
    aus = []
    for k in knoten:
        if k.art in ("text", "trenner", "code"):
            aus.append(k.text)
        elif k.art == "bild":
            aus.append(k.text)
        elif k.art in ("weich", "br"):
            aus.append(" ")
        else:
            aus.append(_klartext(k.kinder))
    return "".join(aus)


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _attr(text: str) -> str:
    return html.escape(text, quote=True)


def _nackte_adresse(text: str, i: int) -> tuple[str, int] | None:
    """Eine nackte Adresse (https://…, www.…) ab `i`, wie GitHub sie
    erkennt: ohne Satzzeichen am Ende, ohne eine schließende Klammer, die
    keine öffnende hat. (Adresse, Ende) oder None."""
    m = _NACKT.match(text, i)
    if not m:
        return None
    adresse = m.group(0)
    while adresse:
        if adresse[-1] in "?!.,:*_~'\"":
            adresse = adresse[:-1]
        elif adresse[-1] == ")" and adresse.count(")") > adresse.count("("):
            adresse = adresse[:-1]
        elif adresse[-1] == ";" and re.search(r"&[A-Za-z0-9]+;$", adresse):
            adresse = adresse[:adresse.rfind("&")]
        else:
            break
    rumpf = re.sub(r"(?i)^https?://", "", adresse)
    host = re.split(r"[/?#]", rumpf, 1)[0]
    if "." not in host or not re.search(r"[A-Za-z0-9]", host.split(".")[-1]):
        return None
    return adresse, i + len(adresse)


def _link_html(href: str, titel: str, extern: bool, inhalt: str) -> str:
    a = f'<a href="{_attr(href)}"'
    if titel:
        a += f' title="{_attr(titel)}"'
    if extern:
        a += ' target="_blank" rel="noopener noreferrer"'
    return a + ">" + inhalt + "</a>"


def _inline_html(knoten: list[_K], ziel, im_link: bool = False) -> str:
    aus = []
    for k in knoten:
        if k.art in ("text", "trenner"):
            aus.append(_esc(k.text))
        elif k.art == "code":
            aus.append("<code>" + _esc(k.text) + "</code>")
        elif k.art == "br":
            aus.append("<br>\n")
        elif k.art == "weich":
            aus.append("\n")
        elif k.art in ("em", "strong", "del"):
            aus.append(f"<{k.art}>" + _inline_html(k.kinder, ziel, im_link) + f"</{k.art}>")
        elif k.art == "link" and im_link:             # kein Link im Link: nur der Text
            aus.append(_inline_html(k.kinder, ziel, True))
        elif k.art == "link":
            aus.append(_link_html(k.href, k.titel, k.extern, _inline_html(k.kinder, ziel, True)))
        elif k.art == "gruppe":                          # ein Link, der keiner sein darf: nur sein Text
            aus.append(_inline_html(k.kinder, ziel, im_link))
        elif k.art == "bild":
            aus.append(_esc(k.text))
    return "".join(aus)


# ── Markdown: Ergebnis ──────────────────────────────────────────────────────

class Gerendert(NamedTuple):
    html: str
    ueberschriften: list            # [(Stufe im Markdown, Anker, Text)]
    zaeune: int                     # Codeblöcke mit ``` oder ~~~
    anker: list                     # Ziele von Links auf dieselbe Seite (#…), ohne „#“


def rendern(text: str, versatz: int = 0, ohne_sprachzeile: bool = False, ziel=link_ziel,
            sprache: str = ORIGINAL) -> Gerendert:
    """Markdown als sicheres HTML.

    `versatz` rückt die Überschriften tiefer (1: `#` wird <h2>). Die Seite
    /hilfe braucht das nicht: die <h1> ist die des README. `ohne_sprachzeile`
    lässt den Absatz weg, der auf die anderen Sprachfassungen verweist („This
    guide in: …“): die Seite hat ihren eigenen Umschalter. `ziel` entscheidet,
    wohin ein Link führt (`link_ziel`). `sprache` ist die Sprache des Texts —
    für die Titel der Hinweiskästen (`> [!NOTE]` …)."""
    zeilen = [_tabs(z) for z in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    leser = _Blockleser()
    bloecke, _ = leser.bloecke(zeilen)
    if ohne_sprachzeile:
        bloecke = [b for b in bloecke if not (b[0] == "p" and _ist_sprachzeile(b[1]))]
    absatz = _Absatz(leser.verweise, ziel)
    slugs = Slugs()
    ueberschriften: list = []
    anker: list = []

    def inline(roh: str) -> str:
        knoten = absatz.lesen(roh)
        _anker_sammeln(knoten, anker)
        return _inline_html(knoten, ziel)

    def block(b, eng: bool = False) -> str:
        art = b[0]
        if art == "p":
            inhalt = inline(b[1])
            return inhalt if eng else "<p>" + inhalt + "</p>"
        if art == "h":
            inhalt = inline(b[2])
            klar = html.unescape(re.sub(r"<[^>]*>", "", inhalt)).strip()
            id_ = slugs(klar)
            ueberschriften.append((b[1], id_, klar))
            stufe = min(6, b[1] + versatz)
            kennung = f' id="{_attr(id_)}"' if id_ else ""
            return f"<h{stufe}{kennung}>{inhalt}</h{stufe}>"
        if art == "hr":
            return "<hr>"
        if art == "code":
            klasse = f' class="language-{_attr(b[1])}"' if re.fullmatch(r"[\w+#.-]{1,40}", b[1] or "") else ""
            return f"<pre><code{klasse}>" + _esc(b[2] + ("\n" if b[2] else "")) + "</code></pre>"
        if art == "zitat":
            kinder = list(b[1])
            m = _KASTEN.match(kinder[0][1]) if kinder and kinder[0][0] == "p" else None
            if m:
                # Hinweiskasten wie auf GitHub: `> [!IMPORTANT]` allein in der ersten Zeile
                art_kasten = m.group(1).lower()
                rest = kinder[0][1][m.end():]
                kinder[:1] = [("p", rest)] if rest.strip() else []
                titel = KASTEN_TITEL[art_kasten].get(sprache) or KASTEN_TITEL[art_kasten][ORIGINAL]
                return (f'<blockquote class="kasten {KASTEN_KLASSE[art_kasten]}">\n'
                        f'<p class="kasten-titel">{_esc(titel)}</p>\n'
                        + "".join(block(k) + "\n" for k in kinder) + "</blockquote>")
            return "<blockquote>\n" + "\n".join(block(k) for k in kinder) + "\n</blockquote>"
        if art == "liste":
            _, typ, start, lose, punkte = b
            kopf = "<ul>" if typ == "ul" else (f'<ol start="{start}">' if start != 1 else "<ol>")
            teile = []
            for kinder in punkte:
                innen = [block(k, eng=not lose) for k in kinder]
                if not lose:
                    teile.append("<li>" + "\n".join(innen) + "</li>")
                else:
                    teile.append("<li>\n" + "\n".join(innen) + "\n</li>")
            return kopf + "\n" + "\n".join(teile) + "\n" + ("</ul>" if typ == "ul" else "</ol>")
        if art == "tabelle":
            _, ausr, kopfzellen, reihen = b

            def zelle(tag, inhalt, ausrichtung):
                # Eine Zelle mit viel Text bekommt eine Mindestbreite (STIL: td.lang):
                # neben einer Spalte mit Code bliebe sie am Handy sonst ein Wort breit.
                # Ausgerichtet wird über Klassen, nicht über style="…" — die Richtlinie
                # der Seite (CSP) lässt keine style-Attribute zu.
                klassen = (["lang"] if tag == "td" and len(inhalt) > 50 else []) + (
                    [_AUSRICHTUNG[ausrichtung]] if ausrichtung else [])
                attr = f' class="{" ".join(klassen)}"' if klassen else ""
                return f"<{tag}{attr}>{inline(inhalt)}</{tag}>"
            kopf = "<tr>" + "".join(zelle("th", z, a) for z, a in zip(kopfzellen, ausr)) + "</tr>"
            rumpf = "".join("<tr>" + "".join(zelle("td", z, a) for z, a in zip(r, ausr)) + "</tr>\n"
                            for r in reihen)
            return ('<div class="tabelle"><table>\n<thead>' + kopf + "</thead>\n"
                    + (f"<tbody>\n{rumpf}</tbody>" if rumpf else "") + "\n</table></div>")
        return ""

    teile = [block(b) for b in bloecke]
    return Gerendert("\n".join(t for t in teile if t) + "\n", ueberschriften, leser.zaeune, anker)


_AUSRICHTUNG = {"left": "links", "right": "rechts", "center": "mitte"}
_KASTEN = re.compile(r"\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\n|$)", re.I)
KASTEN_KLASSE = {"note": "notiz", "tip": "tipp", "important": "wichtig", "warning": "warnung", "caution": "vorsicht"}
KASTEN_TITEL = {
    "note": {"en": "Note", "de": "Hinweis", "fr": "Remarque", "es": "Nota"},
    "tip": {"en": "Tip", "de": "Tipp", "fr": "Astuce", "es": "Consejo"},
    "important": {"en": "Important", "de": "Wichtig", "fr": "Important", "es": "Importante"},
    "warning": {"en": "Warning", "de": "Warnung", "fr": "Avertissement", "es": "Advertencia"},
    "caution": {"en": "Caution", "de": "Vorsicht", "fr": "Attention", "es": "Precaución"},
}


def _anker_sammeln(knoten: list[_K], anker: list) -> None:
    for k in knoten:
        if k.art == "link" and k.href.startswith("#"):
            anker.append(urllib.parse.unquote(k.href[1:]))
        if k.kinder:
            _anker_sammeln(k.kinder, anker)


def _ist_sprachzeile(roh: str) -> bool:
    """„This guide in: English · [Deutsch](README.de.md) · …“ — ein Absatz mit
    Links auf mindestens zwei Sprachfassungen des README."""
    return len(re.findall(r"\]\(\s*<?(?:\./)?README(?:\.[A-Za-z]{2})?\.md>?\s*\)", roh)) >= 2


# ── Gerendert wird einmal je Stand der Datei ────────────────────────────────

_GEMERKT: dict = {}
_SPERRE = threading.Lock()


def _gemerkt(art: str, pfad: Path, bauen):
    """`bauen(text)` für diese Datei — einmal je Stand (Änderungszeit,
    Größe); None, wenn es die Datei nicht gibt."""
    try:
        st = pfad.stat()
        stand = (st.st_mtime_ns, st.st_size)
        schluessel = (art, str(pfad))
        with _SPERRE:
            fund = _GEMERKT.get(schluessel)
        if fund and fund[0] == stand:
            return fund[1]
        text = pfad.read_bytes().decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    wert = bauen(text)
    with _SPERRE:
        _GEMERKT[schluessel] = (stand, wert)
    return wert


def vergessen() -> None:
    """Alles neu rendern (Tests)."""
    with _SPERRE:
        _GEMERKT.clear()


class Anleitung(NamedTuple):
    html: str
    sprache: str                    # die Sprache des Texts
    uebersetzt: bool                # in der gewünschten Sprache (sonst die englische Fassung)


def anleitung(sprache: str, wurzel: Path = WURZEL) -> Anleitung:
    """Die Anleitung als HTML: in der gewünschten Sprache, sonst die
    englische Fassung. Die Zeile „This guide in: …“ fällt weg — die Seite hat
    ihren eigenen Sprachumschalter."""
    sprache = sprache_waehlen(sprache)
    for s in ([sprache] if sprache == ORIGINAL else [sprache, ORIGINAL]):
        pfad = readme_datei(s, wurzel)
        if pfad is None:
            continue
        g = _gemerkt("anleitung", pfad, lambda text, s=s: rendern(text, ohne_sprachzeile=True, sprache=s))
        if g is not None:
            return Anleitung(g.html, s, s == sprache)
    raise FileNotFoundError(2, "README.md fehlt", str(wurzel / "README.md"))


# ── Die Seite /hilfe ────────────────────────────────────────────────────────

HERKUNFT = ("/index.html", "/mobile.html", "/pois.html")     # wohin „←“ zurückführen darf
SPRACHNAMEN = (("de", "Deutsch"), ("en", "English"), ("fr", "Français"), ("es", "Español"))
TEXTE = {
    "de": {"titel": "Hilfe", "zurueck": "Zurück zur App", "sprache": "Sprache",
           "englisch": "Diese Anleitung gibt es noch nicht auf Deutsch — hier die englische Fassung.",
           "fehlt": "Die Anleitung (README.md) fehlt neben server.py. ./deploy.sh kopiert sie ins App-Bundle."},
    "en": {"titel": "Help", "zurueck": "Back to the app", "sprache": "Language",
           "englisch": "",
           "fehlt": "The guide (README.md) is missing next to server.py. ./deploy.sh copies it into the app bundle."},
    "fr": {"titel": "Aide", "zurueck": "Retour à l’application", "sprache": "Langue",
           "englisch": "Ce guide n'existe pas encore en français — voici la version anglaise.",
           "fehlt": "Le guide (README.md) est absent à côté de server.py. ./deploy.sh le copie dans l’application."},
    "es": {"titel": "Ayuda", "zurueck": "Volver a la aplicación", "sprache": "Idioma",
           "englisch": "Esta guía aún no existe en español — aquí está la versión en inglés.",
           "fehlt": "Falta la guía (README.md) junto a server.py. ./deploy.sh la copia en el paquete de la aplicación."},
}

# Farben wie index.html (dunkel) und mobile.html (Tageslicht-Modus); hell folgt dem System
# (prefers-color-scheme) — die Seite hat kein Skript, das den Schalter der App lesen könnte.
# Breite höchstens 760px, am iPhone 16px Rand (mit Safe Area); Tabellen und Code scrollen waagrecht.
STIL = """\
:root{--bg:#0f0e0c;--surface:#1a1916;--surface2:#232220;--border:#2e2c29;--border2:#3d3b37;\
--text:#e8e4dc;--text2:#b5b0a4;--text3:#8a857a;--accent:#c8a95a;--accent2:#8fb87a;--accent3:#e07a5f;\
--accent4:#7eb8c9;--accent5:#c47eb5;\
--mono:'IBM Plex Mono',ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,monospace;\
--serif:'Fraunces','Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;\
--sans:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg:#f2efe6;--surface:#faf8f1;--surface2:#fff;--border:#d9d3c3;\
--border2:#c8c1ae;--text:#1e1c16;--text2:#45412f;--text3:#6d6857;--accent:#8a6a1e;--accent2:#3e7a2d;\
--accent3:#b23f27;--accent4:#226e86;--accent5:#8a3f78;color-scheme:light}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 var(--sans);overflow-wrap:break-word}
.kopf{position:sticky;top:0;z-index:1;display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;\
padding:max(10px,env(safe-area-inset-top)) max(16px,env(safe-area-inset-right)) 10px max(16px,env(safe-area-inset-left));\
background:var(--surface);border-bottom:1px solid var(--border)}
.zurueck{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;flex:none;\
border:1px solid var(--border2);border-radius:8px;color:var(--text);text-decoration:none;font-size:19px;line-height:1}
.zurueck:hover{background:var(--surface2)}
.marke{font-family:'Avenir Next',Avenir,Futura,'Century Gothic','Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,\
sans-serif;font-size:20px;font-weight:700;letter-spacing:-.01em;line-height:1.15;white-space:nowrap;color:var(--text)}
.marke-akzent{color:var(--accent)}
.unter{font-family:var(--mono);font-size:11px;color:var(--text3);letter-spacing:.1em;text-transform:uppercase}
.sprachen{margin-left:auto;font-size:14px;color:var(--text3)}
.sprachen a{display:inline-block;padding:6px 1px;color:var(--text2);text-decoration:none}
.sprachen a:hover{color:var(--text);text-decoration:underline}
.sprachen a[aria-current]{color:var(--accent);font-weight:600}
main{max-width:760px;margin:0 auto;padding:18px max(16px,env(safe-area-inset-right)) \
calc(48px + env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left))}
.sprachhinweis{margin:0 0 18px;padding:10px 14px;border:1px solid var(--border2);border-left:3px solid var(--accent);\
border-radius:6px;background:var(--surface);color:var(--text2);font-size:14px}
h1,h2,h3,h4,h5,h6{font-family:var(--serif);font-weight:500;line-height:1.25;scroll-margin-top:72px}
h1{font-size:2em;margin:.2em 0 .5em}
h2{font-size:1.5em;margin:1.8em 0 .6em;padding-bottom:.25em;border-bottom:1px solid var(--border)}
h3{font-size:1.2em;margin:1.5em 0 .5em}
h4,h5,h6{font-size:1.05em;margin:1.3em 0 .4em}
p,ul,ol,pre,blockquote,.tabelle{margin:0 0 1em}
a{color:var(--accent4)}
a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:3px}
ul,ol{padding-left:1.5em}
li>ul,li>ol{margin:.25em 0 0}
li+li{margin-top:.25em}
li>p{margin:0 0 .5em}
code{font-family:var(--mono);font-size:.86em;background:var(--surface2);border:1px solid var(--border);\
border-radius:4px;padding:.08em .35em}
pre{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 14px;\
overflow-x:auto;-webkit-overflow-scrolling:touch;line-height:1.45}
pre code{background:none;border:0;padding:0;font-size:.84em;white-space:pre}
blockquote{padding:.5em 1em;border-left:3px solid var(--border2);color:var(--text2)}
blockquote>:last-child{margin-bottom:0}
.kasten{background:var(--surface);border-radius:0 6px 6px 0;color:var(--text)}
.kasten-titel{font-weight:600;margin-bottom:.4em}
.notiz{border-left-color:var(--accent4)}.notiz .kasten-titel{color:var(--accent4)}
.tipp{border-left-color:var(--accent2)}.tipp .kasten-titel{color:var(--accent2)}
.wichtig{border-left-color:var(--accent5)}.wichtig .kasten-titel{color:var(--accent5)}
.warnung{border-left-color:var(--accent)}.warnung .kasten-titel{color:var(--accent)}
.vorsicht{border-left-color:var(--accent3)}.vorsicht .kasten-titel{color:var(--accent3)}
hr{border:0;border-top:1px solid var(--border);margin:2em 0}
.tabelle{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;font-size:14px;line-height:1.45;overflow-wrap:normal}
th,td{border:1px solid var(--border);padding:6px 10px;vertical-align:top;text-align:left}
th{background:var(--surface);font-weight:600}
td.lang{min-width:14em}
td code,th code{white-space:nowrap}
th.rechts,td.rechts{text-align:right}
th.mitte,td.mitte{text-align:center}
@media (max-width:520px){.sprachen{margin-left:0;flex-basis:100%}h1{font-size:1.7em}h2{font-size:1.35em}}
"""


def _pruefsumme(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


# Strenge Richtlinie nur für diese Seite: kein Skript, nichts von außen, kein Formular, kein
# Einbetten in fremde Seiten. Der Stil ist per Prüfsumme freigegeben — style-Attribute gibt es
# nicht (Tabellen richten sich über Klassen aus).
CSP = ("default-src 'none'; style-src " + _pruefsumme(STIL)
       + "; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")


def _hilfe_adresse(sprache: str, herkunft: str) -> str:
    return f"{ANLEITUNG_PFAD}?lang={sprache}" + (f"&from={herkunft}" if herkunft else "")


def seite(sprache: str, herkunft: str = "", wurzel: Path = WURZEL) -> tuple[int, str]:
    """Die ganze Seite /hilfe: (Status, HTML).

    `sprache` aus `?lang=` (unbekannt → Englisch), `herkunft` aus `?from=`
    — nur /index.html, /mobile.html und /pois.html, sonst führt „←“ nach /.
    Die Sprachlinks und die README-Links im Text behalten die Herkunft, damit
    „←“ nach dem Umschalten noch zur richtigen Seite führt (am iPhone ist /
    die Mac-Oberfläche)."""
    sprache = sprache_waehlen(sprache)
    herkunft = herkunft if herkunft in HERKUNFT else ""
    t = TEXTE[sprache]
    try:
        a = anleitung(sprache, wurzel)
        status, inhalt = 200, a.html
        if herkunft:
            # README-Links im Text (gerendert ohne Herkunft, einmal für alle Anfragen)
            inhalt = re.sub(r'href="/hilfe\?lang=([a-z]{2})(?=["#])',
                            lambda m: 'href="' + html.escape(_hilfe_adresse(m.group(1), herkunft)), inhalt)
        if not a.uebersetzt:
            inhalt = f'<p class="sprachhinweis" role="note">{_esc(t["englisch"])}</p>\n<article lang="{a.sprache}">\n{inhalt}</article>'
        else:
            inhalt = f'<article lang="{a.sprache}">\n{inhalt}</article>'
    except FileNotFoundError:
        status = 404
        inhalt = f'<p class="sprachhinweis" role="alert">{_esc(t["fehlt"])}</p>'
    sprachlinks = " · ".join(
        f'<a href="{_attr(_hilfe_adresse(s, herkunft))}" hreflang="{s}" lang="{s}"'
        + (' aria-current="page"' if s == sprache else "") + f">{_esc(name)}</a>"
        for s, name in SPRACHNAMEN)
    seite_html = (
        "<!DOCTYPE html>\n"
        f'<html lang="{sprache}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="color-scheme" content="dark light">\n'
        f"<title>Safari Assistant · {_esc(t['titel'])}</title>\n"
        f"<style>{STIL}</style>\n</head>\n<body>\n"
        '<header class="kopf">\n'
        f'<a class="zurueck" href="{_attr(herkunft or "/")}" title="{_attr(t["zurueck"])}" '
        f'aria-label="{_attr(t["zurueck"])}">←</a>\n'
        # 2026-10-04-2: Wortmarke „Safari Assistant“ als Text (wie die Seitenleiste in index.html), „Assistant“ in der Akzentfarbe
        '<span class="marke"><span>Safari</span> <span class="marke-akzent">Assistant</span></span> '
        f'<span class="unter">{_esc(t["titel"])}</span>\n'
        f'<nav class="sprachen" aria-label="{_attr(t["sprache"])}">{sprachlinks}</nav>\n'
        "</header>\n"
        f"<main>\n{inhalt}\n</main>\n</body>\n</html>\n")
    return status, seite_html
