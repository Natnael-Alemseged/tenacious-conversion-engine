from __future__ import annotations

from agent.workflows.kb_inventory import list_kb_doc_paths, list_kb_section_refs


def _posix_paths(paths: list[str]) -> list[str]:
    return [p.replace("\\", "/") for p in paths]


def test_kb_includes_key_seed_docs() -> None:
    paths = _posix_paths(list_kb_doc_paths())
    assert any(p.endswith("/cold.md") for p in paths)
    assert any(p.endswith("/pricing_sheet.md") for p in paths)
    assert any(p.endswith("/case_studies.md") for p in paths)
    assert any("/discovery_transcripts/" in p and p.endswith(".md") for p in paths)
    assert any(p.endswith("/style_guide.md") for p in paths)


def test_kb_section_refs_are_non_empty() -> None:
    refs = _posix_paths(list_kb_section_refs())
    assert len(refs) > 20
    assert any("cold.md#" in r for r in refs)
