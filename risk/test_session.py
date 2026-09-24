from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from risk.session import session_id

UTC = timezone.utc


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        (datetime(2026, 9, 22, 21, 59, 59, tzinfo=UTC), date(2026, 9, 22)),  # Tue 16:59:59 CDT
        (datetime(2026, 9, 22, 22, 0, 0, tzinfo=UTC), date(2026, 9, 23)),  # Tue 17:00 CDT
        (datetime(2026, 3, 6, 22, 59, tzinfo=UTC), date(2026, 3, 6)),  # Fri 16:59 CST
        (datetime(2026, 3, 6, 23, 0, tzinfo=UTC), date(2026, 3, 7)),  # Fri 17:00 CST
        (datetime(2026, 3, 9, 21, 59, tzinfo=UTC), date(2026, 3, 9)),  # Mon 16:59 CDT, after spring forward
        (datetime(2026, 3, 9, 22, 0, tzinfo=UTC), date(2026, 3, 10)),  # Mon 17:00 CDT
        (datetime(2026, 11, 2, 22, 59, tzinfo=UTC), date(2026, 11, 2)),  # Mon 16:59 CST, after fall back
        (datetime(2026, 11, 2, 23, 0, tzinfo=UTC), date(2026, 11, 3)),  # Mon 17:00 CST
        (datetime(2026, 9, 27, 22, 0, tzinfo=UTC), date(2026, 9, 28)),  # Sunday open counts as Monday
    ],
)
def test_session_boundary_is_1700_chicago(ts: datetime, expected: date) -> None:
    assert session_id(ts) == expected


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        session_id(datetime(2026, 9, 22, 14, 0))
