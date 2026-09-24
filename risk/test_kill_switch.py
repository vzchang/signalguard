from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from risk.conftest import ACCOUNT, LIMITS, START, Factory, FakeClock
from risk.kill_switch import KillSwitch
from risk.model import Effect, Mode, Reason
from risk.state import load


def test_armed_switch_is_active(make: Factory) -> None:
    d = make().evaluate()
    assert d.mode is Mode.ACTIVE
    assert d.flags == ()
    assert not d.flatten


def test_unarmed_switch_is_never_active(make: Factory) -> None:
    d = make(armed=False).evaluate()
    assert d.mode is Mode.HALTED
    assert d.has(Reason.NOT_ARMED, Effect.BLOCK)


# boundary pairs: each limit names the largest allowed value


def test_daily_loss_at_limit_is_allowed_and_one_cent_over_trips(make: Factory) -> None:
    ks = make()
    assert not ks.on_equity(START - 200.0).tripped
    assert ks.on_equity(START - 200.01).has(Reason.DAILY_LOSS, Effect.TRIP)


def test_drawdown_at_limit_is_allowed_and_one_cent_over_trips(make: Factory) -> None:
    ks = make(limits=LIMITS.__class__(**{**LIMITS.__dict__, "daily_loss_usd": 10_000.0}))
    ks.on_equity(START + 100.0)  # new peak
    assert not ks.on_equity(START + 100.0 - 400.0).tripped
    assert ks.on_equity(START + 100.0 - 400.01).has(Reason.DRAWDOWN, Effect.TRIP)


def test_position_at_cap_is_allowed_and_one_over_trips(make: Factory) -> None:
    ks = make()
    assert not ks.on_position(-1).tripped
    assert ks.on_position(-2).has(Reason.POSITION_CAP, Effect.TRIP)


def test_order_rate_at_cap_is_allowed_and_one_over_trips(make: Factory) -> None:
    ks = make()
    for _ in range(5):
        assert ks.on_order_action().permits(reducing=False)
    d = ks.on_order_action()
    assert d.has(Reason.ORDER_RATE, Effect.TRIP)
    assert not d.permits(reducing=False)


def test_order_window_forgets_old_actions(make: Factory, clock: FakeClock) -> None:
    ks = make()
    for _ in range(5):
        ks.on_order_action()
    clock.advance(60.0)  # the first five fall exactly on the window edge and drop out
    assert not ks.on_order_action().tripped


def test_market_data_age_at_limit_is_fresh_and_just_over_is_stale(
    make: Factory, clock: FakeClock
) -> None:
    ks = make()
    ks.on_equity(START)
    clock.advance(30.0)
    assert ks.evaluate().mode is Mode.ACTIVE
    clock.advance(0.001)
    ks.on_equity(START)
    assert ks.evaluate().has(Reason.STALE_MARKET_DATA, Effect.BLOCK)


def test_equity_age_at_limit_is_fresh_and_just_over_is_stale(make: Factory, clock: FakeClock) -> None:
    ks = make()
    for _ in range(10):  # keep market data fresh while equity ages
        clock.advance(30.0)
        ks.on_market_data(clock())
    assert ks.evaluate().mode is Mode.ACTIVE
    clock.advance(0.001)
    ks.on_market_data(clock())
    assert ks.evaluate().has(Reason.STALE_EQUITY, Effect.BLOCK)


def test_clock_regression_of_one_second_is_tolerated_and_more_blocks(
    make: Factory, clock: FakeClock
) -> None:
    ks = make()
    clock.advance(-1.0)
    assert not ks.evaluate().has(Reason.CLOCK_REGRESSION)
    clock.advance(-0.001)
    assert ks.evaluate().has(Reason.CLOCK_REGRESSION, Effect.BLOCK)
    clock.advance(1.001)
    assert not ks.evaluate().has(Reason.CLOCK_REGRESSION)


# rules


def test_trip_latches_after_the_condition_clears(make: Factory) -> None:
    ks = make()
    ks.on_equity(START - 500.0)
    d = ks.on_equity(START)
    assert d.has(Reason.DAILY_LOSS, Effect.TRIP)
    assert all(f.latched for f in d.flags if f.reason is Reason.DAILY_LOSS)
    assert d.mode is Mode.HALTED


def test_trip_with_position_open_flattens_and_blocks_new_risk(make: Factory) -> None:
    ks = make(position=1)
    d = ks.on_equity(START - 500.0)
    assert d.mode is Mode.REDUCING
    assert d.flatten
    assert d.permits(reducing=True)
    assert not d.permits(reducing=False)


def test_flat_after_trip_halts_and_stops_flattening(make: Factory) -> None:
    ks = make(position=1)
    ks.on_equity(START - 500.0)
    d = ks.on_position(0)
    assert d.mode is Mode.HALTED
    assert not d.flatten


def test_block_does_not_latch(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.advance(31.0)
    ks.on_equity(START)
    assert ks.evaluate().has(Reason.STALE_MARKET_DATA, Effect.BLOCK)
    assert ks.on_market_data(clock()).mode is Mode.ACTIVE


def test_block_never_flattens(make: Factory) -> None:
    ks = make(position=1)
    d = ks.on_equity(float("nan"))
    assert d.has(Reason.BAD_EQUITY, Effect.BLOCK)
    assert d.mode is Mode.REDUCING
    assert not d.flatten


def test_peak_updates_before_the_drawdown_check(make: Factory) -> None:
    ks = make(limits=LIMITS.__class__(**{**LIMITS.__dict__, "max_drawdown_usd": 0.5}))
    assert not ks.on_equity(START + 1000.0).tripped


def test_bad_equity_never_moves_the_peak(make: Factory, state_path: Path) -> None:
    ks = make()
    for bad in (float("nan"), float("inf"), 0.0, -1.0):
        assert ks.on_equity(bad).has(Reason.BAD_EQUITY, Effect.BLOCK)
    assert load(state_path, ACCOUNT).peak_equity == START


def test_a_stream_of_bad_equity_goes_stale(make: Factory, clock: FakeClock) -> None:
    ks = make(position=1)
    for _ in range(11):
        clock.advance(30.0)
        ks.on_market_data(clock())
        d = ks.on_equity(float("nan"))
    assert d.has(Reason.STALE_EQUITY, Effect.TRIP)


def test_future_tick_counts_as_now_not_as_future(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_market_data(clock() + timedelta(hours=1))
    clock.advance(31.0)
    ks.on_equity(START)
    assert ks.evaluate().has(Reason.STALE_MARKET_DATA)


def test_older_tick_does_not_rewind_freshness(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.advance(20.0)
    ks.on_market_data(clock())
    ks.on_market_data(clock() - timedelta(minutes=5))
    clock.advance(20.0)
    assert not ks.evaluate().has(Reason.STALE_MARKET_DATA)


def test_session_rollover_resets_the_daily_baseline(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_equity(START - 150.0)
    clock.now = clock.now.replace(hour=22, minute=0)  # 17:00 Chicago: a new session
    ks.on_market_data(clock())
    ks.on_equity(START - 150.0)
    assert not ks.on_equity(START - 300.0).tripped


def test_latched_trip_survives_a_session_rollover(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_equity(START - 300.0)
    clock.now = clock.now.replace(hour=22, minute=0)
    ks.on_market_data(clock())
    assert ks.on_equity(START).has(Reason.DAILY_LOSS, Effect.TRIP)


def test_reset_after_rollover_clears_daily_loss(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_equity(START - 300.0)
    clock.now = clock.now.replace(hour=22, minute=0)
    ks.on_market_data(clock())
    ks.on_equity(START - 300.0)
    assert ks.reset("new session").mode is Mode.ACTIVE


def test_reset_trips_again_while_the_breach_holds(make: Factory) -> None:
    ks = make()
    ks.on_equity(START - 300.0)
    d = ks.reset("too early")
    assert d.has(Reason.DAILY_LOSS, Effect.TRIP)
    assert not any(f.latched for f in d.flags)


def test_reset_rebase_peak_clears_drawdown(make: Factory) -> None:
    ks = make(limits=LIMITS.__class__(**{**LIMITS.__dict__, "daily_loss_usd": 10_000.0}))
    ks.on_equity(START - 500.0)
    assert ks.reset("rebase", rebase_peak=True).mode is Mode.ACTIVE


def test_reset_without_rebase_leaves_drawdown_tripped(make: Factory) -> None:
    ks = make(limits=LIMITS.__class__(**{**LIMITS.__dict__, "daily_loss_usd": 10_000.0}))
    ks.on_equity(START - 500.0)
    assert ks.reset("no rebase").has(Reason.DRAWDOWN, Effect.TRIP)


def test_rebase_is_refused_without_fresh_valid_equity(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_equity(float("nan"))
    with pytest.raises(ValueError):
        ks.reset("bad equity", rebase_peak=True)
    ks.on_equity(START)
    clock.advance(301.0)
    with pytest.raises(ValueError):
        ks.reset("stale equity", rebase_peak=True)


def test_rebase_is_refused_without_any_equity(make: Factory) -> None:
    with pytest.raises(ValueError):
        make(armed=False).reset("nothing yet", rebase_peak=True)


def test_rebase_is_refused_without_loaded_state(state_path: Path, clock: FakeClock) -> None:
    state_path.write_text("garbage")
    ks = KillSwitch(LIMITS, state_path, ACCOUNT, clock)
    ks.on_equity(START)
    with pytest.raises(ValueError):
        ks.reset("no state", rebase_peak=True)
    ks.close()


def test_simultaneous_breaches_are_all_reported(make: Factory) -> None:
    ks = make(limits=LIMITS.__class__(**{**LIMITS.__dict__, "max_drawdown_usd": 250.0}))
    d = ks.on_equity(START - 300.0)
    assert d.has(Reason.DAILY_LOSS, Effect.TRIP)
    assert d.has(Reason.DRAWDOWN, Effect.TRIP)


def test_trip_survives_a_restart(make: Factory, state_path: Path) -> None:
    first = make()
    first.on_equity(START - 300.0)
    first.close()
    d = make(armed=False).evaluate()
    assert d.has(Reason.DAILY_LOSS, Effect.TRIP)
    assert load(state_path, ACCOUNT).tripped


def test_restart_with_open_position_does_not_trip_before_data_is_due(
    make: Factory, clock: FakeClock
) -> None:
    ks = make(armed=False)
    ks.on_position(1)
    assert not ks.evaluate().tripped
    clock.advance(31.0)
    assert ks.evaluate().has(Reason.STALE_MARKET_DATA, Effect.TRIP)


def test_second_instance_cannot_arm(make: Factory) -> None:
    make()
    second = make()
    d = second.evaluate()
    assert d.has(Reason.NOT_ARMED)
    assert any("lock" in f.detail for f in d.flags)


def test_naive_clock_is_rejected(state_path: Path) -> None:
    with pytest.raises(ValueError):
        KillSwitch(LIMITS, state_path, ACCOUNT, lambda: FakeClock().now.replace(tzinfo=None))


def test_naive_clock_mid_run_is_rejected(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.now = clock.now.replace(tzinfo=None)
    with pytest.raises(ValueError):
        ks.evaluate()


def test_naive_tick_is_rejected(make: Factory, clock: FakeClock) -> None:
    with pytest.raises(ValueError):
        make().on_market_data(clock().replace(tzinfo=None))


def test_trip_logs_critical(make: Factory, caplog: pytest.LogCaptureFixture) -> None:
    ks = make()
    with caplog.at_level(logging.WARNING, logger="risk.kill_switch"):
        ks.on_equity(START - 300.0)
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_block_logs_warning_once(make: Factory, caplog: pytest.LogCaptureFixture) -> None:
    ks = make()
    caplog.clear()  # arming itself logs a NOT_ARMED block
    with caplog.at_level(logging.WARNING, logger="risk.kill_switch"):
        ks.on_equity(float("nan"))
        assert len(caplog.records) == 1  # logged on the first bad reading, not a later one
        ks.on_equity(float("nan"))
        assert len(caplog.records) == 1


def test_save_failure_blocks_and_recovers(
    make: Factory, state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ks = make()

    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("risk.kill_switch.save", broken)
    d = ks.on_equity(START + 50.0)  # a new peak forces a save
    assert d.has(Reason.SAVE_FAILED, Effect.BLOCK)
    monkeypatch.undo()
    assert ks.evaluate().mode is Mode.ACTIVE
    assert load(state_path, ACCOUNT).peak_equity == START + 50.0


def test_failed_trip_save_logs_critical(
    make: Factory, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ks = make()

    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("risk.kill_switch.save", broken)
    with caplog.at_level(logging.ERROR, logger="risk.kill_switch"):
        ks.on_equity(START - 300.0)
    failed = [r for r in caplog.records if "save failed" in r.getMessage()]
    assert failed and all(r.levelno == logging.CRITICAL for r in failed)


def test_trip_without_loaded_state_latches_in_memory_and_flattens(
    state_path: Path, clock: FakeClock
) -> None:
    state_path.write_text("garbage")
    ks = KillSwitch(LIMITS, state_path, ACCOUNT, clock)
    d = ks.on_position(2)
    assert d.has(Reason.POSITION_CAP, Effect.TRIP)
    assert d.flatten
    assert ks.on_position(0).has(Reason.POSITION_CAP, Effect.TRIP)
    ks.close()


def test_reset_without_loaded_state_clears_the_memory_latch(state_path: Path, clock: FakeClock) -> None:
    state_path.write_text("garbage")
    ks = KillSwitch(LIMITS, state_path, ACCOUNT, clock)
    ks.on_position(2)
    ks.on_position(0)
    assert not ks.reset("operator checked").tripped
    ks.close()


def test_second_drop_in_a_new_session_trips(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.now = clock.now.replace(hour=22, minute=0)
    ks.on_market_data(clock())
    ks.on_equity(START - 150.0)  # sets the new session's baseline
    assert ks.on_equity(START - 350.01).has(Reason.DAILY_LOSS, Effect.TRIP)


def test_small_positive_equity_is_valid(make: Factory) -> None:
    assert not make().on_equity(0.5).has(Reason.BAD_EQUITY)


def test_equal_equity_does_not_rewrite_state(make: Factory, state_path: Path) -> None:
    ks = make()
    before = state_path.stat().st_mtime_ns
    ks.on_equity(START)
    assert state_path.stat().st_mtime_ns == before


def test_rebase_at_exactly_the_max_equity_age_is_allowed(make: Factory, clock: FakeClock) -> None:
    ks = make()
    ks.on_equity(START)
    clock.advance(300.0)
    ks.reset("edge", rebase_peak=True)


def test_failed_non_trip_save_logs_error_not_critical(
    make: Factory, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ks = make()

    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("risk.kill_switch.save", broken)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="risk.kill_switch"):
        ks.on_equity(START + 50.0)
    assert [r.levelno for r in caplog.records] == [logging.ERROR]


# review focus: inputs the spec implies but no rule test above exercises


def test_weekend_readings_then_sunday_open_rebaseline(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.now = clock.now.replace(day=26, hour=15)  # Saturday
    ks.on_market_data(clock())
    ks.on_equity(START - 150.0)
    clock.now = clock.now.replace(day=27, hour=22)  # Sunday 17:00 Chicago opens Monday's session
    ks.on_market_data(clock())
    ks.on_equity(START - 150.0)
    assert not ks.on_equity(START - 340.0).tripped
    assert ks.on_equity(START - 350.01).has(Reason.DAILY_LOSS, Effect.TRIP)


def test_integer_equity_is_accepted(make: Factory) -> None:
    assert make().on_equity(8000).mode is Mode.ACTIVE


def test_long_sleep_with_position_trips_both_feeds(make: Factory, clock: FakeClock) -> None:
    ks = make(position=1)
    clock.advance(3600.0)
    d = ks.evaluate()
    assert d.has(Reason.STALE_MARKET_DATA, Effect.TRIP)
    assert d.has(Reason.STALE_EQUITY, Effect.TRIP)
    assert d.flatten


def test_long_sleep_while_flat_blocks_then_clears(make: Factory, clock: FakeClock) -> None:
    ks = make()
    clock.advance(3600.0)
    assert ks.evaluate().mode is Mode.HALTED
    ks.on_equity(START)
    assert ks.on_market_data(clock()).mode is Mode.ACTIVE


def test_short_position_is_exposure(make: Factory) -> None:
    d = make(position=-1).on_equity(START - 300.0)
    assert d.flatten
    assert d.mode is Mode.REDUCING


def test_missing_state_directory_cannot_arm(tmp_path: Path, clock: FakeClock) -> None:
    ks = KillSwitch(LIMITS, tmp_path / "absent" / "switch.json", ACCOUNT, clock)
    d = ks.evaluate()
    assert d.mode is Mode.HALTED
    assert any("lock" in f.detail for f in d.flags)
    ks.close()


def test_clock_stepping_back_across_the_session_open_keeps_the_daily_loss(
    make: Factory, clock: FakeClock
) -> None:
    ks = make()
    clock.now = datetime(2026, 9, 22, 22, 30, tzinfo=timezone.utc)  # 17:30 Tue: session Sep 23
    ks.on_market_data(clock())
    ks.on_equity(START)
    clock.now = datetime(2026, 9, 23, 8, 10, tzinfo=timezone.utc)  # 03:10 Wed
    ks.on_market_data(clock())
    ks.on_equity(START - 150.0)
    clock.advance(-11 * 3600.0)  # back across 17:00 Tue into the previous session
    ks.on_equity(START - 150.0)
    clock.now = datetime(2026, 9, 23, 8, 15, tzinfo=timezone.utc)
    ks.on_market_data(clock())
    assert ks.on_equity(START - 300.0).has(Reason.DAILY_LOSS, Effect.TRIP)


def test_restart_with_the_clock_behind_the_saved_session_keeps_it(
    make: Factory, clock: FakeClock, state_path: Path
) -> None:
    ks = make()
    clock.now = datetime(2026, 9, 22, 22, 30, tzinfo=timezone.utc)
    ks.on_equity(START)
    ks.close()
    clock.advance(-3600.0)  # a restart on a clock that is an hour slow
    make(armed=False).on_equity(START - 50.0)
    assert load(state_path, ACCOUNT).session_start_equity == START


def test_real_negative_equity_trips_and_flattens(make: Factory) -> None:
    d = make(position=1).on_equity(-500.0)
    assert d.has(Reason.DAILY_LOSS, Effect.TRIP)
    assert d.flatten
