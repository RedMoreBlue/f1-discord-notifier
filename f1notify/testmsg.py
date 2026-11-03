"""Test notifications: uses the real next session of the requested type when one is known."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .discord_out import build_message
from .scheduler import Scheduler
from .schedule import Session


def build_test_payload(scheduler: Scheduler, kind: str, minutes: int) -> dict:
    cfg = scheduler.cfg
    session = next((s for s in scheduler.upcoming(only_enabled=False) if s.kind == kind), None)
    if session is None:
        session = Session(
            season=datetime.now().year, round=0, race_name="Test Grand Prix", circuit="Test Circuit",
            location="Tallinn, Estonia", kind=kind,
            start=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        )
    return build_message(session, minutes, cfg.role_id, cfg.timezone, test=True)
