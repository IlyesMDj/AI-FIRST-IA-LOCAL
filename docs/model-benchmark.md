# Model benchmark

## Method

The benchmark is in `backend/app/services/benchmark.py`. Run it from **AI settings → Model benchmark**, or with `POST /api/benchmark/run {"models": [...]}`. Results are saved to `data/benchmarks/<timestamp>_<model>.json`.

Dataset: `backend/app/demo/synthetic.py`, with 4 fictitious CVs (2 FR, 2 EN, one with a prompt-injection attempt, one with deliberately sensitive data) and 7 job-matching cases with expected statuses. Each model runs **alone** (others unloaded), at `num_ctx=8192`, temperature 0.1, with the same prompts as production.

| Metric | Definition |
|---|---|
| Extraction accuracy | Share of expected skills, employers and schools found (whole-word match) |
| French accuracy | Same, on French CVs only |
| JSON first-try rate | Calls whose output validated against the schema without repair |
| Matching accuracy | Criterion status equals the expected one (e.g. Kubernetes → not found) |
| Summary OK | Summary present, in the CV's language, ≤ 4 sentences |
| Hallucination probes | Skills deliberately absent from a CV (e.g. Java, Kubernetes, React) that were extracted anyway |
| Unverifiable items | Extracted items whose evidence is not found in the CV text |
| Latency | Mean seconds per CV extraction and per criterion (model already loaded) |
| Memory | Model size and share in VRAM (Ollama `/api/ps`), VRAM used (nvidia-smi), free system RAM |

## Results — 2026-11-06, Ryzen 9 8945HS / RTX 4070 Laptop 8 GB / 16 GB RAM

| Metric | **qwen3:8b** | qwen2.5:7b | mistral-nemo 12B |
|---|---|---|---|
| Extraction accuracy | **94.9 %** | 76.9 % | 76.9 % |
| French accuracy | **100 %** | 78.9 % | 84.2 % |
| Valid JSON first try | 100 % | 100 % | 100 % |
| Job matching accuracy | 100 % | 100 % | 100 % |
| Summaries OK | 100 % | 100 % | 50 % |
| Hallucinated probe skills | 0 % | 0 % | 0 % |
| Unverifiable items | 0 % | 0 % | 0 % |
| Extraction time / CV | 17.9 s | **16.9 s** | 40.0 s |
| Time / criterion | 2.5 s | **2.3 s** | 6.6 s |
| Model in memory | 5.8 GB | 4.7 GB | 8.0 GB |
| Share on GPU | 100 % | 100 % | **73 %** (CPU offload) |
| VRAM used (total) | 6.1 GB | 4.9 GB | 6.2 GB |
| Sensitive data leaked into profile | none | none | none |

No sensitive marker (birth date, children, address, nationality) appeared in any profile: redaction happens before the model sees the text.

## Recommendation

- **Primary: `qwen3:8b`** (default). Best accuracy, especially in French, and it fits fully in 8 GB VRAM. Thinking mode is disabled (`think: false`) for fast, deterministic structured output.
- **Fallback: `qwen2.5:7b`**. Slightly faster and lighter (useful when RAM/VRAM is tight), but misses more items.
- **Not recommended on this machine: `mistral-nemo` 12B**. 27 % of the model is offloaded to the CPU, making it 2–3× slower with lower accuracy, and half of its summaries were not in the CV's language.
- Cold start (first load) adds ≈10 s. Keep-alive 10 min avoids reloads during a session.

## Caveats

- Small synthetic dataset: these numbers compare models on this machine; they are not absolute quality measures. Re-run after any prompt change (`PROMPT_VERSION`).
- During the run, free system RAM dropped to ≈0.9–2 GB because other applications were open. The RAM floor (600 MB) prevented swapping.
- Earlier runs counted "Java" as hallucinated when "JavaScript" was extracted (substring match). The matcher now uses whole words. Results above are from the corrected run.
