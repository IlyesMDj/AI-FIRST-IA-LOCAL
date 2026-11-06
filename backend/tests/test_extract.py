"""Extraction. PDF et images générés à la volée avec pymupdf (données inventées)."""
from pathlib import Path

import pymupdf
import pytest

from copilot.config import MAX_UPLOAD_BYTES
from copilot.extract import extract

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "a_cv_fictif.txt"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _pdf_text(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for t in pages:
        page = doc.new_page()
        page.insert_text((72, 72), t, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _pdf_scan(n_pages: int = 1) -> bytes:
    """PDF « scanné » : uniquement des formes dessinées, aucune couche texte."""
    doc = pymupdf.open()
    for _ in range(n_pages):
        page = doc.new_page()
        page.draw_rect(pymupdf.Rect(50, 50, 300, 120), color=(0, 0, 0), fill=(0.2, 0.2, 0.2))
    data = doc.tobytes()
    doc.close()
    return data


def _png() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.clear_with(200)
    return pix.tobytes("png")


def _jpg() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 30), False)
    pix.clear_with(120)
    return pix.tobytes("jpg")


def test_pdf_texte():
    line = "Profil fictif : ingénieure données, Python, SQL, Airflow, dix projets livrés"
    r = extract("cv.PDF", _pdf_text([line, "Deuxième page : Kubernetes, Terraform et FastAPI en production"]))
    assert r.status == "ok"
    assert "ingénieure données" in r.text and "Kubernetes" in r.text
    assert r.page_images == []


def test_pdf_scan_needs_vision():
    r = extract("scan.pdf", _pdf_scan(1))
    assert r.status == "needs_vision"
    assert r.reason
    assert len(r.page_images) == 1 and r.page_images[0].startswith(PNG_MAGIC)


def test_pdf_scan_max_3_pages():
    r = extract("scan.pdf", _pdf_scan(5))
    assert r.status == "needs_vision"
    assert len(r.page_images) == 3
    assert "5" in r.reason


def test_pdf_presque_vide_needs_vision():
    r = extract("cv.pdf", _pdf_text(["p. 1"]))
    assert r.status == "needs_vision"


def test_pdf_corrompu():
    r = extract("cv.pdf", b"%PDF-1.7\n" + b"\x13\x37 garbage " * 50)
    assert r.status == "unsupported" and r.reason


def test_pdf_mal_nomme():
    r = extract("cv.pdf", b"ceci n'est pas un pdf")
    assert r.status == "unsupported" and "PDF" in r.reason


def test_pdf_chiffre():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Texte fictif protégé par mot de passe pour le test")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    r = extract("cv.pdf", data)
    assert r.status == "unsupported" and "mot de passe" in r.reason


def test_txt_utf8_et_md():
    raw = FIXTURE.read_bytes()
    r = extract("a.txt", raw)
    assert r.status == "ok" and "Zéphyrine" in r.text
    assert extract("a.md", "# Titre\nCompétences : Python".encode("utf-8")).status == "ok"


def test_txt_bom_et_cp1252():
    r = extract("a.txt", "﻿Élodie Fictive".encode("utf-8"))
    assert r.text == "Élodie Fictive"
    r = extract("a.txt", "Expérience à Montréal".encode("cp1252"))
    assert r.status == "ok" and r.text == "Expérience à Montréal"


def test_txt_vide():
    r = extract("a.txt", b"   \n\n ")
    assert r.status == "unsupported" and r.reason


def test_images():
    for name, data in (("photo-cv.png", _png()), ("cv.JPG", _jpg()), ("cv.jpeg", _jpg())):
        r = extract(name, data)
        assert r.status == "needs_vision", name
        assert len(r.page_images) == 1 and r.page_images[0].startswith(PNG_MAGIC)


def test_image_corrompue():
    r = extract("cv.png", b"pas une image")
    assert r.status == "unsupported" and r.reason


@pytest.mark.parametrize("name", ["cv.docx", "cv.odt", "cv", "cv.exe", "cv.webp"])
def test_format_inconnu(name):
    r = extract(name, b"contenu quelconque")
    assert r.status == "unsupported"
    assert "non pris en charge" in r.reason


def test_trop_gros():
    r = extract("cv.txt", b"a" * (MAX_UPLOAD_BYTES + 1))
    assert r.status == "unsupported" and "volumineux" in r.reason


def test_vide():
    r = extract("cv.pdf", b"")
    assert r.status == "unsupported" and r.reason


def _pdf_mixte() -> bytes:
    """Page 1 texte, page 2 scan, page 3 texte, page 4 scan."""
    doc = pymupdf.open()
    for i in range(4):
        page = doc.new_page()
        if i % 2 == 0:
            page.insert_text((72, 72), f"Page texte fictive numéro {i + 1} : Python, SQL, Docker, Airflow")
        else:
            page.draw_rect(pymupdf.Rect(50, 50, 300, 120), color=(0, 0, 0), fill=(0.3, 0.3, 0.3))
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_mixte():
    r = extract("cv.pdf", _pdf_mixte())
    assert r.status == "ok"
    assert "numéro 1" in r.text and "numéro 3" in r.text
    assert len(r.page_images) == 2 and all(i.startswith(PNG_MAGIC) for i in r.page_images)
    assert r.reason and "2,4" in r.reason and "scannée" in r.reason


def test_txt_utf16_bom():
    for enc in ("utf-16", "utf-16-be"):
        data = "Élodie Fictive — Python".encode(enc)
        if enc == "utf-16-be":
            data = b"\xfe\xff" + data
        r = extract("a.txt", data)
        assert r.status == "ok", enc
        assert r.text == "Élodie Fictive — Python"


def test_page_geante_rendu_borne():
    doc = pymupdf.open()
    page = doc.new_page(width=5000, height=5000)   # ~1,76 m de côté
    page.draw_rect(pymupdf.Rect(10, 10, 4000, 4000), color=(0, 0, 0), fill=(0.5, 0.5, 0.5))
    data = doc.tobytes()
    doc.close()
    r = extract("scan.pdf", data)
    assert r.status == "needs_vision"
    pix = pymupdf.Pixmap(r.page_images[0])
    assert max(pix.width, pix.height) <= 2000
