"""Functional acceptance tests (fake Ollama, synthetic CVs)."""
from __future__ import annotations

import json

from app.demo.synthetic import JOBS, cv_by_key, make_docx, make_pdf
from tests.conftest import process_all, upload

CAMILLE = cv_by_key("camille_fr_backend")
JORDAN = cv_by_key("jordan_en_data")


def _import_and_process(client, name, content):
    r = upload(client, [(name, content)])
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "imported", res
    process_all()
    return res["candidate_id"]


def _create_job(client, idx=0):
    r = client.post("/api/jobs", json=JOBS[idx])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_import_pdf_and_extract(client):
    cid = _import_and_process(client, "cv_camille.pdf", make_pdf(CAMILLE.text))
    d = client.get(f"/api/candidates/{cid}").json()
    assert d["status"] == "completed", d
    assert d["display_name"] == "Camille Fictif"
    prof = d["profile"]
    names = [s["name"] for s in prof["skills"]]
    assert "FastAPI" in names and "PostgreSQL" in names
    # evidence verification: real skills verified, invented one flagged
    by_name = {s["name"]: s for s in prof["skills"]}
    assert by_name["FastAPI"]["verification"]["status"] == "verified"
    assert by_name["Hallucinated Skill"]["verification"]["status"] == "not_found"
    assert 0 < prof["extraction_metadata"]["confidence"] < 1
    assert any("could not be matched" in w for w in d["warnings"])
    assert [e["company"] for e in prof["experience"]] == ["Société Alpha Données", "Beta Logiciels"]


def test_import_multiple_formats(client):
    r = upload(client, [
        ("a.pdf", make_pdf(CAMILLE.text)),
        ("b.docx", make_docx(JORDAN.text)),
        ("c.txt", cv_by_key("sam_en_devops").text.encode("utf-8")),
    ])
    results = r.json()["results"]
    assert [x["status"] for x in results] == ["imported"] * 3
    process_all()
    lst = client.get("/api/candidates").json()
    assert len(lst) == 3 and all(c["status"] == "completed" for c in lst)


def test_duplicate_detection(client):
    pdf = make_pdf(CAMILLE.text)
    upload(client, [("a.pdf", pdf)])
    r = upload(client, [("copy.pdf", pdf)])
    res = r.json()["results"][0]
    assert res["status"] == "duplicate" and res["existing_candidate_id"]
    assert len(client.get("/api/candidates").json()) == 1


def test_possible_duplicate_flagged_not_merged(client):
    _import_and_process(client, "a.txt", CAMILLE.text.encode())
    cid2 = _import_and_process(client, "b.txt", (CAMILLE.text + "\nMise à jour").encode())
    d = client.get(f"/api/candidates/{cid2}").json()
    assert d["possible_duplicates"] and d["possible_duplicates"][0]["rule"] == "same email address"
    assert len(client.get("/api/candidates").json()) == 2


def test_validate_generated_json_with_repair(client):
    client.fake.fail_mode = "invalid_json_once"
    cid = _import_and_process(client, "a.txt", CAMILLE.text.encode())
    d = client.get(f"/api/candidates/{cid}").json()
    assert d["status"] == "completed"
    assert d["profile"]["extraction_metadata"]["attempts"] == 2


def test_job_and_analysis(client):
    cid = _import_and_process(client, "a.pdf", make_pdf(CAMILLE.text))
    jid = _create_job(client, 0)
    crit = client.get(f"/api/jobs/{jid}/criteria").json()
    assert {c["requirement"] for c in crit} >= {"Python", "PostgreSQL", "Kubernetes"}
    r = client.post("/api/analyses", json={"candidate_ids": [cid], "job_id": jid})
    assert r.status_code == 202
    aid = r.json()[0]["id"]
    process_all()
    a = client.get(f"/api/analyses/{aid}").json()
    assert a["status"] == "completed", a
    res = {c["requirement"]: c for c in a["result"]["criteria"]}
    assert res["Python"]["status"] == "demonstrated"
    assert res["Python"]["evidence"][0]["verified"] is True
    assert res["Python"]["evidence"][0]["location"]["section"] in ("header", "experience", "skills", "summary")
    assert res["Kubernetes"]["status"] == "not_found"
    # No score / ranking anywhere in the payload
    blob = json.dumps(a).lower()
    for forbidden in ('"score"', '"rank"', '"ranking"', '"winner"', '"recommendation"'):
        assert forbidden not in blob


def test_analysis_requires_processed_cv(client):
    r = upload(client, [("a.txt", CAMILLE.text.encode())], )
    cid = r.json()["results"][0]["candidate_id"]
    jid = _create_job(client)
    # still pending (worker not drained)
    r = client.post("/api/analyses", json={"candidate_ids": [cid], "job_id": jid})
    assert r.status_code == 409


def test_assistant_question_with_citation(client):
    cid = _import_and_process(client, "a.txt", CAMILLE.text.encode())
    conv = client.post("/api/conversations", json={"candidate_ids": [cid]}).json()
    r = client.post(f"/api/conversations/{conv['id']}/messages", json={"message": "Does the CV mention PostgreSQL?"})
    lines = [json.loads(l) for l in r.text.strip().split("\n")]
    assert lines[0]["type"] == "sources"
    assert all(s["candidate_id"] == cid for s in lines[0]["sources"])
    assert lines[-1]["type"] == "done" and lines[-1]["citations"]
    hist = client.get(f"/api/conversations/{conv['id']}").json()
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]


def test_compare_two_candidates(client):
    c1 = _import_and_process(client, "a.txt", CAMILLE.text.encode())
    c2 = _import_and_process(client, "b.txt", JORDAN.text.encode())
    jid = _create_job(client, 0)
    client.post("/api/analyses", json={"candidate_ids": [c1, c2], "job_id": jid})
    process_all()
    r = client.post("/api/compare", json={"candidate_ids": [c1, c2], "job_id": jid}).json()
    assert len(r["columns"]) == 2
    assert r["columns"][0]["analysis"]["criteria"]["Python"]["status"] == "demonstrated"
    assert "winner" not in json.dumps(r).lower().replace("no overall score or winner", "")


def test_interview_questions(client):
    cid = _import_and_process(client, "a.txt", CAMILLE.text.encode())
    jid = _create_job(client, 0)
    aid = client.post("/api/analyses/interview", json={"candidate_ids": [cid], "job_id": jid}).json()[0]["id"]
    process_all()
    a = client.get(f"/api/analyses/{aid}").json()
    assert a["status"] == "completed"
    cats = {c["key"]: c["questions"] for c in a["result"]["categories"]}
    assert set(cats) == {"technical", "experience", "project", "problem_solving", "clarification"}
    # discriminatory question generated by the (fake) model was filtered out
    assert a["result"]["removed_questions"] == 1
    assert all("âge" not in q["question"] for qs in cats.values() for q in qs)


def test_delete_candidate(client):
    cid = _import_and_process(client, "a.pdf", make_pdf(CAMILLE.text))
    r = client.delete(f"/api/candidates/{cid}")
    assert r.status_code == 200
    rep = r.json()
    assert rep["success"] is True
    assert all(c["passed"] for c in rep["report"]["verification"])
    assert client.get(f"/api/candidates/{cid}").status_code == 404
    assert client.get(f"/api/deletion-reports/{rep['report_id']}").json()["success"] is True
