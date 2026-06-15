"""Stage 1 sanitizer: structured Safe Harbor identifiers are masked, clinical text isn't."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sanitize import redact_safe_harbor


def test_redacts_structured_identifiers():
    text = "Seen 2026-01-08 (MRN R445789, call 617-555-0142, ssn 123-45-6789, mail a@b.com)."
    out = redact_safe_harbor(text)
    for raw in ("R445789", "617-555-0142", "123-45-6789", "2026-01-08", "a@b.com"):
        assert raw not in out
    for label in ("MRN", "PHONE", "SSN", "DATE", "EMAIL"):
        assert f"[REDACTED: {label}]" in out


def test_clinical_content_is_preserved():
    out = redact_safe_harbor("Dx atrial fibrillation; on warfarin 5mg daily.")
    assert "atrial fibrillation" in out and "warfarin" in out


def test_names_are_not_caught_by_regex():
    # Honest limitation: regex can't reliably catch names — that's the deferred BERT job.
    assert "Dr. Alan Cho" in redact_safe_harbor("Ordered by Dr. Alan Cho.")
