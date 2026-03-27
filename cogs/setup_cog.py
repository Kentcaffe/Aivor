from __future__ import annotations

import discord
from discord.ext import commands

from utils.aivor_embeds import aivor_embed


class SetupCog(commands.Cog):
    """Wizard scurt de configurare inițială."""

    @commands.hybrid_command(name="setup", description="Ghid pas cu pas: ce să configurezi pe server (admin).")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx: commands.Context):
        embed = aivor_embed(
            "Configurare Aivor",
            "**Pași recomandați:**\n"
            "1. Log-uri: `/setlogchannel`, apoi `/setmodlog`, `/setticketlog`, `/setautomodlog`\n"
            "2. AutoMod: `/automod_status` — ajustează cu `/automod_set`, `/blacklist_add`, `/automod_prag`\n"
            "3. Tickete: `/setticketlog`, opțional `/setticketstaff` (rol dedicat staff), apoi `/ticketpanel` într-un canal vizibil\n"
            "4. Level: `/setlevelrole`, `/setlevelreward`, `/xpconfig`\n"
            "5. Economie: utilizatorii pot folosi `/daily`, `/shop`, `/profil_economie`\n\n"
            "**Prefix:** `!` și `a!` — `!help` sau `/help` pentru listă.",
        )
        await ctx.reply(embed=embed, ephemeral=bool(ctx.interaction))


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCog(bot))
