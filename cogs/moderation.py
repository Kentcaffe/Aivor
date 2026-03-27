from __future__ import annotations

import discord
from datetime import timedelta
from discord import app_commands
from discord.ext import commands

from utils.db import execute, fetch_all
from utils.logger import build_log_embed
from utils.moderation_helpers import can_moderate


class Moderation(commands.Cog):
    """Moderare profesională — hybrid (slash + prefix)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_mod_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        logging_cog = self.bot.get_cog("LoggingCog")
        if logging_cog and hasattr(logging_cog, "send_log"):
            await logging_cog.send_log(guild, embed, "mod")

    def _add_case(
        self,
        guild_id: int,
        target_user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration_minutes: int | None = None,
    ) -> int:
        return execute(
            """
            INSERT INTO moderation_cases(guild_id, target_user_id, moderator_id, action, reason, duration_minutes)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (guild_id, target_user_id, moderator_id, action, reason, duration_minutes),
        )

    def _check_mod(self, ctx: commands.Context, target: discord.Member) -> bool:
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return False
        if not can_moderate(ctx.author, target):
            return False
        return True

    @commands.hybrid_command(name="ban", description="Exclude definitiv un membru de pe server; motiv obligatoriu.")
    @app_commands.default_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(membru="Membru de banat", motiv="Motiv obligatoriu")
    async def ban(self, ctx: commands.Context, membru: discord.Member, *, motiv: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motivul este obligatoriu (minim 2 caractere).", ephemeral=bool(ctx.interaction))
            return
        if not self._check_mod(ctx, membru):
            await ctx.reply("❌ Nu poți modera acest membru (ierarhie sau permisiuni).", ephemeral=bool(ctx.interaction))
            return
        try:
            await membru.ban(reason=f"{motiv} | {ctx.author}")
        except discord.Forbidden:
            await ctx.reply("❌ Lipsește permisiunea Ban Members sau rolul botului e prea jos.", ephemeral=bool(ctx.interaction))
            return
        case_id = self._add_case(ctx.guild.id, membru.id, ctx.author.id, "ban", motiv)
        await ctx.reply(f"⛔ {membru} banat. Caz `#{case_id}`")
        embed = build_log_embed("Ban", f"**Caz:** #{case_id}\n**Țintă:** {membru}\n**Mod:** {ctx.author}\n**Motiv:** {motiv}", discord.Color.red())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="unban", description="Scoate banul după ID-ul numeric al utilizatorului.")
    @app_commands.default_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(utilizator_id="ID cont Discord", motiv="Motiv")
    async def unban(self, ctx: commands.Context, utilizator_id: str, *, motiv: str):
        if not ctx.guild:
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motiv obligatoriu.", ephemeral=bool(ctx.interaction))
            return
        try:
            uid = int(utilizator_id)
        except ValueError:
            await ctx.reply("❌ ID invalid.", ephemeral=bool(ctx.interaction))
            return
        user = await self.bot.fetch_user(uid)
        try:
            await ctx.guild.unban(user, reason=f"{motiv} | {ctx.author}")
        except discord.Forbidden:
            await ctx.reply("❌ Nu pot debana.", ephemeral=bool(ctx.interaction))
            return
        except discord.NotFound:
            await ctx.reply("❌ Utilizatorul nu e în lista de banuri.", ephemeral=bool(ctx.interaction))
            return
        case_id = self._add_case(ctx.guild.id, uid, ctx.author.id, "unban", motiv)
        await ctx.reply(f"✅ Unban pentru `{user}`. Caz `#{case_id}`")
        embed = build_log_embed("Unban", f"**Caz:** #{case_id}\n**User:** {user}\n**Mod:** {ctx.author}\n**Motiv:** {motiv}", discord.Color.green())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="kick", description="Dă afară temporar un membru (poate reveni cu invitație).")
    @app_commands.default_permissions(kick_members=True)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, membru: discord.Member, *, motiv: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motiv obligatoriu.", ephemeral=bool(ctx.interaction))
            return
        if not self._check_mod(ctx, membru):
            await ctx.reply("❌ Nu poți modera acest membru.", ephemeral=bool(ctx.interaction))
            return
        try:
            await membru.kick(reason=f"{motiv} | {ctx.author}")
        except discord.Forbidden:
            await ctx.reply("❌ Nu pot da kick.", ephemeral=bool(ctx.interaction))
            return
        case_id = self._add_case(ctx.guild.id, membru.id, ctx.author.id, "kick", motiv)
        await ctx.reply(f"👢 Kick aplicat. Caz `#{case_id}`")
        embed = build_log_embed("Kick", f"**Caz:** #{case_id}\n**Țintă:** {membru}\n**Mod:** {ctx.author}\n**Motiv:** {motiv}", discord.Color.orange())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="mute", description="Timeout (minute).")
    @app_commands.default_permissions(moderate_members=True)
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, membru: discord.Member, minute: int, *, motiv: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motiv obligatoriu.", ephemeral=bool(ctx.interaction))
            return
        if minute < 1 or minute > 10080:
            await ctx.reply("❌ Durată invalidă (1–10080 minute).", ephemeral=bool(ctx.interaction))
            return
        if not self._check_mod(ctx, membru):
            await ctx.reply("❌ Nu poți modera acest membru.", ephemeral=bool(ctx.interaction))
            return
        until = discord.utils.utcnow() + timedelta(minutes=minute)
        try:
            await membru.edit(timed_out_until=until, reason=f"{motiv} | {ctx.author}")
        except discord.Forbidden:
            await ctx.reply("❌ Nu pot aplica timeout.", ephemeral=bool(ctx.interaction))
            return
        case_id = self._add_case(ctx.guild.id, membru.id, ctx.author.id, "mute", motiv, minute)
        await ctx.reply(f"🔇 Timeout {minute} min. Caz `#{case_id}`")
        embed = build_log_embed("Mute", f"**Caz:** #{case_id}\n**Țintă:** {membru}\n**Mod:** {ctx.author}\n**Durată:** {minute}m\n**Motiv:** {motiv}", discord.Color.dark_orange())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="unmute", description="Scoate timeout-ul (mute) de pe un membru.")
    @app_commands.default_permissions(moderate_members=True)
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, membru: discord.Member, *, motiv: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motiv obligatoriu.", ephemeral=bool(ctx.interaction))
            return
        if not self._check_mod(ctx, membru):
            await ctx.reply("❌ Nu poți modera acest membru.", ephemeral=bool(ctx.interaction))
            return
        try:
            await membru.edit(timed_out_until=None, reason=f"{motiv} | {ctx.author}")
        except discord.Forbidden:
            await ctx.reply("❌ Nu pot scoate timeout.", ephemeral=bool(ctx.interaction))
            return
        case_id = self._add_case(ctx.guild.id, membru.id, ctx.author.id, "unmute", motiv)
        await ctx.reply(f"🔊 Unmute. Caz `#{case_id}`")
        embed = build_log_embed("Unmute", f"**Caz:** #{case_id}\n**Țintă:** {membru}\n**Mod:** {ctx.author}", discord.Color.green())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="warn", description="Înregistrează un avertisment cu motiv (istoric moderare).")
    @app_commands.default_permissions(moderate_members=True)
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, membru: discord.Member, *, motiv: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        motiv = motiv.strip()
        if len(motiv) < 2:
            await ctx.reply("❌ Motiv obligatoriu.", ephemeral=bool(ctx.interaction))
            return
        if not self._check_mod(ctx, membru):
            await ctx.reply("❌ Nu poți modera acest membru.", ephemeral=bool(ctx.interaction))
            return
        execute(
            "INSERT INTO warnings(guild_id, user_id, mod_id, reason, source, created_at) VALUES(?, ?, ?, ?, 'manual', ?)",
            (ctx.guild.id, membru.id, ctx.author.id, motiv, int(discord.utils.utcnow().timestamp())),
        )
        case_id = self._add_case(ctx.guild.id, membru.id, ctx.author.id, "warn", motiv)
        total = len(fetch_all("SELECT id FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, membru.id)))
        await ctx.reply(f"⚠️ Warn. Caz `#{case_id}` · Total: **{total}**")
        embed = build_log_embed("Warn", f"**Caz:** #{case_id}\n**Țintă:** {membru}\n**Mod:** {ctx.author}\n**Motiv:** {motiv}", discord.Color.yellow())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="warnings", description="Lista avertismentelor unui membru.")
    @app_commands.default_permissions(moderate_members=True)
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, membru: discord.Member):
        if not ctx.guild:
            return
        entries = fetch_all(
            "SELECT mod_id, reason, source, created_at FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC LIMIT 12",
            (ctx.guild.id, membru.id),
        )
        if not entries:
            await ctx.reply(f"{membru.mention} nu are avertismente.")
            return
        lines = []
        for w in entries:
            mod = ctx.guild.get_member(int(w["mod_id"])) if w["mod_id"] else None
            mn = mod.mention if mod else "AutoMod"
            lines.append(f"• {w['reason']} ({w['source']}) — {mn}")
        await ctx.reply(embed=discord.Embed(title=f"Warnings · {membru.display_name}", description="\n".join(lines), color=discord.Color.gold()), ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="clearwarns", description="Șterge toate avertismentele înregistrate pentru un membru.")
    @app_commands.default_permissions(moderate_members=True)
    @commands.has_permissions(moderate_members=True)
    async def clearwarns(self, ctx: commands.Context, membru: discord.Member):
        if not ctx.guild:
            return
        execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, membru.id))
        await ctx.reply(f"✅ Am șters avertismentele pentru {membru.mention}.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="clear", description="Șterge în masă mesaje vechi din canal (limită sigură, max 200).")
    @app_commands.default_permissions(manage_messages=True)
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context, numar: int):
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            return
        numar = max(1, min(200, numar))
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
        deleted = await ctx.channel.purge(limit=numar)
        msg = f"🧹 Șterse **{len(deleted)}** mesaje."
        if ctx.interaction:
            await ctx.send(msg, ephemeral=True)
        else:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass
            await ctx.send(msg, delete_after=6)
        case_id = self._add_case(ctx.guild.id, ctx.author.id, ctx.author.id, "clear", f"{len(deleted)} mesaje")
        embed = build_log_embed("Clear", f"**Caz:** #{case_id}\n**Mod:** {ctx.author}\n**Canal:** {ctx.channel.mention}", discord.Color.blurple())
        await self._send_mod_log(ctx.guild, embed)

    @commands.hybrid_command(name="lock", description="Blochează canalul: @everyone nu mai poate trimite mesaje.")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            return
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.reply("🔒 Canal blocat.")

    @commands.hybrid_command(name="unlock", description="Deblochează canalul pentru trimitere mesaje.")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            return
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.reply("🔓 Canal deblocat.")

    @commands.hybrid_command(name="slowmode", description="Slowmode în secunde (0 = off).")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, secunde: int):
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        secunde = max(0, min(21600, secunde))
        await ctx.channel.edit(slowmode_delay=secunde)
        await ctx.reply(f"🐢 Slowmode: **{secunde}s**.")

    @commands.hybrid_command(name="case", description="Ultimele acțiuni de moderare înregistrate de bot.")
    async def case_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            return
        rows = fetch_all(
            "SELECT id, target_user_id, moderator_id, action, reason FROM moderation_cases WHERE guild_id = ? ORDER BY id DESC LIMIT 8",
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.reply("Nu există cazuri.")
            return
        lines = [f"`#{r['id']}` **{r['action']}** — {r['reason'][:80]}" for r in rows]
        await ctx.reply(embed=discord.Embed(title="Cazuri recente", description="\n".join(lines), color=discord.Color.dark_blue()), ephemeral=bool(ctx.interaction))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
