"""Random event sequences, restarts, and resets, with the safety invariants checked after every step."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from risk.conftest import ACCOUNT, LIMITS, START, T0, FakeClock
from risk.kill_switch import KillSwitch
from risk.model import Decision, Effect, Mode, Reason
from risk.session import session_id
from risk.state import initialize

settings.register_profile("ci", derandomize=True, max_examples=300, stateful_step_count=40, deadline=None)
settings.register_profile("dev", max_examples=100, stateful_step_count=40, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

EQUITY = st.one_of(
    st.floats(min_value=START - 1000.0, max_value=START + 1000.0),
    st.sampled_from([float("nan"), float("inf"), 0.0, -1.0]),
)


class SwitchMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "switch.json"
        self.clock = FakeClock(T0)
        initialize(self.path, ACCOUNT, START, T0)
        self.switch = KillSwitch(LIMITS, self.path, ACCOUNT, self.clock)
        self.position: int | None = None
        self.decision: Decision = self.switch.evaluate()

    def teardown(self) -> None:
        self.switch.close()
        shutil.rmtree(self.dir)

    @rule(net=EQUITY)
    def equity(self, net: float) -> None:
        self.decision = self.switch.on_equity(net)

    @rule(contracts=st.integers(min_value=-3, max_value=3))
    def position_report(self, contracts: int) -> None:
        self.position = contracts
        self.decision = self.switch.on_position(contracts)

    @rule()
    def tick(self) -> None:
        self.decision = self.switch.on_market_data(self.clock())

    @rule()
    def non_reducing_order(self) -> None:
        self.decision = self.switch.on_order_action()
        if self.decision.has(Reason.ORDER_RATE):
            assert not self.decision.permits(reducing=False)

    @rule(seconds=st.floats(min_value=0.0, max_value=900.0))
    def time_passes(self, seconds: float) -> None:
        self.clock.advance(seconds)
        self.decision = self.switch.evaluate()

    @rule(seconds=st.floats(min_value=0.0, max_value=5.0))
    def clock_steps_back(self, seconds: float) -> None:
        self.clock.advance(-seconds)
        self.decision = self.switch.evaluate()

    @rule()
    def restart(self) -> None:
        latched = {f.reason for f in self.switch.evaluate().flags if f.effect is Effect.TRIP}
        self.switch.close()
        self.switch = KillSwitch(LIMITS, self.path, ACCOUNT, self.clock)
        self.position = None
        self.decision = self.switch.evaluate()
        assert latched <= {f.reason for f in self.decision.flags if f.effect is Effect.TRIP}

    @rule(rebase=st.booleans())
    def reset(self, rebase: bool) -> None:
        before = self.switch.evaluate()
        loss_breached = any(
            f.reason is Reason.DAILY_LOSS and not f.latched for f in before.flags
        )
        session = session_id(self.clock())
        try:
            self.decision = self.switch.reset("property test", rebase_peak=rebase)
        except ValueError:
            return
        if loss_breached and session_id(self.clock()) == session:
            assert self.decision.has(Reason.DAILY_LOSS, Effect.TRIP)

    @invariant()
    def active_only_when_nothing_is_flagged(self) -> None:
        assert (self.decision.mode is Mode.ACTIVE) == (self.decision.flags == ())

    @invariant()
    def flatten_only_when_tripped_and_exposed(self) -> None:
        if self.decision.flatten:
            assert self.decision.tripped
            assert self.decision.mode is Mode.REDUCING
            assert self.position not in (None, 0)

    @invariant()
    def reducing_always_permits_reducing_orders(self) -> None:
        if self.decision.mode is Mode.REDUCING:
            assert self.decision.permits(reducing=True)
            assert not self.decision.permits(reducing=False)


TestSwitchMachine = SwitchMachine.TestCase
