import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.check_environment_configuration as module
from scripts.check_environment_configuration import (main, missing_tools,
                                                     required_agent_environment, required_tools)


class EnvironmentChecksTests(unittest.TestCase):
    def test_x_only_does_not_require_youtube_downloader(self):
        tools = required_tools(
            {"x"},
            {"yt_dlp": "yt-dlp", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "whisper_script": "whisper"},
        )
        self.assertEqual(set(tools), {"ffmpeg", "ffprobe", "whisper_script"})

    def test_youtube_requires_downloader_but_not_x_tools(self):
        tools = required_tools(
            {"youtube"},
            {"yt_dlp": "yt-dlp", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe", "whisper_script": "whisper"},
        )
        self.assertEqual(set(tools), {"yt_dlp", "ffmpeg", "ffprobe", "whisper_script"})

    def test_agent_preflight_does_not_expose_or_require_secret_values(self):
        missing = required_agent_environment({"AGENT_PROVIDER": "anthropic", "AGENT_MODEL": "claude"})
        self.assertEqual(missing, ["ANTHROPIC_API_KEY"])

    def test_comparison_preflight_requires_both_models_and_keys(self):
        missing = required_agent_environment({"FRONTIER_PROVIDER": "anthropic"}, prefix="FRONTIER")
        self.assertEqual(set(missing), {"FRONTIER_MODEL", "FRONTIER_API_KEY"})


class ToolResolutionTests(unittest.TestCase):
    """A configured tool must be found from any working directory."""

    def test_relative_tool_path_resolves_against_project_root_not_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "whisper.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            self.assertEqual(missing_tools({"whisper_script": "tools/whisper.sh"}, root=root), [])
            self.assertEqual(missing_tools({"whisper_script": "tools/absent.sh"}, root=root),
                             ["whisper_script"])

    def test_a_command_on_path_needs_no_file_to_exist(self):
        self.assertEqual(missing_tools({"shell": "sh"}, root=Path("/nonexistent")), [])


class EnvironmentLoadOrderTests(unittest.TestCase):
    """.env must load before any setting is read.

    Tool paths are environment-overridable, so validating them first checks
    the packaged defaults and reports a correctly configured tool as missing.
    That is exactly what happened: WHISPER_SCRIPT was set in .env, and the
    check compared against the bare default from PARAMETERS.json instead.
    """

    def test_dotenv_is_loaded_before_tool_paths_are_read(self):
        calls = []

        def record(name, result):
            calls.append(name)
            return result

        with patch.object(module, "load_dotenv", lambda *a, **k: record("load_dotenv", None)), \
             patch.object(module, "tool_parameters", lambda: record("tool_parameters", {})), \
             patch.object(module, "load_parameters", lambda: None), \
             patch.object(module, "load_sources_markdown", lambda path: {"sources": []}), \
             patch("sys.argv", ["check_environment_configuration.py", "--noout"]):
            self.assertEqual(main(), 0)
        self.assertEqual(calls, ["load_dotenv", "tool_parameters"])


if __name__ == "__main__":
    unittest.main()
