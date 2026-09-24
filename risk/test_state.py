from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from risk.conftest import ACCOUNT, START, T0
from risk.model import Cause, Reason
from risk.state import Lock, StateUnavailable, SwitchState, initialize, load, save


def _raw(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text())
    return data


def _write(path: Path, raw: object) -> None:
    path.write_text(json.dumps(raw))


def _cause(path: Path, account: str = ACCOUNT) -> Cause:
    with pytest.raises(StateUnavailable) as info:
        load(path, account)
    return info.value.cause


def test_initialize_then_load_round_trips(state_path: Path) -> None:
    state = load(state_path, ACCOUNT)
    assert state == SwitchState(ACCOUNT, False, (), None, START, date(2026, 9, 22), START)


def test_tripped_state_round_trips(state_path: Path) -> None:
    tripped = replace(
        load(state_path, ACCOUNT), tripped=True, reasons=(Reason.DRAWDOWN,), tripped_at=T0
    )
    save(state_path, tripped)
    assert load(state_path, ACCOUNT) == tripped


def test_initialize_refuses_to_overwrite(state_path: Path) -> None:
    with pytest.raises(FileExistsError):
        initialize(state_path, ACCOUNT, START, T0)


def test_initialize_accepts_small_positive_equity(tmp_path: Path) -> None:
    initialize(tmp_path / "s.json", ACCOUNT, 0.5, T0)
    assert load(tmp_path / "s.json", ACCOUNT).peak_equity == 0.5


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf")])
def test_initialize_rejects_invalid_equity(tmp_path: Path, bad: float) -> None:
    with pytest.raises(ValueError):
        initialize(tmp_path / "s.json", ACCOUNT, bad, T0)


def test_save_leaves_only_the_state_file(state_path: Path) -> None:
    save(state_path, load(state_path, ACCOUNT))
    assert [p.name for p in state_path.parent.iterdir()] == [state_path.name]


def test_half_written_temp_file_does_not_affect_load(state_path: Path) -> None:
    state_path.with_name(state_path.name + ".tmp").write_text('{"version": 1, "trip')
    assert load(state_path, ACCOUNT).peak_equity == START


def test_missing_file(tmp_path: Path) -> None:
    assert _cause(tmp_path / "absent.json") is Cause.STATE_MISSING


def test_unreadable_path_is_corrupt(tmp_path: Path) -> None:
    assert _cause(tmp_path) is Cause.STATE_CORRUPT  # a directory, not a file


def test_invalid_utf8_is_corrupt(state_path: Path) -> None:
    state_path.write_bytes(b"\xff\xfe")
    assert _cause(state_path) is Cause.STATE_CORRUPT


def test_invalid_json_is_corrupt(state_path: Path) -> None:
    state_path.write_text("{not json")
    assert _cause(state_path) is Cause.STATE_CORRUPT


def test_non_object_json_is_corrupt(state_path: Path) -> None:
    _write(state_path, [1, 2])
    assert _cause(state_path) is Cause.STATE_CORRUPT


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_non_finite_numbers_are_rejected(state_path: Path, literal: str) -> None:
    text = state_path.read_text().replace(f'"peak_equity": {START}', f'"peak_equity": {literal}')
    assert literal in text
    state_path.write_text(text)
    assert _cause(state_path) is Cause.STATE_NON_FINITE


def test_version_mismatch(state_path: Path) -> None:
    _write(state_path, {**_raw(state_path), "version": 2})
    assert _cause(state_path) is Cause.STATE_VERSION


def test_account_mismatch(state_path: Path) -> None:
    assert _cause(state_path, account="OTHER") is Cause.STATE_ACCOUNT


@pytest.mark.parametrize(
    "change",
    [
        {"tripped": "yes"},
        {"reasons": "DRAWDOWN"},
        {"reasons": ["NOT_A_REASON"]},
        {"tripped_at": 5},
        {"tripped_at": "2026-09-22T14:00:00"},
        {"session_id": "not a date"},
        {"peak_equity": "8000"},
        {"peak_equity": True},
    ],
)
def test_malformed_fields_are_corrupt(state_path: Path, change: dict[str, object]) -> None:
    _write(state_path, {**_raw(state_path), **change})
    assert _cause(state_path) is Cause.STATE_CORRUPT


def test_missing_field_is_corrupt(state_path: Path) -> None:
    raw = _raw(state_path)
    del raw["peak_equity"]
    _write(state_path, raw)
    assert _cause(state_path) is Cause.STATE_CORRUPT


STAMP = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc).isoformat()


@pytest.mark.parametrize(
    "change",
    [
        {"tripped": True, "reasons": ["DRAWDOWN"], "tripped_at": None},
        {"tripped": False, "reasons": [], "tripped_at": STAMP},
        {"tripped": True, "reasons": [], "tripped_at": STAMP},
        {"tripped": True, "reasons": ["NOT_ARMED"], "tripped_at": STAMP},
        {"peak_equity": 0},
        {"session_start_equity": 0},
        {"session_start_equity": -1},
    ],
)
def test_inconsistent_state_is_rejected(state_path: Path, change: dict[str, object]) -> None:
    _write(state_path, {**_raw(state_path), **change})
    assert _cause(state_path) is Cause.STATE_INVARIANT


def test_lock_is_exclusive_and_released_on_release(tmp_path: Path) -> None:
    first, second = Lock(tmp_path), Lock(tmp_path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
    second.release()  # releasing twice is harmless


def test_lock_in_missing_directory_is_unavailable(tmp_path: Path) -> None:
    assert not Lock(tmp_path / "no-such-dir").acquire()


@pytest.mark.parametrize(
    "change",
    [
        {"peak_equity": float("nan")},
        {"session_start_equity": float("inf")},
        {"tripped": True},
        {"reasons": (Reason.NOT_ARMED,), "tripped": True, "tripped_at": T0},
    ],
)
def test_save_refuses_a_state_load_would_reject(state_path: Path, change: dict[str, object]) -> None:
    bad = replace(load(state_path, ACCOUNT), **change)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        save(state_path, bad)
    assert load(state_path, ACCOUNT).peak_equity == START


def test_state_unavailable_message_is_the_cause() -> None:
    assert str(StateUnavailable(Cause.STATE_MISSING)) == Cause.STATE_MISSING.value


def test_temp_file_is_written_beside_the_state_file(
    state_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources: list[Path] = []
    real_replace = os.replace

    def spy(src: str, dst: Path) -> None:
        sources.append(Path(src))
        real_replace(src, dst)

    monkeypatch.setattr("risk.state.os.replace", spy)
    save(state_path, load(state_path, ACCOUNT))
    assert [p.parent for p in sources] == [state_path.parent]


def test_failed_save_removes_its_temp_file(state_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("risk.state.os.replace", broken)
    with pytest.raises(OSError):
        save(state_path, load(state_path, ACCOUNT))
    assert [p.name for p in state_path.parent.iterdir()] == [state_path.name]
