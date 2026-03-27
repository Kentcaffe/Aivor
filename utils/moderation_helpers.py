"""Verificări ierarhie roluri pentru moderare."""

from __future__ import annotations

import discord


def can_moderate(actor: discord.Member, target: discord.Member) -> bool:
    if target.guild.owner_id == target.id:
        return False
    if actor.id == target.guild.owner_id:
        return True
    return actor.top_role > target.top_role
