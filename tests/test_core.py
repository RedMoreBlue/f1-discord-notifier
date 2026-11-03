from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from f1notify.discord_out import build_message, local_time, when_text
from f1notify.schedule import parse_races
from f1notify.scheduler import due_reminders

TALLINN = ZoneInfo("Europe/Tallinn")

SAMPLE = {
    "MRData": {"RaceTable": {"season": "2026", "Races": [{
        "season": "2026", "round": "20", "raceName": "Brazilian Grand Prix",
        "Circuit": {"circuitName": "Interlagos", "Location": {"locality": "São Paulo", "country": "Brazil"}},
        "date": "2026-11-08", "time": "17:00:00Z",
        "FirstPractice": {"date": "2026-11-06", "time": "15:30:00Z"},
        "Qualifying": {"date": "2026-11-07", "time": "18:00:00Z"},
        "Sprint": {"date": "2026-11-07"},  # no time yet -> skipped
    }]}}
}


def test_parse_races():
    sessions = parse_races(SAMPLE)
    assert [s.kind for s in sessions] == ["fp1", "qualifying", "race"]
    race = sessions[-1]
    assert race.start == datetime(2026, 11, 8, 17, tzinfo=timezone.utc)
    assert race.key == "2026-20-race"


def test_estonian_time_winter_and_summer():
    race = parse_races(SAMPLE)[-1]
    assert local_time(race, TALLINN) == "Sun 08 Nov 19:00 EET"  # UTC+2 in winter
    summer = race.__class__(**{**race.__dict__, "start": datetime(2026, 7, 5, 14, tzinfo=timezone.utc)})
    assert local_time(summer, TALLINN) == "Sun 05 Jul 17:00 EEST"  # UTC+3 in summer


def test_due_reminders_window_and_dedup():
    race = parse_races(SAMPLE)[-1]
    at_15 = race.start - timedelta(minutes=15)
    assert [m for _, m, _ in due_reminders([race], (60, 15, 5, 0), set(), at_15)] == [15]
    # still sent shortly after (e.g. restart), but not long after
    assert due_reminders([race], (15,), set(), at_15 + timedelta(minutes=2))
    assert not due_reminders([race], (15,), set(), at_15 + timedelta(minutes=5))
    # not before its time
    assert not due_reminders([race], (15,), set(), at_15 - timedelta(seconds=1))
    # never twice
    assert not due_reminders([race], (15,), {"2026-20-race:15"}, at_15)


def test_message_pings_only_role():
    race = parse_races(SAMPLE)[-1]
    msg = build_message(race, 5, "42", TALLINN)
    assert msg["content"].startswith("<@&42>")
    assert msg["allowed_mentions"] == {"parse": [], "roles": ["42"]}
    assert "starts in 5 minutes" in msg["embeds"][0]["title"]
    assert "TEST" in build_message(race, 5, "42", TALLINN, test=True)["content"]


def test_when_text():
    assert when_text(0) == "is starting now!"
    assert when_text(1) == "starts in 1 minute"
    assert when_text(60) == "starts in 1 hour"
    assert when_text(120) == "starts in 2 hours"
