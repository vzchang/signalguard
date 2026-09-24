"""The kill switch: decides whether the system may open risk, only reduce it, or do nothing."""

from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from risk.model import Cause, Decision, Effect, Flag, Limits, Mode, Reason
from risk.session import session_id
from risk.state import Lock, StateUnavailable, SwitchState, load, save

log = logging.getLogger("risk.kill_switch")

CLOCK_TOLERANCE = timedelta(seconds=1)
LATCHED = "condition cleared, still latched"  # pragma: no mutate (equivalent: display text only)
REGRESSED = "clock moved backwards"  # pragma: no mutate (equivalent: display text only)
_RANK = {reason: i for i, reason in enumerate(Reason)}


def _finite(net_liq: float) -> bool:
    return not isinstance(net_liq, bool) and isinstance(net_liq, (int, float)) and math.isfinite(net_liq)


def _valid(net_liq: float) -> bool:
    return _finite(net_liq) and net_liq > 0


class KillSwitch:
    """Watches broker and market data independently of strategy logic and returns a Decision."""

    _regressed: bool  # set by _now, which runs before anything reads it

    def __init__(
        self,
        limits: Limits,
        state_path: Path,
        account_id: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._limits = limits
        self._path = Path(state_path)
        self._clock = clock
        start = clock()
        if start.tzinfo is None:
            raise ValueError("clock must return an aware datetime")
        self._latest_now = start
        # staleness is measured from startup until the first reading arrives
        self._data_ts = start
        self._equity_at = start
        self._net_liq: float | None = None
        self._position: int | None = None
        self._orders: deque[datetime] = deque()
        self._unsaved: SwitchState | None = None
        # any non-empty block set differs from frozenset() and from None alike
        self._last_blocks: frozenset[Reason] = frozenset()  # pragma: no mutate (equivalent: see above)
        self._state: SwitchState | None = None
        self._cause: Cause | None = None
        self._trips: set[Reason] = set()
        self._lock = Lock(self._path.parent)
        if not self._lock.acquire():
            self._cause = Cause.LOCK_UNAVAILABLE
            return
        try:
            self._state = load(self._path, account_id)
        except StateUnavailable as e:
            self._cause = e.cause
            return
        self._trips = set(self._state.reasons)

    def close(self) -> None:
        """Release the process lock."""
        self._lock.release()

    def on_equity(self, net_liq: float) -> Decision:
        """Record the broker's marked-to-market net liquidation value."""
        now = self._begin()
        self._net_liq = net_liq
        if _valid(net_liq):
            # only a valid reading counts as fresh, so a stream of bad values goes stale
            self._equity_at = now
            if self._state is not None:
                state = self._state
                current = session_id(now)
                # forward only, and never on a clock known to be behind: a step back across
                # 17:00 would otherwise rebaseline on post-loss equity and erase the day's loss
                if current > state.session_id and not self._regressed:
                    state = replace(state, session_id=current, session_start_equity=float(net_liq))
                state = replace(state, peak_equity=max(state.peak_equity, float(net_liq)))
                self._commit(state)
        return self._evaluate(now)

    def on_position(self, signed_contracts: int) -> Decision:
        """Record the broker-reported position."""
        # abs(nan) > cap is False, so a NaN position would silently disable the position cap
        if isinstance(signed_contracts, bool) or not isinstance(signed_contracts, int):
            raise ValueError(f"position must be a whole number of contracts, got {signed_contracts!r}")
        now = self._begin()
        self._position = signed_contracts
        return self._evaluate(now)

    def on_order_action(self) -> Decision:
        """Record a submit or modify about to be sent; send only if the result permits it."""
        now = self._begin()
        self._orders.append(now)
        return self._evaluate(now)

    def on_market_data(self, data_ts: datetime) -> Decision:
        """Record a tick by its own timestamp; one from the future counts as now."""
        now = self._begin()
        if data_ts.tzinfo is None:
            raise ValueError("data_ts must be aware")
        self._data_ts = max(self._data_ts, min(data_ts, now))
        return self._evaluate(now)

    def evaluate(self) -> Decision:
        """Re-check every condition; the adapter calls this on a timer."""
        return self._evaluate(self._begin())

    def reset(self, note: str, rebase_peak: bool = False) -> Decision:
        """Clear the latch; a breach that still holds trips again in the returned decision."""
        now = self._begin()
        new_peak: float | None = None
        if rebase_peak:
            net = self._net_liq
            fresh = (now - self._equity_at).total_seconds() <= self._limits.max_equity_age_seconds
            if self._state is None or net is None or not _valid(net) or not fresh:
                raise ValueError("rebase_peak needs loaded state and a fresh valid equity reading")
            new_peak = float(net)
        log.warning("kill switch reset: %s (rebase_peak=%s)", note, rebase_peak)
        self._trips.clear()
        if self._state is not None:
            state = replace(self._state, tripped=False, reasons=(), tripped_at=None)
            if new_peak is not None:
                state = replace(state, peak_equity=new_peak)
            self._commit(state)
        return self._evaluate(now)

    def _begin(self) -> datetime:
        # retry only a save that failed on an earlier event; this event's own saves come later
        if self._unsaved is not None:
            self._save(self._unsaved)
        return self._now()

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("clock must return an aware datetime")
        self._regressed = now < self._latest_now - CLOCK_TOLERANCE
        self._latest_now = max(self._latest_now, now)
        return now

    def _commit(self, state: SwitchState) -> None:
        if state != self._state:
            self._state = state
            self._save(state)

    def _save(self, state: SwitchState) -> None:
        try:
            save(self._path, state)
        except OSError:
            self._unsaved = state
            level = logging.CRITICAL if state.tripped else logging.ERROR
            log.log(level, "kill switch state save failed", exc_info=True)
        else:
            self._unsaved = None

    def _breaches(self, now: datetime, exposed: bool) -> list[Flag]:
        limits = self._limits
        found: list[Flag] = []
        net = self._net_liq
        # finite is enough here: a real negative net liq is the worst loss, not bad data
        if self._state is not None and net is not None and _finite(net):
            loss = self._state.session_start_equity - net
            if loss > limits.daily_loss_usd:
                found.append(Flag(Reason.DAILY_LOSS, Effect.TRIP, f"session loss {loss:.2f}"))
            drawdown = self._state.peak_equity - net
            if drawdown > limits.max_drawdown_usd:
                found.append(Flag(Reason.DRAWDOWN, Effect.TRIP, f"drawdown {drawdown:.2f}"))
        if self._position is not None and abs(self._position) > limits.max_position_contracts:
            found.append(Flag(Reason.POSITION_CAP, Effect.TRIP, f"position {self._position}"))
        cutoff = now - timedelta(seconds=limits.order_window_seconds)
        while self._orders and self._orders[0] <= cutoff:
            self._orders.popleft()
        if len(self._orders) > limits.max_orders:
            found.append(Flag(Reason.ORDER_RATE, Effect.TRIP, f"{len(self._orders)} actions in window"))
        feeds = (
            (Reason.STALE_MARKET_DATA, self._data_ts, limits.max_data_age_seconds),
            (Reason.STALE_EQUITY, self._equity_at, limits.max_equity_age_seconds),
        )
        for reason, since, limit in feeds:
            age = (now - since).total_seconds()
            if age > limit:
                effect = Effect.TRIP if exposed else Effect.BLOCK
                found.append(Flag(reason, effect, f"{age:.1f}s old"))
        return found

    def _latch(self, now: datetime, trips: list[Flag]) -> None:
        new = [f for f in trips if f.reason not in self._trips]
        if not new:
            return
        for f in new:
            log.critical("kill switch tripped: %s (%s)", f.reason.value, f.detail)
            self._trips.add(f.reason)
        if self._state is not None:
            state = self._state
            reasons = tuple(r for r in Reason if r in self._trips)
            self._commit(
                replace(state, tripped=True, reasons=reasons, tripped_at=state.tripped_at or now)
            )

    def _evaluate(self, now: datetime) -> Decision:
        exposed = bool(self._position)
        breaches = self._breaches(now, exposed)
        trips = [f for f in breaches if f.effect is Effect.TRIP]
        self._latch(now, trips)
        flags = list(breaches)
        current = {f.reason for f in trips}
        flags.extend(
            Flag(r, Effect.TRIP, LATCHED, latched=True) for r in self._trips if r not in current
        )
        causes = [self._cause] if self._cause is not None else []
        if self._net_liq is None:
            causes.append(Cause.NO_EQUITY)
        if self._position is None:
            causes.append(Cause.NO_POSITION)
        flags.extend(Flag(Reason.NOT_ARMED, Effect.BLOCK, c.value) for c in causes)
        if self._net_liq is not None and not _valid(self._net_liq):
            flags.append(Flag(Reason.BAD_EQUITY, Effect.BLOCK, f"net_liq {self._net_liq!r}"))
        unsaved = self._unsaved
        if unsaved is not None:
            detail = f"not on disk: tripped={unsaved.tripped}, peak={unsaved.peak_equity:.2f}"
            flags.append(Flag(Reason.SAVE_FAILED, Effect.BLOCK, detail))
        if self._regressed:
            flags.append(Flag(Reason.CLOCK_REGRESSION, Effect.BLOCK, REGRESSED))
        flags.sort(key=lambda f: (_RANK[f.reason], f.effect.value, f.detail))
        if not flags:
            mode = Mode.ACTIVE
        elif exposed:
            mode = Mode.REDUCING
        else:
            mode = Mode.HALTED
        decision = Decision(mode, bool(self._trips) and exposed, tuple(flags))
        blocks = frozenset(f.reason for f in flags if f.effect is Effect.BLOCK)
        if blocks != self._last_blocks and blocks:
            log.warning("kill switch blocking: %s", ", ".join(sorted(r.value for r in blocks)))
        self._last_blocks = blocks
        return decision
