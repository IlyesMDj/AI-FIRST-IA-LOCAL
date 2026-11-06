import time
from pathlib import Path

import pytest

from copilot import config, criteria, llm
from copilot.types import Criterion

FIX = Path(__file__).resolve().parents[1] / "fixtures"
DEMO = FIX / "fiche-de-poste-demo.md"


def test_default_criteria_valid():
    d = criteria.DEFAULT_CRITERIA
    assert 4 <= len(d) <= 8
    assert [c.id for c in d] == [f"C{i}" for i in range(1, len(d) + 1)]
    assert all(isinstance(c, Criterion) for c in d)


def test_load_job_text_uses_first_existing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "JOB_FILE_CANDIDATES", [tmp_path / "absent.md", DEMO])
    title, text = criteria.load_job_text()
    assert title.startswith("Développeur·se Python confirmé·e")
    assert "Atelier Nova" in text


def test_load_job_text_cp1252_fallback(monkeypatch, tmp_path):
    p = tmp_path / "f.md"
    p.write_bytes("Poste : Développeur\nTexte é".encode("cp1252"))
    monkeypatch.setattr(config, "JOB_FILE_CANDIDATES", [p])
    title, text = criteria.load_job_text()
    assert title == "Poste : Développeur" and "é" in text


def test_load_job_text_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "JOB_FILE_CANDIDATES", [tmp_path / "x.md"])
    with pytest.raises(FileNotFoundError):
        criteria.load_job_text()


def _items(n):
    return [{"label": f"Critère {i}", "description": f"desc {i}"} for i in range(n)]


def test_suggest_criteria_ids_and_filtering(monkeypatch):
    out = {"criteria": [
        {"label": "Python", "description": "4 ans"},
        {"label": "Âge inférieur à 35 ans", "description": ""},       # discriminatoire -> écarté
        {"label": "python", "description": "doublon"},                 # doublon -> écarté
        {"label": "SQL"}, {"label": "Docker", "description": "ok"},
        {"label": "x" * 200},                                          # invalide -> écarté
        {"label": "Nationalité française", "description": ""},        # écarté
        {"label": "Anglais technique", "description": "écrit"},
    ]}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: out)
    cs = criteria.suggest_criteria(DEMO.read_text(encoding="utf-8"), "rapide")
    assert [c.label for c in cs] == ["Python", "SQL", "Docker", "Anglais technique"]
    assert [c.id for c in cs] == ["C1", "C2", "C3", "C4"]


def test_suggest_criteria_caps_at_8(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"criteria": _items(12)})
    assert len(criteria.suggest_criteria("fiche", "rapide")) == 8


def test_suggest_criteria_retry_then_error(monkeypatch):
    calls = []

    def fake(*a, **k):
        calls.append(1)
        return {"criteria": _items(2)}
    monkeypatch.setattr(llm, "chat_json", fake)
    with pytest.raises(llm.LLMError):
        criteria.suggest_criteria("fiche", "rapide")
    assert len(calls) == 2


def test_raw_schema_bounds():
    s = criteria.raw_schema()
    c = s["properties"]["criteria"]
    assert c["minItems"] == 4 and c["maxItems"] == 8
    assert "$ref" not in str(s)


@pytest.mark.llm
def test_real_suggest_criteria():
    t0 = time.time()
    cs = criteria.suggest_criteria(DEMO.read_text(encoding="utf-8"), "rapide")
    print(f"\n{time.time() - t0:.1f}s {llm.last_stats} -> {[c.label for c in cs]}")
    assert 4 <= len(cs) <= 8


# --- Corrections relecture : critères discriminatoires -----------------------------------

def C(label, description=""):
    return Criterion(id="C1", label=label, description=description)


@pytest.mark.parametrize("label", [
    "Âge inférieur à 35 ans", "Moins de 30 ans", "Jeune diplômé", "Jeunes talents", "Anglais natif",
    "Français langue maternelle", "Native English speaker", "Culture fit", "Bon fit avec l'équipe",
    "Personnalité affirmée", "Gender balance", "Sexe", "Nationalité française", "Origine ethnique",
    "Religion", "Bonne santé", "Situation familiale stable", "Célibataire", "Photo professionnelle",
    "Belle présentation", "Under 30",
])
def test_criterion_rejected(label):
    c = C(label)
    assert criteria.is_discriminatory(c), label
    assert criteria.criterion_warning(c).startswith("Critère discriminatoire")


@pytest.mark.parametrize("label", [
    "Expérience en santé (secteur)", "Éducation des jeunes enfants", "Esprit dynamique",
    "Interface homme-machine", "Secteur du handicap",
])
def test_criterion_ambiguous_warns_not_rejected(label):
    c = C(label)
    assert not criteria.is_discriminatory(c), label
    assert criteria.criterion_warning(c).startswith("À vérifier")


@pytest.mark.parametrize("label,desc", [
    ("Doctorat en physique", ""), ("Python en production (4 ans et plus)", "Expérience Python en production."),
    ("Au moins 4 ans d'expérience Python", ""), ("Moins de 2 ans d'expérience acceptés", ""),
    ("SQL et PostgreSQL", ""), ("Anglais technique", "Lecture de documentation."), ("Photoshop", ""),
    ("Mentorat / encadrement", ""),
])
def test_criterion_clean(label, desc):
    assert criteria.criterion_warning(C(label, desc)) is None


def test_default_and_fixture_criteria_clean():
    import json
    fx = [Criterion(**c) for c in json.loads((FIX / "b_criteres.json").read_text(encoding="utf-8"))]
    for c in criteria.DEFAULT_CRITERIA + fx:
        assert criteria.criterion_warning(c) is None, c.label


def test_suggest_rejects_hard_keeps_ambiguous(monkeypatch):
    out = {"criteria": [
        {"label": "Python"}, {"label": "Culture fit"}, {"label": "Anglais natif"},
        {"label": "Expérience en santé (secteur)"}, {"label": "SQL"}, {"label": "Docker"},
    ]}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: out)
    labels = [c.label for c in criteria.suggest_criteria("fiche", "rapide")]
    assert labels == ["Python", "Expérience en santé (secteur)", "SQL", "Docker"]
