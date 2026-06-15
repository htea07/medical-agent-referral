"""Escalation / clinical-drift path: the specialist asks, the consent policy answers.

Two things are proven here, both without an API key:
  1. evaluate_escalation is a pure policy decision (grant only pre-consented tags).
  2. a granted escalation actually widens what the *next* request_records discloses,
     and every step lands in the decision log.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import data
import specialist_tools
from audit import AuditLog
from models import Consent, Scope
from scope import evaluate_escalation


def _consent(scope: Scope, allowed: set[str] | None = None) -> Consent:
    return Consent(
        patient_id="p1",
        specialist_org="cardio",
        referral_id="ref1",
        scope=scope,
        escalation_allowed_tags=frozenset(allowed or set()),
    )


# --- pure policy decision -------------------------------------------------

def test_escalation_granted_for_preconsented_tag():
    granted, rationale = evaluate_escalation(_consent(Scope.REFERRAL_RELEVANT, {"pulmonology"}), "pulmonology")
    assert granted is True
    assert "pulmonology" in rationale


def test_escalation_denied_for_non_preconsented_tag():
    granted, _ = evaluate_escalation(_consent(Scope.REFERRAL_RELEVANT, {"pulmonology"}), "psychiatry")
    assert granted is False


def test_escalation_impossible_when_consent_denied():
    granted, _ = evaluate_escalation(_consent(Scope.DENIED, {"pulmonology"}), "pulmonology")
    assert granted is False


def test_escalation_denied_for_protected_category():
    # Even if the patient pre-consented to *some* escalation, a specially protected
    # category (Part 2 / psychotherapy / HIV) can never be reached this way — it needs a
    # specific written authorization an agent can't substitute for.
    granted, rationale = evaluate_escalation(_consent(Scope.REFERRAL_RELEVANT, {"pulmonology"}), "sud")
    assert granted is False
    assert "specifically" in rationale or "specific written" in rationale or "Part 2" in rationale


# --- full tool-layer loop on the seeded synthetic referral ----------------

@pytest.fixture
def restore_referral():
    """The grant mutates the shared store; snapshot and restore around the test."""
    before = data.get_referral("ref_001")
    yield
    data._REFERRALS["ref_001"] = before


def test_grant_then_rediscloses_and_logs_every_step(restore_referral):
    audit = AuditLog()

    r1 = specialist_tools.run_request_records("ref_001", audit_log=audit)
    n_before = len(r1["disclosed_records"])

    esc = specialist_tools.run_request_additional_scope(
        "ref_001", "pulmonology", "AFib + planned surgery: need prior clot/anticoag history", audit_log=audit
    )
    assert esc["granted"] is True

    r2 = specialist_tools.run_request_records("ref_001", audit_log=audit)
    assert len(r2["disclosed_records"]) > n_before  # the pulmonology record is now in scope
    assert any(rec["specialty"] == "pulmonology" for rec in r2["disclosed_records"])

    # Every decision — two disclosures bracketing one grant — is recorded, in order.
    assert [e.action for e in audit] == [
        "disclose_records",
        "escalation_request",
        "disclose_records",
    ]
    assert audit[1].decision == "granted" and audit[1].requested_tag == "pulmonology"

    # Eyeball the enforcement trace with: pytest -s
    print("\n--- decision log: grant then re-disclose ---")
    print(audit.pretty())


def test_denied_escalation_does_not_widen_scope(restore_referral):
    audit = AuditLog()
    r1 = specialist_tools.run_request_records("ref_001", audit_log=audit)
    n_before = len(r1["disclosed_records"])

    # Ordinary specialty the patient did NOT pre-consent to -> routed for manual review.
    esc = specialist_tools.run_request_additional_scope(
        "ref_001", "dermatology", "noticed an unrelated skin finding", audit_log=audit
    )
    assert esc["granted"] is False

    r2 = specialist_tools.run_request_records("ref_001", audit_log=audit)
    assert len(r2["disclosed_records"]) == n_before  # nothing widened
    assert audit[1].action == "escalation_request" and audit[1].decision == "denied"


def test_protected_category_escalation_denied_on_real_data(restore_referral):
    # The patient's SUD record exists and might even seem relevant, but a request to widen
    # into it is refused at the policy layer — Part 2 needs a specific signed authorization.
    audit = AuditLog()
    esc = specialist_tools.run_request_additional_scope(
        "ref_001", "sud", "anticoagulation interacts with alcohol use", audit_log=audit
    )
    assert esc["granted"] is False
    r = specialist_tools.run_request_records("ref_001", audit_log=audit)
    assert all(rec["specialty"] != "addiction_medicine" for rec in r["disclosed_records"])
