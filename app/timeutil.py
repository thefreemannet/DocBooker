"""Time display for the fictional hospital. All booking clocks use America/New_York."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
WINDOW_DAYS = 14


def hospital_now() -> datetime:
    return datetime.now(TZ)


def parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ)
    return parsed.astimezone(TZ)


def format_date(value: datetime) -> str:
    return value.strftime("%A, %B %d, %Y").replace(" 0", " ")


def format_time(value: datetime) -> str:
    return value.strftime("%I:%M %p").lstrip("0")


def format_stamp(value: datetime) -> str:
    return f"{format_time(value)} ET"


def window_end(now: datetime) -> datetime:
    """Last bookable calendar day is today plus 13 days (14 days inclusive)."""
    last = (now.date() + timedelta(days=WINDOW_DAYS - 1))
    return datetime(last.year, last.month, last.day, 23, 59, tzinfo=TZ)


def in_bookable_window(moment: datetime, now: datetime) -> bool:
    moment = moment.astimezone(TZ)
    return now < moment <= window_end(now)
