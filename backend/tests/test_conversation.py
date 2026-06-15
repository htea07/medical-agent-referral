"""Every sample builds a coherent transcript with a sealed ledger — and the cases behave."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import samples
from conversation import PCP, SPEC, build_transcript


def test_every_sample_builds_seals_and_summarizes():
    assert samples.SAMPLES
    for s in samples.SAMPLES:
        turns, audit, summary = build_transcript(s)
        assert turns and audit.verify()
        assert summary and "ledger sealed and verified" in summary.lower()
        roles = {t[0] for t in turns}
        assert PCP in roles and SPEC in roles


def test_denied_case_discloses_nothing():
    s = next(x for x in samples.SAMPLES if "denied" in x.title)
    _, audit, _ = build_transcript(s)
    discloses = [e for e in audit if e.action == "disclose_records"]
    assert discloses[-1].disclosed_ids == ()


def test_emergency_case_discloses_everything():
    s = next(x for x in samples.SAMPLES if "emergency" in x.title)
    _, audit, _ = build_transcript(s)
    discloses = [e for e in audit if e.action == "disclose_records"]
    assert discloses[-1].withheld_ids == () and discloses[-1].break_glass is True


def test_genetic_escalation_is_denied():
    s = next(x for x in samples.SAMPLES if "genetic" in x.title)
    _, audit, _ = build_transcript(s)
    escs = [e for e in audit if e.action == "escalation_request"]
    assert escs and all(e.decision == "denied" for e in escs)
