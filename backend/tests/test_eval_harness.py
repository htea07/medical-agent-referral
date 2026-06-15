"""The harness itself is checked: enforcement leaks nothing and the metrics compute right."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_harness import run


def test_no_leaks_and_all_scenarios_pass():
    report = run()
    # The privacy-critical invariant: nothing the intent marks must-withhold is disclosed.
    assert report["leak_rate"] == 0.0
    assert report["leaked"] == 0
    # And the enforcement matches intent exactly on every scenario (no over-withholding either).
    assert report["passed"] == report["scenarios"]
    assert report["over_withhold_rate"] == 0.0


def test_redaction_recall_catches_structured_but_misses_the_name():
    report = run()
    # 5 planted identifiers; regex masks the 4 structured ones, misses the name.
    assert report["planted_total"] == 5
    assert report["planted_redacted"] == 4
    assert 0.7 < report["redaction_recall"] < 0.85
