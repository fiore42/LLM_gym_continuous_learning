import json
import os
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError

from llm_gym.sources.x_api import XApiError, discover_user_posts, discover_user_posts_with_includes, lookup_posts_with_includes, resolve_user_id
from llm_gym.sources.x_api import _request_json


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode()


class XApiTests(unittest.TestCase):
    def test_looks_up_existing_posts_in_batches(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        os.environ["X_API_BEARER_TOKEN"] = "test-token"
        try:
            def opener(request, timeout=30):
                self.assertIn("ids=1%2C2", request.full_url)
                return _Response({"data": [{"id": "1"}, {"id": "2"}], "includes": {"media": []}})
            posts, includes = lookup_posts_with_includes(["1", "2"], opener=opener)
            self.assertEqual([post["id"] for post in posts], ["1", "2"])
            self.assertEqual(includes, {"media": []})
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old
    def test_expands_media_and_returns_includes(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        os.environ["X_API_BEARER_TOKEN"] = "test-token"
        try:
            def opener(request, timeout=30):
                return _Response({
                    "data": [{"id": "1", "attachments": {"media_keys": ["1_1"]}}],
                    "includes": {"media": [{"media_key": "1_1", "type": "photo", "url": "https://pbs.example/a.jpg"}]},
                    "meta": {},
                })
            posts, includes = discover_user_posts_with_includes("@example", user_id="123", opener=opener)
            self.assertEqual(posts[0]["id"], "1")
            self.assertEqual(includes["media"][0]["media_key"], "1_1")
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old
    def test_user_context_token_is_used_when_supplied(self):
        calls = []
        def opener(request, timeout=30):
            calls.append(request.headers["Authorization"])
            return _Response({"data": [], "meta": {}})
        self.assertEqual(discover_user_posts("@example", user_id="123",
                                            access_token="user-token", opener=opener), [])
        self.assertEqual(calls, ["Bearer user-token"])

    def test_embedded_resource_authorization_error_is_typed(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        os.environ["X_API_BEARER_TOKEN"] = "test-token"
        def opener(request, timeout=30):
            return _Response({"errors": [{
                "detail": "not authorized",
                "type": "https://api.x.com/2/problems/not-authorized-for-resource",
            }]})
        try:
            with self.assertRaises(XApiError) as context:
                discover_user_posts("@example", user_id="123", opener=opener)
            self.assertEqual(
                context.exception.problem_type,
                "https://api.x.com/2/problems/not-authorized-for-resource",
            )
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old

    def test_cached_user_id_skips_username_lookup(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        calls = []
        try:
            os.environ["X_API_BEARER_TOKEN"] = "test-token"
            def opener(request, timeout=30):
                calls.append(request.full_url)
                if "/users/by/username/" in request.full_url:
                    raise AssertionError("cached lookup should not call username endpoint")
                return _Response({"data": [], "meta": {}})
            self.assertEqual(discover_user_posts("@example", user_id="123", opener=opener), [])
            self.assertEqual(len(calls), 1)
            self.assertIn("/2/users/123/tweets?", calls[0])
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old

    def test_http_errors_preserve_api_details(self):
        class ErrorResponse:
            def read(self):
                return b'{"errors":[{"detail":"invalid end_time"}]}'
            def close(self):
                pass
        def opener(request, timeout=30):
            raise HTTPError(request.full_url, 400, "bad", {}, ErrorResponse())
        with self.assertRaisesRegex(RuntimeError, "invalid end_time"):
            _request_json("https://api.x.com/test", "token", opener=opener)

    def test_resolves_user_paginates_and_excludes_non_main_posts(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        calls = []
        try:
            os.environ["X_API_BEARER_TOKEN"] = "test-token"
            def opener(request, timeout=30):
                calls.append(request.full_url)
                if "/users/by/username/" in request.full_url:
                    return _Response({"data": {"id": "123"}})
                if "pagination_token" in request.full_url:
                    return _Response({"data": [{"id": "2", "created_at": "2026-08-05T00:00:00Z"}], "meta": {}})
                return _Response({"data": [{"id": "1", "created_at": "2026-08-04T00:00:00Z"}], "meta": {"next_token": "next"}})
            result = discover_user_posts("@example", since=datetime(2026, 7, 30, tzinfo=timezone.utc), opener=opener)
            self.assertEqual([post["id"] for post in result], ["1", "2"])
            self.assertIn("exclude=replies%2Cretweets", calls[1])
            self.assertIn("pagination_token=next", calls[2])
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old

    def test_global_maximum_clamps_manifest_since_date(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        calls = []
        try:
            os.environ["X_API_BEARER_TOKEN"] = "test-token"
            def opener(request, timeout=30):
                calls.append(request.full_url)
                if "/users/by/username/" in request.full_url:
                    return _Response({"data": {"id": "123"}})
                return _Response({"data": [], "meta": {}})
            discover_user_posts("@example", since=datetime(2026, 7, 12, tzinfo=timezone.utc),
                                until=datetime(2026, 8, 6, tzinfo=timezone.utc), opener=opener)
            self.assertIn("start_time=2026-08-03T00%3A00%3A00Z", calls[1])
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old

    def test_exclusive_cursor_advances_by_one_second(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        calls = []
        try:
            os.environ["X_API_BEARER_TOKEN"] = "test-token"
            def opener(request, timeout=30):
                calls.append(request.full_url)
                if "/users/by/username/" in request.full_url:
                    return _Response({"data": {"id": "123"}})
                return _Response({"data": [], "meta": {}})
            discover_user_posts("@example", since=datetime(2026, 8, 6, 12, tzinfo=timezone.utc),
                                until=datetime(2026, 8, 6, 13, tzinfo=timezone.utc),
                                since_exclusive=True, opener=opener)
            self.assertIn("start_time=2026-08-06T12%3A00%3A01Z", calls[1])
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old

    def test_explicit_until_is_serialized_to_whole_utc_seconds(self):
        old = os.environ.get("X_API_BEARER_TOKEN")
        calls = []
        try:
            os.environ["X_API_BEARER_TOKEN"] = "test-token"
            def opener(request, timeout=30):
                calls.append(request.full_url)
                if "/users/by/username/" in request.full_url:
                    return _Response({"data": {"id": "123"}})
                return _Response({"data": [], "meta": {}})
            discover_user_posts("@example", until=datetime(2026, 8, 6, 12, 0, 0, 123456,
                                tzinfo=timezone.utc), opener=opener)
            self.assertIn("end_time=2026-08-06T12%3A00%3A00Z", calls[1])
        finally:
            if old is None:
                os.environ.pop("X_API_BEARER_TOKEN", None)
            else:
                os.environ["X_API_BEARER_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
