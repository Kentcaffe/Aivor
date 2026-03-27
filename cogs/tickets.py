from __future__ import annotations

import asyncio
import io
import re
from datetime import UTC, datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils.aivor_embeds import aivor_embed
from utils.db import execute, fetch_one, get_guild_settings, update_guild_settings
from utils.logger import build_log_embed
from views.ticket_views import TicketCloseConfirmView, TicketPanelView, TicketStaffView

TICKET_TYPE_LABELS: dict[str, str] = {
    "support": "Support",
    "report": "Report",
    "partnership": "Partnership",
    "other": "Other",
}


def _slug_channel_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9\-]", "", name.lower().replace(" ", "-"))[:32]
    return s or "user"


class Tickets(commands.Cog):
    """Sistem tickete: panou persistent, un ticket activ/user, transcript, log."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_view(TicketPanelView(self))
        self.bot.add_view(TicketStaffView(self))

    def _topic_owner(self, channel: discord.TextChannel) -> int | None:
        t = (channel.topic or "").strip()
        if not t.startswith("ticket_owner:"):
            return None
        try:
            return int(t.split(":", 1)[1].strip())
        except ValueError:
            return None

    def _is_ticket_channel(self, channel: discord.abc.GuildChannel | None) -> bool:
        return isinstance(channel, discord.TextChannel) and self._topic_owner(channel) is not None

    def _is_ticket_staff(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
            return True
        cfg = get_guild_settings(member.guild.id)
        rid = cfg.get("ticket_staff_role_id")
        if isinstance(rid, int) and member.get_role(rid):
            return True
        return False

    def _can_close_ticket(self, user: discord.abc.User, channel: discord.TextChannel) -> bool:
        owner_id = self._topic_owner(channel)
        if owner_id is None:
            return False
        if user.id == owner_id:
            return True
        if not isinstance(user, discord.Member):
            return False
        return self._is_ticket_staff(user)

    def _can_manage_ticket(self, member: discord.Member) -> bool:
        return self._is_ticket_staff(member)

    def _apply_staff_overwrites(
        self,
        guild: discord.Guild,
        base: dict[discord.abc.Snowflake, discord.PermissionOverwrite],
    ) -> None:
        cfg = get_guild_settings(guild.id)
        rid = cfg.get("ticket_staff_role_id")
        if isinstance(rid, int) and (role := guild.get_role(rid)):
            base[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )
            return
        for role in guild.roles:
            if role.is_default():
                continue
            if role.managed and role != guild.me:
                continue
            if role.permissions.manage_channels or role.permissions.administrator:
                base[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                )

    async def get_ticket_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        import os

        target = os.getenv("TICKET_CATEGORY_NAME", "Tickets")
        cfg = get_guild_settings(guild.id)
        category_id = cfg.get("ticket_category_id")
        if isinstance(category_id, int):
            ch = guild.get_channel(category_id)
            if isinstance(ch, discord.CategoryChannel):
                return ch
        for cat in guild.categories:
            if cat.name.lower() == target.lower():
                update_guild_settings(guild.id, ticket_category_id=cat.id)
                return cat
        category = await guild.create_category(target)
        update_guild_settings(guild.id, ticket_category_id=category.id)
        return category

    async def on_ticket_type_selected(self, interaction: discord.Interaction, ticket_type: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda e doar pe server.", ephemeral=True)
            return
        execute(
            """
            INSERT OR REPLACE INTO ticket_draft(guild_id, user_id, ticket_type, updated_at)
            VALUES(?, ?, ?, strftime('%s','now'))
            """,
            (interaction.guild.id, interaction.user.id, ticket_type),
        )
        label = TICKET_TYPE_LABELS.get(ticket_type, ticket_type)
        await interaction.response.send_message(
            f"✅ Tip setat: **{label}**. Apasă **Deschide ticket** pentru a crea canalul.",
            ephemeral=True,
        )

    async def open_ticket_from_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda e doar pe server.", ephemeral=True)
            return
        row = fetch_one(
            "SELECT ticket_type FROM ticket_draft WHERE guild_id = ? AND user_id = ?",
            (interaction.guild.id, interaction.user.id),
        )
        if not row:
            await interaction.response.send_message(
                "❌ Alege mai întâi tipul din meniu (Support, Report, Partnership, Other).",
                ephemeral=True,
            )
            return
        tt = str(row["ticket_type"])
        await self.create_ticket_for_user(interaction, ticket_type=tt)

    async def create_ticket_for_user(self, interaction: discord.Interaction, *, ticket_type: str) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Comanda e doar pe server.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("Eroare membru.", ephemeral=True)
            return
        channel, err = await self._create_ticket_channel(guild, member, ticket_type)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return
        assert channel is not None
        execute(
            "DELETE FROM ticket_draft WHERE guild_id = ? AND user_id = ?",
            (guild.id, member.id),
        )
        await self._log_embed(
            guild,
            "Ticket deschis",
            f"**Tip:** {TICKET_TYPE_LABELS.get(ticket_type, ticket_type)}\n**Utilizator:** {member.mention}\n**Canal:** {channel.mention}",
            discord.Color.green(),
        )
        await interaction.response.send_message(f"✅ Ticket creat: {channel.mention}", ephemeral=True)

    async def _create_ticket_channel(
        self,
        guild: discord.Guild,
        member: discord.Member,
        ticket_type: str,
    ) -> tuple[discord.TextChannel | None, str | None]:
        existing = fetch_one(
            """
            SELECT channel_id FROM tickets
            WHERE guild_id = ? AND owner_user_id = ? AND status = 'open'
            ORDER BY id DESC LIMIT 1
            """,
            (guild.id, member.id),
        )
        if existing:
            ch = guild.get_channel(int(existing["channel_id"]))
            if isinstance(ch, discord.TextChannel):
                return None, f"Ai deja un ticket deschis: {ch.mention}"

        category = await self.get_ticket_category(guild)
        bot_member = guild.me
        if bot_member is None:
            return None, "Bot indisponibil."

        slug = _slug_channel_name(member.display_name)
        prefix = ticket_type[:12]
        channel_name = f"{prefix}-{slug}"[:90]

        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            ),
            bot_member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
        }
        self._apply_staff_overwrites(guild, overwrites)

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"ticket_owner:{member.id}",
        )
        label = TICKET_TYPE_LABELS.get(ticket_type, ticket_type)
        embed = aivor_embed(
            f"Ticket — {label}",
            "Un membru staff te va prelua curând.\n"
            "• **Revendică** — preia ticketul\n"
            "• **Închide ticket** — confirmare, apoi transcript și ștergere canal\n"
            "• În chat: `!close` `!add` `!remove` (prefix `!` sau `a!`)",
        )
        await channel.send(content=member.mention, embed=embed, view=TicketStaffView(self))
        execute(
            """
            INSERT INTO tickets(guild_id, owner_user_id, channel_id, ticket_type, status, created_at)
            VALUES(?, ?, ?, ?, 'open', strftime('%s','now'))
            """,
            (guild.id, member.id, channel.id, ticket_type),
        )
        return channel, None

    async def _log_embed(self, guild: discord.Guild, title: str, description: str, color: discord.Color) -> None:
        logging_cog = self.bot.get_cog("LoggingCog")
        if logging_cog and hasattr(logging_cog, "send_log"):
            embed = build_log_embed(title, description, color)
            await logging_cog.send_log(guild, embed, "ticket")

    async def claim_ticket_button(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Acțiune invalidă.", ephemeral=True)
            return
        if not self._is_ticket_channel(interaction.channel):
            await interaction.response.send_message("Nu e un canal ticket.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not self._can_manage_ticket(interaction.user):
            await interaction.response.send_message("Doar staff-ul poate revendica.", ephemeral=True)
            return
        execute(
            "UPDATE tickets SET claimed_by = ? WHERE guild_id = ? AND channel_id = ? AND status = 'open'",
            (interaction.user.id, interaction.guild.id, interaction.channel.id),
        )
        await interaction.response.send_message(f"📌 Ticket revendicat de {interaction.user.mention}.")

    async def begin_close_confirmation(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Acțiune invalidă.", ephemeral=True)
            return
        if not self._is_ticket_channel(interaction.channel):
            await interaction.response.send_message("Nu e un canal ticket.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not self._can_close_ticket(interaction.user, interaction.channel):
            await interaction.response.send_message("Nu poți închide acest ticket.", ephemeral=True)
            return
        await interaction.response.send_message(
            content="⚠️ **Confirmi închiderea ticketului?** Se generează transcriptul, apoi canalul se șterge.",
            view=TicketCloseConfirmView(self, interaction.channel.id),
        )

    async def confirm_close_after_button(self, interaction: discord.Interaction, channel_id: int) -> None:
        if not interaction.guild or interaction.channel is None or interaction.channel.id != channel_id:
            await interaction.response.send_message("Canal invalid.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Canal invalid.", ephemeral=True)
            return
        if not self._is_ticket_channel(interaction.channel):
            await interaction.response.send_message("Nu e ticket.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not self._can_close_ticket(interaction.user, interaction.channel):
            await interaction.response.send_message("Nu poți închide acest ticket.", ephemeral=True)
            return
        await interaction.response.defer()
        channel = interaction.channel
        await self._finalize_ticket_close(interaction.guild, channel, interaction.user)

    async def _finalize_ticket_close(self, guild: discord.Guild, channel: discord.TextChannel, closed_by: discord.abc.User) -> None:
        await channel.send("🔒 **Ticketul se închide în 5 secunde.** Se generează transcriptul…")
        transcript = await self._build_transcript(channel)
        await self._send_transcript_to_log(guild, channel, closed_by, transcript)
        execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = strftime('%s','now')
            WHERE guild_id = ? AND channel_id = ? AND status = 'open'
            """,
            (guild.id, channel.id),
        )
        await self._log_embed(
            guild,
            "Ticket închis",
            f"**Canal:** `{channel.name}`\n**Închis de:** {closed_by.mention}",
            discord.Color.red(),
        )
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket închis de {closed_by}")
        except discord.HTTPException:
            pass

    async def _build_transcript(self, channel: discord.TextChannel) -> str:
        lines: list[str] = []
        lines.append(f"Transcript ticket — #{channel.name}")
        lines.append(f"Server: {channel.guild.name} ({channel.guild.id})")
        lines.append(f"Canal: {channel.id}")
        lines.append(f"Generat: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append("=" * 60)
        async for msg in channel.history(limit=None, oldest_first=True):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = (msg.content or "").replace("\n", " / ")
            lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {content}")
            if msg.attachments:
                for a in msg.attachments:
                    lines.append(f"    ↳ fișier: {a.filename} | {a.url}")
            if msg.embeds:
                for em in msg.embeds:
                    et = (em.title or "") + " — " + (em.description or "")
                    lines.append(f"    ↳ embed: {et[:400]}")
            if msg.stickers:
                for st in msg.stickers:
                    lines.append(f"    ↳ sticker: {st.name}")
        return "\n".join(lines)

    async def _send_transcript_to_log(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        closed_by: discord.abc.User,
        transcript: str,
    ) -> None:
        cfg = get_guild_settings(guild.id)
        log_id = cfg.get("ticket_log_channel_id") or cfg.get("log_channel_id")
        if not log_id:
            return
        log_ch = guild.get_channel(log_id)
        if not isinstance(log_ch, discord.TextChannel):
            return
        owner_id = self._topic_owner(channel) or 0
        row = fetch_one(
            "SELECT ticket_type FROM tickets WHERE guild_id = ? AND channel_id = ?",
            (guild.id, channel.id),
        )
        ttype = str(row["ticket_type"]) if row else "unknown"
        label = TICKET_TYPE_LABELS.get(ttype, ttype)
        embed = build_log_embed(
            "Transcript ticket",
            f"**Tip:** {label}\n**Canal:** `{channel.name}`\n**Owner ID:** `{owner_id}`\n**Închis de:** {closed_by.mention}",
            discord.Color.blurple(),
        )
        raw = transcript.encode("utf-8")
        if len(raw) > 7_900_000:
            transcript = transcript[:4_000_000] + "\n… [trunchiat]"
            raw = transcript.encode("utf-8")
        fp = io.BytesIO(raw)
        fp.seek(0)
        fname = f"transcript-{channel.id}-{int(datetime.now(UTC).timestamp())}.txt"
        try:
            await log_ch.send(embed=embed, file=discord.File(fp, filename=fname))
        except discord.HTTPException:
            transcript_dir = Path(__file__).resolve().parent.parent / "data" / "transcripts"
            transcript_dir.mkdir(parents=True, exist_ok=True)
            p = transcript_dir / f"{guild.id}_{channel.id}.txt"
            p.write_text(transcript, encoding="utf-8")

    @commands.hybrid_command(name="close", aliases=["ticket_close"], description="Începe închiderea ticketului; confirmi în canal.")
    async def close_cmd(self, ctx: commands.Context) -> None:
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel) or not self._is_ticket_channel(ctx.channel):
            await ctx.reply("Folosește comanda într-un canal ticket.")
            return
        if not isinstance(ctx.author, discord.Member) or not self._can_close_ticket(ctx.author, ctx.channel):
            await ctx.reply("Nu poți închide acest ticket.")
            return
        if ctx.interaction:
            await ctx.interaction.response.send_message(
                "Mesajul de confirmare a fost trimis în ticket.",
                ephemeral=True,
            )
        await ctx.channel.send(
            content="⚠️ **Confirmi închiderea ticketului?**",
            view=TicketCloseConfirmView(self, ctx.channel.id),
        )
        if not ctx.interaction:
            await ctx.reply("👇 Confirmă mai jos.", mention_author=False)

    async def _add_remove_impl(self, ctx: commands.Context, membru: discord.Member, add: bool) -> None:
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel) or not self._is_ticket_channel(ctx.channel):
            await ctx.reply("Comanda merge doar într-un canal ticket.")
            return
        if not isinstance(ctx.author, discord.Member) or not self._can_manage_ticket(ctx.author):
            await ctx.reply("Doar staff-ul poate folosi comanda.")
            return
        if add:
            await ctx.channel.set_permissions(
                membru,
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
            )
            await ctx.reply(f"✅ {membru.mention} a fost adăugat în ticket.")
        else:
            owner_id = self._topic_owner(ctx.channel)
            if membru.id == owner_id:
                await ctx.reply("❌ Nu poți scoate proprietarul ticketului.")
                return
            await ctx.channel.set_permissions(membru, overwrite=None)
            await ctx.reply(f"✅ {membru.mention} a fost scos din ticket.")

    @commands.command(name="add")
    @commands.guild_only()
    async def add_prefix(self, ctx: commands.Context, membru: discord.Member) -> None:
        await self._add_remove_impl(ctx, membru, True)

    @commands.command(name="remove")
    @commands.guild_only()
    async def remove_prefix(self, ctx: commands.Context, membru: discord.Member) -> None:
        await self._add_remove_impl(ctx, membru, False)

    @commands.hybrid_command(name="ticket_add", description="Staff: adaugă un membru în canalul ticket (permisiuni).")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_add(self, ctx: commands.Context, membru: discord.Member) -> None:
        await self._add_remove_impl(ctx, membru, True)

    @commands.hybrid_command(name="ticket_remove", description="Scoate un membru din ticket.")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_remove(self, ctx: commands.Context, membru: discord.Member) -> None:
        await self._add_remove_impl(ctx, membru, False)

    @commands.hybrid_command(name="ticketpanel", description="Admin: trimite panoul cu tipuri de ticket și buton deschidere.")
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx: commands.Context) -> None:
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.reply("Folosește comanda într-un canal text pe server.")
            return
        embed = aivor_embed(
            "Tickete — Aivor",
            "1. Alege **tipul** din meniu (Support, Report, Partnership, Other).\n"
            "2. Apasă **Deschide ticket** — se creează un canal privat în categoria **Tickets**.\n"
            "Un singur ticket deschis per utilizator. Staff vede ticketul după rol sau permisiuni.",
        )
        await ctx.channel.send(embed=embed, view=TicketPanelView(self))
        await ctx.reply("✅ Panel trimis.", ephemeral=bool(ctx.interaction))

    @commands.hybrid_command(
        name="setticketstaff",
        description="Admin: setează rolul staff pentru tickete; fără rol folosește Manage Channels.",
    )
    @commands.has_permissions(administrator=True)
    @app_commands.describe(rol="Lasă gol ca să resetezi rolul dedicat.")
    async def set_ticket_staff(self, ctx: commands.Context, rol: discord.Role | None = None) -> None:
        if not ctx.guild:
            return
        if rol is None:
            update_guild_settings(ctx.guild.id, ticket_staff_role_id=None)
            await ctx.reply("✅ Rol staff ticket eliminat — se folosesc rolurile cu Manage Channels.")
            return
        update_guild_settings(ctx.guild.id, ticket_staff_role_id=rol.id)
        await ctx.reply(f"✅ Rol staff ticket: {rol.mention}")

    @commands.hybrid_command(name="ticket_claim", description="Staff: marchezi ticketul ca preluat de tine.")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_claim(self, ctx: commands.Context) -> None:
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel) or not self._is_ticket_channel(ctx.channel):
            await ctx.reply("Comanda merge doar într-un canal ticket.")
            return
        if not isinstance(ctx.author, discord.Member) or not self._can_manage_ticket(ctx.author):
            await ctx.reply("Doar staff.")
            return
        execute(
            "UPDATE tickets SET claimed_by = ? WHERE guild_id = ? AND channel_id = ? AND status = 'open'",
            (ctx.author.id, ctx.guild.id, ctx.channel.id),
        )
        await ctx.reply(f"✅ Ticket revendicat de {ctx.author.mention}.")

    @commands.hybrid_command(name="ticket_reopen", description="Staff: deschide ticket nou după unul închis (dacă există istoric).")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_reopen(self, ctx: commands.Context, membru: discord.Member) -> None:
        if not ctx.guild:
            return
        prev = fetch_one(
            "SELECT id FROM tickets WHERE guild_id = ? AND owner_user_id = ? AND status = 'closed' ORDER BY closed_at DESC LIMIT 1",
            (ctx.guild.id, membru.id),
        )
        if not prev:
            await ctx.reply("❌ Nu există ticket închis anterior pentru acest membru.")
            return
        channel, err = await self._create_ticket_channel(ctx.guild, membru, "other")
        if err:
            await ctx.reply(f"❌ {err}")
            return
        assert channel is not None
        await self._log_embed(
            ctx.guild,
            "Ticket redeschis",
            f"**Membru:** {membru.mention}\n**Canal:** {channel.mention}\n**De:** {ctx.author.mention}",
            discord.Color.blue(),
        )
        await ctx.reply(f"✅ Ticket nou: {channel.mention}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
