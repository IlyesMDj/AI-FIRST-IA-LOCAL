"""Document validation and text extraction (PDF / DOCX / TXT, OCR fallback).

All documents are treated as untrusted input:
- type is detected from content (magic bytes), never from the extension alone;
- size, page count and DOCX decompressed size are bounded (zip-bomb guard);
- parsing errors are converted into user-friendly ``DocumentError``s.
"""
from __future__ import annotations

import io
import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".jpg", ".jpeg", ".png"}
MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard for scanned images
MAX_DOCX_UNCOMPRESSED = 60 * 1024 * 1024
MAX_DOCX_ENTRIES = 2000
SCANNED_CHARS_PER_PAGE = 60


class DocumentError(Exception):
    def __init__(self, user_message: str, code: str = "document_error"):
        super().__init__(user_message)
        self.user_message = user_message
        self.code = code


@dataclass
class ExtractedDocument:
    text: str
    method: str  # pdf_text | ocr | docx | txt
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- filenames
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9 ._()\-]+")


def sanitize_filename(name: str) -> str:
    """Keep only the final path component and safe characters (path traversal guard)."""
    base = PurePath(name.replace("\\", "/")).name
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = _SAFE_NAME_RE.sub("_", base).strip(" .")
    return (base or "document")[:150]


# ------------------------------------------------------------------ detection
def detect_type(filename: str, content: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError(
            f"Unsupported file type '{ext or 'none'}'. Accepted formats: PDF, DOCX, TXT, JPG, PNG.", "unsupported_type"
        )
    if not content:
        raise DocumentError("The file is empty.", "empty_file")
    if ext == ".pdf":
        if not content.lstrip()[:5].startswith(b"%PDF-"):
            raise DocumentError("The file has a .pdf extension but is not a valid PDF.", "type_mismatch")
        return "pdf"
    if ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise DocumentError("The file has a .docx extension but is not a valid Word document.", "type_mismatch")
        return "docx"
    if ext in (".jpg", ".jpeg"):
        if not content.startswith(b"\xff\xd8\xff"):
            raise DocumentError("The file has an image extension but is not a valid JPEG or PNG image.", "type_mismatch")
        return "jpg"
    if ext == ".png":
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise DocumentError("The file has an image extension but is not a valid JPEG or PNG image.", "type_mismatch")
        return "png"
    # txt / md (UTF-16 text legitimately contains NUL bytes after its BOM)
    if b"\x00" in content[:4096] and content[:2] not in (b"\xff\xfe", b"\xfe\xff"):
        raise DocumentError("The text file contains binary data.", "type_mismatch")
    return "txt"


# ----------------------------------------------------------------- normalise
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠-⁤﻿]")


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CTRL_RE.sub("", text)  # also strips invisible/bidi characters used to hide text
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ------------------------------------------------------------------ extractors
def _decode_txt(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            if enc == "utf-16" and not content[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _extract_docx(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_DOCX_ENTRIES or sum(i.file_size for i in infos) > MAX_DOCX_UNCOMPRESSED:
                raise DocumentError("The Word document is abnormally large once decompressed.", "docx_bomb")
            if "word/document.xml" not in zf.namelist():
                raise DocumentError("The Word document is invalid (missing content).", "malformed_docx")
    except zipfile.BadZipFile as e:
        raise DocumentError("The Word document is corrupted.", "malformed_docx") from e

    import docx  # python-docx

    try:
        d = docx.Document(io.BytesIO(content))
    except Exception as e:  # noqa: BLE001 - library raises many types
        raise DocumentError("The Word document could not be read.", "malformed_docx") from e
    parts: list[str] = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            cells = []
            for c in row.cells:
                t = c.text.strip()
                if t and t not in cells:
                    cells.append(t)
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _ocr_pdf(pdf, max_pages: int) -> str:
    from app.services.ocr import ocr_image_array

    texts = []
    for i in range(min(len(pdf), max_pages)):
        page = pdf[i]
        bitmap = page.render(scale=2.0)
        arr = bitmap.to_numpy()
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        texts.append(ocr_image_array(arr))
        page.close()
    return "\n\n".join(texts)


def _extract_pdf(content: bytes, *, max_pages: int, ocr_enabled: bool) -> ExtractedDocument:
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as e:
        msg = str(e).lower()
        if "password" in msg:
            raise DocumentError("The PDF is password-protected.", "encrypted_pdf") from e
        raise DocumentError("The PDF is corrupted or malformed and cannot be read.", "malformed_pdf") from e
    try:
        n_pages = len(pdf)
        if n_pages == 0:
            raise DocumentError("The PDF has no pages.", "malformed_pdf")
        warnings: list[str] = []
        if n_pages > max_pages:
            warnings.append(f"Only the first {max_pages} of {n_pages} pages were processed.")
        texts = []
        for i in range(min(n_pages, max_pages)):
            page = pdf[i]
            tp = page.get_textpage()
            texts.append(tp.get_text_bounded())
            tp.close()
            page.close()
        text = "\n\n".join(texts)
        if len(text.strip()) < SCANNED_CHARS_PER_PAGE * min(n_pages, max_pages):
            if not ocr_enabled:
                raise DocumentError(
                    "This PDF appears to be scanned (no selectable text) and OCR is disabled in settings.",
                    "scanned_pdf_ocr_disabled",
                )
            try:
                ocr_text = _ocr_pdf(pdf, max_pages)
            except ImportError as e:
                raise DocumentError(
                    "This PDF appears to be scanned and the local OCR engine is not installed "
                    "(pip install rapidocr-onnxruntime).",
                    "ocr_unavailable",
                ) from e
            if len(ocr_text.strip()) < 20:
                raise DocumentError("No readable text could be found in this scanned PDF.", "ocr_empty")
            return ExtractedDocument(ocr_text, "ocr", n_pages, warnings + ["Text obtained by local OCR: check it for recognition errors."])
        return ExtractedDocument(text, "pdf_text", n_pages, warnings)
    finally:
        pdf.close()


def _extract_image(content: bytes, *, ocr_enabled: bool) -> ExtractedDocument:
    """OCR a scanned CV delivered as a JPEG/PNG image (only the text is used)."""
    if not ocr_enabled:
        raise DocumentError("This file is an image: reading it requires OCR, which is disabled in settings.", "image_ocr_disabled")
    try:
        import cv2
        import numpy as np
    except ImportError as e:  # pragma: no cover
        raise DocumentError(
            "This PDF appears to be scanned and the local OCR engine is not installed (pip install rapidocr-onnxruntime).",
            "ocr_unavailable",
        ) from e
    buf = np.frombuffer(content, np.uint8)
    # Decode at 1/8 scale first to check dimensions cheaply (decompression-bomb guard).
    small = cv2.imdecode(buf, cv2.IMREAD_REDUCED_GRAYSCALE_8)
    if small is None:
        raise DocumentError("The image is corrupted and cannot be read.", "malformed_image")
    if small.shape[0] * small.shape[1] * 64 > MAX_IMAGE_PIXELS:
        raise DocumentError("The image is too large to be processed.", "image_too_large")
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise DocumentError("The image is corrupted and cannot be read.", "malformed_image")
    from app.services.ocr import ocr_image_array

    text = ocr_image_array(img)
    if len(text.strip()) < 20:
        raise DocumentError("No readable text could be found in this image.", "ocr_empty")
    return ExtractedDocument(text, "ocr", 1, ["Text obtained by local OCR: check it for recognition errors."])


def extract_text(file_type: str, content: bytes, *, max_pages: int = 30, ocr_enabled: bool = True) -> ExtractedDocument:
    if file_type in ("jpg", "png"):
        doc = _extract_image(content, ocr_enabled=ocr_enabled)
    elif file_type == "pdf":
        doc = _extract_pdf(content, max_pages=max_pages, ocr_enabled=ocr_enabled)
    elif file_type == "docx":
        doc = ExtractedDocument(_extract_docx(content), "docx")
    elif file_type == "txt":
        doc = ExtractedDocument(_decode_txt(content), "txt")
    else:  # pragma: no cover
        raise DocumentError("Unsupported file type.", "unsupported_type")
    doc.text = normalise_text(doc.text)
    if len(doc.text) < 20:
        raise DocumentError("The document contains no usable text.", "empty_text")
    return doc


# ------------------------------------------------------------------- sections
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "summary": ("profil", "profile", "résumé", "resume", "summary", "à propos", "about", "objectif", "objective"),
    "experience": ("expérience", "experience", "parcours professionnel", "emplois", "employment", "work history", "career"),
    "education": ("formation", "education", "études", "diplômes", "diplomes", "academic", "cursus"),
    "skills": ("compétences", "competences", "skills", "savoir-faire", "technologies", "stack", "outils", "expertise"),
    "projects": ("projets", "projects", "réalisations", "portfolio"),
    "languages": ("langues", "languages"),
    "certifications": ("certifications", "certificats", "certificates", "licences", "licenses"),
    "interests": ("centres d'intérêt", "centres d’intérêt", "intérêts", "interests", "loisirs", "hobbies"),
}


def detect_sections(text: str) -> list[dict]:
    """Return [{name, start, end}] covering the text."""
    markers: list[tuple[int, str]] = [(0, "header")]
    pos = 0
    for line in text.split("\n"):
        # Markdown / decorative marks ("## Profil", "**FORMATION**", "— Langues —") don't hide a heading
        stripped = line.strip().lstrip("#*_-=•—– ").rstrip("*_:=—– ").strip()
        low = stripped.lower()
        if 2 < len(stripped) <= 45 and not re.search(r"\d{3,}|@", stripped):
            for name, kws in SECTION_KEYWORDS.items():
                if any(low.startswith(k) for k in kws) and len(low.split()) <= 5:
                    markers.append((pos, name))
                    break
        pos += len(line) + 1
    sections = []
    for i, (start, name) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        if end > start:
            sections.append({"name": name, "start": start, "end": end})
    return sections


def section_at(sections: list[dict], offset: int) -> str:
    for s in sections:
        if s["start"] <= offset < s["end"]:
            return s["name"]
    return "header"
