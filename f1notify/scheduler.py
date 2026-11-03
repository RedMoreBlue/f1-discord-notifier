"""Main loop: keeps the calendar fresh and sends reminders when they are due."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import aiohttp

from .config import Config
from .discord_out import build_message, local_time, send_webhook
from .schedule import Session, fetch_schedule, load_cache, save_cache

log = logging.getLogger(__name__)

TICK_SECONDS = 20
# If a reminder's moment passed less than this long ago (e.g. the service was restarting), still send it.
GRACE = timedelta(minutes=3)
REFRESH_EVERY = timedelta(hours=3)
RETRY_FETCH_AFTER = timedelta(minutes=10)


def due_reminders(
    sessions: Iterable[Session], minutes: Iterable[int], sent: set[str], now: datetime, grace: timedelta = GRACE
) -> list[tuple[Session, int, str]]:
    due = []
    minutes = tuple(minutes)
    for s in sessions:
        for m in minutes:
            key = f"{s.key}:{m}"
            fire_at = s.start - timedelta(minutes=m)
            if key not in sent and fire_at <= now < fire_at + grace:
                due.append((s, m, key))
    return due


class SentState:
    """Remembers which reminders went out, so a restart never sends duplicates."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.sent: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.sent = {}

    def keys(self) -> set[str]:
        return set(self.sent)

    def add(self, key: str, session_start: datetime) -> None:
        self.sent[key] = session_start.isoformat()
        self._save()

    def prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=3)
        old = [k for k, v in self.sent.items() if datetime.fromisoformat(v) < cutoff]
        if old:
            for k in old:
                del self.sent[k]
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.sent, indent=1), encoding="utf-8")
        tmp.replace(self.path)


class Scheduler:
    def __init__(self, cfg: Config, http: aiohttp.ClientSession):
        self.cfg = cfg
        self.http = http
        self.cache_path = cfg.data_dir / "schedule.json"
        self.state = SentState(cfg.data_dir / "sent.json")
        self.sessions: list[Session] = load_cache(self.cache_path)
        self._next_refresh = datetime.min.replace(tzinfo=timezone.utc)

    def upcoming(self, now: datetime | None = None, only_enabled: bool = True) -> list[Session]:
        now = now or datetime.now(timezone.utc)
        return [
            s for s in self.sessions
            if s.start > now and (not only_enabled or s.kind in self.cfg.sessions)
        ]

    async def refresh(self) -> None:
        now = datetime.now(timezone.utc)
        try:
            sessions, raw = await fetch_schedule(self.http, self.cfg.api_base)
        except Exception as e:  # network down, API hiccup...
            log.warning("Could not fetch F1 calendar (%s); using %d cached sessions", e, len(self.sessions))
            self._next_refresh = now + RETRY_FETCH_AFTER
            return
        self.sessions = sessions
        save_cache(self.cache_path, raw)
        self._next_refresh = now + REFRESH_EVERY
        nxt = self.upcoming(now)
        if nxt:
            s = nxt[0]
            log.info("Calendar updated: %d sessions. Next: %s %s at %s",
                     len(sessions), s.race_name, s.name, local_time(s, self.cfg.timezone))
        else:
            log.info("Calendar updated: no upcoming sessions found")

    async def tick(self) -> None:
        now = datetime.now(timezone.utc)
        if now >= self._next_refresh:
            await self.refresh()
        enabled = [s for s in self.sessions if s.kind in self.cfg.sessions]
        for session, minutes, key in due_reminders(enabled, self.cfg.reminder_minutes, self.state.keys(), now):
            payload = build_message(session, minutes, self.cfg.role_id, self.cfg.timezone)
            try:
                await send_webhook(self.http, self.cfg.webhook_url, payload)
            except Exception as e:  # retried on the next tick while still inside the grace window
                log.error("Failed to send reminder %s: %s", key, e)
                continue
            self.state.add(key, session.start)
            log.info("Sent reminder: %s %s (%d min before)", session.race_name, session.name, minutes)
        self.state.prune(now)

    async def run(self) -> None:
        log.info("Scheduler started. Reminders at %s minutes before: %s",
                 ", ".join(map(str, self.cfg.reminder_minutes)), ", ".join(sorted(self.cfg.sessions)))
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Unexpected error in scheduler tick")
            await asyncio.sleep(TICK_SECONDS)
