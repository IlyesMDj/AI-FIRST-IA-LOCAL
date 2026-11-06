import pathlib
import types

import pytest

from copilot import llm

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def resp(content, **stats):
    return types.SimpleNamespace(message=types.SimpleNamespace(content=content), **stats)


class FakeClient:
    def __init__(self, result=None, reject_think=False, exc=None):
        self.result, self.reject_think, self.exc = result, reject_think, exc
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        if self.reject_think and "think" in kw:
            raise TypeError("unexpected keyword 'think'")
        if self.exc:
            raise self.exc
        return self.result


@pytest.fixture
def client(monkeypatch):
    def install(**kw):
        c = FakeClient(**kw)
        monkeypatch.setattr(llm, "_get_client", lambda *a, **k: c)
        return c
    return install


def test_only_llm_imports_ollama():
    offenders = [p.name for p in (BACKEND / "copilot").glob("*.py")
                 if p.name != "llm.py" and "import ollama" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_chat_json_parameters(client):
    c = client(result=resp('{"a": 1}', eval_count=10, eval_duration=2_000_000_000, total_duration=3e9))
    schema = {"type": "object"}
    assert llm.chat_json("rapide", "sys", "usr", schema) == {"a": 1}
    kw = c.calls[0]
    assert kw["model"] == "ministral-3:3b" and kw["format"] == schema and kw["think"] is False
    assert 0 <= kw["options"]["temperature"] <= 0.2
    assert kw["messages"][0] == {"role": "system", "content": "sys"}
    assert llm.last_stats["tok_per_s"] == 5.0


def test_chat_json_images(client):
    c = client(result=resp("{}"))
    llm.chat_json("precis", "s", "u", {}, images=[b"png"])
    assert c.calls[0]["messages"][1]["images"] == [b"png"]
    assert c.calls[0]["model"] == "ministral-3:8b"


def test_chat_json_without_think_support(client):
    c = client(result=resp("{}"), reject_think=True)
    assert llm.chat_json("rapide", "s", "u", {}) == {}
    assert "think" not in c.calls[-1]


@pytest.mark.parametrize("content", ["pas du json", "[1, 2]", ""])
def test_chat_json_invalid_json(client, content):
    client(result=resp(content))
    with pytest.raises(llm.LLMOutputError):
        llm.chat_json("rapide", "s", "u", {})


def test_chat_json_connection_error(client):
    client(exc=ConnectionError("refused"))
    with pytest.raises(llm.LLMError) as ei:
        llm.chat_json("rapide", "s", "u", {})
    assert not isinstance(ei.value, llm.LLMOutputError)


def test_unknown_model_key():
    with pytest.raises(llm.LLMError):
        llm.chat_json("inconnu", "s", "u", {})


def test_chat_stream(client):
    client(result=iter([resp("Bon"), resp(""), resp("jour")]))
    assert "".join(llm.chat_stream("rapide", "s", "u")) == "Bonjour"


def test_vision_to_text_pages(client):
    c = client(result=resp("  Texte page  "))
    out = llm.vision_to_text("rapide", [b"p1", b"p2"])
    assert out == "Texte page\n\nTexte page"
    assert len(c.calls) == 2 and c.calls[0]["messages"][1]["images"] == [b"p1"]
    assert "ne résumes pas" in c.calls[0]["messages"][0]["content"]


def test_health(monkeypatch):
    listed = types.SimpleNamespace(models=[types.SimpleNamespace(model="ministral-3:3b")])
    monkeypatch.setattr(llm, "_get_client", lambda *a, **k: types.SimpleNamespace(list=lambda: listed))
    h = llm.health()
    assert h == {"ok": True, "models": ["ministral-3:3b"], "missing": ["precis"]}


def test_health_down(monkeypatch):
    def boom():
        raise ConnectionError()
    monkeypatch.setattr(llm, "_get_client", lambda *a, **k: types.SimpleNamespace(list=boom))
    assert llm.health()["ok"] is False


@pytest.mark.llm
def test_real_health():
    assert llm.health()["ok"]


# --- Corrections relecture : contexte, timeout, repli think en streaming ------------

def test_num_ctx_passed_everywhere(client):
    c = client(result=resp("{}"))
    llm.chat_json("rapide", "s", "u", {})
    assert c.calls[-1]["options"]["num_ctx"] == llm.NUM_CTX == 16384
    c.result = iter([resp("x")])
    list(llm.chat_stream("rapide", "s", "u"))
    assert c.calls[-1]["options"]["num_ctx"] == llm.NUM_CTX
    c.result = resp("t")
    llm.vision_to_text("rapide", [b"p"])
    assert c.calls[-1]["options"]["num_ctx"] == llm.NUM_CTX


def test_cv_too_long_explicit_error():
    llm.check_cv_fits("x" * 1000, "prompt")
    assert 40_000 < llm.max_cv_chars("prompt") < 55_000   # borne de contexte
    limit = llm.MAX_CV_CHARS                                # borne métier/temps, plus stricte
    with pytest.raises(llm.ContextTooLongError) as ei:
        llm.check_cv_fits("x" * (limit + 1), "prompt")
    assert str(ei.value) == f"CV trop long : {limit + 1} caractères, max {limit}"
    assert isinstance(ei.value, llm.LLMError)


def test_chat_json_refuses_oversized_prompt_without_calling(client):
    c = client(result=resp("{}"))
    with pytest.raises(llm.ContextTooLongError):
        llm.chat_json("rapide", "s", "x" * 60_000, {})
    assert c.calls == []


def test_chat_json_default_timeout_600(monkeypatch):
    seen = {}

    def get_client(timeout_s=None):
        seen["t"] = timeout_s
        return FakeClient(result=resp("{}"))
    monkeypatch.setattr(llm, "_get_client", get_client)
    llm.chat_json("rapide", "s", "u", {})
    assert seen["t"] == llm.JSON_TIMEOUT_S == 600


class LazyThinkRefusal:
    """Comme Ollama en streaming : l'erreur `think` n'arrive qu'à la 1re itération du flux."""
    def __init__(self):
        self.calls = []

    def chat(self, **kw):
        self.calls.append(kw)
        if "think" in kw:
            def gen():
                raise llm.ollama.ResponseError('"ministral" does not support thinking')
                yield  # pragma: no cover
            return gen()
        return iter([resp("ok")])


def test_stream_think_fallback_on_first_iteration(monkeypatch):
    c = LazyThinkRefusal()
    monkeypatch.setattr(llm, "_get_client", lambda *a, **k: c)
    assert "".join(llm.chat_stream("rapide", "s", "u")) == "ok"
    assert "think" in c.calls[0] and "think" not in c.calls[1]


def test_errors_not_chained(client):
    client(exc=ConnectionError("contenu sensible"))
    with pytest.raises(llm.LLMError) as ei:
        llm.chat_json("rapide", "s", "u", {})
    assert ei.value.__cause__ is None and ei.value.__suppress_context__


def test_timeout_message_explicit(client):
    class ReadTimeout(Exception):
        pass
    client(exc=ReadTimeout())
    with pytest.raises(llm.LLMError, match=r"délai dépassé \(600 s\)"):
        llm.chat_json("rapide", "s", "u", {})
