"""Types shared by the kill switch and its saved state."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import Enum


class Mode(Enum):
    """What the system may do: open risk, only reduce it, or nothing."""

    ACTIVE = "ACTIVE"
    REDUCING = "REDUCING"
    HALTED = "HALTED"


class Effect(Enum):
    """Whether a reason latches and flattens (TRIP) or only stops new risk (BLOCK)."""

    TRIP = "TRIP"
    BLOCK = "BLOCK"


class Reason(Enum):
    """Why the switch is not ACTIVE."""

    DAILY_LOSS = "DAILY_LOSS"
    DRAWDOWN = "DRAWDOWN"
    POSITION_CAP = "POSITION_CAP"
    ORDER_RATE = "ORDER_RATE"
    STALE_MARKET_DATA = "STALE_MARKET_DATA"
    STALE_EQUITY = "STALE_EQUITY"
    NOT_ARMED = "NOT_ARMED"
    BAD_EQUITY = "BAD_EQUITY"
    SAVE_FAILED = "SAVE_FAILED"
    CLOCK_REGRESSION = "CLOCK_REGRESSION"


EFFECTS: dict[Reason, frozenset[Effect]] = {
    Reason.DAILY_LOSS: frozenset({Effect.TRIP}),
    Reason.DRAWDOWN: frozenset({Effect.TRIP}),
    Reason.POSITION_CAP: frozenset({Effect.TRIP}),
    Reason.ORDER_RATE: frozenset({Effect.TRIP}),
    Reason.STALE_MARKET_DATA: frozenset({Effect.TRIP, Effect.BLOCK}),
    Reason.STALE_EQUITY: frozenset({Effect.TRIP, Effect.BLOCK}),
    Reason.NOT_ARMED: frozenset({Effect.BLOCK}),
    Reason.BAD_EQUITY: frozenset({Effect.BLOCK}),
    Reason.SAVE_FAILED: frozenset({Effect.BLOCK}),
    Reason.CLOCK_REGRESSION: frozenset({Effect.BLOCK}),
}


class Cause(Enum):
    """Why the switch is not armed; each value is the detail an operator sees."""

    STATE_MISSING = "state file missing"
    STATE_CORRUPT = "state file unreadable or corrupt"
    STATE_NON_FINITE = "non-finite number in state file"
    STATE_VERSION = "state file version mismatch"
    STATE_ACCOUNT = "state file is for another account"
    STATE_INVARIANT = "state file invariant violated"
    LOCK_UNAVAILABLE = "state lock held elsewhere or unobtainable"
    NO_EQUITY = "no equity reading yet"
    NO_POSITION = "no position report yet"


@dataclass(frozen=True)
class Limits:
    """Kill switch thresholds; each names the largest allowed value."""

    daily_loss_usd: float
    max_drawdown_usd: float
    max_position_contracts: int
    max_orders: int
    order_window_seconds: float
    max_data_age_seconds: float
    max_equity_age_seconds: float

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{f.name} must be a number, got {value!r}")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{f.name} must be positive and finite, got {value!r}")
        for name in ("max_position_contracts", "max_orders"):
            if not isinstance(getattr(self, name), int):
                raise ValueError(f"{name} must be a whole number")

    @classmethod
    def from_mapping(cls, raw: Mapping[str, float]) -> Limits:
        """Build limits from config; a missing or unknown key raises ValueError."""
        names = {f.name for f in fields(cls)}
        missing = sorted(names - raw.keys())
        unknown = sorted(raw.keys() - names)
        if missing or unknown:
            raise ValueError(f"limits config: missing {missing}, unknown {unknown}")
        return cls(**raw)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Flag:
    """One reason behind a decision; `latched` marks a trip whose condition has cleared."""

    reason: Reason
    effect: Effect
    detail: str
    latched: bool = False


@dataclass(frozen=True)
class Decision:
    """The switch's verdict on one event."""

    mode: Mode
    flatten: bool
    flags: tuple[Flag, ...]

    def permits(self, reducing: bool) -> bool:
        """Whether an order may be sent: any in ACTIVE, reducing only in REDUCING, none in HALTED."""
        if self.mode is Mode.ACTIVE:
            return True
        return self.mode is Mode.REDUCING and reducing

    def has(self, reason: Reason, effect: Effect | None = None) -> bool:
        """Whether a flag for `reason` (and `effect`, if given) is present."""
        return any(f.reason is reason and (effect is None or f.effect is effect) for f in self.flags)

    @property
    def tripped(self) -> bool:
        """Whether any trip is active or latched."""
        return any(f.effect is Effect.TRIP for f in self.flags)
