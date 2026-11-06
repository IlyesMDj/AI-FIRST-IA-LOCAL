"""Unit tests for pure helpers."""
from app.services.benchmark import _contains
from app.services.documents import detect_sections, sanitize_filename
from app.services.evidence import find_quote, normalise
from app.schemas.llm import CVExtraction


def test_benchmark_word_matching():
    assert not _contains(["JavaScript"], "Java")
    assert _contains(["Apache Airflow"], "Airflow")


def test_evidence_matching_tolerates_case_accents_punctuation():
    src = normalise("Développeuse Backend Senior — Société Alpha Données (2021-03)")
    assert find_quote(src, "developpeuse backend senior, societe alpha donnees").status == "verified"
    assert find_quote(src, "Lead engineer at Google").status == "not_found"


def test_schema_normalises_llm_values():
    obj = CVExtraction.model_validate({
        "candidate_name": "null",
        "experience": [{"position": "Dev", "start_date": "03/2021", "end_date": "aujourd'hui"}],
        "education": [{"degree": "Master", "graduation_year": "en 2018"}],
    })
    assert obj.candidate_name is None
    assert obj.experience[0].end_date == "present"
    assert obj.education[0].graduation_year == 2018


def test_sections_and_filenames():
    secs = detect_sections("Jane Doe\nExpérience\nDev chez X\nFormation\nMaster")
    assert [s["name"] for s in secs] == ["header", "experience", "education"]
    assert sanitize_filename("..\..\C:/évil<>.pdf") == "evil_.pdf"
