import subprocess
from pathlib import Path


def test_memo_pdf_is_two_pages_and_nontrivial():
    subprocess.check_call(["uv", "run", "python", "scripts/generate_act5.py", "--final"])
    pdf = Path("act5/memo.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-1.4")
    assert b"/Count 2" in pdf
    assert len(pdf) > 3_000
