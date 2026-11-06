# CLAUDE.md – Recruiter Copilot Local

Guidance for AI coding agents working on this repository.

## Règles du hackathon (from `main`, still apply)

- **Aucun CV vers une IA distante.** Le seul modèle appelé est Ollama sur `http://127.0.0.1:11434`. Jamais de modèle `-cloud` (set `OLLAMA_NO_CLOUD=1`).
- **Claude Code est une IA distante.** Ne lis jamais `data/` : CV, base, index, exports (blocked by `.claude/settings.json`). Pour tester, utilise des CV fictifs (`samples/`, `backend/app/demo/synthetic.py`).
- **Minimisation.** N'extraire que ce qui sert au poste. Jamais l'adresse, la date de naissance, l'âge, la photo ou la situation familiale.
- **La décision reste humaine.** Critères visibles tirés de la fiche de poste ; faits du CV séparés des interprétations du modèle.
- **Supprimer efface tout** : fichier original, lignes SQLite (`PRAGMA secure_delete = ON`), index, conversations, caches.
- Avant la démo : lancer le sous-agent `privacy-auditor`, puis couper le réseau et dérouler import → réponse utile → suppression → carte des flux → registre.

Stack on this branch: FastAPI backend (`backend/`) + Next.js UI (`frontend/`), default model `qwen3:8b` (see `docs/model-benchmark.md`; any installed Ollama model can be selected in AI settings). The Streamlit starter files from `main` are kept but not used.

## Non-negotiable rules

- **Never read, open, print, upload or commit real CVs or candidate data.** Use only `backend/app/demo/synthetic.py` and the generated files at the top level of `demo_data/`. Do not open `data/` (runtime candidate data), `demo_data/kit/` or `images/` (provided externally, may contain real CVs) unless the user confirms the content is synthetic.
- No external AI/inference provider, analytics, telemetry or cloud SDK. All inference goes through `app/llm/gateway.py` → Ollama on a loopback host.
- No feature may compute a candidate score, ranking, winner, shortlist, or hire/reject recommendation.
- LLM output must never reach the DB without Pydantic validation (`LLMGateway.generate_structured`) and evidence verification (`services/evidence.py`).
- Logs and `LifecycleEvent.details` must not contain personal data (ids, counts, model names, durations only).
- Any new table holding candidate-derived data needs `candidate_id` with `ON DELETE CASCADE` **and** must be added to `services/deletion.py` (explicit delete + verification count) and to the deletion tests.

## Layout

- `backend/app/llm/` – Ollama client (loopback guard), gateway (global inference lock, RAM check, structured output + repair), prompts (injection-resistant, nonce delimiters).
- `backend/app/services/` – documents (PDF/DOCX/TXT, OCR fallback), privacy (redaction, injection detection), candidates (pipeline), analysis, interview, assistant, vector_store (SQLite BLOB vectors, candidate-scoped search), deletion, benchmark, hardware.
- `backend/app/api/` – FastAPI routers under `/api`.
- `backend/app/worker.py` – single background worker (sequential inference).
- `frontend/app/` – Next.js App Router pages; `frontend/components/ui` vendored shadcn-style primitives; API proxied via `next.config.mjs` rewrites.

## Commands

```powershell
cd backend; .\.venv\Scripts\python -m pytest              # must stay green
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend; npm run typecheck; npm run build; npx next start -p 3000 -H 127.0.0.1
```

Real-model integration test: `RCL_TEST_OLLAMA=1 pytest tests/test_ollama_integration.py -s`.

## Conventions

- Python 3.12, type hints, Pydantic v2, SQLAlchemy 2 typed ORM. User-facing error messages live in exceptions' `user_message`.
- Frontend: TypeScript strict, Tailwind tokens from `app/globals.css` (light + dark), no technical jargon in recruiter-facing text.
- React 19 + recent Chrome: `useEffect` callbacks must use a block body (`() => { ... }`) – `scrollIntoView()` now returns a Promise, and an expression body would hand it to React as a cleanup function.
- **i18n (FR/EN)**: UI strings are English source strings wrapped in `t("…")` (`useI18n()`), or `N_("…")` in constant tables; French goes in `frontend/lib/i18n-fr.ts`. `npm run check:i18n` must report 0 missing. Backend user-facing messages stay in English in code and need a French entry in `backend/app/i18n.py` (`tests/test_i18n.py` fails otherwise); they are translated at response time from the `X-Lang` header.
- Bump `PROMPT_VERSION` in `app/llm/prompts.py` when prompts change.
