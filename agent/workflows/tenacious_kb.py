from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class MarkdownSection:
    source_path: str
    heading: str
    text: str

    @property
    def ref(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.heading.lower()).strip("-")
        return f"{self.source_path}#{slug}"


@dataclass(frozen=True)
class TenaciousKnowledgeBase:
    """Lightweight markdown knowledge base (no embeddings).

    This is intended to be:
    - auto-discovered from the repo (so adding docs doesn't require rewiring)
    - deterministic (safe for tests and reproducibility)
    """

    root: Path
    sections: tuple[MarkdownSection, ...]

    def find_first(self, *heading_needles: str) -> MarkdownSection | None:
        needles = [n.lower() for n in heading_needles if n]
        for section in self.sections:
            h = section.heading.lower()
            if any(n in h for n in needles):
                return section
        return None

    def find_all(self, *heading_needles: str) -> list[MarkdownSection]:
        needles = [n.lower() for n in heading_needles if n]
        out: list[MarkdownSection] = []
        for section in self.sections:
            h = section.heading.lower()
            if any(n in h for n in needles):
                out.append(section)
        return out

    def doc_refs(self, *sections: MarkdownSection | None) -> list[str]:
        return [s.ref for s in sections if s is not None]

    def find_first_in_source(
        self,
        *,
        source_suffix: str,
        heading: str | None = None,
        heading_contains: str | None = None,
    ) -> MarkdownSection | None:
        """Find a section by constraining both the source file and heading.

        This avoids accidental matches when new docs are added.
        """
        suffix = source_suffix.replace("\\", "/")
        exact = (heading or "").strip().lower()
        contains = (heading_contains or "").strip().lower()
        for section in self.sections:
            src = section.source_path.replace("\\", "/")
            if not src.endswith(suffix):
                continue
            h = section.heading.strip().lower()
            if exact and h == exact:
                return section
            if contains and contains in h:
                return section
        return None


def _read_sections(path: Path) -> list[MarkdownSection]:
    if not path.exists():
        return []
    sections: list[MarkdownSection] = []
    current_heading = path.stem
    current_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            if current_lines:
                sections.append(
                    MarkdownSection(str(path), current_heading, "\n".join(current_lines).strip())
                )
            current_heading = heading.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            MarkdownSection(str(path), current_heading, "\n".join(current_lines).strip())
        )
    return sections


def _discover_doc_paths(root: Path) -> list[Path]:
    # Treat tenacious_sales_data as the primary KB plus the root sales template.
    candidates: list[Path] = []
    candidates.extend(sorted((root / "tenacious_sales_data" / "seed").rglob("*.md")))
    # Policies can be valuable constraints; include them so they're available for selection.
    candidates.extend(sorted((root / "tenacious_sales_data" / "policy").rglob("*.md")))
    # Root-level sales template is a special case.
    candidates.append(root / "Draft Tenacious Sales Materials Template.md")
    # De-dup while preserving order.
    seen: set[str] = set()
    out: list[Path] = []
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


@lru_cache(maxsize=1)
def load_tenacious_kb() -> TenaciousKnowledgeBase:
    # Stable repo root (avoid depending on the process CWD).
    # tenacious_kb.py -> workflows/ -> agent/ -> conversion-engine/
    root = Path(__file__).resolve().parents[2]
    paths = _discover_doc_paths(root)
    sections: list[MarkdownSection] = []
    for p in paths:
        sections.extend(_read_sections(p))
    return TenaciousKnowledgeBase(root=root, sections=tuple(sections))
