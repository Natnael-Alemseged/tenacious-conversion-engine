from __future__ import annotations

from agent.workflows.tenacious_kb import load_tenacious_kb


def list_kb_doc_paths() -> list[str]:
    kb = load_tenacious_kb()
    # Deterministic: unique paths, sorted (sets unify duplicates).
    return sorted({s.source_path for s in kb.sections})


def list_kb_section_refs() -> list[str]:
    kb = load_tenacious_kb()
    return [s.ref for s in kb.sections]
