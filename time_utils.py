"""
Centralizes the definition of relative time windows ("today", "this week",
"last 7 days", "last month") so every query module agrees on what they mean.

Design decision: "this week" = the current ISO calendar week (Monday
00:00:00 through "now"), which is how most CRM/BI tools define it and how
a business user asking "calls this week" would expect it to behave.
"Last N days" windows are rolling (now - N days .. now), used for the
"last 7 days" / "last 3 days" style questions, which are explicitly
relative-to-now rather than calendar-aligned.

`get_now()` reads FIXED_NOW from the environment (ISO format) if present.
This exists purely so the bundled demo dataset -- generated relative to a
fixed reference time -- keeps producing non-empty, interesting answers
regardless of when the demo is actually run. In production you'd simply
not set FIXED_NOW and it falls back to the real current time.
"""
import os
from datetime import datetime, timedelta, timezone

from dateutil import parser as dtparser


def get_now() -> datetime:
    fixed = os.environ.get("FIXED_NOW")
    if fixed:
        return dtparser.isoparse(fixed)
    return datetime.now(timezone.utc)


def today_range(now=None):
    now = now or get_now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def this_week_range(now=None):
    now = now or get_now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = start_of_day - timedelta(days=now.weekday())  # Monday=0
    return monday, now


def last_n_days_range(n: int, now=None):
    now = now or get_now()
    return now - timedelta(days=n), now


def last_month_range(now=None):
    """Rolling last 30 days -- simplest, least surprising interpretation
    of "last month" for a relative query (vs. the previous calendar month)."""
    return last_n_days_range(30, now)
