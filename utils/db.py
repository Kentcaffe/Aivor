from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot.db"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                mod_log_channel_id INTEGER,
                ticket_log_channel_id INTEGER,
                automod_log_channel_id INTEGER,
                ticket_category_id INTEGER,
                ticket_staff_role_id INTEGER,
                level_roles_json TEXT NOT NULL DEFAULT '{}',
                level_rewards_json TEXT NOT NULL DEFAULT '{}',
                automod_json TEXT NOT NULL DEFAULT '{}',
                xp_cooldown_sec INTEGER NOT NULL DEFAULT 25,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS economy_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                cash INTEGER NOT NULL DEFAULT 500,
                bank INTEGER NOT NULL DEFAULT 0,
                last_daily REAL NOT NULL DEFAULT 0,
                last_work REAL NOT NULL DEFAULT 0,
                inventory_json TEXT NOT NULL DEFAULT '{}',
                profile_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS economy_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                note TEXT,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS leveling_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                total_xp INTEGER NOT NULL DEFAULT 0,
                messages_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                mod_id INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS moderation_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                duration_minutes INTEGER,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL DEFAULT 'other',
                status TEXT NOT NULL DEFAULT 'open',
                claimed_by INTEGER,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                closed_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS ticket_draft (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS automod_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );

            CREATE INDEX IF NOT EXISTS idx_economy_guild_user ON economy_users(guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_leveling_guild_user ON leveling_users(guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_warn_guild_user ON warnings(guild_id, user_id);
            CREATE INDEX IF NOT EXISTS idx_cases_guild_time ON moderation_cases(guild_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status);
            CREATE INDEX IF NOT EXISTS idx_automod_guild_user ON automod_events(guild_id, user_id);
            """
        )
        _migrate_schema()


def _migrate_schema() -> None:
    """Adaugă coloane noi pentru instalări vechi (SQLite)."""
    with _connect() as conn:

        def cols(table: str) -> set[str]:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

        g = cols("guild_settings")
        if "level_rewards_json" not in g:
            conn.execute("ALTER TABLE guild_settings ADD COLUMN level_rewards_json TEXT NOT NULL DEFAULT '{}'")
        if "xp_cooldown_sec" not in g:
            conn.execute("ALTER TABLE guild_settings ADD COLUMN xp_cooldown_sec INTEGER NOT NULL DEFAULT 25")

        e = cols("economy_users")
        if "profile_json" not in e:
            conn.execute("ALTER TABLE economy_users ADD COLUMN profile_json TEXT NOT NULL DEFAULT '{}'")

        l = cols("leveling_users")
        if "messages_count" not in l:
            conn.execute("ALTER TABLE leveling_users ADD COLUMN messages_count INTEGER NOT NULL DEFAULT 0")

        g2 = cols("guild_settings")
        if "ticket_staff_role_id" not in g2:
            conn.execute("ALTER TABLE guild_settings ADD COLUMN ticket_staff_role_id INTEGER")

        t = cols("tickets")
        if "ticket_type" not in t:
            conn.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT NOT NULL DEFAULT 'other'")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_draft (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                ticket_type TEXT NOT NULL,
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        conn.commit()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with _connect() as conn:
        return list(conn.execute(query, params).fetchall())


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with _connect() as conn:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.lastrowid


def ensure_guild_settings(guild_id: int) -> None:
    execute(
        """
        INSERT OR IGNORE INTO guild_settings(guild_id, automod_json, level_roles_json, level_rewards_json)
        VALUES(?, '{}', '{}', '{}')
        """,
        (guild_id,),
    )


def get_guild_settings(guild_id: int) -> dict[str, Any]:
    ensure_guild_settings(guild_id)
    row = fetch_one("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
    if row is None:
        return {}
    data = dict(row)
    data["level_roles"] = json.loads(data.get("level_roles_json") or "{}")
    data["level_rewards"] = json.loads(data.get("level_rewards_json") or "{}")
    data["automod"] = json.loads(data.get("automod_json") or "{}")
    return data


def update_guild_settings(guild_id: int, **fields: Any) -> None:
    if not fields:
        return
    ensure_guild_settings(guild_id)
    fragments = []
    values: list[Any] = []
    for key, value in fields.items():
        fragments.append(f"{key} = ?")
        values.append(value)
    fragments.append("updated_at = ?")
    values.append(int(time.time()))
    values.append(guild_id)
    execute(f"UPDATE guild_settings SET {', '.join(fragments)} WHERE guild_id = ?", tuple(values))


def migrate_json_to_sqlite() -> None:
    # Migrare best-effort din fișierele vechi JSON.
    economy_path = DATA_DIR / "economy.json"
    levels_path = DATA_DIR / "levels.json"
    warns_path = DATA_DIR / "warns.json"
    guild_cfg_path = DATA_DIR / "guild_config.json"
    tickets_path = DATA_DIR / "tickets.json"

    if economy_path.exists():
        _migrate_economy(economy_path)
    if levels_path.exists():
        _migrate_levels(levels_path)
    if warns_path.exists():
        _migrate_warns(warns_path)
    if guild_cfg_path.exists():
        _migrate_guild_cfg(guild_cfg_path)
    if tickets_path.exists():
        _migrate_tickets(tickets_path)


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _migrate_economy(path: Path) -> None:
    data = _safe_json(path)
    for gid, users in data.items():
        if not isinstance(users, dict) or not str(gid).isdigit():
            continue
        for uid, user in users.items():
            if not isinstance(user, dict) or not str(uid).isdigit():
                continue
            execute(
                """
                INSERT OR IGNORE INTO economy_users(guild_id, user_id, cash, bank, last_daily, last_work, inventory_json, profile_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(gid),
                    int(uid),
                    int(user.get("cash", 500)),
                    int(user.get("bank", 0)),
                    float(user.get("last_daily", 0)),
                    float(user.get("last_work", 0)),
                    json.dumps(user.get("inventory", {}), ensure_ascii=False),
                    json.dumps(user.get("profile", {}), ensure_ascii=False),
                ),
            )


def _migrate_levels(path: Path) -> None:
    data = _safe_json(path)
    for gid, users in data.items():
        if not isinstance(users, dict) or not str(gid).isdigit():
            continue
        for uid, user in users.items():
            if not isinstance(user, dict) or not str(uid).isdigit():
                continue
            execute(
                """
                INSERT OR IGNORE INTO leveling_users(guild_id, user_id, xp, level, total_xp)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    int(gid),
                    int(uid),
                    int(user.get("xp", 0)),
                    int(user.get("level", 1)),
                    int(user.get("total_xp", 0)),
                ),
            )


def _migrate_warns(path: Path) -> None:
    data = _safe_json(path)
    for gid, users in data.items():
        if not isinstance(users, dict) or not str(gid).isdigit():
            continue
        for uid, warns in users.items():
            if not str(uid).isdigit() or not isinstance(warns, list):
                continue
            for warning in warns:
                if not isinstance(warning, dict):
                    continue
                execute(
                    """
                    INSERT INTO warnings(guild_id, user_id, mod_id, reason, source, created_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(gid),
                        int(uid),
                        int(warning.get("mod_id", 0)),
                        str(warning.get("reason", "Fără motiv")),
                        str(warning.get("source", "manual")),
                        int(warning.get("timestamp", int(time.time()))),
                    ),
                )


def _migrate_guild_cfg(path: Path) -> None:
    data = _safe_json(path)
    for gid, cfg in data.items():
        if not str(gid).isdigit() or not isinstance(cfg, dict):
            continue
        ensure_guild_settings(int(gid))
        update_guild_settings(
            int(gid),
            log_channel_id=cfg.get("log_channel_id"),
            ticket_category_id=cfg.get("ticket_category_id"),
            level_roles_json=json.dumps(cfg.get("level_roles", {}), ensure_ascii=False),
            automod_json=json.dumps(
                {
                    "anti_link": bool(cfg.get("anti_link", True)),
                    "anti_spam": bool(cfg.get("anti_spam", True)),
                    "anti_caps": bool(cfg.get("anti_caps", True)),
                    "blacklist": cfg.get("blacklist", []),
                    "automod_warn_threshold": int(cfg.get("automod_warn_threshold", 3)),
                },
                ensure_ascii=False,
            ),
        )


def _migrate_tickets(path: Path) -> None:
    data = _safe_json(path)
    for gid, owners in data.items():
        if not str(gid).isdigit() or not isinstance(owners, dict):
            continue
        for uid, channel_id in owners.items():
            if not str(uid).isdigit():
                continue
            execute(
                """
                INSERT OR IGNORE INTO tickets(guild_id, owner_user_id, channel_id, status, created_at)
                VALUES(?, ?, ?, 'open', ?)
                """,
                (int(gid), int(uid), int(channel_id), int(time.time())),
            )
