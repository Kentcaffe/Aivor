from __future__ import annotations

import asyncio
import os
import socket

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils.db import init_db, migrate_json_to_sqlite
from utils.error_log import log_exception
from utils.safe_reply import is_benign_message_reference_error
from utils.storage import ensure_data_files


def get_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    # „a!” înainte de „!” — potrivire stabilă pentru prefixe de lungimi diferite
    return commands.when_mentioned_or("a!", "!")(bot, message)


_SINGLETON_LOCK_SOCK: socket.socket | None = None


def _acquire_single_instance_lock() -> None:
    """O singură instanță bot pe mașină — evită mesaje duble (ex. două terminale cu bot.py)."""
    global _SINGLETON_LOCK_SOCK
    port_raw = os.getenv("AIVOR_LOCK_PORT", "45123")
    try:
        port = int(port_raw)
    except ValueError:
        port = 45123
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
    except OSError as e:
        s.close()
        raise RuntimeError(
            "Rulează deja o instanță Aivor (sau portul local e ocupat). "
            "Închide celălalt terminal / proces Python care are bot.py, apoi încearcă din nou. "
            f"(lock 127.0.0.1:{port}: {e})"
        ) from None
    _SINGLETON_LOCK_SOCK = s


COGS = (
    "cogs.core",
    "cogs.logging_cog",
    "cogs.economy",
    "cogs.leveling",
    "cogs.moderation",
    "cogs.automod",
    "cogs.tickets",
    "cogs.fun",
    "cogs.setup_cog",
)


class RomanianBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix=get_prefix, intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            log_exception("slash_tree", error)
            print(f"[SLASH ERROR] {error}")
            msg = "❌ A apărut o eroare la această comandă. Încearcă din nou."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            except discord.HTTPException:
                pass

        self.tree.on_error = on_tree_error
        ensure_data_files()
        init_db()
        migrate_json_to_sqlite()
        for extension in COGS:
            await self.load_extension(extension)
        guild_id_raw = os.getenv("GUILD_ID")
        if guild_id_raw and guild_id_raw.isdigit():
            guild_obj = discord.Object(id=int(guild_id_raw))
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            print(f"[BOT] Slash sync rapid pe guild {guild_id_raw}")
        await self.tree.sync()

    async def on_ready(self) -> None:
        if self.user:
            print(f"[BOT] Conectat ca {self.user} (ID: {self.user.id})")
        hp = [c.name for c in self.commands if c.name == "help"]
        slash_help = sum(1 for c in self.tree.walk_commands() if c.name == "help")
        if len(hp) != 1 or slash_help != 1:
            print(f"[BOT][ATENȚIE] help prefix={len(hp)} slash_help în tree={slash_help} (așteptat 1+1). Resync slash după modificări.")
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="Aivor | /help"),
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CheckFailure):
            try:
                await ctx.reply("❌ Nu ai permisiunea sau nu poți folosi comanda aici.", ephemeral=bool(ctx.interaction))
            except discord.HTTPException:
                pass
            return
        cmd_name = ctx.command.name if ctx.command else "unknown"
        mode = "slash" if ctx.interaction else "prefix"
        if is_benign_message_reference_error(error):
            log_exception(f"{mode}.{cmd_name}.reference_glitch", error)
            print(f"[CMD ERROR] {error} (mesaj user omis — 50035 message_reference)")
            return
        log_exception(f"{mode}.{cmd_name}", error)
        print(f"[CMD ERROR] {error}")
        try:
            await ctx.reply("❌ Eroare la executarea comenzii.", ephemeral=bool(ctx.interaction))
        except discord.HTTPException:
            if ctx.channel:
                try:
                    await ctx.channel.send("❌ Eroare la executarea comenzii.")
                except discord.HTTPException:
                    pass


async def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Variabila DISCORD_TOKEN nu este setată în .env.")

    _acquire_single_instance_lock()
    print(f"[BOT] PID {os.getpid()} — o singură instanță locală (dacă vezi două răspunsuri, caută alt proces Python sau alt PC cu același token).")

    bot = RomanianBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
