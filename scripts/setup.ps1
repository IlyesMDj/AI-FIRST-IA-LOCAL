# One-time setup (needs internet ONLY for this step).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$root = Split-Path -Parent $PSScriptRoot
$env:NEXT_TELEMETRY_DISABLED = "1"
Set-Location "$root\backend"
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements-dev.txt
Set-Location "$root\frontend"
npm install --no-audit --no-fund
npx next telemetry disable
npm run build
Write-Host "Setup complete. Run scripts\start.ps1"
