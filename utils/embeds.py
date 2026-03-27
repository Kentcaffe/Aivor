import discord


def ok_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=discord.Color.green())
    embed.timestamp = discord.utils.utcnow()
    return embed


def error_embed(description: str) -> discord.Embed:
    embed = discord.Embed(title="Eroare", description=description, color=discord.Color.red())
    embed.timestamp = discord.utils.utcnow()
    return embed


def info_embed(title: str, description: str) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    embed.timestamp = discord.utils.utcnow()
    return embed