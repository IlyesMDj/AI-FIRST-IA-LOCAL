"""LLM gateway: the single entry point for every model call.

Responsibilities
- sequential execution (one global inference lock → one model call at a time);
- model availability check (never downloads models);
- memory check before *loading* a model and unloading of other large LLMs;
- structured generation: JSON-schema constrained output → Pydantic validation
  → controlled repair attempts → typed error.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Iterator, TypeVar

import psutil
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.ollama_client import (
    InsufficientResources,
    InvalidModelResponse,
    OllamaClient,
)
from app.services.settings_service import AISettings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

INFERENCE_LOCK = threading.RLock()
_client: OllamaClient | None = None
_client_lock = threading.Lock()
_model_check_cache: dict[str, float] = {}


def get_client() -> OllamaClient:
    global _client
    with _client_lock:
        if _client is None:
            s = get_settings()
            _client = OllamaClient(
                s.ollama_url,
                allowed_hosts=s.allowed_ollama_hosts,
                timeout_s=s.request_timeout_s,
                connect_timeout_s=s.connect_timeout_s,
            )
        return _client


def set_client(client: OllamaClient | None) -> None:
    """Used by tests and when settings change."""
    global _client
    with _client_lock:
        if _client is not None and client is not _client:
            _client.close()
        _client = client
        _model_check_cache.clear()


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_loose(raw: str) -> Any:
    """Parse JSON, tolerating code fences and leading/trailing prose."""
    text = _FENCE_RE.sub("", raw.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _summarise_validation_error(e: Exception) -> str:
    if isinstance(e, ValidationError):
        parts = []
        for err in e.errors()[:6]:
            loc = ".".join(str(x) for x in err["loc"])
            parts.append(f"{loc}: {err['msg']}")
        return "; ".join(parts)
    return str(e)[:300]


class LLMGateway:
    def __init__(self, ai: AISettings, client: OllamaClient | None = None) -> None:
        self.ai = ai
        self.client = client or get_client()

    # ------------------------------------------------------------ resources
    def options(self, **overrides: Any) -> dict[str, Any]:
        opts = {"num_ctx": self.ai.num_ctx, "temperature": self.ai.temperature, "top_p": self.ai.top_p}
        opts.update({k: v for k, v in overrides.items() if v is not None})
        return opts

    def prepare_model(self, model: str, *, is_embedding: bool = False) -> None:
        now = time.monotonic()
        if now - _model_check_cache.get(model, 0) > 60:
            self.client.ensure_model(model)
            _model_check_cache[model] = now
        running = self.client.running_models()
        running_names = {m.get("name") for m in running}
        if model in running_names:
            return
        # Avoid holding several large LLMs: unload other chat models first.
        if not is_embedding:
            for m in running:
                name = m.get("name", "")
                if name != model and "embed" not in name:
                    log.info("unloading model=%s before loading model=%s", name, model)
                    self.client.unload(name)
        avail_mb = psutil.virtual_memory().available / 1024 / 1024
        if avail_mb < get_settings().min_free_ram_mb:
            raise InsufficientResources(
                f"Only {avail_mb:.0f} MB of RAM is available. Close other applications before running "
                f"the AI analysis, or select a smaller model in AI settings."
            )

    # ----------------------------------------------------------- generation
    def generate_structured(
        self,
        schema: type[T],
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> tuple[T, dict[str, Any]]:
        model = model or self.ai.active_model
        json_schema = schema.model_json_schema()
        convo = list(messages)
        attempts = 0
        last_error = ""
        t0 = time.perf_counter()
        stats: dict[str, Any] = {}
        with INFERENCE_LOCK:
            self.prepare_model(model)
            while attempts <= self.ai.max_repair_attempts:
                attempts += 1
                raw, stats = self.client.chat(
                    model,
                    convo,
                    fmt=json_schema,
                    options=self.options(num_predict=num_predict, num_ctx=num_ctx),
                    keep_alive=self.ai.keep_alive,
                )
                try:
                    obj = schema.model_validate(parse_json_loose(raw))
                    meta = {
                        "model": model,
                        "attempts": attempts,
                        "duration_s": round(time.perf_counter() - t0, 2),
                        "prompt_tokens": stats.get("prompt_eval_count"),
                        "output_tokens": stats.get("eval_count"),
                    }
                    return obj, meta
                except (json.JSONDecodeError, ValidationError, ValueError) as e:
                    last_error = _summarise_validation_error(e)
                    log.warning("invalid structured output attempt=%d model=%s", attempts, model)
                    convo = list(messages) + [
                        {"role": "assistant", "content": raw[:4000]},
                        {
                            "role": "user",
                            "content": (
                                "Your previous answer was not valid for the required JSON schema. "
                                f"Validation errors: {last_error}. "
                                "Return ONLY one JSON object that conforms to the schema. "
                                "Use null for unknown values. Do not add commentary."
                            ),
                        },
                    ]
        raise InvalidModelResponse(
            "The AI model returned an invalid response several times. Try again or select another model.",
            detail=last_error,
        )

    def generate_text(self, messages: list[dict[str, str]], *, model: str | None = None, num_predict: int | None = None) -> str:
        model = model or self.ai.active_model
        with INFERENCE_LOCK:
            self.prepare_model(model)
            text, _ = self.client.chat(
                model, messages, options=self.options(num_predict=num_predict), keep_alive=self.ai.keep_alive
            )
            return text

    def stream_chat(self, messages: list[dict[str, str]], *, model: str | None = None) -> Iterator[str]:
        model = model or self.ai.active_model
        with INFERENCE_LOCK:
            self.prepare_model(model)
            yield from self.client.chat_stream(
                model, messages, options=self.options(num_predict=1024), keep_alive=self.ai.keep_alive
            )

    def embed(self, texts: list[str], *, prefix: str = "search_document: ") -> list[list[float]]:
        """nomic-embed-text expects task prefixes (search_document / search_query)."""
        model = self.ai.embedding_model
        out: list[list[float]] = []
        with INFERENCE_LOCK:
            self.prepare_model(model, is_embedding=True)
            for i in range(0, len(texts), 16):
                batch = [prefix + t for t in texts[i : i + 16]]
                out.extend(self.client.embed(model, batch, keep_alive=self.ai.keep_alive))
        return out
