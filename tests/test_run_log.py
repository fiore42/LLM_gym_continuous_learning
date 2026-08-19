import json
import tempfile
import unittest
from pathlib import Path

from llm_gym.shared.run_log import RunLogger


class RunLogTests(unittest.TestCase):
    def test_writes_structured_event_and_never_stores_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run-log.jsonl"
            logger = RunLogger(path, run_id="run-test")
            logger.event(
                operation="test",
                stage="call",
                parameters={
                    "api_key": "secret-api-key",
                    "command": ["tool", "--password", "secret-password"],
                },
                output={"authorization": "Bearer secret-token", "ok": True},
            )

            record = json.loads(path.read_text(encoding="utf-8"))
            serialized = path.read_text(encoding="utf-8")

        self.assertEqual(record["run_id"], "run-test")
        self.assertEqual(record["parameters"]["api_key"], "[REDACTED]")
        self.assertEqual(record["parameters"]["command"][2], "[REDACTED]")
        self.assertNotIn("secret-api-key", serialized)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("secret-token", serialized)


if __name__ == "__main__":
    unittest.main()
