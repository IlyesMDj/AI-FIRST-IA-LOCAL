"""Hardware monitoring (RAM via psutil, NVIDIA GPU via nvidia-smi when present)."""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

import psutil

_gpu_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])


def gpu_info() -> list[dict[str, Any]]:
    global _gpu_cache
    if time.monotonic() - _gpu_cache[0] < 3:
        return _gpu_cache[1]
    gpus: list[dict[str, Any]] = []
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            out = subprocess.run(
                [exe, "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    gpus.append({
                        "name": parts[0],
                        "vram_total_mb": int(float(parts[1])),
                        "vram_used_mb": int(float(parts[2])),
                        "utilization_pct": int(float(parts[3])) if parts[3].replace(".", "").isdigit() else None,
                        "temperature_c": int(float(parts[4])) if parts[4].replace(".", "").isdigit() else None,
                    })
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    _gpu_cache = (time.monotonic(), gpus)
    return gpus


def snapshot() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    return {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(logical=True),
        "ram_total_mb": int(vm.total / 1048576),
        "ram_available_mb": int(vm.available / 1048576),
        "ram_used_pct": vm.percent,
        "gpus": gpu_info(),
    }
