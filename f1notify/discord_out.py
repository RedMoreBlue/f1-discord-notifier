"""Builds and sends the Discord webhook messages."""
from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

import aiohttp

from .schedule import Session

log = logging.getLogger(__name__)

SESSION_EMOJI = {
    "fp1": "🛠️",
    "fp2": "🛠️",
    "fp3": "🛠️",
    "sprint_qualifying": "⏱️",
    "sprint": "⚡",
    "qualifying": "⏱️",
    "race": "🏁",
}
F1_RED = 0xE10600


def when_text(minutes: int) -> str:
    if minutes == 0:
        return "is starting now!"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"starts in {hours} hour{'s' if hours != 1 else ''}"
    return f"starts in {minutes} minute{'s' if minutes != 1 else ''}"


def local_time(session: Session, tz: ZoneInfo) -> str:
    # e.g. "Sun 08 Nov 19:00 EET"
    return session.start.astimezone(tz).strftime("%a %d %b %H:%M %Z")


def build_message(session: Session, minutes: int, role_id: str, tz: ZoneInfo, test: bool = False) -> dict:
    emoji = SESSION_EMOJI.get(session.kind, "🏎️")
    headline = f"{session.race_name} {session.name} {when_text(minutes)}"
    unix = int(session.start.timestamp())
    embed = {
        "title": f"{emoji} {headline}",
        "color": F1_RED,
        "fields": [
            {"name": "Session", "value": session.name, "inline": True},
            {"name": "Start (Estonian time)", "value": local_time(session, tz), "inline": True},
            {"name": "Countdown", "value": f"<t:{unix}:R>", "inline": True},
            {"name": "Circuit", "value": f"{session.circuit}\n{session.location}", "inline": False},
        ],
        "footer": {"text": f"Round {session.round} · {session.season} season"},
    }
    content = f"<@&{role_id}> {emoji} **{headline}**"
    if test:
        embed["title"] = f"🧪 TEST — {embed['title']}"
        embed["footer"]["text"] = "This is a test notification. " + embed["footer"]["text"]
        content = f"🧪 **TEST** — {content}"
    return {
        "username": "F1 Alerts",
        "content": content,
        "embeds": [embed],
        # only allow pinging the F1 role, never @everyone or users
        "allowed_mentions": {"parse": [], "roles": [role_id]},
    }


async def send_webhook(http: aiohttp.ClientSession, url: str, payload: dict, attempts: int = 3) -> None:
    for attempt in range(1, attempts + 1):
        async with http.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 429:
                retry = float((await resp.json()).get("retry_after", 2))
                log.warning("Rate limited by Discord, retrying in %.1fs", retry)
                await asyncio.sleep(retry)
                continue
            if resp.status >= 500 and attempt < attempts:
                await asyncio.sleep(2 * attempt)
                continue
            if resp.status >= 400:
                raise RuntimeError(f"Discord webhook returned {resp.status}: {await resp.text()}")
            return
    raise RuntimeError("Discord webhook failed after retries")
