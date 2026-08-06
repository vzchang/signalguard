"""
One command to prove the whole demo suite works: run every demo, every test, and
regenerate every chart. Exits non-zero if anything fails, so CI can gate on it.

Run:  python3 run_all.py
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent

DEMOS = [
    "deflated_sharpe_demo.py",
    "purged_cv_demo.py",
    "lookahead_detector_demo.py",
    "walk_forward_demo.py",
    "gate_demo.py",
    "real_data_gate.py",
]
TESTS = [
    "test_deflated_sharpe.py",
    "test_purged_cv.py",
    "test_lookahead_detector.py",
    "test_walk_forward.py",
    "test_gate.py",
    "test_real_data_gate.py",
]
PLOTS = [
    "plot_noise_distribution.py",
    "plot_purged_cv.py",
    "plot_lookahead.py",
    "plot_walk_forward.py",
]


def run(script: str) -> bool:
    r = subprocess.run([sys.executable, script], cwd=HERE,
                       capture_output=True, text=True)
    ok = r.returncode == 0
    tail = (r.stdout.strip().splitlines() or [""])[-1] if ok else (r.stderr.strip().splitlines() or [""])[-1]
    print(f"  [{'OK  ' if ok else 'FAIL'}] {script:32} {tail[:44]}")
    return ok


def main() -> int:
    print("demos"); demos_ok = all([run(s) for s in DEMOS])
    print("tests"); tests_ok = all([run(s) for s in TESTS])
    print("charts"); plots_ok = all([run(s) for s in PLOTS])
    ok = demos_ok and tests_ok and plots_ok
    print()
    print("ALL GREEN" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
