"""API + worker de bout en bout, LLM mocké. Données inventées uniquement."""
from __future__ import annotations

import json
import tempfile
import threading
import time

import pytest
from fastapi.testclient import TestClient

from copilot import api as api_mod
from copilot import criteria as criteria_mod
from copilot import db, llm
from copilot.config import MAX_UPLOAD_BYTES

NAME = "Zéphyrine Cassiopée-Fictive"
CV = (
    f"{NAME}\n"
    "Développeuse back-end, email zephyrine.fictive@exemple.invalid, tél 06 12 34 56 78\n"
    "Expérience : 5 ans de Python en production chez Société Imaginaire du Sud.\n"
    "Conception d'API avec FastAPI et PostgreSQL pour la logistique de comètes.\n"
    "Encadrement de deux développeurs juniors, revues de code hebdomadaires.\n"
)
CRITS = [
    {"id": "C1", "label": "Python", "description": "Python en production"},
    {"id": "C2", "label": "FastAPI", "description": "API web"},
    {"id": "C3", "label": "Docker", "description": "Conteneurs"},
]


class FakeLLM:
    def __init__(self):
        self.block = threading.Event()
        self.block.set()            # pas de blocage par défaut
        self.entered = threading.Event()
        self.calls = 0

    def chat_json(self, model_key, system, user, schema, images=None):
        self.calls += 1
        props = schema.get("properties", {})
        if "evidence" in props:
            self.entered.set()
            assert self.block.wait(10)
            return {
                "display_name": NAME,
                "summary": "Profil back-end Python (résumé factice).",
                "evidence": [
                    {"criterion_id": "C1", "assessment": "présent", "quote": "5 ans de Python en production"},
                    {"criterion_id": "C2", "assessment": "partiel", "quote": "citation inventée absente du texte"},
                    {"criterion_id": "C9", "assessment": "présent", "quote": "hors liste"},
                ],
                "points_to_clarify": ["Docker non mentionné"],
            }
        if "questions" in props:
            return {"questions": [
                {"criterion_id": "C3", "question": f"Question factice {i} sur Docker ?", "rationale": "non trouvé"}
                for i in range(5)
            ]}
        if "criteria" in props:
            return {"criteria": [{"label": f"Critère {i}", "description": ""} for i in range(4)]}
        raise AssertionError("schéma inattendu")

    def chat_stream(self, model_key, system, user):
        yield "Selon le CV, "
        yield "5 ans de Python."


@pytest.fixture
def fake(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(llm, "chat_json", f.chat_json)
    monkeypatch.setattr(llm, "chat_stream", f.chat_stream)
    monkeypatch.setattr(llm, "health", lambda: {"ok": True, "models": ["fake"], "missing": []})
    return f


@pytest.fixture
def client(tmp_path, monkeypatch, fake):
    monkeypatch.setenv("COPILOT_DB", str(tmp_path / "api.db"))
    monkeypatch.setattr(criteria_mod, "load_job_text", lambda: ("Poste fictif", "Fiche de poste fictive."))
    with TestClient(api_mod.app) as c:
        r = c.put("/api/job/criteria", json={"criteria": CRITS})
        assert r.status_code == 200
        yield c


def _upload(client, *files, model="rapide"):
    return client.post("/api/candidates", files=[("files", (n, d, "application/octet-stream")) for n, d in files],
                       data={"model": model})


def _wait(client, cid, statuses=("ready", "error", "unsupported"), timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/candidates/{cid}")
        if r.status_code == 404:
            return None
        if r.json()["status"] in statuses:
            return r.json()
        time.sleep(0.05)
    raise AssertionError("délai dépassé")


def _sse_events(text: str) -> list[dict]:
    return [json.loads(line[5:].strip()) for line in text.splitlines() if line.startswith("data:")]


def test_startup_job_and_health(client):
    job = client.get("/api/job").json()
    assert job["title"] == "Poste fictif"
    assert [c["id"] for c in job["criteria"]] == ["C1", "C2", "C3"]
    h = client.get("/api/health").json()
    assert h["ok"] is True and set(h["model_keys"]) == {"rapide", "precis"}


def test_full_flow(client):
    r = _upload(client, ("cv_premier.txt", CV.encode()), ("cv_second.txt", CV.replace(NAME, "Autre Personne").encode()))
    assert r.status_code == 200, r.text
    up = r.json()
    assert [u["status"] for u in up] == ["pending", "pending"]
    assert up[0]["display_name"] == "cv premier"
    c1, c2 = up[0]["id"], up[1]["id"]

    cand = _wait(client, c1)
    assert cand["status"] == "ready", cand
    assert cand["display_name"] == NAME
    assert "zephyrine.fictive@exemple.invalid" not in cand["redacted_text"]
    assert cand["removed"].get("email") == 1
    ev = {e["criterion_id"]: e for e in cand["analysis"]["evidence"]}
    assert set(ev) == {"C1", "C2", "C3"}
    assert ev["C1"]["quote"] == "5 ans de Python en production"
    assert ev["C2"]["assessment"] == "partiel" and ev["C2"]["quote"] is None
    assert ev["C3"]["assessment"] == "non trouvé"
    assert cand["analysis"]["dropped_quotes"] == 1
    _wait(client, c2)

    # liste et comparaison : ordre d'import, aucun score
    lst = client.get("/api/candidates").json()
    assert [c["id"] for c in lst] == [c1, c2]
    cmp_ = client.get("/api/compare").json()
    assert [c["id"] for c in cmp_["candidates"]] == [c1, c2]
    assert cmp_["candidates"][0]["cells"]["C1"]["assessment"] == "présent"
    blob = json.dumps(cmp_).lower()
    for word in ("score", "rank", "rang", "recommand", "meilleur"):
        assert word not in blob

    # questions
    r = client.post(f"/api/candidates/{c1}/questions", json={"model": "rapide"})
    assert r.status_code == 200, r.text
    qs = r.json()["questions"]
    assert len(qs) == 5 and qs[0]["criterion_id"] == "C3"
    assert len(client.get(f"/api/candidates/{c1}").json()["questions"]) == 5

    # ask : SSE token… done, rien de stocké
    r = client.post(f"/api/candidates/{c1}/ask", json={"question": "Combien d'années de Python ?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse_events(r.text)
    assert "".join(e.get("token", "") for e in events) == "Selon le CV, 5 ans de Python."
    assert events[-1] == {"done": True}

    # effacement vérifiable
    r = client.delete(f"/api/candidates/{c1}")
    assert r.status_code == 200, r.text
    proof = r.json()
    assert proof["verified"] is True
    assert proof["raw_file_hits"] == 0 and proof["extracts_checked"] > 0 and proof["vacuum_ok"] is True
    assert all(v == 0 for v in proof["tables"].values())
    assert client.get(f"/api/candidates/{c1}").status_code == 404
    assert client.delete(f"/api/candidates/{c1}").status_code == 404
    er = client.get("/api/erasures").json()
    assert len(er) == 1 and er[0]["candidate_id_hash"] == proof["candidate_id_hash"]
    assert c1 not in json.dumps(er)
    assert [c["id"] for c in client.get("/api/candidates").json()] == [c2]


def test_ask_error_event(client, monkeypatch):
    cid = _upload(client, ("a.txt", CV.encode())).json()[0]["id"]
    _wait(client, cid)

    def boom(*a, **k):
        raise llm.LLMError("appel Ollama impossible : ConnectError")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "chat_stream", boom)
    r = client.post(f"/api/candidates/{cid}/ask", json={"question": "Expérience Python ?"})
    ev = _sse_events(r.text)
    assert "error" in ev[-1]


def test_erase_during_analysis(client, fake):
    fake.block.clear()
    fake.entered.clear()
    cid = _upload(client, ("x.txt", CV.encode())).json()[0]["id"]
    assert fake.entered.wait(10)
    assert client.get(f"/api/candidates/{cid}").json()["status"] == "analyzing"
    proof = client.delete(f"/api/candidates/{cid}").json()
    assert proof["verified"] is True
    fake.block.set()
    worker = client.app.state.worker
    worker.join()
    assert client.get(f"/api/candidates/{cid}").status_code == 404
    assert client.get("/api/candidates").json() == []
    # le worker est toujours vivant
    cid2 = _upload(client, ("y.txt", CV.encode())).json()[0]["id"]
    assert _wait(client, cid2)["status"] == "ready"


def test_upload_too_large(client):
    big = b"a" * (MAX_UPLOAD_BYTES + 1)
    r = _upload(client, ("ok.txt", CV.encode()), ("gros.txt", big))
    assert r.status_code == 413
    assert "volumineux" in r.json()["detail"]
    assert client.get("/api/candidates").json() == []


def test_unreadable_files(client):
    up = _upload(client, ("cv.docx", b"PK\x03\x04 pas un docx"), ("cv.pdf", b"%PDF-1.4 corrompu"),
                 ("vide.txt", b"")).json()
    for u in up:
        c = _wait(client, u["id"])
        assert c["status"] == "unsupported", c
        assert c["reason"]
        assert c["redacted_text"] is None


def test_upload_stays_in_memory(client, monkeypatch):
    """Un fichier de plusieurs Mo ne doit jamais toucher %TEMP% (pas de SpooledTemporaryFile)."""
    def forbidden(*a, **k):
        raise AssertionError("fichier temporaire créé pendant l'upload")

    import starlette.formparsers as sf
    monkeypatch.setattr(sf, "SpooledTemporaryFile", forbidden)
    for n in ("SpooledTemporaryFile", "TemporaryFile", "NamedTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, n, forbidden)
    payload = (CV + "Ligne de remplissage factice pour dépasser un mégaoctet.\n" * 60000).encode()
    assert 2 * 1024 * 1024 < len(payload) < MAX_UPLOAD_BYTES
    r = _upload(client, ("long.txt", payload))
    assert r.status_code == 200, r.text
    # Le fichier (> 2 Mo) a été reçu et traité sans aucun fichier temporaire ; son texte dépasse
    # ensuite le plafond de CV (llm.MAX_CV_CHARS), d'où un refus clair plutôt qu'une analyse.
    c = _wait(client, r.json()[0]["id"])
    assert c["status"] == "error"
    assert "trop long" in (c["reason"] or "")


def test_llm_failure_sets_error_without_content(client, fake, monkeypatch):
    def down(*a, **k):
        raise llm.LLMError("appel Ollama impossible : ConnectError")

    monkeypatch.setattr(llm, "chat_json", down)
    cid = _upload(client, ("z.txt", CV.encode())).json()[0]["id"]
    c = _wait(client, cid)
    assert c["status"] == "error"
    assert "Python" not in c["reason"] and NAME not in c["reason"]
    assert c["redacted_text"]          # texte masqué conservé → ré-analyse possible
    monkeypatch.setattr(llm, "chat_json", fake.chat_json)
    assert client.post(f"/api/candidates/{cid}/reanalyze", json={"model": "rapide"}).json() == {"status": "pending"}
    assert _wait(client, cid)["status"] == "ready"


def test_questions_before_ready_and_unknown(client):
    assert client.get("/api/candidates/inconnu").status_code == 404
    assert client.post("/api/candidates/inconnu/questions", json={}).status_code == 404
    assert client.delete("/api/candidates/inconnu").status_code == 404


def test_recovery_on_restart(tmp_path, monkeypatch, fake):
    from copilot.types import RedactResult
    path = tmp_path / "rec.db"
    monkeypatch.setenv("COPILOT_DB", str(path))
    monkeypatch.setattr(criteria_mod, "load_job_text", lambda: ("Poste fictif", "Fiche fictive."))
    conn = db.connect(path)
    db.init(conn)
    from copilot.types import Criterion
    db.set_criteria(conn, [Criterion(**c) for c in CRITS])
    with_doc = db.create_candidate(conn, "avec doc")
    db.save_document(conn, with_doc, RedactResult(text=CV, removed={}))
    db.set_status(conn, with_doc, "analyzing")
    no_doc = db.create_candidate(conn, "sans doc")
    conn.close()
    with TestClient(api_mod.app) as c:
        assert _wait(c, with_doc)["status"] == "ready"
        nd = _wait(c, no_doc)
        assert nd["status"] == "error" and "réimporter" in nd["reason"]


def test_put_criteria_rejects_discriminatory(client):
    bad = [{"id": "C1", "label": "Python", "description": ""},
           {"id": "C2", "label": "Moins de 30 ans", "description": ""}]
    r = client.put("/api/job/criteria", json={"criteria": bad})
    assert r.status_code == 422
    assert "Moins de 30 ans" in r.json()["detail"]
    ok = [{"id": "C1", "label": "Python avancé", "description": "Django ou FastAPI"}]
    r = client.put("/api/job/criteria", json={"criteria": ok})
    assert r.status_code == 200 and r.json()["warnings"] == {}


def test_api_responses_are_not_cached(client):
    assert client.get("/api/candidates").headers["cache-control"] == "no-store"
