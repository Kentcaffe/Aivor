"""Motor detecție AutoMod PRO — funcții pure + Violation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

INVITE_RE = re.compile(
    r"(?:https?://)?(?:discord\.(?:gg|com/invite)/[a-zA-Z0-9\-]+|discordapp\.com/invite/[a-zA-Z0-9\-]+)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+", re.IGNORECASE)
REPEAT_CHAR_RE = re.compile(r"(.)\1{7,}", re.DOTALL)


@dataclass(slots=True)
class Violation:
    key: str
    detail: str
    strikes: int = 1
    delete_only: bool = False
    instant_timeout_minutes: int | None = None


def _host_from_url(raw: str) -> str:
    u = raw.strip()
    if u.lower().startswith("www."):
        u = "http://" + u
    try:
        p = urlparse(u)
        h = (p.netloc or "").lower()
        return h.split(":")[0].lstrip("www.")
    except Exception:
        return ""


def is_whitelisted(member: Any, channel: Any, cfg: dict[str, Any]) -> bool:
    try:
        ch_ids = {int(x) for x in (cfg.get("whitelist_channel_ids") or []) if str(x).isdigit()}
        if channel:
            cid = getattr(channel, "id", None)
            if cid in ch_ids:
                return True
            parent = getattr(channel, "parent_id", None)
            if parent and int(parent) in ch_ids:
                return True
        role_ids = {int(x) for x in (cfg.get("whitelist_role_ids") or []) if str(x).isdigit()}
        for r in getattr(member, "roles", []) or []:
            if getattr(r, "id", None) in role_ids:
                return True
    except Exception:
        return False
    return False


def check_everyone_abuse(message: Any, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_everyone_abuse", True):
        return None
    author = message.author
    if hasattr(author, "guild_permissions") and author.guild_permissions.mention_everyone:
        return None
    if getattr(message, "mention_everyone", False):
        return Violation("everyone_abuse", "Mențiune @everyone / @here fără permisiune.")
    return None


def check_zalgo(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_zalgo", True) or not text:
        return None
    lim = float(cfg.get("zalgo_ratio", 0.34))
    comb = 0
    for c in text:
        if unicodedata.category(c) in ("Mn", "Me", "Cf") or unicodedata.combining(c):
            comb += 1
    ratio = comb / max(len(text), 1)
    if ratio >= lim:
        return Violation("zalgo", f"Text cu prea multe caractere Unicode combinate ({ratio:.0%}).")
    return None


def check_repeat_chars(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_repeat_chars", True) or not text:
        return None
    th = int(cfg.get("repeat_char_threshold", 8))
    m = REPEAT_CHAR_RE.search(text)
    if m and len(m.group(0)) >= th:
        return Violation("repeat_chars", f"Caracter repetat excesiv (≥{th}).")
    return None


def _emoji_like_ratio(text: str) -> float:
    if not text:
        return 0.0
    n = 0
    for ch in text:
        o = ord(ch)
        if o > 0x1F000 or (0x2600 <= o <= 0x27BF) or (0x1F300 <= o <= 0x1FAFF):
            n += 1
    return n / len(text)


def check_emoji_spam(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_emoji_spam", True) or len(text) < 6:
        return None
    ratio = float(cfg.get("emoji_spam_ratio", 0.55))
    if _emoji_like_ratio(text) >= ratio:
        return Violation("emoji_spam", f"Prea multe emoji/simboluri (>{ratio:.0%} din mesaj).")
    return None


def check_caps(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_caps", True):
        return None
    min_c = int(cfg.get("caps_min_chars", 8))
    if len(text) < min_c:
        return None
    letters = [c for c in text if c.isalpha()]
    if len(letters) < min_c // 2:
        return None
    up = sum(1 for c in letters if c.isupper())
    r = up / len(letters)
    cr = float(cfg.get("caps_ratio", 0.72))
    if r >= cr:
        return Violation("caps", f"Prea multe majuscule ({r:.0%} din litere).")
    return None


def check_mentions(message: Any, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_mentionspam", True):
        return None
    lim = int(cfg.get("mention_limit", 6))
    n = len(getattr(message, "mentions", []) or [])
    if n >= lim:
        return Violation("mention_spam", f"Prea multe mențiuni într-un mesaj ({n} ≥ {lim}).")
    return None


def _domain_allowed(host: str, whitelist: list[str]) -> bool:
    host = host.lower().strip(".")
    for w in whitelist:
        w = str(w).lower().strip().lstrip("www.")
        if not w:
            continue
        if host == w or host.endswith("." + w):
            return True
    return False


def check_links(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_link", True):
        return None
    wl = [str(x) for x in (cfg.get("link_domain_whitelist") or [])]
    for m in URL_RE.finditer(text):
        raw = m.group(0)
        host = _host_from_url(raw)
        if not host:
            continue
        if wl and _domain_allowed(host, wl):
            continue
        if not wl:
            return Violation("link", f"Link extern blocat (`{host[:80]}`). Adaugă domeniul în whitelist.")
        return Violation("link", f"Domeniu nepermis: `{host[:80]}`.")
    return None


def check_invites(text: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_invite", True):
        return None
    if not INVITE_RE.search(text):
        return None
    allow = [str(x).lower() for x in (cfg.get("invite_whitelist_substrings") or [])]
    low = text.lower()
    for a in allow:
        if a and a in low:
            return None
    return Violation("invite", "Invitație Discord blocată.")


def check_blacklist(text: str, cfg: dict[str, Any]) -> Violation | None:
    low = text.lower()
    entries = list(cfg.get("blacklist_entries") or [])
    if not entries:
        for phrase in cfg.get("blacklist") or []:
            if isinstance(phrase, str) and phrase.lower() in low:
                return Violation("blacklist", f"Cuvânt interzis: `{phrase[:40]}`", strikes=1)
        return None
    for ent in entries:
        if not isinstance(ent, dict):
            continue
        ph = str(ent.get("phrase", "")).strip()
        if not ph or ph.lower() not in low:
            continue
        sev = str(ent.get("severity", "medium")).lower()
        if sev == "low":
            return Violation("blacklist", f"Listă (low): `{ph[:40]}`", strikes=0, delete_only=True)
        if sev == "medium":
            return Violation("blacklist", f"Listă: `{ph[:40]}`", strikes=1)
        if sev == "high":
            return Violation("blacklist", f"Listă (ridicat): `{ph[:40]}`", strikes=2)
        if sev == "critical":
            return Violation(
                "blacklist",
                f"Listă (critic): `{ph[:40]}`",
                strikes=1,
                instant_timeout_minutes=60,
            )
        return Violation("blacklist", f"Listă: `{ph[:40]}`", strikes=1)
    return None


def check_flood(timestamps: list[float], now: float, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_spam", True) or not cfg.get("anti_spam_flood", True):
        return None
    win = float(cfg.get("spam_flood_window_sec", 8.0))
    cnt = int(cfg.get("spam_flood_count", 6))
    recent = [t for t in timestamps if now - t <= win]
    if len(recent) >= cnt:
        return Violation("spam_flood", f"Flood: {len(recent)} mesaje în {win:.0f}s.")
    return None


def check_cross_channel(
    pairs: list[tuple[int, float]], now: float, cfg: dict[str, Any]
) -> Violation | None:
    if not cfg.get("anti_spam", True) or not cfg.get("anti_cross_channel", True):
        return None
    win = float(cfg.get("cross_channel_window_sec", 5.0))
    need = int(cfg.get("cross_channel_min", 3))
    recent = [(ch, t) for ch, t in pairs if now - t <= win]
    chans = {ch for ch, _ in recent}
    if len(chans) >= need:
        return Violation("cross_channel", f"Spam pe {len(chans)} canale în {win:.0f}s.")
    return None


def normalize_message_content(content: str) -> str:
    return " ".join(content.lower().split())


def check_nickname(nick: str, cfg: dict[str, Any]) -> Violation | None:
    if not cfg.get("anti_nickname", True) or not nick:
        return None
    v = check_zalgo(nick, cfg)
    if v:
        v.key = "nickname_zalgo"
        return v
    v = check_invites(nick, cfg)
    if v:
        v.key = "nickname_invite"
        v.detail = "Invitație în pseudonim."
        return v
    v = check_links(nick, cfg)
    if v:
        v.key = "nickname_link"
        v.detail = "Link în pseudonim."
        return v
    v = check_blacklist(nick, cfg)
    if v:
        v.key = "nickname_blacklist"
        v.detail = f"Pseudonim: {v.detail}"
        return v
    return None


def run_message_checks(
    message: Any,
    cfg: dict[str, Any],
    *,
    flood_ts: list[float],
    now: float,
    cross_pairs: list[tuple[int, float]],
) -> Violation | None:
    """everyone → blacklist → zalgo → invite → link → caps → mention → emoji → repeat → cross → flood."""
    if not cfg.get("enabled", True):
        return None

    content = getattr(message, "content", "") or ""

    v = check_everyone_abuse(message, cfg)
    if v:
        return v

    v = check_blacklist(content, cfg)
    if v:
        return v

    v = check_zalgo(content, cfg)
    if v:
        return v

    v = check_invites(content, cfg)
    if v:
        return v

    v = check_links(content, cfg)
    if v:
        return v

    v = check_caps(content, cfg)
    if v:
        return v

    v = check_mentions(message, cfg)
    if v:
        return v

    v = check_emoji_spam(content, cfg)
    if v:
        return v

    v = check_repeat_chars(content, cfg)
    if v:
        return v

    v = check_cross_channel(cross_pairs, now, cfg)
    if v:
        return v

    v = check_flood(flood_ts, now, cfg)
    if v:
        return v

    return None
