import tempfile
import unittest
from pathlib import Path

from scripts.check_markdown_rule_links import (ignored_root_markdown_names,
                                                markdown_files_to_check)


class IgnoredMarkdownTests(unittest.TestCase):
    def test_only_exact_ignored_root_markdown_names_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_text(
                "# personal files\n.notes.md\n*.generated.md\n"
                "docs/private.md\n!README.md\nplain.txt\n",
                encoding="utf-8",
            )
            self.assertEqual(ignored_root_markdown_names(root), {".notes.md"})

    def test_discovery_skips_ignored_notes_but_keeps_project_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_text(".notes.md\n", encoding="utf-8")
            (root / ".notes.md").write_text("personal", encoding="utf-8")
            (root / "README.md").write_text("project", encoding="utf-8")
            docs = root / "docs"
            docs.mkdir()
            (docs / "DESIGN.md").write_text("project", encoding="utf-8")
            data = root / "data"
            data.mkdir()
            (data / "run.md").write_text("runtime", encoding="utf-8")

            self.assertEqual(
                [path.relative_to(root).as_posix()
                 for path in markdown_files_to_check(root)],
                ["README.md", "docs/DESIGN.md"],
            )


if __name__ == "__main__":
    unittest.main()
