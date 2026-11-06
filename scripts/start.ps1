# Starts Recruiter Copilot Local (backend + frontend) in two windows.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1
$root = Split-Path -Parent $PSScriptRoot
$env:NEXT_TELEMETRY_DISABLED = "1"

try { Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 3 | Out-Null }
catch { Write-Warning "Ollama does not answer on http://localhost:11434 - start Ollama first." }

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; `$env:NEXT_TELEMETRY_DISABLED='1'; npm run start"
Start-Sleep 6
Start-Process "http://127.0.0.1:3000"
