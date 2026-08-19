import unittest
from pathlib import Path

from llm_gym.sources.manifest import load_sources_markdown, unsupported_platforms


class ManifestTests(unittest.TestCase):
    def test_initial_youtube_manifest(self):
        path = Path(__file__).parents[1] / "config" / "SOURCES.md"
        manifest = load_sources_markdown(path)
        self.assertEqual(len(manifest["sources"]), 69)
        ibm = next(source for source in manifest["sources"] if source["handle"] == "@IBMTechnology")
        self.assertEqual(ibm["source_folder"], "source/youtube/IBMTechnology")

    def test_same_handle_can_be_tracked_on_multiple_platforms(self):
        path = Path(__file__).parents[1] / "config" / "SOURCES.md"
        sources = load_sources_markdown(path)["sources"]
        self.assertTrue(any(s["platform"] == "youtube" and s["handle"] == "@Google" for s in sources))
        self.assertTrue(any(s["platform"] == "x" and s["handle"] == "@Google" for s in sources))

    def test_unsupported_platforms_are_explicit(self):
        sources = [{"platform": "x", "handle": "@example"}, {"platform": "youtube", "handle": "@ok"}]
        self.assertEqual(unsupported_platforms(sources, {"youtube"})[0]["handle"], "@example")


if __name__ == "__main__":
    unittest.main()
