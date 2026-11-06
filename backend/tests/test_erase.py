"""Effacement vérifiable. Données inventées uniquement."""
import json

import pytest

from copilot import db
from copilot.erase import erase_candidate
from copilot.types import Analysis, Evidence, InterviewQuestion, RedactResult

UNIQUE = "Licorne-Quasar-7f3e9b compétence en tressage de comètes"
NAME = "Ophélie Tournesol-Fictive"


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    db.init(conn)
    yield conn, path
    conn.close()


def _seed(conn, name, unique_line):
    cid = db.create_candidate(conn, name)
    text = (
        f"{name}\n"
        f"Profil : {unique_line}\n"
        "Expérience 2019-2024 chez Société Imaginaire du Nord (Python, SQL)\n"
        f"Projet phare : {unique_line[::-1]} déployé en production\n"
    )
    db.save_document(conn, cid, RedactResult(text=text, removed={"email": 1}))
    a = Analysis(
        display_name=name,
        summary=f"Résumé : {unique_line}",
        evidence=[Evidence(criterion_id="C1", assessment="présent",
                           quote=unique_line, start=10, end=10 + len(unique_line))],
        model="m", prompt_version=1,
    )
    db.save_analysis(conn, cid, a)
    db.save_questions(conn, cid, [InterviewQuestion(question=f"Parlez de {unique_line}",
                                                    rationale="r", criterion_id="C1")])
    db.set_status(conn, cid, "ready")
    return cid


def test_erase_complete(env):
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    other = _seed(conn, "Barnabé Lampadaire-Fictif", "Zigzag-Nébuleuse-a91c22 expert en origami quantique")
    conn.commit()
    # garde-fou : l'extrait est bien présent dans le fichier avant effacement
    assert UNIQUE.encode("utf-8") in path.read_bytes()

    proof = erase_candidate(conn, cid, db_path=path)

    assert proof.verified is True
    assert proof.raw_file_hits == 0
    assert set(proof.tables) >= {"candidates", "documents", "analyses", "evidence", "questions"}
    assert all(v == 0 for v in proof.tables.values())
    raw = path.read_bytes()
    assert UNIQUE.encode("utf-8") not in raw
    assert NAME.encode("utf-8") not in raw
    assert not db.candidate_exists(conn, cid)
    assert db.get_candidate(conn, cid) is None

    # les autres candidats sont intacts
    o = db.get_candidate(conn, other)
    assert o is not None and "Zigzag-Nébuleuse-a91c22" in o["redacted_text"]
    assert o["analysis"] is not None and len(o["questions"]) == 1


def test_journal_sans_nom_ni_texte(env):
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    proof = erase_candidate(conn, cid, db_path=path)
    rows = conn.execute("SELECT candidate_id_hash, erased_at, proof_json FROM erasure_log").fetchall()
    assert len(rows) == 1
    blob = json.dumps([tuple(r) for r in rows], ensure_ascii=False)
    for forbidden in [NAME, "Ophélie", UNIQUE, "Licorne", cid]:
        assert forbidden not in blob
    import hashlib
    assert rows[0][0] == hashlib.sha256(cid.encode()).hexdigest() == proof.candidate_id_hash
    logs = db.list_erasures(conn)
    assert logs[0]["candidate_id_hash"] == proof.candidate_id_hash
    assert logs[0]["verified"] is True
    # le nom ne réapparaît pas dans le fichier via le journal
    assert NAME.encode("utf-8") not in path.read_bytes()


def test_id_inconnu(env):
    conn, path = env
    with pytest.raises(KeyError):
        erase_candidate(conn, "0" * 32, db_path=path)


def test_erase_candidat_sans_document(env):
    conn, path = env
    cid = db.create_candidate(conn, "fichier-inconnu.pdf")
    db.set_status(conn, cid, "unsupported", "Format non pris en charge")
    proof = erase_candidate(conn, cid, db_path=path)
    assert proof.verified and all(v == 0 for v in proof.tables.values())


def test_liste_erasures_ordre(env):
    conn, path = env
    a = _seed(conn, NAME, UNIQUE)
    b = _seed(conn, "Barnabé Lampadaire-Fictif", "Zigzag-Nébuleuse-a91c22 expert en origami quantique")
    pa = erase_candidate(conn, a, db_path=path)
    pb = erase_candidate(conn, b, db_path=path)
    hashes = [e["candidate_id_hash"] for e in db.list_erasures(conn)]
    assert hashes == [pb.candidate_id_hash, pa.candidate_id_hash]


def test_detecteur_de_fuite(env, tmp_path):
    """Le contrôle des octets bruts détecte réellement un résidu (fichier et -journal)."""
    from copilot.erase import _collect_extracts, _raw_hits
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    _seed(conn, "Barnabé Lampadaire-Fictif", "Zigzag-Nébuleuse-a91c22 expert en origami quantique")
    extracts = _collect_extracts(conn, cid, NAME)
    assert len(extracts) >= 3
    assert NAME in extracts
    text = db.get_candidate(conn, cid)["redacted_text"]
    fake = tmp_path / "fuite.db"
    fake.write_bytes(b"\x00" + text.encode("utf-8"))
    assert _raw_hits(fake, extracts) >= 3
    fake.write_bytes(b"")
    fake.with_name("fuite.db-journal").write_bytes(text.encode("utf-8"))
    assert _raw_hits(fake, extracts) >= 3
    # un extrait partagé avec un autre candidat n'est pas retenu (pas de faux positif)
    assert not any("Société Imaginaire" in e for e in extracts)


# --- Corrections après relecture -------------------------------------------------
def test_preuve_champs_v2(env):
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    proof = erase_candidate(conn, cid, db_path=path)
    assert proof.extracts_checked >= 3
    assert proof.vacuum_ok is True and proof.verified is True


def test_vacuum_echoue_preuve_quand_meme(env, monkeypatch):
    import sqlite3
    from copilot import erase as er
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    calls = []

    def boom(c):
        calls.append(1)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(er, "_vacuum", boom)
    monkeypatch.setattr(er, "VACUUM_RETRY_DELAY_S", 0.01)
    proof = erase_candidate(conn, cid, db_path=path)
    assert len(calls) == er.VACUUM_RETRIES >= 2
    assert proof.vacuum_ok is False and proof.verified is False
    assert proof.tables["candidates"] == 0
    logs = db.list_erasures(conn)
    assert logs[0]["candidate_id_hash"] == proof.candidate_id_hash
    assert logs[0]["vacuum_ok"] is False and logs[0]["verified"] is False


def test_vacuum_reussit_apres_retry(env, monkeypatch):
    import sqlite3
    from copilot import erase as er
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    real = er._vacuum
    calls = []

    def flaky(c):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        real(c)

    monkeypatch.setattr(er, "_vacuum", flaky)
    monkeypatch.setattr(er, "VACUUM_RETRY_DELAY_S", 0.01)
    proof = erase_candidate(conn, cid, db_path=path)
    assert len(calls) == 2 and proof.vacuum_ok and proof.verified


def test_chemin_reel_via_pragma(env, tmp_path):
    conn, path = env
    cid = _seed(conn, NAME, UNIQUE)
    proof = erase_candidate(conn, cid, db_path=tmp_path / "inexistant.db")
    assert proof.extracts_checked >= 3 and proof.verified


def test_base_sans_fichier_erreur():
    import sqlite3
    c = sqlite3.connect(":memory:", isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    db.init(c)
    cid = db.create_candidate(c, NAME)
    db.save_document(c, cid, RedactResult(text=UNIQUE, removed={}))
    with pytest.raises((FileNotFoundError, RuntimeError)):
        erase_candidate(c, cid)
    assert db.candidate_exists(c, cid)          # rien n'a été effacé à l'aveugle


def test_doublon_exact_non_verifiable(env):
    conn, path = env
    a = _seed(conn, NAME, UNIQUE)
    b = _seed(conn, NAME, UNIQUE)               # même CV importé deux fois
    proof = erase_candidate(conn, a, db_path=path)
    assert proof.tables["candidates"] == 0
    assert proof.extracts_checked == 0
    assert proof.verified is False              # honnête : impossible de prouver par les octets
    assert db.candidate_exists(conn, b)


def test_doublon_partiel_garde_extraits_uniques(env):
    conn, path = env
    a = _seed(conn, NAME, UNIQUE)
    _seed(conn, "Autre Personne-Fictive", UNIQUE)    # même contenu, nom différent
    proof = erase_candidate(conn, a, db_path=path)
    assert proof.extracts_checked >= 1 and proof.verified is True


def test_document_sans_extrait_verifiable(env):
    conn, path = env
    cid = db.create_candidate(conn, "cv.pdf")
    db.save_document(conn, cid, RedactResult(text="court", removed={}))
    proof = erase_candidate(conn, cid, db_path=path)
    assert proof.verified is False             # seul le nom de fichier est vérifiable : insuffisant
