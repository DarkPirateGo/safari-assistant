#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selbsttest / self-test for tools/privacy_gate.py (stdlib only, Python 3.9+).

Builds throw-away git repositories and plain folders in a temp dir and checks the gate end to end,
including the real git hooks. Prints one line per case and a final "OK n/n" or "FEHLER ..." line;
exit code 0 means every case passed.

This file is published and scanned by the gate itself: every suspicious sample (fake keys, relay
addresses, user paths, host names, coordinates, plates ...) is assembled at runtime. It never uses the
machine's global git configuration or identity (GIT_CONFIG_GLOBAL=/dev/null, GIT_CONFIG_NOSYSTEM=1,
fake HOME, identity via environment variables).
"""
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(HERE, 'privacy_gate.py')
HOOKS = os.path.join(ROOT, '.githooks')
HOOK_NAMES = ('pre-commit', 'commit-msg', 'pre-push')

# ---------------------------------------------------------------- fake samples (assembled at runtime)
AT = '@'
RELAY = 'x7y8z9' + AT + 'privaterelay' + '.appleid.com'
NOREPLY = '123456+DarkPirateGo' + AT + 'users.noreply.github.com'
BOT_MAIL = '49699333+dependabot[bot]' + AT + 'users.noreply.github.com'
WEB_MAIL = 'noreply' + AT + 'github.com'
EXAMPLE_MAIL = 'maxi' + AT + 'example.com'
LOCAL_MAIL = 'maxm' + AT + 'Maxs-Mac' + 'Book-Pro' + '.lo' + 'cal'
NODOT_MAIL = 'maxm' + AT + 'localhost'
ANTHROPIC_KEY = 'sk-' + 'ant-' + 'api03-' + 'Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv'
GITHUB_TOKEN = 'gh' + 'p_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
AWS_KEY = 'AK' + 'IA' + 'Z7Q2X9W4E1R6T3Y8'
USER_PATH = '/Users/' + 'maxm' + '/Projects/x'
HOST_URL = 'http://' + 'Maxs-Mac' + 'Book-Pro' + '.lo' + 'cal:8765/'
COORD = '45.' + '678912, ' + '12.' + '345678'
PLATE = 'M-XY' + ' 1234'
PHONE = '+49 30 ' + '5000 2000'
FENCE = '45.' + '6789,' + '12.' + '3456'            # centre of the test geofence (Northern Italy, fake)
NEAR = ('45.' + '6801', '12.' + '3502')               # ~0.4 km from the centre
FAR = ('45.' + '9000', '12.' + '9000')                # ~50 km away
SCISSORS = '# ' + '-' * 24 + ' >8 ' + '-' * 24

TERM_LINES = [
    '# Test-Liste / test list (fake values only)',   # line 1
    'word: Mustermann',                              # B-02
    'text: beispielweg 12',                          # B-03
    'regex: musterstadt-?\\d{3}',                    # B-04
    'geo: ' + FENCE + ',2',                          # B-05
    'word: Beispielhausen',                          # B-06
    'allow: 6 data/orte.json 2',                     # max. 2 hits of B-06 in data/orte.json
    'text: Grüngasse',                               # B-08
]


# ---------------------------------------------------------------- tiny image builders
def png(extra_chunks=()):
    def chunk(typ, data):
        return struct.pack('>I', len(data)) + typ + data + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 0, 0, 0, 0)
    body = b''.join(chunk(t, d) for t, d in extra_chunks)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + body + chunk(b'IDAT', zlib.compress(b'\x00\x00')) + chunk(b'IEND', b'')


def seg(marker, data):
    return b'\xff' + bytes([marker]) + struct.pack('>H', len(data) + 2) + data


def jpeg(extra=b'', trailer=b''):
    app0 = seg(0xE0, b'JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')
    sos = seg(0xDA, b'\x01\x01\x00\x00\x3f\x00')
    return b'\xff\xd8' + app0 + extra + sos + b'\x12\x34\x56' + b'\xff\xd9' + trailer


def exif_gps():
    tiff = b'MM\x00\x2a' + struct.pack('>I', 8) + struct.pack('>H', 1) + struct.pack('>HHII', 0x8825, 4, 1, 26) + struct.pack('>I', 0)
    return seg(0xE1, b'Exif\x00\x00' + tiff)


# ---------------------------------------------------------------- tiny MP4 builder (box layout like ffmpeg's mp4 muxer)
MIB = 1024 * 1024
ISO6709_KEY = 'com.apple.quicktime.' + 'location.ISO6709'
ISO6709_VALUE = '+12.' + '3456+045.' + '6789/'          # made-up place


def box(typ, payload=b''):
    return struct.pack('>I', 8 + len(payload)) + typ + payload


def mp4_item(typ, text):
    return box(typ, box(b'data', struct.pack('>II', 1, 0) + text.encode('utf-8')))


def mp4_keys(*names):
    """'keys' box of QuickTime metadata (the ilst items then use the 1-based index as type)."""
    return box(b'keys', b'\x00' * 4 + struct.pack('>I', len(names)) + b''.join(box(b'mdta', n.encode('ascii')) for n in names))


def mp4(tags=(), udta=b'', top=b'', brand=b'isom', size=None, trailer=b''):
    """ftyp, free, mdat, moov(mvhd, udta(meta(hdlr, [keys], ilst(©too 'Lavf…', tags)))) - tags: [(type, text)]."""
    ilst = box(b'ilst', mp4_item(b'\xa9too', 'Lavf60.16.100') + b''.join(mp4_item(t, v) for t, v in tags))
    meta = box(b'meta', b'\x00' * 4 + box(b'hdlr', b'\x00' * 8 + b'mdirappl' + b'\x00' * 9) + udta + ilst)
    moov = box(b'moov', box(b'mvhd', b'\x00' * 100) + box(b'udta', meta))
    ftyp = box(b'ftyp', brand + struct.pack('>I', 512) + b'isomiso2avc1mp41')
    media = b'\x00\x00\x00\x02\x09\xf0' * 8
    if size is not None:                                  # pad the media data to reach exactly <size> bytes
        media += b'\x00' * (size - len(ftyp) - 8 - 8 - len(media) - len(moov) - len(top) - len(trailer))
    out = ftyp + box(b'free') + box(b'mdat', media) + moov + top + trailer
    assert size is None or len(out) == size
    return out


# ---------------------------------------------------------------- harness
FIND = re.compile(r'^(BLOCKIERT / BLOCKED|WARNUNG / WARNING)  (\S+)  (.*)$')


def findings(out):
    res = []
    for line in out.splitlines():
        m = FIND.match(line)
        if m:
            res.append((m.group(1).startswith('BLOCK'), m.group(2), m.group(3)))
    return res


def has(out, rid, where=None, block=None):
    for b, r, rest in findings(out):
        if r != rid or (block is not None and b != block):
            continue
        if where is None or rest == where or rest.startswith(where + ' ') or rest.startswith(where + ':'):
            return True
    return False


class Suite(object):
    def __init__(self):
        self.n = self.failed = 0
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='privacy-gate-test-'))
        self.home = self.mkhome('home')
        self.bin = os.path.join(self.tmp, 'bin')
        os.makedirs(self.bin)
        os.symlink(sys.executable, os.path.join(self.bin, 'python3'))   # hooks use the interpreter under test

    # ------------------------------------------------------------- basics
    def check(self, name, cond, detail=''):
        self.n += 1
        if cond:
            print('ok     %3d  %s' % (self.n, name))
        else:
            self.failed += 1
            print('FEHLER %3d  %s%s' % (self.n, name, ('\n       ' + detail.strip().replace('\n', '\n       ')[:1500]) if detail else ''))
        return cond

    def mkhome(self, name, terms=None, mode=0o600):
        home = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(home, '.config', 'privacy-gate'))
        if terms is not None:
            p = os.path.join(home, '.config', 'privacy-gate', 'denylist.txt')
            self.write_file(p, '\n'.join(terms) + '\n')
            os.chmod(p, mode)
        return home

    def env(self, home=None, **extra):
        env = {}
        for k, v in os.environ.items():
            if k.startswith(('GIT_', 'PRIVACY_')) or k in ('HOME', 'XDG_CONFIG_HOME', 'TZ', 'EMAIL'):
                continue
            env[k] = v
        env.update(HOME=home or self.home, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_CEILING_DIRECTORIES=self.tmp, GIT_TERMINAL_PROMPT='0', TZ='UTC',
                   PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8',
                   PATH=self.bin + os.pathsep + os.environ.get('PATH', os.defpath),
                   GIT_AUTHOR_NAME='DARK', GIT_AUTHOR_EMAIL=NOREPLY, GIT_COMMITTER_NAME='DARK', GIT_COMMITTER_EMAIL=NOREPLY,
                   GIT_AUTHOR_DATE='2027-03-15T12:00:00+0000', GIT_COMMITTER_DATE='2027-03-15T12:00:00+0000')
        env['XDG_CONFIG_HOME'] = os.path.join(env['HOME'], '.config')
        for k, v in extra.items():
            if v is None:
                env.pop(k, None)
            else:
                env[k] = v
        return env

    @staticmethod
    def write_file(path, content):
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, 'wb') as fh:
            fh.write(content if isinstance(content, bytes) else content.encode('utf-8'))

    def git(self, repo, *args, **kw):
        p = subprocess.run(['git'] + list(args), cwd=repo, env=kw.get('env') or self.env(), input=kw.get('input'),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.stdout.decode('utf-8', 'replace')
        if kw.get('check', True) and p.returncode != 0:
            raise RuntimeError('git %s failed:\n%s' % (' '.join(args), out))
        return p.returncode, out

    def gate(self, cwd, *args, **kw):
        p = subprocess.run([sys.executable, GATE] + list(args), cwd=cwd, env=kw.get('env') or self.env(),
                           input=kw.get('input'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode('utf-8', 'replace')

    def repo(self, name, files=None, config=None, hooks=False):
        path = os.path.join(self.tmp, name)
        os.makedirs(path)
        self.git(path, 'init', '-q')
        self.git(path, 'symbolic-ref', 'HEAD', 'refs/heads/main')
        for k, v in (config or {}).items():
            self.git(path, 'config', k, v)
        if hooks:
            os.makedirs(os.path.join(path, '.githooks'))
            for h in HOOK_NAMES:
                shutil.copy2(os.path.join(HOOKS, h), os.path.join(path, '.githooks', h))
            with open(GATE, 'rb') as fh:
                self.write_file(os.path.join(path, 'tools', 'privacy_gate.py'), fh.read())
            with open(os.path.join(path, '.git', 'info', 'exclude'), 'a') as fh:
                fh.write('.githooks/\ntools/\n')
            self.git(path, 'config', 'core.hooksPath', '.githooks')
        for rel, content in (files or {}).items():
            self.write_file(os.path.join(path, rel), content)
        return path

    def commit(self, repo, msg, env=None, verify=False, check=True):
        self.git(repo, 'add', '-A', env=env)
        args = ['commit', '-q', '-m', msg] + ([] if verify else ['--no-verify'])
        return self.git(repo, *args, env=env, check=check)

    def head(self, repo):
        return self.git(repo, 'rev-parse', 'HEAD')[1].strip()

    # ------------------------------------------------------------- cases
    def t_cli(self):
        rc, out = self.gate(self.tmp, '--version')
        self.check('--version -> exit 0', rc == 0 and 'privacy_gate.py' in out, out)
        rc, out = self.gate(self.tmp, '--help')
        self.check('--help lists modes and config keys', rc == 0 and all(
            k in out for k in ('--staged', '--push', '--all', '--paths', 'privacy.allowedNames', 'privacy.allowedEmailRegex',
                               'privacy.requireUTC', 'privacy.requireDenylist', 'privacy.denylist')), out)
        rc, out = self.gate(self.tmp, '--bogus')
        self.check('unknown option -> exit 2', rc == 2, out)
        rc, out = self.gate(self.tmp)
        self.check('no mode -> exit 2', rc == 2, out)

    def t_paths_forbidden(self):
        files = {'track.gpx': '<gpx/>', 'export/my-backup.json': '{}', 'rag-store.json': '{}', 'karte.mbtiles': b'x',
                 'TODO.md': 'x', 'config/terms-denylist.txt': 'x', '__pycache__/x.cpython-39.pyc': b'\x00\x01',
                 '.DS_Store': b'\x00\x00\x00\x01Bud1', 'docs/modul/file.pdf': b'%PDF-1.4', 'photo.HEIC': b'\x00ftyp',
                 'tools/private-terms.txt': 'x', 'README.md': 'Hallo Welt\n'}
        repo = self.repo('forbidden', files)
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('forbidden paths -> exit 1', rc == 1, out)
        for p in sorted(files):
            if p != 'README.md':
                self.check('A-F01 forbidden path %s' % p, has(out, 'A-F01', p), out)
        self.check('clean README.md in the same commit has no finding', not any('README.md' in r for _, _, r in findings(out)), out)

    def t_secrets_personal(self):
        repo = self.repo('content', {
            'config.js': 'const a = "%s";\ntoken %s\n%s\n' % (ANTHROPIC_KEY, GITHUB_TOKEN, AWS_KEY),
            'sample.txt': 'Kontakt: %s\nPfad %s\n%s\nTreffpunkt %s\nKennzeichen %s\n' % (RELAY, USER_PATH, HOST_URL, COORD, PLATE),
        })
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('secrets/personal data -> exit 1', rc == 1, out)
        self.check('A-S03 fake Anthropic key', has(out, 'A-S03', 'config.js:1'), out)
        self.check('A-S05 fake GitHub token', has(out, 'A-S05', 'config.js:2'), out)
        self.check('A-S06 fake AWS key', has(out, 'A-S06', 'config.js:3'), out)
        self.check('A-P02 Apple relay e-mail', has(out, 'A-P02', 'sample.txt:1'), out)
        self.check('A-P03 /Users/<name>/ path', has(out, 'A-P03', 'sample.txt:2'), out)
        self.check('A-P05 <name>s-MacBook-Pro host', has(out, 'A-P05', 'sample.txt:3'), out)
        self.check('A-P06 .local host name', has(out, 'A-P06', 'sample.txt:3'), out)
        self.check('A-P13 coordinate pair in Europe (6 decimals)', has(out, 'A-P13', 'sample.txt:4'), out)
        self.check('A-P17 German plate with space', has(out, 'A-P17', 'sample.txt:5'), out)
        self.check('excerpts are masked (no full key, relay or path printed)',
                   ANTHROPIC_KEY[8:] not in out and RELAY not in out and USER_PATH not in out and AWS_KEY not in out, out)

    def t_clean_controls(self):
        clean = '\n'.join([
            'placeholder="sk-' + 'ant-..."', 'icon_32x32' + AT + '2x.png', 'noreply' + AT + 'anthropic.com', NOREPLY,
            'http://192.168.1.23:8765/go/abcd23456x', '127.0.0.1 0.0.0.0 8.8.8.8', '/Users/x/Library', '/Users/…/Library/Python',
            'https://macbook.local:8765/go/k7x2m9pq4d', '/Volumes/YourSSD/ollama', 'Leaflet 1.9.4', 'maplibre-gl-4.7.1.js',
            'HZJ78 · Südliches Afrika', '[[35.28,-17.13],[34.6,-16.2]]', 'Windhoek -22.5594, 17.0832', '+27 12 427 8900 (Pretoria)',
            'Notruf 10111', "TOKEN_ALPHABET = '23456789abcdefghjkmnpqrstuvwxyz'", 'vor Abreise erneut prüfen',
            'git' + AT + 'github.com:DarkPirateGo/safari-assistant.git', EXAMPLE_MAIL, 'v2027-03-15-1']) + '\n'
        data = '{"orte": [["Windhoek", -22.5594, 17.0832, 0, "o", 431000]], "pt": [38.5, 9.5], "t": [25.2, 24.7]}\n'
        repo = self.repo('clean', {'clean.txt': clean, 'data/klein.json': data, 'img/ok.png': png(), 'img/ok.jpg': jpeg()})
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('clean control files -> exit 0, no findings', rc == 0 and not findings(out), out)

    def t_images(self):
        files = {'a/c2pa.jpg': jpeg(seg(0xEB, b'JP\x00\x00' + b'\x00' * 8 + b'jumb')),
                 'a/text.png': png([(b'tEXt', b'Author\x00Maxi Mustermann')]),
                 'a/gps.jpg': jpeg(exif_gps()),
                 'a/trail.jpg': jpeg(trailer=b'MORE-IMAGE-DATA'),
                 'a/comment.jpg': jpeg(seg(0xFE, b'Maxi war hier'))}
        repo = self.repo('images', files)
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('images with metadata -> exit 1', rc == 1, out)
        self.check('A-F04 JPEG APP11 JUMBF/C2PA', has(out, 'A-F04', 'a/c2pa.jpg') and 'C2PA' in out, out)
        self.check('A-F04 PNG tEXt chunk', has(out, 'A-F04', 'a/text.png') and 'tEXt' in out, out)
        self.check('A-F04 JPEG EXIF GPS', has(out, 'A-F04', 'a/gps.jpg') and 'GPS' in out, out)
        self.check('A-F04 JPEG data after EOI', has(out, 'A-F04', 'a/trail.jpg'), out)
        self.check('A-F04 JPEG comment, content not printed', has(out, 'A-F04', 'a/comment.jpg') and 'war hier' not in out, out)

    def t_promo_video(self):
        # 2026-10-04: two exempt kinds - the phone promo and the desktop video, both named safari-assistant-* (2026-10-05:
        # English spelling; the German spelling safari-assistent-* of 2026-10-04 is no longer exempt).
        # The old names (docs/video/dark-promo-<xx>) are no longer exempt: they are blocked like any other video.
        vid, poster = 'docs/video/safari-assistant-promo-en.mp4', 'docs/video/safari-assistant-promo-en-poster.jpg'
        desk, desk_poster = 'docs/video/safari-assistant-desktop-en.mp4', 'docs/video/safari-assistant-desktop-en-poster.jpg'
        repo = self.repo('promo', {vid: mp4(), poster: jpeg(), 'docs/video/safari-assistant-promo-de-poster.png': png(),
                                   'docs/video/safari-assistant-promo-fr.mp4': mp4(size=3 * MIB),
                                   desk: mp4(size=3 * MIB), desk_poster: jpeg(), 'docs/video/safari-assistant-desktop-de-poster.png': png(),
                                   'docs/index.html': '<video src="video/safari-assistant-promo-en.mp4" poster="video/safari-assistant-promo-en-poster.jpg">\n'
                                                      '<video src="video/safari-assistant-desktop-en.mp4" poster="video/safari-assistant-desktop-en-poster.jpg">\n'})
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('promo: ffmpeg-like MP4s with (c)too tag (also 3 MiB, promo and desktop) and clean posters pass (--staged)',
                   rc == 0 and not findings(out), out)
        rc, out = self.gate(repo, '--paths', '.')
        self.check('promo: the same files pass with --paths', rc == 0 and not findings(out), out)
        self.commit(repo, 'promo video')
        rc, out = self.gate(repo, '--all')
        self.check('promo: the same files pass in the history (--all)', rc == 0 and not findings(out), out)
        for target in (vid, desk):
            for label, marker, data in (('(c)xyz tag, 3 MiB (read and inspected above the 2 MiB default)', '\xa9xyz',
                                         mp4(tags=[(b'\xa9xyz', ISO6709_VALUE)], size=3 * MIB)),
                                        (ISO6709_KEY + ' key', ISO6709_KEY,
                                         mp4(tags=[(struct.pack('>I', 1), ISO6709_VALUE)], udta=mp4_keys(ISO6709_KEY)))):
                self.write_file(os.path.join(repo, target), data)
                self.git(repo, 'add', '-A')
                rc, out = self.gate(repo, '--staged')
                self.check('promo: %s with %s -> A-F06, value not printed' % (target, label),
                           rc == 1 and has(out, 'A-F06', target) and marker in out and ISO6709_VALUE not in out, out)
            self.write_file(os.path.join(repo, target), mp4())
            self.git(repo, 'add', '-A')

        tree = os.path.join(self.tmp, 'promo-tree')
        files = {'docs/video/holiday.mp4': mp4(), 'docs/clip.mp4': mp4(), 'POIs/x.mp4': mp4(), 'docs/video/x.txt': 'Hallo\n',
                 'docs/video/safari-assistant-promo-eng.mp4': mp4(), 'docs/video/sub/safari-assistant-promo-en.mp4': mp4(),
                 'site/docs/video/safari-assistant-promo-en.mp4': mp4(), 'docs/video/safari-assistant-promo-en.mov': mp4(),
                 'docs/video/safari-assistant-promo-en-poster.jpeg': jpeg(),
                 # only the two kinds, exact prefix, lower case
                 'docs/video/safari-assistant-en.mp4': mp4(), 'docs/video/safari-assistant-trailer-en.mp4': mp4(),
                 'docs/video/Safari-Assistant-promo-en.mp4': mp4(), 'docs/video/safari-assistant-desktop-EN.mp4': mp4(),
                 # near misses: underscore, and the German spelling of the earlier name (2026-10-05: exempt is only "assistant")
                 'docs/video/safari_assistant-desktop-en.mp4': mp4(), 'docs/video/safari-assistent-desktop-en.mp4': mp4(),
                 'docs/video/safari-assistent-promo-en.mp4': mp4(),
                 'docs/video/safari-assistant-desktop-en-poster.gif': b'GIF89a',
                 'docs/video/sub/safari-assistant-desktop-en-poster.jpg': jpeg()}
        old = {'docs/video/dark-promo-en.mp4': mp4(), 'docs/video/dark-promo-en-poster.jpg': jpeg(),
               'docs/video/dark-promo-de-poster.png': png()}
        for rel, data in list(files.items()) + list(old.items()):
            self.write_file(os.path.join(tree, rel), data)
        content = [('safari-assistant-promo-pt.mp4', mp4(brand=b'qt  '), 'A-F06', 'QuickTime brand'),
                   ('safari-assistant-desktop-nl.mp4', mp4(trailer=b'GPS!'), 'A-F06', 'bytes after the last box (desktop)'),
                   ('safari-assistant-promo-sv.mp4', mp4(top=box(b'uuid', bytes.fromhex('be7acfcb97a942e89c71999491e3afac') + b'<x:xmpmeta/>')),
                    'A-F06', 'XMP in a uuid box'),
                   ('safari-assistant-desktop-da.mp4', mp4(tags=[(b'\xa9mak', 'Kamera')]), 'A-F06', '(c)mak camera make (desktop)'),
                   ('safari-assistant-promo-fi.mp4', b'kein Video\n', 'A-F06', 'not an MP4 at all'),
                   ('safari-assistant-promo-de-poster.png', b'kein Bild\n', 'A-F06', 'poster that is no image'),
                   ('safari-assistant-desktop-fr-poster.jpg', b'kein Bild\n', 'A-F06', 'desktop poster that is no image'),
                   ('safari-assistant-promo-en-poster.jpg', jpeg(exif_gps()), 'A-F04', 'poster with EXIF GPS'),
                   ('safari-assistant-desktop-en-poster.jpg', jpeg(exif_gps()), 'A-F04', 'desktop poster with EXIF GPS'),
                   ('safari-assistant-promo-no.mp4', mp4(tags=[(b'\xa9cmt', 'Kontakt ' + RELAY)]), 'A-P02', 'relay address in a tag (text rules)'),
                   ('safari-assistant-desktop-hu.mp4', mp4(tags=[(b'\xa9ART', 'Maxi Mustermann')]), 'B-02', 'private term in a tag (B rules, desktop)'),
                   ('safari-assistant-promo-es.mp4', mp4(size=15 * MIB + 1), 'A-F02', 'one byte over 15 MiB (promo)'),
                   ('safari-assistant-desktop-es.mp4', mp4(size=15 * MIB + 1), 'A-F02', 'one byte over 15 MiB (desktop)')]
        for name, data, _rid, _label in content:
            self.write_file(os.path.join(tree, 'docs', 'video', name), data)
        fit = ['safari-assistant-promo-it.mp4', 'safari-assistant-desktop-it.mp4']
        for name in fit:
            self.write_file(os.path.join(tree, 'docs', 'video', name), mp4(size=15 * MIB))
        env = self.env(self.mkhome('home-promo', TERM_LINES))
        rc, out = self.gate(tree, '--paths', '.', env=env)
        self.check('promo tree -> exit 1', rc == 1, out)
        for rel in sorted(files):
            self.check('promo: %s stays forbidden (A-F01)' % rel, has(out, 'A-F01', rel), out)
        for rel in sorted(old):
            self.check('promo: old name %s is no longer exempt (A-F01)' % rel, has(out, 'A-F01', rel), out)
        for name, _data, rid, label in content:
            rel = 'docs/video/' + name
            if rid in ('A-P02', 'B-02'):
                rel += ' (MP4-Metadaten / MP4 metadata)'
            self.check('promo: %s -> %s' % (label, rid), has(out, rid, rel), out)
        exact = [name for name, _d, _r, _l in content] + fit
        self.check('promo: the exact names are never A-F01, 15 MiB exactly passes (promo and desktop), B hit redacted',
                   not any(has(out, 'A-F01', 'docs/video/' + n) for n in exact)
                   and not any(n in out for n in fit) and 'Mustermann' not in out, out)
        self.write_file(os.path.join(tree, '.privacy-allowlist'), 'A-F06 docs/video/safari-assistant-promo-pt.mp4 x\n')
        rc, out = self.gate(tree, '--paths', '.', env=env)
        self.check('promo: A-F06 cannot be allowlisted (exit 2)', rc == 2 and 'A-F06' in out, out)

    def t_terms(self):
        home = self.mkhome('home-terms', TERM_LINES)
        env = self.env(home)
        near, far = NEAR, FAR
        repo = self.repo('terms', {
            'b1.txt': 'Kontakt: Maxi Mustermann\nMustermannstrasse 5\n',
            'b2.txt': 'Adresse: Beispielweg 12, 99999 Irgendwo\n',
            'b3.txt': 'Code MUSTERSTADT-123\n',
            'b4.txt': 'Treffpunkt %s %s\numgekehrt %s, %s\nweit weg %s %s\n' % (near[0], near[1], near[1], near[0], far[0], far[1]),
            'b5.json': '{"lat": %s, "lon": %s}\n' % near,
            'b6.json': '{"strasse": "Gr\\u00fcngasse 7"}\n',
            'b7.html': '<p>Gr&uuml;ngasse 7</p>\n',
            'data/orte.json': '{"orte": [["Beispielhausen", -20.1, 30.2], ["Beispielhausen Nord", -20.2, 30.3]]}\n',
            'Mustermann-plan.md': 'x\n'})
        self.git(repo, 'add', '-A', env=env)
        rc, out = self.gate(repo, '--staged', env=env)
        self.check('B terms (default list location) -> exit 1', rc == 1, out)
        self.check('B word: whole word hit', has(out, 'B-02', 'b1.txt:1'), out)
        self.check('B word: no hit inside a longer word', not has(out, 'B-02', 'b1.txt:2'), out)
        self.check('B text: substring hit', has(out, 'B-03', 'b2.txt:1'), out)
        self.check('B regex: hit on folded text', has(out, 'B-04', 'b3.txt:1'), out)
        self.check('B geo: pair inside the fence', has(out, 'B-05', 'b4.txt:1'), out)
        self.check('B geo: reversed axis order', has(out, 'B-05', 'b4.txt:2'), out)
        self.check('B geo: far point not reported', not has(out, 'B-05', 'b4.txt:3'), out)
        self.check('B geo: JSON lat/lon keys', has(out, 'B-05', 'b5.json (JSON)'), out)
        self.check('B text: JSON \\u escape decoded', has(out, 'B-08', 'b6.json:1'), out)
        self.check('B text: HTML entity decoded', has(out, 'B-08', 'b7.html:1'), out)
        self.check('B allow: 2 hits <= allowed count -> suppressed', not has(out, 'B-06'), out)
        self.check('B word in a file name', has(out, 'B-02', 'Mustermann-plan.md (Dateiname'), out)
        self.check('B hits are printed as [redacted]', '[redacted]' in out and 'Maxi Mustermann' not in out
                   and 'eispielweg' not in out.lower() and 'musterstadt' not in out.lower(), out)
        self.write_file(os.path.join(repo, 'data/orte.json'),
                        '{"orte": [["Beispielhausen", 1.1, 2.2], ["Beispielhausen Nord", 1.2, 2.3], ["Beispielhausen Süd", 1.3, 2.4]]}\n')
        self.git(repo, 'add', '-A', env=env)
        rc, out = self.gate(repo, '--staged', env=env)
        self.check('B allow: 3 hits > allowed 2 -> reported with allow hint',
                   has(out, 'B-06', 'data/orte.json:1') and 'allow: 6 data/orte.json 3' in out, out)
        rc, out = self.gate(repo, '--staged', env=self.env(home, GIT_AUTHOR_NAME='Maxi Mustermann'))
        self.check('B term in the author name -> blocked, redacted', rc == 1 and has(out, 'B-02', 'author (git var)')
                   and 'Maxi Mustermann' not in out, out)

    def t_term_lookup(self):
        lists = os.path.join(self.tmp, 'lists')
        self.write_file(os.path.join(lists, 'env-terms.txt'), 'word: Envtestwort\n')
        self.write_file(os.path.join(lists, 'git-terms.txt'), '\n\nword: Gitkonfigwort\n')
        for f in ('env-terms.txt', 'git-terms.txt'):
            os.chmod(os.path.join(lists, f), 0o600)
        home = self.mkhome('home-lookup', ['word: Mustermann'])
        repo = self.repo('lookup', {'x.txt': 'Envtestwort Gitkonfigwort Mustermann\n', 'sub/y.txt': 'y\n'})
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged', env=self.env(home, PRIVACY_DENYLIST=os.path.join(lists, 'env-terms.txt')))
        self.check('lookup: $PRIVACY_DENYLIST wins over the default file',
                   has(out, 'B-01', 'x.txt:1') and 'rules (' in out and rc == 1 and len(findings(out)) == 1, out)
        self.git(repo, 'config', 'privacy.denylist', '../lists/git-terms.txt')
        rc, out = self.gate(os.path.join(repo, 'sub'), '--staged', env=self.env(home))
        self.check('lookup: git config privacy.denylist (relative to repo top, run from a subdir)',
                   rc == 1 and has(out, 'B-03', 'x.txt:1') and len(findings(out)) == 1, out)
        self.git(repo, 'config', '--unset', 'privacy.denylist')
        rc, out = self.gate(repo, '--staged', env=self.env(home))
        self.check('lookup: ~/.config/privacy-gate/denylist.txt as default', rc == 1 and has(out, 'B-01', 'x.txt:1'), out)
        loose = self.mkhome('home-loose', ['word: Mustermann'], mode=0o644)
        rc, out = self.gate(repo, '--staged', env=self.env(loose))
        self.check('warning when the term list is readable by others', 'chmod 600' in out, out)
        bad = self.mkhome('home-bad', ['word: ok', 'Geheimwort ohne Art'])
        rc, out = self.gate(repo, '--staged', env=self.env(bad))
        self.check('malformed term list -> exit 2, line content not printed', rc == 2 and 'Geheimwort' not in out, out)

    def t_allowlist(self):
        repo = self.repo('allow', {'.privacy-allowlist': '# public only\nA-P12 index.html %s\n' % PHONE,
                                   'index.html': '<p>Botschaft %s</p>\n' % PHONE, 'other.html': '<p>%s</p>\n' % PHONE})
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('.privacy-allowlist suppresses the listed file only',
                   not has(out, 'A-P12', 'index.html') and has(out, 'A-P12', 'other.html:1'), out)
        self.write_file(os.path.join(repo, '.privacy-allowlist'), 'A-S03 x.txt %s\n' % ANTHROPIC_KEY)
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('secrets cannot be allowlisted (exit 2)', rc == 2 and 'A-S03' in out, out)

    def t_identity(self):
        cfg = {'privacy.allowedNames': 'DARK', 'privacy.allowedEmailRegex': r'(\d+\+)?DarkPirateGo@users\.noreply\.github\.com'}
        repo = self.repo('ident', {'README.md': 'x\n'}, cfg)
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged', env=self.env(GIT_AUTHOR_NAME='Maxi Mustermann', GIT_AUTHOR_EMAIL=EXAMPLE_MAIL))
        self.check('allowedNames/allowedEmailRegex block another identity',
                   rc == 1 and has(out, 'A-G01', 'author (git var)') and has(out, 'A-G02', 'author (git var)'), out)
        rc, out = self.gate(repo, '--staged')
        self.check('configured identity DARK/noreply passes', rc == 0 and not findings(out), out)
        rc, out = self.gate(repo, '--staged', env=self.env(GIT_AUTHOR_NAME='Maxi Mustermann', GIT_AUTHOR_EMAIL=EXAMPLE_MAIL,
                                                           PRIVACY_ALLOWED_NAMES='Maxi Mustermann, DARK',
                                                           PRIVACY_ALLOWED_EMAIL_REGEX=r'maxi@example\.com|.*noreply.*'))
        self.check('environment wins over git config (fork contributor)', rc == 0 and not has(out, 'A-G01') and not has(out, 'A-G02'), out)
        rc, out = self.gate(repo, '--staged', env=self.env(GIT_AUTHOR_EMAIL=RELAY, PRIVACY_ALLOWED_EMAIL_REGEX='.*'))
        self.check('relay e-mail blocked even when the e-mail regex allows it', rc == 1 and has(out, 'A-G05', 'author (git var)'), out)
        self.commit(repo, 'first')
        self.write_file(os.path.join(repo, 'deps.txt'), 'bump\n')
        self.commit(repo, 'Bump deps', env=self.env(GIT_AUTHOR_NAME='dependabot[bot]', GIT_AUTHOR_EMAIL=BOT_MAIL,
                                                    GIT_COMMITTER_NAME='GitHub', GIT_COMMITTER_EMAIL=WEB_MAIL))
        rc, out = self.gate(repo, '--all')
        self.check('bots / web merges accepted with an allowlist (--all)', rc == 0 and not findings(out), out)

        plain = self.repo('ident-plain', {'README.md': 'x\n'})
        self.git(plain, 'add', '-A')
        for label, mail in (('Apple relay', RELAY), ('.local host', LOCAL_MAIL), ('no-dot domain', NODOT_MAIL)):
            rc, out = self.gate(plain, '--staged', env=self.env(GIT_AUTHOR_EMAIL=mail))
            self.check('no config: %s e-mail blocked (A-G05)' % label, rc == 1 and has(out, 'A-G05', 'author (git var)'), out)
        rc, out = self.gate(plain, '--staged', env=self.env(GIT_AUTHOR_NAME='Maxi Mustermann', GIT_AUTHOR_EMAIL=EXAMPLE_MAIL))
        self.check('no config: any name allowed, non-noreply e-mail only warns (A-G06)',
                   rc == 0 and has(out, 'A-G06', 'author (git var)', block=False) and not has(out, 'A-G01'), out)

    def t_timezone(self):
        repo = self.repo('tz', {'README.md': 'x\n'})
        self.git(repo, 'add', '-A')
        cet = self.env(GIT_AUTHOR_DATE='2027-03-15T12:00:00+0200', GIT_COMMITTER_DATE='2027-03-15T12:00:00+0200')
        rc, out = self.gate(repo, '--staged', env=cet)
        self.check('A-G03 non-UTC timezone is a warning by default',
                   rc == 0 and has(out, 'A-G03', 'author (git var)', block=False) and 'TZ=UTC' in out, out)
        self.git(repo, 'config', 'privacy.requireUTC', 'true')
        rc, out = self.gate(repo, '--staged', env=cet)
        self.check('A-G03 blocks with git config privacy.requireUTC=true', rc == 1 and has(out, 'A-G03', block=True), out)
        self.git(repo, 'config', 'privacy.requireUTC', 'false')
        rc, out = self.gate(repo, '--staged', env=dict(cet, PRIVACY_REQUIRE_UTC='1'))
        self.check('A-G03 blocks with PRIVACY_REQUIRE_UTC=1', rc == 1 and has(out, 'A-G03', block=True), out)
        self.commit(repo, 'at +0200', env=cet)
        rc, out = self.gate(repo, '--all')
        self.check('A-G03 also checked on history (--all)', has(out, 'A-G03', block=False), out)

    def t_require_denylist(self):
        repo = self.repo('require', {'README.md': 'x\n'})
        self.git(repo, 'add', '-A')
        rc, out = self.gate(repo, '--staged')
        self.check('no list, not required -> notice only, exit 0', rc == 0 and 'B rules off' in out, out)
        rc, out = self.gate(repo, '--staged', '--require-denylist')
        self.check('--require-denylist without list -> exit 2 (fail closed)', rc == 2 and 'required' in out, out)
        rc, out = self.gate(repo, '--staged', env=self.env(PRIVACY_REQUIRE_DENYLIST='1'))
        self.check('PRIVACY_REQUIRE_DENYLIST=1 without list -> exit 2', rc == 2, out)
        self.git(repo, 'config', 'privacy.requireDenylist', 'true')
        rc, out = self.gate(repo, '--staged')
        self.check('git config privacy.requireDenylist=true without list -> exit 2', rc == 2 and 'privacy.requireDenylist' in out, out)
        home = self.mkhome('home-require', ['word: Mustermann'])
        rc, out = self.gate(repo, '--staged', env=self.env(home))
        self.check('required list present -> exit 0', rc == 0, out)

    def t_paths_plain(self):
        tree = os.path.join(self.tmp, 'tree')
        self.write_file(os.path.join(tree, 'a.txt'), 'Kontakt %s\n' % RELAY)
        self.write_file(os.path.join(tree, 'track.gpx'), '<gpx/>')
        self.write_file(os.path.join(tree, 'img', 'logo.jpg'), jpeg(seg(0xFE, b'Maxi war hier')))
        self.write_file(os.path.join(tree, 'big.bin'), b'\0' * (2 * 1024 * 1024 + 1))
        self.write_file(os.path.join(tree, '.git', 'config'), '[x]\n%s\n' % AWS_KEY)
        self.write_file(os.path.join(tree, 'sub', '.git', 'HEAD'), 'ref: refs/heads/main\n')
        self.write_file(os.path.join(tree, 'ok.txt'), 'Hallo\n')
        self.write_file(os.path.join(tree, '.privacy-allowlist'), 'A-P12 index.html %s\nA-P12 sub2/*.html %s\n' % (PHONE, PHONE))
        self.write_file(os.path.join(tree, 'sub2', 'x.html'), '<p>%s</p>\n' % PHONE)
        self.write_file(os.path.join(tree, 'sub2', 'r.txt'), '%s\n' % RELAY)
        self.write_file(os.path.join(tree, 'index.html'), '<p>%s</p>\n' % PHONE)
        os.symlink('/Users/' + 'maxm' + '/Documents', os.path.join(tree, 'link-home'))
        rc, out = self.gate(tree, '--paths', '.')
        self.check('--paths on a plain folder (no git) -> exit 1', rc == 1, out)
        self.check('--paths: content rule (A-P02)', has(out, 'A-P02', 'a.txt:1'), out)
        self.check('--paths: path rule (A-F01)', has(out, 'A-F01', 'track.gpx'), out)
        self.check('--paths: image metadata (A-F04)', has(out, 'A-F04', 'img/logo.jpg'), out)
        self.check('--paths: size rule (A-F02)', has(out, 'A-F02', 'big.bin'), out)
        self.check('--paths: top-level .git skipped', '.git/config' not in out and not has(out, 'A-S06'), out)
        self.check('--paths: nested .git flagged', has(out, 'A-F01', 'sub/.git/HEAD'), out)
        self.check('--paths: symlink target checked like git stores it', has(out, 'A-P03', 'link-home:1'), out)
        self.check('--paths: .privacy-allowlist of the tree applies', not has(out, 'A-P12'), out)
        self.check('--paths: clean file has no finding', 'ok.txt' not in out, out)
        rc2, out2 = self.gate(self.tmp, '--paths', tree)
        self.check('--paths with an absolute folder reports the same relative paths',
                   rc2 == 1 and sorted(findings(out2)) == sorted(findings(out)), out2)
        rc3, out3 = self.gate(tree, '--paths', 'sub2')
        self.check('--paths on a sub-folder reports root-relative paths and uses the root allowlist',
                   rc3 == 1 and has(out3, 'A-P02', 'sub2/r.txt:1') and not has(out3, 'A-P12'), out3)

    def t_commit_msg(self):
        home = self.mkhome('home-msg', TERM_LINES)
        repo = self.repo('msg')
        cases = [('message with a relay address', 'Fix\n\nKontakt %s\n' % RELAY, 1, 'A-P02'),
                 ('comment lines are ignored', 'Fix typo\n# %s\n' % RELAY, 0, None),
                 ('text below the scissors line is ignored', 'Fix\n%s\n%s\n' % (SCISSORS, AWS_KEY), 0, None),
                 ('B term in the message, redacted', 'Danke an Maxi Mustermann\n', 1, 'B-02')]
        for i, (label, text, want, rid) in enumerate(cases):
            f = os.path.join(self.tmp, 'msg%d.txt' % i)
            self.write_file(f, text)
            rc, out = self.gate(repo, '--commit-msg', f, env=self.env(home))
            ok = rc == want and (rid is None or has(out, rid, 'commit message')) and 'Mustermann' not in out
            self.check('--commit-msg: ' + label, ok, out)

    def t_all_refs_tags(self):
        home = self.mkhome('home-all', TERM_LINES)
        env = self.env(home)
        repo = self.repo('all', {'README.md': 'x\n'})
        self.commit(repo, 'init', env=env)
        self.git(repo, 'tag', '-a', 'v1', '-m', 'Release\n\nKontakt %s' % RELAY, env=env)
        self.git(repo, 'branch', 'feature/mustermann-fix', env=env)
        rc, out = self.gate(repo, '--all', env=env)
        self.check('--all: annotated tag message is scanned', rc == 1 and has(out, 'A-P02', 'tag v1 message'), out)
        self.check('--all: branch names are scanned (B term)', has(out, 'B-02', 'ref refs/heads/feature/mustermann-fix'), out)

    def t_push(self):
        remote = os.path.join(self.tmp, 'remote.git')
        os.makedirs(remote)
        self.git(remote, 'init', '-q', '--bare')
        repo = self.repo('push', {'README.md': 'x\n', 'keep/.gitkeep': ''}, hooks=True)
        self.git(repo, 'remote', 'add', 'origin', remote)
        self.commit(repo, 'A', verify=True)
        a = self.head(repo)
        rc, out = self.git(repo, 'push', '-q', 'origin', 'main', check=False)
        self.check('pre-push hook: clean push goes through', rc == 0 and self.remote_head(remote) == a, out)
        self.write_file(os.path.join(repo, 'leak.txt'), 'aws %s\n' % AWS_KEY)
        self.commit(repo, 'B (bypassing pre-commit)')
        b = self.head(repo)
        os.remove(os.path.join(repo, 'leak.txt'))
        self.commit(repo, 'C removes the file again')
        rc, out = self.git(repo, 'push', '-q', 'origin', 'main', check=False)
        self.check('pre-push hook blocks a file added and deleted inside the pushed range',
                   rc != 0 and has(out, 'A-S06', 'leak.txt:1') and b[:10] in out and self.remote_head(remote) == a, out)
        stdin = ('refs/heads/main %s refs/heads/main %s\n' % (self.head(repo), a)).encode()
        rc, out = self.gate(repo, '--push', 'origin', input=stdin)
        self.check('--push reads git\'s stdin directly', rc == 1 and has(out, 'A-S06', 'leak.txt:1'), out)
        self.git(repo, 'reset', '-q', '--hard', a)
        self.write_file(os.path.join(repo, '.env'), '')
        self.commit(repo, 'D adds an empty .env')
        rc, out = self.git(repo, 'push', '-q', 'origin', 'main', check=False)
        self.check('pre-push: forbidden path even if its (empty) content is already public',
                   rc != 0 and has(out, 'A-F01', '.env'), out)
        self.git(repo, 'reset', '-q', '--hard', a)
        self.write_file(os.path.join(repo, 'docs', 'NOTES-public.md'), 'Hallo\n')
        self.commit(repo, 'E', verify=True)
        rc, out = self.git(repo, 'push', '-q', 'origin', 'main', check=False)
        self.check('pre-push: next clean push goes through', rc == 0 and self.remote_head(remote) == self.head(repo), out)

    def remote_head(self, remote):
        rc, out = self.git(remote, 'rev-parse', '-q', '--verify', 'refs/heads/main', check=False)
        return out.strip() if rc == 0 else None

    def t_hooks(self):
        ok = True
        detail = ''
        for h in HOOK_NAMES:
            p = os.path.join(HOOKS, h)
            if not os.path.isfile(p):
                ok, detail = False, detail + 'missing %s\n' % h
                continue
            with open(p, 'rb') as fh:
                first = fh.readline()
            if first.strip() != b'#!/bin/sh' or not os.stat(p).st_mode & stat.S_IXUSR:
                ok, detail = False, detail + '%s: shebang/executable bit\n' % h
            r = subprocess.run(['sh', '-n', p], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                ok, detail = False, detail + '%s: %s\n' % (h, r.stdout.decode('utf-8', 'replace'))
        self.check('hooks exist, are executable POSIX sh and parse', ok, detail)
        repo = self.repo('hooks', {'README.md': 'x\n'}, hooks=True)
        env = self.env(PATH=os.path.join(self.tmp, 'no-such-dir'))
        allfail = True
        for h in HOOK_NAMES:
            r = subprocess.run(['/bin/sh', os.path.join(repo, '.githooks', h), 'x'], cwd=repo, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, input=b'')
            allfail = allfail and r.returncode == 1 and b'python3' in r.stdout
        self.check('hooks fail closed when python3 is missing', allfail)
        before = self.git(repo, 'rev-parse', '-q', '--verify', 'HEAD', check=False)[0]
        rc, out = self.commit(repo, 'x', env=self.env(GIT_AUTHOR_EMAIL=RELAY), verify=True, check=False)
        self.check('pre-commit hook blocks a relay identity (no commit created)',
                   rc != 0 and has(out, 'A-G05') and self.git(repo, 'rev-parse', '-q', '--verify', 'HEAD', check=False)[0] == before, out)
        rc, out = self.commit(repo, 'Kontakt %s' % RELAY, verify=True, check=False)
        self.check('commit-msg hook blocks a relay address in the message', rc != 0 and has(out, 'A-P02', 'commit message'), out)
        self.git(repo, 'config', 'privacy.requireDenylist', 'true')
        rc, out = self.commit(repo, 'ok', verify=True, check=False)
        self.check('pre-commit hook fails closed when the required term list is missing', rc != 0 and 'required' in out, out)

    def t_self_scan(self):
        targets = [p for p in (GATE, os.path.abspath(__file__), os.path.join(HERE, 'private-terms.example.txt'),
                               os.path.join(HERE, 'validate_osm_exports.py'), os.path.join(ROOT, 'docs', 'PRIVACY-GATE.md'),
                               os.path.join(ROOT, '.privacy-allowlist'), HOOKS) if os.path.exists(p)]
        # run outside any repository: the maintainer's own clone config (e.g. privacy.requireDenylist) must not matter
        rc, out = self.gate(self.tmp, '--paths', *targets)
        self.check('the gate, this test and the docs pass the gate themselves', rc == 0 and not findings(out), out)

    def run(self):
        cases = [self.t_cli, self.t_paths_forbidden, self.t_secrets_personal, self.t_clean_controls, self.t_images,
                 self.t_promo_video, self.t_terms, self.t_term_lookup, self.t_allowlist, self.t_identity, self.t_timezone, self.t_require_denylist,
                 self.t_paths_plain, self.t_commit_msg, self.t_all_refs_tags, self.t_push, self.t_hooks, self.t_self_scan]
        try:
            for case in cases:
                try:
                    case()
                except Exception as e:           # a crash in a case is a failure, not an abort
                    self.check('%s ohne Absturz / without crash' % case.__name__, False, '%s: %s' % (type(e).__name__, e))
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)
        if self.failed:
            print('FEHLER / FAILED: %d von / of %d Fällen / cases' % (self.failed, self.n))
            return 1
        print('OK %d/%d' % (self.n, self.n))
        return 0


if __name__ == '__main__':
    if not os.path.isfile(GATE):
        print('FEHLER / FAILED: %s fehlt / missing' % GATE)
        sys.exit(1)
    sys.exit(Suite().run())
