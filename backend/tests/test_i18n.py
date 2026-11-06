"""Every user-facing backend message must have a French translation."""
from __future__ import annotations

import ast
import pathlib

from app.demo.synthetic import cv_by_key
from app.i18n import tr
from tests.conftest import process_all, upload

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

# Callables whose first argument is shown to the user.
_USER_CALLS = {
    "DocumentError", "OllamaError", "OllamaUnavailable", "ModelUnavailable", "OllamaTimeout",
    "InsufficientResources", "InvalidModelResponse", "EndpointNotAllowed", "HTTPException", "AssistantError",
}


def _render(node: ast.AST) -> str | None:
    """Render a literal / f-string / implicit concatenation with placeholders filled."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "7" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render(node.left), _render(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _user_messages() -> list[tuple[str, str]]:
    out = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            args = list(node.args)
            if name in _USER_CALLS:
                args = args[1:] if name == "HTTPException" else args[:1]
            elif name == "append" and isinstance(node.func, ast.Attribute) and "warn" in ast.unparse(node.func.value):
                args = args[:1]
            else:
                continue
            for a in args:
                msg = _render(a)
                if msg and " " in msg:
                    out.append((f"{path.name}:{node.lineno}", msg))
    return out


def test_all_user_messages_have_french_translation():
    messages = _user_messages()
    assert len(messages) > 40  # sanity: the scan finds the messages
    missing = [f"{where}: {m}" for where, m in messages if tr(m, "fr") == m]
    assert not missing, "Missing French translations:\n" + "\n".join(missing)


def test_api_returns_french_with_header(client):
    fr = {"X-Lang": "fr"}
    assert client.get("/api/candidates/00000000-0000-0000-0000-000000000000", headers=fr).json()["detail"] == "Candidat introuvable"
    assert client.get("/api/candidates/00000000-0000-0000-0000-000000000000").json()["detail"] == "Candidate not found"
    r = client.post("/api/candidates/upload", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))], headers=fr)
    assert r.json()["results"][0]["error"].startswith("Type de fichier non pris en charge")
    # stored warning translated at read time
    cid = upload(client, [("n.txt", cv_by_key("nora_fr_fullstack_injection").text.encode())]).json()["results"][0]["candidate_id"]
    process_all()
    d = client.get(f"/api/candidates/{cid}", headers={"Accept-Language": "fr-FR,fr;q=0.9"}).json()
    assert any("instructions adressées à une IA" in w for w in d["warnings"])
    rep = client.delete(f"/api/candidates/{cid}", headers=fr).json()["report"]
    assert rep["verification"][0]["check"].startswith("Enregistrements en base")


def test_ollama_errors_translated(client):
    client.fake.fail_mode = "down"
    st = client.get("/api/system/status", headers={"X-Lang": "fr"}).json()
    assert st["issues"] == ["Le moteur d'IA local (Ollama) est injoignable. Démarrez Ollama puis actualisez."]
