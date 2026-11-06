from __future__ import annotations

import os
import queue
import socket

import pytest

os.environ["RCL_START_WORKER"] = "false"
os.environ["RCL_MIN_FREE_RAM_MB"] = "0"


@pytest.fixture
def fake():
    from tests.fake_ollama import FakeOllama

    return FakeOllama()


@pytest.fixture
def client(tmp_path, monkeypatch, fake):
    """App with an isolated data dir and the fake Ollama transport."""
    monkeypatch.setenv("RCL_DATA_DIR", str(tmp_path / "data"))
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.llm import gateway
    from app.llm.ollama_client import OllamaClient
    from app.main import create_app
    from app.worker import worker

    s = get_settings()
    gateway.set_client(OllamaClient(s.ollama_url, allowed_hosts=s.allowed_ollama_hosts, transport=fake.transport()))
    worker.q = queue.Queue()
    worker._queued.clear()
    with TestClient(create_app()) as c:
        c.fake = fake
        yield c
    gateway.set_client(None)
    get_settings.cache_clear()


@pytest.fixture
def no_network(monkeypatch):
    """Fail any real socket connection to a non-loopback address."""
    real_connect = socket.socket.connect
    attempts: list = []

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        attempts.append(host)
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise OSError(f"external network access blocked in test: {host}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    real_gai = socket.getaddrinfo

    def guarded_gai(host, *a, **kw):
        if host not in ("127.0.0.1", "::1", "localhost", None):
            attempts.append(host)
            raise OSError(f"DNS resolution blocked in test: {host}")
        return real_gai(host, *a, **kw)

    monkeypatch.setattr(socket, "getaddrinfo", guarded_gai)
    return attempts


def upload(client, files: list[tuple[str, bytes]], **data):
    return client.post(
        "/api/candidates/upload",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
        data={k: str(v).lower() for k, v in data.items()},
    )


def process_all():
    from app.worker import worker

    worker.drain()
