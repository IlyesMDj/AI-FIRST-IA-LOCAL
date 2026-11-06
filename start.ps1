# Recruiter Copilot — lance l'API locale (127.0.0.1:8000) et l'interface (127.0.0.1:5173).
# Usage : powershell -ExecutionPolicy Bypass -File .\start.ps1   [-Db chemin\vers\base.db]
param(
    [string]$Db = (Join-Path $PSScriptRoot "data\copilot.db")
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Environnement Python introuvable : $python" }

# Ollama doit tourner localement (aucun appel hors de la machine).
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 | Out-Null
} catch {
    Write-Warning "Ollama ne répond pas sur 127.0.0.1:11434 : lancez 'ollama serve' (les analyses échoueront sinon)."
}

$dbFull = [System.IO.Path]::GetFullPath($Db)
New-Item -ItemType Directory -Force -Path (Split-Path $dbFull) | Out-Null

# API : nouvelle fenêtre, base passée par COPILOT_DB. Pas de --reload (pas de surveillance de fichiers).
$apiCmd = "`$env:COPILOT_DB = '$dbFull'; Set-Location '$root\backend'; & '$python' -m uvicorn copilot.api:app --host 127.0.0.1 --port 8000"
$api = Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd -PassThru

# Front : Vite (proxy /api -> 127.0.0.1:8000).
$webCmd = "Set-Location '$root\web'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
$web = Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCmd -PassThru

Write-Host ""
Write-Host "Recruiter Copilot démarre..." -ForegroundColor Cyan
Write-Host "  Interface : http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  API       : http://127.0.0.1:8000/api/health"
Write-Host "  Base      : $dbFull"
Write-Host "Fermez les deux fenêtres PowerShell (PID $($api.Id) et $($web.Id)) pour tout arrêter."
