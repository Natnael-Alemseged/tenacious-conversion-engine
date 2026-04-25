from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InvoiceSummary:
    currency: str
    total_cost_usd: float
    line_items: list[dict[str, Any]]
    window: dict[str, Any]


def read_invoice(path: Path) -> InvoiceSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return InvoiceSummary(
        currency=str(payload.get("currency") or "USD"),
        total_cost_usd=float(payload.get("total_cost_usd") or 0.0),
        line_items=list(payload.get("line_items") or []),
        window=dict(payload.get("window") or {}),
    )


def write_rollup(*, invoices: list[Path], out_path: Path) -> InvoiceSummary:
    items: list[dict[str, Any]] = []
    total = 0.0
    for inv_path in invoices:
        inv = read_invoice(inv_path)
        total += inv.total_cost_usd
        items.append(
            {
                "source_path": str(inv_path),
                "currency": inv.currency,
                "total_cost_usd": inv.total_cost_usd,
                "line_items": inv.line_items,
                "window": inv.window,
            }
        )
    summary = {
        "currency": "USD",
        "window": {"kind": "rollup"},
        "invoices": items,
        "total_cost_usd": total,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return InvoiceSummary(
        currency="USD",
        total_cost_usd=total,
        line_items=items,
        window=summary["window"],
    )
