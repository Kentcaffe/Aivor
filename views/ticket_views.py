"""UI persistent pentru tickete Aivor (custom_id fix — supraviețuiește restart)."""

from __future__ import annotations

from typing import Any

import discord
from discord import ui


class TicketTypeSelect(ui.Select):
    """Meniu tip ticket: Support, Report, Partnership, Other."""

    def __init__(self, cog: Any) -> None:
        self.cog = cog
        options = [
            discord.SelectOption(label="Support", value="support", emoji="🛟", description="Ajutor general"),
            discord.SelectOption(label="Report", value="report", emoji="🚨", description="Raportări / probleme"),
            discord.SelectOption(label="Partnership", value="partnership", emoji="🤝", description="Colaborări"),
            discord.SelectOption(label="Other", value="other", emoji="📩", description="Altele"),
        ]
        super().__init__(
            custom_id="aivor_ticket_type_select",
            placeholder="Alege tipul ticketului…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        t = self.values[0]
        await self.cog.on_ticket_type_selected(interaction, t)


class OpenTicketButton(ui.Button):
    def __init__(self, cog: Any) -> None:
        super().__init__(
            label="Deschide ticket",
            style=discord.ButtonStyle.success,
            emoji="🎫",
            custom_id="aivor_ticket_open_btn",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.open_ticket_from_button(interaction)


class TicketPanelView(ui.View):
    """Panou persistent: dropdown + buton Deschide."""

    def __init__(self, cog: Any) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(TicketTypeSelect(cog))
        self.add_item(OpenTicketButton(cog))


class TicketStaffView(ui.View):
    """Mesaj în canal ticket: revendicare + închidere (cu confirmare)."""

    def __init__(self, cog: Any) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="Revendică", style=discord.ButtonStyle.primary, emoji="📌", custom_id="aivor_ticket_claim_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self.cog.claim_ticket_button(interaction)

    @ui.button(label="Închide ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="aivor_ticket_close_staff")
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self.cog.begin_close_confirmation(interaction)


class TicketCloseConfirmView(ui.View):
    """Confirmare închidere (nu e persistent — timeout 3 min)."""

    def __init__(self, cog: Any, channel_id: int) -> None:
        super().__init__(timeout=180)
        self.cog = cog
        self.channel_id = channel_id

    @ui.button(label="Da, închide", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await self.cog.confirm_close_after_button(interaction, self.channel_id)

    @ui.button(label="Anulează", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(content="✅ Închidere anulată.", view=None)

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
