from __future__ import annotations

from pathlib import Path
from typing import Any


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_page_stream(lines: list[str]) -> bytes:
    # Very small, deterministic PDF page stream using built-in Helvetica.
    # This is intentionally minimal to avoid external deps.
    y = 760
    ops: list[str] = ["BT", "/F1 12 Tf"]
    for line in lines:
        safe = _escape_pdf_text(line)[:160]
        ops.append(f"72 {y} Td ({safe}) Tj")
        y -= 16
    ops.append("ET")
    return ("\n".join(ops) + "\n").encode("utf-8")


def render_memo_pdf(*, evidence: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    claim_map = {cl["claim_id"]: cl for cl in evidence.get("claims", [])}
    sealed = claim_map.get("tau2_sealed_pass_at_1", {})
    auto = claim_map.get("tau2_auto_opt_sealed_pass_at_1", {})
    cost = claim_map.get("total_cost_usd", {})
    cg = claim_map.get("competitive_gap_reply_rate", {})
    gen = claim_map.get("generic_reply_rate", {})
    delta = claim_map.get("competitive_gap_reply_rate_delta", {})
    stalled = claim_map.get("stalled_thread_rate", {})
    cpl = claim_map.get("cost_per_qualified_lead", {})

    page1 = [
        "Tenacious Conversion Engine — Act V Memo (DRAFT)",
        "Page 1/2 — The Decision",
        "",
        f"τ² sealed pass@1: {sealed.get('value')}",
        f"Auto-opt sealed pass@1: {auto.get('value')}",
        f"Measured total cost (USD): {cost.get('value')}",
        f"Competitive-gap reply rate: {cg.get('value')}",
        f"Generic reply rate: {gen.get('value')}",
        f"Reply-rate delta (cg - gen): {delta.get('value')}",
        f"Stalled-thread rate (no booking_created): {stalled.get('value')}",
        f"Cost per qualified lead (USD): {cpl.get('value')}",
        "",
        "Pilot recommendation: Segment 2 email-first pilot, 30 days.",
    ]
    page2 = [
        "Page 2/2 — The Skeptic’s Appendix (DRAFT)",
        "",
        "1) Offshore-perception objection risk (see transcripts).",
        "2) Bench mismatch risk (see seed/bench_summary.json).",
        "3) Public-signal lossiness risk (false positives/negatives).",
        "4) Gap-analysis framing risk (avoid condescension).",
        "",
        "Kill-switch: pause if wrong-signal rate exceeds threshold.",
    ]

    stream1 = _pdf_page_stream(page1)
    stream2 = _pdf_page_stream(page2)

    # Build a minimal 2-page PDF.
    # Objects: catalog, pages, page1, page2, font, content1, content2
    objects: list[bytes] = []

    def obj(data: str | bytes) -> int:
        if isinstance(data, str):
            data_b = data.encode("utf-8")
        else:
            data_b = data
        objects.append(data_b)
        return len(objects)

    font_id = obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content1_id = obj(b"<< /Length %d >>\nstream\n" % len(stream1) + stream1 + b"endstream")
    content2_id = obj(b"<< /Length %d >>\nstream\n" % len(stream2) + stream2 + b"endstream")

    page1_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
        f"/Contents {content1_id} 0 R >>"
    )
    page2_id = obj(
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
        f"/Contents {content2_id} 0 R >>"
    )
    pages_id = obj(f"<< /Type /Pages /Kids [{page1_id} 0 R {page2_id} 0 R] /Count 2 >>")
    catalog_id = obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    # Write xref
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = [0]
    body = bytearray()
    body.extend(header)
    for i, data in enumerate(objects, start=1):
        offsets.append(len(body))
        body.extend(f"{i} 0 obj\n".encode())
        body.extend(data)
        body.extend(b"\nendobj\n")
    xref_start = len(body)
    body.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    body.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        body.extend(f"{off:010d} 00000 n \n".encode())
    body.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF\n"
        ).encode()
    )
    out_path.write_bytes(bytes(body))
