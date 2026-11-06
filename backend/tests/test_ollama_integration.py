"""Integration tests against the REAL local Ollama (synthetic data only).

Run with:  RCL_TEST_OLLAMA=1 pytest tests/test_ollama_integration.py -s
"""
from __future__ import annotations

import os
import queue

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RCL_TEST_OLLAMA") != "1", reason="set RCL_TEST_OLLAMA=1")


@pytest.fixture
def real_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RCL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RCL_MIN_FREE_RAM_MB", "300")
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.llm import gateway
    from app.main import create_app
    from app.worker import worker

    gateway.set_client(None)
    worker.q = queue.Queue()
    worker._queued.clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_real_extraction_analysis_chat_and_deletion(real_client, no_network):
    from app.demo.synthetic import JOBS, cv_by_key, make_pdf
    from tests.conftest import process_all, upload

    c = real_client
    cv = cv_by_key("nora_fr_fullstack_injection")
    cid = upload(c, [("nora.pdf", make_pdf(cv.text))]).json()["results"][0]["candidate_id"]
    process_all()
    d = c.get(f"/api/candidates/{cid}").json()
    print("\nstatus:", d["status"], d["error_message"], "confidence:", d["confidence"])
    assert d["status"] == "completed", d
    skills = [s["name"].lower() for s in d["profile"]["skills"]]
    print("skills:", skills)
    assert any("react" in s for s in skills)
    assert not any(s in ("python", "kubernetes") for s in skills)
    assert d["injection_flags"]

    jid = c.post("/api/jobs", json=JOBS[0]).json()["id"]
    aid = c.post("/api/analyses", json={"candidate_ids": [cid], "job_id": jid}).json()[0]["id"]
    process_all()
    a = c.get(f"/api/analyses/{aid}").json()
    assert a["status"] == "completed", a
    st = {x["requirement"]: x["status"] for x in a["result"]["criteria"]}
    print("analysis:", st)
    assert st["Python"] in ("not_found", "undetermined")

    conv = c.post("/api/conversations", json={"candidate_ids": [cid]}).json()
    r = c.post(f"/api/conversations/{conv['id']}/messages", json={"message": "Quelles sont ses compétences front-end ?"})
    print("chat:", r.text[-400:])
    assert '"type": "done"' in r.text

    rep = c.delete(f"/api/candidates/{cid}").json()
    assert rep["success"]
    assert all(h in ("127.0.0.1", "::1", "localhost") for h in no_network)
