## Worked examples (schema-valid)

These are **committed examples** that validate against the JSON Schemas in
`tenacious_sales_data/schemas/`.

- `hiring_signal_brief.example.json` validates against `tenacious_sales_data/schemas/hiring_signal_brief.schema.json`
- `competitor_gap_brief.example.json` validates against `tenacious_sales_data/schemas/competitor_gap_brief.schema.json`

To verify:

```bash
uv run pytest -q tests/test_schema_examples.py
```

