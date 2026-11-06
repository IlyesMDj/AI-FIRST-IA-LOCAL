"""Deterministic in-process fake of the Ollama REST API (httpx MockTransport).

It never opens a socket. It records every request so tests can assert that
only the local inference endpoint is called.
"""
from __future__ import annotations

import hashlib
import json
import re

import httpx

DOC_RE = re.compile(r"<<<DOCUMENT id=\w+ type=[\w-]+>>>\n(.*?)\n<<<END DOCUMENT id=\w+>>>", re.S)


def _doc(messages: list[dict]) -> str:
    for m in messages:
        found = DOC_RE.findall(m.get("content", ""))
        if found:
            return "\n".join(found)
    return ""


def _embed(text: str, dim: int = 64) -> list[float]:
    v = [0.0] * dim
    for w in re.findall(r"\w+", text.lower()):
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        v[h % dim] += 1.0
    return v


def _line_with(doc: str, term: str) -> str | None:
    for line in doc.split("\n"):
        if term.lower() in line.lower():
            return line.strip("- ").strip()
    return None


def fake_extraction(doc: str) -> dict:
    lines = [l for l in doc.split("\n") if l.strip()]
    skills = []
    for i, l in enumerate(lines):
        if l.strip().lower() in ("compétences", "skills"):
            for s in lines[i + 1].split(","):
                s = s.strip()
                if s:
                    skills.append({"name": s, "category": "technical", "basis": "explicit", "evidence": s})
    exp = []
    for l in lines:
        m = re.match(r"(.+?) [—-] (.+?) \((\d{4}-\d{2}) [–-] ([^)]+)\)", l)
        if m:
            exp.append({"position": m.group(1), "company": m.group(2), "description": None,
                        "start_date": m.group(3), "end_date": m.group(4), "evidence": l})
    edu = []
    for l in lines:
        m = re.match(r"(.+?) [—-] (.*(?:Universit|Institute|cole).*?) \((\d{4})\)", l)
        if m:
            edu.append({"degree": m.group(1), "field": None, "institution": m.group(2),
                        "graduation_year": m.group(3), "evidence": l})
    return {
        "candidate_name": lines[0] if lines else None,
        "professional_summary": "Profil synthétique de test.",
        "skills": skills + [{"name": "Hallucinated Skill", "category": "technical", "basis": "explicit", "evidence": "not in cv at all"}],
        "experience": exp,
        "education": edu,
        "languages": [],
        "certifications": [],
        "projects": [],
    }


def fake_assessment(doc: str, requirement: str) -> dict:
    term = re.split(r"\s+(?:ou|or)\s+|,", requirement)[0].strip()
    line = _line_with(doc, term)
    if line:
        return {"status": "demonstrated", "evidence_quotes": [line], "relevant_experience": None,
                "missing_information": None, "explanation": f"The CV mentions {term}."}
    return {"status": "not_found", "evidence_quotes": [], "relevant_experience": None,
            "missing_information": f"{term} is not mentioned.", "explanation": f"No mention of {term}."}


class FakeOllama:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.models = ["qwen3:8b", "qwen2.5:7b", "nomic-embed-text:latest"]
        self.fail_mode: str | None = None  # None | "down" | "timeout" | "invalid_json_once" | "invalid_json_always"
        self.loaded: set[str] = set()
        self._invalid_sent = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.fail_mode == "down":
            raise httpx.ConnectError("connection refused", request=request)
        path = request.url.path
        if path == "/api/version":
            return httpx.Response(200, json={"version": "fake"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": m, "size": 1000, "details": {}, "capabilities": ["embedding"] if "embed" in m else ["completion"]}
                for m in self.models]})
        if path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": m, "size": 1, "size_vram": 1} for m in self.loaded]})
        if path == "/api/show":
            body = json.loads(request.content)
            if body["model"] not in self.models:
                return httpx.Response(404, json={"error": "model not found"})
            return httpx.Response(200, json={"capabilities": ["embedding"] if "embed" in body["model"] else ["completion"]})
        body = json.loads(request.content) if request.content else {}
        model = body.get("model")
        if model and model not in self.models:
            return httpx.Response(404, json={"error": f"model '{model}' not found"})
        if self.fail_mode == "timeout" and path == "/api/chat":
            raise httpx.ReadTimeout("timeout", request=request)
        if path == "/api/embed":
            self.loaded.add(model)
            return httpx.Response(200, json={"embeddings": [_embed(t) for t in body.get("input", [])]})
        if path == "/api/chat":
            self.loaded.add(model)
            if not body.get("messages"):
                if body.get("keep_alive") == 0:
                    self.loaded.discard(model)
                return httpx.Response(200, json={"message": {"content": ""}, "done": True})
            return self._chat(body)
        return httpx.Response(404, json={"error": "unknown"})

    def _chat(self, body: dict) -> httpx.Response:
        messages = body["messages"]
        system = messages[0]["content"]
        doc = _doc(messages)
        if body.get("stream"):
            refs = re.findall(r"\[(C\d+-(?:\d+|P))\]", messages[-1]["content"])
            answer = f"Selon le CV, voici les éléments trouvés [{refs[0]}]." if refs else "Information non disponible."
            lines = [json.dumps({"message": {"content": w + " "}, "done": False}) for w in answer.split(" ")]
            lines.append(json.dumps({"message": {"content": ""}, "done": True}))
            return httpx.Response(200, content=("\n".join(lines) + "\n").encode())
        if self.fail_mode == "invalid_json_always" or (self.fail_mode == "invalid_json_once" and self._invalid_sent == 0):
            self._invalid_sent += 1
            return httpx.Response(200, json={"message": {"content": "Sure! Here is {not json"}, "done": True})
        if system.startswith("You extract"):
            out = fake_extraction(doc)
        elif system.startswith("You help a recruiter check"):
            req = re.search(r"Requirement to assess \([^)]*\):\n(.+?)\n", messages[-1]["content"]).group(1)
            out = fake_assessment(doc, req)
        elif system.startswith("You prepare structured interview"):
            first = doc.split("\n")[3] if doc.count("\n") > 3 else None
            out = {"questions": [
                {"category": c, "question": f"Question {c}?", "why_relevant": "Job related.", "competency": "Python",
                 "cv_evidence": first} for c in ("technical", "experience", "project", "problem_solving", "clarification")
            ] + [{"category": "clarification", "question": "Quel âge avez-vous ?", "why_relevant": "x", "competency": "x", "cv_evidence": None}]}
        else:
            out = {}
        return httpx.Response(200, json={"message": {"content": json.dumps(out, ensure_ascii=False)}, "done": True,
                                         "prompt_eval_count": 10, "eval_count": 10})
