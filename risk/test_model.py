from __future__ import annotations

import math

import pytest

from risk.model import Decision, Effect, Flag, Limits, Mode, Reason

VALID = {
    "daily_loss_usd": 200.0,
    "max_drawdown_usd": 400.0,
    "max_position_contracts": 1,
    "max_orders": 5,
    "order_window_seconds": 60.0,
    "max_data_age_seconds": 30.0,
    "max_equity_age_seconds": 300.0,
}


def test_from_mapping_builds_valid_limits() -> None:
    assert Limits.from_mapping(VALID) == Limits(**VALID)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1, math.nan, math.inf, True, "5"])
@pytest.mark.parametrize("field", sorted(VALID))
def test_every_limit_rejects_non_positive_non_finite_and_non_numbers(field: str, bad: object) -> None:
    with pytest.raises(ValueError):
        Limits.from_mapping({**VALID, field: bad})  # type: ignore[dict-item]


@pytest.mark.parametrize("field", ["max_position_contracts", "max_orders"])
def test_counts_must_be_whole_numbers(field: str) -> None:
    with pytest.raises(ValueError):
        Limits.from_mapping({**VALID, field: 1.5})


def test_missing_key_is_rejected() -> None:
    raw = dict(VALID)
    del raw["daily_loss_usd"]
    with pytest.raises(ValueError, match="daily_loss_usd"):
        Limits.from_mapping(raw)


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="daily_loss"):
        Limits.from_mapping({**VALID, "daily_loss": 1.0})


def _decision(mode: Mode) -> Decision:
    return Decision(mode, False, ())


def test_active_permits_every_order() -> None:
    assert _decision(Mode.ACTIVE).permits(reducing=False)
    assert _decision(Mode.ACTIVE).permits(reducing=True)


def test_reducing_permits_only_reducing_orders() -> None:
    assert _decision(Mode.REDUCING).permits(reducing=True)
    assert not _decision(Mode.REDUCING).permits(reducing=False)


def test_halted_permits_nothing() -> None:
    assert not _decision(Mode.HALTED).permits(reducing=True)
    assert not _decision(Mode.HALTED).permits(reducing=False)


def test_has_matches_reason_and_optional_effect() -> None:
    d = Decision(Mode.HALTED, False, (Flag(Reason.STALE_EQUITY, Effect.BLOCK, "x"),))
    assert d.has(Reason.STALE_EQUITY)
    assert d.has(Reason.STALE_EQUITY, Effect.BLOCK)
    assert not d.has(Reason.STALE_EQUITY, Effect.TRIP)
    assert not d.has(Reason.DRAWDOWN)
    assert not d.tripped


def test_tripped_is_true_only_with_a_trip_flag() -> None:
    d = Decision(Mode.HALTED, False, (Flag(Reason.DRAWDOWN, Effect.TRIP, "x"),))
    assert d.tripped
