import json
from pathlib import Path


def test_evidence_graph_includes_memo_and_citations():
    evidence = json.loads(Path("act5/evidence_graph.json").read_text(encoding="utf-8"))
    assert "claims" in evidence and isinstance(evidence["claims"], list)
    # This will fail until generate_act5.py emits the new structure.
    assert "memo" in evidence and isinstance(evidence["memo"], dict)
    assert "citations" in evidence and isinstance(evidence["citations"], dict)
