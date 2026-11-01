"""Disk cache for model results, so re-running the same photo costs no credits.

Files live at cache/<step>/<image hash>.json, e.g. cache/identify/3f2a9c....json.
Keying by step as well as image lets later steps (pricing, writing) cache separately.
"""

import json

from listly.config import CACHE_DIR


def _path(step: str, key: str, ext: str = "json"):
    return CACHE_DIR / step / f"{key}.{ext}"


def load(step: str, key: str) -> dict | None:
    """Return the cached result, or None if there isn't a usable one."""
    path = _path(step, key)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # A half-written or hand-edited file shouldn't break the app; just call the model again.
        return None


def save(step: str, key: str, data: dict) -> None:
    path = _path(step, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Explicit UTF-8 because Windows defaults to another encoding (matters for Filipino text later).
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# Generated images are saved as image files, not JSON: smaller, and you can open them to check.
def load_bytes(step: str, key: str, ext: str) -> bytes | None:
    path = _path(step, key, ext)
    return path.read_bytes() if path.exists() else None


def save_bytes(step: str, key: str, ext: str, data: bytes) -> None:
    path = _path(step, key, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
