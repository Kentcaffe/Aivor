from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils.db import get_guild_settings, update_guild_settings
from utils.logger import build_log_embed, get_log_channel_id, set_log_channel_id


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_log(self, guild: discord.Guild, embed: discord.Embed, category: str = "general") -> None:
        cfg = get_guild_settings(guild.id)
        mapped = {
            "general": cfg.get("log_channel_id"),
            "mod": cfg.get("mod_log_channel_id") or cfg.get("log_channel_id"),
            "ticket": cfg.get("ticket_log_channel_id") or cfg.get("log_channel_id"),
            "automod": cfg.get("automod_log_channel_id") or cfg.get("log_channel_id"),
        }
        channel_id = mapped.get(category) or get_log_channel_id(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            await channel.send(embed=embed)

    @app_commands.command(name="setlogchannel", description="Admin: canal pentru evenimente generale și log-uri implicite.")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(canal="Canalul unde vor fi trimise log-urile")
    async def set_log_channel(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda poate fi folosită doar pe server.", ephemeral=True)
            return
        set_log_channel_id(interaction.guild.id, canal.id)
        embed = build_log_embed("Canal logs setat", f"Canal nou: {canal.mention}", discord.Color.green())
        await interaction.response.send_message("✅ Canalul de logs a fost setat cu succes.", ephemeral=True)
        await self.send_log(interaction.guild, embed)

    @app_commands.command(name="setmodlog", description="Admin: canal unde se scriu acțiunile de moderare (ban, kick…).")
    @app_commands.default_permissions(administrator=True)
    async def set_mod_log(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda poate fi folosită doar pe server.", ephemeral=True)
            return
        update_guild_settings(interaction.guild.id, mod_log_channel_id=canal.id)
        await interaction.response.send_message("✅ Canalul de log moderare a fost setat.", ephemeral=True)

    @app_commands.command(name="setticketlog", description="Admin: canal pentru evenimente legate de tickete.")
    @app_commands.default_permissions(administrator=True)
    async def set_ticket_log(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda poate fi folosită doar pe server.", ephemeral=True)
            return
        update_guild_settings(interaction.guild.id, ticket_log_channel_id=canal.id)
        await interaction.response.send_message("✅ Canalul de log ticket a fost setat.", ephemeral=True)

    @app_commands.command(name="setautomodlog", description="Admin: canal pentru acțiuni și avertismente AutoMod.")
    @app_commands.default_permissions(administrator=True)
    async def set_automod_log(self, interaction: discord.Interaction, canal: discord.TextChannel) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Comanda poate fi folosită doar pe server.", ephemeral=True)
            return
        update_guild_settings(interaction.guild.id, automod_log_channel_id=canal.id)
        await interaction.response.send_message("✅ Canalul de log automod a fost setat.", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = build_log_embed("Ban aplicat", f"Utilizatorul `{user}` a fost banat.", discord.Color.red())
        await self.send_log(guild, embed, "mod")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = build_log_embed(
            "Membru nou",
            f"{member.mention} (`{member}`) a intrat pe server.",
            discord.Color.green(),
        )
        await self.send_log(member.guild, embed, "general")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = build_log_embed(
            "Membru plecat",
            f"`{member}` a părăsit serverul.",
            discord.Color.orange(),
        )
        await self.send_log(member.guild, embed, "general")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return
        embed = build_log_embed("Mesaj editat", "", discord.Color.blue())
        embed.add_field(name="Autor", value=str(after.author), inline=False)
        embed.add_field(name="Canal", value=after.channel.mention, inline=False)
        embed.add_field(name="Înainte", value=before.content[:900] or "(gol)", inline=False)
        embed.add_field(name="După", value=after.content[:900] or "(gol)", inline=False)
        await self.send_log(after.guild, embed, "general")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = build_log_embed("Mesaj șters", "", discord.Color.dark_red())
        embed.add_field(name="Autor", value=str(message.author), inline=False)
        embed.add_field(name="Canal", value=message.channel.mention, inline=False)
        embed.add_field(name="Conținut", value=message.content[:1000] or "(gol)", inline=False)
        await self.send_log(message.guild, embed, "general")


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))