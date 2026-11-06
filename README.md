# Recruiter Copilot Local

A local AI recruitment assistant. CVs, extracted data, embeddings and prompts **never leave the computer**: inference runs on [Ollama](https://ollama.com) on `127.0.0.1`, data lives in `./data`.

The AI **assists** the recruiter. It never ranks candidates, scores them, rejects them or recommends a hire.

Projet du hackathon AI First × 42 Paris, édition 11 ([brief](https://ai-first-42-recruiter-copilot.trybailey.app/)). Branch `recruiter-copilot-local`: FastAPI + Next.js implementation (the Streamlit starter on `main` is kept untouched: `.streamlit/`, `samples/`, `scripts/check_local.py`, root `requirements.txt`).

## ⚠️ Dépôt public : aucune donnée candidat
- Runtime data (CVs, database, vectors, logs) lives in `data/`, which is git-ignored: never force it with `git add -f`. The provided CV kit (`demo_data/kit/`) is git-ignored too.
- Before every push, `git status` must list no CV and no database.
- Never let a remote AI agent (Claude Code, Cursor, Copilot…) read `data/`. For Claude Code it is blocked by `.claude/settings.json`.
- Use the **privacy-auditor** sub-agent (`.claude/agents/`) before the demo.

## What it does

| Area | Features |
|---|---|
| Import | Multi-file upload (PDF, scanned PDF via local OCR, DOCX, TXT), preview before import, type/size validation, SHA-256 duplicate refusal, "possible duplicate" flags (e-mail, name+phone) that are never merged automatically, processing states (Imported → Waiting → Processing → Completed / Failed) |
| Minimisation | Birth date, age, family status, nationality, gender, religion, health, social-security number and home address are **removed before storage and before the AI sees the text** |
| Extraction | Strict Pydantic schema sent to Ollama as a JSON-schema constraint, controlled repair loop, explicit vs inferred items, **every item checked against the CV text** (verified / unverified), confidence = verified-evidence ratio |
| Jobs | Title, description, required/optional skills, experience, education, languages, responsibilities, custom criteria |
| Analysis | Per-criterion status *Clearly demonstrated / Partially demonstrated / Not found in the CV / Cannot be determined*, verbatim evidence with source section, relevant experience, missing information. Unverifiable "demonstrated" claims are automatically downgraded. **No score.** |
| Assistant | Streaming chat over one or several candidates, semantic + keyword retrieval (nomic-embed-text), citations `[C1-3]`, strict candidate isolation |
| Comparison | Side-by-side evidence matrix per criterion, skills, experience, projects, education. **No winner.** |
| Interview | Questions by category (technical, experience, project, problem solving, clarification) with why/competency/CV evidence; discriminatory questions are filtered |
| Deletion | One transaction + file overwrite/removal + WAL checkpoint + **verification report** (DB, files, search, API) |
| Privacy center | Data inventory, data-flow diagram, deletion reports, processing register |
| AI settings | Model choice (installed models only), context, temperature, keep-alive, load/unload, live RAM/VRAM |
| Benchmark | Fixed synthetic dataset; accuracy, French, JSON compliance, matching, hallucination, latency, VRAM |
| Export | Analyses & interview plans as Markdown, print view |
| Languages | Full **French / English** interface (FR/EN switch in the header, defaults to the browser language). Backend messages and warnings are translated too. AI answers follow the language of the CV or of the question |

## Quick start (Windows)

Prerequisites: Python 3.12, Node 20+, Ollama running with `qwen3:8b` and `nomic-embed-text` installed.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   # once (needs internet)
powershell -ExecutionPolicy Bypass -File scripts\start.ps1   # then, offline is fine
```

Open http://127.0.0.1:3000. To load synthetic demo data: `cd backend; .\.venv\Scripts\python -m app.demo.seed`.

Manual steps, Docker and troubleshooting: [docs/installation.md](docs/installation.md).

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest                          # 40 tests, fake Ollama, no network
$env:RCL_TEST_OLLAMA="1"; .\.venv\Scripts\python -m pytest tests/test_ollama_integration.py -s   # real Ollama
cd ..\frontend; npm run typecheck; npm run check:i18n; npm run build
```

Test suites: `test_functional.py` (import, extraction, JSON validation, jobs, analysis, assistant, comparison, interview, deletion), `test_privacy.py` (offline run with sockets blocked, local-only endpoint, no telemetry, no CV content in logs, redaction, injection, isolation, deletion of files/embeddings/retrieval, raw DB file scan), `test_reliability.py` (Ollama down, model missing, invalid model output, timeout, malformed PDF, scanned PDF/OCR, zip bomb, large CV, insufficient RAM, deletion during processing).

## Documentation

- [Architecture & roadmap](docs/architecture.md)
- [Installation](docs/installation.md) · [Ollama configuration](docs/ollama-configuration.md) · [Model benchmark](docs/model-benchmark.md)
- [Privacy by design](docs/privacy-by-design.md) · [Data lifecycle](docs/data-lifecycle.md) · [Security](docs/security.md) · [Known limitations](docs/known-limitations.md)
- [Registre simplifié](docs/data/registre-simplifie.md) · [Data flow](docs/data/data-flow.md)

## Repository layout

```
backend/   FastAPI app (app/), tests (tests/), requirements
frontend/  Next.js 15 + Tailwind + shadcn-style components
docs/      documentation
demo_data/ synthetic CVs (fictitious people only)
scripts/   Windows setup / start scripts
data/      created at runtime – candidate data, NEVER committed
```

Only synthetic data is used for development and demonstrations. `data/`, `.env`, databases and any CV files outside the generated demo set are git-ignored.
