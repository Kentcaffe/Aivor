from __future__ import annotations

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.aivor_embeds import aivor_embed
from utils.help_data import STAFF_KEYS, all_category_keys_for_user, is_moderation_staff
from utils.safe_reply import hybrid_reply
from views.help_panel import HelpPanelView, build_category_embed, build_overview_embed


class Core(commands.Cog):
    """Nucleu Aivor — info, branding, ajutor hybrid."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.started_at = time.time()
        # Evită răspuns dublu la același mesaj (două procese sau invocări repetate ale callback-ului).
        self._help_dedup_lock = asyncio.Lock()
        self._help_last_msg: dict[int, float] = {}

    async def _dedup_prefix_help_async(self, message_id: int) -> bool:
        now = time.time()
        async with self._help_dedup_lock:
            t0 = self._help_last_msg.get(message_id)
            if t0 is not None and now - t0 < 12.0:
                return True
            self._help_last_msg[message_id] = now
            if len(self._help_last_msg) > 3000:
                self._help_last_msg.clear()
        return False

    def _help_is_staff(self, ctx: commands.Context) -> bool:
        if ctx.guild and isinstance(ctx.author, discord.Member):
            return is_moderation_staff(ctx.author)
        return False

    async def _send_help_prefix(self, ctx: commands.Context, categorie: str | None) -> None:
        """Doar prefix — hybrid_reply + dedup pe message.id."""
        if ctx.message and await self._dedup_prefix_help_async(ctx.message.id):
            return

        is_staff = self._help_is_staff(ctx)

        if categorie:
            key = categorie.lower().strip()
            if key in STAFF_KEYS and not is_staff:
                embed = aivor_embed(
                    "Acces restricționat",
                    "Categoriile de **moderare**, **AutoMod**, **tickete** și **log-uri** sunt vizibile doar pentru membri staff "
                    "(permisiuni de moderare sau configurare).",
                )
                await hybrid_reply(ctx, embed=embed, ephemeral=False)
                return
            valid = set(all_category_keys_for_user(is_staff))
            if key not in valid:
                embed = aivor_embed(
                    "Categorii disponibile",
                    " · ".join(all_category_keys_for_user(is_staff))
                    + "\nExemplu: `!help economie` sau `/help level`",
                )
                await hybrid_reply(ctx, embed=embed, ephemeral=False)
                return
            embed = build_category_embed(self.bot, key, is_staff=is_staff)
            await hybrid_reply(ctx, embed=embed, ephemeral=False)
            return

        embed = build_overview_embed(self.bot, is_staff=is_staff)
        view = HelpPanelView(self.bot, is_staff=is_staff)
        await hybrid_reply(ctx, embed=embed, view=view, ephemeral=False)

    @commands.command(name="help", aliases=["ajutor", "h"], help="Panou ghid: module + explicații pentru fiecare comandă.")
    async def help_prefix(self, ctx: commands.Context, categorie: str | None = None) -> None:
        await self._send_help_prefix(ctx, categorie)

    @app_commands.command(
        name="help",
        description="Panou ghid: alege modulul și vezi ce face fiecare comandă (slash sau prefix).",
    )
    @app_commands.describe(categorie="Modul: economie, level, fun, info; staff: mod, automod, ticket, log")
    async def help_slash(self, interaction: discord.Interaction, categorie: str | None = None) -> None:
        # Fără get_context + hybrid_reply — evită orice dublare; un singur răspuns la interaction.
        if not hasattr(self.bot, "_help_slash_seen"):
            self.bot._help_slash_seen = set()
        if interaction.id in self.bot._help_slash_seen:
            return
        self.bot._help_slash_seen.add(interaction.id)
        if len(self.bot._help_slash_seen) > 8000:
            self.bot._help_slash_seen.clear()

        is_staff = False
        if interaction.guild and isinstance(interaction.user, discord.Member):
            is_staff = is_moderation_staff(interaction.user)

        if categorie:
            key = categorie.lower().strip()
            if key in STAFF_KEYS and not is_staff:
                embed = aivor_embed(
                    "Acces restricționat",
                    "Categoriile de moderare sunt vizibile doar pentru staff.",
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            valid = set(all_category_keys_for_user(is_staff))
            if key not in valid:
                embed = aivor_embed(
                    "Categorii disponibile",
                    " · ".join(all_category_keys_for_user(is_staff)) + "\nExemplu: `/help economie`",
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)
                return
            embed = build_category_embed(self.bot, key, is_staff=is_staff)
            await interaction.response.send_message(embed=embed, ephemeral=False)
            return

        embed = build_overview_embed(self.bot, is_staff=is_staff)
        view = HelpPanelView(self.bot, is_staff=is_staff)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    @commands.hybrid_command(name="ping", description="Latență gateway bot (heartbeat Discord, în ms).")
    async def ping(self, ctx: commands.Context):
        ws_ms = round(self.bot.latency * 1000)
        embed = aivor_embed(
            "Ping",
            f"**Gateway (WebSocket):** `{ws_ms}` ms\n\n"
            "Măsoară timpul până la ultimul heartbeat cu Discord (nu e ping-ul tău personal). "
            "Valori mici = conexiune stabilă.\n\n"
            "*Comenzi echivalente:* `/ping` · `!ping` · `a!ping`",
        )
        await hybrid_reply(ctx, embed=embed, ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="aivorping", description="La fel ca /ping — latență bot.")
    async def aivorping(self, ctx: commands.Context):
        await self.ping(ctx)

    @commands.hybrid_command(name="uptime", description="De când rulează botul (de la ultima repornire).")
    async def uptime(self, ctx: commands.Context):
        s = int(time.time() - self.started_at)
        days, rem = divmod(s, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days} zile")
        if hours:
            parts.append(f"{hours} ore")
        parts.append(f"{minutes} min")
        parts.append(f"{secs} sec")
        human = " ".join(parts)
        embed = aivor_embed(
            "Uptime",
            f"Botul Aivor rulează continuu de **{human}** (de la ultima repornire a procesului).\n\n"
            f"*Comenzi echivalente:* `/uptime` · `!uptime` · `a!uptime`",
        )
        await hybrid_reply(ctx, embed=embed, ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(
        name="botinfo",
        description="Ce face Aivor, suport Discord și echipă (fără detalii tehnice).",
    )
    async def botinfo(self, ctx: commands.Context):
        SUPPORT_URL = "https://discord.gg/dXpaSMH6YH"
        me = self.bot.user
        embed = aivor_embed(
            "Aivor — informații bot",
            "**Aivor** este un asistent pentru serverul tău Discord: îți aduce **economie** (bani, magazin, jocuri), "
            "**nivel și XP**, **moderare** și **AutoMod**, **tickete** cu panel, **jurnale** pe canale, plus comenzi "
            "**fun** și **info** (ping, server, utilizator). Comenzile merg cu **/** (slash) sau prefix **`!`** / **`a!`** "
            "unde sunt hybrid.\n\n"
            f"**Panou complet:** `/help` · `!help`",
        )
        if me:
            embed.set_thumbnail(url=me.display_avatar.url)
        embed.add_field(
            name="Suport",
            value=f"Întrebări, ajutor și noutăți: **[Intră pe server]({SUPPORT_URL})**",
            inline=False,
        )
        embed.add_field(
            name="Echipă",
            value="**Aivor team**",
            inline=True,
        )
        embed.add_field(
            name="Prezență",
            value="**56** servere moderate.",
            inline=True,
        )
        await hybrid_reply(ctx, embed=embed, ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="serverinfo", description="Membri, canale, boost, verificare, ID server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        assert g is not None
        embed = aivor_embed(
            f"Server — {g.name}",
            "Detalii despre serverul curent (canalul unde ai rulat comanda).",
        )
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        owner = g.owner
        owner_txt = owner.mention if owner else f"<@{g.owner_id}>"
        created = discord.utils.format_dt(g.created_at, "F") if g.created_at else "—"
        locale = getattr(g, "preferred_locale", None)
        loc_line = f"\n**Limbă preferată:** `{locale}`" if locale else ""
        embed.add_field(
            name="Identitate",
            value=f"**ID:** `{g.id}`\n**Creat:** {created}\n**Proprietar:** {owner_txt}{loc_line}",
            inline=False,
        )
        mc = g.member_count or 0
        txt = len(g.text_channels)
        voc = len(g.voice_channels)
        cats = len(g.categories)
        embed.add_field(
            name="Membri & canale",
            value=f"**Membri:** {mc}\n**Canale text:** {txt}\n**Canale voice:** {voc}\n**Categorii:** {cats}",
            inline=True,
        )
        embed.add_field(
            name="Roluri & conținut",
            value=f"**Roluri:** {len(g.roles)}\n**Emoji:** {len(g.emojis)}\n**Stickere:** {len(g.stickers)}",
            inline=True,
        )
        ver = str(g.verification_level).replace("_", " ").title()
        ecf = str(g.explicit_content_filter).replace("_", " ").title()
        boost_n = g.premium_subscription_count or 0
        tier = g.premium_tier
        embed.add_field(
            name="Boost & siguranță",
            value=f"**Nivel Nitro (tier):** {tier}\n**Boost-uri active:** {boost_n}\n**Verificare intrare:** {ver}\n**Filtru conținut explicit:** {ecf}",
            inline=False,
        )
        if g.description:
            embed.add_field(name="Descriere server", value=g.description[:1024], inline=False)
        embed.add_field(
            name="Comenzi",
            value="`/serverinfo` · `!serverinfo` · `a!serverinfo`",
            inline=False,
        )
        await hybrid_reply(ctx, embed=embed, ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(name="userinfo", description="Cont, intrare pe server, roluri (implicit: tu).")
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, utilizator: discord.Member | None = None):
        t = utilizator or ctx.author
        assert isinstance(t, discord.Member)
        embed = aivor_embed(
            f"Utilizator — {t.display_name}",
            "Profil Discord + ce se vede pe acest server.",
        )
        embed.set_thumbnail(url=t.display_avatar.url)
        nick = t.nick or "*(fără pseudonim)*"
        created = discord.utils.format_dt(t.created_at, "R") if t.created_at else "—"
        joined = discord.utils.format_dt(t.joined_at, "R") if t.joined_at else "—"
        embed.add_field(
            name="Cont",
            value=f"**ID:** `{t.id}`\n**Nume global:** {t}\n**Cont creat:** {created}",
            inline=True,
        )
        embed.add_field(
            name="Pe acest server",
            value=f"**Pseudonim:** {nick}\n**A intrat:** {joined}\n**Culoare rol principal:** {str(t.color) if t.color.value else '—'}",
            inline=True,
        )
        roles = [r for r in t.roles if not r.is_default()]
        roles.sort(key=lambda r: r.position, reverse=True)
        if roles:
            role_str = " ".join(r.mention for r in roles[:20])
            if len(roles) > 20:
                role_str += f"\n*…și încă {len(roles) - 20} roluri*"
        else:
            role_str = "—"
        embed.add_field(name=f"Roluri ({len(roles)})", value=role_str[:1024], inline=False)
        embed.add_field(
            name="Comenzi",
            value="`/userinfo` · `!userinfo` · `a!userinfo` — adaugă `@membru` pentru altcineva",
            inline=False,
        )
        await hybrid_reply(ctx, embed=embed, ephemeral=bool(ctx.interaction))


async def setup(bot: commands.Bot):
    await bot.add_cog(Core(bot))
