"""Configurație AutoMod PRO — JSON per server în `guild_settings.automod_json`."""

from __future__ import annotations

import copy
import json
from typing import Any

SCHEMA_VERSION = 2

AUTO_MOD_DEFAULTS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "enabled": True,
    "anti_spam": True,
    "anti_spam_flood": True,
    "spam_flood_count": 6,
    "spam_flood_window_sec": 8.0,
    "anti_duplicate": True,
    "duplicate_window_sec": 20.0,
    "duplicate_min_equal": 2,
    "anti_emoji_spam": True,
    "emoji_spam_ratio": 0.55,
    "anti_repeat_chars": True,
    "repeat_char_threshold": 8,
    "anti_cross_channel": True,
    "cross_channel_min": 3,
    "cross_channel_window_sec": 5.0,
    "anti_link": True,
    "link_domain_whitelist": [],
    "anti_invite": True,
    "invite_whitelist_substrings": [],
    "anti_caps": True,
    "caps_min_chars": 8,
    "caps_ratio": 0.72,
    "anti_mentionspam": True,
    "mention_limit": 6,
    "anti_everyone_abuse": True,
    "anti_zalgo": True,
    "zalgo_ratio": 0.34,
    "anti_nickname": True,
    "blacklist": [],
    "blacklist_entries": [],
    "strike_mute_at": 3,
    "strike_kick_at": 5,
    "strike_ban_at": 7,
    "mute_duration_minutes": 60,
    "whitelist_role_ids": [],
    "whitelist_channel_ids": [],
    "automod_warn_threshold": 3,
    "automod_mute_minutes": 60,
    # False = zero mesaje de la bot în chat (doar ștergere + log). True = linie scurtă, dispare în ~1s.
    "public_channel_notice": False,
}


def _migrate_legacy(cfg: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(cfg)
    ver = int(out.get("schema_version", 1) or 1)
    if ver >= SCHEMA_VERSION:
        return out
    if "strike_mute_at" not in out and out.get("automod_warn_threshold") is not None:
        out["strike_mute_at"] = int(out["automod_warn_threshold"])
    if "mute_duration_minutes" not in out and out.get("automod_mute_minutes") is not None:
        out["mute_duration_minutes"] = int(out["automod_mute_minutes"])
    if "strike_kick_at" not in out:
        out["strike_kick_at"] = 5
    if "strike_ban_at" not in out:
        out["strike_ban_at"] = 7
    if not out.get("blacklist_entries"):
        bl = out.get("blacklist") or []
        out["blacklist_entries"] = [{"phrase": str(p), "severity": "medium"} for p in bl if isinstance(p, str)]
    out["schema_version"] = SCHEMA_VERSION
    return out


def merge_automod_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    merged = copy.deepcopy(AUTO_MOD_DEFAULTS)
    if raw:
        user = _migrate_legacy(copy.deepcopy(raw))
        merged.update(user)
    for k, v in AUTO_MOD_DEFAULTS.items():
        if k not in merged:
            merged[k] = copy.deepcopy(v)
    return merged


def dumps_config(cfg: dict[str, Any]) -> str:
    return json.dumps(cfg, ensure_ascii=False)
