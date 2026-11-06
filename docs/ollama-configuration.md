# Ollama configuration

## Endpoint and privacy guard

The backend talks to Ollama through `app/llm/ollama_client.py` only. The client **refuses** any `RCL_OLLAMA_URL` whose host is not in `RCL_ALLOWED_OLLAMA_HOSTS` (default: `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `ollama`). A remote inference URL cannot be configured by mistake. `httpx` is created with `trust_env=False`, so system proxy variables are ignored.

Endpoints used: `/api/version`, `/api/tags`, `/api/ps`, `/api/show`, `/api/chat`, `/api/embed`. **`/api/pull` is never called.**

## Model roles (inspected on the target machine)

| Model | Size / quant | Role | Fits 8 GB VRAM? |
|---|---|---|---|
| `qwen3:8b` | 8.2B Q4_K_M, 5.2 GB | **Primary**: extraction, analysis, interview, chat (thinking disabled with `think: false`) | Yes, 100 % GPU at 8k ctx (≈6.4 GB) |
| `qwen2.5:7b` | 7.6B Q4_K_M, 4.7 GB | Secondary: faster, strong JSON | Yes |
| `mistral-nemo:latest` | 12.2B Q4_0, 7.1 GB | Alternative (good French) | **Partially**: spills to CPU at 8k ctx, slower |
| `nomic-embed-text:latest` | 137M F16 | Embeddings (768-d) with `search_document:` / `search_query:` prefixes | Yes (≈0.3 GB, coexists with the LLM) |
| `moondream:latest` | 1B, vision | Optional image understanding; not used in the main pipeline (photos are deliberately not processed) | Yes |
| `hermes3:8b`, `llama3.x` | | Not configured by default; can be selected and benchmarked | Yes |

Measured benchmark numbers: [model-benchmark.md](model-benchmark.md).

## Hardware-aware behaviour (RTX 4070 Laptop 8 GB / 16 GB RAM)

| Mechanism | Where | Effect |
|---|---|---|
| Global inference lock | `gateway.INFERENCE_LOCK` | One model call at a time: chat, worker and benchmark never run inference in parallel |
| Single worker thread | `app/worker.py` | Imports and analyses are queued and processed sequentially |
| Unload other LLMs before loading | `LLMGateway.prepare_model` | Never two large chat models in VRAM; the small embedding model may coexist |
| RAM floor | `RCL_MIN_FREE_RAM_MB` (600) | Refuses to *load* a model when RAM is too low, with a clear message, instead of swapping or crashing |
| Bounded context | `num_ctx` 8192 by default | ≈1.2 GB of KV cache for qwen3:8b; long CVs are truncated with a visible warning |
| Bounded output | `num_predict` per task (700 per criterion, 3500 for extraction) | Prevents runaway generations |
| Keep-alive | 10 min default, configurable, manual load/unload in AI settings | Avoids reload latency (≈10 s cold start) while letting VRAM free up |
| Prefix cache reuse | CV placed first in analysis prompts | Ollama reuses the KV cache across the criteria of one analysis |
| Timeouts | connect 5 s, request 300 s (configurable) | A hung model produces a "did not answer in time" error, never a frozen app |
| Monitoring | `/api/system/status` | Running models, VRAM share, RAM, GPU usage (nvidia-smi), queue |

## Generation parameters

Editable in **AI settings** (persisted in the `app_settings` table, defaults from `.env`):

- `num_ctx`: 4096–16384 (8192 recommended)
- `temperature`: 0.1 default (deterministic extraction)
- `top_p`: 0.9
- `keep_alive`: `0` (unload after each call) … `-1` (always)
- `request_timeout_s`, `max_repair_attempts`

## When a model is unavailable

- Status endpoint and dashboard show the problem and propose an installed alternative (e.g. "Select an installed model such as qwen2.5:7b").
- Processing fails for that document with a readable message. It can be re-run after fixing the setting.
- Settings refuse to save a model that is not installed.
- To install a model, the administrator runs `ollama pull <name>` explicitly (outside the application).
