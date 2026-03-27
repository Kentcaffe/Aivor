"""AutoMod PRO — detecție avansată, escaladare 3/5/7, loguri embed."""

from __future__ import annotations

import time
from collections import deque
from datetime import timedelta
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from utils.automod_config import dumps_config, merge_automod_config
from utils.automod_engine import Violation, check_nickname, is_whitelisted, normalize_message_content, run_message_checks
from utils.db import execute, fetch_one, get_guild_settings, update_guild_settings
AIVOR_RED = discord.Color.from_rgb(237, 66, 69)
AIVOR_ORANGE = discord.Color.from_rgb(240, 173, 78)
AIVOR_DARK = discord.Color.from_rgb(35, 39, 47)


def _parse_snowflake(raw: str) -> int | None:
    s = raw.strip()
    if s.startswith("<#") and s.endswith(">"):
        s = s[2:-1]
    elif s.startswith("<@&") and s.endswith(">"):
        s = s[3:-1]
    elif s.startswith("<@") and s.endswith(">") and len(s) > 3:
        s = s[2:-1].lstrip("!")
    if s.isdigit() and len(s) < 22:
        return int(s)
    return None


# Dacă public_channel_notice e activ: un mesaj foarte scurt, șters aproape imediat; cooldown mare = fără spam.
PUBLIC_NOTICE_COOLDOWN_SEC = 25.0
PUBLIC_NOTICE_DELETE_AFTER = 1.2


class AutoMod(commands.Cog):
    """AutoMod PRO — anti-spam, linkuri, blacklist, zalgo, pseudonime, escaladare."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._flood: dict[tuple[int, int], list[float]] = {}
        self._dup: dict[tuple[int, int], deque[str]] = {}
        self._cross: dict[tuple[int, int], list[tuple[int, float]]] = {}
        self._trim_at = 8000
        self._last_public_notice_ts: dict[int, float] = {}

    def _cfg(self, guild_id: int) -> dict[str, Any]:
        gs = get_guild_settings(guild_id)
        return merge_automod_config(gs.get("automod") or {})

    def _save(self, guild_id: int, cfg: dict[str, Any]) -> None:
        update_guild_settings(guild_id, automod_json=dumps_config(cfg))

    def _trim(self) -> None:
        if len(self._flood) <= self._trim_at:
            return
        for d in (self._flood, self._dup, self._cross):
            keys = list(d.keys())[: len(d) // 2]
            for k in keys:
                d.pop(k, None)

    def _count_automod_warns(self, guild_id: int, user_id: int) -> int:
        row = fetch_one(
            "SELECT COUNT(*) AS c FROM warnings WHERE guild_id = ? AND user_id = ? AND source = 'automod'",
            (guild_id, user_id),
        )
        return int(row["c"]) if row else 0

    def _add_automod_warn(self, guild_id: int, user_id: int, reason: str) -> None:
        execute(
            """
            INSERT INTO warnings(guild_id, user_id, mod_id, reason, source, created_at)
            VALUES(?, ?, 0, ?, 'automod', ?)
            """,
            (guild_id, user_id, reason, int(time.time())),
        )

    async def _log_automod(
        self,
        guild: discord.Guild,
        *,
        title: str,
        fields: list[tuple[str, str, bool]],
        color: discord.Color = AIVOR_ORANGE,
    ) -> None:
        logging_cog = self.bot.get_cog("LoggingCog")
        if not logging_cog or not hasattr(logging_cog, "send_log"):
            return
        embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
        for name, value, inline in fields:
            embed.add_field(name=name, value=value[:1024], inline=inline)
        embed.set_footer(text="Aivor · AutoMod PRO")
        await logging_cog.send_log(guild, embed, "automod")

    async def _try_delete(self, message: discord.Message) -> bool:
        try:
            await message.delete()
            return True
        except discord.HTTPException:
            return False

    def _can_send_public_notice(self, channel_id: int) -> bool:
        now = time.time()
        last = self._last_public_notice_ts.get(channel_id, 0.0)
        if now - last < PUBLIC_NOTICE_COOLDOWN_SEC:
            return False
        self._last_public_notice_ts[channel_id] = now
        return True

    async def _send_one_public_notice(self, channel: discord.abc.Messageable, text: str) -> None:
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        if not self._can_send_public_notice(channel.id):
            return
        try:
            await channel.send(text[:2000], delete_after=PUBLIC_NOTICE_DELETE_AFTER)
        except discord.HTTPException:
            pass

    async def _enforce_violation(
        self,
        message: discord.Message,
        member: discord.Member,
        cfg: dict[str, Any],
        violation: Violation,
    ) -> None:
        guild = message.guild
        if not guild:
            return

        deleted = await self._try_delete(message)
        if not deleted:
            await self._log_automod(
                guild,
                title="AutoMod · ștergere eșuată",
                fields=[
                    ("Utilizator", str(member), True),
                    ("Canal", message.channel.mention if message.channel else "—", True),
                    ("Motiv", violation.detail[:900], False),
                    ("Notă", "Botul nu are Manage Messages pe acest canal.", False),
                ],
                color=AIVOR_RED,
            )
            return

        old_strikes = self._count_automod_warns(guild.id, member.id)
        strikes = 0 if violation.delete_only else max(0, int(violation.strikes))
        for _ in range(strikes):
            self._add_automod_warn(guild.id, member.id, f"[{violation.key}] {violation.detail[:180]}")

        new_strikes = self._count_automod_warns(guild.id, member.id)

        execute(
            "INSERT INTO automod_events(guild_id, user_id, reason, action) VALUES(?, ?, ?, ?)",
            (guild.id, member.id, violation.detail[:500], "strike" if strikes else "delete"),
        )

        instant_mute = False
        if violation.instant_timeout_minutes and violation.instant_timeout_minutes > 0:
            try:
                until = discord.utils.utcnow() + timedelta(minutes=int(violation.instant_timeout_minutes))
                await member.timeout(until, reason="AutoMod PRO · severitate critică")
                instant_mute = True
            except discord.HTTPException:
                pass

        await self._log_automod(
            guild,
            title=f"AutoMod · {violation.key}",
            fields=[
                ("Utilizator", f"{member.mention}\n`{member.id}`", True),
                ("Canal", message.channel.mention, True),
                ("Detaliu", violation.detail[:900], False),
                ("Strike-uri AutoMod", f"`{old_strikes}` → `{new_strikes}` (+{strikes})", True),
                ("Mesaj șters", "Da", True),
            ],
            color=AIVOR_ORANGE,
        )

        mute_at = int(cfg.get("strike_mute_at", 3))
        kick_at = int(cfg.get("strike_kick_at", 5))
        ban_at = int(cfg.get("strike_ban_at", 7))
        mute_min = int(cfg.get("mute_duration_minutes", 60))

        o, n = old_strikes, new_strikes
        escal: str | None = None

        if n >= ban_at and o < ban_at:
            try:
                await guild.ban(member, reason="AutoMod PRO · prag strike-uri", delete_message_days=0)
                execute(
                    "INSERT INTO automod_events(guild_id, user_id, reason, action) VALUES(?, ?, ?, ?)",
                    (guild.id, member.id, "Prag ban", "ban"),
                )
                await self._log_automod(
                    guild,
                    title="AutoMod · Ban automat",
                    fields=[
                        ("Utilizator", f"{member} (`{member.id}`)", False),
                        ("Motiv", f"Ajuns la {n} strike-uri (prag {ban_at})", False),
                    ],
                    color=AIVOR_RED,
                )
                execute(
                    """
                    INSERT INTO moderation_cases(guild_id, target_user_id, moderator_id, action, reason, duration_minutes)
                    VALUES(?, ?, 0, 'ban', ?, NULL)
                    """,
                    (guild.id, member.id, f"AutoMod PRO: {n} strike-uri"),
                )
            except discord.HTTPException:
                pass
            return

        if n >= kick_at and o < kick_at:
            try:
                await member.kick(reason="AutoMod PRO · prag strike-uri")
                execute(
                    "INSERT INTO automod_events(guild_id, user_id, reason, action) VALUES(?, ?, ?, ?)",
                    (guild.id, member.id, "Prag kick", "kick"),
                )
                await self._log_automod(
                    guild,
                    title="AutoMod · Kick automat",
                    fields=[
                        ("Utilizator", f"{member} (`{member.id}`)", False),
                        ("Motiv", f"Ajuns la {n} strike-uri (prag {kick_at})", False),
                    ],
                    color=AIVOR_RED,
                )
                execute(
                    """
                    INSERT INTO moderation_cases(guild_id, target_user_id, moderator_id, action, reason, duration_minutes)
                    VALUES(?, ?, 0, 'kick', ?, NULL)
                    """,
                    (guild.id, member.id, f"AutoMod PRO: {n} strike-uri"),
                )
            except discord.HTTPException:
                pass
            return

        if n >= mute_at and o < mute_at:
            try:
                until = discord.utils.utcnow() + timedelta(minutes=mute_min)
                await member.timeout(until, reason="AutoMod PRO · prag strike-uri (timeout)")
                execute(
                    "INSERT INTO automod_events(guild_id, user_id, reason, action) VALUES(?, ?, ?, ?)",
                    (guild.id, member.id, f"Timeout {mute_min}m", f"timeout_{mute_min}m"),
                )
                await self._log_automod(
                    guild,
                    title="AutoMod · Timeout automat",
                    fields=[
                        ("Utilizator", member.mention, True),
                        ("Durată", f"{mute_min} minute", True),
                        ("Motiv", f"Prag {mute_at} strike-uri (total {n})", False),
                    ],
                    color=AIVOR_DARK,
                )
                escal = f"timeout {mute_min} min"
            except discord.HTTPException:
                pass

        # Un singur mesaj scurt în chat (sau deloc): fără spam; detaliile rămân în canalul de log.
        silent = violation.delete_only and strikes == 0
        if silent:
            return

        if not cfg.get("public_channel_notice", False):
            return

        parts: list[str] = [f"🚫 {member.mention}", f"· AutoMod", f"· {violation.key}"]
        if new_strikes:
            parts.append(f"· strike {new_strikes}")
        if instant_mute:
            parts.append(f"· pauză {int(violation.instant_timeout_minutes or 0)} min")
        if escal:
            parts.append(f"· {escal}")
        line = " ".join(parts)
        await self._send_one_public_notice(message.channel, line)

    def _check_duplicate(self, key: tuple[int, int], norm: str, cfg: dict[str, Any]) -> Violation | None:
        if not cfg.get("anti_duplicate", True) or not norm.strip():
            return None
        dq = self._dup.setdefault(key, deque(maxlen=6))
        if len(dq) >= 2 and dq[-1] == dq[-2] == norm:
            return Violation("duplicate", "Mesaje duplicate identice repetate.")
        dq.append(norm)
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if not isinstance(message.author, discord.Member):
            return
        cfg = self._cfg(message.guild.id)
        if not cfg.get("enabled", True):
            return
        if is_whitelisted(message.author, message.channel, cfg):
            return

        self._trim()
        key = (message.guild.id, message.author.id)
        now = time.time()
        norm = normalize_message_content(message.content or "")

        dup_v = self._check_duplicate(key, norm, cfg)
        if dup_v:
            await self._enforce_violation(message, message.author, cfg, dup_v)
            return

        win_f = float(cfg.get("spam_flood_window_sec", 8.0))
        ts = self._flood.setdefault(key, [])
        ts.append(now)
        self._flood[key] = [t for t in ts if now - t <= win_f]

        win_c = float(cfg.get("cross_channel_window_sec", 5.0))
        cp = self._cross.setdefault(key, [])
        cp.append((message.channel.id, now))
        self._cross[key] = [(c, t) for c, t in cp if now - t <= win_c]

        v = run_message_checks(
            message,
            cfg,
            flood_ts=self._flood[key],
            now=now,
            cross_pairs=self._cross[key],
        )
        if v:
            await self._enforce_violation(message, message.author, cfg, v)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.bot or before.guild is None:
            return
        if before.nick == after.nick and before.display_name == after.display_name:
            return
        cfg = self._cfg(after.guild.id)
        if not cfg.get("enabled", True) or not cfg.get("anti_nickname", True):
            return
        nick = after.nick or after.display_name
        if not nick:
            return
        if is_whitelisted(after, None, cfg):
            return
        v = check_nickname(nick, cfg)
        if not v:
            return
        try:
            await after.edit(nick=before.nick, reason="AutoMod PRO · pseudonim invalid")
        except discord.HTTPException:
            try:
                await after.edit(nick=None, reason="AutoMod PRO · pseudonim invalid")
            except discord.HTTPException:
                return
        await self._log_automod(
            after.guild,
            title="AutoMod · Pseudonim resetat",
            fields=[
                ("Membru", str(after), True),
                ("Motiv", v.detail[:900], False),
            ],
            color=AIVOR_ORANGE,
        )

    # ——— Comenzi ———

    @commands.hybrid_group(name="automod", description="Panou AutoMod PRO: status, praguri, whitelist.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def automod_cmd(self, ctx: commands.Context) -> None:
        if ctx.invoked_subcommand is None:
            await self._send_status(ctx)

    async def _send_status(self, ctx: commands.Context) -> None:
        assert ctx.guild
        cfg = self._cfg(ctx.guild.id)
        embed = discord.Embed(title="AutoMod PRO — status", color=AIVOR_DARK)
        embed.add_field(
            name="Module",
            value=(
                f"Spam flood: **{'✓' if cfg.get('anti_spam_flood') else '✗'}** · Duplicate: **{'✓' if cfg.get('anti_duplicate') else '✗'}** · "
                f"Emoji: **{'✓' if cfg.get('anti_emoji_spam') else '✗'}** · Cross-ch: **{'✓' if cfg.get('anti_cross_channel') else '✗'}**\n"
                f"Link: **{'✓' if cfg.get('anti_link') else '✗'}** · Invite: **{'✓' if cfg.get('anti_invite') else '✗'}** · "
                f"CAPS: **{'✓' if cfg.get('anti_caps') else '✗'}** · Mențiuni: **{'✓' if cfg.get('anti_mentionspam') else '✗'}**\n"
                f"Everyone: **{'✓' if cfg.get('anti_everyone_abuse') else '✗'}** · Zalgo: **{'✓' if cfg.get('anti_zalgo') else '✗'}** · Nick: **{'✓' if cfg.get('anti_nickname') else '✗'}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Escaladare (strike-uri)",
            value=f"Timeout la **{cfg.get('strike_mute_at', 3)}** · Kick la **{cfg.get('strike_kick_at', 5)}** · Ban la **{cfg.get('strike_ban_at', 7)}** · Timeout: **{cfg.get('mute_duration_minutes', 60)}** min",
            inline=False,
        )
        if cfg.get("public_channel_notice"):
            chat_line = "**Activ** — o linie scurtă din bot (~1.2s vizibilă), max. la ~25s în același canal."
        else:
            chat_line = "**Oprit** — nu trimite mesaje în chat; doar șterge + jurnal AutoMod (implicit)."
        embed.add_field(name="Mesaj în chat", value=chat_line, inline=False)
        wl = len(cfg.get("whitelist_role_ids") or []) + len(cfg.get("whitelist_channel_ids") or [])
        embed.add_field(name="Whitelist", value=f"{wl} intrări (roluri + canale)", inline=True)
        embed.add_field(
            name="Domenii link (whitelist)",
            value=str(len(cfg.get("link_domain_whitelist") or [])),
            inline=True,
        )
        bl = len(cfg.get("blacklist_entries") or []) or len(cfg.get("blacklist") or [])
        embed.add_field(name="Blacklist", value=f"{bl} reguli", inline=True)
        embed.set_footer(text="Folosește /automod toggle, strikes, whitelist, domain…")
        await ctx.send(embed=embed, ephemeral=bool(ctx.interaction))

    @automod_cmd.command(name="toggle", description="Pornește sau oprește un modul AutoMod.")
    @app_commands.describe(
        feature="anti_spam_flood | anti_duplicate | anti_link | anti_invite | anti_caps | anti_zalgo | …",
        activ="on sau off",
    )
    async def automod_toggle(
        self,
        ctx: commands.Context,
        feature: str,
        activ: str,
    ) -> None:
        assert ctx.guild
        valid = {
            "anti_spam",
            "anti_spam_flood",
            "anti_duplicate",
            "anti_emoji_spam",
            "anti_repeat_chars",
            "anti_cross_channel",
            "anti_link",
            "anti_invite",
            "anti_caps",
            "anti_mentionspam",
            "anti_everyone_abuse",
            "anti_zalgo",
            "anti_nickname",
            "enabled",
            "public_channel_notice",
        }
        feat = feature.lower().strip()
        if feat not in valid:
            await ctx.send(f"❌ Modul invalid. Opțiuni: `{', '.join(sorted(valid))}`", ephemeral=True)
            return
        on = activ.lower().strip() in ("on", "1", "da", "yes", "true")
        cfg = self._cfg(ctx.guild.id)
        cfg[feat] = on
        self._save(ctx.guild.id, cfg)
        await ctx.send(f"✅ `{feat}` → **{'activ' if on else 'inactiv'}**.", ephemeral=True)

    @automod_cmd.command(name="strikes", description="Praguri mute / kick / ban (strike-uri AutoMod).")
    @app_commands.describe(mute_la="Primul timeout la N strike-uri", kick_la="Kick la N", ban_la="Ban la N", minute_timeout="Durată timeout la pragul de mute")
    async def automod_strikes(
        self,
        ctx: commands.Context,
        mute_la: int,
        kick_la: int,
        ban_la: int,
        minute_timeout: int | None = None,
    ) -> None:
        assert ctx.guild
        if not (1 <= mute_la < kick_la < ban_la <= 50):
            await ctx.send("❌ Trebuie `mute < kick < ban` (ex: 3, 5, 7).", ephemeral=True)
            return
        cfg = self._cfg(ctx.guild.id)
        cfg["strike_mute_at"] = mute_la
        cfg["strike_kick_at"] = kick_la
        cfg["strike_ban_at"] = ban_la
        cfg["automod_warn_threshold"] = mute_la
        if minute_timeout is not None:
            m = max(1, min(10080, minute_timeout))
            cfg["mute_duration_minutes"] = m
            cfg["automod_mute_minutes"] = m
        self._save(ctx.guild.id, cfg)
        await ctx.send(
            f"✅ Strike-uri: timeout **{mute_la}** · kick **{kick_la}** · ban **{ban_la}**"
            + (f" · timeout **{cfg['mute_duration_minutes']}** min" if minute_timeout else "")
            + ".",
            ephemeral=True,
        )

    @automod_cmd.command(name="whitelist", description="Adaugă sau scoate canale / roluri din whitelist.")
    @app_commands.describe(
        actiune="add sau remove",
        tipul="channel sau role",
        tinta="Mention sau ID",
    )
    async def automod_whitelist(
        self,
        ctx: commands.Context,
        actiune: str,
        tipul: str,
        tinta: str,
    ) -> None:
        assert ctx.guild
        cfg = self._cfg(ctx.guild.id)
        add = actiune.lower() in ("add", "+", "adauga")
        is_ch = tipul.lower() in ("channel", "canal", "c")
        tid = _parse_snowflake(tinta)
        if tid is None:
            await ctx.send("❌ Folosește ID sau mențiune validă (#canal / @rol).", ephemeral=True)
            return
        key = "whitelist_channel_ids" if is_ch else "whitelist_role_ids"
        lst = [int(x) for x in (cfg.get(key) or []) if str(x).isdigit()]
        if add:
            if tid not in lst:
                lst.append(tid)
        else:
            lst = [x for x in lst if x != tid]
        cfg[key] = lst
        self._save(ctx.guild.id, cfg)
        await ctx.send(f"✅ Whitelist {'actualizat' if add else 'scos'}: `{tid}` ({key}).", ephemeral=True)

    @automod_cmd.command(name="domain", description="Whitelist domenii pentru linkuri (ex: youtube.com).")
    async def automod_domain(self, ctx: commands.Context, actiune: str, domeniu: str) -> None:
        assert ctx.guild
        cfg = self._cfg(ctx.guild.id)
        dom = domeniu.lower().strip().lstrip("www.").split("/")[0]
        lst = list(cfg.get("link_domain_whitelist") or [])
        if actiune.lower() in ("add", "+"):
            if dom and dom not in lst:
                lst.append(dom)
        else:
            lst = [x for x in lst if x != dom]
        cfg["link_domain_whitelist"] = lst
        self._save(ctx.guild.id, cfg)
        await ctx.send(f"✅ Domenii: `{', '.join(lst[:20]) or '—'}`", ephemeral=True)

    @automod_cmd.command(name="inviteallow", description="Subșiruri permise în invitații (ex. cod invitație).")
    async def automod_inviteallow(self, ctx: commands.Context, actiune: str, text: str) -> None:
        assert ctx.guild
        cfg = self._cfg(ctx.guild.id)
        lst = list(cfg.get("invite_whitelist_substrings") or [])
        t = text.strip().lower()
        if actiune.lower() in ("add", "+"):
            if t and t not in lst:
                lst.append(t)
        else:
            lst = [x for x in lst if x != t]
        cfg["invite_whitelist_substrings"] = lst
        self._save(ctx.guild.id, cfg)
        await ctx.send("✅ Listă invite actualizată.", ephemeral=True)

    @commands.hybrid_command(name="blacklist_add", description="Adaugă frază în blacklist (severitate opțională).")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(
        fraza="Text de filtrat",
        severitate="low | medium | high | critical",
    )
    async def blacklist_add(
        self,
        ctx: commands.Context,
        fraza: str,
        severitate: str = "medium",
    ) -> None:
        if not ctx.guild:
            return
        sev = severitate.lower().strip()
        if sev not in ("low", "medium", "high", "critical"):
            sev = "medium"
        cfg = self._cfg(ctx.guild.id)
        entries = list(cfg.get("blacklist_entries") or [])
        ph = fraza.strip()[:200]
        entries = [e for e in entries if isinstance(e, dict) and e.get("phrase", "").lower() != ph.lower()]
        entries.append({"phrase": ph, "severity": sev})
        cfg["blacklist_entries"] = entries
        bl = [e["phrase"] for e in entries if isinstance(e, dict) and e.get("phrase")]
        cfg["blacklist"] = bl
        self._save(ctx.guild.id, cfg)
        await ctx.send(f"✅ Blacklist + `{ph[:80]}` (**{sev}**).", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="blacklist_remove", description="Scoate o frază din blacklist.")
    @commands.has_permissions(administrator=True)
    async def blacklist_remove(self, ctx: commands.Context, *, fraza: str) -> None:
        if not ctx.guild:
            return
        cfg = self._cfg(ctx.guild.id)
        entries = [e for e in (cfg.get("blacklist_entries") or []) if isinstance(e, dict) and e.get("phrase", "").lower() != fraza.lower()]
        cfg["blacklist_entries"] = entries
        cfg["blacklist"] = [e["phrase"] for e in entries if isinstance(e, dict) and e.get("phrase")]
        self._save(ctx.guild.id, cfg)
        await ctx.send("✅ Actualizat blacklist.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="automod_prag", description="[Legacy] Prag strike pentru timeout — folosește /automod strikes.")
    @commands.has_permissions(administrator=True)
    async def automod_prag(self, ctx: commands.Context, prag: int) -> None:
        if not ctx.guild:
            return
        prag = max(1, min(20, prag))
        cfg = self._cfg(ctx.guild.id)
        cfg["strike_mute_at"] = prag
        cfg["automod_warn_threshold"] = prag
        self._save(ctx.guild.id, cfg)
        await ctx.reply(f"✅ Prag timeout la **{prag}** strike-uri.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="automod_mute", description="[Legacy] Minute timeout la prag — folosește /automod strikes.")
    @commands.has_permissions(administrator=True)
    async def automod_mute_cmd(self, ctx: commands.Context, minute: int) -> None:
        if not ctx.guild:
            return
        minute = max(1, min(10080, minute))
        cfg = self._cfg(ctx.guild.id)
        cfg["mute_duration_minutes"] = minute
        cfg["automod_mute_minutes"] = minute
        self._save(ctx.guild.id, cfg)
        await ctx.reply(f"✅ Durată timeout automată: **{minute}** min.", ephemeral=bool(ctx.interaction))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
