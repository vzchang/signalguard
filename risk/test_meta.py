"""Guards on the source itself: rules a behavioral test cannot see."""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent
SOURCES = sorted(p for p in HERE.glob("*.py") if not p.name.startswith("test_") and p.name != "conftest.py")
ALL = sorted(HERE.glob("*.py"))


def test_sources_are_found() -> None:
    assert {p.name for p in SOURCES} == {"__init__.py", "kill_switch.py", "model.py", "session.py", "state.py"}


def test_no_real_time_in_source() -> None:
    # the clock is injected (prime directive 1); reading real time breaks backtest parity
    banned = ("datetime.now", "datetime.utcnow", "time.time", "time.monotonic", "date.today")
    hits = [f"{p.name}: {b}" for p in SOURCES for b in banned if b in p.read_text()]
    assert hits == []


def test_no_coverage_exclusions() -> None:
    marker = "pragma: " + "no cover"
    assert [p.name for p in ALL if marker in p.read_text()] == []


def test_every_mutation_pragma_states_why_it_is_equivalent() -> None:
    marker = "pragma: " + "no mutate"
    lines = [line for p in SOURCES for line in p.read_text().splitlines() if marker in line]
    assert lines  # the known equivalents exist; if none remain, delete this test's premise
    assert [line for line in lines if "(equivalent: " not in line] == []
