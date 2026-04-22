#!/usr/bin/env python3
"""pre-commit hook: rejects commits that mix files from unrelated app modules."""

import subprocess
import sys
from pathlib import Path

# These top-level dirs may always accompany any app module change.
NEUTRAL_ROOTS = {"tests", "eval", "scripts", "docs", "probes", ".github"}


def module_group(path: str) -> str | None:
    """Return the module group for a file path, or None if the file is neutral."""
    parts = Path(path).parts
    if len(parts) == 1:
        return None  # root config file — neutral
    root = parts[0]
    if root in NEUTRAL_ROOTS:
        return None
    if root == "app" and len(parts) >= 2:
        return f"app/{parts[1]}"
    return None  # anything else is neutral


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [f for f in result.stdout.splitlines() if f]


def main() -> None:
    staged = get_staged_files()
    if not staged:
        sys.exit(0)

    modules: dict[str, list[str]] = {}
    for f in staged:
        group = module_group(f)
        if group:
            modules.setdefault(group, []).append(f)

    if len(modules) > 1:
        lines = ["\nCOMMIT REJECTED — staged files span multiple unrelated modules:\n"]
        for group in sorted(modules):
            lines.append(f"  {group}/")
            for f in modules[group]:
                lines.append(f"    {f}")
        lines.append("")
        lines.append("  Split into separate commits, one per module.")
        lines.append("  Use 'git restore --staged <file>' to unstage individual files.")
        lines.append("  To override: git commit --no-verify\n")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
