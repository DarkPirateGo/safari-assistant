"""
RAG-Modul für Safari Assistant (zwischenzeitlich „DARK", davor „Safari Assistent")
==================================================================================
Eigenständiges Modul für PDF-Textextraktion und Chunking.
Wird von server.py eingebunden. Speicherung der Chunks erfolgt
im Browser (IndexedDB) — dieses Modul liefert nur verarbeitete Chunks zurück.

Einbindung in server.py (im do_POST des Handlers, ganz oben):

    from rag import handle_extract_pdf
    # ...
    def do_POST(self):
        if self.path == '/api/extract-pdf':
            return handle_extract_pdf(self)
        # ... deine anderen Endpunkte ...

Und im do_OPTIONS (für CORS-Preflight), falls noch nicht vorhanden:
    if self.path == '/api/extract-pdf':
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Doc-Name')
        self.end_headers()
        return

Benötigt: pip install pymupdf --break-system-packages
"""

import json
import re
from urllib.parse import unquote

# PyMuPDF hat zwei Importnamen: „pymupdf" (heute) und „fitz" (historisch). Je nach Fassung ist
# nur einer vorhanden — beide versuchen, sonst gilt eine installierte Bibliothek als fehlend.
try:
    import pymupdf as fitz
    HAVE_PYMUPDF = True
except ImportError:
    try:
        import fitz  # ältere PyMuPDF-Fassungen
        HAVE_PYMUPDF = True
    except ImportError:
        HAVE_PYMUPDF = False


# ---- Chunking-Parameter ----
CHUNK_WORDS = 450          # Ziel-Wortzahl pro Chunk
CHUNK_OVERLAP_WORDS = 60   # Überlappung zwischen Chunks (Kontext-Erhalt)
MIN_CHUNK_WORDS = 30       # Chunks kürzer als das werden verworfen


def extract_chunks_from_pdf(pdf_bytes):
    """
    Extrahiert Text aus PDF, erkennt Kapitelüberschriften und erzeugt
    überlappende Chunks mit Kapitel- und Seiten-Metadaten.
    Rückgabe: (chunks, total_pages)
    """
    if not HAVE_PYMUPDF:
        raise RuntimeError("PyMuPDF (fitz) nicht installiert. pip install pymupdf --break-system-packages")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    chunks = []
    current_chapter = "Einleitung"
    word_buffer = []

    def flush_buffer(chapter):
        nonlocal word_buffer
        if len(word_buffer) == 0:
            return
        i = 0
        while i < len(word_buffer):
            window = word_buffer[i:i + CHUNK_WORDS]
            if len(window) < MIN_CHUNK_WORDS and chunks:
                break
            text = " ".join(w for w, _ in window).strip()
            start_page = window[0][1] if window else 1
            if text:
                chunks.append({"text": text, "chapter": chapter, "page": start_page})
            i += max(1, CHUNK_WORDS - CHUNK_OVERLAP_WORDS)
        word_buffer = []

    for page_num in range(total_pages):
        page = doc[page_num]
        page_label = page_num + 1
        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                line_text = "".join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue

                max_size = max((s.get("size", 0) for s in spans), default=0)
                is_bold = any("bold" in s.get("font", "").lower() for s in spans)
                looks_like_heading = (
                    len(line_text) < 80
                    and (max_size >= 13 or is_bold)
                    and len(line_text.split()) <= 10
                    and not line_text.endswith(('.', ',', ';', ':'))
                    and (max_size >= 13 or re.match(r'^\s*(\d+[\.\)]|[A-ZÄÖÜ][A-ZÄÖÜ\s]{3,})', line_text))
                )

                if looks_like_heading and len(line_text) > 3:
                    flush_buffer(current_chapter)
                    current_chapter = line_text[:80]
                else:
                    for word in line_text.split():
                        word_buffer.append((word, page_label))
                    if len(word_buffer) >= CHUNK_WORDS * 2:
                        flush_buffer(current_chapter)

    flush_buffer(current_chapter)
    doc.close()
    return chunks, total_pages


def handle_extract_pdf(handler):
    """
    HTTP-Handler für POST /api/extract-pdf.
    Input:  raw PDF-Bytes im Body, Header 'X-Doc-Name' (URL-encoded Dateiname)
    Output: { doc, total_pages, total_chunks, chunks: [{text, chapter, page}] }
    """
    try:
        content_length = int(handler.headers.get('Content-Length', 0))
        if content_length <= 0:
            _send_json(handler, 400, {"error": "Leerer Request-Body"})
            return

        pdf_bytes = handler.rfile.read(content_length)
        doc_name = handler.headers.get('X-Doc-Name', 'dokument.pdf')
        try:
            doc_name = unquote(doc_name)
        except Exception:
            pass

        chunks, total_pages = extract_chunks_from_pdf(pdf_bytes)

        _send_json(handler, 200, {
            "doc": doc_name,
            "total_pages": total_pages,
            "total_chunks": len(chunks),
            "chunks": chunks
        })
    except Exception as e:
        _send_json(handler, 500, {"error": str(e)})


def _send_json(handler, status, obj):
    payload = json.dumps(obj).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Content-Length', str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'rb') as f:
            chunks, pages = extract_chunks_from_pdf(f.read())
        print(f"{pages} Seiten -> {len(chunks)} Chunks")
        for c in chunks[:3]:
            print(f"\n--- Kapitel: {c['chapter']} (Seite {c['page']}) ---")
            print(c['text'][:200])
    else:
        print(f"PyMuPDF verfuegbar: {HAVE_PYMUPDF}")
        print("Usage: python3 rag.py <pdf-datei>")
