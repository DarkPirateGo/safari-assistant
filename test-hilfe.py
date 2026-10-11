# Ausgeführter Test der Hilfe (2026-10-04-2, Safari Assistant): hilfe.py — der Markdown-Renderer der Anleitung —
# und die Seite /hilfe am echten SafariServer (127.0.0.1, Zufallsport, echte HTTP-Anfragen). Wird von
# test-app.js (Sektion 63) ausgeführt; läuft mit Python 3.9+ ohne Internet. Geprüft wird das Modul,
# das server.py selbst geladen hat (m.HILFE) — nicht eine zweite Kopie.
#
# Teile: 1. Escaping und rohes HTML  2. Links  3. Überschriften und Anker  4. Blöcke (Listen, Tabellen,
# Code, Hinweiskästen, Sprachzeile)  5. Sprachen und Rückfall auf Englisch  6. Gemerkt je Dateistand
# 7. Die echte Anleitung  8. Die Route /hilfe (Richtlinie, Header, keine Dateien über den Pfad)
# 9. Zugang aus dem WLAN: genau wie mobile.html (iPhone-Modus + Zugangscode)
import sys, importlib.util, threading, tempfile, shutil, os, re, http.client, time
sys.dont_write_bytecode = True   # kein __pycache__ neben server.py (enthielte absolute Pfade)
from pathlib import Path
from html.parser import HTMLParser
sys.argv = ['server.py']
spec = importlib.util.spec_from_file_location("srv", SERVER_PFAD)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
f = []
tmp = Path(tempfile.mkdtemp(prefix='dark-hilfe-test-'))
server = []


def pruefe(bedingung, meldung):
    if not bedingung:
        f.append(meldung)


class _Tags(HTMLParser):
    """Alle Start-Tags mit Attributen, und ob jedes Tag in der richtigen Reihenfolge zugeht."""
    LEER = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.offen, self.fehler = [], [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))
        if tag not in self.LEER:
            self.offen.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_endtag(self, tag):
        if tag in self.LEER:
            return
        if not self.offen or self.offen[-1] != tag:
            self.fehler.append('</%s> bei offen %s' % (tag, self.offen[-3:]))
            return
        self.offen.pop()


def tags(text):
    leser = _Tags()
    leser.feed(text)
    leser.close()
    return leser


def sauber(text, wo):
    """Ausgeglichen, keine Ereignisattribute, kein style-Attribut (CSP), jedes href erlaubt."""
    t = tags(text)
    pruefe(not t.fehler and not t.offen, '%s: Tags unausgeglichen %s %s' % (wo, t.fehler[:2], t.offen[-3:]))
    for tag, attrs in t.tags:
        for name, wert in attrs:
            pruefe(not name.lower().startswith('on'), '%s: Ereignisattribut <%s %s>' % (wo, tag, name))
            pruefe(name.lower() != 'style', '%s: style-Attribut <%s> (CSP lässt es nicht zu)' % (wo, tag))
            if name == 'href':
                pruefe(re.match(r'^(?:https?://|mailto:|#|/hilfe\?lang=(?:de|en|fr|es)(?:&from=/\w+\.html)?(?:#|$)|/(?:index|mobile|pois)\.html$|/$)', wert or ''),
                       '%s: unerlaubtes href %r' % (wo, wert))


try:
    h = m.HILFE
    if h is None:
        raise RuntimeError('server.py hat hilfe.py nicht geladen: %s' % m.HILFE_FEHLER)

    def md(text, **optionen):
        return h.rendern(text, **optionen).html

    # ── 1. Escaping und rohes HTML ──────────────────────────────────────────
    pruefe(md('a < b & c > d') == '<p>a &lt; b &amp; c &gt; d</p>\n', 'Escaping im Text: %r' % md('a < b & c > d'))
    pruefe(md('`<b>&amp;`') == '<p><code>&lt;b&gt;&amp;amp;</code></p>\n', 'Escaping im Code: %r' % md('`<b>&amp;`'))
    pruefe(md('```\n<b>\n```') == '<pre><code>&lt;b&gt;\n</code></pre>\n', 'Escaping im Codeblock')
    pruefe(md('&copy; &amp; &unbekannt; &#38;') == '<p>© &amp; &amp;unbekannt; &amp;</p>\n', 'Entitäten: %r' % md('&copy; &amp; &unbekannt; &#38;'))
    readme = ('Vorher.\n\n<p align="center">\n<picture><source media="(prefers-color-scheme: dark)" srcset="docs/a.png">'
              '<img src="docs/b.png" width="250" alt="Bild"></picture>\n</p>\n\nNachher.')
    pruefe(md(readme) == '<p>Vorher.</p>\n<p>Nachher.</p>\n', 'HTML-Block nicht weggelassen: %r' % md(readme))
    pruefe(md('<!-- Notiz -->\n\nText') == '<p>Text</p>\n', 'Kommentar nicht weggelassen')
    pruefe(md('a <kbd>Strg</kbd>+<kbd>C</kbd> <br> b') == '<p>a Strg+C <br>\n b</p>\n', 'Tags im Absatz: %r' % md('a <kbd>Strg</kbd>+<kbd>C</kbd> <br> b'))
    pruefe(md('x <span style="color:red">rot</span> y') == '<p>x rot y</p>\n', 'span mit style nicht weggelassen')
    pruefe(md('![Karte: Kenia](docs/karte.png)') == '<p>Karte: Kenia</p>\n', 'Bild nicht zu Alternativtext')
    feindlich = [
        '<script>alert(1)</script>', 'Hallo <script>alert(1)</script> Welt', 'x <img src=x onerror=alert(1)> y <svg onload=alert(1)>',
        '<iframe src=javascript:alert(1)></iframe>', "<div onclick='alert(1)'>\n*mehr*\n</div>", '<a href="javascript:alert(1)">klick</a>',
        '[a](javascript:alert(1)) [b](JaVaScRiPt:alert(1)) [c](&#106;avascript:alert(1)) [d](&#x6A;avascript:x)',
        '[e](data:text/html;base64,PHNjcmlwdD4=) [f](vbscript:msgbox) [g](file:///etc/passwd) [h](//evil.example/)',
        '[i](<java script:alert(1)>) [j](\\javascript:alert(1)) [k](javascript&colon;alert(1))', '<javascript:alert(1)> <data:text/html,x>',
        '![x](javascript:alert(1)) ![y" onerror="alert(1)](z.png)', '[x](http://a "t\\" onmouseover=\\"alert(1)")',
        '[x](http://a"onmouseover="alert(1))', '| <script> | <b>x</b> |\n|---|---|\n| [y](javascript:z) | `<i>` |',
        '> <script>alert(1)</script>\n> [z](javascript:x)', '- <img src=x onerror=alert(1)>\n  - [w](javascript:w)',
        '**<script>** *</script>* ~~<style>~~', '[\x00x](http://a\x00b) \ud800', 'Text\n<script>\nalert(1)\n</script>\nnach',
        '<style>body{display:none}</style>\n\nweiter', '> [!WARNING]\n> <script>alert(1)</script> [n](javascript:n)',
    ]
    for text in feindlich:
        aus = md(text)
        pruefe(not re.search(r'<\s*/?\s*(?:script|iframe|img|svg|style|object|embed|span|kbd|a\s+href="(?:javascript|data))', aus.lower()),
               'feindlich %r → %r' % (text[:40], aus[:120]))
        pruefe('javascript:' not in ' '.join(v or '' for _, a in tags(aus).tags for _, v in a).lower(), 'javascript: in einem Attribut: %r' % text[:40])
        sauber(aus, 'feindlich %r' % text[:30])

    # ── 2. Links ────────────────────────────────────────────────────────────
    blob = 'https://github.com/DarkPirateGo/safari-assistant/blob/main/'
    faelle = {
        'README.md': ('/hilfe?lang=en', False), 'README.de.md': ('/hilfe?lang=de', False), './README.fr.md': ('/hilfe?lang=fr', False),
        'README.es.md#iphone-mode': ('/hilfe?lang=es#iphone-mode', False), '/README.md#x': ('/hilfe?lang=en#x', False),
        'README.pt.md': (blob + 'README.pt.md', True),
        'LICENSE': (blob + 'LICENSE', True), 'SECURITY.md#the-local-certificate-authority': (blob + 'SECURITY.md#the-local-certificate-authority', True),
        'docs/SETUP.md#6-offline-map': (blob + 'docs/SETUP.md#6-offline-map', True), '/CHANGELOG.md': (blob + 'CHANGELOG.md', True),
        'tools/privacy_gate.py': (blob + 'tools/privacy_gate.py', True), 'docs/../NOTICE.md': (blob + 'NOTICE.md', True),
        'Mein Ordner/datei.md': (blob + 'Mein%20Ordner/datei.md', True), '.': ('https://github.com/DarkPirateGo/safari-assistant', True),
        '#iphone-mode': ('#iphone-mode', False),
        'https://ollama.com': ('https://ollama.com', True), 'http://a.example/x y': ('http://a.example/x%20y', True),
        'mailto:a@b.example': ('mailto:a@b.example', True),
    }
    for adresse, soll in faelle.items():
        ist = h.link_ziel(adresse)
        pruefe(ist == soll, 'link_ziel(%r) = %r statt %r' % (adresse, ist, soll))
    for adresse in ('javascript:alert(1)', ' JavaScript:alert(1)', 'java\tscript:x', '\x01javascript:x', 'data:text/html,x',
                    'data:image/png;base64,AAAA', 'vbscript:x', 'file:///etc/passwd', 'ftp://x', '//evil.example/x', '\\\\evil\\x',
                    '../../etc/passwd', '../x', '', '   ', 'ht tp://x', 'java script:x'):
        pruefe(h.link_ziel(adresse) is None, 'link_ziel(%r) ist ein Link: %r' % (adresse, h.link_ziel(adresse)))
    aus = md('[Deutsch](README.de.md) · [Lizenz](LICENSE) · [böse](javascript:alert(1)) · [daten](data:text/html,x) · '
             '[Mail](mailto:x@y.example) · [hier](#oben) · [Web](https://example.org)')
    for muss in ('<a href="/hilfe?lang=de">Deutsch</a>',
                 '<a href="%sLICENSE" target="_blank" rel="noopener noreferrer">Lizenz</a>' % blob,
                 ' böse ', ' daten ', '<a href="mailto:x@y.example" target="_blank" rel="noopener noreferrer">Mail</a>',
                 '<a href="#oben">hier</a>', '<a href="https://example.org" target="_blank" rel="noopener noreferrer">Web</a>'):
        pruefe(muss in aus, 'Links im Text: fehlt %r in %r' % (muss, aus))
    pruefe(aus.count('<a ') == 5, 'Links im Text: %d statt 5 klickbare Links' % aus.count('<a '))

    # ── 3. Überschriften und Anker wie auf GitHub ───────────────────────────
    slugs = {
        'iPhone mode': 'iphone-mode', 'Light profile (16–24 GB RAM)': 'light-profile-1624-gb-ram',
        'For non-German speakers': 'for-non-german-speakers', 'The benchmark — is it still right?': 'the-benchmark--is-it-still-right',
        'Über Safari Assistant': 'über-safari-assistant', 'Marées — pleine et basse mer': 'marées--pleine-et-basse-mer',
        '¿Qué tan segura es la previsión?': 'qué-tan-segura-es-la-previsión', 'wind_factor & 2.1.0 🌊': 'wind_factor--210-',
        'C++ / C#': 'c--c', '6. Offline map': '6-offline-map',
    }
    for text, soll in slugs.items():
        pruefe(h.slug(text) == soll, 'slug(%r) = %r statt %r' % (text, h.slug(text), soll))
    s = h.Slugs()
    pruefe([s(x) for x in ('Karte', 'Karte', 'karte', 'Karte-1', 'Karte')] == ['karte', 'karte-1', 'karte-2', 'karte-1-1', 'karte-3'],
           'doppelte Anker nicht wie GitHub nummeriert')
    g = h.rendern('# Titel\n\n## `server.py` — *der* Kern\n\n### Karte\n\n### Karte\n\n#### Vier ####\n\nSiehe [Karte](#karte-1).')
    for muss in ('<h1 id="titel">Titel</h1>', '<h2 id="serverpy--der-kern"><code>server.py</code> — <em>der</em> Kern</h2>',
                 '<h3 id="karte">Karte</h3>', '<h3 id="karte-1">Karte</h3>', '<h4 id="vier">Vier</h4>', '<a href="#karte-1">Karte</a>'):
        pruefe(muss in g.html, 'Überschriften: fehlt %r' % muss)
    pruefe([(st, a) for st, a, _ in g.ueberschriften] == [(1, 'titel'), (2, 'serverpy--der-kern'), (3, 'karte'), (3, 'karte-1'), (4, 'vier')],
           'Überschriften-Liste: %r' % g.ueberschriften)
    pruefe(g.anker == ['karte-1'], 'Anker-Liste: %r' % g.anker)
    pruefe(md('# A\n## B', versatz=1) == '<h2 id="a">A</h2>\n<h3 id="b">B</h3>\n', 'versatz')

    # ── 4. Blöcke ───────────────────────────────────────────────────────────
    aus = md('- eins\n  - zwei\n    1. drei\n    2. vier\n- fünf\n\n3) ab drei\n4) weiter')
    pruefe(aus == '<ul>\n<li>eins\n<ul>\n<li>zwei\n<ol>\n<li>drei</li>\n<li>vier</li>\n</ol></li>\n</ul></li>\n'
                  '<li>fünf</li>\n</ul>\n<ol start="3">\n<li>ab drei</li>\n<li>weiter</li>\n</ol>\n', 'verschachtelte Listen: %r' % aus)
    aus = md('- **Fett** — erste Zeile\n  zweite Zeile\n\n- nächster Punkt\nfaul fortgesetzt')
    pruefe(aus == '<ul>\n<li>\n<p><strong>Fett</strong> — erste Zeile\nzweite Zeile</p>\n</li>\n<li>\n<p>nächster Punkt\nfaul fortgesetzt</p>\n</li>\n</ul>\n',
           'lose Liste: %r' % aus)
    aus = md('| Option | Bedeutung | x |\n|:---|---:|:-:|\n| `--lan de\\|en` | **fett** \\| Strich |\n| eins |')
    pruefe(aus == '<div class="tabelle"><table>\n<thead><tr><th class="links">Option</th><th class="rechts">Bedeutung</th>'
                  '<th class="mitte">x</th></tr></thead>\n<tbody>\n<tr><td class="links"><code>--lan de|en</code></td>'
                  '<td class="rechts"><strong>fett</strong> | Strich</td><td class="mitte"></td></tr>\n'
                  '<tr><td class="links">eins</td><td class="rechts"></td><td class="mitte"></td></tr>\n</tbody>\n</table></div>\n',
           'Tabelle: %r' % aus)
    aus = md('| a | b |\n|---|---|\n| ' + 'lang ' * 12 + '| x |')
    pruefe('<td class="lang">' in aus and 'style=' not in aus, 'Tabelle: lange Zelle ohne Klasse „lang" oder mit style: %r' % aus)
    pruefe(md('a | b\n--- | --- | ---') == '<p>a | b\n--- | --- | ---</p>\n', 'Tabelle ohne passende Trennzeile')
    g = h.rendern('```bash\npython3 server.py   # Kommentar\n```\n\n~~~\n```\n~~~\n\n    eingerückt\n')
    pruefe(g.html == '<pre><code class="language-bash">python3 server.py   # Kommentar\n</code></pre>\n<pre><code>```\n</code></pre>\n'
                     '<pre><code>eingerückt\n</code></pre>\n', 'Code: %r' % g.html)
    pruefe(g.zaeune == 2, 'Zahl der Codezäune: %r' % g.zaeune)
    aus = md('> Zitat\nfaul\n> > tiefer\n\n---\n\nTitel\n=====')
    pruefe(aus == '<blockquote>\n<p>Zitat\nfaul</p>\n<blockquote>\n<p>tiefer</p>\n</blockquote>\n</blockquote>\n<hr>\n<h1 id="titel">Titel</h1>\n',
           'Zitat/Linie/Überschrift: %r' % aus)
    aus = md('> [!IMPORTANT]\n> - **Nur Apple Silicon.**\n> - 32 GB', sprache='de')
    pruefe(aus == '<blockquote class="kasten wichtig">\n<p class="kasten-titel">Wichtig</p>\n<ul>\n<li><strong>Nur Apple Silicon.</strong></li>\n'
                  '<li>32 GB</li>\n</ul>\n</blockquote>\n', 'Hinweiskasten: %r' % aus)
    pruefe('<p class="kasten-titel">Note</p>\n<p>Text</p>' in md('> [!note]\n> Text'), 'Hinweiskasten (klein geschrieben, englisch)')
    pruefe(md('> [!FOO]\n> x') == '<blockquote>\n<p>[!FOO]\nx</p>\n</blockquote>\n', 'unbekannter Kasten ist ein Zitat')
    sprachzeile = ('# Safari Assistant\n\n*This guide in: **English** · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)*\n\n'
                   'Siehe [die deutsche](README.de.md).')
    pruefe(md(sprachzeile, ohne_sprachzeile=True) == '<h1 id="safari-assistant">Safari Assistant</h1>\n<p>Siehe <a href="/hilfe?lang=de">die deutsche</a>.</p>\n',
           'Sprachzeile fällt nicht weg: %r' % md(sprachzeile, ohne_sprachzeile=True))
    pruefe('This guide in' in md(sprachzeile), 'Sprachzeile fehlt ohne ohne_sprachzeile')
    for text in ('**fett', '*a **b', '[link(', '[a](http://b', '![bild', '`code', '```\noffen', '> zitat\n>> tiefer\n- liste\n  * innen',
                 '**a [b** c](http://d)', '_*_*_*', '[[[x]]]', 'a\\', '<<<>>>', '&&&;;'):
        sauber(md(text), 'unausgeglichen %r' % text)
    beginn = time.monotonic()
    for text in ('x <!--' * 15000, '[' * 5000 + 'x' + '](http://a)' * 10, '*a _b ' * 10000, '> ' * 500 + 'tief',
                 '\n'.join('  ' * i + '- x' for i in range(200))):
        sauber(md(text), 'Laufzeit/Tiefe')
    pruefe(time.monotonic() - beginn < 15, 'feindliche Eingaben brauchen %.1f s (quadratisch?)' % (time.monotonic() - beginn))

    # ── 5. Sprachen und Rückfall auf Englisch ───────────────────────────────
    for wert, soll in (('de', 'de'), ('EN', 'en'), ('fr-FR', 'fr'), ('es_ES', 'es'), ('pt', 'en'), ('', 'en'), (None, 'en'),
                       ('../../etc/passwd', 'en'), ('<script>', 'en')):
        pruefe(h.sprache_waehlen(wert) == soll, 'sprache_waehlen(%r) = %r' % (wert, h.sprache_waehlen(wert)))
    w = tmp / 'wurzel'
    (w / 'release-docs').mkdir(parents=True)
    (w / 'release-docs' / 'README.md').write_text('# Safari Assistant\n\n## Usage\n\nEnglish text. [Deutsch](README.de.md)\n', encoding='utf-8')
    (w / 'release-docs' / 'README.fr.md').write_text('# Safari Assistant\n\n## Utilisation\n\nTexte français.\n', encoding='utf-8')
    h.vergessen()
    hinweise = {'de': 'Diese Anleitung gibt es noch nicht auf Deutsch — hier die englische Fassung.',
                'es': 'Esta guía aún no existe en español — aquí está la versión en inglés.'}
    for sprache, satz in hinweise.items():
        st, seite = h.seite(sprache, '', w)
        pruefe(st == 200, '%s: Status %s' % (sprache, st))
        pruefe('<p class="sprachhinweis" role="note">%s</p>' % satz in seite, '%s: Hinweis fehlt' % sprache)
        pruefe(seite.index('class="sprachhinweis"') < seite.index('<h1'), '%s: Hinweis steht nicht oben' % sprache)
        pruefe('<html lang="%s">' % sprache in seite and '<article lang="en">' in seite and 'English text.' in seite,
               '%s: Sprache der Seite/des Texts falsch' % sprache)
        sauber(seite.split('<body>', 1)[1].rsplit('</body>', 1)[0], 'Seite %s' % sprache)
    st, seite = h.seite('fr', '', w)
    pruefe('class="sprachhinweis"' not in seite and '<article lang="fr">' in seite and 'Texte français.' in seite, 'fr: Übersetzung nicht genommen')
    pruefe('<a href="/hilfe?lang=fr" hreflang="fr" lang="fr" aria-current="page">Français</a>' in seite, 'fr: Sprachumschalter markiert nicht fr')
    pruefe(hinweise['de'] not in h.seite('en', '', w)[1] and 'class="sprachhinweis"' not in h.seite('en', '', w)[1], 'en: Hinweis, obwohl Original')
    for unbekannt in ('xx', 'pt', '../../etc', ''):
        st, seite = h.seite(unbekannt, '', w)
        pruefe('<html lang="en">' in seite and 'class="sprachhinweis"' not in seite and 'English text.' in seite, 'unbekannte Sprache %r ist nicht en' % unbekannt)
    # Neben server.py geht vor release-docs/ (öffentliches Repo: README im Hauptordner)
    (w / 'README.md').write_text('# Safari Assistant\n\nRoot text.\n', encoding='utf-8')
    pruefe('Root text.' in h.seite('en', '', w)[1], 'README.md neben server.py wird nicht zuerst genommen')
    # Herkunft: „←“ nur zu den drei Seiten, sonst nach /; Sprach- und README-Links behalten sie
    st, seite = h.seite('de', '/mobile.html', w)
    pruefe('<a class="zurueck" href="/mobile.html"' in seite, '← führt nicht zu /mobile.html')
    pruefe('<a href="/hilfe?lang=fr&amp;from=/mobile.html" hreflang="fr"' in seite, 'Sprachlinks ohne Herkunft')
    (w / 'README.md').unlink()
    h.vergessen()
    pruefe('<a href="/hilfe?lang=de&amp;from=/pois.html">Deutsch</a>' in h.seite('en', '/pois.html', w)[1], 'README-Link im Text ohne Herkunft')
    for fremd in ('https://evil.example/', '//evil.example', 'javascript:alert(1)', '/server.py', '/index.html?x=1', ''):
        pruefe('<a class="zurueck" href="/"' in h.seite('de', fremd, w)[1], '← mit fremder Herkunft %r führt nicht nach /' % fremd)
    # Ohne README.md: 404-Seite mit Satz in der Sprache, kein Absturz
    leer = tmp / 'leer'
    leer.mkdir()
    st, seite = h.seite('de', '', leer)
    pruefe(st == 404 and 'README.md' in seite and 'role="alert"' in seite, 'ohne README.md: Status %s' % st)

    # ── 6. Gemerkt je Stand der Datei (Änderungszeit, Größe) ────────────────
    datei = w / 'release-docs' / 'README.md'
    h.vergessen()
    zaehler = []
    echt = h.rendern
    h.rendern = lambda *a, **k: (zaehler.append(1), echt(*a, **k))[1]
    try:
        h.anleitung('en', w)
        h.anleitung('en', w)
        h.anleitung('de', w)
        pruefe(len(zaehler) == 1, 'README.md %d-mal gerendert statt einmal' % len(zaehler))
        datei.write_text('# Safari Assistant\n\n## Usage\n\nNeuer Stand.\n', encoding='utf-8')
        st_ = datei.stat()
        os.utime(str(datei), ns=(st_.st_atime_ns, st_.st_mtime_ns + 10 ** 9))
        pruefe('Neuer Stand.' in h.anleitung('en', w).html and len(zaehler) == 2, 'geänderte Datei nicht neu gerendert')
    finally:
        h.rendern = echt
        h.vergessen()
    (w / 'release-docs' / 'README.de.md').write_bytes(b'# Safari Assistant\n\n## Kaputt \xff\xfe\n\nText\x00 <script>x</script>\n')
    a = h.anleitung('de', w)
    pruefe(a.sprache == 'de' and a.uebersetzt and 'Kaputt' in a.html and '<script' not in a.html, 'kaputte Datei: %r' % a.html[:80])

    # ── 7. Die echte Anleitung (README.md neben server.py oder in release-docs/) ──
    echte = h.readme_datei('en', m.BASE_DIR)
    if echte is None:
        f.append('README.md fehlt neben server.py und in release-docs/')
    else:
        h.vergessen()
        g = h.rendern(echte.read_text(encoding='utf-8'), ohne_sprachzeile=True)
        sauber(g.html, 'README.md')
        anker = {a for _, a, _ in g.ueberschriften}
        pruefe([a for a in g.anker if a not in anker] == [], 'README.md: Anker ohne Überschrift %r' % [a for a in g.anker if a not in anker])
        pruefe(g.html.count('<h1') == 1, 'README.md: %d <h1> statt einer' % g.html.count('<h1'))
        for s in ('de', 'fr', 'es'):          # Übersetzungen, sobald es sie gibt
            datei = h.readme_datei(s, m.BASE_DIR)
            if datei is not None:
                gs = h.rendern(datei.read_text(encoding='utf-8'), ohne_sprachzeile=True, sprache=s)
                sauber(gs.html, datei.name)
                anker = {a for _, a, _ in gs.ueberschriften}
                pruefe([a for a in gs.anker if a not in anker] == [], '%s: Anker ohne Überschrift %r' % (datei.name, [a for a in gs.anker if a not in anker]))

    # ── 8. Die Route /hilfe am echten Server ────────────────────────────────
    m.SERVER_INFO.update({'port': 0, 'bind': '127.0.0.1', 'lan': False, 'basis': str(m.BASE_DIR), 'offen': False})

    def starten(handler):
        srv = m.SafariServer(('127.0.0.1', 0), handler)
        threading.Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.2}, daemon=True).start()
        server.append(srv)
        return srv.server_address[1]

    def anfrage(port, pfad, kopf=None):
        k = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        k.request('GET', pfad, headers=kopf or {})
        r = k.getresponse()
        body = r.read()
        hdr = {a.lower(): b for a, b in r.getheaders()}
        k.close()
        return r.status, hdr, body.decode('utf-8', 'replace')

    port = starten(m.SafariHandler)
    st, hdr, seite = anfrage(port, '/hilfe?lang=de&from=/index.html')
    pruefe(st == 200, '/hilfe: Status %s' % st)
    pruefe(hdr.get('content-type') == 'text/html; charset=utf-8', '/hilfe: Content-Type %r' % hdr.get('content-type'))
    csp = hdr.get('content-security-policy', '')
    pruefe(csp == h.CSP, '/hilfe: CSP %r' % csp)
    for muss in ("default-src 'none'", "style-src 'sha256-", "base-uri 'none'", "form-action 'none'", "frame-ancestors 'self'"):
        pruefe(muss in csp, '/hilfe: CSP ohne %s' % muss)
    pruefe('unsafe-inline' not in csp and 'script-src' not in csp, '/hilfe: CSP erlaubt Skripte oder Inline-Stil: %r' % csp)
    stil = re.findall(r'<style>(.*?)</style>', seite, re.S)
    pruefe(len(stil) == 1 and h._pruefsumme(stil[0]) in csp, '/hilfe: Prüfsumme des Stils passt nicht zur CSP')
    pruefe(not re.search(r'<script|<link|<img|<iframe|\ssrc=|url\(|@import', seite, re.I), '/hilfe: lädt etwas (Skript/Bild/Stylesheet)')
    for k, v in {'x-content-type-options': 'nosniff', 'x-frame-options': 'SAMEORIGIN', 'cache-control': 'no-cache'}.items():
        pruefe(hdr.get(k) == v, '/hilfe: Header %s = %r' % (k, hdr.get(k)))
    pruefe('<html lang="de">' in seite and '<a class="zurueck" href="/index.html"' in seite, '/hilfe: Sprache oder ← falsch')
    pruefe('<span class="marke"><span>Safari</span> <span class="marke-akzent">Assistant</span></span>' in seite
           and 'Deutsch</a> · <a' in seite and 'Español</a></nav>' in seite, '/hilfe: Kopf unvollständig')
    # 2026-10-04-2: App-Name im Titel und in der Wortmarke ist „Safari Assistant“ — kein „DARK“ mehr im Kopf
    pruefe('<title>Safari Assistant · Hilfe</title>' in seite and 'DARK' not in seite.split('<main>', 1)[0],
           '/hilfe: Titel/Kopf nennt nicht Safari Assistant oder noch DARK')
    sauber(seite.split('<body>', 1)[1].rsplit('</body>', 1)[0], '/hilfe')
    st, _, seite = anfrage(port, '/hilfe?lang=xx')
    pruefe(st == 200 and '<html lang="en">' in seite and '<a class="zurueck" href="/"' in seite, '/hilfe?lang=xx ist nicht Englisch')
    st, _, seite = anfrage(port, '/hilfe')
    pruefe(st == 200 and '<html lang="en">' in seite, '/hilfe ohne lang ist nicht Englisch')
    _, hdr, _ = anfrage(port, '/index.html')
    pruefe("frame-ancestors 'self'" in hdr.get('content-security-policy', '') and "default-src" not in hdr.get('content-security-policy', ''),
           'andere Seiten bekommen die Hilfe-CSP')
    for pfad in ('/hilfe/', '/hilfe/README.md', '/README.md', '/release-docs/README.md', '/hilfe.py', '/hilfe/../server.py',
                 '/i18n/', '/i18n/de.js'):
        st, _, body = anfrage(port, pfad)
        pruefe(st == 404, '%s: Status %s statt 404' % (pfad, st))
    st, _, _ = anfrage(port, '/hilfe', {'Host': 'evil.example'})
    pruefe(st == 421, '/hilfe mit fremdem Host: Status %s statt 421' % st)
    for pfad in ('/i18n.js', '/i18n/en.js', '/i18n/fr.js', '/i18n/es.js'):
        pruefe(m.STATIK_DATEIEN.get(pfad) == pfad, 'STATIK_DATEIEN ohne %s' % pfad)
    if (m.BASE_DIR / 'i18n.js').is_file():
        st, hdr, _ = anfrage(port, '/i18n.js')
        pruefe(st == 200 and 'javascript' in hdr.get('content-type', ''), '/i18n.js: Status %s, %r' % (st, hdr.get('content-type')))

    # ── 9. WLAN (iPhone): /hilfe genau wie mobile.html — nur im iPhone-Modus und mit Zugangscode ──
    class AusDemWlan(m.SafariHandler):
        def client_ip(self):
            return '192.168.178.9'

    code = 'testcode2345'
    alt_token, alt_an = m._TOKEN_CACHE['wert'], m.LAN_STATE['an']
    m._TOKEN_CACHE['wert'] = code          # kein Lesen/Schreiben von ~/.safari-assistant-zugang
    try:
        port_wlan = starten(AusDemWlan)
        for an in (False, True):
            m.LAN_STATE['an'] = an
            for pfad in ('/hilfe?lang=de&from=/mobile.html', '/mobile.html'):
                ohne = anfrage(port_wlan, pfad)[0]
                falsch = anfrage(port_wlan, pfad, {'Cookie': 'safari_zugang=falsch12345'})[0]
                mit = anfrage(port_wlan, pfad, {'Cookie': 'safari_zugang=' + code})[0]
                soll_mit = 200 if an else 403
                pruefe((ohne, falsch, mit) == (403, 403, soll_mit),
                       'WLAN (iPhone-Modus %s) %s: ohne/falsch/mit Code → %s statt %s' % ('an' if an else 'aus', pfad, (ohne, falsch, mit), (403, 403, soll_mit)))
        st, hdr, seite = anfrage(port_wlan, '/hilfe?lang=fr&from=/mobile.html&t=' + code)
        pruefe(st == 200 and 'safari_zugang=' + code in hdr.get('set-cookie', '') and hdr.get('content-security-policy') == h.CSP,
               'WLAN mit ?t=: Status %s, Cookie %r' % (st, hdr.get('set-cookie')))
        pruefe('<a class="zurueck" href="/mobile.html"' in seite, 'WLAN: ← führt nicht zu /mobile.html')
    finally:
        m._TOKEN_CACHE['wert'], m.LAN_STATE['an'] = alt_token, alt_an
except Exception as e:
    import traceback
    stelle = traceback.extract_tb(e.__traceback__)[-1]
    f.append('Ausnahme: %s: %s (Zeile %s)' % (e.__class__.__name__, e, stelle.lineno))
finally:
    for srv in server:
        try:
            srv.shutdown(); srv.server_close()
        except Exception:
            pass
    shutil.rmtree(str(tmp), ignore_errors=True)

print('FEHLER: ' + ' | '.join(f[:12]) + (' | … (%d insgesamt)' % len(f) if len(f) > 12 else '') if f else 'OK')
sys.exit(1 if f else 0)
