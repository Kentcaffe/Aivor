from __future__ import annotations

from utils.db import init_db, migrate_json_to_sqlite


def run_migrations() -> None:
    init_db()
    migrate_json_to_sqlite()
