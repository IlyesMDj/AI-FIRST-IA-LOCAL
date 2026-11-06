"""Couche SQLite. Données inventées uniquement."""
import threading

import pytest

from copilot import db
from copilot.types import Analysis, Criterion, Evidence, InterviewQuestion, RedactResult


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "sub" / "t.db")
    db.init(c)
    yield c
    c.close()


def _analysis(summary="Résumé fictif"):
    return Analysis(
        display_name="Prénom Fictif",
        summary=summary,
        evidence=[
            Evidence(criterion_id="C1", assessment="présent", quote="Python", start=0, end=6),
            Evidence(criterion_id="C2", assessment="non trouvé"),
        ],
        points_to_clarify=["Disponibilité"],
        dropped_quotes=1,
        model="ministral-3:3b",
        prompt_version=2,
    )


def test_pragmas(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "memory"
    assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2   # MEMORY


def test_init_idempotent(conn):
    db.init(conn)
    db.init(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"job", "criteria", "candidates", "documents", "analyses", "evidence",
            "questions", "erasure_log"} <= tables


def test_cycle_candidat(conn):
    cid = db.create_candidate(conn, "cv-fictif.pdf")
    assert len(cid) == 32 and db.candidate_exists(conn, cid)
    assert db.list_candidates(conn)[0]["status"] == "pending"
    db.set_status(conn, cid, "analyzing")
    db.set_display_name(conn, cid, "Prénom Fictif")
    db.save_document(conn, cid, RedactResult(text="Python [email retiré(e)]", removed={"email": 1}))
    db.save_analysis(conn, cid, _analysis())
    db.save_analysis(conn, cid, _analysis("Deuxième résumé"))   # remplace
    db.save_questions(conn, cid, [InterviewQuestion(question="Q1 ?", rationale="R1", criterion_id="C2")])
    db.save_questions(conn, cid, [InterviewQuestion(question="Q2 ?", rationale="R2"),
                                  InterviewQuestion(question="Q3 ?", rationale="R3", criterion_id="C1")])
    db.set_status(conn, cid, "ready")

    c = db.get_candidate(conn, cid)
    assert c["display_name"] == "Prénom Fictif"
    assert c["status"] == "ready" and c["reason"] is None
    assert c["redacted_text"] == "Python [email retiré(e)]"
    assert c["removed"] == {"email": 1}
    assert c["analysis"]["summary"] == "Deuxième résumé"
    assert Analysis.model_validate(c["analysis"]).dropped_quotes == 1
    assert [q["question"] for q in c["questions"]] == ["Q2 ?", "Q3 ?"]
    assert conn.execute("SELECT COUNT(*) FROM evidence WHERE candidate_id=?", (cid,)).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1


def test_candidat_sans_donnees(conn):
    cid = db.create_candidate(conn, "x.docx")
    db.set_status(conn, cid, "unsupported", "Format non pris en charge")
    c = db.get_candidate(conn, cid)
    assert c["redacted_text"] is None and c["removed"] == {}
    assert c["analysis"] is None and c["questions"] == []
    assert c["reason"] == "Format non pris en charge"
    assert db.get_candidate(conn, "inconnu") is None


def test_list_ordre_import(conn):
    ids = [db.create_candidate(conn, f"cv{i}.pdf") for i in range(5)]
    listed = db.list_candidates(conn)
    assert [c["id"] for c in listed] == ids
    assert set(listed[0]) == {"id", "display_name", "status", "reason", "created_at"}


def test_job_et_criteres(conn):
    j = db.get_job(conn)
    assert j == {"title": "", "text": "", "criteria": []}
    db.set_job(conn, "Poste fictif", "Texte de fiche fictive")
    db.set_criteria(conn, [Criterion(id="C2", label="SQL"), Criterion(id="C1", label="Python", description="d")])
    db.set_criteria(conn, [Criterion(id="C1", label="Python", description="d"), Criterion(id="C2", label="SQL")])
    j = db.get_job(conn)
    assert j["title"] == "Poste fictif" and j["text"] == "Texte de fiche fictive"
    assert [c["id"] for c in j["criteria"]] == ["C1", "C2"]
    assert j["criteria"][0] == {"id": "C1", "label": "Python", "description": "d"}


def test_save_analysis_candidat_efface(conn):
    cid = db.create_candidate(conn, "cv.pdf")
    conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
    with pytest.raises(db.CandidateNotFound):
        db.save_analysis(conn, cid, _analysis())
    with pytest.raises(KeyError):          # CandidateNotFound hérite de KeyError
        db.save_document(conn, cid, RedactResult(text="t", removed={}))
    with pytest.raises(KeyError):
        db.save_questions(conn, cid, [InterviewQuestion(question="Q", rationale="R")])
    for t in ("analyses", "evidence", "documents", "questions"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_cascade(conn):
    cid = db.create_candidate(conn, "cv.pdf")
    db.save_document(conn, cid, RedactResult(text="t", removed={}))
    db.save_analysis(conn, cid, _analysis())
    conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
    for t in ("analyses", "evidence", "documents"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0


def test_ecritures_concurrentes(tmp_path):
    path = tmp_path / "c.db"
    c0 = db.connect(path)
    db.init(c0)
    errors = []

    def work():
        try:
            c = db.connect(path)
            for _ in range(10):
                cid = db.create_candidate(c, "cv.pdf")
                db.save_analysis(c, cid, _analysis())
            c.close()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=work) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    assert len(db.list_candidates(c0)) == 40
    c0.close()


def test_aucun_journal_sur_disque(tmp_path):
    path = tmp_path / "j.db"
    c = db.connect(path)
    db.init(c)
    cid = db.create_candidate(c, "cv.pdf")
    with db.tx(c):
        c.execute("INSERT INTO documents VALUES (?,?,?)", (cid, "texte fictif", "{}"))
        assert not path.with_name("j.db-journal").exists()
        assert not path.with_name("j.db-wal").exists()
    c.close()
