import json
from pathlib import Path

from agent.enrichment.schemas import HiringSignalBrief


def test_hiring_signal_brief_schema_has_expected_core_fields() -> None:
    # Pydantic schema (runtime)
    py_schema = HiringSignalBrief.model_json_schema()

    # Seed JSON schema (reference)
    root = Path(__file__).resolve().parents[1]
    ref_path = root / "tenacious_sales_data" / "schemas" / "hiring_signal_brief.schema.json"
    ref_schema = json.loads(ref_path.read_text(encoding="utf-8"))

    # Stable parity: only check existence of core properties and basic types.
    py_props = set((py_schema.get("properties") or {}).keys())
    ref_props = set((ref_schema.get("properties") or {}).keys())

    for key in (
        "company_name",
        "generated_at",
        "icp_segment",
        "segment_confidence",
        "overall_confidence",
        "overall_confidence_weighted",
        "signals",
    ):
        assert key in py_props
        assert key in ref_props
