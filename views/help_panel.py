"""Panou unic de ajutor Aivor — embed + Select; conținut public vs staff moderare."""

from __future__ import annotations

import discord
from discord.ext import commands

from utils.aivor_embeds import AIVOR_COLOR, FOOTER
from utils.help_data import (
    CATEGORY_META,
    all_category_keys_for_user,
    category_embed_parts,
)


def _avatar_url(bot: commands.Bot) -> str:
    u = bot.user
    return u.display_avatar.url if u else ""


def _footer_extra(suffix: str = "") -> str:
    base = f"{FOOTER} · centrul de comandă"
    return f"{base}{suffix}"


def build_overview_embed(bot: commands.Bot, *, is_staff: bool) -> discord.Embed:
    """Vedere principală: grid doar categorii permise userului."""
    icon = _avatar_url(bot)
    keys = all_category_keys_for_user(is_staff)
    staff_note = ""
    if is_staff:
        staff_note = "\n> *Ai acces și la **Moderare**, **AutoMod**, **Tickete** și **Jurnale** — aceleași reguli slash/prefix.*"
    else:
        staff_note = "\n> *Modulurile pentru staff apar doar dacă ai permisiuni de moderare sau configurare pe server.*"

    embed = discord.Embed(
        color=AIVOR_COLOR,
        description=(
            "**Bun venit.** Mai jos ai **modulele** Aivor — fiecare cu lista de comenzi și *ce face fiecare*.\n\n"
            "**Două moduri de a comanda** (unde comanda e *hybrid*):\n"
            "· **Slash** — ` / ` în chat și alegi comanda din meniul Discord\n"
            "· **Prefix** — ` ! ` sau ` a! ` în fața numelui (ex.: `!daily`)\n"
            f"{staff_note}\n\n"
            "◆ **Meniul derulant** — selectezi modulul; mesajul se actualizează aici.\n"
            "◆ **Comandă rapidă** — `!help economie` · `a!help level` · `/help fun` (aceeași structură).\n\n"
            "_Un singur mesaj. Totul rămâne în acest panou._"
        ),
    )
    embed.set_author(name="Aivor · ghid comenzi", icon_url=icon)
    embed.set_thumbnail(url=icon)

    for row_start in range(0, len(keys), 3):
        for j in range(3):
            idx = row_start + j
            if idx >= len(keys):
                break
            key = keys[idx]
            label, emoji, blurb = CATEGORY_META[key]
            name = f"{emoji} **{label}**"
            value = (
                f"{blurb}\n"
                f"```\n!help {key}\na!help {key}\n/help {key}\n```"
            )
            embed.add_field(name=name, value=value, inline=True)

    embed.set_footer(text=_footer_extra())
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_category_embed(bot: commands.Bot, key: str, *, is_staff: bool) -> discord.Embed:
    """Detaliu modul — câmpuri structurate + intro; filtrat după permisiuni."""
    label, emoji, _ = CATEGORY_META[key]
    icon = _avatar_url(bot)
    desc, fields = category_embed_parts(key, is_staff=is_staff)

    embed = discord.Embed(
        color=AIVOR_COLOR,
        title=f"{emoji}  {label}",
        description=desc,
    )
    embed.set_author(name="Aivor · modul selectat", icon_url=icon)
    embed.set_thumbnail(url=icon)

    for fname, fval in fields:
        v = fval if len(fval) <= 1024 else fval[:1020] + "…"
        n = fname if len(fname) <= 256 else fname[:253] + "…"
        embed.add_field(name=n, value=v, inline=False)

    embed.set_footer(text=_footer_extra(f" · {label}"))
    embed.timestamp = discord.utils.utcnow()
    return embed


class _HelpNavSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, *, is_staff: bool) -> None:
        self.bot = bot
        self.is_staff = is_staff
        opts: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Panou principal",
                value="overview",
                emoji="🏠",
                description="Revenire la rezumat",
            ),
        ]
        for cat_key in all_category_keys_for_user(is_staff):
            lbl, em, blurb = CATEGORY_META[cat_key]
            opts.append(
                discord.SelectOption(
                    label=lbl[:100],
                    value=cat_key,
                    emoji=em,
                    description=blurb[:100],
                )
            )
        super().__init__(
            placeholder="Alege modulul…",
            min_values=1,
            max_values=1,
            options=opts,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        key = self.values[0]
        if key == "overview":
            embed = build_overview_embed(self.bot, is_staff=self.is_staff)
        else:
            embed = build_category_embed(self.bot, key, is_staff=self.is_staff)
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpPanelView(discord.ui.View):
    """Un mesaj, un panou — meniul reîncarcă același embed."""

    def __init__(self, bot: commands.Bot, *, is_staff: bool) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.is_staff = is_staff
        self.add_item(_HelpNavSelect(bot, is_staff=is_staff))
