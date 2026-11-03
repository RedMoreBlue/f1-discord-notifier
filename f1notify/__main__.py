"""Command line entry point.

    python -m f1notify run                         # run the notifier (what the systemd service does)
    python -m f1notify test [--minutes 15] [--session race]   # send a test notification
    python -m f1notify upcoming                    # list upcoming sessions in Estonian time
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import aiohttp

from .config import ALL_SESSIONS, ConfigError, load_config
from .discord_out import local_time, send_webhook
from .scheduler import Scheduler
from .testmsg import build_test_payload


async def cmd_run(cfg) -> None:
    async with aiohttp.ClientSession() as http:
        scheduler = Scheduler(cfg, http)
        if not cfg.bot_token:
            logging.info("DISCORD_BOT_TOKEN not set: running without slash commands")
            await scheduler.run()
            return
        from .bot import F1Bot

        bot = F1Bot(scheduler)
        task = asyncio.create_task(scheduler.run())
        try:
            async with bot:
                await bot.start(cfg.bot_token)
        finally:
            task.cancel()


async def cmd_test(cfg, session: str, minutes: int) -> None:
    async with aiohttp.ClientSession() as http:
        scheduler = Scheduler(cfg, http)
        await scheduler.refresh()
        await send_webhook(http, cfg.webhook_url, build_test_payload(scheduler, session, minutes))
    print("Test notification sent.")


async def cmd_upcoming(cfg, limit: int) -> None:
    async with aiohttp.ClientSession() as http:
        scheduler = Scheduler(cfg, http)
        await scheduler.refresh()
    sessions = scheduler.upcoming(only_enabled=False)[:limit]
    if not sessions:
        print("No upcoming sessions found.")
    for s in sessions:
        mark = "🔔" if s.kind in cfg.sessions else "  "
        print(f"{mark} {local_time(s, cfg.timezone):<22} {s.race_name} – {s.name}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="f1notify", description="F1 session reminders for Discord")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="run the notifier")
    t = sub.add_parser("test", help="send a test notification to the F1 role")
    t.add_argument("--minutes", type=int, default=15, help="minutes before start (0 = starting now)")
    t.add_argument("--session", choices=ALL_SESSIONS, default="race")
    u = sub.add_parser("upcoming", help="list upcoming sessions (🔔 = notifications enabled)")
    u.add_argument("-n", type=int, default=15, help="how many to show")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.command == "run" else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        if args.command == "run":
            asyncio.run(cmd_run(cfg))
        elif args.command == "test":
            asyncio.run(cmd_test(cfg, args.session, args.minutes))
        elif args.command == "upcoming":
            asyncio.run(cmd_upcoming(cfg, args.n))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if args.command == "run":
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
