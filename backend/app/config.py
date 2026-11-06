"""Application configuration.

Static settings come from environment variables prefixed with ``RCL_`` (see
``.env.example``). A small subset (AI settings) can be overridden at runtime
from the UI; those overrides are persisted in the ``app_settings`` table and
merged by :func:`app.services.settings_service.get_ai_settings`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RCL_",
        env_file=str(PROJECT_DIR / ".env"),
        extra="ignore",
    )

    # --- storage -----------------------------------------------------------
    data_dir: Path = PROJECT_DIR / "data"

    # --- Ollama ------------------------------------------------------------
    ollama_url: str = "http://localhost:11434"
    # Only these hosts may be used as inference endpoint (privacy guard).
    allowed_ollama_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"]
    )
    primary_model: str = "qwen3:8b"
    secondary_model: str = "qwen2.5:7b"
    alternative_model: str = "mistral-nemo:latest"
    embedding_model: str = "nomic-embed-text:latest"
    vision_model: str = "moondream:latest"

    # --- generation defaults (overridable in UI) ---------------------------
    num_ctx: int = 8192
    temperature: float = 0.1
    top_p: float = 0.9
    keep_alive: str = "10m"
    request_timeout_s: float = 300.0
    connect_timeout_s: float = 5.0
    max_repair_attempts: int = 2
    min_free_ram_mb: int = 600  # refuse to *load* a model below this

    # --- limits -------------------------------------------------------------
    max_upload_mb: int = 10
    max_files_per_batch: int = 50
    max_text_chars: int = 40_000  # text sent to the LLM is truncated beyond this
    max_pdf_pages: int = 30

    # --- behaviour ----------------------------------------------------------
    auto_process_on_import: bool = True
    ocr_enabled: bool = True
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    start_worker: bool = True
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "recruiter.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def benchmarks_dir(self) -> Path:
        return self.data_dir / "benchmarks"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for d in (self.db_path.parent, self.uploads_dir, self.tmp_dir, self.benchmarks_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
