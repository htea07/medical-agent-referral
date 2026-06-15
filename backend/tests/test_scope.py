"""
Run from the backend/ directory:  pytest
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from audit import AuditLog
from models import Consent, Patient, Record, Referral, Scope
from scope import demographics_visible, disclosable_records


@pytest.fixture
def patient() -> Patient:
    return Patient(
        id="p1",
        name="Test Patient",
        dob="1980-01-01",
        insurance="TEST-1",
        records=(
            Record("r_card", "cardiology", "AFib on warfarin"),
            Record("r_psych", "psychiatry", "GAD on sertraline"),
            Record("r_id", "infectious_disease", "HSV-2 positive"),
        ),
    )


@pytest.fixture
def referral() -> Referral:
    return Referral(
        id="ref1",
        patient_id="p1",
        specialist_org="cardio",
        reason="arrhythmia workup",
        relevant_tags=frozenset({"cardiology"}),
    )


def _consent(scope: Scope) -> Consent:
    return Consent(patient_id="p1", specialist_org="cardio", referral_id="ref1", scope=scope)


def _patient_with_protected() -> Patient:
    # An ordinary cardiology record plus an HIV record that is NOT clinically relevant
    # to the referral — so the only thing that can disclose it is specific authorization.
    return Patient(
        id="p1",
        name="T",
        dob="1980-01-01",
        insurance="X",
        records=(
            Record("r_card", "cardiology", "AFib on warfarin"),
            Record("r_hiv", "infectious_disease", "HIV+ on ART", protected_category="hiv"),
        ),
    )


def test_protected_record_withheld_without_specific_authorization(referral):
    # No special-category authorization -> the protected record is withheld even though
    # consent scope is REFERRAL_RELEVANT.
    p = _patient_with_protected()
    disclosed, withheld = disclosable_records(p, referral, _consent(Scope.REFERRAL_RELEVANT))
    assert [r.id for r in disclosed] == ["r_card"]
    assert [r.id for r in withheld] == ["r_hiv"]


def test_protected_record_disclosed_only_with_specific_authorization(referral):
    # With the specific authorization, the protected record discloses — and note it does
    # so despite infectious_disease NOT being in the referral's relevant_tags: protected
    # data is gated on consent, not relevance.
    p = _patient_with_protected()
    consent = Consent(
        patient_id="p1",
        specialist_org="cardio",
        referral_id="ref1",
        scope=Scope.REFERRAL_RELEVANT,
        authorized_categories=frozenset({"hiv"}),
    )
    disclosed, withheld = disclosable_records(p, referral, consent)
    assert {r.id for r in disclosed} == {"r_card", "r_hiv"}
    assert withheld == []


def test_referral_relevant_discloses_only_matching_tag(patient, referral):
    disclosed, withheld = disclosable_records(patient, referral, _consent(Scope.REFERRAL_RELEVANT))
    assert [r.id for r in disclosed] == ["r_card"]
    assert {r.specialty_tag for r in withheld} == {"psychiatry", "infectious_disease"}


def test_denied_discloses_nothing(patient, referral):
    disclosed, withheld = disclosable_records(patient, referral, _consent(Scope.DENIED))
    assert disclosed == []
    assert len(withheld) == len(patient.records)


def test_demographics_only_discloses_no_clinical_records(patient, referral):
    disclosed, withheld = disclosable_records(patient, referral, _consent(Scope.DEMOGRAPHICS_ONLY))
    assert disclosed == []
    assert len(withheld) == len(patient.records)


def test_emergency_discloses_everything_and_logs(patient, referral):
    audit = AuditLog()
    disclosed, withheld = disclosable_records(
        patient, referral, _consent(Scope.EMERGENCY), audit_log=audit
    )
    assert len(disclosed) == len(patient.records)
    assert withheld == []
    # Break-glass access is allowed but must be recorded.
    assert len(audit) == 1
    assert audit[0].action == "disclose_records"
    assert audit[0].decision == "full"
    assert audit[0].break_glass is True


def test_every_disclosure_is_logged_not_just_emergency(patient, referral):
    # The whole point of the audit upgrade: ordinary, partial disclosures are
    # recorded too, with the exact ids disclosed and withheld.
    audit = AuditLog()
    disclosable_records(patient, referral, _consent(Scope.REFERRAL_RELEVANT), audit_log=audit)
    assert len(audit) == 1
    entry = audit[0]
    assert entry.action == "disclose_records"
    assert entry.decision == "partial"
    assert entry.break_glass is False
    assert entry.disclosed_ids == ("r_card",)
    assert set(entry.withheld_ids) == {"r_psych", "r_id"}


def test_denied_disclosure_is_logged_as_denied(patient, referral):
    audit = AuditLog()
    disclosable_records(patient, referral, _consent(Scope.DENIED), audit_log=audit)
    assert len(audit) == 1 and audit[0].decision == "denied"


def test_disclosed_and_withheld_partition_all_records(patient, referral):
    # Invariant: nothing silently disappears, at every scope level.
    for scope in Scope:
        disclosed, withheld = disclosable_records(patient, referral, _consent(scope))
        assert len(disclosed) + len(withheld) == len(patient.records)


def test_consent_for_wrong_referral_discloses_nothing(patient, referral):
    wrong = Consent(patient_id="p1", specialist_org="cardio", referral_id="OTHER", scope=Scope.EMERGENCY)
    disclosed, withheld = disclosable_records(patient, referral, wrong)
    assert disclosed == []  # even EMERGENCY scope can't cross referrals
    assert len(withheld) == len(patient.records)


def test_demographics_visibility_threshold():
    assert not demographics_visible(_consent(Scope.DENIED))
    assert demographics_visible(_consent(Scope.DEMOGRAPHICS_ONLY))
    assert demographics_visible(_consent(Scope.REFERRAL_RELEVANT))
    assert demographics_visible(_consent(Scope.EMERGENCY))
