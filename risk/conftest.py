"""Shared fixtures: a controllable clock and a fresh state file."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from risk.model import Limits
from risk.state import initialize

T0 = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)  # Tuesday 09:00 Chicago, mid-session
ACCOUNT = "TEST-ACCOUNT"
START = 8000.0
LIMITS = Limits(
    daily_loss_usd=200.0,
    max_drawdown_usd=400.0,
    max_position_contracts=1,
    max_orders=5,
    order_window_seconds=60.0,
    max_data_age_seconds=30.0,
    max_equity_age_seconds=300.0,
)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    path = tmp_path / "switch.json"
    initialize(path, ACCOUNT, START, T0)
    return path
