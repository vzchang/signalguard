"""Fail unless mutmut killed every mutant; mutmut itself exits 0 when mutants survive."""

import json
import subprocess
import sys

STATS = "mutants/mutmut-cicd-stats.json"
FAILING = ("survived", "no_tests", "timeout", "suspicious", "segfault")

subprocess.run(["mutmut", "export-cicd-stats"], check=True, capture_output=True)
with open(STATS) as f:
    stats = json.load(f)
print(json.dumps(stats, indent=2))
if stats["total"] == 0 or any(stats[k] for k in FAILING):
    print(subprocess.run(["mutmut", "results"], capture_output=True, text=True).stdout)
    sys.exit("mutation gate failed: every mutant must be killed, or its line marked equivalent")
