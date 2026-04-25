from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    """
    Golden-path rubric demonstration.

    This script is intentionally offline-safe: it reads committed example artifacts that
    demonstrate the expected shapes (velocity delta, competitor distribution, booking-link parity)
    without requiring live network calls.
    """
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "artifacts"
    hiring = json.loads((artifacts / "sample_hiring_signal_brief_generated.json").read_text())
    gap = json.loads((artifacts / "sample_competitor_gap_brief_generated.json").read_text())

    print("Hiring signal brief:")
    print(f"- domain: {hiring.get('prospect_domain')}")
    print(f"- velocity: {hiring.get('hiring_velocity')}")
    print("")
    print("Competitor gap brief:")
    print(f"- competitors_analyzed: {len(gap.get('competitors_analyzed', []))}")
    print(f"- gap_findings: {len(gap.get('gap_findings', []))}")
    print("")
    print("Booking-link parity examples:")
    print((artifacts / "sms_email_booking_link_examples.md").read_text())


if __name__ == "__main__":
    main()
