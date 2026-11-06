"""Evidence verification: is a quote returned by the model really in the CV?

Matching is done on a normalised form (case-folded, accents stripped,
punctuation → space, whitespace collapsed) with an index map back to the
original text so the source location can be shown to the recruiter.
"""
from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass


@dataclass
class Normalised:
    text: str
    index: list[int]  # normalised position -> original position


def normalise(text: str) -> Normalised:
    out: list[str] = []
    idx: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c)).casefold()
        for c in base:
            if c.isalnum() or c in "+#":
                out.append(c)
                idx.append(i)
                prev_space = False
            elif not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
    while out and out[-1] == " ":
        out.pop()
        idx.pop()
    return Normalised("".join(out), idx)


@dataclass
class Match:
    status: str  # verified | approximate | not_found
    start: int | None = None
    end: int | None = None
    similarity: float = 0.0


def find_quote(source: Normalised, quote: str) -> Match:
    q = normalise(quote).text
    if len(q) < 2:
        return Match("not_found")
    pos = source.text.find(q)
    if pos != -1:
        return Match("verified", source.index[pos], source.index[pos + len(q) - 1] + 1, 1.0)
    # Approximate: longest common block, then compare a window around it.
    sm = difflib.SequenceMatcher(None, source.text, q, autojunk=False)
    m = sm.find_longest_match(0, len(source.text), 0, len(q))
    if m.size < max(4, int(len(q) * 0.3)):
        return Match("not_found")
    w_start = max(0, m.a - m.b)
    w_end = min(len(source.text), w_start + len(q))
    window = source.text[w_start:w_end]
    ratio = difflib.SequenceMatcher(None, window, q, autojunk=False).ratio()
    if ratio >= 0.85:
        return Match("approximate", source.index[w_start], source.index[max(w_start, w_end - 1)] + 1, round(ratio, 2))
    return Match("not_found", similarity=round(ratio, 2))


def term_in_text(source: Normalised, term: str) -> bool:
    t = normalise(term).text
    return bool(t) and f" {t} " in f" {source.text} "
