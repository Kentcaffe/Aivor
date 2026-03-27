from __future__ import annotations

from typing import Optional

import discord

from utils.aivor_embeds import FOOTER
from utils.db import get_guild_settings, update_guild_settings


def get_log_channel_id(guild_id: int) -> Optional[int]:
    cfg = get_guild_settings(guild_id)
    channel_id = cfg.get("log_channel_id")
    if isinstance(channel_id, int):
        return channel_id
    return None


def set_log_channel_id(guild_id: int, channel_id: int) -> None:
    update_guild_settings(guild_id, log_channel_id=channel_id)


def build_log_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER)
    embed.timestamp = discord.utils.utcnow()
    return embed
