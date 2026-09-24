# risk/: the kill switch

Prime directive 4 says the kill switch ships before the first strategy. This is it: a decision
core that watches broker and market data independently of any strategy and answers one
question on every event. May the system open risk, only reduce it, or do nothing?

Standard library only. No broker, no framework: a NautilusTrader adapter will feed it events
and enforce its decisions once the trading core exists.

## The decision

Every event returns a `Decision(mode, flatten, flags)`.

| Mode | Meaning | `permits(reducing)` |
|---|---|---|
| `ACTIVE` | Nothing is flagged | any order |
| `REDUCING` | Something is flagged and a position is open | reducing orders only |
| `HALTED` | Something is flagged and the account is flat | nothing |

`flatten` is true only while tripped with a position open. It is a level, not a one-time
signal, so a crash cannot lose it.

## Trips and blocks

A **trip** latches, survives restarts, and flattens. Only a manual `reset` clears it. A
**block** stops new risk without flattening and clears itself when its condition clears.
Every limit names the largest allowed value; the switch acts only when a value exceeds it.

| Reason | Trips when | Blocks when |
|---|---|---|
| `DAILY_LOSS` | loss since the CME session opened exceeds the limit | |
| `DRAWDOWN` | fall from the peak exceeds the limit | |
| `POSITION_CAP` | the broker reports more contracts than allowed | |
| `ORDER_RATE` | submits and modifies in the window exceed the cap | |
| `STALE_MARKET_DATA` | data is too old **with a position open** | data is too old while flat |
| `STALE_EQUITY` | no valid equity reading recently, **with a position open** | the same, while flat |
| `NOT_ARMED` | | state missing or untrusted, lock held, or no equity or position yet |
| `BAD_EQUITY` | | the broker sent NaN, infinity, or a non-positive value |
| `SAVE_FAILED` | | the last state change is not on disk |
| `CLOCK_REGRESSION` | | the clock moved back more than a second |

Stale data only trips when exposed, so the daily 16:00 to 17:00 CT maintenance break does not
trip a flat account every afternoon. "Daily" is the CME session, which opens 17:00 Chicago the
evening before.

## Persistence

The latch, the peak, and the session's opening equity live in a JSON file outside the repo.
Saves are atomic and flushed to disk. Loading rejects a missing, corrupt, non-finite,
wrong-version, wrong-account, or internally inconsistent file, and the switch then refuses to
arm. A lock on the state directory stops a second instance from arming against the same file.

## What the adapter must do

1. Treat a `ValueError` from `Limits.from_mapping` as fatal.
2. Feed `on_equity` and `on_position` from the broker only. Equity is an `int` or `float` (a
   `Decimal` or numpy scalar reads as bad equity forever); position is a signed `int`.
3. Feed `on_equity` more often than `max_equity_age_seconds`, even when the value has not
   changed. If the broker pushes account values only on change or every few minutes, poll it or
   re-feed the last value; otherwise a flat account blocks on stale equity. Measure the broker's
   real cadence before choosing the limit.
4. Call `on_order_action()` before every submit or modify and send only if `permits` allows it.
5. Never report or gate a cancel. A `HALTED` switch must still be able to cancel working orders.
6. Treat an order as reducing only if it is on the side opposite the position and its quantity
   is at most `abs(position)` minus the quantity of reducing orders already working. An order
   that would reverse the position, or stack on exits already working, is not reducing.
7. Call `evaluate()` on a timer at least twice per shortest staleness limit.
8. While `flatten` is true, keep exactly one working flattening order, deduplicated by client
   order ID.
9. Block oversized orders before they are sent; this core detects a breach only after it.
10. Alert on `CRITICAL` log records from `risk.kill_switch`.
11. Call from one thread.

## Limits it does not remove

| Residual risk | Backstop |
|---|---|
| The process dies, so nothing evaluates | A protective order resting at the exchange on every position |
| A trip whose save failed is lost if the process then restarts | `CRITICAL` alert, and the resting protective orders |
| A clock already wrong when the process starts is not flagged | Rollover only moves forward, so it cannot erase the day's loss, and a tick from the future counts as now, so staleness still works |
| The order window resets on restart | The broker adapter's own submit rate limit |
| First start mid-session misses earlier losses | The drawdown limit still applies |
| A position over the cap is caught only after the fill | Pre-trade blocking in the adapter (rule 9) |
| The position report has no freshness of its own | It shares the broker connection with equity, which does |
| Deposits and withdrawals move equity | Both make it trip early, never late |
| POSIX only (`fcntl` locking) | Windows is not a target |

## Running the checks

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
HYPOTHESIS_PROFILE=ci .venv/bin/coverage run -m pytest risk -q && .venv/bin/coverage report
.venv/bin/mypy --strict risk
.venv/bin/mutmut run && PATH="$PWD/.venv/bin:$PATH" .venv/bin/python .github/scripts/check_mutants.py
```

210 tests, 100% branch coverage, and all 549 mutants killed. A test that pins each reason and
each `NOT_ARMED` cause fails if a new one is added without a test, and a stateful property test
checks the safety invariants after every step of random event sequences, restarts, and resets.
