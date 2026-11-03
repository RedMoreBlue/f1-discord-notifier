"""Configuration loaded from environment variables (or a .env file next to the project)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_DIR = Path(__file__).resolve().parent.parent

ALL_SESSIONS = ("fp1", "fp2", "fp3", "sprint_qualifying", "sprint", "qualifying", "race")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    webhook_url: str
    role_id: str
    reminder_minutes: tuple[int, ...]
    sessions: frozenset[str]
    timezone: ZoneInfo
    bot_token: str | None
    guild_id: int | None
    data_dir: Path
    api_base: str


def load_dotenv(path: Path = PROJECT_DIR / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, never overrides real environment variables."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _int_list(raw: str) -> tuple[int, ...]:
    try:
        values = sorted({int(v) for v in raw.split(",") if v.strip()}, reverse=True)
    except ValueError as e:
        raise ConfigError(f"REMINDER_MINUTES must be comma separated numbers, got {raw!r}") from e
    if any(v < 0 for v in values):
        raise ConfigError("REMINDER_MINUTES cannot contain negative numbers")
    return tuple(values)


def load_config() -> Config:
    load_dotenv()
    env = os.environ

    webhook_url = env.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url.startswith("https://"):
        raise ConfigError("DISCORD_WEBHOOK_URL is missing or invalid (set it in .env)")

    role_id = env.get("F1_ROLE_ID", "").strip()
    if not role_id.isdigit():
        raise ConfigError("F1_ROLE_ID is missing or not a numeric role ID (set it in .env)")

    sessions = frozenset(
        s.strip().lower()
        for s in env.get("SESSIONS", ",".join(ALL_SESSIONS)).split(",")
        if s.strip()
    )
    unknown = sessions - set(ALL_SESSIONS)
    if unknown:
        raise ConfigError(f"Unknown SESSIONS {sorted(unknown)}; valid: {', '.join(ALL_SESSIONS)}")

    guild_id = env.get("DISCORD_GUILD_ID", "").strip()
    data_dir = Path(env.get("DATA_DIR", "").strip() or PROJECT_DIR / "data")

    return Config(
        webhook_url=webhook_url,
        role_id=role_id,
        reminder_minutes=_int_list(env.get("REMINDER_MINUTES", "15,5")),
        sessions=sessions,
        timezone=ZoneInfo(env.get("TIMEZONE", "Europe/Tallinn").strip()),
        bot_token=env.get("DISCORD_BOT_TOKEN", "").strip() or None,
        guild_id=int(guild_id) if guild_id.isdigit() else None,
        data_dir=data_dir,
        api_base=env.get("F1_API_BASE", "https://api.jolpi.ca/ergast/f1").rstrip("/"),
    )
