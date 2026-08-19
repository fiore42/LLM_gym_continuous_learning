import os
import tempfile
import unittest
from pathlib import Path

from llm_gym.sources import x as x_module
from llm_gym.sources.x_api import XApiError
from llm_gym.sources.x import ingest_x_source


class XIngestionTests(unittest.TestCase):
    def test_resource_authorization_retries_with_user_context_token(self):
        old = os.environ.get("X_API_USER_ACCESS_TOKEN")
        calls = []
        try:
            os.environ["X_API_USER_ACCESS_TOKEN"] = "user-token"
            original_resolve = x_module.resolve_user_id
            original_discover = x_module.discover_user_posts_with_includes
            x_module.resolve_user_id = lambda handle: "33836629"

            def discover(*args, **kwargs):
                calls.append(kwargs.get("access_token"))
                if kwargs.get("access_token") is None:
                    raise XApiError(
                        "protected",
                        problem_type="https://api.x.com/2/problems/not-authorized-for-resource",
                    )
                return ([{"id": "1", "created_at": "2026-08-06T00:00:00Z", "text": "hello"}], {})

            x_module.discover_user_posts_with_includes = discover
            try:
                with tempfile.TemporaryDirectory() as directory:
                    result = ingest_x_source(
                        "https://x.com/example",
                        Path(directory) / "example",
                        handle="@example",
                        source_registry_path=Path(directory) / "registry.sqlite3",
                    )
            finally:
                x_module.resolve_user_id = original_resolve
                x_module.discover_user_posts_with_includes = original_discover
            self.assertEqual(result.status, "COMPLETED")
            self.assertEqual(result.failure_count, 0)
            self.assertEqual(result.handled_fallback_count, 1)
            self.assertEqual(result.warnings, ("USED_USER_CONTEXT_AUTH",))
            self.assertEqual(calls, [None, "user-token"])
        finally:
            if old is None:
                os.environ.pop("X_API_USER_ACCESS_TOKEN", None)
            else:
                os.environ["X_API_USER_ACCESS_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
