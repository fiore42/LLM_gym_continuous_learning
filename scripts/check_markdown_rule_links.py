#!/usr/bin/env python3
"""Verify that every project Markdown file links to PROJECT_RULES.md."""

import argparse
import re
import sys
from pathlib import Path


RULES_LINK = re.compile(r"\]\([^)]*PROJECT_RULES\.md\)")
# "data" holds generated runtime output, not project documentation. A note
# written beside a trace is an artifact of a run, and requiring it to carry a
# rules link would make this check fail on ordinary use.
SKIP_DIRECTORIES = {".git", ".venv", ".pytest_cache", "__pycache__", "data"}


def ignored_root_markdown_names(root: Path) -> set[str]:
    """Return exact root-level Markdown names excluded by ``.gitignore``.

    Personal notes such as ``.fieldnotes.md`` and generated review files are
    deliberately outside the repository contract. Only exact filename rules
    are interpreted here; project documentation in subdirectories still has
    to carry the rules link.
    """
    ignore_file = root / ".gitignore"
    if not ignore_file.is_file():
        return set()
    names: set[str] = set()
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        rule = raw.strip()
        if (not rule or rule.startswith(("#", "!")) or "/" in rule
                or not rule.endswith(".md") or any(char in rule for char in "*?[]")):
            continue
        names.add(rule)
    return names


def markdown_files_to_check(root: Path) -> list[Path]:
    """Return project Markdown files, excluding runtime and ignored notes."""
    ignored_root_names = ignored_root_markdown_names(root)
    return [
        path for path in sorted(root.rglob("*.md"))
        if not any(part in SKIP_DIRECTORIES for part in path.parts)
        and not (path.parent == root and path.name in ignored_root_names)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--noout",
        action="store_true",
        help="Suppress normal output; preserve the exit code",
    )
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from llm_gym.shared.settings import load_parameters
    try:
        load_parameters()
    except (OSError, ValueError) as exc:
        print(f"Global parameter validation failed: {exc}", file=sys.stderr)
        return 1

    root = Path(__file__).resolve().parents[1]
    missing = []
    for path in markdown_files_to_check(root):
        if not RULES_LINK.search(path.read_text(encoding="utf-8")):
            missing.append(path.relative_to(root))

    if missing:
        if not args.noout:
            print("Markdown files missing a PROJECT_RULES.md link:")
            for path in missing:
                print(f"- {path}")
        return 1

    if not args.noout:
        print("All project Markdown files reference PROJECT_RULES.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
