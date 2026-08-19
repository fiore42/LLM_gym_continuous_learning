#!/usr/bin/env python3
"""Enforce the machine-checkable subset of PROJECT_RULES.md.

A rule nothing checks becomes decoration. Rule 7 is the only rule in this
project that never drifted, and it is the only one that had a script behind it;
meanwhile Rule 31's requirement was violated by an evaluation entry point for
months without anyone noticing.

This script does not claim to enforce every rule. It enforces the ones a
program can decide, and it prints the ones it cannot so the gap stays visible
instead of being mistaken for compliance.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRECTORIES = {".git", ".venv", ".pytest_cache", "__pycache__", "data", "source"}

# Rules a program can decide. Anything not listed here needs a human, and is
# reported under REVIEW_ONLY rather than silently omitted.
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\b(?:API_KEY|BEARER_TOKEN|ACCESS_TOKEN|SECRET)\s*=\s*['\"][A-Za-z0-9_\-]{16,}"),
)

REVIEW_ONLY = {
    0: "deterministic code owns control flow; models only synthesise",
    5: "changes ship as small reversible stages",
    18: "every fix adds a regression test covering the failure",
    24: "authoritative and derived data are declared and kept distinct",
    28: "each new test was mutation-checked (verifiable only in the commit message)",
    30: "a comparison guards every field that can change its result",
    32: "loops sharing a failure share its handling",
    33: "measured claims carry counts, an artifact path, and a provisional label",
}


def _ignored_root_names(root: Path) -> set[str]:
    """Return exact root-level names excluded by the repository ignore file."""
    ignore_file = root / ".gitignore"
    if not ignore_file.is_file():
        return set()
    names: set[str] = set()
    for raw in ignore_file.read_text(encoding="utf-8").splitlines():
        rule = raw.strip()
        if (not rule or rule.startswith(("#", "!")) or "/" in rule
                or any(char in rule for char in "*?[]")):
            continue
        names.add(rule)
    return names


def _tracked_files(root: Path, suffix: str) -> list[Path]:
    ignored_root_names = _ignored_root_names(root)
    return [p for p in sorted(root.rglob(f"*{suffix}"))
            if not any(part in SKIP_DIRECTORIES for part in p.parts)
            and not (p.parent == root and p.name in ignored_root_names)]


def check_rule_6_no_secrets(root: Path) -> list[str]:
    """Credentials must never appear in tracked source, docs, or config."""
    findings = []
    own_tests = f"test_{Path(__file__).stem}.py"
    for path in (_tracked_files(root, ".py") + _tracked_files(root, ".md")
                 + _tracked_files(root, ".json") + _tracked_files(root, ".example")):
        # This checker and its tests carry credential-shaped fixtures on purpose.
        if path.name in {Path(__file__).name, own_tests}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"Rule 6: possible credential literal in {path.relative_to(root)}")
                break
    return findings


def check_rule_27_no_pinned_registry_values(root: Path) -> list[str]:
    """Tests must not assert a registry value they did not themselves supply.

    Asserting a version passed in as an argument is a round-trip check and is
    safe: nothing outside the test can move it. Asserting one the test never
    supplied means asserting the registry default, which is the shape that
    failed twice — the test broke when the registry advanced while nothing was
    wrong.

    Scoped per test function, because a literal supplied at the top of a
    function legitimises an assertion further down it.
    """
    findings = []
    literal = re.compile(r"(?:synthesis|verification)-v\d+")
    for path in _tracked_files(root / "tests", ".py"):
        # This checker's own tests embed violating code as fixture strings.
        if path.name == f"test_{Path(__file__).stem}.py":
            continue
        supplied: set[str] = set()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(?:def |class )", line):
                supplied = set()
            found = set(literal.findall(line))
            if "assert" not in line:
                supplied |= found
                continue
            unsupplied = found - supplied
            for version in sorted(unsupplied):
                findings.append(
                    f"Rule 27: {path.relative_to(root)}:{number} asserts {version}, which the "
                    f"test never supplied; assert PROMPT_VERSION instead")
    return findings


def check_rule_31_arm_specific_output_paths(root: Path) -> list[str]:
    """A script selecting an arm must not default to a constant output path.

    Two arms sharing a default path overwrite each other, and the surviving
    artifact reads as authoritative.
    """
    findings = []
    # A provider arm is selected by --provider-prefix, or by a --model whose
    # default is empty or environment-derived. A --model with a literal default
    # is something else — the Whisper model size, for instance.
    arm_flag = re.compile(
        r'add_argument\(\s*"--provider-prefix"'
        r'|add_argument\(\s*"--(?:model|prompt-version)"\s*,\s*default\s*=\s*(?:""|None|os\.environ)')
    constant_output = re.compile(
        r'add_argument\(\s*"--(output|output-dir|state|cache-dir)"\s*,\s*default\s*=\s*"[^"]+"')
    for path in _tracked_files(root / "scripts", ".py"):
        text = path.read_text(encoding="utf-8")
        if not arm_flag.search(text):
            continue
        for match in constant_output.finditer(text):
            findings.append(
                f"Rule 31: {path.relative_to(root)} selects an arm but defaults "
                f"--{match.group(1)} to a constant path; derive it from the arm")
    return findings


def check_rule_7_markdown_links(root: Path) -> list[str]:
    """Every project Markdown file links to PROJECT_RULES.md."""
    rules_link = re.compile(r"\]\([^)]*PROJECT_RULES\.md\)")
    return [f"Rule 7: {path.relative_to(root)} does not link to PROJECT_RULES.md"
            for path in _tracked_files(root, ".md")
            if not rules_link.search(path.read_text(encoding="utf-8"))]


def check_rule_28_mutation_note(root: Path, *, revision: str = "HEAD") -> list[str]:
    """A commit touching tests must record the mutations that were run.

    Rule 28 cannot be verified from the tree — a test that was never made to
    fail looks identical to one that was. The commit message is the only
    durable record, so that is what gets checked.
    """
    try:
        changed = subprocess.run(["git", "show", "--name-only", "--format=", revision],
                                 cwd=root, capture_output=True, text=True, timeout=30)
        message = subprocess.run(["git", "log", "-1", "--format=%B", revision],
                                 cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if changed.returncode or message.returncode:
        return []
    touches_tests = any(line.startswith("tests/") for line in changed.stdout.splitlines())
    mentions = re.search(r"mutat|survived|broke one|deliberately break",
                         message.stdout, re.IGNORECASE)
    if touches_tests and not mentions:
        return [f"Rule 28: {revision} changes tests without recording a mutation check"]
    return []


CHECKS = (check_rule_6_no_secrets, check_rule_7_markdown_links,
          check_rule_27_no_pinned_registry_values,
          check_rule_31_arm_specific_output_paths)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noout", action="store_true", help="Suppress normal output")
    parser.add_argument("--check-last-commit", action="store_true",
                        help="Also apply the Rule 28 commit-message check to HEAD")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    findings: list[str] = []
    for check in CHECKS:
        findings.extend(check(root))
    if args.check_last_commit:
        findings.extend(check_rule_28_mutation_note(root))

    if not args.noout:
        enforced = len(CHECKS) + (1 if args.check_last_commit else 0)
        print(f"Rules enforced mechanically: {enforced}")
        if findings:
            print("\nViolations:")
            for finding in findings:
                print(f"- {finding}")
        else:
            print("No violations found.")
        print(f"\nRequires human review ({len(REVIEW_ONLY)} rules) — not checked above:")
        for number, summary in sorted(REVIEW_ONLY.items()):
            print(f"- Rule {number}: {summary}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
