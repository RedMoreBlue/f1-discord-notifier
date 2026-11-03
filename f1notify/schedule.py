"""Fetches the F1 calendar from the Jolpica API (the maintained successor of the Ergast API).

All times from the API are UTC; they are converted to the configured timezone only for display.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

log = logging.getLogger(__name__)

# API field name -> our session id
API_SESSION_FIELDS = {
    "FirstPractice": "fp1",
    "SecondPractice": "fp2",
    "ThirdPractice": "fp3",
    "SprintQualifying": "sprint_qualifying",
    "SprintShootout": "sprint_qualifying",  # name used in 2023
    "Sprint": "sprint",
    "Qualifying": "qualifying",
}

SESSION_NAMES = {
    "fp1": "Practice 1",
    "fp2": "Practice 2",
    "fp3": "Practice 3",
    "sprint_qualifying": "Sprint Qualifying",
    "sprint": "Sprint",
    "qualifying": "Qualifying",
    "race": "Race",
}


@dataclass(frozen=True)
class Session:
    season: int
    round: int
    race_name: str
    circuit: str
    location: str
    kind: str
    start: datetime  # timezone-aware, UTC

    @property
    def key(self) -> str:
        return f"{self.season}-{self.round}-{self.kind}"

    @property
    def name(self) -> str:
        return SESSION_NAMES[self.kind]


def _parse_dt(date: str, time: str | None) -> datetime | None:
    if not time:  # sessions without a confirmed time can't be scheduled
        return None
    return datetime.fromisoformat(f"{date}T{time.replace('Z', '+00:00')}").astimezone(timezone.utc)


def parse_races(data: dict) -> list[Session]:
    sessions: list[Session] = []
    for race in data["MRData"]["RaceTable"]["Races"]:
        loc = race["Circuit"]["Location"]
        common = dict(
            season=int(race["season"]),
            round=int(race["round"]),
            race_name=race["raceName"],
            circuit=race["Circuit"]["circuitName"],
            location=f"{loc['locality']}, {loc['country']}",
        )
        for field, kind in API_SESSION_FIELDS.items():
            if field in race:
                start = _parse_dt(race[field]["date"], race[field].get("time"))
                if start:
                    sessions.append(Session(kind=kind, start=start, **common))
        start = _parse_dt(race["date"], race.get("time"))
        if start:
            sessions.append(Session(kind="race", start=start, **common))
    return sorted(sessions, key=lambda s: s.start)


async def _get_json(http: aiohttp.ClientSession, url: str) -> dict:
    async with http.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.json()


async def fetch_schedule(http: aiohttp.ClientSession, api_base: str) -> tuple[list[Session], dict]:
    """Returns sessions of the current season, plus next season once the current one is over.

    Also returns the raw API payloads so they can be cached to disk.
    """
    now = datetime.now(timezone.utc)
    current = await _get_json(http, f"{api_base}/current.json?limit=100")
    raw = {"current": current}
    sessions = parse_races(current)
    if not any(s.start > now for s in sessions):
        season = int(current["MRData"]["RaceTable"].get("season", now.year))
        try:
            nxt = await _get_json(http, f"{api_base}/{season + 1}.json?limit=100")
            raw["next"] = nxt
            sessions += parse_races(nxt)
        except aiohttp.ClientError as e:
            log.info("Next season's calendar not available yet: %s", e)
    return sessions, raw


def save_cache(path: Path, raw: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw), encoding="utf-8")


def load_cache(path: Path) -> list[Session]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    sessions: list[Session] = []
    for payload in raw.values():
        sessions += parse_races(payload)
    return sorted(sessions, key=lambda s: s.start)
