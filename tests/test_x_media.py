import tempfile
import unittest
from pathlib import Path

from llm_gym.sources.x_media import persist_post_assets


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class _Response:
    def __init__(self, body, content_type):
        self.body = body
        self.headers = _Headers({"Content-Type": content_type, "Content-Length": str(len(body))})
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        if not self.body:
            return b""
        body, self.body = self.body, b""
        return body


class XMediaTests(unittest.TestCase):
    def test_downloads_media_and_linked_document(self):
        def opener(request, timeout=30):
            if request.full_url.endswith(".pdf"):
                return _Response(b"%PDF-test", "application/pdf")
            return _Response(b"image-bytes", "image/jpeg")

        post = {
            "id": "123",
            "attachments": {"media_keys": ["13_123"]},
            "entities": {"urls": [{"expanded_url": "https://example.test/brief.pdf"}]},
        }
        includes = {"media": [{
            "media_key": "13_123", "type": "photo", "url": "https://pbs.test/image.jpg"
        }]}
        with tempfile.TemporaryDirectory() as directory:
            media_count, document_count, warnings = persist_post_assets(
                Path(directory), post, includes, opener=opener
            )
            self.assertEqual((media_count, document_count, warnings), (1, 1, ()))
            self.assertTrue((Path(directory) / "media" / "13_123.jpg").exists())
            self.assertTrue((Path(directory) / "documents" / "1.pdf").exists())
            self.assertTrue((Path(directory) / "media" / "13_123.json").exists())


if __name__ == "__main__":
    unittest.main()
