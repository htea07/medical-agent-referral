"""The decision ledger is hash-chained: it verifies clean and detects tampering."""

from __future__ import annotations

import dataclasses
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audit import AuditLog, DecisionEntry


def _entry(action: str = "disclose_records", decision: str = "partial") -> DecisionEntry:
    return DecisionEntry(
        action=action,
        patient_id="p",
        referral_id="r",
        specialist_org="o",
        scope="REFERRAL_RELEVANT",
        decision=decision,
    )


def test_fresh_log_verifies():
    a = AuditLog()
    a.record(_entry())
    a.record(_entry(action="escalation_request", decision="granted"))
    assert a.verify() is True


def test_entries_are_chained_to_their_predecessor():
    a = AuditLog()
    e1 = a.record(_entry())
    e2 = a.record(_entry())
    assert e1.prev_hash == "0" * 64          # genesis
    assert e2.prev_hash == e1.entry_hash     # each link points at the last


def test_tampering_breaks_the_chain():
    a = AuditLog()
    a.record(_entry(decision="partial"))
    a.record(_entry(decision="granted"))
    # Forge entry 0: change the recorded decision but keep its now-stale hash.
    a.entries[0] = dataclasses.replace(a.entries[0], decision="full")
    assert a.verify() is False
