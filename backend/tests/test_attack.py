"""The injection payload lives in a withheld record and never reaches disclosed output."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import samples
import scope
from sanitize import redact_safe_harbor


def test_injection_is_in_a_record_but_never_disclosed():
    a = samples.ATTACK_SAMPLE
    # The payload really is present somewhere in the patient's chart...
    assert any(samples.INJECTION in r.summary for r in a.patient.records)

    disclosed, withheld = scope.disclosable_records(a.patient, a.referral, a.consent)

    # ...but it sits in a WITHHELD record, so it never enters what the specialist sees.
    disclosed_text = " ".join(redact_safe_harbor(r.summary) for r in disclosed)
    assert samples.INJECTION not in disclosed_text
    assert any(samples.INJECTION in r.summary for r in withheld)
    # And the disclosed set is only the in-scope cardiology records.
    assert {r.specialty_tag for r in disclosed} == {"cardiology"}
