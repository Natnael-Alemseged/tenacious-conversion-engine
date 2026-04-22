#!/usr/bin/env python3
"""commit-msg hook: enforces Conventional Commits format and single-change subject lines."""

import re
import sys

VALID_TYPES = {
    "feat",
    "fix",
    "chore",
    "docs",
    "test",
    "refactor",
    "ci",
    "perf",
    "build",
    "style",
    "revert",
}

# type(scope)!: description  OR  type!: description
CONVENTIONAL_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?!?: .+$")

# Flags a subject that bundles two changes: "fix auth and add endpoint"
CONJUNCTION_RE = re.compile(r"\b(and|&)\b", re.IGNORECASE)


def main() -> None:
    msg_file = sys.argv[1]
    with open(msg_file) as f:
        lines = f.read().splitlines()

    subject = next((line for line in lines if line and not line.startswith("#")), "")

    if not subject:
        _fail("Empty commit message.")

    if not CONVENTIONAL_RE.match(subject):
        _fail(
            "Commit message must follow Conventional Commits format.\n"
            f"  Expected : type(scope): description\n"
            f"  Got      : {subject}\n"
            f"  Valid types: {', '.join(sorted(VALID_TYPES))}\n"
            f"  Examples :\n"
            f"    feat(enrichment): add crunchbase funding signal\n"
            f"    fix(integrations): handle hubspot 429 retries\n"
            f"    chore: bump ruff to 0.15"
        )

    commit_type = subject.split("(")[0].split(":")[0].rstrip("!")
    if commit_type not in VALID_TYPES:
        _fail(
            f"Unknown commit type '{commit_type}'.\n  Valid types: {', '.join(sorted(VALID_TYPES))}"
        )

    desc_part = subject.split(": ", 1)[1] if ": " in subject else ""
    if CONJUNCTION_RE.search(desc_part):
        _fail(
            f"Commit message looks like it bundles multiple changes:\n"
            f"  '{subject}'\n"
            f"  Split into separate commits — one change per commit."
        )

    sys.exit(0)


def _fail(msg: str) -> None:
    print(f"\nCOMMIT REJECTED — {msg}\n", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
