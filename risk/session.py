"""CME trading date for a timestamp."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
SESSION_OPEN = time(17, 0)


def session_id(ts: datetime) -> date:
    """Return the CME trading date `ts` falls in; a session opens 17:00 Chicago the day before."""
    if ts.tzinfo is None:
        raise ValueError("session_id needs an aware timestamp")
    local = ts.astimezone(CHICAGO)
    if local.time() >= SESSION_OPEN:
        return local.date() + timedelta(days=1)
    return local.date()
