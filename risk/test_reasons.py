"""One scenario per (Reason, Effect) pair and per NOT_ARMED cause, checked against the enums."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from risk.conftest import ACCOUNT, LIMITS, START, Factory, FakeClock
from risk.kill_switch import KillSwitch
from risk.model import EFFECTS, Cause, Decision, Effect, Mode, Reason
from risk.state import Lock, load


@dataclass
class Ctx:
    make: Factory
    clock: FakeClock
    state_path: Path
    monkeypatch: pytest.MonkeyPatch
    held: list[Lock] = field(default_factory=list)


@dataclass
class Outcome:
    switch: KillSwitch
    decision: Decision
    clear: Callable[[], Decision] | None = None


def _age_market_data(c: Ctx, position: int) -> Outcome:
    ks = c.make(position=position)
    c.clock.advance(31.0)
    ks.on_equity(START)
    return Outcome(ks, ks.evaluate(), lambda: ks.on_market_data(c.clock()))


def _age_equity(c: Ctx, position: int) -> Outcome:
    ks = c.make(position=position)
    for _ in range(11):
        c.clock.advance(30.0)
        ks.on_market_data(c.clock())
    return Outcome(ks, ks.evaluate(), lambda: ks.on_equity(START))


def _daily_loss(c: Ctx) -> Outcome:
    ks = c.make()
    return Outcome(ks, ks.on_equity(START - 300.0))


def _drawdown(c: Ctx) -> Outcome:
    ks = c.make(limits=replace(LIMITS, daily_loss_usd=10_000.0))
    return Outcome(ks, ks.on_equity(START - 500.0))


def _position_cap(c: Ctx) -> Outcome:
    ks = c.make()
    return Outcome(ks, ks.on_position(2))


def _order_rate(c: Ctx) -> Outcome:
    ks = c.make()
    for _ in range(5):
        ks.on_order_action()
    return Outcome(ks, ks.on_order_action())


def _not_armed(c: Ctx) -> Outcome:
    ks = c.make(armed=False)

    def arm() -> Decision:
        ks.on_equity(START)
        ks.on_position(0)
        return ks.on_market_data(c.clock())

    return Outcome(ks, ks.evaluate(), arm)


def _bad_equity(c: Ctx) -> Outcome:
    ks = c.make()
    return Outcome(ks, ks.on_equity(float("nan")), lambda: ks.on_equity(START))


def _save_failed(c: Ctx) -> Outcome:
    ks = c.make()

    def broken(*_: object) -> None:
        raise OSError("disk full")

    c.monkeypatch.setattr("risk.kill_switch.save", broken)
    decision = ks.on_equity(START + 1.0)

    def repair() -> Decision:
        c.monkeypatch.undo()
        return ks.evaluate()

    return Outcome(ks, decision, repair)


def _clock_regression(c: Ctx) -> Outcome:
    ks = c.make()
    c.clock.advance(-2.0)

    def catch_up() -> Decision:
        c.clock.advance(2.0)
        return ks.evaluate()

    return Outcome(ks, ks.evaluate(), catch_up)


SCENARIOS: dict[tuple[Reason, Effect], Callable[[Ctx], Outcome]] = {
    (Reason.DAILY_LOSS, Effect.TRIP): _daily_loss,
    (Reason.DRAWDOWN, Effect.TRIP): _drawdown,
    (Reason.POSITION_CAP, Effect.TRIP): _position_cap,
    (Reason.ORDER_RATE, Effect.TRIP): _order_rate,
    (Reason.STALE_MARKET_DATA, Effect.TRIP): lambda c: _age_market_data(c, position=1),
    (Reason.STALE_MARKET_DATA, Effect.BLOCK): lambda c: _age_market_data(c, position=0),
    (Reason.STALE_EQUITY, Effect.TRIP): lambda c: _age_equity(c, position=1),
    (Reason.STALE_EQUITY, Effect.BLOCK): lambda c: _age_equity(c, position=0),
    (Reason.NOT_ARMED, Effect.BLOCK): _not_armed,
    (Reason.BAD_EQUITY, Effect.BLOCK): _bad_equity,
    (Reason.SAVE_FAILED, Effect.BLOCK): _save_failed,
    (Reason.CLOCK_REGRESSION, Effect.BLOCK): _clock_regression,
}
TRIPS = [k for k in SCENARIOS if k[1] is Effect.TRIP]
BLOCKS = [k for k in SCENARIOS if k[1] is Effect.BLOCK]


@pytest.fixture
def ctx(
    make: Factory, clock: FakeClock, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Ctx]:
    c = Ctx(make, clock, state_path, monkeypatch)
    yield c
    for lock in c.held:
        lock.release()


def test_scenarios_cover_every_declared_pair() -> None:
    assert set(EFFECTS) == set(Reason)
    assert set(SCENARIOS) == {(r, e) for r, effects in EFFECTS.items() for e in effects}


@pytest.mark.parametrize("key", list(SCENARIOS), ids=lambda k: f"{k[0].value}-{k[1].value}")
def test_scenario_produces_its_pair_and_is_never_active(ctx: Ctx, key: tuple[Reason, Effect]) -> None:
    decision = SCENARIOS[key](ctx).decision
    assert decision.has(*key)
    assert decision.mode is not Mode.ACTIVE
    assert all(isinstance(f.detail, str) and f.detail for f in decision.flags)


@pytest.mark.parametrize("key", TRIPS, ids=lambda k: k[0].value)
def test_trip_is_saved_and_survives_a_restart(ctx: Ctx, key: tuple[Reason, Effect]) -> None:
    outcome = SCENARIOS[key](ctx)
    outcome.switch.close()
    assert key[0] in load(ctx.state_path, ACCOUNT).reasons
    restarted = ctx.make(armed=False).evaluate()
    assert restarted.has(key[0], Effect.TRIP)
    assert all(isinstance(f.detail, str) and f.detail for f in restarted.flags)


@pytest.mark.parametrize("key", TRIPS, ids=lambda k: k[0].value)
def test_trip_flattens_only_with_a_position_open(ctx: Ctx, key: tuple[Reason, Effect]) -> None:
    outcome = SCENARIOS[key](ctx)
    assert outcome.decision.flatten == (outcome.decision.mode is Mode.REDUCING)
    assert outcome.switch.on_position(1).flatten
    assert not outcome.switch.on_position(0).flatten


@pytest.mark.parametrize("key", BLOCKS, ids=lambda k: k[0].value)
def test_block_clears_when_its_condition_clears(ctx: Ctx, key: tuple[Reason, Effect]) -> None:
    outcome = SCENARIOS[key](ctx)
    assert not outcome.decision.flatten
    assert outcome.clear is not None
    assert outcome.clear().mode is Mode.ACTIVE


def _write(path: Path, change: dict[str, object]) -> None:
    raw = json.loads(path.read_text())
    path.write_text(json.dumps({**raw, **change}))


CAUSES: dict[Cause, Callable[[Ctx], KillSwitch]] = {}


def cause(c: Cause) -> Callable[[Callable[[Ctx], KillSwitch]], Callable[[Ctx], KillSwitch]]:
    def register(fn: Callable[[Ctx], KillSwitch]) -> Callable[[Ctx], KillSwitch]:
        CAUSES[c] = fn
        return fn

    return register


@cause(Cause.STATE_MISSING)
def _missing(c: Ctx) -> KillSwitch:
    c.state_path.unlink()
    return c.make()


@cause(Cause.STATE_CORRUPT)
def _corrupt(c: Ctx) -> KillSwitch:
    c.state_path.write_text("{")
    return c.make()


@cause(Cause.STATE_NON_FINITE)
def _non_finite(c: Ctx) -> KillSwitch:
    c.state_path.write_text(c.state_path.read_text().replace(str(START), "NaN"))
    return c.make()


@cause(Cause.STATE_VERSION)
def _version(c: Ctx) -> KillSwitch:
    _write(c.state_path, {"version": 99})
    return c.make()


@cause(Cause.STATE_ACCOUNT)
def _account(c: Ctx) -> KillSwitch:
    _write(c.state_path, {"account_id": "OTHER"})
    return c.make()


@cause(Cause.STATE_INVARIANT)
def _invariant(c: Ctx) -> KillSwitch:
    _write(c.state_path, {"tripped": True})
    return c.make()


@cause(Cause.LOCK_UNAVAILABLE)
def _lock(c: Ctx) -> KillSwitch:
    held = Lock(c.state_path.parent)
    assert held.acquire()
    c.held.append(held)
    return c.make()


@cause(Cause.NO_EQUITY)
def _no_equity(c: Ctx) -> KillSwitch:
    ks = c.make(armed=False)
    ks.on_position(0)
    ks.on_market_data(c.clock())
    return ks


@cause(Cause.NO_POSITION)
def _no_position(c: Ctx) -> KillSwitch:
    ks = c.make(armed=False)
    ks.on_equity(START)
    ks.on_market_data(c.clock())
    return ks


def test_causes_cover_every_declared_cause() -> None:
    assert set(CAUSES) == set(Cause)


@pytest.mark.parametrize("c", list(CAUSES), ids=lambda c: c.name)
def test_each_cause_blocks_with_its_own_detail(ctx: Ctx, c: Cause) -> None:
    decision = CAUSES[c](ctx).evaluate()
    assert decision.mode is Mode.HALTED
    assert {f.reason for f in decision.flags} == {Reason.NOT_ARMED}
    assert c.value in {f.detail for f in decision.flags}
