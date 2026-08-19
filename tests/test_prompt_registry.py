import json
import tempfile
import unittest
from pathlib import Path

from llm_gym.agent.prompt_registry import load_prompt


class PromptRegistryTests(unittest.TestCase):
    def _write(self, root: Path, version: str, number: int) -> None:
        (root / f"{version}.json").write_text(json.dumps({
            "prompt_id": "test",
            "prompt_version": version,
            "version_number": number,
            "system_template": "system",
            "user_template": "{question}{evidence}{revision}",
            "revision_templates": {"revision_prefix": "", "fallback": "fallback",
                                    "validation_error": "error {error}",
                                    "failed_criteria": "criteria {criteria}"},
        }), encoding="utf-8")

    def test_latest_prompt_is_selected_by_explicit_version_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "v4", 4)
            self._write(root, "v5", 5)
            prompt = load_prompt(root=root)
            self.assertEqual(prompt.prompt_version, "v5")
            self.assertTrue(prompt.sha256)

    def test_explicit_prompt_version_can_reproduce_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, "v4", 4)
            self._write(root, "v5", 5)
            self.assertEqual(load_prompt(root=root, version="v4").prompt_version, "v4")
