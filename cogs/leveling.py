from __future__ import annotations

import json
import random
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.aivor_embeds import aivor_embed
from utils.db import execute, fetch_all, fetch_one, get_guild_settings, update_guild_settings


def xp_needed_for_level(level: int) -> int:
    """XP necesar pentru nivelul curent (bară) — creștere netedă."""
    return max(45, int(80 * (level ** 1.42)))


class Leveling(commands.Cog):
    """Leveling premium Aivor — XP, roluri, recompense."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown: dict[tuple[int, int], float] = {}

    def _cooldown_sec(self, guild_id: int) -> int:
        row = fetch_one("SELECT xp_cooldown_sec FROM guild_settings WHERE guild_id = ?", (guild_id,))
        if row and row["xp_cooldown_sec"] is not None:
            return int(row["xp_cooldown_sec"])
        return 25

    def get_user(self, guild_id: int, user_id: int) -> dict:
        execute(
            """
            INSERT OR IGNORE INTO leveling_users(guild_id, user_id, xp, level, total_xp, messages_count)
            VALUES(?, ?, 0, 1, 0, 0)
            """,
            (guild_id, user_id),
        )
        row = fetch_one(
            "SELECT xp, level, total_xp, messages_count FROM leveling_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return dict(row) if row else {"xp": 0, "level": 1, "total_xp": 0, "messages_count": 0}

    async def _apply_level_roles(self, member: discord.Member, new_level: int) -> None:
        guild_cfg = get_guild_settings(member.guild.id)
        role_map = guild_cfg.get("level_roles", {})
        role_id = role_map.get(str(new_level))
        if not role_id:
            return
        role = member.guild.get_role(int(role_id))
        if role:
            try:
                await member.add_roles(role, reason=f"Aivor: nivel {new_level}")
            except discord.Forbidden:
                pass

    async def _apply_level_rewards(self, guild: discord.Guild, member: discord.Member, new_level: int) -> None:
        cfg = get_guild_settings(guild.id)
        rewards = cfg.get("level_rewards", {})
        raw = rewards.get(str(new_level))
        if not raw:
            return
        try:
            money = int(raw.get("money", 0)) if isinstance(raw, dict) else int(raw)
        except (TypeError, ValueError):
            money = 0
        if money <= 0:
            return
        execute(
            """
            INSERT OR IGNORE INTO economy_users(guild_id, user_id, cash, bank, last_daily, last_work, inventory_json, profile_json)
            VALUES(?, ?, 500, 0, 0, 0, '{}', '{}')
            """,
            (guild.id, member.id),
        )
        row = fetch_one("SELECT cash, bank, last_daily, last_work, inventory_json, profile_json FROM economy_users WHERE guild_id = ? AND user_id = ?", (guild.id, member.id))
        if not row:
            return
        cash = int(row["cash"]) + money
        execute(
            """
            UPDATE economy_users SET cash = ? WHERE guild_id = ? AND user_id = ?
            """,
            (cash, guild.id, member.id),
        )
        execute(
            "INSERT INTO economy_transactions(guild_id, user_id, type, amount, note) VALUES(?, ?, ?, ?, ?)",
            (guild.id, member.id, "level_reward", money, f"Nivel {new_level}"),
        )
        try:
            await member.send(embed=aivor_embed("Recompensă nivel", f"Ai primit **`{money}$`** pentru nivelul `{new_level}` pe **{guild.name}**."))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        key = (message.guild.id, message.author.id)
        now = time.time()
        cd = self._cooldown_sec(message.guild.id)
        last = self.cooldown.get(key, 0)
        if now - last < cd:
            return
        self.cooldown[key] = now

        user = self.get_user(message.guild.id, message.author.id)
        gained = random.randint(10, 24)
        xp = int(user["xp"]) + gained
        level = int(user["level"])
        total_xp = int(user["total_xp"]) + gained
        msgs = int(user["messages_count"]) + 1
        need = xp_needed_for_level(level)
        leveled = False
        while xp >= need:
            xp -= need
            level += 1
            need = xp_needed_for_level(level)
            leveled = True
        execute(
            """
            UPDATE leveling_users SET xp = ?, level = ?, total_xp = ?, messages_count = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (xp, level, total_xp, msgs, message.guild.id, message.author.id),
        )
        if leveled:
            await message.channel.send(
                embed=aivor_embed(
                    "Nivel nou",
                    f"{message.author.mention} a ajuns la **nivelul {level}**!",
                )
            )
            await self._apply_level_roles(message.author, level)
            await self._apply_level_rewards(message.guild, message.author, level)

    @commands.hybrid_command(name="rank", description="Poziția ta sau a altcuiva în clasamentul XP pe server.")
    @app_commands.describe(utilizator="Membru")
    async def rank(self, ctx: commands.Context, utilizator: discord.Member | None = None):
        if not ctx.guild:
            return
        target = utilizator or ctx.author
        u = self.get_user(ctx.guild.id, target.id)
        lvl = int(u["level"])
        need = xp_needed_for_level(lvl)
        embed = aivor_embed(
            f"Rank · {target.display_name}",
            f"**Nivel:** `{lvl}`\n**XP:** `{u['xp']}` / `{need}`\n**Total XP:** `{u['total_xp']}`\n**Mesaje numărate:** `{u['messages_count']}`",
        )
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="toplevel", description="Top utilizatori după nivel / XP pe server.")
    async def toplevel(self, ctx: commands.Context):
        if not ctx.guild:
            return
        rows = fetch_all(
            """
            SELECT user_id, level, xp, total_xp FROM leveling_users WHERE guild_id = ?
            ORDER BY level DESC, xp DESC, total_xp DESC LIMIT 10
            """,
            (ctx.guild.id,),
        )
        if not rows:
            await ctx.reply("Nu există date încă.")
            return
        lines = []
        for i, row in enumerate(rows, 1):
            mem = ctx.guild.get_member(int(row["user_id"]))
            name = mem.display_name if mem else f"ID {row['user_id']}"
            need = xp_needed_for_level(int(row["level"]))
            lines.append(f"**{i}.** {name} — `{row['level']}` ({row['xp']}/{need} XP)")
        await ctx.reply(embed=aivor_embed("Leaderboard nivel Aivor", "\n".join(lines)))

    @commands.hybrid_command(name="profil_level", description="Profil detaliat: nivel, XP, progres până la următorul nivel.")
    @app_commands.describe(utilizator="Membru")
    async def profil_level(self, ctx: commands.Context, utilizator: discord.Member | None = None):
        if not ctx.guild:
            return
        m = utilizator or ctx.author
        u = self.get_user(ctx.guild.id, m.id)
        lvl = int(u["level"])
        need = xp_needed_for_level(lvl)
        embed = aivor_embed(
            f"Profil XP · {m.display_name}",
            f"Nivel **{lvl}** · XP curent **{u['xp']}** / **{need}**\nTotal XP: **{u['total_xp']}** · Mesaje: **{u['messages_count']}**",
        )
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="setlevelrole", description="Staff: acordă automat un rol când utilizatorul atinge nivelul setat.")
    @commands.has_permissions(administrator=True)
    @app_commands.describe(level="Nivel", rol="Rol Discord")
    async def setlevelrole(self, ctx: commands.Context, level: int, rol: discord.Role):
        if not ctx.guild:
            return
        cfg = get_guild_settings(ctx.guild.id)
        lr = cfg.get("level_roles", {})
        lr[str(level)] = rol.id
        update_guild_settings(ctx.guild.id, level_roles_json=json.dumps(lr, ensure_ascii=False))
        await ctx.reply(f"✅ La nivel **{level}** se acordă {rol.mention}.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="setlevelreward", description="Staff: sumă cash acordată automat la urcarea unui nivel.")
    @commands.has_permissions(administrator=True)
    async def setlevelreward(self, ctx: commands.Context, level: int, bani: int):
        if not ctx.guild:
            return
        cfg = get_guild_settings(ctx.guild.id)
        rew = cfg.get("level_rewards", {})
        rew[str(level)] = {"money": bani}
        update_guild_settings(ctx.guild.id, level_rewards_json=json.dumps(rew, ensure_ascii=False))
        await ctx.reply(f"✅ La nivel **{level}**: **`{bani}$`**.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="xpconfig", description="Staff: secunde minime între mesaje care acordă XP (anti-spam).")
    @commands.has_permissions(administrator=True)
    async def xpconfig(self, ctx: commands.Context, secunde: int):
        if not ctx.guild:
            return
        secunde = max(10, min(180, secunde))
        update_guild_settings(ctx.guild.id, xp_cooldown_sec=secunde)
        await ctx.reply(f"✅ Cooldown XP: **{secunde}s**.", ephemeral=bool(ctx.interaction))


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
