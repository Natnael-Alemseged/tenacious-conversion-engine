import json
from pathlib import Path

import jsonschema


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_hiring_signal_example_validates_against_schema() -> None:
    schema = _load("tenacious_sales_data/schemas/hiring_signal_brief.schema.json")
    example = _load("docs/worked_examples/hiring_signal_brief.example.json")
    jsonschema.validate(instance=example, schema=schema)


def test_competitor_gap_example_validates_against_schema() -> None:
    schema = _load("tenacious_sales_data/schemas/competitor_gap_brief.schema.json")
    example = _load("docs/worked_examples/competitor_gap_brief.example.json")
    jsonschema.validate(instance=example, schema=schema)
