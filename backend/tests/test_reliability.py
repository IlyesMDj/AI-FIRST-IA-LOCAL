"""Reliability tests: the application must fail gracefully."""
from __future__ import annotations

import io
import zipfile

import pytest

from app.demo.synthetic import cv_by_key, make_pdf, make_scanned_pdf
from app.services.ocr import ocr_available
from tests.conftest import process_all, upload

CAMILLE = cv_by_key("camille_fr_backend")


def _imp(client, name, content):
    r = upload(client, [(name, content)])
    res = r.json()["results"][0]
    process_all()
    return res


def test_ollama_unavailable(client):
    client.fake.fail_mode = "down"
    res = _imp(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed"
    assert "Ollama" in d["error_message"]
    st = client.get("/api/system/status").json()
    assert st["ollama"]["reachable"] is False and st["issues"]
    # recover
    client.fake.fail_mode = None
    client.post(f"/api/candidates/{res['candidate_id']}/process")
    process_all()
    assert client.get(f"/api/candidates/{res['candidate_id']}").json()["status"] == "completed"


def test_model_unavailable(client):
    client.fake.models = ["qwen2.5:7b", "nomic-embed-text:latest"]  # qwen3 missing
    res = _imp(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "not installed" in d["error_message"]
    st = client.get("/api/system/status").json()
    assert st["active_model_available"] is False
    assert any("qwen2.5:7b" in i for i in st["issues"])  # offers an alternative
    # settings refuse a model that is not installed
    s = client.get("/api/settings/ai").json()["settings"]
    s["active_model"] = "does-not-exist:1b"
    assert client.put("/api/settings/ai", json=s).status_code == 400
    s["active_model"] = "qwen2.5:7b"
    assert client.put("/api/settings/ai", json=s).status_code == 200


def test_invalid_model_response(client):
    client.fake.fail_mode = "invalid_json_always"
    res = _imp(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "invalid response" in d["error_message"]
    assert d["profile"] is None  # nothing unvalidated stored


def test_inference_timeout(client):
    client.fake.fail_mode = "timeout"
    res = _imp(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "did not answer in time" in d["error_message"]


def test_malformed_pdf(client):
    res = _imp(client, "broken.pdf", b"%PDF-1.4\n garbage garbage \n%%EOF")
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "PDF" in d["error_message"]


def test_wrong_type_and_empty_rejected(client):
    r = upload(client, [("x.pdf", b"MZ\x90\x00 not a pdf"), ("y.exe", b"MZ"), ("z.txt", b""), ("w.docx", b"hello")])
    statuses = [x["status"] for x in r.json()["results"]]
    assert statuses == ["rejected"] * 4


def test_docx_zip_bomb_rejected(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", b"0" * (70 * 1024 * 1024))
    res = _imp(client, "bomb.docx", buf.getvalue())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "abnormally large" in d["error_message"]


def test_file_too_large(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    r = upload(client, [("big.txt", b"a" * (2 * 1024 * 1024))])
    assert r.json()["results"][0]["status"] == "rejected"


def test_large_cv_truncated_with_warning(client):
    big = CAMILLE.text + ("\nProjet supplémentaire : maintenance d'outils internes en Python." * 800)
    res = _imp(client, "big.txt", big.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "completed"
    assert any("only the first" in w for w in d["warnings"])


def test_insufficient_ram(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "min_free_ram_mb", 10**9)
    res = _imp(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "RAM" in d["error_message"]


@pytest.mark.skipif(not ocr_available(), reason="rapidocr not installed")
def test_scanned_pdf_ocr(client):
    res = _imp(client, "scan.pdf", make_scanned_pdf(cv_by_key("sam_en_devops").text))
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "completed", d
    assert d["ocr_used"] is True
    text = client.get(f"/api/candidates/{res['candidate_id']}/text").json()
    assert text["method"] == "ocr" and "Kubernetes" in text["text"]


def test_scanned_pdf_with_ocr_disabled(client):
    s = client.get("/api/settings/ai").json()["settings"]
    s["ocr_enabled"] = False
    client.put("/api/settings/ai", json=s)
    res = _imp(client, "scan.pdf", make_scanned_pdf("Hello\nWorld"))
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "failed" and "OCR is disabled" in d["error_message"]


def test_deleting_candidate_during_processing_is_safe(client):
    """Worker must not crash or resurrect data if the candidate disappears."""
    res = upload(client, [("a.txt", CAMILLE.text.encode())]).json()["results"][0]
    client.delete(f"/api/candidates/{res['candidate_id']}")
    process_all()  # queued task for a deleted candidate
    assert client.get(f"/api/candidates/{res['candidate_id']}").status_code == 404


def test_pdf_text_extraction_unit():
    from app.services.documents import extract_text

    doc = extract_text("pdf", make_pdf(CAMILLE.text))
    assert doc.method == "pdf_text" and "FastAPI" in doc.text


def _png_of(text: str) -> bytes:
    import io

    from PIL import Image, ImageDraw, ImageFont

    lines = text.split("\n")[:40]
    img = Image.new("RGB", (1240, 60 + 34 * len(lines)), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    for i, line in enumerate(lines):
        draw.text((40, 30 + 34 * i), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not ocr_available(), reason="rapidocr not installed")
def test_image_cv_ocr(client):
    res = _imp(client, "scan.png", _png_of(cv_by_key("sam_en_devops").text))
    d = client.get(f"/api/candidates/{res['candidate_id']}").json()
    assert d["status"] == "completed", d
    assert d["ocr_used"] is True and d["file_type"] == "png"
    assert client.get(f"/api/candidates/{res['candidate_id']}/document").headers["content-type"] == "image/png"


def test_fake_image_rejected(client):
    r = upload(client, [("photo.jpg", b"%PDF-1.4 not an image"), ("x.png", b"GIF89a")])
    assert [x["status"] for x in r.json()["results"]] == ["rejected", "rejected"]


def test_markdown_and_utf16_text(client):
    from app.services.documents import detect_sections, detect_type

    secs = detect_sections("Candidat EXEMPLE\n## Profil\nSept ans\n## Expérience\n**Dev**, A\n## Formation\nIng\n## Compétences\nPython")
    assert [s["name"] for s in secs] == ["header", "summary", "experience", "education", "skills"]
    assert detect_type("cv.txt", "Bonjour CV".encode("utf-16")) == "txt"
    res = _imp(client, "cv.md", CAMILLE.text.encode("utf-8"))
    assert client.get(f"/api/candidates/{res['candidate_id']}").json()["status"] == "completed"
