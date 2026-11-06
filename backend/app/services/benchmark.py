"""Local model benchmark on the fixed synthetic dataset.

Metrics per model
- extraction_recall: expected skills / companies / institutions found
- json_first_try_rate: share of calls valid without repair (schema compliance)
- french_recall: extraction recall on French CVs only
- matching_accuracy: per-criterion status vs expected status
- summary_ok_rate: summary present, in the CV language, ≤ 4 sentences
- hallucination_rate: absent-skill probes extracted + unverifiable items
- latency: mean seconds per extraction / per criterion
- memory: model size, VRAM share (Ollama /api/ps), system RAM available,
  GPU VRAM used (nvidia-smi) after load
Results are written to data/benchmarks/<timestamp>_<model>.json.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from app.config import get_settings
from app.demo.synthetic import CVS, JOBS, MATCHING_CASES, cv_by_key
from app.llm.gateway import LLMGateway
from app.llm.ollama_client import OllamaError
from app.llm.prompts import analysis_messages, extraction_messages
from app.schemas.llm import CriterionAssessment, CVExtraction
from app.services import hardware
from app.services.analysis import postprocess_assessment
from app.services.candidates import postprocess_extraction
from app.services.documents import detect_sections
from app.services.evidence import normalise
from app.services.privacy import redact_sensitive
from app.services.settings_service import AISettings

log = logging.getLogger(__name__)

_state: dict[str, Any] = {"running": False, "progress": "", "error": None}
_lock = threading.Lock()

_FR_WORDS = {"le", "la", "les", "de", "des", "et", "en", "avec", "une", "un", "dans", "pour", "du"}
_EN_WORDS = {"the", "and", "with", "of", "in", "for", "a", "an", "to", "on"}


def _lang(text: str) -> str:
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿ]+", text.lower())
    fr = sum(w in _FR_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    return "fr" if fr >= en else "en"


def _contains(names: list[str], target: str) -> bool:
    """Whole-word match in either direction ('Airflow' ~ 'Apache Airflow',
    but 'Java' does NOT match 'JavaScript')."""
    t = f" {normalise(target).text} "
    for n in names:
        if not n:
            continue
        nn = f" {normalise(n).text} "
        if t in nn or nn in t:
            return True
    return False


def benchmark_model(model: str, ai: AISettings) -> dict[str, Any]:
    cfg = ai.model_copy(update={"active_model": model, "max_repair_attempts": 2})
    gw = LLMGateway(cfg)
    res: dict[str, Any] = {"model": model, "started_at": datetime.now(timezone.utc).isoformat(), "cases": []}
    found = expected = fr_found = fr_expected = probes_hit = probes = 0
    unverified = items = first_try = calls = summary_ok = 0
    ext_lat: list[float] = []
    try:
        for cv in CVS:
            _state["progress"] = f"{model}: extraction {cv.key}"
            text = redact_sensitive(cv.text).text
            obj, meta = gw.generate_structured(CVExtraction, extraction_messages(text), num_predict=3500)
            calls += 1
            first_try += meta["attempts"] == 1
            ext_lat.append(meta["duration_s"])
            data, conf, _ = postprocess_extraction(obj, text, detect_sections(text))
            skills = [s["name"] for s in data["skills"]]
            companies = [e.get("company") or "" for e in data["experience"]]
            insts = [e.get("institution") or "" for e in data["education"]]
            hits = sum(_contains(skills, s) for s in cv.expected_skills)
            hits += sum(_contains(companies, c) for c in cv.expected_companies)
            hits += sum(_contains(insts, i) for i in cv.expected_institutions)
            total = len(cv.expected_skills) + len(cv.expected_companies) + len(cv.expected_institutions)
            found += hits
            expected += total
            if cv.lang == "fr":
                fr_found += hits
                fr_expected += total
            hal = [a for a in cv.absent_skills if _contains(skills, a)]
            probes_hit += len(hal)
            probes += len(cv.absent_skills)
            for sec in ("skills", "experience", "education", "languages", "certifications", "projects"):
                for it in data[sec]:
                    items += 1
                    unverified += it["verification"]["status"] == "not_found"
            summ = data.get("professional_summary") or ""
            sent = len([s for s in re.split(r"[.!?]+", summ) if s.strip()])
            ok = bool(summ) and _lang(summ) == cv.lang and sent <= 4
            summary_ok += ok
            leaked = [m for m in cv.sensitive_markers if m.lower() in json.dumps(data, ensure_ascii=False).lower()]
            res["cases"].append({
                "cv": cv.key, "recall": round(hits / total, 2), "hallucinated_skills": hal,
                "confidence": conf, "summary_ok": ok, "attempts": meta["attempts"],
                "duration_s": meta["duration_s"], "sensitive_leaks": leaked,
            })
        snap_after_load = hardware.snapshot()
        running = [m for m in gw.client.running_models() if m.get("name") == model]

        match_ok = 0
        crit_lat: list[float] = []
        for key, job_idx, req, ok_set in MATCHING_CASES:
            _state["progress"] = f"{model}: matching {key} / {req}"
            cv = cv_by_key(key)
            text = redact_sensitive(cv.text).text
            job = JOBS[job_idx]
            obj, meta = gw.generate_structured(
                CriterionAssessment,
                analysis_messages(text, f"Title: {job['title']}\n{job['description']}", req, "required skill"),
                num_predict=700,
            )
            calls += 1
            first_try += meta["attempts"] == 1
            crit_lat.append(meta["duration_s"])
            out = postprocess_assessment(obj, text, detect_sections(text))
            good = out["status"] in ok_set
            match_ok += good
            res["cases"].append({"matching": f"{key} / {req}", "status": out["status"], "expected": sorted(ok_set), "ok": good})

        res["metrics"] = {
            "extraction_recall": round(found / expected, 3) if expected else None,
            "french_recall": round(fr_found / fr_expected, 3) if fr_expected else None,
            "json_first_try_rate": round(first_try / calls, 3) if calls else None,
            "matching_accuracy": round(match_ok / len(MATCHING_CASES), 3),
            "summary_ok_rate": round(summary_ok / len(CVS), 3),
            "hallucination_probe_rate": round(probes_hit / probes, 3) if probes else None,
            "unverified_item_rate": round(unverified / items, 3) if items else None,
            "mean_extraction_s": round(sum(ext_lat) / len(ext_lat), 1) if ext_lat else None,
            "mean_criterion_s": round(sum(crit_lat) / len(crit_lat), 1) if crit_lat else None,
            "model_size_mb": int(running[0]["size"] / 1048576) if running else None,
            "model_vram_mb": int(running[0].get("size_vram", 0) / 1048576) if running else None,
            "gpu_offload_pct": round(100 * running[0].get("size_vram", 0) / running[0]["size"]) if running and running[0].get("size") else None,
            "system_ram_available_mb": snap_after_load["ram_available_mb"],
            "gpu_vram_used_mb": snap_after_load["gpus"][0]["vram_used_mb"] if snap_after_load["gpus"] else None,
            "num_ctx": cfg.num_ctx,
        }
    except OllamaError as e:
        res["error"] = e.user_message
    res["finished_at"] = datetime.now(timezone.utc).isoformat()
    return res


def run_benchmark(models: list[str], ai: AISettings) -> list[dict]:
    out_dir = get_settings().benchmarks_dir
    results = []
    for m in models:
        r = benchmark_model(m, ai)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", m)
        (out_dir / f"{ts}_{safe}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(r)
        # sequential: free the model before the next one
        try:
            LLMGateway(ai).client.unload(m)
        except OllamaError:
            pass
    return results


def start_background(models: list[str], ai: AISettings) -> bool:
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, progress="starting", error=None, started=time.time())

    def _run():
        try:
            run_benchmark(models, ai)
        except Exception as e:  # noqa: BLE001
            log.exception("benchmark failed")
            _state["error"] = str(e)[:200]
        finally:
            _state.update(running=False, progress="done")

    threading.Thread(target=_run, name="rcl-benchmark", daemon=True).start()
    return True


def status() -> dict:
    return {k: v for k, v in _state.items()}


def list_results() -> list[dict]:
    out = []
    for p in sorted(get_settings().benchmarks_dir.glob("*.json"), reverse=True)[:50]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"file": p.name, "model": d.get("model"), "finished_at": d.get("finished_at"),
                        "metrics": d.get("metrics"), "error": d.get("error"), "cases": d.get("cases", [])})
        except (OSError, json.JSONDecodeError):
            continue
    return out


def ram_ok_for_benchmark() -> bool:
    return psutil.virtual_memory().available / 1048576 > get_settings().min_free_ram_mb
