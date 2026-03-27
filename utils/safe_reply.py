"""Răspunsuri la comenzi hybrid când interacțiunea slash nu mai e validă (10062)."""

from __future__ import annotations

import discord
from discord.ext import commands


def is_benign_message_reference_error(exc: BaseException) -> bool:
    """True doar pentru 50035 message_reference pe primul nivel (nu ascunde lanțuri mixte)."""

    def _match(e: BaseException) -> bool:
        if not isinstance(e, discord.HTTPException) or getattr(e, "code", None) != 50035:
            return False
        tx = (getattr(e, "text", None) or str(e)).lower()
        return "message_reference" in tx

    if _match(exc):
        return True
    orig = getattr(exc, "original", None)
    if orig is not None and _match(orig):
        return True
    return False


def _strip_message_reference(kwargs: dict) -> None:
    kwargs.pop("reference", None)
    kwargs.pop("reply_to", None)


async def hybrid_reply(ctx: commands.Context, **kwargs) -> discord.Message:
    """
    Prefix: reply la mesajul userului. Slash: doar ctx.send (fără reply) — altfel 10062 + fallback
    cu reference invalid poate da 50035 (Unknown message).
    """
    if ctx.interaction is not None:
        _strip_message_reference(kwargs)
        try:
            return await ctx.send(**kwargs)
        except discord.HTTPException as e:
            code = getattr(e, "code", None)
            text = (getattr(e, "text", None) or str(e)).lower()
            bad_ref = code == 50035 and "message_reference" in text
            if ctx.channel is None:
                raise
            if code == 10062 or bad_ref:
                kwargs.pop("ephemeral", None)
                _strip_message_reference(kwargs)
                return await ctx.channel.send(**kwargs)
            raise
    try:
        return await ctx.reply(**kwargs)
    except discord.HTTPException as e:
        code = getattr(e, "code", None)
        text = (getattr(e, "text", None) or str(e)).lower()
        bad_ref = code == 50035 and "message_reference" in text
        if ctx.channel is None:
            raise
        if code == 10062 or bad_ref:
            kwargs.pop("ephemeral", None)
            _strip_message_reference(kwargs)
            return await ctx.channel.send(**kwargs)
        raise
