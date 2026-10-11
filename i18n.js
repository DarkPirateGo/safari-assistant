/* Safari Assistant — interface language (Deutsch · English · Français · Español)
 * Safari Assistant i18n.js v2026-10-05-1
 *
 * Die Seiten sind auf Deutsch geschrieben. Diese Datei übersetzt die Oberfläche zur Laufzeit,
 * ohne den Quelltext der Seiten anzufassen: Textknoten und die Attribute title, placeholder,
 * aria-label und alt werden beim Laden und bei jeder Änderung (MutationObserver) im Wörterbuch
 * der gewählten Sprache nachgeschlagen (i18n/en.js, i18n/fr.js, i18n/es.js — nur das eine wird
 * geladen). Deutsch bleibt die Grundlage — fehlt ein Eintrag, bleibt der deutsche Text stehen.
 *
 * Nie übersetzt: Chat-Blasen (.msg-bubble), Eingabefelder, alles unter [data-i18n-skip].
 * Systemprompts gehen nie durch diese Datei — die Antwortsprache regelt die 🌐-Leiste.
 *
 * The pages are written in German. This file translates the interface at runtime, without
 * touching the pages' source: text nodes and the attributes title, placeholder, aria-label and
 * alt are looked up in the dictionary of the chosen language (i18n/en.js, fr.js, es.js — only
 * that one is loaded) when the page loads and whenever the page changes. A missing entry leaves
 * the German text in place.
 *
 * Dictionary keys: one line, whitespace collapsed. {0}, {1} … stand for values (numbers, names)
 * and may be reordered in the English text. Contributions welcome — see CONTRIBUTING.md.
 */
(function () {
  'use strict';
  var SPEICHER = 'safari-ui-sprache';
  var SPRACHEN = ['de', 'en', 'fr', 'es'];
  // Antwortsprache der KI (Wert der 🌐-Leiste), die zur Oberfläche gehört
  var ANTWORT = { de: 'Deutsch', en: 'English', fr: 'Französisch', es: 'Spanisch' };
  var DATUM = { en: 'en-GB', fr: 'fr-FR', es: 'es-ES' };

  function gespeicherteSprache() {
    try {
      var v = JSON.parse(localStorage.getItem(SPEICHER) || 'null');
      if (SPRACHEN.indexOf(v) >= 0) return v;
    } catch (e) {}
    var nav = String((navigator.languages && navigator.languages[0]) || navigator.language || 'de').toLowerCase().slice(0, 2);
    return SPRACHEN.indexOf(nav) >= 0 ? nav : 'en';
  }

  var lang = gespeicherteSprache();
  var WB = {};            // Wörterbuch der gewählten Sprache (i18n/<sprache>.js)
  var api = {
    lang: lang,
    t: function (s) { return s; },
    tMulti: function (s) { return s; },
    set: setzeSprache,
    markiere: markiereKnoepfe
  };
  window.DARK_I18N = api;           // Name aus der kurzen Zeit, als die App „DARK“ hieß — bleibt (Wörterbücher und Seiten rufen ihn)

  function setzeSprache(neu) {
    if (SPRACHEN.indexOf(neu) < 0 || neu === lang) { markiereKnoepfe(); return; }
    try {
      localStorage.setItem(SPEICHER, JSON.stringify(neu));
      // Die Antwortsprache folgt der Oberfläche — es sei denn, sie war bewusst anders gewählt
      // (z. B. Swahili-Antworten bei englischer Oberfläche): dann bleibt sie.
      var a = JSON.parse(localStorage.getItem('safari-antwortsprache') || 'null');
      if (a === null || a === ANTWORT[lang]) localStorage.setItem('safari-antwortsprache', JSON.stringify(ANTWORT[neu]));
    } catch (e) {}
    location.reload();
  }

  function markiereKnoepfe() {
    var knoepfe = document.querySelectorAll('[data-ui-lang]');
    for (var i = 0; i < knoepfe.length; i++) {
      var an = knoepfe[i].getAttribute('data-ui-lang') === lang;
      knoepfe[i].classList.toggle('active', an);
      knoepfe[i].setAttribute('aria-pressed', an ? 'true' : 'false');
    }
  }

  document.documentElement.setAttribute('lang', lang);
  if (lang === 'de') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', markiereKnoepfe);
    else markiereKnoepfe();
    return;
  }

  // ── Fremdsprache: Wörterbuch, Muster, Übersetzer ─────────────────────────────────────────
  var WS = /\s+/g;
  var muster = { erste: {}, rest: [] };   // Schlüssel mit Platzhaltern, nach den ersten zwei Zeichen sortiert
  var cache = new Map();

  function esc(s) { return s.replace(/[.*+?^$()|[\]\\]/g, '\\$&'); }

  function baueMuster() {
    for (var k in WB) {
      if (!Object.prototype.hasOwnProperty.call(WB, k) || k.indexOf('{') < 0 || !/\{\d+\}/.test(k)) continue;
      var teile = k.split(/(\{\d+\})/);
      var reihenfolge = [];
      var re = '^';
      for (var i = 0; i < teile.length; i++) {
        var m = /^\{(\d+)\}$/.exec(teile[i]);
        if (m) { reihenfolge.push(Number(m[1])); re += '(.*?)'; }
        else re += esc(teile[i]).replace(/\\\{/g, '\\{');
      }
      var eintrag = { re: new RegExp(re + '$'), ord: reihenfolge, wert: WB[k], fest: k.replace(/\{\d+\}/g, '').length };
      var kopf = teile[0];
      if (kopf.length >= 2) (muster.erste[kopf.slice(0, 2)] = muster.erste[kopf.slice(0, 2)] || []).push(eintrag);
      else muster.rest.push(eintrag);
    }
    // Spezifischere Muster (mehr fester Text) zuerst: „Bezug: Kartenmitte (kein GPS) {0}" vor „Bezug: {0} {1}"
    var nachLaenge = function (a, b) { return b.fest - a.fest; };
    for (var z in muster.erste) muster.erste[z].sort(nachLaenge);
    muster.rest.sort(nachLaenge);
  }

  function ausMuster(s, tiefe) {
    var liste = (muster.erste[s.slice(0, 2)] || []).concat(muster.rest);
    for (var i = 0; i < liste.length; i++) {
      var m = liste[i].re.exec(s);
      if (!m) continue;
      var werte = {};
      for (var j = 0; j < liste[i].ord.length; j++) {
        var v = m[j + 1];
        werte[liste[i].ord[j]] = (tiefe < 3 && /[A-Za-zÄÖÜäöüß]{2}/.test(v)) ? uebersetze(v, tiefe + 1) : v;
      }
      return liste[i].wert.replace(/\{(\d+)\}/g, function (_, n) { return werte[n] != null ? werte[n] : ''; });
    }
    return null;
  }

  // Ganzer Text → Wörterbuch → Muster → ohne Schmuck am Rand → in Abschnitten
  var KOPF = /^[\s -⯿\uD800-\uDFFF️‍•·–—\-*#>()[\]]+|^\d{1,2}[.)]\s+/;
  var FUSS = /[\s:…→↗›»!?.,;]+$/;
  // Abschnitte, gröbste Trenner zuerst: erst ganze Abschnitte nachschlagen, nur was fehlt, feiner teilen
  var SATZ;
  try { SATZ = new RegExp('((?<=[.!?])\\s+(?=[„"(A-ZÄÖÜ0-9]))'); }   // Satzzeichen bleibt am Satz
  catch (e) { SATZ = /((?:[.!?])\s+(?=[„"(A-ZÄÖÜ0-9]))/; }            // ältere Browser ohne Lookbehind
  var TRENNER = [/(\s+·\s+|\s+\|\s+)/, /(\s+—\s+|\s+–\s+)/, /(:\s+|;\s+)/, SATZ];

  var gross = null;                   // GROSSSCHRIFT → Schlüssel (für per toUpperCase() erzeugte Abzeichen)
  function direkt(s, tiefe) {
    if (Object.prototype.hasOwnProperty.call(WB, s)) return WB[s];
    var r = ausMuster(s, tiefe);
    if (r != null) return r;
    if (/[A-ZÄÖÜ]{3}/.test(s) && s === s.toUpperCase()) {
      if (!gross) { gross = {}; for (var k in WB) if (k.length < 60 && !gross[k.toUpperCase()]) gross[k.toUpperCase()] = WB[k]; }
      if (Object.prototype.hasOwnProperty.call(gross, s)) return gross[s].toUpperCase();
    }
    return null;
  }

  function ohneRand(s, tiefe) {
    var r = direkt(s, tiefe);
    if (r != null) return r;
    var k = /^\((.+)\)$/.exec(s);                     // „(alle 10 Tage)"
    if (k && k[1].indexOf(')') < 0) { r = ohneRand(k[1], tiefe); if (r != null) return '(' + r + ')'; }
    var kopf = '', fuss = '', kern = s, m;
    if ((m = KOPF.exec(kern)) && m[0].length < kern.length) { kopf = m[0]; kern = kern.slice(m[0].length); r = direkt(kern, tiefe); if (r != null) return kopf + r; }
    if ((m = FUSS.exec(kern)) && m[0].length < kern.length) { fuss = m[0]; kern = kern.slice(0, kern.length - m[0].length); r = direkt(kern, tiefe); if (r != null) return kopf + r + fuss; }
    return null;
  }

  function inAbschnitten(s, stufe, tiefe) {
    for (var st = stufe; st < TRENNER.length; st++) {
      var teile = s.split(TRENNER[st]);
      if (teile.length < 2) continue;
      var geaendert = false;
      for (var i = 0; i < teile.length; i += 2) {
        if (!teile[i] || !/[A-Za-zÄÖÜäöüß]{2}/.test(teile[i])) continue;
        var t = ohneRand(teile[i], tiefe + 1);
        if (t == null) t = inAbschnitten(teile[i], st + 1, tiefe);
        if (t != null) { teile[i] = t; geaendert = true; }
      }
      return geaendert ? teile.join('') : null;
    }
    return null;
  }

  function uebersetze(roh, tiefe) {
    tiefe = tiefe || 0;
    var s = roh.replace(WS, ' ').trim();
    if (s.length < 2 || !/[A-Za-zÄÖÜäöüß]/.test(s)) return roh;
    if (cache.has(s)) { var c = cache.get(s); return c === null ? roh : rand(roh, c); }
    var r = ohneRand(s, tiefe);
    if (r === undefined) r = null;
    if (r == null && tiefe < 2) r = inAbschnitten(s, 0, tiefe);
    if (cache.size > 20000) cache.clear();
    cache.set(s, r);                 // null = kein Eintrag → Original bleibt unverändert
    return r === null ? roh : rand(roh, r);
  }
  // führenden/folgenden Leerraum des Originals erhalten (Textknoten zwischen Elementen)
  function rand(roh, r) {
    var vorn = /^\s*/.exec(roh)[0], hinten = /\s*$/.exec(roh)[0];
    return (vorn ? ' ' : '') + r + (hinten && roh.trim() ? ' ' : '');
  }

  function uebersetzeMehrzeilig(s) {
    if (typeof s !== 'string') return s;
    return s.split('\n').map(function (z) { return z.trim() ? uebersetze(z) : z; }).join('\n');
  }

  api.t = function (s) { return typeof s === 'string' ? uebersetze(s).trim() : s; };
  api.tMulti = uebersetzeMehrzeilig;

  // ── DOM ───────────────────────────────────────────────────────────────────────────────────
  var ATTRIBUTE = ['title', 'placeholder', 'aria-label', 'alt'];
  var AUSLASSEN = '[data-i18n-skip], .msg-bubble, textarea, script, style, [contenteditable]';
  // Eingabefelder: Inhalt nie anfassen, Platzhalter und Titel schon
  var NUR_ATTRIBUTE = '[data-i18n-skip], .msg-bubble, [contenteditable]';

  function auslassen(el) {
    return !el || (el.closest && el.closest(AUSLASSEN) !== null);
  }

  function textKnoten(n) {
    if (!n.data || !/[A-Za-zÄÖÜäöüß]/.test(n.data)) return;
    if (auslassen(n.parentElement)) return;
    var neu = uebersetze(n.data);
    if (neu !== n.data) n.data = neu;
  }

  function attributeVon(el) {
    if (el.closest(NUR_ATTRIBUTE)) return;
    for (var i = 0; i < ATTRIBUTE.length; i++) {
      var a = ATTRIBUTE[i];
      if (!el.hasAttribute(a)) continue;
      var v = el.getAttribute(a);
      var neu = uebersetze(v);
      if (neu !== v) el.setAttribute(a, neu.trim());
    }
    if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit') && el.value) {
      var w = uebersetze(el.value);
      if (w !== el.value) el.value = w.trim();
    }
  }

  function baum(wurzel) {
    if (wurzel.nodeType === 3) { textKnoten(wurzel); return; }
    if (wurzel.nodeType !== 1) return;
    attributeVon(wurzel);
    if (auslassen(wurzel)) return;
    var w = document.createTreeWalker(wurzel, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (n.nodeType === 1 && n.matches(AUSLASSEN)) { attributeVon(n); return NodeFilter.FILTER_REJECT; }
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) textKnoten(n); else attributeVon(n);
    }
  }

  function beobachte() {
    var obs = new MutationObserver(function (eintraege) {
      for (var i = 0; i < eintraege.length; i++) {
        var e = eintraege[i];
        if (e.type === 'childList') {
          for (var j = 0; j < e.addedNodes.length; j++) baum(e.addedNodes[j]);
        } else if (e.type === 'characterData') {
          textKnoten(e.target);
        } else if (e.type === 'attributes' && e.target.nodeType === 1) {
          attributeVon(e.target);
        }
      }
    });
    obs.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRIBUTE });
  }

  // Meldungsfenster des Browsers
  ['alert', 'confirm', 'prompt'].forEach(function (f) {
    var orig = window[f];
    if (typeof orig !== 'function') return;
    window[f] = function (msg) {
      var args = Array.prototype.slice.call(arguments);
      args[0] = uebersetzeMehrzeilig(msg);
      return orig.apply(window, args);
    };
  });

  // Datums- und Zahlformate: die Seiten fragen ausdrücklich nach 'de-DE'
  function ort(loc) { return (loc === 'de-DE' || loc === 'de' || (Array.isArray(loc) && loc[0] === 'de-DE')) ? DATUM[lang] : loc; }
  ['toLocaleDateString', 'toLocaleTimeString', 'toLocaleString'].forEach(function (f) {
    var orig = Date.prototype[f];
    Date.prototype[f] = function (loc, opt) { return orig.call(this, ort(loc), opt); };
  });
  var zahl = Number.prototype.toLocaleString;
  Number.prototype.toLocaleString = function (loc, opt) { return zahl.call(this, ort(loc), opt); };

  function start() {
    baum(document.documentElement);
    if (document.title) document.title = uebersetze(document.title).trim();
    markiereKnoepfe();
  }

  // Das Wörterbuch kommt aus i18n/<sprache>.js (synchron im <head> nachgeladen, damit der
  // Beobachter läuft, bevor der Seiteninhalt eingelesen wird). Fehlt die Datei, bleibt alles deutsch.
  window.__DARK_I18N_DATEN = function (sprache, woerter) {
    if (sprache !== lang || !woerter || typeof woerter !== 'object') return;
    WB = woerter;
    cache.clear();                   // Fehlschläge von vor dem Laden nicht weiterverwenden
    gross = null;
    baueMuster();
    beobachte();
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
  };
  if (document.readyState === 'loading') document.write('<script src="i18n/' + lang + '.js"><\/script>');
  else { var sk = document.createElement('script'); sk.src = 'i18n/' + lang + '.js'; document.head.appendChild(sk); }
})();
