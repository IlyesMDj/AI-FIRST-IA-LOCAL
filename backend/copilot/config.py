"""Configuration. Tout est local : aucune URL hors de la machine."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # dossier hackathon/
DATA_DIR = ROOT / "data"                            # base SQLite (hors du contexte de l'assistant de code)
DB_PATH = DATA_DIR / "copilot.db"
KIT_DIR = ROOT / "kit"                              # kit du soir (cv/ jamais lu par l'assistant de code)
JOB_FILE_CANDIDATES = [KIT_DIR / "fiche-de-poste.md", ROOT / "backend" / "fixtures" / "fiche-de-poste-demo.md"]

OLLAMA_URL = "http://127.0.0.1:11434"
MODELS = {
    "rapide": "ministral-3:3b",
    "precis": "ministral-3:8b",
}
DEFAULT_MODEL = "rapide"
LLM_TIMEOUT_S = 600
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
