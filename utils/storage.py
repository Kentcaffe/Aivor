from __future__ import annotations

import json
import os
import tempfile
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")


def ensure_data_files() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    defaults = {
        "economy.json": {},
        "levels.json": {},
        "warns.json": {},
        "guild_config.json": {},
        "tickets.json": {},
    }
    for filename, default in defaults.items():
        path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2, ensure_ascii=False)


def _path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)


def load_json(filename: str) -> dict[str, Any]:
    ensure_data_files()
    path = _path(filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if not raw:
                save_json(filename, {})
                return {}
            return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        # Dacă fișierul e corupt sau invalid, îl resetăm pentru a menține botul stabil.
        save_json(filename, {})
        return {}


def save_json(filename: str, data: dict[str, Any]) -> None:
    ensure_data_files()
    path = _path(filename)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, prefix="tmp_", suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_guild_store(data: dict[str, Any], guild_id: int) -> dict[str, Any]:
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {}
    return data[gid]


def get_user_store(data: dict[str, Any], guild_id: int, user_id: int) -> dict[str, Any]:
    guild_store = get_guild_store(data, guild_id)
    uid = str(user_id)
    if uid not in guild_store:
        guild_store[uid] = {}
    return guild_store[uid]