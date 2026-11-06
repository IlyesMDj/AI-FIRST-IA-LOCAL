"""PDF / TXT / MD / image → ExtractResult. Seul module qui importe pymupdf.

Tout se passe en mémoire : aucun fichier temporaire, le texte brut n'est jamais écrit.
"""
from __future__ import annotations

from pathlib import PurePath

import pymupdf

from .config import MAX_UPLOAD_BYTES
from .types import ExtractResult

MIN_USEFUL_CHARS_PER_PAGE = 30
VISION_MAX_PAGES = 3
VISION_DPI = 150
VISION_MAX_SIDE = 2000          # px : borne la taille des images envoyées au modèle de vision

TEXT_EXT = {".txt", ".md"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
ACCEPTED = "PDF, TXT, MD, PNG, JPG"

try:  # pas de messages MuPDF sur stderr (ils pourraient citer le contenu du fichier)
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
except Exception:  # pragma: no cover
    pass


def _unsupported(reason: str) -> ExtractResult:
    return ExtractResult(status="unsupported", reason=reason)


def _useful(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def _png_from_pixmap(pix: "pymupdf.Pixmap") -> bytes:
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    if pix.n - pix.alpha > 3:                       # CMYK → RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    while max(pix.width, pix.height) > VISION_MAX_SIDE:
        pix.shrink(1)                               # divise par 2
    return pix.tobytes("png")


def _render_page(page: "pymupdf.Page") -> bytes:
    """Rendu borné : dpi = min(150, 2000*72/max(w,h)) → jamais de pixmap géant."""
    side = max(page.rect.width, page.rect.height) or 1.0
    dpi = max(1, min(VISION_DPI, int(VISION_MAX_SIDE * 72 / side)))
    return _png_from_pixmap(page.get_pixmap(dpi=dpi))


def _extract_text_file(data: bytes) -> ExtractResult:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):          # UTF-16 avec BOM
        try:
            text = data.decode("utf-16")
        except UnicodeDecodeError:
            return _unsupported("Fichier texte UTF-16 corrompu.")
        if _useful(text) == 0:
            return _unsupported("Le fichier texte est vide.")
        return ExtractResult(status="ok", text=text)
    if b"\x00" in data[:4096]:
        return _unsupported("Le fichier texte semble binaire ou corrompu.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    if _useful(text) == 0:
        return _unsupported("Le fichier texte est vide.")
    return ExtractResult(status="ok", text=text)


def _extract_pdf(data: bytes) -> ExtractResult:
    if not data.lstrip()[:5].startswith(b"%PDF"):
        return _unsupported("Le fichier n'est pas un PDF valide (corrompu ou mal nommé).")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return _unsupported("PDF illisible ou corrompu.")
    try:
        if doc.needs_pass:
            return _unsupported("PDF protégé par mot de passe : impossible de le lire.")
        if doc.page_count == 0:
            return _unsupported("PDF sans aucune page.")
        try:
            pages = [page.get_text("text") for page in doc]
        except Exception:
            return _unsupported("PDF illisible ou corrompu.")
        # Seuil PAR PAGE : une page sous le seuil est considérée comme scannée.
        scan_idx = [i for i, p in enumerate(pages) if _useful(p) < MIN_USEFUL_CHARS_PER_PAGE]
        scan_set = set(scan_idx)
        text_pages = [p.strip() for i, p in enumerate(pages) if i not in scan_set]
        if not scan_idx:
            return ExtractResult(status="ok", text="\n\n".join(text_pages))
        try:
            images = [_render_page(doc[i]) for i in scan_idx[:VISION_MAX_PAGES]]
        except Exception:
            return _unsupported("PDF sans texte et impossible à convertir en image.")
        skipped = len(scan_idx) - len(images)
        if not text_pages:
            reason = "PDF sans couche texte (scan) : lecture par le modèle de vision nécessaire."
            if skipped:
                reason += f" Seules les {VISION_MAX_PAGES} premières pages sur {doc.page_count} seront lues."
            return ExtractResult(status="needs_vision", reason=reason, page_images=images)
        # PDF mixte : texte des pages texte + images des pages scannées (à transcrire et AJOUTER).
        nums = ",".join(str(i + 1) for i in scan_idx)
        reason = (f"page {nums} scannée" if len(scan_idx) == 1 else f"pages {nums} scannées")
        reason += " : texte à compléter par le modèle de vision."
        if skipped:
            reason += f" Seules les {VISION_MAX_PAGES} premières pages scannées seront lues."
        return ExtractResult(status="ok", text="\n\n".join(text_pages), reason=reason, page_images=images)
    finally:
        doc.close()


_MAGIC = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",)}


def _extract_image(ext: str, data: bytes) -> ExtractResult:
    if not data.startswith(_MAGIC[ext]):
        return _unsupported("Image illisible ou corrompue (contenu ne correspondant pas à l'extension).")
    try:
        png = _png_from_pixmap(pymupdf.Pixmap(data))
    except Exception:
        return _unsupported("Image illisible ou corrompue.")
    return ExtractResult(
        status="needs_vision",
        reason="Image : lecture par le modèle de vision nécessaire.",
        page_images=[png],
    )


def extract(filename: str, data: bytes) -> ExtractResult:
    ext = PurePath(filename or "").suffix.lower()
    if len(data) > MAX_UPLOAD_BYTES:
        return _unsupported(f"Fichier trop volumineux (maximum {MAX_UPLOAD_BYTES // (1024 * 1024)} Mo).")
    if not data:
        return _unsupported("Fichier vide.")
    if ext in TEXT_EXT:
        return _extract_text_file(data)
    if ext == ".pdf":
        return _extract_pdf(data)
    if ext in IMAGE_EXT:
        return _extract_image(ext, data)
    shown = ext or "sans extension"
    return _unsupported(f"Format non pris en charge ({shown}). Formats acceptés : {ACCEPTED}.")
