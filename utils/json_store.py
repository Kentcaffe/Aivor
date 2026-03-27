"""Persistență JSON atomică pentru date auxiliare (AFK, backup config)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent.parent / "data"


def _path(name: str) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    return BASE / name


def load_json_file(filename: str, default: Any) -> Any:
    path = _path(filename)
    if not path.exists():
        return default
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return default
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return default


def save_json_file(filename: str, data: Any) -> None:
    path = _path(filename)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=BASE, prefix="tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
