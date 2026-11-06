"""FastAPI application entry point.

Run (dev):  uvicorn app.main:app --host 127.0.0.1 --port 8000
The server binds to loopback by default: it is not reachable from the network.
"""
from __future__ import annotations

import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.i18n import get_lang, tr
from app.llm.ollama_client import OllamaError


def configure_logging() -> None:
    s = get_settings()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root = logging.getLogger()
    root.setLevel(s.log_level)
    target = str((s.logs_dir / "app.log").resolve())
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler) and h.baseFilename != target:
            root.removeHandler(h)
            h.close()
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        fh = logging.handlers.RotatingFileHandler(target, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    # httpx logs full URLs at INFO; keep it quiet (no personal data is in URLs, but less noise)
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging()
    init_engine(f"sqlite:///{s.db_path.as_posix()}")
    from app.worker import worker

    if s.start_worker:
        worker.start()
    yield
    worker.stop()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Recruiter Copilot Local", version="1.0.0", lifespan=lifespan,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.allowed_origins, allow_methods=["*"], allow_headers=["*"], allow_credentials=False
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if request.url.path.startswith("/api/") and "Cache-Control" not in resp.headers:
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(OllamaError)
    async def ollama_error_handler(request: Request, exc: OllamaError):
        return JSONResponse(status_code=503, content={"detail": tr(exc.user_message, get_lang(request)), "code": exc.code})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": tr(exc.detail, get_lang(request))},
                            headers=getattr(exc, "headers", None))

    from app.api import assistant, benchmark, candidates, jobs, privacy, system

    app.include_router(system.router)
    app.include_router(candidates.router)
    app.include_router(candidates.deletion_router)
    app.include_router(jobs.router)
    app.include_router(jobs.analysis_router)
    app.include_router(assistant.router)
    app.include_router(privacy.router)
    app.include_router(benchmark.router)
    return app


app = create_app()
