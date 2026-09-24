"""Persisted kill switch state: atomic save, validating load, and the process lock."""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from risk.model import EFFECTS, Cause, Effect, Reason
from risk.session import session_id

VERSION = 1


class StateUnavailable(Exception):
    """The state file cannot be trusted; `cause` says why."""

    def __init__(self, cause: Cause) -> None:
        super().__init__(cause.value)
        self.cause = cause


@dataclass(frozen=True)
class SwitchState:
    """What survives a restart: the latch, the peak, and the session's opening equity."""

    account_id: str
    tripped: bool
    reasons: tuple[Reason, ...]
    tripped_at: datetime | None
    peak_equity: float
    session_id: date
    session_start_equity: float


def consistent(state: SwitchState) -> bool:
    """Whether a state satisfies the invariants load enforces; save refuses anything else."""
    return (
        state.tripped == (state.tripped_at is not None)
        and state.tripped == bool(state.reasons)
        and all(Effect.TRIP in EFFECTS[r] for r in state.reasons)
        and math.isfinite(state.peak_equity)
        and math.isfinite(state.session_start_equity)
        and state.peak_equity > 0
        and state.session_start_equity > 0
    )


def save(path: Path, state: SwitchState) -> None:
    """Replace the state file atomically, and durably across a power loss."""
    if not consistent(state):
        raise ValueError(f"refusing to save an inconsistent state: {state!r}")
    data = json.dumps(
        {
            "version": VERSION,
            "account_id": state.account_id,
            "tripped": state.tripped,
            "reasons": [r.value for r in state.reasons],
            "tripped_at": None if state.tripped_at is None else state.tripped_at.isoformat(),
            "peak_equity": state.peak_equity,
            "session_id": state.session_id.isoformat(),
            "session_start_equity": state.session_start_equity,
        }
    )
    # same directory as the target: rename is only atomic within one filesystem
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:  # json.dumps output is pure ASCII
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        os.unlink(tmp)  # a save retried on every event must not pile up temp files
        raise
    # the rename is only durable once the directory entry itself is flushed
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def initialize(path: Path, account_id: str, net_liq: float, now: datetime) -> None:
    """Create the first state file; refuses to overwrite one that exists."""
    if path.exists():
        raise FileExistsError(path)
    value = float(net_liq)  # save rejects a non-finite or non-positive value
    save(path, SwitchState(account_id, False, (), None, value, session_id(now), value))


def _number(raw: dict[str, Any], key: str) -> float:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(key)
    # json.loads accepts NaN and Infinity, and 1e999 overflows to inf; a NaN peak disarms drawdown
    if not math.isfinite(value):
        raise StateUnavailable(Cause.STATE_NON_FINITE)
    return float(value)


def _parse(raw: dict[str, Any]) -> SwitchState:
    tripped = raw["tripped"]
    reasons = raw["reasons"]
    stamp = raw["tripped_at"]
    if not isinstance(tripped, bool) or not isinstance(reasons, list):
        raise TypeError("tripped or reasons")
    tripped_at = None if stamp is None else datetime.fromisoformat(stamp)
    if tripped_at is not None and tripped_at.tzinfo is None:
        raise ValueError("naive tripped_at")
    return SwitchState(
        account_id=raw["account_id"],
        tripped=tripped,
        reasons=tuple(Reason(r) for r in reasons),
        tripped_at=tripped_at,
        peak_equity=_number(raw, "peak_equity"),
        session_id=date.fromisoformat(raw["session_id"]),
        session_start_equity=_number(raw, "session_start_equity"),
    )


def load(path: Path, account_id: str) -> SwitchState:
    """Read and validate the state file; any doubt raises StateUnavailable."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise StateUnavailable(Cause.STATE_MISSING) from None
    except OSError:
        raise StateUnavailable(Cause.STATE_CORRUPT) from None
    try:
        raw = json.loads(data)  # detects the encoding from the bytes
    except ValueError:  # JSONDecodeError and UnicodeDecodeError are both ValueErrors
        raise StateUnavailable(Cause.STATE_CORRUPT) from None
    if not isinstance(raw, dict):
        raise StateUnavailable(Cause.STATE_CORRUPT)
    if raw.get("version") != VERSION:
        raise StateUnavailable(Cause.STATE_VERSION)
    if raw.get("account_id") != account_id:
        raise StateUnavailable(Cause.STATE_ACCOUNT)
    try:
        state = _parse(raw)
    except (KeyError, TypeError, ValueError):
        raise StateUnavailable(Cause.STATE_CORRUPT) from None
    if not consistent(state):
        raise StateUnavailable(Cause.STATE_INVARIANT)
    return state


class Lock:
    """Exclusive flock on the state file's directory, held for the life of the process."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._fd: int | None = None

    def acquire(self) -> bool:
        """Take the lock without waiting; False if another process holds it."""
        # the directory, not the file: os.replace swaps the file's inode on every save
        try:
            fd = os.open(self._directory, os.O_RDONLY)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    def release(self) -> None:
        """Drop the lock; safe to call twice."""
        if self._fd is not None:
            os.close(self._fd)  # closing the descriptor drops the flock
            self._fd = None
