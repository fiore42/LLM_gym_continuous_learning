import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.show_recent_run_log import main


class StreamSeparationTests(unittest.TestCase):
    """Rule 3: the machine-readable result and the human summary are separate.

    Both used to go to stdout, which made the output unparseable — piping the
    log to jq failed on the trailing count line, so the one command that
    exposes cross-loop observability could not be read by any other tool.
    """

    EVENTS = [{"run_id": "r1", "loop_type": "DIGEST", "operation": "run_digest"},
              {"run_id": "r2", "loop_type": "DIGEST", "operation": "run_digest"}]

    def _run(self, extra_argv=()):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            for event in self.EVENTS:
                handle.write(json.dumps(event) + "\n")
            path = handle.name
        out, err = io.StringIO(), io.StringIO()
        argv = ["show_recent_run_log.py", "--log", path, "--all-runs", *extra_argv]
        try:
            with mock.patch.object(sys, "argv", argv), \
                 redirect_stdout(out), redirect_stderr(err):
                code = main()
        finally:
            Path(path).unlink()
        return code, out.getvalue(), err.getvalue()

    def test_stdout_is_parseable_json_on_its_own(self):
        code, out, _ = self._run()
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 2)

    def test_the_human_summary_goes_to_stderr(self):
        _, out, err = self._run()
        self.assertIn("Showing 2 event(s)", err)
        self.assertNotIn("Showing", out)

    def test_noout_suppresses_both_streams(self):
        _, out, err = self._run(["--noout"])
        self.assertEqual(out, "")
        self.assertEqual(err, "")
