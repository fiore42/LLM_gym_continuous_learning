import json
import tempfile
import unittest
from pathlib import Path

from llm_gym.shared.settings import PARAMETERS_PATH, load_parameters


def _with_agent(**overrides) -> Path:
    """A copy of the real parameters file with the agent block adjusted."""
    payload = json.loads(Path(PARAMETERS_PATH).read_text(encoding="utf-8"))
    payload["agent"].update(overrides)
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    handle.write(json.dumps(payload))
    handle.close()
    return Path(handle.name)


class AgentLimitValidationTests(unittest.TestCase):
    """Every agent limit is rejected at load rather than at first use.

    A limit that only fails when a run reaches it fails after money has been
    spent, and reads as a provider problem rather than a configuration one.
    """

    def test_the_committed_parameters_file_loads(self):
        self.assertIn("agent", load_parameters())

    def test_a_non_positive_output_ceiling_is_rejected(self):
        for value in (0, -1):
            with self.subTest(value=value):
                path = _with_agent(max_output_tokens=value)
                self.addCleanup(path.unlink)
                with self.assertRaisesRegex(ValueError, "max_output_tokens"):
                    load_parameters(path)

    def test_a_missing_output_ceiling_is_rejected(self):
        payload = json.loads(Path(PARAMETERS_PATH).read_text(encoding="utf-8"))
        del payload["agent"]["max_output_tokens"]
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        handle.write(json.dumps(payload))
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            load_parameters(Path(handle.name))

    def test_a_non_integer_output_ceiling_is_rejected(self):
        path = _with_agent(max_output_tokens=4000.5)
        self.addCleanup(path.unlink)
        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            load_parameters(path)


if __name__ == "__main__":
    unittest.main()
