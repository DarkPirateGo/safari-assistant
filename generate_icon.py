#!/usr/bin/env python3
# Safari Assistant — Icon Generator
# Erstellt das App-Icon (weiße Schirmakazie vor tiefstehender Sonne, ✦ für den Assistenten,
# auf Terrakotta) als icon.png (1024x1024, iPhone-Home-Symbol) und icon.iconset/ (macOS).
#
# Nur Pillow nötig — kein cairosvg/rsvg: Das Motiv ist unten als Geometrie definiert und wird
# mit Pillow-Primitiven gezeichnet (4-fach überabgetastet). Dieselbe Geometrie schreibt auf
# Wunsch auch das SVG (--docs), damit SVG und PNGs nie auseinanderlaufen.
#
#   python3 generate_icon.py                    → icon.png + icon.iconset/
#   python3 generate_icon.py --docs docs/img/logo   → zusätzlich SVG + PNGs für Webseite/README

from PIL import Image, ImageDraw, ImageFilter
import math
import os
import sys

# ── Farben ──────────────────────────────────────────────────────────────────
BG    = '#c4532c'   # Terrakotta (Sonnenuntergang) — Weiß darauf: Kontrast 4.5:1
SUN   = '#e8a64e'   # tiefstehende Sonne, warmes Gold
FG    = '#ffffff'   # Akazie, Horizont, ✦

# ── Geometrie (Raster 1024 x 1024) ──────────────────────────────────────────
RADIUS = 229        # Eckenradius der Kachel (≈ 22,4 % wie bei iOS/macOS)

# Krone: geschlossene Catmull-Rom-Kurve durch diese Punkte (flaches Schirmdach)
CROWN = [(136, 376), (184, 336), (290, 302), (392, 284), (466, 288), (556, 270), (650, 278),
         (742, 288), (836, 318), (888, 362), (856, 384), (744, 396), (512, 406), (282, 401),
         (168, 394)]

# Stamm und Äste: sich verjüngende Striche entlang quadratischer Bézierkurven
#   (Start, Kontrollpunkt, Ende, Breite Start, Breite Ende, Wurzelverbreiterung)
LIMBS = [
    ((512, 748), (508, 680), (512, 610), 72, 54, 44),   # Stamm
    ((506, 636), (440, 524), (330, 374), 54, 36, 0),    # Ast links
    ((518, 632), (600, 524), (708, 368), 52, 34, 0),    # Ast rechts
    ((512, 614), (530, 504), (540, 374), 38, 26, 0),    # Ast Mitte
    ((430, 516), (436, 444), (440, 374), 28, 20, 0),    # Nebenast links
]

SUN_C, SUN_R = (512, 749), 268           # Halbscheibe über dem Horizont
GROUND = (132, 734, 892, 764)            # Horizontlinie (abgerundet)
SPARK_C, SPARK_R, SPARK_K = (796, 186), 62, 0.17   # ✦ — der Assistent


# ── Kurven → Punkte ─────────────────────────────────────────────────────────
def crown_segments():
    """Catmull-Rom (geschlossen) → kubische Bézier-Segmente (p0, c1, c2, p1)."""
    pts, n, segs = CROWN, len(CROWN), []
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segs.append((p1, c1, c2, p2))
    return segs


def cubic(p0, c1, c2, p1, t):
    u = 1 - t
    return (u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p1[0],
            u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p1[1])


def quad(p0, c, p1, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1])


def crown_polygon(steps=24):
    out = []
    for p0, c1, c2, p1 in crown_segments():
        out += [cubic(p0, c1, c2, p1, i / steps) for i in range(steps)]
    return out


def limb_polygon(p0, c, p1, w0, w1, flare, n=40):
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        x, y = quad(p0, c, p1, t)
        dx = 2 * (1 - t) * (c[0] - p0[0]) + 2 * t * (p1[0] - c[0])
        dy = 2 * (1 - t) * (c[1] - p0[1]) + 2 * t * (p1[1] - c[1])
        m = math.hypot(dx, dy) or 1
        nx, ny = -dy / m, dx / m
        w = (w0 + (w1 - w0) * t + flare * (1 - t) ** 4) / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    return left + right[::-1]


def spark_segments():
    (cx, cy), r = SPARK_C, SPARK_R
    a = r * SPARK_K
    tips = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    ctrl = [(cx + a, cy - a), (cx + a, cy + a), (cx - a, cy + a), (cx - a, cy - a)]
    return [(tips[i], ctrl[i], tips[(i + 1) % 4]) for i in range(4)]


def spark_polygon(steps=24):
    out = []
    for p0, c, p1 in spark_segments():
        out += [quad(p0, c, p1, i / steps) for i in range(steps)]
    return out


# ── SVG ─────────────────────────────────────────────────────────────────────
def f(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')


def svg(spark=True):
    crown = 'M%s %s' % (f(CROWN[0][0]), f(CROWN[0][1])) + ''.join(
        ' C%s %s %s %s %s %s' % (f(c1[0]), f(c1[1]), f(c2[0]), f(c2[1]), f(p1[0]), f(p1[1]))
        for _, c1, c2, p1 in crown_segments()) + ' Z'
    limbs = ''.join('<path d="M%s Z"/>' % ' L'.join('%s %s' % (f(x), f(y)) for x, y in limb_polygon(*l))
                    for l in LIMBS)
    (sx, sy), r = SUN_C, SUN_R
    x0, y0, x1, y1 = GROUND
    sp = ''
    if spark:
        segs = spark_segments()
        sp = '<path d="M%s %s' % (f(segs[0][0][0]), f(segs[0][0][1])) + ''.join(
            ' Q%s %s %s %s' % (f(c[0]), f(c[1]), f(p1[0]), f(p1[1])) for _, c, p1 in segs) + ' Z"/>'
    tile = '<rect width="1024" height="1024" rx="%d" fill="%s"/>' % (RADIUS, BG)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">\n'
            '<title>Safari Assistant</title>\n'
            f'{tile}\n'
            f'<path fill="{SUN}" d="M{sx - r} {sy} A{r} {r} 0 0 1 {sx + r} {sy} Z"/>\n'
            f'<g fill="{FG}">\n<path d="{crown}"/>\n{limbs}\n'
            f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="{(y1 - y0) / 2:g}"/>\n'
            f'{sp}\n</g>\n</svg>\n')


# ── Pillow-Zeichnung ────────────────────────────────────────────────────────
SS = 4   # Überabtastung gegen Treppenstufen


def draw_art(img, box, offset, spark=True, tile='round'):
    """Zeichnet das Motiv in img; box = Kantenlänge der Kachel, offset = (x, y)."""
    d = ImageDraw.Draw(img)
    s = box / 1024
    ox, oy = offset
    T = lambda p: (ox + p[0] * s, oy + p[1] * s)
    if tile == 'round':
        d.rounded_rectangle([ox, oy, ox + box - 1, oy + box - 1], radius=RADIUS * s, fill=BG)
    else:
        d.rectangle([ox, oy, ox + box - 1, oy + box - 1], fill=BG)
    (sx, sy), r = SUN_C, SUN_R
    d.pieslice([T((sx - r, sy - r)), T((sx + r, sy + r))], 180, 360, fill=SUN)
    d.polygon([T(p) for p in crown_polygon()], fill=FG)
    for l in LIMBS:
        d.polygon([T(p) for p in limb_polygon(*l)], fill=FG)
    x0, y0, x1, y1 = GROUND
    d.rounded_rectangle([T((x0, y0)), T((x1, y1))], radius=(y1 - y0) / 2 * s, fill=FG)
    if spark:
        d.polygon([T(p) for p in spark_polygon()], fill=FG)


def render(size, spark=True, tile='round'):
    """Kachel ohne Rand (Webseite/README, iPhone: tile='square')."""
    big = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    draw_art(big, size * SS, (0, 0), spark, tile)
    return big.resize((size, size), Image.LANCZOS)


def render_macos(size, spark=True):
    """macOS-Raster (Big Sur+): Kachel 824/1024 mittig, weicher Schatten darunter."""
    S = size * SS
    box = round(S * 824 / 1024)
    off = (S - box) // 2
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    shadow = Image.new('L', (S, S), 0)
    ImageDraw.Draw(shadow).rounded_rectangle(
        [off, off + S * 10 / 1024, off + box, off + box + S * 10 / 1024],
        radius=RADIUS * box / 1024, fill=int(255 * 0.30))
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 10 / 1024))
    img.paste((0, 0, 0, 255), (0, 0), shadow)
    tile = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw_art(tile, box, (off, off), spark)
    img.alpha_composite(tile)
    return img.resize((size, size), Image.LANCZOS)


# Ab dieser Größe abwärts ohne ✦ — bei 16/32 px wäre er nur ein Krümel
SMALL = 32

# ── App-Ordner: icon.png (iPhone) + icon.iconset (macOS) ────────────────────
here = os.path.dirname(os.path.abspath(__file__))

# iPhone (apple-touch-icon in mobile.html): randlos und deckend — iOS rundet selbst ab,
# transparente Ecken würden dort schwarz.
render(1024, tile='square').convert('RGB').save(os.path.join(here, 'icon.png'), 'PNG', optimize=True)
print(f'✅ Icon gespeichert: {os.path.join(here, "icon.png")}')

iconset = os.path.join(here, 'icon.iconset')
os.makedirs(iconset, exist_ok=True)
for pt in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        px = pt * scale
        name = f'icon_{pt}x{pt}{"@2x" if scale == 2 else ""}.png'
        render_macos(px, spark=px > SMALL).save(os.path.join(iconset, name), 'PNG', optimize=True)
print(f'✅ Iconset gespeichert: {iconset}/ (10 Größen)')

# ── Optional: SVG + PNGs für Webseite/README ────────────────────────────────
if '--docs' in sys.argv:
    out = sys.argv[sys.argv.index('--docs') + 1]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'safari-assistant-icon.svg'), 'w') as fh:
        fh.write(svg())
    for px in (1024, 512, 192, 32):
        render(px, spark=px > SMALL).save(os.path.join(out, f'safari-assistant-icon-{px}.png'), 'PNG', optimize=True)
    render(180, tile='square').convert('RGB').save(os.path.join(out, 'safari-assistant-icon-180.png'), 'PNG', optimize=True)
    print(f'✅ SVG + PNGs gespeichert: {out}/')

print('Nächster Schritt (auf dem Mac):')
print('  iconutil -c icns icon.iconset -o icon.icns')
print('  → build-app.sh übernimmt icon.icns automatisch als AppIcon.icns')
