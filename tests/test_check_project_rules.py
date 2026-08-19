import tempfile
import unittest
from pathlib import Path

from scripts.check_project_rules import (REVIEW_ONLY, check_rule_6_no_secrets,
                                         check_rule_27_no_pinned_registry_values,
                                         check_rule_31_arm_specific_output_paths,
                                         check_rule_7_markdown_links)


def _write(root: Path, relative: str, body: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class PrecisionTests(unittest.TestCase):
    """A checker that reports false positives gets ignored, and then so does the
    rule behind it. Its first pass over this repo was 20% precise; these pin the
    two distinctions it was missing.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_version_the_test_supplied_may_be_asserted(self):
        """Round-tripping an argument is safe — nothing outside can move it."""
        _write(self.root, "tests/test_thing.py",
               'def test_round_trip():\n'
               '    report = run(prompt_version="synthesis-v4")\n'
               '    assert report["prompt_version"] == "synthesis-v4"\n')
        self.assertEqual(check_rule_27_no_pinned_registry_values(self.root), [])

    def test_a_version_the_test_never_supplied_is_flagged(self):
        """Asserting the registry default breaks when the registry advances."""
        _write(self.root, "tests/test_thing.py",
               'def test_default():\n'
               '    assert render()["prompt_version"] == "synthesis-v7"\n')
        findings = check_rule_27_no_pinned_registry_values(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("synthesis-v7", findings[0])

    def test_supplied_versions_do_not_leak_across_test_functions(self):
        """One function supplying a version must not licence the next one."""
        _write(self.root, "tests/test_thing.py",
               'def test_one():\n'
               '    run(prompt_version="synthesis-v4")\n'
               'def test_two():\n'
               '    assert render()["prompt_version"] == "synthesis-v4"\n')
        self.assertEqual(len(check_rule_27_no_pinned_registry_values(self.root)), 1)

    def test_a_model_flag_with_a_literal_default_is_not_a_provider_arm(self):
        """--model small is a Whisper size, not a provider selection."""
        _write(self.root, "scripts/ingest_thing.py",
               'parser.add_argument("--output", default="data/ingestion")\n'
               'parser.add_argument("--model", default="small")\n')
        self.assertEqual(check_rule_31_arm_specific_output_paths(self.root), [])

    def test_an_environment_derived_model_flag_is_a_provider_arm(self):
        _write(self.root, "scripts/run_thing.py",
               'parser.add_argument("--output", default="data/answer.json")\n'
               'parser.add_argument("--model", default=os.environ.get("AGENT_MODEL", ""))\n')
        findings = check_rule_31_arm_specific_output_paths(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("--output", findings[0])

    def test_an_arm_script_deriving_its_path_is_not_flagged(self):
        _write(self.root, "scripts/run_thing.py",
               'parser.add_argument("--output", default="")\n'
               'parser.add_argument("--provider-prefix", default="AGENT")\n')
        self.assertEqual(check_rule_31_arm_specific_output_paths(self.root), [])

    def test_a_credential_literal_is_found_in_source(self):
        _write(self.root, "llm_gym/leaky.py", 'KEY = "sk-abcdefghijklmnopqrstuvwxyz012345"\n')
        findings = check_rule_6_no_secrets(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("leaky.py", findings[0])

    def test_a_filled_in_example_file_is_also_a_leak(self):
        """A committed .env.example with a real value is the same disclosure.

        This file was originally exempt, and mutation testing showed the
        exemption was dead: the scan never reached the suffix at all.
        """
        _write(self.root, ".env.example",
               'AGENT_API_KEY="sk-zyxwvutsrqponmlkjihgfedcba543210"\n')
        findings = check_rule_6_no_secrets(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn(".env.example", findings[0])

    def test_an_empty_example_file_is_clean(self):
        _write(self.root, ".env.example", 'AGENT_API_KEY=\nAGENT_BASE_URL=\n')
        self.assertEqual(check_rule_6_no_secrets(self.root), [])

    def test_an_ignored_personal_note_is_not_project_documentation(self):
        _write(self.root, ".gitignore", ".notes.md\n")
        _write(self.root, ".notes.md", "personal review without project links\n")
        _write(self.root, "README.md", "[Rules](PROJECT_RULES.md)\n")
        self.assertEqual(check_rule_7_markdown_links(self.root), [])


class HonestCoverageTests(unittest.TestCase):
    def test_unenforceable_rules_are_named_rather_than_omitted(self):
        """Silence about what is unchecked reads as compliance."""
        self.assertIn(28, REVIEW_ONLY)
        self.assertIn(33, REVIEW_ONLY)
        self.assertTrue(all(text.strip() for text in REVIEW_ONLY.values()))


if __name__ == "__main__":
    unittest.main()
