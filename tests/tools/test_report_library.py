"""Regression checks for choosing the newest report without losing source entries."""

import unittest
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from tools.report_library.catalog import mark_latest_reports
from tools.report_library.translate_reports import reading_copy


def entry(path, title, modified, scope="report", localized=None):
    return {"path": path, "title": title, "modified_ns": modified,
            "scope": scope, "localized_titles": localized or {}}


class LatestReportsTest(unittest.TestCase):
    def test_newest_title_across_folders_and_future_updates(self):
        old = entry("old/report.html", "Cube report", 1)
        new = entry("new/report.html", "  CUBE   report ", 2)
        rows = [old, new]
        mark_latest_reports(rows)
        self.assertFalse(old["latest_report"])
        self.assertTrue(new["latest_report"])
        self.assertEqual(old["superseded_by"], new["path"])
        self.assertEqual(new["version_count"], 2)
        old["modified_ns"] = 3
        mark_latest_reports(rows)
        self.assertTrue(old["latest_report"])
        self.assertNotIn("superseded_by", old)
        self.assertEqual(len(rows), 2)

    def test_shared_language_aliases_join_transitively(self):
        rows = [entry("en.html", "Cube", 1, localized={"ja": "キューブ"}),
                entry("ja.html", "キューブ", 2, localized={"en": "The Cube"}),
                entry("new.html", "The Cube", 3)]
        mark_latest_reports(rows)
        self.assertEqual([row["latest_report"] for row in rows], [False, False, True])

    def test_archived_copy_does_not_replace_report(self):
        rows = [entry("report.html", "Cube", 1), entry("archive.html", "Cube", 9, "archive")]
        mark_latest_reports(rows)
        self.assertTrue(rows[0]["latest_report"])
        self.assertNotIn("latest_report", rows[1])

    def test_equal_time_is_deterministic_and_numbered_titles_stay_distinct(self):
        rows = [entry("b.html", "Phase 1", 1), entry("a.html", "Phase 1", 1),
                entry("c.html", "Phase 2", 1)]
        mark_latest_reports(rows)
        self.assertEqual([row["latest_report"] for row in rows], [False, True, True])

    def test_generated_toolbar_uses_native_links_protected_from_source_repair(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "reports/en/items/cube.html"
            original = root / "one-piece/projects/cube/report/index.html"
            result = reading_copy('<html lang="en"><body>Score: 0.95</body></html>',
                                  original, destination, "en", {}, "en")
            self.assertIn('href="../../ja/items/cube.html"', result)
            self.assertIn('href="../index.html"', result)
            self.assertNotIn("onclick=", result)
            self.assertIn(".filter(node=>!node.closest('#report-language-switch'))", result)
            self.assertIn("Score: 0.95", result)

    def test_command_builds_an_external_workspace_without_writing_package_data(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for version in ["old", "new"]:
                path = root / version / "report.html"
                path.parent.mkdir()
                path.write_text('<html lang="en"><title>Cube results</title><body>Evidence</body></html>')
                os.utime(path, (1 if version == "old" else 2,) * 2)
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
            result = subprocess.run([sys.executable, "-m", "tools.report_library",
                                     "--workspace", str(root), "build"], cwd=root,
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads((root / "reports/catalog.json").read_text())
            self.assertEqual(data["report_count"], 1)
            self.assertEqual(data["all_html_count"], 2)
            newest = next(row for row in data["entries"] if row["latest_report"])
            self.assertEqual(newest["path"], "new/report.html")
            self.assertTrue((root / "reports/en/index.html").is_file())
            self.assertTrue((root / "reports/ja/index.html").is_file())


if __name__ == "__main__":
    unittest.main()
