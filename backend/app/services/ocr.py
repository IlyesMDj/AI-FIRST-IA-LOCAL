"""Local OCR (RapidOCR / ONNX Runtime, CPU, offline).

The engine is loaded lazily and kept in memory once created. The ONNX models
ship inside the ``rapidocr-onnxruntime`` wheel: nothing is downloaded.
"""
from __future__ import annotations

import threading
from typing import Any

_engine: Any = None
_lock = threading.Lock()


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _get_engine():
    global _engine
    with _lock:
        if _engine is None:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        return _engine


def ocr_image_array(arr) -> str:
    """OCR a BGR/RGB numpy image and return text lines ordered top→bottom."""
    engine = _get_engine()
    result, _ = engine(arr)
    if not result:
        return ""
    # result: [[box, text, score], ...]; group into lines by y coordinate
    items = []
    for box, text, score in result:
        if float(score) < 0.5:
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append((sum(ys) / 4, min(xs), max(ys) - min(ys), text))
    items.sort(key=lambda t: (t[0], t[1]))
    lines: list[list[tuple]] = []
    for it in items:
        if lines and abs(lines[-1][0][0] - it[0]) < max(8.0, it[2] * 0.5):
            lines[-1].append(it)
        else:
            lines.append([it])
    return "\n".join(" ".join(t[3] for t in sorted(line, key=lambda t: t[1])) for line in lines)
