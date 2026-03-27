from discord.ext import commands


def is_guild_only():
    async def predicate(ctx: commands.Context) -> bool:
        return ctx.guild is not None
    return commands.check(predicate)