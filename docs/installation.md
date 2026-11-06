# Installation

Internet is needed **only once**, to install Python/Node packages. After that, the application works with the network disconnected.

## Prerequisites

| Component | Version tested | Notes |
|---|---|---|
| Windows | 11 (64-bit) | |
| Python | 3.12 | `python --version` |
| Node.js | 22 (20+ OK) | `node --version` |
| Ollama | 0.40 | running at `http://localhost:11434` |
| Models | `qwen3:8b`, `nomic-embed-text:latest` | `ollama list`. Optional: `qwen2.5:7b`, `mistral-nemo:latest` |

The application **never downloads models**. If a model is missing, the dashboard and AI settings say so and propose an installed alternative.

OCR for scanned PDFs uses `rapidocr-onnxruntime` (installed by pip, ships its own ONNX models). No Tesseract install is needed.

## Automated setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

## Manual setup

```powershell
# backend
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
copy ..\.env.example ..\.env        # optional
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# frontend (second terminal)
cd frontend
$env:NEXT_TELEMETRY_DISABLED="1"
npm install
npx next telemetry disable
npm run build        # output in .next-prod (telemetry forced off)
npm run start
```

Open http://127.0.0.1:3000. The API docs are at http://127.0.0.1:8000/api/docs.

If port 3000 is busy, use another one (`-p 3001`). CORS is not involved because the browser only talks to the Next.js server, which proxies `/api` to the backend (`BACKEND_URL`, default `http://127.0.0.1:8000`).

## Demo data (synthetic)

```powershell
cd backend
.\.venv\Scripts\python -m app.demo.seed          # imports 4 fictitious CVs + 3 jobs, runs the AI
.\.venv\Scripts\python -m app.demo.seed --no-ai  # import only
```

You can also upload the files in `demo_data/` (PDF, scanned PDF, DOCX, TXT) from the Import page.

## Docker (optional)

```powershell
docker compose up --build
```

Ollama stays on the host (`host.docker.internal:11434`) so it keeps native GPU access. Ports are published on `127.0.0.1` only, and data is mounted from `./data`.

## Verifying the offline guarantee

1. Disconnect from the network (Wi-Fi off / cable unplugged).
2. Import a demo CV, run an analysis, ask the assistant a question, delete the candidate.
3. Everything works: the only network traffic is loopback (`127.0.0.1:3000 → :8000 → :11434`).

The automated test `test_full_pipeline_offline` reproduces this by blocking every non-loopback socket and DNS lookup.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Local AI offline" | Start Ollama (`ollama serve` or the tray app) |
| "Model unavailable" | `ollama list`, then select an installed model in AI settings |
| "Only N MB of RAM available" | Close applications, or lower `RCL_MIN_FREE_RAM_MB` with care |
| Slow analysis | Use `qwen2.5:7b`, lower the context to 6144, keep the model loaded (keep-alive 10m) |
| Scanned PDF fails | Check that OCR is enabled in AI settings and `rapidocr-onnxruntime` is installed |
