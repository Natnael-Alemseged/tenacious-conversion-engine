from __future__ import annotations

from agent.workflows.lead_orchestrator import _build_subject


def test_subject_under_60_chars_unchanged() -> None:
    subj = _build_subject("Acme", 1)
    assert len(subj) <= 60
    assert "Acme" in subj


def test_subject_long_company_name_truncated_p015() -> None:
    long_name = "NovaCure Machine Learning Infrastructure"
    for seg in range(5):
        subj = _build_subject(long_name, seg)
        assert len(subj) <= 60, f"seg={seg} subject too long ({len(subj)}): {subj!r}"


def test_subject_medium_company_name_truncated() -> None:
    medium_name = "DataBridge Analytics Corporation"
    for seg in range(5):
        subj = _build_subject(medium_name, seg)
        assert len(subj) <= 60, f"seg={seg} subject too long ({len(subj)}): {subj!r}"


def test_subject_unknown_segment_uses_fallback() -> None:
    subj = _build_subject("Acme", 99)
    assert len(subj) <= 60
    assert "Acme" in subj
