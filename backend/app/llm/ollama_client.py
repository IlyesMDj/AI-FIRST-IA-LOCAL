"""Minimal, typed Ollama REST client.

Privacy guard: the client refuses any base URL whose host is not in the
configured allow-list (loopback by default). This makes it impossible to
point the application at a remote inference provider by configuration
mistake.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaError(Exception):
    """Base error. ``user_message`` is safe to show in the UI."""

    code = "ollama_error"

    def __init__(self, user_message: str, *, detail: str | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class OllamaUnavailable(OllamaError):
    code = "ollama_unavailable"


class ModelUnavailable(OllamaError):
    code = "model_unavailable"


class OllamaTimeout(OllamaError):
    code = "inference_timeout"


class InsufficientResources(OllamaError):
    code = "insufficient_resources"


class InvalidModelResponse(OllamaError):
    code = "invalid_model_response"


class EndpointNotAllowed(OllamaError):
    code = "endpoint_not_allowed"


def check_endpoint_allowed(url: str, allowed_hosts: list[str]) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in {h.lower() for h in allowed_hosts}:
        raise EndpointNotAllowed(
            f"The AI endpoint '{host}' is not a local host. Only local inference is allowed.",
        )


def strip_thinking(text: str) -> str:
    return _THINK_RE.sub("", text).strip()


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        *,
        allowed_hosts: list[str],
        timeout_s: float = 300.0,
        connect_timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        check_endpoint_allowed(base_url, allowed_hosts)
        self.base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_s, connect=connect_timeout_s)
        self._client = httpx.Client(
            base_url=self.base_url, timeout=self._timeout, transport=transport, trust_env=False
        )
        self._capabilities: dict[str, list[str]] = {}

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ utils
    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kw)
        except httpx.ConnectError as e:
            raise OllamaUnavailable(
                "Cannot reach the local AI engine (Ollama). Make sure Ollama is running.",
                detail=str(e),
            ) from e
        except httpx.TimeoutException as e:
            raise OllamaTimeout(
                "The local AI engine did not answer in time. Try again, reduce the context size "
                "or choose a smaller model in AI settings.",
                detail=str(e),
            ) from e
        except httpx.HTTPError as e:
            raise OllamaUnavailable("Communication error with the local AI engine.", detail=str(e)) from e
        if resp.status_code == 404:
            raise ModelUnavailable(
                "The selected model is not installed in Ollama. Choose another model in AI settings.",
                detail=resp.text[:300],
            )
        if resp.status_code >= 400:
            msg = resp.text[:300]
            if "memory" in msg.lower():
                raise InsufficientResources(
                    "Not enough memory to load the model. Close other applications or select a smaller model.",
                    detail=msg,
                )
            raise OllamaError("The local AI engine returned an error.", detail=msg)
        return resp

    # --------------------------------------------------------------- metadata
    def version(self) -> str:
        return self._request("GET", "/api/version").json().get("version", "unknown")

    def list_models(self) -> list[dict[str, Any]]:
        models = self._request("GET", "/api/tags").json().get("models", [])
        for m in models:
            if "capabilities" in m:
                self._capabilities[m["name"]] = m["capabilities"]
        return models

    def running_models(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/ps").json().get("models", [])

    def capabilities(self, model: str) -> list[str]:
        if model not in self._capabilities:
            try:
                data = self._request("POST", "/api/show", json={"model": model}).json()
                self._capabilities[model] = data.get("capabilities", [])
            except ModelUnavailable:
                raise
            except OllamaError:
                return []
        return self._capabilities.get(model, [])

    def ensure_model(self, model: str) -> None:
        names = {m["name"] for m in self.list_models()}
        if model not in names and f"{model}:latest" not in names:
            raise ModelUnavailable(
                f"The model '{model}' is not installed in Ollama. Installed models: "
                f"{', '.join(sorted(names)) or 'none'}. Select one of them in AI settings "
                f"(models are never downloaded automatically)."
            )

    # -------------------------------------------------------------- inference
    def _chat_payload(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        fmt: dict | str | None,
        options: dict[str, Any] | None,
        keep_alive: str | int | None,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if fmt is not None:
            payload["format"] = fmt
        if options:
            payload["options"] = options
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        if "thinking" in self.capabilities(model):
            payload["think"] = False  # deterministic, faster structured output
        return payload

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        fmt: dict | str | None = None,
        options: dict[str, Any] | None = None,
        keep_alive: str | int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        payload = self._chat_payload(model, messages, fmt=fmt, options=options, keep_alive=keep_alive, stream=False)
        data = self._request("POST", "/api/chat", json=payload).json()
        content = strip_thinking(data.get("message", {}).get("content", ""))
        stats = {
            k: data.get(k)
            for k in ("total_duration", "load_duration", "prompt_eval_count", "eval_count", "eval_duration")
        }
        return content, stats

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        options: dict[str, Any] | None = None,
        keep_alive: str | int | None = None,
    ) -> Iterator[str]:
        payload = self._chat_payload(model, messages, fmt=None, options=options, keep_alive=keep_alive, stream=True)
        try:
            with self._client.stream("POST", "/api/chat", json=payload) as resp:
                if resp.status_code == 404:
                    raise ModelUnavailable("The selected model is not installed in Ollama.")
                if resp.status_code >= 400:
                    resp.read()
                    raise OllamaError("The local AI engine returned an error.", detail=resp.text[:300])
                in_think = False
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaError("The local AI engine returned an error.", detail=chunk["error"])
                    piece = chunk.get("message", {}).get("content", "")
                    # defensive: hide <think> blocks if a model emits them anyway
                    if "<think>" in piece:
                        in_think = True
                    if in_think:
                        if "</think>" in piece:
                            in_think = False
                            piece = piece.split("</think>", 1)[1]
                        else:
                            continue
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as e:
            raise OllamaUnavailable("Cannot reach the local AI engine (Ollama).", detail=str(e)) from e
        except httpx.TimeoutException as e:
            raise OllamaTimeout("The local AI engine did not answer in time.", detail=str(e)) from e

    def embed(self, model: str, inputs: list[str], keep_alive: str | int | None = None) -> list[list[float]]:
        payload: dict[str, Any] = {"model": model, "input": inputs}
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive
        data = self._request("POST", "/api/embed", json=payload).json()
        embs = data.get("embeddings")
        if not isinstance(embs, list) or len(embs) != len(inputs):
            raise InvalidModelResponse("The embedding model returned an unexpected response.")
        return embs

    def unload(self, model: str) -> None:
        """Ask Ollama to free the model from memory (keep_alive=0)."""
        try:
            if "embedding" in self.capabilities(model):
                self._request("POST", "/api/embed", json={"model": model, "input": [], "keep_alive": 0})
            else:
                self._request("POST", "/api/chat", json={"model": model, "messages": [], "keep_alive": 0})
        except OllamaError as e:
            log.warning("unload failed model=%s code=%s", model, e.code)

    def load(self, model: str, keep_alive: str | int | None = None) -> None:
        """Pre-load a model (empty request)."""
        if "embedding" in self.capabilities(model):
            self._request("POST", "/api/embed", json={"model": model, "input": [], "keep_alive": keep_alive or "10m"})
        else:
            self._request("POST", "/api/chat", json={"model": model, "messages": [], "keep_alive": keep_alive or "10m"})
