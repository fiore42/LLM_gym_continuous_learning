import os
import tempfile
import unittest
from pathlib import Path

from llm_gym.shared.config import has_env_value, load_dotenv
from llm_gym.shared.settings import estimate_x_api_cost, tool_parameters, x_parameters


class ConfigTests(unittest.TestCase):
    def test_global_window_and_x_policy_are_loaded(self):
        from llm_gym.shared.settings import ingestion_parameters
        self.assertEqual(ingestion_parameters()["default_window_days"], 3)
        self.assertEqual(ingestion_parameters()["max_window_days"], 3)
        self.assertFalse(x_parameters()["include_replies"])
        self.assertFalse(x_parameters()["include_retweets"])
        self.assertEqual(estimate_x_api_cost(post_reads=945, user_lookups=19), 4.915)
    def test_tool_paths_can_be_overridden_without_editing_project_config(self):
        old = os.environ.get("WHISPER_SCRIPT")
        try:
            os.environ["WHISPER_SCRIPT"] = "/tmp/test-whisper.sh"
            self.assertEqual(tool_parameters()["whisper_script"], "/tmp/test-whisper.sh")
        finally:
            if old is None:
                os.environ.pop("WHISPER_SCRIPT", None)
            else:
                os.environ["WHISPER_SCRIPT"] = old

    def test_ffprobe_path_can_be_overridden(self):
        old = os.environ.get("FFPROBE_PATH")
        try:
            os.environ["FFPROBE_PATH"] = "/tmp/test-ffprobe"
            self.assertEqual(tool_parameters()["ffprobe"], "/tmp/test-ffprobe")
        finally:
            if old is None:
                os.environ.pop("FFPROBE_PATH", None)
            else:
                os.environ["FFPROBE_PATH"] = old

    def test_loads_values_without_overriding_existing_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "# comment\nYOUTUBE_API_KEY='from-file'\nPROJECT_MODE=local\n",
                encoding="utf-8",
            )
            old_key = os.environ.get("YOUTUBE_API_KEY")
            old_mode = os.environ.get("PROJECT_MODE")
            try:
                os.environ.pop("YOUTUBE_API_KEY", None)
                os.environ.pop("PROJECT_MODE", None)
                self.assertEqual(load_dotenv(env_file), env_file)
                self.assertEqual(os.environ["YOUTUBE_API_KEY"], "from-file")
                self.assertTrue(has_env_value("YOUTUBE_API_KEY"))
            finally:
                if old_key is None:
                    os.environ.pop("YOUTUBE_API_KEY", None)
                else:
                    os.environ["YOUTUBE_API_KEY"] = old_key
                if old_mode is None:
                    os.environ.pop("PROJECT_MODE", None)
                else:
                    os.environ["PROJECT_MODE"] = old_mode


if __name__ == "__main__":
    unittest.main()
