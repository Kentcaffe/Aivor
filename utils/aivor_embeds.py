"""Branding și embed-uri unitare pentru Aivor."""

from __future__ import annotations

from typing import Any

import discord

# Identitate vizuală Aivor (mov închis / accent)
AIVOR_COLOR = discord.Color.from_rgb(88, 101, 242)
FOOTER = "Aivor · asistent premium pentru serverul tău"


def aivor_embed(
    title: str,
    description: str = "",
    *,
    color: discord.Color | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or AIVOR_COLOR,
    )
    embed.set_footer(text=FOOTER)
    embed.timestamp = discord.utils.utcnow()
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed
