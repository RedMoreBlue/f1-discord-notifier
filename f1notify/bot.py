"""Optional Discord bot that adds slash commands (/f1test, /f1next).

Only started when DISCORD_BOT_TOKEN is set. Notifications themselves always go through the webhook.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands

from .discord_out import local_time, send_webhook
from .scheduler import Scheduler
from .testmsg import build_test_payload

log = logging.getLogger(__name__)

SESSION_CHOICES = [
    app_commands.Choice(name="Free Practice 1", value="fp1"),
    app_commands.Choice(name="Free Practice 2", value="fp2"),
    app_commands.Choice(name="Free Practice 3", value="fp3"),
    app_commands.Choice(name="Race", value="race"),
    app_commands.Choice(name="Qualifying", value="qualifying"),
    app_commands.Choice(name="Sprint", value="sprint"),
    app_commands.Choice(name="Sprint Qualifying", value="sprint_qualifying"),
]


class F1Bot(discord.Client):
    def __init__(self, scheduler: Scheduler):
        super().__init__(intents=discord.Intents.default())
        self.scheduler = scheduler
        self.cfg = scheduler.cfg
        self.tree = app_commands.CommandTree(self)
        self._add_commands()

    def _add_commands(self) -> None:
        @self.tree.command(name="f1test", description="Send a test F1 notification to the F1 role")
        @app_commands.describe(minutes="Minutes before the session (0 = starting now)", session="Session type")
        @app_commands.choices(session=SESSION_CHOICES)
        @app_commands.default_permissions(manage_guild=True)  # only admins/mods see it by default
        @app_commands.guild_only()
        async def f1test(
            interaction: discord.Interaction,
            minutes: app_commands.Range[int, 0, 1440] = 15,
            session: app_commands.Choice[str] | None = None,
        ):
            kind = session.value if session else "race"
            payload = build_test_payload(self.scheduler, kind, minutes)
            try:
                await send_webhook(self.scheduler.http, self.cfg.webhook_url, payload)
            except Exception as e:
                await interaction.response.send_message(f"❌ Test failed: {e}", ephemeral=True)
                return
            log.info("Test notification sent by %s", interaction.user)
            await interaction.response.send_message("✅ Test notification sent.", ephemeral=True)

        @self.tree.command(name="f1next", description="Show the next F1 sessions (Estonian time)")
        async def f1next(interaction: discord.Interaction):
            upcoming = self.scheduler.upcoming()[:6]
            if not upcoming:
                await interaction.response.send_message("No upcoming sessions found.", ephemeral=True)
                return
            lines = [
                f"**{s.race_name} – {s.name}**: {local_time(s, self.cfg.timezone)} (<t:{int(s.start.timestamp())}:R>)"
                for s in upcoming
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def setup_hook(self) -> None:
        if self.cfg.guild_id:
            # Guild sync is instant; global sync can take up to an hour to appear.
            guild = discord.Object(id=self.cfg.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        log.info("Slash commands synced")

    async def on_ready(self) -> None:
        log.info("Bot logged in as %s", self.user)
